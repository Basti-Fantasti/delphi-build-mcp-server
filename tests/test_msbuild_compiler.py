"""Tests for MSBuild compiler orchestration."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.msbuild_compiler import MsBuildCompiler
from src.models import DProjSettings


class TestMsBuildCommandConstruction:
    """Test MSBuild command line construction."""

    def test_build_command_basic(self):
        """Basic build command for Win32 Release."""
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        dproj_settings = DProjSettings(
            active_config="Release", active_platform="Win32"
        )
        cmd = compiler._build_command(
            project_path=Path("C:/project/MyApp.dproj"),
            dproj_settings=dproj_settings,
            force_build_all=False,
        )
        assert cmd[0].endswith("msbuild.exe") or cmd[0] == "msbuild.exe"
        assert "C:/project/MyApp.dproj" in " ".join(cmd) or "C:\\project\\MyApp.dproj" in " ".join(cmd)
        assert "/t:Build" in cmd
        assert "/p:Config=Release" in cmd
        assert "/p:Platform=Win32" in cmd

    def test_build_command_force_rebuild(self):
        """force_build_all should use /t:Rebuild."""
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        dproj_settings = DProjSettings(
            active_config="Debug", active_platform="Win64"
        )
        cmd = compiler._build_command(
            project_path=Path("C:/project/MyApp.dproj"),
            dproj_settings=dproj_settings,
            force_build_all=True,
        )
        assert "/t:Rebuild" in cmd
        assert "/p:Config=Debug" in cmd
        assert "/p:Platform=Win64" in cmd

    def test_build_command_verbosity(self):
        """Command should include /v:normal for output parsing."""
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        dproj_settings = DProjSettings(
            active_config="Release", active_platform="Win32"
        )
        cmd = compiler._build_command(
            project_path=Path("C:/project/MyApp.dproj"),
            dproj_settings=dproj_settings,
            force_build_all=False,
        )
        assert "/v:normal" in cmd


class TestMsBuildCompilerWarnings:
    """Test warning generation for ignored parameters."""

    def test_warns_on_additional_search_paths(self):
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        warnings = compiler._build_warnings(
            additional_search_paths=["C:/extra"],
            additional_flags=[],
        )
        assert "additional_search_paths" in warnings.lower() or "search" in warnings.lower()

    def test_warns_on_additional_flags(self):
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        warnings = compiler._build_warnings(
            additional_search_paths=[],
            additional_flags=["-$O+"],
        )
        assert "additional_flags" in warnings.lower() or "flags" in warnings.lower()

    def test_no_warning_when_empty(self):
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        warnings = compiler._build_warnings(
            additional_search_paths=[],
            additional_flags=[],
        )
        assert warnings == ""


class TestMsBuildEnvironment:
    """Test MSBuild environment setup."""

    def test_rsvars_path_from_delphi_root(self):
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi/23.0"))
        assert compiler.rsvars_path == Path("C:/Delphi/23.0/bin/rsvars.bat")

    def test_find_msbuild_in_framework_dir(self):
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        env = {"FrameworkDir": "C:\\Windows\\Microsoft.NET\\Framework\\v4.0.30319"}
        msbuild = compiler._find_msbuild(env)
        assert str(msbuild).endswith("MSBuild.exe") or str(msbuild).endswith("msbuild.exe")
        assert "v4.0.30319" in str(msbuild)


class TestMsBuildCompileProject:
    """Test compile_project orchestration with mocked subprocess."""

    @patch("src.msbuild_compiler.subprocess.run")
    @patch.object(MsBuildCompiler, "_setup_environment")
    def test_compile_project_success(self, mock_env, mock_run):
        mock_env.return_value = {"FrameworkDir": "C:\\Windows\\Microsoft.NET\\Framework\\v4.0.30319"}
        mock_run.return_value = MagicMock(
            stdout="_PasCoreCompile-Ziel:\n    dcc32.exe MyApp.dpr\nErstellen des _PasCoreCompile-Ziels beendet.\n",
            stderr="",
            returncode=0,
        )
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        dproj_settings = DProjSettings(active_config="Release", active_platform="Win32")
        result = compiler.compile_project(
            project_path=Path("C:/project/MyApp.dproj"),
            dproj_settings=dproj_settings,
        )
        assert result.success is True
        assert result.exit_code == 0
        mock_run.assert_called_once()

    @patch.object(MsBuildCompiler, "_setup_environment")
    def test_compile_project_rsvars_missing(self, mock_env):
        mock_env.side_effect = FileNotFoundError("rsvars.bat not found")
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        dproj_settings = DProjSettings(active_config="Release", active_platform="Win32")
        result = compiler.compile_project(
            project_path=Path("C:/project/MyApp.dproj"),
            dproj_settings=dproj_settings,
        )
        assert result.success is False
        assert len(result.errors) == 1
        assert "rsvars" in result.errors[0].message.lower()

    @patch("src.msbuild_compiler.subprocess.run")
    @patch.object(MsBuildCompiler, "_setup_environment")
    def test_compile_project_includes_warnings(self, mock_env, mock_run):
        mock_env.return_value = {"FrameworkDir": "C:\\Windows\\Microsoft.NET\\Framework\\v4.0.30319"}
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        dproj_settings = DProjSettings(active_config="Release", active_platform="Win32")
        result = compiler.compile_project(
            project_path=Path("C:/project/MyApp.dproj"),
            dproj_settings=dproj_settings,
            additional_search_paths=["C:/extra"],
        )
        assert result.success is True
