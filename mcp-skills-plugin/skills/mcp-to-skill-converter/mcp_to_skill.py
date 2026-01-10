#!/usr/bin/env python3
"""
MCP to Skill Converter
======================
Converts any MCP server into a Claude Skill with dynamic tool invocation.

This implements the "progressive disclosure" pattern:
- At startup: Only skill metadata is loaded (~100 tokens)
- On use: Full tool list and instructions are loaded (~5k tokens)
- On execution: Tools are called dynamically (0 context tokens)

Usage:
    # List servers in .mcp.json
    python mcp_to_skill.py --list

    # Convert single server
    python mcp_to_skill.py --name github --output-dir ./skills

    # Convert all compatible servers
    python mcp_to_skill.py --all --output-dir ./skills

    # Legacy mode (backward compatible)
    python mcp_to_skill.py --mcp-config mcp-server-config.json --output-dir ./skills/my-mcp-skill
"""

import json
import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
import argparse


# Compatible MCP server types
COMPATIBLE_TYPES = {"stdio", "http", "sse"}


def sanitize_name(name: str) -> str:
    """
    Sanitize a server name for use as a directory name.

    Removes or replaces special characters that cause path issues:
    - @ symbol (npm scoped packages)
    - / symbol (npm scoped packages)
    - Other special characters

    Args:
        name: Original server name (e.g., "@magicuidesign/mcp")

    Returns:
        Sanitized name (e.g., "magicui")
    """
    import re

    # Common npm scoped package patterns
    # @org/package -> package (or a simplified version)
    if name.startswith("@") and "/" in name:
        # Extract just the package name, removing scope
        parts = name.split("/")
        name = parts[-1]  # Get the last part (package name)

        # If package name is generic like "mcp", use the org name instead
        if name.lower() in ("mcp", "server", "client", "sdk"):
            org = parts[0].lstrip("@")
            # Try to create a meaningful short name
            name = org.replace("-", "").replace("design", "")

    # Remove remaining special characters
    name = re.sub(r'[@/\\:*?"<>|]', '', name)

    # Replace spaces and dots with hyphens
    name = re.sub(r'[\s.]+', '-', name)

    # Remove consecutive hyphens
    name = re.sub(r'-+', '-', name)

    # Remove leading/trailing hyphens
    name = name.strip('-')

    return name.lower() if name else "unnamed-skill"


