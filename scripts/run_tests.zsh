#!/usr/bin/env zsh
set -e

export PATH="$HOME/.local/bin:$PATH"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    local color=$1 msg=$2
    echo -e "${color}${msg}${NC}"
}

print_status $YELLOW 'Running AttuBot Test Suite'
echo '======================================'

# Track test result
local test_result=0

# Step 1: Python tests
echo ''
print_status $YELLOW '[1/3] Running Python tests...'
echo '----------------------------------------'
if python -m pytest -v; then
    print_status $GREEN 'Python tests passed!'
else
    print_status $RED 'Python tests failed!'
    test_result=1
fi

# Step 2: JavaScript tests
echo ''
print_status $YELLOW '[2/3] Running JavaScript tests...'
echo '----------------------------------------'
if npm test; then
    print_status $GREEN 'JavaScript tests passed!'
else
    print_status $RED 'JavaScript tests failed!'
    test_result=1
fi

# Step 3: Bot startup test (in Docker)
if (( test_result == 0 )); then
    echo ''
    print_status $YELLOW '[3/3] Running bot in TEST_MODE...'
    echo '----------------------------------------'

    # Run the bot in test mode using docker-compose
    # The --profile tests activates the tests service which has TEST_MODE=1
    TEST_MODE=1 DEBUG=1 python ./attu-bot.py
    local exit_code=$?

    if (( exit_code == 0 )); then
        print_status $GREEN 'Bot startup test passed!'
    else
        print_status $RED "Bot startup test failed (exit code: $exit_code)"
        test_result=1
    fi
else
    echo ''
    print_status $YELLOW '[3/3] Skipping bot startup test (previous tests failed)'
fi

# Summary
echo ''
echo '======================================'
if (( test_result == 0 )); then
    print_status $GREEN 'All tests passed! ✓'
else
    print_status $RED 'Some tests failed! ✗'
fi
echo '======================================'

exit $test_result
exit $test_result
