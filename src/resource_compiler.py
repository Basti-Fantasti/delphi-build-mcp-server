"""Resource compiler for Delphi version resources."""

import subprocess
from pathlib import Path
from typing import Optional

from src.models import ResourceCompilationResult, VersionInfo


class VrcGenerator:
    """Generates .vrc (version resource script) content from VersionInfo."""

    @staticmethod
    def generate(project_name: str, version_info: VersionInfo) -> str:
        """Generate .vrc file content.

        Args:
            project_name: Project name (used for default values)
            version_info: Version information

        Returns:
            String containing the .vrc file content (Windows RC format)
        """
        vi = version_info
        locale_hex = f"{vi.locale:04X}"
        codepage = "04E4"  # Windows Latin-1 (1252)

        lines = [
            "1 VERSIONINFO",
            f"FILEVERSION {vi.major},{vi.minor},{vi.release},{vi.build}",
            f"PRODUCTVERSION {vi.major},{vi.minor},{vi.release},{vi.build}",
            "FILEFLAGSMASK 0x3FL",
            "FILEFLAGS 0x0L",
            "FILEOS 0x40004L",
            "FILETYPE 0x1L",
            "FILESUBTYPE 0x0L",
            "BEGIN",
            '  BLOCK "StringFileInfo"',
            "  BEGIN",
            f'    BLOCK "{locale_hex}{codepage}"',
            "    BEGIN",
        ]

        # Add key-value pairs
        for key, value in vi.keys.items():
            if value:
                lines.append(f'      VALUE "{key}", "{value}\\0"')
            else:
                lines.append(f'      VALUE "{key}", "\\0"')

        lines.extend([
            "    END",
            "  END",
            '  BLOCK "VarFileInfo"',
            "  BEGIN",
            f"    VALUE \"Translation\", 0x{locale_hex} 0x{codepage}",
            "  END",
            "END",
            "",
        ])

        return "\n".join(lines)


class ResourceCompiler:
    """Compiles version resources using cgrc.exe."""

    def __init__(self, delphi_root: Path):
        """Initialize resource compiler.

        Args:
            delphi_root: Delphi installation root directory
        """
        self.cgrc_path = delphi_root / "bin" / "cgrc.exe"

    def compile_version_resource(
        self,
        project_name: str,
        project_dir: Path,
        version_info: VersionInfo,
    ) -> ResourceCompilationResult:
        """Generate .vrc and compile to .res.

        Args:
            project_name: Project name (without extension)
            project_dir: Directory containing the project
            version_info: Version information from .dproj

        Returns:
            ResourceCompilationResult with success/failure info
        """
        if not self.cgrc_path.exists():
            return ResourceCompilationResult(
                success=False,
                error_output=f"Resource compiler not found: {self.cgrc_path}",
            )

        vrc_path = project_dir / f"{project_name}.vrc"
        res_path = project_dir / f"{project_name}.res"

        try:
            # Generate .vrc content
            vrc_content = VrcGenerator.generate(project_name, version_info)
            vrc_path.write_text(vrc_content, encoding="utf-8")

            # Execute cgrc.exe
            command = [
                str(self.cgrc_path),
                "-c65001",  # UTF-8 codepage
                str(vrc_path.name),
                f"-fo{res_path.name}",
            ]

            result = subprocess.run(
                command,
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )

            if result.returncode != 0:
                error_output = (result.stdout + "\n" + result.stderr).strip()
                return ResourceCompilationResult(
                    success=False,
                    error_output=f"Resource compiler failed:\n{error_output}",
                )

            return ResourceCompilationResult(
                success=True,
                res_file=str(res_path),
            )

        except subprocess.TimeoutExpired:
            return ResourceCompilationResult(
                success=False,
                error_output="Resource compiler timed out after 30 seconds",
            )
        except Exception as e:
            return ResourceCompilationResult(
                success=False,
                error_output=f"Resource compiler execution failed: {e}",
            )
        finally:
            # Clean up .vrc file (matches IDE behavior)
            if vrc_path.exists():
                try:
                    vrc_path.unlink()
                except OSError:
                    pass
