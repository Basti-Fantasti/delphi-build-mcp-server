# Android Compilation + Config Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Android/Android64 compilation support and remove generic delphi_config.toml fallback.

**Architecture:** Extend Platform enum, models, BuildLogParser, ConfigLoader, and Compiler with Android-specific handling (dccaarm.exe, dccaarm64.exe, --compiler-rt, --libpath, --linker). Refactor config loading to require platform-specific config files only.

**Tech Stack:** Python 3.10+, Pydantic, pytest, TOML

**Test command:** `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`

---

### Task 1: Config Refactoring - Remove Generic Fallback

**Files:**
- Modify: `src/config.py:27` (remove DEFAULT_CONFIG_NAME)
- Modify: `src/config.py:48-88` (find_config_file_for_platform)
- Modify: `tests/test_platform_config.py`
- Modify: `src/multi_config_generator.py:10,132-133` (remove DEFAULT_CONFIG_NAME import/usage)

**Step 1: Update tests for new behavior**

In `tests/test_platform_config.py`, update the import (remove `DEFAULT_CONFIG_NAME`) and modify tests:

```python
# Remove DEFAULT_CONFIG_NAME from imports:
from src.config import (
    get_platform_config_filename,
    find_config_file_for_platform,
    PLATFORM_CONFIG_NAMES,
)

# Change test_fallback_to_generic to test_no_fallback_raises_error:
def test_no_platform_config_raises_error(self, monkeypatch):
    """Test FileNotFoundError when no platform-specific config exists."""
    monkeypatch.delenv("DELPHI_CONFIG", raising=False)

    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        # No config files exist

        with pytest.raises(FileNotFoundError, match="delphi_config_win64.toml"):
            find_config_file_for_platform(platform="Win64", base_dir=base_dir)

# Change test_no_platform_specified to test no platform raises error:
def test_no_platform_raises_error(self, monkeypatch):
    """Test error when no platform is specified and no config exists."""
    monkeypatch.delenv("DELPHI_CONFIG", raising=False)

    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)

        with pytest.raises(FileNotFoundError, match="platform must be specified"):
            find_config_file_for_platform(platform=None, base_dir=base_dir)

# Change test_returns_path_even_if_not_exists to expect error:
def test_missing_platform_config_raises_error(self, monkeypatch):
    """Test FileNotFoundError when platform-specific config doesn't exist."""
    monkeypatch.delenv("DELPHI_CONFIG", raising=False)

    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)

        with pytest.raises(FileNotFoundError, match="delphi_config_win64.toml"):
            find_config_file_for_platform(platform="Win64", base_dir=base_dir)
```

**Step 2: Run tests, verify they fail**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_platform_config.py -v`
Expected: FAIL (old behavior still returns generic path)

**Step 3: Implement config refactoring**

In `src/config.py`:

Remove line 27 (`DEFAULT_CONFIG_NAME = "delphi_config.toml"`).

Replace `find_config_file_for_platform` (lines 48-88) with:

```python
def find_config_file_for_platform(
    platform: Optional[str] = None, base_dir: Optional[Path] = None
) -> tuple[Path, str]:
    """Find the appropriate config file for a platform.

    Search order:
    1. DELPHI_CONFIG environment variable (explicit override)
    2. Platform-specific config (e.g., delphi_config_win64.toml)

    Args:
        platform: Target platform (required unless DELPHI_CONFIG is set).
        base_dir: Base directory to search in (defaults to MCP server directory)

    Returns:
        Tuple of (config_path, source) where source describes how file was found:
        - "env" if from DELPHI_CONFIG
        - "platform" if platform-specific file found

    Raises:
        FileNotFoundError: If no matching config file exists
    """
    # Check environment variable for explicit override
    env_path = os.getenv("DELPHI_CONFIG")
    if env_path:
        return Path(env_path), "env"

    # Determine base directory
    if base_dir is None:
        # Use MCP server directory (parent of src/)
        base_dir = Path(__file__).parent.parent

    if not platform:
        raise FileNotFoundError(
            "No platform specified and no DELPHI_CONFIG environment variable set. "
            "A platform must be specified to find the correct config file."
        )

    # Search for platform-specific config
    platform_filename = get_platform_config_filename(platform)
    platform_config_path = base_dir / platform_filename
    if platform_config_path.exists():
        return platform_config_path, "platform"

    raise FileNotFoundError(
        f"Configuration file not found: {platform_config_path}\n"
        f"Expected platform-specific config: {platform_filename}\n"
        "Generate it from an IDE build log using the generate_config_from_build_log tool."
    )
