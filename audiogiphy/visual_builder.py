"""
Visual Builder Module.

This module handles building the visual track by processing video clips,
applying BPM-based speed changes, resizing, and writing 1-second segments to disk.
"""

from typing import List, Tuple, Set
import json
import random

import numpy as np
from pathlib import Path
from tqdm import tqdm
from moviepy import VideoFileClip, AudioFileClip, ColorClip, CompositeVideoClip  # type: ignore
from moviepy import vfx  # type: ignore


def _subclip(clip: VideoFileClip, start: float, end: float) -> VideoFileClip:
    """Extract a subclip from a video clip. Compatible with MoviePy v1 and v2."""
    if hasattr(clip, "subclip"):
        return clip.subclip(start, end)  # type: ignore[attr-defined]
    return clip.subclipped(start, end)  # type: ignore[attr-defined]


def _set_duration(clip: VideoFileClip, duration: float) -> VideoFileClip:
    """Set the duration of a video clip. Compatible with MoviePy v1 and v2."""
    if hasattr(clip, "set_duration"):
        return clip.set_duration(duration)  # type: ignore[attr-defined]
    return clip.with_duration(duration)  # type: ignore[attr-defined]


def _set_audio(clip: VideoFileClip, audio: AudioFileClip) -> VideoFileClip:
    """Attach audio to a video clip. Compatible with MoviePy v1 and v2."""
    if hasattr(clip, "set_audio"):
        return clip.set_audio(audio)  # type: ignore[attr-defined]
    return clip.with_audio(audio)  # type: ignore[attr-defined]


def _speedx(clip: VideoFileClip, factor: float) -> VideoFileClip:
    """Change the playback speed of a video clip. Compatible with MoviePy v1 and v2."""
    if hasattr(clip, "fx"):
        return clip.fx(vfx.speedx, factor=factor)  # type: ignore[attr-defined]
    if hasattr(clip, "with_speed_scaled"):
        return clip.with_speed_scaled(factor=factor)  # type: ignore[attr-defined]
    if hasattr(clip, "with_speed"):
        return clip.with_speed(factor=factor)  # type: ignore[attr-defined]
    return clip


def _resize_letterbox(clip: VideoFileClip, target_resolution: Tuple[int, int]) -> VideoFileClip:
    """
    Resize a video clip to fit within target resolution with letterboxing.
    
    Maintains aspect ratio and adds black bars if needed to fill the target size.
    """
    target_w, target_h = target_resolution
    w, h = clip.size
    scale = min(target_w / w, target_h / h)
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    
    if hasattr(clip, "resize"):
        resized = clip.resize(newsize=(new_w, new_h))  # type: ignore[attr-defined]
    else:
        resized = clip.resized((new_w, new_h))  # type: ignore[attr-defined]
    
    if hasattr(resized, "on_color"):
        return resized.on_color(size=(target_w, target_h), color=(0, 0, 0), pos=("center", "center"))  # type: ignore[attr-defined]
    
    # Fallback: composite on black background
    bg = ColorClip(size=(target_w, target_h), color=(0, 0, 0)).with_duration(getattr(resized, "duration", 1.0))  # type: ignore[attr-defined]
    if hasattr(resized, "set_position"):
        fg = resized.set_position(("center", "center"))  # type: ignore[attr-defined]
    else:
        fg = resized.with_position(("center", "center"))  # type: ignore[attr-defined]
    return CompositeVideoClip([bg, fg])


def load_blacklist(blacklist_path: Path) -> Set[str]:
    """
    Load blacklisted video filenames from a JSON file.
    
    Blacklisted files are source videos that failed to load or process correctly.
    They are excluded from future random selection to avoid repeated errors.
    
    Args:
        blacklist_path: Path to the blacklist JSON file
        
    Returns:
        Set of blacklisted filenames
    """
    if blacklist_path.exists():
        try:
            with open(blacklist_path, 'r') as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_blacklist(blacklist_path: Path, blacklist: Set[str]) -> None:
    """Save blacklisted video filenames to a JSON file."""
    try:
        with open(blacklist_path, 'w') as f:
            json.dump(list(blacklist), f, indent=2)
    except Exception as e:
        print(f"[warn] Failed to save blacklist: {e}", flush=True)


