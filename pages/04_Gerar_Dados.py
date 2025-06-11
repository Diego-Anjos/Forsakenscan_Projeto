"""
04_Gerar_Dados.py
-----------------
Popula a base 'analise_transacoes' com dados sintéticos:
• 3 000 usuários + limites
• 11 000 transações (≈10 % suspeitas) + compras
• ofertas de empréstimo
• tentativas de exceder limite
"""
import random
from uuid import uuid4
from decimal import Decimal

import streamlit as st
if not hasattr(st, "rerun"):
    st.rerun = st.experimental_rerun  # alias p/ versões antigas


from faker import Faker
from mysql.connector.errors import IntegrityError

from db import get_conn, get_cursor

fake = Faker("pt_BR")

# ─────────────────────────  LISTAS FIXAS  ─────────────────────────
BANCOS      = ["Itaú", "Bradesco", "Nubank", "Inter", "Santander",
               "Banco do Brasil", "Caixa", "C6 Bank", "BTG Pactual"]
FORMAS_PG   = ["Pix", "Transferência", "Cartão", "Boleto"]
LOJAS       = ["Amazon", "Mercado Livre", "Magalu", "Shein",
               "Kabum", "Netshoes", "Steam"]
CATEGORIAS  = ["Eletrônicos", "Vestuário", "Casa", "Alimentos",
               "Beleza", "Games"]
EST_CIVIL   = ["Solteiro(a)", "Casado(a)", "Divorciado(a)",
               "Viúvo(a)", "União estável"]
SIT_PROF    = ["Empregado", "Desempregado", "Autônomo",
               "Estudante", "Aposentado"]

# ─────────────────────────  HELPERS  ─────────────────────────
def _username_unico(vistos: set[str]) -> str:
    while True:
        cand = fake.user_name() + str(random.randint(10, 99))
        if cand not in vistos:
            vistos.add(cand)
            return cand

def _to_float(v):
    return float(v) if isinstance(v, Decimal) else v

# ─────────────────────────  1) USUÁRIOS + LIMITES  ─────────────────────────
def gerar_usuarios(qtd: int = 3_000) -> None:
    st.info(f"🔄 Inserindo {qtd:,} usuários…")
    conn = get_conn()
    cur  = get_cursor()

    insert_usr = """
        INSERT INTO usuarios
              (nome, email, banco, cidade, estado, username, senha, tipo,
               cpf, rg, data_nascimento, endereco, telefone, renda,
               profissao, estado_civil, situacao_prof)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'normal',
                %s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    insert_lim = """
        INSERT INTO limites_usuario
              (user_id, limite_pagamento, limite_dia, limite_noite)
        VALUES (%s,%s,%s,%s)
    """

    data_usr, data_lim = [], []
    users_vistos: set[str] = set()

    while len(data_usr) < qtd:
        try:
            cpf = fake.unique.cpf()
        except Exception:
            fake.unique.clear()
            continue

        renda = round(random.uniform(1_200, 20_000), 2)
        data_usr.append((
            fake.name(),
            fake.free_email(),
            random.choice(BANCOS),
            fake.city(),
            fake.estado_sigla(),
            _username_unico(users_vistos),
            fake.password(length=10),
            cpf,
            str(random.randint(1_000_000, 9_999_999)),
            fake.date_of_birth(minimum_age=18, maximum_age=75),
            fake.address()[:240],
            fake.phone_number(),
            renda,
            fake.job()[:90],
            random.choice(EST_CIVIL),
            random.choice(SIT_PROF),
        ))

    try:
        cur.executemany(insert_usr, data_usr)
        conn.commit()
    except IntegrityError as e:
        conn.rollback()
        st.error(f"Erro de integridade: {e.msg}")
        return

    cur.execute("SELECT id, renda FROM usuarios ORDER BY id DESC LIMIT %s", (qtd,))
    for uid, renda_db in cur.fetchall():
        renda = _to_float(renda_db)
        lim_dia   = round(renda * random.uniform(1.5, 4.0), 2)
        lim_noite = round(lim_dia / 2, 2)
        data_lim.append((uid, round(renda * 3, 2), lim_dia, lim_noite))

    cur.executemany(insert_lim, data_lim)
    conn.commit()
    st.success("✅ Usuários e limites gerados com sucesso!")

# ─────────────────────────  2) TRANSAÇÕES + COMPRAS  ─────────────────────────
def gerar_transacoes(qtd: int = 11_000) -> None:
    st.info(f"🔄 Inserindo {qtd:,} transações…")
    conn = get_conn()
    cur  = get_cursor()

    cur.execute("SELECT id FROM usuarios")
    user_ids = [x[0] for x in cur.fetchall()]
    if not user_ids:
        st.error("Não há usuários na base."); return

    tipos = ["Compra", "Pagamento", "Transferência", "PIX",
             "Recebimento", "Cash-In", "Saque"]

    insert_tx = """
        INSERT INTO transacoes
              (user_id, valor, tipo_transacao, forma_pagamento, codigo, data_hora,
               localizacao, banco_origem, banco_destino, suspeita, motivo_suspeita)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    insert_shop = """
        INSERT INTO compras_online
              (user_id, codigo_tx, loja, categoria, produto, qtd, valor_unit, valor_total)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """

    tx_data, shop_data = [], []
    suspeitos = 0
    for _ in range(qtd):
        uid   = random.choice(user_ids)
        tipo  = random.choice(tipos)
        valor = round(random.uniform(1, 20_000), 2)
        forma = random.choice(FORMAS_PG) if tipo in ("Compra", "Pagamento",
                                                     "Transferência", "PIX", "Saque") else "Interno"
        codigo    = uuid4().hex[:10]
        data_h    = fake.date_time_between(start_date="-90d", end_date="now")
        suspeita  = 1 if random.random() < 0.10 else 0
        motivo    = "valor atípico" if suspeita else None
        if suspeita:
            suspeitos += 1

        tx_data.append((
            uid, valor, tipo, forma, codigo, data_h,
            fake.city(),
            fake.swift(length=11) if random.random() < 0.5 else None,
            fake.swift(length=11) if random.random() < 0.5 else None,
            suspeita, motivo,
        ))

        if tipo == "Compra":
            qtd_prod = random.randint(1, 5)
            v_unit   = round(valor / qtd_prod, 2)
            shop_data.append((
                uid, codigo,
                random.choice(LOJAS),
                random.choice(CATEGORIAS),
                fake.word().title(),
                qtd_prod, v_unit, valor,
            ))

    cur.executemany(insert_tx, tx_data)
    if shop_data:
        cur.executemany(insert_shop, shop_data)
    conn.commit()
    st.success(f"✅ Transações inseridas (🚩 {suspeitos:,} suspeitas).")

