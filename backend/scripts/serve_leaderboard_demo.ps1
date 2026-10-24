$ErrorActionPreference = 'Stop'
$backendRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $backendRoot
$env:APP_ENV = 'dev'
$env:DATABASE_URL = 'sqlite+aiosqlite:///' + (Join-Path $backendRoot 'leaderboard_demo.db').Replace('\', '/')
$env:UPLOAD_DIR = Join-Path $backendRoot 'uploads/leaderboard-demo'
$env:LOG_DIR = Join-Path $backendRoot 'logs/leaderboard-demo-server'
$env:AGENT_WORKER_ENABLED = 'false'
& (Join-Path $backendRoot '.venv/Scripts/python.exe') -m uvicorn app.main:app --host 127.0.0.1 --port 8010
