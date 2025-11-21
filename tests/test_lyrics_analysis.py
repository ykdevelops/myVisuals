"""
Smoke tests for lyrics analysis module.
Verifies that functions can be called without crashing.
"""
import pytest
from pathlib import Path

from audiogiphy.lyrics_analysis import (
    detect_lyrics,
    LyricsResult,
    LyricWord,
)


def test_lyric_word_dataclass():
    """Test that LyricWord can be created."""
    word = LyricWord(word="hello", start=0.5, end=0.8)
    assert word.word == "hello"
    assert word.start == 0.5
    assert word.end == 0.8


def test_lyrics_result_dataclass():
    """Test that LyricsResult can be created."""
    words = [
        LyricWord(word="hello", start=0.0, end=0.5),
        LyricWord(word="world", start=0.5, end=1.0),
    ]
    result = LyricsResult(
        transcript="hello world",
        words=words,
        language="en",
        duration=1.0,
    )
    assert result.transcript == "hello world"
    assert len(result.words) == 2
    assert result.language == "en"
    assert result.duration == 1.0


def test_detect_lyrics_missing_file():
    """Test that detect_lyrics raises FileNotFoundError for missing file."""
    try:
        from audiogiphy.lyrics_analysis import WHISPER_AVAILABLE
        if not WHISPER_AVAILABLE:
            pytest.skip("Whisper not installed")
    except ImportError:
        pytest.skip("Whisper not installed")
    
    with pytest.raises(FileNotFoundError):
        detect_lyrics("nonexistent_file.wav")


@pytest.mark.skipif(
    not Path("clean mashup mix 88 to 134.wav").exists(),
    reason="Sample audio file not found"
)
def test_detect_lyrics_with_sample():
    """Test lyrics detection with actual sample file if available."""
    try:
        from audiogiphy.lyrics_analysis import WHISPER_AVAILABLE
        if not WHISPER_AVAILABLE:
            pytest.skip("Whisper not installed")
    except ImportError:
        pytest.skip("Whisper not installed")
    
    audio_path = "clean mashup mix 88 to 134.wav"
    result = detect_lyrics(audio_path)
    
    assert isinstance(result, LyricsResult)
    assert len(result.transcript) > 0
    assert len(result.words) > 0
    assert result.language is not None
    assert result.duration > 0
    
    # Verify word structure
    for word in result.words:
        assert isinstance(word, LyricWord)
        assert len(word.word) > 0
        assert word.start >= 0
        assert word.end >= word.start

