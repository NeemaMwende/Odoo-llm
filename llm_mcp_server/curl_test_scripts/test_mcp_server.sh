#!/bin/bash

# MCP Server Comprehensive Test Suite
# Tests all 4 modes with different configurations

set -e  # Exit on any error

# Configuration
API_KEY="${MCP_API_KEY:-f7bb2e2f7fe72a18dac64b79b6d51a7e631fda24}"
BASE_URL="${MCP_BASE_URL:-http://localhost:8069/mcp}"
HEALTH_URL="${MCP_BASE_URL:-http://localhost:8069/mcp/health}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Test result tracking
declare -a FAILED_TEST_NAMES=()

print_header() {
    echo -e "\n${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}\n"
}

print_test() {
    echo -e "${YELLOW}Testing: $1${NC}"
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
}

print_success() {
    echo -e "${GREEN}✅ PASS: $1${NC}"
    PASSED_TESTS=$((PASSED_TESTS + 1))
}

print_failure() {
    echo -e "${RED}❌ FAIL: $1${NC}"
    echo -e "${RED}   Error: $2${NC}"
    FAILED_TESTS=$((FAILED_TESTS + 1))
    FAILED_TEST_NAMES+=("$1")
}

print_info() {
    echo -e "${BLUE}ℹ️  Info: $1${NC}"
}

# Test helper function
run_test() {
    local test_name="$1"
    local expected_status="$2"
    local expected_content="$3"
    shift 3
    local curl_command=("$@")
    
    print_test "$test_name"
    
    # Run curl command and capture response and status
    local response
    local http_status
    local temp_file=$(mktemp)
    
    if response=$(curl -s -w "%{http_code}" -o "$temp_file" "${curl_command[@]}" 2>/dev/null); then
        http_status="${response}"
        response=$(cat "$temp_file")
        rm -f "$temp_file"
    else
        print_failure "$test_name" "Curl command failed"
        rm -f "$temp_file"
        return 1
    fi
    
    # Check HTTP status
    if [[ "$http_status" != "$expected_status" ]]; then
        print_failure "$test_name" "Expected status $expected_status, got $http_status"
        echo "Response: $response"
        return 1
    fi
    
    # Check content if specified
    if [[ -n "$expected_content" && "$response" != *"$expected_content"* ]]; then
        print_failure "$test_name" "Response doesn't contain expected content: $expected_content"
        echo "Response: $response"
        return 1
    fi
    
    print_success "$test_name"
    return 0
}

# JSON-RPC Request Templates
initialize_request() {
    cat << 'EOF'
{
    "jsonrpc": "2.0",
    "method": "initialize",
    "id": 1,
    "params": {
        "protocolVersion": "2025-06-18",
        "clientInfo": {
            "name": "test-suite",
            "version": "1.0.0"
        }
    }
}
EOF
}

tools_list_request() {
    cat << 'EOF'
{
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 2
}
EOF
}

tools_call_request() {
    cat << 'EOF'
{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "id": 3,
    "params": {
        "name": "odoo_record_retriever",
        "arguments": {
            "model": "res.users",
            "limit": 1
        }
    }
}
EOF
}

initialized_notification() {
    cat << 'EOF'
{
    "jsonrpc": "2.0",
    "method": "notifications/initialized"
}
EOF
}

invalid_request() {
    cat << 'EOF'
{
    "jsonrpc": "2.0",
    "method": "nonexistent/method",
    "id": 999
}
EOF
}

# Test Functions for Different Modes

test_health_endpoint() {
    print_header "HEALTH ENDPOINT TESTS"
    
    run_test "Health Check (GET)" "200" '"status"' \
        -X GET "$HEALTH_URL"
    
    run_test "Health Check (POST)" "200" '"status"' \
        -X POST "$HEALTH_URL" \
        -H "Content-Type: application/json" \
        -d '{}'
}

