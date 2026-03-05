"""Tests for Android build log parsing."""

import tempfile
from pathlib import Path

import pytest

from src.buildlog_parser import BuildLogParser


# Minimal Android64 build log (from real build output)
ANDROID64_DEBUG_LOG = """\
Erzeugen
  Erzeugen von LadaFuelMonitor.dproj (Debug, Android64)
  brcc32 Befehlszeile für "LadaFuelMonitor.vrc"
    c:\\program files (x86)\\embarcadero\\studio\\23.0\\bin\\cgrc.exe -c65001 LadaFuelMonitor.vrc -foLadaFuelMonitor.res
  dccaarm64 Befehlszeile für "LadaFuelMonitor.dpr"
    c:\\program files (x86)\\embarcadero\\studio\\23.0\\bin\\dccaarm64.exe -$O- --no-config -B -Q -TX.so \
    -I"c:\\program files (x86)\\embarcadero\\studio\\23.0\\lib\\Android64\\debug" \
    -U"c:\\program files (x86)\\embarcadero\\studio\\23.0\\lib\\Android64\\debug";"c:\\program files (x86)\\embarcadero\\studio\\23.0\\lib\\Android64\\release" \
    -NSSystem;Xml;Data;Datasnap;Web;Soap; \
    --compiler-rt:C:\\ndk\\lib\\clang\\18\\lib\\linux\\libclang_rt.builtins-aarch64-android.a \
    --libpath:C:\\ndk\\sysroot\\usr\\lib\\aarch64-linux-android\\23;C:\\ndk\\sysroot\\usr\\lib\\aarch64-linux-android \
    --linker:C:\\ndk\\bin\\ld.lld.exe \
    -V -VN -NO.\\Android64\\Debug  LadaFuelMonitor.dpr
  Erfolg
"""

# Minimal Android (32-bit) build log
ANDROID32_DEBUG_LOG = """\
Erzeugen
  Erzeugen von LadaFuelMonitor.dproj (Debug, Android)
  dccaarm Befehlszeile für "LadaFuelMonitor.dpr"
    c:\\program files (x86)\\embarcadero\\studio\\23.0\\bin\\dccaarm.exe -$O- --no-config -B -Q -TX.so \
    -I"c:\\program files (x86)\\embarcadero\\studio\\23.0\\lib\\Android\\debug" \
    -U"c:\\program files (x86)\\embarcadero\\studio\\23.0\\lib\\Android\\debug" \
    -NSSystem;Xml;Data;Datasnap;Web;Soap; \
    --compiler-rt:C:\\ndk\\lib\\clang\\18\\lib\\linux\\libclang_rt.builtins-arm-android.a \
    --libpath:C:\\ndk\\sysroot\\usr\\lib\\arm-linux-androideabi\\23;C:\\ndk\\sysroot\\usr\\lib\\arm-linux-androideabi \
    --linker:C:\\ndk\\bin\\ld.lld.exe \
    -V -VN -NO.\\Android\\Debug  LadaFuelMonitor.dpr
  Erfolg
"""


class TestAndroidBuildLogParsing:
    """Tests for Android build log parsing."""

    def _parse_log(self, content: str):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            f.flush()
            parser = BuildLogParser(Path(f.name))
            return parser.parse()

    def test_android64_platform_detected(self):
        info = self._parse_log(ANDROID64_DEBUG_LOG)
        assert info.platform.value == "Android64"

    def test_android32_platform_detected(self):
        info = self._parse_log(ANDROID32_DEBUG_LOG)
        assert info.platform.value == "Android"

    def test_android64_compiler_path(self):
        info = self._parse_log(ANDROID64_DEBUG_LOG)
        assert "dccaarm64.exe" in str(info.compiler_path)

    def test_android32_compiler_path(self):
        info = self._parse_log(ANDROID32_DEBUG_LOG)
        assert "dccaarm.exe" in str(info.compiler_path)

    def test_android64_compiler_rt_extracted(self):
        info = self._parse_log(ANDROID64_DEBUG_LOG)
        assert info.android_compiler_rt is not None
        assert "aarch64" in str(info.android_compiler_rt)

    def test_android32_compiler_rt_extracted(self):
        info = self._parse_log(ANDROID32_DEBUG_LOG)
        assert info.android_compiler_rt is not None
        assert "arm-android" in str(info.android_compiler_rt)

    def test_android64_linker_extracted(self):
        info = self._parse_log(ANDROID64_DEBUG_LOG)
        assert info.android_linker is not None
        assert "ld.lld.exe" in str(info.android_linker)

    def test_android64_sdk_libpaths_extracted(self):
        info = self._parse_log(ANDROID64_DEBUG_LOG)
        assert len(info.sdk_libpaths) > 0
        libpath_strs = [str(p) for p in info.sdk_libpaths]
        assert any("aarch64-linux-android" in s for s in libpath_strs)

    def test_android32_sdk_libpaths_extracted(self):
        info = self._parse_log(ANDROID32_DEBUG_LOG)
        assert len(info.sdk_libpaths) > 0
        libpath_strs = [str(p) for p in info.sdk_libpaths]
        assert any("arm-linux-androideabi" in s for s in libpath_strs)

    def test_android_no_config_flag(self):
        info = self._parse_log(ANDROID64_DEBUG_LOG)
        assert "--no-config" in info.compiler_flags

    def test_android_compiler_rt_not_in_flags(self):
        info = self._parse_log(ANDROID64_DEBUG_LOG)
        assert "--compiler-rt" not in info.compiler_flags

    def test_android_linker_not_in_flags(self):
        info = self._parse_log(ANDROID64_DEBUG_LOG)
        assert "--linker" not in info.compiler_flags

    def test_android_libpath_not_in_flags(self):
        info = self._parse_log(ANDROID64_DEBUG_LOG)
        assert "--libpath" not in info.compiler_flags

    def test_android64_cgrc_path_extracted(self):
        info = self._parse_log(ANDROID64_DEBUG_LOG)
        assert info.resource_compiler_path is not None
        assert "cgrc.exe" in str(info.resource_compiler_path)

    def test_android_delphi_version_detected(self):
        info = self._parse_log(ANDROID64_DEBUG_LOG)
        assert info.delphi_version == "23.0"

    def test_android64_build_config_debug(self):
        info = self._parse_log(ANDROID64_DEBUG_LOG)
        assert info.build_config == "Debug"


class TestAndroidBuildLogWithRealFiles:
    """Tests using the actual build log files provided."""

    @pytest.fixture(params=[
        "android32-debug.txt",
        "android32-release.txt",
        "android64-debug.txt",
        "android64-release.txt",
    ])
    def build_log_path(self, request):
        path = Path(__file__).parent.parent / request.param
        if not path.exists():
            pytest.skip(f"Build log file not found: {path}")
        return path

    def test_parses_without_error(self, build_log_path):
        parser = BuildLogParser(build_log_path)
        info = parser.parse()
        assert info is not None

    def test_correct_platform(self, build_log_path):
        parser = BuildLogParser(build_log_path)
        info = parser.parse()
        filename = build_log_path.name
        if "android64" in filename:
            assert info.platform.value == "Android64"
        elif "android32" in filename:
            assert info.platform.value == "Android"

    def test_android_sdk_fields_populated(self, build_log_path):
        parser = BuildLogParser(build_log_path)
        info = parser.parse()
        assert info.android_compiler_rt is not None
        assert info.android_linker is not None
        assert len(info.sdk_libpaths) > 0
