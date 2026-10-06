"""Geração de documentos .docx no padrão institucional (cabeçalho verde)."""
from datetime import datetime
from io import BytesIO

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

import db
import prazos

VERDE = RGBColor(0x1A, 0x5C, 0x37)


def _sombrear(cell, hex_cor):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_cor)
    tcPr.append(shd)


def _base(titulo, subtitulo):
    doc = Document()
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2)
        s.top_margin = s.bottom_margin = Cm(1.8)
    st = doc.styles["Normal"]
    st.font.name = "Arial"
    st.font.size = Pt(10)

    cab = doc.add_table(rows=1, cols=1)
    c = cab.rows[0].cells[0]
    _sombrear(c, "1A5C37")
    p = c.paragraphs[0]
    r = p.add_run("ASSEMBLEIA LEGISLATIVA DO ESTADO DO CEARÁ")
    r.bold, r.font.size, r.font.color.rgb = True, Pt(12), RGBColor(255, 255, 255)
    p2 = c.add_paragraph()
    r2 = p2.add_run("Departamento de Administração · Núcleo de Patrimônio")
    r2.font.size, r2.font.color.rgb = Pt(9), RGBColor(255, 255, 255)

    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rh = h.add_run(titulo)
    rh.bold, rh.font.size, rh.font.color.rgb = True, Pt(14), VERDE
    if subtitulo:
        s = doc.add_paragraph()
        s.alignment = WD_ALIGN_PARAGRAPH.CENTER
        s.add_run(subtitulo).italic = True
    return doc


def _secao(doc, texto):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    r = p.add_run(texto.upper())
    r.bold, r.font.color.rgb = True, VERDE


def _tabela(doc, cabecalho, linhas, larguras=None):
    t = doc.add_table(rows=1, cols=len(cabecalho))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(cabecalho):
        cel = t.rows[0].cells[i]
        _sombrear(cel, "1A5C37")
        run = cel.paragraphs[0].add_run(h)
        run.bold, run.font.size, run.font.color.rgb = True, Pt(9), RGBColor(255, 255, 255)
    for ln in linhas:
        cells = t.add_row().cells
        for i, v in enumerate(ln):
            run = cells[i].paragraphs[0].add_run("" if v is None else str(v))
            run.font.size = Pt(9)
    if larguras:
        for row in t.rows:
            for i, w in enumerate(larguras):
                row.cells[i].width = Cm(w)
    return t


def _nota(doc, texto):
    t = doc.add_table(rows=1, cols=1)
    c = t.rows[0].cells[0]
    _sombrear(c, "EEF4F0")
    r = c.paragraphs[0].add_run(texto)
    r.font.size, r.italic = Pt(8.5), True


