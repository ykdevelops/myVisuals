"""
Smoke tests for visual builder module.
Verifies that functions can be called without crashing.
"""
import pytest
from pathlib import Path

from audiogiphy.visual_builder import build_visual_track


def test_build_visual_track_missing_folder():
    """Test that build_visual_track raises FileNotFoundError for missing folder."""
    with pytest.raises(FileNotFoundError):
        build_visual_track(
            video_folder="nonexistent_folder",
            bpm_values=[120.0] * 10,
            duration_seconds=10,
            target_resolution=(1080, 1920),
            base_bpm=120.0,
        )


def test_build_visual_track_empty_folder():
    """Test that build_visual_track raises FileNotFoundError for folder with no MP4s."""
    # Create a temporary empty directory
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(FileNotFoundError, match="No usable MP4 files"):
            build_visual_track(
                video_folder=tmpdir,
                bpm_values=[120.0] * 10,
                duration_seconds=10,
                target_resolution=(1080, 1920),
                base_bpm=120.0,
            )


@pytest.mark.skipif(
    not Path("bank").exists() or len(list(Path("bank").glob("*.mp4"))) == 0,
    reason="Bank folder with MP4 files not found"
)
def test_build_visual_track_with_bank():
    """Test visual builder with actual bank folder if available."""
    bank_path = Path("bank")
    mp4_files = list(bank_path.glob("*.mp4"))
    if not mp4_files:
        pytest.skip("No MP4 files in bank folder")
    
    # Test with a very short duration to keep test fast
    duration = 2
    bpm_values = [120.0] * duration
    
    # Use a temporary checkpoint directory
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        checkpoint_dir = Path(tmpdir) / "test_checkpoints"
        clip_paths = build_visual_track(
            video_folder=str(bank_path),
            bpm_values=bpm_values,
            duration_seconds=duration,
            target_resolution=(1080, 1920),
            base_bpm=120.0,
            checkpoint_dir=checkpoint_dir,
        )
        assert len(clip_paths) == duration
        assert all(isinstance(p, Path) for p in clip_paths)
        # Verify clips were created
        assert all(p.exists() for p in clip_paths)

