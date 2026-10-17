@echo off
title Agente de Noticias - Launcher
echo ========================================
echo   Iniciando Redacao Digital IA
echo ========================================

set "ROOT=%~dp0"

echo [+] Iniciando Backend (FastAPI - Porta 8000)...
start "Backend - FastAPI" cmd /k "cd /d %ROOT%backend && if exist venv\Scripts\activate.bat (call venv\Scripts\activate.bat) && set PYTHONPATH=. && uvicorn app.main:app --reload --port 8000"

echo [+] Iniciando Frontend (Next.js - Porta 3000)...
start "Frontend - Next.js" cmd /k "cd /d %ROOT%frontend && npm run dev"

echo.
echo Servicos iniciados com sucesso!
echo Backend:  http://localhost:8000/docs
echo Frontend: http://localhost:3000
echo ========================================
pause
