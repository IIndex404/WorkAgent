@echo off
cd /d "%~dp0"
set "WORKAGENT_COMPOSE=compose.yml"
if exist compose.local.yml set "WORKAGENT_COMPOSE=compose.local.yml"
docker compose -f "%WORKAGENT_COMPOSE%" up -d --build --wait
if errorlevel 1 (pause & exit /b 1)
start "" http://127.0.0.1:8000
