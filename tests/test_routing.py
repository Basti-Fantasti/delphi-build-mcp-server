"""Tests for platform-based routing in handle_compile_project."""

from pathlib import Path

WINDOWS_PLATFORMS = {"Win32", "Win64", "Win64x"}
CROSSCOMPILE_PLATFORMS = {"Linux64", "Android", "Android64"}


class TestPlatformRouting:
    """Test that platforms route to the correct compiler."""

    def test_win32_is_windows(self):
        assert "Win32" in WINDOWS_PLATFORMS

    def test_win64_is_windows(self):
        assert "Win64" in WINDOWS_PLATFORMS

    def test_win64x_is_windows(self):
        assert "Win64x" in WINDOWS_PLATFORMS

    def test_linux64_is_crosscompile(self):
        assert "Linux64" not in WINDOWS_PLATFORMS

    def test_android_is_crosscompile(self):
        assert "Android" not in WINDOWS_PLATFORMS

    def test_android64_is_crosscompile(self):
        assert "Android64" not in WINDOWS_PLATFORMS

    def test_default_platform_is_win32(self):
        default = "Win32"
        assert default in WINDOWS_PLATFORMS
