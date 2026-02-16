# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.8.0] - 2026-02-16

### Added

- **Version Resource Compilation**: Automatic `.res` file generation from `.dproj` version info before compilation
  - New `VersionInfo` model extracts version numbers, locale, and key-value pairs (CompanyName, FileDescription, etc.) from `.dproj` files
  - New `ResourceCompiler` class generates `.vrc` files and compiles them to `.res` using `cgrc.exe`
  - New `ResourceCompilationResult` model for tracking resource compilation outcome
  - Integrated as automatic pre-compilation step in `compile_project()` - runs before `dcc` when version info is present
  - Extracts `cgrc.exe` path from IDE build logs (German and English formats)
  - Supports MSBuild variable substitution in version info keys (`$(MSBuildProjectName)`, etc.)
  - 15 new tests covering VRC generation, resource compilation, and build log extraction

### Fixed

- **Linux64 Compilation Failure**: Fixed `F1030: Ungültige Compileranweisung: '--syslibroot'` when compiling for Linux64 platform
  - Root cause: build log parser's `_extract_compiler_flags()` captured `--syslibroot` and `--libpath` as generic compiler flags (the long flag regex matched them, but the skip list only had single-dash flags)
  - These were then written to `[compiler.flags]` in config as bare strings and passed to the compiler without their required `:path` values, before the correct `--syslibroot:{path}` was added from `[linux_sdk]`
  - Fix: added `--syslibroot` and `--libpath` to `skip_long_flags` in build log parser
  - Defense-in-depth: added same flags to `skip_flags` in `compiler.py`'s `_build_command()` to protect against stale config files
  - Regenerated `delphi_config_linux64.toml` without the offending bare flags
  - 6 new tests verifying Linux64-specific flag extraction

## [1.7.0] - 2026-02-06

### Added

- **WSL Path Conversion**: Automatic conversion of WSL-style paths (`/mnt/<drive>/...`) to Windows paths when the MCP server runs as a Windows process
  - New `src/path_utils.py` module with `convert_wsl_to_windows_path()` function
  - Applied to all path inputs across all 4 MCP tools (compile, generate config, multi-config, extend config)
  - Supports `win32` and `win64` platform detection
  - No-op on non-Windows platforms (safe for native Linux usage)

### Fixed

- **Platform-Specific Config Loading**: Fixed `ConfigLoader` not finding platform-specific config files (e.g., `delphi_config_win64.toml`)
  - Root cause: config was loaded before `.dproj` parsing determined the platform, so `ConfigLoader` was always created without a platform parameter
  - Fix: reordered `compile_project()` to parse `.dproj` first, then create `ConfigLoader(platform=...)` with the correct platform

- **Build Log Parser - German Warning Detection**: Fixed build log parser including German compiler warnings/hints as part of the compiler command
  - Root cause: `compiler_output_pattern` only matched English format (`file.pas(line,col): warning W1234:`)
  - German format (`[dcc32/dcc64/dcclinux64 Warnung] file.pas(line): W1047 message`) was not detected, causing warning text to be parsed as library paths and generating invalid TOML keys
  - Fix: extended regex to match both English and German bracketed output formats for all compiler variants (dcc32, dcc64, dcclinux64)

## [1.6.0] - 2026-02-02

### Added

- **Streamable HTTP Transport**: New `--transport streamable-http` CLI option for network access
  - Enables remote MCP clients (e.g., Claude Code in WSL-Ubuntu) to connect over TCP/IP
  - Endpoint: `http://<host>:<port>/mcp`
  - Default bind: `0.0.0.0:8080`
  - CLI flags: `--transport`, `--host`, `--port`
  - Uses MCP SDK's `StreamableHTTPSessionManager` with stateful sessions
  - No new dependencies (uvicorn, starlette already included in MCP SDK)
- **WSL Interop Support**: Use the Delphi MCP server from WSL-Ubuntu via stdio through the Windows Python binary
  - No HTTP server needed -- Claude Code manages the server lifecycle automatically
  - Verified end-to-end: WSL bash -> Windows Python -> MCP server -> Delphi compiler -> compiled .exe
- **Server CLI Options**: `--transport`, `--host`, `--port` command-line arguments
  - Default transport remains `stdio` (no breaking changes)
- **Auto-Start Script**: `start_mcp_server.bat` for launching the HTTP server at Windows logon
  - Place in Windows Startup folder (`shell:startup`) for automatic start
  - Starts minimized, configurable host/port
- **Test Scripts**: Scripts for verifying both transport modes
  - `test_stdio_wsl.sh` -- test stdio transport from WSL via Windows Python
  - `test_http_transport.sh` -- test Streamable HTTP transport (bash)
  - `test_http_transport.bat` -- test Streamable HTTP transport (Windows)
