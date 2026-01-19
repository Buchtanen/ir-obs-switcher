# PowerShell script to run tests automatically
# Usage: .\run_tests.ps1 [test_file_or_pattern]

param(
    [string]$TestPattern = "tests/"
)

Write-Host "Running tests: $TestPattern" -ForegroundColor Cyan
Write-Host ""

# Run pytest with verbose output
python -m pytest $TestPattern -v --tb=short

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "All tests passed!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Some tests failed!" -ForegroundColor Red
    exit $LASTEXITCODE
}
