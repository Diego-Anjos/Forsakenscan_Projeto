# ========================================
# 02_Mestre.py – Área do Administrador
# ========================================
import streamlit as st
if not hasattr(st, "rerun"):
    st.rerun = st.experimental_rerun  # alias p/ versões antigas


import pandas as pd
import plotly.express as px
from datetime import datetime, date, timedelta
import numpy as np
from st_aggrid import GridOptionsBuilder, AgGrid, GridUpdateMode  # <-- Adicione esta linha
from io import BytesIO  # <-- Adicione esta linha

from db import get_conn, get_cursor
conn = get_conn()
cursor = get_cursor(dictionary=True)

st.set_page_config(page_title="Relatórios – Mestre", layout="wide")


# Adicione esta função no início do arquivo (após as importações, por exemplo)
def registrar_fato(acao, descricao, user_id=None, entidade=None):
    """Registra um fato no banco de dados"""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO fatos_usuarios 
            (user_id, acao, descricao, entidade, data_hora)
            VALUES (%s, %s, %s, %s, NOW())
        """, (user_id, acao, descricao, entidade))
        conn.commit()
        cursor.close()
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao registrar fato: {str(e)}")

# ── validação de acesso ──
if not (st.session_state.get("logged_in") and st.session_state.get("is_admin")):
    st.warning("Acesso restrito a administradores.")
    st.stop()

# ── KPIs no topo ──
st.title("🔒 Relatórios de Atividades dos Usuários")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Fatos do Sistema", pd.read_sql("SELECT COUNT(*) AS c FROM fatos_usuarios", conn)["c"][0])
c2.metric("Transações", pd.read_sql("SELECT COUNT(*) AS c FROM transacoes", conn)["c"][0])
c3.metric("Transações suspeitas", pd.read_sql("SELECT COUNT(*) AS c FROM transacoes WHERE suspeita=1", conn)["c"][0])
c4.metric("Usuários cadastrados", pd.read_sql("SELECT COUNT(*) AS c FROM usuarios", conn)["c"][0])

# Adicione esta nova aba na lista de abas existente (procure por "Adicionar a nova aba na lista de abas"):
aba_fatos, aba_tx, aba_fraude, aba_edit, aba_logs, aba_senhas, aba_padrao5, aba_cashin, aba_lavagem, aba_compras, aba_compras_baixo, aba_limites, aba_fluxo, aba_risco = st.tabs(
    ["🗂️ Fatos", "💵 Transações", "🚩 Fraudes", "📝 Edições", "🛂 Logins", "🔑 Senhas",
     "🔍 Padrão 5", "💰 Cash-In Sem Histórico", "💸 Lavagem de Dinheiro",
     "🛍️ Compras Iguais", "🧾 Compras de Baixo Valor", "🛑 Limites",
     "📈 Fluxo Anômalo",                # 👈  NOVO
     "⚠️ Contas de Risco"]
)

# ==== CONTROLE DE LIMITES ====
with aba_limites:
    st.header("🛑 Controle de Limites por Turno")
    
    # Seção 1: Configuração de Limites
    with st.expander("⚙️ Configurar Limites por Usuário"):
        col1, col2 = st.columns(2)
        with col1:
            user_id = st.number_input("ID do Usuário", min_value=1, key="limite_user_id")
            username = pd.read_sql(f"SELECT username FROM usuarios WHERE id = {user_id}", conn)["username"][0] if user_id else "N/A"
            st.write(f"Usuário: {username}")
        
        with col2:
            limite_dia = st.number_input("Limite Diurno (R$)", min_value=0.0, value=10000.0, step=100.0, key="limite_dia")
            limite_noite = st.number_input("Limite Noturno (R$)", min_value=0.0, value=5000.0, step=100.0, key="limite_noite")
        
        if st.button("Salvar Limites", key="salvar_limites"):
            # Corrigido: Criar cursor antes de usar
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO limites_usuario (user_id, limite_dia, limite_noite)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    limite_dia = VALUES(limite_dia),
                    limite_noite = VALUES(limite_noite)
                """, (user_id, limite_dia, limite_noite))
                conn.commit()
                st.success("Limites atualizados com sucesso!")
            except Exception as e:
                conn.rollback()
                st.error(f"Erro ao atualizar limites: {str(e)}")
            finally:
                cursor.close()
    
    # Seção 2: Visualização de Limites
    with st.expander("📊 Visualizar Todos os Limites"):
        df_limites = pd.read_sql("""
            SELECT u.id as user_id, u.username, 
                   COALESCE(l.limite_dia, 10000) as limite_dia,
                   COALESCE(l.limite_noite, 5000) as limite_noite
            FROM usuarios u
            LEFT JOIN limites_usuario l ON u.id = l.user_id
            ORDER BY u.username
        """, conn)
        st.dataframe(df_limites.style.format({
            'limite_dia': 'R$ {:.2f}',
            'limite_noite': 'R$ {:.2f}'
        }), use_container_width=True)
    
    # Seção 3: Tentativas de Exceder Limites
    with st.expander("🚨 Histórico de Tentativas de Exceder Limites"):
        df_tentativas = pd.read_sql("""
            SELECT t.id, t.user_id, u.username, 
                   t.valor_tentativa, t.limite, 
                   t.turno, DATE_FORMAT(t.data_hora, '%%d/%%m/%%Y %%H:%%i') as data_hora,
                   (t.valor_tentativa - t.limite) as excedente
            FROM tentativas_limite t
            JOIN usuarios u ON u.id = t.user_id
            ORDER BY t.data_hora DESC
            LIMIT 200
        """, conn)
        
        if not df_tentativas.empty:
            st.write(f"Total de tentativas: {len(df_tentativas)}")
            st.dataframe(df_tentativas.style.format({
                'valor_tentativa': 'R$ {:.2f}',
                'limite': 'R$ {:.2f}',
                'excedente': 'R$ {:.2f}'
            }), use_container_width=True)
            
            # Gráficos de análise
            tab1, tab2 = st.tabs(["Por Usuário", "Por Turno"])
            with tab1:
                fig_user = px.bar(df_tentativas['username'].value_counts().reset_index(),
                                 x='username', y='count',
                                 title='Tentativas por Usuário')
                st.plotly_chart(fig_user, use_container_width=True)
            
            with tab2:
                fig_turno = px.pie(df_tentativas, names='turno',
                                  title='Distribuição por Turno')
                st.plotly_chart(fig_turno, use_container_width=True)
        else:
            st.info("Nenhuma tentativa de exceder limites registrada")

