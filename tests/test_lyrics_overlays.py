"""
Smoke tests for lyrics overlays module.
"""
import pytest
import json
import tempfile
from pathlib import Path

from audiogiphy.lyrics_overlays import (
    extract_lyric_anchors,
    map_anchors_to_seconds,
    build_karaoke_mapping,
    is_stopword,
    find_last_content_word,
)


def test_is_stopword():
    """Test stopword detection."""
    assert is_stopword("the")
    assert is_stopword("a")
    assert is_stopword("you")
    assert not is_stopword("glamorous")
    assert not is_stopword("home")
    assert not is_stopword("money")


def test_find_last_content_word():
    """Test finding last content word in phrase."""
    words = [
        {"word": "take", "start": 10.0, "end": 10.5},
        {"word": "your", "start": 10.5, "end": 11.0},
        {"word": "broke", "start": 11.0, "end": 11.5},
        {"word": "ass", "start": 11.5, "end": 12.0},
        {"word": "home", "start": 12.0, "end": 12.5},
    ]
    result = find_last_content_word(words)
    assert result is not None
    assert result["word"] == "home"


def test_extract_lyric_anchors():
    """Test extracting anchors from JSON file."""
    # Create temporary JSON file
    test_data = {
        "transcript": "test",
        "words": [
            {"word": "Are", "start": 0.0, "end": 0.5},
            {"word": "you", "start": 0.5, "end": 1.0},
            {"word": "ready", "start": 1.0, "end": 1.5},
            {"word": "take", "start": 10.0, "end": 10.5},
            {"word": "your", "start": 10.5, "end": 11.0},
            {"word": "broke", "start": 11.0, "end": 11.5},
            {"word": "ass", "start": 11.5, "end": 12.0},
            {"word": "home", "start": 12.0, "end": 12.5},
        ],
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_data, f)
        temp_path = f.name
    
    try:
        anchors = extract_lyric_anchors(temp_path)
        assert len(anchors) > 0
        assert all("word" in a and "time_end_sec" in a for a in anchors)
    finally:
        Path(temp_path).unlink()


def test_map_anchors_to_seconds():
    """Test mapping anchors to second indices."""
    anchors = [
        {"word": "ready", "time_end_sec": 1.5},
        {"word": "home", "time_end_sec": 12.5},
        {"word": "glamorous", "time_end_sec": 22.0},
    ]
    
    mapping = map_anchors_to_seconds(anchors, duration_seconds=30)
    
    assert 1 in mapping
    assert mapping[1] == "ready"
    assert 12 in mapping
    assert mapping[12] == "home"
    assert 22 in mapping
    assert mapping[22] == "glamorous"


def test_map_anchors_multiple_in_same_second():
    """Test that multiple anchors in same second keep the latest."""
    anchors = [
        {"word": "first", "time_end_sec": 5.2},
        {"word": "second", "time_end_sec": 5.8},
    ]
    
    mapping = map_anchors_to_seconds(anchors, duration_seconds=10)
    
    assert 5 in mapping
    assert mapping[5] == "second"  # Should keep the later one


def test_build_karaoke_mapping():
    """Test building karaoke mapping from JSON file."""
    # Create temporary JSON file with word data
    test_data = {
        "transcript": "Take your broke",
        "language": "en",
        "duration": 3.0,
        "words": [
            {"word": "Take", "start": 0.5, "end": 0.8},
            {"word": "your", "start": 0.8, "end": 1.2},
            {"word": "broke", "start": 1.2, "end": 1.5},
        ],
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_data, f)
        temp_path = f.name
    
    try:
        mapping = build_karaoke_mapping(temp_path, duration_seconds=3)
        
        # Second 0 should have "TAKE" (word starts at 0.5, ends at 0.8, intersects [0, 1))
        assert 0 in mapping
        assert mapping[0] == "TAKE"
        
        # Second 1 should have "YOUR" (word starts at 0.8, ends at 1.2, intersects [1, 2))
        # Note: word at 0.8-1.2 spans both second 0 and 1, but we check start < s+1 and end > s
        # For second 1: start=0.8 < 2 (✓), end=1.2 > 1 (✓) -> included
        assert 1 in mapping
        assert "YOUR" in mapping[1]
        
        # Second 2 should have "BROKE" (word starts at 1.2, ends at 1.5, intersects [2, 3))
        # Actually, word at 1.2-1.5 doesn't intersect [2, 3), so it should be in second 1
        # Let me verify: for second 2: start=1.2 < 3 (✓), end=1.5 > 2 (✗) -> not included
        # For second 1: start=1.2 < 2 (✓), end=1.5 > 1 (✓) -> included
        assert 1 in mapping
        assert "BROKE" in mapping[1]
        
    finally:
        Path(temp_path).unlink()


