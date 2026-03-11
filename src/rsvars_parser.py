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
        self.rsvars_path = rsvars_path

    def parse(self) -> dict[str, str]:
        """Parse rsvars.bat and return extracted environment variables.

        Variables are expanded using previously parsed values and existing OS env.

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

                var_value = self._expand_vars(var_value, parsed_vars)
                parsed_vars[var_name] = var_value

        return parsed_vars

    def build_msbuild_env(self) -> dict[str, str]:
        """Build a complete environment for MSBuild execution.

        Merges parsed rsvars.bat variables onto the current OS environment.
        """
        env = os.environ.copy()
        parsed_vars = self.parse()
        env.update(parsed_vars)
        return env

    def _expand_vars(self, value: str, parsed_vars: dict[str, str]) -> str:
        """Expand %VARNAME% references in a value.

        Looks up variables in order: 1) already-parsed rsvars vars, 2) OS environment
        """
        def replace_var(match: re.Match) -> str:
            var_name = match.group(1)
            if var_name in parsed_vars:
                return parsed_vars[var_name]
            return os.environ.get(var_name, "")

        return self.VAR_REF_PATTERN.sub(replace_var, value)
