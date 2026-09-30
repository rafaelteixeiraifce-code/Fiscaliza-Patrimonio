"""Sistema de Fiscalização de Contratos — Núcleo de Patrimônio/ALECE.

Rodar:  streamlit run app.py
"""
import hashlib
import re
from datetime import datetime, date, time
from pathlib import Path

import pandas as pd
import streamlit as st

import db
import documentos
import prazos

st.set_page_config(page_title="Fiscalização de Contratos — ALECE", page_icon="📋", layout="wide")
db.iniciar()

st.markdown(
    """<style>
    .faixa{background:#1a5c37;color:#fff;padding:10px 16px;border-radius:6px;margin-bottom:12px}
    .faixa b{font-size:1.1rem}
    </style>""",
    unsafe_allow_html=True,
)

PRIORIDADES = ["Normal", "Urgente"]
TIPOS_OC = ["Atraso", "Qualidade do serviço", "Dano/extravio de bem", "Documental",
            "Regularidade fiscal/trabalhista", "Conduta da equipe", "Outro"]
GRAVIDADES = ["Leve", "Média", "Grave"]
STATUS_OC = ["Aberta", "Notificada", "Saneada", "Encaminhada ao Gestor", "Arquivada"]
TIPOS_EVID = ["Foto", "Relatório técnico (1ª via)", "Relatório técnico (2ª via)",
              "E-mail", "Nota fiscal", "Certidão", "Notificação", "Resposta da contratada", "Outro"]

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown('<div class="faixa"><b>📋 Fiscalização</b><br>Núcleo de Patrimônio · ALECE</div>',
                unsafe_allow_html=True)
    usuario = st.text_input("Seu nome", value=st.session_state.get("usuario", ""),
                            placeholder="Quem está registrando")
    st.session_state["usuario"] = usuario
    pagina = st.radio("Menu", ["Painel", "Ordens de Serviço", "Nova OS", "Ocorrências",
                               "Contrato e prazos", "Auditoria"])
    c = db.um("SELECT * FROM contrato WHERE id=1")
    st.caption(f"{c['pregao']} · {c['empresa']}")

if not usuario.strip():
    st.info("Informe seu nome na barra lateral. Todo registro fica assinado com ele na trilha de auditoria.")
    st.stop()


# ---------------------------------------------------------------- helpers
def brl(v):
    return f"R$ {v or 0:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def salvar_evidencia(arquivo, os_row, tipo, descricao, evento_id=None, ocorrencia_id=None):
    dados = arquivo.getvalue()
    sha = hashlib.sha256(dados).hexdigest()
    pasta = db.EVID / (os_row["numero"] if os_row else "SEM-OS")
    pasta.mkdir(parents=True, exist_ok=True)
    nome = re.sub(r"[^\w.\-]", "_", arquivo.name)
    destino = pasta / f"{datetime.now():%Y%m%d-%H%M%S}_{nome}"
    destino.write_bytes(dados)
    db.executar(
        """INSERT INTO evidencia (os_id, evento_id, ocorrencia_id, tipo, arquivo, sha256,
           descricao, enviado_por, enviado_em) VALUES (?,?,?,?,?,?,?,?,?)""",
        (os_row["id"] if os_row else None, evento_id, ocorrencia_id, tipo, str(destino), sha,
         descricao, usuario, db.agora()),
        usuario, "Anexou evidência", f"{destino.name} sha256={sha[:12]}",
    )


def lista_os():
    rows = db.consultar(
        """SELECT os.*, ci.codigo AS item FROM os LEFT JOIN contrato_item ci ON ci.id=os.item_id
           ORDER BY os.id DESC"""
    )
    for r in rows:
        a = prazos.analisar(r)
        r["situacao"], r["proxima"], r["prazo_dt"] = a["situacao"], a["proxima_etapa"], a["prazo"]
        r["n_bens"] = db.um("SELECT COUNT(*) n FROM os_bem WHERE os_id=?", (r["id"],))["n"]
    return rows


def proximo_numero():
    ano = date.today().year
    n = db.um("SELECT COUNT(*) n FROM os WHERE numero LIKE ?", (f"OS-{ano}-%",))["n"] + 1
    return f"OS-{ano}-{n:03d}"


