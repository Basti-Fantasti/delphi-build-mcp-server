"""Data models for Delphi Build MCP Server."""

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Platform(str, Enum):
    """Target platform for compilation."""

    WIN32 = "Win32"
    WIN64 = "Win64"
    WIN64X = "Win64x"
    LINUX64 = "Linux64"


class BuildConfig(str, Enum):
    """Build configuration type."""

    DEBUG = "Debug"
    RELEASE = "Release"


# Supported configurations and platforms as constants
SUPPORTED_CONFIGS = ["Debug", "Release"]
SUPPORTED_PLATFORMS = ["Win32", "Win64", "Win64x", "Linux64", "Android", "Android64"]


class BuildLogEntry(BaseModel):
    """Entry representing a parsed build log file."""

    path: str = Field(description="Path to the build log file")
    config: str = Field(description="Build configuration (Debug/Release)")
    platform: str = Field(description="Target platform (Win32/Win64/etc)")
    auto_detected: bool = Field(description="Whether config/platform was auto-detected from header")


class MultiConfigGenerationResult(BaseModel):
    """Result of multi-config generation operation."""

    success: bool = Field(description="Whether generation succeeded")
    config_file_path: str = Field(description="Path to generated config file")
    build_logs_processed: list[BuildLogEntry] = Field(
        default_factory=list, description="List of processed build log entries"
    )
    statistics: dict = Field(default_factory=dict, description="Generation statistics")
    message: str = Field(description="Human-readable message about the result")


class CompilationError(BaseModel):
    """A single compilation error."""

    file: str = Field(description="Source file where error occurred")
    line: int = Field(description="Line number of the error")
    column: int = Field(description="Column number of the error")
    message: str = Field(description="Error message")
    error_code: Optional[str] = Field(default=None, description="Error code (e.g., E2003)")


class CompilationStatistics(BaseModel):
    """Statistics about the compilation process."""

    lines_compiled: int = Field(default=0, description="Number of lines compiled")
    warnings_filtered: int = Field(default=0, description="Number of warnings filtered out")
    hints_filtered: int = Field(default=0, description="Number of hints filtered out")


class CompilationResult(BaseModel):
    """Result of a compilation operation."""

    success: bool = Field(description="Whether compilation succeeded")
    exit_code: int = Field(description="Compiler exit code")
    errors: list[CompilationError] = Field(
        default_factory=list, description="List of compilation errors"
    )
    compilation_time_seconds: float = Field(description="Time taken to compile")
    output_executable: Optional[str] = Field(
        default=None, description="Path to output executable if successful"
    )
    statistics: CompilationStatistics = Field(
        default_factory=CompilationStatistics, description="Compilation statistics"
    )


class DetectedInfo(BaseModel):
    """Information detected from a build log."""

    delphi_version: str = Field(description="Detected Delphi version")
    platform: str = Field(description="Detected platform (Win32/Win64/Linux64)")
    build_config: str = Field(description="Detected build configuration (Debug/Release)")
    compiler_executable: str = Field(description="Path to compiler executable")


class ConfigGenerationResult(BaseModel):
    """Result of configuration file generation."""

    success: bool = Field(description="Whether config generation succeeded")
    config_file_path: str = Field(description="Path to generated config file")
    statistics: dict[str, int] = Field(description="Generation statistics")
    detected_info: DetectedInfo = Field(description="Information detected from build log")
    message: str = Field(description="Human-readable message about the result")


class DelphiConfig(BaseModel):
    """Delphi installation configuration."""

    version: str = Field(description="Delphi version (e.g., '23.0')")
    root_path: Path = Field(description="Delphi installation root directory")
    compiler_win32: Optional[Path] = Field(
        default=None, description="Override path to dcc32.exe"
    )
    compiler_win64: Optional[Path] = Field(
        default=None, description="Override path to dcc64.exe"
    )
    compiler_linux64: Optional[Path] = Field(
        default=None, description="Override path to dcclinux64.exe"
    )

    @field_validator("root_path", "compiler_win32", "compiler_win64", "compiler_linux64", mode="before")
    @classmethod
    def convert_to_path(cls, v: str | Path | None) -> Path | None:
        """Convert string paths to Path objects."""
        if v is None or isinstance(v, Path):
            return v
        return Path(v)


