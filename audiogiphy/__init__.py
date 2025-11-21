"""
AudioGiphy - BPM-driven video visualizer MVP.

An experimental tool that turns a music track into a vertical video
made from 1 second GIF clips, roughly synced to the track BPM.
"""

__version__ = "0.1.0"

__all__ = [
    "render_video",
    "analyze_bpm_segments",
    "analyze_bpm_per_second",
    "analyze_global_bpm",
    "BpmSegment",
    "build_visual_track",
    "GiphyClient",
    "app",
    "detect_lyrics",
    "LyricsResult",
    "LyricWord",
    "extract_lyric_anchors",
    "map_anchors_to_seconds",
    "build_karaoke_mapping",
]

from audiogiphy.render_pipeline import render_video
from audiogiphy.audio_analysis import (
    BpmSegment,
    analyze_bpm_segments,
    analyze_bpm_per_second,
    analyze_global_bpm,
)
from audiogiphy.visual_builder import build_visual_track
from audiogiphy.giphy_placeholder import GiphyClient
from audiogiphy.lyrics_analysis import detect_lyrics, LyricsResult, LyricWord
from audiogiphy.lyrics_overlays import extract_lyric_anchors, map_anchors_to_seconds, build_karaoke_mapping

# Lazy import for API (only if flask is installed)
try:
    from audiogiphy.api import app
except ImportError:
    app = None