def data_hora(label, key, padrao=None):
    padrao = padrao or datetime.now()
    c1, c2 = st.columns(2)
    d = c1.date_input(label, value=padrao.date(), key=key + "_d", format="DD/MM/YYYY")
    h = c2.time_input("Hora", value=time(padrao.hour, padrao.minute), key=key + "_h")
    return datetime.combine(d, h).strftime("%Y-%m-%d %H:%M")


# ================================================================ PAINEL
if pagina == "Painel":
    st.markdown(f'<div class="faixa"><b>Painel do contrato</b> — {c["empresa"]} · Processo {c["processo"]}</div>',
                unsafe_allow_html=True)
    rows = lista_os()
    itens = db.consultar("SELECT * FROM contrato_item WHERE contrato_id=1")
    atestado = db.um("SELECT COALESCE(SUM(valor_atestado),0) v FROM os WHERE cancelada=0")["v"]
    previsto_aberto = db.um(
        "SELECT COALESCE(SUM(valor_previsto),0) v FROM os WHERE cancelada=0 AND valor_atestado IS NULL")["v"]

    k = st.columns(5)
    k[0].metric("OS abertas", sum(r["situacao"] in ("Aberta", "ATRASADA", "Rejeitada — aguardando correção") for r in rows))
    k[1].metric("OS atrasadas", sum(r["situacao"] == "ATRASADA" for r in rows))
    k[2].metric("Bens fora da Casa", db.um(
        """SELECT COUNT(*) n FROM os_bem b JOIN os ON os.id=b.os_id
           WHERE EXISTS (SELECT 1 FROM evento e WHERE e.os_id=os.id AND e.tipo='Retirada (1ª via)')
             AND NOT EXISTS (SELECT 1 FROM evento e WHERE e.os_id=os.id AND e.tipo='Devolução (2ª via)')""")["n"])
    k[3].metric("Ocorrências abertas", db.um(
        "SELECT COUNT(*) n FROM ocorrencia WHERE status IN ('Aberta','Notificada')")["n"])
    k[4].metric("Saldo do contrato", brl(c["valor_global"] - atestado - previsto_aberto),
                help="Valor global − atestado − previsto em OS ainda não atestadas")

    st.subheader("Execução financeira por item")
    fin = []
    for it in itens:
        v = db.um("SELECT COALESCE(SUM(valor_atestado),0) a, COALESCE(SUM(CASE WHEN valor_atestado IS NULL "
                  "THEN valor_previsto END),0) p FROM os WHERE item_id=? AND cancelada=0", (it["id"],))
        fin.append({"Item": f"{it['codigo']} — {it['descricao']}", "Contratado": it["valor"],
                    "Atestado": v["a"], "Comprometido (OS abertas)": v["p"],
                    "Saldo": it["valor"] - v["a"] - v["p"],
                    "% executado": round(100 * v["a"] / it["valor"], 1) if it["valor"] else 0})
    st.dataframe(pd.DataFrame(fin), hide_index=True, width="stretch",
                 column_config={k_: st.column_config.NumberColumn(format="R$ %.2f")
                                for k_ in ["Contratado", "Atestado", "Comprometido (OS abertas)", "Saldo"]})

    st.subheader("Atenção agora")
    pend = [r for r in rows if r["situacao"] in ("ATRASADA", "Aberta", "Rejeitada — aguardando correção")]
    pend.sort(key=lambda r: (r["situacao"] != "ATRASADA", r["prazo_dt"] or datetime.max))
    if pend:
        st.dataframe(pd.DataFrame([{
            "OS": r["numero"], "Situação": r["situacao"], "Próxima etapa": r["proxima"],
            "Prazo": prazos.fmt(r["prazo_dt"]), "Setor": r["setor"], "Bens": r["n_bens"],
            "Prioridade": r["prioridade"]} for r in pend]), hide_index=True, width="stretch")
    else:
        st.success("Nenhuma OS pendente.")

    gar = [r for r in rows if r["situacao"] == "Em garantia"]
    if gar:
        st.subheader("Serviços em garantia")
        st.dataframe(pd.DataFrame([{"OS": r["numero"], "Garantia até": prazos.fmt(r["prazo_dt"]),
                                    "Setor": r["setor"]} for r in gar]), hide_index=True)