class MCPSkillGenerator:
    """Generate a Skill from an MCP server configuration."""

    def __init__(self, mcp_config: Dict[str, Any], output_dir: Path):
        self.mcp_config = mcp_config
        self.output_dir = Path(output_dir)
        self.server_name = mcp_config.get('name', 'unnamed-mcp-server')
        self.tools_cache = None  # Cache tools for access after generation

    async def generate(self):
        """Generate the complete skill structure."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        print(f"Generating skill for MCP server: {self.server_name}")

        # 1. Introspect MCP server to get tool list
        tools = await self._get_mcp_tools()
        self.tools_cache = tools  # Cache for later access
        
        # 2. Generate SKILL.md
        self._generate_skill_md(tools)
        
        # 3. Generate executor script
        self._generate_executor()
        
        # 4. Generate config file
        self._generate_config()
        
        # 5. Generate package.json (if needed)
        self._generate_package_json()
        
        print(f"✓ Skill generated at: {self.output_dir}")
        print(f"✓ Tools available: {len(tools)}")
        
    async def _get_mcp_tools(self) -> List[Dict[str, Any]]:
        """Connect to MCP server and get available tools via introspection."""
        server_type = self.mcp_config.get('type', 'stdio')

        if server_type == 'http':
            return await self._get_mcp_tools_http()
        elif server_type == 'sse':
            return await self._get_mcp_tools_sse()
        else:
            return await self._get_mcp_tools_stdio()

    async def _get_mcp_tools_stdio(self) -> List[Dict[str, Any]]:
        """Connect to stdio MCP server and get available tools."""
        command = self.mcp_config.get('command', '')
        args = self.mcp_config.get('args', [])
        env = self.mcp_config.get('env')

        print(f"Introspecting MCP server (stdio): {command} {' '.join(args)}")

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            print("Warning: mcp package not installed. Using mock tools.", file=sys.stderr)
            print("Install with: pip install mcp", file=sys.stderr)
            return self._get_mock_tools()

        try:
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env
            )

            # Use proper async context manager pattern
            async with stdio_client(server_params) as streams:
                read_stream, write_stream = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    response = await session.list_tools()

                    tools = []
                    for tool in response.tools:
                        tools.append({
                            "name": tool.name,
                            "description": tool.description or "No description",
                            "inputSchema": tool.inputSchema
                        })

                    print(f"✓ Found {len(tools)} tools")
                    return tools

        except Exception as e:
            print(f"Warning: Failed to introspect MCP server: {e}", file=sys.stderr)
            print("Using mock tools for demonstration.", file=sys.stderr)
            return self._get_mock_tools()

    async def _get_mcp_tools_http(self) -> List[Dict[str, Any]]:
        """Connect to HTTP MCP server and get available tools."""
        url = self.mcp_config.get('url', '')

        print(f"Introspecting MCP server (HTTP): {url}")

        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError:
            print("Warning: mcp package not installed. Using mock tools.", file=sys.stderr)
            print("Install with: pip install mcp", file=sys.stderr)
            return self._get_mock_tools()

        try:
            # Use HTTP client for streamable HTTP transport
            async with streamablehttp_client(url) as streams:
                read_stream, write_stream, _ = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    response = await session.list_tools()

                    tools = []
                    for tool in response.tools:
                        tools.append({
                            "name": tool.name,
                            "description": tool.description or "No description",
                            "inputSchema": tool.inputSchema
                        })

                    print(f"✓ Found {len(tools)} tools")
                    return tools

        except Exception as e:
            print(f"Warning: Failed to introspect HTTP MCP server: {e}", file=sys.stderr)
            print("Using mock tools for demonstration.", file=sys.stderr)
            return self._get_mock_tools()

    async def _get_mcp_tools_sse(self) -> List[Dict[str, Any]]:
        """Connect to SSE MCP server and get available tools."""
        url = self.mcp_config.get('url', '')

        print(f"Introspecting MCP server (SSE): {url}")

        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client
        except ImportError:
            print("Warning: mcp package not installed. Using mock tools.", file=sys.stderr)
            print("Install with: pip install mcp", file=sys.stderr)
            return self._get_mock_tools()

        try:
            # Use SSE client for Server-Sent Events transport
            async with sse_client(url) as streams:
                read_stream, write_stream = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    response = await session.list_tools()

                    tools = []
                    for tool in response.tools:
                        tools.append({
                            "name": tool.name,
                            "description": tool.description or "No description",
                            "inputSchema": tool.inputSchema
                        })

                    print(f"✓ Found {len(tools)} tools")
                    return tools

        except Exception as e:
            print(f"Warning: Failed to introspect SSE MCP server: {e}", file=sys.stderr)
            print("Using mock tools for demonstration.", file=sys.stderr)
            return self._get_mock_tools()

    def _get_mock_tools(self) -> List[Dict[str, Any]]:
        """Return mock tools when introspection fails."""
        return [
            {
                "name": "example_tool",
                "description": "An example tool from the MCP server (mock - introspection failed)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "First parameter"}
                    },
                    "required": ["param1"]
                }
            }
        ]
    
    def _generate_skill_md(self, tools: List[Dict[str, Any]]):
        """Generate the SKILL.md file with instructions for Claude."""

        # Create tool list for Claude
        tool_list = "\n".join([
            f"- `{t['name']}`: {t.get('description', 'No description')}"
            for t in tools
        ])

        # Count tools
        tool_count = len(tools)

        # Note: Keywords should be added by the agent after conversion
        # based on semantic understanding of what the MCP server does.
        # See SKILL.md instructions for the agent workflow.

        content = f"""---
name: {self.server_name}
description: Dynamic access to {self.server_name} MCP server ({tool_count} tools)
version: 1.0.0
---

# {self.server_name} Skill

Access {self.server_name} MCP server capabilities.

## Context Efficiency

Traditional MCP approach:
- All {tool_count} tools loaded at startup
- Estimated context: {tool_count * 500} tokens

This skill approach:
- Metadata only: ~100 tokens
- Full instructions (when used): ~5k tokens
- Tool execution: 0 tokens (runs externally)

