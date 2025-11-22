"""
Configuration constants for AudioGiphy.

This module centralizes all configuration values and constants used across
the codebase, eliminating magic numbers and duplicate definitions.
"""

from pathlib import Path
from typing import Tuple

# Paths (relative to project root)
CHECKPOINTS_DIR = "checkpoints"

# Video defaults
DEFAULT_FPS = 30
DEFAULT_RESOLUTION: Tuple[int, int] = (1080, 1920)  # width, height
CLIP_DURATION_SECONDS = 1.0

# Audio analysis defaults
BPM_WINDOW_SECONDS = 8.0
BPM_HOP_SECONDS = 4.0
DEFAULT_BPM_FALLBACK = 120.0

# Visual builder defaults
BASE_WINDOW_SECONDS = 1.2  # For extracting subclips from source videos
CHECKPOINT_INTERVAL = 50  # Save checkpoint every N seconds

# Lyrics analysis defaults
WHISPER_MODEL_SIZE = "large"  # Options: tiny, base, small, medium, large (large = highest accuracy, slower)
WHISPER_DEFAULT_LANGUAGE = "en"  # English
WHISPER_TEMPERATURE = 0.0  # More deterministic, less random (0.0 = most deterministic)
WHISPER_COMPRESSION_RATIO_THRESHOLD = 2.4  # Filter out hallucinations (lower = stricter)
WHISPER_LOGPROB_THRESHOLD = -1.0  # Filter low-confidence words (lower = stricter)
WHISPER_NO_SPEECH_THRESHOLD = 0.6  # Better for music with beats (lower = more sensitive)

# Lyrics overlay defaults
LYRICS_FONT_SIZE = 120  # Font size for lyric overlays (large, centered, not cropped)
LYRICS_KARAOKE_FONT_SIZE = 80  # Font size for karaoke mode (smaller than phrase-ending overlay)
LYRICS_TEXT_COLOR = "white"  # Text color
LYRICS_STROKE_COLOR = "white"  # Outline/stroke color (white outline as requested)
LYRICS_STROKE_WIDTH = 8  # Outline width (thicker for white-on-white visibility effect)
LYRICS_VERTICAL_POSITION = 0.25  # Vertical position (0.0 = top, 1.0 = bottom, 0.25 = upper quarter)
LYRICS_MAX_HEIGHT_RATIO = 0.3  # Maximum height for text as ratio of frame height (30% prevents cropping)

# Watermark defaults
WATERMARK_TEXT = "Powered by GIPHY"  # Watermark text content
WATERMARK_FONT_SIZE = 40  # Font size for watermark (smaller than lyrics, readable but subtle)
WATERMARK_TEXT_COLOR = "white"  # Watermark text color
WATERMARK_OPACITY = 0.8  # Watermark opacity (0.0 = transparent, 1.0 = opaque, 0.8 = 80% visible)
WATERMARK_MARGIN_RIGHT = 20  # Margin from right edge in pixels
WATERMARK_MARGIN_BOTTOM = 20  # Margin from bottom edge in pixels

# GIPHY overlay defaults
GIPHY_OVERLAY_SIZE_RATIO = 0.3  # Size of GIPHY overlay as ratio of frame width (30% of width)
GIPHY_OVERLAY_POSITION = "bottom-right"  # Position: "bottom-right", "bottom-left", "top-right", "top-left", "center"
GIPHY_OVERLAY_MARGIN = 20  # Margin from edges in pixels

