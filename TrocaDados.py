import streamlit as st
if not hasattr(st, "rerun"):
    st.rerun = st.experimental_rerun  # alias p/ versões antigas


from datetime import datetime
import sqlite3  # ou importe sua conexão do db.py

# Configurações iniciais
st.set_page_config(page_title="Troca de Dados Sensíveis", page_icon="🔒")

# Conexão com o banco (ajuste conforme seu projeto)
def get_connection():
    return sqlite3.connect('seu_banco.db')  # ou use sua conexão existente

# Função para registrar auditoria (CORRIGIDA)
def registrar_auditoria(tipo_acao, detalhes, usuario_id):
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO auditoria 
            (tipo_operacao, detalhes, usuario_id, data_hora) 
            VALUES (?, ?, ?, ?)""",
            (tipo_acao, str(detalhes), usuario_id, datetime.now())
        )
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        st.error(f"Erro ao registrar auditoria: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()

# Seção 1: Atualização de Dados Sensíveis (CORRIGIDA)
def atualizar_dados_sensiveis():
    st.header("🔐 Atualização de Dados Sensíveis")
    
    with st.form("form_dados"):
        novo_email = st.text_input("Novo E-mail", type="default")
        novo_telefone = st.text_input("Novo Telefone", max_chars=15)
        
        if st.form_submit_button("Atualizar Dados"):
            if novo_email or novo_telefone:
                try:
                    registrar_auditoria(
                        "ATUALIZACAO_DADOS",
                        f"Email: {novo_email}, Telefone: {novo_telefone}",
                        st.session_state.get('usuario_id')
                    )
                    st.success("Dados atualizados com sucesso!")
                except Exception as e:
                    st.error(f"Erro na atualização: {str(e)}")
            else:
                st.warning("Por favor, preencha pelo menos um campo")

# Seção 2: Operação de Saque (CORRIGIDA)
def realizar_saque():
    st.header("💸 Operação de Saque")
    
    with st.form("form_saque"):
        valor = st.number_input("Valor", min_value=0.01, format="%.2f")
        conta_destino = st.selectbox("Conta Destino", ["Conta Corrente", "Poupança", "Outra"])
        submit = st.form_submit_button("Confirmar Saque")
        
        if submit:
            try:
                registrar_auditoria(
                    "SAQUE",
                    f"Valor: R$ {valor:.2f} | Destino: {conta_destino}",
                    st.session_state.get('usuario_id')
                )
                
                st.success(f"Saque de R$ {valor:.2f} realizado!")
                st.markdown(f"""
                **Comprovante Digital**  
                **Código:** {datetime.now().strftime("%Y%m%d%H%M%S")}  
                **Valor:** R$ {valor:.2f}  
                **Conta Destino:** {conta_destino}  
                **Data/Hora:** {datetime.now().strftime("%d/%m/%Y %H:%M")}  
                **Status:** Concluído
                """)
            except Exception as e:
                st.error(f"Falha no saque: {str(e)}")

# Seção 3: Logout Seguro (CORRIGIDA)
def logout():
    st.header("🚪 Encerramento de Sessão")
    
    if st.button("🔒 Sair do Sistema"):
        try:
            registrar_auditoria(
                "LOGOUT",
                "Usuário saiu do sistema",
                st.session_state.get('usuario_id')
            )
            
            # Limpeza da sessão
            for key in list(st.session_state.keys()):
                del st.session_state[key]
                
            st.success("Sessão encerrada com sucesso!")
            st.balloons()
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao encerrar sessão: {str(e)}")

# Layout Principal
def main():
    tab1, tab2, tab3 = st.tabs([
        "📧 Dados Sensíveis", 
        "💰 Saque", 
        "🔒 Sair"
    ])
    
    with tab1:
        atualizar_dados_sensiveis()
    
    with tab2:
        realizar_saque()
    
    with tab3:
        logout()

if __name__ == "__main__":
    # Verificação de segurança (simulação - substitua pela sua lógica real)
    if 'usuario_id' not in st.session_state:
        st.error("Acesso não autorizado! Redirecionando para login...")
        st.stop()
    
    main()