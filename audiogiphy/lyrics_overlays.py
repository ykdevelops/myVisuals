"""
Lyrics Overlay Module.

This module handles parsing lyric detection output and extracting
phrase-ending words for overlay on video clips.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

__all__ = [
    "extract_lyric_anchors",
    "map_anchors_to_seconds",
    "build_karaoke_mapping",
]

logger = logging.getLogger("audiogiphy.lyrics_overlays")

# Common stopwords to skip when choosing phrase-ending words
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "can", "it",
    "its", "this", "that", "these", "those", "i", "you", "he", "she",
    "we", "they", "them", "us", "me", "him", "her", "my", "your", "his",
    "her", "our", "their", "what", "which", "who", "whom", "whose",
    "where", "when", "why", "how", "all", "each", "every", "both",
    "few", "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "just", "now",
}


def is_stopword(word: str) -> bool:
    """
    Check if a word is a stopword.
    
    Args:
        word: Word to check (will be lowercased and stripped)
        
    Returns:
        True if word is a stopword
    """
    cleaned = word.lower().strip().rstrip(".,!?;:")
    return cleaned in STOPWORDS or len(cleaned) <= 1


def find_last_content_word(words: List[dict]) -> Optional[dict]:
    """
    Find the last non-stopword word in a list of words.
    
    Args:
        words: List of word dicts with 'word', 'start', 'end' keys
        
    Returns:
        Word dict of last content word, or None if all are stopwords
    """
    for word_data in reversed(words):
        word_text = word_data.get("word", "").strip()
        if not is_stopword(word_text):
            return word_data
    # If all are stopwords, return the last one anyway
    return words[-1] if words else None


def detect_phrases_from_words(words: List[dict], gap_threshold: float = 1.0) -> List[List[dict]]:
    """
    Detect phrases from word list by finding gaps in timestamps.
    
    Groups words into phrases based on time gaps. If words are more than
    gap_threshold seconds apart, they belong to different phrases.
    
    Uses a more lenient threshold for music with instrumental breaks.
    
    Args:
        words: List of word dicts with 'word', 'start', 'end' keys
        gap_threshold: Seconds of gap to consider a new phrase (default: 2.0 for music)
        
    Returns:
        List of phrases, each phrase is a list of word dicts
    """
    if not words:
        return []
    
    phrases: List[List[dict]] = []
    current_phrase: List[dict] = [words[0]]
    
    for i in range(1, len(words)):
        prev_end = words[i - 1].get("end", 0.0)
        curr_start = words[i].get("start", 0.0)
        gap = curr_start - prev_end
        
        if gap > gap_threshold:
            # New phrase detected
            phrases.append(current_phrase)
            current_phrase = [words[i]]
        else:
            current_phrase.append(words[i])
    
    # Add final phrase
    if current_phrase:
        phrases.append(current_phrase)
    
    return phrases


def detect_phrases_by_punctuation(words: List[dict]) -> List[List[dict]]:
    """
    Detect phrases by splitting on punctuation marks and natural boundaries.
    
    This is the primary method for phrase detection. Splits on:
    1. Punctuation marks (., !, ?, ;, :)
    2. Natural pauses (gaps > 0.3s but < 2.0s to avoid instrumental breaks)
    3. Words that are likely phrase endings (like "home", "say") followed by sentence starts
    
    Args:
        words: List of word dicts with 'word', 'start', 'end' keys
        
    Returns:
        List of phrases, each phrase is a list of word dicts
    """
    if not words:
        return []
    
    phrases: List[List[dict]] = []
    current_phrase: List[dict] = []
    
    # Words that often end phrases in lyrics (even without punctuation)
    phrase_ending_words = {"home", "say", "yeah", "ready", "go", "know", "see", "do", "be"}
    
    for i, word_data in enumerate(words):
        current_phrase.append(word_data)
        word_text = word_data.get("word", "").strip().rstrip(".,!?;:")
        word_lower = word_text.lower()
        
        # Check if word ends with punctuation
        original_word = word_data.get("word", "").strip()
        if original_word and original_word[-1] in ".,!?;:":
            # This word ends a phrase
            phrases.append(current_phrase)
            current_phrase = []
        # Check for natural pauses (gaps > 0.3s but < 2.0s)
        elif i < len(words) - 1:
            next_word = words[i + 1]
            gap = next_word.get("start", 0.0) - word_data.get("end", 0.0)
            # If there's a meaningful gap, treat it as a phrase boundary
            if 0.3 < gap < 2.0:
                phrases.append(current_phrase)
                current_phrase = []
            # Also check if this word is a phrase-ending word and next word starts a new thought
            # (e.g., "home" followed by "you" or capitalized word)
            elif word_lower in phrase_ending_words:
                next_word_text = next_word.get("word", "").strip()
                # If next word is capitalized or a common sentence starter, end phrase here
                if next_word_text and (next_word_text[0].isupper() or next_word_text.lower() in {"if", "and", "but", "then", "you", "i"}):
                    phrases.append(current_phrase)
                    current_phrase = []
    
    # Add final phrase if there are remaining words
    if current_phrase:
        phrases.append(current_phrase)
    
    return phrases


def extract_lyric_anchors(lyrics_json_path: str) -> List[dict]:
    """
    Extract lyric anchors from a lyrics JSON file.
    
    Parses the JSON output from detect-lyrics and extracts phrase-ending
    words with their end timestamps. Uses punctuation-first detection with
    gap-based fallback.
    
    Args:
        lyrics_json_path: Path to JSON file from detect-lyrics
        
    Returns:
        List of anchor dicts, each with 'word' and 'time_end_sec' keys
        
    Raises:
        FileNotFoundError: If lyrics file doesn't exist
        ValueError: If JSON structure is invalid
    """
    path = Path(lyrics_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Lyrics file not found: {lyrics_json_path}")
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in lyrics file: {e}") from e
    
    words = data.get("words", [])
    if not words:
        logger.warning("No words found in lyrics file")
        return []
    
    logger.info(f"Parsing {len(words)} words from lyrics file")
    
    # Primary method: Detect phrases by punctuation
    punctuation_phrases = detect_phrases_by_punctuation(words)
    logger.info(f"Punctuation-based detection: {len(punctuation_phrases)} phrases")
    
    # Fallback method: Detect phrases by gaps (for songs without punctuation)
    gap_phrases = detect_phrases_from_words(words, gap_threshold=0.5)
    logger.info(f"Gap-based detection (0.5s threshold): {len(gap_phrases)} phrases")
    
    # Use punctuation-based if it found more phrases, otherwise use gap-based
    # Punctuation is more reliable, so prefer it even if it finds fewer phrases
    if len(punctuation_phrases) >= len(gap_phrases) or len(punctuation_phrases) > 1:
        final_phrases = punctuation_phrases
        detection_method = "punctuation"
    else:
        final_phrases = gap_phrases
        detection_method = "gap-based"
    
    logger.info(f"Using {detection_method} detection: {len(final_phrases)} phrases")
    
    # Extract anchors from phrases
    # For each phrase, find the last content word (non-stopword)
    anchors: List[dict] = []
    for i, phrase in enumerate(final_phrases):
        if not phrase:
            continue
            
        last_word = find_last_content_word(phrase)
        if last_word:
            word_text = last_word.get("word", "").strip().rstrip(".,!?;:")
            end_time = last_word.get("end", 0.0)
            
            # Also check if there are multiple content words - prefer the last one
            # This handles cases where punctuation appears mid-phrase
            content_words = [w for w in phrase if not is_stopword(w.get("word", "").strip())]
            if len(content_words) > 1:
                # Use the last content word, not necessarily the punctuation-marked one
                last_content = content_words[-1]
                word_text = last_content.get("word", "").strip().rstrip(".,!?;:")
                end_time = last_content.get("end", 0.0)
            
            anchors.append({
                "word": word_text,
                "time_end_sec": float(end_time),
            })
            logger.debug(f"Phrase {i+1} ({len(phrase)} words): '{word_text}' at {end_time:.2f}s")
    
    logger.info(f"Extracted {len(anchors)} lyric anchors from {len(final_phrases)} phrases")
    return anchors


def map_anchors_to_seconds(
    anchors: List[dict],
    duration_seconds: int,
) -> Dict[int, str]:
    """
    Map lyric anchors to one-second clip indices.
    
    For each anchor, determines which second (clip index) it belongs to
    based on its end time. If multiple anchors land in the same second,
    keeps the last one chronologically.
    
    Args:
        anchors: List of anchor dicts with 'word' and 'time_end_sec'
        duration_seconds: Total duration of video in seconds
        
    Returns:
        Dict mapping second index -> word text
    """
    mapping: Dict[int, str] = {}
    time_tracking: Dict[int, float] = {}  # Track times for each second
    
    logger.debug(f"Mapping {len(anchors)} anchors to {duration_seconds} seconds")
    
    for anchor in anchors:
        time_end = anchor.get("time_end_sec", 0.0)
        word = anchor.get("word", "")
        
        # Map to second index (round down)
        second_index = int(time_end)
        
        # Clamp to valid range
        if 0 <= second_index < duration_seconds:
            # If multiple anchors in same second, keep the latest one
            if second_index not in mapping or time_end > time_tracking.get(second_index, 0.0):
                if second_index in mapping:
                    logger.debug(f"Replacing anchor at second {second_index}: '{mapping[second_index]}' ({time_tracking[second_index]:.2f}s) -> '{word}' ({time_end:.2f}s)")
                mapping[second_index] = word
                time_tracking[second_index] = time_end
                logger.debug(f"Mapped '{word}' at {time_end:.2f}s -> second {second_index}")
        else:
            logger.debug(f"Anchor '{word}' at {time_end:.2f}s is outside valid range [0, {duration_seconds}), skipping")
    
    logger.info(f"Mapped {len(mapping)} lyric anchors to seconds (out of {len(anchors)} total anchors)")
    if mapping:
        logger.debug(f"Mapping details: {dict(sorted(mapping.items()))}")
    return mapping


def build_karaoke_mapping(lyrics_json_path: str, duration_seconds: int) -> Dict[int, str]:
    """
    Build a per-second karaoke mapping from lyrics JSON.
    
    For each integer second s, collects all words whose [start, end) interval
    intersects [s, s+1), sorts them by start time, and joins them into a string.
    
    Args:
        lyrics_json_path: Path to JSON file from detect-lyrics
        duration_seconds: Total duration of video in seconds
        
    Returns:
        Dict mapping second index -> text line (uppercase words joined by spaces)
        Empty dict for seconds with no words
        
    Raises:
        FileNotFoundError: If lyrics file doesn't exist
        ValueError: If JSON structure is invalid
    """
    path = Path(lyrics_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Lyrics file not found: {lyrics_json_path}")
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in lyrics file: {e}") from e
    
    words = data.get("words", [])
    if not words:
        logger.warning("No words found in lyrics file")
        return {}
    
    logger.info(f"Building karaoke mapping from {len(words)} words for {duration_seconds} seconds")
    
    mapping: Dict[int, str] = {}
    
    # For each integer second s in [0, duration_seconds)
    for s in range(duration_seconds):
        # Collect words whose [start, end) intersects [s, s+1)
        # A word intersects if: start < s+1 AND end > s
        words_in_second = []
        for word_data in words:
            start = word_data.get("start", 0.0)
            end = word_data.get("end", 0.0)
            
            # Check if word interval [start, end) intersects [s, s+1)
            if start < s + 1 and end > s:
                word_text = word_data.get("word", "").strip()
                if word_text:
                    words_in_second.append((start, word_text))
        
        # Sort words by start time to maintain chronological order
        words_in_second.sort(key=lambda x: x[0])
        
        # Join words into uppercase string
        if words_in_second:
            text_line = " ".join(word_text.upper() for _, word_text in words_in_second)
            mapping[s] = text_line
            logger.debug(f"Second {s}: '{text_line}' ({len(words_in_second)} words)")
    
    logger.info(f"Built karaoke mapping: {len(mapping)} seconds have lyrics out of {duration_seconds} total")
    if mapping:
        sample_seconds = sorted(mapping.keys())[:5]
        logger.debug(f"Sample mappings: {[(s, mapping[s][:30] + '...' if len(mapping[s]) > 30 else mapping[s]) for s in sample_seconds]}")
    
    return mapping

