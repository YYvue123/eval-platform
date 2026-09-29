param([int]$Port = 8765)
$root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $root
& "$root\backend\.venv\Scripts\python.exe" -m uvicorn `
  tools.stats_service.app:app --host 127.0.0.1 --port $Port