```

In `src/multi_config_generator.py`:
- Remove `DEFAULT_CONFIG_NAME` from the import on line 10
- On line 132-133, change `output_path = output_dir / DEFAULT_CONFIG_NAME` to `output_path = output_dir / "delphi_config.toml"` (unified mode is an explicit choice, so hardcode is fine)

**Step 4: Run tests, verify they pass**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_platform_config.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`
Expected: PASS (no regressions)

**Step 6: Commit**

```bash
git add src/config.py src/multi_config_generator.py tests/test_platform_config.py
git commit -m "Remove generic delphi_config.toml fallback, require platform-specific configs"
```

---

### Task 2: Models - Add Android Platform and SDK Config

**Files:**
- Modify: `src/models.py:10-16` (Platform enum)
- Modify: `src/models.py:106-128` (DelphiConfig - add compiler fields)
- Modify: `src/models.py:130-162` (SystemPaths - add Android lib paths)
- Modify: `src/models.py:194-216` (after LinuxSDKConfig - add AndroidSDKConfig)
- Modify: `src/models.py:219-229` (Config - add android_sdk field)
- Modify: `src/models.py:294-334` (BuildLogInfo - add Android fields)

**Step 1: Write tests for new models**

Create `tests/test_android_models.py`:

```python
"""Tests for Android platform models."""

from pathlib import Path

from src.models import (
    AndroidSDKConfig,
    Config,
    CompilerConfig,
    DelphiConfig,
    LinuxSDKConfig,
    PathsConfig,
    Platform,
    SystemPaths,
)


class TestPlatformEnum:
    """Tests for Android entries in Platform enum."""

    def test_android_platform_exists(self):
        assert Platform.ANDROID.value == "Android"

    def test_android64_platform_exists(self):
        assert Platform.ANDROID64.value == "Android64"


class TestAndroidSDKConfig:
    """Tests for AndroidSDKConfig model."""

    def test_default_values(self):
        sdk = AndroidSDKConfig()
        assert sdk.compiler_rt is None
        assert sdk.libpaths == []
        assert sdk.linker is None

    def test_with_all_values(self):
        sdk = AndroidSDKConfig(
            compiler_rt=Path("C:/ndk/lib/libclang_rt.builtins-aarch64-android.a"),
            libpaths=[Path("C:/ndk/sysroot/usr/lib/aarch64-linux-android/23")],
            linker=Path("C:/ndk/bin/ld.lld.exe"),
        )
        assert sdk.compiler_rt is not None
        assert len(sdk.libpaths) == 1
        assert sdk.linker is not None

    def test_string_paths_converted(self):
        sdk = AndroidSDKConfig(
            compiler_rt="C:/ndk/lib/libclang_rt.a",
            libpaths=["C:/ndk/lib1", "C:/ndk/lib2"],
            linker="C:/ndk/bin/ld.lld.exe",
        )
        assert isinstance(sdk.compiler_rt, Path)
        assert all(isinstance(p, Path) for p in sdk.libpaths)
        assert isinstance(sdk.linker, Path)


class TestDelphiConfigAndroidCompilers:
    """Tests for Android compiler fields in DelphiConfig."""

    def test_default_none(self):
        cfg = DelphiConfig(version="23.0", root_path=Path("C:/Embarcadero"))
        assert cfg.compiler_android is None
        assert cfg.compiler_android64 is None

    def test_can_set_compilers(self):
        cfg = DelphiConfig(
            version="23.0",
            root_path=Path("C:/Embarcadero"),
            compiler_android=Path("C:/bin/dccaarm.exe"),
            compiler_android64=Path("C:/bin/dccaarm64.exe"),
        )
        assert cfg.compiler_android == Path("C:/bin/dccaarm.exe")
        assert cfg.compiler_android64 == Path("C:/bin/dccaarm64.exe")


class TestSystemPathsAndroid:
    """Tests for Android lib path fields in SystemPaths."""

    def test_android_lib_paths_default_none(self):
        sp = SystemPaths(
            rtl=Path("C:/rtl"),
            vcl=Path("C:/vcl"),
        )
        assert sp.lib_android_release is None
        assert sp.lib_android_debug is None
        assert sp.lib_android64_release is None
        assert sp.lib_android64_debug is None

    def test_can_set_android_lib_paths(self):
        sp = SystemPaths(
            rtl=Path("C:/rtl"),
            vcl=Path("C:/vcl"),
            lib_android_release=Path("C:/lib/Android/Release"),
            lib_android_debug=Path("C:/lib/Android/Debug"),
            lib_android64_release=Path("C:/lib/Android64/Release"),
            lib_android64_debug=Path("C:/lib/Android64/Debug"),
        )
        assert sp.lib_android_release is not None
        assert sp.lib_android64_debug is not None


class TestConfigWithAndroidSDK:
    """Tests for Config model with android_sdk field."""

    def test_default_android_sdk(self):
        cfg = Config(
            delphi=DelphiConfig(version="23.0", root_path=Path("C:/Embarcadero")),
            paths=PathsConfig(system=SystemPaths(rtl=Path("C:/rtl"), vcl=Path("C:/vcl"))),
        )
        assert cfg.android_sdk is not None
        assert cfg.android_sdk.compiler_rt is None
```

