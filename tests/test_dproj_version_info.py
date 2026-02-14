"""Tests for version info extraction from .dproj files."""

import tempfile
from pathlib import Path

import pytest

from src.dproj_parser import DProjParser
from src.models import VersionInfo


# Minimal .dproj with VerInfo_Keys style (newer format)
DPROJ_VERINFO_KEYS = """\
<?xml version="1.0" encoding="utf-8"?>
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
    <PropertyGroup>
        <MainSource>TestApp.dpr</MainSource>
        <Configuration Condition="'$(Configuration)'==''">Debug</Configuration>
        <Platform Condition="'$(Platform)'==''">Win32</Platform>
        <ProjectGuid>{TEST-GUID}</ProjectGuid>
    </PropertyGroup>
    <PropertyGroup Condition="'$(Base)'!=''">
        <VerInfo_Locale>1031</VerInfo_Locale>
        <VerInfo_Keys>CompanyName=TestCo;FileDescription=Test Application;FileVersion=2.5.1.42;InternalName=;LegalCopyright=Copyright 2024;LegalTrademarks=;OriginalFilename=;ProductName=TestApp;ProductVersion=2.5.0.0;Comments=</VerInfo_Keys>
    </PropertyGroup>
    <ItemGroup>
        <BuildConfiguration Include="Debug">
            <Key>Cfg_1</Key>
        </BuildConfiguration>
        <BuildConfiguration Include="Release">
            <Key>Cfg_2</Key>
        </BuildConfiguration>
    </ItemGroup>
</Project>
"""

# Minimal .dproj with individual VerInfo_* properties (older format)
DPROJ_VERINFO_INDIVIDUAL = """\
<?xml version="1.0" encoding="utf-8"?>
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
    <PropertyGroup>
        <MainSource>TestApp.dpr</MainSource>
        <Configuration Condition="'$(Configuration)'==''">Debug</Configuration>
        <Platform Condition="'$(Platform)'==''">Win32</Platform>
        <ProjectGuid>{TEST-GUID}</ProjectGuid>
    </PropertyGroup>
    <PropertyGroup Condition="'$(Base)'!=''">
        <VerInfo_MajorVer>3</VerInfo_MajorVer>
        <VerInfo_MinorVer>6</VerInfo_MinorVer>
        <VerInfo_Release>1</VerInfo_Release>
        <VerInfo_Build>316</VerInfo_Build>
        <VerInfo_Locale>1033</VerInfo_Locale>
        <VerInfo_Keys>CompanyName=OldCo;FileDescription=Old App;FileVersion=3.6.1.316;InternalName=;LegalCopyright=;LegalTrademarks=;OriginalFilename=;ProductName=OldApp;ProductVersion=3.6.0.0;Comments=</VerInfo_Keys>
    </PropertyGroup>
    <ItemGroup>
        <BuildConfiguration Include="Debug">
            <Key>Cfg_1</Key>
        </BuildConfiguration>
        <BuildConfiguration Include="Release">
            <Key>Cfg_2</Key>
        </BuildConfiguration>
    </ItemGroup>
</Project>
"""

# Minimal .dproj with VerInfo_IncludeVerInfo=false
DPROJ_VERINFO_DISABLED = """\
<?xml version="1.0" encoding="utf-8"?>
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
    <PropertyGroup>
        <MainSource>TestApp.dpr</MainSource>
        <Configuration Condition="'$(Configuration)'==''">Debug</Configuration>
        <Platform Condition="'$(Platform)'==''">Win32</Platform>
        <ProjectGuid>{TEST-GUID}</ProjectGuid>
    </PropertyGroup>
    <PropertyGroup Condition="'$(Base)'!=''">
        <VerInfo_IncludeVerInfo>false</VerInfo_IncludeVerInfo>
        <VerInfo_Keys>CompanyName=;FileVersion=1.0.0.0</VerInfo_Keys>
    </PropertyGroup>
    <ItemGroup>
        <BuildConfiguration Include="Debug">
            <Key>Cfg_1</Key>
        </BuildConfiguration>
    </ItemGroup>
</Project>
"""