test_stateless_json_mode() {
    print_header "MODE 1: STATELESS + JSON RESPONSE"
    print_info "Expected: POST works, GET/DELETE return METHOD_NOT_FOUND"
    
    # POST requests should work
    run_test "Initialize (POST)" "200" '"result"' \
        -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d "$(initialize_request)"
    
    run_test "Tools List (POST)" "200" '"tools"' \
        -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d "$(tools_list_request)"
    
    run_test "Tools Call (POST, with auth)" "200" '"content"' \
        -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -H "Authorization: Bearer $API_KEY" \
        -d "$(tools_call_request)"
    
    run_test "Initialized Notification (POST)" "202" "" \
        -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d "$(initialized_notification)"
    
    # GET requests should fail
    run_test "GET Request (should fail)" "200" "METHOD_NOT_FOUND\|not supported in stateless mode" \
        -X GET "$BASE_URL" \
        -H "Accept: text/event-stream" \
        --max-time 5
    
    # DELETE requests should fail
    run_test "DELETE Request (should fail)" "200" "METHOD_NOT_FOUND\|not supported in stateless mode" \
        -X DELETE "$BASE_URL" \
        --max-time 5
}

test_stateful_json_mode() {
    print_header "MODE 3: STATEFUL + JSON RESPONSE"
    print_info "Expected: POST/DELETE work, GET behavior depends on implementation"
    
    # POST requests should work
    run_test "Initialize (POST)" "200" '"result"' \
        -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d "$(initialize_request)"
    
    run_test "Tools List (POST)" "200" '"tools"' \
        -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d "$(tools_list_request)"
    
    # DELETE requests should work
    run_test "DELETE Request (session cleanup)" "204" "" \
        -X DELETE "$BASE_URL" \
        --max-time 5
}

test_stateful_sse_mode() {
    print_header "MODE 4: STATEFUL + SSE STREAMING"
    print_info "Expected: POST returns JSON, GET returns SSE stream, DELETE works"
    
    # POST requests should return JSON
    run_test "Initialize (POST)" "200" '"result"' \
        -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d "$(initialize_request)"
    
    run_test "Tools List (POST)" "200" '"tools"' \
        -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d "$(tools_list_request)"
    
    # GET requests should return SSE stream
    run_test "GET SSE Stream" "200" "event: connected" \
        -X GET "$BASE_URL" \
        -H "Accept: text/event-stream" \
        --max-time 10
    
    # Test resumability if enabled
    test_resumability_features
    
    # DELETE requests should work
    run_test "DELETE Request (session cleanup)" "204" "" \
        -X DELETE "$BASE_URL" \
        --max-time 5
}

test_resumability_features() {
    print_header "RESUMABILITY TESTS"
    print_info "Testing event storage and stream resumption"
    
    # Test basic event ID generation
    print_test "Event ID generation"
    local stream_output
    if stream_output=$(curl -s --max-time 8 -X GET "$BASE_URL" -H "Accept: text/event-stream" 2>/dev/null); then
        if [[ "$stream_output" == *"id: "* ]]; then
            print_success "Event ID generation"
            local first_event_id
            first_event_id=$(echo "$stream_output" | grep "^id: " | head -1 | cut -d' ' -f2 | tr -d '\r')
            print_info "Sample Event ID: $first_event_id"
            
            # Test resumption
            print_test "Stream resumption with Last-Event-ID"
            local resumed_stream
            if resumed_stream=$(curl -s --max-time 8 -X GET "$BASE_URL" \
                -H "Accept: text/event-stream" \
                -H "Last-Event-ID: $first_event_id" 2>/dev/null); then
                
                if [[ "$resumed_stream" == *"reconnected"* ]]; then
                    print_success "Stream resumption with Last-Event-ID"
                else
                    print_failure "Stream resumption with Last-Event-ID" "No reconnected event found"
                fi
            else
                print_failure "Stream resumption with Last-Event-ID" "Resume request failed"
            fi
        else
            print_info "Event IDs not found - resumability may be disabled"
        fi
    else
        print_failure "Event ID generation" "SSE stream request failed"
    fi
}