# ==== FATOS ====
with aba_fatos:
    st.header("🗂️ Histórico Completo de Atividades")
    st.markdown("""
    **Registro de todas as ações realizadas no sistema:**  
    • Acompanhamento completo de atividades dos usuários  
    • Alterações, cadastros, exclusões e outras operações  
    """)
    
    df_fatos = pd.read_sql("""
        SELECT f.id,
               DATE_FORMAT(f.data_hora,'%d/%m/%Y %H:%i') AS data_hora,
               u.username, f.acao,
               COALESCE(f.entidade,'–') AS entidade,
               f.descricao
          FROM fatos_usuarios f
          JOIN usuarios u ON u.id = f.user_id
      ORDER BY f.id DESC
         LIMIT 1000
    """, conn)
    st.dataframe(df_fatos, use_container_width=True)

# ==== TRANSACOES ====
with aba_tx:
    st.header("💵 Todas as Transações Financeiras")
    st.markdown("""
    **Registro completo de movimentações financeiras:**  
    • Compras, transferências, pagamentos e outras operações  
    • Identificação de transações marcadas como suspeitas  
    """)
    
    df_tx = pd.read_sql("""
        SELECT t.id,
               DATE_FORMAT(t.data_hora,'%d/%m/%Y %H:%i') AS data_hora,
               u.username,
               t.tipo_transacao AS tipo,
               COALESCE(t.forma_pagamento,'–') AS forma,
               t.valor,
               IF(t.suspeita, '🚩','') AS flag
          FROM transacoes t
          JOIN usuarios u ON u.id = t.user_id
      ORDER BY t.id DESC
         LIMIT 1000
    """, conn)
    
    # Mini-gráfico de transações por tipo
    st.dataframe(df_tx, use_container_width=True)
    fig_tx = px.pie(df_tx, names='tipo', title='Distribuição por Tipo de Transação')
    st.plotly_chart(fig_tx, use_container_width=True)

# ==== FRAUDES ====
with aba_fraude:
    st.subheader("🚩 Transações marcadas como suspeitas")
    col_ini, col_fim = st.columns(2)
    ini = col_ini.date_input("De", date.today() - timedelta(days=30), key="fraude_ini_date")
    fim = col_fim.date_input("Até", date.today(), key="fraude_fim_date")
    
    df_fraud = pd.read_sql("""
        SELECT t.id,
               DATE_FORMAT(t.data_hora,'%d/%m/%Y %H:%i') AS data_hora,
               u.username,
               t.tipo_transacao AS tipo,
               t.valor,
               t.motivo_suspeita AS motivo
          FROM transacoes t
          JOIN usuarios u ON u.id = t.user_id
         WHERE t.suspeita = 1
           AND DATE(t.data_hora) BETWEEN %s AND %s
      ORDER BY t.id DESC
    """, conn, params=(ini, fim))
    
    st.write(f"➤ Encontradas {len(df_fraud)} transações suspeitas")
    st.dataframe(df_fraud, use_container_width=True)
    
    # Mini-gráficos de análise
    if not df_fraud.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig_tipo = px.pie(df_fraud, names='tipo', title='Tipos de Transações Suspeitas')
            st.plotly_chart(fig_tipo, use_container_width=True)
        with col2:
            fig_valor = px.histogram(df_fraud, x='valor', title='Distribuição de Valores')
            st.plotly_chart(fig_valor, use_container_width=True)

# ==== EDIÇÕES DE PERFIL ====
with aba_edit:
    st.subheader("📝 Histórico de Edições de Perfil")
    col1, col2 = st.columns(2)
    with col1:
        data_ini = st.date_input("De", date.today() - timedelta(days=30), key="edit_ini_date")
    with col2:
        data_fim = st.date_input("Até", date.today(), key="edit_fim_date")
    
    df_edit = pd.read_sql("""
        SELECT f.id,
               DATE_FORMAT(f.data_hora,'%d/%m/%Y %H:%i') AS data_hora,
               u.username,
               f.campo,
               f.valor_antigo AS de,
               f.valor_novo   AS para
          FROM fatos_usuarios f
          JOIN usuarios u ON u.id = f.user_id
         WHERE f.acao = 'editar_perfil'
           AND DATE(f.data_hora) BETWEEN %s AND %s
      ORDER BY f.id DESC
         LIMIT 500
    """, conn, params=(data_ini, data_fim))
    
    st.dataframe(df_edit, use_container_width=True)
    
    # Mini-gráfico de campos editados
    if not df_edit.empty:
        fig_campo = px.bar(df_edit['campo'].value_counts().reset_index(), 
                          x='campo', y='count', 
                          title='Campos Mais Editados')
        st.plotly_chart(fig_campo, use_container_width=True)