class SystemPaths(BaseModel):
    """System library paths configuration."""

    rtl: Path = Field(description="RTL source path")
    vcl: Path = Field(description="VCL source path")
    lib_win32_release: Optional[Path] = Field(default=None)
    lib_win32_debug: Optional[Path] = Field(default=None)
    lib_win64_release: Optional[Path] = Field(default=None)
    lib_win64_debug: Optional[Path] = Field(default=None)
    lib_win64x_release: Optional[Path] = Field(default=None)
    lib_win64x_debug: Optional[Path] = Field(default=None)
    lib_linux64_release: Optional[Path] = Field(default=None)
    lib_linux64_debug: Optional[Path] = Field(default=None)

    @field_validator(
        "rtl",
        "vcl",
        "lib_win32_release",
        "lib_win32_debug",
        "lib_win64_release",
        "lib_win64_debug",
        "lib_win64x_release",
        "lib_win64x_debug",
        "lib_linux64_release",
        "lib_linux64_debug",
        mode="before",
    )
    @classmethod
    def convert_to_path(cls, v: str | Path | None) -> Path | None:
        """Convert string paths to Path objects."""
        if v is None or isinstance(v, Path):
            return v
        return Path(v)


class PathsConfig(BaseModel):
    """All path configurations."""

    system: SystemPaths = Field(description="System library paths")
    libraries: dict[str, Path] = Field(
        default_factory=dict, description="Third-party library paths"
    )

    @field_validator("libraries", mode="before")
    @classmethod
    def convert_library_paths(cls, v: dict[str, str | Path]) -> dict[str, Path]:
        """Convert library path strings to Path objects."""
        return {k: Path(v) if isinstance(v, str) else v for k, v in v.items()}


class CompilerConfig(BaseModel):
    """Compiler-specific configuration."""

    namespaces: dict[str, list[str]] = Field(
        default_factory=lambda: {"prefixes": []}, description="Namespace prefixes"
    )
    aliases: dict[str, str] = Field(
        default_factory=dict, description="Unit name aliases"
    )
    flags: dict[str, list[str]] = Field(
        default_factory=lambda: {"flags": []}, description="Compiler flags from build log"
    )


class LinuxSDKConfig(BaseModel):
    """Linux SDK configuration for cross-compilation."""

    sysroot: Optional[Path] = Field(
        default=None, description="SDK sysroot path (--syslibroot)"
    )
    libpaths: list[Path] = Field(
        default_factory=list, description="SDK library paths (--libpath)"
    )

    @field_validator("sysroot", mode="before")
    @classmethod
    def convert_sysroot(cls, v: str | Path | None) -> Path | None:
        """Convert sysroot path to Path object."""
        if v is None or isinstance(v, Path):
            return v
        return Path(v)

    @field_validator("libpaths", mode="before")
    @classmethod
    def convert_libpaths(cls, v: list[str | Path]) -> list[Path]:
        """Convert libpaths to Path objects."""
        return [Path(p) if isinstance(p, str) else p for p in v]


class Config(BaseModel):
    """Complete configuration model."""

    delphi: DelphiConfig = Field(description="Delphi installation settings")
    paths: PathsConfig = Field(description="Library paths")
    compiler: CompilerConfig = Field(
        default_factory=CompilerConfig, description="Compiler settings"
    )
    linux_sdk: LinuxSDKConfig = Field(
        default_factory=LinuxSDKConfig, description="Linux SDK settings for cross-compilation"
    )


