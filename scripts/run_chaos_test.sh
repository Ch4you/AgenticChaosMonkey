#!/bin/bash

###############################################################################
# Chaos Testing Runner Script
# 
# This script runs a complete chaos testing workflow:
# 1. Starts Mock Server
# 2. Starts Chaos Proxy with logging
# 3. Runs Travel Agent with test query
# 4. Generates Resilience Scorecard Report
#
# Usage: ./scripts/run_chaos_test.sh [options]
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
REPORT_DIR="$PROJECT_ROOT/reports"

MOCK_SERVER_PORT=8001
PROXY_PORT=8080
OLLAMA_PORT=11434

MOCK_PID=""
PROXY_PID=""

# Detect Python command (prefer conda python over system python3)
PYTHON_CMD="python3"
if command -v python &> /dev/null; then
    if python -c "import sys" 2>/dev/null; then
        # Check if it has our modules
        if python -c "import mitmproxy" 2>/dev/null || python -c "import fastapi" 2>/dev/null; then
            PYTHON_CMD="python"
        fi
    fi
fi

# Generate a future date for testing (next December 25th)
# This ensures we don't try to book flights in the past
CURRENT_YEAR=$(date +%Y)
CURRENT_MONTH=$(date +%m)
CURRENT_DAY=$(date +%d)

# Check if December 25th has already passed this year
if [ "$CURRENT_MONTH" -gt "12" ] || ([ "$CURRENT_MONTH" -eq "12" ] && [ "$CURRENT_DAY" -gt "25" ]); then
    # Already past December 25th this year, use next year
    TARGET_YEAR=$((CURRENT_YEAR + 1))
else
    # December 25th hasn't passed yet this year, use this year
    TARGET_YEAR=$CURRENT_YEAR
fi
FUTURE_DATE="$TARGET_YEAR-12-25"

# Default test query with explicit future date
TEST_QUERY="Book a flight from New York to Los Angeles on December 25th, $TARGET_YEAR"
MODEL="llama3.2"

