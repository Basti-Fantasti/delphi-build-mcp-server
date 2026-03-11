# MSBuild Hybrid Compilation Design

## Problem

The MCP server compiles Delphi projects by calling `dcc32.exe`/`dcc64.exe` directly, bypassing the IDE's MSBuild pipeline. This produces executables that differ from IDE builds:

- **Missing application icon** — the .dproj `Icon_MainIcon` is not embedded
- **Missing manifest** — `Manifest_File` (with `asInvoker` execution level) is not embedded, causing Windows installer detection heuristics to demand admin privileges for exe names containing "Setup"
- **Missing DPI awareness** — `AppDPIAwarenessMode` is not applied
- **Smaller file size** — ~250KB smaller due to missing resources

The root cause is that the IDE uses MSBuild targets (`BuildVersionResource`, `_PasCoreCompile`) which generate a `.vrc` containing icon, manifest, and version info references, compile it to `.res` via `cgrc.exe`, then invoke `dcc32.exe`. The MCP server's `ResourceCompiler` only handles version info.

## Solution

Use MSBuild for Windows targets (Win32/Win64/Win64x) to guarantee IDE-identical output. Keep direct dcc invocation for cross-compilation targets (Linux64/Android/Android64) where MSBuild CLI support is unreliable.

## Architecture

### Current Flow

```
compile_delphi_project → DelphiCompiler → dcc32/dcc64/dcclinux64
```

### New Flow

```
compile_delphi_project (in main.py handle_compile_project)
  1. Validate project file exists
  2. Parse .dproj with DProjParser to determine platform + config
  3. Route based on platform:
     → Win32/Win64/Win64x?
       → Load minimal config (only delphi.root_path needed)
       → MsBuildCompiler → msbuild.exe (with rsvars.bat environment)
       → MsBuildOutputParser → extracts dcc section → existing OutputParser
     → Linux64/Android/Android64?
       → Load full platform-specific config
       → DelphiCompiler → dcc* (unchanged)
```

The key restructuring: `.dproj` parsing is pulled out of `DelphiCompiler` into `handle_compile_project` so the routing decision can happen before compiler instantiation. `DProjParser` is called standalone to determine the effective platform, then the appropriate compiler is instantiated.

## Components

### New Files

#### `src/rsvars_parser.py`

Parses `rsvars.bat` from the Delphi installation to extract environment variables needed by MSBuild.

**Primary approach**: Read `rsvars.bat` line by line, extract `@SET` assignments into a dictionary. Apply these on top of the current process environment.

**Fallback approach**: If parsing fails (e.g., `rsvars.bat` format changes), fall back to running MSBuild via `cmd.exe /c "call rsvars.bat && msbuild.exe ..."`.

Location of `rsvars.bat`: `{delphi.root_path}/bin/rsvars.bat`

Expected variables set by `rsvars.bat`:
- `BDS` — Delphi installation root
- `BDSCOMMONDIR` — Common files directory
- `FrameworkDir`, `FrameworkVersion` — .NET framework location
- `PATH` — Extended with Delphi bin directory
- `LANGDIR` — Language directory
- `PLATFORM` — (not the target platform, the host platform)

#### `src/msbuild_compiler.py`

Orchestrates MSBuild compilation for Windows targets.

**Class: `MsBuildCompiler`**

Responsibilities:
- Locate `msbuild.exe` (from `rsvars.bat` environment PATH or known locations)
- Build MSBuild command line
- Execute MSBuild subprocess with correct environment
- Return `CompilationResult` (same model as `DelphiCompiler`)

**MSBuild command construction**:
```
msbuild.exe <project.dproj> /t:Build|Rebuild /p:Config=<Debug|Release> /p:Platform=<Win32|Win64|Win64x> /v:normal
```

- `/t:Build` for incremental builds, `/t:Rebuild` when `force_build_all=True`
- `/p:Config=<config>` maps to `override_config`
- `/p:Platform=<platform>` maps to `override_platform`
- `/v:normal` for sufficient output to parse warnings/errors

