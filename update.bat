@echo off
echo ========================================
echo    FACEIT Bot Update Manager  
echo ========================================

REM Читаем текущую версию
set /p CURRENT_VERSION=<VERSION

echo Current version: %CURRENT_VERSION%
echo.

REM Показываем меню опций
echo Available actions:
echo   1. Quick patch update (%CURRENT_VERSION% -^> next patch)
echo   2. Rebuild current version
echo   3. View logs
echo   4. Status check
echo   5. Rollback (restart without rebuild)
echo.

set /p ACTION="Select action (1-5): "

if "%ACTION%"=="1" (
    echo.
    echo 🔨 Creating patch update...
    call release.bat patch
) else if "%ACTION%"=="2" (
    echo.
    echo 🔨 Rebuilding current version...
    docker-compose down
    set VERSION=%CURRENT_VERSION%
    docker-compose build --build-arg VERSION=%CURRENT_VERSION% faceit-bot
    docker-compose up -d faceit-bot
    echo ✅ Rebuilt version %CURRENT_VERSION%
) else if "%ACTION%"=="3" (
    echo.
    echo 📜 Bot logs:
    docker-compose logs faceit-bot --tail 50
) else if "%ACTION%"=="4" (
    echo.
    echo 📊 Current status:
    docker-compose ps
    echo.
    echo 🖼 Docker images:
    docker images | findstr faceit-bot
    echo.
    echo 📊 Resource usage:
    docker stats faceit-telegram-bot-v%CURRENT_VERSION% --no-stream --format "CPU: {{.CPUPerc}} | Memory: {{.MemUsage}}"
) else if "%ACTION%"=="5" (
    echo.
    echo ⏹ Stopping bot...
    docker-compose down
    echo 🚀 Restarting...
    set VERSION=%CURRENT_VERSION%
    docker-compose up -d faceit-bot
    echo ✅ Rollback completed
) else (
    echo Invalid option
    exit /b 1
)

echo.
echo ========================================