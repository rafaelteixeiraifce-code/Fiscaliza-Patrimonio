"""Regras de prazo e situação da OS.

O fluxo de uma OS é uma sequência de eventos. A situação e os prazos
são sempre DERIVADOS dos eventos registrados — nunca digitados à mão.
Assim o sistema não "esquece" de marcar atraso.
"""
from datetime import datetime, timedelta

import db

# Ordem do fluxo. Cada etapa tem o evento que a conclui.
EVENTOS = [
    "Emissão da OS",
    "Avaliação inicial",
    "Retirada (1ª via)",
    "Comunicação de atraso",
    "Devolução (2ª via)",
    "Conferência — aceite",
    "Conferência — rejeição",
    "Reincidência em garantia",
    "Outro registro",
]

FMT = "%Y-%m-%d %H:%M"


def _dt(s):
    if not s:
        return None
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def feriados():
    return {r["data"] for r in db.consultar("SELECT data FROM feriado")}


def somar(inicio: datetime, chave: str) -> datetime:
    p = db.um("SELECT quantidade, unidade FROM prazo WHERE chave=?", (chave,))
    if not p or inicio is None:
        return None
    q, u = p["quantidade"], p["unidade"]
    if u == "horas":
        return inicio + timedelta(hours=q)
    if u == "dias_corridos":
        return inicio + timedelta(days=q)
    # dias úteis: conta a partir do dia seguinte, pula fim de semana e feriado,
    # vence no fim do expediente (23:59) do último dia útil
    fer, d, n = feriados(), inicio, 0
    while n < int(q):
        d += timedelta(days=1)
        if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in fer:
            n += 1
    return d.replace(hour=23, minute=59, second=0)


def dias_uteis_entre(a: datetime, b: datetime) -> int:
    fer, n, d = feriados(), 0, a.date()
    while d < b.date():
        d += timedelta(days=1)
        if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in fer:
            n += 1
    return n


def ultimo(eventos, tipo):
    xs = [e for e in eventos if e["tipo"] == tipo]
    return _dt(xs[-1]["data_hora"]) if xs else None


def analisar(os_row) -> dict:
    """Retorna situação, próxima etapa, prazo e marcos de uma OS."""
    ev = db.consultar(
        "SELECT * FROM evento WHERE os_id=? ORDER BY data_hora, id", (os_row["id"],)
    )
    agora = datetime.now()
    emissao = _dt(os_row["emitida_em"])
    urgente = os_row["prioridade"] == "Urgente"
    avaliacao = ultimo(ev, "Avaliação inicial")
    retirada = ultimo(ev, "Retirada (1ª via)")
    devolucao = ultimo(ev, "Devolução (2ª via)")
    aceite = ultimo(ev, "Conferência — aceite")
    rejeicao = ultimo(ev, "Conferência — rejeição")

    marcos = []  # (etapa, prazo, cumprido_em)

    if urgente:
        p_ret = somar(emissao, "avaliacao_urgente")
        marcos.append(("Recolhimento (urgente)", p_ret, retirada))
    else:
        p_av = somar(emissao, "avaliacao_normal")
        marcos.append(("Avaliação inicial", p_av, avaliacao))
        p_ret = somar(avaliacao, "retirada") if avaliacao else None
        marcos.append(("Retirada", p_ret, retirada))

    p_dev = somar(retirada, "devolucao") if retirada else None
    marcos.append(("Devolução", p_dev, devolucao))
    fim_garantia = somar(aceite, "garantia") if aceite else None

    # situação
    if os_row.get("cancelada"):
        sit, prox, prazo = "Cancelada", None, None
    elif aceite and (not rejeicao or aceite > rejeicao):
        sit = "Em garantia" if fim_garantia and agora <= fim_garantia else "Encerrada"
        prox, prazo = None, fim_garantia
    elif rejeicao and (not devolucao or rejeicao > devolucao):
        sit, prox, prazo = "Rejeitada — aguardando correção", "Nova devolução", None
    else:
        sit, prox, prazo = "Aberta", None, None
        for etapa, pz, feito in marcos:
            if not feito:
                prox, prazo = etapa, pz
                break
        if prox is None:
            prox = "Conferência pela fiscalização"
        if prazo and agora > prazo:
            sit = "ATRASADA"

    # atrasos já consumados (etapa cumprida depois do prazo)
    atrasos = []
    for etapa, pz, feito in marcos:
        if pz and feito and feito > pz:
            atrasos.append((etapa, dias_uteis_entre(pz, feito)))
        elif pz and not feito and agora > pz and sit not in ("Cancelada",):
            atrasos.append((etapa, dias_uteis_entre(pz, agora)))

    return {
        "situacao": sit,
        "proxima_etapa": prox,
        "prazo": prazo,
        "marcos": marcos,
        "atrasos": atrasos,
        "fim_garantia": fim_garantia,
        "eventos": ev,
    }


def fmt(d):
    return d.strftime("%d/%m/%Y %H:%M") if d else "—"