# ==== ALTERAÇÕES DE SENHA ====
with aba_senhas:
    st.subheader("🔑 Histórico de Alterações de Senha")
    col1, col2 = st.columns(2)
    with col1:
        senha_ini = st.date_input("De", date.today() - timedelta(days=30), key="senha_ini_date")
    with col2:
        senha_fim = st.date_input("Até", date.today(), key="senha_fim_date")
    
    df_senhas = pd.read_sql("""
        SELECT f.id,
               DATE_FORMAT(f.data_hora,'%d/%m/%Y %H:%i') AS data_hora,
               u.username,
               f.descricao
          FROM fatos_usuarios f
          JOIN usuarios u ON u.id = f.user_id
         WHERE f.acao = 'Alterar senha'
           AND DATE(f.data_hora) BETWEEN %s AND %s
      ORDER BY f.id DESC
         LIMIT 500
    """, conn, params=(senha_ini, senha_fim))
    
    st.dataframe(df_senhas, use_container_width=True)
    
    # Mini-gráfico de alterações por usuário
    if not df_senhas.empty:
        fig_senhas = px.bar(df_senhas['username'].value_counts().reset_index(),
                           x='username', y='count',
                           title='Alterações por Usuário')
        st.plotly_chart(fig_senhas, use_container_width=True)

# ==== LOGINS ====
with aba_logs:
    st.subheader("Tentativas de Login")
    col1, col2, col3 = st.columns(3)
    with col1:
        data_inicio = st.date_input("Data inicial", value=date.today() - timedelta(days=30), key="log_ini_date")
    with col2:
        data_fim = st.date_input("Data final", value=date.today(), key="log_fim_date")
    with col3:
        resultado = st.selectbox("Resultado", ["Todos", "Sucesso", "Falha"], key="log_result_select")
    
    query = """
        SELECT l.id,
               DATE_FORMAT(l.data_hora,'%d/%m/%Y %H:%i') AS data_hora,
               COALESCE(u.username,'–') AS usuario,
               l.resultado,
               l.ip,
               l.user_agent
          FROM logs l
     LEFT JOIN usuarios u ON u.id = l.user_id
         WHERE DATE(l.data_hora) BETWEEN %s AND %s
    """
    params = [data_inicio, data_fim]
    
    if resultado != "Todos":
        query += " AND l.resultado = %s"
        params.append("ok" if resultado == "Sucesso" else "fail")
    
    query += " ORDER BY l.id DESC LIMIT 1000"
    
    df_logs = pd.read_sql(query, conn, params=tuple(params))
    st.dataframe(df_logs, use_container_width=True)
    
    # Mini-gráfico de tentativas por resultado
    if not df_logs.empty:
        fig_logs = px.pie(df_logs, names='resultado', title='Resultado das Tentativas')
        st.plotly_chart(fig_logs, use_container_width=True)

