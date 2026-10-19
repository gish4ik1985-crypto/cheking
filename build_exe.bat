@echo off
rem Сборка переносимой программы: dist\Проверка чертежей\ (папку целиком копируйте на любой компьютер с Windows)
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
rem Интерфейс (React + shadcn/ui) собирается в frontend\dist; нужен Node.js. Без него остаются прежние страницы из web	emplates.
if exist "frontend\package.json" (
  where npm >nul 2>nul
  if not errorlevel 1 (
    pushd frontend
    call npm install
    call npm run build
    popd
  ) else (
    echo Node.js не найден: интерфейс не собран, будут использованы прежние страницы.
  )
)
".venv\Scripts\python.exe" -m pip install pyinstaller
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean checking.spec
echo.
echo Готово: dist\ПроверкаЧертежей\ПроверкаЧертежей.exe
pause
