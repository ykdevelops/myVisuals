#!/usr/bin/env python3
"""
Convert all GIF files in a folder to MP4 format.
This improves performance and quality for the video renderer.
"""
import subprocess
from pathlib import Path
from typing import Tuple
from tqdm import tqdm


def convert_gif_to_mp4(gif_path: Path, mp4_path: Path) -> bool:
    """Convert a single GIF to MP4 using ffmpeg."""
    try:
        # Use ffmpeg to convert GIF to MP4
        # -y: overwrite output file if it exists
        # -i: input file
        # -vf: video filter to ensure good quality
        # -pix_fmt yuv420p: ensure compatibility
        # -movflags +faststart: optimize for streaming
        cmd = [
            "ffmpeg",
            "-y",  # overwrite output
            "-i", str(gif_path),
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # ensure even dimensions
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-an",  # no audio
            str(mp4_path),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error converting {gif_path.name}: {e.stderr}", flush=True)
        return False
    except Exception as e:
        print(f"Unexpected error converting {gif_path.name}: {e}", flush=True)
        return False


def convert_gif_bank(input_dir: str | Path, output_dir: str | Path | None = None) -> Tuple[int, int, int]:
    """
    Convert all GIF files from input directory to MP4 format.
    
    Args:
        input_dir: Path to folder containing GIF files
        output_dir: Path to output folder (defaults to same as input_dir)
        
    Returns:
        Tuple of (converted_count, skipped_count, failed_count)
    """
    input_folder = Path(input_dir)
    if not input_folder.exists():
        raise FileNotFoundError(f"Input folder not found: {input_folder}")
    
    if output_dir is None:
        output_folder = input_folder
    else:
        output_folder = Path(output_dir)
        output_folder.mkdir(parents=True, exist_ok=True)
    
    # Find all GIF files
    gif_files = sorted([f for f in input_folder.glob("*.gif") if f.is_file()])
    if not gif_files:
        print("No GIF files found in input folder", flush=True)
        return (0, 0, 0)
    
    print(f"Found {len(gif_files)} GIF files to convert", flush=True)
    
    converted = 0
    skipped = 0
    failed = 0
    
    for gif_path in tqdm(gif_files, desc="Converting GIFs to MP4", ncols=80):
        if output_folder == input_folder:
            mp4_path = gif_path.with_suffix(".mp4")
        else:
            mp4_path = output_folder / gif_path.with_suffix(".mp4").name
        
        # Skip if MP4 already exists
        if mp4_path.exists():
            skipped += 1
            continue
        
        if convert_gif_to_mp4(gif_path, mp4_path):
            converted += 1
        else:
            failed += 1
    
    print(f"\nConversion complete:", flush=True)
    print(f"  Converted: {converted}", flush=True)
    print(f"  Skipped (already exists): {skipped}", flush=True)
    print(f"  Failed: {failed}", flush=True)
    
    if failed == 0 and converted > 0:
        print(f"\nAll GIFs converted successfully! You can now delete the .gif files if desired.", flush=True)
    
    return (converted, skipped, failed)


def main():
    """Main entry point for command-line usage."""
    bank_folder = Path("bank")
    if not bank_folder.exists():
        print(f"Error: {bank_folder} folder not found", flush=True)
        return
    
    convert_gif_bank(bank_folder)


if __name__ == "__main__":
    main()

