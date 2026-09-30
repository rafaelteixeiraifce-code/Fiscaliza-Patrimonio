"""Camada de dados — SQLite.

Toda escrita passa por `executar()`, que também grava a trilha de auditoria.
Os caminhos podem apontar para a pasta de rede via variáveis de ambiente:
    FISCALIZA_DADOS   -> pasta onde fica o banco (padrão: ./dados)
    FISCALIZA_EVID    -> pasta das evidências   (padrão: ./dados/evidencias)
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
DADOS = Path(os.environ.get("FISCALIZA_DADOS", BASE / "dados"))
EVID = Path(os.environ.get("FISCALIZA_EVID", DADOS / "evidencias"))
DB_PATH = DADOS / "fiscaliza.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS contrato (
    id INTEGER PRIMARY KEY,
    numero TEXT, processo TEXT, pregao TEXT,
    empresa TEXT, cnpj TEXT,
    vigencia_inicio TEXT, vigencia_fim TEXT,
    valor_global REAL, gestor TEXT, fiscal TEXT, obs TEXT
);
CREATE TABLE IF NOT EXISTS contrato_item (
    id INTEGER PRIMARY KEY,
    contrato_id INTEGER REFERENCES contrato(id),
    codigo TEXT, descricao TEXT, catser TEXT, valor REAL
);
CREATE TABLE IF NOT EXISTS prazo (
    chave TEXT PRIMARY KEY, descricao TEXT,
    quantidade REAL, unidade TEXT,          -- horas | dias_uteis | dias_corridos
    base_legal TEXT
);
CREATE TABLE IF NOT EXISTS feriado (data TEXT PRIMARY KEY, descricao TEXT);

CREATE TABLE IF NOT EXISTS os (
    id INTEGER PRIMARY KEY,
    numero TEXT UNIQUE,
    contrato_id INTEGER REFERENCES contrato(id),
    item_id INTEGER REFERENCES contrato_item(id),
    emitida_em TEXT, prioridade TEXT,
    setor TEXT, solicitante TEXT, descricao TEXT,
    local_execucao TEXT,                    -- Sede da contratada | Dependências da ALECE
    valor_previsto REAL, valor_atestado REAL,
    cancelada INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS os_bem (
    id INTEGER PRIMARY KEY,
    os_id INTEGER REFERENCES os(id),
    tombo TEXT, tag TEXT, descricao TEXT, defeito TEXT, localizacao TEXT
);
CREATE TABLE IF NOT EXISTS evento (
    id INTEGER PRIMARY KEY,
    os_id INTEGER REFERENCES os(id),
    tipo TEXT, data_hora TEXT,
    responsavel_alece TEXT, responsavel_contratada TEXT,
    observacao TEXT,
    registrado_por TEXT, registrado_em TEXT
);
CREATE TABLE IF NOT EXISTS ocorrencia (
    id INTEGER PRIMARY KEY,
    os_id INTEGER REFERENCES os(id),
    data TEXT, tipo TEXT, gravidade TEXT,
    descricao TEXT, providencia TEXT,
    prazo_saneamento TEXT, status TEXT,
    registrado_por TEXT, registrado_em TEXT
);
CREATE TABLE IF NOT EXISTS evidencia (
    id INTEGER PRIMARY KEY,
    os_id INTEGER, evento_id INTEGER, ocorrencia_id INTEGER,
    tipo TEXT, arquivo TEXT, sha256 TEXT, descricao TEXT,
    enviado_por TEXT, enviado_em TEXT
);
CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY,
    quando TEXT, usuario TEXT, acao TEXT, detalhe TEXT
);
"""


def agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def conexao():
    DADOS.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def consultar(sql, params=()):
    with conexao() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def um(sql, params=()):
    r = consultar(sql, params)
    return r[0] if r else None


def executar(sql, params=(), usuario="-", acao=None, detalhe=""):
    """Executa uma escrita e registra na auditoria. Retorna lastrowid."""
    with conexao() as con:
        cur = con.execute(sql, params)
        if acao:
            con.execute(
                "INSERT INTO auditoria (quando, usuario, acao, detalhe) VALUES (?,?,?,?)",
                (agora(), usuario, acao, detalhe),
            )
        return cur.lastrowid


def iniciar():
    EVID.mkdir(parents=True, exist_ok=True)
    with conexao() as con:
        con.executescript(SCHEMA)
        if con.execute("SELECT COUNT(*) FROM contrato").fetchone()[0] == 0:
            _semente(con)


def _semente(con):
    """Dados iniciais do PE 001/2026 (Sumário Executivo e Parecer Técnico)."""
    con.execute(
        """INSERT INTO contrato (id, numero, processo, pregao, empresa, cnpj,
           vigencia_inicio, vigencia_fim, valor_global, gestor, fiscal, obs)
           VALUES (1, 'a definir', '13051/2025', 'PE 001/2026',
           'BMS Empreendimento de Serviços LTDA', '63.008.305/0001-60',
           '', '', 217000.00, 'a designar', 'a designar',
           'Lote único. Execução na sede da contratada (Bauru/SP). Subcontratação vedada.')"""
    )
    con.executemany(
        "INSERT INTO contrato_item (contrato_id, codigo, descricao, catser, valor) VALUES (1,?,?,?,?)",
        [
            ("01", "Manutenção corretiva de mobiliário", "5410", 147000.00),
            ("02", "Higienização e limpeza de estofados", "17132", 25000.00),
            ("03", "Substituição de espuma e revestimento", "5410", 45000.00),
        ],
    )
    con.executemany(
        "INSERT INTO prazo VALUES (?,?,?,?,?)",
        [
            ("avaliacao_normal", "Avaliação inicial (normal)", 2, "dias_uteis", "TR, Seção 6"),
            ("avaliacao_urgente", "Avaliação/recolhimento (urgente)", 24, "horas", "TR, Seção 6"),
            ("retirada", "Retirada após avaliação/autorização", 1, "dias_uteis", "TR, Seção 6"),
            ("devolucao", "Execução e devolução após recolhimento", 10, "dias_uteis", "TR, Seção 6"),
            ("aviso_atraso", "Antecedência mínima do aviso de atraso", 2, "dias_corridos", "TR 9.6 (versão ETP)"),
            ("garantia", "Garantia após aceite", 90, "dias_corridos", "ETP 3.5"),
        ],
    )
    con.executemany(
        "INSERT INTO feriado VALUES (?,?)",
        [
            ("2026-10-12", "Nossa Senhora Aparecida"),
            ("2026-11-02", "Finados"),
            ("2026-11-15", "Proclamação da República"),
            ("2026-11-20", "Consciência Negra"),
            ("2026-12-25", "Natal"),
            ("2027-01-01", "Confraternização Universal"),
            ("2027-03-19", "São José (CE)"),
            ("2027-03-25", "Data Magna do Ceará"),
            ("2027-03-26", "Sexta-feira Santa"),
            ("2027-04-13", "Fundação de Fortaleza"),
        ],
    )
