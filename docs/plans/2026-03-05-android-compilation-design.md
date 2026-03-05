# Android Compilation Support + Config Refactoring

**Date:** 2026-03-05
**Version:** v1.9.0

## Overview

Add Android (32-bit) and Android64 (64-bit) compilation support to the Delphi Build MCP Server, and refactor config loading to only support platform-specific config files (removing the generic `delphi_config.toml` fallback).

## Part 1: Config Refactoring -- Remove Generic Fallback

### Problem

`find_config_file_for_platform()` falls back to `delphi_config.toml` when no platform-specific config exists. The `load()` method then raises `FileNotFoundError` for this generic file, even though the user has platform-specific configs like `delphi_config_win32.toml`.

### Solution

- Remove `DEFAULT_CONFIG_NAME` constant and all generic fallback logic
- `find_config_file_for_platform()` raises `FileNotFoundError` with a clear message: "Expected delphi_config_android64.toml. Generate it from an IDE build log."
- `DELPHI_CONFIG` env var override is preserved as an escape hatch
- Config generators already default to platform-specific names -- no change needed

### Files Affected

- `src/config.py`
- Tests for platform config

## Part 2: Android Platform Support -- Models

### Platform Enum

Add `ANDROID = "Android"` and `ANDROID64 = "Android64"` to `Platform` enum in `models.py`.

### DelphiConfig Model

Add optional compiler path fields:
- `compiler_android: Optional[Path]` (dccaarm.exe)
- `compiler_android64: Optional[Path]` (dccaarm64.exe)

### SystemPaths Model

Add Android lib path fields:
- `lib_android_release`, `lib_android_debug`
- `lib_android64_release`, `lib_android64_debug`

### AndroidSDKConfig Model (New)

```python
class AndroidSDKConfig(BaseModel):
    compiler_rt: Optional[Path]  # --compiler-rt: path to libclang_rt.builtins-*.a
    libpaths: list[Path]         # --libpath: NDK sysroot lib paths
    linker: Optional[Path]       # --linker: path to ld.lld.exe
```

### Config Model

Add `android_sdk: AndroidSDKConfig` field parallel to existing `linux_sdk`.

### BuildLogInfo Model

Add fields:
- `android_compiler_rt: Optional[Path]`
- `android_linker: Optional[Path]`
- Reuse existing `sdk_libpaths` for both Linux and Android

## Part 3: Build Log Parser -- Android Detection

### Compiler Detection

Add `dccaarm\.exe` and `dccaarm64\.exe` to `COMPILER_PATTERNS` and `_extract_compiler_command()` regex.

### Platform Detection in `_parse_compiler_command()`

- `dccaarm.exe` with `\Android\` in paths -> `Platform.ANDROID`
- `dccaarm64.exe` with `\Android64\` in paths -> `Platform.ANDROID64`

### New Extraction Methods

- `_extract_android_compiler_rt()`: Parse `--compiler-rt:path`
- `_extract_android_linker()`: Parse `--linker:path`
- Reuse `_extract_sdk_libpaths()` for `--libpath` (works for both Linux64 and Android)

### Android-Specific Flags

From the build logs, Android compilations use:
- `--compiler-rt:path` (libclang_rt.builtins)
- `--libpath:paths` (NDK sysroot libs)
- `--linker:path` (ld.lld.exe)
- `-TX.so` (output as shared library)
- `-V -VN` (version info flags)
- `-NO` (native output directory, similar to -NU for DCU)

## Part 4: Config Loader -- Android Execution

### get_compiler_path()

- `"Android"` -> `delphi.compiler_android` or `root_path/bin/dccaarm.exe`
- `"Android64"` -> `delphi.compiler_android64` or `root_path/bin/dccaarm64.exe`

### get_all_search_paths()

Add Android/Android64 branches using the new SystemPaths fields.

### _validate_config()

Add optional warnings for missing Android compilers (non-fatal, like Linux64).

### New Methods

- `get_android_sdk_compiler_rt()` -> `Path | None`
- `get_android_sdk_libpaths()` -> `list[Path]`
- `get_android_sdk_linker()` -> `Path | None`

## Part 5: Compiler -- Android Command Building

### _build_command()

Add Android-specific block (parallel to Linux64 block):

```python
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

### _find_output_executable()

- Android apps produce `.so` files
- Add `"Android"` and `"Android64"` subdirectory search patterns

## Part 6: Config Generator -- Android TOML Generation

### _generate_toml()

Call `_generate_android_sdk_section()` when platform is Android/Android64.

### _generate_android_sdk_section() (New)

Generate `[android_sdk]` section with `compiler_rt`, `libpaths`, `linker` from build log.

### _categorize_paths()

Android NDK paths (CatalogRepository/AndroidSDK-*) are excluded from `[paths.libraries]` since they go into `[android_sdk]`.

### _generate_system_paths_section()

Detect `\lib\Android\` and `\lib\Android64\` paths for the system lib fields.

## Part 7: Testing

### New Test Files

- `test_android_buildlog.py` -- Parse all 4 Android build logs
- `test_android_compilation.py` -- Command building with mock config

### Updated Tests

- `test_platform_config.py` -- Android config filename tests
- `test_buildlog_resource.py` -- cgrc.exe extraction from Android logs

### Test Data

Use the 4 provided build log files as fixtures:
- `android32-debug.txt`, `android32-release.txt`
- `android64-debug.txt`, `android64-release.txt`

## Implementation Order

1. Config refactoring (remove generic fallback)
2. Models (Platform enum, new fields, AndroidSDKConfig)
3. BuildLogParser (Android compiler detection + extraction)
4. ConfigLoader (Android compiler paths, SDK methods)
5. Compiler (Android command building, output detection)
6. ConfigGenerator (Android TOML generation)
7. Tests
