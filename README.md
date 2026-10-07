# dtr-mcp-setup

Código y setup de los tres conectores MCP del despacho DTR: `dtr-mercantil`
(cerebro documental interno), `poder-judicial` (jurisprudencia CENDOJ,
[mclaramunt/PoderJudicialMCPServer](https://github.com/mclaramunt/PoderJudicialMCPServer),
MIT) y `kabiku` (facturación, vía Playwright). El código vive vendorizado en
`servers/` — sobre todo para que `dtr-mercantil` tenga por fin una copia de
seguridad con historial (antes no estaba en ningún repo).

`poder-judicial` y `kabiku` se instalan **por máquina**: `setup.ps1` usa por
defecto `$env:USERPROFILE\Desktop\...`, así que funciona igual en el servidor
central que en cualquier PC de oficina, con cualquier cuenta de Windows.
`dtr-mercantil` es la excepción: su ruta está fijada a propósito al servidor
central (ver "PCs de oficina" más abajo) y nunca se instala en otra máquina.

```
servers/
  dtr-mercantil/          código de brain-DTR (sin .venv ni tools/, que son
                           entorno local de ese servidor, no código)
  dtr-mercantil-remoto/   proxy MCP local (stdio) que habla HTTPS con el
                           servidor central, para PCs de oficina
  poder-judicial/         código del MCP de CENDOJ (sin .venv)
  kabiku/                 código del MCP de facturación (sin .venv)
setup.ps1                 registra los conectores para un usuario/PC nuevo
```

## Los cuatro componentes

1. **dtr-mercantil** — cerebro documental (K:, 1.033 expedientes, 148k docs).
   Solo tiene sentido ejecutarlo en el servidor central, atado al índice SQLite
   ya construido allí (2 GB, sync diaria de las 06:00) — `setup.ps1` nunca lo
   instala, solo verifica si ya existe en `E:\Users\aaron_dtr\Desktop\brain-DTR`
   y registra el comando si es así.
   Desde 2026-10-04 también corre en modo red (`server.py --http`,
   streamable-http por HTTPS en `0.0.0.0:8766`, certificado autofirmado en
   `certs/`, solo la parte pública vendorizada — la clave privada nunca sale
   del servidor central). Sin autenticación de usuario — decisión explícita
   del despacho.
2. **dtr-mercantil-remoto** — el componente que de verdad usan los PCs de
   oficina para hablar con dtr-mercantil. **No es** un "conector remoto por
   URL" de Claude Desktop — probamos eso y no funciona, ver "Trampas
   conocidas" — es un MCP local normal (stdio, como los otros) cuyas tools
   simplemente reenvían cada llamada por HTTPS a `https://10.80.152.3:8766/mcp`
   usando la red del propio PC. El certificado de confianza va incrustado en
   el código (no hace falta tocar el almacén de certificados de Windows).
   Limitación conocida: los enlaces "abrir archivo"/"abrir carpeta" abren el
   fichero en el servidor central, no en la pantalla del usuario.
3. **poder-judicial** — no depende de nada local; `setup.ps1` lo instala en
   cualquier máquina si no existe ya, usando la copia vendorizada de
   `servers/poder-judicial` (sin red) o, si no la encuentra, descargando el
   zip del repo original.
4. **kabiku** — facturación (Kabiku), vía Playwright porque no tiene API
   pública. Se instala en cualquier máquina igual que `poder-judicial`.
   Necesita `KABIKU_USERNAME`/`KABIKU_PASSWORD` por variable de entorno (ver
   `servers/kabiku/README.md`) — si faltan, se instala pero no se registra el
   conector.

## Uso (servidor central o cualquier PC)

```powershell
# 1. Cierra Claude Desktop (menú de la app, no Task Manager) antes de ejecutar.
# 2. En PowerShell:
.\setup.ps1
# 3. Reabre Claude Desktop y comprueba en Conectores.
```

El script es idempotente y hace copia de seguridad de `claude_desktop_config.json`
antes de tocarlo (`claude_desktop_config.json.bak-<fecha>`).

**Importante:** el script debe ejecutarse con Claude Desktop **cerrado**. Si
está abierto, la propia app puede volver a guardar `claude_desktop_config.json`
desde su estado en memoria y pisar el registro (nos pasó de verdad durante el
desarrollo de este setup). El script detecta si la app está abierta y avisa.

## PCs de oficina (sin Citrix, Claude Desktop normal)

`setup.ps1` detecta solo si `brain-DTR` NO existe localmente (caso normal en
un PC de oficina) y entonces:
- instala y registra `poder-judicial` localmente, como en cualquier máquina;
- **no** intenta registrar `dtr-mercantil` por comando local (no tiene
  sentido: el índice no vive ahí);
- instala y registra `dtr-mercantil-remoto` (el proxy local que habla HTTPS
  con el servidor central) bajo el nombre `dtr-mercantil` en
  `claude_desktop_config.json` — para Claude Desktop es indistinguible de
  tener dtr-mercantil local.

Para que esto funcione, el PC de oficina necesita alcanzar
`10.80.152.3:8766` por su propia red (la de la oficina, no internet). Si no
responde, lo más probable es que el proceso `--http` del servidor central no
esté levantado — depende de que alguien haya copiado
`servers/dtr-mercantil/start_mcp_http.bat` a la carpeta Inicio de ese
servidor (quedó pendiente, ver más abajo).

La tarea de Cowork "Alta de usuario: conectores MCP" que acompaña a este repo
vive solo en la cuenta/máquina donde se creó — no se replica sola a otros
PCs. Para un PC de oficina, el flujo es clonar este repo y ejecutar
`setup.ps1` desde una terminal normal, sin pasar por Cowork.

## Prerrequisitos del servidor central (peculiares)

- Sin admin, sin `winget`, y el hosting **bloquea instaladores MSI**.
- No tenía `git` de sistema — se instaló MinGit portable en
  `brain-DTR\tools\git`.
- Hay un Python 3.12 portable vendorizado en `brain-DTR\tools\python312`,
  reutilizado para crear venvs sin depender de un Python de sistema.
- Un PC de oficina normal no tiene estas restricciones: `setup.ps1` usa el
  `python` del PATH si no encuentra el portable de brain-DTR.

## Trampas conocidas (no se deducen del código)

1. `poder-judicial` declara `mcp[cli]>=1.9.2` sin tope superior; pip trae la
   serie 2.x, donde `FastMCP` ya no existe (`ModuleNotFoundError:
   mcp.server.fastmcp`). El script fuerza `pip install "mcp[cli]<2"` después
   de instalar el paquete.
2. El buscador del CENDOJ (`poderjudicial.es/search/**`) devuelve 403 desde
   el servidor central (bloqueo por IP de datacenter, no arreglable desde
   ahí). Desde un PC de oficina normal debería funcionar.
3. `dtr-mercantil` no distingue usuarios: expone todo K: a quien tenga el
   conector, local o remoto. Ya estaba anotado como pendiente de RGPD/murallas
   chinas antes de este setup; el modo `--http` lo amplía a toda la red de
   oficina. Decisión explícita del despacho, no un descuido.
4. **Los "conectores remotos por URL" de Claude Desktop no sirven para esto**
   (lo probamos y falló con errores de conexión incluso probando desde el
   propio servidor donde corre el servicio): esos conectores los conecta la
   nube de Anthropic, no el ordenador del usuario, y una IP privada tipo
   `10.80.152.3` no es alcanzable desde internet por definición — ningún
   cambio de firewall local lo arregla. La solución real es
   `dtr-mercantil-remoto` (proxy local, stdio), no un conector por URL. La
   alternativa oficial de Anthropic para este caso es "MCP Tunnels", pero
   está en research preview solo para cuentas Enterprise.
5. En `server.py --http`, **no llames a tu variable `config`** si el módulo
   `config.py` del proyecto ya ocupa ese nombre a nivel global — `config =
   uvicorn.Config(...)` pisa el `import config` y rompe TODAS las tools que
   lean `config.algo` (p. ej. `estado_sync` fallaba con `'Config' object has
   no attribute 'DB_PATH'`). Pasó de verdad; usa `uvicorn_config` o similar.

## Pendiente

- Registrar `servers/dtr-mercantil/start_mcp_http.bat` como autoarranque en
  el servidor central (carpeta Inicio o tarea programada). Un classifier de
  seguridad de Claude Code bloqueó hacerlo desde la sesión que montó esto;
  falta que alguien lo copie a mano a la carpeta Inicio del usuario del
  servidor.
- Arreglar los enlaces `abrir`/`carpeta` para los usuarios remotos del modo
  `--http` (hoy asumen que cliente y servidor son la misma máquina; haría
  falta un "abridor" ligero corriendo localmente en cada PC, ya que K: está
  montada igual en todos).
- Mantener sincronizado `servers/` con los originales cuando cambien
  (`brain-DTR` y `mcp-poder-judicial` en el servidor central) — hoy es una
  copia manual, no automática.