# ==== PADRÃO 5: TROCA DE DADOS + PAGAMENTOS ====
# ==== PADRÃO 5: TROCA DE DADOS + PAGAMENTOS ====
# ==== PADRÃO 5: TROCA DE DADOS + PAGAMENTOS ====
# ==== PADRÃO 5: TROCA DE DADOS + PAGAMENTOS ====
with aba_padrao5:
    st.header("🔍 Padrão 5: Troca de Dados + Pagamentos")
    st.markdown(
        """
        **Esta análise identifica possível lavagem de dinheiro ou conta tomada**  
        quando um usuário altera dados sensíveis (e-mail / telefone) e, dentro de poucas horas, 
        realiza pagamentos ou transferências de valor. O objetivo é sinalizar contas que mudam 
        o canal de contato antes de movimentar dinheiro, um comportamento típico de fraude.
        """
    )

    # Consulta para obter todas as alterações de e-mail/telefone
    st.subheader("Todas as Alterações de Dados Sensíveis")
    alteracoes_sql = """
    SELECT 
        f.id,
        u.username,
        f.campo,
        f.acao,
        DATE_FORMAT(f.data_hora, '%d/%m/%Y %H:%i') as data_hora,
        f.valor_antigo,
        f.valor_novo
    FROM fatos_usuarios f
    JOIN usuarios u ON u.id = f.user_id
    WHERE f.acao = 'editar_perfil'
      AND (f.campo = 'email' OR f.campo = 'telefone')
    ORDER BY f.data_hora DESC
    LIMIT 1000
    """
    
    df_alteracoes = pd.read_sql(alteracoes_sql, conn)
    
    if not df_alteracoes.empty:
        st.dataframe(
            df_alteracoes.style.format({
                'data_hora': lambda x: str(x) if x else ''
            }),
            use_container_width=True,
            height=400
        )
        
        # Métricas das alterações
        col1, col2 = st.columns(2)
        col1.metric("Total de Alterações", len(df_alteracoes))
        col2.metric("Última Alteração", df_alteracoes['data_hora'].iloc[0])
    else:
        st.info("Nenhuma alteração de dados sensíveis encontrada")

    # Consulta principal para identificar o padrão
    st.subheader("Pagamentos Realizados Após Alteração de Dados")
    st.markdown("""
    **Lista de transações realizadas até 24 horas após alteração de e-mail/telefone:**
    """)

    padrao5_sql = """
    WITH ult_alt AS (
        SELECT 
            user_id,
            MAX(data_hora) AS alt_time
        FROM fatos_usuarios
        WHERE acao = 'editar_perfil'
          AND (campo = 'email' OR campo = 'telefone')
        GROUP BY user_id
    ),
    pay AS (
        SELECT 
            user_id, 
            data_hora, 
            valor, 
            tipo_transacao,
            forma_pagamento,
            banco
        FROM transacoes
        WHERE tipo_transacao IN ('SAQUE', 'TRANSFERENCIA', 'PAGAMENTO', 'TED', 'DOC', 'PIX')
    )
    SELECT 
        u.username AS usuario,
        u.banco,
        DATE_FORMAT(a.alt_time, '%d/%m/%Y %H:%i') AS alteracao,
        DATE_FORMAT(p.data_hora, '%d/%m/%Y %H:%i') AS pagamento,
        p.tipo_transacao AS tipo,
        p.forma_pagamento AS forma,
        p.valor,
        TIMESTAMPDIFF(HOUR, a.alt_time, p.data_hora) AS horas_apos_alteracao
    FROM ult_alt a
    JOIN pay p ON p.user_id = a.user_id
    JOIN usuarios u ON u.id = a.user_id
    WHERE p.data_hora > a.alt_time
      AND TIMESTAMPDIFF(HOUR, a.alt_time, p.data_hora) <= 24
    ORDER BY p.data_hora DESC
    LIMIT 1000
    """

    df_padrao5 = pd.read_sql(padrao5_sql, conn)

    if not df_padrao5.empty:
        # Métricas detalhadas de valores
        st.markdown("### Resumo Financeiro")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total de Casos", len(df_padrao5))
        col2.metric("Valor Total", f"R$ {df_padrao5['valor'].sum():,.2f}")
        col3.metric("Valor Médio", f"R$ {df_padrao5['valor'].mean():,.2f}")
        col4.metric("Tempo Médio", f"{df_padrao5['horas_apos_alteracao'].mean():.1f} horas")
        
        # Top 5 maiores valores
        st.markdown("### Top 5 Maiores Valores")
        top5 = df_padrao5.nlargest(5, 'valor')[['usuario', 'banco', 'valor', 'tipo', 'horas_apos_alteracao']]
        st.dataframe(
            top5.style.format({
                'valor': 'R$ {:.2f}',
                'horas_apos_alteracao': '{:.1f} horas'
            }),
            use_container_width=True
        )

        # Botão de exportação
        csv = df_padrao5.to_csv(index=False).encode('utf-8')
        st.download_button(
            "⬇️ Exportar CSV",
            csv,
            file_name=f"padrao5_troca_dados_pagamentos_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.success("✅ Nenhum caso de pagamento após alteração de dados encontrado")

# ==== REGRA 6: CASH-IN SEM HISTÓRICO ====
with aba_cashin:
    st.header("💰 Regra 6: Cash-In Sem Histórico")
    st.markdown("""
    **Detecta transações de entrada de dinheiro (Cash-In) em contas:**  
    1. Sem transações anteriores nos últimos 7 dias  
    2. Com valores acima de R$ 5.000  
    """)
    
    # Filtros
    col1, col2 = st.columns(2)
    with col1:
        cashin_ini = st.date_input("Data inicial", date.today() - timedelta(days=30), key="cashin_ini_date")
    with col2:
        cashin_fim = st.date_input("Data final", date.today(), key="cashin_fim_date")
    
    min_valor = st.number_input("Valor mínimo (R$)", min_value=5000, value=5000, step=1000, key="cashin_min_valor")
    
    if st.button("Analisar Cash-In Suspeitos", key="cashin_analisar_btn"):
        query = """
        SELECT 
            t.id,
            t.data_hora,
            u.username,
            u.banco,
            t.valor,
            (SELECT COUNT(*) 
             FROM transacoes t_ant 
             WHERE t_ant.user_id = t.user_id 
               AND t_ant.data_hora < t.data_hora
               AND t_ant.data_hora >= DATE_SUB(t.data_hora, INTERVAL 7 DAY)) AS transacoes_anteriores
        FROM transacoes t
        JOIN usuarios u ON u.id = t.user_id
        WHERE t.tipo_transacao = 'Cash-In'
          AND DATE(t.data_hora) BETWEEN %s AND %s
          AND t.valor >= %s
          AND NOT EXISTS (
              SELECT 1 
              FROM transacoes t_ant 
              WHERE t_ant.user_id = t.user_id
                AND t_ant.data_hora < t.data_hora
                AND t_ant.data_hora >= DATE_SUB(t.data_hora, INTERVAL 7 DAY)
          )
        ORDER BY t.valor DESC
        """
        
        params = (cashin_ini, cashin_fim, min_valor)
        
        try:
            df_cashin = pd.read_sql(query, conn, params=params)
            
            if not df_cashin.empty:
                # Converter a coluna data_hora para datetime
                df_cashin['data_hora'] = pd.to_datetime(df_cashin['data_hora'])
                
                st.success(f"✅ {len(df_cashin)} transações suspeitas encontradas")
                
                # Métricas rápidas
                col1, col2, col3 = st.columns(3)
                col1.metric("Total de Casos", len(df_cashin))
                col2.metric("Maior Valor", f"R$ {df_cashin['valor'].max():,.2f}")
                col3.metric("Média de Valor", f"R$ {df_cashin['valor'].mean():,.2f}")
                
                # Dados detalhados
                st.dataframe(
                    df_cashin.style.format({
                        'valor': 'R$ {:.2f}',
                        'transacoes_anteriores': '{:,}',
                        'data_hora': lambda x: x.strftime('%d/%m/%Y %H:%M') if not pd.isnull(x) else ''
                    }),
                    use_container_width=True
                )
                
                # Mini-gráficos de análise
                tab1, tab2 = st.tabs(["Por Banco", "Distribuição de Valores"])
                
                with tab1:
                    fig_banco = px.bar(df_cashin['banco'].value_counts().reset_index(),
                                      x='banco', y='count',
                                      title='Cash-In Suspeitos por Banco')
                    st.plotly_chart(fig_banco, use_container_width=True)
                
                with tab2:
                    fig_valores = px.histogram(df_cashin, x='valor',
                                             title='Distribuição de Valores',
                                             nbins=20)
                    st.plotly_chart(fig_valores, use_container_width=True)
                
                # Exportar dados
                csv = df_cashin.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Exportar CSV",
                    csv,
                    file_name=f"cashin_suspeito_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key="cashin_export_btn"
                )
            else:
                st.info("Nenhuma transação de Cash-In suspeita encontrada")
                
        except Exception as e:
            st.error(f"Erro na consulta: {str(e)}")
            st.text("Consulta SQL executada:")
            st.code(query)
            st.text("Parâmetros utilizados:")
            st.code(params)

