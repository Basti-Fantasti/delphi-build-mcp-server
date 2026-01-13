"""Generate delphi_config.toml from build log information."""

import os
import re
from pathlib import Path
from typing import Optional

from src.buildlog_parser import BuildLogParser
from src.models import BuildLogInfo, ConfigGenerationResult, DetectedInfo


class ConfigGenerator:
    """Generates TOML configuration files from build log information."""

    def __init__(self, use_env_vars: bool = True):
        """Initialize config generator.

        Args:
            use_env_vars: Whether to replace paths with environment variables
        """
        self.use_env_vars = use_env_vars

    def generate_from_build_log(
        self, build_log_path: Path, output_path: Path
    ) -> ConfigGenerationResult:
        """Generate configuration from a build log file.

        Args:
            build_log_path: Path to IDE build log
            output_path: Path where to save the generated config

        Returns:
            ConfigGenerationResult with generation statistics

        Raises:
            FileNotFoundError: If build log doesn't exist
            ValueError: If build log cannot be parsed
        """
        # Parse the build log
        parser = BuildLogParser(build_log_path)
        log_info = parser.parse()

        # Generate TOML content
        toml_content = self._generate_toml(log_info)

        # Write to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(toml_content)

        # Prepare result
        detected_info = DetectedInfo(
            delphi_version=log_info.delphi_version,
            platform=log_info.platform.value,
            build_config=log_info.build_config,
            compiler_executable=str(log_info.compiler_path),
        )

        statistics = {
            "total_paths_found": len(log_info.search_paths),
            "unique_paths": len(set(log_info.search_paths)),
            "compiler_flags_found": len(log_info.compiler_flags),
        }

        return ConfigGenerationResult(
            success=True,
            config_file_path=str(output_path.absolute()),
            statistics=statistics,
            detected_info=detected_info,
            message=f"Configuration file generated successfully with {statistics['unique_paths']} library paths",
        )

    def _generate_toml(self, log_info: BuildLogInfo) -> str:
        """Generate TOML content from build log information.

        Args:
            log_info: Parsed build log information

        Returns:
            TOML file content as string
        """
        lines = []

        # Header
        lines.append("# Delphi Build MCP Server Configuration")
        lines.append("#")
        lines.append("# Auto-generated from IDE build log")
        lines.append(f"# Delphi Version: {log_info.delphi_version}")
        lines.append(f"# Platform: {log_info.platform.value}")
        lines.append(f"# Build Config: {log_info.build_config}")
        lines.append("#")
        lines.append("")

        # Delphi installation section
        lines.extend(self._generate_delphi_section(log_info))
        lines.append("")

        # System paths section
        system_paths, library_paths = self._categorize_paths(log_info.search_paths, log_info)
        lines.extend(self._generate_system_paths_section(system_paths, log_info))
        lines.append("")

        # Library paths section
        lines.extend(self._generate_library_paths_section(library_paths))
        lines.append("")

        # Compiler flags section
        lines.extend(self._generate_compiler_flags_section(log_info))
        lines.append("")

        # Compiler namespaces section
        lines.extend(self._generate_namespaces_section(log_info))
        lines.append("")

        # Compiler aliases section
        lines.extend(self._generate_aliases_section(log_info))
        lines.append("")

        # Linux SDK section (for cross-compilation)
        lines.extend(self._generate_linux_sdk_section(log_info))

        return "\n".join(lines)

    def _generate_delphi_section(self, log_info: BuildLogInfo) -> list[str]:
        """Generate [delphi] section.

        Args:
            log_info: Build log information

        Returns:
            List of TOML lines
        """
        lines = ["# " + "=" * 77, "# Delphi Installation Configuration", "# " + "=" * 77, "[delphi]"]

        # Version
        lines.append(f'version = "{log_info.delphi_version}"')
        lines.append("")

        # Root path (derived from compiler path)
        compiler_path = log_info.compiler_path
        # Assume root is 2 levels up from bin/dcc32.exe
        root_path = compiler_path.parent.parent

        root_path_str = self._format_path(root_path)
        lines.append("# Delphi installation root directory")
        lines.append(f'root_path = "{root_path_str}"')
        lines.append("")

        lines.append("# Compiler executables (auto-detected from root_path if not specified)")
        lines.append('# compiler_win32 = "C:/Program Files (x86)/Embarcadero/Studio/23.0/bin/dcc32.exe"')
        lines.append('# compiler_win64 = "C:/Program Files (x86)/Embarcadero/Studio/23.0/bin/dcc64.exe"')
        lines.append('# compiler_linux64 = "C:/Program Files (x86)/Embarcadero/Studio/23.0/bin/dcclinux64.exe"')

        return lines

    def _generate_system_paths_section(
        self, system_paths: list[Path], log_info: BuildLogInfo
    ) -> list[str]:
        """Generate [paths.system] section.

        Args:
            system_paths: List of system paths
            log_info: Build log information

        Returns:
            List of TOML lines
        """
        lines = [
            "# " + "=" * 77,
            "# System Library Paths",
            "# " + "=" * 77,
            "[paths.system]",
        ]

        # Find RTL and VCL paths
        rtl_path = None
        vcl_path = None

        for path in system_paths:
            path_str = str(path).lower()
            if "rtl" in path_str and "common" in path_str and not rtl_path:
                rtl_path = path
            elif "vcl" in path_str and not "jvcl" in path_str and not vcl_path:
                vcl_path = path

        # Write RTL and VCL
        if rtl_path:
            lines.append(f'rtl = "{self._format_path(rtl_path)}"')
        else:
            lines.append('rtl = "C:/Program Files (x86)/Embarcadero/Studio/23.0/source/rtl/common"')

        if vcl_path:
            lines.append(f'vcl = "{self._format_path(vcl_path)}"')
        else:
            lines.append('vcl = "C:/Program Files (x86)/Embarcadero/Studio/23.0/source/vcl"')

        lines.append("")

        # Find lib paths for different platforms/configs
        lib_paths = {
            "lib_win32_release": None,
            "lib_win32_debug": None,
            "lib_win64_release": None,
            "lib_win64_debug": None,
            "lib_linux64_release": None,
            "lib_linux64_debug": None,
        }

        for path in system_paths:
            path_str = str(path).lower()
            if "\\lib\\win32\\release" in path_str:
                lib_paths["lib_win32_release"] = path
            elif "\\lib\\win32\\debug" in path_str:
                lib_paths["lib_win32_debug"] = path
            elif "\\lib\\win64\\release" in path_str:
                lib_paths["lib_win64_release"] = path
            elif "\\lib\\win64\\debug" in path_str:
                lib_paths["lib_win64_debug"] = path
            elif "\\lib\\linux64\\release" in path_str:
                lib_paths["lib_linux64_release"] = path
            elif "\\lib\\linux64\\debug" in path_str:
                lib_paths["lib_linux64_debug"] = path

        # Write lib paths
        lines.append("# Compiled library paths")
        for key, path in lib_paths.items():
            if path:
                lines.append(f'{key} = "{self._format_path(path)}"')

        return lines

    def _generate_library_paths_section(self, library_paths: list[Path]) -> list[str]:
        """Generate [paths.libraries] section.

        Args:
            library_paths: List of third-party library paths

        Returns:
            List of TOML lines
        """
        lines = [
            "# " + "=" * 77,
            "# Third-Party Library Paths",
            "# " + "=" * 77,
            "[paths.libraries]",
            "# All library paths from your build log",
            "",
        ]

        # Generate unique names for libraries
        used_names: dict[str, int] = {}

        for idx, path in enumerate(library_paths, 1):
            # Try to derive a meaningful name from the path
            base_name = self._derive_library_name(path, idx)

            # Ensure uniqueness
            if base_name in used_names:
                used_names[base_name] += 1
                lib_name = f"{base_name}_{used_names[base_name]}"
            else:
                used_names[base_name] = 1
                lib_name = base_name

            path_str = self._format_path(path)
            lines.append(f'{lib_name} = "{path_str}"')

        return lines

    def _generate_namespaces_section(self, log_info: BuildLogInfo) -> list[str]:
        """Generate [compiler.namespaces] section.

        Args:
            log_info: Build log information

        Returns:
            List of TOML lines
        """
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
            # Default namespaces
            lines.append("prefixes = [")
            lines.append('    "Winapi", "System.Win", "Data.Win", "Datasnap.Win",')
            lines.append('    "Web.Win", "Soap.Win", "Xml.Win", "Bde",')
            lines.append('    "System", "Xml", "Data", "Datasnap", "Web", "Soap", "Vcl"')
            lines.append("]")

        return lines

    def _generate_aliases_section(self, log_info: BuildLogInfo) -> list[str]:
        """Generate [compiler.aliases] section.

        Args:
            log_info: Build log information

        Returns:
            List of TOML lines
        """
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
            # Default aliases
            lines.append('"Generics.Collections" = "System.Generics.Collections"')
            lines.append('"Generics.Defaults" = "System.Generics.Defaults"')
            lines.append('"WinTypes" = "Winapi.Windows"')
            lines.append('"WinProcs" = "Winapi.Windows"')
            lines.append('"SysUtils" = "System.SysUtils"')
            lines.append('"Classes" = "System.Classes"')

        return lines

    def _generate_linux_sdk_section(self, log_info: BuildLogInfo) -> list[str]:
        """Generate [linux_sdk] section for cross-compilation.

        Args:
            log_info: Build log information

        Returns:
            List of TOML lines
        """
        lines = [
            "# " + "=" * 77,
            "# Linux SDK Configuration (for cross-compilation)",
            "# " + "=" * 77,
            "[linux_sdk]",
            "# Linux SDK sysroot and library paths for cross-compilation to Linux64",
            "# These are extracted from IDE build logs when compiling for Linux64 target",
        ]

        # Check if we have SDK info from the build log
        if log_info.sdk_sysroot:
            sysroot_str = self._format_path(log_info.sdk_sysroot)
            lines.append(f'sysroot = "{sysroot_str}"')
        else:
            # Example/placeholder
            lines.append('# sysroot = "C:/Users/${USERNAME}/Documents/Embarcadero/Studio/SDKs/ubuntu22.04.sdk"')

        lines.append("")

        if log_info.sdk_libpaths:
            lines.append("libpaths = [")
            for path in log_info.sdk_libpaths:
                path_str = self._format_path(path)
                lines.append(f'    "{path_str}",')
            lines.append("]")
        else:
            # Example/placeholder
            lines.append("# libpaths = [")
            lines.append('#     "C:/Users/${USERNAME}/Documents/Embarcadero/Studio/SDKs/ubuntu22.04.sdk/usr/lib/gcc/x86_64-linux-gnu/11",')
            lines.append('#     "C:/Users/${USERNAME}/Documents/Embarcadero/Studio/SDKs/ubuntu22.04.sdk/usr/lib/x86_64-linux-gnu",')
            lines.append('#     "C:/Users/${USERNAME}/Documents/Embarcadero/Studio/SDKs/ubuntu22.04.sdk/lib/x86_64-linux-gnu",')
            lines.append('#     "C:/Users/${USERNAME}/Documents/Embarcadero/Studio/SDKs/ubuntu22.04.sdk/lib64",')
            lines.append("# ]")

        return lines

    def _generate_compiler_flags_section(self, log_info: BuildLogInfo) -> list[str]:
        """Generate [compiler.flags] section.

        Args:
            log_info: Build log information

        Returns:
            List of TOML lines
        """
        lines = [
            "# " + "=" * 77,
            "# Compiler Flags",
            "# " + "=" * 77,
            "[compiler.flags]",
            "# Compiler flags extracted from build log",
            "# These flags are passed directly to the compiler",
        ]

        if log_info.compiler_flags:
            flags_str = ", ".join(f'"{flag}"' for flag in log_info.compiler_flags)
            lines.append(f"flags = [{flags_str}]")
        else:
            # Default essential flags
            lines.append('flags = ["--no-config", "-B", "-Q"]')

        return lines

    def _categorize_paths(
        self, paths: list[Path], log_info: BuildLogInfo
    ) -> tuple[list[Path], list[Path]]:
        """Categorize paths into system paths and library paths.

        Args:
            paths: All search paths
            log_info: Build log information

        Returns:
            Tuple of (system_paths, library_paths)
        """
        system_paths = []
        library_paths = []

        # Get Delphi root
        compiler_root = log_info.compiler_path.parent.parent
        compiler_root_str = str(compiler_root).lower()

        for path in paths:
            path_str = str(path).lower()

            # System paths are under Delphi installation directory
            if compiler_root_str in path_str:
                system_paths.append(path)
            else:
                library_paths.append(path)

        return system_paths, library_paths

    def _derive_library_name(self, path: Path, index: int) -> str:
        """Derive a meaningful name for a library from its path.

        Args:
            path: Library path
            index: Index number (fallback)

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
                # Add qualifier if path suggests it
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

        # Last resort: use index
        return f"library_{index}"

    def _format_path(self, path: Path) -> str:
        """Format a path for TOML output, optionally replacing with env vars.

        Args:
            path: Path to format

        Returns:
            Formatted path string
        """
        path_str = str(path)

        # Fix encoding corruption from IDE build logs
        # The IDE sometimes corrupts environment variables like %USERDIR% to ½SUSERDIR%
        # This happens due to character encoding issues (½ is 0xBD, $ is 0x24)
        corrupted_patterns = [
            ("½SUSERDIR%", "${USERDIR}"),
            ("½SUSERNAME%", "${USERNAME}"),
            ("½S", "${"),  # Generic fix for any other corrupted env vars
        ]
        for corrupted, fixed in corrupted_patterns:
            path_str = path_str.replace(corrupted, fixed)

        if self.use_env_vars:
            # Replace common patterns
            username = os.getenv("USERNAME", "")
            if username:
                user_pattern = f"C:\\Users\\{username}"
                path_str = path_str.replace(user_pattern, "C:/Users/${USERNAME}")
                path_str = path_str.replace(user_pattern.lower(), "C:/Users/${USERNAME}")

        # Convert backslashes to forward slashes
        path_str = path_str.replace("\\", "/")

        return path_str


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Generate delphi_config.toml from IDE build log",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.config_generator build.log
  python -m src.config_generator build.log -o my_config.toml
  python -m src.config_generator build.log --no-env-vars
        """,
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
        default="delphi_config.toml",
        help="Output configuration file path (default: delphi_config.toml)",
    )

    parser.add_argument(
        "--no-env-vars",
        action="store_true",
        help="Don't replace paths with environment variables like ${USERNAME}",
    )

    args = parser.parse_args()

    # Convert paths
    build_log_path = Path(args.build_log)
    output_path = Path(args.output)

    # Check if build log exists
    if not build_log_path.exists():
        print(f"Error: Build log file not found: {build_log_path}", file=sys.stderr)
        sys.exit(1)

    # Generate config
    try:
        print(f"Reading build log: {build_log_path}")
        generator = ConfigGenerator(use_env_vars=not args.no_env_vars)
        result = generator.generate_from_build_log(build_log_path, output_path)

        # Print results
        print(f"\n[SUCCESS] {result.message}")
        print(f"\nGenerated: {result.config_file_path}")
        print(f"\nDetected Information:")
        print(f"  Delphi Version: {result.detected_info.delphi_version}")
        print(f"  Platform: {result.detected_info.platform}")
        print(f"  Build Config: {result.detected_info.build_config}")
        print(f"  Compiler: {result.detected_info.compiler_executable}")
        print(f"\nStatistics:")
        print(f"  Total paths found: {result.statistics['total_paths_found']}")
        print(f"  Unique paths: {result.statistics['unique_paths']}")
        print(f"  Compiler flags: {result.statistics['compiler_flags_found']}")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error parsing build log: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