**Step 2: Run tests, verify they fail**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_android_models.py -v`
Expected: FAIL (Platform.ANDROID not defined, AndroidSDKConfig not defined)

**Step 3: Implement model changes**

In `src/models.py`:

Add to Platform enum (after LINUX64):
```python
ANDROID = "Android"
ANDROID64 = "Android64"
```

Add to DelphiConfig (after compiler_linux64):
```python
compiler_android: Optional[Path] = Field(
    default=None, description="Override path to dccaarm.exe"
)
compiler_android64: Optional[Path] = Field(
    default=None, description="Override path to dccaarm64.exe"
)
```

Update the `@field_validator` decorator on DelphiConfig to include the new fields:
```python
@field_validator("root_path", "compiler_win32", "compiler_win64", "compiler_linux64", "compiler_android", "compiler_android64", mode="before")
```

Add to SystemPaths (after lib_linux64_debug):
```python
lib_android_release: Optional[Path] = Field(default=None)
lib_android_debug: Optional[Path] = Field(default=None)
lib_android64_release: Optional[Path] = Field(default=None)
lib_android64_debug: Optional[Path] = Field(default=None)
```

Update the `@field_validator` decorator on SystemPaths to include the new fields.

Add new AndroidSDKConfig class (after LinuxSDKConfig):
```python
class AndroidSDKConfig(BaseModel):
    """Android SDK/NDK configuration for cross-compilation."""

    compiler_rt: Optional[Path] = Field(
        default=None, description="Path to libclang_rt.builtins (--compiler-rt)"
    )
    libpaths: list[Path] = Field(
        default_factory=list, description="NDK sysroot library paths (--libpath)"
    )
    linker: Optional[Path] = Field(
        default=None, description="Path to ld.lld.exe linker (--linker)"
    )

    @field_validator("compiler_rt", "linker", mode="before")
    @classmethod
    def convert_paths(cls, v: str | Path | None) -> Path | None:
        if v is None or isinstance(v, Path):
            return v
        return Path(v)

    @field_validator("libpaths", mode="before")
    @classmethod
    def convert_libpaths(cls, v: list[str | Path]) -> list[Path]:
        return [Path(p) if isinstance(p, str) else p for p in v]