# ==== REGRA LAVAGEM DE DINHEIRO - DEPÓSITOS E RETIRADAS IMEDIATAS ====
# ───────────────────────────────────────────────────────────────
# Aba: Lavagem de Dinheiro – Entradas e Saídas Imediatas
# ───────────────────────────────────────────────────────────────
# ==== REGRA LAVAGEM DE DINHEIRO - DEPÓSITOS E RETIRADAS IMEDIATAS ====
with aba_lavagem:
    st.header("💸 Lavagem de Dinheiro – Entradas e Saídas Imediatas")
    st.markdown("""
    São exibidos todos os pares de entrada (Recebimento / Cash-In)  
    e saída (Cash-Out, Transferência, Saque) ocorrendo em até 5 minutos  
    entre as transações, sem filtro de valor.  
    """)

    # ── Consulta SQL corrigida ─────────────────────────────────────────────
    sql_lav = """
        SELECT
            t_in.user_id,
            u.cpf                             AS cpf,
            t_in.data_hora     AS entrada,
            t_in.valor         AS val_in,
            t_out.data_hora    AS saida,
            t_out.valor        AS val_out,
            TIMESTAMPDIFF(SECOND, t_in.data_hora, t_out.data_hora)/60.0 AS dif_min
        FROM transacoes t_in
        JOIN transacoes t_out
          ON t_out.user_id   = t_in.user_id
         AND t_out.data_hora  >  t_in.data_hora
         AND t_out.data_hora <= t_in.data_hora + INTERVAL 5 MINUTE
        JOIN usuarios u
          ON u.id = t_in.user_id
        WHERE t_in.tipo_transacao  IN ('Recebimento','Cash-In')
          AND t_out.tipo_transacao IN (
              'Cash-Out',  -- seu filtro original
              'Saída',     -- acrescentado para pegar as simulações
              'Transferência',
              'Saque'
          )
        ORDER BY t_in.data_hora
    """
    df_lav = pd.read_sql(sql_lav, conn, parse_dates=["entrada","saida"])

    df_lav = pd.read_sql(sql_lav, conn, parse_dates=["entrada", "saida"])

    # ── Exibição da tabela completa ────────────────────────────
    if df_lav.empty:
        st.info("✅ Nenhum par suspeito encontrado.")
    else:
        df_tbl = (
            df_lav
            .assign(
                entrada=lambda d: d["entrada"].dt.strftime("%d/%m/%Y %H:%M:%S"),
                saida  =lambda d: d["saida"].dt.strftime("%d/%m/%Y %H:%M:%S"),
            )
            .rename(columns={
                "cpf":     "CPF",
                "val_in":  "Valor Entrada (R$)",
                "val_out": "Valor Saída (R$)",
                "dif_min": "Intervalo (min)"
            })
        )
        st.subheader(f"Pares suspeitos encontrados: {len(df_tbl)}")
        st.dataframe(df_tbl, use_container_width=True)

        st.markdown("---")

        # ── Gráfico de dispersão (intervalo × valor de saída) ───────
        fig_scatter = px.scatter(
            df_lav,
            x="dif_min",
            y="val_out",
            color="cpf",
            size="val_out",
            hover_data=["entrada", "saida"],
            labels={
                "dif_min": "Intervalo (min)",
                "val_out": "Valor Saída (R$)",
                "cpf":     "CPF",
            },
            title="Intervalo entre Entrada → Saída vs Valor de Saída",
            template="plotly_dark",
        )
        fig_scatter.update_layout(height=350, margin=dict(t=40, b=20))
        st.plotly_chart(fig_scatter, use_container_width=True, key="mestre_lav_scatter")

        st.markdown("---")

        # ── Top N CPFs por soma de Saída ───────────────────────────
        df_top = (
            df_lav
            .groupby("cpf", as_index=False)["val_out"]
            .sum()
            .rename(columns={"val_out": "Total Saída (R$)"})
            .sort_values("Total Saída (R$)", ascending=False)
        )
        max_users = st.slider(
            "Exibir top N CPFs no gráfico",
            min_value=1,
            max_value=len(df_top),
            value=min(10, len(df_top)),
            step=1,
            key="mestre_lav_top_n",
        )
        df_plot = df_top.head(max_users)

        fig_bar = px.bar(
            df_plot,
            x="Total Saída (R$)",
            y="cpf",
            orientation="h",
            text="Total Saída (R$)",
            labels={"cpf": "CPF"},
            title=f"Top {max_users} CPFs por Total de Saída",
            template="plotly_dark",
        )
        fig_bar.update_traces(texttemplate="R$ %{text:,.2f}", textposition="outside")
        fig_bar.update_layout(
            yaxis_categoryorder="total ascending",
            height=30 * max_users + 150,
            margin=dict(l=120, r=20, t=50, b=20),
        )
        st.plotly_chart(fig_bar, use_container_width=True, key="mestre_lav_bar")

        # ── Download dos dados completos ───────────────────────────
        csv = df_lav.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Exportar pares como CSV",
            csv,
            file_name="lavagem_pares.csv",
            mime="text/csv",
            key="mestre_lav_export",
        )


