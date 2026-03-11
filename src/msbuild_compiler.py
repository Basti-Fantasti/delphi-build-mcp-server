"""MSBuild compiler orchestration for Windows Delphi targets."""

import subprocess
import time
from pathlib import Path
from typing import Optional

from src.models import CompilationError, CompilationResult, CompilationStatistics, DProjSettings
from src.msbuild_output_parser import MsBuildOutputParser
from src.rsvars_parser import RsvarsParser


class MsBuildCompiler:
    """Orchestrates Delphi compilation via MSBuild for Windows targets."""

    def __init__(self, delphi_root: Path):
        self.delphi_root = delphi_root
        self.rsvars_path = delphi_root / "bin" / "rsvars.bat"

    def compile_project(
        self,
        project_path: Path,
        dproj_settings: DProjSettings,
        force_build_all: bool = False,
        additional_search_paths: Optional[list[str]] = None,
        additional_flags: Optional[list[str]] = None,
    ) -> CompilationResult:
        start_time = time.time()
        additional_search_paths = additional_search_paths or []
        additional_flags = additional_flags or []

        warnings_text = self._build_warnings(additional_search_paths, additional_flags)

        try:
            env = self._setup_environment()
        except FileNotFoundError as e:
            return CompilationResult(
                success=False,
                exit_code=1,
                errors=[CompilationError(
                    file="rsvars.bat", line=0, column=0,
                    message=str(e), error_code=None,
                )],
                compilation_time_seconds=round(time.time() - start_time, 2),
            )

        msbuild_path = self._find_msbuild(env)
        command = self._build_command(project_path, dproj_settings, force_build_all, msbuild_path)
        output, exit_code = self._execute(command, project_path.parent, env)

        if warnings_text:
            output = warnings_text + "\n" + output

        parser = MsBuildOutputParser()
        errors, statistics = parser.parse(output)

        compilation_time = time.time() - start_time

        output_exe = None
        if exit_code == 0:
            output_exe = self._find_output_executable(project_path, dproj_settings)

        return CompilationResult(
            success=exit_code == 0,
            exit_code=exit_code,
            errors=errors,
            compilation_time_seconds=round(compilation_time, 2),
            output_executable=str(output_exe) if output_exe else None,
            statistics=statistics,
        )

    def _setup_environment(self) -> dict[str, str]:
        parser = RsvarsParser(self.rsvars_path)
        return parser.build_msbuild_env()

    def _find_msbuild(self, env: dict[str, str]) -> Path:
        framework_dir = env.get("FrameworkDir", "")
        if framework_dir:
            return Path(framework_dir) / "MSBuild.exe"
        return Path("msbuild.exe")

    def _build_command(
        self,
        project_path: Path,
        dproj_settings: DProjSettings,
        force_build_all: bool,
        msbuild_path: Optional[Path] = None,
    ) -> list[str]:
        exe = str(msbuild_path) if msbuild_path else "msbuild.exe"
        target = "/t:Rebuild" if force_build_all else "/t:Build"
        return [
            exe,
            str(project_path),
            target,
            f"/p:Config={dproj_settings.active_config}",
            f"/p:Platform={dproj_settings.active_platform}",
            "/v:normal",
        ]

    def _build_warnings(
        self, additional_search_paths: list[str], additional_flags: list[str],
    ) -> str:
        warnings = []
        if additional_search_paths:
            warnings.append("Warning: additional_search_paths ignored - MSBuild reads paths from .dproj")
        if additional_flags:
            warnings.append("Warning: additional_flags ignored - MSBuild reads flags from .dproj")
        return "\n".join(warnings)

    def _execute(
        self, command: list[str], working_dir: Path, env: dict[str, str],
    ) -> tuple[str, int]:
        try:
            result = subprocess.run(
                command, cwd=str(working_dir), capture_output=True, text=True,
                encoding="utf-8", errors="replace", env=env, timeout=600,
            )
            output = result.stdout + "\n" + result.stderr
            return output, result.returncode
        except FileNotFoundError:
            return self._execute_cmd_fallback(command, working_dir)
        except subprocess.TimeoutExpired:
            return "MSBuild compilation timed out after 10 minutes", 1
        except Exception as e:
            return f"MSBuild execution failed: {e}", 1

    def _execute_cmd_fallback(
        self, command: list[str], working_dir: Path,
    ) -> tuple[str, int]:
        try:
            rsvars = str(self.rsvars_path)
            msbuild_args = " ".join(f'"{arg}"' if " " in arg else arg for arg in command)
            cmd_line = f'call "{rsvars}" && {msbuild_args}'
            result = subprocess.run(
                ["cmd.exe", "/c", cmd_line], cwd=str(working_dir),
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
            )
            output = result.stdout + "\n" + result.stderr
            return output, result.returncode
        except subprocess.TimeoutExpired:
            return "MSBuild compilation timed out after 10 minutes (cmd fallback)", 1
        except Exception as e:
            return f"MSBuild cmd fallback failed: {e}", 1

    def _find_output_executable(
        self, project_path: Path, dproj_settings: DProjSettings
    ) -> Optional[Path]:
        platform = dproj_settings.active_platform
        is_package = False
        if dproj_settings.main_source:
            is_package = dproj_settings.main_source.lower().endswith(".dpk")
        ext = ".bpl" if is_package else ".exe"

        if dproj_settings.output_dir:
            exe_path = dproj_settings.output_dir / (project_path.stem + ext)
            if exe_path.exists():
                return exe_path

        exe_path = project_path.with_suffix(ext)
        if exe_path.exists():
            return exe_path

        config = dproj_settings.active_config
        subdir = f"{platform}/{config}"
        exe_path = project_path.parent / subdir / (project_path.stem + ext)
        if exe_path.exists():
            return exe_path

        return None
