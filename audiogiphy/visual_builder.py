"""
Visual Builder Module.

This module handles building the visual track by processing video clips,
applying BPM-based speed changes, resizing, and writing 1-second segments to disk.
"""

from typing import List, Tuple, Set, Dict
import json
import random
import logging

import numpy as np
from pathlib import Path
from tqdm import tqdm
from moviepy import VideoFileClip, AudioFileClip, ColorClip, CompositeVideoClip  # type: ignore
from moviepy import vfx  # type: ignore

from audiogiphy.config import (
    DEFAULT_FPS,
    CLIP_DURATION_SECONDS,
    BASE_WINDOW_SECONDS,
    CHECKPOINT_INTERVAL,
    CHECKPOINTS_DIR,
    LYRICS_FONT_SIZE,
    LYRICS_KARAOKE_FONT_SIZE,
    LYRICS_TEXT_COLOR,
    LYRICS_STROKE_COLOR,
    LYRICS_STROKE_WIDTH,
    LYRICS_VERTICAL_POSITION,
    LYRICS_MAX_HEIGHT_RATIO,
    WATERMARK_TEXT,
    WATERMARK_FONT_SIZE,
    WATERMARK_TEXT_COLOR,
    WATERMARK_OPACITY,
    WATERMARK_MARGIN_RIGHT,
    WATERMARK_MARGIN_BOTTOM,
)

__all__ = ["build_visual_track", "_add_watermark"]

logger = logging.getLogger("audiogiphy.visual_builder")


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