# ==== REGRA DE COMPRAS SUSPEITAS ====
with aba_compras:
    st.header("🛍️ Regra: Compras Iguais em Curto Período")
    st.markdown("""
    Esta visualização mostra **todas as compras repetidas por valor, loja e forma de pagamento**,  
    realizadas por um mesmo usuário, sem aplicar filtros de tempo ou quantidade mínima.
    """)

    try:
        query = """
        SELECT 
            t.user_id,
            u.username,
            u.banco,
            t.forma_pagamento,
            t.valor,
            COUNT(*) as total_compras,
            MIN(t.data_hora) as primeira_compra,
            MAX(t.data_hora) as ultima_compra,
            TIMESTAMPDIFF(MINUTE, MIN(t.data_hora), MAX(t.data_hora)) as minutos_entre,
            GROUP_CONCAT(t.id SEPARATOR ', ') as ids_transacoes
        FROM transacoes t
        JOIN usuarios u ON u.id = t.user_id
        WHERE t.tipo_transacao = 'Compra'
        GROUP BY t.user_id, t.forma_pagamento, t.valor
        HAVING COUNT(*) > 1
        ORDER BY total_compras DESC, minutos_entre ASC
        """

        df_compras = pd.read_sql(query, conn)

        if not df_compras.empty:
            df_compras['primeira_compra'] = pd.to_datetime(df_compras['primeira_compra'])
            df_compras['ultima_compra']   = pd.to_datetime(df_compras['ultima_compra'])

            st.success(f"Total de padrões de compras repetidas: {len(df_compras)}")

            st.dataframe(
                df_compras.style.format({
                    'valor': 'R$ {:.2f}',
                    'minutos_entre': '{:.1f} min',
                    'primeira_compra': lambda x: x.strftime('%d/%m/%Y %H:%M'),
                    'ultima_compra': lambda x: x.strftime('%d/%m/%Y %H:%M')
                }),
                use_container_width=True
            )

            # Botão exportação
            csv = df_compras.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Exportar CSV",
                               csv,
                               file_name="compras_repetidas.csv",
                               mime="text/csv")

        else:
            st.info("Nenhum padrão de compras repetidas encontrado.")

    except Exception as e:
        st.error(f"Erro ao buscar dados: {str(e)}")


# ==== REGRA: TRANSAÇÕES DE BAIXO VALOR (INCLUINDO PIX) ====
# ==== REGRA: TRANSAÇÕES DE BAIXO VALOR (INCLUINDO PIX) ====
# ==== REGRA: TRANSAÇÕES DE BAIXO VALOR (INCLUINDO PIX) ====
with aba_compras_baixo:
    st.header("🧾 Regra: Tentativas de simulação com valores mínimos")
    st.markdown("""
    Esta visualização mostra **todas as transações com valor entre R$ 0,01 e R$ 1,00**, sem aplicar filtros.  
    Os dados já estão disponíveis no sistema e são exibidos para análise completa.
    """)

    try:
        query = """
        SELECT 
            t.id,
            t.user_id,
            u.username,
            t.tipo_transacao,
            t.valor,
            t.data_hora,
            t.forma_pagamento,
            t.banco,
            t.motivo_suspeita
        FROM transacoes t
        JOIN usuarios u ON u.id = t.user_id
        WHERE t.valor BETWEEN 0.01 AND 1.00
        ORDER BY t.data_hora DESC
        """

        df_baixo_valor = pd.read_sql(query, conn)

        if df_baixo_valor.empty:
            st.info("Nenhuma transação de baixo valor encontrada.")
        else:
            df_baixo_valor['data_hora'] = pd.to_datetime(df_baixo_valor['data_hora'])

            st.success(f"Total de transações encontradas: {len(df_baixo_valor)}")
            st.dataframe(
                df_baixo_valor.style.format({
                    'valor': 'R$ {:.2f}',
                    'data_hora': lambda x: x.strftime('%d/%m/%Y %H:%M')
                }),
                use_container_width=True
            )

            csv = df_baixo_valor.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Exportar CSV", csv, file_name="transacoes_baixo_valor.csv", mime="text/csv")

    except Exception as e:
        st.error(f"Erro ao buscar dados: {str(e)}")


