"""Tests for WSL-to-Windows path conversion."""

from unittest.mock import patch

import pytest

from src.path_utils import convert_wsl_to_windows_path


class TestConvertWslToWindowsPath:
    """Tests for convert_wsl_to_windows_path function."""

    @patch("src.path_utils.sys")
    def test_wsl_path_converts_on_win32(self, mock_sys):
        """Standard WSL path is converted when running on win32."""
        mock_sys.platform = "win32"
        result = convert_wsl_to_windows_path("/mnt/x/git_local/profdiaf-wire/ProfDiaF.dproj")
        assert result == "X:\\git_local\\profdiaf-wire\\ProfDiaF.dproj"

    @patch("src.path_utils.sys")
    def test_wsl_path_converts_on_win64(self, mock_sys):
        """Standard WSL path is converted when running on win64."""
        mock_sys.platform = "win64"
        result = convert_wsl_to_windows_path("/mnt/c/Users/Teufel/project/Main.dpr")
        assert result == "C:\\Users\\Teufel\\project\\Main.dpr"

    @patch("src.path_utils.sys")
    def test_drive_letter_is_uppercased(self, mock_sys):
        """Drive letter is always uppercased."""
        mock_sys.platform = "win32"
        result = convert_wsl_to_windows_path("/mnt/c/some/path")
        assert result == "C:\\some\\path"

    @patch("src.path_utils.sys")
    def test_drive_root_only(self, mock_sys):
        """WSL drive root /mnt/c converts to C:\\."""
        mock_sys.platform = "win32"
        result = convert_wsl_to_windows_path("/mnt/c")
        assert result == "C:"

    @patch("src.path_utils.sys")
    def test_drive_root_with_trailing_slash(self, mock_sys):
        """WSL drive root /mnt/c/ converts to C:\\."""
        mock_sys.platform = "win32"
        result = convert_wsl_to_windows_path("/mnt/c/")
        assert result == "C:\\"

    @patch("src.path_utils.sys")
    def test_various_drive_letters(self, mock_sys):
        """Multiple drive letters are handled correctly."""
        mock_sys.platform = "win32"
        for letter in ("c", "d", "x", "z"):
            result = convert_wsl_to_windows_path(f"/mnt/{letter}/data")
            assert result == f"{letter.upper()}:\\data"

    @patch("src.path_utils.sys")
    def test_deep_path(self, mock_sys):
        """Deeply nested paths are converted correctly."""
        mock_sys.platform = "win32"
        result = convert_wsl_to_windows_path("/mnt/d/a/b/c/d/e/f/file.pas")
        assert result == "D:\\a\\b\\c\\d\\e\\f\\file.pas"

    @patch("src.path_utils.sys")
    def test_path_with_spaces(self, mock_sys):
        """Paths with spaces are preserved."""
        mock_sys.platform = "win32"
        result = convert_wsl_to_windows_path("/mnt/c/Program Files/Embarcadero/Studio/23.0")
        assert result == "C:\\Program Files\\Embarcadero\\Studio\\23.0"

    @patch("src.path_utils.sys")
    def test_windows_path_unchanged_on_windows(self, mock_sys):
        """Already-Windows paths are returned unchanged."""
        mock_sys.platform = "win32"
        result = convert_wsl_to_windows_path("C:\\Users\\Teufel\\project\\Main.dpr")
        assert result == "C:\\Users\\Teufel\\project\\Main.dpr"

    @patch("src.path_utils.sys")
    def test_non_mnt_unix_path_unchanged_on_windows(self, mock_sys):
        """Non-/mnt/ Unix paths are returned unchanged on Windows."""
        mock_sys.platform = "win32"
        result = convert_wsl_to_windows_path("/home/user/project/file.dpr")
        assert result == "/home/user/project/file.dpr"

    @patch("src.path_utils.sys")
    def test_wsl_path_unchanged_on_linux(self, mock_sys):
        """WSL-style paths are NOT converted when running on Linux."""
        mock_sys.platform = "linux"
        result = convert_wsl_to_windows_path("/mnt/c/Users/Teufel/project/Main.dpr")
        assert result == "/mnt/c/Users/Teufel/project/Main.dpr"

    @patch("src.path_utils.sys")
    def test_wsl_path_unchanged_on_darwin(self, mock_sys):
        """WSL-style paths are NOT converted when running on macOS."""
        mock_sys.platform = "darwin"
        result = convert_wsl_to_windows_path("/mnt/c/Users/Teufel/project/Main.dpr")
        assert result == "/mnt/c/Users/Teufel/project/Main.dpr"

    @patch("src.path_utils.sys")
    def test_mnt_with_long_name_not_matched(self, mock_sys):
        """/mnt/cd/... is NOT a valid WSL mount (must be single letter)."""
        mock_sys.platform = "win32"
        result = convert_wsl_to_windows_path("/mnt/cd/some/path")
        assert result == "/mnt/cd/some/path"

    @patch("src.path_utils.sys")
    def test_relative_path_unchanged(self, mock_sys):
        """Relative paths are returned unchanged."""
        mock_sys.platform = "win32"
        result = convert_wsl_to_windows_path("relative/path/file.dpr")
        assert result == "relative/path/file.dpr"

    @patch("src.path_utils.sys")
    def test_dot_path_unchanged(self, mock_sys):
        """Dot path is returned unchanged."""
        mock_sys.platform = "win32"
        result = convert_wsl_to_windows_path(".")
        assert result == "."
