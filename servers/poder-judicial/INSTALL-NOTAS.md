# Notas de instalación — MCP poder-judicial (CENDOJ)

Instalado el 29/09/2026 en `E:\Users\aaron_dtr\Desktop\mcp-poder-judicial`.
Origen: https://github.com/mclaramunt/PoderJudicialMCPServer (MIT), rama `main`.

## Cómo se instaló (y por qué así)

El método del README (`pipx run --spec git+https://…`) **no sirve aquí**: esta
máquina no tiene git, ni node, ni pipx, ni uv. Se hizo:

1. Descarga del zip por codeload (sin git).
2. Copia del código a esta carpeta.
3. Venv propio con el Python 3.12 portable de `brain-DTR\tools\python312`.
4. `pip install .` dentro de ese venv.

**Venv separado a propósito.** No se instaló en el venv de `brain-DTR` por dos
razones: (a) ese venv tiene `mcp` 2.x y este código necesita 1.x (ver abajo);
(b) ambos proyectos tienen un módulo de nivel superior llamado `server.py`, que
colisionaría en el mismo `site-packages`.

## Trampa 1 — hay que pinear `mcp<2`

`pyproject.toml` declara `mcp[cli]>=1.9.2` **sin tope superior**, y pip resuelve
`mcp` 2.2.0, donde `FastMCP` pasó a llamarse `MCPServer`. Con 2.x el server no
arranca:

    ModuleNotFoundError: No module named 'mcp.server.fastmcp'

Solución aplicada (sin tocar el código de terceros): `pip install "mcp[cli]<2"`
en este venv. Instalado: **mcp 1.30.0**.
Si algún día se reinstala o se actualiza, hay que repetir el pin.

## Trampa 2 — el buscador del CENDOJ está bloqueado desde este servidor

Todo el subárbol `https://www.poderjudicial.es/search/**` devuelve **403**
(«Parece que no tiene permisos para acceder al recurso solicitado») desde esta
máquina, mientras el resto del dominio responde 200.

Comprobado que **no** es un problema del paquete ni de cabeceras:
- Falla igual con `requests` y con un navegador real desde esta misma máquina.
- Falla en todas las rutas de `/search/` (`indexAN.jsp`, `search.action`,
  `contenidos.action`, `publicaciones/`, `igualdad/`), no solo en las del MCP.
- El repo no tiene ninguna issue abierta sobre esto.

Conclusión: es un bloqueo por **IP de salida** del hosting (rango de datacenter)
del CGPJ sobre su aplicación de búsqueda. No se ha intentado eludirlo: es un
control de acceso del titular del sitio.

Consecuencia práctica: el MCP arranca y expone sus tools, pero `search` y
`retrieve_judgment_text` devolverán error mientras se ejecuten desde este
servidor. Desde la red de la oficina o un equipo normal debería funcionar.

## Estado verificado

Handshake MCP por stdio OK:

- servidor: `Court Judgments API`, mcp 1.30.0, protocolo 2025-11-25
- tools: `search`, `retrieve_judgment_text`
- resource: `judgment://text/{reference_id}`

## Registro

Entrada `poder-judicial` añadida en:
- `E:\Users\aaron_dtr\Desktop\brain-DTR\.mcp.json` (Claude Code)
- `%APPDATA%\Claude\claude_desktop_config.json` (Claude Desktop; copia previa en
  `claude_desktop_config.json.bak-20260929`)

Comando: `.venv\Scripts\poder-judicial-mcp.exe` (se usa el console script y no
`python server.py` para que no haya ambigüedad con el `server.py` de brain-DTR).

## Comprobación rápida

```powershell
# ¿sigue bloqueado el CENDOJ?  (403 = sí)
(Invoke-WebRequest https://www.poderjudicial.es/search/indexAN.jsp -UseBasicParsing -SkipHttpErrorCheck).StatusCode
# ¿arranca el server?
E:\Users\aaron_dtr\Desktop\mcp-poder-judicial\.venv\Scripts\python.exe -c "from mcp.server.fastmcp import FastMCP; print('ok')"
```
