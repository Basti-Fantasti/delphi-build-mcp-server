# Design Document: Extend Configuration Feature

**Version:** 1.0
**Date:** 2026-01-21
**Target Release:** v1.5.0
**Status:** Draft

---

## 1. Overview

### 1.1 Purpose

Add the ability to extend an existing `delphi_config.toml` file with settings extracted from a new IDE build log. This allows users to incrementally add support for new platforms, configurations, or libraries without regenerating the entire configuration from scratch.

### 1.2 Background

Currently, two approaches exist for generating configuration files:

| Tool | Purpose | Limitation |
|------|---------|------------|
| `config_generator.py` | Generate config from single build log | Overwrites existing config |
| `multi_config_generator.py` | Generate config from multiple build logs | Requires all logs upfront |

**Gap:** No way to add a new platform (e.g., Win64x) to an existing working configuration without regenerating everything.

### 1.3 Decision

Implement a new `ConfigExtender` class with a corresponding MCP tool `extend_config_from_build_log`.

- **TOML Library:** Use standard `tomllib` for reading (Python 3.11+) / `tomli` for older versions
- **Comments:** Accept that user comments in existing config will be lost during extension
- **Output:** Generate clean, auto-formatted TOML output

---

## 2. Use Cases

### 2.1 Primary Use Cases

| ID | Use Case | Description |
|----|----------|-------------|
| UC-1 | Add new platform | User has Win32/Win64 config, wants to add Win64x support |
| UC-2 | Add new build configuration | User has Debug config, wants to add Release paths |
| UC-3 | Add new libraries | Project now uses additional third-party libraries |
| UC-4 | Update SDK paths | Linux SDK paths changed, need to update config |

### 2.2 User Stories

**US-1:** As a developer, I want to add Win64x platform support to my existing config by providing a Win64x build log, so that I don't have to regenerate my entire configuration.

**US-2:** As a developer, I want to extend my config with paths from a new library I've added to my project, so that compilation succeeds without manual config editing.

---

## 3. Technical Design

### 3.1 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      MCP Server (main.py)                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────┐ │
│  │ ConfigGenerator  │  │MultiConfigGen    │  │ConfigExtender│
│  │ (single log)     │  │(multiple logs)   │  │(extend)    │ │
│  └────────┬─────────┘  └────────┬─────────┘  └─────┬──────┘ │
│           │                     │                   │        │
│           └─────────────────────┼───────────────────┘        │
│                                 │                            │
│                    ┌────────────▼────────────┐               │
│                    │    BuildLogParser       │               │
│                    └─────────────────────────┘               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 New Components

#### 3.2.1 `ConfigExtender` Class

**Location:** `src/config_extender.py`

**Responsibilities:**
- Load and parse existing TOML configuration
- Parse new build log using `BuildLogParser`
- Merge new settings into existing configuration
- Handle path deduplication (case-insensitive on Windows)
- Generate updated TOML output

#### 3.2.2 `ExtendConfigResult` Model

**Location:** `src/models.py`

**Fields:**
- `success: bool` - Whether extension succeeded
- `config_file_path: str` - Path to updated config file
- `paths_added: int` - Number of new library paths added
- `paths_skipped: int` - Number of duplicate paths skipped
- `platforms_added: list[str]` - New platforms added (e.g., ["Win64x"])
- `message: str` - Human-readable result message

### 3.3 Merge Strategy

#### 3.3.1 Section Merge Rules

| Section | Merge Strategy |
|---------|----------------|
| `[delphi]` | Keep existing values, don't overwrite |
| `[paths.system]` | Add missing `lib_*` paths only |
| `[paths.libraries]` | Add new paths, skip duplicates |
| `[compiler.flags]` | Merge arrays, deduplicate |
| `[compiler.namespaces]` | Merge prefixes, deduplicate |
| `[compiler.aliases]` | Add missing aliases only |
| `[linux_sdk]` | Add if not present, don't overwrite |

#### 3.3.2 Path Deduplication

Paths are considered duplicates if they match after normalization:
1. Convert to lowercase
2. Replace backslashes with forward slashes
3. Remove trailing slashes
4. Expand environment variables for comparison