```

Add to Config model (after linux_sdk):
```python
android_sdk: AndroidSDKConfig = Field(
    default_factory=AndroidSDKConfig, description="Android SDK/NDK settings for cross-compilation"
)
```

Add to BuildLogInfo (after resource_compiler_path):
```python
android_compiler_rt: Optional[Path] = Field(
    default=None, description="Path to libclang_rt.builtins (--compiler-rt)"
)
android_linker: Optional[Path] = Field(
    default=None, description="Path to ld.lld.exe linker (--linker)"
)
```

Update the `@field_validator` for `compiler_path` in BuildLogInfo to also cover `android_compiler_rt` and `android_linker`:
```python
@field_validator("compiler_path", "sdk_sysroot", "resource_compiler_path", "android_compiler_rt", "android_linker", mode="before")
```

**Step 4: Run tests, verify they pass**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_android_models.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/models.py tests/test_android_models.py
git commit -m "Add Android/Android64 platform enum, SDK config, and model fields"
```

---

### Task 3: BuildLogParser - Android Compiler Detection

**Files:**
- Modify: `src/buildlog_parser.py:13-23` (COMPILER_PATTERNS)
- Modify: `src/buildlog_parser.py:85-86` (_extract_compiler_command regex)
- Modify: `src/buildlog_parser.py:138-156` (_parse_compiler_command platform detection)
- Modify: `src/buildlog_parser.py:34-49` (parse method - extract Android SDK fields)
- Add new methods: `_extract_android_compiler_rt`, `_extract_android_linker`

**Step 1: Write tests for Android build log parsing**

Create `tests/test_android_buildlog.py`:

```python
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
```

**Step 2: Run tests, verify they fail**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_android_buildlog.py -v`
Expected: FAIL (dccaarm64.exe not recognized)

**Step 3: Implement BuildLogParser changes**

In `src/buildlog_parser.py`:

Update `COMPILER_PATTERNS` (add before German patterns):
```python
COMPILER_PATTERNS = [
    r"dcc32\.exe\s+(.+)",
    r"dcc64\.exe\s+(.+)",
    r"dcclinux64\.exe\s+(.+)",
    r"dccaarm\.exe\s+(.+)",       # Android 32-bit compiler
    r"dccaarm64\.exe\s+(.+)",     # Android 64-bit compiler
    r"dcc32\s+Befehlszeile",
    r"dcc32\s+command\s+line",
    r"dcc64\s+Befehlszeile",
    r"dcc64\s+command\s+line",
    r"dcclinux64\s+Befehlszeile",
    r"dcclinux64\s+command\s+line",
    r"dccaarm\s+Befehlszeile",    # Android 32-bit German
    r"dccaarm\s+command\s+line",   # Android 32-bit English
    r"dccaarm64\s+Befehlszeile",  # Android 64-bit German
    r"dccaarm64\s+command\s+line", # Android 64-bit English
]
```

Update `_extract_compiler_command` regex (line ~86):
```python
if re.search(r"dcc32\.exe|dcc64\.exe|dcclinux64\.exe|dccaarm\.exe|dccaarm64\.exe", line, re.IGNORECASE):
```

Update compiler output pattern to include Android compilers:
```python
compiler_output_pattern = re.compile(
    r"^\s+("
    r"\S+\.\w+\(\d+(?:,\d+)?\):\s*(?:warning|error|hint|fatal)\s+[A-Z]\d+"
    r"|"
    r"\[dcc(?:32|64|linux64|aarm|aarm64)\s+(?:Warnung|Hinweis|Fehler|Fataler Fehler"
    r"|Warning|Hint|Error|Fatal Error)\]"
    r")",
    re.IGNORECASE
)
```

Update `_parse_compiler_command` regex and platform detection:
```python
compiler_match = re.search(
    r"([a-z]:\\[^\"]+\\dcc(?:32|64|linux64|aarm64|aarm)\.exe)", command, re.IGNORECASE
)
```

And the platform detection block:
```python
compiler_name = compiler_path.name.lower()
if "dccaarm64" in compiler_name:
    platform = Platform.ANDROID64
elif "dccaarm" in compiler_name:
    platform = Platform.ANDROID
elif "dcclinux64" in compiler_name:
    platform = Platform.LINUX64