def test_build_karaoke_mapping_edge_cases():
    """Test karaoke mapping with edge cases."""
    # Test word spanning multiple seconds
    test_data = {
        "transcript": "test",
        "language": "en",
        "duration": 5.0,
        "words": [
            {"word": "word", "start": 0.5, "end": 2.5},  # Spans seconds 0, 1, 2
            {"word": "exact", "start": 3.0, "end": 3.5},  # Starts exactly at second boundary
            {"word": "end", "start": 4.5, "end": 5.0},  # Ends exactly at duration
        ],
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_data, f)
        temp_path = f.name
    
    try:
        mapping = build_karaoke_mapping(temp_path, duration_seconds=5)
        
        # Word spanning 0.5-2.5 should appear in seconds 0, 1, 2
        assert 0 in mapping
        assert "WORD" in mapping[0]
        assert 1 in mapping
        assert "WORD" in mapping[1]
        assert 2 in mapping
        assert "WORD" in mapping[2]
        
        # Word at exact boundary should appear
        assert 3 in mapping
        assert "EXACT" in mapping[3]
        
        # Word ending at duration should appear in second 4
        assert 4 in mapping
        assert "END" in mapping[4]
        
    finally:
        Path(temp_path).unlink()


def test_build_karaoke_mapping_empty_seconds():
    """Test karaoke mapping with empty seconds."""
    test_data = {
        "transcript": "test",
        "language": "en",
        "duration": 5.0,
        "words": [
            {"word": "first", "start": 0.5, "end": 0.8},
            {"word": "last", "start": 4.0, "end": 4.5},
        ],
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_data, f)
        temp_path = f.name
    
    try:
        mapping = build_karaoke_mapping(temp_path, duration_seconds=5)
        
        # Only seconds 0 and 4 should have words
        assert 0 in mapping
        assert 4 in mapping
        # Seconds 1, 2, 3 should be empty (not in mapping)
        assert 1 not in mapping
        assert 2 not in mapping
        assert 3 not in mapping
        
    finally:
        Path(temp_path).unlink()


def test_build_karaoke_mapping_multiple_words_per_second():
    """Test karaoke mapping with multiple words in same second."""
    test_data = {
        "transcript": "test",
        "language": "en",
        "duration": 2.0,
        "words": [
            {"word": "Take", "start": 0.2, "end": 0.5},
            {"word": "your", "start": 0.5, "end": 0.8},
            {"word": "broke", "start": 0.8, "end": 1.1},
            {"word": "ass", "start": 1.1, "end": 1.4},
        ],
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_data, f)
        temp_path = f.name
    
    try:
        mapping = build_karaoke_mapping(temp_path, duration_seconds=2)
        
        # Second 0 should have all words in chronological order
        assert 0 in mapping
        text_line = mapping[0]
        assert "TAKE" in text_line
        assert "YOUR" in text_line
        assert "BROKE" in text_line
        # Verify order: TAKE should come before YOUR, YOUR before BROKE
        assert text_line.index("TAKE") < text_line.index("YOUR")
        assert text_line.index("YOUR") < text_line.index("BROKE")
        
        # Second 1 should have words that intersect [1, 2)
        assert 1 in mapping
        # BROKE (0.8-1.1) intersects [1, 2): start=0.8 < 2 (✓), end=1.1 > 1 (✓)
        # ASS (1.1-1.4) intersects [1, 2): start=1.1 < 2 (✓), end=1.4 > 1 (✓)
        assert "BROKE" in mapping[1] or "ASS" in mapping[1]
        
    finally:
        Path(temp_path).unlink()

