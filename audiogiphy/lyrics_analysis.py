"""
Lyrics Analysis Module.

This module handles speech-to-text transcription of audio files using Whisper,
providing word-level timestamps for lyric detection and synchronization.
"""

from dataclasses import dataclass
from typing import List, Optional
import logging
from pathlib import Path

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    whisper = None

from audiogiphy.config import (
    WHISPER_MODEL_SIZE,
    WHISPER_DEFAULT_LANGUAGE,
    WHISPER_TEMPERATURE,
    WHISPER_COMPRESSION_RATIO_THRESHOLD,
    WHISPER_LOGPROB_THRESHOLD,
    WHISPER_NO_SPEECH_THRESHOLD,
)

__all__ = [
    "LyricWord",
    "LyricsResult",
    "detect_lyrics",
]

logger = logging.getLogger("audiogiphy.lyrics_analysis")


@dataclass
class LyricWord:
    """
    A single word with timing information.
    
    Attributes:
        word: The word text
        start: Start time in seconds
        end: End time in seconds
    """
    word: str
    start: float
    end: float


@dataclass
class LyricsResult:
    """
    Complete lyrics analysis result.
    
    Attributes:
        transcript: Full transcript as a single string
        words: List of words with timestamps
        language: Detected language code (e.g., 'en')
        duration: Audio duration in seconds
    """
    transcript: str
    words: List[LyricWord]
    language: str
    duration: float


def detect_lyrics(
    audio_path: str,
    language: Optional[str] = None,
    model_size: Optional[str] = None,
    initial_prompt: Optional[str] = None,
) -> LyricsResult:
    """
    Detect lyrics from an audio file using Whisper speech-to-text.
    
    This function transcribes the audio and provides word-level timestamps
    for synchronization with visuals.
    
    Args:
        audio_path: Path to input audio file
        language: Language code (e.g., 'en', 'es', 'fr'). None for auto-detect
        model_size: Whisper model size ('tiny', 'base', 'small', 'medium', 'large')
                    None to use default from config
        initial_prompt: Optional prompt to guide transcription (e.g., song title, artist)
        
    Returns:
        LyricsResult containing transcript, word timestamps, language, and duration
        
    Raises:
        FileNotFoundError: If audio file doesn't exist
        RuntimeError: If Whisper is not installed or transcription fails
        ValueError: If model_size is invalid
    """
    if not WHISPER_AVAILABLE:
        raise RuntimeError(
            "Whisper is not installed. Please install it with: pip install openai-whisper"
        )
    
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    if model_size is None:
        model_size = WHISPER_MODEL_SIZE
    
    valid_models = ["tiny", "base", "small", "medium", "large"]
    if model_size not in valid_models:
        raise ValueError(f"Invalid model_size: {model_size}. Must be one of {valid_models}")
    
    if language is None:
        language = WHISPER_DEFAULT_LANGUAGE
    
    logger.info(f"Loading Whisper model: {model_size}")
    try:
        model = whisper.load_model(model_size)
    except Exception as e:
        raise RuntimeError(f"Failed to load Whisper model: {e}") from e
    
    logger.info(f"Transcribing audio: {audio_path}")
    logger.info(f"Language: {language if language != 'auto' else 'auto-detect'}")
    if initial_prompt:
        logger.info(f"Initial prompt: {initial_prompt}")
    
    # Build transcription options optimized for music
    transcribe_options = {
        "word_timestamps": True,
        "verbose": False,
        "temperature": WHISPER_TEMPERATURE,
        "compression_ratio_threshold": WHISPER_COMPRESSION_RATIO_THRESHOLD,
        "logprob_threshold": WHISPER_LOGPROB_THRESHOLD,
        "no_speech_threshold": WHISPER_NO_SPEECH_THRESHOLD,
    }
    
    # Add language if specified
    if language != "auto":
        transcribe_options["language"] = language
    
    # Add initial prompt if provided (helps with context)
    if initial_prompt:
        transcribe_options["initial_prompt"] = initial_prompt
    
    try:
        # Transcribe with word-level timestamps and optimized parameters
        result = model.transcribe(str(path), **transcribe_options)
    except Exception as e:
        raise RuntimeError(f"Whisper transcription failed: {e}") from e
    
    # Extract full transcript
    transcript = result["text"].strip()
    
    # Extract word-level timestamps
    words: List[LyricWord] = []
    segments = result.get("segments", [])
    
    for segment in segments:
        segment_words = segment.get("words", [])
        for word_data in segment_words:
            word_text = word_data.get("word", "").strip()
            start_time = word_data.get("start", 0.0)
            end_time = word_data.get("end", start_time)
            
            # Skip empty words
            if not word_text:
                continue
            
            words.append(LyricWord(
                word=word_text,
                start=float(start_time),
                end=float(end_time),
            ))
    
    # Get detected language
    detected_language = result.get("language", language)
    
    # Calculate duration from segments
    duration = 0.0
    if segments:
        last_segment = segments[-1]
        duration = float(last_segment.get("end", 0.0))
    
    logger.info(f"Transcription complete: {len(words)} words detected")
    logger.info(f"Detected language: {detected_language}")
    
    return LyricsResult(
        transcript=transcript,
        words=words,
        language=detected_language,
        duration=duration,
    )