def _bytes(doc):
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def dossie_os(os_id: int, usuario: str) -> bytes:
    o = db.um(
        """SELECT os.*, ci.codigo, ci.descricao AS item_desc, c.empresa, c.cnpj,
                  c.processo, c.pregao, c.numero AS contrato_num
           FROM os JOIN contrato c ON c.id=os.contrato_id
           LEFT JOIN contrato_item ci ON ci.id=os.item_id WHERE os.id=?""",
        (os_id,),
    )
    a = prazos.analisar(o)
    doc = _base(f"DOSSIÊ DE FISCALIZAÇÃO — {o['numero']}",
                f"Processo {o['processo']} · {o['pregao']} · Contrato {o['contrato_num']}")

    _secao(doc, "1. Identificação")
    _tabela(doc, ["Campo", "Informação"], [
        ("Contratada", f"{o['empresa']} (CNPJ {o['cnpj']})"),
        ("Item contratual", f"{o['codigo']} — {o['item_desc']}"),
        ("Emissão da OS", prazos.fmt(prazos._dt(o["emitida_em"]))),
        ("Prioridade", o["prioridade"]),
        ("Setor / solicitante", f"{o['setor']} / {o['solicitante']}"),
        ("Local de execução", o["local_execucao"]),
        ("Descrição", o["descricao"]),
        ("Situação apurada", a["situacao"]),
    ], [5, 12])

    _secao(doc, "2. Bens patrimoniais envolvidos")
    bens = db.consultar("SELECT * FROM os_bem WHERE os_id=?", (os_id,))
    _tabela(doc, ["Tombo", "TAG", "Descrição", "Defeito relatado", "Localização"],
            [(b["tombo"], b["tag"], b["descricao"], b["defeito"], b["localizacao"]) for b in bens]
            or [("—",) * 5])

    _secao(doc, "3. Prazos contratuais")
    _tabela(doc, ["Etapa", "Prazo", "Cumprido em", "Resultado"], [
        (et, prazos.fmt(pz), prazos.fmt(fe),
         "No prazo" if (pz and fe and fe <= pz) else
         ("ATRASO" if (pz and fe and fe > pz) else "Pendente"))
        for et, pz, fe in a["marcos"]
    ])
    if a["fim_garantia"]:
        doc.add_paragraph(f"Garantia do serviço até {prazos.fmt(a['fim_garantia'])}.")
    _nota(doc, "Prazos calculados automaticamente a partir dos eventos registrados e da "
               "parametrização vigente (dias úteis descontam fins de semana e feriados cadastrados).")

    _secao(doc, "4. Histórico de eventos")
    _tabela(doc, ["Data/hora", "Evento", "Resp. ALECE", "Resp. contratada", "Observação", "Registrado por"],
            [(prazos.fmt(prazos._dt(e["data_hora"])), e["tipo"], e["responsavel_alece"],
              e["responsavel_contratada"], e["observacao"], e["registrado_por"]) for e in a["eventos"]]
            or [("—",) * 6])

    _secao(doc, "5. Ocorrências")
    oc = db.consultar("SELECT * FROM ocorrencia WHERE os_id=? ORDER BY data", (os_id,))
    _tabela(doc, ["Data", "Tipo", "Gravidade", "Descrição", "Providência", "Status"],
            [(x["data"], x["tipo"], x["gravidade"], x["descricao"], x["providencia"], x["status"]) for x in oc]
            or [("—",) * 6])

    _secao(doc, "6. Evidências arquivadas")
    evs = db.consultar("SELECT * FROM evidencia WHERE os_id=? ORDER BY enviado_em", (os_id,))
    _tabela(doc, ["Tipo", "Arquivo", "SHA-256 (12 primeiros)", "Enviado em", "Por"],
            [(x["tipo"], x["arquivo"].split("/")[-1], x["sha256"][:12], x["enviado_em"], x["enviado_por"]) for x in evs]
            or [("—",) * 5])
    _nota(doc, "O código SHA-256 é a 'impressão digital' de cada arquivo no momento do registro. "
               "Qualquer alteração posterior no arquivo muda o código, permitindo comprovar a integridade da evidência.")

    doc.add_paragraph()
    doc.add_paragraph(f"Fortaleza/CE, {datetime.now():%d/%m/%Y}.").alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for linha in ("_______________________________________", "Fiscal Técnico do Contrato"):
        doc.add_paragraph(linha).alignment = WD_ALIGN_PARAGRAPH.CENTER
    rod = doc.add_paragraph(f"Gerado pelo Sistema de Fiscalização de Contratos em {db.agora()} por {usuario}.")
    rod.runs[0].font.size = Pt(7)
    return _bytes(doc)


def notificacao(oc_id: int, usuario: str) -> bytes:
    x = db.um(
        """SELECT oc.*, os.numero AS os_num, c.empresa, c.cnpj, c.processo, c.numero AS contrato_num
           FROM ocorrencia oc LEFT JOIN os ON os.id=oc.os_id
           JOIN contrato c ON c.id=COALESCE(os.contrato_id,1) WHERE oc.id=?""",
        (oc_id,),
    )
    doc = _base("NOTIFICAÇÃO À CONTRATADA", f"Minuta — Processo {x['processo']} · Contrato {x['contrato_num']}")
    doc.add_paragraph(f"À {x['empresa']} — CNPJ {x['cnpj']}")
    doc.add_paragraph(
        "A Fiscalização Técnica do contrato, no exercício das atribuições previstas no art. 117 da "
        "Lei nº 14.133/2021 e no Ato Normativo ALECE nº 337/2023, NOTIFICA essa empresa acerca da "
        "ocorrência abaixo descrita, para que adote as providências de saneamento no prazo indicado."
    )
    _tabela(doc, ["Campo", "Informação"], [
        ("Ordem de Serviço", x["os_num"] or "Não vinculada"),
        ("Data da constatação", x["data"]),
        ("Tipo", x["tipo"]),
        ("Gravidade", x["gravidade"]),
        ("Descrição", x["descricao"]),
        ("Providência exigida", x["providencia"]),
        ("Prazo para saneamento", x["prazo_saneamento"] or "a definir"),
    ], [5, 12])
    doc.add_paragraph(
        "O não atendimento poderá ensejar glosa proporcional e a comunicação ao Gestor do Contrato para "
        "instauração de processo administrativo de responsabilização, assegurados o contraditório e a ampla "
        "defesa (arts. 155 a 158 da Lei nº 14.133/2021)."
    )
    _nota(doc, "MINUTA gerada pelo sistema — revisar redação e fundamentação antes de assinar e enviar.")
    doc.add_paragraph(f"Fortaleza/CE, {datetime.now():%d/%m/%Y}.").alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for linha in ("_______________________________________", "Fiscal Técnico do Contrato"):
        doc.add_paragraph(linha).alignment = WD_ALIGN_PARAGRAPH.CENTER
    return _bytes(doc)

