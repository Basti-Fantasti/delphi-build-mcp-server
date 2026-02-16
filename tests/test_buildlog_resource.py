"""Tests for build log parsing: resource compiler extraction and Linux64 flags."""

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


# Linux64 build log with --syslibroot and --libpath flags
BUILD_LOG_LINUX64 = """\
Erzeugen von CRAHub.dproj (Debug, Linux64)
dcclinux64 Befehlszeile für "CRAHub.dpr"
  c:\\program files (x86)\\embarcadero\\studio\\23.0\\bin\\dcclinux64.exe -$O- -$R+ -$Q+ --no-config -B -Q \
  -I"c:\\program files (x86)\\embarcadero\\studio\\23.0\\lib\\Linux64\\debug" \
  -U"c:\\program files (x86)\\embarcadero\\studio\\23.0\\lib\\Linux64\\debug";"c:\\program files (x86)\\embarcadero\\studio\\23.0\\lib\\Linux64\\release" \
  -NSSystem;Xml;Data;Datasnap;Web;Soap \
  --syslibroot:C:\\Users\\Test\\Documents\\Embarcadero\\Studio\\SDKs\\ubuntu22.04.sdk \
  --libpath:C:\\Users\\Test\\Documents\\Embarcadero\\Studio\\SDKs\\ubuntu22.04.sdk\\usr\\lib\\gcc\\x86_64-linux-gnu\\11;C:\\Users\\Test\\Documents\\Embarcadero\\Studio\\SDKs\\ubuntu22.04.sdk\\lib64 \
  -NHC:\\Users\\Public\\Documents\\Embarcadero\\Studio\\23.0\\hpp\\Linux64 \
  CRAHub.dpr
Erfolg
"""


class TestBuildLogLinux64Flags:
    """Tests for Linux64-specific flag extraction from build logs."""

    def _parse_log(self, content: str) -> "BuildLogInfo":
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            f.flush()
            parser = BuildLogParser(Path(f.name))
            return parser.parse()

    def test_syslibroot_not_in_compiler_flags(self):
        """--syslibroot must not appear in compiler_flags (extracted separately as SDK option)."""
        info = self._parse_log(BUILD_LOG_LINUX64)
        assert "--syslibroot" not in info.compiler_flags

    def test_libpath_not_in_compiler_flags(self):
        """--libpath must not appear in compiler_flags (extracted separately as SDK option)."""
        info = self._parse_log(BUILD_LOG_LINUX64)
        assert "--libpath" not in info.compiler_flags

    def test_no_config_still_in_flags(self):
        """--no-config should still be extracted as a compiler flag."""
        info = self._parse_log(BUILD_LOG_LINUX64)
        assert "--no-config" in info.compiler_flags

    def test_sdk_sysroot_extracted(self):
        """SDK sysroot should be extracted from --syslibroot."""
        info = self._parse_log(BUILD_LOG_LINUX64)
        assert info.sdk_sysroot is not None
        assert "ubuntu22.04.sdk" in str(info.sdk_sysroot)

    def test_sdk_libpaths_extracted(self):
        """SDK library paths should be extracted from --libpath."""
        info = self._parse_log(BUILD_LOG_LINUX64)
        assert len(info.sdk_libpaths) > 0
        libpath_strs = [str(p) for p in info.sdk_libpaths]
        assert any("x86_64-linux-gnu" in s for s in libpath_strs)

    def test_platform_detected_as_linux64(self):
        """Platform should be detected as Linux64."""
        info = self._parse_log(BUILD_LOG_LINUX64)
        assert info.platform.value == "Linux64"
