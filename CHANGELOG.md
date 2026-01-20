# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-01-20

### Added

- **Win64x Platform Support**: Full support for the new LLVM-based 64-bit Windows platform (Delphi 12+)
  - `Win64x` added to `Platform` enum and `SUPPORTED_PLATFORMS`
  - Win64x uses the same `dcc64.exe` compiler as Win64
  - Platform detection from library paths (distinguishes Win64x from Win64 by checking for `/Win64x/` in paths)
  - New library path configuration: `lib_win64x_release` and `lib_win64x_debug`
  - Platform-specific output directory search (`Win64x/Debug`, `Win64x/Release`)
  - Updated config generator to extract Win64x-specific lib paths
  - Updated multi-config generator for Win64x platform normalization
  - Updated configuration template with Win64x examples

### Notes

- Win64x (Modern 64-bit Windows) is Embarcadero's new LLVM-based 64-bit compiler introduced in Delphi 12
- Win64x produces faster and more optimized code compared to the classic Win64 compiler
- Both Win64 and Win64x targets use the same `dcc64.exe` compiler executable

## [1.3.0] - 2026-01-14

### Added

- **Multi-Config Generator CLI**: Command-line interface for generating config from multiple build logs
  - Run with: `uv run python -m src.multi_config_generator build_win32.log build_win64.log`
  - Supports `-o/--output` for custom output path
  - Supports `--no-env-vars` to disable environment variable substitution

### Fixed

- **Multi-Config Generator**: Fixed several issues preventing successful compilation
  - Fixed missing `extract_config_platform_from_header` method call
  - Added required `[paths.system]` section with RTL/VCL and lib paths
  - Fixed library path naming to use unique platform-suffixed names (e.g., `jvcl_lib_win32`, `jvcl_lib_win64`)
  - Now includes both debug and release lib paths (resource files like `Controls.res` are only in release folder)

- **MSBuild Variable Substitution**: Fixed `.dproj` parser to properly substitute variables
  - `$(Platform)` and `$(Config)` are now replaced with actual values
  - Previously these were removed, causing output paths like `bin\_\` instead of `bin\Win32_Debug\`

## [1.2.0] - 2026-01-14

### Fixed

- **Package Project Support (.dpk)**: Fixed compilation of Delphi package projects
  - Now reads `<MainSource>` element from `.dproj` files to determine actual source file
  - Supports `.dpk` (package) files in addition to `.dpr` (application) files
  - Correctly identifies output as `.bpl` (Borland Package Library) for packages instead of `.exe`
  - Linux packages output `.so` extension

### Changed

- **Compiler**: Renamed internal `_get_dpr_path()` to `_get_source_path()` for clarity
- **Validation**: Now accepts `.dpr`, `.dpk`, and `.dproj` file extensions as input
- **DProjParser**: Added `_get_main_source()` method to extract `<MainSource>` element
- **DProjSettings**: Added `main_source` field to store the main source filename

## [1.1.0] - 2026-01-13

### Added

- **Linux64 Cross-Compilation Support**: Full support for compiling Delphi projects targeting Linux64
  - New `dcclinux64.exe` compiler integration for cross-compilation from Windows
  - Linux SDK configuration with `--syslibroot` and `--libpath` support
  - New `[linux_sdk]` configuration section in `delphi_config.toml`:
    - `sysroot`: SDK sysroot path for cross-compilation
    - `libpaths`: SDK library paths for linking
  - Platform-specific library paths: `lib_linux64_release` and `lib_linux64_debug`
  - Automatic detection of Linux64 executables (no file extension)
  - Platform-specific output directory search (`Linux64/Debug`, `Linux64/Release`)

- **Multi-Platform Configuration Generator**: Generate unified config from multiple build logs
  - New `MultiConfigGenerator` class in `multi_config_generator.py` module
  - Support for combining Debug/Release × Win32/Win64/Linux64 configurations
  - Hierarchical config with platform and config-specific settings
  - Auto-detection of config/platform from build log headers
  - Intelligent path categorization (common paths vs platform/config-specific)
  - New MCP tool `generate_config_from_multiple_build_logs`:
    - `build_log_paths`: Array of paths to IDE build log files (required)
    - `output_config_path`: Output file path (default: `delphi_config.toml`)
    - `use_env_vars`: Replace user paths with `${USERNAME}` (default: true)

- **Enhanced Models**:
  - `Platform` enum now includes `LINUX64`
  - `LinuxSDKConfig` model for Linux SDK settings
  - `BuildLogInfo` extended with `sdk_sysroot` and `sdk_libpaths` fields

### Changed

- **Configuration Loader**: Extended to support Linux64 platform
  - `get_compiler_path()` now returns path to `dcclinux64.exe` for Linux64
  - `get_all_search_paths()` supports Linux64 library paths
  - New `get_linux_sdk_sysroot()` method for SDK sysroot path
  - New `get_linux_sdk_libpaths()` method for SDK library paths

- **Compiler**: Enhanced for Linux64 cross-compilation
  - Automatically adds `--syslibroot` and `--libpath` flags for Linux64 builds
  - Handles Linux64 executables without `.exe` extension
  - Searches platform-specific output directories

### Notes

- Linux64 cross-compilation requires:
  - Delphi with Linux64 target support (Delphi 10.2 Tokyo or later)
  - PAServer configured on a Linux machine for remote debugging
  - Linux SDK properly installed and configured in Delphi IDE

## [1.0.0] - 2025-01-08

### Added

- Initial release of Delphi Build MCP Server
- Core compilation functionality:
  - `compile_delphi_project` MCP tool for compiling Delphi projects
  - Support for Win32 and Win64 platforms
  - Debug and Release build configurations
  - Automatic .dproj parsing for build settings
- Configuration management:
  - TOML-based configuration file (`delphi_config.toml`)
  - `generate_config_from_build_log` tool for automatic config generation
  - Environment variable expansion (`${USERNAME}`)
- Output parsing:
  - Error extraction with file, line, column information
  - Filtering of warnings and hints (errors only)
  - Support for English and German compiler messages
- Response file support for projects with 80+ library paths
- Namespace prefix and unit alias support
- Sample projects for testing (Working and Broken examples)
