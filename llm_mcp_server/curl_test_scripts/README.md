# MCP Server curl Test Scripts

Comprehensive test suite for the Odoo MCP Server using curl-based testing.

## Quick Start

```bash
cd curl_test_scripts

# Run quick smoke test
./run_all_tests.sh quick

# Test current server configuration  
./run_all_tests.sh current

# Run all available tests
./run_all_tests.sh all
```

## Directory Structure

```
curl_test_scripts/
├── run_all_tests.sh              # Master test runner
├── test_mcp_current_mode.sh       # Quick smoke test (any mode)
├── test_mode1_stateless_json.sh   # Mode 1: Stateless + JSON
├── test_mode3_stateful_json.sh    # Mode 3: Stateful + JSON  
├── test_mode4_stateful_sse.sh     # Mode 4: Stateful + SSE
├── test_resumability.sh           # Resumability features
├── test_mcp_server.sh            # Comprehensive test suite
└── README_TESTING.md             # Detailed documentation
```

## Test Scripts Overview

### 🚀 **Quick Tests** (No Configuration Changes Needed)

#### `test_mcp_current_mode.sh`
- **Purpose**: Smoke test for current server configuration
- **Tests**: 7 essential test cases
- **Time**: ~30 seconds
- **Usage**: `./test_mcp_current_mode.sh`

#### `test_resumability.sh`
- **Purpose**: Focused resumability testing
- **Tests**: Event IDs, stream resumption, replay functionality
- **Time**: ~45 seconds  
- **Usage**: `./test_resumability.sh`

### ⚙️ **Mode-Specific Tests** (Require Specific Configuration)

#### `test_mode1_stateless_json.sh`
- **Configuration Required**:
  - Stateless Mode = `True`
  - JSON Response Mode = `True` 
  - Enable Resumability = `False` (irrelevant)
- **Tests**: POST works, GET/DELETE fail
- **Usage**: `./test_mode1_stateless_json.sh`

