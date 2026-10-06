# server.py — servidor MCP (stdio) del cerebro documental DTR.
# Expone búsqueda FTS (insensible a acentos/mayúsculas), navegación de
# expedientes, grafo de relaciones y resolución de rutas absolutas en K:.
import os
import re
import sys
from datetime import datetime, timedelta
from urllib.parse import quote

import config
from dtr_common import abrir_db, normalizar, human_size, fts_query_desde_texto
from mcp.server.mcpserver import Image, MCPServer

INSTRUCCIONES = """Cerebro documental del despacho DTR (unidad K:, sistema
MERCANTIL): 148k documentos de 1.033 expedientes, indexados con texto completo
(insensible a acentos/mayúsculas) y un grafo de relaciones entre expedientes.

Flujo recomendado:
1. buscar_documentos para localizar contenido (o documentos_recientes para
   novedades); 2. leer_documento para el texto completo de un hit;
3. leer_expediente (modo resumen) para el contexto de un expediente;
4. vecinos_expediente para ver conexiones.

REGLA DE FORMATO OBLIGATORIA al citar cualquier documento: la ruta se escribe
SIEMPRE como enlace markdown clicable, nunca como texto plano. Patrón, dado el
id N del documento:
  [`K:\\ruta\\al\\archivo.pdf`](http://localhost:8765/abrir?id=N)
y opcionalmente ([carpeta](http://localhost:8765/carpeta?id=N)).
Las tools ya devuelven las rutas en ese formato: cópialo tal cual en tu
respuesta. Si solo conoces el id, construye el enlace con el patrón anterior.
Al hacer clic, el archivo se abre en su aplicación nativa en el equipo del
usuario. Una respuesta que cite rutas sin enlace clicable es incorrecta.
Los estados: 'escaneado(ocr?)' = PDF sin capa de texto (no buscable aún);
'sin-extractor' = formato antiguo (.doc/.xls) indexado solo por nombre.
Para VER un documento dentro del chat usa ver_documento(id): renderiza las
páginas como imagen. Es LA herramienta para los 'escaneado(ocr?)': no tienen
texto extraído, pero puedes leerlos visualmente con ella. También sirve para
imágenes (jpg/png/tif) y para comprobar firmas, sellos o maquetación de
cualquier PDF."""

mcp = MCPServer("dtr-mercantil", instructions=INSTRUCCIONES)


def _con():
    return abrir_db(solo_lectura=True)


def _ruta_abs(ruta_rel: str) -> str:
    return os.path.join(config.RAIZ_DATOS, ruta_rel)


ABRIDOR = "http://localhost:8765"


def _link(ruta_rel: str, doc_id=None) -> str:
    """La ruta absoluta ES el enlace clicable (abre el archivo), seguida del
    enlace a su carpeta. Vía el visualizador local, puerto 8765."""
    abs_p = _ruta_abs(ruta_rel)
    if doc_id is not None:
        sufijo = f"id={doc_id}"
    else:
        sufijo = "ruta=" + quote(abs_p, safe="")
    return (f"[`{abs_p}`]({ABRIDOR}/abrir?{sufijo}) "
            f"([carpeta]({ABRIDOR}/carpeta?{sufijo}))")


def _fecha(mtime) -> str:
    try:
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except (OSError, ValueError, TypeError):
        return "?"


def _buscar_expediente(con, clave: str):
    """Resuelve slug exacto, nombre exacto o coincidencia parcial."""
    clave_norm = normalizar(clave).strip()
    row = con.execute("SELECT * FROM expedientes WHERE slug=?",
                      (clave_norm.replace(" ", "-"),)).fetchone()
    if row:
        return row, []
    row = con.execute("SELECT * FROM expedientes WHERE nombre_norm=?",
                      (clave_norm,)).fetchone()
    if row:
        return row, []
    candidatos = con.execute(
        "SELECT * FROM expedientes WHERE nombre_norm LIKE ? OR slug LIKE ? "
        "ORDER BY n_docs DESC LIMIT 10",
        (f"%{clave_norm}%", f"%{clave_norm.replace(' ', '-')}%")).fetchall()
    if len(candidatos) == 1:
        return candidatos[0], []
    return None, candidatos