# ================================================================ NOVA OS
elif pagina == "Nova OS":
    st.markdown('<div class="faixa"><b>Emitir Ordem de Serviço</b></div>', unsafe_allow_html=True)
    itens = db.consultar("SELECT * FROM contrato_item WHERE contrato_id=1")
    with st.form("nova_os", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        numero = c1.text_input("Número da OS", value=proximo_numero())
        item = c2.selectbox("Item contratual", itens, format_func=lambda i: f"{i['codigo']} — {i['descricao']}")
        prioridade = c3.selectbox("Prioridade", PRIORIDADES)
        emitida = data_hora("Emitida em", "emissao")
        c4, c5 = st.columns(2)
        setor = c4.text_input("Setor solicitante")
        solicitante = c5.text_input("Solicitante / contato")
        local = st.radio("Local de execução", ["Sede da contratada", "Dependências da ALECE"], horizontal=True)
        descricao = st.text_area("Descrição do serviço solicitado")
        valor = st.number_input("Valor previsto (R$)", min_value=0.0, step=10.0,
                                help="Estimativa para controle de saldo. O valor atestado é informado na conferência.")
        st.markdown("**Bens patrimoniais** — um por linha")
        bens = st.data_editor(
            pd.DataFrame([{"Tombo": "", "TAG": "", "Descrição": "", "Defeito relatado": "", "Localização": ""}]),
            num_rows="dynamic", width="stretch", key="bens_nova")
        ok = st.form_submit_button("Emitir OS", type="primary")
    if ok:
        if not descricao or not setor:
            st.error("Setor e descrição são obrigatórios.")
        elif db.um("SELECT 1 FROM os WHERE numero=?", (numero,)):
            st.error("Já existe OS com esse número.")
        else:
            os_id = db.executar(
                """INSERT INTO os (numero, contrato_id, item_id, emitida_em, prioridade, setor, solicitante,
                   descricao, local_execucao, valor_previsto) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (numero, 1, item["id"], emitida, prioridade, setor, solicitante, descricao, local, valor),
                usuario, "Emitiu OS", numero)
            for _, b in bens.iterrows():
                if str(b["Tombo"]).strip() or str(b["Descrição"]).strip():
                    db.executar("INSERT INTO os_bem (os_id, tombo, tag, descricao, defeito, localizacao) VALUES (?,?,?,?,?,?)",
                                (os_id, b["Tombo"], b["TAG"], b["Descrição"], b["Defeito relatado"], b["Localização"]))
            db.executar("""INSERT INTO evento (os_id, tipo, data_hora, observacao, registrado_por, registrado_em)
                           VALUES (?,?,?,?,?,?)""",
                        (os_id, "Emissão da OS", emitida, descricao, usuario, db.agora()))
            st.success(f"{numero} emitida. Abra em **Ordens de Serviço** para registrar as próximas etapas.")

# ================================================================ LISTA / DETALHE OS
elif pagina == "Ordens de Serviço":
    rows = lista_os()
    if not rows:
        st.info("Nenhuma OS emitida ainda.")
        st.stop()
    filtro = st.multiselect("Filtrar situação", sorted({r["situacao"] for r in rows}))
    vis = [r for r in rows if not filtro or r["situacao"] in filtro]
    st.dataframe(pd.DataFrame([{
        "OS": r["numero"], "Situação": r["situacao"], "Item": r["item"], "Prioridade": r["prioridade"],
        "Setor": r["setor"], "Bens": r["n_bens"], "Próxima etapa": r["proxima"],
        "Prazo": prazos.fmt(r["prazo_dt"])} for r in vis]), hide_index=True, width="stretch")

    escolha = st.selectbox("Abrir OS", vis, format_func=lambda r: f"{r['numero']} — {r['situacao']} — {r['setor']}")
    o = db.um("SELECT * FROM os WHERE id=?", (escolha["id"],))
    a = prazos.analisar(o)
    st.markdown(f'<div class="faixa"><b>{o["numero"]}</b> · {a["situacao"]} · {o["prioridade"]}</div>',
                unsafe_allow_html=True)

    t1, t2, t3, t4, t5 = st.tabs(["Linha do tempo", "Registrar evento", "Bens", "Evidências", "Fechamento"])

    with t1:
        m = pd.DataFrame([{"Etapa": e, "Prazo": prazos.fmt(p), "Cumprido em": prazos.fmt(f),
                           "Resultado": "✅ No prazo" if (p and f and f <= p) else
                           ("⚠️ Atraso" if (p and f and f > p) else
                            ("🔴 Vencido" if (p and not f and datetime.now() > p) else "⏳ Pendente"))}
                          for e, p, f in a["marcos"]])
        st.dataframe(m, hide_index=True, width="stretch")
        for etapa, dias in a["atrasos"]:
            st.warning(f"{etapa}: {dias} dia(s) útil(eis) além do prazo.")
        st.markdown("**Eventos registrados**")
        st.dataframe(pd.DataFrame([{"Quando": prazos.fmt(prazos._dt(e["data_hora"])), "Evento": e["tipo"],
                                    "Resp. ALECE": e["responsavel_alece"],
                                    "Resp. contratada": e["responsavel_contratada"],
                                    "Obs.": e["observacao"], "Por": e["registrado_por"]} for e in a["eventos"]]),
                     hide_index=True, width="stretch")

    with t2:
        with st.form("evento", clear_on_submit=True):
            tipo = st.selectbox("Evento", prazos.EVENTOS[1:])
            quando = data_hora("Data do evento", "ev")
            c1, c2 = st.columns(2)
            r_alece = c1.text_input("Responsável ALECE (acompanhou)")
            r_contr = c2.text_input("Responsável da contratada")
            obs = st.text_area("Observação")
            arqs = st.file_uploader("Anexar evidências (fotos, relatório assinado, e-mail em PDF…)",
                                    accept_multiple_files=True)
            tipo_ev = st.selectbox("Tipo das evidências anexadas", TIPOS_EVID)
            ok = st.form_submit_button("Registrar", type="primary")
        if ok:
            ev_id = db.executar(
                """INSERT INTO evento (os_id, tipo, data_hora, responsavel_alece, responsavel_contratada,
                   observacao, registrado_por, registrado_em) VALUES (?,?,?,?,?,?,?,?)""",
                (o["id"], tipo, quando, r_alece, r_contr, obs, usuario, db.agora()),
                usuario, "Registrou evento", f"{o['numero']}: {tipo}")
            for f in arqs or []:
                salvar_evidencia(f, o, tipo_ev, f"{tipo} — {obs}", evento_id=ev_id)
            st.success("Evento registrado.")
            st.rerun()

    with t3:
        bens = db.consultar("SELECT id, tombo, tag, descricao, defeito, localizacao FROM os_bem WHERE os_id=?", (o["id"],))
        st.dataframe(pd.DataFrame(bens).drop(columns="id", errors="ignore"), hide_index=True, width="stretch")
        with st.form("add_bem", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            tb, tg, ds = c1.text_input("Tombo"), c2.text_input("TAG"), c3.text_input("Descrição")
            df_ = st.text_input("Defeito relatado")
            if st.form_submit_button("Adicionar bem"):
                db.executar("INSERT INTO os_bem (os_id, tombo, tag, descricao, defeito) VALUES (?,?,?,?,?)",
                            (o["id"], tb, tg, ds, df_), usuario, "Adicionou bem", f"{o['numero']}: {tb}")
                st.rerun()

    with t4:
        evs = db.consultar("SELECT * FROM evidencia WHERE os_id=? ORDER BY enviado_em DESC", (o["id"],))
        for x in evs:
            p = Path(x["arquivo"])
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{x['tipo']}** · {p.name}  \n{x['descricao'] or ''}  \n"
                        f"`sha256 {x['sha256'][:16]}…` · {x['enviado_em']} · {x['enviado_por']}")
            if p.exists():
                if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    c2.image(str(p), width=140)
                c2.download_button("Baixar", p.read_bytes(), p.name, key=f"dl{x['id']}")
            else:
                c2.error("Arquivo não encontrado")
        with st.form("avulsa", clear_on_submit=True):
            arqs = st.file_uploader("Anexar evidência avulsa", accept_multiple_files=True)
            tipo_ev = st.selectbox("Tipo", TIPOS_EVID)
            desc = st.text_input("Descrição")
            if st.form_submit_button("Anexar"):
                for f in arqs or []:
                    salvar_evidencia(f, o, tipo_ev, desc)
                st.rerun()

    with t5:
        c1, c2 = st.columns(2)
        with c1:
            with st.form("valor"):
                v = st.number_input("Valor atestado para medição (R$)", min_value=0.0,
                                    value=float(o["valor_atestado"] or 0), step=10.0)
                if st.form_submit_button("Salvar valor atestado"):
                    db.executar("UPDATE os SET valor_atestado=? WHERE id=?", (v, o["id"]),
                                usuario, "Atestou valor", f"{o['numero']}: {brl(v)}")
                    st.rerun()
            if st.button("Cancelar esta OS"):
                db.executar("UPDATE os SET cancelada=1 WHERE id=?", (o["id"],), usuario, "Cancelou OS", o["numero"])
                st.rerun()
        with c2:
            st.download_button("📄 Gerar dossiê da OS (.docx)", documentos.dossie_os(o["id"], usuario),
                               f"Dossie_{o['numero']}.docx", type="primary")

# ================================================================ OCORRÊNCIAS
elif pagina == "Ocorrências":
    st.markdown('<div class="faixa"><b>Ocorrências e notificações</b> (art. 117, §1º, Lei 14.133)</div>',
                unsafe_allow_html=True)
    oss = [{"id": None, "numero": "— não vinculada —"}] + db.consultar("SELECT id, numero FROM os ORDER BY id DESC")
    with st.expander("Registrar nova ocorrência", expanded=False):
        with st.form("oc", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            os_sel = c1.selectbox("OS", oss, format_func=lambda r: r["numero"])
            tipo = c2.selectbox("Tipo", TIPOS_OC)
            grav = c3.selectbox("Gravidade", GRAVIDADES)
            dt = st.date_input("Data da constatação", format="DD/MM/YYYY")
            desc = st.text_area("O que foi constatado (fatos, sem adjetivos)")
            prov = st.text_area("Providência exigida da contratada")
            prazo_s = st.date_input("Prazo para saneamento", value=None, format="DD/MM/YYYY")
            arqs = st.file_uploader("Evidências", accept_multiple_files=True)
            if st.form_submit_button("Registrar ocorrência", type="primary"):
                oc_id = db.executar(
                    """INSERT INTO ocorrencia (os_id, data, tipo, gravidade, descricao, providencia,
                       prazo_saneamento, status, registrado_por, registrado_em) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (os_sel["id"], dt.isoformat(), tipo, grav, desc, prov,
                     prazo_s.isoformat() if prazo_s else None, "Aberta", usuario, db.agora()),
                    usuario, "Registrou ocorrência", f"{tipo} / {os_sel['numero']}")
                o = db.um("SELECT * FROM os WHERE id=?", (os_sel["id"],)) if os_sel["id"] else None
                for f in arqs or []:
                    salvar_evidencia(f, o, "Foto", desc[:80], ocorrencia_id=oc_id)
                st.rerun()

    ocs = db.consultar("""SELECT oc.*, os.numero AS os_num FROM ocorrencia oc
                          LEFT JOIN os ON os.id=oc.os_id ORDER BY oc.data DESC""")
    for x in ocs:
        with st.container(border=True):
            c1, c2 = st.columns([4, 2])
            c1.markdown(f"**#{x['id']} · {x['tipo']}** ({x['gravidade']}) · OS {x['os_num'] or '—'} · {x['data']}  \n"
                        f"{x['descricao']}  \n*Providência:* {x['providencia'] or '—'} · *Prazo:* {x['prazo_saneamento'] or '—'}")
            novo = c2.selectbox("Status", STATUS_OC, index=STATUS_OC.index(x["status"]), key=f"st{x['id']}")
            if novo != x["status"]:
                db.executar("UPDATE ocorrencia SET status=? WHERE id=?", (novo, x["id"]),
                            usuario, "Alterou status de ocorrência", f"#{x['id']}: {x['status']} → {novo}")
                st.rerun()
            c2.download_button("Minuta de notificação", documentos.notificacao(x["id"], usuario),
                               f"Notificacao_{x['id']}.docx", key=f"nt{x['id']}")

# ================================================================ CONTRATO E PRAZOS
elif pagina == "Contrato e prazos":
    st.markdown('<div class="faixa"><b>Contrato e parametrização</b></div>', unsafe_allow_html=True)
    with st.form("contrato"):
        c1, c2, c3 = st.columns(3)
        numero = c1.text_input("Nº do contrato", c["numero"])
        ini = c2.text_input("Início da vigência (AAAA-MM-DD)", c["vigencia_inicio"])
        fim = c3.text_input("Fim da vigência (AAAA-MM-DD)", c["vigencia_fim"])
        c4, c5, c6 = st.columns(3)
        gestor = c4.text_input("Gestor", c["gestor"])
        fiscal = c5.text_input("Fiscal técnico", c["fiscal"])
        valor = c6.number_input("Valor global (R$)", value=float(c["valor_global"]))
        obs = st.text_area("Observações", c["obs"])
        if st.form_submit_button("Salvar contrato"):
            db.executar("""UPDATE contrato SET numero=?, vigencia_inicio=?, vigencia_fim=?, gestor=?, fiscal=?,
                           valor_global=?, obs=? WHERE id=1""",
                        (numero, ini, fim, gestor, fiscal, valor, obs), usuario, "Alterou contrato", numero)
            st.rerun()

    st.subheader("Prazos contratuais")
    st.caption("Ajuste quando o TR final for confirmado. Toda alteração fica na auditoria; OS já emitidas são recalculadas.")
    pz = pd.DataFrame(db.consultar("SELECT * FROM prazo"))
    ed = st.data_editor(pz, hide_index=True, disabled=["chave"], width="stretch",
                        column_config={"unidade": st.column_config.SelectboxColumn(
                            options=["horas", "dias_uteis", "dias_corridos"])})
    if st.button("Salvar prazos"):
        for _, r in ed.iterrows():
            db.executar("UPDATE prazo SET descricao=?, quantidade=?, unidade=?, base_legal=? WHERE chave=?",
                        (r["descricao"], r["quantidade"], r["unidade"], r["base_legal"], r["chave"]),
                        usuario, "Alterou prazo", f"{r['chave']}={r['quantidade']} {r['unidade']}")
        st.success("Prazos salvos.")

    st.subheader("Feriados e pontos facultativos")
    fe = st.data_editor(pd.DataFrame(db.consultar("SELECT * FROM feriado ORDER BY data")),
                        num_rows="dynamic", hide_index=True, width="stretch")
    if st.button("Salvar feriados"):
        with db.conexao() as con:
            con.execute("DELETE FROM feriado")
            con.executemany("INSERT OR REPLACE INTO feriado VALUES (?,?)",
                            [(r["data"], r["descricao"]) for _, r in fe.iterrows() if r["data"]])
        db.executar("SELECT 1", (), usuario, "Alterou feriados", f"{len(fe)} datas")
        st.success("Feriados salvos.")

    st.subheader("Itens contratados")
    st.dataframe(pd.DataFrame(db.consultar("SELECT codigo, descricao, catser, valor FROM contrato_item")),
                 hide_index=True)
    st.caption(f"Banco de dados: `{db.DB_PATH}` · Evidências: `{db.EVID}`")

# ================================================================ AUDITORIA
elif pagina == "Auditoria":
    st.markdown('<div class="faixa"><b>Trilha de auditoria</b> — somente leitura</div>', unsafe_allow_html=True)
    log = pd.DataFrame(db.consultar("SELECT quando, usuario, acao, detalhe FROM auditoria ORDER BY id DESC"))
    st.dataframe(log, hide_index=True, width="stretch")
    if not log.empty:
        st.download_button("Exportar CSV", log.to_csv(index=False).encode("utf-8-sig"), "auditoria.csv")
