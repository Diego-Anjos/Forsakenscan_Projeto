"""
fraude.py – motor de regras de detecção de fraude
================================================

Implementa todas as regras de detecção de fraude para o sistema bancário.
Cada regra devolve (flag: bool, motivo: str). A função pública
`avaliar_transacao(tx_dict)` percorre todas e retorna (suspeita, motivos).
"""

# fraude.py  –  motor de regras de detecção de fraude
from datetime import datetime, time, timedelta

from db import get_conn, get_cursor      # ← NOVO
conn   = get_conn()                      # ← NOVO
cursor = get_cursor(dictionary=True, buffered=True)   # ← NOVO

# ------------------------------------------------------------------
# REGRA #01 – LIMITE POR TURNO (VERSÃO MELHORADA)
# ------------------------------------------------------------------
H_INI_DIA, H_FIM_DIA = time(6, 0), time(22,59,59)
H_INI_NOITE, H_FIM_NOITE = time(23, 0), time(5,59,59)

def _obter_limites_usuario(user_id: int) -> tuple:
    """Obtém limites personalizados ou retorna padrão se não existir"""
    cursor.execute("""
        SELECT limite_dia, limite_noite 
        FROM limites_usuario
        WHERE user_id = %s
    """, (user_id,))
    result = cursor.fetchone()
    return (result["limite_dia"], result["limite_noite"]) if result else (10_000, 5_000)

def _turno(dt: datetime) -> str:
    """Determina se é turno dia ou noite"""
    return "dia" if H_INI_DIA <= dt.time() <= H_FIM_DIA else "noite"

def _total_turno(user_id: int, turno: str) -> float:
    """Calcula o total gasto no turno atual, considerando apenas transações relevantes"""
    tipos_considerados = ("Compra", "Pagamento", "Transferência", "Saque", "PIX")
    
    if turno == "dia":
        cursor.execute("""
            SELECT COALESCE(SUM(valor),0) AS total
            FROM transacoes
            WHERE user_id = %s
              AND DATE(data_hora)=CURDATE()
              AND TIME(data_hora) BETWEEN %s AND %s
              AND tipo_transacao IN %s
        """, (user_id, H_INI_DIA, H_FIM_DIA, tipos_considerados))
    else:
        cursor.execute("""
            SELECT COALESCE(SUM(valor),0) AS total
            FROM transacoes
            WHERE user_id = %s
              AND (
                    (DATE(data_hora)=CURDATE() AND TIME(data_hora)>=%s)
                 OR (DATE(data_hora)=DATE_SUB(CURDATE(),INTERVAL 1 DAY)
                    AND TIME(data_hora)<=%s
              )
              AND tipo_transacao IN %s
        """, (user_id, H_INI_NOITE, H_FIM_NOITE, tipos_considerados))
    
    return float(cursor.fetchone()["total"])

def _registrar_tentativa_limite(user_id: int, valor: float, limite: float, turno: str):
    """Registra tentativa de exceder limite para auditoria"""
    cursor.execute("""
        INSERT INTO tentativas_limite 
        (user_id, valor_tentativa, limite, turno, data_hora) 
        VALUES (%s, %s, %s, %s, NOW())
    """, (user_id, valor, limite, turno))
    conn.commit()

def regra_01_limites_turno(tx: dict):
    """Versão melhorada da regra de limites por turno"""
    try:
        # Obter limites personalizados para o usuário
        limite_dia, limite_noite = _obter_limites_usuario(tx["user_id"])
        
        # Determinar turno e limite aplicável
        turno_tx = _turno(tx["data_hora"])
        limite = limite_dia if turno_tx == "dia" else limite_noite
        
        # Calcular soma das transações no turno
        soma = _total_turno(tx["user_id"], turno_tx) + float(tx["valor"])
        
        if soma > limite:
            # Registrar tentativa e retornar alerta
            _registrar_tentativa_limite(tx["user_id"], soma, limite, turno_tx)
            return True, f"Limite {turno_tx} excedido (R$ {soma:,.2f} > {limite:,.2f})"
        
        return False, ""
    
    except Exception as e:
        print(f"Erro na regra de limites: {str(e)}")
        conn.rollback()
        return False, ""