def _add_text_overlay(
    clip: VideoFileClip,
    text: str,
    resolution: Tuple[int, int],
) -> VideoFileClip:
    """
    Add a text overlay to a video clip.
    
    Args:
        clip: Video clip to overlay text on
        text: Text to display (will be uppercased and made bold)
        resolution: Target resolution (width, height)
        
    Returns:
        CompositeVideoClip with text overlay on top
    """
    try:
        from moviepy import TextClip  # type: ignore
        
        # Convert text to uppercase and ensure it's bold
        text_upper = text.upper().strip()
        
        # Calculate safe size to prevent cropping - constrain both width and height
        # Use 85% of width and 30% of height to ensure text fits without cropping
        max_width = int(resolution[0] * 0.85)
        max_height = int(resolution[1] * LYRICS_MAX_HEIGHT_RATIO)  # e.g. 30% of frame height
        
        # Ensure text clip duration matches video clip duration
        clip_duration = getattr(clip, 'duration', None) or CLIP_DURATION_SECONDS
        
        # Create text clip - MoviePy uses font_size not fontsize, and text parameter name
        # Try bold fonts in order of preference
        bold_fonts = ["Arial-Bold", "Arial-Black", "Helvetica-Bold", "DejaVu-Sans-Bold"]
        txt_clip = None
        
        for font_name in bold_fonts + [None]:  # Try bold fonts, then default
            try:
                if font_name:
                    txt_clip = TextClip(
                        text=text_upper,
                        font_size=LYRICS_FONT_SIZE,
                        color=LYRICS_TEXT_COLOR,
                        stroke_color=LYRICS_STROKE_COLOR,
                        stroke_width=LYRICS_STROKE_WIDTH,
                        font=font_name,
                        method="caption",
                        size=(max_width, max_height),  # Constrain both width and height to prevent cropping
                    ).with_duration(clip_duration)
                    logger.debug(f"Successfully created text clip with font: {font_name}, size=({max_width}, {max_height})")
                    break
                else:
                    # Fallback: no font specified (use default, still uppercase and bold via stroke)
                    txt_clip = TextClip(
                        text=text_upper,
                        font_size=LYRICS_FONT_SIZE,
                        color=LYRICS_TEXT_COLOR,
                        stroke_color=LYRICS_STROKE_COLOR,
                        stroke_width=LYRICS_STROKE_WIDTH,
                        method="caption",
                        size=(max_width, max_height),
                    ).with_duration(clip_duration)
                    logger.debug(f"Created text clip with default font, size=({max_width}, {max_height})")
                    break
            except Exception as e:
                if font_name:
                    logger.debug(f"Font {font_name} failed: {e}, trying next")
                else:
                    # Last resort: basic text clip without caption method
                    try:
                        txt_clip = TextClip(
                            text=text_upper,
                            font_size=LYRICS_FONT_SIZE,
                            color=LYRICS_TEXT_COLOR,
                            stroke_color=LYRICS_STROKE_COLOR,
                            stroke_width=LYRICS_STROKE_WIDTH,
                        ).with_duration(clip_duration)
                        logger.debug("Created basic text clip (no caption method)")
                        break
                    except Exception as e2:
                        logger.warning(f"All text clip creation methods failed: {e2}")
                        raise
        
        if txt_clip is None:
            raise RuntimeError("Failed to create text clip with any method")
        
        # Position text consistently using vertical position constant
        # Center horizontally, position vertically based on LYRICS_VERTICAL_POSITION
        y_position = resolution[1] * LYRICS_VERTICAL_POSITION  # e.g. 0.25 for upper quarter
        txt_clip = txt_clip.with_position(("center", y_position))
        
        # Get base clip size to ensure composite maintains original resolution
        base_size = getattr(clip, 'size', None) or resolution
        
        # Composite text over video (text clip on top - outmost layer)
        # IMPORTANT: Explicitly set size to base clip size so composite doesn't shrink to fit text
        result = CompositeVideoClip([clip, txt_clip], size=base_size)
        
        # Verify composite contains both clips and text is on top
        if hasattr(result, 'clips') and len(result.clips) >= 2:
            logger.debug(f"Composite verified: {len(result.clips)} clips (base video + text overlay)")
            # Verify the first clip is the original video clip (base layer)
            base_clip = result.clips[0]
            # Verify the last clip is the text overlay (top layer)
            top_clip = result.clips[-1]
            if base_clip is clip and top_clip is txt_clip:
                logger.debug("Composite layers verified: video (base) + text (top/outmost)")
            else:
                logger.warning("Composite layer order may be incorrect")
        else:
            logger.warning(f"Composite clip structure unexpected: {len(result.clips) if hasattr(result, 'clips') else 'unknown'} clips")
        
        # Ensure result has correct duration and size
        result = result.with_duration(clip_duration)
        if hasattr(clip, 'size') and clip.size:
            # Verify size is preserved
            if hasattr(result, 'size') and result.size != clip.size:
                logger.warning(f"Composite size mismatch: original={clip.size}, composite={result.size}")
        
        # Log text details
        logger.debug(f"Created text overlay: text='{text_upper}' (uppercase, bold), position=center/{y_position:.0f}px, duration={clip_duration}, composite_size={result.size if hasattr(result, 'size') else 'N/A'}, text_constraints=({max_width}x{max_height})")
        return result
    except Exception as e:
        logger.error(f"Failed to create text overlay: {e}", exc_info=True)
        logger.warning("Returning original clip without text overlay due to error")
        # CRITICAL: Always return the original clip if overlay fails
        # This ensures dancing GIFs are still visible even if text overlay fails
        return clip


