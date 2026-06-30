# Agent Gateway User Guide

This module provides a framework-agnostic client for discovering and invoking MCP tools and A2A agent cards via SAP Agent Gateway. It automatically detects the agent type (LoB vs Customer) based on credential file presence and handles authentication accordingly.

## Installation

This package is part of the SAP Cloud SDK for Python. Import and use it directly in your application.

For LangChain integration, install the optional extra:

```bash
pip install sap-cloud-sdk[langchain]
```

## Quick Start

### Customer Agent Flow

Customer agents use file-based credentials with mTLS authentication. MCP servers are read from `integrationDependencies` in the credentials file.

#### Credential Detection

The SDK looks for credentials in the following order:

1. **`AGW_CREDENTIALS_PATH`** env var — direct path to a JSON credentials file.
2. **`SERVICE_BINDING_ROOT`** env var — scans all subdirectories for one whose `type` file contains `integration-credentials`, then reads `credentials` from that directory (servicebinding.io format).
3. **`/bindings`** — same scan as above, used as the default when `SERVICE_BINDING_ROOT` is not set.

**servicebinding.io layout** (used on BTP Kyma / Kubernetes):

```
$SERVICE_BINDING_ROOT/
└── my-agw-binding/
    ├── type          # must contain "integration-credentials"
    ├── instance_name # optional, ignored by the SDK
    └── credentials   # JSON credentials object
```

**Flat file** (used with `AGW_CREDENTIALS_PATH`):

```
/path/to/credentials.json   # JSON credentials object
```

```python
from sap_cloud_sdk.agentgateway import create_client

agw_client = create_client()

# Discover tools from all servers in integrationDependencies
tools = await agw_client.list_mcp_tools(user_token="user-jwt")

for tool in tools:
    print(f"{tool.name}: {tool.description}")

# Filter to a specific ORD ID — tenant ID is derived from credentials automatically
tools = await agw_client.list_mcp_tools(
    user_token="user-jwt",
    ord_id="sap.s4:apiResource:API_PRODUCT_0002_MCP:v1",
)

# Invoke a tool — pass the MCPTool object directly
result = await agw_client.call_mcp_tool(
    tool=tools[0],
    user_token="user-jwt",
    cost_center="1000",
)
```

> **Note:** AGW currently requires a user token for all tool calls (principal propagation). Passing `user_token` is therefore required for customer agents.

### LoB Agent Flow

LoB agents use BTP Destination Service for credential management. Tools and A2A agents are auto-discovered from destination fragments.

```python
from sap_cloud_sdk.agentgateway import ClientConfig, create_client

config = ClientConfig(timeout=30.0)
agw_client = create_client(tenant_subdomain="my-tenant", config=config)

# Discover MCP tools (auto-discovered from destination fragments)
# Pass user_token to use principal propagation when listing tools
tools = await agw_client.list_mcp_tools(user_token="user-jwt")

# Invoke a tool (user_token required for principal propagation)
result = await agw_client.call_mcp_tool(
    tool=tools[0],
    user_token="user-jwt",
    order_id="12345",
)
```

### A2A Agent Cards (LoB only)

Discover A2A agents and their agent cards from destination fragments labelled `agw.a2a.server`. Each fragment must have a `URL` property; the agent card is fetched from `{URL}/.well-known/agent-card.json` and the ORD ID is extracted from the second-to-last URL path segment.

```python
from sap_cloud_sdk.agentgateway import AgentCardFilter, create_client

agw_client = create_client(tenant_subdomain="my-tenant")

# Discover all A2A agents
agents = await agw_client.list_agent_cards()

for agent in agents:
    print(agent.ord_id)
    print(agent.agent_card.raw)  # full agent card JSON payload

# Filter by agent card name (post-fetch) or ORD ID (pre-fetch)
agents = await agw_client.list_agent_cards(
    filter=AgentCardFilter(
        agent_names=["Sample Agent"],
        ord_ids=["sap.s4:apiAccess:purchaseOrderAI:agent:v1"],
    )
)
```

### LangChain Integration

Convert MCP tools to LangChain `StructuredTool` objects for use with LangChain agents:

```python
from sap_cloud_sdk.agentgateway import create_client
from sap_cloud_sdk.agentgateway.converters import mcp_tool_to_langchain

agw_client = create_client(tenant_subdomain="my-tenant")
tools = await agw_client.list_mcp_tools(user_token="user-jwt")

langchain_tools = [
    mcp_tool_to_langchain(
        t,
        agw_client.call_mcp_tool,
        get_user_token=lambda: request.headers["Authorization"],
    )
    for t in tools
]

# Use with LangChain agent
llm_with_tools = llm.bind_tools(langchain_tools)
```

By default, optional tool parameters that resolve to `None` are not forwarded to `call_mcp_tool`. Set `omit_none=False` to forward them explicitly:

```python
mcp_tool_to_langchain(
    t,
    agw_client.call_mcp_tool,
    get_user_token=lambda: request.headers["Authorization"],
    omit_none=False,
)
```

## Concepts

### Agent Types

