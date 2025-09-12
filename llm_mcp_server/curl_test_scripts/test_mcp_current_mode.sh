#!/bin/bash

# Quick MCP Server Test for Current Configuration
# Tests the current server mode without requiring configuration changes

set -e

# Configuration
API_KEY="${MCP_API_KEY:-f7bb2e2f7fe72a18dac64b79b6d51a7e631fda24}"
BASE_URL="${MCP_BASE_URL:-http://localhost:8069/mcp}"
HEALTH_URL="${MCP_BASE_URL:-http://localhost:8069/mcp/health}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}\n"
}

print_test() {
    echo -e "${YELLOW}Testing: $1${NC}"
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
}

print_success() {
    echo -e "${GREEN}✅ PASS${NC}"
    PASSED_TESTS=$((PASSED_TESTS + 1))
}

print_failure() {
    echo -e "${RED}❌ FAIL: $1${NC}"
    FAILED_TESTS=$((FAILED_TESTS + 1))
}

# Quick test function
quick_test() {
    local test_name="$1"
    local curl_command=("${@:2}")

    print_test "$test_name"

    if output=$(curl -s --max-time 10 "${curl_command[@]}" 2>/dev/null); then
        echo "Response: ${output:0:100}..."
        print_success
    else
        print_failure "Request failed or timed out"
    fi
}

print_header "QUICK MCP SERVER TEST - CURRENT MODE"

# Health check
quick_test "Health Check" \
    -X GET "$HEALTH_URL"

# Initialize
quick_test "Initialize (POST)" \
    -X POST "$BASE_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{
        "jsonrpc": "2.0",
        "method": "initialize",
        "id": 1,
        "params": {
            "protocolVersion": "2025-06-18",
            "clientInfo": {"name": "quick-test", "version": "1.0"}
        }
    }'

# Tools list
quick_test "Tools List (POST)" \
    -X POST "$BASE_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": 2
    }'

# Authenticated tool call
quick_test "Tool Call with Auth (POST)" \
    -X POST "$BASE_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Authorization: Bearer $API_KEY" \
    -d '{
        "jsonrpc": "2.0",
        "method": "tools/call",
        "id": 3,
        "params": {
            "name": "odoo_record_retriever",
            "arguments": {"model": "res.users", "limit": 1}
        }
    }'

# Test GET request (will work in stateful mode, fail in stateless)
quick_test "SSE Stream (GET) - may fail in stateless mode" \
    -X GET "$BASE_URL" \
    -H "Accept: text/event-stream" \
    --max-time 5

# Test DELETE request (will work in stateful mode, fail in stateless)
quick_test "Session Delete (DELETE) - may fail in stateless mode" \
    -X DELETE "$BASE_URL" \
    --max-time 5

# Test notification
quick_test "Notification (POST)" \
    -X POST "$BASE_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }'

print_header "SUMMARY"
echo -e "Total Tests: $TOTAL_TESTS"
echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
echo -e "${RED}Failed: $FAILED_TESTS${NC}"

if [[ $FAILED_TESTS -gt 0 ]]; then
    echo -e "\n${YELLOW}Note: Some failures are expected depending on server mode${NC}"
    echo -e "${YELLOW}Run the full test suite (test_mcp_server.sh) for comprehensive testing${NC}"
fi

echo -e "\n${GREEN}Quick test completed!${NC}"
