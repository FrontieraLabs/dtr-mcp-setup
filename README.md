# dtr-mcp-setup

Setup de configuración de los conectores MCP del despacho DTR para una cuenta
de usuario **nueva** en esta misma máquina. No instala los sistemas desde
cero: ambos ya corren como instalación compartida en este servidor; este repo
solo registra los dos conectores en el `claude_desktop_config.json` del
usuario que ejecuta el script (ese fichero es por-usuario, en `%APPDATA%`).

## Conectores

1. **dtr-mercantil** — cerebro documental (K:, 1.033 expedientes, 148k docs).
   Instalación compartida en `E:\Users\aaron_dtr\Desktop\brain-DTR`. El script
   solo verifica que existe y registra el comando; nunca la reinstala (está
   atada a datos de K: y al índice ya construido — ver `MIGRACION.md` de ese
   proyecto).
2. **poder-judicial** — jurisprudencia CENDOJ
   ([mclaramunt/PoderJudicialMCPServer](https://github.com/mclaramunt/PoderJudicialMCPServer),
   MIT). Instalación compartida en `E:\Users\aaron_dtr\Desktop\mcp-poder-judicial`.
   Si esa carpeta no existe (p. ej. en una máquina de reemplazo), el script la
   instala desde cero: descarga el zip de GitHub (esta máquina no tiene git),
   crea un venv con el Python 3.12 portable de `brain-DTR\tools\python312` y
   pinea `mcp[cli]<2` (ver "Trampas conocidas" abajo).

## Uso

```powershell
# 1. Cierra Claude Desktop (menú de la app, no Task Manager) antes de ejecutar.
# 2. Desde una cuenta de usuario nueva, en PowerShell:
.\setup.ps1
# 3. Reabre Claude Desktop. Los dos conectores deben aparecer en la lista.
```

El script es idempotente: se puede volver a ejecutar sin romper nada. Hace
una copia de seguridad de `claude_desktop_config.json` antes de tocarlo
(`claude_desktop_config.json.bak-<fecha>`).

**Importante:** el script debe ejecutarse con Claude Desktop **cerrado**. Si
está abierto, la propia app puede volver a guardar su `claude_desktop_config.json`
desde el estado que tiene en memoria y pisar el registro de los conectores
(nos pasó durante el desarrollo de este setup). El script detecta si la app
está abierta y avisa.

## Prerrequisitos de esta máquina (peculiares)

- Sin admin, sin `winget`, y el hosting **bloquea instaladores MSI**.
- No hay `git`, `node`, `pipx` ni `uv` instalados globalmente — por eso
  `poder-judicial` se instala descargando el zip por `codeload.github.com` en
  vez de `pipx run --spec git+...` (lo que indica el README de ese repo).
- Hay un Python 3.12 portable ya vendorizado en
  `brain-DTR\tools\python312` — se reutiliza para crear el venv de
  `poder-judicial` en vez de depender de un Python del sistema.

## Trampas conocidas (no se deducen del código)

1. `poder-judicial` declara `mcp[cli]>=1.9.2` sin tope superior; pip trae la
   serie 2.x, donde `FastMCP` ya no existe (`ModuleNotFoundError:
   mcp.server.fastmcp`). El script fuerza `pip install "mcp[cli]<2"` después
   de instalar el paquete.
2. El buscador del CENDOJ (`poderjudicial.es/search/**`) devuelve 403 desde
   este servidor (bloqueo por IP de datacenter, no arreglable desde aquí).
   El MCP arranca y expone sus tools igualmente; `search` solo funcionará
   desde la red de la oficina o un equipo normal.

## Varios ordenadores (PCs de oficina, no solo el servidor central)

Este repo sirve para dos escenarios distintos:

1. **Nueva cuenta de Windows en el servidor central** (donde ya corren K:, el
   índice y `brain-DTR`): `setup.ps1` registra los dos conectores sin instalar
   nada nuevo.
2. **PC físico distinto en la oficina**: aunque la unidad K: esté montada
   igual en todos los equipos, el *índice* de dtr-mercantil (2 GB de SQLite
   construido por la sincronización diaria de las 06:00) solo vive en el
   servidor central — no tiene sentido ni está soportado reconstruirlo en
   cada PC. En estos equipos `setup.ps1` detecta que `brain-DTR` no existe,
   **omite dtr-mercantil sin error** y solo instala y registra
   `poder-judicial` (que no depende de nada local y es igual de válido en
   cualquier máquina; de hecho, al tener IP de oficina en vez de IP de
   datacenter, es probable que aquí el buscador del CENDOJ sí funcione).

Hacer que un PC de oficina también pueda usar dtr-mercantil requeriría
exponerlo en red desde el servidor central (en vez de un proceso local por
stdio) — es un cambio de arquitectura aparte, con una implicación de
seguridad/RGPD ya anotada como pendiente en `CLAUDE.md` del proyecto
(`dtr-mercantil` no distingue usuarios y expone todo K:). No está hecho aquí.

La tarea de Cowork "Alta de usuario: conectores MCP" que acompaña a este
repo vive solo en la cuenta/máquina donde se creó — no se replica sola a
otros PCs. Para un PC de oficina, el flujo es simplemente clonar este repo
y ejecutar `setup.ps1` desde una terminal normal, sin pasar por Cowork.

## Pendiente (siguiente paso, fuera de este repo)

Decidir si merece la pena exponer dtr-mercantil en red para los PCs de
oficina, y si es así, resolver también que los enlaces `http://localhost:8765/abrir`
de `estado_server.py` asumen que cliente y servidor son la misma máquina.
