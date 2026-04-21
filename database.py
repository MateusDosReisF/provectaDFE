import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), 'provecta.db')

STATUS = {
    'pendente':   'Pendente',
    'entrada_ok': 'Entrada OK',
    'cancelada':  'Cancelada',
    'ignorada':   'Ignorada',
}

DDL = """
CREATE TABLE IF NOT EXISTS documentos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nsu         TEXT    UNIQUE NOT NULL,
    tipo        TEXT,
    schema_doc  TEXT,
    chave       TEXT,
    chave_ref   TEXT,
    tipo_evento TEXT,
    emitente    TEXT,
    destinatario TEXT,
    valor       TEXT,
    data_emissao TEXT,
    xml_raw     TEXT,
    status      TEXT DEFAULT 'pendente',
    data_entrada TEXT,
    observacao  TEXT,
    criado_em   TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT
);
"""


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def inicializar():
    with _conn() as con:
        con.executescript(DDL)


def salvar_documento(doc) -> bool:
    """Insere ou ignora se NSU já existe. Retorna True se inseriu."""
    with _conn() as con:
        cur = con.execute("""
            INSERT OR IGNORE INTO documentos
                (nsu, tipo, schema_doc, chave, chave_ref, tipo_evento,
                 emitente, destinatario, valor, data_emissao, xml_raw, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            doc.nsu, doc.tipo, doc.schema, doc.chave,
            getattr(doc, 'chave_ref', ''),
            getattr(doc, 'tipo_evento', ''),
            doc.emitente, doc.destinatario,
            doc.valor, doc.data_emissao, doc.xml_raw,
            'cancelada' if getattr(doc, 'tipo_evento', '') in ('110111', '110112') else 'pendente',
        ))
        inseriu = cur.rowcount > 0

    # Se é cancelamento, atualiza a NF-e referenciada
    chave_ref = getattr(doc, 'chave_ref', '')
    if inseriu and chave_ref and getattr(doc, 'tipo_evento', '') in ('110111', '110112'):
        cancelar_por_chave(chave_ref)

    return inseriu


def cancelar_por_chave(chave: str):
    with _conn() as con:
        con.execute(
            "UPDATE documentos SET status='cancelada' WHERE chave=? AND status != 'cancelada'",
            (chave,)
        )


def atualizar_status(nsu: str, status: str, observacao: str = ''):
    agora = datetime.now().strftime('%d/%m/%Y %H:%M') if status == 'entrada_ok' else None
    with _conn() as con:
        con.execute(
            "UPDATE documentos SET status=?, data_entrada=COALESCE(?,data_entrada), observacao=? WHERE nsu=?",
            (status, agora, observacao or None, nsu)
        )


def atualizar_status_lote(nsus: list[str], status: str):
    agora = datetime.now().strftime('%d/%m/%Y %H:%M') if status == 'entrada_ok' else None
    with _conn() as con:
        for nsu in nsus:
            con.execute(
                "UPDATE documentos SET status=?, data_entrada=COALESCE(?,data_entrada) WHERE nsu=?",
                (status, agora, nsu)
            )


def listar_documentos(status_filtro: str = 'todos', busca: str = '') -> list[sqlite3.Row]:
    query = "SELECT * FROM documentos WHERE 1=1"
    params = []
    if status_filtro != 'todos':
        query += " AND status=?"
        params.append(status_filtro)
    if busca:
        query += " AND (chave LIKE ? OR emitente LIKE ? OR destinatario LIKE ? OR nsu LIKE ?)"
        like = f'%{busca}%'
        params.extend([like, like, like, like])
    query += " ORDER BY CAST(nsu AS INTEGER) DESC"
    with _conn() as con:
        return con.execute(query, params).fetchall()


def buscar_por_nsu(nsu: str) -> sqlite3.Row | None:
    with _conn() as con:
        return con.execute("SELECT * FROM documentos WHERE nsu=?", (nsu,)).fetchone()


def get_config(chave: str, default: str = '') -> str:
    with _conn() as con:
        row = con.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
        return row['valor'] if row else default


def set_config(chave: str, valor: str):
    with _conn() as con:
        con.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES (?,?)", (chave, valor))


def estatisticas() -> dict:
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM documentos").fetchone()[0]
        por_status = {
            row['status']: row['cnt']
            for row in con.execute("SELECT status, COUNT(*) as cnt FROM documentos GROUP BY status").fetchall()
        }
    return {'total': total, **por_status}
