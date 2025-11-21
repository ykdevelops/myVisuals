# AudioGiphy

AudioGiphy is a Python tool that creates vertical videos from audio tracks by syncing 1-second visual clips to the track's BPM (beats per minute). It includes advanced lyric detection and overlay features, supporting both phrase-ending word highlights and full karaoke mode. This MVP demonstrates a fully local, memory-efficient video rendering pipeline that analyzes audio, detects lyrics, selects clips from a local bank, and produces a final MP4 synchronized to the music.

## Overview

AudioGiphy takes a local audio file and a folder of MP4 clips, then:

- **Analyzes BPM** over time using librosa
- **Detects lyrics** using OpenAI Whisper (optional) with word-level timestamps
- **Selects clips** randomly from a local bank folder
- **Builds 1-second segments** synced to the BPM timeline
- **Overlays lyrics** (optional) in phrase-ending mode or full karaoke mode
- **Renders a vertical MP4** (1080x1920 by default) with the original audio attached

The tool is designed to be memory-efficient, handling long videos (48+ minutes) without running out of memory by writing clips to disk immediately and using ffmpeg for efficient concatenation.

## Requirements

- **Python**: 3.11 or higher
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

### Basic Render (BPM-synced visuals only)

```bash
python -m audiogiphy.cli render \
  --audio "song.mp3" \
  --gif-folder bank \
  --duration-seconds 60 \
  --output output.mp4
```

### Render with Phrase-Ending Lyrics

```bash
# First, detect lyrics
python -m audiogiphy.cli detect-lyrics \
  --audio "song.mp3" \
  --lyrics-output lyrics.json

# Then render with lyrics overlay
python -m audiogiphy.cli render \
  --audio "song.mp3" \
  --gif-folder bank \
  --duration-seconds 60 \
  --output output_with_lyrics.mp4 \
  --lyrics-json lyrics.json
```

### Render with Karaoke Mode (All Words)

```bash
# Detect lyrics (same as above)
python -m audiogiphy.cli detect-lyrics \
  --audio "song.mp3" \
  --lyrics-output lyrics.json

# Render with karaoke mode
python -m audiogiphy.cli render \
  --audio "song.mp3" \
  --gif-folder bank \
  --duration-seconds 60 \
  --output karaoke_output.mp4 \
  --lyrics-json lyrics.json \
  --karaoke-mode
```

### Example Folder Layout

```
myVisuals/
├── bank/              # MP4 clips (source videos)
├── mixes/             # Audio files (.wav, .mp3)
├── renders/           # Output videos
├── audiogiphy/        # Package source code
└── *.json             # Lyrics JSON files (from detect-lyrics)
```

## CLI Commands

### Render Command

Creates a BPM-synced video with optional lyric overlays.

**Required arguments:**
- `--audio`: Path to input audio file (WAV, MP3, etc.)
- `--gif-folder`: Path to folder containing MP4 video files

**Optional arguments:**
- `--duration-seconds`: Duration of output video in seconds (default: 60)
- `--output`: Path for output video file (default: output.mp4)
- `--width`: Video width in pixels (default: 1080)
- `--height`: Video height in pixels (default: 1920)
- `--seed`: Random seed for reproducible results
- `--lyrics-json`: Path to lyrics JSON file from `detect-lyrics`. If provided, overlays phrase-ending words on video.
- `--karaoke-mode`: Display all words per second (karaoke mode). Requires `--lyrics-json`.

**Examples:**
```bash
# Basic render
python -m audiogiphy.cli render --audio song.mp3 --gif-folder bank --duration-seconds 30 --output out.mp4

# With phrase-ending lyrics
python -m audiogiphy.cli render --audio song.mp3 --gif-folder bank --output out.mp4 --lyrics-json lyrics.json

# With karaoke mode (all words)
python -m audiogiphy.cli render --audio song.mp3 --gif-folder bank --output karaoke.mp4 --lyrics-json lyrics.json --karaoke-mode
```

### Detect Lyrics Command

Detects lyrics from an audio file using OpenAI Whisper and outputs word-level timestamps.

**Required arguments:**
- `--audio`: Path to input audio file (WAV, MP3, etc.)

**Optional arguments:**
- `--lyrics-output`: Path to output file (JSON or .txt). If not provided, prints to terminal only
- `--language`: Language code (e.g., 'en', 'es', 'fr'). Default: auto-detect
- `--model-size`: Whisper model size - tiny, base, small, medium, large (default: medium)
- `--initial-prompt`: Optional prompt to guide transcription (e.g., 'Glamorous by Fergie feat Ludacris')

**Examples:**
```bash
# Detect and print to terminal
python -m audiogiphy.cli detect-lyrics --audio song.mp3

# Detect and save to JSON
python -m audiogiphy.cli detect-lyrics --audio song.mp3 --lyrics-output lyrics.json

# Detect with custom language and model
python -m audiogiphy.cli detect-lyrics --audio song.mp3 --language es --model-size small --lyrics-output lyrics.json
```

**Note:** If the audio file is shorter than the requested duration, the output will be clamped to the audio length.

## Features

### 1. BPM Analysis with librosa

