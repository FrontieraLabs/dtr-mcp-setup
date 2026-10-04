@echo off
rem run_sync.bat — sincroniza K: al cerebro y regenera los .md (sin LLM)
setlocal
set "ROOT=E:\Users\aaron_dtr\Desktop\brain-DTR"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "LOG=C:\dtr-brain\brain\_meta\sync.log"
set PYTHONIOENCODING=utf-8

if not exist "C:\dtr-brain\brain\_meta" mkdir "C:\dtr-brain\brain\_meta"

echo ============================================================>> "%LOG%"
echo === INICIO %date% %time% >> "%LOG%"
"%PY%" "%ROOT%\sync_index.py" >> "%LOG%" 2>&1
if %errorlevel%==9 (
  echo *** otra sync en curso, se omite esta corrida >> "%LOG%"
  goto fin
)
if errorlevel 1 echo *** sync_index.py devolvio error %errorlevel% >> "%LOG%"
"%PY%" "%ROOT%\build_brain.py" >> "%LOG%" 2>&1
if errorlevel 1 echo *** build_brain.py devolvio error %errorlevel% >> "%LOG%"
:fin
echo === FIN %date% %time% >> "%LOG%"
endlocal
