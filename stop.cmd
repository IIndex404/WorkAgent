@echo off
cd /d "%~dp0"
set "WORKAGENT_COMPOSE=compose.yml"
if exist compose.local.yml set "WORKAGENT_COMPOSE=compose.local.yml"
docker compose -f "%WORKAGENT_COMPOSE%" stop
pause