# Parse arguments
SKIP_MOCK=false
SKIP_PROXY=false
NO_CLEANUP=false
QUERY=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-mock)
            SKIP_MOCK=true
            shift
            ;;
        --skip-proxy)
            SKIP_PROXY=true
            shift
            ;;
        --no-cleanup)
            NO_CLEANUP=true
            shift
            ;;
        --query)
            QUERY="$2"
            shift 2
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --skip-mock       Skip starting mock server (assume it's running)"
            echo "  --skip-proxy      Skip starting chaos proxy (assume it's running)"
            echo "  --no-cleanup      Don't cleanup processes on exit"
            echo "  --query TEXT      Test query for the agent (default: flight booking query)"
            echo "  --model NAME      Ollama model name (default: llama3.2)"
            echo "  --help            Show this help message"
            echo ""
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Use custom query if provided
if [ -n "$QUERY" ]; then
    TEST_QUERY="$QUERY"
fi

###############################################################################
# Helper Functions
###############################################################################

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Cleanup function
cleanup() {
    if [ "$NO_CLEANUP" = false ]; then
        print_info "Cleaning up processes..."
        
        if [ -n "$MOCK_PID" ]; then
            kill $MOCK_PID 2>/dev/null || true
            print_info "Stopped Mock Server (PID: $MOCK_PID)"
        fi
        
        if [ -n "$PROXY_PID" ]; then
            kill $PROXY_PID 2>/dev/null || true
            print_info "Stopped Chaos Proxy (PID: $PROXY_PID)"
        fi
    fi
}

# Set trap for cleanup on exit
trap cleanup EXIT INT TERM

# Check if command exists
check_command() {
    if ! command -v $1 &> /dev/null; then
        print_error "$1 is not installed or not in PATH"
        return 1
    fi
    return 0
}

# Check if port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Wait for service to be ready
wait_for_service() {
    local url=$1
    local name=$2
    local max_attempts=30
    local attempt=0
    
    print_info "Waiting for $name to be ready..."
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            print_success "$name is ready"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    
    print_error "$name failed to start after ${max_attempts}s"
    return 1
}

###############################################################################
# Prerequisites Check
###############################################################################

print_header "Checking Prerequisites"

# Check Python
if ! check_command python3; then
    print_error "Python 3 is required"
    exit 1
fi

# Check Ollama
if ! check_command ollama; then
    print_warning "Ollama not found. Make sure Ollama is running."
else
    print_success "Ollama found"
fi

# Check if Ollama is running
if check_port $OLLAMA_PORT; then
    print_success "Ollama is running on port $OLLAMA_PORT"
else
    print_warning "Ollama doesn't seem to be running on port $OLLAMA_PORT"
    print_info "Please start Ollama: ollama serve"
fi

# Check mitmproxy
if ! check_command mitmdump; then
    print_error "mitmproxy is required. Install with: pip install mitmproxy"
    exit 1
fi

print_success "All prerequisites checked"

###############################################################################
# Setup Directories
###############################################################################

print_header "Setting Up Directories"

mkdir -p "$LOG_DIR"
mkdir -p "$REPORT_DIR"

# Clear previous log files to avoid accumulation
# This ensures each test run starts with fresh logs
if [ -f "$LOG_DIR/proxy.log" ]; then
    > "$LOG_DIR/proxy.log"  # Truncate to zero size
    print_info "Cleared previous proxy.log"
fi
if [ -f "$LOG_DIR/agent_output.log" ]; then
    > "$LOG_DIR/agent_output.log"  # Truncate to zero size
    print_info "Cleared previous agent_output.log"
fi

print_success "Created directories: $LOG_DIR, $REPORT_DIR"

###############################################################################
# Start Mock Server
###############################################################################

if [ "$SKIP_MOCK" = false ]; then
    print_header "Starting Mock Server"
    
    # Check if port is already in use
    if check_port $MOCK_SERVER_PORT; then
        print_warning "Port $MOCK_SERVER_PORT is already in use"
        print_info "Assuming Mock Server is already running. Use --skip-mock to skip this check."
    else
        cd "$PROJECT_ROOT"
        $PYTHON_CMD src/tools/mock_server.py > "$LOG_DIR/mock_server.log" 2>&1 &
        MOCK_PID=$!
        
        print_info "Started Mock Server (PID: $MOCK_PID) using $PYTHON_CMD"
        print_info "Logs: $LOG_DIR/mock_server.log"
        
        # Wait for mock server to be ready (give it more time)
        sleep 3
        if wait_for_service "http://localhost:$MOCK_SERVER_PORT/health" "Mock Server"; then
            print_success "Mock Server is ready"
        else
            print_error "Mock Server failed to start"
            print_info "Check logs: $LOG_DIR/mock_server.log"
            # Show last few lines of log for debugging
            if [ -f "$LOG_DIR/mock_server.log" ]; then
                print_info "Last 10 lines of mock_server.log:"
                tail -10 "$LOG_DIR/mock_server.log" | sed 's/^/  /'
            fi
            exit 1
        fi
    fi
else
    print_info "Skipping Mock Server startup (--skip-mock)"
fi

###############################################################################
# Start Chaos Proxy
###############################################################################

if [ "$SKIP_PROXY" = false ]; then
    print_header "Starting Chaos Proxy"
    
    # Check if port is already in use
    if check_port $PROXY_PORT; then
        print_warning "Port $PROXY_PORT is already in use"
        print_info "Assuming Chaos Proxy is already running. Use --skip-proxy to skip this check."
    else
        cd "$PROJECT_ROOT"
        
        # Set environment variables
        export PROXY_LOG_FILE="$LOG_DIR/proxy.log"
        
        # Start proxy with logging
        mitmdump -s agent_chaos_sdk/proxy/addon.py \
            --listen-port $PROXY_PORT \
            > "$LOG_DIR/proxy_stdout.log" 2>&1 &
        PROXY_PID=$!
        
        print_info "Started Chaos Proxy (PID: $PROXY_PID)"
        print_info "Proxy logs: $LOG_DIR/proxy.log"
        print_info "Proxy stdout: $LOG_DIR/proxy_stdout.log"
        
        # Wait for proxy to be ready
        sleep 2
        print_success "Chaos Proxy is ready"
    fi
else
    print_info "Skipping Chaos Proxy startup (--skip-proxy)"
fi

###############################################################################
# Run Travel Agent Test
###############################################################################

print_header "Running Travel Agent Test"

cd "$PROJECT_ROOT"

# Set proxy environment variables
# Clear NO_PROXY to force localhost traffic through proxy
export NO_PROXY=""
export no_proxy=""
export HTTP_PROXY="http://localhost:$PROXY_PORT"
export HTTPS_PROXY="http://localhost:$PROXY_PORT"

print_info "Test Query: $TEST_QUERY"
print_info "Target Date: $FUTURE_DATE (ensures future date, not past)"
print_info "Model: $MODEL"
print_info "Using proxy: $HTTP_PROXY"

# Run the agent
$PYTHON_CMD examples/production_simulation/travel_agent.py \
    --query "$TEST_QUERY" \
    --model "$MODEL" \
    > "$LOG_DIR/agent_output.log" 2>&1

AGENT_EXIT_CODE=$?

if [ $AGENT_EXIT_CODE -eq 0 ]; then
    print_success "Travel Agent completed successfully"
else
    print_warning "Travel Agent exited with code $AGENT_EXIT_CODE"
    print_info "Check logs: $LOG_DIR/agent_output.log"
    if [ -f "$LOG_DIR/agent_output.log" ]; then
        print_info "Last 20 lines of agent output:"
        tail -20 "$LOG_DIR/agent_output.log" | sed 's/^/  /'
    fi
fi

# Wait a bit for all logs to be written
sleep 2

###############################################################################
# Generate Resilience Report
###############################################################################

print_header "Generating Resilience Report"

cd "$PROJECT_ROOT"

# Check if log file exists
LOG_FILE="$LOG_DIR/proxy.log"
if [ ! -f "$LOG_FILE" ]; then
    print_warning "Proxy log file not found: $LOG_FILE"
    print_info "Trying to find alternative log files..."
    
    # Try to find any log file
    if [ -f "$LOG_DIR/proxy_stdout.log" ]; then
        LOG_FILE="$LOG_DIR/proxy_stdout.log"
        print_info "Using: $LOG_FILE"
    else
        print_error "No log files found. Cannot generate report."
        print_info "Available log files:"
        ls -lh "$LOG_DIR/" 2>/dev/null || true
        exit 1
    fi
fi

# Generate reports
$PYTHON_CMD src/reporter/generate.py \
    --log-file "$LOG_FILE" \
    --output-dir "$REPORT_DIR"

if [ $? -eq 0 ]; then
    print_success "Report generated successfully"
    print_info "JSON Report: $REPORT_DIR/resilience_report.json"
    print_info "Markdown Report: $REPORT_DIR/resilience_report.md"
else
    print_error "Failed to generate report"
    exit 1
fi

###############################################################################
# Summary
###############################################################################

print_header "Test Complete!"

echo ""
print_success "All steps completed successfully"
echo ""
print_info "Logs:"
echo "  - Mock Server: $LOG_DIR/mock_server.log"
echo "  - Proxy: $LOG_DIR/proxy.log"
echo "  - Agent: $LOG_DIR/agent_output.log"
echo ""
print_info "Reports:"
echo "  - JSON: $REPORT_DIR/resilience_report.json"
echo "  - Markdown: $REPORT_DIR/resilience_report.md"
echo ""

# Display report summary if available
if [ -f "$REPORT_DIR/resilience_report.md" ]; then
    print_info "Report Summary:"
    echo ""
    head -n 30 "$REPORT_DIR/resilience_report.md" | grep -E "^(##|Grade:|Resilience|System)" || true
    echo ""
fi

print_info "View full report: cat $REPORT_DIR/resilience_report.md"
print_info "View JSON report: cat $REPORT_DIR/resilience_report.json"
echo ""

