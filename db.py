"""
db.py  –  conexão MySQL reutilizável e auto-reconectável
-------------------------------------------------------
Use get_conn() sempre que precisar de um objeto de conexão
e get_cursor() quando precisar apenas do cursor.
Se a conexão tiver expirado (timeout) ela será recriada
automaticamente sem derrubar a aplicação.
"""
import mysql.connector
from mysql.connector import Error

# 🔧  Ajuste estes parâmetros ao seu ambiente.
_DB_CFG = {
    "host":     "localhost",
    "user":     "root",
    "password": "123456789",
    "database": "analise_transacoes",
    "charset":  "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
}

_conn = None   # cache da conexão viva


def _connect():
    """Cria uma nova conexão MySQL."""
    return mysql.connector.connect(**_DB_CFG)


def get_conn():
    """
    Devolve conexão ativa. Se ela estiver fechada por timeout
    ou nunca tiver sido criada, reconecta automaticamente.
    """
    global _conn
    try:
        if _conn is None or not _conn.is_connected():
            _conn = _connect()
    except Error:
        _conn = _connect()
    return _conn


def get_cursor(dictionary: bool = False, buffered: bool = False):
    """Retorna cursor já garantido com conexão ativa."""
    return get_conn().cursor(dictionary=dictionary, buffered=buffered)
