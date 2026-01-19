#!/bin/bash
# Bash script to run tests automatically
# Usage: ./run_tests.sh [test_file_or_pattern]

TEST_PATTERN="${1:-tests/}"

echo "Running tests: $TEST_PATTERN"
echo ""

# Run pytest with verbose output
python -m pytest "$TEST_PATTERN" -v --tb=short

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "All tests passed!"
else
    echo ""
    echo "Some tests failed!"
    exit $EXIT_CODE
fi
