"""Tests for generic delphi_config.toml fallback for Windows targets."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import find_config_file_for_platform, ConfigLoader

# Minimal Windows config content
MINIMAL_CONFIG = """\
[delphi]
version = "23.0"
root_path = "C:/Program Files (x86)/Embarcadero/Studio/23.0"
"""

# Full config content (backwards compatibility)
FULL_WIN32_CONFIG = """\
[delphi]
version = "23.0"
root_path = "C:/Program Files (x86)/Embarcadero/Studio/23.0"

[paths.system]
rtl = "C:/Delphi/source/rtl"
vcl = "C:/Delphi/source/vcl"
lib_win32_release = "C:/Delphi/lib/Win32/release"

[compiler.namespaces]
prefixes = ["System", "Winapi"]

[compiler.flags]
flags = ["--no-config"]
"""


class TestGenericConfigFallback:
    """Test fallback to generic delphi_config.toml for Windows platforms."""

    def test_win32_falls_back_to_generic(self, tmp_path):
        generic = tmp_path / "delphi_config.toml"
        generic.write_text(MINIMAL_CONFIG)
        path, source = find_config_file_for_platform(platform="Win32", base_dir=tmp_path)
        assert path == generic
        assert source == "generic"

    def test_win64_falls_back_to_generic(self, tmp_path):
        generic = tmp_path / "delphi_config.toml"
        generic.write_text(MINIMAL_CONFIG)
        path, source = find_config_file_for_platform(platform="Win64", base_dir=tmp_path)
        assert path == generic
        assert source == "generic"

    def test_win64x_falls_back_to_generic(self, tmp_path):
        generic = tmp_path / "delphi_config.toml"
        generic.write_text(MINIMAL_CONFIG)
        path, source = find_config_file_for_platform(platform="Win64x", base_dir=tmp_path)
        assert path == generic
        assert source == "generic"

    def test_platform_specific_takes_priority(self, tmp_path):
        generic = tmp_path / "delphi_config.toml"
        generic.write_text(MINIMAL_CONFIG)
        specific = tmp_path / "delphi_config_win32.toml"
        specific.write_text(FULL_WIN32_CONFIG)
        path, source = find_config_file_for_platform(platform="Win32", base_dir=tmp_path)
        assert path == specific
        assert source == "platform"

    def test_linux64_does_not_fall_back_to_generic(self, tmp_path):
        generic = tmp_path / "delphi_config.toml"
        generic.write_text(MINIMAL_CONFIG)
        with pytest.raises(FileNotFoundError):
            find_config_file_for_platform(platform="Linux64", base_dir=tmp_path)

    def test_android64_does_not_fall_back_to_generic(self, tmp_path):
        generic = tmp_path / "delphi_config.toml"
        generic.write_text(MINIMAL_CONFIG)
        with pytest.raises(FileNotFoundError):
            find_config_file_for_platform(platform="Android64", base_dir=tmp_path)

    def test_android32_does_not_fall_back_to_generic(self, tmp_path):
        generic = tmp_path / "delphi_config.toml"
        generic.write_text(MINIMAL_CONFIG)
        with pytest.raises(FileNotFoundError):
            find_config_file_for_platform(platform="Android", base_dir=tmp_path)


class TestMinimalConfigLoading:
    """Test that minimal config (only [delphi]) loads successfully."""

    def test_load_minimal_config(self, tmp_path):
        config_file = tmp_path / "delphi_config.toml"
        config_file.write_text(MINIMAL_CONFIG)
        loader = ConfigLoader(config_path=config_file, platform="Win32")
        with patch.object(loader, '_validate_config'):
            config = loader.load()
        assert config.delphi.version == "23.0"
        assert config.paths.system.rtl is None
        assert config.paths.libraries == {}
        assert config.compiler.flags == {"flags": []}
