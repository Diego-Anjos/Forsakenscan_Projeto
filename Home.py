# ========================================
# home.py – Login, Cadastro e Recuperação
# ========================================
import os
import re
import secrets
import string
from datetime import date
from pathlib import Path

import streamlit as st

from db import get_conn, get_cursor

# ────────────────────────────────────────
# Configuração da página
# ────────────────────────────────────────
st.set_page_config(page_title="Autenticação", layout="centered")

# ────────────────────────────────────────
# Caminho do logo e exibição
# ────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
LOGO_PATH = PROJECT_ROOT / "Logo" / "Logo de ForsakenScan com Olho.png"

if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), use_container_width=True)
else:
    st.warning(f"Logo não encontrado em: {LOGO_PATH}")

st.markdown("<h1 style='text-align:center;'>FORSAKENSCAN</h1>", unsafe_allow_html=True)

# ────────────────────────────────────────
# Conexão resiliente
# ────────────────────────────────────────
conn = get_conn()
cursor = get_cursor(dictionary=True)

# ────────────────────────────────────────
# Estado padrão da sessão
# ────────────────────────────────────────
_DEFAULTS = dict(
    logged_in=False,
    user_id=None,
    username=None,
    name=None,
    email=None,
    is_admin=False,
)
for k, v in _DEFAULTS.items():
    st.session_state.setdefault(k, v)

# ────────────────────────────────────────
# Utilidades
# ────────────────────────────────────────
only_digits = lambda x: re.sub(r"\D", "", x or "")


def gerar_senha_tmp(n: int = 8) -> str:
    alfa = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alfa) for _ in range(n))


def registrar_login(
    uid: int | None, username: str | None, is_admin: bool, ok: bool
) -> None:
    """
    Registra cada tentativa de login na tabela **logs**.
    - uid: id na tabela `usuarios`
    - username: texto digitado
    - is_admin: tentativa de administrador?
    - ok: sucesso/fracasso
    """
    ip, ua = None, None
    try:
        ip = os.environ.get("REMOTE_ADDR")
        ua = st.request.headers.get("user-agent")  # type: ignore[attr-defined]
    except Exception:
        pass

    cur = get_cursor()
    cur.execute(
        """
        INSERT INTO logs (user_id, usuario, admin_user, resultado, ip, user_agent)
                   VALUES (%s,       %s,      %s,        %s,        %s, %s)
        """,
        (
            uid,
            None if is_admin else username,
            username if is_admin else None,
            "ok" if ok else "fail",
            ip,
            ua,
        ),
    )
    get_conn().commit()


# ────────────────────────────────────────
# JS – máscaras (IMask)
# ────────────────────────────────────────
import streamlit.components.v1 as components

components.html(
    """
    <script src="https://unpkg.com/imask"></script>
    <script>
      window.addEventListener('load',()=>{
        const M={cpf:'000.000.000-00',rg:'00.000.000-0',
                 t11:'(00) 00000-0000',t10:'(00) 0000-0000'};
        document.querySelectorAll('input[id^="cpf"],input[id^="rg"],input[id^="tel"]')
          .forEach(i=>{
            if(i.id.startsWith('cpf')) IMask(i,{mask:M.cpf});
            if(i.id.startsWith('rg'))  IMask(i,{mask:M.rg});
            if(i.id.startsWith('tel')) IMask(i,{mask:[M.t11,M.t10]});
          });
      });
    </script>
    """,
    height=0,
)

# ────────────────────────────────────────
# Menu lateral
# ────────────────────────────────────────
opcao = st.sidebar.radio(
    "Navegar",
    ("Login", "Cadastro", "Esqueci minha senha"),
    key="menu_auth",
)

# Add logout button if user is logged in
if st.session_state.logged_in:
    if st.sidebar.button("Deslogar da conta"):
        st.session_state.update(**_DEFAULTS)
        st.success("Você foi deslogado com sucesso!")
        st.rerun()
        
# ════════════════════════════════════════
# 1) LOGIN
# ════════════════════════════════════════
if opcao == "Login":
    st.title("Entrar no Sistema")

    with st.form(key="frm_login"):
        ident = st.text_input("CPF, e-mail ou usuário")
        senha = st.text_input("Senha", type="password")
        ok_btn = st.form_submit_button("Entrar")

    if ok_btn:
        cur = get_cursor(dictionary=True)
        user, origem = None, None

        # Tentativa em `usuarios`
        cur.execute(
            """
            SELECT id,nome,email,username,senha,conta_bloqueada
              FROM usuarios
             WHERE username=%s OR email=%s OR cpf=%s
             LIMIT 1
            """,
            (ident, ident, only_digits(ident)),
        )
        user = cur.fetchone()
        origem = "usuarios" if user else None

        # Tentativa em `administradores`
        if not user:
            cur.execute(
                """
                SELECT id,nome,email,username,senha
                  FROM administradores
                 WHERE username=%s OR email=%s
                 LIMIT 1
                """,
                (ident, ident),
            )
            user = cur.fetchone()
            origem = "administradores" if user else None

        # Falha geral
        if not user or senha != user["senha"]:
            st.error("Credenciais inválidas.")
            registrar_login(
                uid=user["id"] if user else None,
                username=ident,
                is_admin=(origem == "administradores"),
                ok=False,
            )
            st.stop()

        # Conta bloqueada
        if origem == "usuarios" and user.get("conta_bloqueada"):
            st.error("Seu cadastro está bloqueado.")
            registrar_login(user["id"], ident, False, False)
            st.stop()

        # Sucesso
        st.session_state.update(
            logged_in=True,
            user_id=user["id"] if origem == "usuarios" else None,
            username=user["username"],
            name=user["nome"],
            email=user["email"],
            is_admin=(origem == "administradores"),
        )
        registrar_login(
            user["id"] if origem == "usuarios" else None,
            user["username"],
            origem == "administradores",
            True,
        )
        st.success("Login efetuado!")
        st.rerun()