## How This Works

Instead of loading all MCP tool definitions upfront, this skill:
1. Tells you what tools are available (just names and brief descriptions)
2. You decide which tool to call based on the user's request
3. Generate a JSON command to invoke the tool
4. The executor handles the actual MCP communication

## Available Tools

{tool_list}

## Usage Pattern

When the user's request matches this skill's capabilities:

**Step 1: Identify the right tool** from the list above

**Step 2: Generate a tool call** in this JSON format:

```json
{{
  "tool": "tool_name",
  "arguments": {{
    "param1": "value1",
    "param2": "value2"
  }}
}}
```

**Step 3: Execute via bash** (from project root):

```bash
python .claude/skills/mcp-skills/executor.py --skill {self.server_name} --call 'YOUR_JSON_HERE'
```

## Getting Tool Details

If you need detailed information about a specific tool's parameters:

```bash
python .claude/skills/mcp-skills/executor.py --skill {self.server_name} --describe tool_name
```

This loads ONLY that tool's schema, not all tools.

## Examples

### Example 1: Simple tool call

User: "Use {self.server_name} to do X"

Your workflow:
1. Identify tool: `example_tool`
2. Generate call JSON
3. Execute:

```bash
python .claude/skills/mcp-skills/executor.py --skill {self.server_name} --call '{{"tool": "example_tool", "arguments": {{"param1": "value"}}}}'
```

### Example 2: Get tool details first

```bash
python .claude/skills/mcp-skills/executor.py --skill {self.server_name} --describe example_tool
```

Returns the full schema, then you can generate the appropriate call.

## Error Handling

If the executor returns an error:
- Check the tool name is correct
- Verify required arguments are provided
- Ensure the MCP server is accessible

## Performance Notes

Context usage comparison for this skill:

| Scenario | MCP (preload) | Skill (dynamic) |
|----------|---------------|-----------------|
| Idle | {tool_count * 500} tokens | 100 tokens |
| Active | {tool_count * 500} tokens | 5k tokens |
| Executing | {tool_count * 500} tokens | 0 tokens |

Savings: ~{int((1 - 5000/(tool_count * 500)) * 100)}% reduction in typical usage

---

