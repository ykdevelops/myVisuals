"""
Smoke tests for config module.
Verifies that config values are valid and accessible.
"""
import pytest

from audiogiphy import config


def test_config_values_exist():
    """Verify all config constants exist and have valid types."""
    assert hasattr(config, "DEFAULT_FPS")
    assert isinstance(config.DEFAULT_FPS, int)
    assert config.DEFAULT_FPS > 0
    
    assert hasattr(config, "DEFAULT_RESOLUTION")
    assert isinstance(config.DEFAULT_RESOLUTION, tuple)
    assert len(config.DEFAULT_RESOLUTION) == 2
    assert all(isinstance(x, int) and x > 0 for x in config.DEFAULT_RESOLUTION)
    
    assert hasattr(config, "CLIP_DURATION_SECONDS")
    assert isinstance(config.CLIP_DURATION_SECONDS, float)
    assert config.CLIP_DURATION_SECONDS > 0
    
    assert hasattr(config, "BPM_WINDOW_SECONDS")
    assert isinstance(config.BPM_WINDOW_SECONDS, float)
    assert config.BPM_WINDOW_SECONDS > 0
    
    assert hasattr(config, "BPM_HOP_SECONDS")
    assert isinstance(config.BPM_HOP_SECONDS, float)
    assert config.BPM_HOP_SECONDS > 0
    
    assert hasattr(config, "CHECKPOINTS_DIR")
    assert isinstance(config.CHECKPOINTS_DIR, str)
    assert len(config.CHECKPOINTS_DIR) > 0

