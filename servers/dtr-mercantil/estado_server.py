# estado_server.py — visualizador local del cerebro DTR en http://localhost:8765
# Solo lectura: lee index.db y sync.log. Sin dependencias externas.
import json
import os
import re
import sqlite3
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

import config

PUERTO = 8765


def _resolver_destino(q):
    """Resuelve ?id= o ?ruta= a una ruta absoluta validada dentro de K:.
    Devuelve (ruta, None) o (None, mensaje_error)."""
    if "id" in q:
        try:
            doc_id = int(q["id"][0])
        except ValueError:
            return None, "id inválido"
        try:
            con = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro",
                                  uri=True, timeout=5)
            fila = con.execute("SELECT ruta_rel FROM docs WHERE id=?",
                               (doc_id,)).fetchone()
            con.close()
        except sqlite3.Error:
            return None, "índice no disponible"
        if not fila:
            return None, f"no existe documento con id {doc_id}"
        destino = os.path.join(config.RAIZ_DATOS, fila[0])
    elif "ruta" in q:
        destino = os.path.normpath(unquote(q["ruta"][0]))
    else:
        return None, "falta parámetro id o ruta"
    raiz = os.path.normpath(config.RAIZ_DATOS).lower().rstrip("\\")
    if not os.path.normpath(destino).lower().startswith(raiz):
        return None, "solo se pueden abrir rutas dentro de K:"
    if not os.path.exists(destino):
        return None, f"no existe: {destino}"
    return destino, None


def abrir_destino(path_qs: str, en_carpeta: bool):
    q = parse_qs(urlparse(path_qs).query)
    destino, err = _resolver_destino(q)
    if err:
        return f"<h3>No se pudo abrir</h3><p>{err}</p>", 404
    try:
        if en_carpeta and not os.path.isdir(destino):
            subprocess.Popen(["explorer", "/select,", destino])
        else:
            os.startfile(destino)  # abre con la app predeterminada
    except OSError as e:
        return f"<h3>Error al abrir</h3><p>{e}</p>", 500
    nombre = os.path.basename(destino) or destino
    return (f"<p style='font:14px system-ui;padding:24px'>Abriendo "
            f"<b>{nombre}</b>… Podés cerrar esta pestaña.</p>"
            f"<script>setTimeout(()=>window.close(), 1500)</script>"), 200
TOTAL_ESTIMADO = 146000  # censo inicial de archivos indexables/ficha en K:


def _pid_sync_vivo():
    from dtr_common import pid_vivo
    try:
        with open(os.path.join(config.META_DIR, "sync.pid")) as f:
            pid = int(f.read().strip())
        return pid if pid_vivo(pid) else None
    except (OSError, ValueError):
        return None


def _tail_log(n=400):
    try:
        with open(config.LOG_PATH, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 65536))
            lineas = f.read().decode("utf-8", errors="replace").splitlines()
        return lineas[-n:]
    except OSError:
        return []


