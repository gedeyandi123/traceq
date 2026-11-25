param(
    [ValidateSet("fast", "full")]
    [string]$Mode = "fast",
    [ValidateSet("all", "python", "web")]
    [string]$Scope = "all",
    [string[]]$TestPath = @(),
    [string[]]$DbPath = @(),
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$UvCacheDir = Join-Path $env:TEMP "traceq-uv-cache"
$RuffCacheDir = Join-Path $env:TEMP "traceq-ruff-cache"
$VenvScripts = Join-Path $RepoRoot ".venv\Scripts"

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

function Invoke-PythonTool {
    param(
        [string]$ExeName,
        [string[]]$Arguments
    )
    $LocalExe = Join-Path $VenvScripts "$ExeName.exe"
    if (Test-Path $LocalExe) {
        & $LocalExe @Arguments
    }
    else {
        uv run --no-sync --offline --cache-dir $UvCacheDir $ExeName @Arguments
    }
}

Push-Location $RepoRoot
$PrevVirtualEnv = $env:VIRTUAL_ENV
$PrevPath = $env:PATH
if (Test-Path $VenvScripts) {
    $env:VIRTUAL_ENV = Join-Path $RepoRoot ".venv"
    $env:PATH = "$VenvScripts;$env:PATH"
}
try {
    if ($Scope -in @("all", "python")) {
        if ($Mode -eq "fast") {
            Invoke-Step "Ruff lint & format (local .venv)" {
                Invoke-PythonTool "ruff" @("check", "--cache-dir", $RuffCacheDir, ".")
                if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
                Invoke-PythonTool "ruff" @("format", "--check", "--cache-dir", $RuffCacheDir, ".")
            }
        }
        else {
            Invoke-Step "All pre-commit hooks" {
                pre-commit run --all-files
            }
        }

        Invoke-Step "Python typecheck (pyright)" {
            $VenvPython = Join-Path $VenvScripts "python.exe"
            if (Test-Path $VenvPython) {
                & $VenvPython -m pyright
            }
            else {
                uv run --no-sync --offline --cache-dir $UvCacheDir pyright
            }
        }

        Invoke-Step "Module boundaries (import-linter)" {
            Invoke-PythonTool "lint-imports" @("--no-cache")
        }

        Invoke-Step "Local socketpair preflight (2s timeout)" {
            $VenvPython = Join-Path $VenvScripts "python.exe"
            $PyExe = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
            $psi = [System.Diagnostics.ProcessStartInfo]::new()
            $psi.FileName = $PyExe
            $psi.Arguments = "-c `"import socket; a, b = socket.socketpair(); a.close(); b.close()`""
            $psi.UseShellExecute = $false
            $psi.RedirectStandardError = $true
            $proc = [System.Diagnostics.Process]::Start($psi)
            if (-not $proc.WaitForExit(2000)) {
                try { $proc.Kill() } catch {}
                throw "Local loopback socketpair() is blocked/hung (Windows sandbox). Re-run scripts/verify.ps1 -Scope python with BypassSandbox: true."
            }
            if ($proc.ExitCode -ne 0) {
                $err = $proc.StandardError.ReadToEnd().Trim()
                throw "Local loopback socketpair() preflight failed ($($proc.ExitCode)): $err. Re-run scripts/verify.ps1 -Scope python with BypassSandbox: true."
            }
        }

        if ($Mode -eq "fast") {
            Invoke-Step "Fast Python test suite (not slow and not db)" {
                if ($TestPath.Count -gt 0) {
                    Invoke-PythonTool "pytest" (@("-p", "no:cacheprovider", "-q", "--tb=short") + $TestPath)
                }
                else {
                    Invoke-PythonTool "pytest" @("-p", "no:cacheprovider", "-m", "not slow and not db", "-q", "--tb=short")
                }
            }
            if ($DbPath.Count -gt 0) {
                Invoke-Step "Targeted DB tests" {
                    Invoke-PythonTool "pytest" (@("-p", "no:cacheprovider", "-m", "db", "-q", "--tb=short") + $DbPath)
                }
            }
        }
        else {
            Invoke-Step "Full Python test suite" {
                Invoke-PythonTool "pytest" @("-p", "no:cacheprovider", "-q", "--tb=short")
            }
        }
    }

    if ($Scope -in @("all", "web")) {
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

        if ($Mode -eq "full" -or $Build) {
            Invoke-Step "Web production build" {
                $env:NEXT_TELEMETRY_DISABLED = "1"
                npm --prefix web run build
            }
        }
    }

    Write-Host "Verification ($Mode / $Scope) passed!" -ForegroundColor Green
}
finally {
    $env:VIRTUAL_ENV = $PrevVirtualEnv
    $env:PATH = $PrevPath
    Pop-Location
}
