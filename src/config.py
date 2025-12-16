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

from src.models import Config, CompilerConfig, DelphiConfig, PathsConfig, SystemPaths


class ConfigLoader:
    """Loads and validates Delphi configuration from TOML files."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize config loader.

        Args:
            config_path: Path to config file. If None, searches standard locations.
        """
        self.config_path = config_path or self._find_config_file()
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

    def _find_config_file(self) -> Path:
        """Find the config file in standard locations.

        Returns:
            Path to config file

        Searches:
            1. DELPHI_CONFIG environment variable
            2. Current working directory
            3. Script directory
        """
        # Check environment variable
        env_path = os.getenv("DELPHI_CONFIG")
        if env_path:
            return Path(env_path)

        # Check current directory
        cwd_config = Path.cwd() / "delphi_config.toml"
        if cwd_config.exists():
            return cwd_config

        # Check script directory
        script_dir = Path(__file__).parent.parent
        script_config = script_dir / "delphi_config.toml"
        if script_config.exists():
            return script_config

        # Return default path (will fail later if doesn't exist)
        return cwd_config

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

        return Config(delphi=delphi_config, paths=paths_config, compiler=compiler_config)

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
            platform: Target platform ("Win32" or "Win64")

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

        else:
            raise ValueError(f"Unknown platform: {platform}")

    def get_all_search_paths(self) -> list[Path]:
        """Get all configured search paths (system + libraries).

        Returns:
            List of all search paths
        """
        if not self.config:
            raise ValueError("Configuration not loaded")

        paths = []

        # Add system lib paths (compiled .dcu files)
        # NOTE: We do NOT add rtl/vcl source paths - the compiler knows where to find them
        system = self.config.paths.system

        if system.lib_win32_release:
            paths.append(system.lib_win32_release)
        if system.lib_win32_debug:
            paths.append(system.lib_win32_debug)
        if system.lib_win64_release:
            paths.append(system.lib_win64_release)
        if system.lib_win64_debug:
            paths.append(system.lib_win64_debug)

        # Add library paths
        paths.extend(self.config.paths.libraries.values())

        return paths