def load_checkpoint(checkpoint_dir: Path) -> Tuple[int, List[Path], Set[str]]:
    """
    Load checkpoint data: last completed second, saved clip paths, and blacklist.
    
    Returns file paths as Path objects (not VideoFileClip objects) to avoid
    loading thousands of clips into memory.
    
    Args:
        checkpoint_dir: Directory containing checkpoint files
        
    Returns:
        Tuple of (last_completed_sec, list of clip paths, blacklist)
    """
    checkpoint_file = checkpoint_dir / "checkpoint.json"
    blacklist_file = checkpoint_dir / "blacklist.json"

    if not checkpoint_file.exists():
        return 0, [], load_blacklist(blacklist_file)

    try:
        with open(checkpoint_file, 'r') as f:
            data = json.load(f)
            last_sec = data.get("last_completed_sec", 0)
            saved_clips = data.get("saved_clips", [])
            existing_clips = [Path(c) for c in saved_clips if Path(c).exists()]
            return last_sec, existing_clips, load_blacklist(blacklist_file)
    except Exception as e:
        print(f"[warn] Failed to load checkpoint: {e}, starting fresh", flush=True)
        return 0, [], load_blacklist(blacklist_file)


def save_checkpoint(checkpoint_dir: Path, last_completed_sec: int, saved_clips: List[Path], blacklist: Set[str]) -> None:
    """
    Save checkpoint progress to disk.
    
    Args:
        checkpoint_dir: Directory to save checkpoint files
        last_completed_sec: Last second that was successfully processed
        saved_clips: List of Path objects pointing to generated clip files
        blacklist: Set of blacklisted filenames
    """
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = checkpoint_dir / "checkpoint.json"

    try:
        saved_clips_str = [str(clip_path) for clip_path in saved_clips]
        with open(checkpoint_file, 'w') as f:
            json.dump({
                "last_completed_sec": last_completed_sec,
                "saved_clips": saved_clips_str,
            }, f, indent=2)
        save_blacklist(checkpoint_dir / "blacklist.json", blacklist)
    except Exception as e:
        print(f"[warn] Failed to save checkpoint: {e}", flush=True)


