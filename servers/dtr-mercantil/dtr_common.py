# Utilidades compartidas: normalización, slugs, esquema SQLite
import os
import re
import sqlite3
import unicodedata

import config


def normalizar(s: str) -> str:
    """minúsculas + sin acentos, para comparaciones insensibles."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def slugify(s: str) -> str:
    s = normalizar(s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80] or "sin-nombre"


def human_size(n) -> str:
    n = float(n or 0)
    for unidad in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:,.0f} {unidad}"
        n /= 1024
    return f"{n:,.1f} TB"


def extracto_de(texto: str, palabras: int = None) -> str:
    palabras = palabras or config.EXTRACTO_PALABRAS
    trozos = (texto or "").split()
    ext = " ".join(trozos[:palabras])
    return ext + (" …" if len(trozos) > palabras else "")


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS docs(
  id INTEGER PRIMARY KEY,
  ruta_rel TEXT UNIQUE NOT NULL,
  expediente TEXT NOT NULL,
  slug TEXT NOT NULL,
  nombre TEXT NOT NULL,
  nombre_norm TEXT NOT NULL,
  ext TEXT,
  size INTEGER,
  mtime REAL,
  hash TEXT,
  paginas INTEGER,
  estado TEXT,
  extracto TEXT,
  actualizado TEXT
);
CREATE INDEX IF NOT EXISTS idx_docs_slug ON docs(slug);
CREATE INDEX IF NOT EXISTS idx_docs_nombre_norm ON docs(nombre_norm);
CREATE TABLE IF NOT EXISTS textos(doc_id INTEGER PRIMARY KEY, texto TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
  texto, content='textos', content_rowid='doc_id',
  tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS textos_ai AFTER INSERT ON textos BEGIN
  INSERT INTO fts(rowid, texto) VALUES (new.doc_id, new.texto);
END;
CREATE TRIGGER IF NOT EXISTS textos_ad AFTER DELETE ON textos BEGIN
  INSERT INTO fts(fts, rowid, texto) VALUES ('delete', old.doc_id, old.texto);
END;
CREATE TRIGGER IF NOT EXISTS textos_au AFTER UPDATE ON textos BEGIN
  INSERT INTO fts(fts, rowid, texto) VALUES ('delete', old.doc_id, old.texto);
  INSERT INTO fts(rowid, texto) VALUES (new.doc_id, new.texto);
END;
CREATE TABLE IF NOT EXISTS expedientes(
  slug TEXT PRIMARY KEY,
  nombre TEXT NOT NULL,
  nombre_norm TEXT NOT NULL,
  ruta_abs TEXT NOT NULL,
  n_docs INTEGER DEFAULT 0,
  size_total INTEGER DEFAULT 0,
  actualizado TEXT,
  dirty INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS aristas(
  src TEXT NOT NULL, dst TEXT NOT NULL, tipo TEXT NOT NULL,
  peso INTEGER DEFAULT 1, ejemplo TEXT,
  PRIMARY KEY (src, dst, tipo)
);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""


def abrir_db(solo_lectura: bool = False) -> sqlite3.Connection:
    if solo_lectura:
        con = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True,
                              timeout=30)
    else:
        os.makedirs(config.META_DIR, exist_ok=True)
        con = sqlite3.connect(config.DB_PATH, timeout=60)
        con.executescript(SCHEMA)
    con.row_factory = sqlite3.Row
    return con


def pid_vivo(pid: int) -> bool:
    """Comprobación segura en Windows de si un PID sigue vivo (nunca mata)."""
    import ctypes
    SYNCHRONIZE, WAIT_TIMEOUT = 0x00100000, 0x102
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not h:
        return False
    try:
        return k32.WaitForSingleObject(h, 0) == WAIT_TIMEOUT
    finally:
        k32.CloseHandle(h)


def fts_query_desde_texto(q: str) -> str:
    """Convierte texto libre del usuario en una consulta FTS5 segura (AND de
    términos con prefijo). unicode61 remove_diacritics ya iguala acentos."""
    tokens = re.findall(r"[\w]+", q, flags=re.UNICODE)
    if not tokens:
        return '""'
    return " ".join(f'"{t}"*' for t in tokens[:12])
