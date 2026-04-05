@echo off
chcp 65001 >nul
cd /d "%~dp0"
python stock_agent_demo.py
