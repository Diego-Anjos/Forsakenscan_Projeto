# ========================================
# DASHBOARD – Visão Geral de Transações & Segurança
# ========================================
import os
from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
if not hasattr(st, "rerun"):
    st.rerun = st.experimental_rerun  # alias p/ versões antigas



from db import get_conn, get_cursor

# ────────────────────────────────────────
# Config
# ────────────────────────────────────────
st.set_page_config(page_title="Dashboard – Visão Geral", layout="wide")
conn = get_conn()

# ────────────────────────────────────────
# Autorização mínima – admin
# ────────────────────────────────────────
sess = st.session_state
if "logged_in" not in sess or not sess.logged_in or not sess.is_admin:  # type: ignore[attr-defined]
    st.warning("⚠️ Apenas administradores podem visualizar o dashboard.")
    st.stop()

# ════════════════════════════════════════
# Dados principais (transações)
# ════════════════════════════════════════
SQL_TX = """
SELECT t.id, t.user_id, t.valor, t.tipo_transacao, t.forma_pagamento,
       t.data_hora, t.suspeita, u.banco, u.cpf
  FROM transacoes t
  JOIN usuarios  u ON u.id = t.user_id
"""

with st.spinner("Carregando dados …"):
    df_tx = pd.read_sql(SQL_TX, conn, parse_dates=["data_hora"])

# KPIs
c1, c2, c3 = st.columns(3)
c1.metric("Total de transações", f"{len(df_tx):,}")
c2.metric("Volume financeiro", f"R$ {df_tx['valor'].sum():,.2f}")
c3.metric("Marcadas suspeitas", f"{df_tx['suspeita'].sum():,}")

st.divider()

# ────────────────────────────────────────
# GRÁFICO 1 – valor por tipo
# ────────────────────────────────────────
fig_tipo = px.bar(
    df_tx.groupby("tipo_transacao")["valor"].sum().reset_index(),
    x="tipo_transacao",
    y="valor",
    title="Soma de valores por tipo de transação",
    labels={"valor": "Valor (R$)", "tipo_transacao": "Tipo"},
)
st.plotly_chart(fig_tipo, use_container_width=True)

# ────────────────────────────────────────
# GRÁFICO 2 – distribuição por banco
# ────────────────────────────────────────
fig_banco = px.pie(df_tx, names="banco", values="valor", title="Valores por banco")
st.plotly_chart(fig_banco, use_container_width=True)

# ════════════════════════════════════════
# GRÁFICO 3 – explosão de transações por minuto
# ════════════════════════════════════════
with st.expander("⚡ Explosão de transações por minuto", expanded=True):
    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    with col_f1:
        dt_ini = st.date_input("De", value=pd.Timestamp.now().date() - pd.Timedelta(days=1))
    with col_f2:
        dt_fim = st.date_input("Até", value=pd.Timestamp.now().date())
    with col_f3:
        thr_cpf = st.number_input("Mínimo p/ destacar CPF", 2, 40, value=3, step=1)

    if st.button("Gerar gráficos ⚡", key="btn_explosao"):
        p_ini, p_fim = dt_ini.strftime("%Y-%m-%d"), dt_fim.strftime("%Y-%m-%d")

        sql_tot = """
            SELECT DATE_FORMAT(data_hora,'%Y-%m-%d %H:%i:00') AS minuto,
                   COUNT(*) AS total
              FROM transacoes
             WHERE DATE(data_hora) BETWEEN %s AND %s
          GROUP BY minuto
          ORDER BY minuto
        """
        df_tot = pd.read_sql(sql_tot, conn, params=(p_ini, p_fim))
        df_tot["minuto"] = pd.to_datetime(df_tot["minuto"])
        df_tot = df_tot.dropna(subset=["minuto"])

        if df_tot.empty:
            st.info("Sem transações no intervalo selecionado.")
        else:
            fig_tot = go.Figure(
                go.Scatter(x=df_tot["minuto"], y=df_tot["total"], mode="lines+markers", fill="tozeroy")
            )
            fig_tot.update_layout(title="Volume total de transações por minuto", xaxis_title="Timestamp", yaxis_title="Qtd", hovermode="x unified")
            st.plotly_chart(fig_tot, use_container_width=True)

        # Scatter CPF
        sql_cpf = """
            SELECT DATE_FORMAT(t.data_hora,'%Y-%m-%d %H:%i:00') AS minuto, u.cpf, COUNT(*) AS qtd
              FROM transacoes t JOIN usuarios u ON u.id = t.user_id
             WHERE DATE(t.data_hora) BETWEEN %s AND %s
          GROUP BY minuto,u.cpf  HAVING qtd >= %s
        """
        df_cpf = pd.read_sql(sql_cpf, conn, params=(p_ini, p_fim, thr_cpf))
        df_cpf["minuto"] = pd.to_datetime(df_cpf["minuto"])

        if not df_cpf.empty:
            fig_cpf = px.scatter(df_cpf, x="minuto", y="qtd", color="cpf", size="qtd", title=f"CPFs com ≥ {thr_cpf} transações/min", labels={"minuto": "Timestamp", "qtd": "Qtd"})
            st.plotly_chart(fig_cpf, use_container_width=True)

# ════════════════════════════════════════
# 5) Alterações de dados sensíveis + Cash-Out
# ════════════════════════════════════════
# ===============================
# 🛡️ Alterações de dados sensíveis & Cash-Out
# ===============================

