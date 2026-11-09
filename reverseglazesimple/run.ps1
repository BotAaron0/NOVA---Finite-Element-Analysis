param(
    [ValidateSet('match', 'index')][string]$Command = 'match',
    [string]$Inputs = '',
    [string]$Output = ''
)
$ErrorActionPreference = 'Stop'
if (-not $Inputs) { $Inputs = Join-Path $PSScriptRoot 'inputs.txt' }
$candidates = @(
    (Join-Path $PSScriptRoot '.venv/Scripts/python.exe'),
    (Join-Path (Split-Path $PSScriptRoot) '.venv/Scripts/python.exe'),
    (Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
)
$selectedPython = $null
foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
        & $candidate -c "import importlib.util,sys; sys.exit(not all(importlib.util.find_spec(n) for n in ('numpy','PIL','pdfplumber','pypdfium2')))"
        if ($LASTEXITCODE -eq 0) { $selectedPython = $candidate; break }
    }
}
if (-not $selectedPython) {
    throw 'Install dependencies inside reverseglazesimple: python -m venv .venv; .\.venv\Scripts\python -m pip install -e .'
}
Push-Location $PSScriptRoot
try {
    Write-Host "Using inputs: $Inputs"
    $arguments = @('-m', 'glaze_matcher.cli', $Command, '--inputs', $Inputs)
    if ($Output) { $arguments += @('--output', $Output) }
    & $selectedPython @arguments
    $resultCode = $LASTEXITCODE
} finally { Pop-Location }
exit $resultCode