@mcp.tool()
def buscar_documentos(query: str, expediente: str = "", tipo: str = "",
                      limite: int = 20, orden: str = "relevancia") -> str:
    """Búsqueda de texto completo (insensible a acentos y mayúsculas) sobre
    todos los documentos de K:. Filtros opcionales: expediente (nombre o
    slug), tipo (extensión, ej. 'pdf') y orden ('relevancia' o 'fecha').
    Devuelve por hit: documento (id), expediente, fecha, RUTA ABSOLUTA con
    enlace clicable y snippet."""
    con = _con()
    try:
        q = fts_query_desde_texto(query)
        sql = """
            SELECT d.id, d.expediente, d.nombre, d.ruta_rel, d.ext,
                   d.estado, d.mtime,
                   snippet(fts, 0, '«', '»', ' … ', 14) AS snip,
                   bm25(fts) AS rank
            FROM fts JOIN docs d ON d.id = fts.rowid
            WHERE fts MATCH ?"""
        params = [q]
        if expediente:
            exp, cands = _buscar_expediente(con, expediente)
            if not exp:
                ops = "\n".join(f"- {c['nombre']} (slug: {c['slug']})"
                                for c in cands) or "(ninguno)"
                return f"Expediente '{expediente}' ambiguo o no encontrado. " \
                       f"Candidatos:\n{ops}"
            sql += " AND d.slug = ?"
            params.append(exp["slug"])
        if tipo:
            sql += " AND d.ext = ?"
            params.append("." + tipo.lower().lstrip("."))
        sql += " ORDER BY " + ("d.mtime DESC" if orden == "fecha"
                               else "rank") + " LIMIT ?"
        params.append(max(1, min(int(limite), 100)))
        hits = con.execute(sql, params).fetchall()
        if not hits:
            return (f"Sin resultados para: {query}. Prueba con menos "
                    f"palabras o sinónimos; recuerda que 35k PDFs "
                    f"escaneados aún no tienen texto (falta OCR).")
        out = [f"{len(hits)} resultado(s) para '{query}' "
               f"(orden: {orden}):", ""]
        for h in hits:
            out.append(f"### {h['nombre']}  (id {h['id']})")
            out.append(f"- Expediente: {h['expediente']} · "
                       f"{_fecha(h['mtime'])}")
            out.append(f"- {_link(h['ruta_rel'], h['id'])}")
            out.append(f"- Snippet: {h['snip']}")
            out.append("")
        return "\n".join(out)
    finally:
        con.close()