# ════════════════════════════════════════
# 2) CADASTRO
# ════════════════════════════════════════
elif opcao == "Cadastro":
    st.title("Criar Conta Bancária")

    bancos = [
        "Itaú",
        "Bradesco",
        "Nubank",
        "Inter",
        "Santander",
        "Banco do Brasil",
        "Caixa",
        "C6 Bank",
        "BTG Pactual",
    ]
    estados_civis = [
        "Solteiro(a)",
        "Casado(a)",
        "Divorciado(a)",
        "Viúvo(a)",
        "União estável",
    ]
    situacoes = [
        "Empregado",
        "Desempregado",
        "Autônomo",
        "Estudante",
        "Aposentado",
    ]

    with st.form("frm_cad"):
        col1, col2 = st.columns(2, gap="large")
        with col1:
            nome = st.text_input("Nome completo")
            cpf = st.text_input("CPF", key="cpf")
            rg = st.text_input("RG", key="rg")
            dnasc = st.date_input("Data de nascimento", value=date(2000, 1, 1))
            tel = st.text_input("Telefone", key="tel")
            renda = st.number_input(
                "Renda mensal (R$)", min_value=0.0, step=100.0, format="%.2f"
            )
            estc = st.selectbox("Estado civil", estados_civis)
        with col2:
            email = st.text_input("E-mail")
            banco = st.selectbox("Banco", bancos)
            end = st.text_input("Endereço completo")
            cidade = st.text_input("Cidade")
            uf = st.text_input("UF", max_chars=2)
            prof = st.text_input("Profissão")
            sitp = st.selectbox("Situação profissional", situacoes)

        user = st.text_input("Usuário (nickname)")
        p1 = st.text_input("Senha", type="password")
        p2 = st.text_input("Confirmar senha", type="password")
        cadastro_ok = st.form_submit_button("Cadastrar")

    if cadastro_ok:
        if p1 != p2:
            st.warning("As senhas não coincidem.")
            st.stop()

        cur = get_cursor()
        cur.execute(
            "SELECT 1 FROM usuarios WHERE cpf=%s OR username=%s",
            (only_digits(cpf), user),
        )
        if cur.fetchone():
            st.error("CPF ou usuário já cadastrados.")
            st.stop()

        cur.execute(
            """
            INSERT INTO usuarios (
                nome, email, banco, cidade, estado, username, senha,
                cpf, rg, data_nascimento, endereco, telefone, renda,
                profissao, estado_civil, situacao_prof
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s
            )
            """,
            (
                nome,
                email,
                banco,
                cidade,
                uf.upper(),
                user,
                p1,
                only_digits(cpf),
                only_digits(rg),
                dnasc,
                end,
                tel,
                renda,
                prof,
                estc,
                sitp,
            ),
        )
        conn.commit()
        st.success("Usuário cadastrado com sucesso!")

# ════════════════════════════════════════
# 3) RECUPERAÇÃO DE SENHA
# ════════════════════════════════════════
else:  # Esqueci minha senha
    st.title("Recuperar Senha")

    with st.form("frm_rec"):
        usr = st.text_input("Usuário")
        cpf_rec = st.text_input("CPF", key="cpf_rec")
        mail = st.text_input("E-mail")
        rec_btn = st.form_submit_button("Gerar nova senha")

    if rec_btn:
        cur = get_cursor(dictionary=True)
        cur.execute(
            "SELECT id, cpf, email FROM usuarios WHERE username = %s LIMIT 1", (usr,)
        )
        u = cur.fetchone()

        if not u:
            st.error("Usuário não encontrado.")
        elif only_digits(u["cpf"]) != only_digits(cpf_rec) or mail != u["email"]:
            st.error("Dados não conferem.")
        else:
            nova = gerar_senha_tmp()
            cur.execute("UPDATE usuarios SET senha=%s WHERE id=%s", (nova, u["id"]))
            conn.commit()
            st.success(f"Nova senha gerada: **{nova}**  (troque após o login)")
