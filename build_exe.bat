@echo off
rem Сборка переносимой программы: dist\Проверка чертежей\ (папку целиком копируйте на любой компьютер с Windows)
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
".venv\Scripts\python.exe" -m pip install pyinstaller
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean checking.spec
echo.
echo Готово: dist\ПроверкаЧертежей\ПроверкаЧертежей.exe
pause
