from dataclasses import dataclass
from typing import List, Tuple, Set
import json
import subprocess

import librosa
import numpy as np
from pathlib import Path
from tqdm import tqdm

import argparse
import os
import random
from moviepy import VideoFileClip, AudioFileClip, ColorClip, CompositeVideoClip  # type: ignore
from moviepy import vfx  # type: ignore


@dataclass
class BpmSegment:
    """
    A region of the mix that has roughly constant BPM.

    start  segment start time in seconds
    end    segment end time in seconds
    bpm    estimated BPM in that region
    """
    start: float
    end: float
    bpm: float


def analyze_bpm_segments(
    audio_path: str,
    sr: int | None = None,
    window_seconds: float = 8.0,
    hop_seconds: float = 4.0,
    min_bpm: float = 60.0,
    max_bpm: float = 180.0,
    change_threshold: float = 2.5,
) -> List[BpmSegment]:
    """
    Analyze the whole mix once and detect regions where the BPM is roughly constant.
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
        return [BpmSegment(start=0.0, end=total_duration, bpm=120.0)]

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
    Expand a list of BpmSegment objects into a per second BPM timeline.
    """
    if not segments:
        return [120.0] * duration_seconds

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


# ----------------------------
# Rendering pipeline (visuals)
# ----------------------------

def _subclip(clip: VideoFileClip, start: float, end: float) -> VideoFileClip:
    if hasattr(clip, "subclip"):
        return clip.subclip(start, end)  # type: ignore[attr-defined]
    return clip.subclipped(start, end)  # type: ignore[attr-defined]


def _set_duration(clip: VideoFileClip, duration: float) -> VideoFileClip:
    if hasattr(clip, "set_duration"):
        return clip.set_duration(duration)  # type: ignore[attr-defined]
    return clip.with_duration(duration)  # type: ignore[attr-defined]


def _set_audio(clip: VideoFileClip, audio: AudioFileClip) -> VideoFileClip:
    if hasattr(clip, "set_audio"):
        return clip.set_audio(audio)  # type: ignore[attr-defined]
    return clip.with_audio(audio)  # type: ignore[attr-defined]


def _speedx(clip: VideoFileClip, factor: float) -> VideoFileClip:
    if hasattr(clip, "fx"):
        return clip.fx(vfx.speedx, factor=factor)  # type: ignore[attr-defined]
    if hasattr(clip, "with_speed_scaled"):
        return clip.with_speed_scaled(factor=factor)  # type: ignore[attr-defined]
    if hasattr(clip, "with_speed"):
        return clip.with_speed(factor=factor)  # type: ignore[attr-defined]
    return clip


def _resize_letterbox(clip: VideoFileClip, target_resolution: Tuple[int, int]) -> VideoFileClip:
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
    bg = ColorClip(size=(target_w, target_h), color=(0, 0, 0)).with_duration(getattr(resized, "duration", 1.0))  # type: ignore[attr-defined]
    if hasattr(resized, "set_position"):
        fg = resized.set_position(("center", "center"))  # type: ignore[attr-defined]
    else:
        fg = resized.with_position(("center", "center"))  # type: ignore[attr-defined]
    return CompositeVideoClip([bg, fg])


def load_blacklist(blacklist_path: Path) -> Set[str]:
    """Load blacklisted video filenames."""
    if blacklist_path.exists():
        try:
            with open(blacklist_path, 'r') as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_blacklist(blacklist_path: Path, blacklist: Set[str]) -> None:
    """Save blacklisted video filenames."""
    try:
        with open(blacklist_path, 'w') as f:
            json.dump(list(blacklist), f, indent=2)
    except Exception as e:
        print(f"[warn] Failed to save blacklist: {e}", flush=True)


