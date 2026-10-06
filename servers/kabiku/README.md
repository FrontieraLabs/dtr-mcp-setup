# mcp-kabiku

MCP para el Portal del Cliente de Kabiku ([app.kabiku.es](https://app.kabiku.es)),
usado por el despacho para facturación. Alcance deliberadamente limitado:
**solo crear facturas y leer facturas existentes** — nada de editar/borrar.

## Por qué automatización de navegador (Playwright) y no una API

Kabiku ([kabiku.es](https://kabiku.es), producto de Check-it) no tiene API
pública ni sección de desarrolladores. El Portal del Cliente es una app
Django clásica server-side (formularios HTML + CSRF, sin JSON API visible),
así que el MCP la conduce con Playwright igual que lo haría una persona:
login con usuario/contraseña, rellenar el formulario de nueva factura, leer
la tabla de facturas existentes.

## Credenciales

**Nunca se escriben en el código ni en el chat.** Se leen de variables de
entorno en tiempo de ejecución:

- `KABIKU_USERNAME`
- `KABIKU_PASSWORD`

Configúralas en el bloque `env` del conector dentro de
`claude_desktop_config.json` (o `.mcp.json` para Claude Code), no en un
fichero del repo.

## Estado

- `kabiku_client.py`: login, `crear_factura` y `leer_facturas` implementados
  contra los selectores reales de `app.kabiku.es` (formulario Django con
  formsets para líneas/suplidos, desplegable de contactos ya cargado con 441
  opciones, filtros reales del listado).
- **Sin probar de extremo a extremo todavía** — Claude nunca ha ejecutado
  estas funciones (no debía usar tus credenciales ni crear una factura real
  de prueba él mismo). Antes de confiar en esto, prueba tú `crear_factura`
  una vez con `emitir=False` (queda como BORRADOR, se puede borrar desde el
  propio Kabiku con el enlace "Borrar" del listado si era solo una prueba) y
  revisa que el resultado en Kabiku es el esperado.
- `crear_factura` solo selecciona contactos **ya existentes** en
  `/contactos/contactos/` — no crea contactos nuevos.
- "Emitir" en España normalmente no se puede deshacer (normativa
  Veri*Factu/TicketBAI); por eso `crear_factura` guarda borrador por defecto
  y `emitir=True` es un paso explícito aparte.

## Instalación

```powershell
python -m venv .venv
.venv\Scripts\pip install .
.venv\Scripts\playwright install chromium
```

## Trampas conocidas

- Mismo pin que los otros MCPs del despacho: `mcp[cli]<2` (pyproject ya lo
  fija), porque con `mcp` 2.x `FastMCP`/`MCPServer` cambia de sitio.
- Playwright necesita descargar el binario de Chromium la primera vez
  (`playwright install chromium`) — no es un instalador MSI, es un zip, así
  que funciona sin admin.
