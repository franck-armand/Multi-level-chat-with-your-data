#!/bin/bash
# Comprehensive test suite for ChatWithDocs
# Usage: ./test_system.sh [level]
# Levels: unit, integration, e2e, api, docker, all

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Level 1: Unit Tests
test_unit() {
    print_header "LEVEL 1: UNIT TESTS"
    print_info "Testing individual components..."
    
    uv run pytest tests/ -v --tb=short
    
    print_success "All unit tests passed!"
    echo ""
}

# Level 2: Component Demo
test_components() {
    print_header "LEVEL 2: COMPONENT TESTS"
    print_info "Running component demo..."
    
    uv run python demo.py
    
    print_success "All components working!"
    echo ""
}

# Level 3: Integration Tests
test_integration() {
    print_header "LEVEL 3: INTEGRATION TESTS"
    print_info "Testing end-to-end flow..."
    
    uv run python test_e2e_full.py
    
    print_success "Integration tests passed!"
    echo ""
}

# Level 4: API Tests
test_api() {
    print_header "LEVEL 4: API TESTS"
    print_info "Testing FastAPI server..."
    
    # Check if server is running
    if ! curl -s http://localhost:8000/api/health > /dev/null; then
        print_error "API server not running!"
        print_info "Start it with: uv run python -m uvicorn api.main:app --reload"
        exit 1
    fi
    
    print_info "Testing health endpoint..."
    curl -s http://localhost:8000/api/health | python -m json.tool
    
    print_info "Testing chat endpoint..."
    curl -s -X POST http://localhost:8000/api/chat \
        -H "Content-Type: application/json" \
        -d '{
            "message": "What is the capital of France?",
            "user_id": "test_user_123",
            "thread_id": null
        }' | python -m json.tool
    
    print_info "Testing file upload..."
    echo "This is a test document about Paris, the capital of France." > /tmp/test_doc.txt
    curl -s -X POST http://localhost:8000/api/upload \
        -F "file=@/tmp/test_doc.txt" \
        -F "user_id=test_user_123" | python -m json.tool
    
    print_info "Testing conversations list..."
    curl -s http://localhost:8000/api/conversations/test_user_123 | python -m json.tool
    
    print_success "API tests completed!"
    echo ""
}

# Level 5: Streamlit UI Test
test_ui() {
    print_header "LEVEL 5: STREAMLIT UI TEST"
    print_info "Launching Streamlit UI..."
    print_info "Open http://localhost:8501 in your browser"
    print_info "Press Ctrl+C to stop"
    echo ""
    
    uv run streamlit run app/streamlit_app_v2.py --server.port=8501
}

# Level 6: Docker Tests
test_docker() {
    print_header "LEVEL 6: DOCKER TESTS"
    print_info "Testing Docker deployment..."
    
    print_info "Building Docker image..."
    docker-compose build
    
    print_info "Starting services..."
    docker-compose up -d
    
    print_info "Waiting for services to start..."
    sleep 10
    
    print_info "Testing health endpoint..."
    curl -s http://localhost:8000/api/health | python -m json.tool
    
    print_info "Testing Streamlit UI..."
    curl -s -o /dev/null -w "%{http_code}" http://localhost:8501
    
    print_success "Docker deployment successful!"
    print_info "Stop with: docker-compose down"
    echo ""
}

# Run all tests
test_all() {
    print_header "RUNNING ALL TESTS"
    test_unit
    test_components
    test_integration
    
    print_header "API & DOCKER TESTS"
    print_info "To test API, first start the server:"
    print_info "  uv run python -m uvicorn api.main:app --reload"
    print_info "Then run: ./test_system.sh api"
    echo ""
    print_info "To test Docker:"
    print_info "  ./test_system.sh docker"
    echo ""
    print_info "To test Streamlit UI:"
    print_info "  ./test_system.sh ui"
}

# Main
LEVEL=${1:-all}

case $LEVEL in
    unit)
        test_unit
        ;;
    component|components|demo)
        test_components
        ;;
    integration|e2e)
        test_integration
        ;;
    api)
        test_api
        ;;
    ui|streamlit)
        test_ui
        ;;
    docker)
        test_docker
        ;;
    all|*)
        test_all
        ;;
esac

print_success "Test execution complete!"
