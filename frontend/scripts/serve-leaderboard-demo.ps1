$ErrorActionPreference = 'Stop'
$frontendRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $frontendRoot
$env:VITE_API_PROXY_TARGET = 'http://127.0.0.1:8010'
& node (Join-Path $frontendRoot 'node_modules/vite/bin/vite.js') --host=127.0.0.1 --port=5180 --strictPort
