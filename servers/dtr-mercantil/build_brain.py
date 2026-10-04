# build_brain.py — (re)genera INDEX.md y los <expediente>.md a partir del
# índice SQLite. Solo reescribe los expedientes marcados como dirty y borra
# los .md de expedientes que ya no existen. Generación 100% mecánica.
import json
import os
import sys
import time
from datetime import datetime

import config
from dtr_common import abrir_db, human_size


def md_escape(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def fecha(mtime) -> str:
    try:
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except Exception:
        return "?"


def ruta_abs_de(ruta_rel: str) -> str:
    return os.path.join(config.RAIZ_DATOS, ruta_rel)


def generar_expediente_md(con, exp) -> str:
    docs = con.execute(
        "SELECT * FROM docs WHERE slug=? ORDER BY ruta_rel",
        (exp["slug"],)).fetchall()
    L = []
    L.append(f"# {exp['nombre']}")
    L.append("")
    L.append(f"**Ruta base:** `{exp['ruta_abs']}`")
    L.append(f"**Documentos:** {exp['n_docs']} · "
             f"**Tamaño:** {human_size(exp['size_total'])} · "
             f"**Actualizado:** {exp['actualizado'] or '?'}")
    L.append("")

    # Relaciones del grafo
    salientes = con.execute("""
        SELECT a.*, e.nombre AS dst_nombre FROM aristas a
        JOIN expedientes e ON e.slug = a.dst
        WHERE a.src=? ORDER BY a.peso DESC LIMIT 25""",
        (exp["slug"],)).fetchall()
    entrantes = con.execute("""
        SELECT a.*, e.nombre AS src_nombre FROM aristas a
        JOIN expedientes e ON e.slug = a.src
        WHERE a.dst=? AND a.src != a.dst ORDER BY a.peso DESC LIMIT 25""",
        (exp["slug"],)).fetchall()
    if salientes or entrantes:
        L.append("## Relacionados")
        for a in salientes:
            if a["tipo"] == "menciona-a":
                L.append(f"- menciona a [[{a['dst']}]] "
                         f"({a['dst_nombre']}) en {a['peso']} doc(s) — "
                         f"ej. {a['ejemplo']}")
            else:
                L.append(f"- nombre similar a [[{a['dst']}]] "
                         f"({a['dst_nombre']}) — token: {a['ejemplo']}")
        for a in entrantes:
            if a["tipo"] == "menciona-a":
                L.append(f"- mencionado por [[{a['src']}]] "
                         f"({a['src_nombre']}) en {a['peso']} doc(s)")
        L.append("")

    # Tabla de documentos
    L.append("## Documentos")
    L.append("")
    L.append("| Documento | Tipo | Tamaño | Modificado | Ruta absoluta "
             "| Nº págs | Estado |")
    L.append("|---|---|---|---|---|---|---|")
    for d in docs:
        L.append(
            f"| {md_escape(d['nombre'])} | {(d['ext'] or '').lstrip('.')} "
            f"| {human_size(d['size'])} | {fecha(d['mtime'])} "
            f"| `{ruta_abs_de(d['ruta_rel'])}` "
            f"| {d['paginas'] if d['paginas'] else ''} "
            f"| {d['estado']} |")
    L.append("")

    # Fragmentos clave
    con_texto = [d for d in docs if d["extracto"]]
    if con_texto:
        L.append("## Fragmentos clave")
        L.append("")
        recientes = sorted(con_texto, key=lambda d: d["mtime"] or 0,
                           reverse=True)[:config.MAX_FRAGMENTOS_MD]
        for d in recientes:
            L.append(f"- **{d['nombre']}** — `{ruta_abs_de(d['ruta_rel'])}`")
            L.append(f"  > {md_escape(d['extracto'])}")
        if len(con_texto) > config.MAX_FRAGMENTOS_MD:
            L.append(f"- … y {len(con_texto)-config.MAX_FRAGMENTOS_MD} "
                     f"documentos más con texto (usar búsqueda FTS).")
        L.append("")
    return "\n".join(L)


def generar_index_md(con) -> str:
    exps = con.execute(
        "SELECT * FROM expedientes ORDER BY nombre COLLATE NOCASE").fetchall()
    total_docs = sum(e["n_docs"] for e in exps)
    total_size = sum(e["size_total"] or 0 for e in exps)
    estados = con.execute(
        "SELECT estado, COUNT(*) n FROM docs GROUP BY estado "
        "ORDER BY n DESC").fetchall()
    ultima = con.execute(
        "SELECT v FROM meta WHERE k='ultima_sync'").fetchone()

    L = []
    L.append("# Cerebro documental DTR — sistema MERCANTIL (K:)")
    L.append("")
    L.append(f"**Raíz de datos:** `{config.RAIZ_DATOS}` · "
             f"**Expedientes:** {len(exps)} · **Documentos:** {total_docs} · "
             f"**Tamaño:** {human_size(total_size)}")
    L.append(f"**Última sincronización:** {ultima['v'] if ultima else '?'}")
    L.append("")
    L.append("**Documentos por estado:** " + " · ".join(
        f"{e['estado']}: {e['n']}" for e in estados))
    L.append("")
    L.append("| Expediente | Docs | Tamaño | Mapa | Ruta en K: |")
    L.append("|---|---|---|---|---|")
    for e in exps:
        L.append(f"| {md_escape(e['nombre'])} | {e['n_docs']} "
                 f"| {human_size(e['size_total'])} "
                 f"| [{e['slug']}](expedientes/{e['slug']}.md) "
                 f"| `{e['ruta_abs']}` |")
    L.append("")
    return "\n".join(L)


def exportar_graph_json(con):
    nodos = [{"id": e["slug"], "nombre": e["nombre"], "docs": e["n_docs"]}
             for e in con.execute("SELECT * FROM expedientes")]
    aristas = [{"src": a["src"], "dst": a["dst"], "tipo": a["tipo"],
                "peso": a["peso"], "ejemplo": a["ejemplo"]}
               for a in con.execute("SELECT * FROM aristas")]
    with open(config.GRAPH_PATH, "w", encoding="utf-8") as f:
        json.dump({"generado": datetime.now().isoformat(timespec="seconds"),
                   "nodos": nodos, "aristas": aristas},
                  f, ensure_ascii=False, indent=1)
    return len(nodos), len(aristas)


def build():
    t0 = time.time()
    os.makedirs(config.EXPEDIENTES_DIR, exist_ok=True)
    con = abrir_db()

    dirty = con.execute("SELECT * FROM expedientes WHERE dirty=1").fetchall()
    for exp in dirty:
        md = generar_expediente_md(con, exp)
        destino = os.path.join(config.EXPEDIENTES_DIR, f"{exp['slug']}.md")
        with open(destino, "w", encoding="utf-8") as f:
            f.write(md)
    con.execute("UPDATE expedientes SET dirty=0")

    # borrar .md huérfanos
    vigentes = {r["slug"] + ".md"
                for r in con.execute("SELECT slug FROM expedientes")}
    borrados = 0
    for fn in os.listdir(config.EXPEDIENTES_DIR):
        if fn.endswith(".md") and fn not in vigentes:
            os.remove(os.path.join(config.EXPEDIENTES_DIR, fn))
            borrados += 1

    with open(os.path.join(config.BRAIN_DIR, "INDEX.md"), "w",
              encoding="utf-8") as f:
        f.write(generar_index_md(con))
    n_nodos, n_aristas = exportar_graph_json(con)
    con.commit()
    con.close()
    print(f"BRAIN OK en {time.time()-t0:,.1f}s — regenerados={len(dirty)} "
          f"md_borrados={borrados} grafo={n_nodos} nodos/"
          f"{n_aristas} aristas", flush=True)
    if not dirty and not borrados:
        print("Sin cambios en el cerebro.", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"=== build_brain {datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)
    build()
