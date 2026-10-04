#Requires -Version 5.1
<#
Registra los conectores MCP dtr-mercantil y poder-judicial para el usuario
actual. Ver README.md para contexto y trampas conocidas.
#>

param(
    [string]$DtrMercantilRoot = "E:\Users\aaron_dtr\Desktop\brain-DTR",
    [string]$DtrMercantilHttpUrl = "http://10.80.152.3:8766/mcp",
    [string]$PoderJudicialRoot = "E:\Users\aaron_dtr\Desktop\mcp-poder-judicial",
    [string]$PoderJudicialVendoredSource = (Join-Path $PSScriptRoot "servers\poder-judicial"),
    [string]$PoderJudicialZipUrl = "https://codeload.github.com/mclaramunt/PoderJudicialMCPServer/zip/refs/heads/main"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "    AVISO: $msg" -ForegroundColor Yellow }

# --- 0. Claude Desktop debe estar cerrado: si está abierto, autoguarda sus
#        preferencias por encima de este fichero y pierde el registro. ---
Write-Step "Comprobando que Claude Desktop esté cerrado"
$abiertos = Get-Process -Name "claude" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "C:\Program Files\Claude\*" }
if ($abiertos) {
    Write-Warn2 "Claude Desktop sigue abierto ($($abiertos.Count) procesos). Ciérralo desde su propio menú (no Task Manager) y vuelve a ejecutar este script."
    exit 1
}
Write-Ok "Claude Desktop no está corriendo"

# --- 1. dtr-mercantil: solo verificar, nunca reinstalar (instalación compartida atada a K:). ---
Write-Step "Verificando dtr-mercantil"
$dtrPython = Join-Path $DtrMercantilRoot ".venv\Scripts\python.exe"
$dtrServer = Join-Path $DtrMercantilRoot "server.py"
$dtrOk = (Test-Path $dtrPython) -and (Test-Path $dtrServer)
if ($dtrOk) {
    Write-Ok "Instalación encontrada en $DtrMercantilRoot"
} else {
    Write-Warn2 "No se encontró $DtrMercantilRoot: no se registrará dtr-mercantil. Esto es NORMAL en un PC de oficina (dtr-mercantil solo vive en el servidor central, atado al índice ya construido sobre K: — no es instalable aquí). Si esta máquina DEBERÍA ser el servidor central y el aviso te sorprende, revisa la ruta con -DtrMercantilRoot o consulta MIGRACION.md de ese proyecto."
}

# --- 2. poder-judicial: instalar desde cero si no existe. ---
Write-Step "Verificando poder-judicial"
$pjPython = Join-Path $PoderJudicialRoot ".venv\Scripts\python.exe"
$pjExe = Join-Path $PoderJudicialRoot ".venv\Scripts\poder-judicial-mcp.exe"
$pjOk = (Test-Path $pjPython) -and (Test-Path $pjExe)

