@echo off
title NIFTY Algo Daily & Weekly P&L Tracker
echo ========================================================================
echo    CHECKING DAILY & WEEKLY P&L STATUS (NIFTY OPTIONS ALGO)
echo ========================================================================
echo.
python track_daily_weekly_pnl.py
echo.
echo Opening Interactive HTML Dashboard...
start report_daily_weekly_pnl.html
echo.
pause
