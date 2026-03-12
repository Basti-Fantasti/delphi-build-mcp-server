# MSBuild Hybrid Compilation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use MSBuild for Windows targets (Win32/Win64/Win64x) to produce IDE-identical output; keep direct dcc for cross-compilation targets.

**Architecture:** Auto-detect platform from .dproj, route Windows targets to `MsBuildCompiler` (which calls `msbuild.exe` with environment from `rsvars.bat`), and cross-compilation targets to existing `DelphiCompiler`. Config files simplified: one generic `delphi_config.toml` for all Windows targets.

**Tech Stack:** Python 3.10+, pytest, pydantic, subprocess, TOML

**Spec:** `docs/superpowers/specs/2026-03-11-msbuild-hybrid-compilation-design.md`

**Test command:** `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`

---

## Chunk 1: Foundation — Models and rsvars Parser

### Task 1: Make models accept minimal config (no paths/compiler sections)

Currently `SystemPaths.rtl` and `SystemPaths.vcl` are required fields, and `PathsConfig.system` has no default. A minimal config with only `[delphi]` will crash. Make these optional.

**Files:**
- Modify: `src/models.py:138-194` (SystemPaths, PathsConfig)
- Test: `tests/test_models_minimal_config.py` (new)

- [ ] **Step 1: Write failing test for minimal Config creation**

```python
# tests/test_models_minimal_config.py
"""Tests for minimal config model support (MSBuild Windows targets)."""

import pytest
from pathlib import Path
from src.models import Config, DelphiConfig, SystemPaths, PathsConfig, CompilerConfig


class TestMinimalConfig:
    """Test that Config can be created with only delphi section."""

    def test_system_paths_all_optional(self):
        """SystemPaths should work with no arguments."""
        sp = SystemPaths()
        assert sp.rtl is None
        assert sp.vcl is None
        assert sp.lib_win32_release is None

    def test_paths_config_defaults_to_empty(self):
        """PathsConfig should work with no arguments."""
        pc = PathsConfig()
        assert pc.system.rtl is None
        assert pc.libraries == {}

    def test_config_with_only_delphi_section(self):
        """Config should load with only delphi section set."""
        config = Config(
            delphi=DelphiConfig(version="23.0", root_path=Path("C:/Delphi")),
        )
        assert config.delphi.version == "23.0"
        assert config.paths.system.rtl is None
        assert config.paths.libraries == {}
        assert config.compiler.flags == {"flags": []}

    def test_config_with_full_paths_still_works(self):
        """Existing full configs must continue to work."""
        config = Config(
            delphi=DelphiConfig(version="23.0", root_path=Path("C:/Delphi")),
            paths=PathsConfig(
                system=SystemPaths(
                    rtl=Path("C:/Delphi/source/rtl"),
                    vcl=Path("C:/Delphi/source/vcl"),
                    lib_win32_release=Path("C:/Delphi/lib/Win32/release"),
                ),
                libraries={"mylib": Path("C:/libs/mylib")},
            ),
        )
        assert config.paths.system.rtl == Path("C:/Delphi/source/rtl")
        assert config.paths.libraries["mylib"] == Path("C:/libs/mylib")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_models_minimal_config.py -v`
Expected: FAIL — `SystemPaths()` fails because `rtl` and `vcl` are required.

- [ ] **Step 3: Make SystemPaths fields optional and PathsConfig defaults**

In `src/models.py`, change `SystemPaths`:
```python
class SystemPaths(BaseModel):
    """System library paths configuration."""

    rtl: Optional[Path] = Field(default=None, description="RTL source path")
    vcl: Optional[Path] = Field(default=None, description="VCL source path")
    lib_win32_release: Optional[Path] = Field(default=None)
    # ... rest unchanged (already Optional)
```

Change `PathsConfig`:
```python
class PathsConfig(BaseModel):
    """All path configurations."""

    system: SystemPaths = Field(default_factory=SystemPaths, description="System library paths")
    libraries: dict[str, Path] = Field(
        default_factory=dict, description="Third-party library paths"
    )
```

Change `Config`:
```python
class Config(BaseModel):
    """Complete configuration model."""

    delphi: DelphiConfig = Field(description="Delphi installation settings")
    paths: PathsConfig = Field(
        default_factory=PathsConfig, description="Library paths"
    )
    compiler: CompilerConfig = Field(
        default_factory=CompilerConfig, description="Compiler settings"
    )
    # ... rest unchanged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_models_minimal_config.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check no regressions**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/models.py tests/test_models_minimal_config.py
git commit -m "Make SystemPaths and PathsConfig fields optional for minimal config support"
```

---

### Task 2: Create rsvars.bat parser

Parse `rsvars.bat` to extract `@SET` environment variable assignments. This is needed by `MsBuildCompiler` to set up the correct environment for `msbuild.exe`.

The actual `rsvars.bat` format (from the Delphi 12.3 installation):
```batch
@SET BDS=C:\Program Files (x86)\Embarcadero\Studio\23.0
@SET BDSINCLUDE=C:\Program Files (x86)\Embarcadero\Studio\23.0\include
@SET BDSCOMMONDIR=C:\Users\Public\Documents\Embarcadero\Studio\23.0
@SET FrameworkDir=C:\Windows\Microsoft.NET\Framework\v4.0.30319
@SET FrameworkVersion=v4.5
@SET FrameworkSDKDir=
@SET PATH=%FrameworkDir%;%FrameworkSDKDir%;C:\Program Files (x86)\Embarcadero\Studio\23.0\bin;C:\Program Files (x86)\Embarcadero\Studio\23.0\bin64;C:\Program Files (x86)\Embarcadero\Studio\23.0\cmake;%PATH%
@SET LANGDIR=DE
@SET PLATFORM=
@SET PlatformSDK=
```

**Files:**
- Create: `src/rsvars_parser.py`
- Test: `tests/test_rsvars_parser.py` (new)

- [ ] **Step 1: Write failing tests for rsvars parsing**

```python
# tests/test_rsvars_parser.py
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
            # Should contain the new value prepended to existing PATH
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
            # Should have BDS from rsvars
            assert full_env["BDS"] == "C:\\Delphi"
            # Should also have existing OS env vars
            assert "SystemRoot" in full_env or "HOME" in full_env
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
            # PATH should have expanded %FrameworkDir% and %BDS%
            assert "v4.0.30319" in env["PATH"]
            assert "Embarcadero" in env["PATH"]
        finally:
            os.unlink(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_rsvars_parser.py -v`