def build_visual_track(
    video_folder: str,
    bpm_values: List[float],
    duration_seconds: int,
    target_resolution: Tuple[int, int],
    base_bpm: float,
    speed_min: float = 0.5,
    speed_max: float = 2.0,
    checkpoint_dir: Path | None = None,
) -> List[Path]:
    """
    Build visual track by generating 1-second clips and writing them to disk.
    
    For each second of the output video:
    1. Randomly selects a source MP4 from the video folder
    2. Extracts a random subclip
    3. Adjusts playback speed based on local BPM relative to base BPM
    4. Resizes with letterboxing to target resolution
    5. Writes a 1-second MP4 clip to disk
    
    This function is memory-efficient: clips are written to disk immediately
    and not kept in memory. Only file paths are returned.
    
    Args:
        video_folder: Path to folder containing source MP4 files
        bpm_values: Per-second BPM timeline from audio analysis
        duration_seconds: Total duration of output video in seconds
        target_resolution: Target video resolution (width, height)
        base_bpm: Base/reference BPM for speed calculations
        speed_min: Minimum speed multiplier (default 0.5x)
        speed_max: Maximum speed multiplier (default 2.0x)
        checkpoint_dir: Directory for checkpoints (default: checkpoints/)
        
    Returns:
        List of Path objects pointing to generated 1-second clip files in order
        
    Raises:
        FileNotFoundError: If video folder doesn't exist or has no usable files
    """
    folder = Path(video_folder)
    if not folder.exists():
        raise FileNotFoundError(f"Video folder not found: {video_folder}")

    # Load blacklist and checkpoint
    if checkpoint_dir is None:
        checkpoint_dir = Path("checkpoints")
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    blacklist = load_blacklist(checkpoint_dir / "blacklist.json")
    start_sec, saved_clip_paths, existing_blacklist = load_checkpoint(checkpoint_dir)
    blacklist.update(existing_blacklist)

    # Filter out blacklisted files
    all_video_paths = sorted([p for p in folder.glob("*.mp4") if p.is_file()])
    video_paths = [p for p in all_video_paths if p.name not in blacklist]

    if not video_paths:
        raise FileNotFoundError(f"No usable MP4 files found in: {video_folder} (all blacklisted?)")

    if start_sec > 0:
        print(f"[resume] Resuming from second {start_sec}, {len(saved_clip_paths)} clips already saved", flush=True)

    clip_paths: List[Path] = saved_clip_paths.copy()
    skipped_count = 0
    checkpoint_interval = 50  # Save checkpoint every 50 seconds

    for sec in tqdm(
        range(start_sec, duration_seconds),
        desc="Building 1s clips",
        ncols=80,
        initial=start_sec,
        total=duration_seconds,
    ):
        local_bpm = bpm_values[sec] if sec < len(bpm_values) else base_bpm
        if not np.isfinite(local_bpm) or local_bpm <= 0:
            local_bpm = base_bpm
        speed = float(np.clip(local_bpm / base_bpm, speed_min, speed_max))

        checkpoint_clip_path = checkpoint_dir / f"clip_{sec:06d}.mp4"

        # Try to load a random video with error handling
        video_clip = None
        video_path: Path | None = None
        max_tries = 5

        for attempt in range(max_tries):
            candidate = random.choice(video_paths)
            if candidate.name in blacklist:
                continue
            video_path = candidate
            try:
                video_clip = VideoFileClip(str(video_path), audio=False)
                dur = video_clip.duration
                if dur is None or dur <= 0:
                    raise ValueError(f"Invalid duration: {dur}")
                break  # Success
            except Exception as e:
                if video_clip is not None:
                    try:
                        video_clip.close()
                    except Exception:
                        pass
                    video_clip = None
                if video_path.name not in blacklist:
                    print(f"[blacklist] Adding {video_path.name} to blacklist (error: {type(e).__name__})", flush=True)
                    blacklist.add(video_path.name)
                    save_blacklist(checkpoint_dir / "blacklist.json", blacklist)
                video_path = None
                if attempt == max_tries - 1:
                    print(f"[warn] Failed to load video after {max_tries} tries at clip {sec}, using fallback", flush=True)
                    skipped_count += 1

        # Process the clip with error handling
        sub = None
        sped = None
        boxed = None
        one_sec = None
        try:
            if video_clip is None:
                # Create a black frame as fallback
                one_sec = ColorClip(size=target_resolution, color=(0, 0, 0)).with_duration(1.0)
            else:
                base_window = 1.2
                max_start = max(0.0, (video_clip.duration or 0.0) - base_window)
                start_t = random.uniform(0.0, max_start) if max_start > 0 else 0.0
                sub = _subclip(video_clip, start_t, min(start_t + base_window, video_clip.duration))
                sped = _speedx(sub, factor=speed)
                boxed = _resize_letterbox(sped, target_resolution)
                one_sec = _set_duration(boxed, 1.0)

            checkpoint_clip_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                one_sec.write_videofile(
                    str(checkpoint_clip_path),
                    codec="libx264",
                    audio=False,
                    fps=30,
                    preset="ultrafast",
                )
            except TypeError:
                one_sec.write_videofile(
                    str(checkpoint_clip_path),
                    codec="libx264",
                    audio=False,
                    fps=30,
                )

            one_sec.close()
            one_sec = None

            clip_paths.append(checkpoint_clip_path)

        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"[warn] Error processing {video_path.name if video_path else 'fallback'} at clip {sec}: {type(e).__name__}: {error_msg}", flush=True)
            if sec < 5:
                traceback.print_exc()
            skipped_count += 1
            # Fallback black frame
            try:
                fallback = ColorClip(size=target_resolution, color=(0, 0, 0)).with_duration(1.0)
                fallback.write_videofile(
                    str(checkpoint_clip_path),
                    codec="libx264",
                    audio=False,
                    fps=30,
                    preset="ultrafast",
                )
                fallback.close()
                clip_paths.append(checkpoint_clip_path)
            except Exception as fallback_err:
                print(f"[error] Failed to create fallback clip: {fallback_err}", flush=True)
                clip_paths.append(checkpoint_clip_path)
        finally:
            # Always close source clips to free resources immediately
            for clip_to_close in [one_sec, boxed, sped, sub, video_clip]:
                if clip_to_close is not None:
                    try:
                        clip_to_close.close()
                    except Exception:
                        pass

        # Save checkpoint periodically
        if (sec + 1) % checkpoint_interval == 0 or sec == duration_seconds - 1:
            save_checkpoint(checkpoint_dir, sec + 1, clip_paths, blacklist)
            print(f"[checkpoint] Saved progress at second {sec + 1}/{duration_seconds}", flush=True)

    if skipped_count > 0:
        print(f"[info] Skipped {skipped_count} problematic clips (used black frames)", flush=True)

    print(f"[info] Final blacklist: {len(blacklist)} files", flush=True)
    print(f"[info] Generated {len(clip_paths)} clip files", flush=True)

    return clip_paths