def termo_recebimento_provisorio(medicao_id: int, usuario: str) -> bytes:
    """Gera o Termo de Recebimento Provisório da Medição Mensal (.docx)."""
    m = db.um(
        """SELECT m.*, c.empresa, c.cnpj, c.processo, c.pregao, c.numero AS contrato_num
           FROM medicao m
           JOIN contrato c ON c.id = m.contrato_id
           WHERE m.id = ?""",
        (medicao_id,),
    )
    
    if not m:
        raise ValueError("Medição não encontrada.")

    # Consulta todas as OSs pertencentes a esta medição
    oss = db.consultar(
        """SELECT os.numero, os.emitida_em, os.setor, ci.codigo AS item_codigo,
                  ci.descricao AS item_desc, mo.valor_atestado
           FROM medicao_os mo
           JOIN os ON os.id = mo.os_id
           LEFT JOIN contrato_item ci ON ci.id = os.item_id
           WHERE mo.medicao_id = ?
           ORDER BY os.numero ASC""",
        (medicao_id,),
    )

    doc = _base(
        f"TERMO DE RECEBIMENTO PROVISÓRIO — MEDIÇÃO {m['numero']}",
        f"Processo {m['processo']} · {m['pregao']} · Contrato {m['contrato_num']}",
    )

    _secao(doc, "1. Identificação do Período e Contratada")
    _tabela(
        doc,
        ["Campo", "Informação"],
        [
            ("Contratada", f"{m['empresa']} (CNPJ {m['cnpj']})"),
            ("Mês de referência", m["mes_referencia"]),
            ("Período de apuração", f"{m['data_inicio']} a {m['data_fim']}"),
            ("Valor total apurado", f"R$ {m['valor_total']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")),
            ("Observações", m["observacao"] or "Sem observações adicionais."),
        ],
        [5, 12],
    )

    _secao(doc, "2. Ordens de Serviço Consolidadas na Medição")
    linhas_os = [
        (
            o["numero"],
            o["emitida_em"],
            o["setor"],
            f"{o['item_codigo']} — {o['item_desc']}",
            f"R$ {o['valor_atestado']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        )
        for o in oss
    ]
    
    _tabela(
        doc,
        ["Nº OS", "Emitida em", "Setor", "Item Contratual", "Valor Atestado"],
        linhas_os or [("—",) * 5],
        [3, 3, 4, 4, 3],
    )

    # Consulta se há checklist gravado para incluir no Termo Provisório
    chk = db.obter_checklist_medicao(medicao_id)
    if chk:
        _secao(doc, "3. Verificação de Regularidade Fiscal e Trabalhista")
        _tabela(
            doc,
            ["Item / Certidão", "Situação na Consulta"],
            [
                ("Regularidade Cadastral / SICAF", "REGULAR" if chk["sicaf_regular"] else "PENDENTE/IRREGULAR"),
                ("CND Federal e Prev. Social (Receita/PGFN)", "VÁLIDA" if chk["cnd_federal_valida"] else "PENDENTE/IRREGULAR"),
                ("CRF - FGTS (Caixa Econômica)", "VÁLIDA" if chk["fgts_valido"] else "PENDENTE/IRREGULAR"),
                ("CNDT - Certidão Trabalhista (TST)", "VÁLIDA" if chk["cndt_valida"] else "PENDENTE/IRREGULAR"),
                ("CND Estadual (SEFAZ)", "VÁLIDA" if chk["cnd_estadual_valida"] else "PENDENTE/IRREGULAR"),
                ("CND Municipal (Prefeitura)", "VÁLIDA" if chk["cnd_municipal_valida"] else "PENDENTE/IRREGULAR"),
                ("Resultado Final da Análise", chk["situacao_final"]),
            ],
            [9, 8],
        )

    _secao(doc, "3. Atesto de Recebimento Provisório")
    doc.add_paragraph(
        "Atestamos, para fins do disposto no art. 140, inciso II, alínea 'a', da Lei nº 14.133/2021 "
        "e do Ato Normativo ALECE nº 337/2023, que os serviços especificados nas Ordens de Serviço "
        "relação acima foram prestados e conferidos provisoriamente, estando em conformidade com as "
        "especificações técnicas do contrato."
    )
    
    _nota(
        doc,
        "Este termo constitui o Recebimento Provisório da medição mensal para instrução da nota fiscal. "
        "O pagamento permanece condicionado à verificação da regularidade fiscal e trabalhista da contratada."
    )

    doc.add_paragraph()
    doc.add_paragraph(f"Fortaleza/CE, {datetime.now():%d/%m/%Y}.").alignment = WD_ALIGN_PARAGRAPH.RIGHT
    
    doc.add_paragraph()
    for linha in ("_______________________________________", "Fiscal Técnico do Contrato"):
        doc.add_paragraph(linha).alignment = WD_ALIGN_PARAGRAPH.CENTER

    rod = doc.add_paragraph(
        f"Documento gerado pelo Sistema de Fiscalização de Contratos em {db.agora()} por {usuario}."
    )
    rod.runs[0].font.size = Pt(7)

    return _bytes(doc)