def _add_karaoke_overlay(
    clip: VideoFileClip,
    text: str,
    resolution: Tuple[int, int],
) -> VideoFileClip:
    """
    Add a karaoke-style text overlay to a video clip.
    
    Similar to _add_text_overlay but uses smaller font size for displaying
    multiple words per second. Text is automatically wrapped within constraints.
    
    Args:
        clip: Video clip to overlay text on
        text: Text to display (will be uppercased)
        resolution: Target resolution (width, height)
        
    Returns:
        CompositeVideoClip with text overlay on top
    """
    try:
        from moviepy import TextClip  # type: ignore
        
        # Convert text to uppercase
        text_upper = text.upper().strip()
        
        if not text_upper:
            logger.debug("Empty text provided for karaoke overlay, returning original clip")
            return clip
        
        # Calculate safe size to prevent cropping - constrain both width and height
        # Use 85% of width and 30% of height to ensure text fits without cropping
        max_width = int(resolution[0] * 0.85)
        max_height = int(resolution[1] * LYRICS_MAX_HEIGHT_RATIO)  # e.g. 30% of frame height
        
        # Ensure text clip duration matches video clip duration
        clip_duration = getattr(clip, 'duration', None) or CLIP_DURATION_SECONDS
        
        # Create text clip - MoviePy uses font_size not fontsize, and text parameter name
        # Try bold fonts in order of preference
        bold_fonts = ["Arial-Bold", "Arial-Black", "Helvetica-Bold", "DejaVu-Sans-Bold"]
        txt_clip = None
        
        for font_name in bold_fonts + [None]:  # Try bold fonts, then default
            try:
                if font_name:
                    txt_clip = TextClip(
                        text=text_upper,
                        font_size=LYRICS_KARAOKE_FONT_SIZE,
                        color=LYRICS_TEXT_COLOR,
                        stroke_color=LYRICS_STROKE_COLOR,
                        stroke_width=LYRICS_STROKE_WIDTH,
                        font=font_name,
                        method="caption",
                        size=(max_width, max_height),  # Constrain both width and height to prevent cropping
                    ).with_duration(clip_duration)
                    logger.debug(f"Successfully created karaoke text clip with font: {font_name}, size=({max_width}, {max_height})")
                    break
                else:
                    # Fallback: no font specified (use default)
                    txt_clip = TextClip(
                        text=text_upper,
                        font_size=LYRICS_KARAOKE_FONT_SIZE,
                        color=LYRICS_TEXT_COLOR,
                        stroke_color=LYRICS_STROKE_COLOR,
                        stroke_width=LYRICS_STROKE_WIDTH,
                        method="caption",
                        size=(max_width, max_height),
                    ).with_duration(clip_duration)
                    logger.debug(f"Created karaoke text clip with default font, size=({max_width}, {max_height})")
                    break
            except Exception as e:
                if font_name:
                    logger.debug(f"Font {font_name} failed: {e}, trying next")
                else:
                    # Last resort: basic text clip without caption method
                    try:
                        txt_clip = TextClip(
                            text=text_upper,
                            font_size=LYRICS_KARAOKE_FONT_SIZE,
                            color=LYRICS_TEXT_COLOR,
                            stroke_color=LYRICS_STROKE_COLOR,
                            stroke_width=LYRICS_STROKE_WIDTH,
                        ).with_duration(clip_duration)
                        logger.debug("Created basic karaoke text clip (no caption method)")
                        break
                    except Exception as e2:
                        logger.warning(f"All karaoke text clip creation methods failed: {e2}")
                        raise
        
        if txt_clip is None:
            raise RuntimeError("Failed to create karaoke text clip with any method")
        
        # Position text consistently using vertical position constant
        # Center horizontally, position vertically based on LYRICS_VERTICAL_POSITION
        y_position = resolution[1] * LYRICS_VERTICAL_POSITION  # e.g. 0.25 for upper quarter
        txt_clip = txt_clip.with_position(("center", y_position))
        
        # Get base clip size to ensure composite maintains original resolution
        base_size = getattr(clip, 'size', None) or resolution
        
        # Composite text over video (text clip on top - outmost layer)
        # IMPORTANT: Explicitly set size to base clip size so composite doesn't shrink to fit text
        result = CompositeVideoClip([clip, txt_clip], size=base_size)
        
        # Verify composite contains both clips and text is on top
        if hasattr(result, 'clips') and len(result.clips) >= 2:
            logger.debug(f"Karaoke composite verified: {len(result.clips)} clips (base video + text overlay)")
            # Verify the first clip is the original video clip (base layer)
            base_clip = result.clips[0]
            # Verify the last clip is the text overlay (top layer)
            top_clip = result.clips[-1]
            if base_clip is clip and top_clip is txt_clip:
                logger.debug("Karaoke composite layers verified: video (base) + text (top/outmost)")
            else:
                logger.warning("Karaoke composite layer order may be incorrect")
        else:
            logger.warning(f"Karaoke composite clip structure unexpected: {len(result.clips) if hasattr(result, 'clips') else 'unknown'} clips")
        
        # Ensure result has correct duration and size
        result = result.with_duration(clip_duration)
        if hasattr(clip, 'size') and clip.size:
            # Verify size is preserved
            if hasattr(result, 'size') and result.size != clip.size:
                logger.warning(f"Karaoke composite size mismatch: original={clip.size}, composite={result.size}")
        
        # Log text details
        logger.debug(f"Created karaoke overlay: text='{text_upper[:50]}{'...' if len(text_upper) > 50 else ''}' (uppercase), position=center/{y_position:.0f}px, duration={clip_duration}, composite_size={result.size if hasattr(result, 'size') else 'N/A'}, text_constraints=({max_width}x{max_height})")
        return result
    except Exception as e:
        logger.error(f"Failed to create karaoke overlay: {e}", exc_info=True)
        logger.warning("Returning original clip without karaoke overlay due to error")
        # CRITICAL: Always return the original clip if overlay fails
        # This ensures dancing GIFs are still visible even if text overlay fails
        return clip


