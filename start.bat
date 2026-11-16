@echo off
title Automated Multi-Platform Posting System

echo ============================================================
echo   Automated Multi-Platform Posting System
echo   Dxora Technologies - Technical Assignment
echo ============================================================
echo.

REM Check if .env exists
if not exist ".env" (
    echo [WARNING] .env file not found!
    echo Copying .env.example to .env ...
    copy .env.example .env
    echo.
    echo Please edit .env and add your API credentials before posting.
    echo.
)

echo [1/2] Starting FastAPI backend on http://localhost:4000 ...
start "FastAPI Backend" cmd /k "uvicorn app.main:app --host 0.0.0.0 --port 4000"

echo Waiting for backend to start...
timeout /t 3 /nobreak > nul

echo.
echo [2/2] Starting Streamlit frontend ...
echo.
echo ============================================================
echo   FastAPI Backend : http://localhost:4000
echo   Swagger UI      : http://localhost:4000/docs
echo   Streamlit UI    : http://localhost:8501
echo ============================================================
echo.
streamlit run streamlit_app.py
