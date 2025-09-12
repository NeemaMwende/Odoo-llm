# MCP HTTP Streamable Server API Specification

## Executive Summary

The MCP (Model Context Protocol) HTTP Streamable Server provides a robust transport layer for bidirectional communication between MCP clients and servers using HTTP with Server-Sent Events (SSE). It supports both stateful session-based connections and stateless operation modes, with optional resumability through event stores.

## Architecture Overview

```mermaid
graph TB
    subgraph "Client Side"
        C[MCP Client]
        HC[HTTP Client]
    end

    subgraph "Server Side"
        HS[HTTP Server/ASGI]
        ST[StreamableHTTP Transport]
        SM[Session Manager]
        ES[Event Store<br/>Optional]
        MS[MCP Server]
    end

    C --> HC
    HC -->|HTTP/SSE| HS
    HS --> ST
    ST --> SM
    SM --> MS
    ST -.->|Resumability| ES

    style ES stroke-dasharray: 5 5
```

## Core Components

### 1. Transport Layer

- **StreamableHTTPServerTransport**: Main transport implementation
- **StreamableHTTPSessionManager**: Session lifecycle management
- **EventStore**: Optional interface for resumability

### 2. Communication Modes

```mermaid
graph LR
    subgraph "Response Modes"
        SSE[SSE Stream<br/>Default]
        JSON[JSON Response<br/>Optional]
    end

    subgraph "Session Modes"
        SF[Stateful<br/>Session Tracking]
        SL[Stateless<br/>No Sessions]
    end

    POST[POST Request] --> SSE
    POST --> JSON

    SF --> Sessions[Persistent Sessions]
    SL --> Fresh[Fresh Transport<br/>per Request]
```

## API Endpoints

### POST / - Send Messages

Sends JSON-RPC messages to the server and receives responses.

```mermaid
sequenceDiagram
    participant Client
    participant Server
    participant MCP App

    Client->>Server: POST / (JSON-RPC Request)
    Note over Server: Validate Headers
    Server->>MCP App: Process Message

    alt SSE Mode (Default)
        Server-->>Client: SSE Stream
        Server-->>Client: event: message
        Server-->>Client: data: {response}
        Server-->>Client: id: 123
    else JSON Mode
        Server-->>Client: JSON Response
    end
```

**Request Requirements:**

- Headers:
  - `Content-Type: application/json`
  - `Accept: application/json, text/event-stream`
  - `mcp-session-id: <session-id>` (except for initialize)
  - `mcp-protocol-version: 2025-03-26` (optional)

**Response Types:**
| Mode | Content-Type | Use Case |
|------|--------------|----------|
| SSE | `text/event-stream` | Real-time streaming responses |
| JSON | `application/json` | Simple request-response |

### GET / - Server Stream

Establishes a standalone SSE stream for server-initiated messages.

```mermaid
sequenceDiagram
    participant Client
    participant Server

    Client->>Server: GET /
    Note over Server: Validate Session
    Server-->>Client: SSE Stream Established

    loop Server Events
        Server-->>Client: event: message
        Server-->>Client: data: {notification/request}
    end
```

**Features:**

- One GET stream per session maximum
- Supports resumability via `Last-Event-ID` header
- Server can send notifications and requests

### DELETE / - Terminate Session

Explicitly terminates a session and closes all associated streams.

```mermaid
sequenceDiagram
    participant Client
    participant Server

    Client->>Server: DELETE /
    Note over Server: Validate Session
    Server->>Server: Close all streams
    Server->>Server: Mark terminated
    Server-->>Client: 200 OK
```

## Session Lifecycle

```mermaid
stateDiagram-v2
    [*] --> New: Initial Request

    New --> Initializing: POST /initialize
    Initializing --> Active: Session Created

    Active --> Active: POST Requests
    Active --> Streaming: GET / (Optional)
    Streaming --> Active: Continue Operations

    Active --> Terminated: DELETE /
    Active --> Terminated: Server Shutdown
    Streaming --> Terminated: Connection Lost

    Terminated --> [*]

    note right of Active
        Session ID required
        for all requests
    end note

    note right of Streaming
        Server can push
        notifications
    end note
```

## Headers Reference

### Request Headers

| Header                 | Required   | Description                                             |
| ---------------------- | ---------- | ------------------------------------------------------- |
| `mcp-session-id`       | Yes\*      | Session identifier (ASCII 0x21-0x7E)                    |
| `mcp-protocol-version` | No         | Protocol version (default: 2025-03-26)                  |
| `Accept`               | Yes (POST) | Must include `application/json` and `text/event-stream` |
| `Content-Type`         | Yes (POST) | Must be `application/json`                              |
| `Last-Event-ID`        | No         | Resume SSE stream from specific event                   |

\*Not required for initialize requests

### Response Headers

| Header           | Description                               |
| ---------------- | ----------------------------------------- |
| `mcp-session-id` | Session ID (if active)                    |
| `Content-Type`   | `application/json` or `text/event-stream` |
| `Cache-Control`  | `no-cache, no-transform` (SSE)            |
| `Connection`     | `keep-alive` (SSE)                        |

## Status Codes

