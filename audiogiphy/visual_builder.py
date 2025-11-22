"""
Visual Builder Module.

This module handles building the visual track by processing video clips,
applying BPM-based speed changes, resizing, and writing 1-second segments to disk.
"""

from typing import List, Tuple, Set, Dict, Any, Optional
import json
import random
import logging
import tempfile
import os
import hashlib

import numpy as np

from pathlib import Path

try:
    # MoviePy v2 style imports
    from moviepy import (
        VideoFileClip,
        AudioFileClip,
        CompositeVideoClip,
        vfx,
        TextClip,
        ColorClip,
    )
except Exception:  # pragma: no cover - fallback for older MoviePy
    # MoviePy v1 style imports
    from moviepy.editor import (  # type: ignore[no-redef]
        VideoFileClip,
        AudioFileClip,
        CompositeVideoClip,
        vfx,
        TextClip,
        ColorClip,
    )

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
    GIPHY_OVERLAY_SIZE_RATIO,
    GIPHY_OVERLAY_POSITION,
    GIPHY_OVERLAY_MARGIN,
)

logger = logging.getLogger("audiogiphy.visual_builder")


def _resize_letterbox(
    clip: VideoFileClip,
    target_resolution: Tuple[int, int],
) -> VideoFileClip:
    """
    Resize a clip to the target resolution with letterboxing while keeping aspect ratio.

    This function is compatible with both MoviePy v1 (resize) and v2 (resized).
    """
    target_w, target_h = target_resolution

    # Try to get size; fall back to target_resolution if missing
    size = getattr(clip, "size", None)
    if size is None:
        width, height = target_w, target_h
    else:
        width, height = size

    # Compute aspect ratios
    aspect = width / height if height else 1.0
    target_aspect = target_w / target_h if target_h else aspect

    if aspect > target_aspect:
        # Clip is wider than target → fit width
        new_w = target_w
        new_h = int(target_w / aspect) if aspect else target_h
    else:
        # Clip is taller than target → fit height
        new_h = target_h
        new_w = int(target_h * aspect) if target_h else target_w

    # Safeguard minimum size
    new_w = max(1, new_w)
    new_h = max(1, new_h)

    # Safe resize for different MoviePy versions
    try:
        if hasattr(clip, "resize"):
            resized = clip.resize(newsize=(new_w, new_h))  # type: ignore[attr-defined]
        else:
            resized = clip.resized((new_w, new_h))  # type: ignore[attr-defined]
    except Exception as e:
        logger.warning(f"Failed to resize clip to {new_w}x{new_h}: {e}, using original clip")
        resized = clip

    # Create black background (letterbox) and composite
    try:
        bg = ColorClip(size=target_resolution, color=(0, 0, 0))
        bg = bg.with_duration(clip.duration) if hasattr(bg, "with_duration") else bg.set_duration(clip.duration)  # type: ignore[attr-defined]
        x_center = (target_w - new_w) // 2
        y_center = (target_h - new_h) // 2

        if hasattr(resized, "set_position"):
            resized_pos = resized.set_position((x_center, y_center))  # type: ignore[attr-defined]
        else:
            resized_pos = resized.with_position((x_center, y_center))  # type: ignore[attr-defined]

        composed = CompositeVideoClip([bg, resized_pos])
        return composed
    except Exception as e:
        logger.warning(f"Failed to create letterboxed clip: {e}, returning resized/original clip")
        return resized


def _set_duration(clip: VideoFileClip, duration: float) -> VideoFileClip:
    """Set the duration of a clip in a MoviePy v1/v2 compatible way."""
    if hasattr(clip, "set_duration"):
        return clip.set_duration(duration)  # type: ignore[attr-defined]
    return clip.with_duration(duration)  # type: ignore[attr-defined]


def _subclip(
    clip: VideoFileClip,
    start: float,
    end: float,
) -> VideoFileClip:
    """Extract a subclip [start, end) in a MoviePy v1/v2 compatible way."""
    if hasattr(clip, "subclip"):
        return clip.subclip(start, end)  # type: ignore[attr-defined]
    elif hasattr(clip, "subclipped"):
        return clip.subclipped(start, end)  # type: ignore[attr-defined]
    elif hasattr(clip, "with_subclip"):
        return clip.with_subclip(start, end)  # type: ignore[attr-defined]
    else:
        # Fallback: use slicing if available
        return clip[start:end]  # type: ignore[index]


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
    logger.warning("No supported speed change method found; returning original clip")
    return clip


def _create_black_frame(
    resolution: Tuple[int, int],
    duration: float,
) -> VideoFileClip:
    """Create a black placeholder clip for the given duration."""
    w, h = resolution
    clip = ColorClip(size=(w, h), color=(0, 0, 0))
    return _set_duration(clip, duration)


