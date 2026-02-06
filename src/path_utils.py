"""Path utilities for WSL-to-Windows path conversion."""

import re
import sys


# Matches WSL mount paths: /mnt/<single drive letter>/...
_WSL_PATH_PATTERN = re.compile(r"^/mnt/([a-zA-Z])(/.*)?$")


def convert_wsl_to_windows_path(path_str: str) -> str:
    """Convert a WSL-style path to a Windows path when running on Windows.

    When the MCP server runs as a Windows process (python.exe / uv.exe) but is
    called from a WSL environment, paths arrive in WSL format
    (e.g. ``/mnt/x/git_local/project/File.dproj``).  This function converts
    them to the equivalent Windows path
    (e.g. ``X:\\git_local\\project\\File.dproj``).

    On non-Windows platforms the path is returned unchanged.

    Args:
        path_str: The path string as received from the MCP client.

    Returns:
        The (possibly converted) path string.
    """
    if sys.platform not in ("win32", "win64"):
        return path_str

    match = _WSL_PATH_PATTERN.match(path_str)
    if not match:
        return path_str

    drive_letter = match.group(1).upper()
    rest = match.group(2) or ""
    windows_rest = rest.replace("/", "\\")
    return f"{drive_letter}:{windows_rest}"