*This skill was auto-generated from an MCP server configuration.*
*Generator: mcp_to_skill.py*
"""
        
        skill_path = self.output_dir / "SKILL.md"
        skill_path.write_text(content)
        print(f"✓ Generated: {skill_path}")
    
    def _generate_executor(self):
        """Generate the executor script that communicates with MCP server."""

        executor_code = '''#!/usr/bin/env python3
"""
MCP Skill Executor
==================
Handles dynamic communication with the MCP server.
Supports stdio, HTTP, and SSE transport types.
Uses proper async context manager pattern for MCP client connections.
"""

import json
import sys
import asyncio
import argparse
from pathlib import Path

# Check if mcp package is available
HAS_MCP = False
HAS_HTTP = False
HAS_SSE = False

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP = True
except ImportError:
    print("Warning: mcp package not installed. Install with: pip install mcp", file=sys.stderr)

try:
    from mcp.client.streamable_http import streamablehttp_client
    HAS_HTTP = True
except ImportError:
    pass  # HTTP support optional

try:
    from mcp.client.sse import sse_client
    HAS_SSE = True
except ImportError:
    pass  # SSE support optional


class MCPExecutorStdio:
    """Execute MCP tool calls via stdio transport."""

    def __init__(self, server_config):
        if not HAS_MCP:
            raise ImportError("mcp package is required. Install with: pip install mcp")

        self.server_config = server_config
        self._server_params = StdioServerParameters(
            command=server_config["command"],
            args=server_config.get("args", []),
            env=server_config.get("env")
        )

    async def _run_with_session(self, operation):
        async with stdio_client(self._server_params) as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await operation(session)

    async def list_tools(self):
        async def _list(session):
            response = await session.list_tools()
            return [{"name": tool.name, "description": tool.description} for tool in response.tools]
        return await self._run_with_session(_list)

    async def describe_tool(self, tool_name: str):
        async def _describe(session):
            response = await session.list_tools()
            for tool in response.tools:
                if tool.name == tool_name:
                    return {"name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema}
            return None
        return await self._run_with_session(_describe)

    async def call_tool(self, tool_name: str, arguments: dict):
        async def _call(session):
            response = await session.call_tool(tool_name, arguments)
            return response.content
        return await self._run_with_session(_call)

    async def close(self):
        pass


class MCPExecutorHTTP:
    """Execute MCP tool calls via HTTP transport."""

    def __init__(self, server_config):
        if not HAS_HTTP:
            raise ImportError("HTTP transport requires mcp package with streamable_http support")

        self.server_config = server_config
        self._url = server_config["url"]

    async def _run_with_session(self, operation):
        async with streamablehttp_client(self._url) as streams:
            read_stream, write_stream, _ = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await operation(session)

    async def list_tools(self):
        async def _list(session):
            response = await session.list_tools()
            return [{"name": tool.name, "description": tool.description} for tool in response.tools]
        return await self._run_with_session(_list)

    async def describe_tool(self, tool_name: str):
        async def _describe(session):
            response = await session.list_tools()
            for tool in response.tools:
                if tool.name == tool_name:
                    return {"name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema}
            return None
        return await self._run_with_session(_describe)

    async def call_tool(self, tool_name: str, arguments: dict):
        async def _call(session):
            response = await session.call_tool(tool_name, arguments)
            return response.content
        return await self._run_with_session(_call)

    async def close(self):
        pass


class MCPExecutorSSE:
    """Execute MCP tool calls via SSE (Server-Sent Events) transport."""

    def __init__(self, server_config):
        if not HAS_SSE:
            raise ImportError("SSE transport requires mcp package with sse support")

        self.server_config = server_config
        self._url = server_config["url"]

    async def _run_with_session(self, operation):
        async with sse_client(self._url) as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await operation(session)

    async def list_tools(self):
        async def _list(session):
            response = await session.list_tools()
            return [{"name": tool.name, "description": tool.description} for tool in response.tools]
        return await self._run_with_session(_list)

    async def describe_tool(self, tool_name: str):
        async def _describe(session):
            response = await session.list_tools()
            for tool in response.tools:
                if tool.name == tool_name:
                    return {"name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema}
            return None
        return await self._run_with_session(_describe)

    async def call_tool(self, tool_name: str, arguments: dict):
        async def _call(session):
            response = await session.call_tool(tool_name, arguments)
            return response.content
        return await self._run_with_session(_call)

    async def close(self):
        pass


def create_executor(config):
    """Factory to create appropriate executor based on config type."""
    server_type = config.get("type", "stdio")
    if server_type == "http":
        return MCPExecutorHTTP(config)
    elif server_type == "sse":
        return MCPExecutorSSE(config)
    else:
        return MCPExecutorStdio(config)


async def main():
    parser = argparse.ArgumentParser(description="MCP Skill Executor")
    parser.add_argument("--call", help="JSON tool call to execute")
    parser.add_argument("--describe", help="Get tool schema")
    parser.add_argument("--list", action="store_true", help="List all tools")

    args = parser.parse_args()

    # Load server config
    config_path = Path(__file__).parent / "mcp-config.json"
    if not config_path.exists():
        print(f"Error: Configuration file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    if not HAS_MCP:
        print("Error: mcp package not installed", file=sys.stderr)
        print("Install with: pip install mcp", file=sys.stderr)
        sys.exit(1)

    executor = create_executor(config)

    try:
        if args.list:
            tools = await executor.list_tools()
            print(json.dumps(tools, indent=2))

        elif args.describe:
            schema = await executor.describe_tool(args.describe)
            if schema:
                print(json.dumps(schema, indent=2))
            else:
                print(f"Tool not found: {args.describe}", file=sys.stderr)
                sys.exit(1)

        elif args.call:
            call_data = json.loads(args.call)
            result = await executor.call_tool(
                call_data["tool"],
                call_data.get("arguments", {})
            )

            # Format result
            if isinstance(result, list):
                for item in result:
                    if hasattr(item, 'text'):
                        print(item.text)
                    else:
                        print(json.dumps(item.__dict__ if hasattr(item, '__dict__') else item, indent=2))
            else:
                print(json.dumps(result.__dict__ if hasattr(result, '__dict__') else result, indent=2))
        else:
            parser.print_help()

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    finally:
        await executor.close()


if __name__ == "__main__":
    asyncio.run(main())
'''
        
        executor_path = self.output_dir / "executor.py"
        executor_path.write_text(executor_code)
        executor_path.chmod(0o755)
        print(f"✓ Generated: {executor_path}")
    
    def _generate_config(self):
        """Save MCP server config for the executor."""
        config_path = self.output_dir / "mcp-config.json"
        with open(config_path, 'w') as f:
            json.dump(self.mcp_config, f, indent=2)
        print(f"✓ Generated: {config_path}")
    
    def _generate_package_json(self):
        """Generate package.json for dependencies."""
        package = {
            "name": f"skill-{self.server_name}",
            "version": "1.0.0",
            "description": f"Claude Skill wrapper for {self.server_name} MCP server",
            "scripts": {
                "setup": "pip install mcp"
            }
        }
        
        package_path = self.output_dir / "package.json"
        with open(package_path, 'w') as f:
            json.dump(package, f, indent=2)
        print(f"✓ Generated: {package_path}")


def find_mcp_json(start_path: Optional[Path] = None, explicit_path: Optional[str] = None) -> Path:
    """
    Find .mcp.json file using the following priority:
    1. Use explicit_path if provided
    2. Search current directory
    3. Search parent directories recursively (like git does)

    Args:
        start_path: Starting directory for search (defaults to current directory)
        explicit_path: Explicit path to .mcp.json if provided

    Returns:
        Path to .mcp.json file

    Raises:
        FileNotFoundError: If .mcp.json cannot be found
    """
    if explicit_path:
        path = Path(explicit_path)
        if path.exists():
            return path
        raise FileNotFoundError(f"Specified .mcp.json not found: {explicit_path}")

    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()
    while True:
        mcp_json = current / ".mcp.json"
        if mcp_json.exists():
            return mcp_json

        parent = current.parent
        if parent == current:  # Reached root
            break
        current = parent

    raise FileNotFoundError(
        "Could not find .mcp.json in current or parent directories. "
        "Use --mcp-json to specify the path explicitly."
    )


def load_mcp_json(path: Path) -> Dict[str, Any]:
    """
    Load and validate .mcp.json file.

    Args:
        path: Path to .mcp.json file

    Returns:
        Parsed JSON data

    Raises:
        ValueError: If .mcp.json is invalid (missing mcpServers key)
    """
    with open(path) as f:
        data = json.load(f)

    if "mcpServers" not in data:
        raise ValueError(f"Invalid .mcp.json: missing 'mcpServers' key in {path}")

    return data


def get_compatible_servers(mcp_json: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Filter servers to only compatible types (stdio and http).

    Args:
        mcp_json: Parsed .mcp.json data

    Returns:
        Dictionary of compatible servers
    """
    servers = mcp_json.get("mcpServers", {})
    compatible = {}

    for name, config in servers.items():
        server_type = config.get("type", "stdio")  # Default to stdio
        if server_type in COMPATIBLE_TYPES:
            compatible[name] = config
        else:
            print(f"⚠️  Skipping '{name}': type '{server_type}' not supported (only {COMPATIBLE_TYPES})")

    return compatible


