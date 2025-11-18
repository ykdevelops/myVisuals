"""
Command-Line Interface for AudioGiphy.

Provides a simple CLI for rendering BPM-synced videos from audio tracks.
"""

import argparse
import sys
import traceback

from audiogiphy.render_pipeline import render_video


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.
    
    Returns:
        Namespace object with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="AudioGiphy - BPM-driven video visualizer MVP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Render a 60-second video
  python -m audiogiphy.cli \\
    --audio mixes/test_mix.mp3 \\
    --gif-folder bank \\
    --duration-seconds 60 \\
    --output renders/test_output.mp4

  # Render with custom resolution and seed
  python -m audiogiphy.cli \\
    --audio mixes/test_mix.mp3 \\
    --gif-folder bank \\
    --duration-seconds 120 \\
    --output renders/output.mp4 \\
    --width 720 \\
    --height 1280 \\
    --seed 42
        """
    )
    
    parser.add_argument(
        "--audio",
        required=True,
        help="Path to input audio file (WAV, MP3, etc.)"
    )
    parser.add_argument(
        "--gif-folder",
        required=True,
        help="Path to folder containing MP4 video files (legacy arg name, accepts MP4s)"
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=60,
        help="Duration of output video in seconds (default: 60)"
    )
    parser.add_argument(
        "--output",
        default="output.mp4",
        help="Path for output video file (default: output.mp4)"
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1080,
        help="Video width in pixels (default: 1080)"
    )
    parser.add_argument(
        "--height",
        type=int,
        default=1920,
        help="Video height in pixels (default: 1920)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible results (optional)"
    )
    
    return parser.parse_args()


def main() -> None:
    """Main entry point for the CLI."""
    try:
        args = parse_args()
        print("[cli] AudioGiphy MVP - Starting render", flush=True)
        print(f"[cli] Audio: {args.audio}", flush=True)
        print(f"[cli] Video folder: {args.gif_folder}", flush=True)
        print(f"[cli] Duration: {args.duration_seconds}s", flush=True)
        print(f"[cli] Output: {args.output}", flush=True)
        print(f"[cli] Resolution: {args.width}x{args.height}", flush=True)
        
        render_video(
            audio_path=args.audio,
            video_folder=args.gif_folder,
            duration_seconds=args.duration_seconds,
            output_path=args.output,
            resolution=(args.width, args.height),
            seed=args.seed,
        )
        
        print("[cli] Render completed successfully!", flush=True)
        
    except KeyboardInterrupt:
        print("\n[cli] Interrupted by user", flush=True)
        sys.exit(1)
    except Exception as e:
        print(f"[cli] ERROR: {repr(e)}", flush=True)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