with st.expander("🛡️ Alterações de dados sensíveis & Cash-Out", expanded=True):

    # 1. Carrega alterações de email e telefone
    SQL_CHG = """
        SELECT 
            f.user_id,
            u.cpf,
            f.data_hora,
            f.campo,
            f.valor_antigo,
            f.valor_novo,
            'Alteração' AS evento
        FROM fatos_usuarios f
        JOIN usuarios u ON u.id = f.user_id
        WHERE f.campo IN ('email', 'telefone')
    """
    df_chg = pd.read_sql(SQL_CHG, conn, parse_dates=["data_hora"])

    # 2. Carrega transações de saída
    SQL_CO = """
        SELECT 
            user_id,
            data_hora,
            valor,
            'Cash-Out' AS evento
        FROM transacoes
        WHERE tipo_transacao IN ('Cash-Out', 'Saque')
    """
    df_co = pd.read_sql(SQL_CO, conn, parse_dates=["data_hora"])

    if df_chg.empty:
        st.info("Nenhuma alteração de e-mail ou telefone registrada.")
        st.stop()

    # 3. Tabela de alterações (últimos 5)
    st.subheader("🗒️ Ocorrências de alteração")
    st.dataframe(df_chg.head(5), use_container_width=True)

    # 4. Contagem por tipo
    st.subheader("📊 Contagem de alterações por campo")
    df_cnt = df_chg["campo"].value_counts().reset_index()
    df_cnt.columns = ["Campo", "Quantidade"]

    fig_cnt = px.bar(
        df_cnt,
        x="Campo",
        y="Quantidade",
        text_auto=True,
        color="Campo",
        title="Total de alterações por tipo de dado",
        template="plotly_dark"
    )
    fig_cnt.update_layout(showlegend=False)
    st.plotly_chart(fig_cnt, use_container_width=True)

    # 5. Timeline de eventos
    st.subheader("📌 Timeline Alteração vs Cash-Out (janela 24h)")

    # Une ambos e junta com CPF
    usuarios_df = pd.read_sql("SELECT id, cpf FROM usuarios", conn)
    df_timeline = pd.concat([
        df_chg[['user_id', 'data_hora', 'evento']],
        df_co[['user_id', 'data_hora', 'evento']]
    ], ignore_index=True)

    df_timeline = df_timeline.merge(
        usuarios_df.rename(columns={"id": "user_id"}), 
        on="user_id", how="left"
    )
    df_timeline.dropna(subset=["cpf"], inplace=True)

    fig = px.scatter(
        df_timeline,
        x="data_hora",
        y="cpf",
        color="evento",
        symbol="evento",
        title="⏱️ Timeline de Alterações e Saques (Cash-Out)",
        labels={"data_hora": "Data/Hora", "cpf": "Usuário"},
        template="plotly_dark"
    )
    fig.update_traces(marker=dict(size=9))
    fig.update_layout(yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════
# 6) Entradas × Saídas imediatas (≤ 5 min)
# ════════════════════════════════════════
# ════════════════════════════════════════
# ════════════════════════════════════════
# 6) Entradas & Saídas em ≤ 5 min (lavagem)
# ════════════════════════════════════════
with st.expander("💸 Entradas & Saídas em ≤ 5 min (lavagem)", expanded=True):

    # ── 6.1 Carrega todos os pares de entrada → saída em até 5 min ──
    SQL_LAV = """
        SELECT
            t_in.user_id,
            u.cpf,
            t_in.data_hora   AS entrada,
            t_in.valor       AS val_in,
            t_out.data_hora  AS saida,
            t_out.valor      AS val_out,
            TIMESTAMPDIFF(SECOND, t_in.data_hora, t_out.data_hora)/60.0 AS dif_min
        FROM transacoes t_in
        JOIN transacoes t_out
          ON t_out.user_id = t_in.user_id
         AND t_out.data_hora >  t_in.data_hora
         AND t_out.data_hora <= t_in.data_hora + INTERVAL 5 MINUTE
        JOIN usuarios u
          ON u.id = t_in.user_id
        WHERE t_in.tipo_transacao  IN ('Recebimento','Cash-In')
          AND t_out.tipo_transacao NOT IN ('Recebimento','Cash-In')
        ORDER BY t_in.data_hora
    """
    df_lav = pd.read_sql(SQL_LAV, conn, parse_dates=["entrada", "saida"])

    if df_lav.empty:
        st.info("Nenhum par suspeito encontrado.")
    else:
        # ── 6.2 Tabela com todos os pares ─────────────────────────
        df_tbl = (
            df_lav
            .assign(
                entrada=lambda d: d["entrada"].dt.strftime("%d/%m/%Y %H:%M:%S"),
                saida  =lambda d: d["saida"].dt.strftime("%d/%m/%Y %H:%M:%S"),
            )
            .rename(columns={
                "cpf":    "CPF",
                "val_in": "Valor Entrada (R$)",
                "val_out":"Valor Saída (R$)",
                "dif_min":"Δ Tempo (min)"
            })
        )
        st.subheader(f"Pares suspeitos encontrados ({len(df_tbl)})")
        st.dataframe(df_tbl, use_container_width=True)

        st.markdown("---")

        # ── 6.3 Scatter: tempo vs. valor de saída ───────────────────
        fig_scatter = px.scatter(
            df_lav,
            x="dif_min",
            y="val_out",
            color="cpf",
            size="val_out",
            hover_data=["entrada", "saida"],
            labels={
                "dif_min": "Tempo entre (min)",
                "val_out": "Valor Saída (R$)",
                "cpf":     "CPF"
            },
            title="Saídas em até 5 min após entrada",
            template="plotly_dark"
        )
        fig_scatter.update_layout(height=350, margin=dict(t=40,b=20))
        st.plotly_chart(fig_scatter, use_container_width=True, key="lav_scatter")

        st.markdown("---")

        # ── 6.4 Top N usuários por total de saída ───────────────────
        df_top = (
            df_lav
            .groupby("cpf", as_index=False)["val_out"]
            .sum()
            .rename(columns={"val_out": "Total Saída (R$)"})
            .sort_values("Total Saída (R$)", ascending=False)
        )
        max_users = st.slider(
            "Exibir top N usuários no gráfico", 
            min_value=1, 
            max_value=len(df_top), 
            value=min(10, len(df_top)), 
            step=1,
            key="lav_top_n"
        )
        df_plot = df_top.head(max_users)

        fig_bar = px.bar(
            df_plot,
            x="Total Saída (R$)",
            y="cpf",
            orientation="h",
            text="Total Saída (R$)",
            labels={"cpf": "CPF"},
            title=f"Top {max_users} Usuários por Total de Saída Suspeita",
            template="plotly_dark"
        )
        fig_bar.update_traces(texttemplate="R$ %{text:,.2f}", textposition="outside")
        fig_bar.update_layout(
            yaxis_categoryorder="total ascending",
            height=30 * max_users + 150,
            margin=dict(l=120, r=20, t=50, b=20)
        )
        st.plotly_chart(fig_bar, use_container_width=True, key="lav_bar")


# ════════════════════════════════════════
# 7) Alterações de senha múltiplas vezes
# ════════════════════════════════════════
# ════════════════════════════════════════
# 7) Alterações de senha múltiplas vezes
# ════════════════════════════════════════
with st.expander("🔑 Alterações de senha múltiplas vezes", expanded=False):

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        dias_ref = st.number_input(
            "Período analisado (dias)",
            min_value=1,
            max_value=90,
            value=30,
            step=1,
            key="pwd_dias_ref_7"
        )
    with col_t2:
        thr_pwd = st.number_input(
            "Mínimo de trocas para alertar",
            min_value=2,
            max_value=20,
            value=3,
            step=1,
            key="pwd_thr_pwd_7"
        )

    if st.button("Verificar trocas de senha", key="btn_pwd_7"):
        # ── 7.1  Busca eventos de troca de senha
        SQL_PWD = """
            SELECT f.user_id,
                   u.cpf,
                   f.data_hora
              FROM fatos_usuarios f
              JOIN usuarios u ON u.id = f.user_id
             WHERE (f.campo = 'senha' OR f.acao = 'Alterar senha')
               AND f.data_hora >= CURDATE() - INTERVAL %s DAY
        """
        df_pwd = pd.read_sql(SQL_PWD, conn, params=(dias_ref,), parse_dates=["data_hora"])

        if df_pwd.empty:
            st.success("Nenhuma troca de senha registrada no período.")
            st.stop()

        # ── 7.2  Contagem por usuário
        cnt = (
            df_pwd
              .groupby(["user_id", "cpf"])
              .size()
              .reset_index(name="qtd")
              .query("qtd >= @thr_pwd")
              .sort_values("qtd", ascending=False)
        )
        st.metric("Usuários acima do limite", f"{cnt.shape[0]}")

        if cnt.empty:
            st.info(f"Nenhum usuário com ≥ {thr_pwd} trocas de senha nos últimos {dias_ref} dias.")
            st.stop()

        # ── 7.3  Barra: top usuários por nº de trocas
        fig_bar_pwd = px.bar(
            cnt.head(15),
            x="qtd",
            y="cpf",
            orientation="h",
            text="qtd",
            labels={"qtd": "Trocas", "cpf": "CPF"},
            title=f"Top usuários por trocas de senha (últimos {dias_ref} dias)",
        )
        fig_bar_pwd.update_layout(yaxis_categoryorder="total ascending")
        st.plotly_chart(fig_bar_pwd, use_container_width=True)

# ════════════════════════════════════════
# 8) Top 5 maiores valores **recebidos**
# ════════════════════════════════════════
with st.expander("💰 Top 5 maiores valores recebidos", expanded=False):

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        dias_receb = st.number_input(
            "Período (dias)",
            min_value=1,
            max_value=365,
            value=30,
            step=1,
        )
    with col_r2:
        forma_in = st.selectbox(
            "Filtrar forma",
            ["Todas", "Recebimento", "Cash-In", "Pix", "Transferência"],
            index=0,
        )

    if st.button("Gerar ranking", key="btn_top_receb"):

        # ── 8.1  Base de dados: transações de entrada ──────────────
        filtros_in = ("Recebimento", "Cash-In")
        if forma_in != "Todas":
            filtros_in = (forma_in,)  # tupla de 1 elemento

        sql_in = f"""
            SELECT t.user_id,
                   u.cpf,
                   u.nome,
                   t.valor
              FROM transacoes t
              JOIN usuarios u ON u.id = t.user_id
             WHERE t.tipo_transacao IN {filtros_in}
               AND t.data_hora >= CURDATE() - INTERVAL %s DAY
        """
        df_in = pd.read_sql(sql_in, conn, params=(dias_receb,))

        if df_in.empty:
            st.info("Nenhuma entrada no período selecionado.")
            st.stop()

        # ── 8.2  Soma por usuário e top 5 ──────────────────────────
        top_in = (
            df_in.groupby(["user_id", "cpf", "nome"])["valor"]
            .sum()
            .sort_values(ascending=False)
            .head(5)
            .reset_index()
        )

        # ── 8.3  Pie chart ou ranking (usuário escolhe) ────────────
        view = st.radio(
            "Visualização",
            ["Pizza", "Ranking (barra)"],
            horizontal=True,
        )

        if view == "Pizza":
            fig_pie = px.pie(
                top_in,
                names="cpf",
                values="valor",
                hover_data=["nome", "valor"],
                hole=0.45,
                title=f"Top 5 CPFs por valor de entrada (últimos {dias_receb} dias)",
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            fig_bar = px.bar(
                top_in,
                x="valor",
                y="cpf",
                text="valor",
                orientation="h",
                labels={"valor": "Valor Recebido (R$)", "cpf": "CPF"},
                title=f"Top 5 CPFs por valor de entrada (últimos {dias_receb} dias)",
            )
            fig_bar.update_layout(yaxis_categoryorder="total ascending")
            st.plotly_chart(fig_bar, use_container_width=True)

        # ── 8.4  Tabela detalhada ─────────────────────────────────
        st.dataframe(
            top_in.rename(columns={"valor": "Valor Recebido (R$)"}),
            use_container_width=True,
        )

# ════════════════════════════════════════
# 9) Compras on-line – soma por categoria
# ════════════════════════════════════════
with st.expander("🛒 Compras por categoria (on-line)", expanded=False):

    # ▸ Parâmetros
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        dias_comp = st.number_input(
            "Período (dias)",
            min_value=1,
            max_value=365,
            value=90,
            step=1,
        )
    with col_c2:
        top_n = st.number_input(
            "Mostrar Top-N categorias",
            min_value=3,
            max_value=30,
            value=10,
            step=1,
        )

    if st.button("Gerar gráfico", key="btn_cat"):

        # ── 9.1  Consulta compras_online ───────────────────────────
        SQL_CAT = f"""
            SELECT
                COALESCE(categoria,'(Sem categoria)') AS categoria,
                SUM(
                    COALESCE(valor_total, valor_unit * COALESCE(qtd,1))
                ) AS total
            FROM compras_online
            WHERE data_hora >= CURDATE() - INTERVAL %s DAY
            GROUP BY categoria
            ORDER BY total DESC
            LIMIT {int(top_n)}
        """
        df_cat = pd.read_sql(SQL_CAT, conn, params=(dias_comp,))

        if df_cat.empty:
            st.info("Nenhuma compra encontrada no período selecionado.")
            st.stop()

        # ── 9.2  Gráfico de barras horizontais ────────────────────
        fig_cat = px.bar(
            df_cat,
            x="total",
            y="categoria",
            orientation="h",
            text="total",
            labels={"total": "Valor total (R$)", "categoria": "Categoria"},
            title=f"Top {len(df_cat)} categorias – soma de compras on-line (últimos {dias_comp} dias)",
        )
        fig_cat.update_layout(yaxis_categoryorder="total ascending")
        st.plotly_chart(fig_cat, use_container_width=True)

        # ── 9.3  Tabela detalhada ─────────────────────────────────
        st.dataframe(
            df_cat.rename(columns={"total": "Valor total (R$)"}),
            use_container_width=True,
        )

# ════════════════════════════════════════
# 10) Top usuários por valor de compras
# ════════════════════════════════════════
with st.expander("💳 Top usuários que mais gastam em compras", expanded=False):

    # ▸ filtros de período & Top-N
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        dias_usr = st.number_input(
            "Período (dias)",
            min_value=1,
            max_value=365,
            value=90,
            step=1,
            key="top_comp_dias_usr",
        )
    with col_u2:
        top_u = st.number_input(
            "Mostrar Top-N usuários",
            min_value=3,
            max_value=50,
            value=10,
            step=1,
            key="top_comp_n_usr",
        )

    if st.button("Gerar ranking de gastos", key="btn_top_user_comp"):

        # 10.1 ▶ Carrega compras online
        SQL_ON = """
            SELECT user_id,
                   COALESCE(valor_total, valor_unit * COALESCE(qtd,1)) AS valor
              FROM compras_online
             WHERE data_hora >= CURDATE() - INTERVAL %s DAY
        """
        df_on = pd.read_sql(SQL_ON, conn, params=(dias_usr,))

        # 10.2 ▶ Carrega transações do tipo 'Compra'
        SQL_TX = """
            SELECT user_id,
                   valor
              FROM transacoes
             WHERE tipo_transacao = 'Compra'
               AND data_hora >= CURDATE() - INTERVAL %s DAY
        """
        df_tx = pd.read_sql(SQL_TX, conn, params=(dias_usr,))

        # 10.3 ▶ Combina e agrega gastos
        df_comb = pd.concat([df_on, df_tx], ignore_index=True)
        if df_comb.empty:
            st.info("Nenhuma compra encontrada no período selecionado.")
            st.stop()

        df_top = (
            df_comb.groupby("user_id")["valor"]
            .sum()
            .sort_values(ascending=False)
            .head(int(top_u))
            .reset_index()
        )

        # 10.4 ▶ Busca CPF/nome para os user_id retornados
        ids = df_top["user_id"].tolist()
        if ids:
            placeholders = ",".join(["%s"] * len(ids))
            sql_users = f"""
                SELECT id AS user_id, cpf, nome
                  FROM usuarios
                 WHERE id IN ({placeholders})
            """
            df_users = pd.read_sql(sql_users, conn, params=ids)
            df_top = df_top.merge(df_users, on="user_id", how="left")

        # 10.5 ▶ Gráfico de barras horizontais
        fig_topu = px.bar(
            df_top,
            x="valor",
            y="cpf",
            orientation="h",
            text="valor",
            hover_data=["nome"],
            labels={"valor": "Gasto total (R$)", "cpf": "CPF"},
            title=f"Top {len(df_top)} usuários por gastos em compras (últimos {dias_usr} dias)",
        )
        fig_topu.update_layout(yaxis_categoryorder="total ascending")
        st.plotly_chart(fig_topu, use_container_width=True)

        # 10.6 ▶ Tabela detalhada (sem coluna user_id)
        df_disp = (
            df_top.rename(
                columns={
                    "cpf": "CPF",
                    "nome": "Nome",
                    "valor": "Gasto total (R$)",
                }
            )
            .loc[:, ["CPF", "Nome", "Gasto total (R$)"]]
        )
        st.dataframe(df_disp, use_container_width=True)

# ════════════════════════════════════════
# 11) Média de valor por categoria × valor recente
# ════════════════════════════════════════
with st.expander("📊 Média de pagamentos por categoria", expanded=False):

    # ▸ Parâmetro: período em dias para cálculo da média
    dias_media = st.number_input(
        "Dias para média",
        min_value=1,
        max_value=365,
        value=90,
        step=1,
        key="media_cat_dias"
    )

    if st.button("Calcular média", key="btn_media_cat"):

        # ── 11.1 consulta média por categoria ────────────────────
        SQL_AVG = """
            SELECT
                COALESCE(categoria,'(Sem categoria)') AS categoria,
                AVG(COALESCE(valor_total, valor_unit*qtd, 0)) AS media
            FROM compras_online
            WHERE data_hora >= CURDATE() - INTERVAL %s DAY
            GROUP BY categoria
            ORDER BY media DESC
        """
        df_avg = pd.read_sql(SQL_AVG, conn, params=(dias_media,))

        if df_avg.empty:
            st.info("Nenhuma compra encontrada no período selecionado.")
        else:
            # ── 11.2 gráfico de barras da média ────────────────────
            fig_avg = px.bar(
                df_avg,
                x="categoria",
                y="media",
                text="media",
                labels={"categoria": "Categoria", "media": "Média (R$)"},
                title=f"Média de pagamentos por categoria (últimos {dias_media} dias)",
                template="plotly_dark"
            )
            fig_avg.update_traces(
                texttemplate="R$ %{text:,.2f}",
                textposition="outside",
            )
            fig_avg.update_layout(
                xaxis_tickangle=-30,
                yaxis_title="Média (R$)",
            )
            st.plotly_chart(fig_avg, use_container_width=True)

            # ── 11.3 tabela resumida de médias ───────────────────────
            st.dataframe(
                df_avg.rename(columns={"media": "Média (R$)"}),
                use_container_width=True
            )

# ════════════════════════════════════════
# 12) Radar de risco de comportamento (por usuário) – com cores individuais
# ════════════════════════════════════════
# ---------- Radar de Risco de Comportamento (apenas para usuários suspeitos) -----------
with st.expander("🕵️ Radar de Risco - Usuários Suspeitos", expanded=False):

    # 1. Filtros de período e critérios
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        dias_risk = st.number_input(
            "Período de análise (dias)",
            min_value=1,
            max_value=365,
            value=30,
            step=1,
            key="radar_periodo_suspeitos"
        )
    with col_r2:
        min_suspeitas = st.number_input(
            "Mínimo de transações suspeitas",
            min_value=1,
            value=3,
            step=1,
            help="Filtra apenas usuários com N ou mais transações suspeitas"
        )

    # 2. Consulta para identificar usuários suspeitos
    if st.button("Buscar usuários suspeitos", key="btn_buscar_suspeitos"):
        
        # Consulta para encontrar usuários com transações suspeitas
        sql_suspeitos = """
            SELECT 
                u.id,
                u.cpf,
                COUNT(*) AS qtd_suspeitas,
                SUM(t.valor) AS valor_total_suspeitas
            FROM transacoes t
            JOIN usuarios u ON u.id = t.user_id
            WHERE t.suspeita = 1
              AND t.data_hora >= CURDATE() - INTERVAL %s DAY
            GROUP BY u.id, u.cpf
            HAVING COUNT(*) >= %s
            ORDER BY qtd_suspeitas DESC
        """
        
        df_suspeitos = pd.read_sql(sql_suspeitos, conn, params=(dias_risk, min_suspeitas))
        
        if df_suspeitos.empty:
            st.warning(f"Nenhum usuário com {min_suspeitas} ou mais transações suspeitas nos últimos {dias_risk} dias.")
            st.stop()
        
        # 3. Seleção do usuário para análise detalhada
        usuario_selecionado = st.selectbox(
            "Selecione um usuário para análise detalhada",
            df_suspeitos["cpf"].tolist(),
            key="select_suspeito"
        )
        
        user_id = int(df_suspeitos.loc[df_suspeitos["cpf"] == usuario_selecionado, "id"].iloc[0])
        
        # 4. Métricas para o radar de risco
        with st.spinner("Calculando métricas de risco..."):
            
            # 4.1 Alterações de perfil
            sql_perfil = """
                SELECT COUNT(*) AS cnt
                FROM fatos_usuarios
                WHERE user_id = %s
                  AND (campo IN ('email','telefone') OR acao LIKE 'Alterar%')
                  AND data_hora >= CURDATE() - INTERVAL %s DAY
            """
            qtd_perfil = pd.read_sql(sql_perfil, conn, params=(user_id, dias_risk))["cnt"].iloc[0]
            
            # 4.2 Total de compras
            sql_comp = """
                SELECT COALESCE(SUM(COALESCE(valor_total, valor_unit * COALESCE(qtd,1))),0) AS total
                FROM compras_online
                WHERE user_id = %s
                  AND data_hora >= CURDATE() - INTERVAL %s DAY
            """
            total_comp = pd.read_sql(sql_comp, conn, params=(user_id, dias_risk))["total"].iloc[0]
            
            # 4.3 Saldo pendente
            sql_saldo = "SELECT COALESCE(saldo_pendente,0) AS saldo FROM usuarios WHERE id = %s"
            saldo_pend = pd.read_sql(sql_saldo, conn, params=(user_id,))["saldo"].iloc[0]
            
            # 4.4 Transações suspeitas
            qtd_suspeitas = int(df_suspeitos.loc[df_suspeitos["cpf"] == usuario_selecionado, "qtd_suspeitas"])
            
            # 4.5 Valor total de transações suspeitas
            valor_suspeitas = float(df_suspeitos.loc[df_suspeitos["cpf"] == usuario_selecionado, "valor_total_suspeitas"])
            
            # 5. Montagem do DataFrame para o radar
            df_radar = pd.DataFrame({
                "theta": [
                    "Alterações de perfil", 
                    "Total compras (R$)", 
                    "Saldo pendente (R$)",
                    "Transações suspeitas",
                    "Valor suspeitas (R$)"
                ],
                "r": [
                    qtd_perfil, 
                    total_comp, 
                    saldo_pend,
                    qtd_suspeitas,
                    valor_suspeitas
                ]
            })
            
            # 6. Radar Chart
            fig_radar = px.line_polar(
                df_radar,
                r="r",
                theta="theta",
                color="theta",
                line_close=True,
                markers=True,
                color_discrete_sequence=px.colors.qualitative.Set2,
                title=f"Radar de risco para {usuario_selecionado} (últimos {dias_risk}d)",
            )
            fig_radar.update_traces(fill="toself")
            fig_radar.update_layout(
                legend_title_text="Métrica",
                polar=dict(
                    radialaxis=dict(visible=True, tickangle=45)
                )
            )
            st.plotly_chart(fig_radar, use_container_width=True)
            
            # 7. Tabela com valores detalhados
            st.markdown("**Valores das métricas**")
            df_display = df_radar.set_index("theta").rename(columns={"r": "Valor"})
            st.dataframe(df_display, use_container_width=True)
            
            # 8. Lista de transações suspeitas
            st.markdown("**Transações suspeitas recentes**")
            sql_tx_suspeitas = """
                SELECT 
                    t.id,
                    t.tipo_transacao AS tipo,
                    t.valor,
                    t.data_hora,
                    t.motivo_suspeita AS motivo
                FROM transacoes t
                WHERE t.user_id = %s
                  AND t.suspeita = 1
                  AND t.data_hora >= CURDATE() - INTERVAL %s DAY
                ORDER BY t.data_hora DESC
            """
            df_tx_suspeitas = pd.read_sql(sql_tx_suspeitas, conn, params=(user_id, dias_risk))
            st.dataframe(df_tx_suspeitas, use_container_width=True)
# ════════════════════════════════════════
# 13) Média de entradas (renda) vs gastos recentes
# ════════════════════════════════════════
# ════════════════════════════════════════
# 13) Renda média e gastos por usuário
# ════════════════════════════════════════
with st.expander("💸 Renda média e gastos por usuário", expanded=False):

    dias_renda = st.number_input(
        "Período (dias)",
        min_value=1,
        max_value=365,
        value=30,
        step=1,
        key="med_renda_periodo_all"
    )

    if st.button("Calcular renda e gastos", key="btn_med_renda_all"):

        # ── 13.1 Média de renda por usuário ─────────────────────
        SQL_INC = """
            SELECT
              u.id         AS user_id,
              u.cpf        AS CPF,
              AVG(t.valor) AS renda_media
            FROM transacoes t
            JOIN usuarios u ON u.id = t.user_id
            WHERE t.tipo_transacao <> 'Compra'
              AND t.data_hora >= CURDATE() - INTERVAL %s DAY
            GROUP BY u.id, u.cpf
        """
        df_inc = pd.read_sql(SQL_INC, conn, params=(dias_renda,))

        # ── 13.2 Gasto total por usuário ─────────────────────────
        SQL_OUT = """
            SELECT
              user_id,
              SUM(valor) AS gasto_total
            FROM transacoes
            WHERE tipo_transacao = 'Compra'
              AND data_hora >= CURDATE() - INTERVAL %s DAY
            GROUP BY user_id
        """
        df_out = pd.read_sql(SQL_OUT, conn, params=(dias_renda,))

        # ── 13.3 Merge e formatações ────────────────────────────
        df_merge = (
            df_inc
            .merge(df_out, on="user_id", how="left")
            .fillna(0)
            .sort_values("gasto_total", ascending=False)
        )
        df_merge["renda_media"] = df_merge["renda_media"].round(2)
        df_merge["gasto_total"] = df_merge["gasto_total"].round(2)

        if df_merge.empty:
            st.info("Nenhum registro encontrado no período selecionado.")
            st.stop()

        # ── 13.4 Mostrar tabela completa ────────────────────────
        st.subheader(f"Renda média vs gasto total (últimos {dias_renda} dias)")
        st.dataframe(
            df_merge.rename(columns={
                "renda_media": "Renda média (R$)",
                "gasto_total": "Gasto total (R$)"
            }).set_index("CPF"),
            use_container_width=True
        )

        # ── 13.5 Controle de quantos usuários exibir no gráfico ──
        max_users = st.number_input(
            "Qtd. de usuários no gráfico",
            min_value=1,
            max_value=len(df_merge),
            value=min(15, len(df_merge)),
            step=1,
            key="limite_usuarios"
        )
        df_plot = df_merge.head(max_users)

        # ── 13.6 Gráfico comparativo filtrado ───────────────────
        df_melt = df_plot.reset_index().melt(
            id_vars="CPF",
            value_vars=["renda_media", "gasto_total"],
            var_name="Métrica",
            value_name="Valor"
        )
        fig_cmp = px.bar(
            df_melt,
            x="Valor",
            y="CPF",
            color="Métrica",
            orientation="h",
            text="Valor",
            labels={"Valor": "R$ período", "CPF": "Usuário", "Métrica": ""},
            title=f"Comparativo: Renda média vs Gasto total (top {max_users} usuários)",
            template="plotly_dark"
        )
        fig_cmp.update_traces(texttemplate="R$ %{text:,.2f}", textposition="outside")
        fig_cmp.update_layout(yaxis_categoryorder="total ascending", height=30 * max_users + 200)
        st.plotly_chart(fig_cmp, use_container_width=True)


# ════════════════════════════════════════
# 14) Fatos do sistema – timeline de ações
# ════════════════════════════════════════
from datetime import date, timedelta

# ════════════════════════════════════════
# 14) Fatos do sistema – timeline de ações
# ════════════════════════════════════════
with st.expander("📜 Timeline de Fatos do Sistema & Atividades Suspeitas", expanded=False):

    # ── 14.1 Período ────────────────────────────────────────────
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        dt_inicio = st.date_input(
            label="Data início",
            value=date.today() - timedelta(days=30),
            key="fatos_data_inicio"
        )
    with col_f2:
        dt_fim = st.date_input(
            label="Data fim",
            value=date.today(),
            key="fatos_data_fim"
        )

    gerar = st.button("Gerar timeline completa", key="btn_fatos_completo")

    if gerar:

        if dt_fim < dt_inicio:
            st.error("⚠️ A data final deve ser maior ou igual à data inicial.")
            st.stop()

        # ── 14.2 Consulta unificada ─────────────────────────────
        sql_fatos = """
            /* Fatos de auditoria */
            SELECT DATE(f.data_hora) AS dt,
                   f.acao            AS evento,
                   COUNT(*)          AS qtd
            FROM fatos_usuarios f
            WHERE f.data_hora BETWEEN %s AND %s + INTERVAL 1 DAY
            GROUP BY DATE(f.data_hora), evento

            UNION ALL

            /* Transações suspeitas */
            SELECT DATE(t.data_hora) AS dt,
                   COALESCE(t.motivo_suspeita, 'Transação suspeita') AS evento,
                   COUNT(*) AS qtd
            FROM transacoes t
            WHERE t.suspeita = 1
              AND t.data_hora BETWEEN %s AND %s + INTERVAL 1 DAY
            GROUP BY DATE(t.data_hora), evento

            ORDER BY dt;
        """
        df_fatos = pd.read_sql(sql_fatos, conn, params=(dt_inicio, dt_fim, dt_inicio, dt_fim))

        if df_fatos.empty:
            st.info("Nenhum fato ou transação suspeita no período selecionado.")
            st.stop()

        # ── 14.3 Linha diária ───────────────────────────────────
        fig_fatos = px.line(
            df_fatos,
            x="dt",
            y="qtd",
            color="evento",
            markers=True,
            labels={"dt": "Data", "qtd": "Quantidade", "evento": "Evento"},
            title=f"Fatos & Suspeitas por dia ({dt_inicio} → {dt_fim})"
        )
        st.plotly_chart(fig_fatos, use_container_width=True, key="chart_fatos_timeline")

        # ── 14.4 Barra total (relevância) ───────────────────────
        df_tot_ev = (
            df_fatos
            .groupby("evento", as_index=False)["qtd"]
            .sum()
            .sort_values("qtd", ascending=True)
        )
        total_all = df_tot_ev["qtd"].sum()
        df_tot_ev["label"] = (
            df_tot_ev["qtd"].astype(str)
            + " ("
            + (df_tot_ev["qtd"] / total_all * 100).round(1).astype(str)
            + "%)"
        )

        fig_bar = px.bar(
            df_tot_ev,
            x="qtd",
            y="evento",
            orientation="h",
            text="label",
            labels={"evento": "Evento", "qtd": "Total"},
            title="Total de fatos & suspeitas no período"
        )
        fig_bar.update_layout(yaxis_categoryorder="total ascending")
        st.plotly_chart(fig_bar, use_container_width=True, key="chart_fatos_bar")

# ════════════════════════════════════════
# 15) Fatos de Transações Suspeitas
# ════════════════════════════════════════
with st.expander("🚩 Fatos de transações suspeitas", expanded=False):
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        dt_inicio_tx = st.date_input(
            "De",
            value=pd.Timestamp.now().date() - timedelta(days=30),
            key="fatos_tx_de"
        )
    with col_f2:
        dt_fim_tx = st.date_input(
            "Até",
            value=pd.Timestamp.now().date(),
            key="fatos_tx_ate"
        )

    if st.button("Gerar gráfico", key="btn_fatos_tx"):
        sql_fatos_tx = """
            SELECT
                DATE(data_hora)       AS dia,
                motivo_suspeita       AS motivo,
                COUNT(*)              AS qtd
            FROM transacoes
            WHERE suspeita = 1
              AND DATE(data_hora) BETWEEN %s AND %s
            GROUP BY dia, motivo_suspeita
            ORDER BY dia
        """
        df_fatos_tx = pd.read_sql(sql_fatos_tx, conn, params=(dt_inicio_tx, dt_fim_tx))

        if df_fatos_tx.empty:
            st.info("Nenhuma transação suspeita no período selecionado.")
        else:
            fig_fatos_tx = px.bar(
                df_fatos_tx,
                x="dia",
                y="qtd",
                color="motivo",
                text="qtd",
                labels={
                    "dia": "Data",
                    "qtd": "Quantidade",
                    "motivo": "Motivo da suspeita"
                },
                title=f"Transações suspeitas por motivo ({dt_inicio_tx} a {dt_fim_tx})",
            )
            fig_fatos_tx.update_layout(
                barmode="group",
                xaxis_title="Data",
                yaxis_title="Qtd de transações"
            )
            st.plotly_chart(fig_fatos_tx, use_container_width=True)

# ════════════════════════════════════════
# 16) Transações marcadas como suspeitas
# ════════════════════════════════════════
with st.expander("🚩 Transações marcadas como suspeitas", expanded=False):
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        fra_ini = st.date_input(
            "De",
            value=pd.Timestamp.now().date() - timedelta(days=30),
            key="fraudes_de"
        )
    with col_f2:
        fra_fim = st.date_input(
            "Até",
            value=pd.Timestamp.now().date(),
            key="fraudes_ate"
        )

    if st.button("Gerar relatórios de fraudes", key="btn_fraudes"):
        SQL_FRAUDE = """
            SELECT
                t.id,
                DATE_FORMAT(t.data_hora,'%d/%m/%Y %H:%i') AS data_hora,
                u.username,
                t.tipo_transacao AS tipo,
                t.valor,
                t.motivo_suspeita AS motivo
            FROM transacoes t
            JOIN usuarios u ON u.id = t.user_id
            WHERE t.suspeita = 1
              AND DATE(t.data_hora) BETWEEN %s AND %s
            ORDER BY t.data_hora DESC
        """
        df_fraud = pd.read_sql(SQL_FRAUDE, conn, params=(fra_ini, fra_fim))

        st.write(f"➤ Encontradas **{len(df_fraud)}** transações suspeitas")
        st.dataframe(df_fraud, use_container_width=True)

        if not df_fraud.empty:
            col_a, col_b = st.columns(2)
            with col_a:
                fig_tipo = px.pie(
                    df_fraud,
                    names="tipo",
                    title="Tipos de Transações Suspeitas",
                    hole=0.4,
                    labels={"tipo": "Tipo"}
                )
                st.plotly_chart(fig_tipo, use_container_width=True)
            with col_b:
                fig_valor = px.histogram(
                    df_fraud,
                    x="valor",
                    nbins=20,
                    title="Distribuição de Valores Suspeitos",
                    labels={"valor": "Valor (R$)"}
                )
                st.plotly_chart(fig_valor, use_container_width=True)

# ════════════════════════════════════════
# 17) Histórico de Edições de Perfil
# ════════════════════════════════════════
with st.expander("📝 Histórico de Edições de Perfil", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        ed_de = st.date_input(
            "De",
            value=pd.Timestamp.now().date() - timedelta(days=30),
            key="edicoes_de"
        )
    with c2:
        ed_ate = st.date_input(
            "Até",
            value=pd.Timestamp.now().date(),
            key="edicoes_ate"
        )

    if st.button("Gerar histórico de edições", key="btn_edicoes"):
        # 1) Busca os detalhes de edição
        SQL_ED = """
            SELECT
                f.id,
                DATE_FORMAT(f.data_hora, '%d/%m/%Y %H:%i') AS data_hora,
                u.username,
                f.campo,
                f.valor_antigo AS de,
                f.valor_novo   AS para
            FROM fatos_usuarios f
            JOIN usuarios u ON u.id = f.user_id
            WHERE f.entidade = 'usuarios'
              AND DATE(f.data_hora) BETWEEN %s AND %s
            ORDER BY f.data_hora DESC
        """
        df_ed = pd.read_sql(SQL_ED, conn, params=(ed_de, ed_ate))

        st.write(f"➤ Encontradas **{len(df_ed)}** edições de perfil")
        st.dataframe(df_ed, use_container_width=True)

        if not df_ed.empty:
            # 2) Gráfico: quais campos foram mais alterados
            df_cnt = (
                df_ed
                .groupby("campo")
                .size()
                .reset_index(name="qtd")
                .sort_values("qtd", ascending=False)
            )

            fig_ed = px.bar(
                df_cnt,
                x="campo", y="qtd",
                text="qtd",
                labels={"campo": "Campo editado", "qtd": "Nº de edições"},
                title="Campos de perfil mais editados"
            )
            fig_ed.update_layout(xaxis_title=None, yaxis_title="Edições")
            st.plotly_chart(fig_ed, use_container_width=True)

# ════════════════════════════════════════
# 18) Tentativas de Login OK vs FAIL
# ════════════════════════════════════════
with st.expander("🔐 Tentativas de Login", expanded=False):
    lcol1, lcol2 = st.columns(2)
    with lcol1:
        login_de = st.date_input(
            "Data inicial",
            value=pd.Timestamp.now().date() - timedelta(days=30),
            key="login_de"
        )
    with lcol2:
        login_ate = st.date_input(
            "Data final",
            value=pd.Timestamp.now().date(),
            key="login_ate"
        )

    if st.button("Gerar gráfico de logins", key="btn_logins"):
        SQL_LOG = """
            SELECT resultado,
                   COUNT(*) AS qtd
              FROM logs
             WHERE DATE(data_hora) BETWEEN %s AND %s
             GROUP BY resultado
        """
        df_log = pd.read_sql(SQL_LOG, conn, params=(login_de, login_ate))

        st.write(f"▶️ Total de tentativas: **{int(df_log['qtd'].sum())}**")
        st.dataframe(df_log, use_container_width=True)

        # Gráfico de barras OK vs FAIL
        fig_log = px.bar(
            df_log,
            x="resultado",
            y="qtd",
            color="resultado",
            text="qtd",
            labels={"resultado": "Resultado", "qtd": "Quantidade"},
            title="Tentativas de Login: OK vs FAIL"
        )
        fig_log.update_traces(textposition="outside")
        fig_log.update_layout(
            xaxis_title=None,
            yaxis_title="Número de tentativas",
            showlegend=False,
            margin=dict(t=50, b=20, l=20, r=20)
        )
        st.plotly_chart(fig_log, use_container_width=True)

# ════════════════════════════════════════
# 19) Alterações de senha múltiplas vezes (Mestre)
# ════════════════════════════════════════
# ════════════════════════════════════════
# 19) Alterações de senha múltiplas vezes (Mestre)
# ════════════════════════════════════════
with st.expander("🔑 Alterações de senha múltiplas vezes", expanded=False):

    # ── Parâmetros de análise ───────────────────────────────────
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        dias_ref = st.number_input(
            "Período analisado (dias)",
            min_value=1,
            max_value=90,
            value=30,
            step=1,
            key="pwd_dias_ref_19"               # <<< key única
        )
    with col_t2:
        thr_pwd = st.number_input(
            "Mínimo de trocas para alertar",
            min_value=2,
            max_value=20,
            value=3,
            step=1,
            key="pwd_thr_pwd_19"                # <<< key única
        )

    if st.button("Verificar trocas de senha", key="btn_pwd_19"):   # <<< key única

        # ── 19.1  Buscar eventos de troca de senha ────────────────
        SQL_PWD = """
            SELECT f.user_id,
                   u.cpf,
                   f.data_hora
              FROM fatos_usuarios f
              JOIN usuarios u ON u.id = f.user_id
             WHERE (f.campo = 'senha' OR f.acao = 'Alterar senha')
               AND f.data_hora >= CURDATE() - INTERVAL %s DAY
        """
        df_pwd = pd.read_sql(
            SQL_PWD,
            conn,
            params=(dias_ref,),
            parse_dates=["data_hora"],
        )

        if df_pwd.empty:
            st.success("Nenhuma troca de senha registrada no período.")
            st.stop()

        # ── 19.2  Contagem por usuário ─────────────────────────────
        cnt = (
            df_pwd
            .groupby(["user_id", "cpf"])
            .size()
            .reset_index(name="qtd")
            .query("qtd >= @thr_pwd")
            .sort_values("qtd", ascending=False)
        )

        # KPI de quantos usuários estão acima do limite
        st.metric("Usuários acima do limite", f"{cnt.shape[0]}")

        if cnt.empty:
            st.info(f"Nenhum usuário com ≥ {thr_pwd} trocas de senha nos últimos {dias_ref} dias.")
            st.stop()

        # ── 19.3  Gráfico de barras: top usuários por trocas ──────
        fig_bar_pwd = px.bar(
            cnt.head(15),
            x="qtd",
            y="cpf",
            orientation="h",
            text="qtd",
            labels={"qtd": "Trocas", "cpf": "CPF"},
            title=f"Top usuários por trocas de senha (últimos {dias_ref} dias)",
        )
        fig_bar_pwd.update_layout(yaxis_categoryorder="total ascending")
        st.plotly_chart(fig_bar_pwd, use_container_width=True)


# ════════════════════════════════════════
# 20) Entradas sem histórico (Cash-In Sem Histórico)
# ════════════════════════════════════════
# ════════════════════════════════════════
# 20) Entradas sem histórico (Cash-In Sem Histórico)
# ════════════════════════════════════════
with st.expander("💰 Regra 6: Cash-In Sem Histórico", expanded=False):

    # ── Busca todas as cash-ins >= R$ 5000 sem histórico nos 7d anteriores ──
    SQL = """
        SELECT
            u.cpf                  AS CPF,
            COUNT(*)               AS qtd_casos,
            SUM(t.valor)           AS total_valor
        FROM transacoes t
        JOIN usuarios u ON u.id = t.user_id
        WHERE t.tipo_transacao = 'Recebimento'
          AND t.valor >= 5000
          AND NOT EXISTS (
                SELECT 1
                  FROM transacoes t2
                 WHERE t2.user_id = t.user_id
                   AND t2.data_hora < t.data_hora
                   AND t2.data_hora >= t.data_hora - INTERVAL 7 DAY
          )
        GROUP BY u.cpf
        ORDER BY qtd_casos DESC
        LIMIT 10
    """
    df_cashin = pd.read_sql(SQL, conn)

    if df_cashin.empty:
        st.info("Nenhuma transação suspeita encontrada.")
    else:
        # ── Gráfico de barras: top 10 usuários por número de casos ──
        fig = px.bar(
            df_cashin,
            x="qtd_casos",
            y="CPF",
            orientation="h",
            text="qtd_casos",
            labels={"qtd_casos": "Casos sem histórico", "CPF": "Usuário"},
            title="Top 10 Usuários com Cash-In Sem Histórico (≥ R$ 5 000)",
            template="plotly_dark"
        )
        fig.update_layout(
            yaxis=dict(autorange="reversed"),
            margin=dict(l=100, t=50, r=20, b=20)
        )
        fig.update_traces(texttemplate="%{text}", textposition="outside")
        st.plotly_chart(fig, use_container_width=True)

        # ── Tabela resumida (opcional) ─────────────────────────────
        st.dataframe(
            df_cashin.rename(columns={
                "qtd_casos": "Casos sem histórico",
                "total_valor": "Valor total (R$)"
            }),
            use_container_width=True
        )

# ════════════════════════════════════════
# 21) Contas com Alto Risco de Fraude (via flag de suspeita)
# ════════════════════════════════════════
with st.expander("⚠️ Contas com Alto Risco de Fraude", expanded=False):
    risco_de  = st.date_input("Data inicial", key="dash_risco_de")
    risco_ate = st.date_input("Data final",   key="dash_risco_ate")
    top_n     = st.number_input(
        "Top N usuários",
        min_value=1,
        value=10,
        step=1,
        key="dash_risco_topn",
    )

    if st.button("Gerar lista de risco", key="dash_btn_risco"):
        SQL_RISCO = """
            SELECT
              u.id                     AS user_id,
              u.username,
              u.email,
              u.banco,
              COUNT(*)                 AS total_suspeitas,
              SUM(t.valor)             AS valor_total_suspeitas,
              MAX(t.data_hora)         AS ultima_suspeita
            FROM transacoes AS t
            JOIN usuarios    AS u ON u.id = t.user_id
            WHERE t.suspeita = 1
              AND DATE(t.data_hora) BETWEEN %s AND %s
            GROUP BY u.id
            HAVING total_suspeitas > 0
            ORDER BY total_suspeitas DESC, valor_total_suspeitas DESC
            LIMIT %s
        """

        df_risco = pd.read_sql(
            SQL_RISCO,
            conn,
            params=(risco_de, risco_ate, top_n)
        )

        if df_risco.empty:
            st.info("Nenhuma conta com transações suspeitas nesse período.")
        else:
            st.success(f"{len(df_risco)} contas com transações suspeitas")
            c1, c2, c3 = st.columns(3)
            c1.metric("Contas suspeitas", len(df_risco))
            c2.metric("Máx. Suspeitas",  int(df_risco["total_suspeitas"].max()))
            c3.metric(
                "Valor Médio (R$)",
                f"R$ {df_risco['valor_total_suspeitas'].mean():,.2f}"
            )

            # tabela detalhada
            df_tabela = (
                df_risco
                .assign(
                    valor_total_suspeitas=lambda d: d["valor_total_suspeitas"]
                                                    .map("R$ {:,.2f}".format),
                    ultima_suspeita=lambda d: d["ultima_suspeita"]
                                              .dt.strftime("%d/%m/%Y %H:%M")
                )
            )
            st.dataframe(df_tabela, use_container_width=True)

            # gráfico de barras horizontais
            fig = px.bar(
                df_risco.sort_values("total_suspeitas", ascending=True),
                x="total_suspeitas",
                y="username",
                orientation="h",
                labels={
                    "total_suspeitas":          "Qtd. Suspeitas",
                    "username":                 "Usuário"
                },
                title=f"Top {top_n} contas por transações suspeitas",
                hover_data=["valor_total_suspeitas", "ultima_suspeita"]
            )
            fig.update_layout(
                margin=dict(t=40, b=20, l=120, r=20),
                yaxis=dict(autorange="reversed")
            )
            st.plotly_chart(fig, use_container_width=True)

# ════════════════════════════════════════
# Estatísticas de Valores de Transação (Simplificado)
# ════════════════════════════════════════
# ════════════════════════════════════════
# Estatísticas de Valores de Transação (Simplificado)
# ════════════════════════════════════════
with st.expander("📊 Estatísticas de Valores de Transação", expanded=False):

    # carregamos num DataFrame à parte (não em df_tx!)
    df_stats = pd.read_sql(
        "SELECT valor, suspeita FROM transacoes",
        conn
    )

    # calculamos as métricas sobre df_stats
    média   = df_stats["valor"].mean()
    mediana = df_stats["valor"].median()
    std_dev = df_stats["valor"].std()
    cv_rel  = std_dev / média * 100

    # exibe os KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Média (R$)",           f"R$ {média:,.2f}")
    k2.metric("Mediana (R$)",         f"R$ {mediana:,.2f}")
    k3.metric("Desvio-Padrão (R$)",   f"R$ {std_dev:,.2f}")
    k4.metric("Coef. Var (%)",       f"{cv_rel:.1f}%")

    st.markdown("---")

    # histograma sobre df_stats
    fig = px.histogram(
        df_stats,
        x="valor",
        nbins=30,
        title="Distribuição de Valores de Transação",
        labels={"valor": "Valor (R$)"}
    )
    # ... etc ...
    st.plotly_chart(fig, use_container_width=True)

    # tabela resumida
    resumo = pd.DataFrame({
        "Estatística": ["Média", "Mediana", "Desvio-Padrão", "Coef. Var (%)"],
        "Valor": [
            f"R$ {média:,.2f}",
            f"R$ {mediana:,.2f}",
            f"R$ {std_dev:,.2f}",
            f"{cv_rel:.1f}%"
        ]
    }).set_index("Estatística")
    st.table(resumo)


# ════════════════════════════════════════
# 16) 🚨 Fraudes Detectadas por Banco
# ════════════════════════════════════════
# ════════════════════════════════════════
# 16) 🚨 Fraudes Detectadas por Banco
# ════════════════════════════════════════
with st.expander("🚨 Fraudes Detectadas por Banco", expanded=False):

    # 1) Consulta direta, já trazendo o banco de cada usuário
    SQL_FRAUD = """
      SELECT
        u.banco       AS banco,
        COUNT(*)      AS qtd
      FROM transacoes t
      JOIN usuarios u
        ON u.id = t.user_id
      WHERE t.suspeita = 1
      GROUP BY u.banco
      ORDER BY qtd DESC
    """
    df_fraud_bank = pd.read_sql(SQL_FRAUD, conn)

    if df_fraud_bank.empty:
        st.info("Nenhuma fraude detectada.")
    else:
        # 2) KPI de quantos bancos foram afetados
        st.metric("Bancos afetados", df_fraud_bank["banco"].nunique())

        # 3) Gráfico de barras
        fig_fb = px.bar(
            df_fraud_bank,
            x="qtd",
            y="banco",
            orientation="h",
            text="qtd",
            labels={"qtd": "Qtd de fraudes", "banco": "Banco"},
            title="Quantidade de fraudes por banco",
            template="plotly_dark"
        )
        fig_fb.update_layout(
            yaxis_categoryorder="total ascending",
            margin=dict(l=120, r=40, t=50, b=40),
            height=400
        )
        fig_fb.update_traces(texttemplate="%{text}", textposition="outside")
        st.plotly_chart(fig_fb, use_container_width=True)

        # 4) (Opcional) mostrar tabela
        st.dataframe(df_fraud_bank.rename(columns={"qtd":"Qtd de fraudes"}), use_container_width=True)


# ════════════════════════════════════════
# 17) Tendências (Últimos N dias) — corrigido
# ════════════════════════════════════════
with st.expander("📈 Tendências (Últimos N dias)", expanded=False):

    col_per, col_met = st.columns(2)
    with col_per:
        n_dias = st.slider("Período (dias)", 7, 90, 30)
    with col_met:
        metricas = st.multiselect(
            "Indicadores",
            ["Total transações", "Volume (R$)",
             "Fraudes (qtd)", "Volume fraudado (R$)"],
            default=["Total transações", "Fraudes (qtd)"]
        )

    # recorte do dataframe
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=n_dias-1)
    df_per = df_tx[df_tx["data_hora"].dt.date >= cutoff.date()].copy()
    df_per["dia"] = df_per["data_hora"].dt.date       # nova coluna

    # agrega por dia COM apply (evita KeyError)
    daily = (
        df_per.groupby("dia")
              .apply(lambda g: pd.Series({
                  "total_tx" : g.shape[0],
                  "volume"   : g["valor"].sum(),
                  "fraud_qtd": g["suspeita"].sum(),
                  "fraud_vol": g.loc[g["suspeita"] == 1, "valor"].sum()
              }))
              .reset_index()
              .sort_values("dia")
    )

    # reshape longo
    map_cols = {
        "Total transações"     : "total_tx",
        "Volume (R$)"          : "volume",
        "Fraudes (qtd)"        : "fraud_qtd",
        "Volume fraudado (R$)" : "fraud_vol"
    }
    df_long = daily.melt(
        id_vars="dia",
        value_vars=[map_cols[m] for m in metricas],
        var_name="Métrica",
        value_name="valor"
    )
    df_long["Métrica"] = df_long["Métrica"].map({v: k for k, v in map_cols.items()})

    # gráfico
    fig_trend = px.line(
        df_long,
        x="dia", y="valor",
        color="Métrica", markers=True,
        labels={"dia": "Data", "valor": "Valor"},
        title=f"Tendência diária (últimos {n_dias} dias)"
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    # KPIs resumo
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Tx/dia (média)",   f"{daily['total_tx'].mean():,.0f}")
    k2.metric("Vol/dia (R$)",     f"{daily['volume'].mean():,.2f}")
    k3.metric("% fraudes",
              f"{(daily['fraud_qtd'].sum()/daily['total_tx'].sum()*100):.2f}%")
    k4.metric("Vol. fraudado (R$)",
              f"{daily['fraud_vol'].sum():,.2f}")
    
# ════════════════════════════════════════
# 18) 📍 Fraudes por Estado
# ════════════════════════════════════════
with st.expander("📍 Fraudes por Estado", expanded=False):

    # ── 18.1 Consulta de fraudes por estado ───────────────────
    SQL_EST = """
        SELECT
            COALESCE(u.estado,'(Ignorado)') AS estado,
            COUNT(*)                        AS qtd_fraudes
        FROM transacoes t
        JOIN usuarios u
          ON u.id = t.user_id
        WHERE t.suspeita = 1
        GROUP BY u.estado
        ORDER BY qtd_fraudes DESC
    """
    df_est = pd.read_sql(SQL_EST, conn)

    if df_est.empty:
        st.info("Nenhuma fraude detectada por estado.")
    else:
        # ── 18.2 Gráfico de barras horizontais ──────────────────
        fig_est = px.bar(
            df_est,
            x="qtd_fraudes",
            y="estado",
            orientation="h",
            text="qtd_fraudes",
            labels={"estado": "Estado", "qtd_fraudes": "Número de Fraudes"},
            title="Quantidade de Fraudes por Estado",
            template="plotly_dark"
        )
        fig_est.update_layout(
            yaxis=dict(autorange="reversed"),
            margin=dict(l=100, t=50, r=20, b=20),
            height=400
        )
        fig_est.update_traces(texttemplate="%{text}", textposition="outside")
        st.plotly_chart(fig_est, use_container_width=True, key="chart_fraudes_estado")

        # ── 18.3 Tabela resumida ────────────────────────────────
        st.dataframe(
            df_est.rename(columns={"qtd_fraudes": "Número de Fraudes"}),
            use_container_width=True
        )
