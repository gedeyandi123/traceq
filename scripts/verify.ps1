param(
    [ValidateSet("fast", "full")]
    [string]$Mode = "fast",
    [string[]]$TestPath = @()
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$UvCacheDir = ($RepoRoot -replace "\\", "/") + "/.uv-cache"

function Invoke-Step {
    param(
        [string]$Title,
        [scriptblock]$Action
    )
    Write-Host "==> $Title" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed ($LASTEXITCODE): $Title"
    }
}

Push-Location $RepoRoot
try {
    if ($Mode -eq "fast") {
        Invoke-Step "Ruff lint & format (pre-commit)" {
            pre-commit run ruff-check --all-files
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            pre-commit run ruff-format --all-files
        }
    }
    else {
        Invoke-Step "All pre-commit hooks" {
            pre-commit run --all-files
        }
    }

    Invoke-Step "Python typecheck (pyright)" {
        uv run --cache-dir $UvCacheDir pyright
    }

    Invoke-Step "Module boundaries (import-linter)" {
        uv run --cache-dir $UvCacheDir lint-imports
    }

    if ($Mode -eq "fast") {
        Invoke-Step "Fast Python test suite (not slow and not db)" {
            if ($TestPath.Count -gt 0) {
                uv run --cache-dir $UvCacheDir pytest -p no:cacheprovider -q --tb=short @TestPath
            }
            else {
                uv run --cache-dir $UvCacheDir pytest -p no:cacheprovider -m "not slow and not db" -q --tb=short
            }
        }
    }
    else {
        Invoke-Step "Full Python test suite" {
            uv run --cache-dir $UvCacheDir pytest -p no:cacheprovider -q --tb=short
        }
    }

    Invoke-Step "Web typegen, typecheck, lint, & unit tests" {
        Push-Location web
        try {
            npx next typegen
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            npm run typecheck
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            npm run lint
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            npm test
        }
        finally {
            Pop-Location
        }
    }

    if ($Mode -eq "full") {
        Invoke-Step "Web production build" {
            $env:NEXT_TELEMETRY_DISABLED = "1"
            npm --prefix web run build
        }
    }

    Write-Host "Verification ($Mode) passed!" -ForegroundColor Green
}
finally {
    Pop-Location
}