def estado():
    d = {"corriendo": bool(_pid_sync_vivo()), "docs": 0, "expedientes": 0,
         "aristas": 0, "estados": [], "ultima_sync": None, "db_mb": 0,
         "progreso": None, "eta_min": None, "velocidad": None,
         "log": [], "total_estimado": TOTAL_ESTIMADO}
    try:
        con = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True,
                              timeout=5)
        con.row_factory = sqlite3.Row
        d["docs"] = con.execute("SELECT COUNT(*) c FROM docs").fetchone()["c"]
        d["expedientes"] = con.execute(
            "SELECT COUNT(*) c FROM expedientes").fetchone()["c"]
        d["aristas"] = con.execute(
            "SELECT COUNT(*) c FROM aristas").fetchone()["c"]
        agg = {}
        for r in con.execute("SELECT estado, COUNT(*) n FROM docs "
                             "GROUP BY estado"):
            clave = "error" if (r["estado"] or "").startswith("error") \
                else r["estado"]
            agg[clave] = agg.get(clave, 0) + r["n"]
        d["estados"] = sorted(agg.items(), key=lambda kv: -kv[1])
        u = con.execute("SELECT v FROM meta WHERE k='ultima_sync'").fetchone()
        d["ultima_sync"] = u["v"] if u else None
        con.close()
    except sqlite3.Error:
        pass
    try:
        total = os.path.getsize(config.DB_PATH)
        for suf in ("-wal", "-shm"):
            try:
                total += os.path.getsize(config.DB_PATH + suf)
            except OSError:
                pass
        d["db_mb"] = round(total / 1048576, 1)
    except OSError:
        pass

    lineas = _tail_log()
    utiles = [l for l in lineas if re.search(
        r"procesados|SYNC OK|BRAIN OK|INICIO|FIN|Sin cambios|omite|error",
        l, re.I)]
    d["log"] = utiles[-12:]
    if d["corriendo"]:
        m = None
        for l in reversed(lineas):
            m = re.search(r"([\d.,]+) procesados \(([\d.,]+)s\)", l)
            if m:
                break
        if m:
            hechos = int(re.sub(r"[.,]", "", m.group(1)))
            seg = int(re.sub(r"[.,]", "", m.group(2)))
            if seg > 0:
                v = hechos / seg
                d["velocidad"] = round(v, 1)
                restante = max(0, TOTAL_ESTIMADO - d["docs"])
                d["eta_min"] = round(restante / v / 60)
        d["progreso"] = min(99, round(100 * d["docs"] / TOTAL_ESTIMADO))
    elif d["ultima_sync"]:
        d["progreso"] = 100
    return d


def grafo_datos(min_peso=1, limite_aristas=500):
    d = {"nodos": [], "aristas": [], "total_aristas": 0}
    try:
        con = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True,
                              timeout=5)
        con.row_factory = sqlite3.Row
        d["total_aristas"] = con.execute(
            "SELECT COUNT(*) c FROM aristas").fetchone()["c"]
        crudas = con.execute(
            "SELECT src, dst, tipo, peso, ejemplo FROM aristas "
            "WHERE peso >= ? ORDER BY peso DESC LIMIT 6000",
            (min_peso,)).fetchall()
        # tope por nodo: evita que unos pocos hubs acaparen el dibujo
        POR_NODO = 5
        cuenta = {}
        aristas = []
        for a in crudas:
            if cuenta.get(a["src"], 0) < POR_NODO or \
                    cuenta.get(a["dst"], 0) < POR_NODO:
                aristas.append(a)
                cuenta[a["src"]] = cuenta.get(a["src"], 0) + 1
                cuenta[a["dst"]] = cuenta.get(a["dst"], 0) + 1
            if len(aristas) >= limite_aristas:
                break
        usados = {a["src"] for a in aristas} | {a["dst"] for a in aristas}
        if usados:
            marcas = ",".join("?" * len(usados))
            nodos = con.execute(
                f"SELECT slug, nombre, n_docs FROM expedientes "
                f"WHERE slug IN ({marcas})", list(usados)).fetchall()
            d["nodos"] = [dict(n) for n in nodos]
        d["aristas"] = [dict(a) for a in aristas]
        con.close()
    except sqlite3.Error:
        pass
    return d


