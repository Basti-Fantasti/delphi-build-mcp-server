"""Generate delphi_config.toml from multiple build logs for different configs/platforms."""

import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from src.buildlog_parser import BuildLogParser
from src.models import (
    BuildLogEntry,
    BuildLogInfo,
    MultiConfigGenerationResult,
    SUPPORTED_CONFIGS,
    SUPPORTED_PLATFORMS,
)


class MultiConfigGenerator:
    """Generates hierarchical TOML configuration from multiple build logs.

    This generator accepts one or more build logs (Debug/Release, Win32/Win64)
    and creates a unified configuration file with platform and config-specific
    sections.
    """

    def __init__(self, use_env_vars: bool = True):
        """Initialize multi-config generator.

        Args:
            use_env_vars: Whether to replace paths with environment variables
        """
        self.use_env_vars = use_env_vars

    def generate_from_build_logs(
        self,
        build_log_paths: list[str],
        output_path: Path,
    ) -> MultiConfigGenerationResult:
        """Generate configuration from multiple build log files.

        Args:
            build_log_paths: List of paths to IDE build log files
            output_path: Path where to save the generated config

        Returns:
            MultiConfigGenerationResult with generation statistics

        Raises:
            FileNotFoundError: If any build log doesn't exist
            ValueError: If no build logs can be parsed
        """
        # Parse all build logs
        parsed_logs: dict[tuple[str, str], BuildLogInfo] = {}
        log_entries: list[BuildLogEntry] = []

        for log_path_str in build_log_paths:
            log_path = Path(log_path_str)
            if not log_path.exists():
                raise FileNotFoundError(f"Build log not found: {log_path}")

            parser = BuildLogParser(log_path)

            # Parse the log content
            log_info = parser.parse()

            # Get config and platform from parsed log
            config = log_info.build_config
            platform = log_info.platform.value
            auto_detected = True  # Values are detected from compiler command

            # Normalize config and platform names
            config = self._normalize_config(config)
            platform = self._normalize_platform(platform)

            # Store parsed log info keyed by (config, platform)
            key = (config, platform)
            if key in parsed_logs:
                # If we already have this config/platform, merge paths
                self._merge_log_info(parsed_logs[key], log_info)
            else:
                parsed_logs[key] = log_info

            log_entries.append(BuildLogEntry(
                path=str(log_path),
                config=config,
                platform=platform,
                auto_detected=auto_detected,
            ))

        if not parsed_logs:
            raise ValueError("No build logs could be parsed successfully")

        # Generate TOML content
        toml_content = self._generate_toml(parsed_logs)

        # Write to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(toml_content)

        # Prepare statistics
        statistics = {
            "build_logs_parsed": len(build_log_paths),
            "configs_found": list(set(e.config for e in log_entries)),
            "platforms_found": list(set(e.platform for e in log_entries)),
            "total_library_paths": self._count_total_paths(parsed_logs),
        }

        return MultiConfigGenerationResult(
            success=True,
            config_file_path=str(output_path.absolute()),
            build_logs_processed=log_entries,
            statistics=statistics,
            message=f"Configuration file generated successfully from {len(build_log_paths)} build log(s)",
        )

    def _normalize_config(self, config: str) -> str:
        """Normalize configuration name to standard format."""
        config_lower = config.lower()
        if config_lower == "debug":
            return "Debug"
        elif config_lower == "release":
            return "Release"
        return config

    def _normalize_platform(self, platform: str) -> str:
        """Normalize platform name to standard format."""
        platform_lower = platform.lower()
        if platform_lower == "win32":
            return "Win32"
        elif platform_lower == "win64":
            return "Win64"
        elif platform_lower == "linux64":
            return "Linux64"
        elif platform_lower == "android":
            return "Android"
        elif platform_lower == "android64":
            return "Android64"
        return platform

    def _merge_log_info(self, existing: BuildLogInfo, new: BuildLogInfo) -> None:
        """Merge new log info into existing one (for duplicate config/platform)."""
        # Merge search paths (deduplicated)
        existing_paths = set(str(p).lower() for p in existing.search_paths)
        for path in new.search_paths:
            if str(path).lower() not in existing_paths:
                existing.search_paths.append(path)
                existing_paths.add(str(path).lower())

        # Merge namespace prefixes
        existing_ns = set(ns.lower() for ns in existing.namespace_prefixes)
        for ns in new.namespace_prefixes:
            if ns.lower() not in existing_ns:
                existing.namespace_prefixes.append(ns)
                existing_ns.add(ns.lower())

    def _count_total_paths(self, parsed_logs: dict[tuple[str, str], BuildLogInfo]) -> int:
        """Count total unique library paths across all logs."""
        all_paths = set()
        for log_info in parsed_logs.values():
            for path in log_info.search_paths:
                all_paths.add(str(path).lower())
        return len(all_paths)

    def _generate_toml(self, parsed_logs: dict[tuple[str, str], BuildLogInfo]) -> str:
        """Generate TOML content from parsed build logs.

        Args:
            parsed_logs: Dictionary mapping (config, platform) to BuildLogInfo

        Returns:
            TOML file content as string
        """
        lines = []

        # Get any log info to extract common settings
        first_log = next(iter(parsed_logs.values()))

        # Header
        lines.append("# Delphi Build MCP Server Configuration")
        lines.append("#")
        lines.append("# Auto-generated from multiple IDE build logs")
        lines.append(f"# Delphi Version: {first_log.delphi_version}")
        lines.append(f"# Configurations: {', '.join(sorted(set(k[0] for k in parsed_logs.keys())))}")
        lines.append(f"# Platforms: {', '.join(sorted(set(k[1] for k in parsed_logs.keys())))}")
        lines.append("#")
        lines.append("")

        # Delphi installation section
        lines.extend(self._generate_delphi_section(first_log))
        lines.append("")

        # System paths section (required by config loader)
        lines.extend(self._generate_system_paths_section(first_log, parsed_logs))
        lines.append("")

        # Library paths section - include ALL library paths with unique names
        lines.extend(self._generate_all_libraries_section(parsed_logs, first_log))
        lines.append("")

        # Compiler flags section (common flags)
        lines.extend(self._generate_compiler_flags_section(parsed_logs))
        lines.append("")

        # Compiler namespaces section
        lines.extend(self._generate_namespaces_section(first_log))
        lines.append("")

        # Compiler aliases section
        lines.extend(self._generate_aliases_section(first_log))

        return "\n".join(lines)

    def _categorize_paths_across_logs(
        self, parsed_logs: dict[tuple[str, str], BuildLogInfo]
    ) -> tuple[list[Path], dict[tuple[str, str], list[Path]]]:
        """Categorize paths into common and platform/config-specific.

        Args:
            parsed_logs: Dictionary mapping (config, platform) to BuildLogInfo

        Returns:
            Tuple of (common_paths, platform_config_specific_paths)
        """
        # Count how many logs each path appears in
        path_counts: dict[str, int] = defaultdict(int)
        path_to_original: dict[str, Path] = {}
        all_log_keys = set(parsed_logs.keys())

        for log_info in parsed_logs.values():
            seen_in_this_log = set()
            for path in log_info.search_paths:
                normalized = str(path).lower().replace("\\", "/")
                if normalized not in seen_in_this_log:
                    path_counts[normalized] += 1
                    path_to_original[normalized] = path
                    seen_in_this_log.add(normalized)

        total_logs = len(parsed_logs)

        # Paths that appear in ALL logs are common
        common_paths = [
            path_to_original[normalized]
            for normalized, count in path_counts.items()
            if count == total_logs
        ]

        # For each config/platform, collect paths unique to it
        common_normalized = set(
            str(p).lower().replace("\\", "/") for p in common_paths
        )

        platform_config_paths: dict[tuple[str, str], list[Path]] = {}
        for key, log_info in parsed_logs.items():
            specific_paths = []
            for path in log_info.search_paths:
                normalized = str(path).lower().replace("\\", "/")
                if normalized not in common_normalized:
                    specific_paths.append(path)
            if specific_paths:
                platform_config_paths[key] = specific_paths

        return common_paths, platform_config_paths

    def _generate_delphi_section(self, log_info: BuildLogInfo) -> list[str]:
        """Generate [delphi] section."""
        lines = [
            "# " + "=" * 77,
            "# Delphi Installation Configuration",
            "# " + "=" * 77,
            "[delphi]",
        ]

        # Version
        lines.append(f'version = "{log_info.delphi_version}"')
        lines.append("")

        # Root path (derived from compiler path)
        compiler_path = log_info.compiler_path
        root_path = compiler_path.parent.parent
        root_path_str = self._format_path(root_path)

        lines.append("# Delphi installation root directory")
        lines.append(f'root_path = "{root_path_str}"')
        lines.append("")

        lines.append("# Compiler executables (auto-detected from root_path if not specified)")
        lines.append('# compiler_win32 = "C:/Program Files (x86)/Embarcadero/Studio/23.0/bin/dcc32.exe"')
        lines.append('# compiler_win64 = "C:/Program Files (x86)/Embarcadero/Studio/23.0/bin/dcc64.exe"')

        return lines

    def _generate_system_paths_section(
        self, log_info: BuildLogInfo, parsed_logs: dict[tuple[str, str], BuildLogInfo]
    ) -> list[str]:
        """Generate [paths.system] section with RTL/VCL and lib paths."""
        lines = [
            "# " + "=" * 77,
            "# System Paths (Delphi RTL/VCL)",
            "# " + "=" * 77,
            "[paths.system]",
        ]

        # Derive paths from compiler root
        compiler_root = log_info.compiler_path.parent.parent
        rtl_path = compiler_root / "source" / "rtl"
        vcl_path = compiler_root / "source" / "vcl"

        lines.append(f'rtl = "{self._format_path(rtl_path)}"')
        lines.append(f'vcl = "{self._format_path(vcl_path)}"')
        lines.append("")

        # Get platforms from parsed logs
        platforms = set(k[1] for k in parsed_logs.keys())

        # For each platform found, always include BOTH debug and release lib paths
        # (resource files like Controls.res are only in release folder)
        for platform in sorted(platforms):
            for config in ["debug", "release"]:
                field_name = f"lib_{platform.lower()}_{config}"
                lib_path = compiler_root / "lib" / platform / config
                lines.append(f'{field_name} = "{self._format_path(lib_path)}"')

        # Add placeholder comments for platforms not in build logs
        all_platforms = ["Win32", "Win64", "Linux64"]
        for platform in all_platforms:
            if platform not in platforms:
                for config in ["debug", "release"]:
                    field_name = f"lib_{platform.lower()}_{config}"
                    default_path = compiler_root / "lib" / platform / config
                    lines.append(f'# {field_name} = "{self._format_path(default_path)}"')

        return lines

    def _find_system_lib_in_search_paths(
        self, log_info: BuildLogInfo, platform: str, config: str
    ) -> Optional[Path]:
        """Find the Delphi system lib path in search paths."""
        platform_lower = platform.lower()
        config_lower = config.lower()
        compiler_root = str(log_info.compiler_path.parent.parent).lower()

        for path in log_info.search_paths:
            path_str = str(path).lower().replace("\\", "/")
            # Check if it's a Delphi system lib path
            if compiler_root.replace("\\", "/") in path_str:
                if f"/lib/{platform_lower}/{config_lower}" in path_str:
                    return path

        # Fallback: construct from compiler root
        return log_info.compiler_path.parent.parent / "lib" / platform / config.lower()

    def _generate_all_libraries_section(
        self, parsed_logs: dict[tuple[str, str], BuildLogInfo], first_log: BuildLogInfo
    ) -> list[str]:
        """Generate [paths.libraries] section with ALL library paths.

        Collects all library paths from all build logs and assigns unique names.
        Platform-specific paths get platform suffix to avoid conflicts.
        """
        lines = [
            "# " + "=" * 77,
            "# Library Paths",
            "# " + "=" * 77,
            "[paths.libraries]",
            "# Third-party libraries extracted from IDE build logs",
            "",
        ]

        # Collect all unique library paths with their source info
        all_library_paths: list[tuple[Path, str, str]] = []  # (path, config, platform)
        seen_paths: set[str] = set()

        for (config, platform), log_info in parsed_logs.items():
            system_paths, library_paths = self._categorize_paths(log_info.search_paths, log_info)
            for path in library_paths:
                normalized = str(path).lower().replace("\\", "/")
                if normalized not in seen_paths:
                    seen_paths.add(normalized)
                    all_library_paths.append((path, config, platform))

        # Generate unique names for all libraries
        used_names: dict[str, int] = {}

        for idx, (path, config, platform) in enumerate(all_library_paths, 1):
            base_name = self._derive_library_name(path, idx)

            # Check if this path is platform-specific (contains platform name in path)
            path_lower = str(path).lower()
            is_platform_specific = any(p in path_lower for p in ["/win32", "/win64", "/linux64", "\\win32", "\\win64", "\\linux64"])

            if is_platform_specific:
                # Add platform suffix for platform-specific paths
                base_name = f"{base_name}_{platform.lower()}"

            if base_name in used_names:
                used_names[base_name] += 1
                lib_name = f"{base_name}_{used_names[base_name]}"
            else:
                used_names[base_name] = 1
                lib_name = base_name

            path_str = self._format_path(path)
            lines.append(f'{lib_name} = "{path_str}"')

        if not all_library_paths:
            lines.append("# No library paths found in build logs")

        return lines

    def _generate_platform_config_sections(
        self,
        platform_config_paths: dict[tuple[str, str], list[Path]],
        parsed_logs: dict[tuple[str, str], BuildLogInfo],
    ) -> list[str]:
        """Generate [paths.<Platform>.<Config>] sections."""
        lines = [
            "",
            "# " + "=" * 77,
            "# Platform and Configuration Specific Paths",
            "# " + "=" * 77,
        ]

        # Get all platforms and configs
        platforms = sorted(set(k[1] for k in parsed_logs.keys()))
        configs = sorted(set(k[0] for k in parsed_logs.keys()))

        for platform in platforms:
            for config in configs:
                key = (config, platform)
                if key in parsed_logs:
                    log_info = parsed_logs[key]
                    specific_paths = platform_config_paths.get(key, [])

                    lines.append("")
                    lines.append(f"[paths.{platform}.{config}]")
                    lines.append(f"# Paths specific to {platform} {config} configuration")

                    # Find and add the system lib path for this config/platform
                    system_paths, lib_paths = self._categorize_paths(specific_paths, log_info)

                    # Look for the compiled library path (lib/win32/debug, lib/win64/release, etc.)
                    lib_path = self._find_system_lib_path(system_paths, platform, config)
                    if lib_path:
                        lines.append(f'lib = "{self._format_path(lib_path)}"')

                    # Add any other platform/config specific library paths
                    # Use unique naming to avoid duplicate TOML keys
                    if lib_paths:
                        lines.append("")
                        lines.append("# Additional libraries for this configuration")
                        # Reserve 'lib' for system lib path
                        used_names: dict[str, int] = {"lib": 1}
                        for idx, path in enumerate(lib_paths, 1):
                            path_str = self._format_path(path)
                            base_name = self._derive_library_name(path, idx)

                            # Ensure unique key names within this section
                            if base_name in used_names:
                                used_names[base_name] += 1
                                lib_name = f"{base_name}_{used_names[base_name]}"
                            else:
                                used_names[base_name] = 1
                                lib_name = base_name

                            lines.append(f'{lib_name} = "{path_str}"')

        return lines

    def _find_system_lib_path(
        self, system_paths: list[Path], platform: str, config: str
    ) -> Optional[Path]:
        """Find the Delphi system library path for a specific platform/config."""
        platform_lower = platform.lower()
        config_lower = config.lower()

        # Prefer paths without locale suffix (e.g., lib/win32/release over lib/win32/release/DE)
        best_match = None
        best_match_len = 999

        for path in system_paths:
            path_str = str(path).lower().replace("\\", "/")
            # Look for paths like lib/win32/debug or lib/win64/release
            if f"/lib/{platform_lower}/{config_lower}" in path_str:
                # Shorter paths are preferred (no locale suffix)
                if len(path_str) < best_match_len:
                    best_match = path
                    best_match_len = len(path_str)

        return best_match

    def _generate_compiler_flags_section(
        self, parsed_logs: dict[tuple[str, str], BuildLogInfo]
    ) -> list[str]:
        """Generate [compiler.flags] section with common and platform/config-specific flags."""
        lines = [
            "# " + "=" * 77,
            "# Compiler Flags",
            "# " + "=" * 77,
            "[compiler.flags]",
            "# Common compiler flags (applied to all configurations)",
        ]

        # Find flags common to all logs
        all_flags_sets = [set(log.compiler_flags) for log in parsed_logs.values()]
        if all_flags_sets:
            common_flags = all_flags_sets[0]
            for flags_set in all_flags_sets[1:]:
                common_flags = common_flags.intersection(flags_set)
            common_flags = sorted(list(common_flags))
        else:
            common_flags = []

        if common_flags:
            flags_str = ", ".join(f'"{flag}"' for flag in common_flags)
            lines.append(f"common = [{flags_str}]")
        else:
            lines.append('common = ["--no-config", "-Q", "-B"]')

        # Get all platforms and configs
        platforms = sorted(set(k[1] for k in parsed_logs.keys()))
        configs = sorted(set(k[0] for k in parsed_logs.keys()))

        # Add platform/config-specific flags sections
        for platform in platforms:
            for config in configs:
                key = (config, platform)
                if key in parsed_logs:
                    log_info = parsed_logs[key]
                    # Get flags unique to this platform/config combination
                    specific_flags = [f for f in log_info.compiler_flags if f not in common_flags]

                    if specific_flags:
                        lines.append("")
                        lines.append(f"[compiler.flags.{platform}.{config}]")
                        # Convert backslashes to forward slashes for TOML compatibility
                        escaped_flags = [f.replace("\\", "/") for f in sorted(specific_flags)]
                        flags_str = ", ".join(f'"{flag}"' for flag in escaped_flags)
                        lines.append(f"flags = [{flags_str}]")

        return lines

    def _generate_namespaces_section(self, log_info: BuildLogInfo) -> list[str]:
        """Generate [compiler.namespaces] section."""
        lines = [
            "# " + "=" * 77,
            "# Namespace Prefixes",
            "# " + "=" * 77,
            "[compiler.namespaces]",
            "# Namespace prefixes for unit lookup",
        ]

        if log_info.namespace_prefixes:
            prefixes_str = ", ".join(f'"{ns}"' for ns in log_info.namespace_prefixes)
            lines.append(f"prefixes = [{prefixes_str}]")
        else:
            lines.append("prefixes = [")
            lines.append('    "Winapi", "System.Win", "Data.Win", "Datasnap.Win",')
            lines.append('    "Web.Win", "Soap.Win", "Xml.Win", "Bde",')
            lines.append('    "System", "Xml", "Data", "Datasnap", "Web", "Soap", "Vcl"')
            lines.append("]")

        return lines

    def _generate_aliases_section(self, log_info: BuildLogInfo) -> list[str]:
        """Generate [compiler.aliases] section."""
        lines = [
            "# " + "=" * 77,
            "# Unit Aliases",
            "# " + "=" * 77,
            "[compiler.aliases]",
            "# Unit name aliases for legacy code compatibility",
        ]

        if log_info.unit_aliases:
            for old_name, new_name in log_info.unit_aliases.items():
                lines.append(f'"{old_name}" = "{new_name}"')
        else:
            lines.append('"Generics.Collections" = "System.Generics.Collections"')
            lines.append('"Generics.Defaults" = "System.Generics.Defaults"')
            lines.append('"WinTypes" = "Winapi.Windows"')
            lines.append('"WinProcs" = "Winapi.Windows"')
            lines.append('"SysUtils" = "System.SysUtils"')
            lines.append('"Classes" = "System.Classes"')

        return lines

    def _categorize_paths(
        self, paths: list[Path], log_info: BuildLogInfo
    ) -> tuple[list[Path], list[Path]]:
        """Categorize paths into system paths and library paths."""
        system_paths = []
        library_paths = []

        compiler_root = log_info.compiler_path.parent.parent
        compiler_root_str = str(compiler_root).lower()

        for path in paths:
            path_str = str(path).lower()
            if compiler_root_str in path_str:
                system_paths.append(path)
            else:
                library_paths.append(path)

        return system_paths, library_paths

    def _derive_library_name(self, path: Path, index: int) -> str:
        """Derive a meaningful name for a library from its path."""
        path_str = str(path).lower()

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

        dir_name = path.name.lower().replace(" ", "_").replace("-", "_")
        dir_name = re.sub(r"[\d._-]+$", "", dir_name)

        if dir_name and len(dir_name) > 2:
            return dir_name

        return f"library_{index}"

    def _format_path(self, path: Path) -> str:
        """Format a path for TOML output, optionally replacing with env vars."""
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

        path_str = path_str.replace("\\", "/")

        return path_str


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Generate delphi_config.toml from multiple IDE build logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.multi_config_generator debug.log release.log
  python -m src.multi_config_generator win32_debug.log win64_release.log -o my_config.toml
  python -m src.multi_config_generator *.log --no-env-vars