```python
def _normalize_path_for_comparison(self, path: str) -> str:
    """Normalize path for duplicate detection."""
    normalized = path.lower().replace("\\", "/").rstrip("/")
    # Expand ${USERNAME} for comparison
    username = os.getenv("USERNAME", "")
    normalized = normalized.replace("${username}", username.lower())
    return normalized
```

#### 3.3.3 Library Naming

When adding new library paths, generate unique names:
1. Derive name from path (existing `_derive_library_name` logic)
2. If name exists, append numeric suffix (`_2`, `_3`, etc.)
3. Track used names to avoid collisions

### 3.4 Data Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Existing Config │     │  New Build Log  │     │ Extended Config │
│ (TOML file)     │     │  (text file)    │     │ (TOML file)     │
└────────┬────────┘     └────────┬────────┘     └────────▲────────┘
         │                       │                       │
         ▼                       ▼                       │
┌─────────────────┐     ┌─────────────────┐              │
│ tomllib.load()  │     │ BuildLogParser  │              │
└────────┬────────┘     └────────┬────────┘              │
         │                       │                       │
         ▼                       ▼                       │
┌─────────────────────────────────────────┐              │
│           ConfigExtender._merge()        │              │
│  - Merge paths                          │              │
│  - Deduplicate                          │              │
│  - Add platform-specific settings       │              │
└────────────────────┬────────────────────┘              │
                     │                                   │
                     ▼                                   │
         ┌─────────────────────┐                         │
         │ _generate_toml()    │─────────────────────────┘
         └─────────────────────┘
```

---

## 4. API Design

### 4.1 MCP Tool Definition

**Tool Name:** `extend_config_from_build_log`

**Description:** Extend an existing delphi_config.toml with settings from a new IDE build log. Useful for adding support for new platforms or libraries.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `existing_config_path` | string | Yes | - | Path to existing delphi_config.toml |
| `build_log_path` | string | Yes | - | Path to IDE build log file |
| `output_config_path` | string | No | (overwrites existing) | Output path for extended config |
| `use_env_vars` | boolean | No | true | Replace paths with ${USERNAME} |

**Returns:** `ExtendConfigResult`

### 4.2 Python API

```python
from src.config_extender import ConfigExtender
from pathlib import Path

extender = ConfigExtender(use_env_vars=True)
result = extender.extend_from_build_log(
    existing_config_path=Path("delphi_config.toml"),
    build_log_path=Path("build_win64x.log"),
    output_path=Path("delphi_config.toml")  # Optional, defaults to overwrite
)

print(f"Added {result.paths_added} new paths")
print(f"Skipped {result.paths_skipped} duplicate paths")
print(f"New platforms: {result.platforms_added}")
```

### 4.3 CLI Interface

**Command:**
```bash
uv run python -m src.config_extender existing_config.toml build_log.log
uv run python -m src.config_extender existing_config.toml build_log.log -o extended_config.toml
uv run python -m src.config_extender existing_config.toml build_log.log --no-env-vars
```

**Arguments:**
- `existing_config` (positional): Path to existing config file
- `build_log` (positional): Path to build log file
- `-o, --output`: Output file path (default: overwrite existing)
- `--no-env-vars`: Don't use environment variable substitution

---

## 5. Implementation Details

### 5.1 File Structure

```
src/
├── config_extender.py      # NEW: ConfigExtender class
├── models.py               # ADD: ExtendConfigResult model
├── config_generator.py     # EXISTING: No changes
├── multi_config_generator.py # EXISTING: No changes
└── ...

main.py                     # ADD: extend_config_from_build_log tool
```

### 5.2 Class Structure

```python
# src/config_extender.py

