"""Parser for Windows Registry Delphi configuration."""

import re
import winreg
from pathlib import Path
from typing import Optional

from src.models import BuildLogInfo, Platform


class RegistryParser:
    """Parses Windows Registry to extract Delphi library configuration."""

    # Registry base path for Delphi
    BDS_REGISTRY_PATH = r"Software\Embarcadero\BDS"

    def __init__(self, delphi_version: str = "23.0", platform: str = "Win32"):
        """Initialize registry parser.

        Args:
            delphi_version: Delphi version (e.g., "23.0" for Delphi 12)
            platform: Target platform ("Win32" or "Win64")
        """
        self.delphi_version = delphi_version
        self.platform = platform
        self.registry_path = f"{self.BDS_REGISTRY_PATH}\\{delphi_version}\\Library\\{platform}"

    def parse(self) -> BuildLogInfo:
        """Parse registry to extract library paths and settings.

        Returns:
            BuildLogInfo with extracted configuration

        Raises:
            FileNotFoundError: If registry key not found
            PermissionError: If cannot access registry
        """
        try:
            # Open registry key
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.registry_path, 0, winreg.KEY_READ
            )

            # Read values
            search_path = self._read_registry_value(key, "Search Path", "")
            debug_dcu_path = self._read_registry_value(key, "Debug DCU Path", "")

            # Close key
            winreg.CloseKey(key)

            # Parse paths
            search_paths = self._parse_path_string(search_path)

            # Add debug paths if present
            if debug_dcu_path:
                debug_paths = self._parse_path_string(debug_dcu_path)
                search_paths.extend(debug_paths)

            # Determine compiler path
            compiler_path = self._get_compiler_path()

            # Create BuildLogInfo
            return BuildLogInfo(
                compiler_path=compiler_path,
                delphi_version=self.delphi_version,
                platform=Platform.WIN32 if self.platform == "Win32" else Platform.WIN64,
                build_config="Release",  # Registry doesn't specify this
                search_paths=self._deduplicate_paths(search_paths),
                namespace_prefixes=[],  # Would need to read from another key
                unit_aliases={},  # Would need to read from another key
                compiler_flags=[],
            )

        except FileNotFoundError:
            raise FileNotFoundError(
                f"Registry key not found: {self.registry_path}\n"
                f"Make sure Delphi {self.delphi_version} is installed."
            )
        except PermissionError:
            raise PermissionError(f"Cannot access registry key: {self.registry_path}")

    def _read_registry_value(self, key: winreg.HKEYType, value_name: str, default: str = "") -> str:
        """Read a string value from registry key.

        Args:
            key: Open registry key
            value_name: Name of the value to read
            default: Default value if not found

        Returns:
            String value from registry
        """
        try:
            value, _ = winreg.QueryValueEx(key, value_name)
            return value if value else default
        except FileNotFoundError:
            return default

    def _parse_path_string(self, path_string: str) -> list[Path]:
        """Parse a semicolon-separated path string from registry.

        Handles environment variables like $(BDS), $(BDSLIB), etc.

        Args:
            path_string: Semicolon-separated paths with possible env vars

        Returns:
            List of Path objects
        """
        if not path_string:
            return []

        paths = []

        # Split by semicolons
        path_parts = [p.strip() for p in path_string.split(";") if p.strip()]

        for part in path_parts:
            # Expand environment variables
            expanded = self._expand_variables(part)

            if expanded:
                try:
                    paths.append(Path(expanded))
                except Exception:
                    # Skip invalid paths
                    continue

        return paths

    def _expand_variables(self, path_str: str) -> Optional[str]:
        """Expand Delphi environment variables in path.

        Common variables:
        - $(BDS) - Delphi installation directory
        - $(BDSLIB) - Library directory
        - $(BDSCOMMONDIR) - Common directory
        - $(Platform) - Platform name
        - $(LANGDIR) - Language directory

        Args:
            path_str: Path string with possible variables

        Returns:
            Expanded path string, or None if cannot expand
        """
        # Get BDS (Delphi installation) path from registry
        try:
            root_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                f"{self.BDS_REGISTRY_PATH}\\{self.delphi_version}",
                0,
                winreg.KEY_READ,
            )
            bds_path, _ = winreg.QueryValueEx(root_key, "RootDir")
            winreg.CloseKey(root_key)
        except Exception:
            bds_path = f"C:\\Program Files (x86)\\Embarcadero\\Studio\\{self.delphi_version}"

        # Define variable mappings
        variables = {
            "$(BDS)": bds_path.rstrip("\\"),
            "$(BDSLIB)": f"{bds_path.rstrip('\\\\')}\\lib",
            "$(BDSCOMMONDIR)": f"C:\\Users\\Public\\Documents\\Embarcadero\\Studio\\{self.delphi_version}",
            "$(BDSUSERDIR)": f"C:\\Users\\{self._get_username()}\\Documents\\Embarcadero\\Studio\\{self.delphi_version}",
            "$(BDSCatalogRepository)": f"C:\\Users\\{self._get_username()}\\Documents\\Embarcadero\\Studio\\{self.delphi_version}\\CatalogRepository",
            "$(BDSCatalogRepositoryAllUsers)": f"C:\\Users\\Public\\Documents\\Embarcadero\\Studio\\{self.delphi_version}\\CatalogRepository",
            "$(Platform)": self.platform,
            "$(LANGDIR)": "",  # Usually empty
        }

        # Replace variables
        expanded = path_str
        for var, value in variables.items():
            expanded = expanded.replace(var, value)

        # If still has unresolved variables, return None
        if "$(" in expanded:
            return None

        return expanded

    def _get_username(self) -> str:
        """Get current Windows username.

        Returns:
            Username string
        """
        import os

        return os.environ.get("USERNAME", "User")

    def _get_compiler_path(self) -> Path:
        """Get compiler executable path based on platform.

        Returns:
            Path to compiler executable
        """
        # Try to get from registry
        try:
            root_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                f"{self.BDS_REGISTRY_PATH}\\{self.delphi_version}",
                0,
                winreg.KEY_READ,
            )
            bds_path, _ = winreg.QueryValueEx(root_key, "RootDir")
            winreg.CloseKey(root_key)

            compiler_name = "dcc32.exe" if self.platform == "Win32" else "dcc64.exe"
            return Path(bds_path) / "bin" / compiler_name

        except Exception:
            # Fallback to default path
            compiler_name = "dcc32.exe" if self.platform == "Win32" else "dcc64.exe"
            return Path(
                f"C:\\Program Files (x86)\\Embarcadero\\Studio\\{self.delphi_version}\\bin\\{compiler_name}"
            )

    def _deduplicate_paths(self, paths: list[Path]) -> list[Path]:
        """Remove duplicate paths while preserving order.

        Args:
            paths: List of paths

        Returns:
            List of unique paths
        """
        seen = set()
        unique_paths = []

        for path in paths:
            normalized = str(path).lower()
            if normalized not in seen:
                seen.add(normalized)
                unique_paths.append(path)

        return unique_paths
