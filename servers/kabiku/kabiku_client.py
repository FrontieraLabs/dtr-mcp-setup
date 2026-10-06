# kabiku_client.py — automatizacion de navegador (Playwright, API async —
# el servidor MCP ya corre dentro de un bucle asyncio, así que la API sync
# de Playwright no vale aquí) contra el Portal del Cliente de Kabiku
# (app.kabiku.es). Kabiku no tiene API publica: es una app Django clasica
# (formularios server-side + CSRF + formsets), asi que se conduce como lo
# haria una persona.
import os
import re
from urllib.parse import urlencode

from playwright.async_api import async_playwright

BASE_URL = "https://app.kabiku.es"


def _credenciales():
    usuario = os.environ.get("KABIKU_USERNAME")
    password = os.environ.get("KABIKU_PASSWORD")
    if not usuario or not password:
        raise RuntimeError(
            "Faltan KABIKU_USERNAME / KABIKU_PASSWORD en el entorno. "
            "Configuralas en el 'env' del conector (claude_desktop_config.json) "
            "o en un .env local; nunca las escribas en el codigo.")
    return usuario, password


class SesionKabiku:
    """Un login por instancia; usar como contexto asincrono:
    async with SesionKabiku() as k:
        await k.crear_factura(...)
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw = None
        self._browser = None
        self._page = None

    async def __aenter__(self):
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        self._page = await self._browser.new_page()
        await self._login()
        return self

    async def __aexit__(self, *exc):
        await self._browser.close()
        await self._pw.stop()

    async def _login(self):
        usuario, password = _credenciales()
        page = self._page
        await page.goto(f"{BASE_URL}/")
        await page.fill("#id_username", usuario)
        await page.fill("#id_password", password)
        await page.click("button[type=submit]")
        await page.wait_for_load_state("networkidle")
        if await page.locator("#id_username").count() > 0:
            # Seguimos en el formulario de login: credenciales rechazadas.
            raise RuntimeError(
                "Login en Kabiku rechazado (usuario/contrasena incorrectos "
                "o cuenta bloqueada). Revisa KABIKU_USERNAME/KABIKU_PASSWORD.")

    # --- Crear factura ---------------------------------------------------
    async def crear_factura(self, cliente: str, lineas: list[dict],
                            referencia: str = "", fecha_operacion: str = "",
                            observaciones: str = "", emitir: bool = False) -> dict:
        """cliente: texto a buscar en el desplegable de destinatarios
        (razon social o NIF; debe existir ya como contacto en Kabiku — ver
        /contactos/contactos/). lineas: lista de dicts con
        {descripcion, cantidad, importe_unitario, iva_pct (opcional, % IVA
        de esa linea)}. fecha_operacion: DD/MM/AAAA (formato del propio
        formulario); vacio = la que proponga Kabiku por defecto.
        emitir=False (por defecto) guarda como BORRADOR, revisable y
        corregible desde el propio Kabiku antes de emitir. emitir=True pulsa
        "Emitir": en facturacion espanola esto normalmente ya no se puede
        deshacer (solo rectificar con otra factura) por la normativa
        Veri*Factu/TicketBAI — usar con conocimiento de causa, nunca por
        defecto."""
        page = self._page
        await page.goto(f"{BASE_URL}/facturador/facturas/create/")
        await page.wait_for_load_state("networkidle")

        await self._seleccionar_destinatario(cliente)

        for i, linea in enumerate(lineas):
            if i > 0:
                await page.click("a:has-text('Añadir linea')")
            prefijo = f"lineas-{i}-"
            await page.fill(f"#id_{prefijo}descripcion", linea["descripcion"])
            await page.fill(f"#id_{prefijo}cantidad", str(linea["cantidad"]))
            await page.fill(f"#id_{prefijo}importe_unitario",
                           str(linea["importe_unitario"]))
            if "iva_pct" in linea:
                await page.fill(f"#id_{prefijo}porcentaje_tipo_impositivo",
                               str(linea["iva_pct"]))

        if referencia:
            await page.fill("#id_factura-referencia", referencia)
        if fecha_operacion:
            await page.fill("#fecha_operacion", fecha_operacion)
        if observaciones:
            await page.fill("#id_factura-observaciones", observaciones)

        boton = "Emitir" if emitir else "Guardar borrador"
        await page.click(f"button:has-text('{boton}')")
        await page.wait_for_load_state("networkidle")

        # Tras guardar, Kabiku redirige al listado o a la ficha; intentamos
        # extraer el identificador de la URL resultante (p.ej. .../read/N).
        m = re.search(r"/facturas/(?:read|update)/(\d+)", page.url)
        return {
            "estado": "emitida" if emitir else "borrador",
            "id": m.group(1) if m else None,
            "url": page.url,
        }

    async def _seleccionar_destinatario(self, cliente: str):
        page = self._page
        select = page.locator("#id_destinatario-search")
        opciones = await select.locator("option").all_text_contents()
        cliente_norm = cliente.strip().lower()
        candidatos = [o for o in opciones if cliente_norm in o.lower()]
        if not candidatos:
            raise ValueError(
                f"Ningun contacto de Kabiku coincide con '{cliente}'. "
                f"Tiene que existir ya en /contactos/contactos/ (este MCP no "
                f"crea contactos nuevos).")
        if len(candidatos) > 1:
            raise ValueError(
                f"'{cliente}' es ambiguo, coincide con varios contactos: "
                f"{candidatos[:10]}. Usa un texto mas especifico (p.ej. el NIF).")
        await select.select_option(label=candidatos[0])

    # --- Leer facturas -----------------------------------------------------
    async def leer_facturas(self, desde: str = "", hasta: str = "",
                            estado: str = "", limite: int = 30) -> list[dict]:
        """desde/hasta: DD/MM/AAAA (fecha emision = 'fecha_expedicion' en
        Kabiku). estado: 'borrador', 'emitida' o 'anulada' (vacio = todos).
        Devuelve filas de la tabla de /facturador/facturas/ tal cual las
        muestra Kabiku."""
        page = self._page
        per_page = next((v for v in (10, 20, 50, 100) if limite <= v), "all")
        params = {"per_page": str(per_page)}
        if desde:
            params["fecha_expedicion_from"] = desde
        if hasta:
            params["fecha_expedicion_to"] = hasta
        if estado:
            params["estado_emision"] = estado
        await page.goto(f"{BASE_URL}/facturador/facturas/?{urlencode(params)}")
        await page.wait_for_load_state("networkidle")

        filas = []
        for row in await page.locator("table tbody tr").all():
            celdas = [c.strip() for c in await row.locator("td").all_inner_texts()]
            if not celdas or not any(celdas):
                continue
            link_ver = row.locator("a:has-text('Ver')")
            factura_id = None
            if await link_ver.count() > 0:
                href = await link_ver.get_attribute("href") or ""
                m = re.search(r"/read/(\d+)", href)
                factura_id = m.group(1) if m else None
            filas.append({"id": factura_id, "celdas": celdas})
        return filas