def _measure_text_size(text_clip: TextClip) -> Tuple[int, int]:
    """
    Attempt to measure text size in a way compatible with MoviePy v1 and v2.
    """
    # Prefer explicit size attribute
    if hasattr(text_clip, "size") and text_clip.size is not None:
        return tuple(int(x) for x in text_clip.size)  # type: ignore[return-value]

    # Fallbacks
    w = getattr(text_clip, "w", None)
    h = getattr(text_clip, "h", None)

    if w is not None and h is not None:
        return int(w), int(h)

    logger.debug("TextClip missing size/w/h; defaulting to minimal size (100x50)")
    return 100, 50


def _add_text_overlay(
    clip: VideoFileClip,
    text: str,
    resolution: Tuple[int, int],
) -> VideoFileClip:
    """
    Add a text overlay to a video clip for 1 second (phrase-ending word mode).
    """
    width, height = resolution

    # Create text clip with safe defaults
    try:
        txt_clip = TextClip(
            text=text,  # Use text= keyword argument for MoviePy v2
            font_size=LYRICS_FONT_SIZE,
            color=LYRICS_TEXT_COLOR,
            stroke_color=LYRICS_STROKE_COLOR,
            stroke_width=LYRICS_STROKE_WIDTH,
            method="caption",
            size=(int(width * 0.85), None),  # 85% of width for text wrapping
        )
    except TypeError:
        # Some MoviePy versions use a different signature for TextClip
        try:
            txt_clip = TextClip(
                text=text,  # Use text= keyword argument for MoviePy v2
                font_size=LYRICS_FONT_SIZE,
                color=LYRICS_TEXT_COLOR,
                stroke_color=LYRICS_STROKE_COLOR,
                stroke_width=LYRICS_STROKE_WIDTH,
            )
        except Exception as e:
            logger.warning(f"Failed to create TextClip for lyrics: {e}")
            return clip
    except Exception as e:
        logger.warning(f"Failed to create TextClip for lyrics: {e}")
        return clip

    # Measure text size in a robust way
    txt_w, txt_h = _measure_text_size(txt_clip)

    # Constrain height
    max_txt_h = int(height * LYRICS_MAX_HEIGHT_RATIO)
    if txt_h > max_txt_h:
        # Resize text to fit within max height while preserving aspect ratio
        scale_factor = max_txt_h / txt_h if txt_h else 1.0
        new_w = max(1, int(txt_w * scale_factor))
        new_h = max(1, int(txt_h * scale_factor))
        try:
            if hasattr(txt_clip, "resize"):
                txt_clip = txt_clip.resize(newsize=(new_w, new_h))  # type: ignore[attr-defined]
            else:
                txt_clip = txt_clip.resized((new_w, new_h))  # type: ignore[attr-defined]
            txt_w, txt_h = new_w, new_h
        except Exception as e:
            logger.warning(f"Failed to resize TextClip to fit height: {e}")

    # Position text in band specified by LYRICS_VERTICAL_POSITION
    # LYRICS_VERTICAL_POSITION is a fraction of height (0.0 top, 1.0 bottom)
    y_center = int(height * LYRICS_VERTICAL_POSITION)
    y_top = max(0, y_center - txt_h // 2)

    # Ensure text doesn't go off the bottom
    if y_top + txt_h > height:
        y_top = height - txt_h

    # Center horizontally
    x_left = max(0, (width - txt_w) // 2)

    # Set duration and position
    try:
        txt_clip = _set_duration(txt_clip, CLIP_DURATION_SECONDS)
        if hasattr(txt_clip, "set_position"):
            txt_clip = txt_clip.set_position((x_left, y_top))  # type: ignore[attr-defined]
        else:
            txt_clip = txt_clip.with_position((x_left, y_top))  # type: ignore[attr-defined]
    except Exception as e:
        logger.warning(f"Failed to configure TextClip duration/position: {e}")
        return clip

    # Compose text over original clip
    try:
        composed = CompositeVideoClip([clip, txt_clip])
        composed = _set_duration(composed, CLIP_DURATION_SECONDS)
        return composed
    except Exception as e:
        logger.warning(f"Failed to composite TextClip onto video: {e}")
        return clip


def _add_karaoke_overlay(
    clip: VideoFileClip,
    text: str,
    resolution: Tuple[int, int],
) -> VideoFileClip:
    """
    Add a karaoke-style overlay: multiple lines of text in a semi-transparent band.
    """
    width, height = resolution

    # Split into lines
    words = text.split()
    if not words:
        return clip

    lines: List[str] = []
    current_line: List[str] = []

    # Rough line wrapping: keep up to 3 lines max
    KARAOKE_MAX_LINES = 3
    for word in words:
        # If current line + new word too long, wrap
        if len(" ".join(current_line + [word])) > 40 and current_line:
            lines.append(" ".join(current_line))
            current_line = [word]
            if len(lines) >= KARAOKE_MAX_LINES:
                break
        else:
            current_line.append(word)

    if current_line and len(lines) < KARAOKE_MAX_LINES:
        lines.append(" ".join(current_line))

    # Create background band
    band_height = int(height * 0.3)  # 30% of height
    band_y_top = int(height * LYRICS_VERTICAL_POSITION) - band_height // 2
    band_y_top = max(0, band_y_top)
    band_y_bottom = min(height, band_y_top + band_height)
    band_height = band_y_bottom - band_y_top

    try:
        # Solid band, but we will treat it as translucent in overall design
        band_color = (0, 0, 0)
        band_clip = ColorClip(size=(width, band_height), color=band_color)
        band_clip = _set_duration(band_clip, CLIP_DURATION_SECONDS)
        KARAOKE_BACKGROUND_OPACITY = 0.6  # 60% opacity
        if hasattr(band_clip, "set_opacity"):
            band_clip = band_clip.set_opacity(KARAOKE_BACKGROUND_OPACITY)  # type: ignore[attr-defined]
        elif hasattr(band_clip, "with_opacity"):
            band_clip = band_clip.with_opacity(KARAOKE_BACKGROUND_OPACITY)  # type: ignore[attr-defined]
    except Exception as e:
        logger.warning(f"Failed to create karaoke background band: {e}")
        band_clip = None

    # Create text clips for each line
    text_clips: List[VideoFileClip] = []
    KARAOKE_LINE_SPACING = 10
    line_height = LYRICS_KARAOKE_FONT_SIZE + KARAOKE_LINE_SPACING
    total_text_height = line_height * len(lines)

    start_y = band_y_top + max(0, (band_height - total_text_height) // 2)

    for i, line in enumerate(lines):
        try:
            txt_clip = TextClip(
                text=line,  # Use text= keyword argument for MoviePy v2
                font_size=LYRICS_KARAOKE_FONT_SIZE,
                color=LYRICS_TEXT_COLOR,
                stroke_color=LYRICS_STROKE_COLOR,
                stroke_width=LYRICS_STROKE_WIDTH,
                method="caption",
                size=(int(width * 0.9), None),
            )
        except (TypeError, ValueError):
            try:
                txt_clip = TextClip(
                    text=line,  # Use text= keyword argument for MoviePy v2
                    font_size=LYRICS_KARAOKE_FONT_SIZE,
                    color=LYRICS_TEXT_COLOR,
                    stroke_color=LYRICS_STROKE_COLOR,
                    stroke_width=LYRICS_STROKE_WIDTH,
                )
            except Exception as e:
                logger.warning(f"Failed to create karaoke TextClip for line '{line}': {e}")
                continue
        except Exception as e:
            logger.warning(f"Failed to create karaoke TextClip for line '{line}': {e}")
            continue

        # Measure size
        txt_w, txt_h = _measure_text_size(txt_clip)

        # Position text line
        x_left = max(0, (width - txt_w) // 2)
        y_top = start_y + i * line_height

        # Ensure we don't go outside the band
        if y_top + txt_h > band_y_top + band_height:
            break

        try:
            txt_clip = _set_duration(txt_clip, CLIP_DURATION_SECONDS)
            if hasattr(txt_clip, "set_position"):
                txt_clip = txt_clip.set_position((x_left, y_top))  # type: ignore[attr-defined]
            else:
                txt_clip = txt_clip.with_position((x_left, y_top))  # type: ignore[attr-defined]
            text_clips.append(txt_clip)
        except Exception as e:
            logger.warning(f"Failed to configure karaoke text clip: {e}")
            continue

    # Composite band + text onto clip
    overlays: List[VideoFileClip] = []
    if band_clip is not None:
        try:
            if hasattr(band_clip, "set_position"):
                band_clip = band_clip.set_position((0, band_y_top))  # type: ignore[attr-defined]
            else:
                band_clip = band_clip.with_position((0, band_y_top))  # type: ignore[attr-defined]
            overlays.append(band_clip)
        except Exception as e:
            logger.warning(f"Failed to position karaoke band clip: {e}")

    overlays.extend(text_clips)

    if not overlays:
        return clip

    try:
        composed = CompositeVideoClip([clip] + overlays)
        composed = _set_duration(composed, CLIP_DURATION_SECONDS)
        return composed
    except Exception as e:
        logger.warning(f"Failed to composite karaoke overlay: {e}")
        return clip


def _download_giphy_gif(gif_url: str, cache_dir: Path) -> Optional[Path]:
    """
    Download a GIPHY MP4/GIF file and cache it locally.

    Uses the MD5 hash of the URL as the filename to ensure uniqueness.
    """
    try:
        # Create a deterministic filename from the URL
        url_hash = hashlib.md5(gif_url.encode("utf-8")).hexdigest()
        ext = ".mp4"
        filename = f"{url_hash}{ext}"
        cache_path = cache_dir / filename

        # If already cached, return existing path
        if cache_path.exists():
            logger.debug(f"Using cached GIPHY file for URL {gif_url}")
            return cache_path

        # Lazy import to avoid unnecessary dependency in some environments
        import requests

        logger.info(f"Downloading GIPHY MP4 from {gif_url}")
        response = requests.get(gif_url, stream=True, timeout=10)
        response.raise_for_status()

        # Write to temporary file first, then move into place
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp_file.write(chunk)
            tmp_path = Path(tmp_file.name)

        tmp_path.replace(cache_path)
        logger.info(f"Saved GIPHY MP4 to cache: {cache_path}")
        return cache_path

    except Exception as e:
        logger.warning(f"Failed to download GIPHY file from {gif_url}: {e}")
        return None


def _load_giphy_as_base_clip(
    gif_mp4_path: str,
    resolution: Tuple[int, int],
    speed: float = 1.0,
) -> VideoFileClip | None:
    """
    Load a GIPHY MP4/GIF clip and make it full-screen (same size as dance visuals).
    Letterboxes to match target resolution, applies speed adjustment, and sets duration to 1 second.
    
    Args:
        gif_mp4_path: Local path to GIPHY MP4/GIF file
        resolution: Target resolution (width, height)
        speed: Speed multiplier (for BPM sync)
        
    Returns:
        VideoFileClip ready to use as base clip, or None if loading fails
    """
    try:
        width, height = resolution
        
        # Load GIF/MP4 as video clip
        gif_clip = VideoFileClip(gif_mp4_path, audio=False)
        
        # Apply speed change (if needed)
        if speed != 1.0:
            gif_clip = _speedx(gif_clip, speed)
        
        # Resize with letterbox to target resolution (same as dance visuals)
        boxed = _resize_letterbox(gif_clip, resolution)
        
        # Set duration to exactly 1 second (loop if needed)
        gif_duration = getattr(boxed, 'duration', None) or 1.0
        if gif_duration < CLIP_DURATION_SECONDS:
            # Loop the GIF to match clip duration by concatenating copies
            try:
                from moviepy import concatenate_videoclips  # type: ignore
                num_loops = int(CLIP_DURATION_SECONDS / gif_duration) + 1
                looped_clips = [boxed] * num_loops
                result = concatenate_videoclips(looped_clips).with_duration(CLIP_DURATION_SECONDS)
            except Exception:
                # Fallback: just extend duration (will freeze on last frame)
                result = boxed.with_duration(CLIP_DURATION_SECONDS)
        else:
            result = _set_duration(boxed, CLIP_DURATION_SECONDS)
        
        logger.debug(f"Loaded GIPHY as base clip: {gif_mp4_path}, size={result.size if hasattr(result, 'size') else 'N/A'}")
        return result
    except Exception as e:
        logger.warning(f"Failed to load GIPHY as base clip from {gif_mp4_path}: {e}", exc_info=True)
        return None


def _add_giphy_overlay(
    base_clip: VideoFileClip,
    gif_mp4_path: str,
    resolution: Tuple[int, int],
) -> VideoFileClip:
    """
    Load a GIPHY MP4 clip (local path), resize it to a smaller box,
    place it in a corner, and composite it on top of the base clip.
    
    Args:
        base_clip: Base video clip (dancing background)
        gif_mp4_path: Local path to GIPHY MP4/GIF file
        resolution: Target resolution (width, height)
        
    Returns:
        CompositeVideoClip with GIF overlay, or original clip if overlay fails
    """
    try:
        width, height = resolution
        clip_duration = getattr(base_clip, 'duration', None) or CLIP_DURATION_SECONDS
        
        # Load GIF/MP4 as video clip
        gif_clip = VideoFileClip(gif_mp4_path, audio=False)
        
        # Resize to overlay size (30% of frame width, maintain aspect ratio)
        overlay_width = int(width * GIPHY_OVERLAY_SIZE_RATIO)
        overlay_height = int(gif_clip.h * (overlay_width / gif_clip.w))
        
        # Ensure overlay doesn't exceed reasonable bounds
        max_height = int(height * 0.4)  # Max 40% of frame height
        if overlay_height > max_height:
            overlay_height = max_height
            overlay_width = int(gif_clip.w * (overlay_height / gif_clip.h))
        
        if hasattr(gif_clip, "resize"):
            gif_clip = gif_clip.resize(newsize=(overlay_width, overlay_height))
        else:
            gif_clip = gif_clip.resized((overlay_width, overlay_height))
        
        # Set duration to match clip duration (loop if needed)
        gif_duration = getattr(gif_clip, 'duration', None) or 1.0
        if gif_duration < clip_duration:
            # Loop the GIF to match clip duration by concatenating copies
            try:
                from moviepy import concatenate_videoclips  # type: ignore
                num_loops = int(clip_duration / gif_duration) + 1
                looped_clips = [gif_clip] * num_loops
                gif_clip = concatenate_videoclips(looped_clips).with_duration(clip_duration)
            except Exception:
                # Fallback: just extend duration (will freeze on last frame)
                gif_clip = gif_clip.with_duration(clip_duration)
        else:
            gif_clip = gif_clip.with_duration(clip_duration)
        
        # Position overlay based on config
        if GIPHY_OVERLAY_POSITION == "bottom-right":
            x_position = width - overlay_width - GIPHY_OVERLAY_MARGIN
            y_position = height - overlay_height - GIPHY_OVERLAY_MARGIN
        elif GIPHY_OVERLAY_POSITION == "bottom-left":
            x_position = GIPHY_OVERLAY_MARGIN
            y_position = height - overlay_height - GIPHY_OVERLAY_MARGIN
        elif GIPHY_OVERLAY_POSITION == "top-right":
            x_position = width - overlay_width - GIPHY_OVERLAY_MARGIN
            y_position = GIPHY_OVERLAY_MARGIN
        elif GIPHY_OVERLAY_POSITION == "top-left":
            x_position = GIPHY_OVERLAY_MARGIN
            y_position = GIPHY_OVERLAY_MARGIN
        else:  # center
            x_position = (width - overlay_width) // 2
            y_position = (height - overlay_height) // 2
        
        # Ensure position is not negative
        x_position = max(0, x_position)
        y_position = max(0, y_position)
        
        # Set clip position
        if hasattr(gif_clip, "set_position"):
            gif_clip = gif_clip.set_position((x_position, y_position))  # type: ignore[attr-defined]
        else:
            gif_clip = gif_clip.with_position((x_position, y_position))  # type: ignore[attr-defined]
        
        # Get base clip size
        base_size = getattr(base_clip, 'size', None) or resolution
        
        # Composite: base clip first, then GIF overlay (GIF on top)
        result = CompositeVideoClip([base_clip, gif_clip], size=base_size)
        result = result.with_duration(clip_duration)
        
        logger.debug(f"Added GIPHY overlay: size={overlay_width}x{overlay_height}, position=({x_position}, {y_position})")
        
        # NOTE: Do NOT close gif_clip here - it's part of the composite and needs to remain open
        # until the composite is written. MoviePy will handle cleanup automatically.
        
        return result
    except Exception as e:
        logger.warning(f"Failed to add GIPHY overlay from {gif_mp4_path}: {e}", exc_info=True)
        # Ensure we always return a valid clip
        if base_clip is None:
            logger.error("base_clip is None in _add_giphy_overlay, creating fallback")
            return _create_black_frame(resolution, CLIP_DURATION_SECONDS)
        return base_clip


def _add_watermark(
    clip: VideoFileClip,
    resolution: Tuple[int, int],
) -> VideoFileClip:
    """
    Add a watermark overlay to a video clip.
    
    Args:
        clip: Base video clip to add watermark to
        resolution: Target resolution (width, height)
        
    Returns:
        CompositeVideoClip with watermark, or original clip if watermark fails
    """
    try:
        width, height = resolution
        clip_duration = getattr(clip, 'duration', None) or CLIP_DURATION_SECONDS
        
        # Try multiple fonts for watermark
        watermark_fonts = ["Arial", "Helvetica", "DejaVu-Sans", "Arial-Bold", "Helvetica-Bold", "DejaVu-Sans-Bold"]
        txt_clip = None
        
        for font_name in watermark_fonts + [None]:
            try:
                txt_clip = TextClip(
                    text=WATERMARK_TEXT,
                    font_size=WATERMARK_FONT_SIZE,
                    color=WATERMARK_TEXT_COLOR,
                    font=font_name,
                ).with_duration(clip_duration)
                logger.debug(f"Successfully created watermark text clip with font: {font_name}")
                break
            except Exception as e:
                logger.debug(f"Font {font_name} failed for watermark: {e}, trying next")
        
        if txt_clip is None:
            raise RuntimeError("Failed to create watermark text clip with any method")
        
        # Calculate position based on text size
        txt_w, txt_h = txt_clip.size if hasattr(txt_clip, 'size') and txt_clip.size else (0, 0)
        x_position = width - txt_w - WATERMARK_MARGIN_RIGHT
        y_position = height - txt_h - WATERMARK_MARGIN_BOTTOM
        
        x_position = max(0, x_position)
        y_position = max(0, y_position)
        
        txt_clip = txt_clip.with_position((x_position, y_position))
        
        if hasattr(txt_clip, "set_opacity"):
            txt_clip = txt_clip.set_opacity(WATERMARK_OPACITY)
        elif hasattr(txt_clip, "with_opacity"):
            txt_clip = txt_clip.with_opacity(WATERMARK_OPACITY)
        else:
            logger.debug("Opacity method not available, watermark will be fully opaque")
        
        base_size = getattr(clip, 'size', None) or resolution
        result = CompositeVideoClip([clip, txt_clip], size=base_size)
        result = result.with_duration(clip_duration)
        logger.debug(f"Created watermark overlay: text='{WATERMARK_TEXT}', position=({x_position}, {y_position}), opacity={WATERMARK_OPACITY}")
        return result
    except Exception as e:
        logger.error(f"Failed to create watermark overlay: {e}", exc_info=True)
        logger.warning("Returning original clip without watermark overlay due to error")
        return clip


def load_blacklist(blacklist_path: Path) -> Set[str]:
    """
    Load blacklisted video filenames from a JSON file.
    
    Blacklisted files are source videos that failed to load or process correctly.
    They are excluded from future random selection to avoid repeated errors.
    
    Args:
        blacklist_path: Path to the blacklist JSON file
        
    Returns:
        Set of blacklisted filenames (relative to video_folder)
    """
    if not blacklist_path.exists():
        return set()
    
    try:
        with open(blacklist_path, 'r') as f:
            data = json.load(f)
        if isinstance(data, list):
            return set(str(name) for name in data)
        logger.warning(f"Unexpected blacklist format in {blacklist_path}, expected list")
        return set()
    except Exception as e:
        logger.warning(f"Failed to load blacklist from {blacklist_path}: {e}")
        return set()


def save_blacklist(blacklist_path: Path, blacklist: Set[str]) -> None:
    """
    Save blacklisted video filenames to a JSON file.
    """
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
        Tuple of (start_sec, clip_paths, blacklist)
    """
    checkpoint_file = checkpoint_dir / "checkpoint.json"
    clip_list_file = checkpoint_dir / "clip_list.json"
    blacklist_file = checkpoint_dir / "blacklist.json"
    
    if not checkpoint_file.exists():
        return 0, [], set()
    
    try:
        with open(checkpoint_file, 'r') as f:
            checkpoint_data = json.load(f)
        start_sec = int(checkpoint_data.get("last_completed_second", 0))
    except Exception as e:
        logger.warning(f"Failed to load checkpoint from {checkpoint_file}: {e}")
        start_sec = 0
    
    clip_paths: List[Path] = []
    if clip_list_file.exists():
        try:
            with open(clip_list_file, 'r') as f:
                clip_list = json.load(f)
            if isinstance(clip_list, list):
                clip_paths = [checkpoint_dir / str(p) for p in clip_list]
        except Exception as e:
            logger.warning(f"Failed to load clip list from {clip_list_file}: {e}")
    
    blacklist = load_blacklist(blacklist_file)
    
    return start_sec, clip_paths, blacklist


def save_checkpoint(
    checkpoint_dir: Path,
    last_completed_second: int,
    clip_paths: List[Path],
    blacklist: Set[str],
) -> None:
    """
    Save checkpoint data to disk.
    
    Args:
        checkpoint_dir: Directory where checkpoint files are stored
        last_completed_second: Last fully processed second index (0-based, inclusive)
        clip_paths: List of Path objects for generated clips
        blacklist: Set of blacklisted filenames
    """
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    
    checkpoint_file = checkpoint_dir / "checkpoint.json"
    clip_list_file = checkpoint_dir / "clip_list.json"
    blacklist_file = checkpoint_dir / "blacklist.json"
    
    try:
        checkpoint_data = {
            "last_completed_second": last_completed_second,
            "num_clips": len(clip_paths),
        }
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        
        clip_list_data = [p.name for p in clip_paths]
        with open(clip_list_file, 'w') as f:
            json.dump(clip_list_data, f, indent=2)
        
        save_blacklist(blacklist_file, blacklist)
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
    giphy_segment_plan: Dict[int, Dict[str, Any]] | None = None,
) -> List[Path]:
    """
    Build visual track by generating 1-second clips and writing them to disk.
    
    Clips are picked randomly from `video_folder`, sped up or slowed down
    based on the BPM at each second, resized to `target_resolution` with
    letterboxing, and written as individual MP4 files. Supports resuming
    via checkpoints to avoid recomputing already generated clips.
    
    Args:
        video_folder: Folder containing MP4 clips to sample from
        bpm_values: List of BPM values for each second
        duration_seconds: Total video duration in seconds
        target_resolution: Output resolution (width, height)
        base_bpm: Reference BPM for normal playback speed
        speed_min: Minimum speed factor (for very low BPM)
        speed_max: Maximum speed factor (for very high BPM)
        checkpoint_dir: Directory to store checkpoint files (if None, use CHECKPOINTS_DIR)
        lyrics_mapping: Optional mapping second -> phrase-ending word for overlay
        karaoke_mapping: Optional mapping second -> text line for karaoke overlay
        giphy_segment_plan: Optional mapping for GIPHY overlays per segment:
                            {segment_id: {"gif_query": ..., "gif_urls": [...], "start": ..., "end": ...}}
                            For future GIPHY overlay compositing. Currently threaded through but not used.
        
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

    # Precompute mapping from second -> segment info for GIPHY overlays
    # This allows quick lookup during the main loop
    second_to_giphy_segment: Dict[int, Dict[str, Any]] = {}
    giphy_cache_dir: Path | None = None
    
    if giphy_segment_plan is not None and len(giphy_segment_plan) > 0:
        # Create cache directory for GIPHY downloads
        giphy_cache_dir = checkpoint_dir / "giphy_cache"
        giphy_cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Build mapping: for each segment, assign it to all integer seconds it covers
        for segment_id, segment_data in giphy_segment_plan.items():
            segment_start = segment_data.get("start", 0.0)
            segment_end = segment_data.get("end", float('inf'))
            gif_urls = segment_data.get("gif_urls", [])
            
            if not gif_urls:
                logger.debug(f"Segment {segment_id} has no GIF URLs, skipping")
                continue
            
            # Assign this segment to all integer seconds it covers
            for sec in range(int(segment_start), min(int(segment_end) + 1, duration_seconds)):
                if sec not in second_to_giphy_segment:
                    second_to_giphy_segment[sec] = segment_data
                # If multiple segments overlap, prefer the one that starts earlier
                elif segment_data.get("start", 0.0) < second_to_giphy_segment[sec].get("start", 0.0):
                    second_to_giphy_segment[sec] = segment_data
        
        logger.info(f"Precomputed GIPHY segment mapping: {len(second_to_giphy_segment)} seconds will use GIPHY GIFs as base clips")

    clip_paths: List[Path] = saved_clip_paths.copy()
    checkpoint_interval = CHECKPOINT_INTERVAL
    skipped_count = 0

    # Safety: ensure BPM list is at least duration_seconds long
    if len(bpm_values) < duration_seconds:
        last_bpm = bpm_values[-1] if bpm_values else base_bpm
        bpm_values = bpm_values + [last_bpm] * (duration_seconds - len(bpm_values))

    for sec in range(start_sec, duration_seconds):
        logger.debug(f"Building clip for second {sec}/{duration_seconds}")

        # Load BPM for this second
        if sec < len(bpm_values):
            local_bpm = bpm_values[sec]
        else:
            local_bpm = base_bpm
        speed = float(np.clip(local_bpm / base_bpm, speed_min, speed_max))

        checkpoint_clip_path = checkpoint_dir / f"clip_{sec:06d}.mp4"

        # Check if we should use a GIPHY GIF as the base clip for this second
        use_giphy = False
        gif_urls: List[str] = []
        gif_query = "unknown"
        
        if second_to_giphy_segment and sec in second_to_giphy_segment:
            segment_data = second_to_giphy_segment[sec]
            gif_urls = segment_data.get("gif_urls", [])
            gif_query = segment_data.get("gif_query", "unknown")
            use_giphy = len(gif_urls) > 0 and giphy_cache_dir is not None
        
        if use_giphy:
            # Use GIPHY GIF as base clip (full screen, same size as dance visuals)
            try:
                selected_gif_url = random.choice(gif_urls)
                logger.debug(f"Using GIPHY GIF for query '{gif_query}' at second {sec}")
                
                # Download and cache the GIF
                cached_path = _download_giphy_gif(selected_gif_url, giphy_cache_dir)
                
                if cached_path:
                    # Load GIPHY GIF as full-screen base clip
                    one_sec = _load_giphy_as_base_clip(str(cached_path), target_resolution, speed)
                    if one_sec is None:
                        logger.warning(f"Failed to load GIPHY GIF for '{gif_query}' at second {sec}, falling back to bank")
                        use_giphy = False  # Fall through to bank logic
                    else:
                        logger.debug(f"Successfully loaded GIPHY GIF for '{gif_query}' at second {sec}")
                else:
                    logger.warning(f"Failed to cache GIPHY file for '{gif_query}' at second {sec}, falling back to bank")
                    use_giphy = False  # Fall through to bank logic
            except Exception as e:
                logger.warning(f"Failed to load GIPHY GIF at second {sec}: {e}", exc_info=True)
                use_giphy = False  # Fall through to bank logic
        
        # If not using GIPHY (or GIPHY failed), use dance GIF from bank
        if not use_giphy:
            # Try to load a random video from bank with error handling
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
                    break
                except Exception as e:
                    logger.warning(f"Failed to load video {candidate}: {e}")
                    blacklist.add(candidate.name)
                    if video_clip is not None:
                        video_clip.close()
                    video_clip = None

            if video_clip is None:
                logger.error("Failed to load any video clip after multiple attempts; using black frame")
                one_sec = _create_black_frame(target_resolution, CLIP_DURATION_SECONDS)
                skipped_count += 1
            else:
                try:
                    duration = video_clip.duration or CLIP_DURATION_SECONDS
                    if duration <= 0:
                        raise ValueError(f"Invalid clip duration: {duration}")

                    # Extract a random window and speed it via BPM
                    base_window = BASE_WINDOW_SECONDS
                    max_start = max(duration - base_window, 0)
                    start_time = random.uniform(0, max_start)
                    end_time = start_time + base_window

                    sub = _subclip(video_clip, start_time, min(end_time, duration))

                    # Apply speed change
                    sub = _speedx(sub, speed)

                    # Resize with letterbox to target res
                    boxed = _resize_letterbox(sub, target_resolution)

                    # Set duration to exactly 1 second
                    one_sec = _set_duration(boxed, CLIP_DURATION_SECONDS)
                except Exception as e:
                    logger.warning(f"Error processing video {video_path}: {e}")
                    blacklist.add(video_path.name if video_path else "unknown")
                    if video_clip is not None:
                        video_clip.close()
                    one_sec = _create_black_frame(target_resolution, CLIP_DURATION_SECONDS)
                    skipped_count += 1
                # NOTE: Do NOT close video_clip here - one_sec maintains a reference chain
                # (one_sec → boxed → sub → video_clip) and needs it open until write_videofile completes.
                # The clip will be cleaned up when one_sec is closed after writing.

        # Note: Lyric overlays have been removed - GIPHY GIFs are now used as base clips (not overlays)

        # Write 1-second clip to disk
        # Safety check: ensure one_sec is not None and is valid
        if one_sec is None:
            logger.error(f"one_sec is None for second {sec}, creating black frame fallback")
            one_sec = _create_black_frame(target_resolution, CLIP_DURATION_SECONDS)
            skipped_count += 1
        
        # Additional validation: ensure clip has required attributes
        if not hasattr(one_sec, 'duration') or getattr(one_sec, 'duration', None) is None:
            logger.warning(f"Clip for second {sec} has invalid duration, recreating black frame")
            one_sec = _create_black_frame(target_resolution, CLIP_DURATION_SECONDS)
            skipped_count += 1
        
        try:
            # Ensure clip is valid before writing
            if one_sec is None:
                raise ValueError("one_sec is None after all checks")
            
            one_sec.write_videofile(  # type: ignore[attr-defined]
                str(checkpoint_clip_path),
                codec="libx264",
                fps=DEFAULT_FPS,
                audio=False,
            )
            clip_paths.append(checkpoint_clip_path)
        except Exception as e:
            logger.error(f"Failed to write clip for second {sec}: {e}", exc_info=True)
            # Try to create and write a black frame as absolute fallback
            try:
                fallback_clip = _create_black_frame(target_resolution, CLIP_DURATION_SECONDS)
                fallback_clip.write_videofile(
                    str(checkpoint_clip_path),
                    codec="libx264",
                    fps=DEFAULT_FPS,
                    audio=False,
                )
                clip_paths.append(checkpoint_clip_path)
                logger.info(f"Created black frame fallback for second {sec}")
            except Exception as fallback_error:
                logger.error(f"Failed to create fallback black frame for second {sec}: {fallback_error}")
                blacklist.add(video_path.name if video_path else f"unknown_sec_{sec}")
                skipped_count += 1
        finally:
            try:
                one_sec.close()
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