def extract_server_config(mcp_json: Dict[str, Any], server_name: str) -> Dict[str, Any]:
    """
    Transform .mcp.json entry to converter-compatible format.

    Args:
        mcp_json: Parsed .mcp.json data
        server_name: Name of server to extract

    Returns:
        Server configuration in converter format

    Raises:
        ValueError: If server not found or incompatible
    """
    servers = mcp_json.get("mcpServers", {})

    if server_name not in servers:
        available = list(servers.keys())
        raise ValueError(
            f"Server '{server_name}' not found in .mcp.json. "
            f"Available servers: {', '.join(available)}"
        )

    config = servers[server_name]
    server_type = config.get("type", "stdio")

    if server_type not in COMPATIBLE_TYPES:
        raise ValueError(
            f"Server '{server_name}' has type '{server_type}' which is not supported. "
            f"Only {COMPATIBLE_TYPES} types are compatible."
        )

    # Handle different transport types
    if server_type == "http":
        if "url" not in config:
            raise ValueError(f"HTTP server '{server_name}' missing required 'url' field")
        return {
            "name": server_name,
            "type": "http",
            "url": config["url"]
        }
    elif server_type == "sse":
        if "url" not in config:
            raise ValueError(f"SSE server '{server_name}' missing required 'url' field")
        return {
            "name": server_name,
            "type": "sse",
            "url": config["url"]
        }
    else:
        # stdio type
        if "command" not in config:
            raise ValueError(f"Server '{server_name}' missing required 'command' field")
        return {
            "name": server_name,
            "type": "stdio",
            "command": config["command"],
            "args": config.get("args", []),
            "env": config.get("env")
        }