**Parameters handled differently from `DelphiCompiler`**:
- `additional_search_paths` — ignored with a warning in the output (MSBuild reads .dproj)
- `additional_flags` — ignored with a warning in the output (MSBuild reads .dproj)
- `force_build_all` — mapped to `/t:Rebuild` vs `/t:Build`

Note: When `additional_search_paths` or `additional_flags` are provided for a Windows target, a warning is included in the compilation output (e.g., "Warning: additional_search_paths ignored — MSBuild reads paths from .dproj"). This prevents silent confusion.

**Output executable detection**: `MsBuildCompiler` uses `DProjParser` to read `DCC_ExeOutput` from the .dproj to locate the output file. The `DProjSettings` are already parsed in `handle_compile_project` and passed to the compiler, so no duplicate parsing occurs.

**Resource compilation**: `MsBuildCompiler` does NOT run `ResourceCompiler` — MSBuild handles all resource compilation (icon, manifest, version info, DPI awareness) via its `BuildVersionResource` target.

**Timeout**: MSBuild builds may take longer than direct dcc due to resource compilation and pre/post-build events. The timeout is set to 10 minutes (vs 5 minutes for direct dcc).

**Note on `/p:Config`**: Delphi's MSBuild integration uses `/p:Config=` (not the standard MSBuild `/p:Configuration=`). This is Delphi-specific and must not be "corrected" to the standard form.

#### `src/msbuild_output_parser.py`

Extracts compiler output from MSBuild log and delegates to existing `OutputParser`.

**Class: `MsBuildOutputParser`**

Approach:
1. Find the `_PasCoreCompile` section in MSBuild output
2. Extract the dcc compiler output lines from that section
3. Feed extracted lines to the existing `OutputParser.parse()` method
4. Also detect MSBuild-level errors (e.g., target failures, missing files)

MSBuild output structure (from IDE build log analysis):
```
BuildVersionResource-Ziel:
    cgrc.exe ...
    <resource compiler output>
_PasCoreCompile-Ziel:
    dcc32.exe ...
    <compiler warnings/errors in format: path(line,col): warning WXXXX: message>
Erstellen des _PasCoreCompile-Ziels beendet.
```

The parser must handle both German and English MSBuild target names since the IDE locale affects output.

Known target name patterns:
- German: `_PasCoreCompile-Ziel:` / `Erstellen des _PasCoreCompile-Ziels beendet.`
- English: `_PasCoreCompile:` / `Done building target "_PasCoreCompile".`

The parser should match on `_PasCoreCompile` as a substring to be locale-agnostic.

### Modified Files

#### `main.py`

**`handle_compile_project`** restructuring:

The current flow has `DelphiCompiler.compile_project()` internally parsing the .dproj and loading the config. This must be restructured so the routing decision happens before compiler instantiation:

```python
async def handle_compile_project(arguments: dict) -> str:
    # 1. Validate and resolve project path
    project_path = Path(convert_wsl_to_windows_path(arguments["project_path"]))

    # 2. Parse .dproj to determine platform and config (standalone)
    dproj_path = project_path if project_path.suffix == ".dproj" else project_path.with_suffix(".dproj")
    dproj_parser = DProjParser(dproj_path)
    dproj_settings = dproj_parser.parse(override_config, override_platform)
    platform = dproj_settings.active_platform

    # 3. Route based on platform
    if platform in ("Win32", "Win64", "Win64x"):
        # Load minimal config (only needs delphi.root_path)
        config_loader = ConfigLoader(platform=platform)
        config = config_loader.load()
        compiler = MsBuildCompiler(delphi_root=config.delphi.root_path)
        result = compiler.compile_project(project_path, dproj_settings, ...)
    else:
        # Use existing DelphiCompiler for cross-compilation
        compiler = DelphiCompiler(config_loader=ConfigLoader(platform=platform))
        result = compiler.compile_project(project_path, ...)
```