elif "dcc32" in compiler_name:
    platform = Platform.WIN32
else:
    if re.search(r"[/\\]Win64x[/\\]", command, re.IGNORECASE):
        platform = Platform.WIN64X
    else:
        platform = Platform.WIN64
```

Note: `dccaarm64` must be checked before `dccaarm` since `dccaarm` is a substring.

Add new extraction methods:
```python
def _extract_android_compiler_rt(self, command: str) -> Path | None:
    """Extract --compiler-rt path from Android build command."""
    pattern = r"--compiler-rt:([^\s]+)"
    match = re.search(pattern, command, re.IGNORECASE)
    if not match:
        return None
    return Path(match.group(1).strip())

def _extract_android_linker(self, command: str) -> Path | None:
    """Extract --linker path from Android build command."""
    pattern = r"--linker:([^\s]+)"
    match = re.search(pattern, command, re.IGNORECASE)
    if not match:
        return None
    return Path(match.group(1).strip())
```

Update `_parse_compiler_command` to extract Android SDK fields (after the Linux64 section):
```python
# Extract Android SDK options (only for Android builds)
android_compiler_rt = None
android_linker = None
if platform in (Platform.ANDROID, Platform.ANDROID64):
    android_compiler_rt = self._extract_android_compiler_rt(command)
    android_linker = self._extract_android_linker(command)
    # Reuse _extract_sdk_libpaths for --libpath (works for both Linux and Android)
    sdk_libpaths = self._extract_sdk_libpaths(command)
```

Update `_extract_compiler_flags` skip list to include Android flags:
```python
skip_long_flags = ["--syslibroot", "--libpath", "--compiler-rt", "--linker"]
```

Update `parse()` method to set Android fields on the result:
```python
def parse(self) -> BuildLogInfo:
    self._read_log_file()
    resource_compiler_path = self._extract_resource_compiler_path()
    compiler_command = self._extract_compiler_command()
    info = self._parse_compiler_command(compiler_command)
    info.resource_compiler_path = resource_compiler_path
    return info
```

And in `_parse_compiler_command`, the return block becomes:
```python
return BuildLogInfo(
    compiler_path=compiler_path,
    delphi_version=delphi_version,
    platform=platform,
    build_config=build_config,
    search_paths=search_paths,
    namespace_prefixes=namespace_prefixes,
    unit_aliases=unit_aliases,
    compiler_flags=compiler_flags,
    sdk_sysroot=sdk_sysroot,
    sdk_libpaths=sdk_libpaths,
    android_compiler_rt=android_compiler_rt,
    android_linker=android_linker,
)
```

**Step 4: Run tests, verify they pass**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_android_buildlog.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/buildlog_parser.py tests/test_android_buildlog.py
git commit -m "Add Android/Android64 build log parsing with SDK field extraction"
```

---

### Task 4: ConfigLoader - Android Compiler Paths and SDK Methods

**Files:**
- Modify: `src/config.py:246-295` (_validate_config)
- Modify: `src/config.py:297-331` (get_compiler_path)
- Modify: `src/config.py:333-375` (get_all_search_paths)
- Modify: `src/config.py:203-244` (_parse_config - add android_sdk parsing)
- Add new methods: get_android_sdk_compiler_rt, get_android_sdk_libpaths, get_android_sdk_linker

**Step 1: Implement ConfigLoader changes**

In `src/config.py`:

Import the new model:
```python
from src.models import Config, CompilerConfig, DelphiConfig, LinuxSDKConfig, AndroidSDKConfig, PathsConfig, SystemPaths
```

Update `_parse_config` to add Android SDK parsing (after linux_sdk_config):
```python
# Parse Android SDK configuration (optional)
android_sdk_raw = raw_config.get("android_sdk", {})
android_sdk_config = AndroidSDKConfig(
    compiler_rt=android_sdk_raw.get("compiler_rt"),
    libpaths=android_sdk_raw.get("libpaths", []),
    linker=android_sdk_raw.get("linker"),
)

return Config(
    delphi=delphi_config,
    paths=paths_config,
    compiler=compiler_config,
    linux_sdk=linux_sdk_config,
    android_sdk=android_sdk_config,
)
```

