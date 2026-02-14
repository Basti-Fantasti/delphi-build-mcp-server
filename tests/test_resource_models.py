"""Tests for resource compilation models."""

from src.models import VersionInfo, ResourceCompilationResult


class TestVersionInfo:
    """Tests for VersionInfo model."""

    def test_defaults(self):
        """Test default values."""
        vi = VersionInfo()
        assert vi.major == 0
        assert vi.minor == 0
        assert vi.release == 0
        assert vi.build == 0
        assert vi.locale == 1033
        assert vi.keys == {}

    def test_with_values(self):
        """Test construction with explicit values."""
        vi = VersionInfo(
            major=2, minor=5, release=1, build=42,
            locale=1031,
            keys={"CompanyName": "TestCo", "FileDescription": "TestApp"},
        )
        assert vi.major == 2
        assert vi.minor == 5
        assert vi.release == 1
        assert vi.build == 42
        assert vi.locale == 1031
        assert vi.keys["CompanyName"] == "TestCo"

    def test_file_version_string(self):
        """Test file_version_string property."""
        vi = VersionInfo(major=1, minor=2, release=3, build=4)
        assert vi.file_version_string == "1.2.3.4"


class TestResourceCompilationResult:
    """Tests for ResourceCompilationResult model."""

    def test_success_result(self):
        """Test successful result."""
        result = ResourceCompilationResult(
            success=True,
            res_file="C:\\project\\MyApp.res",
        )
        assert result.success is True
        assert result.res_file == "C:\\project\\MyApp.res"
        assert result.error_output is None

    def test_failure_result(self):
        """Test failure result."""
        result = ResourceCompilationResult(
            success=False,
            error_output="cgrc.exe: fatal error RC1015",
        )
        assert result.success is False
        assert result.res_file is None
        assert "fatal error" in result.error_output
