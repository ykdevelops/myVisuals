"""
Smoke tests for render pipeline module.
Verifies that functions can be called without crashing.
"""
import pytest
from pathlib import Path

from audiogiphy.render_pipeline import render_video


def test_render_video_missing_audio():
    """Test that render_video raises FileNotFoundError for missing audio."""
    with pytest.raises(FileNotFoundError):
        render_video(
            audio_path="nonexistent_audio.wav",
            video_folder="bank",
            duration_seconds=10,
            output_path="test_output.mp4",
        )


def test_render_video_missing_video_folder():
    """Test that render_video raises FileNotFoundError for missing video folder."""
    # Create a dummy audio file for testing
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_audio:
        tmp_audio.write(b"dummy audio data")
        tmp_audio_path = tmp_audio.name
    
    try:
        with pytest.raises(FileNotFoundError):
            render_video(
                audio_path=tmp_audio_path,
                video_folder="nonexistent_folder",
                duration_seconds=10,
                output_path="test_output.mp4",
            )
    finally:
        Path(tmp_audio_path).unlink(missing_ok=True)


@pytest.mark.skipif(
    not Path("clean mashup mix 88 to 134.wav").exists() or 
    not Path("bank").exists() or 
    len(list(Path("bank").glob("*.mp4"))) == 0,
    reason="Required files not found for full pipeline test"
)
def test_render_video_end_to_end():
    """Test full render pipeline with actual files if available."""
    audio_path = "clean mashup mix 88 to 134.wav"
    bank_path = Path("bank")
    
    # Test with very short duration to keep test fast
    duration = 3
    output_path = "test_render_output.mp4"
    
    try:
        render_video(
            audio_path=audio_path,
            video_folder=str(bank_path),
            duration_seconds=duration,
            output_path=output_path,
            resolution=(720, 1280),  # Smaller resolution for faster test
        )
        # Verify output was created
        assert Path(output_path).exists()
    finally:
        # Cleanup
        Path(output_path).unlink(missing_ok=True)
        # Cleanup checkpoint directory
        checkpoint_dir = Path(output_path).parent / "checkpoints" / Path(output_path).stem
        if checkpoint_dir.exists():
            import shutil
            shutil.rmtree(checkpoint_dir, ignore_errors=True)

