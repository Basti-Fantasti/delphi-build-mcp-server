"""Parser for Delphi .dproj (MSBuild) project files."""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from src.models import DProjSettings


class DProjParser:
    """Parses .dproj files to extract build settings and compiler configuration."""

    # MSBuild namespace used in .dproj files
    MSBUILD_NS = {"ms": "http://schemas.microsoft.com/developer/msbuild/2003"}

    # Mapping of DCC properties to compiler flags
    DCC_FLAG_MAPPING = {
        "DCC_Optimize": lambda v: "-$O+" if v == "true" else "-$O-",
        "DCC_DebugInfoInExe": lambda v: "-$D+" if v == "true" else "-$D-",
        "DCC_LocalDebugSymbols": lambda v: "-$L+" if v == "true" else "-$L-",
        "DCC_SymbolReferenceInfo": lambda v: "-$Y+" if v == "true" else "-$Y-",
        "DCC_AssertionsRuntime": lambda v: "-$C+" if v == "true" else "-$C-",
        "DCC_IOChecking": lambda v: "-$I+" if v == "true" else "-$I-",
        "DCC_RangeChecking": lambda v: "-$R+" if v == "true" else "-$R-",
        "DCC_OverflowChecking": lambda v: "-$Q+" if v == "true" else "-$Q-",
        "DCC_WriteableConst": lambda v: "-$J+" if v == "true" else "-$J-",
    }

    def __init__(self, dproj_path: Path):
        """Initialize parser with .dproj file path.

        Args:
            dproj_path: Path to the .dproj file
        """
        self.dproj_path = dproj_path
        self.project_dir = dproj_path.parent
        self.tree: Optional[ET.ElementTree] = None
        self.root: Optional[ET.Element] = None

    def parse(
        self, override_config: Optional[str] = None, override_platform: Optional[str] = None
    ) -> DProjSettings:
        """Parse the .dproj file and extract settings.

        Args:
            override_config: Override the active configuration (e.g., "Debug", "Release")
            override_platform: Override the active platform (e.g., "Win32", "Win64")

        Returns:
            DProjSettings with extracted configuration

        Raises:
            FileNotFoundError: If .dproj file doesn't exist
            ValueError: If .dproj file is invalid
        """
        self._load_project_file()

        # Get active configuration and platform
        active_config = override_config or self._get_active_configuration()
        active_platform = override_platform or self._get_active_platform()

        # Extract settings for this configuration/platform combination
        settings = self._extract_settings(active_config, active_platform)

        return settings

    def _load_project_file(self) -> None:
        """Load and parse the .dproj XML file."""
        if not self.dproj_path.exists():
            raise FileNotFoundError(f"Project file not found: {self.dproj_path}")

        try:
            self.tree = ET.parse(self.dproj_path)
            self.root = self.tree.getroot()
        except ET.ParseError as e:
            raise ValueError(f"Invalid .dproj file: {e}")

    def _get_active_configuration(self) -> str:
        """Get the active build configuration from the project.

        Returns:
            Active configuration name (e.g., "Debug", "Release")
        """
        # Look for PropertyGroup with Configuration element
        for prop_group in self.root.findall(".//ms:PropertyGroup", self.MSBUILD_NS):
            config_elem = prop_group.find("ms:Configuration", self.MSBUILD_NS)
            if config_elem is not None and config_elem.text:
                # Remove the condition check - just use the default value
                condition = prop_group.get("Condition", "")
                if "'$(Configuration)'==''" in condition or not condition:
                    return config_elem.text

        # Default to Debug if not found
        return "Debug"

    def _get_active_platform(self) -> str:
        """Get the active platform from the project.

        Returns:
            Active platform (e.g., "Win32", "Win64")
        """
        # Look for PropertyGroup with Platform element
        for prop_group in self.root.findall(".//ms:PropertyGroup", self.MSBUILD_NS):
            platform_elem = prop_group.find("ms:Platform", self.MSBUILD_NS)
            if platform_elem is not None and platform_elem.text:
                condition = prop_group.get("Condition", "")
                if "'$(Platform)'==''" in condition or not condition:
                    return platform_elem.text

        # Default to Win32 if not found
        return "Win32"

    def _get_main_source(self) -> Optional[str]:
        """Get the main source file from the project.

        This reads the <MainSource> element which specifies the actual source
        file to compile (e.g., 'MyApp.dpr' for applications or 'MyPackage.dpk'
        for packages).

        Returns:
            Main source filename (e.g., "MyApp.dpr" or "MyPackage.dpk"), or None if not found
        """
        # Look for MainSource element in any PropertyGroup
        for prop_group in self.root.findall(".//ms:PropertyGroup", self.MSBUILD_NS):
            main_source_elem = prop_group.find("ms:MainSource", self.MSBUILD_NS)
            if main_source_elem is not None and main_source_elem.text:
                return main_source_elem.text.strip()

        return None

    def _extract_settings(self, config: str, platform: str) -> DProjSettings:
        """Extract all settings for the specified configuration and platform.

        Args:
            config: Build configuration (e.g., "Debug", "Release")
            platform: Target platform (e.g., "Win32", "Win64")

        Returns:
            DProjSettings with extracted configuration
        """
        # Extract MainSource element (the actual source file to compile)
        main_source = self._get_main_source()

        settings = DProjSettings(active_config=config, active_platform=platform, main_source=main_source)

        # Build a map from config/platform names to their internal Cfg keys
        config_key_map = self._build_config_key_map()

        # Find all PropertyGroups that match this config/platform
        # MSBuild uses a hierarchy: Base -> Base_Platform -> Cfg_X -> Cfg_X_Platform
        property_groups = []

        # Get the config key (e.g., "Cfg_1" for "Debug", "Cfg_2" for "Release")
        config_key = config_key_map.get(config, "Cfg_1")

        # Conditions to match, in order of specificity
        # The conditions use internal variables like $(Base), $(Cfg_1), etc.
        matching_conditions = [
            "'$(Base)'!=''",                              # Base settings
            f"'$(Base_{platform})'!=''",                  # Platform-specific base
            f"'$({config_key})'!=''",                     # Config-specific (Debug/Release)
            f"'$({config_key}_{platform})'!=''",          # Config + Platform specific
        ]

        # Also check for alternative condition formats
        alt_conditions = [
            f"'$(Config)'=='{config}'",
            f"'$(Platform)'=='{platform}'",
            f"'{config}|{platform}'",
        ]

        for prop_group in self.root.findall(".//ms:PropertyGroup", self.MSBUILD_NS):
            condition = prop_group.get("Condition", "")

            # Include if no condition (global settings)
            if not condition:
                property_groups.append(prop_group)
                continue

            # Check if condition matches any of our target conditions
            for match_cond in matching_conditions:
                if match_cond in condition:
                    property_groups.append(prop_group)
                    break
            else:
                # Also check alternative conditions
                for alt_cond in alt_conditions:
                    if alt_cond in condition:
                        property_groups.append(prop_group)
                        break

        # Process each PropertyGroup and merge settings
        for prop_group in property_groups:
            self._process_property_group(prop_group, settings)

        return settings

    def _build_config_key_map(self) -> dict[str, str]:
        """Build a map from configuration names to their internal keys.

        Returns:
            Dictionary mapping config names (e.g., "Debug") to keys (e.g., "Cfg_1")
        """
        config_map = {}

        # Look for BuildConfiguration items that define the mapping
        for build_config in self.root.findall(".//ms:BuildConfiguration", self.MSBUILD_NS):
            include_name = build_config.get("Include", "")
            key_elem = build_config.find("ms:Key", self.MSBUILD_NS)
            if include_name and key_elem is not None and key_elem.text:
                config_map[include_name] = key_elem.text

        # Default mappings if not found
        if "Debug" not in config_map:
            config_map["Debug"] = "Cfg_1"
        if "Release" not in config_map:
            config_map["Release"] = "Cfg_2"

        return config_map

    def _process_property_group(self, prop_group: ET.Element, settings: DProjSettings) -> None:
        """Process a PropertyGroup element and update settings.

        Args:
            prop_group: PropertyGroup XML element
            settings: DProjSettings to update
        """
        for elem in prop_group:
            tag_name = elem.tag.replace("{" + self.MSBUILD_NS["ms"] + "}", "")
            value = elem.text or ""

            # Process different DCC properties
            # Use extend to accumulate values from multiple PropertyGroups
            if tag_name == "DCC_Define":
                new_defines = self._parse_semicolon_list(value)
                for d in new_defines:
                    if d not in settings.defines:
                        settings.defines.append(d)

            elif tag_name == "DCC_UnitSearchPath":
                new_paths = self._parse_path_list(value)
                for p in new_paths:
                    if p not in settings.unit_search_paths:
                        settings.unit_search_paths.append(p)

            elif tag_name == "DCC_IncludePath":
                new_paths = self._parse_path_list(value)
                for p in new_paths:
                    if p not in settings.include_paths:
                        settings.include_paths.append(p)

            elif tag_name == "DCC_ResourcePath":
                new_paths = self._parse_path_list(value)
                for p in new_paths:
                    if p not in settings.resource_paths:
                        settings.resource_paths.append(p)

            elif tag_name == "DCC_ExeOutput":
                settings.output_dir = self._resolve_path(value)

            elif tag_name == "DCC_DcuOutput":
                settings.dcu_output_dir = self._resolve_path(value)

            elif tag_name == "DCC_Namespace":
                new_namespaces = self._parse_semicolon_list(value)
                for ns in new_namespaces:
                    if ns not in settings.namespace_prefixes:
                        settings.namespace_prefixes.append(ns)

            # Handle compiler flags
            elif tag_name in self.DCC_FLAG_MAPPING:
                flag = self.DCC_FLAG_MAPPING[tag_name](value.lower())
                if flag not in settings.compiler_flags:
                    settings.compiler_flags.append(flag)

    def _parse_semicolon_list(self, value: str) -> list[str]:
        """Parse a semicolon-separated list.

        Args:
            value: Semicolon-separated string

        Returns:
            List of items
        """
        if not value:
            return []
        items = []
        for item in value.split(";"):
            item = item.strip()
            # Skip empty items and MSBuild variable references
            if item and not (item.startswith("$(") and item.endswith(")")):
                items.append(item)
        return items

    def _parse_path_list(self, value: str) -> list[Path]:
        """Parse a semicolon-separated list of paths.

        Args:
            value: Semicolon-separated path string

        Returns:
            List of resolved Path objects
        """
        if not value:
            return []

        paths = []
        for path_str in value.split(";"):
            path_str = path_str.strip()
            if path_str:
                # Resolve MSBuild variables and relative paths
                resolved = self._resolve_path(path_str)
                if resolved:
                    paths.append(resolved)

        return paths

    def _resolve_path(self, path_str: str) -> Optional[Path]:
        """Resolve a path string, handling MSBuild variables and relative paths.

        Args:
            path_str: Path string that may contain MSBuild variables

        Returns:
            Resolved Path object, or None if path is empty
        """
        if not path_str:
            return None

        # Remove MSBuild variables for now (we can enhance this later)
        # Common variables: $(DCC_UnitSearchPath), $(Platform), $(Config), etc.
        path_str = path_str.strip()

        # Skip if it's just a variable reference
        if path_str.startswith("$(") and path_str.endswith(")"):
            return None

        # Remove variable references from the path
        import re

        path_str = re.sub(r"\$\([^)]+\)", "", path_str)
        path_str = path_str.strip()

        if not path_str:
            return None

        # Convert to Path and resolve relative to project directory
        path = Path(path_str)

        if not path.is_absolute():
            path = (self.project_dir / path).resolve()

        return path
