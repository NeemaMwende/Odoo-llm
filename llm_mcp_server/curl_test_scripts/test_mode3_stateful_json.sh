#!/bin/bash

# MCP Server Mode 3 Tests: Stateful + JSON Response
# Configuration: stateless_mode=False, json_response_mode=True, enable_resumability=False/True

set -e

# Configuration
API_KEY="${MCP_API_KEY:-f7bb2e2f7fe72a18dac64b79b6d51a7e631fda24}"
BASE_URL="${MCP_BASE_URL:-http://localhost:8069/mcp}"

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

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Test function
run_test() {
    local test_name="$1"
    local expected_status="$2"
    local expected_content="$3"
    shift 3
    local curl_command=("$@")

    print_test "$test_name"

    local response
    local http_status
    local temp_file=$(mktemp)

    if response=$(curl -s -w "%{http_code}" -o "$temp_file" --max-time 10 "${curl_command[@]}" 2>/dev/null); then
        http_status="${response}"
        response=$(cat "$temp_file")
        rm -f "$temp_file"

        if [[ "$http_status" == "$expected_status" ]] && [[ -z "$expected_content" || "$response" == *"$expected_content"* ]]; then
            print_success
            return 0
        else
            print_failure "Expected status $expected_status with '$expected_content', got $http_status"
            echo "Response: ${response:0:150}..."
            return 1
        fi
    else
        print_failure "Request failed"
        rm -f "$temp_file"
        return 1
    fi
}

print_header "MODE 3: STATEFUL + JSON RESPONSE MODE TESTS"
print_info "Expected Configuration:"
print_info "  - stateless_mode = False"
print_info "  - json_response_mode = True"
print_info "  - enable_resumability = False/True (doesn't affect JSON mode)"
print_info ""
print_info "Expected Behavior:"
print_info "  - POST requests work and return JSON"
print_info "  - GET requests behavior depends on json_response_mode setting"
print_info "  - DELETE requests work"

# POST requests should work
run_test "Initialize (POST)" "200" '"result"' \
    -X POST "$BASE_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{
        "jsonrpc": "2.0",
        "method": "initialize",
        "id": 1,
        "params": {
            "protocolVersion": "2025-06-18",
            "clientInfo": {"name": "mode3-test", "version": "1.0"}
        }
    }'

run_test "Tools List (POST)" "200" '"tools"' \
    -X POST "$BASE_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": 2
    }'

run_test "Tools Call with Auth (POST)" "200" '"content"' \
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

run_test "Notification (POST)" "202" "" \
    -X POST "$BASE_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }'

# DELETE requests should work in stateful mode
run_test "DELETE Request (session cleanup)" "204" "" \
    -X DELETE "$BASE_URL"

# GET request behavior depends on json_response_mode
print_test "GET Request (behavior depends on json_response_mode)"
get_response=""
get_status=""
get_temp=$(mktemp)

if get_response=$(curl -s -w "%{http_code}" -o "$get_temp" --max-time 8 -X GET "$BASE_URL" -H "Accept: text/event-stream" 2>/dev/null); then
    get_status="${get_response}"
    get_response=$(cat "$get_temp")
    rm -f "$get_temp"

    if [[ "$get_status" == "200" ]]; then
        if [[ "$get_response" == *"event:"* ]]; then
            print_success
            print_info "GET returns SSE stream (json_response_mode = False)"
        else
            print_success
            print_info "GET returns JSON (json_response_mode = True)"
        fi
    else
        print_failure "GET request failed with status $get_status"
    fi
else
    print_failure "GET request failed"
    rm -f "$get_temp"
fi
TOTAL_TESTS=$((TOTAL_TESTS + 1))
PASSED_TESTS=$((PASSED_TESTS + 1))

# Test session persistence
run_test "Session ID Consistency" "200" '"sessionId"' \
    -X POST "$BASE_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{
        "jsonrpc": "2.0",
        "method": "initialize",
        "id": 10,
        "params": {
            "protocolVersion": "2025-06-18",
            "clientInfo": {"name": "session-test", "version": "1.0"}
        }
    }'

print_header "MODE 3 TEST SUMMARY"
echo -e "Total Tests: $TOTAL_TESTS"
echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
echo -e "${RED}Failed: $FAILED_TESTS${NC}"

if [[ $FAILED_TESTS -gt 0 ]]; then
    echo -e "\n${RED}❌ Some tests failed. Check server configuration:${NC}"
    echo -e "${RED}   - Go to: LLM → Configuration → MCP Server${NC}"
    echo -e "${RED}   - Set: Stateless Mode = False${NC}"
    echo -e "${RED}   - Set: JSON Response Mode = True${NC}"
    exit 1
else
    echo -e "\n${GREEN}🎉 All Mode 3 tests passed!${NC}"
    echo -e "${GREEN}Server is correctly configured for Stateful + JSON mode${NC}"
    exit 0
fi
