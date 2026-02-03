#!/usr/bin/env python3
"""Delphi Build MCP Server - Main entry point."""

import argparse
import asyncio
import contextlib
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.responses import Response

from src.compiler import DelphiCompiler
from src.config import ConfigLoader
from src.config_generator import ConfigGenerator
from src.config_extender import ConfigExtender
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
        "compilation performed in the Delphi IDE. This eliminates manual configuration. "
        "Supports platform-specific config files (e.g., delphi_config_win64.toml) for "
        "simpler multi-platform setups."
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
                "description": "Output path for generated config file. If not specified, generates platform-specific filename (e.g., delphi_config_win32.toml) by default.",
                "default": None,
            },
            "use_platform_specific_name": {
                "type": "boolean",
                "description": "Generate platform-specific filename (e.g., delphi_config_win64.toml) based on detected platform. Set to false for generic delphi_config.toml. Ignored if output_config_path is specified.",
                "default": True,
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
        "and platforms. By default, creates separate platform-specific config files "
        "(e.g., delphi_config_win32.toml, delphi_config_win64.toml). "
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
                "description": "Output path for unified config file. Only used when generate_separate_files=False.",
                "default": "delphi_config.toml",
            },
            "generate_separate_files": {
                "type": "boolean",
                "description": "Generate separate platform-specific config files (default). Set to false for a single unified config.",
                "default": True,
            },
            "output_dir": {
                "type": "string",
                "description": "Output directory for generated platform-specific files. Defaults to current directory.",
                "default": ".",
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

EXTEND_CONFIG_TOOL = Tool(
    name="extend_config_from_build_log",
    description=(
        "Extend an existing delphi_config.toml with settings from a new IDE build log. "
        "Useful for adding support for new platforms (e.g., Win64x) or libraries without "
        "regenerating the entire configuration. Intelligently merges new paths while "
        "preserving existing settings and avoiding duplicates."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "existing_config_path": {
                "type": "string",
                "description": "Absolute path to existing delphi_config.toml file",
            },
            "build_log_path": {
                "type": "string",
                "description": "Absolute path to IDE build log file",
            },
            "output_config_path": {
                "type": "string",
                "description": "Output path for extended config file (default: overwrites existing)",
                "default": None,
            },
            "use_env_vars": {
                "type": "boolean",
                "description": "Replace user paths with ${USERNAME} environment variable",
                "default": True,
            },
        },
        "required": ["existing_config_path", "build_log_path"],
    },
)


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [COMPILE_TOOL, GENERATE_CONFIG_TOOL, GENERATE_MULTI_CONFIG_TOOL, EXTEND_CONFIG_TOOL]


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

        elif name == "extend_config_from_build_log":
            result = await handle_extend_config(arguments)
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
    output_config_path_str = arguments.get("output_config_path")
    output_config_path = Path(output_config_path_str) if output_config_path_str else None
    use_platform_specific_name = arguments.get("use_platform_specific_name", True)
    use_env_vars = arguments.get("use_env_vars", True)

    # Initialize generator
    generator = ConfigGenerator(use_env_vars=use_env_vars)

    # Generate config
    result = generator.generate_from_build_log(
        build_log_path=build_log_path,
        output_path=output_config_path,
        use_platform_specific_name=use_platform_specific_name,
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
    output_config_path_str = arguments.get("output_config_path")
    output_config_path = Path(output_config_path_str) if output_config_path_str else None
    generate_separate_files = arguments.get("generate_separate_files", True)
    output_dir_str = arguments.get("output_dir", ".")
    output_dir = Path(output_dir_str)
    use_env_vars = arguments.get("use_env_vars", True)

    # Initialize generator
    generator = MultiConfigGenerator(use_env_vars=use_env_vars)

    # Generate config from multiple logs
    result = generator.generate_from_build_logs(
        build_log_paths=build_log_paths,
        output_path=output_config_path,
        generate_separate_files=generate_separate_files,
        output_dir=output_dir,
    )

    # Convert to JSON
    return json.dumps(result.model_dump(), indent=2)


async def handle_extend_config(arguments: dict) -> str:
    """Handle extend_config_from_build_log tool invocation.

    Args:
        arguments: Tool arguments

    Returns:
        JSON string with extension result
    """
    import json

    # Extract arguments
    existing_config_path = Path(arguments["existing_config_path"])
    build_log_path = Path(arguments["build_log_path"])
    output_config_path = arguments.get("output_config_path")
    if output_config_path:
        output_config_path = Path(output_config_path)
    use_env_vars = arguments.get("use_env_vars", True)

    # Initialize extender
    extender = ConfigExtender(use_env_vars=use_env_vars)

    # Extend config
    result = extender.extend_from_build_log(
        existing_config_path=existing_config_path,
        build_log_path=build_log_path,
        output_path=output_config_path,
    )

    # Convert to JSON
    return json.dumps(result.model_dump(), indent=2)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Delphi Build MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport type (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0, only used with streamable-http)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080, only used with streamable-http)",
    )
    return parser.parse_args()


async def run_streamable_http(host: str, port: int) -> None:
    """Run the MCP server with Streamable HTTP transport."""
    import uvicorn

    session_manager = StreamableHTTPSessionManager(app=app)

    @contextlib.asynccontextmanager
    async def lifespan(starlette_app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    # Starlette handles lifespan only; /mcp routing is done at the ASGI level
    # to avoid Starlette's endpoint wrapper which expects a Response return value.
    # StreamableHTTPSessionManager.handle_request is a raw ASGI app that writes
    # directly to the send callable.
    starlette_app = Starlette(lifespan=lifespan)

    async def asgi_app(scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/mcp":
            await session_manager.handle_request(scope, receive, send)
        else:
            await starlette_app(scope, receive, send)

    config = uvicorn.Config(
        asgi_app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    """Main entry point for the MCP server."""
    args = parse_args()

    if args.transport == "streamable-http":
        await run_streamable_http(args.host, args.port)
    else:
        # Run the server using stdio transport (default, unchanged behavior)
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
