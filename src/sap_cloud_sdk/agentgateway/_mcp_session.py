"""Shared helpers for MCP session management."""

import uuid

import httpx
from mcp import ClientSession, McpError
from mcp.client.streamable_http import streamable_http_client

from sap_cloud_sdk.agentgateway._models import MCPTool
from sap_cloud_sdk.agentgateway.exceptions import AgentGatewayServerError


async def invoke_mcp_tool(tool: MCPTool, auth_token: str, timeout: float, **kwargs) -> str:
    """Open an MCP session, call a tool, and return its text result.

    Handles McpError from both initialize() and call_tool(), and checks
    result.isError, raising AgentGatewayServerError in all three cases.

    Args:
        tool: MCPTool to invoke.
        auth_token: Raw bearer token for the Authorization header.
        timeout: HTTP timeout in seconds.
        **kwargs: Tool input parameters forwarded to call_tool().

    Returns:
        Tool result as a string, or "" if the response has no content.

    Raises:
        AgentGatewayServerError: If the server returns any kind of error.
    """
    async with httpx.AsyncClient(
        headers={
            "Authorization": f"Bearer {auth_token}",
            "x-correlation-id": str(uuid.uuid4()),
        },
        timeout=timeout,
    ) as http_client:
        async with streamable_http_client(tool.url, http_client=http_client) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                try:
                    await session.initialize()
                except McpError as e:
                    raise AgentGatewayServerError(
                        f"Agent Gateway rejected MCP session for tool '{tool.name}': {e.error.message}",
                        error_code=e.error.code,
                    ) from e
                try:
                    result = await session.call_tool(tool.name, kwargs)
                except McpError as e:
                    raise AgentGatewayServerError(
                        f"Agent Gateway returned error for tool '{tool.name}': {e.error.message}",
                        error_code=e.error.code,
                    ) from e
                if result.isError:
                    raise AgentGatewayServerError(
                        f"Tool '{tool.name}' returned an error: {_error_text(result.content)}"
                    )
                if not result.content:
                    return ""
                return str(getattr(result.content[0], "text", ""))


def _error_text(content: list) -> str:
    """Extract a human-readable message from MCP error content blocks."""
    texts = [getattr(block, "text", None) for block in content]
    message = " ".join(t for t in texts if t)
    return message or "unknown error"
