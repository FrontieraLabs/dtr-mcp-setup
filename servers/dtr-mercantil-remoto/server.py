# server.py — proxy MCP local para dtr-mercantil.
#
# Por que existe: el conector remoto "por URL" de Claude Desktop lo conecta
# la nube de Anthropic, no el ordenador del usuario — por eso una URL con IP
# privada (https://10.80.152.3:8766/mcp) nunca responde desde ahi, por mucho
# que la red de oficina sea capaz de alcanzarla directamente.
#
# Este proxy evita el problema: es un MCP local de toda la vida (stdio,
# igual que poder-judicial/kabiku), que Claude Desktop ejecuta en el PC del
# usuario. Dentro, cada tool simplemente hace una llamada MCP por HTTPS a
# dtr-mercantil (servidor central) usando la red del propio PC — la misma
# red que ya confirmasteis que SI llega a 10.80.152.3.
import base64
import os
import ssl

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.fastmcp import FastMCP, Image
import httpx

REMOTE_URL = os.environ.get("DTR_MERCANTIL_URL", "https://10.80.152.3:8766/mcp")

# Certificado publico (autofirmado) de dtr-mercantil, incrustado aqui para no
# depender de ficheros extra al empaquetar/instalar este proxy. Es solo la
# parte publica — nunca una clave privada.
CERT_PEM = """-----BEGIN CERTIFICATE-----
MIIDGzCCAgOgAwIBAgIUD+Hq7w/OHG4+D1IMhTJ4YmtbQh8wDQYJKoZIhvcNAQEL
BQAwKDEmMCQGA1UEAwwdZHRyLW1lcmNhbnRpbC5idWZldGVkdHIubG9jYWwwHhcN
MjYxMDA1MjM1MDM2WhcNMzExMDA1MjM1MDM2WjAoMSYwJAYDVQQDDB1kdHItbWVy
Y2FudGlsLmJ1ZmV0ZWR0ci5sb2NhbDCCASIwDQYJKoZIhvcNAQEBBQADggEPADCC
AQoCggEBALvGsxlzFmkuTOC1/ysNWGgVB0OIeocBwHpouqK/Nlzd1M8Aifam/Hs3
DnsB/a8ka7miWxjM7k7Ju1cvQoL0RWz7lPe4IaB3mr39BFFvDZMh5ZaCDZJp3gm4
vJ3wYQC188cIsyaJIwoTS14H9t0ZB4xMD0Yh53txvwTheMJcqxXtcPbLDaDh+AC1
ZdKcVVpm54sVryHRiyYJ81iMWguZv1ild0/E3e0Ban6es5A+rCHqxmh3RTcxSWjX
ljVtw1PpSIDjbYYsVROiY/q9VMrbi3zdCYeJR0V3J5i7QLdae9lvivx6Z+YWIILa
6QP7qnb6QIdcw69VXkwoBqdLZi/SjkMCAwEAAaM9MDswKAYDVR0RBCEwH4cEClCY
A4IGRFRSLUlBgglsb2NhbGhvc3SHBH8AAAEwDwYDVR0TAQH/BAUwAwEB/zANBgkq
hkiG9w0BAQsFAAOCAQEAGuaa2tJSrUjhKl9lhs0w4LOf76Skm6BYyU+pq4y7wMek
wQZAJYBy2sVpzkuuZr9QFVWbj0jKUlW6esOFCzJyM1IG6+i4KDKawnYf+y+MvfPv
4gbuH5TzAUKDbfDr2lEGVV73/Rnjr4owWQYUDmE9GqUZqrRO5vzsBwSBpKtNEKLX
3hvyqWTBawfJ+obnHLwowJBauaepsntZppQAKk7NHIeLRXB+P5AXyRqVAcuBi7OC
n4dbc23e6mhkzE9ce+WJ/GVgEE6fCDHGrehiatgND0qx1ABNSm9Izh1Bbqvq7pVm
nBPt8mTL3OO9RxRgblgTI1SXQlunJMurzMRDMwMsag==
-----END CERTIFICATE-----
"""

INSTRUCCIONES = """Cerebro documental del despacho DTR (unidad K:, sistema
MERCANTIL), accedido en red desde el servidor central. Mismas tools e
instrucciones que la instalacion local; ver ahi para el detalle de uso.

REGLA DE FORMATO OBLIGATORIA al citar cualquier documento: la ruta se escribe
SIEMPRE como enlace markdown clicable. Nota: los enlaces 'abrir'/'carpeta'
abren el fichero EN EL SERVIDOR CENTRAL, no en tu PC — es una limitacion
conocida de este modo remoto."""