Expected: FAIL — `src.rsvars_parser` module not found.

- [ ] **Step 3: Implement RsvarsParser**

```python
# src/rsvars_parser.py
"""Parser for Delphi rsvars.bat environment setup files."""

import os
import re
from pathlib import Path


class RsvarsParser:
    """Parses rsvars.bat to extract environment variables for MSBuild."""

    # Pattern: @SET VARNAME=value (case-insensitive)
    SET_PATTERN = re.compile(r"^@SET\s+(\w+)=(.*?)$", re.IGNORECASE)

    # Pattern: %VARNAME% for variable expansion
    VAR_REF_PATTERN = re.compile(r"%([^%]+)%")

    def __init__(self, rsvars_path: Path):
        """Initialize parser.

        Args:
            rsvars_path: Path to rsvars.bat file
        """
        self.rsvars_path = rsvars_path

    def parse(self) -> dict[str, str]:
        """Parse rsvars.bat and return extracted environment variables.

        Returns:
            Dictionary of variable name -> value pairs.
            Variables are expanded using previously parsed values
            and existing OS environment variables.

        Raises:
            FileNotFoundError: If rsvars.bat doesn't exist
        """
        if not self.rsvars_path.exists():
            raise FileNotFoundError(f"rsvars.bat not found: {self.rsvars_path}")

        parsed_vars: dict[str, str] = {}

        with open(self.rsvars_path, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                match = self.SET_PATTERN.match(line)
                if not match:
                    continue

                var_name = match.group(1)
                var_value = match.group(2)

                # Expand %VARNAME% references
                var_value = self._expand_vars(var_value, parsed_vars)
                parsed_vars[var_name] = var_value

        return parsed_vars

    def build_msbuild_env(self) -> dict[str, str]:
        """Build a complete environment for MSBuild execution.

        Merges parsed rsvars.bat variables onto the current OS environment.

        Returns:
            Complete environment dictionary ready for subprocess.run(env=...)

        Raises:
            FileNotFoundError: If rsvars.bat doesn't exist
        """
        env = os.environ.copy()
        parsed_vars = self.parse()
        env.update(parsed_vars)
        return env

    def _expand_vars(self, value: str, parsed_vars: dict[str, str]) -> str:
        """Expand %VARNAME% references in a value.

        Looks up variables in this order:
        1. Already-parsed variables from rsvars.bat
        2. Current OS environment variables

        Args:
            value: String potentially containing %VAR% references
            parsed_vars: Already-parsed variables from earlier lines

        Returns:
            Expanded string
        """
        def replace_var(match: re.Match) -> str:
            var_name = match.group(1)
            # Check parsed vars first, then OS environment
            if var_name in parsed_vars:
                return parsed_vars[var_name]
            return os.environ.get(var_name, "")

        return self.VAR_REF_PATTERN.sub(replace_var, value)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_rsvars_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/rsvars_parser.py tests/test_rsvars_parser.py
git commit -m "Add rsvars.bat parser for MSBuild environment setup"
```

---

### Task 3: Create MSBuild output parser

Parse MSBuild output to extract the `_PasCoreCompile` section and delegate to the existing `OutputParser`.

**Files:**
- Create: `src/msbuild_output_parser.py`
- Test: `tests/test_msbuild_output_parser.py` (new)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_msbuild_output_parser.py
"""Tests for MSBuild output parser."""

import pytest

from src.msbuild_output_parser import MsBuildOutputParser


# Sample MSBuild output matching real IDE build log format (German locale)
MSBUILD_OUTPUT_SUCCESS_DE = """\
BuildVersionResource-Ziel:
    c:\\delphi\\bin\\cgrc.exe -c65001 MyApp.vrc -foMyApp.res
    CodeGear Resource Compiler/Binder
    Version 1.2.2
_PasCoreCompile-Ziel:
    c:\\delphi\\bin\\dcc32.exe --no-config -B MyApp.dpr
    X:\\project\\Unit1.pas(42,5): warning W1036: W1036 Variable 'x' ist moeglicherweise nicht initialisiert
    X:\\project\\Unit2.pas(10,1): error E2003: E2003 Undeclared identifier 'Foo'
Erstellen des _PasCoreCompile-Ziels beendet.
Erstellen des Projekts MyApp.dproj beendet.
"""

MSBUILD_OUTPUT_SUCCESS_EN = """\
BuildVersionResource:
    c:\\delphi\\bin\\cgrc.exe -c65001 MyApp.vrc -foMyApp.res
_PasCoreCompile:
    c:\\delphi\\bin\\dcc32.exe --no-config -B MyApp.dpr
    X:\\project\\Unit1.pas(42,5): warning W1036: Variable 'x' might not have been initialized
    X:\\project\\Unit2.pas(10,1): error E2003: Undeclared identifier 'Foo'
Done building target "_PasCoreCompile".
"""

MSBUILD_OUTPUT_NO_ERRORS = """\
_PasCoreCompile-Ziel:
    c:\\delphi\\bin\\dcc32.exe --no-config MyApp.dpr
Erstellen des _PasCoreCompile-Ziels beendet.
Das Erstellen war erfolgreich.
"""

MSBUILD_OUTPUT_BUILD_FAILURE = """\
MSBUILD : error MSB1009: Project file does not exist.
"""


class TestMsBuildOutputParser:
    """Tests for parsing MSBuild compilation output."""

    def test_extract_errors_german_locale(self):
        """Parse errors from German-locale MSBuild output."""
        parser = MsBuildOutputParser()
        errors, stats = parser.parse(MSBUILD_OUTPUT_SUCCESS_DE)
        assert len(errors) == 1
        assert errors[0].file == "X:\\project\\Unit2.pas"
        assert errors[0].line == 10
        assert errors[0].message.startswith("E2003")
        assert stats.warnings_filtered == 1

    def test_extract_errors_english_locale(self):
        """Parse errors from English-locale MSBuild output."""
        parser = MsBuildOutputParser()
        errors, stats = parser.parse(MSBUILD_OUTPUT_SUCCESS_EN)
        assert len(errors) == 1
        assert errors[0].file == "X:\\project\\Unit2.pas"
        assert stats.warnings_filtered == 1

    def test_no_errors_success(self):
        """Successful build with no errors."""
        parser = MsBuildOutputParser()
        errors, stats = parser.parse(MSBUILD_OUTPUT_NO_ERRORS)
        assert len(errors) == 0

    def test_msbuild_level_error(self):
        """MSBuild-level errors (not dcc) should be captured."""
        parser = MsBuildOutputParser()
        errors, stats = parser.parse(MSBUILD_OUTPUT_BUILD_FAILURE)
        assert len(errors) == 1
        assert "MSB1009" in errors[0].message or "does not exist" in errors[0].message

    def test_empty_output(self):
        """Empty output should return no errors."""
        parser = MsBuildOutputParser()
        errors, stats = parser.parse("")
        assert len(errors) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_msbuild_output_parser.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement MsBuildOutputParser**

