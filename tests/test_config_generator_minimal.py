"""Tests for minimal config generation for Windows platforms."""

import tempfile
from pathlib import Path

import pytest

from src.config_generator import ConfigGenerator


# Minimal Win32 Release build log (just enough for detection)
WIN32_BUILD_LOG = """\
dcc32 Befehlszeile für "MyApp.dpr"
  c:\\program files (x86)\\embarcadero\\studio\\23.0\\bin\\dcc32.exe --no-config -B MyApp.dpr
"""


class TestMinimalWindowsConfigGeneration:
    """Test that Windows build logs produce minimal configs."""

    def test_windows_config_is_minimal(self, tmp_path):
        """Win32 build log should produce config with only [delphi] section."""
        log_file = tmp_path / "build.log"
        log_file.write_text(WIN32_BUILD_LOG)
        output_file = tmp_path / "delphi_config.toml"

        generator = ConfigGenerator(use_env_vars=False)
        result = generator.generate_from_build_log(
            build_log_path=log_file,
            output_path=output_file,
        )

        assert result.success
        content = output_file.read_text()
        # Should have [delphi] section
        assert "[delphi]" in content
        assert "root_path" in content
        # Should NOT have full paths/compiler sections
        assert "[paths.libraries]" not in content
        assert "[compiler.flags]" not in content
        assert "[compiler.namespaces]" not in content
        # Should have a comment about MSBuild
        assert "MSBuild" in content or "msbuild" in content

    def test_windows_config_default_filename(self, tmp_path):
        """Windows build logs should default to generic delphi_config.toml filename."""
        log_file = tmp_path / "build.log"
        log_file.write_text(WIN32_BUILD_LOG)

        generator = ConfigGenerator(use_env_vars=False)
        result = generator.generate_from_build_log(
            build_log_path=log_file,
            output_path=None,
            use_platform_specific_name=True,  # Should still produce generic name for Windows
        )

        assert result.success
        # For Windows, should be delphi_config.toml (not delphi_config_win32.toml)
        assert result.config_file_path.endswith("delphi_config.toml")