@mcp.tool()
def leer_expediente(clave: str, modo: str = "resumen") -> str:
    """Mapa de un expediente (por slug o nombre, admite coincidencia
    parcial). modo='resumen' (por defecto): datos, relaciones del grafo y
    los 30 documentos más recientes con enlaces — rápido y compacto.
    modo='completo': el .md íntegro con la tabla de TODOS los documentos
    (puede ser muy largo en expedientes grandes)."""
    con = _con()
    try:
        exp, cands = _buscar_expediente(con, clave)
        if not exp:
            ops = "\n".join(f"- {c['nombre']} (slug: {c['slug']})"
                            for c in cands) or "(ninguno)"
            return f"Expediente '{clave}' no encontrado. Candidatos:\n{ops}"

        if modo == "completo":
            ruta_md = os.path.join(config.EXPEDIENTES_DIR,
                                   f"{exp['slug']}.md")
            try:
                with open(ruta_md, encoding="utf-8") as f:
                    md = f.read()
                if len(md) > 120_000:
                    md = md[:120_000] + ("\n\n[... recortado; usa "
                                         "buscar_documentos con "
                                         f"expediente='{exp['slug']}' para "
                                         "encontrar documentos concretos]")
                return md
            except FileNotFoundError:
                return (f"El .md aún no se generó (slug: {exp['slug']}). "
                        f"Ejecuta run_sync.bat.")

        # modo resumen
        if exp["slug"] == "_raiz":
            base = "`K:\\`"
        else:
            base = _link(os.path.relpath(exp["ruta_abs"], config.RAIZ_DATOS))
        out = [f"# {exp['nombre']}  (slug: {exp['slug']})",
               f"Ruta base: {base}",
               f"{exp['n_docs']} documentos · "
               f"{human_size(exp['size_total'])}", ""]
        por_estado = con.execute(
            "SELECT estado, COUNT(*) n FROM docs WHERE slug=? "
            "GROUP BY estado ORDER BY n DESC", (exp["slug"],)).fetchall()
        out.append("Estados: " + " · ".join(
            f"{r['estado']}: {r['n']}" for r in por_estado))
        out.append("")
        rel = con.execute("""
            SELECT a.*, e.nombre AS otro FROM aristas a
            JOIN expedientes e ON e.slug =
              CASE WHEN a.src=? THEN a.dst ELSE a.src END
            WHERE a.src=? OR a.dst=? ORDER BY a.peso DESC LIMIT 12""",
            (exp["slug"], exp["slug"], exp["slug"])).fetchall()
        if rel:
            out.append("## Relacionados (grafo)")
            for a in rel:
                sentido = ("menciona a" if a["src"] == exp["slug"]
                           else "mencionado por") \
                    if a["tipo"] == "menciona-a" else "nombre similar a"
                out.append(f"- {sentido} **{a['otro']}** (peso {a['peso']})")
            out.append("")
        docs = con.execute(
            "SELECT * FROM docs WHERE slug=? ORDER BY mtime DESC LIMIT 30",
            (exp["slug"],)).fetchall()
        out.append("## Documentos más recientes (30 de "
                   f"{exp['n_docs']})")
        for d in docs:
            out.append(f"- **{d['nombre']}** ({_fecha(d['mtime'])}, "
                       f"{d['estado']}, id {d['id']})")
            out.append(f"  {_link(d['ruta_rel'], d['id'])}")
        out.append("")
        out.append(f"[Tabla completa: leer_expediente('{exp['slug']}', "
                   f"modo='completo') · buscar dentro: buscar_documentos("
                   f"query, expediente='{exp['slug']}')]")
        return "\n".join(out)
    finally:
        con.close()


@mcp.tool()
def leer_documento(ruta_o_id: str, desde_char: int = 0) -> str:
    """Devuelve metadatos + texto extraído de un documento, por id numérico,
    ruta absoluta (K:\\...) o ruta relativa. Usa desde_char para paginar
    documentos largos (se devuelven 40.000 caracteres por llamada)."""
    con = _con()
    try:
        clave = ruta_o_id.strip().strip('"')
        if clave.isdigit():
            d = con.execute("SELECT * FROM docs WHERE id=?",
                            (int(clave),)).fetchone()
        else:
            rel = clave
            drive = config.RAIZ_DATOS.rstrip("\\").lower()
            if rel.lower().startswith(drive):
                rel = rel[len(config.RAIZ_DATOS.rstrip('\\')):].lstrip("\\/")
            d = con.execute("SELECT * FROM docs WHERE ruta_rel=?",
                            (rel,)).fetchone()
            if not d:
                d = con.execute(
                    "SELECT * FROM docs WHERE nombre_norm=? LIMIT 1",
                    (normalizar(os.path.basename(clave)),)).fetchone()
        if not d:
            return f"Documento no encontrado: {ruta_o_id}. " \
                   f"Prueba resolver_ruta(nombre) para localizarlo."
        texto_row = con.execute("SELECT texto FROM textos WHERE doc_id=?",
                                (d["id"],)).fetchone()
        texto = texto_row["texto"] if texto_row else ""
        cab = [f"# {d['nombre']}",
               f"- Id: {d['id']} · Expediente: {d['expediente']}",
               f"- {_link(d['ruta_rel'], d['id'])}",
               f"- Tipo: {d['ext']} · Tamaño: {human_size(d['size'])} · "
               f"Modificado: {_fecha(d['mtime'])} · "
               f"Páginas: {d['paginas'] or '-'} · Estado: {d['estado']}",
               ""]
        if not texto:
            cab.append("(Sin texto extraído para este documento; abrir la "
                       "ruta absoluta directamente.)")
            return "\n".join(cab)
        trozo = texto[desde_char:desde_char + 40000]
        cab.append(trozo)
        if desde_char + 40000 < len(texto):
            cab.append(f"\n[... continúa: llamar con "
                       f"desde_char={desde_char + 40000}; "
                       f"total {len(texto)} caracteres]")
        return "\n".join(cab)
    finally:
        con.close()


