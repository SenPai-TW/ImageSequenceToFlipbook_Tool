@echo off
setlocal
chcp 65001 >nul
title 安裝 Flipbook 工具必要套件

if not exist "%~dp0_flipbook_install_runtime.ps1" (
  echo 找不到安裝程式：_flipbook_install_runtime.ps1
  echo 請確認檔案與此批次檔放在同一個資料夾。
  echo.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0_flipbook_install_runtime.ps1"
set "INSTALL_RESULT=%ERRORLEVEL%"

echo.
if not "%INSTALL_RESULT%"=="0" (
  echo 安裝失敗。請保留此視窗中的錯誤訊息，以便排查。
  pause
  exit /b %INSTALL_RESULT%
)

echo 安裝完成，現在可以雙擊「開啟Flipbook工具.vbs」。
pause
endlocal
