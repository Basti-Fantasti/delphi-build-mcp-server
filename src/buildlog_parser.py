"""Parser for Delphi IDE build logs to extract compiler settings."""

import re
from pathlib import Path

from src.models import BuildLogInfo, Platform


class BuildLogParser:
    """Parses IDE build logs to extract compiler configuration."""

    # Patterns for locating compiler command
    COMPILER_PATTERNS = [
        r"dcc32\.exe\s+(.+)",  # Win32 compiler
        r"dcc64\.exe\s+(.+)",  # Win64 compiler
        r"dcc32\s+Befehlszeile",  # German: command line
        r"dcc32\s+command\s+line",  # English: command line
        r"dcc64\s+Befehlszeile",  # German: command line
        r"dcc64\s+command\s+line",  # English: command line
    ]

    def __init__(self, build_log_path: Path):
        """Initialize parser with build log file path.

        Args:
            build_log_path: Path to the build log file
        """
        self.build_log_path = build_log_path
        self.log_content = ""

    def parse(self) -> BuildLogInfo:
        """Parse the build log and extract compiler information.

        Returns:
            BuildLogInfo with extracted configuration

        Raises:
            FileNotFoundError: If build log file doesn't exist
            ValueError: If compiler command cannot be found in log
        """
        self._read_log_file()
        compiler_command = self._extract_compiler_command()
        return self._parse_compiler_command(compiler_command)

    def _read_log_file(self) -> None:
        """Read the build log file content."""
        if not self.build_log_path.exists():
            raise FileNotFoundError(f"Build log not found: {self.build_log_path}")

        with open(self.build_log_path, "r", encoding="utf-8", errors="replace") as f:
            self.log_content = f.read()

    def _extract_compiler_command(self) -> str:
        """Extract the complete compiler command from the log.

        Returns:
            The complete compiler command line

        Raises:
            ValueError: If compiler command cannot be found
        """
        lines = self.log_content.split("\n")

        # Find the line with compiler path
        compiler_line_idx = None
        for idx, line in enumerate(lines):
            if re.search(r"dcc32\.exe|dcc64\.exe", line, re.IGNORECASE):
                compiler_line_idx = idx
                break

        if compiler_line_idx is None:
            raise ValueError("Compiler command not found in build log")

        # Collect the compiler command and all continuation lines
        # Continuation lines are indented with spaces
        command_lines = [lines[compiler_line_idx]]
        idx = compiler_line_idx + 1

        while idx < len(lines):
            line = lines[idx]
            # Check if line is a continuation (starts with spaces)
            if line and (line.startswith("  ") or line.startswith("\t")):
                command_lines.append(line.strip())
                idx += 1
            else:
                # Not a continuation line, stop
                break

        # Join all lines into one command
        full_command = " ".join(command_lines)
        return full_command

    def _parse_compiler_command(self, command: str) -> BuildLogInfo:
        """Parse the compiler command line to extract settings.

        Args:
            command: The complete compiler command line

        Returns:
            BuildLogInfo with extracted settings
        """
        # Detect compiler path and platform
        compiler_match = re.search(
            r"([a-z]:\\[^\"]+\\dcc(?:32|64)\.exe)", command, re.IGNORECASE
        )
        if not compiler_match:
            raise ValueError("Could not extract compiler path from command")

        compiler_path = Path(compiler_match.group(1))
        platform = Platform.WIN32 if "dcc32" in compiler_path.name.lower() else Platform.WIN64

        # Detect Delphi version from path
        version_match = re.search(r"Studio\\([\d.]+)", str(compiler_path), re.IGNORECASE)
        delphi_version = version_match.group(1) if version_match else "unknown"

        # Detect build configuration from paths
        build_config = "Debug" if "\\Debug" in command or "\\debug" in command else "Release"

        # Extract search paths from -U, -I, -R, -O flags
        search_paths = self._extract_search_paths(command)

        # Extract namespace prefixes from -NS flag
        namespace_prefixes = self._extract_namespace_prefixes(command)

        # Extract unit aliases from -A flag
        unit_aliases = self._extract_unit_aliases(command)

        # Extract other compiler flags
        compiler_flags = self._extract_compiler_flags(command)

        return BuildLogInfo(
            compiler_path=compiler_path,
            delphi_version=delphi_version,
            platform=platform,
            build_config=build_config,
            search_paths=search_paths,
            namespace_prefixes=namespace_prefixes,
            unit_aliases=unit_aliases,
            compiler_flags=compiler_flags,
        )

    def _extract_search_paths(self, command: str) -> list[Path]:
        """Extract all search paths from -U, -I, -R, -O flags.

        Args:
            command: The compiler command line

        Returns:
            List of unique search paths (deduplicated, order preserved)
        """
        all_paths: list[Path] = []

        # Patterns for different path flags
        # Match the flag followed by everything until the next - flag
        path_flags = ["-U", "-I", "-R", "-O"]

        for flag in path_flags:
            # Match flag followed by everything until we hit another dash flag
            # Use lookahead to stop at next flag like -LE, -LN, -NBC, etc.
            pattern = rf"{flag}(.*?)(?=\s+-[A-Z]+|\s+Working\.dpr|$)"
            matches = re.finditer(pattern, command, re.IGNORECASE | re.DOTALL)

            for match in matches:
                path_string = match.group(1)

                # Clean up the path string:
                # - Remove all quotes (both " and ')
                # - Replace newlines and carriage returns with spaces
                # - Normalize whitespace
                path_string = path_string.replace('"', '').replace("'", '')
                path_string = path_string.replace('\n', ' ').replace('\r', ' ')
                path_string = ' '.join(path_string.split())  # Normalize whitespace

                # Split by semicolons
                paths = [p.strip() for p in path_string.split(";") if p.strip()]

                # Filter and validate paths
                for p in paths:
                    # Skip empty or very short strings
                    if not p or len(p) < 3:
                        continue

                    # Must look like a path (contains : or \ or /)
                    if not any(char in p for char in [':', '\\', '/']):
                        continue

                    # Skip if it looks like a flag or other non-path content
                    if p.startswith('-') or p.startswith('$'):
                        continue

                    # Clean up the path
                    clean_path = p.strip()

                    # Handle paths that might have trailing garbage
                    # Stop at common flag prefixes
                    for stop_marker in [' -', ' Working.dpr', ' .dpr']:
                        if stop_marker in clean_path:
                            clean_path = clean_path.split(stop_marker)[0].strip()

                    if clean_path and len(clean_path) > 2:
                        try:
                            all_paths.append(Path(clean_path))
                        except Exception:
                            # Skip invalid paths
                            continue

        # Deduplicate while preserving order
        seen = set()
        unique_paths = []
        for path in all_paths:
            # Normalize path for comparison
            normalized = path.as_posix().lower()
            if normalized not in seen:
                seen.add(normalized)
                unique_paths.append(path)

        return unique_paths

    def _extract_namespace_prefixes(self, command: str) -> list[str]:
        """Extract namespace prefixes from -NS flag.

        Args:
            command: The compiler command line

        Returns:
            List of namespace prefixes
        """
        # Match -NS flag followed by everything until we hit another flag like -O, -R, -U, etc.
        # The namespace string may span multiple lines in the build log
        pattern = r"-NS(.*?)(?=\s+-[A-Z]|\s+\w+\.dpr|$)"
        match = re.search(pattern, command, re.IGNORECASE | re.DOTALL)

        if not match:
            return []

        namespace_string = match.group(1)
        # Clean up: remove newlines and extra whitespace
        namespace_string = namespace_string.replace('\n', '').replace('\r', '')
        namespace_string = ' '.join(namespace_string.split())  # Normalize whitespace

        # Split by semicolons and filter empty strings
        namespaces = [ns.strip() for ns in namespace_string.split(";") if ns.strip()]
        return namespaces

    def _extract_unit_aliases(self, command: str) -> dict[str, str]:
        """Extract unit name aliases from -A flag.

        Args:
            command: The compiler command line

        Returns:
            Dictionary mapping old names to new names
        """
        # Match -A flag followed by alias definitions
        pattern = r"-A([^\s]+)"
        match = re.search(pattern, command)

        if not match:
            return {}

        alias_string = match.group(1)
        aliases = {}

        # Split by semicolons to get individual alias definitions
        alias_defs = [a.strip() for a in alias_string.split(";") if a.strip()]

        for alias_def in alias_defs:
            # Each definition is OldName=NewName
            if "=" in alias_def:
                old_name, new_name = alias_def.split("=", 1)
                aliases[old_name.strip()] = new_name.strip()

        return aliases

    def _extract_compiler_flags(self, command: str) -> list[str]:
        """Extract other compiler flags (excluding paths, namespaces, aliases).

        Args:
            command: The compiler command line

        Returns:
            List of additional compiler flags
        """
        flags = []

        # Extract flags like -B, -Q, -$O-, --no-config, -TX.exe, etc.
        # Pattern matches:
        # 1. --flag-name (long flags like --no-config)
        # 2. -$X+ or -$X- (compiler switches)
        # 3. -TX.ext (target extension flags)
        # 4. -X (single letter flags like -B, -Q)
        flag_patterns = [
            r"(--[a-z][-a-z]*)",  # Long flags like --no-config
            r"(-\$[A-Z][+-]?)",   # Compiler switches like -$O-, -$W+
            r"(-T[A-Z]\.[a-z]+)", # Target extension like -TX.exe
            r"(-[A-Z])(?=\s|$)",  # Single letter flags like -B, -Q
        ]

        # Skip prefixes that are handled elsewhere
        skip_prefixes = ["-U", "-I", "-R", "-O", "-NS", "-A", "-D", "-E", "-LE", "-LN", "-NU", "-NB", "-NH", "-NO"]

        for pattern in flag_patterns:
            matches = re.finditer(pattern, command, re.IGNORECASE)
            for match in matches:
                flag = match.group(1)
                # Skip flags we've already processed elsewhere
                if not any(flag.upper().startswith(prefix) for prefix in skip_prefixes):
                    if flag not in flags:
                        flags.append(flag)

        return flags
