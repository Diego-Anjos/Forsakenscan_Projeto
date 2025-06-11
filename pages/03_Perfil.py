# ========================================
# 03_Perfil.py – Área do usuário
# ========================================
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from uuid import uuid4
import secrets, string, re

from db import get_conn, get_cursor       # <- NOVO
conn   = get_conn()  
                 # <- NOVO
cursor = get_cursor(dictionary=True, buffered=True)     # <- NOVO

from fraude import avaliar_transacao


# ------------------------------------------------------------------
# Listas fixas
# ------------------------------------------------------------------
BANCOS_OPTS = [
    "Itaú","Bradesco","Nubank","Inter","Santander",
    "Banco do Brasil","Caixa","C6 Bank","BTG Pactual",
    "Banco Original","Next","Neon","PagBank","Banco Pan",
    "Banco BMG","Sicredi","Sicoob","Banrisul","BRB",
    "Banco Safra","Banco Daycoval","BV (Votorantim)"
]
EST_CIVIL_OPTS = ["Solteiro(a)","Casado(a)","Divorciado(a)","Viúvo(a)","União estável"]
SIT_PROF_OPTS  = ["Empregado","Desempregado","Autônomo","Estudante","Aposentado"]
FORMAS_PG      = ("Pix","Transferência","Cartão",
                  "Boleto pagamento","Boleto depósito")
LOJAS          = ["Amazon","Mercado Livre","Magalu","Shein",
                  "Kabum","Netshoes","Steam","Outro"]
CATEGORIAS     = ["Eletrônicos","Vestuário","Casa","Alimentos",
                  "Beleza","Games","Outros"]

# ------------------------------------------------------------------
# Funções auxiliares
# ------------------------------------------------------------------
fmt_moeda = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X",".")

def barcode44() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(44))

def prox_uteis(n=3):
    d = datetime.now().date(); add = 0
    while add < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            add += 1
    return d

def validar_cpf(cpf: str) -> bool:
    """Validação básica de CPF (apenas formato)"""
    cpf = re.sub(r'[^0-9]', '', cpf)
    return len(cpf) == 11

