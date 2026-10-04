# MIGRACIÓN — Cerebro documental DTR

> **Para Claude Code en una cuenta nueva:** lee este archivo entero antes de
> tocar nada. Contiene todo el contexto del proyecto: qué es, cómo funciona,
> qué decisiones se tomaron y por qué, estado actual y pendientes. Junto con
> `CLAUDE.md` (resumen técnico que se autocarga) tienes continuidad total.
> **Para el usuario:** guarda este archivo; si migras de máquina, llévate la
> carpeta completa `E:\Users\aaron_dtr\Desktop\brain-DTR`.

## 1. Qué es esto

Cerebro documental local para el Bufete DTR (despacho jurídico, España,
usuario: aaron@rvconsulting.services, escribe en español/voseo). Indexa la
unidad **K:** (sistema MERCANTIL: ~348 GB, ~148.300 documentos, 1.033
expedientes = carpetas de primer nivel con nombre de cliente o asunto) y la
expone a Claude vía MCP con búsqueda FTS insensible a acentos, mapa en
Markdown y grafo de relaciones. Construido el 20-21/09/2026 en este servidor
(Windows Server 2022, dominio HOSTPROV, sin admin).

**Regla de oro: K: es SOLO LECTURA. Jamás escribir/mover/borrar ahí.**
**Restricción dura: el cron no llama a ningún LLM — coste cero, todo
mecánico. El razonamiento lo pone Claude al consultar.**

## 2. Estado actual (28/09/2026)

- Primera indexación completa: 21/09 (7 h). Desde entonces la sync diaria
  (06:00, ~13 min) corre sola sin errores; refleja altas/cambios/bajas.
- ~148.300 docs: ~67k con texto FTS · ~35k `escaneado(ocr?)` (sin OCR aún)
  · ~44k `sin-extractor` (.doc/.xls/imágenes/vídeos) · ~700 `error:*`.
- Grafo: 1.033 nodos, ~11.200 aristas. Índice: 1,5 GB.
- Criterios de aceptación: 11/11 OK + altas/bajas demostradas en producción.

## 3. Mapa de archivos

| Qué | Dónde |
|---|---|
| Código | `E:\Users\aaron_dtr\Desktop\brain-DTR` (este proyecto) |
| Python 3.12 portable | `tools\python312` (zip NuGet; el hosting bloquea MSI) |
| Venv | `.venv` (pypdf, python-docx, openpyxl, extract-msg, mcp 2.x, pymupdf, fonttools) |
| Cerebro generado | `C:\dtr-brain\brain\` → INDEX.md, expedientes\*.md |
| Índice + meta | `C:\dtr-brain\brain\_meta\` → index.db (FTS5), manifest.json, graph.json, sync.log, sync.pid |
| Log de cada corrida | `C:\dtr-brain\brain\_meta\sync.log` |

Componentes: `config.py` (rutas/límites/stopwords) · `sync_index.py`
(incremental + grafo) · `build_brain.py` (.md) · `server.py` (MCP) ·
`estado_server.py` (dashboard) · `run_sync.bat` · `start_dashboard.bat`.

## 4. Automatización en esta máquina

- Tarea programada **"DTR-Brain-Sync"**: diaria 06:00, ejecuta run_sync.bat
  (modo "solo interactivo": requiere sesión de Windows iniciada).
- Dashboard **http://localhost:8765** (estado) y **/grafo** (grafo
  interactivo): autoarranca vía `DTR-Brain-Dashboard.bat` en la carpeta
  Inicio del usuario. Endpoints `/abrir?id=N` y `/carpeta?id=N` abren
  archivos de K: (os.startfile, validado contra rutas fuera de K:).
- Lock anti-solape: `_meta\sync.pid` (si hay sync viva, la nueva se omite).

## 5. Registro del MCP (por máquina, independiente de la cuenta)

- Claude Code: `.mcp.json` en esta carpeta.
- Claude Desktop: `%APPDATA%\Claude\claude_desktop_config.json`, entrada
  `dtr-mercantil` (command = .venv\Scripts\python.exe, args = server.py,
  env PYTHONPATH + PYTHONIOENCODING=utf-8).
- Con cuenta nueva solo hay que **aprobar** el servidor la primera vez.
- Tools: buscar_documentos, leer_documento, ver_documento (renderiza PDF/
  imagen en el chat con pymupdf — clave para escaneados), leer_expediente
  (modo resumen/completo), vecinos_expediente, documentos_recientes,
  resolver_ruta, indice_cerebro, estado_sync.
- Los enlaces de las tools van a `http://localhost:8765/abrir?id=N` porque
  **Claude Desktop bloquea file://**. La ruta misma es el texto del enlace.
