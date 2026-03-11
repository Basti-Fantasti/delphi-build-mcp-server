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

    # Pattern that normalizes MSBuild dcc output: "file(line,col): severity code: msg"
    # to the format OutputParser expects: "file(line,col) severity code: msg"
    # (removes the ': ' separator between location and severity keyword)
    LOCATION_COLON_PATTERN = re.compile(
        r"^(.+\(\d+(?:,\d+)?\))\s*:\s*(Error|Warning|Hint|Fatal|Fehler|Warnung|Hinweis|Schwerwiegend)\b",
        re.IGNORECASE,
    )

    def parse(self, output: str) -> tuple[list[CompilationError], CompilationStatistics]:
        """Parse MSBuild output for compilation errors."""
        if not output.strip():
            return [], CompilationStatistics()

        # Check for MSBuild-level errors first
        msbuild_errors = self._parse_msbuild_errors(output)
        if msbuild_errors:
            return msbuild_errors, CompilationStatistics()

        # Extract the _PasCoreCompile section
        dcc_output = self._extract_pas_compile_section(output)

        # Normalize MSBuild format to OutputParser-compatible format
        normalized = self._normalize_dcc_output(dcc_output)

        # Delegate to existing OutputParser
        parser = OutputParser()
        return parser.parse(normalized)

    def _normalize_dcc_output(self, output: str) -> str:
        """Normalize MSBuild-wrapped dcc output to OutputParser-compatible format.

        MSBuild produces: "file(line,col): error E2003: message"
        OutputParser expects: "file(line,col) error E2003: message"

        Removes the ': ' separator between the location and severity keyword.
        """
        normalized_lines = []
        for line in output.splitlines():
            match = self.LOCATION_COLON_PATTERN.match(line.strip())
            if match:
                # Replace ': severity' with ' severity'
                normalized_line = self.LOCATION_COLON_PATTERN.sub(
                    lambda m: f"{m.group(1)} {m.group(2)}", line.strip()
                )
                normalized_lines.append(normalized_line)
            else:
                normalized_lines.append(line)
        return "\n".join(normalized_lines)

    def _extract_pas_compile_section(self, output: str) -> str:
        """Extract the _PasCoreCompile section from MSBuild output.

        Handles both German and English locale output by matching
        on '_PasCoreCompile' as a substring.
        """
        lines = output.splitlines()
        in_section = False
        section_lines = []

        for line in lines:
            if "_PasCoreCompile" in line and not in_section:
                in_section = True
                continue

            if in_section:
                # End of section detection
                # German: "Erstellen des _PasCoreCompile-Ziels beendet."
                # English: 'Done building target "_PasCoreCompile".'
                if "_PasCoreCompile" in line and (
                    "beendet" in line.lower() or "done" in line.lower()
                ):
                    break
                # Another target started — check for non-indented target header lines
                stripped = line.strip()
                if stripped and not stripped.startswith(" "):
                    if stripped.endswith("-Ziel:") or (
                        stripped.endswith(":") and ":" not in stripped[:-1]
                    ):
                        break
                section_lines.append(line)

        return "\n".join(section_lines)

    def _parse_msbuild_errors(self, output: str) -> list[CompilationError]:
        """Parse MSBuild-level errors (not dcc compiler errors)."""
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