GRAFO_HTML = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cerebro DTR — grafo</title>
<style>
:root{color-scheme:light dark;--bg:#f6f7f9;--panel:#fff;--ink:#1a2233;
 --ink2:#5b6577;--muted:#8b93a3;--linea:#e4e7ec;--azul:#3d6fa8;
 --neutro:#a7aeba;
 --s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;
 --s6:#008300}
@media (prefers-color-scheme: dark){:root{--bg:#14181f;--panel:#1d232d;
 --ink:#e8ebf0;--ink2:#aab2c0;--muted:#7c8494;--linea:#2b323e;
 --azul:#7aa7d9;--neutro:#4a5261;
 --s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;
 --s6:#008300}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
 font:14px/1.5 system-ui,Segoe UI,sans-serif;display:flex;
 flex-direction:column;height:100vh}
header{padding:12px 20px;display:flex;gap:16px;align-items:center;
 flex-wrap:wrap;border-bottom:1px solid var(--linea)}
header h1{font-size:15px;margin:0}
header a{color:var(--azul);text-decoration:none;font-size:13px}
input[type=search]{background:var(--panel);border:1px solid var(--linea);
 color:var(--ink);border-radius:8px;padding:6px 10px;width:230px}
label{font-size:12px;color:var(--ink2)}
#lienzo{flex:1;display:block;width:100%;cursor:grab}
#info{position:fixed;bottom:14px;left:14px;background:var(--panel);
 border:1px solid var(--linea);border-radius:10px;padding:10px 14px;
 max-width:420px;font-size:12.5px;color:var(--ink2);display:none}
#info b{color:var(--ink)}
#stats{position:fixed;top:64px;right:14px;background:var(--panel);
 border:1px solid var(--linea);border-radius:10px;padding:12px 14px;
 width:250px;font-size:12.5px;color:var(--ink2)}
#stats h3{margin:0 0 6px;font-size:11px;color:var(--muted);
 text-transform:uppercase;letter-spacing:.4px}
#stats .num{color:var(--ink);font-weight:600;
 font-variant-numeric:tabular-nums}
#stats .hub{cursor:pointer;padding:2px 0;white-space:nowrap;overflow:hidden;
 text-overflow:ellipsis}
#stats .hub:hover{color:var(--ink)}
.chip{display:inline-flex;align-items:center;gap:5px;margin:2px 6px 2px 0;
 cursor:pointer;font-size:12px;color:var(--ink2)}
.chip:hover{color:var(--ink)}
.chip .pto{width:10px;height:10px;border-radius:50%;flex:none}
#vacio{position:fixed;inset:0;display:flex;align-items:center;
 justify-content:center;color:var(--muted);text-align:center;padding:40px}
#vacio[hidden]{display:none}
.leyenda{font-size:12px;color:var(--ink2);display:flex;gap:14px;
 align-items:center}
.tr{display:inline-block;width:22px;height:0;border-top:2px solid var(--azul);
 vertical-align:middle}
.tr2{border-top:2px dashed var(--neutro)}
</style></head><body>
<header>
 <h1>Grafo de expedientes</h1>
 <a href="/">&larr; volver al estado</a>
 <input type="search" id="buscar" placeholder="buscar expediente…">
 <label>peso mín. <input type="range" id="peso" min="1" max="10" value="3"
  style="vertical-align:middle"> <span id="peso-v">3</span></label>
 <span class="leyenda"><span><span class="tr"></span> menciona-a</span>
  <span><span class="tr tr2"></span> nombre-similar</span></span>
 <span id="resumen" style="font-size:12px;color:var(--muted)"></span>
</header>
<canvas id="lienzo"></canvas>
<div id="stats">
 <h3>Métricas</h3>
 <div id="stats-nums">cargando…</div>
 <h3 style="margin-top:10px">Comunidades</h3>
 <div id="leyenda-grupos"></div>
 <h3 style="margin-top:10px">Más conectados</h3>
 <div id="hubs"></div>
</div>
<div id="info"></div>
<div id="vacio" hidden>El grafo se genera en la fase final de cada
 sincronización.<br>Todavía no hay aristas — volvé cuando la corrida
 termine.</div>
<script>
const cv = document.getElementById("lienzo"), cx = cv.getContext("2d");
const css = v => getComputedStyle(document.documentElement)
  .getPropertyValue(v).trim();
let nodos = [], aristas = [], porId = {}, vecinos = {};
let cam = {x:0, y:0, z:1}, arrastre = null, hover = null, sel = null;
let filtroTxt = "", simPasos = 0;

function tam(n){ return 4 + Math.min(10, Math.sqrt(n.n_docs || 1)); }

