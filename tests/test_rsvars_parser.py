"""Tests for rsvars.bat parser."""

import os
import tempfile
from pathlib import Path

import pytest

from src.rsvars_parser import RsvarsParser


class TestRsvarsParser:
    """Tests for parsing rsvars.bat environment variables."""

    def _write_rsvars(self, content: str) -> Path:
        """Write rsvars.bat content to a temp file and return path."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".bat", delete=False, encoding="utf-8"
        )
        f.write(content)
        f.close()
        return Path(f.name)

    def test_parse_simple_set(self):
        """Parse basic @SET assignments."""
        path = self._write_rsvars(
            '@SET BDS=C:\\Delphi\n@SET LANGDIR=DE\n'
        )
        try:
            parser = RsvarsParser(path)
            env = parser.parse()
            assert env["BDS"] == "C:\\Delphi"
            assert env["LANGDIR"] == "DE"
        finally:
            os.unlink(path)

    def test_parse_empty_value(self):
        """Empty values should be set as empty strings."""
        path = self._write_rsvars('@SET PLATFORM=\n')
        try:
            parser = RsvarsParser(path)
            env = parser.parse()
            assert env["PLATFORM"] == ""
        finally:
            os.unlink(path)

    def test_parse_path_with_variable_expansion(self):
        """Variables like %BDS% should be expanded using already-parsed values."""
        path = self._write_rsvars(
            '@SET BDS=C:\\Delphi\n'
            '@SET MYPATH=%BDS%\\bin\n'
        )
        try:
            parser = RsvarsParser(path)
            env = parser.parse()
            assert env["MYPATH"] == "C:\\Delphi\\bin"
        finally:
            os.unlink(path)

    def test_parse_path_with_existing_env_var(self):
        """Variables referencing existing env vars (like %PATH%) should expand them."""
        path = self._write_rsvars(
            '@SET MYVAR=new_value;%PATH%\n'
        )
        try:
            parser = RsvarsParser(path)
            env = parser.parse()
            assert env["MYVAR"].startswith("new_value;")
        finally:
            os.unlink(path)

    def test_skip_non_set_lines(self):
        """Lines that are not @SET should be ignored."""
        path = self._write_rsvars(
            'REM This is a comment\n'
            '@SET BDS=C:\\Delphi\n'
            ':: another comment\n'
            '\n'
        )
        try:
            parser = RsvarsParser(path)
            env = parser.parse()
            assert env["BDS"] == "C:\\Delphi"
            assert len(env) == 1
        finally:
            os.unlink(path)

    def test_case_insensitive_set_keyword(self):
        """@set, @SET, @Set should all work."""
        path = self._write_rsvars(
            '@set BDS=C:\\Delphi\n'
            '@Set LANGDIR=EN\n'
        )
        try:
            parser = RsvarsParser(path)
            env = parser.parse()
            assert env["BDS"] == "C:\\Delphi"
            assert env["LANGDIR"] == "EN"
        finally:
            os.unlink(path)

    def test_parse_with_utf8_bom(self):
        """rsvars.bat with UTF-8 BOM should parse correctly."""
        f = tempfile.NamedTemporaryFile(
            mode="wb", suffix=".bat", delete=False
        )
        # Write BOM + content
        f.write(b'\xef\xbb\xbf@SET BDS=C:\\Delphi\n')
        f.close()
        path = Path(f.name)
        try:
            parser = RsvarsParser(path)
            env = parser.parse()
            assert env["BDS"] == "C:\\Delphi"
        finally:
            os.unlink(path)

    def test_file_not_found_raises(self):
        """Should raise FileNotFoundError if rsvars.bat doesn't exist."""
        parser = RsvarsParser(Path("C:/nonexistent/rsvars.bat"))
        with pytest.raises(FileNotFoundError):
            parser.parse()

    def test_build_msbuild_env_merges_with_os_env(self):
        """build_msbuild_env should merge parsed vars onto os.environ."""
        path = self._write_rsvars(
            '@SET BDS=C:\\Delphi\n'
            '@SET LANGDIR=DE\n'
        )
        try:
            parser = RsvarsParser(path)
            full_env = parser.build_msbuild_env()
            assert full_env["BDS"] == "C:\\Delphi"
            # Check for a common OS env var (case-insensitive check for cross-platform)
            env_keys_lower = {k.lower() for k in full_env}
            assert "systemroot" in env_keys_lower or "home" in env_keys_lower
        finally:
            os.unlink(path)

    def test_parse_real_rsvars_format(self):
        """Parse a realistic rsvars.bat matching Delphi 12.3 format."""
        content = (
            '@SET BDS=C:\\Program Files (x86)\\Embarcadero\\Studio\\23.0\n'
            '@SET BDSINCLUDE=C:\\Program Files (x86)\\Embarcadero\\Studio\\23.0\\include\n'
            '@SET BDSCOMMONDIR=C:\\Users\\Public\\Documents\\Embarcadero\\Studio\\23.0\n'
            '@SET FrameworkDir=C:\\Windows\\Microsoft.NET\\Framework\\v4.0.30319\n'
            '@SET FrameworkVersion=v4.5\n'
            '@SET FrameworkSDKDir=\n'
            '@SET PATH=%FrameworkDir%;%FrameworkSDKDir%;%BDS%\\bin;%BDS%\\bin64;%BDS%\\cmake;%PATH%\n'
            '@SET LANGDIR=DE\n'
            '@SET PLATFORM=\n'
            '@SET PlatformSDK=\n'
        )
        path = self._write_rsvars(content)
        try:
            parser = RsvarsParser(path)
            env = parser.parse()
            assert env["BDS"] == "C:\\Program Files (x86)\\Embarcadero\\Studio\\23.0"
            assert env["FrameworkVersion"] == "v4.5"
            assert env["LANGDIR"] == "DE"
            assert env["PLATFORM"] == ""
            assert "v4.0.30319" in env["PATH"]
            assert "Embarcadero" in env["PATH"]
        finally:
            os.unlink(path)