This tool merges multiple build logs (e.g., Debug/Release, Win32/Win64) into a
single hierarchical configuration file with platform and config-specific sections.
        """,
    )

    parser.add_argument(
        "build_logs",
        type=str,
        nargs="+",
        help="Paths to IDE build log files (at least one required)",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="delphi_config.toml",
        help="Output configuration file path (default: delphi_config.toml)",
    )

    parser.add_argument(
        "--no-env-vars",
        action="store_true",
        help="Don't replace paths with environment variables like ${USERNAME}",
    )

    args = parser.parse_args()

    # Convert output path
    output_path = Path(args.output)

    # Validate build log files exist
    missing_files = []
    for log_path in args.build_logs:
        if not Path(log_path).exists():
            missing_files.append(log_path)

    if missing_files:
        print("Error: Build log file(s) not found:", file=sys.stderr)
        for f in missing_files:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(1)

    # Generate config
    try:
        print(f"Processing {len(args.build_logs)} build log(s):")
        for log_path in args.build_logs:
            print(f"  - {log_path}")

        generator = MultiConfigGenerator(use_env_vars=not args.no_env_vars)
        result = generator.generate_from_build_logs(args.build_logs, output_path)

        # Print results
        print(f"\n[SUCCESS] {result.message}")
        print(f"\nGenerated: {result.config_file_path}")
        print(f"\nBuild Logs Processed:")
        for entry in result.build_logs_processed:
            auto_str = " (auto-detected)" if entry.auto_detected else ""
            print(f"  - {entry.path}: {entry.platform} {entry.config}{auto_str}")
        print(f"\nStatistics:")
        print(f"  Build logs parsed: {result.statistics['build_logs_parsed']}")
        print(f"  Configurations: {', '.join(result.statistics['configs_found'])}")
        print(f"  Platforms: {', '.join(result.statistics['platforms_found'])}")
        print(f"  Total library paths: {result.statistics['total_library_paths']}")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error parsing build logs: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
