# MCP Server Testing Guide

This guide covers comprehensive testing of the Odoo MCP Server implementation.

## Test Suite Overview

We provide two curl-based test scripts:

### 1. **Quick Test** (`test_mcp_current_mode.sh`)
- Tests the current server configuration
- No manual configuration changes required
- Good for smoke testing and CI/CD
- ~7 test cases, runs in <30 seconds

### 2. **Comprehensive Test** (`test_mcp_server.sh`)
- Tests all 4 server modes with configuration changes
- Requires manual configuration between test suites
- Complete protocol validation
- ~30+ test cases, comprehensive coverage

## Server Configuration Modes

| Mode | Stateless | JSON Response | Resumability | POST | GET | DELETE |
|------|-----------|---------------|-------------|------|-----|--------|
| 1    | ✅        | ✅            | ❌          | ✅   | ❌  | ❌     |
| 2    | ✅        | ❌            | ❌          | ✅   | ❌  | ❌     |
| 3    | ❌        | ✅            | ❌/✅       | ✅   | ?   | ✅     |
| 4    | ❌        | ❌            | ❌/✅       | ✅   | ✅  | ✅     |

## Running Tests

### Prerequisites
```bash
# Ensure curl is installed
curl --version

# Set API key (optional, defaults to test key)
export MCP_API_KEY="your-api-key-here"

# Set server URL (optional, defaults to localhost:8069)
export MCP_BASE_URL="http://localhost:8069/mcp"
```

### Quick Test
```bash
# Test current configuration
./test_mcp_current_mode.sh
```

Example output:
```
=== QUICK MCP SERVER TEST - CURRENT MODE ===

Testing: Health Check
Response: {"status":"healthy","server":"odoo_llm_mcp_server"...
✅ PASS

Testing: Initialize (POST)  
Response: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion"...
✅ PASS
```

### Comprehensive Test
```bash
# Test all modes (requires manual config changes)
./test_mcp_server.sh
```

The script will prompt you to change server configuration between test suites.

## Test Categories

### 1. **Health Endpoint Tests**
- GET /mcp/health
- POST /mcp/health
- Validates basic server functionality

### 2. **JSON-RPC Protocol Tests**
- `initialize` method
- `tools/list` method
- `tools/call` method (with authentication)
- `notifications/initialized` method

### 3. **HTTP Method Tests**
- POST requests (all modes)
- GET requests (stateful modes only)
- DELETE requests (stateful modes only)

### 4. **Authentication Tests**
- Anonymous requests (initialize, tools/list)
- Authenticated requests (tools/call)
- Invalid API key handling
- Missing authentication

### 5. **Protocol Validation Tests**
- Invalid Accept headers
- Invalid Content-Type headers
- Protocol version mismatches
- Malformed JSON-RPC requests
- Unknown methods

### 6. **Mode-Specific Tests**
- **Stateless Mode**: GET/DELETE should return METHOD_NOT_FOUND
- **Stateful Mode**: All HTTP methods should work
- **SSE Mode**: GET should return streaming events
- **JSON Mode**: All responses should be JSON

## Expected Responses

### Successful JSON-RPC Request
```json
{
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "protocolVersion": "2025-06-18",
        "capabilities": {"tools": {"listChanged": false}},
        "serverInfo": {"name": "odoo_llm_mcp_server", "version": "1.0.0"}
    }
}
```

### JSON-RPC Error Response
```json
{
    "jsonrpc": "2.0", 
    "id": 1,
    "error": {
        "code": -32601,
        "message": "Method not found: unknown/method",
        "data": null
    }
}
```

### SSE Stream Response
```
event: connected
data: {"jsonrpc":"2.0","id":0,"result":{"type":"connected","timestamp":1757684075.48}}
id: ba7df73b-7556-47c9-8dac-554cdf5f2716

event: ping
data: {"jsonrpc":"2.0","id":1,"result":{"type":"ping","count":1,"timestamp":1757684075.48}}
id: 9b5f666a-619e-4f7a-836b-ab2fac22b2e2
```

### Notification Response
```
HTTP/1.1 202 Accepted
Content-Length: 0
```

## Troubleshooting

### Common Issues

1. **Connection Refused**
   ```bash
   curl: (7) Failed to connect to localhost:8069
   ```
   - Ensure Odoo server is running
   - Check if MCP module is installed and updated

2. **Authentication Errors**
   ```json
   {"error": {"code": -32602, "message": "Missing API key"}}
   ```
   - Generate API key in Odoo: Settings → Users & Companies → API Keys
   - Set `MCP_API_KEY` environment variable

3. **Invalid JSON-RPC Response**
   ```json
   {"error": {"code": -32700, "message": "Parse error"}}
   ```
   - Check JSON syntax in request body
   - Ensure Content-Type is application/json

4. **Method Not Found Errors**
   ```json
   {"error": {"code": -32601, "message": "GET not supported in stateless mode"}}
   ```
   - Check server configuration mode
   - GET requests only work in stateful mode

### Debug Mode
Enable debug logging by setting:
```bash
# In Odoo configuration
log_level = debug

# Or check logs
tail -f /var/log/odoo/odoo.log | grep -E "(MCP|mcp)"
```

## Integration with CI/CD

### GitHub Actions Example
```yaml
- name: Test MCP Server
  run: |
    # Start Odoo server
    docker-compose up -d odoo
    
    # Wait for server to be ready
    wget --retry-connrefused --waitretry=5 --timeout=60 -qO- http://localhost:8069/mcp/health
    
    # Run quick test
    ./test_mcp_current_mode.sh
    
    # Run comprehensive test (requires automation of config changes)
    # ./test_mcp_server.sh
```

### Jenkins Pipeline Example
```groovy
pipeline {
    agent any
    stages {
        stage('Test MCP Server') {
            steps {
                sh './test_mcp_current_mode.sh'
            }
        }
    }
}
```

## Future Enhancements

### Unit Test Framework
We'll create a Python-based unit test framework using:
- `unittest` or `pytest` for test structure
- `requests` for HTTP client
- Mock Odoo environment for isolated testing
- Test fixtures for different server configurations

### Load Testing
- Use `curl` with parallel execution
- Test concurrent connections
- SSE stream stress testing
- Tool execution performance testing

### Integration Testing
- Test with real MCP clients (Claude Desktop, Letta)
- End-to-end workflow testing
- Multi-session testing
- Resumability testing

## Contributing

To add new tests:

1. **Curl Tests**: Add new test functions to `test_mcp_server.sh`
2. **Unit Tests**: Create Python test files (coming soon)
3. **Documentation**: Update this README with new test scenarios

Test naming convention: `test_<category>_<specific_case>`
- Example: `test_authentication_invalid_key`
- Example: `test_stateless_mode_get_request_fails`