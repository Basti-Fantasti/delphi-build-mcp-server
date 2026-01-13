#!/usr/bin/env python3
"""Delphi Build MCP Server - Main entry point."""

import asyncio
import sys
from pathlib import Path
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from src.compiler import DelphiCompiler
from src.config import ConfigLoader
from src.config_generator import ConfigGenerator
from src.multi_config_generator import MultiConfigGenerator


# Create MCP server instance
app = Server("delphi-build-server")


# Tool definitions
COMPILE_TOOL = Tool(
    name="compile_delphi_project",
    description=(
        "Compile a Delphi project (.dpr or .dproj file) and return parsed results. "
        "Automatically reads build configuration from .dproj file and library paths from config file. "
        "Returns only compilation errors, filtering out warnings and hints."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": "Absolute path to .dpr or .dproj file",
            },
            "force_build_all": {
                "type": "boolean",
                "description": "Force rebuild all units (adds -B flag)",
                "default": False,
            },
            "override_config": {
                "type": "string",
                "description": 'Override active build config (e.g., "Debug", "Release")',
                "default": None,
            },
            "override_platform": {
                "type": "string",
                "description": 'Override active platform (e.g., "Win32", "Win64")',
                "default": None,
            },
            "additional_search_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Extra unit search paths to add",
                "default": [],
            },
            "additional_flags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional compiler flags to append",
                "default": [],
            },
        },
        "required": ["project_path"],
    },
)

GENERATE_CONFIG_TOOL = Tool(
    name="generate_config_from_build_log",
    description=(
        "Generate delphi_config.toml file automatically by parsing an IDE build log. "
        "Extracts all library paths, compiler settings, and configuration from a successful "
        "compilation performed in the Delphi IDE. This eliminates manual configuration."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "build_log_path": {
                "type": "string",
                "description": "Absolute path to IDE build log file",
            },
            "output_config_path": {
                "type": "string",
                "description": "Output path for generated config file",
                "default": "delphi_config.toml",
            },
            "use_env_vars": {
                "type": "boolean",
                "description": "Replace user paths with ${USERNAME} environment variable",
                "default": True,
            },
        },
        "required": ["build_log_path"],
    },
)

GENERATE_MULTI_CONFIG_TOOL = Tool(
    name="generate_config_from_multiple_build_logs",
    description=(
        "Generate delphi_config.toml file from multiple IDE build logs for different configurations "
        "and platforms. Creates a hierarchical config with platform and config-specific settings. "
        "Use this when you have build logs from multiple configurations (Debug/Release) and/or "
        "platforms (Win32/Win64/Linux64)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "build_log_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Array of absolute paths to IDE build log files (e.g., Debug-Win32, Release-Win64, Debug-Linux64)",
            },
            "output_config_path": {
                "type": "string",
                "description": "Output path for generated config file",
                "default": "delphi_config.toml",
            },
            "use_env_vars": {
                "type": "boolean",
                "description": "Replace user paths with ${USERNAME} environment variable",
                "default": True,
            },
        },
        "required": ["build_log_paths"],
    },
)


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [COMPILE_TOOL, GENERATE_CONFIG_TOOL, GENERATE_MULTI_CONFIG_TOOL]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool invocations."""
    try:
        if name == "compile_delphi_project":
            result = await handle_compile_project(arguments)
            return [TextContent(type="text", text=result)]

        elif name == "generate_config_from_build_log":
            result = await handle_generate_config(arguments)
            return [TextContent(type="text", text=result)]

        elif name == "generate_config_from_multiple_build_logs":
            result = await handle_generate_multi_config(arguments)
            return [TextContent(type="text", text=result)]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        error_msg = f"Error executing {name}: {str(e)}"
        return [TextContent(type="text", text=error_msg)]


async def handle_compile_project(arguments: dict) -> str:
    """Handle compile_delphi_project tool invocation.

    Args:
        arguments: Tool arguments

    Returns:
        JSON string with compilation result
    """
    import json

    # Extract arguments
    project_path = Path(arguments["project_path"])
    force_build_all = arguments.get("force_build_all", False)
    override_config = arguments.get("override_config")
    override_platform = arguments.get("override_platform")
    additional_search_paths = arguments.get("additional_search_paths", [])
    additional_flags = arguments.get("additional_flags", [])

    # Initialize compiler
    compiler = DelphiCompiler()

    # Compile project
    result = compiler.compile_project(
        project_path=project_path,
        force_build_all=force_build_all,
        override_config=override_config,
        override_platform=override_platform,
        additional_search_paths=additional_search_paths,
        additional_flags=additional_flags,
    )

    # Convert to JSON
    return json.dumps(result.model_dump(), indent=2)


async def handle_generate_config(arguments: dict) -> str:
    """Handle generate_config_from_build_log tool invocation.

    Args:
        arguments: Tool arguments

    Returns:
        JSON string with generation result
    """
    import json

    # Extract arguments
    build_log_path = Path(arguments["build_log_path"])
    output_config_path = Path(arguments.get("output_config_path", "delphi_config.toml"))
    use_env_vars = arguments.get("use_env_vars", True)

    # Initialize generator
    generator = ConfigGenerator(use_env_vars=use_env_vars)

    # Generate config
    result = generator.generate_from_build_log(
        build_log_path=build_log_path, output_path=output_config_path
    )

    # Convert to JSON
    return json.dumps(result.model_dump(), indent=2)


async def handle_generate_multi_config(arguments: dict) -> str:
    """Handle generate_config_from_multiple_build_logs tool invocation.

    Args:
        arguments: Tool arguments

    Returns:
        JSON string with generation result
    """
    import json

    # Extract arguments
    build_log_paths = arguments["build_log_paths"]
    output_config_path = Path(arguments.get("output_config_path", "delphi_config.toml"))
    use_env_vars = arguments.get("use_env_vars", True)

    # Initialize generator
    generator = MultiConfigGenerator(use_env_vars=use_env_vars)

    # Generate config from multiple logs
    result = generator.generate_from_build_logs(
        build_log_paths=build_log_paths, output_path=output_config_path
    )

    # Convert to JSON
    return json.dumps(result.model_dump(), indent=2)


async def main():
    """Main entry point for the MCP server."""
    # Run the server using stdio transport
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
