@echo off
rem Проверка из командной строки:  check.bat "D:\КД\папка" --spec "СП.xlsx" --out отчёт.xlsx
chcp 65001 >nul
"%~dp0.venv\Scripts\python.exe" -X utf8 -m checking %*