def load_checkpoint(checkpoint_dir: Path) -> Tuple[int, List[Path], Set[str]]:
    """
    Load checkpoint: returns (last_completed_sec, list of saved clip file paths, blacklist).

    Returns file paths as Path objects to avoid loading many clips into memory.
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
        print(f"[warn] Failed to load checkpoint: {e}, starting fresh", flush=True)
        return 0, [], load_blacklist(blacklist_file)


def save_checkpoint(checkpoint_dir: Path, last_completed_sec: int, saved_clips: List[Path], blacklist: Set[str]) -> None:
    """Save checkpoint progress. saved_clips should be a list of Path objects."""
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
        print(f"[warn] Failed to save checkpoint: {e}", flush=True)


def build_visual_track(
    video_folder: str,
    bpm_values: List[float],
    duration_seconds: int,
    target_resolution: Tuple[int, int],
    base_bpm: float,
    speed_min: float = 0.5,
    speed_max: float = 2.0,
    checkpoint_dir: Path | None = None,
) -> List[Path]:
    """
    Build visual track by generating 1 second clips and writing them to disk.

    Simple version:
      For each second, pick a random video file,
      cut a random window,
      retime with BPM factor,
      resize,
      and export a 1 second clip.

    Returns a list of paths to the generated clips in order.
    """
    folder = Path(video_folder)
    if not folder.exists():
        raise FileNotFoundError(f"Video folder not found: {video_folder}")

    # Load blacklist and checkpoint
    if checkpoint_dir is None:
        checkpoint_dir = Path("checkpoints")
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
        print(f"[resume] Resuming from second {start_sec}, {len(saved_clip_paths)} clips already saved", flush=True)

    clip_paths: List[Path] = saved_clip_paths.copy()
    skipped_count = 0
    checkpoint_interval = 50  # Save checkpoint every 50 seconds

    for sec in tqdm(
        range(start_sec, duration_seconds),
        desc="Assembling 1s clips",
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
                    print(f"[blacklist] Adding {video_path.name} to blacklist (error: {type(e).__name__})", flush=True)
                    blacklist.add(video_path.name)
                    save_blacklist(checkpoint_dir / "blacklist.json", blacklist)
                video_path = None
                if attempt == max_tries - 1:
                    print(f"[warn] Failed to load video after {max_tries} tries at clip {sec}, using fallback", flush=True)
                    skipped_count += 1

        # Process the clip with error handling
        sub = None
        sped = None
        boxed = None
        one_sec = None
        try:
            if video_clip is None:
                # Create a black frame as fallback
                one_sec = ColorClip(size=target_resolution, color=(0, 0, 0)).with_duration(1.0)
            else:
                base_window = 1.2
                max_start = max(0.0, (video_clip.duration or 0.0) - base_window)
                start_t = random.uniform(0.0, max_start) if max_start > 0 else 0.0
                sub = _subclip(video_clip, start_t, min(start_t + base_window, video_clip.duration))
                sped = _speedx(sub, factor=speed)
                boxed = _resize_letterbox(sped, target_resolution)
                one_sec = _set_duration(boxed, 1.0)

            checkpoint_clip_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                one_sec.write_videofile(
                    str(checkpoint_clip_path),
                    codec="libx264",
                    audio=False,
                    fps=30,
                    preset="ultrafast",
                )
            except TypeError:
                one_sec.write_videofile(
                    str(checkpoint_clip_path),
                    codec="libx264",
                    audio=False,
                    fps=30,
                )

            one_sec.close()
            one_sec = None

            clip_paths.append(checkpoint_clip_path)

        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"[warn] Error processing {video_path.name if video_path else 'fallback'} at clip {sec}: {type(e).__name__}: {error_msg}", flush=True)
            if sec < 5:
                traceback.print_exc()
            skipped_count += 1
            # Fallback black frame
            try:
                fallback = ColorClip(size=target_resolution, color=(0, 0, 0)).with_duration(1.0)
                fallback.write_videofile(
                    str(checkpoint_clip_path),
                    codec="libx264",
                    audio=False,
                    fps=30,
                    preset="ultrafast",
                )
                fallback.close()
                clip_paths.append(checkpoint_clip_path)
            except Exception as fallback_err:
                print(f"[error] Failed to create fallback clip: {fallback_err}", flush=True)
                clip_paths.append(checkpoint_clip_path)
        finally:
            for clip_to_close in [one_sec, boxed, sped, sub, video_clip]:
                if clip_to_close is not None:
                    try:
                        clip_to_close.close()
                    except Exception:
                        pass

        # Save checkpoint periodically
        if (sec + 1) % checkpoint_interval == 0 or sec == duration_seconds - 1:
            save_checkpoint(checkpoint_dir, sec + 1, clip_paths, blacklist)
            print(f"[checkpoint] Saved progress at second {sec + 1}/{duration_seconds}", flush=True)

    if skipped_count > 0:
        print(f"[info] Skipped {skipped_count} problematic clips (used black frames)", flush=True)

    print(f"[info] Final blacklist: {len(blacklist)} files", flush=True)
    print(f"[info] Generated {len(clip_paths)} clip files", flush=True)

    return clip_paths


def analyze_bpm_per_second(audio_path: str, duration_seconds: int) -> List[float]:
    print("[bpm] analyze_bpm_segments()", flush=True)
    segments = analyze_bpm_segments(audio_path)
    print(f"[bpm] segments: {len(segments)}", flush=True)
    return bpm_timeline_from_segments(segments, duration_seconds)


def analyze_global_bpm(audio_path: str, duration_seconds: int) -> float:
    segments = analyze_bpm_segments(audio_path)
    if not segments:
        return 120.0
    bpms = []
    weights = []
    for s in segments:
        bpms.append(s.bpm)
        weights.append(max(0.1, s.end - s.start))
    w = np.array(weights) / np.sum(weights)
    return float(bpms[int(np.argmax(w))])


def render_video(
    audio_path: str,
    video_folder: str,
    duration_seconds: int,
    output_path: str,
    resolution: Tuple[int, int] = (1080, 1920),
    seed: int | None = None,
) -> None:
    """
    Render video with memory efficient design.

    Uses ffmpeg for concatenation to avoid loading many clips into memory.
    Only loads the final concatenated video once for audio attachment.
    """
    print("[render] start", flush=True)
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)
    print("[render] analyze BPM per-second...", flush=True)
    bpm_values = analyze_bpm_per_second(audio_path, duration_seconds)
    print("[render] base BPM...", flush=True)
    base_bpm = analyze_global_bpm(audio_path, duration_seconds)
    print("[render] build visuals...", flush=True)
    checkpoint_dir = Path(output_path).parent / "checkpoints" / Path(output_path).stem
    clip_paths = build_visual_track(
        video_folder=video_folder,
        bpm_values=bpm_values,
        duration_seconds=duration_seconds,
        target_resolution=resolution,
        base_bpm=base_bpm,
        checkpoint_dir=checkpoint_dir,
    )

    if len(clip_paths) != duration_seconds:
        raise ValueError(f"Expected {duration_seconds} clips, got {len(clip_paths)}")

    print("[render] concatenating clips with ffmpeg...", flush=True)
    visuals_raw_path = checkpoint_dir / "visuals_raw.mp4"
    concat_list_path = checkpoint_dir / "concat_list.txt"

    with open(concat_list_path, 'w') as f:
        for clip_path in clip_paths:
            abs_path = clip_path.resolve()
            f.write(f"file '{abs_path}'\n")

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list_path),
                "-c", "copy",
                str(visuals_raw_path),
                "-y",
            ],
            check=True,
            capture_output=True,
        )
        print(f"[render] ffmpeg concat completed: {visuals_raw_path}", flush=True)
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else "Unknown error"
        raise RuntimeError(f"ffmpeg concat failed: {error_msg}") from e
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Please install ffmpeg to use this script.")

    print("[render] load/trim audio...", flush=True)
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    audio = _subclip(AudioFileClip(audio_path), 0, duration_seconds)

    print("[render] attaching audio and writing final output...", flush=True)
    visual = VideoFileClip(str(visuals_raw_path), audio=False)

    final = _set_duration(_set_audio(visual, audio), duration_seconds)
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=30,
        threads=os.cpu_count() or 4,
        preset="medium",
    )

    visual.close()
    audio.close()
    final.close()

    print("[render] done", flush=True)
    print(f"[render] Final output: {output_path}", flush=True)
    print(f"[render] Checkpoint directory: {checkpoint_dir} (can be deleted after verification)", flush=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BPM-driven MP4 visualizer (1s segments)")
    p.add_argument("--audio", required=True)
    p.add_argument("--gif-folder", required=True, help="Folder containing MP4 video files (legacy arg name)")
    p.add_argument("--duration-seconds", type=int, default=60)
    p.add_argument("--output", default="output.mp4")
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument("--seed", type=int, default=None)
    return p.parse_args()


if __name__ == "__main__":
    import traceback
    try:
        args = parse_args()
        print("[main] args parsed", flush=True)
        render_video(
            audio_path=args.audio,
            video_folder=args.gif_folder,
            duration_seconds=args.duration_seconds,
            output_path=args.output,
            resolution=(args.width, args.height),
            seed=args.seed,
        )
        print("[main] completed OK", flush=True)
    except Exception as e:
        print("[main] ERROR:", repr(e), flush=True)
        traceback.print_exc()
        raise