def remove_server_from_mcp_json(mcp_json_path: Path, server_name: str):
    """
    Remove a server from .mcp.json after successful conversion.

    Args:
        mcp_json_path: Path to .mcp.json file
        server_name: Name of server to remove
    """
    with open(mcp_json_path) as f:
        data = json.load(f)

    if "mcpServers" in data and server_name in data["mcpServers"]:
        del data["mcpServers"][server_name]
        with open(mcp_json_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✓ Removed '{server_name}' from {mcp_json_path}")
    else:
        print(f"⚠️  Server '{server_name}' not found in {mcp_json_path}")


def initialize_mcp_skills_registry(output_base: Path):
    """
    Initialize the mcp-skills registry directory with templates if it doesn't exist.

    Args:
        output_base: Base output directory (mcp-skills/)
    """
    output_base = Path(output_base)
    output_base.mkdir(parents=True, exist_ok=True)

    # Get templates directory (relative to this script)
    script_dir = Path(__file__).parent
    templates_dir = script_dir / "templates"

    # Copy registry SKILL.md if not exists
    registry_skill_path = output_base / "SKILL.md"
    if not registry_skill_path.exists():
        template_skill = templates_dir / "registry-SKILL.md"
        if template_skill.exists():
            import shutil
            shutil.copy(template_skill, registry_skill_path)
            print(f"✓ Created registry SKILL.md at {output_base}")
        else:
            print(f"⚠️  Template not found: {template_skill}")

    # Copy index.json if not exists
    index_path = output_base / "index.json"
    if not index_path.exists():
        template_index = templates_dir / "index.json"
        if template_index.exists():
            import shutil
            shutil.copy(template_index, index_path)
            print(f"✓ Created index.json at {output_base}")
        else:
            # Create default index.json
            index = {
                "name": "mcp-skills",
                "version": "1.0.0",
                "description": "Registry of MCP-derived skills with progressive disclosure",
                "skills": []
            }
            with open(index_path, 'w') as f:
                json.dump(index, f, indent=2)
            print(f"✓ Created index.json at {output_base}")


def update_mcp_skills_index(output_base: Path, server_name: str, tools_count: int, description: str):
    """
    Update the mcp-skills/index.json with the new skill.

    Args:
        output_base: Base output directory (mcp-skills/)
        server_name: Name of the skill
        tools_count: Number of tools in the skill
        description: Brief description of the skill
    """
    # Ensure registry is initialized
    initialize_mcp_skills_registry(output_base)

    index_path = Path(output_base) / "index.json"

    with open(index_path) as f:
        index = json.load(f)

    # Note: Keywords should be added by the agent after conversion
    # based on semantic understanding of what the MCP server does.
    # See SKILL.md instructions for the agent workflow.

    # Check if skill already exists
    existing = next((s for s in index["skills"] if s["name"] == server_name), None)
    if existing:
        existing["tools"] = tools_count
        existing["description"] = description
    else:
        index["skills"].append({
            "name": server_name,
            "description": description,
            "tools": tools_count,
            "category": "integration"
        })

    with open(index_path, 'w') as f:
        json.dump(index, f, indent=2)
    print(f"✓ Updated index.json with '{server_name}'")


async def convert_single_server(mcp_json: Dict[str, Any], server_name: str, output_base: str, mcp_json_path: Optional[Path] = None):
    """
    Convert a single server from .mcp.json.

    Args:
        mcp_json: Parsed .mcp.json data
        server_name: Name of server to convert
        output_base: Base output directory
        mcp_json_path: Path to .mcp.json (for removal after conversion)
    """
    config = extract_server_config(mcp_json, server_name)

    # Sanitize the name for filesystem compatibility
    sanitized_name = sanitize_name(server_name)
    if sanitized_name != server_name:
        print(f"📝 Sanitizing name: '{server_name}' → '{sanitized_name}'")

    # Update config with sanitized name for skill generation
    config["name"] = sanitized_name

    output_dir = Path(output_base) / sanitized_name

    generator = MCPSkillGenerator(config, output_dir)
    await generator.generate()

    # Update the mcp-skills index with sanitized name
    update_mcp_skills_index(Path(output_base), sanitized_name, len(generator.tools_cache or []), f"{sanitized_name} MCP server integration")

    # Remove original name from .mcp.json after successful conversion
    if mcp_json_path:
        remove_server_from_mcp_json(Path(mcp_json_path), server_name)


async def convert_all_servers(mcp_json: Dict[str, Any], output_base: str, mcp_json_path: Optional[Path] = None):
    """
    Convert all compatible servers from .mcp.json.

    Args:
        mcp_json: Parsed .mcp.json data
        output_base: Base output directory
        mcp_json_path: Path to .mcp.json (for removal after conversion)
    """
    compatible = get_compatible_servers(mcp_json)

    if not compatible:
        print("❌ No compatible servers found in .mcp.json")
        return

    print(f"🔄 Converting {len(compatible)} server(s)...")

    success_count = 0
    converted_servers = []  # Stores (original_name, sanitized_name, tools_count)
    for server_name in compatible:
        try:
            print(f"\n{'='*60}")
            print(f"Converting: {server_name}")
            print('='*60)

            config = extract_server_config(mcp_json, server_name)

            # Sanitize the name for filesystem compatibility
            sanitized_name = sanitize_name(server_name)
            if sanitized_name != server_name:
                print(f"📝 Sanitizing name: '{server_name}' → '{sanitized_name}'")

            # Update config with sanitized name for skill generation
            config["name"] = sanitized_name

            output_dir = Path(output_base) / sanitized_name

            generator = MCPSkillGenerator(config, output_dir)
            await generator.generate()
            success_count += 1
            converted_servers.append((server_name, sanitized_name, len(generator.tools_cache or [])))

            # Update the mcp-skills index with sanitized name
            update_mcp_skills_index(Path(output_base), sanitized_name, len(generator.tools_cache or []), f"{sanitized_name} MCP server integration")

        except Exception as e:
            print(f"❌ Failed to convert '{server_name}': {e}")

    # Remove all successfully converted servers from .mcp.json (use original names)
    if mcp_json_path and converted_servers:
        print(f"\n{'='*60}")
        print("Cleaning up .mcp.json...")
        for original_name, _, _ in converted_servers:
            remove_server_from_mcp_json(Path(mcp_json_path), original_name)

    print(f"\n{'='*60}")
    print(f"✅ Successfully converted {success_count}/{len(compatible)} servers")
    print('='*60)


async def list_servers(explicit_path: Optional[str] = None):
    """
    List all servers in .mcp.json with compatibility info.

    Args:
        explicit_path: Optional explicit path to .mcp.json
    """
    mcp_json_path = find_mcp_json(explicit_path=explicit_path)
    mcp_json = load_mcp_json(mcp_json_path)

    print(f"📄 Servers in: {mcp_json_path}\n")

    servers = mcp_json.get("mcpServers", {})
    compatible = get_compatible_servers(mcp_json)

    print(f"{'Name':<25} {'Type':<10} {'Compatible':<12} {'Command'}")
    print("-" * 80)

    for name, config in servers.items():
        server_type = config.get("type", "stdio")
        is_compatible = "✅ Yes" if name in compatible else "❌ No"
        command = config.get("command", config.get("url", "N/A"))
        print(f"{name:<25} {server_type:<10} {is_compatible:<12} {command}")

    print(f"\n📊 Total: {len(servers)} servers, {len(compatible)} compatible")


def validate_arguments(args):
    """
    Validate mutually exclusive arguments.

    Args:
        args: Parsed command-line arguments

    Raises:
        SystemExit: If arguments are invalid
    """
    if args.mcp_config and (args.name or args.all):
        raise SystemExit("Error: --mcp-config cannot be used with --name or --all")

    if args.name and args.all:
        raise SystemExit("Error: --name and --all are mutually exclusive")

    if args.list:
        return  # --list doesn't require output-dir

    if not args.mcp_config and not args.name and not args.all:
        raise SystemExit("Error: Must specify --mcp-config, --name, or --all")

    # output-dir is now optional - we default to mcp-skills/ next to .mcp.json
    if args.mcp_config and not args.output_dir:
        raise SystemExit("Error: --output-dir is required for legacy --mcp-config mode")


async def convert_mcp_to_skill(mcp_config_path: str, output_dir: str):
    """Convert an MCP server configuration to a Skill (legacy mode)."""

    # Load MCP config
    with open(mcp_config_path) as f:
        mcp_config = json.load(f)

    # Generate skill
    generator = MCPSkillGenerator(mcp_config, Path(output_dir))
    await generator.generate()
    
    print("\n" + "="*60)
    print("✓ Skill generation complete!")
    print("="*60)
    print(f"\nGenerated files:")
    print(f"  - SKILL.md (instructions for Claude)")
    print(f"  - executor.py (MCP communication handler)")
    print(f"  - mcp-config.json (MCP server configuration)")
    print(f"  - package.json (dependencies)")
    
    print(f"\nTo use this skill:")
    print(f"1. Install dependencies:")
    print(f"   pip install mcp")
    print(f"\n2. Use the central executor from project root:")
    print(f"   python .claude/skills/mcp-skills/executor.py --skill <name> --list")
    print(f"\n3. Claude will discover it via the mcp-skills registry")
    
    print(f"\nContext savings:")
    print(f"  Before (MCP): All tools preloaded (~10k-50k tokens)")
    print(f"  After (Skill): ~100 tokens until used")
    print(f"  Reduction: ~90-99%")


async def async_main():
    """Async main function to handle all conversion modes."""
    parser = argparse.ArgumentParser(
        description="Convert MCP servers to Claude Skills with progressive disclosure",
        epilog="""
Examples:
  # List available servers in .mcp.json
  python mcp_to_skill.py --list

  # Convert single server (auto-discovers .mcp.json)
  python mcp_to_skill.py --name github --output-dir ./skills

  # Convert all compatible servers
  python mcp_to_skill.py --all --output-dir ./skills

  # Specify custom .mcp.json location
  python mcp_to_skill.py --mcp-json /path/to/.mcp.json --name github --output-dir ./skills

  # Legacy mode (backward compatible)
  python mcp_to_skill.py --mcp-config github.json --output-dir ./skills/github
""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # New .mcp.json mode arguments
    parser.add_argument(
        "--mcp-json",
        help="Path to .mcp.json file (auto-discovers if not specified)"
    )
    parser.add_argument(
        "--name",
        help="Name of specific MCP server to convert"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Convert all compatible MCP servers"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available servers in .mcp.json"
    )

    # Existing arguments (backward compatible)
    parser.add_argument(
        "--mcp-config",
        help="[Legacy] Path to individual MCP config JSON"
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for generated skill(s). Default: .claude/skills/mcp-skills/ relative to .mcp.json"
    )

    args = parser.parse_args()

    try:
        # Validate argument combinations
        validate_arguments(args)

        # Handle --list command
        if args.list:
            await list_servers(args.mcp_json)
            return

        # Legacy mode
        if args.mcp_config:
            await convert_mcp_to_skill(args.mcp_config, args.output_dir)
            return

        # New .mcp.json mode
        mcp_json_path = find_mcp_json(explicit_path=args.mcp_json)
        mcp_json = load_mcp_json(mcp_json_path)

        # Default output to mcp-skills/ directory next to .mcp.json
        output_dir = args.output_dir
        if not output_dir:
            mcp_json_dir = Path(mcp_json_path).parent
            output_dir = str(mcp_json_dir / ".claude" / "skills" / "mcp-skills")
            print(f"📂 Default output: {output_dir}")

        if args.name:
            # Single server conversion
            print(f"📄 Using: {mcp_json_path}")
            await convert_single_server(mcp_json, args.name, output_dir, mcp_json_path)
        elif args.all:
            # Batch conversion
            print(f"📄 Using: {mcp_json_path}")
            await convert_all_servers(mcp_json, output_dir, mcp_json_path)

    except (FileNotFoundError, ValueError) as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def main():
    """Entry point for the script."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
