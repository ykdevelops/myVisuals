"""
Command-Line Interface for AudioGiphy.

Provides a simple CLI for rendering BPM-synced videos from audio tracks
and detecting lyrics from audio files.
"""

import argparse
import sys
import logging
import subprocess
import json
from pathlib import Path

from audiogiphy.render_pipeline import render_video
from audiogiphy.config import DEFAULT_RESOLUTION

__all__ = ["main"]

# Configure logging with simple tags
class ModuleFormatter(logging.Formatter):
    """Custom formatter that extracts module name from logger name."""
    def format(self, record):
        # Extract module name from logger name (e.g., "audiogiphy.audio_analysis" -> "audio")
        logger_name = record.name
        # Special handling for ffmpeg logger
        if logger_name == 'ffmpeg':
            record.name = 'ffmpeg'
        elif logger_name.startswith('audiogiphy.'):
            module = logger_name.split('.')[-1]
            # Map module names to simple tags
            tag_map = {
                'audio_analysis': 'audio',
                'visual_builder': 'visual',
                'render_pipeline': 'render',
                'giphy_placeholder': 'giphy',
                'cli': 'cli',
                'lyrics_analysis': 'lyrics',
            }
            record.name = tag_map.get(module, module)
        return super().format(record)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ModuleFormatter("[%(name)s] %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[handler])

logger = logging.getLogger("audiogiphy.cli")


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.
    
    Returns:
        Namespace object with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="AudioGiphy - BPM-driven video visualizer and lyric detector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    subparsers.required = True
    
    # Render subcommand
    render_parser = subparsers.add_parser(
        "render",
        help="Render a BPM-synced video from audio and video clips",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Render a 60-second video
  python -m audiogiphy.cli render \\
    --audio mixes/test_mix.mp3 \\
    --gif-folder bank \\
    --duration-seconds 60 \\
    --output renders/test_output.mp4

  # Render with custom resolution and seed
  python -m audiogiphy.cli render \\
    --audio mixes/test_mix.mp3 \\
    --gif-folder bank \\
    --duration-seconds 120 \\
    --output renders/output.mp4 \\
    --width 720 \\
    --height 1280 \\
    --seed 42
        """
    )
    
    render_parser.add_argument(
        "--audio",
        required=True,
        help="Path to input audio file (WAV, MP3, etc.)"
    )
    render_parser.add_argument(
        "--gif-folder",
        required=True,
        help="Path to folder containing MP4 video files (legacy arg name, accepts MP4s)"
    )
    render_parser.add_argument(
        "--duration-seconds",
        type=int,
        default=60,
        help="Duration of output video in seconds (default: 60)"
    )
    render_parser.add_argument(
        "--output",
        default="output.mp4",
        help="Path for output video file (default: output.mp4)"
    )
    render_parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_RESOLUTION[0],
        help=f"Video width in pixels (default: {DEFAULT_RESOLUTION[0]})"
    )
    render_parser.add_argument(
        "--height",
        type=int,
        default=DEFAULT_RESOLUTION[1],
        help=f"Video height in pixels (default: {DEFAULT_RESOLUTION[1]})"
    )
    render_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible results (optional)"
    )
    render_parser.add_argument(
        "--lyrics-json",
        type=str,
        default=None,
        help="Path to lyrics JSON file from detect-lyrics. If provided, overlays phrase-ending words on video."
    )
    render_parser.add_argument(
        "--karaoke-mode",
        action="store_true",
        help="Display all words per second (karaoke mode). Requires --lyrics-json."
    )
    render_parser.add_argument(
        "--lyrics-giphy-plan",
        type=str,
        default=None,
        help="Path to LLM JSON with segments and gif_query. Enables GIPHY overlay planning."
    )
    
    # Detect lyrics subcommand
    lyrics_parser = subparsers.add_parser(
        "detect-lyrics",
        help="Detect lyrics from an audio file using speech-to-text",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Detect lyrics and print to terminal
  python -m audiogiphy.cli detect-lyrics --audio song.wav

  # Detect lyrics and save to JSON file
  python -m audiogiphy.cli detect-lyrics \\
    --audio song.wav \\
    --lyrics-output lyrics.json

  # Detect lyrics with custom language and model
  python -m audiogiphy.cli detect-lyrics \\
    --audio song.wav \\
    --language es \\
    --model-size small
        """
    )
    
    lyrics_parser.add_argument(
        "--audio",
        required=True,
        help="Path to input audio file (WAV, MP3, etc.)"
    )
    lyrics_parser.add_argument(
        "--lyrics-output",
        type=str,
        default=None,
        help="Path to output file (JSON or .txt). If not provided, prints to terminal only"
    )
    lyrics_parser.add_argument(
        "--language",
        type=str,
        default=None,
        help="Language code (e.g., 'en', 'es', 'fr'). Default: auto-detect"
    )
    lyrics_parser.add_argument(
        "--model-size",
        type=str,
        choices=["tiny", "base", "small", "medium", "large"],
        default=None,
        help="Whisper model size (default: from config)"
    )
    lyrics_parser.add_argument(
        "--initial-prompt",
        type=str,
        default=None,
        help="Optional prompt to guide transcription (e.g., 'Glamorous by Fergie feat Ludacris')"
    )
    
    return parser.parse_args()


def check_ffmpeg() -> None:
    """Check if ffmpeg is installed and available."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError(
            "ffmpeg is not installed or not found in PATH. "
            "Please install ffmpeg to use AudioGiphy.\n"
            "Installation: https://ffmpeg.org/download.html"
        )


def validate_paths(audio_path: str, video_folder: str = None) -> None:
    """Validate that required paths exist."""
    audio_file = Path(audio_path)
    if not audio_file.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    if video_folder is not None:
        video_dir = Path(video_folder)
        if not video_dir.exists():
            raise FileNotFoundError(f"Video folder not found: {video_folder}")
        
        if not video_dir.is_dir():
            raise ValueError(f"Video folder path is not a directory: {video_folder}")
        
        # Check for MP4 files
        mp4_files = list(video_dir.glob("*.mp4"))
        if not mp4_files:
            raise ValueError(f"No MP4 files found in video folder: {video_folder}")


def format_lyrics_output(result, output_path: str = None) -> None:
    """
    Format and output lyrics detection results.
    
    Args:
        result: LyricsResult object
        output_path: Optional path to write output file (JSON or .txt)
    """
    # Print header
    print("\n" + "=" * 70)
    print("LYRICS DETECTION RESULTS")
    print("=" * 70)
    print(f"Audio duration: {result.duration:.2f} seconds")
    print(f"Detected language: {result.language}")
    print(f"Total words: {len(result.words)}")
    print("=" * 70)
    
    # Print full transcript
    print("\nFULL TRANSCRIPT:")
    print("-" * 70)
    print(result.transcript)
    print("-" * 70)
    
    # Print word-level timestamps
    print("\nWORD TIMESTAMPS:")
    print("-" * 70)
    print(f"{'Start (s)':<12} {'End (s)':<12} {'Word'}")
    print("-" * 70)
    for word in result.words:
        print(f"{word.start:<12.3f} {word.end:<12.3f} {word.word}")
    print("-" * 70)
    
    # Write to file if requested
    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        if output_file.suffix.lower() == ".json":
            # JSON output
            json_data = {
                "transcript": result.transcript,
                "language": result.language,
                "duration": result.duration,
                "words": [
                    {
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                    }
                    for word in result.words
                ],
            }
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            print(f"\n✓ Results saved to JSON: {output_path}")
        else:
            # Plain text output
            with open(output_file, "w", encoding="utf-8") as f:
                f.write("LYRICS DETECTION RESULTS\n")
                f.write("=" * 70 + "\n")
                f.write(f"Audio duration: {result.duration:.2f} seconds\n")
                f.write(f"Detected language: {result.language}\n")
                f.write(f"Total words: {len(result.words)}\n")
                f.write("=" * 70 + "\n\n")
                f.write("FULL TRANSCRIPT:\n")
                f.write("-" * 70 + "\n")
                f.write(result.transcript + "\n")
                f.write("-" * 70 + "\n\n")
                f.write("WORD TIMESTAMPS:\n")
                f.write("-" * 70 + "\n")
                f.write(f"{'Start (s)':<12} {'End (s)':<12} {'Word'}\n")
                f.write("-" * 70 + "\n")
                for word in result.words:
                    f.write(f"{word.start:<12.3f} {word.end:<12.3f} {word.word}\n")
                f.write("-" * 70 + "\n")
            print(f"\n✓ Results saved to text file: {output_path}")


def handle_render_command(args) -> None:
    """Handle the render subcommand."""
    logger.info("AudioGiphy MVP - Starting render")
    logger.info(f"Audio: {args.audio}")
    logger.info(f"Video folder: {args.gif_folder}")
    logger.info(f"Duration: {args.duration_seconds}s")
    logger.info(f"Output: {args.output}")
    logger.info(f"Resolution: {args.width}x{args.height}")
    
    # Validate prerequisites
    logger.info("Validating prerequisites")
    check_ffmpeg()
    validate_paths(args.audio, args.gif_folder)
    
    # Validate karaoke mode requires lyrics JSON
    if args.karaoke_mode and not args.lyrics_json:
        raise ValueError("--karaoke-mode requires --lyrics-json to be provided")
    
    # Validate GIPHY plan file exists if provided
    if args.lyrics_giphy_plan:
        from pathlib import Path
        if not Path(args.lyrics_giphy_plan).exists():
            raise FileNotFoundError(f"GIPHY plan file not found: {args.lyrics_giphy_plan}")
    
    render_video(
        audio_path=args.audio,
        video_folder=args.gif_folder,
        duration_seconds=args.duration_seconds,
        output_path=args.output,
        resolution=(args.width, args.height),
        seed=args.seed,
        lyrics_json_path=args.lyrics_json,
        karaoke_mode=args.karaoke_mode,
        lyrics_giphy_plan_path=args.lyrics_giphy_plan,
    )
    
    logger.info("Render completed successfully!")


def handle_detect_lyrics_command(args) -> None:
    """Handle the detect-lyrics subcommand."""
    from audiogiphy.lyrics_analysis import detect_lyrics
    
    logger.info("Starting lyrics detection")
    logger.info(f"Audio: {args.audio}")
    
    validate_paths(args.audio)
    
    # Run lyrics detection
    result = detect_lyrics(
        audio_path=args.audio,
        language=args.language if args.language else "auto",
        model_size=args.model_size,
        initial_prompt=args.initial_prompt,
    )
    
    # Format and output results
    format_lyrics_output(result, args.lyrics_output)
    
    logger.info("Lyrics detection completed successfully!")


def main() -> None:
    """Main entry point for the CLI."""
    try:
        args = parse_args()
        
        if args.command == "render":
            handle_render_command(args)
        elif args.command == "detect-lyrics":
            handle_detect_lyrics_command(args)
        else:
            logger.error(f"Unknown command: {args.command}")
            sys.exit(1)
        
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"ERROR: {repr(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
