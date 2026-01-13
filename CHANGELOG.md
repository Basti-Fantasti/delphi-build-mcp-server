# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
