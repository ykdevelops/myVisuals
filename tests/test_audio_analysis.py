"""
Smoke tests for audio analysis module.
Verifies that functions can be called without crashing.
"""
import pytest
from pathlib import Path

from audiogiphy.audio_analysis import (
    analyze_bpm_segments,
    analyze_bpm_per_second,
    analyze_global_bpm,
    BpmSegment,
    bpm_timeline_from_segments,
)


def test_bpm_segment_dataclass():
    """Test that BpmSegment can be created."""
    segment = BpmSegment(start=0.0, end=10.0, bpm=120.0)
    assert segment.start == 0.0
    assert segment.end == 10.0
    assert segment.bpm == 120.0


def test_bpm_timeline_from_segments():
    """Test that bpm_timeline_from_segments works with sample data."""
    segments = [
        BpmSegment(start=0.0, end=5.0, bpm=120.0),
        BpmSegment(start=5.0, end=10.0, bpm=140.0),
    ]
    timeline = bpm_timeline_from_segments(segments, duration_seconds=10)
    assert len(timeline) == 10
    assert timeline[0] == 120.0
    assert timeline[5] == 140.0


def test_analyze_bpm_segments_missing_file():
    """Test that analyze_bpm_segments raises FileNotFoundError for missing file."""
    with pytest.raises(FileNotFoundError):
        analyze_bpm_segments("nonexistent_file.wav")


def test_analyze_bpm_per_second_missing_file():
    """Test that analyze_bpm_per_second raises FileNotFoundError for missing file."""
    with pytest.raises(FileNotFoundError):
        analyze_bpm_per_second("nonexistent_file.wav", duration_seconds=10)


def test_analyze_global_bpm_missing_file():
    """Test that analyze_global_bpm raises FileNotFoundError for missing file."""
    with pytest.raises(FileNotFoundError):
        analyze_global_bpm("nonexistent_file.wav", duration_seconds=10)


@pytest.mark.skipif(
    not Path("clean mashup mix 88 to 134.wav").exists(),
    reason="Sample audio file not found"
)
def test_analyze_bpm_per_second_with_sample():
    """Test BPM analysis with actual sample file if available."""
    audio_path = "clean mashup mix 88 to 134.wav"
    duration = 10  # Analyze first 10 seconds
    bpm_values = analyze_bpm_per_second(audio_path, duration)
    assert len(bpm_values) == duration
    assert all(isinstance(bpm, float) and bpm > 0 for bpm in bpm_values)

