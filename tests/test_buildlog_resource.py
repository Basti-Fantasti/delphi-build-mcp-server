"""Tests for resource compiler extraction from build logs."""

import tempfile
from pathlib import Path

import pytest

from src.buildlog_parser import BuildLogParser


# Minimal build log with cgrc.exe line (German format, matching real logs)
BUILD_LOG_WITH_CGRC = """\
Erzeugen
  Erzeugen von TestApp.dproj (Debug, Win32)
  brcc32 Befehlszeile für "TestApp.vrc"
    c:\\program files (x86)\\embarcadero\\studio\\23.0\\bin\\cgrc.exe -c65001 TestApp.vrc -foTestApp.res
  dcc32 Befehlszeile für "TestApp.dpr"
    c:\\program files (x86)\\embarcadero\\studio\\23.0\\bin\\dcc32.exe --no-config -B -Q TestApp.dpr
  Erfolg
"""

# English format
BUILD_LOG_WITH_CGRC_EN = """\
Build
  Building TestApp.dproj (Debug, Win32)
  brcc32 command line for "TestApp.vrc"
    c:\\program files (x86)\\embarcadero\\studio\\23.0\\bin\\cgrc.exe -c65001 TestApp.vrc -foTestApp.res
  dcc32 command line for "TestApp.dpr"
    c:\\program files (x86)\\embarcadero\\studio\\23.0\\bin\\dcc32.exe --no-config -B -Q TestApp.dpr
  Success
"""

# Build log without resource compilation
BUILD_LOG_NO_CGRC = """\
Erzeugen
  Erzeugen von TestApp.dproj (Debug, Win32)
  dcc32 Befehlszeile für "TestApp.dpr"
    c:\\program files (x86)\\embarcadero\\studio\\23.0\\bin\\dcc32.exe --no-config -B -Q TestApp.dpr
  Erfolg
"""


class TestBuildLogResourceCompiler:
    """Tests for cgrc.exe extraction from build logs."""

    def _parse_log(self, content: str) -> "BuildLogInfo":
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            f.flush()
            parser = BuildLogParser(Path(f.name))
            return parser.parse()

    def test_extracts_cgrc_path_german(self):
        """Test cgrc.exe path extracted from German build log."""
        info = self._parse_log(BUILD_LOG_WITH_CGRC)
        assert info.resource_compiler_path is not None
        assert "cgrc.exe" in str(info.resource_compiler_path)

    def test_extracts_cgrc_path_english(self):
        """Test cgrc.exe path extracted from English build log."""
        info = self._parse_log(BUILD_LOG_WITH_CGRC_EN)
        assert info.resource_compiler_path is not None
        assert "cgrc.exe" in str(info.resource_compiler_path)

    def test_no_cgrc_returns_none(self):
        """Test None when no cgrc.exe in build log."""
        info = self._parse_log(BUILD_LOG_NO_CGRC)
        assert info.resource_compiler_path is None