mcp = FastMCP("dtr-mercantil", instructions=INSTRUCCIONES)


_SSL_CONTEXT = ssl.create_default_context(cadata=CERT_PEM)


def _http_client_factory(headers=None, timeout=None, auth=None):
    return httpx.AsyncClient(headers=headers, timeout=timeout, auth=auth,
                             verify=_SSL_CONTEXT)


async def _forward(nombre: str, **argumentos):
    async with streamablehttp_client(REMOTE_URL, httpx_client_factory=_http_client_factory) as (
        read, write, _get_session_id,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resultado = await session.call_tool(nombre, argumentos)

    if resultado.isError:
        texto = "\n".join(b.text for b in resultado.content if b.type == "text")
        return f"Error de dtr-mercantil (servidor central): {texto or '(sin detalle)'}"

    salida = []
    for bloque in resultado.content:
        if bloque.type == "text":
            salida.append(bloque.text)
        elif bloque.type == "image":
            formato = (bloque.mimeType or "image/png").split("/")[-1]
            salida.append(Image(data=base64.b64decode(bloque.data), format=formato))
    if len(salida) == 1 and isinstance(salida[0], str):
        return salida[0]
    return salida or "(sin contenido)"


@mcp.tool()
async def buscar_documentos(query: str, expediente: str = "", tipo: str = "",
                           limite: int = 20, orden: str = "relevancia") -> str:
    """Búsqueda de texto completo (insensible a acentos y mayúsculas) sobre
    todos los documentos de K:. Filtros opcionales: expediente (nombre o
    slug), tipo (extensión, ej. 'pdf') y orden ('relevancia' o 'fecha').
    Devuelve por hit: documento (id), expediente, fecha, RUTA ABSOLUTA con
    enlace clicable y snippet."""
    return await _forward("buscar_documentos", query=query, expediente=expediente,
                          tipo=tipo, limite=limite, orden=orden)


@mcp.tool()
async def leer_expediente(clave: str, modo: str = "resumen") -> str:
    """Mapa de un expediente (por slug o nombre, admite coincidencia
    parcial). modo='resumen' (por defecto) o modo='completo'."""
    return await _forward("leer_expediente", clave=clave, modo=modo)


@mcp.tool()
async def leer_documento(ruta_o_id: str, desde_char: int = 0) -> str:
    """Devuelve metadatos + texto extraído de un documento, por id numérico,
    ruta absoluta (K:\\...) o ruta relativa. Usa desde_char para paginar
    documentos largos."""
    return await _forward("leer_documento", ruta_o_id=ruta_o_id, desde_char=desde_char)


@mcp.tool()
async def ver_documento(ruta_o_id: str, pagina: int = 1, paginas: int = 1):
    """Muestra un documento VISUALMENTE (renderiza PDF/imagen). pagina =
    primera página; paginas = cuántas (máx. 4)."""
    return await _forward("ver_documento", ruta_o_id=ruta_o_id, pagina=pagina,
                          paginas=paginas)


@mcp.tool()
async def indice_cerebro() -> str:
    """Devuelve INDEX.md: lista maestra de expedientes."""
    return await _forward("indice_cerebro")


@mcp.tool()
async def resolver_ruta(nombre: str, limite: int = 15) -> str:
    """Dado un id o (parte de un) nombre de archivo, devuelve la(s) RUTA(s)
    ABSOLUTA(s) reales en K: con su expediente."""
    return await _forward("resolver_ruta", nombre=nombre, limite=limite)


@mcp.tool()
async def documentos_recientes(dias: int = 14, expediente: str = "",
                               limite: int = 30) -> str:
    """Documentos añadidos o modificados en K: en los últimos N días."""
    return await _forward("documentos_recientes", dias=dias, expediente=expediente,
                          limite=limite)


@mcp.tool()
async def vecinos_expediente(clave: str) -> str:
    """Grafo de relaciones de un expediente."""
    return await _forward("vecinos_expediente", clave=clave)


@mcp.tool()
async def estado_sync() -> str:
    """Estado del cerebro: raíz, última sincronización, documentos por
    estado, expedientes, aristas del grafo y tamaño del índice."""
    return await _forward("estado_sync")


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