def _add_watermark(
    clip: VideoFileClip,
    resolution: Tuple[int, int],
) -> VideoFileClip:
    """
    Add a watermark overlay to a video clip.
    
    The watermark appears in the bottom-right corner with configurable opacity,
    margins, and styling. It's designed to be subtle but readable.
    
    Args:
        clip: Video clip to overlay watermark on
        resolution: Target resolution (width, height)
        
    Returns:
        CompositeVideoClip with watermark overlay on top
    """
    try:
        from moviepy import TextClip  # type: ignore
        
        # Get clip duration
        clip_duration = getattr(clip, 'duration', None) or CLIP_DURATION_SECONDS
        
        # Create text clip for watermark
        # Try common fonts, fallback to default
        watermark_fonts = ["Arial", "Helvetica", "DejaVu-Sans"]
        txt_clip = None
        
        for font_name in watermark_fonts + [None]:
            try:
                if font_name:
                    txt_clip = TextClip(
                        text=WATERMARK_TEXT,
                        font_size=WATERMARK_FONT_SIZE,
                        color=WATERMARK_TEXT_COLOR,
                        font=font_name,
                    ).with_duration(clip_duration)
                    logger.debug(f"Successfully created watermark text clip with font: {font_name}")
                    break
                else:
                    # Fallback: default font
                    txt_clip = TextClip(
                        text=WATERMARK_TEXT,
                        font_size=WATERMARK_FONT_SIZE,
                        color=WATERMARK_TEXT_COLOR,
                    ).with_duration(clip_duration)
                    logger.debug("Created watermark text clip with default font")
                    break
            except Exception as e:
                if font_name:
                    logger.debug(f"Font {font_name} failed for watermark: {e}, trying next")
                else:
                    logger.warning(f"All watermark font attempts failed: {e}")
                    raise
        
        if txt_clip is None:
            raise RuntimeError("Failed to create watermark text clip with any method")
        
        # Position watermark in bottom-right corner with margins
        # Use relative positioning: position relative to bottom-right, then offset by margins
        width, height = resolution
        
        # Try to get text clip size for accurate positioning
        txt_w = 0
        txt_h = 0
        try:
            if hasattr(txt_clip, 'size') and txt_clip.size:
                txt_w, txt_h = txt_clip.size
            else:
                # Estimate text width based on font size and character count
                # Rough estimate: each character is about 0.6 * font_size wide
                txt_w = int(len(WATERMARK_TEXT) * WATERMARK_FONT_SIZE * 0.6)
                txt_h = WATERMARK_FONT_SIZE
                logger.debug(f"Text clip size not available, using estimate: {txt_w}x{txt_h}")
        except Exception as e:
            logger.debug(f"Could not determine text clip size: {e}, using estimate")
            txt_w = int(len(WATERMARK_TEXT) * WATERMARK_FONT_SIZE * 0.6)
            txt_h = WATERMARK_FONT_SIZE
        
        # Calculate position: bottom-right corner minus margins minus text size
        x_position = width - txt_w - WATERMARK_MARGIN_RIGHT
        y_position = height - txt_h - WATERMARK_MARGIN_BOTTOM
        
        # Ensure position is not negative
        x_position = max(0, x_position)
        y_position = max(0, y_position)
        
        txt_clip = txt_clip.with_position((x_position, y_position))
        
        # Apply opacity (80% visible = 0.8 opacity)
        # Note: Opacity is applied after positioning to ensure it works correctly
        if hasattr(txt_clip, "set_opacity"):
            txt_clip = txt_clip.set_opacity(WATERMARK_OPACITY)  # type: ignore[attr-defined]
        elif hasattr(txt_clip, "with_opacity"):
            txt_clip = txt_clip.with_opacity(WATERMARK_OPACITY)  # type: ignore[attr-defined]
        else:
            # Fallback: watermark will be fully opaque
            logger.debug("Opacity method not available, watermark will be fully opaque")
        
        # Get base clip size to ensure composite maintains original resolution
        base_size = getattr(clip, 'size', None) or resolution
        
        # Composite watermark over video (watermark on top - outmost layer)
        # IMPORTANT: Explicitly set size to base clip size so composite doesn't shrink
        result = CompositeVideoClip([clip, txt_clip], size=base_size)
        
        # Ensure result has correct duration and size
        result = result.with_duration(clip_duration)
        
        logger.debug(f"Created watermark overlay: text='{WATERMARK_TEXT}', position=({x_position}, {y_position}), opacity={WATERMARK_OPACITY}, composite_size={result.size if hasattr(result, 'size') else 'N/A'}")
        return result
    except Exception as e:
        logger.error(f"Failed to create watermark overlay: {e}", exc_info=True)
        logger.warning("Returning original clip without watermark overlay due to error")
        # CRITICAL: Always return the original clip if watermark fails
        # This ensures video is still rendered even if watermark fails
        return clip


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
        logger.warning(f"Failed to save blacklist: {e}")


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
        logger.warning(f"Failed to load checkpoint: {e}, starting fresh")
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
        logger.warning(f"Failed to save checkpoint: {e}")