test_protocol_validation() {
    print_header "PROTOCOL VALIDATION TESTS"
    
    # Invalid Accept header for POST
    run_test "Invalid Accept Header (POST)" "200" '"code":406' \
        -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: text/plain" \
        -d "$(initialize_request)"
    
    # Invalid Content-Type for POST
    run_test "Invalid Content-Type (POST)" "200" '"code":415' \
        -X POST "$BASE_URL" \
        -H "Content-Type: text/plain" \
        -H "Accept: application/json, text/event-stream" \
        -d "$(initialize_request)"
    
    # Invalid Accept header for GET (in stateful mode)
    run_test "Invalid Accept Header (GET)" "200" '"code":406' \
        -X GET "$BASE_URL" \
        -H "Accept: application/json" \
        --max-time 5
    
    # Invalid JSON-RPC method
    run_test "Invalid Method" "200" '"code":-32601' \
        -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d "$(invalid_request)"
    
    # Malformed JSON
    run_test "Malformed JSON" "200" '"code":-32700' \
        -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d '{"invalid json"}'
}

test_authentication() {
    print_header "AUTHENTICATION TESTS"
    
    # Tools call without auth should fail
    run_test "Tools Call (no auth)" "200" '"code":-32602' \
        -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d "$(tools_call_request)"
    
    # Tools call with invalid auth should fail
    run_test "Tools Call (invalid auth)" "200" '"code":-32602' \
        -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -H "Authorization: Bearer invalid-key" \
        -d "$(tools_call_request)"
    
    # Tools call with valid auth should work
    run_test "Tools Call (valid auth)" "200" '"content"' \
        -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -H "Authorization: Bearer $API_KEY" \
        -d "$(tools_call_request)"
}

# Helper function to change server configuration
change_server_config() {
    local stateless_mode="$1"
    local json_response_mode="$2" 
    local enable_resumability="$3"
    
    print_info "Changing server config: stateless=$stateless_mode, json_response=$json_response_mode, resumability=$enable_resumability"
    print_info "Please update the MCP Server configuration in Odoo UI and press Enter to continue..."
    print_info "Go to: LLM → Configuration → MCP Server"
    print_info "Set: Stateless Mode = $stateless_mode"
    print_info "Set: JSON Response Mode = $json_response_mode"
    print_info "Set: Enable Resumability = $enable_resumability"
    read -r
}

print_summary() {
    print_header "TEST SUMMARY"
    echo -e "Total Tests: $TOTAL_TESTS"
    echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
    echo -e "${RED}Failed: $FAILED_TESTS${NC}"
    
    if [[ $FAILED_TESTS -gt 0 ]]; then
        echo -e "\n${RED}Failed Tests:${NC}"
        for test_name in "${FAILED_TEST_NAMES[@]}"; do
            echo -e "${RED}  - $test_name${NC}"
        done
        echo
        exit 1
    else
        echo -e "\n${GREEN}🎉 All tests passed!${NC}\n"
        exit 0
    fi
}

# Main test execution
main() {
    print_header "MCP SERVER COMPREHENSIVE TEST SUITE"
    print_info "Testing against: $BASE_URL"
    print_info "Using API Key: ${API_KEY:0:10}..."
    
    # Always test health endpoint
    test_health_endpoint
    
    # Test protocol validation (works in any mode)
    test_protocol_validation
    
    # Test authentication (works in any mode) 
    test_authentication
    
    echo -e "\n${YELLOW}Now testing different server modes...${NC}"
    echo -e "${YELLOW}You'll need to change the server configuration between tests.${NC}\n"
    
    # Mode 1: Stateless + JSON
    change_server_config "True" "True" "False"
    test_stateless_json_mode
    
    # Mode 3: Stateful + JSON
    change_server_config "False" "True" "False"
    test_stateful_json_mode
    
    # Mode 4: Stateful + SSE
    change_server_config "False" "False" "True"
    test_stateful_sse_mode
    
    print_summary
}

# Check if curl is available
if ! command -v curl &> /dev/null; then
    echo -e "${RED}Error: curl is not installed${NC}"
    exit 1
fi

# Run main function
main "$@"