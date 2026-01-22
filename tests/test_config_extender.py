"""Tests for ConfigExtender class."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config_extender import ConfigExtender


# Sample TOML config for testing
SAMPLE_CONFIG = """# Delphi Build MCP Server Configuration
[delphi]
version = "23.0"
root_path = "C:/Program Files (x86)/Embarcadero/Studio/23.0"

[paths.system]
rtl = "C:/Program Files (x86)/Embarcadero/Studio/23.0/source/rtl"
vcl = "C:/Program Files (x86)/Embarcadero/Studio/23.0/source/vcl"
lib_win32_release = "C:/Program Files (x86)/Embarcadero/Studio/23.0/lib/Win32/release"
lib_win32_debug = "C:/Program Files (x86)/Embarcadero/Studio/23.0/lib/Win32/debug"
lib_win64_release = "C:/Program Files (x86)/Embarcadero/Studio/23.0/lib/Win64/release"
lib_win64_debug = "C:/Program Files (x86)/Embarcadero/Studio/23.0/lib/Win64/debug"

[paths.libraries]
spring4d = "C:/Libraries/Spring4D/Source"
dunitx = "C:/Libraries/DUnitX/Source"

[compiler.flags]
flags = ["--no-config", "-B", "-Q"]

[compiler.namespaces]
prefixes = ["System", "Winapi", "Vcl", "Data"]

[compiler.aliases]
"SysUtils" = "System.SysUtils"
"""

# Sample build log for Win64x platform
SAMPLE_BUILD_LOG_WIN64X = """Build started at 2026-01-21 10:00:00
Configuration: Debug
Platform: Win64x

"C:\\Program Files (x86)\\Embarcadero\\Studio\\23.0\\bin\\dcc64.exe"
  -$D+ -$L+ -$Y+ -$O- --no-config -B -Q
  -NSSystem;Winapi;Vcl;Data;Xml
  -ASysUtils=System.SysUtils
  -U"C:\\Program Files (x86)\\Embarcadero\\Studio\\23.0\\lib\\Win64x\\debug"
  -U"C:\\Program Files (x86)\\Embarcadero\\Studio\\23.0\\lib\\Win64x\\release"
  -U"C:\\Libraries\\Spring4D\\Source"
  -U"C:\\Libraries\\DUnitX\\Source"
  -U"C:\\Libraries\\NewLib\\Source"
  Working.dpr

Build succeeded
"""

# Sample build log for Linux64 platform with SDK
SAMPLE_BUILD_LOG_LINUX64 = """Build started at 2026-01-21 10:00:00
Configuration: Release
Platform: Linux64

"C:\\Program Files (x86)\\Embarcadero\\Studio\\23.0\\bin\\dcclinux64.exe"
  -$D- -$O+ --no-config -B -Q
  -NSSystem;Winapi;Posix
  -U"C:\\Program Files (x86)\\Embarcadero\\Studio\\23.0\\lib\\Linux64\\release"
  -U"C:\\Libraries\\Spring4D\\Source"
  --syslibroot:C:\\Users\\Test\\Documents\\SDKs\\ubuntu.sdk
  --libpath:C:\\Users\\Test\\Documents\\SDKs\\ubuntu.sdk\\usr\\lib\\x86_64-linux-gnu
  Working.dpr