def _doc_por_clave(con, clave: str):
    clave = clave.strip().strip('"')
    if clave.isdigit():
        return con.execute("SELECT * FROM docs WHERE id=?",
                           (int(clave),)).fetchone()
    rel = clave
    drive = config.RAIZ_DATOS.rstrip("\\").lower()
    if rel.lower().startswith(drive):
        rel = rel[len(config.RAIZ_DATOS.rstrip('\\')):].lstrip("\\/")
    d = con.execute("SELECT * FROM docs WHERE ruta_rel=?", (rel,)).fetchone()
    if not d:
        d = con.execute("SELECT * FROM docs WHERE nombre_norm=? LIMIT 1",
                        (normalizar(os.path.basename(clave)),)).fetchone()
    return d


@mcp.tool()
def ver_documento(ruta_o_id: str, pagina: int = 1, paginas: int = 1):
    """Muestra un documento VISUALMENTE dentro del chat: renderiza como
    imagen las páginas de un PDF (indispensable para los 'escaneado(ocr?)',
    que no tienen texto — así puedes leerlos con visión) o la imagen misma
    (jpg/png/tif). pagina = primera página a mostrar (desde 1);
    paginas = cuántas (máx. 4 por llamada)."""
    con = _con()
    try:
        d = _doc_por_clave(con, ruta_o_id)
    finally:
        con.close()
    if not d:
        return f"Documento no encontrado: {ruta_o_id}"
    abs_p = _ruta_abs(d["ruta_rel"])
    ext = (d["ext"] or "").lower()
    salida = [f"**{d['nombre']}** (id {d['id']}) — "
              f"{_link(d['ruta_rel'], d['id'])}"]
    try:
        if ext == ".pdf":
            import pymupdf
            with pymupdf.open(abs_p) as pdf:
                total = pdf.page_count
                ini = max(0, int(pagina) - 1)
                fin = min(total, ini + max(1, min(int(paginas), 4)))
                if ini >= total:
                    return f"El PDF tiene {total} páginas; pediste la " \
                           f"{pagina}."
                salida[0] += f" · páginas {ini+1}-{fin} de {total}"
                for i in range(ini, fin):
                    pix = pdf[i].get_pixmap(dpi=110)
                    salida.append(Image(data=pix.tobytes("png"),
                                        format="png"))
                if fin < total:
                    salida.append(f"[Siguientes: ver_documento('{d['id']}', "
                                  f"pagina={fin+1})]")
        elif ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp",
                     ".tif", ".tiff"):
            import pymupdf
            with pymupdf.open(abs_p) as img:
                pix = img[0].get_pixmap(dpi=96)
                salida.append(Image(data=pix.tobytes("png"), format="png"))
        else:
            return (f"No sé renderizar '{ext}' visualmente. Para texto usa "
                    f"leer_documento('{d['id']}').")
    except Exception as e:
        return f"No se pudo renderizar {abs_p}: {type(e).__name__}: {e}"
    return salida