# ==== FLUXO ANÔMALO – Entradas × Saídas ============================
with aba_fluxo:
    st.header("📈 Fluxo Anômalo de Gastos")
    st.markdown("""
    **O que esta aba faz?**  
    • Calcula, por usuário, o total de **saídas** (gastos) e **entradas** em um período selecionado.  
    • Compara o total de saídas deste período com as saídas do **período anterior** de mesmo tamanho.  
    • Se o usuário gastar **≥ 2 ×** o total do período anterior, gera um alerta.  
    """)

    col1, col2 = st.columns(2)
    with col1:
        ini = st.date_input("Data inicial", date.today() - timedelta(days=30), key="fluxo_ini")
    with col2:
        fim = st.date_input("Data final", date.today(), key="fluxo_fim")

    dias          = (fim - ini).days + 1
    prev_ini      = ini - timedelta(days=dias)
    prev_fim      = ini - timedelta(days=1)

    if st.button("Analisar Fluxo", key="btn_fluxo"):
        # --- consulta SQL consolidada ---
        query = """
        WITH saidas_atual AS (
            SELECT user_id,
                   SUM(valor) AS saidas_atual
            FROM transacoes
            WHERE tipo_transacao IN ('Compra','Pagamento','Transferência','Saque')
              AND DATE(data_hora) BETWEEN %s AND %s
            GROUP BY user_id
        ),
        saidas_prev AS (
            SELECT user_id,
                   SUM(valor) AS saidas_prev
            FROM transacoes
            WHERE tipo_transacao IN ('Compra','Pagamento','Transferência','Saque')
              AND DATE(data_hora) BETWEEN %s AND %s
            GROUP BY user_id
        ),
        entradas AS (
            SELECT user_id,
                   SUM(valor) AS entradas_atual
            FROM transacoes
            WHERE tipo_transacao IN ('Recebimento','Cash-In')
              AND DATE(data_hora) BETWEEN %s AND %s
            GROUP BY user_id
        )
        SELECT u.id               AS user_id,
               u.username,
               u.banco,
               COALESCE(e.entradas_atual,0)        AS entradas,
               COALESCE(sa.saidas_atual,0)         AS saidas,
               COALESCE(sp.saidas_prev,0)          AS saidas_prev,
               CASE 
                   WHEN COALESCE(sp.saidas_prev,0)=0 AND COALESCE(sa.saidas_atual,0)>0
                        THEN 9999         -- evita divisão por zero
                   WHEN COALESCE(sp.saidas_prev,0)=0 THEN 0
                   ELSE COALESCE(sa.saidas_atual,0)/sp.saidas_prev
               END                                 AS razao
        FROM usuarios u
        LEFT JOIN saidas_atual sa ON sa.user_id = u.id
        LEFT JOIN saidas_prev sp  ON sp.user_id = u.id
        LEFT JOIN entradas e      ON e.user_id  = u.id
        HAVING razao >= 2
        ORDER BY razao DESC
        """
        params = (ini, fim, prev_ini, prev_fim, ini, fim)

        try:
            df_fluxo = pd.read_sql(query, conn, params=params)

            if df_fluxo.empty:
                st.success("✅ Nenhum alerta de fluxo encontrado.")
            else:
                st.success(f"🚨 {len(df_fluxo)} usuários com gasto ≥ 2× o período anterior")

                st.dataframe(
                    df_fluxo.style.format({
                        'entradas'   : 'R$ {:.2f}',
                        'saidas'     : 'R$ {:.2f}',
                        'saidas_prev': 'R$ {:.2f}',
                        'razao'      : '{:.2f}×'
                    }),
                    use_container_width=True
                )

                # gráfico rápido
                import plotly.express as px
                fig = px.bar(df_fluxo, x='username', y='razao',
                             color='razao',
                             color_continuous_scale='RdYlGn_r',
                             title='Razão de Saída Atual ÷ Saída Anterior')
                st.plotly_chart(fig, use_container_width=True)

                # download
                csv = df_fluxo.to_csv(index=False).encode('utf-8')
                st.download_button("⬇️ Exportar CSV",
                                   csv,
                                   file_name=f"fluxo_anomalo_{datetime.now():%Y%m%d_%H%M%S}.csv",
                                   mime="text/csv")
        except Exception as e:
            st.error(f"Erro na análise: {e}")