async function cargar(){
 const minP = document.getElementById("peso").value;
 const d = await (await fetch("/api/grafo?min_peso=" + minP)).json();
 document.getElementById("vacio").hidden = d.aristas.length > 0;
 document.getElementById("resumen").textContent =
   d.nodos.length + " nodos · " + d.aristas.length + " de " +
   d.total_aristas + " aristas";
 porId = {}; vecinos = {};
 const previos = Object.fromEntries(nodos.map(n => [n.slug, n]));
 nodos = d.nodos.map((n, i) => {
   const p = previos[n.slug];
   const ang = 6.28 * i / d.nodos.length, r = 300 + 150 * Math.random();
   return Object.assign({x: p ? p.x : Math.cos(ang)*r,
     y: p ? p.y : Math.sin(ang)*r, vx:0, vy:0}, n); });
 nodos.forEach(n => porId[n.slug] = n);
 aristas = d.aristas.filter(a => porId[a.src] && porId[a.dst]);
 aristas.forEach(a => { (vecinos[a.src] = vecinos[a.src]||new Set()).add(a.dst);
   (vecinos[a.dst] = vecinos[a.dst]||new Set()).add(a.src); });
 grupos = agrupar();
 pintarPaneles(d);
 simPasos = 300; encuadrar = true;
}

let grupos = [];
const PALETA = ["--s1","--s2","--s3","--s4","--s5","--s6"];
const grado = s => (vecinos[s] ? vecinos[s].size : 0);

function agrupar(){
 // comunidades por propagación de etiquetas, ponderada por peso de arista
 const et = {}; nodos.forEach(n => et[n.slug] = n.slug);
 const ady = {};
 aristas.forEach(a => { (ady[a.src] = ady[a.src]||[]).push([a.dst, a.peso]);
   (ady[a.dst] = ady[a.dst]||[]).push([a.src, a.peso]); });
 for(let it = 0; it < 40; it++){
  let cambios = 0;
  for(const n of nodos){
   const v = ady[n.slug]; if(!v || !v.length) continue;
   const votos = {};
   v.forEach(([o,p]) => votos[et[o]] = (votos[et[o]]||0) + p);
   const mejor = Object.entries(votos).sort((a,b) => b[1]-a[1])[0][0];
   if(mejor !== et[n.slug]){ et[n.slug] = mejor; cambios++; }
  }
  if(!cambios) break;
 }
 const comp = {};
 nodos.forEach(n => (comp[et[n.slug]] = comp[et[n.slug]]||[]).push(n));
 const orden = Object.values(comp).sort((a,b) => b.length - a.length);
 orden.forEach((g, i) => {
   const color = i < PALETA.length ? css(PALETA[i]) : css("--neutro");
   g.forEach(n => { n.color = color; n.grupo = i; });
   g.hub = g.reduce((m,n) => grado(n.slug) > grado(m.slug) ? n : m, g[0]);
 });
 return orden;
}

function seleccionar(slug){
 const n = porId[slug];
 if(!n) return;
 sel = n; mostrarInfo(n);
 cam.x = -n.x * cam.z; cam.y = -n.y * cam.z;
}

function pintarPaneles(d){
 const docsRep = nodos.reduce((s,n) => s + (n.n_docs||0), 0);
 document.getElementById("stats-nums").innerHTML =
  `<div>Expedientes en el grafo: <span class="num">${nodos.length}</span></div>` +
  `<div>Aristas visibles: <span class="num">${aristas.length}</span>` +
  ` de <span class="num">${d.total_aristas}</span></div>` +
  `<div>Comunidades: <span class="num">${grupos.length}</span></div>` +
  `<div>Docs representados: <span class="num">` +
  `${docsRep.toLocaleString("es-ES")}</span></div>`;
 document.getElementById("leyenda-grupos").innerHTML = grupos.slice(0,6)
  .map((g,i) => `<span class="chip" onclick="seleccionar('${g.hub.slug}')">` +
    `<span class="pto" style="background:${css(PALETA[i])}"></span>` +
    `${g.hub.nombre.slice(0,20)} (${g.length})</span>`).join("") +
  (grupos.length > 6 ?
    `<span class="chip"><span class="pto" ` +
    `style="background:${css("--neutro")}"></span>` +
    `otros ${grupos.length-6} grupos</span>` : "");
 const hubs = [...nodos].sort((a,b) => grado(b.slug) - grado(a.slug))
  .slice(0, 5);
 document.getElementById("hubs").innerHTML = hubs.map(n =>
  `<div class="hub" onclick="seleccionar('${n.slug}')" title="${n.nombre}">` +
  `<span class="num">${grado(n.slug)}</span> · ${n.nombre.slice(0,24)}` +
  `</div>`).join("");
}

