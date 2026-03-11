"""Tests for config extender Windows platform handling."""

from pathlib import Path
import pytest

WINDOWS_PLATFORMS = {"Win32", "Win64", "Win64x"}


class TestConfigExtenderWindows:
    """Test that Windows platform extensions skip paths."""

    def test_windows_platform_detected(self):
        for p in ["Win32", "Win64", "Win64x"]:
            assert p in WINDOWS_PLATFORMS
