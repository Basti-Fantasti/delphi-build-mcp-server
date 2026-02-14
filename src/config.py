"""Configuration file loading and management."""

import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from src.models import Config, CompilerConfig, DelphiConfig, LinuxSDKConfig, PathsConfig, SystemPaths


# Platform-specific config file naming
PLATFORM_CONFIG_NAMES = {
    "Win32": "delphi_config_win32.toml",
    "Win64": "delphi_config_win64.toml",
    "Win64x": "delphi_config_win64x.toml",
    "Linux64": "delphi_config_linux64.toml",
    "Android": "delphi_config_android.toml",
    "Android64": "delphi_config_android64.toml",
}

DEFAULT_CONFIG_NAME = "delphi_config.toml"


def get_platform_config_filename(platform: str) -> str:
    """Get the platform-specific config filename.

    Args:
        platform: Platform name (e.g., "Win32", "Win64", "Win64x", "Linux64")

    Returns:
        Platform-specific config filename (e.g., "delphi_config_win64.toml")
    """
    # Normalize platform name
    platform_normalized = platform.lower()
    for key, filename in PLATFORM_CONFIG_NAMES.items():
        if key.lower() == platform_normalized:
            return filename
    # Fallback for unknown platforms
    return f"delphi_config_{platform_normalized}.toml"


def find_config_file_for_platform(
    platform: Optional[str] = None, base_dir: Optional[Path] = None
) -> tuple[Path, str]:
    """Find the appropriate config file for a platform.

    Search order:
    1. DELPHI_CONFIG environment variable (explicit override)
    2. Platform-specific config (e.g., delphi_config_win64.toml)
    3. Generic config (delphi_config.toml)

    Args:
        platform: Target platform (optional). If provided, searches for
            platform-specific config first.
        base_dir: Base directory to search in (defaults to MCP server directory)

    Returns:
        Tuple of (config_path, source) where source describes how file was found:
        - "env" if from DELPHI_CONFIG
        - "platform" if platform-specific file found
        - "generic" if fallback to delphi_config.toml
    """
    # Check environment variable for explicit override
    env_path = os.getenv("DELPHI_CONFIG")
    if env_path:
        return Path(env_path), "env"

    # Determine base directory
    if base_dir is None:
        # Use MCP server directory (parent of src/)
        base_dir = Path(__file__).parent.parent

    # Search for platform-specific config if platform is provided
    if platform:
        platform_filename = get_platform_config_filename(platform)
        platform_config_path = base_dir / platform_filename
        if platform_config_path.exists():
            return platform_config_path, "platform"

    # Fallback to generic config
    generic_path = base_dir / DEFAULT_CONFIG_NAME
    return generic_path, "generic"