Build succeeded
"""


@pytest.fixture
def temp_config_file():
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(SAMPLE_CONFIG)
        temp_path = f.name
    yield Path(temp_path)
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_build_log_win64x():
    """Create a temporary build log for Win64x."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        f.write(SAMPLE_BUILD_LOG_WIN64X)
        temp_path = f.name
    yield Path(temp_path)
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_build_log_linux64():
    """Create a temporary build log for Linux64."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        f.write(SAMPLE_BUILD_LOG_LINUX64)
        temp_path = f.name
    yield Path(temp_path)
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_output_file():
    """Create a temporary output file path."""
    temp_path = Path(tempfile.mktemp(suffix=".toml"))
    yield temp_path
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


class TestConfigExtender:
    """Tests for ConfigExtender class."""

    def test_extend_adds_new_platform(
        self, temp_config_file, temp_build_log_win64x, temp_output_file
    ):
        """Test that extending config adds a new platform."""
        extender = ConfigExtender(use_env_vars=False)
        result = extender.extend_from_build_log(
            existing_config_path=temp_config_file,
            build_log_path=temp_build_log_win64x,
            output_path=temp_output_file,
        )

        assert result.success
        assert "Win64x" in result.platforms_added

        # Read output and verify Win64x lib paths added
        with open(temp_output_file, "r") as f:
            content = f.read()
        assert "lib_win64x_debug" in content
        assert "lib_win64x_release" in content

    def test_extend_skips_duplicates(
        self, temp_config_file, temp_build_log_win64x, temp_output_file
    ):
        """Test that duplicate paths are skipped."""
        extender = ConfigExtender(use_env_vars=False)
        result = extender.extend_from_build_log(
            existing_config_path=temp_config_file,
            build_log_path=temp_build_log_win64x,
            output_path=temp_output_file,
        )

        assert result.success
        # Spring4D and DUnitX are in both config and build log - should be skipped
        assert result.paths_skipped > 0

    def test_extend_preserves_existing(
        self, temp_config_file, temp_build_log_win64x, temp_output_file
    ):
        """Test that existing settings are preserved."""
        extender = ConfigExtender(use_env_vars=False)
        result = extender.extend_from_build_log(
            existing_config_path=temp_config_file,
            build_log_path=temp_build_log_win64x,
            output_path=temp_output_file,
        )

        assert result.success

        # Read output and verify existing settings preserved
        with open(temp_output_file, "r") as f:
            content = f.read()

        # Existing delphi version should be preserved
        assert 'version = "23.0"' in content
        # Existing lib paths should be preserved
        assert "lib_win32_release" in content
        assert "lib_win64_debug" in content

    def test_extend_adds_new_libraries(
        self, temp_config_file, temp_build_log_win64x, temp_output_file
    ):
        """Test that new library paths are added."""
        extender = ConfigExtender(use_env_vars=False)
        result = extender.extend_from_build_log(
            existing_config_path=temp_config_file,
            build_log_path=temp_build_log_win64x,
            output_path=temp_output_file,
        )

        assert result.success
        assert result.paths_added > 0

        # Read output and verify NewLib was added
        with open(temp_output_file, "r") as f:
            content = f.read()
        assert "NewLib" in content or "newlib" in content

    def test_path_normalization(self):
        """Test case-insensitive path comparison."""
        extender = ConfigExtender(use_env_vars=False)

        path1 = "C:\\Libraries\\Spring4D\\Source"
        path2 = "C:/LIBRARIES/spring4d/source"

        norm1 = extender._normalize_path_for_comparison(path1)
        norm2 = extender._normalize_path_for_comparison(path2)

        assert norm1 == norm2

    def test_library_naming(self):
        """Test unique name generation for new libraries."""
        extender = ConfigExtender(use_env_vars=False)

        path = Path("C:/Libraries/Spring4D/Source")
        name = extender._derive_library_name(path)

        assert name == "spring4d_source"

    def test_make_unique_name(self):
        """Test unique name generation with suffix."""
        extender = ConfigExtender(use_env_vars=False)

        used_names = {"library", "library_2"}
        unique = extender._make_unique_name("library", used_names)

        assert unique == "library_3"

    def test_missing_config_error(self, temp_build_log_win64x):
        """Test proper error for missing config file."""
        extender = ConfigExtender(use_env_vars=False)

        with pytest.raises(FileNotFoundError) as exc_info:
            extender.extend_from_build_log(
                existing_config_path=Path("nonexistent.toml"),
                build_log_path=temp_build_log_win64x,
            )

        assert "not found" in str(exc_info.value)

    def test_missing_build_log_error(self, temp_config_file):
        """Test proper error for missing build log."""
        extender = ConfigExtender(use_env_vars=False)

        with pytest.raises(FileNotFoundError) as exc_info:
            extender.extend_from_build_log(
                existing_config_path=temp_config_file,
                build_log_path=Path("nonexistent.log"),
            )

        assert "not found" in str(exc_info.value)

    def test_overwrites_existing_when_no_output(self, temp_config_file, temp_build_log_win64x):
        """Test that existing config is overwritten when no output path specified."""
        extender = ConfigExtender(use_env_vars=False)

        # Read original content
        with open(temp_config_file, "r") as f:
            original_content = f.read()

        result = extender.extend_from_build_log(
            existing_config_path=temp_config_file,
            build_log_path=temp_build_log_win64x,
            # No output_path - should overwrite existing
        )

        assert result.success
        assert result.config_file_path == str(temp_config_file.absolute())

        # Read updated content
        with open(temp_config_file, "r") as f:
            updated_content = f.read()

        # Content should be different (extended)
        assert "lib_win64x" in updated_content

    def test_namespace_merge(self, temp_config_file, temp_build_log_win64x, temp_output_file):
        """Test that namespaces are merged without duplicates."""
        extender = ConfigExtender(use_env_vars=False)
        result = extender.extend_from_build_log(
            existing_config_path=temp_config_file,
            build_log_path=temp_build_log_win64x,
            output_path=temp_output_file,
        )

        assert result.success

        # Read output and verify namespaces
        with open(temp_output_file, "r") as f:
            content = f.read()

        # Both original (System, Winapi, Vcl, Data) and any new ones should be present
        assert "System" in content
        assert "Winapi" in content

    def test_alias_merge(self, temp_config_file, temp_build_log_win64x, temp_output_file):
        """Test that aliases are merged, existing not overwritten."""
        extender = ConfigExtender(use_env_vars=False)
        result = extender.extend_from_build_log(
            existing_config_path=temp_config_file,
            build_log_path=temp_build_log_win64x,
            output_path=temp_output_file,
        )

        assert result.success

        # Read output and verify alias preserved
        with open(temp_output_file, "r") as f:
            content = f.read()

        assert "SysUtils" in content
        assert "System.SysUtils" in content


class TestConfigExtenderLinuxSDK:
    """Tests for ConfigExtender Linux SDK handling."""

    def test_extend_adds_linux_sdk(
        self, temp_config_file, temp_build_log_linux64, temp_output_file
    ):
        """Test that Linux SDK settings are added."""
        extender = ConfigExtender(use_env_vars=False)
        result = extender.extend_from_build_log(
            existing_config_path=temp_config_file,
            build_log_path=temp_build_log_linux64,
            output_path=temp_output_file,
        )

        assert result.success

        # Read output and verify Linux SDK section
        with open(temp_output_file, "r") as f:
            content = f.read()

        assert "[linux_sdk]" in content
        assert "sysroot" in content
        assert "libpaths" in content


class TestExtendConfigResult:
    """Tests for ExtendConfigResult model."""

    def test_result_fields(self, temp_config_file, temp_build_log_win64x, temp_output_file):
        """Test that result contains expected fields."""
        extender = ConfigExtender(use_env_vars=False)
        result = extender.extend_from_build_log(
            existing_config_path=temp_config_file,
            build_log_path=temp_build_log_win64x,
            output_path=temp_output_file,
        )

        assert hasattr(result, "success")
        assert hasattr(result, "config_file_path")
        assert hasattr(result, "paths_added")
        assert hasattr(result, "paths_skipped")
        assert hasattr(result, "platforms_added")
        assert hasattr(result, "settings_updated")
        assert hasattr(result, "message")

        assert isinstance(result.success, bool)
        assert isinstance(result.paths_added, int)
        assert isinstance(result.paths_skipped, int)
        assert isinstance(result.platforms_added, list)
        assert isinstance(result.settings_updated, dict)
        assert isinstance(result.message, str)