# Minimal .dproj without any VerInfo
DPROJ_NO_VERINFO = """\
<?xml version="1.0" encoding="utf-8"?>
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
    <PropertyGroup>
        <MainSource>TestApp.dpr</MainSource>
        <Configuration Condition="'$(Configuration)'==''">Debug</Configuration>
        <Platform Condition="'$(Platform)'==''">Win32</Platform>
        <ProjectGuid>{TEST-GUID}</ProjectGuid>
    </PropertyGroup>
    <ItemGroup>
        <BuildConfiguration Include="Debug">
            <Key>Cfg_1</Key>
        </BuildConfiguration>
    </ItemGroup>
</Project>
"""


class TestDProjVersionInfoKeys:
    """Tests for VerInfo_Keys style extraction."""

    def _parse_dproj(self, content: str) -> "DProjSettings":
        with tempfile.TemporaryDirectory() as tmpdir:
            dproj_path = Path(tmpdir) / "TestApp.dproj"
            dproj_path.write_text(content, encoding="utf-8")
            parser = DProjParser(dproj_path)
            return parser.parse()

    def test_extracts_version_from_keys(self):
        """Test version numbers extracted from FileVersion in VerInfo_Keys."""
        settings = self._parse_dproj(DPROJ_VERINFO_KEYS)
        assert settings.version_info is not None
        assert settings.version_info.major == 2
        assert settings.version_info.minor == 5
        assert settings.version_info.release == 1
        assert settings.version_info.build == 42

    def test_extracts_locale(self):
        """Test locale extracted from VerInfo_Locale."""
        settings = self._parse_dproj(DPROJ_VERINFO_KEYS)
        assert settings.version_info.locale == 1031

    def test_extracts_keys(self):
        """Test key-value pairs extracted from VerInfo_Keys."""
        settings = self._parse_dproj(DPROJ_VERINFO_KEYS)
        assert settings.version_info.keys["CompanyName"] == "TestCo"
        assert settings.version_info.keys["FileDescription"] == "Test Application"
        assert settings.version_info.keys["LegalCopyright"] == "Copyright 2024"

    def test_msbuilds_vars_resolved_in_keys(self):
        """Test $(MSBuildProjectName) resolved to project stem in keys."""
        dproj_with_vars = DPROJ_VERINFO_KEYS.replace(
            "FileDescription=Test Application",
            "FileDescription=$(MSBuildProjectName)"
        )
        settings = self._parse_dproj(dproj_with_vars)
        assert settings.version_info.keys["FileDescription"] == "TestApp"


class TestDProjVersionInfoIndividual:
    """Tests for individual VerInfo_* property extraction."""

    def _parse_dproj(self, content: str) -> "DProjSettings":
        with tempfile.TemporaryDirectory() as tmpdir:
            dproj_path = Path(tmpdir) / "TestApp.dproj"
            dproj_path.write_text(content, encoding="utf-8")
            parser = DProjParser(dproj_path)
            return parser.parse()

    def test_individual_properties_override_keys_version(self):
        """Test individual VerInfo_MajorVer etc. override FileVersion from keys."""
        settings = self._parse_dproj(DPROJ_VERINFO_INDIVIDUAL)
        assert settings.version_info is not None
        assert settings.version_info.major == 3
        assert settings.version_info.minor == 6
        assert settings.version_info.release == 1
        assert settings.version_info.build == 316


class TestDProjVersionInfoDisabled:
    """Tests for disabled version info."""

    def _parse_dproj(self, content: str) -> "DProjSettings":
        with tempfile.TemporaryDirectory() as tmpdir:
            dproj_path = Path(tmpdir) / "TestApp.dproj"
            dproj_path.write_text(content, encoding="utf-8")
            parser = DProjParser(dproj_path)
            return parser.parse()

    def test_disabled_returns_none(self):
        """Test VerInfo_IncludeVerInfo=false returns None version_info."""
        settings = self._parse_dproj(DPROJ_VERINFO_DISABLED)
        assert settings.version_info is None


class TestDProjNoVersionInfo:
    """Tests for projects without version info."""

    def _parse_dproj(self, content: str) -> "DProjSettings":
        with tempfile.TemporaryDirectory() as tmpdir:
            dproj_path = Path(tmpdir) / "TestApp.dproj"
            dproj_path.write_text(content, encoding="utf-8")
            parser = DProjParser(dproj_path)
            return parser.parse()

    def test_no_verinfo_returns_none(self):
        """Test project without VerInfo returns None version_info."""
        settings = self._parse_dproj(DPROJ_NO_VERINFO)
        assert settings.version_info is None
