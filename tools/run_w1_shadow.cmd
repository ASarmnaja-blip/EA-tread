@echo off
REM W1 forward shadow logger, Amendment 12 section 6.
REM READ-ONLY with respect to the market: it logs signals and never sends an order.
cd /d C:\Users\66985\Documents\EA-tread
set PYTHONIOENCODING=utf-8
"C:\Users\66985\AppData\Local\Programs\Python\Python312\python.exe" research\pilot\w1_shadow.py >> data\w1_shadow_task.log 2>&1
