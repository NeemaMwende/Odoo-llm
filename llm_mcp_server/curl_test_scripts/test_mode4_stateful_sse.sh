#!/bin/bash

# MCP Server Mode 4 Tests: Stateful + SSE Streaming
# Configuration: stateless_mode=False, json_response_mode=False, enable_resumability=True/False

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

# Detect resumability mode
detect_resumability() {
    local output
    if output=$(curl -s --max-time 5 -X GET "$BASE_URL" -H "Accept: text/event-stream" 2>/dev/null); then
        if [[ "$output" == *"id: "* ]]; then
            echo "enabled"
        else
            echo "disabled"  
        fi
    else
        echo "unknown"
    fi
}

test_resumability_features() {
    print_header "RESUMABILITY TESTS"
    
    local resumability_mode
    resumability_mode=$(detect_resumability)
    
    if [[ "$resumability_mode" == "enabled" ]]; then
        print_info "✅ Resumability is ENABLED"
        
        # Test event ID generation
        print_test "Event ID Generation"
        local stream_output
        if stream_output=$(curl -s --max-time 8 -X GET "$BASE_URL" -H "Accept: text/event-stream" 2>/dev/null); then
            if [[ "$stream_output" == *"id: "* ]]; then
                print_success
                local first_event_id
                first_event_id=$(echo "$stream_output" | grep "^id: " | head -1 | cut -d' ' -f2 | tr -d '\r')
                print_info "Sample Event ID: $first_event_id"
                
                # Test proper event replay with concurrent streams
                print_test "Event Replay (Concurrent Stream Test)"
                
                # Create temp files for stream capture
                local stream1_log=$(mktemp)
                local stream2_log=$(mktemp)
                
                # Start first stream in background and let it run partially
                print_info "Starting initial stream..."
                curl -s --max-time 4 -X GET "$BASE_URL" -H "Accept: text/event-stream" > "$stream1_log" 2>/dev/null &
                local stream1_pid=$!
                
                # Let it generate some events (connected + ping1 + ping2)
                sleep 2
                
                # Kill the first stream to simulate disconnection
                kill $stream1_pid 2>/dev/null || true
                wait $stream1_pid 2>/dev/null || true
                
                # Extract event IDs from the partial stream
                local event_ids
                event_ids=$(grep "^id: " "$stream1_log" | cut -d' ' -f2 | tr -d '\r')
                
                if [[ -n "$event_ids" ]]; then
                    # Get the second event ID (should be ping1 with id=1)
                    local middle_event_id
                    middle_event_id=$(echo "$event_ids" | sed -n '2p')
                    
                    if [[ -n "$middle_event_id" ]]; then
                        print_info "Resuming from Event ID: $middle_event_id"
                        
                        # Start new stream with Last-Event-ID to test replay
                        if curl -s --max-time 8 -X GET "$BASE_URL" \
                            -H "Accept: text/event-stream" \
                            -H "Last-Event-ID: $middle_event_id" > "$stream2_log" 2>/dev/null; then
                            
                            local resumed_content
                            resumed_content=$(cat "$stream2_log")
                            
                            # Verify replay functionality
                            local tests_passed=0
                            local total_checks=3
                            
                            # Check 1: Reconnected event present
                            if [[ "$resumed_content" == *"reconnected"* ]]; then
                                tests_passed=$((tests_passed + 1))
                                print_info "✓ Reconnection event found"
                            fi
                            
                            # Check 2: Resumed_from field contains our event ID
                            if [[ "$resumed_content" == *"resumed_from"* && "$resumed_content" == *"$middle_event_id"* ]]; then
                                tests_passed=$((tests_passed + 1))
                                print_info "✓ Resumed_from event ID verified"
                            fi
                            
                            # Check 3: Later events are replayed (ping with higher count OR type ping/close)
                            if [[ "$resumed_content" == *'"count":'* ]] || [[ "$resumed_content" == *'"type":"ping"'* ]] || [[ "$resumed_content" == *'"type":"stream_closed"'* ]]; then
                                tests_passed=$((tests_passed + 1))
                                print_info "✓ Later events replayed (found ping/close events)"
                            else
                                print_info "✗ No later events found in replay"
                                echo "Full resumed content:"
                                echo "$resumed_content"
                            fi
                            
                            if [[ $tests_passed -eq $total_checks ]]; then
                                print_success
                            else
                                print_failure "Replay verification failed ($tests_passed/$total_checks checks passed)"
                                echo "Resume content preview: ${resumed_content:0:200}..."
                            fi
                        else
                            print_failure "Resume request failed"
                        fi
                    else
                        print_failure "Could not extract middle event ID"
                    fi
                else
                    print_failure "No event IDs captured from initial stream"
                fi
                
                # Cleanup temp files
                rm -f "$stream1_log" "$stream2_log"
            else
                print_failure "No event IDs found"
            fi
        else
            print_failure "SSE stream request failed"
        fi
        
    elif [[ "$resumability_mode" == "disabled" ]]; then
        print_info "❌ Resumability is DISABLED"
        
        print_test "SSE without Event IDs"
        local stream_output
        if stream_output=$(curl -s --max-time 5 -X GET "$BASE_URL" -H "Accept: text/event-stream" 2>/dev/null); then
            if [[ "$stream_output" == *"event:"* ]] && [[ "$stream_output" != *"id: "* ]]; then
                print_success
            else
                print_failure "Unexpected SSE format"
            fi
        else
            print_failure "SSE stream failed"
        fi
    else
        print_info "❓ Cannot detect resumability mode"
    fi
}