#### `src/models.py`

**`SystemPaths`** changes:

Currently `rtl` and `vcl` are required `Path` fields. For the minimal Windows config (which has no `[paths.system]` section), these must become optional:

```python
class SystemPaths(BaseModel):
    rtl: Optional[Path] = None
    vcl: Optional[Path] = None
    lib_win32_release: Optional[Path] = None
    # ... etc
```

**`PathsConfig`** changes:

The `system` field should default to an empty `SystemPaths`:
```python
class PathsConfig(BaseModel):
    system: SystemPaths = SystemPaths()
    libraries: dict[str, Path] = {}
```

**`Config`** changes:

The `paths` field should default to an empty `PathsConfig`:
```python
class Config(BaseModel):
    delphi: DelphiConfig
    paths: PathsConfig = PathsConfig()
    compiler: CompilerConfig = CompilerConfig()
    # ... etc
```

This allows the minimal config (only `[delphi]` section) to load without crashing.

#### `src/config.py`

**`find_config_file_for_platform`** changes:

#### `src/config.py`

**`find_config_file_for_platform`** changes:

For Win32/Win64/Win64x:
1. Check `DELPHI_CONFIG` env var (unchanged)
2. Look for platform-specific file, e.g., `delphi_config_win32.toml` (backwards compatibility)
3. Fall back to generic `delphi_config.toml`

For Linux64/Android/Android64:
- Unchanged — require platform-specific config file with full paths

**`ConfigLoader`** changes:
- For Windows targets, only `delphi.root_path` is validated as required
- Search paths, flags, namespaces, aliases are optional (ignored by MSBuild)

**`_parse_config`** changes:
- Make `[paths]`, `[paths.system]`, `[compiler]` sections optional with sensible defaults
- When these sections are missing, create empty model instances

**`_validate_config`** changes:
- Accept a `platform` parameter to know whether MSBuild will be used
- For Windows platforms: only validate `delphi.root_path` exists, skip search path and library warnings
- For cross-compilation platforms: full validation as today (compiler paths, library paths, SDK paths)

#### `src/config_generator.py`

**`ConfigGenerator.generate_from_build_log`** changes:

When the detected platform is Win32/Win64/Win64x:
- Generate a minimal `delphi_config.toml` with only:
  - `[delphi]` section: `version`, `root_path`
  - A comment explaining MSBuild handles all other settings
- Default output filename: `delphi_config.toml` (not platform-specific, since one config covers all Windows targets)

When the detected platform is Linux64/Android/Android64:
- Unchanged — generate full config with all paths, flags, etc.
- Default output filename: platform-specific (e.g., `delphi_config_linux64.toml`)

#### `src/multi_config_generator.py`

When processing multiple build logs:
- Group Windows platform logs together — generate a single minimal `delphi_config.toml`
- Generate separate platform-specific configs for cross-compilation targets (unchanged)

#### `src/config_extender.py`

When extending for a Windows platform:
- Only merge `delphi.root_path` (if different)
- Skip search paths/flags since MSBuild handles those

### Unchanged Files

- `src/compiler.py` — Stays as-is, used for Linux64/Android
- `src/resource_compiler.py` — Still used by `DelphiCompiler` for cross-compilation
- `src/dproj_parser.py` — Used by both `handle_compile_project` (for platform routing) and `DelphiCompiler`; `MsBuildCompiler` uses the parsed `DProjSettings` for output path detection
- `src/output_parser.py` — Reused by `MsBuildOutputParser` for the extracted dcc section
- `src/buildlog_parser.py` — Unchanged, used by config generators

## Config File Strategy

### Before (current)

Each platform/config combination needs its own TOML:
- `delphi_config_win32.toml` (from Debug or Release build log)
- `delphi_config_win64.toml` (from Debug or Release build log)
- `delphi_config_linux64.toml`
- `delphi_config_android64.toml`