class ConfigExtender:
    """Extends existing TOML configuration with new build log settings."""

    def __init__(self, use_env_vars: bool = True):
        """Initialize config extender."""

    def extend_from_build_log(
        self,
        existing_config_path: Path,
        build_log_path: Path,
        output_path: Optional[Path] = None,
    ) -> ExtendConfigResult:
        """Extend existing config with settings from build log."""

    def _load_existing_config(self, config_path: Path) -> dict:
        """Load and parse existing TOML configuration."""

    def _merge_configs(
        self,
        existing: dict,
        new_log_info: BuildLogInfo
    ) -> tuple[dict, MergeStatistics]:
        """Merge new build log info into existing config."""

    def _merge_system_paths(
        self,
        existing_system: dict,
        new_log_info: BuildLogInfo
    ) -> tuple[dict, int, int]:
        """Merge system library paths."""

    def _merge_library_paths(
        self,
        existing_libraries: dict,
        new_paths: list[Path]
    ) -> tuple[dict, int, int]:
        """Merge third-party library paths."""

    def _merge_namespaces(
        self,
        existing_ns: list[str],
        new_ns: list[str]
    ) -> list[str]:
        """Merge namespace prefix lists."""

    def _merge_aliases(
        self,
        existing_aliases: dict,
        new_aliases: dict
    ) -> dict:
        """Merge unit alias dictionaries."""

    def _is_duplicate_path(
        self,
        new_path: Path,
        existing_paths: list[str]
    ) -> bool:
        """Check if path already exists (case-insensitive)."""

    def _detect_new_platforms(
        self,
        existing_config: dict,
        new_log_info: BuildLogInfo
    ) -> list[str]:
        """Detect which platforms are being added."""

    def _generate_toml(self, config: dict) -> str:
        """Generate TOML content from merged config dictionary."""
```

### 5.3 Model Addition

```python
# src/models.py

class ExtendConfigResult(BaseModel):
    """Result of configuration extension operation."""

    success: bool = Field(description="Whether extension succeeded")
    config_file_path: str = Field(description="Path to extended config file")
    paths_added: int = Field(description="Number of new library paths added")
    paths_skipped: int = Field(description="Number of duplicate paths skipped")
    platforms_added: list[str] = Field(
        default_factory=list,
        description="New platforms added (e.g., ['Win64x'])"
    )
    settings_updated: dict[str, int] = Field(
        default_factory=dict,
        description="Count of settings updated per section"
    )
    message: str = Field(description="Human-readable result message")
```

### 5.4 MCP Tool Registration

```python
# main.py

@server.tool()
async def extend_config_from_build_log(
    existing_config_path: str,
    build_log_path: str,
    output_config_path: str = None,
    use_env_vars: bool = True,
) -> ExtendConfigResult:
    """Extend an existing delphi_config.toml with settings from a new IDE build log.

    This tool merges new paths and settings into an existing configuration file,
    useful for adding support for new platforms (e.g., Win64x) or libraries.

    Args:
        existing_config_path: Path to existing delphi_config.toml
        build_log_path: Path to IDE build log file
        output_config_path: Output path (default: overwrite existing)
        use_env_vars: Replace paths with ${USERNAME} (default: true)

    Returns:
        ExtendConfigResult with merge statistics
    """
```

---

## 6. Error Handling

### 6.1 Error Cases

| Error | Cause | Response |
|-------|-------|----------|
| `FileNotFoundError` | Existing config not found | Raise with helpful message |
| `FileNotFoundError` | Build log not found | Raise with helpful message |
| `ValueError` | Invalid TOML in existing config | Raise with parse error details |
| `ValueError` | Cannot parse build log | Raise with parser error |
| `PermissionError` | Cannot write output file | Raise with path info |

### 6.2 Warnings

- Warn if no new paths were added (config might already be complete)
- Warn if Delphi version in build log differs from existing config

---

## 7. Testing Plan

### 7.1 Unit Tests

| Test Case | Description |
|-----------|-------------|
| `test_extend_adds_new_platform` | Add Win64x to existing Win32/Win64 config |
| `test_extend_skips_duplicates` | Verify duplicate paths are not added |
| `test_extend_preserves_existing` | Existing paths/settings retained |
| `test_path_normalization` | Case-insensitive path comparison |
| `test_library_naming` | Unique names for new libraries |
| `test_namespace_merge` | Namespaces merged without duplicates |
| `test_alias_merge` | Aliases merged, existing not overwritten |
| `test_missing_config_error` | Proper error for missing config |
| `test_missing_build_log_error` | Proper error for missing log |

### 7.2 Integration Tests

| Test Case | Description |
|-----------|-------------|
| `test_extend_then_compile` | Extend config, then compile project |
| `test_mcp_tool_integration` | Test via MCP tool interface |
| `test_cli_interface` | Test command-line interface |

---

## 8. Documentation Updates

### 8.1 Files to Update

| File | Changes |
|------|---------|
| `README.md` | Add feature to Features list, add tool documentation, add usage example |
| `CHANGELOG.md` | Add v1.5.0 section with new feature |
| `pyproject.toml` | Bump version to 1.5.0 |
| `DOCUMENTATION.md` | Add detailed tool documentation |
| `QUICKSTART.md` | Add extend config example |

### 8.2 README Updates

**Features section:**
```markdown
- **Extend Configuration**: Add new platforms or libraries to existing config without regenerating
```

**Tools section:**
```markdown
### `extend_config_from_build_log`