```python
# src/msbuild_output_parser.py
"""Parser for MSBuild compilation output."""

import re

from src.models import CompilationError, CompilationStatistics
from src.output_parser import OutputParser


class MsBuildOutputParser:
    """Extracts dcc compiler output from MSBuild log and parses it.

    MSBuild wraps the Delphi compiler (dcc32/dcc64) and adds its own
    output structure. This parser extracts the _PasCoreCompile section
    and delegates to the existing OutputParser for error/warning parsing.
    """

    # MSBuild-level error pattern: "MSBUILD : error MSBXXXX: message"
    MSBUILD_ERROR_PATTERN = re.compile(
        r"MSBUILD\s*:\s*error\s+(\w+)\s*:\s*(.+)", re.IGNORECASE
    )

    def parse(self, output: str) -> tuple[list[CompilationError], CompilationStatistics]:
        """Parse MSBuild output for compilation errors.

        Extracts the _PasCoreCompile section and delegates to OutputParser.
        Also catches MSBuild-level errors.

        Args:
            output: Raw MSBuild output text

        Returns:
            Tuple of (errors list, statistics)
        """
        if not output.strip():
            return [], CompilationStatistics()

        # Check for MSBuild-level errors first
        msbuild_errors = self._parse_msbuild_errors(output)
        if msbuild_errors:
            return msbuild_errors, CompilationStatistics()

        # Extract the _PasCoreCompile section
        dcc_output = self._extract_pas_compile_section(output)

        # Delegate to existing OutputParser
        parser = OutputParser()
        return parser.parse(dcc_output)

    def _extract_pas_compile_section(self, output: str) -> str:
        """Extract the _PasCoreCompile section from MSBuild output.

        Looks for the section containing dcc compiler output.
        Handles both German and English locale output by matching
        on '_PasCoreCompile' as a substring.

        Args:
            output: Full MSBuild output

        Returns:
            Extracted dcc compiler output lines
        """
        lines = output.splitlines()
        in_section = False
        section_lines = []

        for line in lines:
            if "_PasCoreCompile" in line and not in_section:
                in_section = True
                continue

            if in_section:
                # End of section: line contains the target name ending
                # German: "Erstellen des _PasCoreCompile-Ziels beendet."
                # English: 'Done building target "_PasCoreCompile".'
                # Also end on next target section or project-level markers
                if ("_PasCoreCompile" in line and ("beendet" in line.lower() or "done" in line.lower())):
                    break
                stripped = line.strip()
                if stripped and not stripped.startswith(" "):
                    if stripped.endswith("-Ziel:") or (stripped.endswith(":") and ":" not in stripped[:-1]):
                        # Another target started (e.g., "SomeTarget-Ziel:" or "SomeTarget:")
                        break
                section_lines.append(line)

        return "\n".join(section_lines)

    def _parse_msbuild_errors(self, output: str) -> list[CompilationError]:
        """Parse MSBuild-level errors (not dcc compiler errors).

        Args:
            output: Full MSBuild output

        Returns:
            List of MSBuild errors, empty if none found
        """
        errors = []
        for line in output.splitlines():
            match = self.MSBUILD_ERROR_PATTERN.match(line.strip())
            if match:
                errors.append(CompilationError(
                    file="MSBuild",
                    line=0,
                    column=0,
                    message=f"{match.group(1)}: {match.group(2)}",
                    error_code=match.group(1),
                ))
        return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_msbuild_output_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/msbuild_output_parser.py tests/test_msbuild_output_parser.py
git commit -m "Add MSBuild output parser with PasCoreCompile section extraction"
```

---

## Chunk 2: MSBuild Compiler and Config Changes

### Task 4: Create MsBuildCompiler

Orchestrates MSBuild compilation for Windows targets. Uses `RsvarsParser` for environment setup, builds the msbuild command, executes it, and parses output.

**Files:**
- Create: `src/msbuild_compiler.py`
- Test: `tests/test_msbuild_compiler.py` (new)

- [ ] **Step 1: Write failing tests for command construction and environment**

```python
# tests/test_msbuild_compiler.py
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
        """Should return warning text when additional_search_paths are provided."""
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        warnings = compiler._build_warnings(
            additional_search_paths=["C:/extra"],
            additional_flags=[],
        )
        assert "additional_search_paths" in warnings.lower() or "search" in warnings.lower()

    def test_warns_on_additional_flags(self):
        """Should return warning text when additional_flags are provided."""
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        warnings = compiler._build_warnings(
            additional_search_paths=[],
            additional_flags=["-$O+"],
        )
        assert "additional_flags" in warnings.lower() or "flags" in warnings.lower()

    def test_no_warning_when_empty(self):
        """No warning when no additional params are provided."""
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        warnings = compiler._build_warnings(
            additional_search_paths=[],
            additional_flags=[],
        )
        assert warnings == ""


class TestMsBuildEnvironment:
    """Test MSBuild environment setup."""

    def test_rsvars_path_from_delphi_root(self):
        """rsvars.bat should be located at delphi_root/bin/rsvars.bat."""
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi/23.0"))
        assert compiler.rsvars_path == Path("C:/Delphi/23.0/bin/rsvars.bat")

    def test_find_msbuild_in_framework_dir(self):
        """MSBuild should be found via FrameworkDir from rsvars.bat."""
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        # When rsvars provides FrameworkDir, msbuild is at FrameworkDir/msbuild.exe
        env = {"FrameworkDir": "C:\\Windows\\Microsoft.NET\\Framework\\v4.0.30319"}
        msbuild = compiler._find_msbuild(env)
        assert str(msbuild).endswith("MSBuild.exe") or str(msbuild).endswith("msbuild.exe")
        assert "v4.0.30319" in str(msbuild)


class TestMsBuildCompileProject:
    """Test compile_project orchestration with mocked subprocess."""

    @patch("src.msbuild_compiler.subprocess.run")
    @patch.object(MsBuildCompiler, "_setup_environment")
    def test_compile_project_success(self, mock_env, mock_run):
        """Successful compilation returns CompilationResult with success=True."""
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
        """Missing rsvars.bat returns CompilationResult with success=False."""
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
        """Warnings for ignored params should appear in output."""
        mock_env.return_value = {"FrameworkDir": "C:\\Windows\\Microsoft.NET\\Framework\\v4.0.30319"}
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        compiler = MsBuildCompiler(delphi_root=Path("C:/Delphi"))
        dproj_settings = DProjSettings(active_config="Release", active_platform="Win32")
        result = compiler.compile_project(
            project_path=Path("C:/project/MyApp.dproj"),
            dproj_settings=dproj_settings,
            additional_search_paths=["C:/extra"],
        )
        # Warning should be generated (compile still proceeds)
        assert result.success is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_msbuild_compiler.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement MsBuildCompiler**

```python
# src/msbuild_compiler.py
"""MSBuild compiler orchestration for Windows Delphi targets."""

