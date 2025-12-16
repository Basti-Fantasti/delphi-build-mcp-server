"""Parser for Delphi compiler output."""

import re
from typing import Optional

from src.models import CompilationError, CompilationStatistics


class OutputParser:
    """Parses Delphi compiler output to extract errors and filter warnings/hints."""

    # Pattern for Delphi compiler messages (English and German)
    # Format: FileName.pas(line,col): [Error/Fehler/Warning/Warnung/Hint/Hinweis] E####: Message
    # Example: Unit1.pas(42,15): Error: E2003 Undeclared identifier: 'Foo'
    # Example: Unit1.pas(42,15) Fehler: E2003 Undeklarierter Bezeichner: 'Foo'
    MESSAGE_PATTERN = re.compile(
        r"^(.+?)\((\d+)(?:,(\d+))?\)\s*(Error|Warning|Hint|Fatal|Fehler|Warnung|Hinweis|Schwerwiegend)(?:\s*:)?\s*([EWHFewh]\d+)?\s*:?\s*(.+)$",
        re.IGNORECASE
    )

    # Alternative pattern for messages without file location (English and German)
    # Example: Fatal: F1026 File not found: 'System.pas'
    # Example: Schwerwiegend: F1026 Datei nicht gefunden: 'System.pas'
    SIMPLE_MESSAGE_PATTERN = re.compile(
        r"^(Error|Warning|Hint|Fatal|Fehler|Warnung|Hinweis|Schwerwiegend)\s*:?\s*([EWHFewh]\d+)?\s*:?\s*(.+)$",
        re.IGNORECASE
    )

    def __init__(self):
        """Initialize output parser."""
        self.errors: list[CompilationError] = []
        self.statistics = CompilationStatistics()

    def parse(self, output: str) -> tuple[list[CompilationError], CompilationStatistics]:
        """Parse compiler output and extract errors.

        Args:
            output: Raw compiler output text

        Returns:
            Tuple of (errors list, statistics)
        """
        lines = output.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            self._parse_line(line)

        return self.errors, self.statistics

    def _parse_line(self, line: str) -> None:
        """Parse a single line of compiler output.

        Args:
            line: Single line from compiler output
        """
        # Try full pattern first (with file location)
        match = self.MESSAGE_PATTERN.match(line)

        if match:
            file_path = match.group(1)
            line_num = int(match.group(2))
            col_num = int(match.group(3)) if match.group(3) else 0
            severity = match.group(4)
            error_code = match.group(5)
            message = match.group(6)

            self._process_message(
                severity=severity,
                error_code=error_code,
                message=message,
                file_path=file_path,
                line_num=line_num,
                col_num=col_num,
            )
            return

        # Try simple pattern (without file location)
        match = self.SIMPLE_MESSAGE_PATTERN.match(line)

        if match:
            severity = match.group(1)
            error_code = match.group(2)
            message = match.group(3)

            self._process_message(
                severity=severity,
                error_code=error_code,
                message=message,
                file_path="",
                line_num=0,
                col_num=0,
            )
            return

        # Check for lines compiled info
        # Format: "12345 lines, 2.5 seconds"
        lines_match = re.search(r"(\d+)\s+lines?", line, re.IGNORECASE)
        if lines_match:
            self.statistics.lines_compiled = int(lines_match.group(1))

    def _process_message(
        self,
        severity: str,
        error_code: Optional[str],
        message: str,
        file_path: str,
        line_num: int,
        col_num: int,
    ) -> None:
        """Process a compiler message and decide whether to include it.

        Args:
            severity: Message severity (Error, Warning, Hint, Fatal)
            error_code: Error code (e.g., "E2003", "W1011", "H2443")
            message: Error message text
            file_path: Source file path
            line_num: Line number
            col_num: Column number
        """
        # Normalize error code
        if error_code:
            error_code = error_code.upper()

        # Determine message type based on severity and error code
        is_error = self._is_error(severity, error_code)
        is_warning = self._is_warning(severity, error_code)
        is_hint = self._is_hint(severity, error_code)

        # Update statistics
        if is_warning:
            self.statistics.warnings_filtered += 1
            return  # Filter out warnings

        if is_hint:
            self.statistics.hints_filtered += 1
            return  # Filter out hints

        # Only keep errors and fatal errors
        if is_error:
            error = CompilationError(
                file=file_path or "(unknown)",
                line=line_num,
                column=col_num,
                message=message.strip(),
                error_code=error_code,
            )
            self.errors.append(error)

    def _is_error(self, severity: str, error_code: Optional[str]) -> bool:
        """Check if message is an error.

        Args:
            severity: Message severity (English or German)
            error_code: Error code

        Returns:
            True if message is an error
        """
        severity_lower = severity.lower()

        # Fatal is always an error (English: "fatal", German: "schwerwiegend")
        if severity_lower in ("fatal", "schwerwiegend"):
            return True

        # Error severity (English: "error", German: "fehler")
        if severity_lower in ("error", "fehler"):
            return True

        # Error codes starting with E or F
        if error_code and error_code[0] in ("E", "F"):
            return True

        return False

    def _is_warning(self, severity: str, error_code: Optional[str]) -> bool:
        """Check if message is a warning.

        Args:
            severity: Message severity (English or German)
            error_code: Error code

        Returns:
            True if message is a warning
        """
        # Warning severity (English: "warning", German: "warnung")
        if severity.lower() in ("warning", "warnung"):
            return True

        # Warning codes starting with W
        if error_code and error_code[0] == "W":
            return True

        return False

    def _is_hint(self, severity: str, error_code: Optional[str]) -> bool:
        """Check if message is a hint.

        Args:
            severity: Message severity (English or German)
            error_code: Error code

        Returns:
            True if message is a hint
        """
        # Hint severity (English: "hint", German: "hinweis")
        if severity.lower() in ("hint", "hinweis"):
            return True

        # Hint codes starting with H
        if error_code and error_code[0] == "H":
            return True

        return False