Extend an existing configuration with settings from a new IDE build log.

**Parameters:**
- `existing_config_path` (required): Path to existing delphi_config.toml
- `build_log_path` (required): Path to IDE build log file
- `output_config_path`: Output path (default: overwrites existing)
- `use_env_vars`: Replace paths with ${USERNAME} (default: true)

**Returns:**
- `success`: Whether extension succeeded
- `paths_added`: Number of new paths added
- `paths_skipped`: Number of duplicates skipped
- `platforms_added`: List of new platforms (e.g., ["Win64x"])
```

### 8.3 CHANGELOG Entry

```markdown
## [1.5.0] - 2026-XX-XX

### Added

- **Extend Configuration Tool**: New `extend_config_from_build_log` MCP tool
  - Extend existing delphi_config.toml with settings from new build logs
  - Add support for new platforms without regenerating entire config
  - Intelligent path deduplication (case-insensitive)
  - Preserves existing settings while adding new ones
  - CLI support: `uv run python -m src.config_extender config.toml build.log`
```

---

## 9. Acceptance Criteria

- [ ] `ConfigExtender` class implemented in `src/config_extender.py`
- [ ] `ExtendConfigResult` model added to `src/models.py`
- [ ] MCP tool `extend_config_from_build_log` registered in `main.py`
- [ ] CLI interface implemented with argparse
- [ ] Path deduplication works case-insensitively
- [ ] Existing config values preserved (not overwritten)
- [ ] Unit tests pass with >80% coverage
- [ ] Integration test: extend config then compile succeeds
- [ ] README.md updated with new feature
- [ ] CHANGELOG.md updated with v1.5.0 entry
- [ ] pyproject.toml version bumped to 1.5.0
- [ ] Git tag v1.5.0 created and pushed

---

## 10. Open Questions

1. **Backup existing config?** Should we create a `.bak` file before overwriting?
   - **Decision:** No, users can use version control or manually backup

2. **Dry-run mode?** Should we support `--dry-run` to preview changes?
   - **Decision:** Nice-to-have for future version, not in v1.5.0

3. **Multiple build logs at once?** Support extending with multiple logs?
   - **Decision:** Out of scope, users can run extend multiple times

---

## Appendix A: Example Usage

### A.1 Adding Win64x Platform

**Before:** Config has Win32 and Win64 support

```bash
# Generate Win64x build log from IDE
# Then extend config:
uv run python -m src.config_extender delphi_config.toml build_win64x.log
```

**Output:**
```
Reading existing config: delphi_config.toml
Reading build log: build_win64x.log

[SUCCESS] Configuration extended successfully

New platforms added: Win64x
Paths added: 12
Paths skipped (duplicates): 63
Settings updated:
  - paths.system: 2 (lib_win64x_release, lib_win64x_debug)
  - paths.libraries: 10

Updated: delphi_config.toml
```

### A.2 MCP Tool Usage

```
User: Please extend my delphi_config.toml with the Win64x build log at build_win64x.log

Claude: I'll extend your configuration with the Win64x platform support.

[Calls extend_config_from_build_log tool]

Done! I've extended your configuration:
- Added Win64x platform support
- Added 2 new system library paths (lib_win64x_release, lib_win64x_debug)
- Added 10 new library paths
- Skipped 63 duplicate paths that were already in your config
```
