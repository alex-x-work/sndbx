@echo off
rem Runs sndbx.py with uv, which installs PyYAML from the script's metadata, or with python without uv
where uv >nul 2>nul
if %errorlevel% equ 0 (
  uv run --quiet --script "%~dp0sndbx.py" %*
) else (
  python "%~dp0sndbx.py" %*
)
exit /b %errorlevel%
