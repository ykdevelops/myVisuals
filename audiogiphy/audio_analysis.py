"""
Audio BPM Analysis Module.

This module handles analyzing audio files to detect BPM (beats per minute)
over time, creating a timeline that drives video clip speed synchronization.
"""

from dataclasses import dataclass
from typing import List
import logging

import librosa
import numpy as np
from pathlib import Path
from tqdm import tqdm

from audiogiphy.config import BPM_WINDOW_SECONDS, BPM_HOP_SECONDS, DEFAULT_BPM_FALLBACK

__all__ = [
    "BpmSegment",
    "analyze_bpm_segments",
    "bpm_timeline_from_segments",
    "analyze_bpm_per_second",
    "analyze_global_bpm",
]

logger = logging.getLogger("audiogiphy.audio_analysis")


@dataclass
class BpmSegment:
    """
    A region of the audio track that has roughly constant BPM.
    
    Attributes:
        start: Segment start time in seconds
        end: Segment end time in seconds
        bpm: Estimated BPM in that region
    """
    start: float
    end: float
    bpm: float


def analyze_bpm_segments(
    audio_path: str,
    sr: int | None = None,
    window_seconds: float = BPM_WINDOW_SECONDS,
    hop_seconds: float = BPM_HOP_SECONDS,
    min_bpm: float = 60.0,
    max_bpm: float = 180.0,
    change_threshold: float = 2.5,
) -> List[BpmSegment]:
    """
    Analyze the audio file to detect regions where the BPM is roughly constant.
    
    This function slides a window over the audio track and estimates BPM for each
    window using librosa's tempo detection. It then groups consecutive windows
    with similar BPM into segments.
    
    Args:
        audio_path: Path to the audio file
        sr: Sample rate (None to use file's native rate)
        window_seconds: Length of analysis window in seconds
        hop_seconds: Step size between windows in seconds
        min_bpm: Minimum valid BPM value
        max_bpm: Maximum valid BPM value
        change_threshold: BPM change threshold to start a new segment
        
    Returns:
        List of BpmSegment objects representing regions of constant BPM
        
    Raises:
        FileNotFoundError: If audio file doesn't exist
        ValueError: If audio has zero duration or invalid parameters
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    # Load the whole mix once
    y, sr_loaded = librosa.load(str(path), sr=sr, mono=True)
    sr = sr_loaded
    total_duration = len(y) / sr

    if total_duration <= 0:
        raise ValueError("Audio has zero duration")

    hop_length = max(256, int(sr * 0.01))

    window_bpm: List[float] = []
    window_starts: List[float] = []

    if hop_seconds <= 0:
        raise ValueError("hop_seconds must be > 0")
    n_steps = int(np.ceil(total_duration / hop_seconds))
    
    for i in tqdm(range(n_steps), desc="BPM windows", ncols=80):
        start_sec = i * float(hop_seconds)
        end_sec = min(start_sec + float(window_seconds), float(total_duration))
        if end_sec - start_sec < 0.5:
            break  # too short to analyze

        start_idx = int(start_sec * sr)
        end_idx = int(end_sec * sr)
        y_win = y[start_idx:end_idx]

        # Energy check
        if y_win.size == 0:
            bpm = float("nan")
        else:
            rms = float(np.sqrt(np.mean(y_win ** 2))) if y_win.size else 0.0
            if rms < 1e-4:
                bpm = float("nan")
            else:
                onset_env = librosa.onset.onset_strength(
                    y=y_win,
                    sr=sr,
                    hop_length=hop_length,
                )
                if onset_env.size < 4 or float(np.sum(onset_env)) < 1e-3:
                    bpm = float("nan")
                else:
                    tempo = librosa.beat.tempo(
                        onset_envelope=onset_env,
                        sr=sr,
                        hop_length=hop_length,
                        aggregate=np.median,
                    )
                    bpm_val = float(tempo[0]) if tempo.size else float("nan")
                    if np.isfinite(bpm_val):
                        bpm = float(np.clip(bpm_val, min_bpm, max_bpm))
                    else:
                        bpm = float("nan")

        window_starts.append(start_sec)
        window_bpm.append(bpm)

    # Fill NaNs by forward and backward fill
    for i in range(1, len(window_bpm)):
        if not np.isfinite(window_bpm[i]) and np.isfinite(window_bpm[i - 1]):
            window_bpm[i] = window_bpm[i - 1]
    for i in range(len(window_bpm) - 2, -1, -1):
        if not np.isfinite(window_bpm[i]) and np.isfinite(window_bpm[i + 1]):
            window_bpm[i] = window_bpm[i + 1]

    # If still all NaN, give up with a default
    finite_bpms = [b for b in window_bpm if np.isfinite(b)]
    if not finite_bpms:
        return [BpmSegment(start=0.0, end=total_duration, bpm=DEFAULT_BPM_FALLBACK)]

    # Replace remaining NaNs with global median
    global_bpm = float(np.median(finite_bpms))
    window_bpm = [float(global_bpm) if not np.isfinite(b) else float(b) for b in window_bpm]

    # Build segments by grouping windows that have similar BPM
    segments: List[BpmSegment] = []
    current_start = window_starts[0]
    current_bpm = window_bpm[0]

    for i in range(1, len(window_bpm)):
        this_start = window_starts[i]
        this_bpm = window_bpm[i]
        if abs(this_bpm - current_bpm) > change_threshold:
            segments.append(BpmSegment(start=current_start, end=this_start, bpm=current_bpm))
            current_start = this_start
            current_bpm = this_bpm

    # Close final segment at end of track
    segments.append(BpmSegment(start=current_start, end=total_duration, bpm=current_bpm))

    return segments


def bpm_timeline_from_segments(
    segments: List[BpmSegment],
    duration_seconds: int,
) -> List[float]:
    """
    Expand a list of BpmSegment objects into a per-second BPM timeline.
    
    For each second from 0 to duration_seconds-1, this function finds which
    segment covers that time and returns its BPM value. This creates a simple
    array where index i contains the BPM for second i.
    
    Args:
        segments: List of BpmSegment objects from analyze_bpm_segments
        duration_seconds: Total duration of the timeline in seconds
        
    Returns:
        List of BPM values, one per second, indexed by second number
    """
    if not segments:
        return [DEFAULT_BPM_FALLBACK] * duration_seconds

    bpm_values: List[float] = []
    for t in range(duration_seconds):
        time = float(t)
        bpm_for_t = segments[-1].bpm  # default to last
        for seg in segments:
            if seg.start <= time < seg.end:
                bpm_for_t = seg.bpm
                break
        bpm_values.append(float(bpm_for_t))
    return bpm_values


def analyze_bpm_per_second(audio_path: str, duration_seconds: int) -> List[float]:
    """
    Analyze audio and return a per-second BPM timeline.
    
    This is a convenience function that combines analyze_bpm_segments and
    bpm_timeline_from_segments to produce a simple per-second BPM array.
    
    Args:
        audio_path: Path to the audio file
        duration_seconds: Duration of the output video in seconds
        
    Returns:
        List of BPM values, one per second
        
    Usage:
        Used in the render pipeline to get BPM values for each second
        of video, which drives the speed adjustment of visual clips.
    """
    logger.info("Analyzing BPM segments")
    segments = analyze_bpm_segments(audio_path)
    logger.info(f"Found {len(segments)} BPM segments")
    return bpm_timeline_from_segments(segments, duration_seconds)


def analyze_global_bpm(audio_path: str, duration_seconds: int) -> float:
    """
    Analyze audio and return a single global BPM value.
    
    This computes a weighted median BPM across all segments, giving more
    weight to longer segments. This is used as the "base BPM" for speed
    calculations - clips are sped up or slowed down relative to this base.
    
    Args:
        audio_path: Path to the audio file
        duration_seconds: Duration (used for consistency, not directly in calculation)
        
    Returns:
        Single float representing the global/base BPM
        
    Usage:
        Used in the render pipeline as the reference BPM. Local BPM values
        are divided by this base to determine speed multipliers for clips.
    """
    segments = analyze_bpm_segments(audio_path)
    if not segments:
        return DEFAULT_BPM_FALLBACK
    
    # Weighted median by segment length
    bpms = []
    weights = []
    for s in segments:
        bpms.append(s.bpm)
        weights.append(max(0.1, s.end - s.start))
    w = np.array(weights) / np.sum(weights)
    # Approximate weighted median by picking BPM of max weight
    return float(bpms[int(np.argmax(w))])

