"""
Render Pipeline Module.

This module orchestrates the complete video rendering pipeline:
1. Audio BPM analysis
2. Visual clip generation
3. FFmpeg concatenation
4. Audio attachment
5. Final output writing
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Tuple

from moviepy import VideoFileClip, AudioFileClip  # type: ignore

from audiogiphy.audio_analysis import analyze_bpm_per_second, analyze_global_bpm
from audiogiphy.visual_builder import build_visual_track, _subclip, _set_duration, _set_audio, _add_watermark
from audiogiphy.config import DEFAULT_FPS, DEFAULT_RESOLUTION, CHECKPOINTS_DIR
from audiogiphy.lyrics_overlays import extract_lyric_anchors, map_anchors_to_seconds, build_karaoke_mapping

__all__ = ["render_video"]

logger = logging.getLogger("audiogiphy.render_pipeline")


def render_video(
    audio_path: str,
    video_folder: str,
    duration_seconds: int,
    output_path: str,
    resolution: Tuple[int, int] = DEFAULT_RESOLUTION,
    seed: int | None = None,
    lyrics_json_path: str | None = None,
    karaoke_mode: bool = False,
) -> None:
    """
    Render a complete video from audio and video clips.
    
    This is the main entry point for the rendering pipeline. It:
    1. Analyzes the audio to get BPM timeline and base BPM
    2. Builds 1-second visual clips synced to BPM
    3. Concatenates clips using ffmpeg (memory-efficient)
    4. Attaches the original audio track
    5. Writes the final output video
    
    The pipeline is designed to be memory-efficient, handling long videos
    (e.g., 48+ minutes) without running out of memory by:
    - Writing clips to disk immediately
    - Using ffmpeg stream copy for concatenation (no re-encoding)
    - Only loading one VideoFileClip at a time (the final concatenated video)
    
    Args:
        audio_path: Path to input audio file
        video_folder: Path to folder containing source MP4 files
        duration_seconds: Duration of output video in seconds
        output_path: Path for output video file
        resolution: Target resolution (width, height), default from config
        seed: Random seed for reproducible results (optional)
        lyrics_json_path: Optional path to lyrics JSON file from detect-lyrics
        karaoke_mode: If True, display all words per second (karaoke mode). If False, display phrase-ending words (default: False)
        
    Raises:
        FileNotFoundError: If audio file doesn't exist
        RuntimeError: If ffmpeg is not found or concatenation fails
        ValueError: If number of generated clips doesn't match duration
    """
    import random
    import numpy as np
    import librosa
    
    logger.info("Starting video render pipeline")
    
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)
        logger.info(f"Random seed set to: {seed}")
    
    # Check audio duration and clamp if needed
    audio_duration = librosa.get_duration(path=audio_path)
    if audio_duration < duration_seconds:
        logger.warning(f"Audio duration ({audio_duration:.1f}s) is shorter than requested ({duration_seconds}s). Clamping to audio duration.")
        duration_seconds = int(audio_duration)
    
    # Step 1: Analyze audio BPM
    logger.info("Analyzing audio BPM")
    bpm_values = analyze_bpm_per_second(audio_path, duration_seconds)
    base_bpm = analyze_global_bpm(audio_path, duration_seconds)
    logger.info(f"Base BPM: {base_bpm:.1f}")
    
    # Process lyrics if provided
    lyrics_mapping = None
    karaoke_mapping = None
    if lyrics_json_path:
        if karaoke_mode:
            # Karaoke mode: display all words per second
            logger.info("Processing lyrics for karaoke mode")
            logger.info(f"Lyrics JSON path: {lyrics_json_path}")
            try:
                karaoke_mapping = build_karaoke_mapping(lyrics_json_path, duration_seconds)
                logger.info(f"Built karaoke mapping: {len(karaoke_mapping)} seconds have lyrics")
                if karaoke_mapping:
                    sample_seconds = sorted(karaoke_mapping.keys())[:10]
                    logger.debug(f"Sample karaoke mappings: {[(s, karaoke_mapping[s][:30] + '...' if len(karaoke_mapping[s]) > 30 else karaoke_mapping[s]) for s in sample_seconds]}")
            except Exception as e:
                logger.warning(f"Failed to load lyrics for karaoke mode: {e}, continuing without lyric overlays", exc_info=True)
                karaoke_mapping = None
        else:
            # Phrase-ending mode: display phrase-ending words only
            logger.info("Processing lyrics for phrase-ending overlay")
            logger.info(f"Lyrics JSON path: {lyrics_json_path}")
            try:
                anchors = extract_lyric_anchors(lyrics_json_path)
                logger.info(f"Extracted {len(anchors)} lyric anchors")
                if anchors:
                    anchor_list = [(a['word'], f"{a['time_end_sec']:.2f}s") for a in anchors]
                    logger.debug(f"Anchors: {anchor_list}")
                
                lyrics_mapping = map_anchors_to_seconds(anchors, duration_seconds)
                logger.info(f"Mapped {len(lyrics_mapping)} lyric overlays to seconds")
                if lyrics_mapping:
                    mapped_seconds = sorted(lyrics_mapping.keys())
                    logger.info(f"Lyrics will appear at seconds: {mapped_seconds}")
                    logger.debug(f"Full mapping: {dict(sorted(lyrics_mapping.items()))}")
            except Exception as e:
                logger.warning(f"Failed to load lyrics: {e}, continuing without lyric overlays", exc_info=True)
                lyrics_mapping = None
    
    # Step 2: Build visual track (generates 1-second clips on disk)
    logger.info("Generating 1s clips")
    checkpoint_dir = Path(output_path).parent / CHECKPOINTS_DIR / Path(output_path).stem
    clip_paths = build_visual_track(
        video_folder=video_folder,
        bpm_values=bpm_values,
        duration_seconds=duration_seconds,
        target_resolution=resolution,
        base_bpm=base_bpm,
        checkpoint_dir=checkpoint_dir,
        lyrics_mapping=lyrics_mapping,
        karaoke_mapping=karaoke_mapping,
    )

    if len(clip_paths) != duration_seconds:
        raise ValueError(f"Expected {duration_seconds} clips, got {len(clip_paths)}")

    # Step 3: Concatenate clips using ffmpeg (memory-efficient)
    visuals_raw_path = checkpoint_dir / "visuals_raw.mp4"
    concat_list_path = checkpoint_dir / "concat_list.txt"

    # Create ffmpeg concat list file
    with open(concat_list_path, 'w') as f:
        for clip_path in clip_paths:
            abs_path = clip_path.resolve()
            f.write(f"file '{abs_path}'\n")

    # Use ffmpeg concat demuxer (stream copy, no re-encoding = fast and memory-efficient)
    ffmpeg_logger = logging.getLogger("ffmpeg")
    try:
        ffmpeg_logger.info("Concatenating clips")
        subprocess.run(
            [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list_path),
                "-c", "copy",  # Stream copy, no re-encoding
                str(visuals_raw_path),
                "-y",  # Overwrite output file
            ],
            check=True,
            capture_output=True,
        )
        ffmpeg_logger.info("Concatenation completed")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else "Unknown error"
        raise RuntimeError(f"ffmpeg concat failed: {error_msg}") from e
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Please install ffmpeg to use this script.")

    # Step 4: Load audio and attach to video
    logger.info("Attaching audio")
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    audio = _subclip(AudioFileClip(audio_path), 0, duration_seconds)

    logger.info("Writing final output")
    # Load the concatenated video once (only one VideoFileClip in memory)
    visual = VideoFileClip(str(visuals_raw_path), audio=False)

    # Add watermark to the final video (applied once to entire video)
    logger.info("Adding watermark overlay")
    visual = _add_watermark(visual, resolution)

    # Attach audio and write final output
    final = _set_duration(_set_audio(visual, audio), duration_seconds)
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=DEFAULT_FPS,
        threads=os.cpu_count() or 4,
        preset="medium",
    )

    # Cleanup
    visual.close()
    audio.close()
    final.close()

    logger.info("Render complete!")
    logger.info(f"Final output: {output_path}")
    logger.info(f"Checkpoint directory: {checkpoint_dir} (can be deleted after verification)")