let encuadrar = false;
function ajustarVista(){
 if(!nodos.length) return;
 const xs = nodos.map(n=>n.x), ys = nodos.map(n=>n.y);
 const w = Math.max(...xs)-Math.min(...xs)+200,
       h = Math.max(...ys)-Math.min(...ys)+200;
 cam.z = Math.max(0.2, Math.min(1.5,
   Math.min(cv.clientWidth/w, cv.clientHeight/h)));
 cam.x = -((Math.max(...xs)+Math.min(...xs))/2)*cam.z;
 cam.y = -((Math.max(...ys)+Math.min(...ys))/2)*cam.z;
}

function paso(){
 if(simPasos <= 0) return;
 simPasos--;
 for(const a of aristas){
  const s = porId[a.src], t = porId[a.dst];
  let dx = t.x-s.x, dy = t.y-s.y, d = Math.hypot(dx,dy)||1;
  const f = (d-170)*0.004;
  s.vx += f*dx/d; s.vy += f*dy/d; t.vx -= f*dx/d; t.vy -= f*dy/d;
 }
 for(let i=0;i<nodos.length;i++) for(let j=i+1;j<nodos.length;j++){
  const a=nodos[i], b=nodos[j];
  let dx=b.x-a.x, dy=b.y-a.y, d2=dx*dx+dy*dy;
  if(d2 < 1) { dx = Math.random()-0.5; dy = Math.random()-0.5; d2 = 1; }
  if(d2 < 90000){ const f = 900/d2;
   a.vx -= f*dx; a.vy -= f*dy; b.vx += f*dx; b.vy += f*dy; }
 }
 for(const n of nodos){ n.vx *= 0.85; n.vy *= 0.85;
  n.x += n.vx; n.y += n.vy; }
}

function dibujar(){
 const W = cv.width = cv.clientWidth * devicePixelRatio;
 const H = cv.height = cv.clientHeight * devicePixelRatio;
 cx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
 cx.clearRect(0,0,W,H);
 cx.save();
 cx.translate(cv.clientWidth/2 + cam.x, cv.clientHeight/2 + cam.y);
 cx.scale(cam.z, cam.z);
 const foco = sel || hover;
 const conx = foco ? (vecinos[foco.slug] || new Set()) : null;
 for(const a of aristas){
  const s = porId[a.src], t = porId[a.dst];
  const activa = foco && (a.src===foco.slug || a.dst===foco.slug);
  cx.globalAlpha = foco ? (activa ? 0.9 : 0.06) : 0.35;
  cx.strokeStyle = a.tipo !== "menciona-a" ? css("--neutro") :
    (s.color === t.color ? (s.color || css("--azul")) : css("--muted"));
  cx.lineWidth = Math.min(4, 0.8 + a.peso*0.15) / cam.z;
  cx.setLineDash(a.tipo === "menciona-a" ? [] : [4/cam.z, 4/cam.z]);
  cx.beginPath(); cx.moveTo(s.x,s.y); cx.lineTo(t.x,t.y); cx.stroke();
 }
 cx.setLineDash([]);
 for(const n of nodos){
  const enc = filtroTxt &&
    n.nombre.toLowerCase().includes(filtroTxt);
  const activo = !foco || foco===n || (conx && conx.has(n.slug));
  cx.globalAlpha = activo ? 1 : 0.15;
  cx.beginPath(); cx.arc(n.x, n.y, tam(n), 0, 7);
  cx.fillStyle = enc ? css("--ink") : (n.color || css("--azul"));
  cx.fill();
  if(sel === n || hover === n){
   cx.strokeStyle = css("--ink"); cx.lineWidth = 2/cam.z; cx.stroke();
  }
  cx.globalAlpha = 1;
  if(cam.z > 0.7 && (activo && (foco || enc || tam(n) > 9))){
   cx.fillStyle = css("--ink2");
   cx.font = (11/cam.z) + "px system-ui";
   cx.fillText(n.nombre.slice(0,28), n.x + tam(n) + 3/cam.z, n.y + 3/cam.z);
  }
 }
 cx.restore();
}