#### `test_mode3_stateful_json.sh`
- **Configuration Required**:
  - Stateless Mode = `False`
  - JSON Response Mode = `True`
  - Enable Resumability = `False/True` (doesn't matter)
- **Tests**: POST works, DELETE works, GET behavior varies
- **Usage**: `./test_mode3_stateful_json.sh`

#### `test_mode4_stateful_sse.sh`  
- **Configuration Required**:
  - Stateless Mode = `False`
  - JSON Response Mode = `False`
  - Enable Resumability = `True` (recommended)
- **Tests**: POST returns JSON, GET returns SSE, resumability features
- **Usage**: `./test_mode4_stateful_sse.sh`

### 📋 **Comprehensive Tests** (Manual Configuration Changes)

#### `test_mcp_server.sh`
- **Purpose**: Tests all modes with manual configuration prompts
- **Tests**: 30+ test cases across all modes
- **Time**: 10+ minutes (with configuration changes)
- **Usage**: `./test_mcp_server.sh`

## Master Test Runner

The `run_all_tests.sh` script provides a unified interface:

### Available Commands

```bash
# Quick tests (no config changes)
./run_all_tests.sh quick          # Smoke test
./run_all_tests.sh current        # Current mode test
./run_all_tests.sh resumability   # Resumability test

# Mode-specific tests (require config)
./run_all_tests.sh mode1          # Stateless + JSON
./run_all_tests.sh mode3          # Stateful + JSON
./run_all_tests.sh mode4          # Stateful + SSE

# Comprehensive tests
./run_all_tests.sh comprehensive  # All modes with prompts
./run_all_tests.sh all            # All available tests

# Help
./run_all_tests.sh help           # Show usage information
```

### Environment Variables

```bash
# Set API key (optional, has default)
export MCP_API_KEY="your-api-key-here"

# Set server URL (optional, defaults to localhost)
export MCP_BASE_URL="http://localhost:8069/mcp"

# Run tests
./run_all_tests.sh current
```

## Server Configuration

Change server configuration in Odoo UI:
- **Path**: LLM → Configuration → MCP Server
- **Fields**:
  - **Stateless Mode**: True/False
  - **JSON Response Mode**: True/False  
  - **Enable Resumability**: True/False

### Mode Matrix

| Mode | Stateless | JSON Response | Resumability | POST | GET | DELETE |
|------|-----------|---------------|-------------|------|-----|--------|
| 1    | ✅        | ✅            | ❌          | ✅   | ❌  | ❌     |
| 2*   | ✅        | ❌            | ❌          | ✅   | ❌  | ❌     |
| 3    | ❌        | ✅            | ❌/✅       | ✅   | ❓  | ✅     |
| 4    | ❌        | ❌            | ❌/✅       | ✅   | ✅  | ✅     |

*Mode 2 (Stateless + SSE) is theoretical - not commonly used

## Test Coverage

### Protocol Features ✅
- JSON-RPC 2.0 compliance
- HTTP method validation (POST/GET/DELETE)
- Header validation (Accept, Content-Type)
- Protocol version checking
- Error code compliance

### Authentication ✅
- Anonymous requests (initialize, tools/list)
- Authenticated requests (tools/call)
- API key validation (Bearer token)
- Invalid key handling

### MCP Features ✅
- Server initialization
- Tool discovery (tools/list)
- Tool execution (tools/call)
- Notifications handling
- Session management
- **Resumability** (event IDs, stream resumption)

### Error Handling ✅
- Invalid JSON parsing
- Unknown methods  
- Invalid parameters
- Missing authentication
- Protocol violations

## Example Test Run

```bash
$ ./run_all_tests.sh current

╔════════════════════════════════════════════════════════════════╗
║                    MCP SERVER TEST SUITE                       ║
║                 Comprehensive Test Runner                      ║
╚════════════════════════════════════════════════════════════════╝

🧪 CURRENT CONFIGURATION TEST
════════════════════════════════════════════════════════════════

Running: test_mcp_current_mode.sh
Description: Test current server configuration
────────────────────────────────────────────────────────────────

=== QUICK MCP SERVER TEST - CURRENT MODE ===

Testing: Health Check
✅ PASS

Testing: Initialize (POST)
✅ PASS

Testing: Tools List (POST)
✅ PASS

Testing: Tool Call with Auth (POST)
✅ PASS

Testing: SSE Stream (GET)
✅ PASS

Testing: Session Delete (DELETE)
✅ PASS

Testing: Notification (POST)
✅ PASS

=== SUMMARY ===
Total Tests: 7
Passed: 7
Failed: 0

🎉 Quick test completed!

✅ test_mcp_current_mode.sh completed successfully

═══ TEST COMPLETED ═══
```

## Troubleshooting

### Common Issues

1. **Connection Refused**
   - Ensure Odoo server is running
   - Check MCP module is installed/updated

2. **Authentication Errors**  
   - Set valid `MCP_API_KEY` environment variable
   - Generate API key in Odoo UI

3. **Mode Detection Failures**
   - Check server configuration matches expected mode
   - Use mode-specific test scripts directly

4. **Permission Errors**
   - Ensure test scripts are executable: `chmod +x *.sh`

### Debug Mode

Enable verbose curl output:
```bash
# Add -v flag to curl commands in test scripts
curl -v -X POST ...
```

Check Odoo logs:
```bash
tail -f /var/log/odoo/odoo.log | grep -E "(MCP|mcp)"
```

## CI/CD Integration

### GitHub Actions
```yaml
- name: Test MCP Server
  run: |
    cd curl_test_scripts
    ./run_all_tests.sh quick
```

### Jenkins
```groovy
stage('MCP Tests') {
    steps {
        dir('curl_test_scripts') {
            sh './run_all_tests.sh current'
        }
    }
}
```

## Contributing

To add new tests:
1. Follow existing script patterns
2. Use consistent naming: `test_<category>_<specific>.sh`
3. Add to `run_all_tests.sh` if needed
4. Update this README

## Next Steps

- **Unit Tests**: Python-based unit test framework
- **Load Testing**: Concurrent connection testing
- **Integration Tests**: Real MCP client testing