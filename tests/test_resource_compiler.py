"""Tests for resource compiler module."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.models import VersionInfo
from src.resource_compiler import ResourceCompiler, VrcGenerator


class TestVrcGenerator:
    """Tests for .vrc file content generation."""

    def test_generates_versioninfo_block(self):
        """Test generated content contains VERSIONINFO block."""
        vi = VersionInfo(
            major=1, minor=2, release=3, build=4,
            locale=1033,
            keys={"CompanyName": "TestCo", "FileDescription": "TestApp"},
        )
        content = VrcGenerator.generate("TestApp", vi)
        assert "1 VERSIONINFO" in content
        assert "FILEVERSION 1,2,3,4" in content
        assert "PRODUCTVERSION 1,2,3,4" in content

    def test_contains_string_file_info(self):
        """Test generated content contains StringFileInfo block."""
        vi = VersionInfo(
            major=1, minor=0, release=0, build=0,
            keys={"CompanyName": "TestCo", "FileDescription": "TestApp"},
        )
        content = VrcGenerator.generate("TestApp", vi)
        assert 'BLOCK "StringFileInfo"' in content
        assert 'VALUE "CompanyName"' in content
        assert 'VALUE "FileDescription"' in content

    def test_contains_var_file_info(self):
        """Test generated content contains VarFileInfo block."""
        vi = VersionInfo(locale=1033)
        content = VrcGenerator.generate("TestApp", vi)
        assert 'BLOCK "VarFileInfo"' in content
        assert "VALUE \"Translation\"" in content

    def test_locale_affects_translation(self):
        """Test locale ID affects Translation value."""
        vi_us = VersionInfo(locale=1033)  # US English
        vi_de = VersionInfo(locale=1031)  # German
        content_us = VrcGenerator.generate("App", vi_us)
        content_de = VrcGenerator.generate("App", vi_de)
        assert "0x0409" in content_us  # 1033 = 0x0409
        assert "0x0407" in content_de  # 1031 = 0x0407

    def test_locale_affects_string_block_id(self):
        """Test locale ID affects the StringFileInfo block identifier."""
        vi_us = VersionInfo(locale=1033)
        vi_de = VersionInfo(locale=1031)
        content_us = VrcGenerator.generate("App", vi_us)
        content_de = VrcGenerator.generate("App", vi_de)
        assert 'BLOCK "040904E4"' in content_us  # 0409 = US English
        assert 'BLOCK "040704E4"' in content_de  # 0407 = German

    def test_file_version_in_keys(self):
        """Test FileVersion key matches version numbers."""
        vi = VersionInfo(
            major=2, minor=5, release=1, build=42,
            keys={"FileVersion": "2.5.1.42"},
        )
        content = VrcGenerator.generate("App", vi)
        assert '"2.5.1.42\\0"' in content or '"2.5.1.42' in content

    def test_empty_keys_still_valid(self):
        """Test generation works with no keys (minimal valid .vrc)."""
        vi = VersionInfo(major=1, minor=0, release=0, build=0)
        content = VrcGenerator.generate("App", vi)
        assert "1 VERSIONINFO" in content
        assert "FILEVERSION 1,0,0,0" in content


class TestResourceCompiler:
    """Tests for ResourceCompiler (cgrc.exe execution)."""

    def test_cgrc_not_found_returns_error(self):
        """Test error when cgrc.exe does not exist."""
        rc = ResourceCompiler(delphi_root=Path("/nonexistent/delphi"))
        vi = VersionInfo(major=1)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = rc.compile_version_resource("App", Path(tmpdir), vi)
        assert result.success is False
        assert "not found" in result.error_output

    @patch("src.resource_compiler.subprocess.run")
    def test_successful_compilation(self, mock_run):
        """Test successful resource compilation."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            # Create fake cgrc.exe
            cgrc_dir = tmpdir_path / "bin"
            cgrc_dir.mkdir()
            cgrc_path = cgrc_dir / "cgrc.exe"
            cgrc_path.write_text("fake")

            rc = ResourceCompiler(delphi_root=tmpdir_path)
            vi = VersionInfo(major=1, minor=0, release=0, build=0)
            result = rc.compile_version_resource("TestApp", tmpdir_path, vi)

        assert result.success is True
        assert result.res_file is not None
        assert "TestApp.res" in result.res_file

    @patch("src.resource_compiler.subprocess.run")
    def test_compilation_failure(self, mock_run):
        """Test resource compiler returns non-zero exit code."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="fatal error RC1015"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            cgrc_dir = tmpdir_path / "bin"
            cgrc_dir.mkdir()
            (cgrc_dir / "cgrc.exe").write_text("fake")

            rc = ResourceCompiler(delphi_root=tmpdir_path)
            vi = VersionInfo(major=1)
            result = rc.compile_version_resource("App", tmpdir_path, vi)

        assert result.success is False
        assert "fatal error" in result.error_output

    @patch("src.resource_compiler.subprocess.run")
    def test_command_includes_utf8_codepage(self, mock_run):
        """Test cgrc.exe command includes -c65001 for UTF-8."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            cgrc_dir = tmpdir_path / "bin"
            cgrc_dir.mkdir()
            (cgrc_dir / "cgrc.exe").write_text("fake")

            rc = ResourceCompiler(delphi_root=tmpdir_path)
            vi = VersionInfo(major=1)
            rc.compile_version_resource("App", tmpdir_path, vi)

        args = mock_run.call_args[0][0]
        assert "-c65001" in args
        assert "-foApp.res" in args

    @patch("src.resource_compiler.subprocess.run")
    def test_vrc_file_cleaned_up(self, mock_run):
        """Test .vrc file is deleted after compilation."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            cgrc_dir = tmpdir_path / "bin"
            cgrc_dir.mkdir()
            (cgrc_dir / "cgrc.exe").write_text("fake")

            rc = ResourceCompiler(delphi_root=tmpdir_path)
            vi = VersionInfo(major=1)
            rc.compile_version_resource("App", tmpdir_path, vi)

            vrc_path = tmpdir_path / "App.vrc"
            assert not vrc_path.exists()