function coordMundo(e){
 const r = cv.getBoundingClientRect();
 return {x:(e.clientX - r.left - cv.clientWidth/2 - cam.x)/cam.z,
         y:(e.clientY - r.top - cv.clientHeight/2 - cam.y)/cam.z};
}
function nodoEn(p){
 for(let i = nodos.length-1; i >= 0; i--){
  const n = nodos[i];
  if(Math.hypot(n.x-p.x, n.y-p.y) < tam(n)+3) return n;
 }
 return null;
}
cv.addEventListener("mousedown", e => {
 const n = nodoEn(coordMundo(e));
 arrastre = n ? {nodo:n} : {px:e.clientX, py:e.clientY};
 if(n){ sel = n; mostrarInfo(n); } });
addEventListener("mousemove", e => {
 if(arrastre && arrastre.nodo){ const p = coordMundo(e);
  arrastre.nodo.x = p.x; arrastre.nodo.y = p.y; simPasos = 30; }
 else if(arrastre){ cam.x += e.clientX-arrastre.px;
  cam.y += e.clientY-arrastre.py;
  arrastre.px = e.clientX; arrastre.py = e.clientY; }
 else { hover = nodoEn(coordMundo(e));
  cv.style.cursor = hover ? "pointer" : "grab"; } });
addEventListener("mouseup", () => arrastre = null);
cv.addEventListener("dblclick", () => { sel = null;
 document.getElementById("info").style.display = "none"; });
cv.addEventListener("wheel", e => { e.preventDefault();
 cam.z = Math.max(0.2, Math.min(4, cam.z * (e.deltaY < 0 ? 1.12 : 0.9))); },
 {passive:false});
document.getElementById("buscar").addEventListener("input", e =>
 filtroTxt = e.target.value.trim().toLowerCase());
document.getElementById("peso").addEventListener("change", e => {
 document.getElementById("peso-v").textContent = e.target.value; cargar(); });

function mostrarInfo(n){
 const rel = aristas.filter(a => a.src===n.slug || a.dst===n.slug)
  .sort((a,b) => b.peso-a.peso).slice(0,8)
  .map(a => { const otro = a.src===n.slug ?
     porId[a.dst].nombre : porId[a.src].nombre;
   return (a.tipo==="menciona-a" ?
     (a.src===n.slug ? "menciona a " : "mencionado por ") : "similar a ") +
     "<b>" + otro + "</b> (" + a.peso + ")"; }).join("<br>");
 const el = document.getElementById("info");
 el.innerHTML = "<b>" + n.nombre + "</b> · " + n.n_docs +
   " docs<br>" + rel;
 el.style.display = "block";
}

(function bucle(){ paso();
 if(encuadrar && simPasos === 150){ ajustarVista(); encuadrar = false; }
 dibujar(); requestAnimationFrame(bucle); })();
