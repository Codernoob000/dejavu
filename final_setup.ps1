# Run from the project root with the venv active, right before recording or presenting.
# Requires HINDSIGHT_URL and HINDSIGHT_API_KEY to be set in this window already.
# Usage:  .\final_setup.ps1            (strict mode on: Hindsight-only recall)
#         .\final_setup.ps1 -NoStrict  (union with local ledger, more forgiving)
param([switch]$NoStrict)

if (-not $env:HINDSIGHT_URL -or -not $env:HINDSIGHT_API_KEY) {
    Write-Host "Set HINDSIGHT_URL and HINDSIGHT_API_KEY first." -ForegroundColor Red; exit 1
}

# Start from a clean local state
if (Test-Path data\ledger.json) { Remove-Item data\ledger.json }
Remove-Item Env:DEJAVU_STRICT -ErrorAction SilentlyContinue

# Seed, then read the bank name seed.py actually used (older seed.py rotates to a suffixed bank)
$env:HINDSIGHT_BANK = "dejavu-" + (Get-Date -Format "MMddHHmm")
Write-Host "Seeding ..."
$out = python -m app.seed 2>&1 | Out-String
Write-Host $out
if ($out -match "into bank (\S+)") {
    $env:HINDSIGHT_BANK = $Matches[1]
} else {
    Write-Host "Could not read the bank name from the seed output. Stopping." -ForegroundColor Red; exit 1
}
if ($out -notmatch "errors: 0") {
    Write-Host "Seed reported errors. Stopping." -ForegroundColor Red; exit 1
}
Write-Host "Using bank: $env:HINDSIGHT_BANK" -ForegroundColor Green

# Hindsight retains asynchronously; recall is empty until it finishes
$wait = 90
Write-Host "Waiting $wait s for Hindsight to finish processing ..."
for ($i = $wait; $i -gt 0; $i -= 10) {
    Write-Host "  $i s left"
    Start-Sleep -Seconds 10
}

if (-not $NoStrict) { $env:DEJAVU_STRICT = "1" }
Write-Host "Strict mode: $env:DEJAVU_STRICT   Bank: $env:HINDSIGHT_BANK"
Write-Host "Starting app on http://localhost:8000 (Ctrl+C to stop). Do NOT click Reset demo while presenting."
Write-Host "Check the badge reads '0 retained' before you hit record." -ForegroundColor Yellow
uvicorn app.main:app