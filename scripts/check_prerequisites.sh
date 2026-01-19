#!/bin/bash

###############################################################################
# Prerequisites Check Script
# 
# This script checks if all prerequisites are met before running chaos tests.
#
# Usage: ./scripts/check_prerequisites.sh
###############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

check_command() {
    if command -v $1 &> /dev/null; then
        print_success "$1 is installed"
        return 0
    else
        print_error "$1 is not installed"
        return 1
    fi
}

check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        return 0
    else
        return 1
    fi
}


print_header "Checking Prerequisites"

ERRORS=0
WARNINGS=0

# Check Python
echo "1. Checking Python..."
if check_command python3; then
    PYTHON_VERSION=$(python3 --version)
    print_info "  Version: $PYTHON_VERSION"
else
    ((ERRORS++))
fi

# Check Python modules
echo ""
echo "2. Checking Python modules..."

# Try to find the correct Python interpreter (prefer conda python over system python3)
PYTHON_CMD="python3"
if command -v python &> /dev/null; then
    # Check if 'python' has our modules (likely conda environment)
    if python -c "import sys" 2>/dev/null; then
        # Test if it can import one of our key modules
        if python -c "import mitmproxy" 2>/dev/null || python -c "import httpx" 2>/dev/null; then
            PYTHON_CMD="python"
        fi
    fi
fi

print_info "Using Python: $($PYTHON_CMD --version 2>&1 | head -1)"
print_info "Python path: $($PYTHON_CMD -c 'import sys; print(sys.executable)' 2>&1)"

# Check modules (module_name:import_name pairs)
check_module_pair() {
    local module_name=$1
    local import_name=$2
    
    if [ "$module_name" = "langchain_ollama" ]; then
        # Special check for langchain_ollama
        if $PYTHON_CMD -c "from langchain_ollama import ChatOllama" 2>/dev/null; then
            print_success "Python module 'langchain_ollama' is installed"
            return 0
        else
            print_error "Python module 'langchain_ollama' is not installed"
            return 1
        fi
    else
        if $PYTHON_CMD -c "import $import_name" 2>/dev/null; then
            print_success "Python module '$module_name' is installed"
            return 0
        else
            print_error "Python module '$module_name' is not installed"
            return 1
        fi
    fi
}

# Check each module (using parallel arrays to avoid associative arrays)
check_module_pair "mitmproxy" "mitmproxy" || ((ERRORS++))
check_module_pair "httpx" "httpx" || ((ERRORS++))
check_module_pair "langchain" "langchain" || ((ERRORS++))
check_module_pair "fastapi" "fastapi" || ((ERRORS++))
check_module_pair "uvicorn" "uvicorn" || ((ERRORS++))
check_module_pair "pydantic" "pydantic" || ((ERRORS++))
check_module_pair "pyyaml" "yaml" || ((ERRORS++))
check_module_pair "langchain_ollama" "" || ((ERRORS++))

# Check Ollama
echo ""
echo "3. Checking Ollama..."
if check_command ollama; then
    if check_port 11434; then
        print_success "Ollama service is running on port 11434"
        
        # Check if model is available
        if ollama list 2>/dev/null | grep -q "llama3.2"; then
            print_success "Model 'llama3.2' is available"
        else
            print_warning "Model 'llama3.2' is not available. Run: ollama pull llama3.2"
            ((WARNINGS++))
        fi
    else
        print_warning "Ollama is installed but not running. Start with: ollama serve"
        ((WARNINGS++))
    fi
else
    print_error "Ollama is not installed"
    ((ERRORS++))
fi

# Check mitmproxy
echo ""
echo "4. Checking mitmproxy..."
if check_command mitmdump; then
    MITM_VERSION=$(mitmdump --version 2>&1 | head -n 1)
    print_info "  Version: $MITM_VERSION"
else
    print_error "mitmproxy is not installed. Install with: pip install mitmproxy"
    ((ERRORS++))
fi

# Check ports
echo ""
echo "5. Checking ports..."
PORTS=("8001:Mock Server" "8080:Chaos Proxy" "11434:Ollama")
for port_info in "${PORTS[@]}"; do
    IFS=':' read -r port name <<< "$port_info"
    if check_port $port; then
        print_warning "Port $port ($name) is already in use"
        print_info "  You may need to stop the service or use --skip flags"
        ((WARNINGS++))
    else
        print_success "Port $port ($name) is available"
    fi
done

# Check project structure
echo ""
echo "6. Checking project structure..."
REQUIRED_DIRS=("scripts" "src" "examples" "config")
for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        print_success "Directory '$dir' exists"
    else
        print_error "Directory '$dir' is missing"
        ((ERRORS++))
    fi
done

REQUIRED_FILES=("scripts/run_chaos_test.sh" "src/tools/mock_server.py" "examples/production_simulation/travel_agent.py" "config/chaos_config.yaml")
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        print_success "File '$file' exists"
    else
        print_error "File '$file' is missing"
        ((ERRORS++))
    fi
done

# Check script permissions
echo ""
echo "7. Checking script permissions..."
if [ -x "scripts/run_chaos_test.sh" ]; then
    print_success "Script 'scripts/run_chaos_test.sh' is executable"
else
    print_warning "Script 'scripts/run_chaos_test.sh' is not executable"
    print_info "  Fix with: chmod +x scripts/run_chaos_test.sh"
    ((WARNINGS++))
fi

# Summary
echo ""
print_header "Summary"

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    print_success "All checks passed! You're ready to run the chaos test."
    echo ""
    print_info "Run: ./scripts/run_chaos_test.sh"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    print_warning "All critical checks passed, but there are $WARNINGS warning(s)"
    echo ""
    print_info "You can proceed, but review the warnings above."
    print_info "Run: ./scripts/run_chaos_test.sh"
    exit 0
else
    print_error "Found $ERRORS error(s) and $WARNINGS warning(s)"
    echo ""
    print_info "Please fix the errors before running the chaos test."
    print_info "See scripts/PREPARE.md for detailed setup instructions."
    exit 1
fi