# [MANTENHA O RESTO DO ARQUIVO INALTERADO A PARTIR DAQUI...]
# [AS OUTRAS REGRAS (02-07) PERMANECEM EXATAMENTE COMO ESTÃO NO SEU ARQUIVO ORIGINAL]

# ------------------------------------------------------------------
# REGRA #02 – 5+ transações em 5 minutos (mesmo CPF ou vários CPFs)
# ------------------------------------------------------------------
def regra_02_5_transacoes_5min(tx: dict):
    # Verificação para o mesmo usuário
    cursor.execute("""
        SELECT COUNT(*) AS c
        FROM transacoes
        WHERE user_id = %s
          AND tipo_transacao IN ('Compra','Pagamento','Transferência')
          AND data_hora >= NOW() - INTERVAL 5 MINUTE
    """, (tx["user_id"],))
    mesmo_usuario = cursor.fetchone()["c"] >= 4  # Já conta com a atual
    
    # Verificação para vários CPFs (mesmo IP)
    ip = tx.get("ip")
    if ip:
        cursor.execute("""
            SELECT COUNT(DISTINCT t.user_id) AS usuarios_distintos
            FROM transacoes t
            JOIN logs l ON l.user_id = t.user_id
            WHERE t.data_hora >= NOW() - INTERVAL 5 MINUTE
              AND t.tipo_transacao IN ('Compra','Pagamento','Transferência')
              AND l.ip = %s
              AND l.data_hora >= NOW() - INTERVAL 5 MINUTE
        """, (ip,))
        varios_usuarios = cursor.fetchone()["usuarios_distintos"] >= 5
    else:
        varios_usuarios = False
    
    if mesmo_usuario:
        return True, "5+ transações do mesmo usuário em 5 minutos"
    if varios_usuarios:
        return True, "5+ transações de diferentes usuários (mesmo IP) em 5 minutos"
    return False, ""

# ------------------------------------------------------------------
# REGRA #03 – 3 tentativas de login falhas
# ------------------------------------------------------------------
def regra_03_tentativas_login(tx: dict):
    cursor.execute("""
        SELECT COUNT(*) AS tentativas
        FROM logs
        WHERE user_id = %s
          AND resultado = 'fail'
          AND data_hora >= NOW() - INTERVAL 30 MINUTE
        ORDER BY data_hora DESC
        LIMIT 3
    """, (tx["user_id"],))
    tentativas = cursor.fetchone()["tentativas"]
    if tentativas >= 3:
        return True, "3+ tentativas de login falhas em 30 minutos"
    return False, ""

# ------------------------------------------------------------------
# REGRA #04 – Alteração múltipla de senha
# ------------------------------------------------------------------
def regra_04_alteracao_senha(tx: dict):
    cursor.execute("""
        SELECT COUNT(*) AS alteracoes
        FROM fatos_usuarios
        WHERE user_id = %s
          AND acao = 'Alterar senha'
          AND data_hora >= NOW() - INTERVAL 7 DAY
    """, (tx["user_id"],))
    alteracoes = cursor.fetchone()["alteracoes"]
    if alteracoes >= 3:
        return True, f"{alteracoes} alterações de senha em 7 dias"
    return False, ""

# ------------------------------------------------------------------
# REGRA #05 – Troca de dados sensíveis + saque
# ------------------------------------------------------------------
def regra_05_troca_dados_saque(tx: dict):
    # Verifica se houve alteração de e-mail ou telefone recente
    cursor.execute("""
        SELECT COUNT(*) AS alteracoes
        FROM fatos_usuarios
        WHERE user_id = %s
          AND acao = 'editar_perfil'
          AND campo IN ('email', 'telefone')
          AND data_hora >= NOW() - INTERVAL 1 HOUR
    """, (tx["user_id"],))
    alteracoes = cursor.fetchone()["alteracoes"]
    
    if alteracoes > 0 and tx["tipo_transacao"] in ('Saque', 'Transferência'):
        return True, "Alteração de dados sensíveis seguida de saque"
    return False, ""