The audio file is analyzed using librosa to detect BPM changes over time. The analysis:
- Slides a window over the audio track
- Estimates BPM for each window
- Groups similar BPM regions into segments
- Creates a per-second BPM timeline
- Adjusts clip playback speed based on local BPM relative to base BPM

### 2. Lyric Detection with Whisper

Optional lyric detection using OpenAI Whisper:
- **Model**: Medium by default (configurable: tiny, base, small, medium, large)
- **Word-level timestamps**: Precise start/end times for each word
- **Language detection**: Auto-detects language or specify manually
- **Music-optimized**: Tuned parameters for better music transcription
- **Output formats**: JSON (with timestamps) or plain text

### 3. Lyric Overlay Modes

Two lyric overlay modes are available:

#### Phrase-Ending Mode (Default)
- Detects lyric phrases using punctuation and time gaps
- Extracts the last meaningful word from each phrase
- Displays large, bold, white text (120px) centered on screen
- Words appear at phrase endings for one second

#### Karaoke Mode (`--karaoke-mode`)
- Displays all words spoken in each second
- Words are joined into lines and auto-wrapped
- Smaller font size (80px) for readability
- Text positioned in upper quarter of screen
- Perfect for synchronized karaoke-style display

### 4. 1 Second Visual Clips from Local Bank

For each second of the output video:
- A random MP4 is selected from the video bank folder
- A random subclip is extracted
- Playback speed is adjusted based on local BPM relative to the base BPM
- The clip is resized with letterboxing to the target resolution (1080x1920)
- Optional lyric overlay is applied (if lyrics JSON provided)
- A 1-second MP4 clip is written to disk

### 5. Final MP4 with Original Audio

- All 1-second clips are concatenated using ffmpeg (stream copy, no re-encoding)
- The original audio track is trimmed to match the video duration
- Audio is attached to the video
- The final MP4 is written to the output path

## Project Structure

```
audiogiphy/
├── __init__.py           # Package initialization and exports
├── audio_analysis.py     # BPM analysis functions
├── visual_builder.py     # Video clip processing and building
├── lyrics_analysis.py    # Whisper-based lyric detection
├── lyrics_overlays.py    # Lyric parsing and overlay mapping
├── render_pipeline.py    # Main rendering orchestration
├── config.py             # Centralized configuration constants
├── cli.py                # Command-line interface
├── giphy_placeholder.py  # Placeholder for future GIPHY API integration
├── api.py                # Flask API endpoints
└── api_server.py         # API server entry point
```

## Memory Efficiency

The pipeline is designed to handle long videos without running out of memory:
- Clips are written to disk immediately, not kept in memory
- Only one VideoFileClip is loaded at a time (the final concatenated video)
- ffmpeg handles concatenation efficiently using stream copy (no re-encoding)
- Checkpoints allow resuming interrupted renders

## Checkpoints

The script automatically saves checkpoints every 50 seconds. If interrupted, it will resume from the last checkpoint when run again with the same output path.

Checkpoints are stored in: `<output_directory>/checkpoints/<output_filename>/`

## Error Handling

The tool handles common failures gracefully:
- **Missing ffmpeg**: Clear error message with installation instructions
- **No usable clips**: Validates MP4 files exist in the bank folder
- **Audio shorter than duration**: Automatically clamps duration to audio length
- **Corrupted clips**: Automatically blacklists problematic files and uses fallback frames
- **Lyric detection failures**: Logs warnings and continues without lyrics
- **Text overlay failures**: Preserves video clip even if text rendering fails

## Configuration

Key configuration constants are centralized in `audiogiphy/config.py`:
- Video defaults (resolution, FPS, clip duration)
- BPM analysis parameters
- Whisper model settings
- Lyric overlay styling (font size, colors, positioning)

## Testing

Run tests with pytest:
```bash
pytest tests/
```

Test coverage includes:
- BPM analysis
- Visual builder
- Lyric detection
- Lyric overlays (phrase-ending and karaoke mapping)
- Render pipeline

## Web Frontend (Vue.js)

AudioGiphy includes a minimal Vue.js web interface for testing renders without using the CLI.

### Setup Frontend

1. Install Node.js and npm (if not already installed)

2. Install frontend dependencies:
```bash
cd frontend
npm install
```

3. Start the backend API server (in one terminal):
```bash
python -m audiogiphy.api_server
```

4. Start the Vue.js dev server (in another terminal):
```bash
cd frontend
npm run dev
```

5. Open your browser to `http://localhost:5173`

### Using the Web Interface

- Fill in the form with your render parameters
- Click "Start Render" to begin
- Watch logs stream in real-time
- Errors are displayed at the top if validation fails

### Building for Production

To build the frontend for production:
```bash
cd frontend
npm run build
```

The built files will be in `frontend/dist/` and will be served automatically by the API server.

## Future Work

- **Real GIPHY API Integration**: Replace local video folder with real-time GIPHY search using `GiphyClient` in `giphy_placeholder.py`
- **Mood and Genre Aware Clip Selection**: Analyze audio mood/genre and select clips that match
- **Advanced Lyric Styling**: Customizable fonts, colors, animations
- **Multi-language Support**: Enhanced language detection and transcription

## License

[Add your license here]

## Contributing

This is an MVP project. Contributions and feedback welcome!
