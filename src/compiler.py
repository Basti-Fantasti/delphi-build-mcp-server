"""Delphi compiler orchestration and execution."""

import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from src.config import ConfigLoader
from src.dproj_parser import DProjParser
from src.models import CompilationError, CompilationResult, CompilationStatistics
from src.output_parser import OutputParser
from src.resource_compiler import ResourceCompiler


class DelphiCompiler:
    """Orchestrates Delphi compilation process."""

    def __init__(self, config_loader: Optional[ConfigLoader] = None):
        """Initialize compiler.

        Args:
            config_loader: Config loader instance. If None, creates a new one.
        """
        self.config_loader = config_loader or ConfigLoader()
        self.config = None

    def compile_project(
        self,
        project_path: Path,
        force_build_all: bool = False,
        override_config: Optional[str] = None,
        override_platform: Optional[str] = None,
        additional_search_paths: Optional[list[str]] = None,
        additional_flags: Optional[list[str]] = None,
    ) -> CompilationResult:
        """Compile a Delphi project.

        Args:
            project_path: Path to .dpr or .dproj file
            force_build_all: Force rebuild all units (-B flag)
            override_config: Override active build config (Debug/Release)
            override_platform: Override active platform (Win32/Win64)
            additional_search_paths: Extra search paths to add
            additional_flags: Additional compiler flags

        Returns:
            CompilationResult with errors and statistics

        Raises:
            FileNotFoundError: If project file not found
            ValueError: If project file is invalid
        """
        # Validate project file
        if not project_path.exists():
            raise FileNotFoundError(f"Project file not found: {project_path}")

        if project_path.suffix.lower() not in [".dpr", ".dpk", ".dproj"]:
            raise ValueError(f"Invalid project file: {project_path}. Expected .dpr, .dpk, or .dproj")

        # Parse .dproj file first to determine platform before loading config
        dproj_path = self._get_dproj_path(project_path)
        dproj_settings = None

        if dproj_path and dproj_path.exists():
            dproj_parser = DProjParser(dproj_path)
            dproj_settings = dproj_parser.parse(override_config, override_platform)
            platform = dproj_settings.active_platform
        else:
            # No .dproj, use override or default to Win32
            platform = override_platform or "Win32"

        # Load configuration with platform so the correct config file is found
        if not self.config:
            self.config_loader = ConfigLoader(platform=platform)
            self.config = self.config_loader.load()

        # Get the actual source file to compile (.dpr or .dpk, not .dproj)
        source_path = self._get_source_path(project_path, dproj_settings)
        if not source_path.exists():
            raise FileNotFoundError(f"Delphi project source file not found: {source_path}")

        # Resource compilation step (before dcc)
        start_time = time.time()
        if dproj_settings and dproj_settings.version_info:
            rc = ResourceCompiler(self.config.delphi.root_path)
            rc_result = rc.compile_version_resource(
                project_name=source_path.stem,
                project_dir=source_path.parent,
                version_info=dproj_settings.version_info,
            )
            if not rc_result.success:
                return CompilationResult(
                    success=False,
                    exit_code=1,
                    errors=[CompilationError(
                        file=f"{source_path.stem}.vrc",
                        line=0,
                        column=0,
                        message=rc_result.error_output or "Resource compilation failed",
                        error_code=None,
                    )],
                    compilation_time_seconds=round(time.time() - start_time, 2),
                )

        # Build compiler command
        compiler_path = self.config_loader.get_compiler_path(platform)
        command = self._build_command(
            compiler_path=compiler_path,
            project_path=source_path,  # Compile the source file (.dpr or .dpk), not .dproj
            dproj_settings=dproj_settings,
            force_build_all=force_build_all,
            additional_search_paths=additional_search_paths or [],
            additional_flags=additional_flags or [],
            platform=platform,
        )

        # Execute compilation
        output, exit_code = self._execute_compiler(command, source_path.parent)
        compilation_time = time.time() - start_time

        # Parse output
        parser = OutputParser()
        errors, statistics = parser.parse(output)

        # Determine output executable path
        output_exe = None
        if exit_code == 0:
            output_exe = self._find_output_executable(project_path, dproj_settings, platform)

        return CompilationResult(
            success=exit_code == 0,
            exit_code=exit_code,
            errors=errors,
            compilation_time_seconds=round(compilation_time, 2),
            output_executable=str(output_exe) if output_exe else None,
            statistics=statistics,
        )

    def _get_dproj_path(self, project_path: Path) -> Optional[Path]:
        """Get .dproj path corresponding to .dpr file.

        Args:
            project_path: Path to .dpr or .dproj file

        Returns:
            Path to .dproj file, or None if not found
        """
        if project_path.suffix.lower() == ".dproj":
            return project_path

        # Look for .dproj with same name
        dproj_path = project_path.with_suffix(".dproj")
        return dproj_path if dproj_path.exists() else None

    def _get_source_path(self, project_path: Path, dproj_settings: Optional[any] = None) -> Path:
        """Get the main source file path to compile.

        This determines the actual source file (.dpr for applications, .dpk for packages)
        by reading the <MainSource> element from the .dproj file if available.

        Args:
            project_path: Path to .dpr, .dpk, or .dproj file
            dproj_settings: Parsed .dproj settings (if available)

        Returns:
            Path to the main source file (.dpr or .dpk)
        """
        # If already a source file (.dpr or .dpk), return it directly
        if project_path.suffix.lower() in [".dpr", ".dpk"]:
            return project_path

        # If we have .dproj settings with main_source, use that
        if dproj_settings and dproj_settings.main_source:
            return project_path.parent / dproj_settings.main_source

        # Fallback: look for .dpr file with same name as .dproj
        return project_path.with_suffix(".dpr")

    def _build_command(
        self,
        compiler_path: Path,
        project_path: Path,
        dproj_settings: Optional[any],
        force_build_all: bool,
        additional_search_paths: list[str],
        additional_flags: list[str],
        platform: str = "Win32",
    ) -> list[str]:
        """Build the complete compiler command line.

        Args:
            compiler_path: Path to compiler executable
            project_path: Path to project file
            dproj_settings: Parsed .dproj settings (if available)
            force_build_all: Whether to force rebuild all
            additional_search_paths: Extra search paths
            additional_flags: Additional compiler flags
            platform: Target platform ("Win32", "Win64", or "Linux64")

        Returns:
            Command as list of arguments
        """
        command = [str(compiler_path)]

        # Add compiler flags from config file (extracted from build log)
        # These include essential flags like --no-config, -$O-, -$W+, etc.
        # Skip flags handled elsewhere: -B/-Q (added below), --syslibroot/--libpath (Linux SDK section)
        skip_flags = {"-B", "-Q", "--syslibroot", "--libpath"}
        config_flags = self.config.compiler.flags.get("flags", [])
        for flag in config_flags:
            if flag not in skip_flags:
                command.append(flag)

        # Add compiler flags from .dproj (like -$O-, -$R+, etc.)
        if dproj_settings:
            for flag in dproj_settings.compiler_flags:
                # Only add if not already present (avoid duplicates)
                if flag not in command:
                    command.append(flag)

            # Add defines
            if dproj_settings.defines:
                defines_str = ";".join(dproj_settings.defines)
                command.append(f"-D{defines_str}")

        # Add build all flag
        if force_build_all:
            command.append("-B")

        # Add quiet flag
        command.append("-Q")

        # Build search paths - merge global config paths with .dproj paths
        all_search_paths = []

        # Add config file paths (global paths from delphi_config.toml)
        all_search_paths.extend(self.config_loader.get_all_search_paths(platform))

        # Add .dproj search paths (project-specific paths)
        if dproj_settings:
            all_search_paths.extend(dproj_settings.unit_search_paths)
            all_search_paths.extend(dproj_settings.include_paths)
            all_search_paths.extend(dproj_settings.resource_paths)

        # Add additional search paths from caller
        all_search_paths.extend([Path(p) for p in additional_search_paths])

        # Deduplicate paths while preserving order
        unique_paths = self._deduplicate_paths(all_search_paths)

        # Add search paths to command
        if unique_paths:
            search_path_str = ";".join(str(p) for p in unique_paths)
            command.append(f"-U{search_path_str}")
            command.append(f"-I{search_path_str}")
            command.append(f"-R{search_path_str}")

        # Add namespace prefixes - merge global config with .dproj namespaces
        namespace_prefixes = self._merge_namespaces(
            self.config.compiler.namespaces.get("prefixes", []),
            dproj_settings.namespace_prefixes if dproj_settings else []
        )

        if namespace_prefixes:
            ns_str = ";".join(namespace_prefixes)
            command.append(f"-NS{ns_str}")

        # Add unit aliases
        if self.config.compiler.aliases:
            alias_parts = []
            for old, new in self.config.compiler.aliases.items():
                alias_parts.append(f"{old}={new}")
            if alias_parts:
                alias_str = ";".join(alias_parts)
                command.append(f"-A{alias_str}")

        # Add output directories
        if dproj_settings:
            if dproj_settings.output_dir:
                command.append(f"-E{dproj_settings.output_dir}")
            if dproj_settings.dcu_output_dir:
                command.append(f"-NU{dproj_settings.dcu_output_dir}")

        # Add Linux SDK options for cross-compilation
        if platform == "Linux64":
            sdk_sysroot = self.config_loader.get_linux_sdk_sysroot()
            sdk_libpaths = self.config_loader.get_linux_sdk_libpaths()

            if sdk_sysroot:
                command.append(f"--syslibroot:{sdk_sysroot}")

            if sdk_libpaths:
                libpath_str = ";".join(str(p) for p in sdk_libpaths)
                command.append(f"--libpath:{libpath_str}")

        # Add additional flags from caller
        command.extend(additional_flags)

        # Add project file (must be last)
        # Use just filename since we're running from project directory
        command.append(project_path.name)

        return command

    def _deduplicate_paths(self, paths: list[Path]) -> list[Path]:
        """Deduplicate paths while preserving order.

        Args:
            paths: List of paths to deduplicate

        Returns:
            Deduplicated list of paths
        """
        unique_paths = []
        seen = set()
        for path in paths:
            # Normalize path for comparison (case-insensitive on Windows)
            path_str = str(path).lower().replace("/", "\\")
            if path_str not in seen:
                seen.add(path_str)
                unique_paths.append(path)
        return unique_paths

    def _merge_namespaces(self, config_namespaces: list[str], dproj_namespaces: list[str]) -> list[str]:
        """Merge namespace lists without duplicates while preserving order.

        Config namespaces come first, then any additional dproj namespaces.

        Args:
            config_namespaces: Namespaces from config file
            dproj_namespaces: Namespaces from .dproj file

        Returns:
            Merged list of unique namespaces
        """
        merged = []
        seen = set()

        # Add config namespaces first
        for ns in config_namespaces:
            ns_lower = ns.lower()
            if ns_lower not in seen:
                seen.add(ns_lower)
                merged.append(ns)

        # Add dproj namespaces (only if not already present)
        for ns in dproj_namespaces:
            ns_lower = ns.lower()
            if ns_lower not in seen:
                seen.add(ns_lower)
                merged.append(ns)

        return merged

    def _execute_compiler(self, command: list[str], working_dir: Path) -> tuple[str, int]:
        """Execute the compiler and capture output.

        Uses a response file (@file.rsp) if command line is too long.

        Args:
            command: Compiler command as list
            working_dir: Working directory for execution

        Returns:
            Tuple of (output string, exit code)
        """
        try:
            # Check if command line is too long (Windows limit is ~8191 characters)
            # Calculate full command line length
            command_line = " ".join(command)
            use_response_file = len(command_line) > 8000

            if use_response_file:
                # Create a temporary response file
                response_file = working_dir / "delphi_compile.rsp"

                # Write all arguments (except compiler executable) to response file
                # Each argument on its own line
                with open(response_file, "w", encoding="utf-8") as f:
                    for arg in command[1:]:  # Skip compiler executable
                        # Quote arguments that contain spaces
                        if " " in arg and not arg.startswith('"'):
                            f.write(f'"{arg}"\n')
                        else:
                            f.write(f"{arg}\n")

                # Build new command using response file
                actual_command = [command[0], f"@{response_file.name}"]
            else:
                actual_command = command
                response_file = None

            # Execute compilation with timeout (5 minutes max)
            result = subprocess.run(
                actual_command,
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )

            # Combine stdout and stderr
            output = result.stdout + "\n" + result.stderr

            # Clean up response file if we created one
            if response_file and response_file.exists():
                response_file.unlink()

            return output, result.returncode

        except subprocess.TimeoutExpired:
            return "Compilation timed out after 5 minutes", 1
        except Exception as e:
            return f"Compiler execution failed: {e}", 1

    def _find_output_executable(
        self, project_path: Path, dproj_settings: Optional[any], platform: str = "Win32"
    ) -> Optional[Path]:
        """Find the output executable or package library after successful compilation.

        Args:
            project_path: Project file path
            dproj_settings: .dproj settings (if available)
            platform: Target platform ("Win32", "Win64", or "Linux64")

        Returns:
            Path to output file (.exe, .bpl, or Linux executable), or None if not found
        """
        # Determine if this is a package based on main_source extension
        is_package = False
        if dproj_settings and dproj_settings.main_source:
            is_package = dproj_settings.main_source.lower().endswith(".dpk")
        elif project_path.suffix.lower() == ".dpk":
            is_package = True

        # Determine file extension based on platform and project type
        if platform == "Linux64":
            # Linux executables/libraries have no extension (or .so for shared libs)
            exe_extension = ".so" if is_package else ""
        else:
            # Windows: .bpl for packages, .exe for applications
            exe_extension = ".bpl" if is_package else ".exe"

        # Check if .dproj specifies output directory
        if dproj_settings and dproj_settings.output_dir:
            exe_name = project_path.stem + exe_extension
            exe_path = dproj_settings.output_dir / exe_name
            if exe_path.exists():
                return exe_path

        # Check default location (same directory as project)
        if exe_extension:
            exe_path = project_path.with_suffix(exe_extension)
        else:
            exe_path = project_path.with_suffix("")
        if exe_path.exists():
            return exe_path

        # Check platform-specific directories
        project_dir = project_path.parent
        exe_name = project_path.stem + exe_extension

        # Platform-specific subdirectories to search
        subdirs = []
        if platform == "Win32":
            subdirs = ["Win32/Debug", "Win32/Release"]
        elif platform == "Win64":
            subdirs = ["Win64/Debug", "Win64/Release"]
        elif platform == "Win64x":
            subdirs = ["Win64x/Debug", "Win64x/Release"]
        elif platform == "Linux64":
            subdirs = ["Linux64/Debug", "Linux64/Release"]

        for subdir in subdirs:
            exe_path = project_dir / subdir / exe_name
            if exe_path.exists():
                return exe_path

        return None
