# BPM-Driven Video Visualizer

A memory-efficient Python script that generates synchronized video visuals from a folder of MP4 clips, driven by BPM analysis of an audio track.

## Features

- **BPM Analysis**: Uses librosa to analyze audio and detect BPM changes throughout the track
- **Dynamic Speed**: Adjusts video clip playback speed based on local BPM relative to base BPM
- **Memory Efficient**: Uses ffmpeg for concatenation instead of loading thousands of clips into memory
- **Checkpoint System**: Can resume rendering from checkpoints if interrupted
- **Blacklist System**: Automatically blacklists problematic source files

## Requirements

- Python 3.10+
- ffmpeg
- Python packages (see `requirements.txt`)

## Installation

1. Clone this repository:
```bash
git clone <your-repo-url>
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

4. Install ffmpeg:
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
```

## Usage

```bash
python main.py \
  --audio path/to/audio.wav \
  --gif-folder path/to/video_bank \
  --duration-seconds 2936 \
  --output output.mp4 \
  --width 720 \
  --height 1280 \
  --seed 42  # optional
```

### Arguments

- `--audio`: Path to audio file (WAV, MP3, etc.)
- `--gif-folder`: Folder containing MP4 video files (legacy arg name, accepts MP4s)
- `--duration-seconds`: Duration of output video in seconds
- `--output`: Output file path
- `--width`: Video width in pixels (default: 1080)
- `--height`: Video height in pixels (default: 1920)
- `--seed`: Random seed for reproducible results (optional)

## How It Works

1. **BPM Analysis**: Analyzes the audio file to detect BPM segments and creates a per-second BPM timeline
2. **Clip Generation**: For each second:
   - Randomly selects a source MP4 from the video bank
   - Extracts a random subclip
   - Adjusts speed based on local BPM
   - Resizes with letterboxing to target resolution
   - Writes to disk as a 1-second clip
3. **Concatenation**: Uses ffmpeg concat demuxer to combine all clips (fast, no re-encoding)
4. **Audio Attachment**: Attaches the trimmed audio track to the final video

## Memory Efficiency

The script is designed to handle long videos (e.g., 48+ minutes) without running out of memory:
- Clips are written to disk immediately, not kept in memory
- Only one VideoFileClip is loaded at a time (the final concatenated video)
- ffmpeg handles concatenation efficiently using stream copy

## Checkpoints

The script automatically saves checkpoints every 50 seconds. If interrupted, it will resume from the last checkpoint when run again with the same output path.

Checkpoints are stored in: `checkpoints/<output_filename>/`

## License

[Add your license here]

