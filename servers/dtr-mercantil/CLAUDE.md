# Cerebro documental DTR — sistema MERCANTIL

> Contexto completo del proyecto (historia, decisiones, estado, pendientes,
> verificación de salud): **lee `MIGRACION.md`** antes de trabajar aquí.

Sistema local que indexa la unidad K: (348 GB, 148k docs, 1.033 expedientes
de un despacho jurídico) y lo expone a Claude vía MCP. Sin LLM en el cron:
toda la generación es mecánica.

## Regla de oro
**K: es SOLO LECTURA. Jamás crear, mover o borrar nada dentro de K:.**

## Arquitectura
- `config.py` — rutas, extensiones, límites, stopwords del grafo.
- `sync_index.py` — recorrido incremental de K: (tamaño+mtime → hash →
  extracción), índice SQLite FTS5 (`unicode61 remove_diacritics 2`),
  grafo mecánico (aristas "menciona-a" por FTS con nombres de expediente,
  "nombre-similar" por token compartido). Lock por PID en _meta/sync.pid.
- `build_brain.py` — regenera INDEX.md y los .md de expedientes dirty en
  C:\dtr-brain\brain\, borra huérfanos, exporta graph.json.
- `server.py` — MCP `dtr-mercantil` (SDK mcp 2.x: `MCPServer`, no FastMCP).
  Tools: buscar_documentos, leer_documento, ver_documento (renderiza PDF
  como imagen con pymupdf), leer_expediente, vecinos_expediente,
  documentos_recientes, resolver_ruta, indice_cerebro, estado_sync.
  Los enlaces apuntan a http://localhost:8765/abrir?id=N (Claude Desktop
  bloquea file://).
  Dos modos de arranque: `python server.py` (stdio, uso local/Citrix en este
  servidor) o `python server.py --http` (streamable-http en `0.0.0.0:8766`,
  para que PCs de oficina lo usen desde su Claude Desktop normal como
  conector remoto `http://10.80.152.3:8766/mcp` — ver `start_mcp_http.bat`
  y el repo `FrontieraLabs/dtr-mcp-setup`). Decisión explícita del usuario:
  sin autenticación, acceso abierto a quien llegue por red (ver pendiente
  de RGPD abajo, ya existía antes de esto). Los enlaces `abrir`/`carpeta` de
  arriba NO funcionan para los usuarios remotos del modo `--http` (abrirían
  el archivo en el servidor, no en su PC) — limitación conocida, sin
  resolver todavía.
- `estado_server.py` — visualizador local puerto 8765: / (estado), /grafo
  (canvas interactivo), /abrir y /carpeta (abren archivos de K:, validado
  contra path traversal). Autoarranque: carpeta Inicio del usuario.
- `run_sync.bat` — sync+build con log en C:\dtr-brain\brain\_meta\sync.log.
  Tarea programada "DTR-Brain-Sync" diaria 06:00 (modo solo-interactivo).

## Entorno (peculiar)
- Python 3.12 portable en `tools\python312` (zip NuGet: el hosting bloquea
  MSI y no hay admin ni winget). Venv del proyecto en `.venv`.
- El python.exe del venv lanza el intérprete base como proceso hijo.
- `os.kill(pid, 0)` NO sirve en Windows para chequear procesos: usar
  `dtr_common.pid_vivo()` (OpenProcess/WaitForSingleObject).
- pypdf puede emitir surrogates UTF-16 inválidos → `_limpia()` los sanea
  antes de SQLite. Bajo pythonw no hay stdout (guardar con `if sys.stdout`).
- MCP registrado en: `.mcp.json` (Claude Code, esta carpeta) y
  `%APPDATA%\Claude\claude_desktop_config.json` (Claude Desktop, toda la
  máquina). Ambos por máquina, independientes de la cuenta de Claude.

## Pendientes conocidos
- OCR de 35.296 PDFs escaneados (fase 2).
- Extracción de 19.5k .doc antiguos (necesitaría conversor).
- Enriquecimiento tipo Graphiti con `claude -p` bajo suscripción (fase 2).
- El MCP no distingue usuarios: expone todo K: (relevante para murallas
  chinas / RGPD; se puede añadir lista de exclusión en config.py). Con el
  modo `--http` (2026-10-04) esto aplica también a cualquiera que llegue por
  red de oficina, no solo a quien tenga sesión en este servidor — decisión
  explícita del usuario de no restringirlo por ahora.
- Arreglar los enlaces `abrir`/`carpeta` para el modo `--http` (hoy asumen
  que cliente y servidor son la misma máquina; para PCs de oficina remotos
  habría que separar un "abridor" ligero que corra localmente en cada PC).
- Registrar `start_mcp_http.bat` como autoarranque (carpeta Inicio o tarea
  programada) quedó pendiente: un classifier de seguridad bloqueó escribir
  en la carpeta Inicio desde la sesión de Claude Code. Hoy el servidor
  `--http` solo sigue vivo mientras no se reinicie/cierre sesión a mano;
  falta que alguien copie `start_mcp_http.bat` a la carpeta Inicio del
  usuario (o cree una tarea programada) para que sobreviva a un reinicio.

## Para el proyecto de Claude Desktop
Las instrucciones del Proyecto (por cuenta) están en `PROMPT-PROYECTO.md`.