class ConfigLoader:
    """Loads and validates Delphi configuration from TOML files."""

    def __init__(self, config_path: Optional[Path] = None, platform: Optional[str] = None):
        """Initialize config loader.

        Args:
            config_path: Path to config file. If None, searches standard locations.
            platform: Target platform for platform-specific config file search.
                If provided and no explicit config_path, will search for
                platform-specific config (e.g., delphi_config_win64.toml) first.
        """
        self.platform = platform
        self.config_source: Optional[str] = None  # "env", "platform", or "generic"

        if config_path:
            self.config_path = config_path
            self.config_source = "explicit"
        else:
            self.config_path, self.config_source = self._find_config_file()

        self.config: Optional[Config] = None

    def load(self) -> Config:
        """Load and validate the configuration file.

        Returns:
            Loaded Config object

        Raises:
            FileNotFoundError: If config file not found
            ValueError: If config file is invalid
        """
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                "Please create delphi_config.toml from the template or generate it "
                "from a build log using the generate_config_from_build_log tool."
            )

        # Load TOML file
        try:
            with open(self.config_path, "rb") as f:
                raw_config = tomllib.load(f)
        except Exception as e:
            raise ValueError(f"Invalid TOML syntax in config file: {e}")

        # Expand environment variables
        expanded_config = self._expand_env_vars(raw_config)

        # Parse into Pydantic model
        try:
            self.config = self._parse_config(expanded_config)
        except Exception as e:
            raise ValueError(f"Invalid configuration structure: {e}")

        # Validate configuration
        self._validate_config()

        return self.config

    def _find_config_file(self) -> tuple[Path, str]:
        """Find the config file using platform-aware search.

        Returns:
            Tuple of (path, source) where source is one of:
            - "env" if from DELPHI_CONFIG
            - "platform" if platform-specific file found
            - "generic" if fallback to delphi_config.toml

        Searches:
            1. DELPHI_CONFIG environment variable (explicit override)
            2. Platform-specific config (e.g., delphi_config_win64.toml)
            3. Generic config (delphi_config.toml)
        """
        return find_config_file_for_platform(platform=self.platform)

    def _expand_env_vars(self, config: dict[str, Any]) -> dict[str, Any]:
        """Recursively expand environment variables in config values.

        Supports ${VAR_NAME} syntax.

        Args:
            config: Configuration dictionary

        Returns:
            Configuration with expanded variables
        """

        def expand_value(value: Any) -> Any:
            """Expand variables in a single value."""
            if isinstance(value, str):
                # Find all ${VAR_NAME} patterns
                pattern = r"\$\{([^}]+)\}"

                def replace_var(match: re.Match) -> str:
                    var_name = match.group(1)
                    return os.getenv(var_name, match.group(0))

                return re.sub(pattern, replace_var, value)

            elif isinstance(value, dict):
                return {k: expand_value(v) for k, v in value.items()}

            elif isinstance(value, list):
                return [expand_value(item) for item in value]

            else:
                return value

        return expand_value(config)

    def _parse_config(self, raw_config: dict[str, Any]) -> Config:
        """Parse raw config dictionary into Config model.

        Args:
            raw_config: Raw configuration dictionary

        Returns:
            Parsed Config object
        """
        # Parse Delphi configuration
        delphi_config = DelphiConfig(**raw_config["delphi"])

        # Parse system paths
        system_paths = SystemPaths(**raw_config["paths"]["system"])

        # Parse library paths
        libraries = raw_config["paths"].get("libraries", {})

        # Create PathsConfig
        paths_config = PathsConfig(system=system_paths, libraries=libraries)

        # Parse compiler configuration (with defaults)
        compiler_raw = raw_config.get("compiler", {})
        compiler_config = CompilerConfig(
            namespaces=compiler_raw.get("namespaces", {"prefixes": []}),
            aliases=compiler_raw.get("aliases", {}),
            flags=compiler_raw.get("flags", {"flags": []}),
        )

        # Parse Linux SDK configuration (optional)
        linux_sdk_raw = raw_config.get("linux_sdk", {})
        linux_sdk_config = LinuxSDKConfig(
            sysroot=linux_sdk_raw.get("sysroot"),
            libpaths=linux_sdk_raw.get("libpaths", []),
        )

        return Config(
            delphi=delphi_config,
            paths=paths_config,
            compiler=compiler_config,
            linux_sdk=linux_sdk_config,
        )

    def _validate_config(self) -> None:
        """Validate the loaded configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        if not self.config:
            raise ValueError("Configuration not loaded")

        # Check if Delphi root path exists
        if not self.config.delphi.root_path.exists():
            raise ValueError(
                f"Delphi installation not found at: {self.config.delphi.root_path}\n"
                "Please verify the delphi.root_path setting in your config file."
            )

        # Check if compilers exist
        dcc32 = self.get_compiler_path("Win32")
        dcc64 = self.get_compiler_path("Win64")
        dcclinux64 = self.get_compiler_path("Linux64")

        if not dcc32.exists():
            raise ValueError(
                f"Delphi Win32 compiler not found at: {dcc32}\n"
                "Please verify your Delphi installation."
            )

        if not dcc64.exists():
            print(
                f"Warning: Delphi Win64 compiler not found at: {dcc64}\n"
                "Win64 compilation will not be available."
            )

        if not dcclinux64.exists():
            print(
                f"Warning: Delphi Linux64 compiler not found at: {dcclinux64}\n"
                "Linux64 cross-compilation will not be available."
            )

        # Warn about missing library paths (non-fatal)
        missing_libs = []
        for lib_name, lib_path in self.config.paths.libraries.items():
            if not lib_path.exists():
                missing_libs.append(f"{lib_name}: {lib_path}")

        if missing_libs:
            print(
                "Warning: Some library paths do not exist:\n"
                + "\n".join(f"  - {lib}" for lib in missing_libs)
            )

    def get_compiler_path(self, platform: str) -> Path:
        """Get the compiler executable path for a platform.

        Args:
            platform: Target platform ("Win32", "Win64", "Win64x", or "Linux64")

        Returns:
            Path to compiler executable
        """
        if not self.config:
            raise ValueError("Configuration not loaded")

        if platform == "Win32":
            if self.config.delphi.compiler_win32:
                return self.config.delphi.compiler_win32
            return self.config.delphi.root_path / "bin" / "dcc32.exe"

        elif platform == "Win64":
            if self.config.delphi.compiler_win64:
                return self.config.delphi.compiler_win64
            return self.config.delphi.root_path / "bin" / "dcc64.exe"

        elif platform == "Win64x":
            # Win64x uses the same dcc64.exe compiler as Win64
            if self.config.delphi.compiler_win64:
                return self.config.delphi.compiler_win64
            return self.config.delphi.root_path / "bin" / "dcc64.exe"

        elif platform == "Linux64":
            if self.config.delphi.compiler_linux64:
                return self.config.delphi.compiler_linux64
            return self.config.delphi.root_path / "bin" / "dcclinux64.exe"

        else:
            raise ValueError(f"Unknown platform: {platform}")

    def get_all_search_paths(self, platform: str = "Win32") -> list[Path]:
        """Get all configured search paths (system + libraries) for a platform.

        Args:
            platform: Target platform ("Win32", "Win64", "Win64x", or "Linux64")

        Returns:
            List of all search paths
        """
        if not self.config:
            raise ValueError("Configuration not loaded")

        paths = []

        # Add system lib paths (compiled .dcu files)
        # NOTE: We do NOT add rtl/vcl source paths - the compiler knows where to find them
        system = self.config.paths.system

        if platform == "Win32":
            if system.lib_win32_release:
                paths.append(system.lib_win32_release)
            if system.lib_win32_debug:
                paths.append(system.lib_win32_debug)
        elif platform == "Win64":
            if system.lib_win64_release:
                paths.append(system.lib_win64_release)
            if system.lib_win64_debug:
                paths.append(system.lib_win64_debug)
        elif platform == "Win64x":
            if system.lib_win64x_release:
                paths.append(system.lib_win64x_release)
            if system.lib_win64x_debug:
                paths.append(system.lib_win64x_debug)
        elif platform == "Linux64":
            if system.lib_linux64_release:
                paths.append(system.lib_linux64_release)
            if system.lib_linux64_debug:
                paths.append(system.lib_linux64_debug)

        # Add library paths
        paths.extend(self.config.paths.libraries.values())

        return paths

    def get_linux_sdk_sysroot(self) -> Path | None:
        """Get the Linux SDK sysroot path for cross-compilation.

        Returns:
            Path to SDK sysroot or None if not configured
        """
        if not self.config:
            raise ValueError("Configuration not loaded")

        return self.config.linux_sdk.sysroot

    def get_linux_sdk_libpaths(self) -> list[Path]:
        """Get the Linux SDK library paths for cross-compilation.

        Returns:
            List of SDK library paths
        """
        if not self.config:
            raise ValueError("Configuration not loaded")

        return self.config.linux_sdk.libpaths

    def get_resource_compiler_path(self) -> Path:
        """Get the resource compiler (cgrc.exe) path.

        Returns:
            Path to cgrc.exe
        """
        if not self.config:
            raise ValueError("Configuration not loaded")

        return self.config.delphi.root_path / "bin" / "cgrc.exe"
