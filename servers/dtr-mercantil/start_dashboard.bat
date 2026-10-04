@echo off
rem start_dashboard.bat - arranca el visualizador del cerebro DTR
rem (si el puerto 8765 ya esta en uso, la nueva instancia muere sola)
set "ROOT=E:\Users\aaron_dtr\Desktop\brain-DTR"
start "" "%ROOT%\.venv\Scripts\pythonw.exe" "%ROOT%\estado_server.py"
