"""Tests for platform-specific config file functionality."""

import os
import tempfile
from pathlib import Path

import pytest

from src.config import (
    get_platform_config_filename,
    find_config_file_for_platform,
    PLATFORM_CONFIG_NAMES,
)


class TestGetPlatformConfigFilename:
    """Tests for get_platform_config_filename function."""

    def test_win32_filename(self):
        """Test Win32 returns correct filename."""
        assert get_platform_config_filename("Win32") == "delphi_config_win32.toml"

    def test_win64_filename(self):
        """Test Win64 returns correct filename."""
        assert get_platform_config_filename("Win64") == "delphi_config_win64.toml"

    def test_win64x_filename(self):
        """Test Win64x returns correct filename."""
        assert get_platform_config_filename("Win64x") == "delphi_config_win64x.toml"

    def test_linux64_filename(self):
        """Test Linux64 returns correct filename."""
        assert get_platform_config_filename("Linux64") == "delphi_config_linux64.toml"

    def test_case_insensitive(self):
        """Test platform names are case-insensitive."""
        assert get_platform_config_filename("win32") == "delphi_config_win32.toml"
        assert get_platform_config_filename("WIN64") == "delphi_config_win64.toml"
        assert get_platform_config_filename("Win64X") == "delphi_config_win64x.toml"

    def test_unknown_platform_fallback(self):
        """Test unknown platform generates reasonable filename."""
        assert get_platform_config_filename("OSX64") == "delphi_config_osx64.toml"


class TestFindConfigFileForPlatform:
    """Tests for find_config_file_for_platform function."""

    def test_env_override_takes_precedence(self, monkeypatch):
        """Test DELPHI_CONFIG env var takes precedence."""
        env_path = "/custom/path/config.toml"
        monkeypatch.setenv("DELPHI_CONFIG", env_path)

        path, source = find_config_file_for_platform(platform="Win64")
        assert path == Path(env_path)
        assert source == "env"

    def test_platform_specific_found(self, monkeypatch):
        """Test platform-specific config is found when present."""
        monkeypatch.delenv("DELPHI_CONFIG", raising=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            # Create platform-specific config
            platform_config = base_dir / "delphi_config_win64.toml"
            platform_config.write_text("# Win64 config")

            path, source = find_config_file_for_platform(platform="Win64", base_dir=base_dir)
            assert path == platform_config
            assert source == "platform"

    def test_no_platform_config_raises_error(self, monkeypatch):
        """Test raises FileNotFoundError when no platform-specific config exists."""
        monkeypatch.delenv("DELPHI_CONFIG", raising=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            # Only generic config exists, no platform-specific
            generic_config = base_dir / "delphi_config.toml"
            generic_config.write_text("# Generic config")

            with pytest.raises(FileNotFoundError, match="delphi_config_win64.toml"):
                find_config_file_for_platform(platform="Win64", base_dir=base_dir)

    def test_no_platform_raises_error(self, monkeypatch):
        """Test raises FileNotFoundError when no platform is specified."""
        monkeypatch.delenv("DELPHI_CONFIG", raising=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            with pytest.raises(FileNotFoundError, match="platform must be specified"):
                find_config_file_for_platform(platform=None, base_dir=base_dir)

    def test_missing_platform_config_raises_error(self, monkeypatch):
        """Test raises FileNotFoundError when platform config file is missing."""
        monkeypatch.delenv("DELPHI_CONFIG", raising=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            # No files exist at all

            with pytest.raises(FileNotFoundError, match="delphi_config_win64.toml"):
                find_config_file_for_platform(platform="Win64", base_dir=base_dir)


class TestPlatformConfigNames:
    """Tests for PLATFORM_CONFIG_NAMES constant."""

    def test_all_platforms_defined(self):
        """Test all expected platforms are defined."""
        expected_platforms = ["Win32", "Win64", "Win64x", "Linux64", "Android", "Android64"]
        for platform in expected_platforms:
            assert platform in PLATFORM_CONFIG_NAMES

    def test_filenames_follow_convention(self):
        """Test all filenames follow the naming convention."""
        for platform, filename in PLATFORM_CONFIG_NAMES.items():
            assert filename.startswith("delphi_config_")
            assert filename.endswith(".toml")
            assert platform.lower() in filename.lower()
