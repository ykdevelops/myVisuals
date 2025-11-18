# AudioGiphy

AudioGiphy is an experimental tool that turns a music track into a vertical video made from 1 second GIF clips, roughly synced to the track BPM.

## Overview

This MVP demonstrates a BPM-driven video visualizer that:
- Analyzes audio files to detect BPM changes over time
- Randomly selects clips from a local folder of MP4s/GIFs
- Builds 1-second visual segments synced to BPM
- Concatenates segments with ffmpeg and attaches the original audio

The tool is designed to be memory-efficient, handling long videos (48+ minutes) without running out of memory by writing clips to disk and using ffmpeg for concatenation.

## Requirements

- **Python**: 3.10 or higher
- **ffmpeg**: Must be installed and available in PATH
- **Python packages**: See `requirements.txt`

### Installing ffmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/ykdevelops/myVisuals.git
cd myVisuals
```

2. Create a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Quick Start

```bash
python -m audiogiphy.cli \
  --audio path/to/audio.wav \
  --gif-folder path/to/video_bank \
  --duration-seconds 60 \
  --output output.mp4
```

### Example

```bash
python -m audiogiphy.cli \
  --audio mixes/test_mix.mp3 \
  --gif-folder bank \
  --duration-seconds 60 \
  --output renders/test_output.mp4 \
  --width 720 \
  --height 1280 \
  --seed 42
```

## CLI Arguments

- `--audio` (required): Path to input audio file (WAV, MP3, etc.)
- `--gif-folder` (required): Path to folder containing MP4 video files
- `--duration-seconds` (optional): Duration of output video in seconds (default: 60)
- `--output` (optional): Path for output video file (default: output.mp4)
- `--width` (optional): Video width in pixels (default: 1080)
- `--height` (optional): Video height in pixels (default: 1920)
- `--seed` (optional): Random seed for reproducible results

## How It Works

1. **BPM Analysis**: Analyzes the audio file to detect BPM segments and creates a per-second BPM timeline
2. **Clip Generation**: For each second:
   - Randomly selects a source MP4 from the video bank
   - Extracts a random subclip
   - Adjusts speed based on local BPM relative to base BPM
   - Resizes with letterboxing to target resolution
   - Writes to disk as a 1-second clip
3. **Concatenation**: Uses ffmpeg concat demuxer to combine all clips (fast, no re-encoding)
4. **Audio Attachment**: Attaches the trimmed audio track to the final video

## Project Structure

```
audiogiphy/
├── __init__.py           # Package initialization
├── audio_analysis.py     # BPM analysis functions
├── visual_builder.py     # Video clip processing and building
├── giphy_placeholder.py  # Placeholder for future GIPHY API integration
├── render_pipeline.py    # Main rendering orchestration
└── cli.py                # Command-line interface
```

## Memory Efficiency

The script is designed to handle long videos without running out of memory:
- Clips are written to disk immediately, not kept in memory
- Only one VideoFileClip is loaded at a time (the final concatenated video)
- ffmpeg handles concatenation efficiently using stream copy

## Checkpoints

The script automatically saves checkpoints every 50 seconds. If interrupted, it will resume from the last checkpoint when run again with the same output path.

Checkpoints are stored in: `checkpoints/<output_filename>/`

## Future Work

- **GIPHY API Integration**: Replace local video folder with real-time GIPHY search via `GiphyClient`
- **Lyric Analysis**: Optional lyric analysis using speech-to-text to better sync visuals
- **Mood and Genre Tagging**: Better clip selection based on audio mood/genre detection
- **Web Interface**: Simple web UI for easier use

## License

[Add your license here]

## Contributing

This is an MVP project. Contributions and feedback welcome!
