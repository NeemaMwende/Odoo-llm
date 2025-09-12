#!/bin/bash

# MCP Server Test Suite Runner
# Runs all test scripts and provides comprehensive reporting

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

print_banner() {
    echo -e "${CYAN}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                    MCP SERVER TEST SUITE                       ║"
    echo "║                 Comprehensive Test Runner                      ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_header() {
    echo -e "\n${BLUE}═══ $1 ═══${NC}\n"
}

print_test_section() {
    echo -e "\n${YELLOW}🧪 $1${NC}"
    echo -e "${YELLOW}$(printf '═%.0s' {1..60})${NC}"
}

run_test_script() {
    local script_name="$1"
    local description="$2"
    local script_path="$SCRIPT_DIR/$script_name"
    
    if [[ ! -f "$script_path" ]]; then
        echo -e "${RED}❌ Script not found: $script_name${NC}"
        return 1
    fi
    
    echo -e "\n${CYAN}Running: $script_name${NC}"
    echo -e "${BLUE}Description: $description${NC}"
    echo -e "${YELLOW}$(printf '─%.0s' {1..60})${NC}"
    
    if "$script_path"; then
        echo -e "${GREEN}✅ $script_name completed successfully${NC}"
        return 0
    else
        echo -e "${RED}❌ $script_name failed${NC}"
        return 1
    fi
}

show_help() {
    echo -e "${BLUE}MCP Server Test Suite Usage:${NC}"
    echo ""
    echo -e "${YELLOW}Available Commands:${NC}"
    echo "  ./run_all_tests.sh quick          - Run quick smoke test"
    echo "  ./run_all_tests.sh current        - Test current server configuration"
    echo "  ./run_all_tests.sh current-full   - Full test suite for current configuration"
    echo "  ./run_all_tests.sh mode1          - Test Mode 1: Stateless + JSON"
    echo "  ./run_all_tests.sh mode3          - Test Mode 3: Stateful + JSON" 
    echo "  ./run_all_tests.sh mode4          - Test Mode 4: Stateful + SSE"
    echo "  ./run_all_tests.sh resumability   - Test resumability features"
    echo "  ./run_all_tests.sh comprehensive  - Run comprehensive test suite (requires config changes)"
    echo ""
    echo -e "${YELLOW}Environment Variables:${NC}"
    echo "  MCP_API_KEY    - API key for authenticated requests"
    echo "  MCP_BASE_URL   - Base URL for MCP server (default: http://localhost:8069/mcp)"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo "  MCP_API_KEY=your-key ./run_all_tests.sh current"
    echo "  MCP_BASE_URL=http://remote:8069/mcp ./run_all_tests.sh quick"
    echo ""
}

print_banner

