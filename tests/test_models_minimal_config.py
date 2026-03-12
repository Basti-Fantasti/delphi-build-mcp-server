"""Tests for minimal config model support (MSBuild Windows targets)."""

import pytest
from pathlib import Path
from src.models import Config, DelphiConfig, SystemPaths, PathsConfig, CompilerConfig


class TestMinimalConfig:
    """Test that Config can be created with only delphi section."""

    def test_system_paths_all_optional(self):
        """SystemPaths should work with no arguments."""
        sp = SystemPaths()
        assert sp.rtl is None
        assert sp.vcl is None
        assert sp.lib_win32_release is None

    def test_paths_config_defaults_to_empty(self):
        """PathsConfig should work with no arguments."""
        pc = PathsConfig()
        assert pc.system.rtl is None
        assert pc.libraries == {}

    def test_config_with_only_delphi_section(self):
        """Config should load with only delphi section set."""
        config = Config(
            delphi=DelphiConfig(version="23.0", root_path=Path("C:/Delphi")),
        )
        assert config.delphi.version == "23.0"
        assert config.paths.system.rtl is None
        assert config.paths.libraries == {}
        assert config.compiler.flags == {"flags": []}

    def test_config_with_full_paths_still_works(self):
        """Existing full configs must continue to work."""
        config = Config(
            delphi=DelphiConfig(version="23.0", root_path=Path("C:/Delphi")),
            paths=PathsConfig(
                system=SystemPaths(
                    rtl=Path("C:/Delphi/source/rtl"),
                    vcl=Path("C:/Delphi/source/vcl"),
                    lib_win32_release=Path("C:/Delphi/lib/Win32/release"),
                ),
                libraries={"mylib": Path("C:/libs/mylib")},
            ),
        )
        assert config.paths.system.rtl == Path("C:/Delphi/source/rtl")
        assert config.paths.libraries["mylib"] == Path("C:/libs/mylib")