- Instrucciones de proyecto para Claude Desktop: `PROMPT-PROYECTO.md`.
  Preguntas de prueba: `PREGUNTAS-EJEMPLO.md`.

## 6. Decisiones tomadas (y por qué)

1. **Grafo mecánico, no Graphiti**: el usuario pidió Graphiti; se descartó
   porque exige API key de pago (la suscripción de Claude no sirve para
   frameworks de terceros) y rompía el "cron sin LLM". Aristas:
   "menciona-a" (FTS del nombre de cada expediente en docs ajenos, NEAR 12,
   cap 40 por destino) y "nombre-similar" (token compartido ≥6 chars).
2. **Stopwords jurídicas** en config.py (~70 términos: concurso, herencia,
   tasacion, costas...): sin ellas, carpetas temáticas genéricas
   ("Concursos") generaban aristas con medio corpus. Los hubs que quedan
   (Concursos, ada, KIKO D VENTURES) son legítimos: sus docs mencionan a
   muchos clientes.
3. **Expediente = carpeta de nivel 1** (no hay patrón EXP-AAAA-NNN); los
   267 sueltos de la raíz van al pseudo-expediente `_raiz`.
4. **leer_expediente devuelve resumen por defecto** (no el .md entero: el
   de "ada" tiene 8.776 docs) → respuestas más rápidas y menos tokens.
5. Incremental por (tamaño+mtime) → hash blake2b de 128 KB → extracción
   solo de cambios. Manifest se guarda cada 2.000 archivos y se reconstruye
   desde la BD si falta (recuperación de crash).

## 7. Trampas del entorno (aprendidas a golpes)

- `os.kill(pid, 0)` NO vale en Windows para comprobar procesos → usar
  `dtr_common.pid_vivo()` (OpenProcess/WaitForSingleObject).
- pypdf emite a veces surrogates UTF-16 inválidos que SQLite rechaza →
  `_limpia()` sanea con encode/decode utf-8 errors=replace.
- Bajo pythonw.exe no hay stdout → `if sys.stdout:` antes de reconfigure.
- El python.exe del venv (base NuGet) lanza el intérprete real como hijo:
  verás 2 procesos python por corrida.
- SDK mcp 2.x: `from mcp.server.mcpserver import MCPServer, Image`
  (FastMCP ya no existe). `Image(data=..., format='png')` para imágenes.
- PowerShell 5.1: sin `&&`; schtasks /sc onlogon requiere admin (usar
  carpeta Inicio); Get-Content sin -Encoding UTF8 desfigura el log.
- Hay archivos con mtime corrupto (año 2098) → documentos_recientes filtra
  fechas futuras.

## 8. Verificación de salud (tras migrar o ante dudas)

```powershell
# ¿Sync diaria viva?  (debe listar SYNC OK recientes con errores=0)
Get-Content C:\dtr-brain\brain\_meta\sync.log -Tail 200 -Encoding UTF8 | Select-String 'SYNC OK'
# ¿Tarea programada?  ¿Dashboard?
schtasks /query /tn "DTR-Brain-Sync"
Invoke-WebRequest http://localhost:8765/api/estado -UseBasicParsing
# Sync manual si hace falta
E:\Users\aaron_dtr\Desktop\brain-DTR\run_sync.bat
```

## 9. Pendientes / hoja de ruta

1. **OCR** de los ~35k PDFs escaneados (hoy invisibles a la búsqueda;
   `ver_documento` los muestra y Claude puede leerlos con visión).
2. Extraer texto de ~19,5k **.doc** antiguos (requiere conversor, p. ej.
   LibreOffice headless portable).
3. **Enriquecimiento tipo Graphiti** con la suscripción: resúmenes/entidades
   por expediente vía `claude -p` en lotes acotados (fase 2 acordada).
4. Watcher **tiempo real** de K: (ReadDirectoryChangesW) si el usuario
   quiere frescura inferior a 24 h (ofrecido, no confirmado).
5. Modo "solo esta comunidad" en /grafo (ofrecido, no confirmado).
6. RGPD (usuario migrando a Claude Team): el MCP no distingue usuarios —
   expone todo K: a quien use esta máquina; si piden murallas chinas,
   añadir lista de exclusión de expedientes en config.py. DPA de Team
   cubre encargo de tratamiento; EIPD pendiente del DPO del despacho.
