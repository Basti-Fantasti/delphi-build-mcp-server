# Resource Compilation Support

## Problem

The MCP server's `compile_project` tool only runs the Delphi Pascal compiler (dcc32/dcc64/dcclinux64). The IDE build process has a preceding step: compiling version resources with `cgrc.exe` (CodeGear Resource Compiler). Without this step, projects that rely on `{$R *.res}` for version info will fail or produce executables without embedded version information.

## Build Flow

IDE build order (from build logs):

1. **BuildVersionResource**: `cgrc.exe -c65001 Project.vrc -foProject.res`
2. **_PasCoreCompile**: `dcc32/dcc64/dcclinux64.exe ... Project.dpr`

The resource compiler is the same binary (`cgrc.exe` in `<delphi_root>/bin/`) for all target platforms.

## Design

### New Module: `src/resource_compiler.py`

Handles .vrc generation and cgrc.exe execution.

**Class: `ResourceCompiler`**
- Constructor takes `delphi_root: Path` (derives cgrc.exe path as `root/bin/cgrc.exe`)
- `compile_version_resource(project_name, project_dir, version_info)` -> `ResourceCompilationResult`
  - Generates `.vrc` file in project directory
  - Executes `cgrc.exe -c65001 <name>.vrc -fo<name>.res`
  - Deletes `.vrc` after successful compilation (matches IDE behavior)
  - Returns result with success/failure and any error output

**Class: `VrcGenerator`**
- `generate(project_name, version_info)` -> str (RC script content)
- Produces standard Windows VERSIONINFO resource script

### New Model: `VersionInfo` (in models.py)

```python
class VersionInfo(BaseModel):
    major: int = 0
    minor: int = 0
    release: int = 0
    build: int = 0
    locale: int = 1033
    keys: dict[str, str] = {}  # CompanyName, FileDescription, etc.

class ResourceCompilationResult(BaseModel):
    success: bool
    res_file: Optional[str]  # Path to .res if successful
    error_output: Optional[str]
```

### Changes to `src/dproj_parser.py`

Extract version info from PropertyGroups:

- `VerInfo_IncludeVerInfo` - bool flag (default true when VerInfo_Keys present)
- `VerInfo_Keys` - semicolon-separated key=value pairs
- `VerInfo_MajorVer`, `VerInfo_MinorVer`, `VerInfo_Release`, `VerInfo_Build` - individual version numbers
- `VerInfo_Locale` - locale ID (default 1033)

Both .dproj formats supported:
1. **VerInfo_Keys style** (newer): version from `FileVersion` key value
2. **Individual VerInfo_* style** (older): version from separate XML elements

New field on `DProjSettings`: `version_info: Optional[VersionInfo]`

### Changes to `src/compiler.py`

In `compile_project()`, after config loading, before dcc execution:

```python
if dproj_settings and dproj_settings.version_info:
    rc = ResourceCompiler(self.config.delphi.root_path)
    rc_result = rc.compile_version_resource(
        project_name=source_path.stem,
        project_dir=source_path.parent,
        version_info=dproj_settings.version_info,
    )
    if not rc_result.success:
        return CompilationResult(success=False, ...)
```

### Changes to `src/buildlog_parser.py`

Extract cgrc.exe command from IDE build logs:
- Match `cgrc.exe` lines in the log
- Extract resource compiler path
- Store as `resource_compiler_path: Optional[Path]` on `BuildLogInfo`

### Changes to `src/config.py`

Add `get_resource_compiler_path()` to `ConfigLoader`:
- Returns `root_path / "bin" / "cgrc.exe"`

### .vrc Format

Standard Windows RC VERSIONINFO block:

```rc
1 VERSIONINFO
FILEVERSION 1,0,0,0
PRODUCTVERSION 1,0,0,0
FILEFLAGSMASK 0x3FL
FILEFLAGS 0x0L
FILEOS 0x40004L
FILETYPE 0x1L
FILESUBTYPE 0x0L
BEGIN
  BLOCK "StringFileInfo"
  BEGIN
    BLOCK "040904E4"
    BEGIN
      VALUE "CompanyName", "...\0"
      VALUE "FileVersion", "1.0.0.0\0"
      ...
    END
  END
  BLOCK "VarFileInfo"
  BEGIN
    VALUE "Translation", 0x0409 0x04E4
  END
END
```

### Error Handling

- cgrc.exe not found: clear error message, no dcc execution
- .vrc generation failure: error return, no dcc execution
- cgrc.exe non-zero exit: parse stderr, return error, no dcc execution
- All resource errors surfaced in `CompilationResult`

### Testing

- VersionInfo extraction from .dproj (both VerInfo_Keys and individual property formats)
- .vrc content generation (verify correct RC syntax)
- Resource compiler command building
- BuildLogParser cgrc.exe extraction
- Compiler integration: resource step before dcc
