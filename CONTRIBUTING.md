# Contributing to Delphi Build MCP Server

Thank you for your interest in contributing to the Delphi Build MCP Server! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Reporting Issues](#reporting-issues)
- [Feature Requests](#feature-requests)

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment. Be kind, constructive, and patient with others.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Set up the development environment (see below)
4. Create a branch for your changes
5. Make your changes and test them
6. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.10 or higher
- [UV](https://github.com/astral-sh/uv) package manager
- Delphi 11, 12, or 13 (for testing compilation features)

### Installation

```bash
# Clone your fork
git clone https://github.com/YOUR-USERNAME/delphi-build-mcp-server.git
cd delphi-build-mcp-server

# Install UV if needed
# Windows: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies including dev tools
uv sync
uv pip install -e ".[dev]"
```

## Project Structure

```
delphi-build-mcp-server/
├── main.py                       # MCP server entry point
├── src/
│   ├── models.py                 # Pydantic data models
│   ├── buildlog_parser.py        # Parse IDE build logs
│   ├── dproj_parser.py           # Parse .dproj files
│   ├── config.py                 # Load TOML configuration
│   ├── output_parser.py          # Parse compiler output
│   ├── config_generator.py       # Generate TOML configs
│   ├── compiler.py               # Compiler orchestration
│   └── registry_parser.py        # Windows registry utilities
├── tests/                        # Test suite
├── sample/                       # Sample projects for testing
│   ├── working/                  # Project that compiles successfully
│   └── broken/                   # Project with intentional errors
└── delphi_config.toml.template   # Configuration template
```

### Key Modules

- **main.py**: MCP server implementation exposing tools to AI agents
- **compiler.py**: Core compilation logic, command building, execution
- **output_parser.py**: Parses compiler output (English/German), filters warnings/hints
- **buildlog_parser.py**: Extracts library paths from IDE build logs
- **dproj_parser.py**: Parses .dproj XML files for build settings
- **config_generator.py**: Generates TOML config from build logs

## Coding Standards

This project uses automated tools to enforce code quality.

### Formatting with Black

```bash
# Format all source files
uv run black src/

# Check formatting without changes
uv run black --check src/
```

Configuration: Line length 100 characters (see `pyproject.toml`).

### Linting with Ruff

```bash
# Run linter
uv run ruff check src/

# Auto-fix issues where possible
uv run ruff check --fix src/
```

### Type Checking with mypy

```bash
uv run mypy src/
```

All new code should include type hints. The project uses Python 3.10+ typing features.

### Code Style Guidelines

- Use descriptive variable and function names
- Write docstrings for public functions and classes
- Keep functions focused and reasonably sized
- Handle errors gracefully with meaningful messages
- Support both English and German compiler output when parsing

## Testing

### Running Tests

```bash
# Run all tests with coverage
uv run pytest

# Run specific test file
uv run pytest tests/test_output_parser.py

# Run with verbose output
uv run pytest -v

# Run without coverage (faster)
uv run pytest --no-cov
```

### Test Sample Projects

Two sample Delphi projects are included for integration testing:

```bash
# Test compilation of sample projects
uv run python test_compile_samples.py
```

- `sample/working/Working.dproj` - Should compile successfully
- `sample/broken/Broken.dproj` - Has intentional errors for testing error parsing

### Writing Tests

- Place tests in the `tests/` directory
- Name test files `test_*.py`
- Name test functions `test_*`
- Use pytest fixtures for common setup
- Test both success and error cases
- Include tests for English and German compiler output

## Submitting Changes

### Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Follow coding standards
   - Add tests for new functionality
   - Update documentation if needed

3. **Run quality checks**
   ```bash
   uv run black src/
   uv run ruff check src/
   uv run mypy src/
   uv run pytest
   ```

4. **Commit your changes**
   - Write clear, descriptive commit messages
   - Reference issue numbers if applicable

5. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```
   Then create a pull request on GitHub.

### PR Guidelines

- Provide a clear description of changes
- Link related issues
- Include test results or screenshots if relevant
- Keep PRs focused on a single feature or fix
- Be responsive to review feedback

### What We Look For

- Code follows project style guidelines
- Tests pass and coverage is maintained
- New features have appropriate tests
- Documentation is updated if needed
- Changes don't break existing functionality
- MCP protocol compatibility is maintained

## Reporting Issues

When reporting bugs, please include:

1. **Description**: What happened vs. what you expected
2. **Steps to reproduce**: Minimal steps to trigger the issue
3. **Environment**:
   - Python version (`python --version`)
   - Delphi version
   - Operating system
   - MCP client (Claude Code, Cline, etc.)
4. **Error messages**: Full error output or logs
5. **Configuration**: Relevant parts of `delphi_config.toml` (sanitize paths)

### Good Bug Report Example

```
Title: Compilation fails with German locale

Description:
When using Delphi with German localization, fatal errors are not
parsed correctly. The server reports success but there were errors.

Steps to reproduce:
1. Configure Delphi IDE to German
2. Compile a project with a fatal error
3. Observe that success=true despite errors

Environment:
- Python 3.11.5
- Delphi 12.2 (German)
- Windows 11
- Claude Code

Error output:
[Schwerwiegend] Unit1.pas(10): F2084 Interner Fehler: ...
```

## Feature Requests

We welcome feature requests! When proposing new features:

1. **Check existing issues** to avoid duplicates
2. **Describe the use case**: What problem does it solve?
3. **Propose a solution**: How might it work?
4. **Consider alternatives**: Are there other approaches?

### Good Feature Request Example

```
Title: Support for Delphi project groups (.groupproj)

Use case:
Large projects often use project groups. Currently, each project
must be compiled individually.

Proposed solution:
Add a compile_project_group tool that:
1. Parses .groupproj file
2. Compiles projects in dependency order
3. Returns aggregated results

Alternatives considered:
- Script to call compile_delphi_project multiple times
  (works but loses dependency ordering)
```

## Areas for Contribution

Here are some areas where contributions are especially welcome:

- **Compiler output parsing**: Support for additional languages/locales
- **Error recovery**: Better handling of edge cases
- **Documentation**: Improving guides and examples
- **Testing**: Expanding test coverage
- **Performance**: Optimizing compilation workflows
- **New Delphi versions**: Supporting future Delphi releases

## Questions?

If you have questions about contributing:

- Open a [Discussion](https://github.com/Basti-Fantasti/delphi-build-mcp-server/discussions)
- Check existing issues and PRs
- Review the [DOCUMENTATION.md](DOCUMENTATION.md) for technical details

Thank you for contributing!