- **LoB (Line of Business) Agent**: Uses BTP Destination Service for credentials. Requires `tenant_subdomain`. MCP tools and A2A agent cards are auto-discovered from destination fragments.
- **Customer Agent**: Uses file-based credentials mounted on the pod filesystem with mTLS authentication. MCP servers are defined in the credentials file's `integrationDependencies`. A2A agent card discovery is not yet supported.

The SDK automatically detects the agent type based on the presence of a credentials file.

### Fragments and Labels

The SDK discovers resources via BTP Destination Service fragments filtered by the `sap-managed-runtime-type` label:

| Label value | Resource |
|---|---|
| `agw.mcp.server` | MCP tool server — `URL` property points to the MCP endpoint |
| `agw.a2a.server` | A2A agent — `URL` property is the agent base URL; ORD ID is extracted from the second-to-last URL path segment |
| `subscriber.ias` | IAS credential fragment for system-scoped token acquisition |
| `subscriber.ias.user` | IAS credential fragment for user-scoped token exchange |

## API

### Factory Function

```python
def create_client(
    tenant_subdomain: str | Callable[[], str] | None = None,
    config: ClientConfig | None = None,
) -> AgentGatewayClient
```

- `tenant_subdomain`: Required for LoB agents, ignored for Customer agents. Can be a string or callable.
- `config`: Optional `ClientConfig` used to control HTTP timeout and in-memory token cache behavior.

### ClientConfig

Use `ClientConfig` to tune request timeouts and token cache behavior for a client instance.

```python
from sap_cloud_sdk.agentgateway import ClientConfig, create_client

config = ClientConfig(
    timeout=30.0,
    fallback_token_ttl_seconds=300.0,
    token_expiry_buffer_seconds=30.0,
    max_system_token_cache_size=32,
    max_user_token_cache_size=256,
)

agw_client = create_client(tenant_subdomain="my-tenant", config=config)
```

- `timeout`: HTTP timeout in seconds for token requests, MCP calls, and agent card fetches. Default: `60.0`.
- `fallback_token_ttl_seconds`: Used when the token response does not include expiry metadata. Default: `300.0`.
- `token_expiry_buffer_seconds`: Safety buffer subtracted from explicit token expiries before a cached token is reused. Default: `30.0`.
- `max_system_token_cache_size`: Maximum number of cached system tokens per client instance. Default: `32`.
- `max_user_token_cache_size`: Maximum number of cached exchanged user tokens per client instance. Default: `256`.

The SDK keeps token caches per `AgentGatewayClient` instance and reuses valid cached tokens for repeated authentication calls. System and user token caches are bounded independently with least-recently-used eviction.

### AgentGatewayClient

```python
class AgentGatewayClient:
    async def list_mcp_tools(
        self,
        user_token: str | Callable[[], str] | None = None,
        ord_id: str | None = None,
    ) -> list[MCPTool]

    async def call_mcp_tool(
        self,
        tool: MCPTool | str,
        user_token: str | Callable[[], str] | None = None,
        ord_id: str | None = None,
        **kwargs,
    ) -> str

    async def list_agent_cards(
        self,
        filter: AgentCardFilter | None = None,
    ) -> list[Agent]
```

### AgentCardFilter

```python
from sap_cloud_sdk.agentgateway import AgentCardFilter

AgentCardFilter(
    agent_names=[],  # agent card names to include (matched against card JSON `name`); empty = no filter
    ord_ids=[],      # ORD IDs to include (extracted from fragment URL); empty = no filter
)
```

Both fields default to empty lists. Filters are applied with AND semantics: if both are set, an agent must match both to be included. `agent_names` is applied after fetching (requires reading the card); `ord_ids` is applied before fetching (extracted from the fragment URL, no card request needed).

### Data Models

```python
@dataclass
class Agent:
    ord_id: str       # ORD ID from fragment ordId property
    agent_card: AgentCard

@dataclass
class AgentCard:
    raw: dict         # full parsed JSON from /.well-known/agent-card.json

@dataclass
class MCPTool:
    name: str
    server_name: str
    description: str
    input_schema: dict
    url: str
    fragment_name: str | None
```

#### `list_mcp_tools`

| Parameter | Type | Description |
|-----------|------|-------------|
| `user_token` | `str \| Callable[[], str] \| None` | User JWT for principal propagation. When provided, a jwt-bearer token exchange is performed instead of a system token request. |
| `ord_id` | `str \| None` | ORD ID to filter results to a single MCP server. The tenant ID is derived from the credentials — no need to pass it separately. Raises `AgentGatewaySDKError` if the ORD ID matches multiple `integrationDependencies` entries. |

#### `call_mcp_tool`

| Parameter | Type | Description |
|-----------|------|-------------|
| `tool` | `MCPTool \| str` | The tool to invoke. Pass an `MCPTool` object (from `list_mcp_tools`) or a tool name as a string. When a string is given, `list_mcp_tools` is called first to resolve the tool — provide `ord_id` to narrow the lookup. |
| `user_token` | `str \| Callable[[], str] \| None` | User JWT for principal propagation. Required for LoB agents; optional for customer agents (falls back to system token). |
| `ord_id` | `str \| None` | ORD ID used to resolve the tool when `tool` is given as a string. The tenant ID is derived from the credentials automatically. |
| `**kwargs` | | Tool input parameters forwarded directly to the MCP tool. See `tool.input_schema` for expected fields. |
