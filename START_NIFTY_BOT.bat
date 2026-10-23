@echo off
title NIFTY 50 Options Algo Bot & Monitor
color 0B
echo ================================================================================
echo    ANGEL ONE NIFTY 50 OPTIONS ALGO TRADING BOT  (ALL-IN-ONE)
echo ================================================================================
echo  * Initial Capital: Rs 50,000 (Fresh Start from Scratch)
echo  * Position Size:   2 Lots (130 Qty) OTM-1 Options
echo  * Staged Targets:  T1 @ +100 pts (Book 1 Lot)  /  T2 @ +200 pts (Runner)
echo  * Risk Control:    SL 50 pts  /  Instant Breakeven (+4 pts buffer) on Lot 2
echo  * Telegram Alerts: GOLD Zone (-5077267080)
echo ================================================================================
echo.
echo Select an option:
echo   [1] Start Full Bot + Web HUD Dashboard (app.py - Recommended)
echo   [2] Start Console-Only Live Trading Bot (nifty_algo_bot.py)
echo   [3] Check Status & Today's Levels (One-time check)
echo   [4] Reset to Clean Scratch (Wipes history and resets to Rs 50,000)
echo.
set /p choice="Enter choice (1-4, default is 1): "

if "%choice%"=="1" goto run_app
if "%choice%"=="2" goto run_bot
if "%choice%"=="3" goto check_status
if "%choice%"=="4" goto reset_scratch
goto run_app

:run_app
echo.
echo Launching All-in-One Bot + Web Dashboard HUD on http://localhost:7860...
python app.py
goto end

:run_bot
echo.
echo Launching Console-Only Algo Trading Bot...
python nifty_algo_bot.py
goto end

:check_status
echo.
echo Checking status...
python nifty_algo_bot.py --status
goto end

:reset_scratch
echo.
echo Resetting to scratch...
python nifty_algo_bot.py --reset
goto end

:end
echo.
pause
