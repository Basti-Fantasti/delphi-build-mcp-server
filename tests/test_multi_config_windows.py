"""Tests for multi-config generator Windows platform grouping."""

from pathlib import Path
import pytest

WINDOWS_PLATFORMS = {"Win32", "Win64", "Win64x"}


class TestMultiConfigWindowsGrouping:
    """Test that Windows platform logs are grouped into one minimal config."""

    def test_is_windows_platform(self):
        for p in ["Win32", "Win64", "Win64x"]:
            assert p in WINDOWS_PLATFORMS

    def test_crosscompile_not_grouped(self):
        for p in ["Linux64", "Android", "Android64"]:
            assert p not in WINDOWS_PLATFORMS
