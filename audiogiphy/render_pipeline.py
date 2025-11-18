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
from pathlib import Path
from typing import Tuple

from moviepy import VideoFileClip, AudioFileClip  # type: ignore

from audiogiphy.audio_analysis import analyze_bpm_per_second, analyze_global_bpm
from audiogiphy.visual_builder import build_visual_track, _subclip, _set_duration, _set_audio


def render_video(
    audio_path: str,
    video_folder: str,
    duration_seconds: int,
    output_path: str,
    resolution: Tuple[int, int] = (1080, 1920),
    seed: int | None = None,
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
        resolution: Target resolution (width, height), default (1080, 1920)
        seed: Random seed for reproducible results (optional)
        
    Raises:
        FileNotFoundError: If audio file doesn't exist
        RuntimeError: If ffmpeg is not found or concatenation fails
        ValueError: If number of generated clips doesn't match duration
    """
    import random
    import numpy as np
    
    print("[render] Starting video render pipeline", flush=True)
    
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)
        print(f"[render] Random seed set to: {seed}", flush=True)
    
    # Step 1: Analyze audio BPM
    print("[render] Analyzing audio BPM...", flush=True)
    bpm_values = analyze_bpm_per_second(audio_path, duration_seconds)
    base_bpm = analyze_global_bpm(audio_path, duration_seconds)
    print(f"[render] Base BPM: {base_bpm:.1f}", flush=True)
    
    # Step 2: Build visual track (generates 1-second clips on disk)
    print("[render] Building visual track...", flush=True)
    checkpoint_dir = Path(output_path).parent / "checkpoints" / Path(output_path).stem
    clip_paths = build_visual_track(
        video_folder=video_folder,
        bpm_values=bpm_values,
        duration_seconds=duration_seconds,
        target_resolution=resolution,
        base_bpm=base_bpm,
        checkpoint_dir=checkpoint_dir,
    )

    if len(clip_paths) != duration_seconds:
        raise ValueError(f"Expected {duration_seconds} clips, got {len(clip_paths)}")

    # Step 3: Concatenate clips using ffmpeg (memory-efficient)
    print("[render] Concatenating clips with ffmpeg...", flush=True)
    visuals_raw_path = checkpoint_dir / "visuals_raw.mp4"
    concat_list_path = checkpoint_dir / "concat_list.txt"

    # Create ffmpeg concat list file
    with open(concat_list_path, 'w') as f:
        for clip_path in clip_paths:
            abs_path = clip_path.resolve()
            f.write(f"file '{abs_path}'\n")

    # Use ffmpeg concat demuxer (stream copy, no re-encoding = fast and memory-efficient)
    try:
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
        print(f"[render] FFmpeg concatenation completed: {visuals_raw_path}", flush=True)
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else "Unknown error"
        raise RuntimeError(f"ffmpeg concat failed: {error_msg}") from e
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Please install ffmpeg to use this script.")

    # Step 4: Load audio and attach to video
    print("[render] Loading and trimming audio...", flush=True)
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    audio = _subclip(AudioFileClip(audio_path), 0, duration_seconds)

    print("[render] Attaching audio and writing final output...", flush=True)
    # Load the concatenated video once (only one VideoFileClip in memory)
    visual = VideoFileClip(str(visuals_raw_path), audio=False)

    # Attach audio and write final output
    final = _set_duration(_set_audio(visual, audio), duration_seconds)
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=30,
        threads=os.cpu_count() or 4,
        preset="medium",
    )

    # Cleanup
    visual.close()
    audio.close()
    final.close()

    print("[render] Render complete!", flush=True)
    print(f"[render] Final output: {output_path}", flush=True)
    print(f"[render] Checkpoint directory: {checkpoint_dir} (can be deleted after verification)", flush=True)