print_header "MODE 4: STATEFUL + SSE STREAMING MODE TESTS"
print_info "Expected Configuration:"
print_info "  - stateless_mode = False"
print_info "  - json_response_mode = False"
print_info "  - enable_resumability = True/False"
print_info ""
print_info "Expected Behavior:"
print_info "  - POST requests work and return JSON"
print_info "  - GET requests work and return SSE streams"
print_info "  - DELETE requests work"
print_info "  - Resumability features depend on enable_resumability setting"

# POST requests should return JSON (even in SSE mode)
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
            "clientInfo": {"name": "mode4-test", "version": "1.0"}
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

# GET requests should return SSE streams
run_test "SSE Stream (GET)" "200" "event: connected" \
    -X GET "$BASE_URL" \
    -H "Accept: text/event-stream"

# DELETE requests should work
run_test "DELETE Request (session cleanup)" "204" "" \
    -X DELETE "$BASE_URL"

# Test resumability features
test_resumability_features

# Test multiple concurrent sessions
print_test "Concurrent Sessions Support"
session1_response=$(curl -s -X POST "$BASE_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"clientInfo":{"name":"session1"}}}' 2>/dev/null)
    
session2_response=$(curl -s -X POST "$BASE_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","method":"initialize","id":2,"params":{"clientInfo":{"name":"session2"}}}' 2>/dev/null)

if [[ "$session1_response" == *'"sessionId"'* ]] && [[ "$session2_response" == *'"sessionId"'* ]]; then
    session1_id=$(echo "$session1_response" | grep -o '"sessionId":"[^"]*"' | cut -d'"' -f4)
    session2_id=$(echo "$session2_response" | grep -o '"sessionId":"[^"]*"' | cut -d'"' -f4)
    
    if [[ "$session1_id" != "$session2_id" ]]; then
        print_success
        print_info "Session 1: ${session1_id:0:20}..."
        print_info "Session 2: ${session2_id:0:20}..."
    else
        print_failure "Sessions have same ID"
    fi
else
    print_failure "Failed to get session IDs"
fi

print_header "MODE 4 TEST SUMMARY"
echo -e "Total Tests: $TOTAL_TESTS"
echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
echo -e "${RED}Failed: $FAILED_TESTS${NC}"

if [[ $FAILED_TESTS -gt 0 ]]; then
    echo -e "\n${RED}❌ Some tests failed. Check server configuration:${NC}"
    echo -e "${RED}   - Go to: LLM → Configuration → MCP Server${NC}"
    echo -e "${RED}   - Set: Stateless Mode = False${NC}"
    echo -e "${RED}   - Set: JSON Response Mode = False${NC}"
    echo -e "${RED}   - Set: Enable Resumability = True (recommended)${NC}"
    exit 1
else
    echo -e "\n${GREEN}🎉 All Mode 4 tests passed!${NC}"
    echo -e "${GREEN}Server is correctly configured for Stateful + SSE mode${NC}"
    
    resumability_status=$(detect_resumability)
    case "$resumability_status" in
        "enabled")  echo -e "${GREEN}✅ Resumability is working${NC}" ;;
        "disabled") echo -e "${YELLOW}⚠️  Resumability is disabled${NC}" ;;
        *)          echo -e "${BLUE}ℹ️  Resumability status unclear${NC}" ;;
    esac
    exit 0
fi