Update `get_compiler_path` - add before the `else` clause:
```python
elif platform == "Android":
    if self.config.delphi.compiler_android:
        return self.config.delphi.compiler_android
    return self.config.delphi.root_path / "bin" / "dccaarm.exe"

elif platform == "Android64":
    if self.config.delphi.compiler_android64:
        return self.config.delphi.compiler_android64
    return self.config.delphi.root_path / "bin" / "dccaarm64.exe"
```

Update `get_all_search_paths` - add after Linux64 block:
```python
elif platform == "Android":
    if system.lib_android_release:
        paths.append(system.lib_android_release)
    if system.lib_android_debug:
        paths.append(system.lib_android_debug)
elif platform == "Android64":
    if system.lib_android64_release:
        paths.append(system.lib_android64_release)
    if system.lib_android64_debug:
        paths.append(system.lib_android64_debug)
```

Add new Android SDK accessor methods (after get_linux_sdk_libpaths):
```python
def get_android_sdk_compiler_rt(self) -> Path | None:
    """Get the Android NDK compiler-rt library path."""
    if not self.config:
        raise ValueError("Configuration not loaded")
    return self.config.android_sdk.compiler_rt

def get_android_sdk_libpaths(self) -> list[Path]:
    """Get the Android NDK library paths."""
    if not self.config:
        raise ValueError("Configuration not loaded")
    return self.config.android_sdk.libpaths

def get_android_sdk_linker(self) -> Path | None:
    """Get the Android NDK linker path."""
    if not self.config:
        raise ValueError("Configuration not loaded")
    return self.config.android_sdk.linker
```

**Step 2: Run full test suite**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/config.py
git commit -m "Add Android compiler paths and SDK accessor methods to ConfigLoader"
```

---

### Task 5: Compiler - Android Command Building and Output Detection

**Files:**
- Modify: `src/compiler.py:286-296` (_build_command - add Android block)
- Modify: `src/compiler.py:440-482` (_find_output_executable - add Android)

**Step 1: Implement compiler changes**

In `src/compiler.py`, in `_build_command`, after the Linux64 block (line ~296) add:

```python
# Add Android SDK options for cross-compilation
if platform in ("Android", "Android64"):
    compiler_rt = self.config_loader.get_android_sdk_compiler_rt()
    sdk_libpaths = self.config_loader.get_android_sdk_libpaths()
    linker = self.config_loader.get_android_sdk_linker()

    if compiler_rt:
        command.append(f"--compiler-rt:{compiler_rt}")

    if sdk_libpaths:
        libpath_str = ";".join(str(p) for p in sdk_libpaths)
        command.append(f"--libpath:{libpath_str}")

    if linker:
        command.append(f"--linker:{linker}")
```

In `_find_output_executable`, update the extension logic:
```python
if platform == "Linux64":
    exe_extension = ".so" if is_package else ""
elif platform in ("Android", "Android64"):
    exe_extension = ".so"  # Android apps always produce .so
else:
    exe_extension = ".bpl" if is_package else ".exe"
```

And add Android subdirectories:
```python
elif platform == "Android":
    subdirs = ["Android/Debug", "Android/Release"]
elif platform == "Android64":
    subdirs = ["Android64/Debug", "Android64/Release"]
```

**Step 2: Run full test suite**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/compiler.py
git commit -m "Add Android SDK flags to compiler command and Android output detection"
```

---

### Task 6: ConfigGenerator - Android TOML Generation

**Files:**
- Modify: `src/config_generator.py:89-141` (_generate_toml)
- Modify: `src/config_generator.py:429-457` (_categorize_paths)
- Modify: `src/config_generator.py:175-256` (_generate_system_paths_section)
- Add: `_generate_android_sdk_section` method

**Step 1: Implement config generator changes**

In `src/config_generator.py`:

Update `_generate_toml` to call Android SDK section (after linux_sdk section call):
```python
# Android SDK section (for cross-compilation)
lines.extend(self._generate_android_sdk_section(log_info))
```

