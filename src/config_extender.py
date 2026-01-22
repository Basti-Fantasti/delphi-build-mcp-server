"""Extend existing delphi_config.toml with settings from a new build log."""

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from src.buildlog_parser import BuildLogParser
from src.models import BuildLogInfo, ExtendConfigResult


@dataclass
class MergeStatistics:
    """Statistics from the merge operation."""

    paths_added: int = 0
    paths_skipped: int = 0
    platforms_added: list[str] = field(default_factory=list)
    settings_updated: dict[str, int] = field(default_factory=dict)


class ConfigExtender:
    """Extends existing TOML configuration with new build log settings."""

    def __init__(self, use_env_vars: bool = True):
        """Initialize config extender.

        Args:
            use_env_vars: Whether to replace paths with environment variables
        """
        self.use_env_vars = use_env_vars

    def extend_from_build_log(
        self,
        existing_config_path: Path,
        build_log_path: Path,
        output_path: Optional[Path] = None,
    ) -> ExtendConfigResult:
        """Extend existing config with settings from build log.

        Args:
            existing_config_path: Path to existing delphi_config.toml
            build_log_path: Path to IDE build log file
            output_path: Optional output path (default: overwrite existing)

        Returns:
            ExtendConfigResult with merge statistics

        Raises:
            FileNotFoundError: If existing config or build log not found
            ValueError: If config is invalid or build log cannot be parsed
        """
        # Validate inputs
        if not existing_config_path.exists():
            raise FileNotFoundError(f"Existing config not found: {existing_config_path}")
        if not build_log_path.exists():
            raise FileNotFoundError(f"Build log not found: {build_log_path}")

        # Set output path
        if output_path is None:
            output_path = existing_config_path

        # Load existing config
        existing_config = self._load_existing_config(existing_config_path)

        # Parse new build log
        parser = BuildLogParser(build_log_path)
        new_log_info = parser.parse()

        # Detect new platforms being added
        platforms_added = self._detect_new_platforms(existing_config, new_log_info)

        # Merge configs
        merged_config, stats = self._merge_configs(existing_config, new_log_info)
        stats.platforms_added = platforms_added

        # Generate TOML output
        toml_content = self._generate_toml(merged_config)

        # Write to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(toml_content)

        # Build result message
        message_parts = []
        if stats.platforms_added:
            message_parts.append(f"Added platform(s): {', '.join(stats.platforms_added)}")
        message_parts.append(f"Added {stats.paths_added} new paths")
        message_parts.append(f"Skipped {stats.paths_skipped} duplicate paths")

        return ExtendConfigResult(
            success=True,
            config_file_path=str(output_path.absolute()),
            paths_added=stats.paths_added,
            paths_skipped=stats.paths_skipped,
            platforms_added=stats.platforms_added,
            settings_updated=stats.settings_updated,
            message=". ".join(message_parts),
        )

    def _load_existing_config(self, config_path: Path) -> dict:
        """Load and parse existing TOML configuration.

        Args:
            config_path: Path to TOML config file

        Returns:
            Parsed config dictionary

        Raises:
            ValueError: If TOML cannot be parsed
        """
        try:
            with open(config_path, "rb") as f:
                return tomllib.load(f)
        except Exception as e:
            raise ValueError(f"Invalid TOML in existing config: {e}")

    def _detect_new_platforms(
        self, existing_config: dict, new_log_info: BuildLogInfo
    ) -> list[str]:
        """Detect which platforms are being added.

        Args:
            existing_config: Existing configuration dictionary
            new_log_info: New build log information

        Returns:
            List of new platform names
        """
        new_platform = new_log_info.platform.value
        existing_system = existing_config.get("paths", {}).get("system", {})

        # Check if we have lib paths for this platform
        platform_lower = new_platform.lower()
        release_key = f"lib_{platform_lower}_release"
        debug_key = f"lib_{platform_lower}_debug"

        has_release = release_key in existing_system
        has_debug = debug_key in existing_system

        if not has_release and not has_debug:
            return [new_platform]
        return []

    def _merge_configs(
        self, existing: dict, new_log_info: BuildLogInfo
    ) -> tuple[dict, MergeStatistics]:
        """Merge new build log info into existing config.

        Args:
            existing: Existing configuration dictionary
            new_log_info: New build log information

        Returns:
            Tuple of (merged_config, statistics)
        """
        stats = MergeStatistics()
        merged = self._deep_copy_dict(existing)

        # Ensure required sections exist
        if "paths" not in merged:
            merged["paths"] = {}
        if "system" not in merged["paths"]:
            merged["paths"]["system"] = {}
        if "libraries" not in merged["paths"]:
            merged["paths"]["libraries"] = {}
        if "compiler" not in merged:
            merged["compiler"] = {}
        if "namespaces" not in merged["compiler"]:
            merged["compiler"]["namespaces"] = {}
        if "aliases" not in merged["compiler"]:
            merged["compiler"]["aliases"] = {}
        if "flags" not in merged["compiler"]:
            merged["compiler"]["flags"] = {}

        # Merge system paths
        system_added, system_skipped = self._merge_system_paths(
            merged["paths"]["system"], new_log_info
        )
        stats.paths_added += system_added
        stats.paths_skipped += system_skipped
        if system_added > 0:
            stats.settings_updated["paths.system"] = system_added

        # Categorize paths from new build log
        compiler_root = new_log_info.compiler_path.parent.parent
        compiler_root_str = str(compiler_root).lower()

        library_paths = []
        for path in new_log_info.search_paths:
            path_str = str(path).lower()
            if compiler_root_str not in path_str:
                library_paths.append(path)

        # Merge library paths
        lib_added, lib_skipped = self._merge_library_paths(
            merged["paths"]["libraries"], library_paths
        )
        stats.paths_added += lib_added
        stats.paths_skipped += lib_skipped
        if lib_added > 0:
            stats.settings_updated["paths.libraries"] = lib_added

        # Merge namespaces
        ns_added = self._merge_namespaces(
            merged["compiler"]["namespaces"], new_log_info.namespace_prefixes
        )
        if ns_added > 0:
            stats.settings_updated["compiler.namespaces"] = ns_added

        # Merge aliases
        alias_added = self._merge_aliases(
            merged["compiler"]["aliases"], new_log_info.unit_aliases
        )
        if alias_added > 0:
            stats.settings_updated["compiler.aliases"] = alias_added

        # Merge compiler flags
        flags_added = self._merge_flags(
            merged["compiler"]["flags"], new_log_info.compiler_flags
        )
        if flags_added > 0:
            stats.settings_updated["compiler.flags"] = flags_added

        # Handle Linux SDK if present
        if new_log_info.sdk_sysroot or new_log_info.sdk_libpaths:
            if "linux_sdk" not in merged:
                merged["linux_sdk"] = {}
            sdk_added = self._merge_linux_sdk(merged["linux_sdk"], new_log_info)
            if sdk_added > 0:
                stats.settings_updated["linux_sdk"] = sdk_added

        return merged, stats

    def _deep_copy_dict(self, d: dict) -> dict:
        """Create a deep copy of a dictionary."""
        result = {}
        for key, value in d.items():
            if isinstance(value, dict):
                result[key] = self._deep_copy_dict(value)
            elif isinstance(value, list):
                result[key] = value.copy()
            else:
                result[key] = value
        return result

    def _merge_system_paths(
        self, existing_system: dict, new_log_info: BuildLogInfo
    ) -> tuple[int, int]:
        """Merge system library paths.

        Args:
            existing_system: Existing system paths section
            new_log_info: New build log information

        Returns:
            Tuple of (paths_added, paths_skipped)
        """
        added = 0
        skipped = 0

        platform = new_log_info.platform.value
        platform_lower = platform.lower()
        config = new_log_info.build_config.lower()

        # Compute the Delphi lib path for this platform/config
        compiler_root = new_log_info.compiler_path.parent.parent
        lib_path = compiler_root / "lib" / platform / config

        # Add lib path for this platform/config
        field_name = f"lib_{platform_lower}_{config}"
        if field_name not in existing_system:
            existing_system[field_name] = self._format_path(lib_path)
            added += 1
        else:
            skipped += 1

        # Also add the other config (debug/release) for this platform
        other_config = "release" if config == "debug" else "debug"
        other_field = f"lib_{platform_lower}_{other_config}"
        other_lib_path = compiler_root / "lib" / platform / other_config
        if other_field not in existing_system:
            existing_system[other_field] = self._format_path(other_lib_path)
            added += 1

        return added, skipped

    def _merge_library_paths(
        self, existing_libraries: dict, new_paths: list[Path]
    ) -> tuple[int, int]:
        """Merge third-party library paths.

        Args:
            existing_libraries: Existing library paths section
            new_paths: New library paths from build log

        Returns:
            Tuple of (paths_added, paths_skipped)
        """
        added = 0
        skipped = 0

        # Get all existing paths (normalized for comparison)
        existing_paths_normalized = set()
        for value in existing_libraries.values():
            if isinstance(value, str):
                existing_paths_normalized.add(self._normalize_path_for_comparison(value))

        # Track used names to generate unique names
        used_names = set(existing_libraries.keys())

        for path in new_paths:
            normalized_new = self._normalize_path_for_comparison(str(path))
            if normalized_new in existing_paths_normalized:
                skipped += 1
                continue

            # Generate unique name for this library
            base_name = self._derive_library_name(path)
            lib_name = self._make_unique_name(base_name, used_names)
            used_names.add(lib_name)

            # Add the path
            existing_libraries[lib_name] = self._format_path(path)
            existing_paths_normalized.add(normalized_new)
            added += 1

        return added, skipped

    def _merge_namespaces(
        self, existing_ns: dict, new_ns: list[str]
    ) -> int:
        """Merge namespace prefix lists.

        Args:
            existing_ns: Existing namespaces section
            new_ns: New namespace prefixes from build log

        Returns:
            Number of namespaces added
        """
        if not new_ns:
            return 0

        added = 0
        existing_prefixes = existing_ns.get("prefixes", [])
        existing_lower = set(ns.lower() for ns in existing_prefixes)

        for ns in new_ns:
            if ns.lower() not in existing_lower:
                existing_prefixes.append(ns)
                existing_lower.add(ns.lower())
                added += 1

        existing_ns["prefixes"] = existing_prefixes
        return added

    def _merge_aliases(
        self, existing_aliases: dict, new_aliases: dict[str, str]
    ) -> int:
        """Merge unit alias dictionaries.

        Args:
            existing_aliases: Existing aliases section
            new_aliases: New aliases from build log

        Returns:
            Number of aliases added
        """
        if not new_aliases:
            return 0

        added = 0
        for old_name, new_name in new_aliases.items():
            # Only add if not already present
            if old_name not in existing_aliases:
                existing_aliases[old_name] = new_name
                added += 1

        return added

    def _merge_flags(
        self, existing_flags: dict, new_flags: list[str]
    ) -> int:
        """Merge compiler flags.

        Args:
            existing_flags: Existing flags section
            new_flags: New flags from build log

        Returns:
            Number of flags added
        """
        if not new_flags:
            return 0

        added = 0
        existing_list = existing_flags.get("flags", [])
        if not existing_list:
            existing_list = existing_flags.get("common", [])

        existing_lower = set(f.lower() for f in existing_list)

        for flag in new_flags:
            if flag.lower() not in existing_lower:
                existing_list.append(flag)
                existing_lower.add(flag.lower())
                added += 1

        # Store in 'flags' or 'common' depending on what exists
        if "common" in existing_flags:
            existing_flags["common"] = existing_list
        else:
            existing_flags["flags"] = existing_list

        return added

    def _merge_linux_sdk(
        self, existing_sdk: dict, new_log_info: BuildLogInfo
    ) -> int:
        """Merge Linux SDK settings.

        Args:
            existing_sdk: Existing linux_sdk section
            new_log_info: New build log information

        Returns:
            Number of settings added
        """
        added = 0

        # Only add sysroot if not present
        if new_log_info.sdk_sysroot and "sysroot" not in existing_sdk:
            existing_sdk["sysroot"] = self._format_path(new_log_info.sdk_sysroot)
            added += 1

        # Merge libpaths
        if new_log_info.sdk_libpaths:
            existing_libpaths = existing_sdk.get("libpaths", [])
            existing_normalized = set(
                self._normalize_path_for_comparison(str(p)) for p in existing_libpaths
            )

            for path in new_log_info.sdk_libpaths:
                normalized = self._normalize_path_for_comparison(str(path))
                if normalized not in existing_normalized:
                    existing_libpaths.append(self._format_path(path))
                    existing_normalized.add(normalized)
                    added += 1

            existing_sdk["libpaths"] = existing_libpaths

        return added

    def _normalize_path_for_comparison(self, path: str) -> str:
        """Normalize path for duplicate detection.

        Args:
            path: Path string to normalize

        Returns:
            Normalized path for comparison
        """
        # Convert to lowercase, forward slashes, no trailing slash
        normalized = path.lower().replace("\\", "/").rstrip("/")

        # Expand ${USERNAME} for comparison
        username = os.getenv("USERNAME", "")
        if username:
            normalized = normalized.replace("${username}", username.lower())

        return normalized

    def _derive_library_name(self, path: Path) -> str:
        """Derive a meaningful name for a library from its path.

        Args:
            path: Library path

        Returns:
            Library name suitable for use as TOML key
        """
        path_str = str(path).lower()

        # Known library patterns
        patterns = {
            "dunitx": "dunitx",
            "delphi-mocks": "delphi_mocks",
            "delphi_mocks": "delphi_mocks",
            "testinsight": "testinsight",
            "spring4d": "spring4d",
            "zeoslib": "zeoslib",
            "dmvcframework": "dmvcframework",
            "loggerpro": "loggerpro",
            "jcl": "jcl",
            "jvcl": "jvcl",
            "abbrevia": "abbrevia",
            "lockbox": "lockbox",
            "omni": "omnithreadlibrary",
            "python4delphi": "python4delphi",
            "markdown": "markdown",
            "toml": "toml",
            "yaml": "yaml",
        }

        for pattern, name in patterns.items():
            if pattern in path_str:
                if "include" in path_str:
                    return f"{name}_include"
                elif "source" in path_str or "src" in path_str:
                    return f"{name}_source"
                elif "\\lib\\" in path_str or "/lib/" in path_str:
                    return f"{name}_lib"
                else:
                    return name

        # Fallback: use directory name
        dir_name = path.name.lower().replace(" ", "_").replace("-", "_")
        # Remove version numbers
        dir_name = re.sub(r"[\d._-]+$", "", dir_name)

        if dir_name and len(dir_name) > 2:
            return dir_name

        return "library"

    def _make_unique_name(self, base_name: str, used_names: set[str]) -> str:
        """Generate a unique name by appending suffix if needed.

        Args:
            base_name: Base name to make unique
            used_names: Set of already used names

        Returns:
            Unique name
        """
        if base_name not in used_names:
            return base_name

        counter = 2
        while f"{base_name}_{counter}" in used_names:
            counter += 1

        return f"{base_name}_{counter}"

    def _format_path(self, path: Path) -> str:
        """Format a path for TOML output.

        Args:
            path: Path to format

        Returns:
            Formatted path string
        """
        path_str = str(path)

        # Fix encoding corruption from IDE build logs
        corrupted_patterns = [
            ("½SUSERDIR%", "${USERDIR}"),
            ("½SUSERNAME%", "${USERNAME}"),
            ("½S", "${"),
        ]
        for corrupted, fixed in corrupted_patterns:
            path_str = path_str.replace(corrupted, fixed)

        if self.use_env_vars:
            username = os.getenv("USERNAME", "")
            if username:
                user_pattern = f"C:\\Users\\{username}"
                path_str = path_str.replace(user_pattern, "C:/Users/${USERNAME}")
                path_str = path_str.replace(user_pattern.lower(), "C:/Users/${USERNAME}")

        # Convert backslashes to forward slashes
        path_str = path_str.replace("\\", "/")

        return path_str

    def _generate_toml(self, config: dict) -> str:
        """Generate TOML content from merged config dictionary.

        Args:
            config: Merged configuration dictionary

        Returns:
            TOML file content as string
        """
        lines = []

        # Header
        lines.append("# Delphi Build MCP Server Configuration")
        lines.append("#")
        lines.append("# Extended configuration file")
        if "delphi" in config:
            version = config["delphi"].get("version", "unknown")
            lines.append(f"# Delphi Version: {version}")
        lines.append("#")
        lines.append("")

        # [delphi] section
        if "delphi" in config:
            lines.extend(self._section_to_toml("delphi", config["delphi"]))
            lines.append("")

        # [paths.system] section
        if "paths" in config and "system" in config["paths"]:
            lines.append("# " + "=" * 77)
            lines.append("# System Library Paths")
            lines.append("# " + "=" * 77)
            lines.append("[paths.system]")
            for key, value in config["paths"]["system"].items():
                lines.append(f'{key} = "{value}"')
            lines.append("")

        # [paths.libraries] section
        if "paths" in config and "libraries" in config["paths"]:
            lines.append("# " + "=" * 77)
            lines.append("# Third-Party Library Paths")
            lines.append("# " + "=" * 77)
            lines.append("[paths.libraries]")
            for key, value in config["paths"]["libraries"].items():
                lines.append(f'{key} = "{value}"')
            lines.append("")

        # [compiler.flags] section
        if "compiler" in config and "flags" in config["compiler"]:
            lines.append("# " + "=" * 77)
            lines.append("# Compiler Flags")
            lines.append("# " + "=" * 77)
            lines.append("[compiler.flags]")
            flags_section = config["compiler"]["flags"]
            for key, value in flags_section.items():
                if isinstance(value, list):
                    flags_str = ", ".join(f'"{f}"' for f in value)
                    lines.append(f"{key} = [{flags_str}]")
                elif isinstance(value, dict):
                    # Nested section like [compiler.flags.Win64.Debug]
                    pass  # Handle below
                else:
                    lines.append(f'{key} = "{value}"')
            lines.append("")

        # [compiler.namespaces] section
        if "compiler" in config and "namespaces" in config["compiler"]:
            lines.append("# " + "=" * 77)
            lines.append("# Namespace Prefixes")
            lines.append("# " + "=" * 77)
            lines.append("[compiler.namespaces]")
            ns_section = config["compiler"]["namespaces"]
            if "prefixes" in ns_section:
                prefixes = ns_section["prefixes"]
                prefixes_str = ", ".join(f'"{ns}"' for ns in prefixes)
                lines.append(f"prefixes = [{prefixes_str}]")
            lines.append("")

        # [compiler.aliases] section
        if "compiler" in config and "aliases" in config["compiler"]:
            lines.append("# " + "=" * 77)
            lines.append("# Unit Aliases")
            lines.append("# " + "=" * 77)
            lines.append("[compiler.aliases]")
            for key, value in config["compiler"]["aliases"].items():
                lines.append(f'"{key}" = "{value}"')
            lines.append("")

        # [linux_sdk] section
        if "linux_sdk" in config:
            lines.append("# " + "=" * 77)
            lines.append("# Linux SDK Configuration")
            lines.append("# " + "=" * 77)
            lines.append("[linux_sdk]")
            sdk_section = config["linux_sdk"]
            if "sysroot" in sdk_section:
                lines.append(f'sysroot = "{sdk_section["sysroot"]}"')
            if "libpaths" in sdk_section:
                lines.append("libpaths = [")
                for path in sdk_section["libpaths"]:
                    lines.append(f'    "{path}",')
                lines.append("]")
            lines.append("")

        return "\n".join(lines)

    def _section_to_toml(self, section_name: str, section_dict: dict) -> list[str]:
        """Convert a section dictionary to TOML lines.

        Args:
            section_name: Name of the section
            section_dict: Section data

        Returns:
            List of TOML lines
        """
        lines = []
        lines.append("# " + "=" * 77)
        lines.append(f"# {section_name.title()} Configuration")
        lines.append("# " + "=" * 77)
        lines.append(f"[{section_name}]")

        for key, value in section_dict.items():
            if isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            elif isinstance(value, bool):
                lines.append(f'{key} = {str(value).lower()}')
            elif isinstance(value, (int, float)):
                lines.append(f'{key} = {value}')
            elif isinstance(value, list):
                if all(isinstance(v, str) for v in value):
                    values_str = ", ".join(f'"{v}"' for v in value)
                    lines.append(f"{key} = [{values_str}]")
                else:
                    lines.append(f"{key} = {value}")

        return lines


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Extend existing delphi_config.toml with settings from IDE build log",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.config_extender existing_config.toml build_log.log
  python -m src.config_extender existing_config.toml build_log.log -o extended_config.toml
  python -m src.config_extender existing_config.toml build_log.log --no-env-vars
        """,
    )

    parser.add_argument(
        "existing_config",
        type=str,
        help="Path to existing delphi_config.toml file",
    )

    parser.add_argument(
        "build_log",
        type=str,
        help="Path to IDE build log file",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output configuration file path (default: overwrite existing)",
    )

    parser.add_argument(
        "--no-env-vars",
        action="store_true",
        help="Don't replace paths with environment variables like ${USERNAME}",
    )

    args = parser.parse_args()

    # Convert paths
    existing_config_path = Path(args.existing_config)
    build_log_path = Path(args.build_log)
    output_path = Path(args.output) if args.output else None

    # Check if files exist
    if not existing_config_path.exists():
        print(f"Error: Existing config file not found: {existing_config_path}", file=sys.stderr)
        sys.exit(1)

    if not build_log_path.exists():
        print(f"Error: Build log file not found: {build_log_path}", file=sys.stderr)
        sys.exit(1)

    # Extend config
    try:
        print(f"Reading existing config: {existing_config_path}")
        print(f"Reading build log: {build_log_path}")

        extender = ConfigExtender(use_env_vars=not args.no_env_vars)
        result = extender.extend_from_build_log(
            existing_config_path=existing_config_path,
            build_log_path=build_log_path,
            output_path=output_path,
        )

        # Print results
        print(f"\n[SUCCESS] Configuration extended successfully")
        print(f"\nUpdated: {result.config_file_path}")

        if result.platforms_added:
            print(f"\nNew platforms added: {', '.join(result.platforms_added)}")

        print(f"\nStatistics:")
        print(f"  Paths added: {result.paths_added}")
        print(f"  Paths skipped (duplicates): {result.paths_skipped}")

        if result.settings_updated:
            print(f"\nSettings updated:")
            for section, count in result.settings_updated.items():
                print(f"  - {section}: {count}")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error parsing config/build log: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
