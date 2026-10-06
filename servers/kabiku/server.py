# server.py — MCP "kabiku": crear y leer facturas en el Portal del Cliente
# de Kabiku (app.kabiku.es) via automatizacion de navegador (sin API publica).
from mcp.server.fastmcp import FastMCP

from kabiku_client import SesionKabiku

INSTRUCCIONES = """Conector al Portal del Cliente de Kabiku (app.kabiku.es),
usado por el despacho para facturacion. Kabiku no tiene API publica: este
MCP conduce un navegador real (Playwright) para iniciar sesion y operar el
portal, igual que lo haria una persona.

Alcance deliberadamente limitado: SOLO crear facturas y leer facturas
existentes. No edita ni borra facturas ya creadas."""

mcp = FastMCP("kabiku", instructions=INSTRUCCIONES)


@mcp.tool()
async def crear_factura(cliente: str, lineas: list[dict], referencia: str = "",
                        fecha_operacion: str = "", observaciones: str = "",
                        emitir: bool = False) -> str:
    """Crea una factura nueva en Kabiku para un cliente YA EXISTENTE como
    contacto (no crea contactos nuevos).
    cliente: texto para localizar el contacto (razon social o NIF) — si hay
    varias coincidencias, falla y pide ser mas especifico.
    lineas: lista de dicts, uno por linea de factura:
      {"descripcion": str, "cantidad": float, "importe_unitario": float,
       "iva_pct": float (opcional)}
    referencia, fecha_operacion (DD/MM/AAAA), observaciones: opcionales.
    emitir: False (por defecto) guarda como BORRADOR — revisable y
    corregible en Kabiku antes de emitir de verdad. True pulsa "Emitir":
    en Espana esto normalmente ya NO se puede deshacer (solo rectificar
    con otra factura), por la normativa Veri*Factu/TicketBAI. Usar emitir=True
    solo si el usuario lo ha pedido explicitamente para ESA factura."""
    async with SesionKabiku() as k:
        resultado = await k.crear_factura(cliente=cliente, lineas=lineas,
                                          referencia=referencia,
                                          fecha_operacion=fecha_operacion,
                                          observaciones=observaciones,
                                          emitir=emitir)
    return f"Factura creada ({resultado['estado']}), id {resultado['id']}: {resultado['url']}"


@mcp.tool()
async def leer_facturas(desde: str = "", hasta: str = "", estado: str = "",
                        limite: int = 30) -> str:
    """Lista facturas existentes en Kabiku. desde/hasta: DD/MM/AAAA (fecha de
    emision). estado: 'borrador', 'emitida' o 'anulada' (vacio = todos)."""
    async with SesionKabiku() as k:
        filas = await k.leer_facturas(desde=desde, hasta=hasta, estado=estado,
                                      limite=limite)
    if not filas:
        return "Sin facturas para ese filtro."
    out = [f"{len(filas)} factura(s):", ""]
    for f in filas:
        out.append(f"- id {f['id']}: {' | '.join(f['celdas'])}")
    return "\n".join(out)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