# ------------------------------------------------------------------
# REGRA #06 – Cash In sem histórico (conta nova)
# ------------------------------------------------------------------
def regra_06_cashin_sem_historico(tx: dict):
    if tx["tipo_transacao"] == "Cash-In":
        cursor.execute("""
            SELECT COUNT(*) AS transacoes_anteriores
            FROM transacoes
            WHERE user_id = %s
              AND data_hora < %s
              AND data_hora >= DATE_SUB(%s, INTERVAL 7 DAY)
        """, (tx["user_id"], tx["data_hora"], tx["data_hora"]))
        historico = cursor.fetchone()["transacoes_anteriores"]
        
        if historico == 0 and float(tx["valor"]) > 5000:
            return True, "Cash-In alto em conta sem histórico"
    return False, ""

# ------------------------------------------------------------------
# REGRA #07 – Depósitos e saques rápidos (lavagem de dinheiro)
# ------------------------------------------------------------------
def regra_07_deposito_saque_rapido(tx: dict):
    if tx["tipo_transacao"] in ("Saque", "Transferência"):
        cursor.execute("""
            SELECT valor, TIMESTAMPDIFF(MINUTE, data_hora, %s) as minutos
            FROM transacoes
            WHERE user_id = %s
              AND tipo_transacao = 'Cash-In'
              AND data_hora >= DATE_SUB(%s, INTERVAL 1 HOUR)
            ORDER BY data_hora DESC
            LIMIT 1
        """, (tx["data_hora"], tx["user_id"], tx["data_hora"]))
        deposito = cursor.fetchone()
        
        if deposito and deposito["minutos"] < 10 and float(tx["valor"]) >= deposito["valor"] * 0.9:
            return True, f"Saque de {tx['valor']} após depósito há {deposito['minutos']} minutos"
    return False, ""

# ------------------------------------------------------------------
# MOTOR – lista de regras ativas
# ------------------------------------------------------------------
REGRAS_ATIVAS = [
    regra_01_limites_turno,
    regra_02_5_transacoes_5min,
    regra_03_tentativas_login,
    regra_04_alteracao_senha,
    regra_05_troca_dados_saque,
    regra_06_cashin_sem_historico,
    regra_07_deposito_saque_rapido,
]

def avaliar_transacao(tx: dict):
    """
    Executa todas as REGRAS_ATIVAS.
    tx precisa conter: user_id, valor, data_hora, tipo_transacao.
    Retorna: (suspeita: bool, motivos: str)
    """
    resultados = []
    for regra in REGRAS_ATIVAS:
        try:
            flag, motivo = regra(tx)
            if flag:
                resultados.append((regra.__name__, motivo))
        except Exception as e:
            print(f"Erro na regra {regra.__name__}: {str(e)}")
            conn.rollback()
    
    if resultados:
        # Ordenar por prioridade (regras mais críticas primeiro)
        resultados.sort(key=lambda x: 0 if "limites_turno" in x[0] else 
                                     1 if "5_transacoes" in x[0] else 2)
        motivos = "; ".join(m for _, m in resultados)
        return True, motivos
    return False, ""

def registrar_fraude(tx_id: int, motivos: str):
    """
    Registra uma fraude detectada na tabela dedicada
    """
    cursor.execute("""
        INSERT INTO fraudes_detectadas
        (transacao_id, motivos, data_deteccao)
        VALUES (%s, %s, NOW())
        ON DUPLICATE KEY UPDATE
        motivos = VALUES(motivos),
        data_deteccao = VALUES(data_deteccao)
    """, (tx_id, motivos))
    conn.commit()