class DProjSettings(BaseModel):
    """Settings extracted from a .dproj file."""

    active_config: str = Field(description="Active build configuration")
    active_platform: str = Field(description="Active platform")
    main_source: Optional[str] = Field(
        default=None, description="Main source file from <MainSource> element (e.g., 'MyApp.dpr' or 'MyPackage.dpk')"
    )
    compiler_flags: list[str] = Field(
        default_factory=list, description="Compiler command-line flags"
    )
    defines: list[str] = Field(default_factory=list, description="Conditional defines")
    unit_search_paths: list[Path] = Field(
        default_factory=list, description="Unit search paths"
    )
    include_paths: list[Path] = Field(
        default_factory=list, description="Include file paths"
    )
    resource_paths: list[Path] = Field(
        default_factory=list, description="Resource file paths"
    )
    output_dir: Optional[Path] = Field(default=None, description="Output directory for EXE")
    dcu_output_dir: Optional[Path] = Field(
        default=None, description="Output directory for DCU files"
    )
    namespace_prefixes: list[str] = Field(
        default_factory=list, description="Namespace prefixes from project"
    )
    version_info: Optional["VersionInfo"] = Field(
        default=None, description="Version information for resource compilation"
    )

    @field_validator(
        "unit_search_paths", "include_paths", "resource_paths", "output_dir", "dcu_output_dir",
        mode="before",
    )
    @classmethod
    def convert_paths(cls, v: list[str | Path] | str | Path | None) -> list[Path] | Path | None:
        """Convert path strings to Path objects."""
        if v is None:
            return None
        if isinstance(v, (str, Path)):
            return Path(v) if isinstance(v, str) else v
        return [Path(p) if isinstance(p, str) else p for p in v]


class ExtendConfigResult(BaseModel):
    """Result of configuration extension operation."""

    success: bool = Field(description="Whether extension succeeded")
    config_file_path: str = Field(description="Path to extended config file")
    paths_added: int = Field(description="Number of new library paths added")
    paths_skipped: int = Field(description="Number of duplicate paths skipped")
    platforms_added: list[str] = Field(
        default_factory=list, description="New platforms added (e.g., ['Win64x'])"
    )
    settings_updated: dict[str, int] = Field(
        default_factory=dict, description="Count of settings updated per section"
    )
    message: str = Field(description="Human-readable result message")


class BuildLogInfo(BaseModel):
    """Information extracted from a build log."""

    compiler_path: Path = Field(description="Path to compiler executable")
    delphi_version: str = Field(description="Detected Delphi version")
    platform: Platform = Field(description="Target platform")
    build_config: str = Field(description="Build configuration")
    search_paths: list[Path] = Field(description="All detected search paths")
    namespace_prefixes: list[str] = Field(
        default_factory=list, description="Namespace prefixes"
    )
    unit_aliases: dict[str, str] = Field(
        default_factory=dict, description="Unit aliases"
    )
    compiler_flags: list[str] = Field(
        default_factory=list, description="Additional compiler flags"
    )
    # Linux64 SDK fields
    sdk_sysroot: Optional[Path] = Field(
        default=None, description="Linux SDK sysroot path (--syslibroot)"
    )
    sdk_libpaths: list[Path] = Field(
        default_factory=list, description="Linux SDK library paths (--libpath)"
    )
    resource_compiler_path: Optional[Path] = Field(
        default=None, description="Path to resource compiler (cgrc.exe)"
    )

    @field_validator("compiler_path", "sdk_sysroot", "resource_compiler_path", mode="before")
    @classmethod
    def convert_compiler_path(cls, v: str | Path | None) -> Path | None:
        """Convert compiler path to Path object."""
        if v is None:
            return None
        return Path(v) if isinstance(v, str) else v

    @field_validator("search_paths", "sdk_libpaths", mode="before")
    @classmethod
    def convert_search_paths(cls, v: list[str | Path]) -> list[Path]:
        """Convert search paths to Path objects."""
        return [Path(p) if isinstance(p, str) else p for p in v]


class VersionInfo(BaseModel):
    """Version information extracted from .dproj for resource compilation."""

    major: int = Field(default=0, description="Major version number")
    minor: int = Field(default=0, description="Minor version number")
    release: int = Field(default=0, description="Release version number")
    build: int = Field(default=0, description="Build version number")
    locale: int = Field(default=1033, description="Locale ID (default: 1033 = US English)")
    keys: dict[str, str] = Field(
        default_factory=dict,
        description="Version info key-value pairs (CompanyName, FileDescription, etc.)",
    )

    @property
    def file_version_string(self) -> str:
        """Return version as dotted string (e.g., '1.2.3.4')."""
        return f"{self.major}.{self.minor}.{self.release}.{self.build}"


class ResourceCompilationResult(BaseModel):
    """Result of resource compilation step."""

    success: bool = Field(description="Whether resource compilation succeeded")
    res_file: Optional[str] = Field(
        default=None, description="Path to generated .res file if successful"
    )
    error_output: Optional[str] = Field(
        default=None, description="Error output from resource compiler"
    )