# ─────────────────────────  3) EMPRÉSTIMOS  ─────────────────────────
def gerar_emprestimos(taxa_oferta: float = 0.25) -> None:
    st.info("🔄 Gerando ofertas de empréstimo…")
    conn = get_conn()
    cur  = get_cursor()

    cur.execute("SELECT id, renda FROM usuarios")
    dados = cur.fetchall()

    insert_emp = """
        INSERT INTO emprestimos
              (user_id, valor, taxa_juros, prazo_meses, status)
        VALUES (%s,%s,%s,%s,%s)
    """
    emp_data = []
    for uid, renda_db in dados:
        if random.random() > taxa_oferta:
            continue
        renda = _to_float(renda_db)
        valor  = round(random.uniform(renda * 0.5, renda * 5), 2)
        status = random.choices(("oferta", "aceito", "recusado"),
                                weights=(50, 30, 20))[0]
        emp_data.append((
            uid, valor,
            random.choice((1.8, 2.2, 2.5, 3.0)),
            random.choice((12, 24, 36, 48)),
            status,
        ))
    if emp_data:
        cur.executemany(insert_emp, emp_data)
        conn.commit()
    st.success(f"✅ Empréstimos gerados: {len(emp_data):,}")

# ─────────────────────────  4) TENTATIVAS DE LIMITE  ─────────────────────────
def gerar_tentativas_limite() -> None:
    st.info("🔄 Registrando tentativas de exceder limite…")
    conn = get_conn()
    cur  = get_cursor()

    cur.execute("SELECT user_id, limite_dia FROM limites_usuario")
    dados = cur.fetchall()

    insert_tl = """
        INSERT INTO tentativas_limite
              (user_id, valor_tentativa, limite, turno)
        VALUES (%s,%s,%s,%s)
    """
    linhas = []
    for uid, lim_db in dados:
        lim = _to_float(lim_db)
        if random.random() < 0.20:
            for _ in range(random.randint(1, 3)):
                linhas.append((
                    uid,
                    round(lim * random.uniform(1.1, 2.0), 2),
                    lim,
                    random.choice(("dia", "noite")),
                ))
    if linhas:
        cur.executemany(insert_tl, linhas)
        conn.commit()
    st.success(f"✅ Tentativas registradas: {len(linhas):,}")

# ─────────────────────────  INTERFACE  ─────────────────────────
def main() -> None:
    st.title("🚀 Gerador de Dados – Ambiente de Teste")

    if st.button("Popular Banco (⚠️ 3 000 usuários & 11 000 transações)",
                 type="primary"):
        gerar_usuarios()
        gerar_transacoes()
        gerar_emprestimos()
        gerar_tentativas_limite()
        st.balloons()
        st.success("🎉 Base de testes criada com sucesso!")

if __name__ == "__main__":
    main()