def build_visual_track(
    video_folder: str,
    bpm_values: List[float],
    duration_seconds: int,
    target_resolution: Tuple[int, int],
    base_bpm: float,
    speed_min: float = 0.5,
    speed_max: float = 2.0,
    checkpoint_dir: Path | None = None,
    lyrics_mapping: Dict[int, str] | None = None,
    karaoke_mapping: Dict[int, str] | None = None,
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
        lyrics_mapping: Optional dict mapping second index -> phrase-ending word (for phrase-ending overlay mode)
        karaoke_mapping: Optional dict mapping second index -> text line (for karaoke mode, takes precedence over lyrics_mapping)
        
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
        checkpoint_dir = Path(CHECKPOINTS_DIR)
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
        logger.info(f"Resuming from second {start_sec}, {len(saved_clip_paths)} clips already saved")

    clip_paths: List[Path] = saved_clip_paths.copy()
    skipped_count = 0
    checkpoint_interval = CHECKPOINT_INTERVAL

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
                    logger.debug(f"Adding {video_path.name} to blacklist (error: {type(e).__name__})")
                    blacklist.add(video_path.name)
                    save_blacklist(checkpoint_dir / "blacklist.json", blacklist)
                video_path = None
                if attempt == max_tries - 1:
                    logger.warning(f"Failed to load video after {max_tries} tries at clip {sec}, using fallback")
                    skipped_count += 1

        # Process the clip with error handling
        sub = None
        sped = None
        boxed = None
        one_sec = None
        try:
            if video_clip is None:
                # Create a black frame as fallback
                one_sec = ColorClip(size=target_resolution, color=(0, 0, 0)).with_duration(CLIP_DURATION_SECONDS)
            else:
                base_window = BASE_WINDOW_SECONDS
                max_start = max(0.0, (video_clip.duration or 0.0) - base_window)
                start_t = random.uniform(0.0, max_start) if max_start > 0 else 0.0
                sub = _subclip(video_clip, start_t, min(start_t + base_window, video_clip.duration))
                sped = _speedx(sub, factor=speed)
                boxed = _resize_letterbox(sped, target_resolution)
                one_sec = _set_duration(boxed, CLIP_DURATION_SECONDS)
            
            # Add text overlay if this second has lyrics
            # Karaoke mode takes precedence over phrase-ending mode
            if karaoke_mapping is not None and sec in karaoke_mapping:
                # Karaoke mode: display all words for this second
                text_line = karaoke_mapping[sec]
                try:
                    logger.debug(f"Adding karaoke overlay to clip {sec}: '{text_line[:50]}{'...' if len(text_line) > 50 else ''}'")
                    one_sec = _add_karaoke_overlay(one_sec, text_line, target_resolution)
                    logger.debug(f"Successfully added karaoke overlay to clip {sec}")
                except Exception as e:
                    logger.error(f"Failed to add karaoke overlay at second {sec}: {e}", exc_info=True)
                    # Continue without overlay - one_sec is still the original clip
            elif lyrics_mapping is not None and sec in lyrics_mapping:
                # Phrase-ending mode: display single word
                word_text = lyrics_mapping[sec]
                try:
                    # Store original clip info for verification
                    original_clip_type = type(one_sec).__name__
                    original_clip_size = getattr(one_sec, 'size', None)
                    original_clip_duration = getattr(one_sec, 'duration', None)
                    
                    logger.info(f"Adding lyric overlay '{word_text}' to clip {sec} (original: {original_clip_type}, size={original_clip_size}, duration={original_clip_duration})")
                    one_sec = _add_text_overlay(one_sec, word_text, target_resolution)
                    
                    # Verify overlay was applied correctly
                    overlay_clip_type = type(one_sec).__name__
                    overlay_clip_size = getattr(one_sec, 'size', None)
                    overlay_clip_duration = getattr(one_sec, 'duration', None)
                    
                    if overlay_clip_type == 'CompositeVideoClip':
                        logger.info(f"Successfully added lyric overlay '{word_text}' to clip {sec} (composite: {overlay_clip_type}, size={overlay_clip_size}, duration={overlay_clip_duration})")
                    else:
                        logger.warning(f"Overlay result is not CompositeVideoClip: {overlay_clip_type} - original clip may be lost")
                except Exception as e:
                    logger.error(f"Failed to add lyric overlay at second {sec}: {e}", exc_info=True)
                    logger.warning(f"Continuing without overlay - original clip preserved")
                    # Continue without overlay - one_sec is still the original clip
            elif sec == 0:
                # Log once at the start to confirm which mode is active
                if karaoke_mapping is not None:
                    logger.info(f"Karaoke mapping available with {len(karaoke_mapping)} entries: {sorted(karaoke_mapping.keys())[:10]}{'...' if len(karaoke_mapping) > 10 else ''}")
                elif lyrics_mapping is not None:
                    logger.info(f"Lyrics mapping available with {len(lyrics_mapping)} entries: {list(lyrics_mapping.keys())}")
                    logger.debug(f"Will check each second for lyric overlays")

            checkpoint_clip_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                one_sec.write_videofile(
                    str(checkpoint_clip_path),
                    codec="libx264",
                    audio=False,
                    fps=DEFAULT_FPS,
                    preset="ultrafast",
                )
            except TypeError:
                one_sec.write_videofile(
                    str(checkpoint_clip_path),
                    codec="libx264",
                    audio=False,
                    fps=DEFAULT_FPS,
                )

            one_sec.close()
            one_sec = None

            clip_paths.append(checkpoint_clip_path)

        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Error processing {video_path.name if video_path else 'fallback'} at clip {sec}: {type(e).__name__}: {error_msg}")
            if sec < 5:
                logger.debug("Traceback:", exc_info=True)
            skipped_count += 1
            # Fallback black frame
            try:
                fallback = ColorClip(size=target_resolution, color=(0, 0, 0)).with_duration(CLIP_DURATION_SECONDS)
                fallback.write_videofile(
                    str(checkpoint_clip_path),
                    codec="libx264",
                    audio=False,
                    fps=DEFAULT_FPS,
                    preset="ultrafast",
                )
                fallback.close()
                clip_paths.append(checkpoint_clip_path)
            except Exception as fallback_err:
                logger.error(f"Failed to create fallback clip: {fallback_err}")
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
            logger.info(f"Saved progress at second {sec + 1}/{duration_seconds}")

    if skipped_count > 0:
        logger.info(f"Skipped {skipped_count} problematic clips (used black frames)")

    logger.info(f"Final blacklist: {len(blacklist)} files")
    logger.info(f"Generated {len(clip_paths)} clip files")

    return clip_paths