All contain full search paths, compiler flags, namespaces, aliases.

### After (new)

One generic config for all Windows targets:
```toml
# delphi_config.toml
# Minimal config — MSBuild reads all other settings from .dproj and registry

[delphi]
version = "23.0"
root_path = "c:/program files (x86)/embarcadero/studio/23.0"
```

Platform-specific configs only for cross-compilation:
- `delphi_config_linux64.toml` (full paths, flags, etc.)
- `delphi_config_android64.toml` (full paths, flags, etc.)

### Config Lookup Priority

1. `DELPHI_CONFIG` environment variable (always wins)
2. Platform-specific file (e.g., `delphi_config_win32.toml`) — backwards compatibility
3. Generic `delphi_config.toml` — new, sufficient for all Windows targets
4. Error if nothing found

For cross-compilation targets (Linux64/Android), step 3 is skipped — a platform-specific config is required since it contains SDK paths and compiler flags not available in any generic config.

## API

### `compile_delphi_project` Tool

**No changes to the tool interface.** Same parameters, same return type.

Behavioral changes:
- `additional_search_paths` — ignored with warning when MSBuild is used
- `additional_flags` — ignored with warning when MSBuild is used
- `force_build_all` — maps to `/t:Rebuild` (MSBuild) or `-B` flag (dcc)

### `generate_config_from_build_log` Tool

**No changes to the tool interface.**

Behavioral changes:
- Windows build logs produce a minimal `delphi_config.toml`
- Cross-compilation build logs produce full platform-specific configs (unchanged)
- Tool description updated to mention MSBuild for Windows targets

## WSL Path Handling

The existing `convert_wsl_to_windows_path` in `main.py` converts `/mnt/c/...` paths to `C:\...`. This applies to MSBuild as well — the `.dproj` path passed to `msbuild.exe` must be a Windows-native path. The conversion happens in `handle_compile_project` before reaching either compiler, so no changes are needed.

## Backwards Compatibility

- **Existing `delphi_config_win32.toml` / `delphi_config_win64.toml` files**: Continue to work. The config lookup checks for platform-specific files before falling back to generic `delphi_config.toml`. If a full config exists, it still loads — the extra paths/flags are simply unused by MSBuild.
- **Existing API callers**: No changes needed. Same tool name, same parameters, same return type.
- **`.dpk` (package) projects**: Work the same way with MSBuild — MSBuild handles packages identically to applications.

## Error Handling

### MSBuild Not Found

If `msbuild.exe` cannot be located via `rsvars.bat` or PATH:
- Return a clear error message explaining MSBuild is required for Windows compilation
- Suggest running from a Delphi command prompt or verifying the Delphi installation

### `rsvars.bat` Parsing Failure

If the primary parsing approach fails:
1. Log a warning
2. Fall back to `cmd.exe /c "call rsvars.bat && msbuild.exe ..."` approach
3. If that also fails, return error with details

### MSBuild Compilation Failure

If MSBuild returns non-zero exit code:
- Parse output for errors using `MsBuildOutputParser`
- Return `CompilationResult` with `success=False` and parsed errors
- Include MSBuild-level errors (not just dcc errors)

## Testing Strategy

### Unit Tests

- `test_rsvars_parser.py` — Parse sample `rsvars.bat` files, extract env vars
- `test_msbuild_compiler.py` — Command construction, environment setup (mocked execution)
- `test_msbuild_output_parser.py` — Parse sample MSBuild output, extract errors/warnings
- `test_config_generator.py` — Verify minimal config for Windows, full config for cross-compilation
- `test_config.py` — Verify config lookup falls back to generic `delphi_config.toml` for Windows

### Integration Tests

- Compile a real project with MSBuild and verify output matches IDE build
- Verify fallback from rsvars parsing to cmd.exe wrapper
- Verify cross-compilation targets still use direct dcc unchanged