@mcp.tool()
def indice_cerebro() -> str:
    """Devuelve INDEX.md: la lista maestra de todos los expedientes con
    conteos, tamaños y rutas base en K:."""
    try:
        with open(os.path.join(config.BRAIN_DIR, "INDEX.md"),
                  encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "INDEX.md aún no generado. Ejecuta run_sync.bat."


@mcp.tool()
def resolver_ruta(nombre: str, limite: int = 15) -> str:
    """Dado un id o (parte de un) nombre de archivo, devuelve la(s) RUTA(s)
    ABSOLUTA(s) reales en K: con su expediente."""
    con = _con()
    try:
        if nombre.strip().isdigit():
            filas = con.execute("SELECT * FROM docs WHERE id=?",
                                (int(nombre.strip()),)).fetchall()
        else:
            filas = con.execute(
                "SELECT * FROM docs WHERE nombre_norm LIKE ? "
                "ORDER BY mtime DESC LIMIT ?",
                (f"%{normalizar(nombre)}%", max(1, min(int(limite), 50)))
            ).fetchall()
        if not filas:
            return f"Ningún documento coincide con '{nombre}'."
        out = []
        for d in filas:
            out.append(f"- {d['nombre']} (id {d['id']}, "
                       f"exp. {d['expediente']}, {_fecha(d['mtime'])}) → "
                       f"{_link(d['ruta_rel'], d['id'])}")
        return "\n".join(out)
    finally:
        con.close()


@mcp.tool()
def documentos_recientes(dias: int = 14, expediente: str = "",
                         limite: int = 30) -> str:
    """Documentos añadidos o modificados en K: en los últimos N días
    (por fecha de modificación del archivo), opcionalmente filtrados por
    expediente. Útil para '¿qué ha entrado esta semana?'."""
    con = _con()
    try:
        desde = (datetime.now() - timedelta(days=max(1, int(dias)))
                 ).timestamp()
        # tope superior: hay archivos con reloj corrupto (p.ej. año 2098)
        hasta = (datetime.now() + timedelta(days=2)).timestamp()
        sql = "SELECT * FROM docs WHERE mtime >= ? AND mtime <= ?"
        params = [desde, hasta]
        if expediente:
            exp, cands = _buscar_expediente(con, expediente)
            if not exp:
                ops = "\n".join(f"- {c['nombre']} (slug: {c['slug']})"
                                for c in cands) or "(ninguno)"
                return f"Expediente '{expediente}' ambiguo o no " \
                       f"encontrado. Candidatos:\n{ops}"
            sql += " AND slug = ?"
            params.append(exp["slug"])
        sql += " ORDER BY mtime DESC LIMIT ?"
        params.append(max(1, min(int(limite), 100)))
        filas = con.execute(sql, params).fetchall()
        if not filas:
            return f"Sin documentos modificados en los últimos {dias} días."
        out = [f"{len(filas)} documento(s) de los últimos {dias} días:", ""]
        for d in filas:
            out.append(f"- **{d['nombre']}** ({_fecha(d['mtime'])}, "
                       f"exp. {d['expediente']}, {d['estado']})")
            out.append(f"  {_link(d['ruta_rel'], d['id'])}")
        return "\n".join(out)
    finally:
        con.close()


@mcp.tool()
def vecinos_expediente(clave: str) -> str:
    """Grafo de relaciones de un expediente: a quién menciona, quién lo
    menciona y expedientes con nombre similar (posible mismo cliente)."""
    con = _con()
    try:
        exp, cands = _buscar_expediente(con, clave)
        if not exp:
            ops = "\n".join(f"- {c['nombre']} (slug: {c['slug']})"
                            for c in cands) or "(ninguno)"
            return f"Expediente '{clave}' no encontrado. Candidatos:\n{ops}"
        out = [f"# Relaciones de {exp['nombre']} (slug {exp['slug']})",
               f"Ruta base: `{exp['ruta_abs']}`", ""]
        filas = con.execute("""
            SELECT a.*, es.nombre AS n_src, ed.nombre AS n_dst
            FROM aristas a
            JOIN expedientes es ON es.slug=a.src
            JOIN expedientes ed ON ed.slug=a.dst
            WHERE a.src=? OR a.dst=? ORDER BY a.peso DESC LIMIT 60""",
            (exp["slug"], exp["slug"])).fetchall()
        if not filas:
            out.append("(Sin relaciones detectadas.)")
        for a in filas:
            if a["tipo"] == "menciona-a" and a["src"] == exp["slug"]:
                out.append(f"- menciona a **{a['n_dst']}** [{a['dst']}] "
                           f"en {a['peso']} doc(s) — ej. {a['ejemplo']}")
            elif a["tipo"] == "menciona-a":
                out.append(f"- mencionado por **{a['n_src']}** [{a['src']}] "
                           f"en {a['peso']} doc(s)")
            else:
                otro = a["n_dst"] if a["src"] == exp["slug"] else a["n_src"]
                slug_otro = a["dst"] if a["src"] == exp["slug"] else a["src"]
                out.append(f"- nombre similar: **{otro}** [{slug_otro}] "
                           f"(token: {a['ejemplo']})")
        return "\n".join(out)
    finally:
        con.close()


@mcp.tool()
def estado_sync() -> str:
    """Estado del cerebro: raíz, última sincronización, documentos por
    estado, expedientes, aristas del grafo y tamaño del índice."""
    con = _con()
    try:
        ultima = con.execute(
            "SELECT v FROM meta WHERE k='ultima_sync'").fetchone()
        n_docs = con.execute("SELECT COUNT(*) n FROM docs").fetchone()["n"]
        n_exp = con.execute(
            "SELECT COUNT(*) n FROM expedientes").fetchone()["n"]
        n_ar = con.execute("SELECT COUNT(*) n FROM aristas").fetchone()["n"]
        estados = con.execute(
            "SELECT estado, COUNT(*) n FROM docs GROUP BY estado "
            "ORDER BY n DESC").fetchall()
        try:
            db_size = human_size(os.path.getsize(config.DB_PATH))
        except OSError:
            db_size = "?"
        out = [f"- Raíz de datos: `{config.RAIZ_DATOS}` (solo lectura)",
               f"- Última sincronización: "
               f"{ultima['v'] if ultima else 'nunca'}",
               f"- Expedientes: {n_exp} · Documentos: {n_docs} · "
               f"Aristas del grafo: {n_ar}",
               f"- Tamaño del índice: {db_size}",
               "- Documentos por estado:"]
        for e in estados:
            out.append(f"  - {e['estado']}: {e['n']}")
        return "\n".join(out)
    finally:
        con.close()


if __name__ == "__main__":
    if "--http" in sys.argv:
        # Instancia de red para PCs de oficina (Claude Desktop normal, sin
        # Citrix): ver E:\Users\aaron_dtr\Desktop\brain-DTR\start_mcp_http.bat
        # y el README de dtr-mcp-setup para el contexto completo.
        # HTTPS obligatorio (los conectores remotos de Claude Desktop no
        # aceptan HTTP plano): certificado autofirmado generado por
        # tools\gen_cert.py en certs\, instalado como de confianza por
        # setup.ps1 en cada PC que lo use.
        import uvicorn

        host = os.environ.get("DTR_HTTP_HOST", "0.0.0.0")
        port = int(os.environ.get("DTR_HTTP_PORT", "8766"))
        certs_dir = os.path.join(os.path.dirname(__file__), "certs")
        keyfile = os.path.join(certs_dir, "dtr-mercantil.key")
        certfile = os.path.join(certs_dir, "dtr-mercantil.crt")

        app = mcp.streamable_http_app(host=host)
        config = uvicorn.Config(app, host=host, port=port,
                                ssl_keyfile=keyfile, ssl_certfile=certfile)
        uvicorn.Server(config).run()
    else:
        mcp.run(transport="stdio")