Update `_generate_system_paths_section` to detect Android lib paths.
In the lib_paths dict, add:
```python
"lib_android_release": None,
"lib_android_debug": None,
"lib_android64_release": None,
"lib_android64_debug": None,
```

And in the detection loop, add (before the existing Win64x check):
```python
elif "\\lib\\android64\\release" in path_str:
    lib_paths["lib_android64_release"] = path
elif "\\lib\\android64\\debug" in path_str:
    lib_paths["lib_android64_debug"] = path
elif "\\lib\\android\\release" in path_str:
    lib_paths["lib_android_release"] = path
elif "\\lib\\android\\debug" in path_str:
    lib_paths["lib_android_debug"] = path
```

Note: `android64` must be checked before `android` since `android` is a substring.

Add `_generate_android_sdk_section`:
```python
def _generate_android_sdk_section(self, log_info: BuildLogInfo) -> list[str]:
    """Generate [android_sdk] section for Android cross-compilation."""
    lines = [
        "# " + "=" * 77,
        "# Android SDK/NDK Configuration (for cross-compilation)",
        "# " + "=" * 77,
        "[android_sdk]",
        "# Android NDK paths for cross-compilation to Android/Android64",
    ]

    if log_info.android_compiler_rt:
        rt_str = self._format_path(log_info.android_compiler_rt)
        lines.append(f'compiler_rt = "{rt_str}"')
    else:
        lines.append('# compiler_rt = "C:/path/to/ndk/lib/clang/18/lib/linux/libclang_rt.builtins-aarch64-android.a"')

    lines.append("")

    if log_info.sdk_libpaths and log_info.platform in (Platform.ANDROID, Platform.ANDROID64):
        lines.append("libpaths = [")
        for path in log_info.sdk_libpaths:
            path_str = self._format_path(path)
            lines.append(f'    "{path_str}",')
        lines.append("]")
    else:
        lines.append("# libpaths = []")

    lines.append("")

    if log_info.android_linker:
        linker_str = self._format_path(log_info.android_linker)
        lines.append(f'linker = "{linker_str}"')
    else:
        lines.append('# linker = "C:/path/to/ndk/bin/ld.lld.exe"')

    return lines
```

Add `Platform` to imports:
```python
from src.models import BuildLogInfo, ConfigGenerationResult, DetectedInfo, Platform
```

In `_generate_delphi_section`, add commented Android compiler examples:
```python
lines.append('# compiler_android = "C:/Program Files (x86)/Embarcadero/Studio/23.0/bin/dccaarm.exe"')
lines.append('# compiler_android64 = "C:/Program Files (x86)/Embarcadero/Studio/23.0/bin/dccaarm64.exe"')
```

**Step 2: Update multi_config_generator similarly**

In `src/multi_config_generator.py`:

Update `_generate_system_paths_section` to handle Android platform names in the lib path generation. The existing loop `for platform in sorted(platforms)` already handles this if `SystemPaths` has the right fields. Just update the `all_platforms` list:
```python
all_platforms = ["Win32", "Win64", "Win64x", "Linux64", "Android", "Android64"]
```

Also add Android-specific path detection in `_generate_all_libraries_section` where `is_platform_specific` is checked:
```python
is_platform_specific = any(p in path_lower for p in [
    "/win32", "/win64x", "/win64", "/linux64", "/android64", "/android",
    "\\win32", "\\win64x", "\\win64", "\\linux64", "\\android64", "\\android",
])
```

Note: `android64` before `android` to avoid false matches.

**Step 3: Run full test suite**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/config_generator.py src/multi_config_generator.py
git commit -m "Add Android SDK section to config generators"
```

---

### Task 7: Integration Test with Real Build Logs

**Files:**
- The 4 build log files in the project root

**Step 1: Run the full test with real build log files**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_android_buildlog.py::TestAndroidBuildLogWithRealFiles -v`
Expected: PASS (all 4 build logs parse correctly)

**Step 2: Run full test suite one final time**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`
Expected: ALL PASS

**Step 3: Final commit (if any fixups needed)**

Only commit if there were fixes needed from the integration test.