def registrar_fato(acao, desc, campo=None, valor_antigo=None, valor_novo=None):
    try:
        if campo:
            cursor.execute(
                """INSERT INTO fatos_usuarios 
                   (user_id, acao, descricao, campo, valor_antigo, valor_novo) 
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (user_id, acao, desc, campo, valor_antigo, valor_novo))
        else:
            cursor.execute(
                "INSERT INTO fatos_usuarios (user_id, acao, descricao) VALUES (%s, %s, %s)",
                (user_id, acao, desc))
        conn.commit()
    except Exception as e:
        st.error(f"Erro ao registrar ação: {str(e)}")

# ------------------------------------------------------------------
# Autenticação
# ------------------------------------------------------------------
if not st.session_state.get("logged_in"):
    st.warning("⚠️ Faça login.")
    st.stop()

if st.session_state.get("is_admin"):
    st.info("Área de perfil indisponível para contas **administrador**. "
            "Use o menu **Mestre** para monitorar o sistema.")
    st.stop()

user_id   = st.session_state.user_id
username  = st.session_state.username
email     = st.session_state.email

# ------------------------------------------------------------------
# Carrega transações do cliente
# ------------------------------------------------------------------
try:
    cursor.execute("""
    SELECT tipo_transacao   AS tipo,
           valor,
           data_hora,
           codigo,
           banco_origem,
           banco_destino,
           forma_pagamento,
           suspeita,
           motivo_suspeita
      FROM transacoes
     WHERE user_id = %s
     ORDER BY data_hora DESC
    """, (user_id,))

    df = pd.DataFrame(cursor.fetchall()) if cursor.rowcount else pd.DataFrame(
        columns=[
          "tipo","valor","data_hora","codigo",
          "banco_origem","banco_destino","forma_pagamento",
          "suspeita","motivo_suspeita"
        ]
    )
    if not df.empty:
        df["data_hora"] = pd.to_datetime(df["data_hora"])

    tot_tx  = len(df)
    tot_out = df[df["tipo"].isin(["Compra","Pagamento","Transferência"])]["valor"].sum()
    tot_in  = df[df["tipo"].isin(["Recebimento","Cash-In"])]["valor"].sum()
    saldo   = tot_in - tot_out
except Exception as e:
    st.error(f"Erro ao carregar transações: {str(e)}")
    st.stop()

# ------------------------------------------------------------------
# Layout
# ------------------------------------------------------------------
st.set_page_config(page_title="Meu Perfil", layout="wide")
st.markdown("""
<style>
body{background:linear-gradient(to right,#0f2027,#203a43,#2c5364)}
.card{background:#0d1117;border-radius:18px;padding:26px;text-align:center;
      box-shadow:0 0 10px #00000040}
.card h6{margin:0;font-size:1rem;color:#9ca3af;font-weight:400}
.card h3{margin:0;font-size:2.2rem}
</style>""", unsafe_allow_html=True)

st.markdown("<h1 style='display:flex;gap:8px;align-items:center'>👤 Meu Perfil</h1>",
            unsafe_allow_html=True)
st.markdown(f"**Usuário:** `{username}` | **Email:** `{email}`")

cor_saldo = "#2ecc71" if saldo >= 0 else "#e74c3c"
c1,c2,c3,c4 = st.columns(4, gap="large")
c1.markdown(f"<div class='card'><h6>Total de Transações</h6><h3>{tot_tx}</h3></div>",
            unsafe_allow_html=True)
c2.markdown(f"<div class='card'><h6>Total Gasto</h6>"
            f"<h3 style='color:#e74c3c'>{fmt_moeda(tot_out)}</h3></div>",
            unsafe_allow_html=True)
c3.markdown(f"<div class='card'><h6>Total Recebido</h6>"
            f"<h3 style='color:#2ecc71'>{fmt_moeda(tot_in)}</h3></div>",
            unsafe_allow_html=True)
c4.markdown(f"<div class='card'><h6>Saldo Disponível</h6>"
            f"<h3 style='color:{cor_saldo}'>{fmt_moeda(saldo)}</h3></div>",
            unsafe_allow_html=True)

# ------------------------------------------------------------------
# Tabs
# ------------------------------------------------------------------
tab_transf, tab_shop, tab_extrato, tab_loan = st.tabs(
    ("💸 Pagamentos / Boletos", "🛒 Compras Online",
     "📊 Extrato Detalhado",    "💳 Ofertas de Empréstimo")
)


# ---------- TAB 1 (Pagamentos/Boleto) -----------------------------
with tab_transf:
    cur = conn.cursor(dictionary=True)
    st.markdown("### Realizar Pagamento/Transferência")
    
    c_forma,c_cpf,c_val,c_pwd,c_btn = st.columns([2,2,1,1,1])
    with c_forma:
        forma = st.selectbox("Forma", FORMAS_PG, key="pg_forma")
    with c_cpf:
        cpf_dest = st.text_input("CPF destinatário (opcional)", key="pg_cpf", 
                                help="Somente números, sem pontos ou traços")
    with c_val:
        valor = st.number_input("Valor (R$)", min_value=0.01, step=10.0,
                                format="%.2f", key="pg_val")
    with c_pwd:
        pwd = st.text_input("Senha", type="password", key="pg_pwd")
    with c_btn:
        if st.button("Enviar/Emitir", key="btn_pg", 
                    help="Confirme os dados antes de enviar"):
            if valor <= 0:
                st.warning("Informe valor > 0."); st.stop()
                
            # Validação de CPF
            if cpf_dest.strip() and not validar_cpf(cpf_dest):
                st.error("CPF inválido. Digite apenas os 11 números."); st.stop()
                
            cursor.execute("SELECT senha FROM usuarios WHERE id=%s",(user_id,))
            if pwd != cursor.fetchone()["senha"]:
                st.error("Senha incorreta."); st.stop()
                
            tx = {"user_id": user_id, "valor": valor, "data_hora": datetime.now()}
            suspeita, motivo = avaliar_transacao(tx)

            # Boleto depósito
            if forma == "Boleto depósito":
                codigo = barcode44(); venc = prox_uteis(3)
                try:
                    cursor.execute("""
                    INSERT INTO transacoes
                        (user_id,valor,tipo_transacao,forma_pagamento,codigo,data_hora,
                        localizacao,banco_origem,banco_destino,suspeita,motivo_suspeita)
                    VALUES
                        (%s,%s,'Cash-In','Boleto',%s,NOW(),'On-line',
                        'Boleto','Conta Corrente',%s,%s)
                    """, (user_id, valor, codigo, suspeita, motivo))
                    conn.commit()
                    registrar_fato("Cash-In", f"Boleto {fmt_moeda(valor)} gerado")
                    
                    # Mostrar comprovante
                    st.success("Boleto gerado com sucesso!")
                    st.markdown(f"""
                    **Comprovante de Boleto**  
                    **Código:** `{codigo}`  
                    **Valor:** {fmt_moeda(valor)}  
                    **Vencimento:** {venc.strftime('%d/%m/%Y')}  
                    **Status:** Gerado
                    """)
                    st.stop()
                except Exception as e:
                    st.error(f"Erro ao gerar boleto: {str(e)}")
                    st.stop()

            # Transferências normais
            if forma in ("Pix","Transferência") and not cpf_dest.strip():
                st.warning("Informe CPF destinatário."); st.stop()
            if saldo < valor and forma != "Cartão":
                st.error("Saldo insuficiente."); st.stop()

            dest = None
            if cpf_dest.strip():
                try:
                    cursor.execute("SELECT id,banco FROM usuarios WHERE cpf=%s",
                                   (cpf_dest.strip(),))
                    dest = cursor.fetchone()
                    if forma in ("Pix","Transferência") and not dest:
                        st.error("CPF não encontrado."); st.stop()
                except Exception as e:
                    st.error(f"Erro ao verificar destinatário: {str(e)}")
                    st.stop()

            cod = uuid4().hex[:10]
            banco_rem = "Conta Corrente"

            try:
                cursor.execute("""
                INSERT INTO transacoes
                    (user_id,valor,tipo_transacao,forma_pagamento,codigo,data_hora,
                    localizacao,banco_origem,banco_destino,suspeita,motivo_suspeita)
                VALUES
                    (%s,%s,%s,%s,%s,NOW(),'On-line',%s,%s,%s,%s)
                """,(
                    user_id, valor,
                    "Transferência" if dest else "Pagamento",
                    forma, cod,
                    banco_rem,
                    dest["banco"] if dest else "Estabelecimento",
                    suspeita, motivo
                ))

                if dest:
                    cursor.execute("""
                    INSERT INTO transacoes
                    (user_id,valor,tipo_transacao,forma_pagamento,codigo,data_hora,
                    localizacao,banco_origem,banco_destino,suspeita,motivo_suspeita)
                    VALUES
                    (%s,%s,'Recebimento',%s,%s,NOW(),'On-line',%s,%s,%s,%s)
                    """,(
                        dest["id"], valor,
                        forma, cod,
                        banco_rem, dest["banco"],
                        suspeita, motivo
                    ))
                
                conn.commit()
                registrar_fato("Pagamento", f"{forma} {fmt_moeda(valor)}")
                
                # Mostrar comprovante
                st.success("Transação realizada com sucesso!")
                st.markdown(f"""
                **Comprovante de Transação**  
                **Código:** `{cod}`  
                **Tipo:** {forma}  
                **Valor:** {fmt_moeda(valor)}  
                **Data/Hora:** {datetime.now().strftime('%d/%m/%Y %H:%M')}  
                **Status:** Concluído
                """)
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao registrar transação: {str(e)}")
                conn.rollback()
                st.stop()

# ---------- TAB 2 (Compras Online) --------------------------------
with tab_shop:
    cur = conn.cursor(dictionary=True)
    st.markdown("### Nova compra")
    s_loja, s_cat = st.columns(2)
    with s_loja:
        loja_sel = st.selectbox("Loja", LOJAS, key="loja")
        loja = st.text_input("Nome da loja", key="loja_out") if loja_sel=="Outro" else loja_sel
    with s_cat:
        categoria = st.selectbox("Categoria", CATEGORIAS, key="cat")

    prod = st.text_input("Produto / Descrição", key="produto")
    q_col, q_val = st.columns(2)
    with q_col:
        qtd = st.number_input("Qtd", min_value=1, step=1, key="qtd")
    with q_val:
        v_unit = st.number_input("Valor unitário (R$)", min_value=0.01,
                                 step=10.0, format="%.2f", key="vunit")

    total = qtd * v_unit
    st.markdown(f"**Total:** {fmt_moeda(total)}")

    pwd_shop = st.text_input("Senha", type="password", key="pwd_shop")
    if st.button("Comprar", key="btn_shop"):
        if not prod.strip():
            st.warning("Descreva o produto."); st.stop()
        if total <= 0:
            st.warning("Valor inválido."); st.stop()
            
        try:
            cursor.execute("SELECT senha FROM usuarios WHERE id=%s",(user_id,))
            if pwd_shop != cursor.fetchone()["senha"]:
                st.error("Senha incorreta."); st.stop()
            if saldo < total:
                st.error("Saldo insuficiente."); st.stop()

            codigo = uuid4().hex[:10]
            cursor.execute("""
            INSERT INTO transacoes
              (user_id,valor,tipo_transacao,forma_pagamento,codigo,data_hora,
               localizacao,banco_origem,banco_destino,suspeita)
            VALUES
              (%s,%s,'Compra','Online',%s,NOW(),'On-line',
               'Conta Corrente',%s,0)
            """, (user_id, total, codigo, loja))
            cursor.execute("""
            INSERT INTO compras_online
              (user_id,codigo_tx,loja,categoria,produto,qtd,valor_unit,
               valor_total,data_hora)
            VALUES
              (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """, (user_id, codigo, loja, categoria, prod,
                  qtd, v_unit, total))
            conn.commit()
            registrar_fato("Compra online", f"{loja} {fmt_moeda(total)}")
            
            # Mostrar comprovante
            st.success("Compra realizada com sucesso!")
            st.markdown(f"""
            **Comprovante de Compra**  
            **Loja:** {loja}  
            **Produto:** {prod}  
            **Quantidade:** {qtd}  
            **Valor Unitário:** {fmt_moeda(v_unit)}  
            **Total:** {fmt_moeda(total)}  
            **Código:** `{codigo}`  
            **Data/Hora:** {datetime.now().strftime('%d/%m/%Y %H:%M')}
            """)
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao registrar compra: {str(e)}")
            conn.rollback()
            st.stop()

# ---------- TAB 3 (Extrato Detalhado) -----------------------------
with tab_extrato:
    cur = conn.cursor(dictionary=True)
    st.markdown("### Filtros do Extrato")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        data_inicio = st.date_input("Data inicial", 
                                  value=datetime.now().date() - timedelta(days=30))
    with col2:
        data_fim = st.date_input("Data final", 
                               value=datetime.now().date())
    with col3:
        tipo_transacao = st.multiselect("Tipo de transação", 
                                      ["Todos", "Compra", "Pagamento", "Transferência", 
                                       "Recebimento", "Cash-In", "Boleto"])
    
    if st.button("Aplicar Filtros"):
        try:
            query = """
            SELECT tipo_transacao AS tipo, valor, data_hora, codigo,
                   banco_origem, banco_destino, forma_pagamento,
                   suspeita, motivo_suspeita
            FROM transacoes
            WHERE user_id = %s
            AND DATE(data_hora) BETWEEN %s AND %s
            """
            params = [user_id, data_inicio, data_fim]
            
            if "Todos" not in tipo_transacao and tipo_transacao:
                query += " AND tipo_transacao IN (%s)" % ",".join(["%s"]*len(tipo_transacao))
                params.extend(tipo_transacao)
            
            query += " ORDER BY data_hora DESC"
            
            cursor.execute(query, tuple(params))
            df_filtrado = pd.DataFrame(cursor.fetchall())
            
            if not df_filtrado.empty:
                df_filtrado["data_hora"] = pd.to_datetime(df_filtrado["data_hora"])
                st.markdown(f"**Total de transações:** {len(df_filtrado)}")
                
                for _, r in df_filtrado.iterrows():
                    cor = "#2ecc71" if r.tipo in ("Recebimento","Cash-In") else \
                          "#e67e22" if r.tipo=="Transferência" else "#e74c3c"
                    st.markdown(f"""
                    <div style='background:#0d1117;padding:10px 14px;border-radius:10px;margin-bottom:10px;'>
                    <b>{r.tipo}</b> | <span style='color:{cor}'>{fmt_moeda(r.valor)}</span> | {r.data_hora.strftime('%d/%m/%Y %H:%M')}<br>
                    <small>Código: <code>{r.codigo or '—'}</code> | Forma: {r.forma_pagamento or '—'} |
                    {r.banco_origem or '—'} ▶ {r.banco_destino or '—'}</small>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("Nenhuma transação encontrada com os filtros aplicados.")
        except Exception as e:
            st.error(f"Erro ao filtrar transações: {str(e)}")

# ---------- TAB 4 (Ofertas de Empréstimo) --------------------------
# ----------- TAB 4 (Ofertas de Empréstimo) -------------------------------
# ---------- TAB 4 (Ofertas de Empréstimo) ---------------------------
# ---------- TAB 4 (Ofertas de Empréstimo) ---------------------------
# ---------- TAB 4 (Ofertas de Empréstimo) ---------------------------
# ---------- TAB 4 (Ofertas de Empréstimo) ---------------------------
with tab_loan:
    cur = conn.cursor(dictionary=True)
    import random
    from datetime import datetime
    st.markdown("### 💳 Ofertas Personalizadas de Empréstimo")

    # 1. Verifica todas as ofertas do usuário
    cursor.execute("""
        SELECT * FROM emprestimos
        WHERE user_id = %s
        ORDER BY criado_em DESC
    """, (user_id,))
    todas_ofertas = cursor.fetchall()
    
    # 2. Separa ofertas ativas (status 'oferta') e histórico
    oferta_ativa = next((o for o in todas_ofertas if o['status'] == 'oferta'), None)
    historico_ofertas = [o for o in todas_ofertas if o['status'] != 'oferta']
    
    # 3. Se não tem oferta ativa, verifica se precisa gerar nova
    if not oferta_ativa:
        dias_ref = 30
        cursor.execute("""
            SELECT
                SUM(CASE WHEN tipo_transacao IN ('Recebimento','Cash-In') THEN valor ELSE 0 END) AS entradas,
                SUM(CASE WHEN tipo_transacao IN ('Compra','Pagamento','Transferência','Saque') THEN valor ELSE 0 END) AS saidas
            FROM transacoes
            WHERE user_id = %s AND DATE(data_hora) >= CURDATE() - INTERVAL %s DAY
        """, (user_id, dias_ref))
        res = cursor.fetchone() or {}
        entradas = float(res.get("entradas") or 0)
        saidas = float(res.get("saidas") or 0)
        precisa_limite = saidas > entradas * 1.2

        if precisa_limite:
            # Gera nova oferta apenas se não houver ofertas recentes recusadas
            ultima_recusa = next((o for o in historico_ofertas if o['status'] == 'recusado'), None)
            if not ultima_recusa or (datetime.now() - ultima_recusa['criado_em']).days > 7:
                valor_oferta = random.randint(1000, 20000) / 100 * 100
                taxa = random.choice([1.69, 1.79, 1.89, 1.99])
                prazo = random.choice([12, 24, 36])
                cursor.execute("""
                    INSERT INTO emprestimos (user_id, valor, taxa_juros, prazo_meses, status)
                    VALUES (%s, %s, %s, %s, 'oferta')
                """, (user_id, valor_oferta, taxa, prazo))
                conn.commit()
                cursor.execute("SELECT * FROM emprestimos WHERE id=LAST_INSERT_ID()")
                oferta_ativa = cursor.fetchone()

    # 4. Exibição da oferta ativa (se houver)
    if oferta_ativa:
        parc = oferta_ativa["valor"] * oferta_ativa["taxa_juros"]/100 / (1 - (1 + oferta_ativa["taxa_juros"]/100)**(-oferta_ativa["prazo_meses"]))
        st.success("🎯 Temos uma oferta especial para você!")
        st.markdown(f"""
        **Valor:** {fmt_moeda(oferta_ativa['valor'])}  
        **Taxa:** {oferta_ativa['taxa_juros']}% a.m  
        **Prazo:** {oferta_ativa['prazo_meses']} meses  
        **Parcela estimada:** **{fmt_moeda(parc)}**
        """)

        col_aceita, col_recusa = st.columns(2)
        with col_aceita:
            if st.button("✅ Aceitar Oferta", key="btn_emprestimo_ok"):
                try:
                    cursor.execute("UPDATE emprestimos SET status='aceito' WHERE id=%s", (oferta_ativa['id'],))
                    cod = uuid4().hex[:10]
                    cursor.execute("""
                        INSERT INTO transacoes
                        (user_id, valor, tipo_transacao, forma_pagamento, codigo, data_hora,
                         localizacao, banco_origem, banco_destino, suspeita, motivo_suspeita)
                        VALUES (%s, %s, 'Cash-In', 'Crédito', %s, NOW(),
                                'Sistema', 'Banco', 'Conta Corrente', 0, NULL)
                    """, (user_id, oferta_ativa["valor"], cod))
                    conn.commit()
                    registrar_fato("Empréstimo", f"Oferta aceita e crédito de {fmt_moeda(oferta_ativa['valor'])}")
                    st.success("Oferta aceita e valor creditado na conta!")
                    st.rerun()
                except Exception as e:
                    conn.rollback()
                    st.error(f"Erro ao processar empréstimo: {str(e)}")

        with col_recusa:
            if st.button("❌ Recusar Oferta", key="btn_emprestimo_no"):
                cursor.execute("UPDATE emprestimos SET status='recusado' WHERE id=%s", (oferta_ativa['id'],))
                conn.commit()
                registrar_fato("Empréstimo", "Oferta recusada")
                st.info("Oferta recusada. Você poderá receber novas propostas futuramente.")
                st.rerun()
    else:
        st.warning("🚫 Nenhuma oferta disponível no momento.")
        st.info("Continue movimentando sua conta para aumentar seu limite e receber novas propostas de crédito futuramente!")

    # 5. Mostrar histórico de ofertas (se houver)
    if historico_ofertas:
        st.markdown("---")
        st.markdown("### Histórico de Ofertas")
        for oferta in historico_ofertas:
            status_cor = "#2ecc71" if oferta['status'] == 'aceito' else "#e74c3c" if oferta['status'] == 'recusado' else "#f39c12"
            st.markdown(f"""
            <div style='background:#0d1117;padding:10px 14px;border-radius:10px;margin-bottom:10px;'>
            <b>Oferta de {fmt_moeda(oferta['valor'])}</b> | 
            <span style='color:{status_cor}'>{oferta['status'].capitalize()}</span> | 
            {oferta['criado_em'].strftime('%d/%m/%Y %H:%M')}<br>
            <small>Taxa: {oferta['taxa_juros']}% a.m | Prazo: {oferta['prazo_meses']} meses</small>
            </div>
            """, unsafe_allow_html=True)


# ------------------------------------------------------------------
# Histórico
# ------------------------------------------------------------------
st.markdown("<hr style='margin-top:28px;border:1px solid #ffffff22'>",
            unsafe_allow_html=True)
st.markdown("## 🗒️ Últimas Transações")

if df.empty:
    st.info("Nenhuma transação.")
else:
    for _, r in df.head(15).iterrows():
        cor = "#2ecc71" if r.tipo in ("Recebimento","Cash-In") else \
              "#e67e22" if r.tipo=="Transferência" else "#e74c3c"
        st.markdown(f"""
<div style='background:#0d1117;padding:10px 14px;border-radius:10px;margin-bottom:10px;'>
<b>{r.tipo}</b> | <span style='color:{cor}'>{fmt_moeda(r.valor)}</span> | {r.data_hora.strftime('%d/%m/%Y %H:%M')}<br>
<small>Código: <code>{r.codigo or '—'}</code> | Forma: {r.forma_pagamento or '—'} |
{r.banco_origem or '—'} ▶ {r.banco_destino or '—'}</small>
</div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# Configurações – Editar Dados / Alterar Senha
# ------------------------------------------------------------------
st.markdown("## ⚙️ Configurações da Conta")
tab_edit, tab_pwd = st.tabs(("✏️ Editar Dados", "🔑 Alterar Senha"))

# ---------- EDITAR DADOS ------------------------------------------
with tab_edit: 
    cur = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
        SELECT nome,email,banco,cpf,rg,data_nascimento,endereco,
               cidade,estado,telefone,renda,profissao,
               estado_civil,situacao_prof
          FROM usuarios
         WHERE id=%s
        """, (user_id,))
        dados_atuais = cursor.fetchone()

        c1,c2 = st.columns(2, gap="large")
        with c1:
            nome_n  = st.text_input("Nome completo", value=dados_atuais["nome"])
            cpf_n   = st.text_input("CPF", value=dados_atuais["cpf"], disabled=True)
            rg_n    = st.text_input("RG",  value=dados_atuais["rg"],  disabled=True)
            nasc_n  = st.date_input("Data nasc.", value=dados_atuais["data_nascimento"])
            tel_n   = st.text_input("Telefone", value=dados_atuais["telefone"])
            renda_n = st.number_input("Renda (R$)", value=float(dados_atuais["renda"] or 0),
                                      step=100.0, format="%.2f")
            est_civ = st.selectbox("Estado civil", EST_CIVIL_OPTS,
                                   index=EST_CIVIL_OPTS.index(dados_atuais["estado_civil"]))
        with c2:
            email_n = st.text_input("Email", value=dados_atuais["email"])

            bancos = BANCOS_OPTS.copy()
            if dados_atuais["banco"] not in bancos:
                bancos.insert(0, dados_atuais["banco"])
            banco_n = st.selectbox("Banco", bancos,
                                   index=bancos.index(dados_atuais["banco"]))

            end_n    = st.text_input("Endereço", value=dados_atuais["endereco"])
            cidade_n = st.text_input("Cidade", value=dados_atuais["cidade"])
            uf_n     = st.text_input("UF", value=dados_atuais["estado"], max_chars=2)
            prof_n   = st.text_input("Profissão", value=dados_atuais["profissao"])
            sit_prof = st.selectbox("Situação prof.", SIT_PROF_OPTS,
                                    index=SIT_PROF_OPTS.index(dados_atuais["situacao_prof"]))

        if st.button("Salvar alterações"):
            if not validar_cpf(cpf_n):
                st.error("CPF inválido. Digite apenas os 11 números."); st.stop()
                
            try:
                # Primeiro atualiza os dados
                cursor.execute("""
                UPDATE usuarios SET
                  nome=%s,email=%s,banco=%s,cpf=%s,rg=%s,data_nascimento=%s,
                  endereco=%s,cidade=%s,estado=%s,telefone=%s,renda=%s,
                  profissao=%s,estado_civil=%s,situacao_prof=%s
                WHERE id=%s
                """, (
                    nome_n,email_n,banco_n,cpf_n,rg_n,nasc_n,
                    end_n,cidade_n,uf_n,tel_n,renda_n,
                    prof_n,est_civ,sit_prof,user_id))
                
                # Registra cada campo alterado
                campos_alterados = []
                
                if nome_n != dados_atuais['nome']:
                    registrar_fato("editar_perfil", "Alteração de nome", "nome", dados_atuais['nome'], nome_n)
                    campos_alterados.append("nome")
                
                if email_n != dados_atuais['email']:
                    registrar_fato("editar_perfil", "Alteração de email", "email", dados_atuais['email'], email_n)
                    campos_alterados.append("email")
                    
                if banco_n != dados_atuais['banco']:
                    registrar_fato("editar_perfil", "Alteração de banco", "banco", dados_atuais['banco'], banco_n)
                    campos_alterados.append("banco")
                    
                if cpf_n != dados_atuais['cpf']:
                    registrar_fato("editar_perfil", "Alteração de CPF", "cpf", dados_atuais['cpf'], cpf_n)
                    campos_alterados.append("cpf")
                    
                if rg_n != dados_atuais['rg']:
                    registrar_fato("editar_perfil", "Alteração de RG", "rg", dados_atuais['rg'], rg_n)
                    campos_alterados.append("rg")
                    
                if nasc_n != dados_atuais['data_nascimento']:
                    registrar_fato("editar_perfil", "Alteração de data de nascimento", "data_nascimento", 
                                  str(dados_atuais['data_nascimento']), str(nasc_n))
                    campos_alterados.append("data_nascimento")
                    
                if end_n != dados_atuais['endereco']:
                    registrar_fato("editar_perfil", "Alteração de endereço", "endereco", dados_atuais['endereco'], end_n)
                    campos_alterados.append("endereco")
                    
                if cidade_n != dados_atuais['cidade']:
                    registrar_fato("editar_perfil", "Alteração de cidade", "cidade", dados_atuais['cidade'], cidade_n)
                    campos_alterados.append("cidade")
                    
                if uf_n != dados_atuais['estado']:
                    registrar_fato("editar_perfil", "Alteração de estado", "estado", dados_atuais['estado'], uf_n)
                    campos_alterados.append("estado")
                    
                if tel_n != dados_atuais['telefone']:
                    registrar_fato("editar_perfil", "Alteração de telefone", "telefone", dados_atuais['telefone'], tel_n)
                    campos_alterados.append("telefone")
                    
                if float(renda_n) != float(dados_atuais['renda'] or 0):
                    registrar_fato("editar_perfil", "Alteração de renda", "renda", str(dados_atuais['renda']), str(renda_n))
                    campos_alterados.append("renda")
                    
                if prof_n != dados_atuais['profissao']:
                    registrar_fato("editar_perfil", "Alteração de profissão", "profissao", dados_atuais['profissao'], prof_n)
                    campos_alterados.append("profissao")
                    
                if est_civ != dados_atuais['estado_civil']:
                    registrar_fato("editar_perfil", "Alteração de estado civil", "estado_civil", 
                                  dados_atuais['estado_civil'], est_civ)
                    campos_alterados.append("estado_civil")
                    
                if sit_prof != dados_atuais['situacao_prof']:
                    registrar_fato("editar_perfil", "Alteração de situação profissional", "situacao_prof", 
                                  dados_atuais['situacao_prof'], sit_prof)
                    campos_alterados.append("situacao_prof")
                
                conn.commit()
                
                if campos_alterados:
                    registrar_fato("Update perfil", f"Dados pessoais alterados: {', '.join(campos_alterados)}")
                st.success("Dados atualizados com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao atualizar dados: {str(e)}")
                conn.rollback()
    except Exception as e:
        st.error(f"Erro ao carregar dados do usuário: {str(e)}")

# ---------- ALTERAR SENHA -----------------------------------------
with tab_pwd:
    cur = conn.cursor(dictionary=True)
    pwd_old = st.text_input("Senha atual", type="password")
    pwd_new = st.text_input("Nova senha",  type="password")
    pwd_cnf = st.text_input("Confirmar nova senha", type="password")

    if st.button("Alterar senha"):
        try:
            cursor.execute("SELECT senha FROM usuarios WHERE id=%s",(user_id,))
            if pwd_old != cursor.fetchone()["senha"]:
                st.error("Senha atual incorreta.")
            elif pwd_new != pwd_cnf:
                st.warning("As senhas não coincidem.")
            elif len(pwd_new) < 6:
                st.warning("Use ao menos 6 caracteres.")
            else:
                cursor.execute("UPDATE usuarios SET senha=%s WHERE id=%s",
                               (pwd_new,user_id))
                conn.commit()
                registrar_fato("Alterar senha","Senha atualizada")
                st.success("Senha alterada com sucesso!")
                st.session_state.logged_in = False  # Força novo login
                st.rerun()
        except Exception as e:
            st.error(f"Erro ao alterar senha: {str(e)}")
            conn.rollback()