```mermaid
graph TD
    subgraph "Success Codes"
        S200[200 OK<br/>Success]
        S202[202 Accepted<br/>Notification Received]
    end

    subgraph "Client Errors"
        E400[400 Bad Request<br/>Invalid JSON/Params]
        E404[404 Not Found<br/>Invalid Session]
        E406[406 Not Acceptable<br/>Missing Accept Headers]
        E409[409 Conflict<br/>Stream Already Exists]
        E415[415 Unsupported Media<br/>Wrong Content-Type]
    end

    subgraph "Server Errors"
        E500[500 Internal Error<br/>Processing Failed]
    end
```

## Configuration Options

```python
# Basic Configuration
StreamableHTTPServerTransport(
    mcp_session_id=None,              # Auto-generate if None
    is_json_response_enabled=False,   # Use JSON instead of SSE
    event_store=None,                 # Enable resumability
    security_settings=None            # DNS rebinding protection
)

# Session Manager Configuration
StreamableHTTPSessionManager(
    app=mcp_server,                   # MCP Server instance
    event_store=event_store,          # Optional resumability
    json_response=False,              # Response mode
    stateless=False,                  # Session mode
    security_settings=settings        # Security config
)
```

## Resumability with Event Store

```mermaid
sequenceDiagram
    participant Client
    participant Server
    participant EventStore

    Note over Client,EventStore: Normal Operation
    Client->>Server: Request
    Server->>EventStore: store_event()
    Server-->>Client: Response (id: 123)

    Note over Client,EventStore: Connection Lost
    Client--xServer: Connection Drops

    Note over Client,EventStore: Reconnection
    Client->>Server: GET /<br/>Last-Event-ID: 123
    Server->>EventStore: replay_events_after(123)
    EventStore-->>Server: Missed Events
    Server-->>Client: Replay Events
    Server-->>Client: Continue Stream
```

## Implementation Example

### Server Setup

```python
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount

# Create MCP server
mcp = FastMCP("My MCP Server")

# Define tools
@mcp.tool()
def hello(name: str) -> str:
    """Say hello to someone"""
    return f"Hello, {name}!"

# Mount as ASGI application
app = Starlette(
    routes=[
        Mount("/mcp", app=mcp.streamable_http_app())
    ]
)

# Run with: uvicorn app:app --reload
```

### Client Connection Flow

```mermaid
graph TD
    Start([Client Start])
    Init[POST /initialize<br/>No Session ID]
    GetSession[Receive Session ID<br/>from Response]
    Store[Store Session ID]

    UseAPI{API Operations}
    Post[POST /<br/>Include Session ID]
    Get[GET /<br/>Optional SSE Stream]

    End[DELETE /<br/>Terminate Session]
    Stop([Client Stop])

    Start --> Init
    Init --> GetSession
    GetSession --> Store
    Store --> UseAPI

    UseAPI --> Post
    UseAPI --> Get
    Post --> UseAPI
    Get --> UseAPI

    UseAPI --> End
    End --> Stop
```

## Security Features

### DNS Rebinding Protection

- Validates Host headers against allowed origins
- Configurable via `TransportSecuritySettings`
- Prevents malicious redirects

### Session Security

- Session IDs use visible ASCII characters only (0x21-0x7E)
- Validation pattern: `^[\x21-\x7E]+$`
- Sessions isolated from each other

### Protocol Versioning

- Negotiated during initialization
- Supports version compatibility checks
- Default: `2025-03-26`

## Performance Considerations

### Stateful Mode

- ✅ Session persistence
- ✅ Event store support
- ✅ Multiple concurrent streams
- ❌ Higher memory usage
- **Use for:** Traditional server deployments

### Stateless Mode

- ✅ No session overhead
- ✅ Scales horizontally
- ✅ Serverless compatible
- ❌ No resumability
- **Use for:** Serverless, edge computing

## Error Handling

```mermaid
graph LR
    subgraph "Request Validation"
        V1[Check Method]
        V2[Check Headers]
        V3[Check Session]
        V4[Parse JSON]
    end

    subgraph "Error Response"
        E1[Error Code]
        E2[Error Message]
        E3[Status Code]
    end

    V1 -->|Invalid| E1
    V2 -->|Missing| E2
    V3 -->|Invalid| E3
    V4 -->|Failed| E1

    E1 --> Response[JSON Error Response]
    E2 --> Response
    E3 --> Response
```

## Best Practices

1. **Session Management**

   - Always store session IDs securely
   - Implement proper cleanup on disconnect
   - Use event stores for critical applications

2. **Error Recovery**

   - Implement exponential backoff for reconnections
   - Store Last-Event-ID for resumability
   - Handle all HTTP status codes

3. **Performance**

   - Use JSON mode for simple request-response
   - Implement connection pooling
   - Monitor stream health

4. **Security**
   - Enable DNS rebinding protection
   - Validate all inputs
   - Use HTTPS in production

## Conclusion

The MCP HTTP Streamable Server provides a flexible, scalable transport layer for MCP applications. With support for both stateful and stateless operations, SSE streaming, and optional resumability, it can adapt to various deployment scenarios from traditional servers to modern serverless architectures.
