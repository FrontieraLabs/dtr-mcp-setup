@echo off
rem start_mcp_http.bat - arranca dtr-mercantil en red (streamable-http) para
rem que los PCs de oficina lo usen desde su Claude Desktop normal, sin Citrix.
rem Si el puerto ya esta en uso, la nueva instancia muere sola.
set "ROOT=E:\Users\aaron_dtr\Desktop\brain-DTR"
start "" "%ROOT%\.venv\Scripts\pythonw.exe" "%ROOT%\server.py" --http