# ==== CONTAS DE RISCO ========================================================================
with aba_risco:
    st.header("⚠️ Contas com Alto Risco de Fraude")
    st.markdown("""
    Lista consolidada dos usuários com maior incidência de violações.  
    Use os botões para **Bloquear / Desbloquear / Encerrar** a conta  
    (todas as ações ficam registradas em *historico_bloqueios* e *fatos_usuarios*).
    """)

    # 1) Consulta consolidada ----------------------------------------------------------
    sql_risco = """
    WITH fraudes AS (
        SELECT user_id, COUNT(*) AS qtd_fraudes, SUM(valor) AS valor_fraudes
        FROM transacoes
        WHERE suspeita = 1
        GROUP BY user_id
    ),
    tentativas AS (
        SELECT user_id, COUNT(*) AS tentativas_limite
        FROM tentativas_limite
        GROUP BY user_id
    ),
    hist AS (
        SELECT user_id,
               SUM(acao='BLOQUEIO')     AS bloqueios,
               SUM(acao='DESBLOQUEIO')  AS desbloqueios
        FROM historico_bloqueios
        GROUP BY user_id
    )
    SELECT u.id                AS user_id,
           u.username, u.nome, u.banco, u.cidade, u.estado,
           COALESCE(f.qtd_fraudes, 0)        AS fraudes,
           COALESCE(f.valor_fraudes, 0)      AS valor_fraudes,
           COALESCE(t.tentativas_limite, 0)  AS tentativas_limite,
           COALESCE(h.bloqueios, 0)          AS bloqueios,
           COALESCE(h.desbloqueios, 0)       AS desbloqueios,
           u.conta_bloqueada,
           u.saldo_pendente
    FROM usuarios u
    LEFT JOIN fraudes     f ON f.user_id = u.id
    LEFT JOIN tentativas  t ON t.user_id = u.id
    LEFT JOIN hist        h ON h.user_id = u.id
    WHERE f.qtd_fraudes IS NOT NULL
       OR t.tentativas_limite IS NOT NULL
       OR u.saldo_pendente IS NOT NULL
    ORDER BY f.qtd_fraudes DESC, t.tentativas_limite DESC
    LIMIT 50;
    """

    df_risco = pd.read_sql(sql_risco, conn)

    if df_risco.empty:
        st.warning("Nenhuma conta de risco foi identificada.")
        st.stop()

    st.dataframe(df_risco, use_container_width=True)

    st.download_button("📥 Exportar CSV",
                       df_risco.to_csv(index=False).encode("utf-8"),
                       file_name="contas_risco.csv",
                       mime="text/csv")

    st.markdown("---")
    st.subheader("🔧 Ações Administrativas")

    # 2) Ações linha a linha ------------------------------------------------------------
    for _, row in df_risco.iterrows():
        col1, col2, col3, _ = st.columns([4, 1, 1, 0.5])

        with col1:
            st.write(
                f"**{row.nome or row.username}** `({row.user_id})` • "
                f"{row.cidade}/{row.estado} | "
                f"Fraudes: **{row.fraudes}** | "
                f"Limite: **{row.tentativas_limite}** | "
                f"Saldo pendente: **R$ {row.saldo_pendente or 0:,.2f}**"
            )

        with col2:
            if row.conta_bloqueada:
                if st.button("🔓 Desbloq.", key=f"unblock_{row.user_id}"):
                    cursor.execute(
                        "UPDATE usuarios SET conta_bloqueada = 0 WHERE id = %s",
                        (row.user_id,)
                    )
                    cursor.execute(
                        "INSERT INTO historico_bloqueios (user_id, acao, motivo) VALUES (%s, 'DESBLOQUEIO', 'Revisão administrativa')",
                        (row.user_id,)
                    )
                    conn.commit()
                    st.success("Usuário desbloqueado.")
                    st.rerun()
            else:
                if st.button("🔒 Bloquear", key=f"block_{row.user_id}"):
                    cursor.execute(
                        "UPDATE usuarios SET conta_bloqueada = 1 WHERE id = %s",
                        (row.user_id,)
                    )
                    cursor.execute(
                        "INSERT INTO historico_bloqueios (user_id, acao, motivo) VALUES (%s, 'BLOQUEIO', 'Alto risco detectado')",
                        (row.user_id,)
                    )
                    conn.commit()
                    st.warning("Usuário bloqueado.")
                    st.rerun()

        with col3:
            if st.button("🚫 Encerrar", key=f"close_{row.user_id}"):
                saldo = row.saldo_pendente or 0

                if saldo > 0:
                    st.warning(
                        f"Conta NÃO encerrada: saldo pendente de R$ {saldo:,.2f}. "
                        "O time responsável irá analisar a destinação dos valores."
                    )
                    cursor.execute(
                        """
                        INSERT INTO fatos_usuarios
                              (user_id, acao, descricao, data_hora)
                        VALUES (%s,
                                'Encerrar – saldo pendente',
                                'Encerramento impedido por saldo pendente',
                                NOW())
                        """,
                        (row.user_id,)
                    )
                    conn.commit()
                else:
                    cursor.execute(
                        """
                        UPDATE usuarios
                           SET ativo             = 0,
                               motivo_inativacao = 'Encerrada pela área de risco (fraudes)',
                               data_inativacao   = NOW()
                         WHERE id = %s
                        """,
                        (row.user_id,)
                    )
                    conn.commit()
                    st.success("Conta encerrada definitivamente (saldo zerado).")
                    st.rerun()