cargar(); setInterval(cargar, 60000);
</script></body></html>"""


HTML = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cerebro DTR — estado</title>
<style>
:root{color-scheme:light dark;
 --bg:#f6f7f9;--panel:#ffffff;--ink:#1a2233;--ink2:#5b6577;--muted:#8b93a3;
 --linea:#e4e7ec;--azul:#3d6fa8;--ok:#2e7d4f;--warn:#b07c1f;--err:#b3423a;
 --neutro:#7a8494}
@media (prefers-color-scheme: dark){:root{
 --bg:#14181f;--panel:#1d232d;--ink:#e8ebf0;--ink2:#aab2c0;--muted:#7c8494;
 --linea:#2b323e;--azul:#7aa7d9;--ok:#5cb385;--warn:#d4a94f;--err:#d97b74;
 --neutro:#9aa3b2}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
 font:14px/1.5 system-ui,Segoe UI,sans-serif;padding:24px}
h1{font-size:18px;margin:0 0 4px}
.sub{color:var(--ink2);margin:0 0 20px;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
 gap:12px;margin-bottom:16px}
.tile{background:var(--panel);border:1px solid var(--linea);border-radius:10px;
 padding:14px 16px}
.tile .k{font-size:12px;color:var(--muted);margin-bottom:2px}
.tile .v{font-size:22px;font-weight:600;font-variant-numeric:tabular-nums}
.tile .n{font-size:12px;color:var(--ink2)}
.panel{background:var(--panel);border:1px solid var(--linea);
 border-radius:10px;padding:16px;margin-bottom:16px}
.panel h2{font-size:13px;color:var(--ink2);margin:0 0 12px;font-weight:600;
 text-transform:uppercase;letter-spacing:.4px}
.badge{display:inline-flex;align-items:center;gap:6px;font-weight:600}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.bar{height:10px;background:var(--linea);border-radius:5px;overflow:hidden}
.bar>div{height:100%;background:var(--azul);border-radius:5px;
 transition:width .6s}
.fila{display:grid;grid-template-columns:170px 1fr 90px;gap:10px;
 align-items:center;margin:7px 0;font-variant-numeric:tabular-nums}
.fila .et{font-size:13px;color:var(--ink2);text-align:right;
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fila .num{font-size:13px;color:var(--ink);text-align:left}
.mini{height:8px;background:var(--linea);border-radius:4px;overflow:hidden}
.mini>div{height:100%;border-radius:4px}
pre{background:var(--bg);border:1px solid var(--linea);border-radius:8px;
 padding:12px;font:12px/1.6 Consolas,monospace;color:var(--ink2);
 overflow-x:auto;margin:0;white-space:pre-wrap;word-break:break-all}
.pie{color:var(--muted);font-size:12px;margin-top:14px}
</style></head><body>
<h1>Cerebro documental DTR — sistema MERCANTIL (K:)</h1>
<p class="sub">Visualizador local · se actualiza solo cada 10 s ·
 salida en <code>C:\\dtr-brain\\brain</code> ·
 <a href="/grafo" style="color:var(--azul)">ver grafo de expedientes &rarr;</a></p>

<div class="panel" id="p-sync">
 <h2>Sincronización</h2>
 <div style="display:flex;justify-content:space-between;align-items:center;
  margin-bottom:10px;flex-wrap:wrap;gap:8px">
  <span class="badge"><span class="dot" id="dot"></span>
   <span id="sync-txt">…</span></span>
  <span style="color:var(--ink2);font-size:13px" id="eta"></span>
 </div>
 <div class="bar"><div id="prog" style="width:0%"></div></div>
</div>

<div class="grid">
 <div class="tile"><div class="k">Expedientes</div><div class="v" id="t-exp">–</div></div>
 <div class="tile"><div class="k">Documentos indexados</div><div class="v" id="t-docs">–</div><div class="n" id="t-docs-n"></div></div>
 <div class="tile"><div class="k">Aristas del grafo</div><div class="v" id="t-ar">–</div></div>
 <div class="tile"><div class="k">Tamaño del índice</div><div class="v" id="t-db">–</div></div>
 <div class="tile"><div class="k">Última sync completa</div><div class="v" style="font-size:15px" id="t-ult">–</div></div>
</div>

<div class="panel">
 <h2>Documentos por estado</h2>
 <div id="estados"></div>
</div>

<div class="panel">
 <h2>Últimas líneas del log</h2>
 <pre id="log">cargando…</pre>
</div>
<p class="pie">Índice: SQLite FTS5 · K: es solo lectura ·
 tarea diaria 06:00 (DTR-Brain-Sync)</p>
<script>
const COLOR = {ok:"var(--ok)", "escaneado(ocr?)":"var(--warn)",
  error:"var(--err)"};
const fmt = n => n.toLocaleString("es-ES");
async function tick(){
 let d;
 try{ d = await (await fetch("/api/estado")).json(); }
 catch(e){ document.getElementById("sync-txt").textContent =
   "servidor de estado no responde"; return; }
 const dot = document.getElementById("dot");
 const txt = document.getElementById("sync-txt");
 if(d.corriendo){ dot.style.background = "var(--warn)";
  txt.textContent = "Indexación en curso" +
   (d.velocidad ? " · " + d.velocidad + " docs/s" : ""); }
 else if(d.ultima_sync){ dot.style.background = "var(--ok)";
  txt.textContent = "Al día (sin sync en curso)"; }
 else { dot.style.background = "var(--neutro)";
  txt.textContent = "Sin sincronizar todavía"; }
 document.getElementById("eta").textContent =
   d.corriendo && d.eta_min != null ?
   "quedan ~" + (d.eta_min >= 90 ? (d.eta_min/60).toFixed(1) + " h"
                : d.eta_min + " min") : "";
 document.getElementById("prog").style.width = (d.progreso ?? 0) + "%";
 document.getElementById("t-exp").textContent = fmt(d.expedientes);
 document.getElementById("t-docs").textContent = fmt(d.docs);
 document.getElementById("t-docs-n").textContent =
   d.corriendo ? "de ~" + fmt(d.total_estimado) + " estimados" : "";
 document.getElementById("t-ar").textContent = fmt(d.aristas);
 document.getElementById("t-db").textContent = d.db_mb + " MB";
 document.getElementById("t-ult").textContent =
   d.ultima_sync ? d.ultima_sync.replace("T"," ") : "nunca";
 const max = Math.max(1, ...d.estados.map(e => e[1]));
 document.getElementById("estados").innerHTML = d.estados.map(e => {
  const c = COLOR[e[0]] || "var(--neutro)";
  return `<div class="fila"><div class="et" title="${e[0]}">${e[0]}</div>
   <div class="mini"><div style="width:${100*e[1]/max}%;background:${c}">
   </div></div><div class="num">${fmt(e[1])}</div></div>`; }).join("") ||
   "<span style='color:var(--muted)'>sin datos aún</span>";
 document.getElementById("log").textContent =
   d.log.join("\\n") || "(log vacío)";
}
tick(); setInterval(tick, 10000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/estado"):
            cuerpo = json.dumps(estado(), ensure_ascii=False).encode("utf-8")
            tipo = "application/json; charset=utf-8"
        elif self.path.startswith("/abrir") or \
                self.path.startswith("/carpeta"):
            html, codigo = abrir_destino(
                self.path, self.path.startswith("/carpeta"))
            cuerpo = html.encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            return
        elif self.path.startswith("/api/grafo"):
            try:
                q = parse_qs(urlparse(self.path).query)
                min_peso = int(q.get("min_peso", ["1"])[0])
            except (ValueError, IndexError):
                min_peso = 1
            cuerpo = json.dumps(grafo_datos(min_peso),
                                ensure_ascii=False).encode("utf-8")
            tipo = "application/json; charset=utf-8"
        elif self.path.startswith("/grafo"):
            cuerpo = GRAFO_HTML.encode("utf-8")
            tipo = "text/html; charset=utf-8"
        elif self.path in ("/", "/index.html"):
            cuerpo = HTML.encode("utf-8")
            tipo = "text/html; charset=utf-8"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    if sys.stdout:  # bajo pythonw.exe no hay consola
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(f"Visualizador en http://localhost:{PUERTO}", flush=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PUERTO), Handler)
    srv.serve_forever()
