@echo off
echo Updating sketch_to_revit from GitHub...
cd /d "%~dp0\.."
git pull
echo.
echo Done! Files are up to date.
pause
