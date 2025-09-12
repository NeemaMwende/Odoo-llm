#!/bin/bash

# MCP Server Resumability Testing
# Tests event storage, replay, and resumption functionality

set -e

# Configuration
BASE_URL="${MCP_BASE_URL:-http://localhost:8069/mcp}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}\n"
}

print_test() {
    echo -e "${YELLOW}Testing: $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ PASS: $1${NC}"
}

print_failure() {
    echo -e "${RED}❌ FAIL: $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Extract event ID from SSE stream
extract_event_id() {
    local sse_output="$1"
    echo "$sse_output" | grep "^id: " | head -1 | cut -d' ' -f2 | tr -d '\r'
}

# Extract all event IDs from SSE stream
extract_all_event_ids() {
    local sse_output="$1"
    echo "$sse_output" | grep "^id: " | cut -d' ' -f2 | tr -d '\r'
}

test_basic_sse_with_event_ids() {
    print_test "Basic SSE stream generates event IDs"
    
    local output
    if output=$(curl -s --max-time 10 -X GET "$BASE_URL" -H "Accept: text/event-stream" 2>/dev/null); then
        local event_ids
        event_ids=$(extract_all_event_ids "$output")
        local id_count
        id_count=$(echo "$event_ids" | wc -l | tr -d ' ')
        
        if [[ $id_count -gt 0 ]]; then
            print_success "Generated $id_count event IDs"
            echo "First Event ID: $(echo "$event_ids" | head -1)"
            echo "Sample events with IDs:"
            echo "$output" | head -15
            return 0
        else
            print_failure "No event IDs found in SSE stream"
            echo "Output: ${output:0:200}..."
            return 1
        fi
    else
        print_failure "Failed to get SSE stream"
        return 1
    fi
}

test_resumption_with_last_event_id() {
    print_test "Stream resumption with Last-Event-ID"
    
    # First, get a complete stream and extract an event ID
    print_info "Getting initial stream to extract event ID..."
    local initial_stream
    if initial_stream=$(curl -s --max-time 10 -X GET "$BASE_URL" -H "Accept: text/event-stream" 2>/dev/null); then
        local first_event_id
        first_event_id=$(extract_event_id "$initial_stream")
        
        if [[ -n "$first_event_id" ]]; then
            print_info "Extracted event ID: $first_event_id"
            
            # Now try to resume from that event ID
            print_info "Attempting to resume from event ID: $first_event_id"
            local resumed_stream
            if resumed_stream=$(curl -s --max-time 10 -X GET "$BASE_URL" \
                -H "Accept: text/event-stream" \
                -H "Last-Event-ID: $first_event_id" 2>/dev/null); then
                
                if [[ "$resumed_stream" == *"reconnected"* ]]; then
                    print_success "Stream resumed with reconnection event"
                    echo "Resumed stream preview:"
                    echo "$resumed_stream" | head -10
                    return 0
                else
                    print_failure "No reconnection event found in resumed stream"
                    echo "Resumed stream: ${resumed_stream:0:200}..."
                    return 1
                fi
            else
                print_failure "Failed to resume stream"
                return 1
            fi
        else
            print_failure "No event ID found in initial stream"
            echo "Initial stream: ${initial_stream:0:200}..."
            return 1
        fi
    else
        print_failure "Failed to get initial stream"
        return 1
    fi
}

test_invalid_last_event_id() {
    print_test "Invalid Last-Event-ID handling"
    
    local output
    if output=$(curl -s --max-time 10 -X GET "$BASE_URL" \
        -H "Accept: text/event-stream" \
        -H "Last-Event-ID: invalid-event-id-123" 2>/dev/null); then
        
        if [[ "$output" == *"reconnected"* ]] || [[ "$output" == *"connected"* ]]; then
            print_success "Server handles invalid event ID gracefully"
            echo "Response type: $(echo "$output" | grep "event:" | head -1)"
        else
            print_failure "Unexpected response to invalid event ID"
            echo "Output: ${output:0:200}..."
        fi
    else
        print_failure "Request with invalid event ID failed"
    fi
}

test_event_id_format() {
    print_test "Event ID format validation"
    
    local output
    if output=$(curl -s --max-time 10 -X GET "$BASE_URL" -H "Accept: text/event-stream" 2>/dev/null); then
        local event_ids
        event_ids=$(extract_all_event_ids "$output")
        
        local valid_format=true
        local sample_ids=""
        
        while IFS= read -r event_id; do
            if [[ -n "$event_id" ]]; then
                sample_ids="$sample_ids$event_id "
                # Check if it looks like a UUID (basic check)
                if [[ ! "$event_id" =~ ^[a-f0-9-]{36}$ ]] && [[ ${#event_id} -lt 8 ]]; then
                    valid_format=false
                fi
            fi
        done <<< "$event_ids"
        
        if [[ "$valid_format" == true ]]; then
            print_success "Event IDs have valid format"
            echo "Sample IDs: $sample_ids"
        else
            print_failure "Some event IDs have invalid format"
            echo "Sample IDs: $sample_ids"
        fi
    else
        print_failure "Failed to get stream for ID format check"
    fi
}

test_event_uniqueness() {
    print_test "Event ID uniqueness"
    
    local output
    if output=$(curl -s --max-time 10 -X GET "$BASE_URL" -H "Accept: text/event-stream" 2>/dev/null); then
        local event_ids
        event_ids=$(extract_all_event_ids "$output")
        
        local unique_count
        local total_count
        unique_count=$(echo "$event_ids" | sort | uniq | wc -l | tr -d ' ')
        total_count=$(echo "$event_ids" | wc -l | tr -d ' ')
        
        if [[ "$unique_count" -eq "$total_count" ]]; then
            print_success "All $total_count event IDs are unique"
        else
            print_failure "Found duplicate event IDs: $unique_count unique out of $total_count total"
        fi
    else
        print_failure "Failed to get stream for uniqueness check"
    fi
}

test_session_persistence() {
    print_test "Session persistence across requests"
    
    # Make first request and get session ID from response
    local first_response
    if first_response=$(curl -s -X POST "$BASE_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"protocolVersion":"2025-06-18","clientInfo":{"name":"test","version":"1.0"}}}' 2>/dev/null); then
        
        local session_id
        session_id=$(echo "$first_response" | grep -o '"sessionId":"[^"]*"' | cut -d'"' -f4)
        
        if [[ -n "$session_id" ]]; then
            print_info "Got session ID: ${session_id:0:20}..."
            
            # Now test if SSE stream uses the same session concept
            local sse_output
            if sse_output=$(curl -s --max-time 5 -X GET "$BASE_URL" \
                -H "Accept: text/event-stream" \
                -H "X-MCP-Session-ID: $session_id" 2>/dev/null); then
                
                if [[ "$sse_output" == *"connected"* ]] || [[ "$sse_output" == *"ping"* ]]; then
                    print_success "SSE stream works with session context"
                else
                    print_failure "SSE stream doesn't work with session"
                fi
            else
                print_failure "Failed to test SSE with session ID"
            fi
        else
            print_failure "No session ID found in initialize response"
            echo "Response: ${first_response:0:200}..."
        fi
    else
        print_failure "Failed to initialize session"
    fi
}

detect_resumability_mode() {
    print_header "DETECTING RESUMABILITY MODE"
    
    # Quick check if resumability is enabled by looking for event IDs
    local output
    if output=$(curl -s --max-time 5 -X GET "$BASE_URL" -H "Accept: text/event-stream" 2>/dev/null); then
        if [[ "$output" == *"id: "* ]]; then
            print_info "✅ Resumability appears to be ENABLED (event IDs found)"
            return 0
        else
            print_info "❌ Resumability appears to be DISABLED (no event IDs found)"
            return 1
        fi
    else
        print_info "❓ Cannot detect resumability mode (GET request failed)"
        return 2
    fi
}

main() {
    print_header "MCP SERVER RESUMABILITY TEST SUITE"
    print_info "Testing against: $BASE_URL"
    
    # Detect current mode
    local resumability_enabled=false
    if detect_resumability_mode; then
        resumability_enabled=true
    fi
    
    if [[ "$resumability_enabled" == true ]]; then
        print_header "RESUMABILITY TESTS (ENABLED MODE)"
        
        test_basic_sse_with_event_ids
        echo
        test_event_id_format
        echo
        test_event_uniqueness
        echo
        test_resumption_with_last_event_id
        echo
        test_invalid_last_event_id
        echo
        test_session_persistence
        
    else
        print_header "RESUMABILITY TESTS (DISABLED MODE)"
        print_info "Resumability is disabled - testing basic SSE without event IDs"
        
        print_test "SSE stream without resumability"
        local output
        if output=$(curl -s --max-time 5 -X GET "$BASE_URL" -H "Accept: text/event-stream" 2>/dev/null); then
            if [[ "$output" == *"event:"* ]] && [[ "$output" != *"id: "* ]]; then
                print_success "SSE stream works without event IDs (resumability disabled)"
            else
                print_failure "Unexpected SSE format"
                echo "Output: ${output:0:200}..."
            fi
        else
            print_failure "SSE stream failed"
        fi
        
        print_info "To test full resumability, enable it in server config:"
        print_info "Go to: LLM → Configuration → MCP Server"
        print_info "Set: Enable Resumability = True"
    fi
    
    print_header "RESUMABILITY TEST COMPLETED"
}

# Check prerequisites
if ! command -v curl &> /dev/null; then
    echo -e "${RED}Error: curl is not installed${NC}"
    exit 1
fi

main "$@"