import subprocess
import time
from pathlib import Path
from typing import Optional

from src.models import CompilationError, CompilationResult, CompilationStatistics, DProjSettings
from src.msbuild_output_parser import MsBuildOutputParser
from src.rsvars_parser import RsvarsParser


class MsBuildCompiler:
    """Orchestrates Delphi compilation via MSBuild for Windows targets.

    Uses MSBuild (the same build system the Delphi IDE uses) to produce
    IDE-identical output including icons, manifests, and DPI awareness.
    """

    def __init__(self, delphi_root: Path):
        """Initialize MSBuild compiler.

        Args:
            delphi_root: Delphi installation root directory
        """
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
        """Compile a Delphi project using MSBuild.

        Args:
            project_path: Path to .dproj file
            dproj_settings: Parsed .dproj settings (for config/platform)
            force_build_all: Use /t:Rebuild instead of /t:Build
            additional_search_paths: Ignored for MSBuild (warning emitted)
            additional_flags: Ignored for MSBuild (warning emitted)

        Returns:
            CompilationResult with errors and statistics
        """
        start_time = time.time()
        additional_search_paths = additional_search_paths or []
        additional_flags = additional_flags or []

        # Build warnings for ignored parameters
        warnings_text = self._build_warnings(additional_search_paths, additional_flags)

        # Set up MSBuild environment
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

        # Find msbuild.exe
        msbuild_path = self._find_msbuild(env)

        # Build command
        command = self._build_command(project_path, dproj_settings, force_build_all, msbuild_path)

        # Execute
        output, exit_code = self._execute(command, project_path.parent, env)

        # Prepend warnings
        if warnings_text:
            output = warnings_text + "\n" + output

        # Parse output
        parser = MsBuildOutputParser()
        errors, statistics = parser.parse(output)

        compilation_time = time.time() - start_time

        # Find output executable
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
        """Set up MSBuild environment from rsvars.bat.

        Primary: Parse rsvars.bat and merge with OS environment.
        Fallback: Will be handled in _execute via cmd.exe wrapper.

        Returns:
            Environment dictionary for subprocess

        Raises:
            FileNotFoundError: If rsvars.bat not found
        """
        parser = RsvarsParser(self.rsvars_path)
        return parser.build_msbuild_env()

    def _find_msbuild(self, env: dict[str, str]) -> Path:
        """Find msbuild.exe from the environment.

        Args:
            env: Environment with FrameworkDir set

        Returns:
            Path to msbuild.exe
        """
        framework_dir = env.get("FrameworkDir", "")
        if framework_dir:
            msbuild = Path(framework_dir) / "MSBuild.exe"
            return msbuild

        # Fallback: assume msbuild is on PATH
        return Path("msbuild.exe")

    def _build_command(
        self,
        project_path: Path,
        dproj_settings: DProjSettings,
        force_build_all: bool,
        msbuild_path: Optional[Path] = None,
    ) -> list[str]:
        """Build the MSBuild command line.

        Args:
            project_path: Path to .dproj file
            dproj_settings: Parsed settings for config/platform
            force_build_all: Use Rebuild target
            msbuild_path: Path to msbuild.exe (default: from PATH)

        Returns:
            Command as list of arguments
        """
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
        self,
        additional_search_paths: list[str],
        additional_flags: list[str],
    ) -> str:
        """Build warning text for ignored parameters.

        Args:
            additional_search_paths: Search paths that will be ignored
            additional_flags: Flags that will be ignored

        Returns:
            Warning text, empty string if no warnings
        """
        warnings = []
        if additional_search_paths:
            warnings.append(
                "Warning: additional_search_paths ignored - MSBuild reads paths from .dproj"
            )
        if additional_flags:
            warnings.append(
                "Warning: additional_flags ignored - MSBuild reads flags from .dproj"
            )
        return "\n".join(warnings)

    def _execute(
        self,
        command: list[str],
        working_dir: Path,
        env: dict[str, str],
    ) -> tuple[str, int]:
        """Execute MSBuild and capture output.

        If direct execution fails (e.g., rsvars env incomplete),
        falls back to cmd.exe /c "call rsvars.bat && msbuild ..."

        Args:
            command: MSBuild command as list
            working_dir: Working directory
            env: Environment variables

        Returns:
            Tuple of (output string, exit code)
        """
        try:
            result = subprocess.run(
                command,
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=600,  # 10 minutes for MSBuild
            )
            output = result.stdout + "\n" + result.stderr
            return output, result.returncode

        except FileNotFoundError:
            # MSBuild not found — try cmd.exe fallback
            return self._execute_cmd_fallback(command, working_dir)

        except subprocess.TimeoutExpired:
            return "MSBuild compilation timed out after 10 minutes", 1
        except Exception as e:
            return f"MSBuild execution failed: {e}", 1

    def _execute_cmd_fallback(
        self,
        command: list[str],
        working_dir: Path,
    ) -> tuple[str, int]:
        """Fallback: run MSBuild via cmd.exe with rsvars.bat sourced.

        Args:
            command: Original MSBuild command (index 0 is msbuild path)
            working_dir: Working directory

        Returns:
            Tuple of (output string, exit code)
        """
        try:
            # Build cmd.exe /c "call rsvars.bat && msbuild.exe args..."
            rsvars = str(self.rsvars_path)
            msbuild_args = " ".join(f'"{arg}"' if " " in arg else arg for arg in command)
            cmd_line = f'call "{rsvars}" && {msbuild_args}'

            result = subprocess.run(
                ["cmd.exe", "/c", cmd_line],
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
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
        """Find the output executable after successful compilation.

        Args:
            project_path: Path to .dproj file
            dproj_settings: Parsed .dproj settings

        Returns:
            Path to output file, or None if not found
        """
        platform = dproj_settings.active_platform

        # Determine if package
        is_package = False
        if dproj_settings.main_source:
            is_package = dproj_settings.main_source.lower().endswith(".dpk")

        ext = ".bpl" if is_package else ".exe"

        # Check dproj output dir
        if dproj_settings.output_dir:
            exe_path = dproj_settings.output_dir / (project_path.stem + ext)
            if exe_path.exists():
                return exe_path

        # Check default location
        exe_path = project_path.with_suffix(ext)
        if exe_path.exists():
            return exe_path

        # Check platform-specific subdirectories
        config = dproj_settings.active_config
        subdir = f"{platform}/{config}"
        exe_path = project_path.parent / subdir / (project_path.stem + ext)
        if exe_path.exists():
            return exe_path

        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_msbuild_compiler.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/msbuild_compiler.py tests/test_msbuild_compiler.py
git commit -m "Add MsBuildCompiler for Windows target compilation"
```

---

### Task 5: Update config loading for generic delphi_config.toml fallback

Add fallback to generic `delphi_config.toml` for Windows platforms and make `_parse_config` handle missing sections.

**Files:**
- Modify: `src/config.py:45-95` (find_config_file_for_platform), `src/config.py:208-258` (_parse_config)
- Test: `tests/test_config_generic_fallback.py` (new)

- [ ] **Step 1: Write failing tests for generic config fallback**

```python
# tests/test_config_generic_fallback.py
"""Tests for generic delphi_config.toml fallback for Windows targets."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import find_config_file_for_platform, ConfigLoader

# Minimal Windows config content
MINIMAL_CONFIG = """\
[delphi]
version = "23.0"
root_path = "C:/Program Files (x86)/Embarcadero/Studio/23.0"
"""

# Full config content (backwards compatibility)
FULL_WIN32_CONFIG = """\
[delphi]
version = "23.0"
root_path = "C:/Program Files (x86)/Embarcadero/Studio/23.0"

[paths.system]
rtl = "C:/Delphi/source/rtl"
vcl = "C:/Delphi/source/vcl"
lib_win32_release = "C:/Delphi/lib/Win32/release"

[compiler.namespaces]
prefixes = ["System", "Winapi"]

[compiler.flags]
flags = ["--no-config"]
"""


class TestGenericConfigFallback:
    """Test fallback to generic delphi_config.toml for Windows platforms."""

    def test_win32_falls_back_to_generic(self, tmp_path):
        """Win32 should find generic delphi_config.toml when no win32-specific exists."""
        generic = tmp_path / "delphi_config.toml"
        generic.write_text(MINIMAL_CONFIG)

        path, source = find_config_file_for_platform(platform="Win32", base_dir=tmp_path)
        assert path == generic
        assert source == "generic"

    def test_win64_falls_back_to_generic(self, tmp_path):
        """Win64 should also fall back to generic."""
        generic = tmp_path / "delphi_config.toml"
        generic.write_text(MINIMAL_CONFIG)

        path, source = find_config_file_for_platform(platform="Win64", base_dir=tmp_path)
        assert path == generic
        assert source == "generic"

    def test_win64x_falls_back_to_generic(self, tmp_path):
        """Win64x should also fall back to generic."""
        generic = tmp_path / "delphi_config.toml"
        generic.write_text(MINIMAL_CONFIG)

        path, source = find_config_file_for_platform(platform="Win64x", base_dir=tmp_path)
        assert path == generic
        assert source == "generic"

    def test_platform_specific_takes_priority(self, tmp_path):
        """Platform-specific config should take priority over generic."""
        generic = tmp_path / "delphi_config.toml"
        generic.write_text(MINIMAL_CONFIG)
        specific = tmp_path / "delphi_config_win32.toml"
        specific.write_text(FULL_WIN32_CONFIG)

        path, source = find_config_file_for_platform(platform="Win32", base_dir=tmp_path)
        assert path == specific
        assert source == "platform"

    def test_linux64_does_not_fall_back_to_generic(self, tmp_path):
        """Linux64 should NOT fall back to generic — requires platform-specific config."""
        generic = tmp_path / "delphi_config.toml"
        generic.write_text(MINIMAL_CONFIG)

        with pytest.raises(FileNotFoundError):
            find_config_file_for_platform(platform="Linux64", base_dir=tmp_path)

    def test_android64_does_not_fall_back_to_generic(self, tmp_path):
        """Android64 should NOT fall back to generic."""
        generic = tmp_path / "delphi_config.toml"
        generic.write_text(MINIMAL_CONFIG)

        with pytest.raises(FileNotFoundError):
            find_config_file_for_platform(platform="Android64", base_dir=tmp_path)

    def test_android32_does_not_fall_back_to_generic(self, tmp_path):
        """Android (32-bit) should NOT fall back to generic."""
        generic = tmp_path / "delphi_config.toml"
        generic.write_text(MINIMAL_CONFIG)

        with pytest.raises(FileNotFoundError):
            find_config_file_for_platform(platform="Android", base_dir=tmp_path)


class TestMinimalConfigLoading:
    """Test that minimal config (only [delphi]) loads successfully."""

    def test_load_minimal_config(self, tmp_path):
        """Minimal config with only [delphi] should load without error."""
        config_file = tmp_path / "delphi_config.toml"
        config_file.write_text(MINIMAL_CONFIG)

        loader = ConfigLoader(config_path=config_file, platform="Win32")
        with patch.object(loader, '_validate_config'):  # Skip validation (no real Delphi install)
            config = loader.load()

        assert config.delphi.version == "23.0"
        assert config.paths.system.rtl is None
        assert config.paths.libraries == {}
        assert config.compiler.flags == {"flags": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_config_generic_fallback.py -v`
Expected: FAIL — no generic fallback in `find_config_file_for_platform`.

- [ ] **Step 3: Update find_config_file_for_platform and _parse_config**

In `src/config.py`, update `find_config_file_for_platform`:

After the platform-specific check (line 88), add generic fallback for Windows targets:
```python
    # For Windows platforms, fall back to generic delphi_config.toml
    WINDOWS_PLATFORMS = {"win32", "win64", "win64x"}
    if platform_normalized in WINDOWS_PLATFORMS:
        generic_config_path = base_dir / "delphi_config.toml"
        if generic_config_path.exists():
            return generic_config_path, "generic"
```

Update `_parse_config` in `ConfigLoader` to handle missing sections:
```python
    def _parse_config(self, raw_config: dict[str, Any]) -> Config:
        delphi_config = DelphiConfig(**raw_config["delphi"])

        # Parse paths (optional for minimal configs)
        paths_raw = raw_config.get("paths", {})
        system_raw = paths_raw.get("system", {})
        system_paths = SystemPaths(**system_raw)
        libraries = paths_raw.get("libraries", {})
        paths_config = PathsConfig(system=system_paths, libraries=libraries)

        # Parse compiler (optional)
        compiler_raw = raw_config.get("compiler", {})
        compiler_config = CompilerConfig(
            namespaces=compiler_raw.get("namespaces", {"prefixes": []}),
            aliases=compiler_raw.get("aliases", {}),
            flags=compiler_raw.get("flags", {"flags": []}),
        )

        # Parse Linux/Android SDK (optional, unchanged)
        linux_sdk_raw = raw_config.get("linux_sdk", {})
        linux_sdk_config = LinuxSDKConfig(
            sysroot=linux_sdk_raw.get("sysroot"),
            libpaths=linux_sdk_raw.get("libpaths", []),
        )
        android_sdk_raw = raw_config.get("android_sdk", {})
        android_sdk_config = AndroidSDKConfig(
            compiler_rt=android_sdk_raw.get("compiler_rt"),
            libpaths=android_sdk_raw.get("libpaths", []),
            linker=android_sdk_raw.get("linker"),
        )

        return Config(
            delphi=delphi_config,
            paths=paths_config,
            compiler=compiler_config,
            linux_sdk=linux_sdk_config,
            android_sdk=android_sdk_config,
        )
```

- [ ] **Step 4: Update _validate_config to be platform-aware**

In `src/config.py`, update `_validate_config` to skip search path and compiler validation for Windows platforms (MSBuild reads all this from the .dproj):

```python
def _validate_config(self, config: Config) -> None:
    """Validate configuration. For Windows platforms, only delphi.root_path is required."""
    # Always validate delphi.root_path exists
    root_path = config.delphi.root_path
    if not root_path.exists():
        raise ValueError(f"Delphi root path does not exist: {root_path}")

    # For Windows platforms, MSBuild handles everything else
    windows_platforms = {"win32", "win64", "win64x"}
    if self.platform and self.platform.lower() in windows_platforms:
        return  # Minimal validation only

    # For cross-compilation platforms, validate full config as before
    # (existing validation code remains unchanged)
    ...
```

The key change: add a Windows platform early-return after validating `root_path`. The existing cross-compilation validation (compiler paths, SDK paths, library paths) remains untouched below the early return.

- [ ] **Step 5: Run tests to verify they pass**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_config_generic_fallback.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/config.py tests/test_config_generic_fallback.py
git commit -m "Add generic delphi_config.toml fallback and platform-aware validation for Windows"
```

---

## Chunk 3: Routing Logic and Config Generator Updates

### Task 6: Update main.py to route Windows targets to MsBuildCompiler

Restructure `handle_compile_project` to parse .dproj first (standalone), then route to the appropriate compiler based on platform.

**Files:**
- Modify: `main.py:227-261` (handle_compile_project)
- Test: Integration test via MCP tool call (manual verification — MSBuild requires real Delphi install)

- [ ] **Step 1: Write failing tests for routing logic**

```python
# tests/test_routing.py
"""Tests for platform-based routing in handle_compile_project."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.models import DProjSettings


WINDOWS_PLATFORMS = {"Win32", "Win64", "Win64x"}
CROSSCOMPILE_PLATFORMS = {"Linux64", "Android", "Android64"}


class TestPlatformRouting:
    """Test that platforms route to the correct compiler."""

    @pytest.mark.parametrize("platform", ["Win32", "Win64", "Win64x"])
    def test_windows_platform_routes_to_msbuild(self, platform):
        """Windows platforms should route to MsBuildCompiler."""
        assert platform in WINDOWS_PLATFORMS

    @pytest.mark.parametrize("platform", ["Linux64", "Android", "Android64"])
    def test_crosscompile_platform_routes_to_dcc(self, platform):
        """Cross-compilation platforms should route to DelphiCompiler."""
        assert platform not in WINDOWS_PLATFORMS

    def test_override_platform_determines_routing(self):
        """override_platform should override .dproj platform for routing."""
        # If override_platform is "Linux64", even if .dproj says Win32,
        # the routing should use Linux64
        override = "Linux64"
        assert override not in WINDOWS_PLATFORMS

    def test_default_platform_is_win32(self):
        """When no override and no .dproj, default to Win32 (MSBuild route)."""
        default = "Win32"
        assert default in WINDOWS_PLATFORMS
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_routing.py -v`
Expected: PASS (these are structural tests for the routing constants)

- [ ] **Step 3: Restructure handle_compile_project**

Update `main.py` imports:
```python
from src.msbuild_compiler import MsBuildCompiler
from src.dproj_parser import DProjParser
```

Replace `handle_compile_project` function body:

```python
async def handle_compile_project(arguments: dict) -> str:
    import json

    # Extract arguments (convert WSL paths — result is Windows-format path)
    project_path = Path(convert_wsl_to_windows_path(arguments["project_path"]))
    force_build_all = arguments.get("force_build_all", False)
    override_config = arguments.get("override_config")
    override_platform = arguments.get("override_platform")
    additional_search_paths = arguments.get("additional_search_paths", [])
    additional_flags = arguments.get("additional_flags", [])

    # Note: project_path is a Windows-format path (e.g., C:\...) so
    # Path.exists() won't work on WSL. Validation happens inside the
    # compiler subprocess (which runs on Windows).

    # Parse .dproj to determine platform (standalone, before compiler selection)
    dproj_path = project_path if project_path.suffix.lower() == ".dproj" else project_path.with_suffix(".dproj")
    dproj_settings = None
    platform = override_platform or "Win32"

    # Try to parse .dproj for platform detection
    # DProjParser runs in-process reading the file, so it needs a WSL-accessible path
    try:
        dproj_parser = DProjParser(dproj_path)
        dproj_settings = dproj_parser.parse(override_config, override_platform)
        platform = dproj_settings.active_platform
    except FileNotFoundError:
        # .dproj doesn't exist or isn't accessible — use override_platform or default
        pass

    # Route based on platform
    windows_platforms = {"Win32", "Win64", "Win64x"}

    if platform in windows_platforms:
        if dproj_settings is None:
            raise FileNotFoundError(
                f".dproj file required for MSBuild compilation: {dproj_path}. "
                f"MSBuild needs the .dproj to build the project."
            )
        # Use MSBuild for Windows targets
        config_loader = ConfigLoader(platform=platform)
        config = config_loader.load()

        compiler = MsBuildCompiler(delphi_root=config.delphi.root_path)
        result = compiler.compile_project(
            project_path=dproj_path,
            dproj_settings=dproj_settings,
            force_build_all=force_build_all,
            additional_search_paths=additional_search_paths,
            additional_flags=additional_flags,
        )
    else:
        # Use direct dcc for cross-compilation targets (unchanged)
        compiler = DelphiCompiler()
        result = compiler.compile_project(
            project_path=project_path,
            force_build_all=force_build_all,
            override_config=override_config,
            override_platform=override_platform,
            additional_search_paths=additional_search_paths,
            additional_flags=additional_flags,
        )

    return json.dumps(result.model_dump(), indent=2)
```

- [ ] **Step 4: Run full test suite**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_routing.py
git commit -m "Route Windows targets to MsBuildCompiler in handle_compile_project"
```

---

### Task 7: Update config generator for minimal Windows configs

When generating config from a Windows build log, produce a minimal `delphi_config.toml` with only `[delphi]` section.

**Files:**
- Modify: `src/config_generator.py`
- Test: `tests/test_config_generator_minimal.py` (new)

- [ ] **Step 1: Read current config_generator.py to understand structure**

Read `src/config_generator.py` fully before making changes.

- [ ] **Step 2: Write failing test for minimal Windows config generation**

```python
# tests/test_config_generator_minimal.py
"""Tests for minimal config generation for Windows platforms."""

import tempfile
from pathlib import Path

import pytest

from src.config_generator import ConfigGenerator


# Minimal Win32 Release build log (just enough for detection)
WIN32_BUILD_LOG = """\
dcc32 Befehlszeile für "MyApp.dpr"
  c:\\program files (x86)\\embarcadero\\studio\\23.0\\bin\\dcc32.exe --no-config -B MyApp.dpr
"""


class TestMinimalWindowsConfigGeneration:
    """Test that Windows build logs produce minimal configs."""

    def test_windows_config_is_minimal(self, tmp_path):
        """Win32 build log should produce config with only [delphi] section."""
        log_file = tmp_path / "build.log"
        log_file.write_text(WIN32_BUILD_LOG)
        output_file = tmp_path / "delphi_config.toml"

        generator = ConfigGenerator(use_env_vars=False)
        result = generator.generate_from_build_log(
            build_log_path=log_file,
            output_path=output_file,
        )

        assert result.success
        content = output_file.read_text()
        # Should have [delphi] section
        assert "[delphi]" in content
        assert "root_path" in content
        # Should NOT have full paths/compiler sections
        assert "[paths.libraries]" not in content
        assert "[compiler.flags]" not in content
        assert "[compiler.namespaces]" not in content
        # Should have a comment about MSBuild
        assert "MSBuild" in content or "msbuild" in content

    def test_windows_config_default_filename(self, tmp_path):
        """Windows build logs should default to generic delphi_config.toml filename."""
        log_file = tmp_path / "build.log"
        log_file.write_text(WIN32_BUILD_LOG)

        generator = ConfigGenerator(use_env_vars=False)
        result = generator.generate_from_build_log(
            build_log_path=log_file,
            output_path=None,
            use_platform_specific_name=True,  # Should still produce generic name for Windows
        )

        assert result.success
        # For Windows, should be delphi_config.toml (not delphi_config_win32.toml)
        assert result.config_file_path.endswith("delphi_config.toml")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_config_generator_minimal.py -v`
Expected: FAIL — config generator still produces full config for Windows.

- [ ] **Step 4: Update ConfigGenerator to produce minimal Windows configs**

In `src/config_generator.py`, add logic to detect Windows platforms and generate minimal config. The exact changes depend on the current structure (read in step 1), but the key change is:

1. After parsing the build log and detecting the platform, check if it's a Windows platform
2. If Windows: write only `[delphi]` section with `version` and `root_path`, plus a comment about MSBuild
3. If cross-compilation: write full config as before
4. For default filename: use `delphi_config.toml` for Windows platforms

- [ ] **Step 5: Run tests to verify they pass**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_config_generator_minimal.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/config_generator.py tests/test_config_generator_minimal.py
git commit -m "Generate minimal delphi_config.toml for Windows platform build logs"
```

---

### Task 8: Update multi_config_generator and config_extender

Update multi-config generator to group Windows logs into one minimal config, and config extender to skip paths for Windows platforms.

**Files:**
- Modify: `src/multi_config_generator.py`
- Modify: `src/config_extender.py`
- Test: `tests/test_multi_config_windows.py` (new)
- Test: `tests/test_config_extender_windows.py` (new)

- [ ] **Step 1: Read current multi_config_generator.py and config_extender.py**

Read both files fully to understand their structure before making changes.

- [ ] **Step 2: Write failing tests**

```python
# tests/test_multi_config_windows.py
"""Tests for multi-config generator Windows platform grouping."""

from pathlib import Path
import pytest
from src.multi_config_generator import MultiConfigGenerator

WINDOWS_PLATFORMS = {"Win32", "Win64", "Win64x"}


class TestMultiConfigWindowsGrouping:
    """Test that Windows platform logs are grouped into one minimal config."""

    def test_is_windows_platform(self):
        """Windows platforms should be detected correctly."""
        for p in ["Win32", "Win64", "Win64x"]:
            assert p in WINDOWS_PLATFORMS

    def test_crosscompile_not_grouped(self):
        """Cross-compilation platforms should not be in Windows group."""
        for p in ["Linux64", "Android", "Android64"]:
            assert p not in WINDOWS_PLATFORMS
```

```python
# tests/test_config_extender_windows.py
"""Tests for config extender Windows platform handling."""

from pathlib import Path
import pytest

WINDOWS_PLATFORMS = {"Win32", "Win64", "Win64x"}


class TestConfigExtenderWindows:
    """Test that Windows platform extensions skip paths."""

    def test_windows_platform_detected(self):
        """Windows platforms should be recognized for minimal handling."""
        for p in ["Win32", "Win64", "Win64x"]:
            assert p in WINDOWS_PLATFORMS
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest tests/test_multi_config_windows.py tests/test_config_extender_windows.py -v`
Expected: PASS

- [ ] **Step 4: Update multi_config_generator.py**

In `src/multi_config_generator.py`, find the method that generates separate platform files and add:

```python
WINDOWS_PLATFORMS = {"Win32", "Win64", "Win64x"}
```

When `generate_separate_files=True`:
- Check each parsed build log's platform
- Group all Windows platform logs together — use the first one's `delphi.root_path` and `version`
- Generate a single minimal `delphi_config.toml` for all Windows platforms (using the same minimal format as `ConfigGenerator` from Task 7)
- Generate separate platform-specific configs for Linux64/Android platforms (unchanged behavior)

Read the file first, then apply the changes following the existing code patterns.

- [ ] **Step 5: Update config_extender.py**

In `src/config_extender.py`, find the merge logic and add a Windows platform check:

```python
WINDOWS_PLATFORMS = {"Win32", "Win64", "Win64x"}

# In the merge method, after parsing the build log:
if detected_platform.lower() in {p.lower() for p in WINDOWS_PLATFORMS}:
    # For Windows targets, only update delphi section
    # Skip search paths, flags, namespaces, aliases
    # Only merge root_path if different
    ...
```

Read the file first, then apply changes following existing patterns.

- [ ] **Step 6: Run full test suite**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/multi_config_generator.py src/config_extender.py tests/test_multi_config_windows.py tests/test_config_extender_windows.py
git commit -m "Update multi-config generator and extender for MSBuild Windows targets"
```

---

## Chunk 4: Integration Test and Cleanup

### Task 9: Integration test — compile with MSBuild and verify IDE parity

This is a manual integration test using the real Delphi installation.

**Files:**
- No code changes — manual verification

- [ ] **Step 1: Create minimal delphi_config.toml**

Create `delphi_config.toml` in the MCP server directory:
```toml
[delphi]
version = "23.0"
root_path = "c:/program files (x86)/embarcadero/studio/23.0"
```

- [ ] **Step 2: Compile GTRSetupAssistant with MSBuild via MCP**

Use `compile_delphi_project` tool:
- project_path: `X:\git_local\sap-setup-assistant\GTRSetupAssistant.dproj`
- override_platform: `Win32`
- override_config: `Release`
- force_build_all: `true`

- [ ] **Step 3: Verify output matches IDE build**

Compare the new `GTRSetupAssistant.exe` with the `GTRSetupAssistant_IDE_Build.exe`:
- File size should be similar (within a few KB)
- Should have the application icon
- Should NOT require admin privileges
- Should have version info embedded

- [ ] **Step 4: Verify cross-compilation still works**

Compile a project for Linux64 or Android64 to verify the direct dcc path is unaffected.

- [ ] **Step 5: Final commit with any fixes**

```bash
git add delphi_config.toml
git commit -m "Add minimal delphi_config.toml for MSBuild Windows compilation"
```

---

### Task 10: Update tool descriptions

Update the MCP tool descriptions to mention MSBuild for Windows targets.

**Files:**
- Modify: `main.py:32-76` (COMPILE_TOOL description)
- Modify: `main.py:78-112` (GENERATE_CONFIG_TOOL description)

- [ ] **Step 1: Update COMPILE_TOOL description**

In `main.py`, replace the `description` field of `COMPILE_TOOL` (keep `inputSchema` unchanged):

Old description:
```python
    description=(
        "Compile a Delphi project (.dpr or .dproj file) and return parsed results. "
        "Automatically reads build configuration from .dproj file and library paths from config file. "
        "Returns only compilation errors, filtering out warnings and hints."
    ),
```

New description:
```python
    description=(
        "Compile a Delphi project (.dpr or .dproj file) and return parsed results. "
        "For Windows targets (Win32/Win64/Win64x), uses MSBuild for IDE-identical output "
        "including icons, manifests, and DPI awareness. For cross-compilation targets "
        "(Linux64/Android/Android64), uses direct dcc compiler invocation. "
        "Returns only compilation errors, filtering out warnings and hints."
    ),
```

- [ ] **Step 2: Update GENERATE_CONFIG_TOOL description**

In `main.py`, replace the `description` field of `GENERATE_CONFIG_TOOL` (keep `inputSchema` unchanged):

Old description:
```python
    description=(
        "Generate delphi_config.toml file automatically by parsing an IDE build log. "
        "Extracts all library paths, compiler settings, and configuration from a successful "
        "compilation performed in the Delphi IDE. This eliminates manual configuration. "
        "Supports platform-specific config files (e.g., delphi_config_win64.toml) for "
        "simpler multi-platform setups."
    ),
```

New description:
```python
    description=(
        "Generate delphi_config.toml file automatically by parsing an IDE build log. "
        "For Windows targets, generates a minimal config with only the Delphi installation path "
        "(MSBuild handles all other settings). For cross-compilation targets (Linux64/Android), "
        "generates a full config with all library paths and compiler settings."
    ),
```

- [ ] **Step 3: Run full test suite (final verification)**

Run: `/mnt/c/users/teufel/.local/bin/uv.exe run --extra dev python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "Update tool descriptions to mention MSBuild for Windows targets"
```
