"""SQLite: paneles, conversación, documentos, capítulos y su índice de texto (FTS5)."""
import sqlite3
from contextlib import contextmanager

import config

ESQUEMA = """
CREATE TABLE IF NOT EXISTS paneles(
  id TEXT PRIMARY KEY, nombre TEXT, descripcion TEXT, contexto TEXT, agentes TEXT, orden INTEGER);
CREATE TABLE IF NOT EXISTS mensajes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, panel_id TEXT, pregunta_id INTEGER, rol TEXT,
  agente_id TEXT, texto TEXT, imagenes TEXT, error INTEGER DEFAULT 0, ts REAL);
CREATE TABLE IF NOT EXISTS docs(
  id TEXT PRIMARY KEY, panel_id TEXT, agente_id TEXT, ambito TEXT, pregunta_id INTEGER,
  nombre TEXT, fabrica_id TEXT, estado TEXT, paso TEXT, error TEXT, caracteres INTEGER DEFAULT 0,
  texto TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS capitulos(
  id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT, agente_id TEXT, orden INTEGER,
  titulo TEXT, resumen TEXT, claves TEXT, texto TEXT, simplificado INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS semillas(nombre TEXT PRIMARY KEY);   -- paneles de serie ya sembrados
CREATE INDEX IF NOT EXISTS i_cap_doc ON capitulos(doc_id);
CREATE INDEX IF NOT EXISTS i_cap_ag ON capitulos(agente_id);
CREATE INDEX IF NOT EXISTS i_docs_ag ON docs(agente_id);
CREATE VIRTUAL TABLE IF NOT EXISTS capfts USING fts5(
  titulo, resumen, texto, cap_id UNINDEXED, agente_id UNINDEXED,
  tokenize='unicode61 remove_diacritics 2');
"""
# columnas añadidas después de la primera versión
MIGRACIONES = [("mensajes", "ronda", "INTEGER DEFAULT 0"),
               ("mensajes", "adjuntos", "TEXT"),
               ("mensajes", "fuentes", "TEXT")]


@contextmanager
def db():
    c = sqlite3.connect(config.DB, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init():
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(ESQUEMA)
        for tabla, col, tipo in MIGRACIONES:
            if col not in {r["name"] for r in c.execute(f"PRAGMA table_info({tabla})")}:
                c.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}")
        # un reinicio corta los hilos de procesado: que no queden «en curso» para siempre
        c.execute("UPDATE docs SET estado='error', error='Interrumpido por un reinicio; pulsa Reprocesar' "
                  "WHERE estado NOT IN ('listo','error')")
