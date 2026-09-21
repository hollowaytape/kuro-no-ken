@echo off
rem Double-click to rebuild the patched disk from KuroNoKen_dump.xlsx.
cd /d "%~dp0"
python build.py
pause
