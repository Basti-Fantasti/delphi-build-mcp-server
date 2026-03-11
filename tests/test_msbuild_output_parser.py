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