if ($pjOk) {
    Write-Ok "Instalación encontrada en $PoderJudicialRoot"
} else {
    Write-Step "poder-judicial no está instalado: instalando en $PoderJudicialRoot"

    if (Test-Path $PoderJudicialRoot) {
        Write-Warn2 "La carpeta $PoderJudicialRoot existe pero está incompleta. Revisa manualmente antes de continuar."
        exit 1
    }

    # 2a. Conseguir el código: preferir la copia vendorizada en este mismo
    #     repo (servers\poder-judicial) y solo si no está, descargar el zip
    #     del repo original (esta máquina no tiene git de sistema).
    if (Test-Path (Join-Path $PoderJudicialVendoredSource "pyproject.toml")) {
        Write-Host "    Copiando código vendorizado de $PoderJudicialVendoredSource"
        Copy-Item $PoderJudicialVendoredSource $PoderJudicialRoot -Recurse
    } else {
        $tmpZip = Join-Path $env:TEMP "poder-judicial-mcp.zip"
        $tmpExtract = Join-Path $env:TEMP "poder-judicial-mcp-extract"
        Write-Host "    No hay copia vendorizada local; descargando $PoderJudicialZipUrl"
        Invoke-WebRequest -Uri $PoderJudicialZipUrl -OutFile $tmpZip -UseBasicParsing

        if (Test-Path $tmpExtract) { Remove-Item $tmpExtract -Recurse -Force }
        Expand-Archive -Path $tmpZip -DestinationPath $tmpExtract -Force

        $extractedSubdir = Get-ChildItem $tmpExtract -Directory | Select-Object -First 1
        Move-Item $extractedSubdir.FullName $PoderJudicialRoot
        Remove-Item $tmpZip -Force
        Remove-Item $tmpExtract -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Ok "Código listo en $PoderJudicialRoot"

    # 2b. Elegir intérprete base para el venv: el Python 3.12 portable de
    #     brain-DTR si estamos en el servidor central, si no el 'python' del
    #     PATH (caso normal en un PC de oficina con Python ya instalado).
    $portablePython = Join-Path $DtrMercantilRoot "tools\python312\python.exe"
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if (Test-Path $portablePython) {
        $baseInterpreter = $portablePython
    } elseif ($systemPython) {
        $baseInterpreter = $systemPython.Source
    } else {
        Write-Warn2 "No hay Python disponible (ni el portable de brain-DTR ni 'python' en el PATH). Instala Python 3.12+ en este equipo y vuelve a ejecutar el script."
        exit 1
    }

    Write-Host "    Creando venv con $baseInterpreter"
    & $baseInterpreter -m venv (Join-Path $PoderJudicialRoot ".venv")

    # 2c. Instalar el paquete y, SIEMPRE, pinear mcp<2 después (trampa 1 del README).
    & $pjPython -m pip install --upgrade pip | Out-Null
    & $pjPython -m pip install $PoderJudicialRoot
    & $pjPython -m pip install "mcp[cli]<2"
    Write-Ok "Dependencias instaladas (con mcp<2 pineado)"

    # 2d. Verificación de arranque.
    $check = & $pjPython -c "from mcp.server.fastmcp import FastMCP; print('ok')" 2>&1
    if ($check -notmatch "ok") {
        Write-Warn2 "El server no verificó correctamente: $check"
        exit 1
    }
    Write-Ok "poder-judicial instalado y verificado en $PoderJudicialRoot"
}

# --- 3. Registrar en claude_desktop_config.json del usuario actual. ---
Write-Step "Registrando conectores en claude_desktop_config.json"
$configDir = Join-Path $env:APPDATA "Claude"
$configPath = Join-Path $configDir "claude_desktop_config.json"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null

if (Test-Path $configPath) {
    $backup = "$configPath.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
    Copy-Item $configPath $backup
    Write-Ok "Copia de seguridad: $backup"
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
} else {
    $config = [PSCustomObject]@{}
}

if (-not (Get-Member -InputObject $config -Name "mcpServers" -MemberType NoteProperty)) {
    $config | Add-Member -MemberType NoteProperty -Name "mcpServers" -Value ([PSCustomObject]@{})
}

if ($dtrOk) {
    $config.mcpServers | Add-Member -MemberType NoteProperty -Name "dtr-mercantil" -Force -Value ([PSCustomObject]@{
        command = $dtrPython
        args    = @((Join-Path $DtrMercantilRoot "server.py"))
        env     = [PSCustomObject]@{
            PYTHONPATH       = $DtrMercantilRoot
            PYTHONIOENCODING = "utf-8"
        }
    })
    Write-Ok "dtr-mercantil registrado"
}

$config.mcpServers | Add-Member -MemberType NoteProperty -Name "poder-judicial" -Force -Value ([PSCustomObject]@{
    command = $pjExe
    args    = @()
    env     = [PSCustomObject]@{
        PYTHONIOENCODING = "utf-8"
    }
})
Write-Ok "poder-judicial registrado"

$json = $config | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($configPath, $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "Guardado: $configPath"

if ($dtrOk) {
    Write-Step "Listo. Abre Claude Desktop y comprueba en Conectores que aparecen dtr-mercantil y poder-judicial."
} else {
    Write-Step "poder-judicial registrado. Para dtr-mercantil (PC de oficina, no servidor central):"
    Write-Host "    Añade manualmente un conector remoto en Claude Desktop:"
    Write-Host "    Configuración -> Conectores -> Añadir conector personalizado"
    Write-Host "    URL: $DtrMercantilHttpUrl  (sin autenticación)"
    Write-Host "    Nota: los enlaces 'abrir archivo'/'abrir carpeta' que devuelva no abrirán nada en este PC (limitación conocida)."
}
