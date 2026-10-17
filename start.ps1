<#
.SYNOPSIS
    Inicia o Backend (FastAPI / Uvicorn) e o Frontend (Next.js) do Agente de Notícias em janelas separadas.
#>

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Iniciando Redacao Digital IA" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Iniciar Backend
$backendDir = Join-Path $root "backend"
$backendVenvPy = Join-Path $backendDir "venv\Scripts\python.exe"

if (-not (Test-Path $backendVenvPy)) {
    Write-Host "[!] venv nao encontrado no backend. Usando python padrao..." -ForegroundColor Yellow
    $backendCmd = "cd '$backendDir'; `$env:PYTHONPATH='.'; python -m uvicorn app.main:app --reload --port 8000"
} else {
    $backendCmd = "cd '$backendDir'; `$env:PYTHONPATH='.'; .\venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000"
}

Write-Host "[+] Abrindo janela do Backend (FastAPI em http://localhost:8000)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Write-Host '--- BACKEND FASTAPI (Porta 8000) ---' -ForegroundColor Green; $backendCmd"

# 2. Iniciar Frontend
$frontendDir = Join-Path $root "frontend"
Write-Host "[+] Abrindo janela do Frontend (Next.js em http://localhost:3000)..." -ForegroundColor Green
$frontendCmd = "cd '$frontendDir'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Write-Host '--- FRONTEND NEXT.JS (Porta 3000) ---' -ForegroundColor Cyan; $frontendCmd"

Write-Host ""
Write-Host "Servidores iniciados!" -ForegroundColor Green
Write-Host "-> Backend:  http://localhost:8000/docs" -ForegroundColor Gray
Write-Host "-> Frontend: http://localhost:3000" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
