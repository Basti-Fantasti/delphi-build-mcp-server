# Delphi Build MCP Server - Complete Documentation

Comprehensive documentation for the Delphi Build MCP Server.

## Table of Contents

1. [Overview](#overview)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Available Tools](#available-tools)
5. [How It Works](#how-it-works)
6. [Advanced Usage](#advanced-usage)
7. [Troubleshooting](#troubleshooting)
8. [API Reference](#api-reference)
9. [Examples](#examples)

---

## Overview

### What is the Delphi Build MCP Server?

The Delphi Build MCP Server is a Model Context Protocol (MCP) server that enables AI coding agents like Claude Code to compile Delphi projects programmatically. It bridges the gap between AI-assisted development and the Delphi command-line compiler.

### Key Features

- **Automatic Configuration**: Generate config from IDE build logs with multi-line parsing
- **Smart Compilation**: Reads .dproj files for build settings
- **Filtered Output**: Returns only errors, filters warnings and hints
- **Multiple Platforms**: Supports Win32 and Win64
- **Multiple Configurations**: Handles Debug, Release, and custom configs
- **Environment Variables**: Auto-expands ${USERNAME} and other variables
- **Error Parsing**: Extracts file, line, column, and message from errors
- **Multi-Language Support**: Parses both English and German compiler output
- **Response File Support**: Handles command lines >8000 characters automatically
- **80+ Library Paths**: Successfully handles projects with extensive dependencies

### Architecture

```
┌─────────────────┐
│   Claude Code   │
│   (MCP Client)  │
└────────┬────────┘
         │ MCP Protocol
         ▼
┌─────────────────────────────────────┐
│   Delphi Build MCP Server           │
├─────────────────────────────────────┤
│ Tools:                              │
│ • compile_delphi_project            │
│ • generate_config_from_build_log    │
├─────────────────────────────────────┤
│ Components:                         │
│ • .dproj Parser                     │
│ • Build Log Parser                  │
│ • Compiler Output Parser            │
│ • Config Manager                    │
└────────┬────────────────────────────┘
         │ Command Line
         ▼
┌─────────────────┐
│ dcc32.exe       │
│ dcc64.exe       │
└─────────────────┘
```

---

## Installation

### Prerequisites

- **Delphi**: Version 11.x, 12.x, or 13.x
- **Python**: 3.10 or higher
- **MCP Client**: Claude Code or compatible

### Install via UV (Recommended)

First, install UV if you haven't already:

```bash
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using pip
pip install uv
```

Then clone and install the MCP server:

```bash
git clone https://github.com/Basti-Fantasti/delphi-build-mcp-server.git
cd delphi-build-mcp-server
uv sync
```

### Verify Installation

```bash
uv run python main.py --version
```

---

## Configuration

### Configuration File Location

The server looks for `delphi_config.toml` in:

1. Path specified in `DELPHI_CONFIG` environment variable
2. Current working directory
3. MCP server directory

### Configuration File Structure

```toml
# delphi_config.toml

[delphi]
version = "23.0"
root_path = "C:/Program Files (x86)/Embarcadero/Studio/23.0"

[paths.system]
rtl = "C:/Program Files (x86)/Embarcadero/Studio/23.0/source/rtl/common"
vcl = "C:/Program Files (x86)/Embarcadero/Studio/23.0/source/vcl"
lib_win32_release = "C:/Program Files (x86)/Embarcadero/Studio/23.0/lib/win32/release"
lib_win32_debug = "C:/Program Files (x86)/Embarcadero/Studio/23.0/lib/win32/debug"

[paths.libraries]
dunitx = "C:/Program Files (x86)/Embarcadero/Studio/23.0/source/DunitX"
spring4d = "X:/Delphi_libs/D12/spring4d/Library/Delphi12/Win32"
# ... more libraries

[compiler.namespaces]
prefixes = ["Winapi", "System.Win", "Data.Win", "System", "Vcl"]

[compiler.aliases]
"WinTypes" = "Winapi.Windows"
"SysUtils" = "System.SysUtils"
# ... more aliases
```

### Generating Configuration Automatically

See [Quick Start Guide](QUICKSTART.md#step-2-generate-configuration-from-ide-build-log) for instructions on generating config from a build log.

### Environment Variables

The config file supports environment variable expansion:

```toml
[paths.libraries]
# Uses ${USERNAME} which expands at runtime
testinsight = "C:/Users/${USERNAME}/AppData/Local/Programs/TestInsight/Source"
```

**Supported variables:**
- `${USERNAME}` - Current Windows username
- `${USERPROFILE}` - User profile directory
- `${PROGRAMFILES}` - Program Files directory
- `${PROGRAMFILES(X86)}` - Program Files (x86) directory
- Any custom environment variable

---

## Available Tools

### Tool 1: `compile_delphi_project`

Compile a Delphi project and return parsed results.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `project_path` | string | **Yes** | - | Absolute path to .dpr or .dproj file |
| `force_build_all` | boolean | No | false | Force rebuild all units (-B flag) |
| `override_config` | string | No | null | Override active build config ("Debug", "Release") |
| `override_platform` | string | No | null | Override active platform ("Win32", "Win64") |
| `additional_search_paths` | array | No | [] | Extra unit search paths |
| `additional_flags` | array | No | [] | Additional compiler flags |

#### Return Value

```json
{
  "success": true,
  "exit_code": 0,
  "errors": [
    {
      "file": "Unit1.pas",
      "line": 42,
      "column": 15,
      "message": "Undeclared identifier: 'Foo'",
      "error_code": "E2003"
    }
  ],
  "compilation_time_seconds": 2.5,
  "output_executable": "C:\\MyProject\\Win32\\Debug\\MyApp.exe",
  "statistics": {
    "lines_compiled": 15234,
    "warnings_filtered": 3,
    "hints_filtered": 12
  }
}
```

#### Example Usage

**From Claude Code:**
```
Please compile X:\MyProjects\MyApp\MyApp.dproj
```

**Direct MCP call:**
```json
{
  "method": "tools/call",
  "params": {
    "name": "compile_delphi_project",
    "arguments": {
      "project_path": "X:\\MyProjects\\MyApp\\MyApp.dproj"
    }
  }
}
```

---

### Tool 2: `generate_config_from_build_log`

Generate `delphi_config.toml` from an IDE build log.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `build_log_path` | string | **Yes** | - | Path to IDE build log |
| `output_config_path` | string | No | "delphi_config.toml" | Output file path |
| `use_env_vars` | boolean | No | true | Replace paths with ${USERNAME} |

#### Return Value

```json
{
  "success": true,
  "config_file_path": "X:\\delphi-build-mcp-server\\delphi_config.toml",
  "statistics": {
    "total_paths_found": 127,
    "unique_paths": 58,
    "compiler_flags_found": 15
  },
  "detected_info": {
    "delphi_version": "23.0",
    "platform": "Win32",
    "build_config": "Debug",
    "compiler_executable": "C:\\Program Files (x86)\\Embarcadero\\Studio\\23.0\\bin\\dcc32.exe"
  },
  "message": "Configuration file generated successfully with 58 library paths"
}
```

#### How to Get a Build Log

**Method 1: IDE Messages Window**
1. Tools → Options → Building → Show compiler progress → "Verbose"
2. Build your project
3. View → Messages
4. Right-click → Copy All
5. Paste into a text file

**Method 2: Build Output Redirection**
```bash
msbuild MyProject.dproj /v:detailed > build.log 2>&1
```

**Method 3: IDE Build Events**
1. Project → Options → Building → Build Events
2. Post-build event: `copy $(MSGS) build.log`

#### Example Usage

**From Claude Code:**
```
I have a build log at C:\MyProject\build.log. Please generate a Delphi configuration from it.
```

---

## How It Works

### Compilation Process Flow

```
1. Tool Call: compile_delphi_project
   ↓
2. Load delphi_config.toml
   • Read Delphi installation paths
   • Load library search paths
   • Load namespace/alias settings
   ↓
3. Parse .dproj file (if present)
   • Detect active configuration (Debug/Release)
   • Detect active platform (Win32/Win64)
   • Extract compiler flags and defines
   • Extract project-specific search paths
   • Get output directories
   ↓
4. Merge configurations
   • Config file library paths
   • .dproj search paths
   • .dproj compiler flags
   • Additional tool parameters
   ↓
5. Select compiler
   • Win32 → dcc32.exe
   • Win64 → dcc64.exe
   ↓
6. Build command line
   • Compiler flags from .dproj
   • Search paths (-U, -I, -R, -O) - excludes RTL/VCL sources
   • Namespace prefixes (-NS)
   • Unit aliases (-A)
   • Defines (-D)
   • Output paths (-E, -N, -NH, -NU)
   ↓
7. Execute compiler
   • If command line >8000 chars → Create response file (@file.rsp)
   • Run as subprocess
   • Capture stdout/stderr
   • Cleanup response file
   ↓
8. Parse output (English/German)
   • Extract errors (E####, F####, Fehler, Schwerwiegend)
   • Filter warnings (W####, Warnung)
   • Filter hints (H####, Hinweis)
   • Extract file:line:col info
   ↓
9. Return results
   • Structured error list
   • Statistics
   • Output executable path
```

### .dproj File Parsing

The server parses .dproj files (MSBuild XML format) to extract:

#### Active Configuration Detection

```xml
<PropertyGroup>
  <Configuration Condition="'$(Configuration)'==''">Debug</Configuration>
  <Platform Condition="'$(Platform)'==''">Win32</Platform>
</PropertyGroup>
```

#### Configuration-Specific Settings

```xml
<PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Debug|Win32'">
  <DCC_Define>DEBUG</DCC_Define>
  <DCC_Optimize>false</DCC_Optimize>
  <DCC_DebugInfoInExe>true</DCC_DebugInfoInExe>
  <DCC_UnitSearchPath>$(DCC_UnitSearchPath);X:\MyLibs</DCC_UnitSearchPath>
</PropertyGroup>
```

#### Compiler Flags Mapping

| .dproj Property | Compiler Flag | Description |
|-----------------|---------------|-------------|
| `DCC_Define` | `-D` | Conditional defines |
| `DCC_Optimize` | `-$O+/-` | Optimization |
| `DCC_DebugInfoInExe` | `-$D+/-` | Debug info |
| `DCC_UnitSearchPath` | `-U` | Unit search paths |
| `DCC_IncludePath` | `-I` | Include paths |
| `DCC_ResourcePath` | `-R` | Resource paths |
| `DCC_Namespace` | `-NS` | Namespace prefixes |
| `DCC_ExeOutput` | `-E` | Executable output |
| `DCC_DcuOutput` | `-NU` | DCU output |

### Build Log Parsing

The config generator parses compiler command lines from build logs:

#### Multi-line Command Parsing

Build logs often span multiple lines:
```
dcc32 Befehlszeile für "MyApp.dpr"
  c:\program files (x86)\embarcadero\studio\23.0\bin\dcc32.exe -$O- -B -Q
  -U"path1";"path2";
  "path3" MyApp.dpr
```

The parser:
1. Detects the compiler command line start
2. Uses `re.DOTALL` regex flag to match across line boundaries
3. Reads continuation lines (lines starting with spaces/tabs)
4. Handles quoted paths with spaces
5. Extracts all `-U`, `-I`, `-R`, `-O` paths (successfully extracts 80+ paths)
6. Deduplicates while preserving order
7. **Fully functional** - tested with 83 paths extracted from complex build logs

#### Path Extraction

```
Input:  -U"c:\program files\...";C:\Users\Teufel\...;X:\Libs\...
Output:
  - c:/program files/...
  - C:/Users/${USERNAME}/...
  - X:/Libs/...
```

#### Language Detection

Supports localized output:
- **German**: "dcc32 Befehlszeile", "Erfolg"
- **English**: "dcc32 command line", "Success"
- **French**: "ligne de commande dcc32", "Succès"

---

## Advanced Usage

### Custom Build Configurations

Override the active configuration from .dproj:

```json
{
  "project_path": "MyApp.dproj",
  "override_config": "Release",
  "override_platform": "Win64"
}
```

### Additional Search Paths

Add extra paths at runtime:

```json
{
  "project_path": "MyApp.dproj",
  "additional_search_paths": [
    "X:\\ExtraLibs\\Lib1",
    "X:\\ExtraLibs\\Lib2"
  ]
}
```

### Force Full Rebuild

Force recompilation of all units:

```json
{
  "project_path": "MyApp.dproj",
  "force_build_all": true
}
```

### Custom Compiler Flags

Add additional compiler flags:

```json
{
  "project_path": "MyApp.dproj",
  "additional_flags": [
    "-$D+",    // Debug info on
    "-$L+",    // Local symbols
    "-V"       // Verbose
  ]
}
```

### Response File Support (Automatic)

When your project has many library paths and the compiler command line exceeds 8000 characters, the server automatically:

1. Creates a temporary response file: `project_dir/delphi_compile.rsp`
2. Writes all compiler arguments to the file (one per line)
3. Invokes compiler with: `dcc32.exe @delphi_compile.rsp`
4. Cleans up the response file after compilation

**This happens automatically** - you don't need to configure anything. The server handles projects with 80+ library paths without issues.

### Multi-Language Compiler Output

The output parser automatically detects and handles both English and German compiler messages:

| Message Type | English | German |
|--------------|---------|--------|
| Error | Error, Fatal | Fehler, Schwerwiegend |
| Warning | Warning | Warnung |
| Hint | Hint | Hinweis |

Error codes (E####, W####, H####, F####) are recognized in all languages.

### Registry Parser (Alternative Method)

A Windows Registry parser is included (`src/registry_parser.py`) as an alternative to build log parsing:

```python
from src.registry_parser import RegistryParser
from pathlib import Path

# Parse library paths from Windows Registry
parser = RegistryParser(delphi_version="23.0", platform="Win32")
build_info = parser.parse()

print(f"Found {len(build_info.search_paths)} paths in registry")
```

**Note:** This is NOT integrated into the main workflow. The build log parser is fully functional and preferred for config generation.

---

## Troubleshooting

### Common Issues

#### Issue: "CONFIG_NOT_FOUND"

**Error Message:**
```
Configuration file not found: delphi_config.toml
```

**Solutions:**
1. Generate config from build log (see Quick Start)
2. Copy template: `cp delphi_config.toml.template delphi_config.toml`
3. Set `DELPHI_CONFIG` environment variable
4. Place config in MCP server directory

---

#### Issue: "Unit not found"

**Error Message:**
```
Fatal: E2202 Required package 'rtl' not found
```

**Solutions:**

1. **Check system paths in config:**
```toml
[paths.system]
rtl = "C:/Program Files (x86)/Embarcadero/Studio/23.0/source/rtl/common"
lib_win32_release = "C:/Program Files (x86)/Embarcadero/Studio/23.0/lib/win32/release"
```

2. **Regenerate config from fresh build log** (recommended)

3. **Add missing path manually:**
```toml
[paths.libraries]
missing_lib = "X:/path/to/library"
```

---

#### Issue: "Compiler not found"

**Error Message:**
```
Delphi compiler not found at: C:\Program Files (x86)\Embarcadero\Studio\23.0\bin\dcc32.exe
```

**Solutions:**

1. **Verify Delphi installation:**
```bash
dir "C:\Program Files (x86)\Embarcadero\Studio\23.0\bin\dcc32.exe"
```

2. **Update config with correct version:**
```toml
[delphi]
version = "22.0"  # For Delphi 11
# or
version = "23.0"  # For Delphi 12
```

3. **Specify compiler path explicitly:**
```toml
[delphi]
compiler_win32 = "C:/Program Files (x86)/Embarcadero/Studio/22.0/bin/dcc32.exe"
```

---

#### Issue: Path with spaces causing errors

**Error Message:**
```
Error: Invalid parameter: Files
```

**Cause:** Path not properly quoted

**Solution:** The server handles this automatically, but if manually editing config, use forward slashes and quote if needed:

```toml
# Good
lockbox = "C:/Users/Username/Documents/Embarcadero/Studio/23.0/CatalogRepository/LockBox-12-64bit/run/library surface"

# Also works
lockbox = 'C:/Users/Username/Documents/Embarcadero/Studio/23.0/CatalogRepository/LockBox-12-64bit/run/library surface'
```

---

#### Issue: Different build results than IDE

**Cause:** Active configuration mismatch

**Solution:**

1. **Check .dproj active config:**
```xml
<Configuration Condition="'$(Configuration)'==''">Debug</Configuration>
```

2. **Override if needed:**
```json
{
  "project_path": "MyApp.dproj",
  "override_config": "Debug",
  "override_platform": "Win32"
}
```

3. **Regenerate config from correct build:**
- Build the project in IDE with the desired configuration
- Generate new build log
- Regenerate config file

---

### Debug Mode

Enable debug output to see detailed compilation process:

```toml
[server]
debug = true
log_level = "DEBUG"
```

This outputs:
- Full compiler command line
- All search paths
- Parsed .dproj settings
- Raw compiler output

---

## API Reference

### Configuration Schema

#### `[delphi]` Section

```toml
[delphi]
version = "string"              # Required: Delphi version ("22.0", "23.0")
root_path = "string"            # Required: Delphi installation root
compiler_win32 = "string"       # Optional: Override dcc32.exe path
compiler_win64 = "string"       # Optional: Override dcc64.exe path
```

#### `[paths.system]` Section

```toml
[paths.system]
rtl = "string"                  # Required: RTL source path (NOT used in compilation)
vcl = "string"                  # Required: VCL source path (NOT used in compilation)
lib_win32_release = "string"    # Optional: Win32 release libs (.dcu files) - USED
lib_win32_debug = "string"      # Optional: Win32 debug libs (.dcu files) - USED
lib_win64_release = "string"    # Optional: Win64 release libs (.dcu files) - USED
lib_win64_debug = "string"      # Optional: Win64 debug libs
```

**Important Note:** RTL and VCL source paths are stored in the configuration for reference but are **NOT** added to the compiler's search paths. The compiler already knows where to find its own runtime library. Adding RTL/VCL source paths to the search paths would cause the compiler to attempt recompiling the RTL from source, which requires .obj files and will fail with errors like `E1026 File not found: 'ftol.obj'`. Only the `lib_*` paths (containing compiled .dcu files) are passed to the compiler.

#### `[paths.libraries]` Section

```toml
[paths.libraries]
# All optional - add as many as needed
library_name = "string"
another_lib = "string"
```

#### `[compiler.namespaces]` Section

```toml
[compiler.namespaces]
prefixes = [
  "Winapi",
  "System.Win",
  "System",
  "Vcl"
]
```

#### `[compiler.aliases]` Section

```toml
[compiler.aliases]
"OldName" = "NewName"
"WinTypes" = "Winapi.Windows"
```

---

## Examples

### Example 1: Simple Compilation

**Request:**
```
Please compile MyApp.dproj
```

**MCP Call:**
```json
{
  "name": "compile_delphi_project",
  "arguments": {
    "project_path": "X:\\Projects\\MyApp\\MyApp.dproj"
  }
}
```

**Response:**
```json
{
  "success": true,
  "exit_code": 0,
  "errors": [],
  "compilation_time_seconds": 1.8,
  "output_executable": "X:\\Projects\\MyApp\\Win32\\Debug\\MyApp.exe",
  "statistics": {
    "lines_compiled": 5420,
    "warnings_filtered": 0,
    "hints_filtered": 8
  }
}
```

---

### Example 2: Compilation with Errors

**Request:**
```
Compile MyApp.dproj
```

**Response:**
```json
{
  "success": false,
  "exit_code": 1,
  "errors": [
    {
      "file": "Unit1.pas",
      "line": 42,
      "column": 15,
      "message": "Undeclared identifier: 'Calculate'",
      "error_code": "E2003"
    },
    {
      "file": "Unit2.pas",
      "line": 78,
      "column": 3,
      "message": "Incompatible types: 'String' and 'Integer'",
      "error_code": "E2010"
    }
  ],
  "compilation_time_seconds": 0.9,
  "output_executable": null,
  "statistics": {
    "lines_compiled": 3200,
    "warnings_filtered": 2,
    "hints_filtered": 5
  }
}
```

---

### Example 3: Config Generation

**Request:**
```
Generate config from X:\build.log
```

**MCP Call:**
```json
{
  "name": "generate_config_from_build_log",
  "arguments": {
    "build_log_path": "X:\\build.log",
    "output_config_path": "delphi_config.toml",
    "use_env_vars": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "config_file_path": "X:\\delphi-build-mcp-server\\delphi_config.toml",
  "statistics": {
    "total_paths_found": 89,
    "unique_paths": 47,
    "compiler_flags_found": 12
  },
  "detected_info": {
    "delphi_version": "23.0",
    "platform": "Win32",
    "build_config": "Debug",
    "compiler_executable": "C:\\Program Files (x86)\\Embarcadero\\Studio\\23.0\\bin\\dcc32.exe"
  },
  "message": "Configuration file generated successfully with 47 library paths"
}
```

---

### Example 4: AI-Assisted Development Workflow

**Full conversation flow:**

```
User: I want to add a new feature to my Delphi app. It's at X:\MyApp\MyApp.dproj

Claude: I'll help you add a new feature. First, let me compile the project to make sure it's in a working state.

[Calls compile_delphi_project]

Great! The project compiles successfully. What feature would you like to add?

User: Add a JSON export function to the TCustomer class

Claude: I'll add a JSON export function. Let me first read the Customer unit...

[Reads TCustomer.pas]

Now I'll add the export function...

[Edits file to add ToJSON method]

Let me compile to verify the changes...

[Calls compile_delphi_project]

Perfect! The new JSON export function compiles without errors. I've added:

1. Uses clause: System.JSON
2. Method: function ToJSON: TJSONObject;
3. Implementation with all customer fields

Would you like me to add a corresponding FromJSON method as well?
```

---

## Best Practices

### 1. Always Use .dproj Files

**Why:** .dproj files contain all compiler settings and ensure the MCP server compiles exactly like the IDE.

**How:** When creating projects, use "File → New → Project" in the IDE to generate both .dpr and .dproj files.

### 2. Keep Config File Updated

**When to update:**
- After installing new libraries via GetIt
- After adding components to the IDE
- After upgrading Delphi version
- After changing library paths in IDE

**How:** Regenerate from a fresh build log.

### 3. Use Verbose Build Logs

**Why:** Captures all compiler paths and flags.

**How:** Tools → Options → Building → Show compiler progress → "Verbose"

### 4. Separate Configs for Different Machines

**Why:** Library paths may differ across development machines.

**How:** Use machine-specific config files:
```bash
delphi_config.machine1.toml
delphi_config.machine2.toml
```

Set via environment variable:
```bash
set DELPHI_CONFIG=delphi_config.machine1.toml
```

### 5. Version Control

**Include in git:**
- `delphi_config.toml.template` (generic template)
- `.gitignore` entry for `delphi_config.toml` (machine-specific)

**Exclude from git:**
- `delphi_config.toml` (contains machine-specific paths)
- `build.log` (build artifacts)

### 6. CI/CD Integration

For continuous integration:

```yaml
# .github/workflows/build.yml
steps:
  - name: Install UV
    run: |
      curl -LsSf https://astral.sh/uv/install.sh | sh

  - name: Setup Delphi MCP Server
    run: |
      cd delphi-build-mcp-server
      uv venv
      uv pip install -e .
      uv run python -m src.config_generator ci-build.log

  - name: Compile Project
    run: |
      cd delphi-build-mcp-server
      uv run python -m src.compiler MyApp.dproj --platform Win32 --config Release
```

---

## Performance Tips

### 1. Incremental Compilation

Avoid `force_build_all` unless necessary:

```json
{
  "project_path": "MyApp.dproj",
  "force_build_all": false  // Default: only recompile changed units
}
```

### 2. Minimal Library Paths

Remove unused library paths from config to speed up unit resolution.

### 3. DCU Caching

Let Delphi cache DCU files for faster subsequent builds.

---

## Security Considerations

### Path Validation

The server validates all paths before compilation to prevent injection attacks.

### Sandboxing

Consider running the MCP server in a restricted environment for untrusted code compilation.

### Credential Protection

Never include credentials or API keys in Delphi source files that may be read by the AI agent.

---

## Changelog

### Version 1.0.0 (Planned)
- Initial release
- `compile_delphi_project` tool
- `generate_config_from_build_log` tool
- .dproj file parsing
- Build log parsing
- Output filtering (warnings/hints)

### Version 1.1.0 (Future)
- Package (.dpk) compilation support
- Multiple configuration support
- Build cache optimization

---

## Contributing

Contributions are welcome! Please see CONTRIBUTING.md for guidelines.

---

## License

MIT License - see LICENSE file for details.

---

## Support

- **Documentation**: This file
- **Quick Start**: [QUICKSTART.md](QUICKSTART.md)
- **Issues**: https://github.com/your-org/delphi-build-mcp-server/issues
- **Discussions**: https://github.com/your-org/delphi-build-mcp-server/discussions