- **WSL-Ubuntu Documentation**: Setup guide with two options (stdio interop and Streamable HTTP)

## [1.5.0] - 2026-01-22

### Added

- **Platform-Specific Config Files**: Support for platform-specific configuration files with automatic fallback
  - New file naming convention: `delphi_config_{platform}.toml` (e.g., `delphi_config_win64.toml`)
  - Supported platforms: Win32, Win64, Win64x, Linux64, Android, Android64
  - Config search order:
    1. `DELPHI_CONFIG` environment variable (explicit override)
    2. `delphi_config_{platform}.toml` (platform-specific)
    3. `delphi_config.toml` (generic fallback)

- **Config Generator Enhancements**:
  - New `use_platform_specific_name` parameter for `generate_config_from_build_log`
  - Auto-generates platform-specific filename based on detected platform in build log
  - CLI flag: `-g/--generic` to generate generic config file (platform-specific is default)

- **Multi-Config Generator Enhancements**:
  - New `generate_separate_files` parameter for `generate_config_from_multiple_build_logs`
  - Generate separate platform-specific config files from multiple build logs (default behavior)
  - New `output_dir` parameter for specifying output directory
  - CLI flags: `-u/--unified` for unified config, `-d/--output-dir`

- **New Helper Functions** in `src/config.py`:
  - `get_platform_config_filename(platform)`: Get platform-specific config filename
  - `find_config_file_for_platform(platform, base_dir)`: Find config file with fallback search

- **ConfigLoader Enhancements**:
  - New `platform` parameter for platform-aware config file loading
  - New `config_source` attribute indicating how config was found ("env", "platform", "generic", "explicit")

- **Extend Configuration Tool**: New `extend_config_from_build_log` MCP tool and `ConfigExtender` class
  - Extend existing `delphi_config.toml` with settings from new build logs
  - Add support for new platforms (e.g., Win64x) without regenerating entire config
  - Intelligent path deduplication (case-insensitive comparison)
  - Preserves existing settings while adding new ones
  - Merges namespaces, aliases, and compiler flags without duplicates
  - Linux SDK settings support for cross-compilation
  - CLI support: `uv run python -m src.config_extender existing_config.toml build_log.log`
  - Options: `-o/--output` for custom output path, `--no-env-vars` to disable variable substitution

- **New Data Model**: `ExtendConfigResult` in `src/models.py`
  - `success`: Whether extension succeeded
  - `config_file_path`: Path to extended config file
  - `paths_added`: Number of new library paths added
  - `paths_skipped`: Number of duplicate paths skipped
  - `platforms_added`: List of new platforms added (e.g., ["Win64x"])
  - `settings_updated`: Dictionary of settings updated per section

- **Unit Tests**: Comprehensive test suites
  - 13 new tests for platform-specific config functionality
  - 14 test cases for `ConfigExtender` covering path normalization, duplicate detection, merging logic, and error handling

### Changed

- **Default to Platform-Specific Config Files**: Both config generators now generate platform-specific config files by default
  - `config_generator.py`: Generates `delphi_config_{platform}.toml` by default (e.g., `delphi_config_win32.toml`)
  - `multi_config_generator.py`: Generates separate platform-specific files by default
  - This simplifies the common use case of generating platform-specific configs

- **Subprocess Timeout**: Compiler execution now has a 5-minute timeout to prevent hanging

### Fixed

- **Build Log Parser - Warning Line Handling**: Fixed parser incorrectly including compiler warning/error/hint lines as part of the compiler command. The parser now properly stops collecting continuation lines when it encounters compiler output (lines matching `file.pas(line,col): warning/error/hint`)

- **Build Log Parser - Compiler Flag Extraction**: Fixed extraction of compiler flags like `-$D0`, `-$L-`, `-$Y-`. The regex pattern now correctly captures numeric values and +/- modifiers

- **USERDIR Environment Variable Expansion**: Fixed handling of corrupted `$(USERDIR)` variable from IDE build logs (appears as `½SUSERDIR%` due to encoding). The variable is now correctly expanded to the actual user directory path (`C:/Users/{username}/Documents/Embarcadero/Studio/{version}`)

- **Path Replacement with Forward Slashes**: Fixed `${USERNAME}` replacement not working for paths that had forward slashes after USERDIR expansion. Now handles both forward and backward slash variants

### Notes

- Platform-specific configs simplify multi-platform setups by separating platform-specific paths into dedicated files
- Existing unified configs continue to work unchanged (backward compatible)
- The extend config feature is useful when you already have a working configuration and want to add support for a new platform or incorporate new library paths from a recent build log
- Comments in existing TOML files will be lost during extension (due to TOML library limitations)

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
