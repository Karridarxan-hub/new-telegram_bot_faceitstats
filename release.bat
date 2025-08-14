@echo off
echo ========================================
echo    FACEIT Bot Release Manager
echo ========================================

if "%1"=="" (
    echo Usage: release.bat [major^|minor^|patch^|version]
    echo.
    echo Examples:
    echo   release.bat patch    - 1.0.0 -^> 1.0.1
    echo   release.bat minor    - 1.0.0 -^> 1.1.0  
    echo   release.bat major    - 1.0.0 -^> 2.0.0
    echo   release.bat 1.5.2    - Set specific version
    echo.
    type VERSION
    echo Current version: ^^
    exit /b 1
)

REM Читаем текущую версию
set /p CURRENT_VERSION=<VERSION

echo Current version: %CURRENT_VERSION%

REM Определяем новую версию
if "%1"=="major" (
    for /f "tokens=1,2,3 delims=." %%a in ("%CURRENT_VERSION%") do (
        set /a NEW_MAJOR=%%a+1
        set NEW_VERSION=!NEW_MAJOR!.0.0
    )
) else if "%1"=="minor" (
    for /f "tokens=1,2,3 delims=." %%a in ("%CURRENT_VERSION%") do (
        set /a NEW_MINOR=%%b+1
        set NEW_VERSION=%%a.!NEW_MINOR!.0
    )
) else if "%1"=="patch" (
    for /f "tokens=1,2,3 delims=." %%a in ("%CURRENT_VERSION%") do (
        set /a NEW_PATCH=%%c+1
        set NEW_VERSION=%%a.%%b.!NEW_PATCH!
    )
) else (
    set NEW_VERSION=%1
)

setlocal enabledelayedexpansion
echo New version: !NEW_VERSION!

REM Подтверждение
set /p CONFIRM="Continue with release !NEW_VERSION!? (y/N): "
if /i not "%CONFIRM%"=="y" (
    echo Release cancelled.
    exit /b 1
)

REM Обновляем VERSION файл
echo !NEW_VERSION! > VERSION
echo ✓ Updated VERSION file

REM Останавливаем текущий бот
echo.
echo ⏹ Stopping current bot...
docker-compose down

REM Устанавливаем версию для docker-compose
set VERSION=!NEW_VERSION!

REM Собираем новый образ с версией
echo.
echo 🔨 Building version !NEW_VERSION!...
docker-compose build --build-arg VERSION=!NEW_VERSION! faceit-bot

REM Запускаем новую версию
echo.
echo 🚀 Starting bot v!NEW_VERSION!...
docker-compose up -d faceit-bot

REM Показываем статус
echo.
echo 📊 Status:
docker-compose ps

echo.
echo ✅ Successfully released version !NEW_VERSION!
echo 📋 Container: faceit-telegram-bot-v!NEW_VERSION!
echo 🎯 Image: faceit-bot:!NEW_VERSION!

REM Показываем логи
echo.
echo 📜 Recent logs:
docker-compose logs faceit-bot --tail 10

echo.
echo ========================================
echo   Release !NEW_VERSION! completed!
echo ========================================