case "${1:-help}" in
    "quick")
        print_test_section "QUICK SMOKE TEST"
        run_test_script "test_mcp_current_mode.sh" "Quick smoke test for current configuration"
        ;;
        
    "current")
        print_test_section "CURRENT CONFIGURATION TEST"
        run_test_script "test_mcp_current_mode.sh" "Test current server configuration"
        ;;
        
    "mode1")
        print_test_section "MODE 1: STATELESS + JSON"
        echo -e "${BLUE}ℹ️  Ensure server is configured with:${NC}"
        echo -e "${BLUE}   - Stateless Mode = True${NC}"
        echo -e "${BLUE}   - JSON Response Mode = True${NC}"
        read -p "Press Enter when ready..."
        run_test_script "test_mode1_stateless_json.sh" "Test Stateless + JSON mode"
        ;;
        
    "mode3")
        print_test_section "MODE 3: STATEFUL + JSON"
        echo -e "${BLUE}ℹ️  Ensure server is configured with:${NC}"
        echo -e "${BLUE}   - Stateless Mode = False${NC}"
        echo -e "${BLUE}   - JSON Response Mode = True${NC}"
        read -p "Press Enter when ready..."
        run_test_script "test_mode3_stateful_json.sh" "Test Stateful + JSON mode"
        ;;
        
    "mode4")
        print_test_section "MODE 4: STATEFUL + SSE"
        echo -e "${BLUE}ℹ️  Ensure server is configured with:${NC}"
        echo -e "${BLUE}   - Stateless Mode = False${NC}"
        echo -e "${BLUE}   - JSON Response Mode = False${NC}"
        echo -e "${BLUE}   - Enable Resumability = True (recommended)${NC}"
        read -p "Press Enter when ready..."
        run_test_script "test_mode4_stateful_sse.sh" "Test Stateful + SSE mode"
        ;;
        
    "resumability")
        print_test_section "RESUMABILITY FEATURES"
        run_test_script "test_resumability.sh" "Test resumability and event replay features"
        ;;
        
    "comprehensive")
        print_test_section "COMPREHENSIVE TEST SUITE"
        echo -e "${BLUE}ℹ️  This will run all mode-specific tests sequentially${NC}"
        echo -e "${BLUE}ℹ️  You'll need to change server configuration between modes${NC}"
        read -p "Press Enter to continue..."
        
        failed_tests=0
        total_tests=0
        
        # Run each mode test
        for mode in mode1 mode3 mode4; do
            echo -e "${BLUE}ℹ️  Please configure server for $mode before continuing${NC}"
            read -p "Press Enter when server is configured for $mode..."
            total_tests=$((total_tests + 1))
            case $mode in
                "mode1") run_test_script "test_mode1_stateless_json.sh" "Mode 1 test" || failed_tests=$((failed_tests + 1)) ;;
                "mode3") run_test_script "test_mode3_stateful_json.sh" "Mode 3 test" || failed_tests=$((failed_tests + 1)) ;;
                "mode4") run_test_script "test_mode4_stateful_sse.sh" "Mode 4 test" || failed_tests=$((failed_tests + 1)) ;;
            esac
        done
        
        # Summary
        echo -e "${BLUE}ℹ️  Comprehensive Test Results:${NC}"
        echo -e "Total Mode Tests: $total_tests"
        echo -e "${GREEN}Successful: $((total_tests - failed_tests))${NC}"
        echo -e "${RED}Failed: $failed_tests${NC}"
        
        if [[ $failed_tests -eq 0 ]]; then
            echo -e "${GREEN}🎉 All comprehensive tests passed!${NC}"
        else
            echo -e "${RED}❌ Some comprehensive tests failed${NC}"
            exit 1
        fi
        ;;
        
    "current-full")
        print_header "FULL TEST FOR CURRENT CONFIGURATION"
        
        failed_tests=0
        total_tests=0
        
        # Quick test
        print_test_section "1. QUICK SMOKE TEST"
        total_tests=$((total_tests + 1))
        run_test_script "test_mcp_current_mode.sh" "Quick smoke test" || failed_tests=$((failed_tests + 1))
        
        # Resumability test
        print_test_section "2. RESUMABILITY TEST"
        total_tests=$((total_tests + 1))
        run_test_script "test_resumability.sh" "Resumability features" || failed_tests=$((failed_tests + 1))
        
        # Mode-specific test
        print_test_section "3. MODE-SPECIFIC TEST"
        total_tests=$((total_tests + 1))
        
        # Detect current mode and run appropriate test
        echo -e "${BLUE}ℹ️  Detecting current server mode...${NC}"
        mode_test=""
        sse_check=""
        if sse_check=$(curl -s --max-time 3 -X GET "${MCP_BASE_URL:-http://localhost:8069/mcp}" -H "Accept: text/event-stream" 2>/dev/null); then
            if [[ "$sse_check" == *"not supported in stateless mode"* ]]; then
                mode_test="test_mode1_stateless_json.sh"
                echo -e "${BLUE}ℹ️  Detected: Mode 1 (Stateless + JSON)${NC}"
            elif [[ "$sse_check" == *"event: connected"* ]]; then
                mode_test="test_mode4_stateful_sse.sh"
                echo -e "${BLUE}ℹ️  Detected: Mode 4 (Stateful + SSE)${NC}"
            else
                mode_test="test_mode3_stateful_json.sh"
                echo -e "${BLUE}ℹ️  Detected: Mode 3 (Stateful + JSON)${NC}"
            fi
            
            run_test_script "$mode_test" "Mode-specific test" || failed_tests=$((failed_tests + 1))
        else
            echo -e "${YELLOW}⚠️  Could not detect mode, running current config test${NC}"
            run_test_script "test_mcp_current_mode.sh" "Current configuration fallback" || failed_tests=$((failed_tests + 1))
        fi
        
        # Summary
        print_header "CURRENT CONFIGURATION TEST SUMMARY"
        echo -e "Total Test Suites: $total_tests"
        echo -e "${GREEN}Successful: $((total_tests - failed_tests))${NC}"
        echo -e "${RED}Failed: $failed_tests${NC}"
        
        if [[ $failed_tests -eq 0 ]]; then
            echo -e "\n${GREEN}🎉 All tests for current configuration passed!${NC}"
            exit 0
        else
            echo -e "\n${RED}❌ Some tests failed${NC}"
            exit 1
        fi
        ;;
        
    "help"|"--help"|"-h"|*)
        show_help
        ;;
esac

print_header "TEST COMPLETED"