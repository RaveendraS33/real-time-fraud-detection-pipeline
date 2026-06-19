$ErrorActionPreference = "Stop"
$env:RUN_INTEGRATION_TESTS = "1"

try {
    & "$PSScriptRoot\..\.venv\Scripts\pytest.exe" `
        "$PSScriptRoot\..\tests\integration\test_live_pipeline.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Integration test failed with exit code $LASTEXITCODE"
    }
}
finally {
    Remove-Item Env:RUN_INTEGRATION_TESTS -ErrorAction SilentlyContinue
}

