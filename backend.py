from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float, DECIMAL, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

# Configuração do Banco de Dados
DATABASE_URL = "mysql+mysqlconnector://root:123456789@localhost/analise_transacoes"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

app = FastAPI()

# Libera o CORS para front-end acessar
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelos
class Produto(Base):
    __tablename__ = "produtos"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(255))
    preco = Column(Float)
    categoria = Column(String(255))

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(255))
    email = Column(String(255))
    banco = Column(String(100))
    cidade = Column(String(100))
    estado = Column(String(2))
    username = Column(String(100), unique=True)
    senha = Column(String(255))
    data_criacao = Column(DateTime, default=datetime.now)

class Transacao(Base):
    __tablename__ = "transacoes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('usuarios.id'))
    valor = Column(DECIMAL(10, 2))
    tipo_transacao = Column(String(50))
    forma_pagamento = Column(String(20), nullable=True)
    data_hora = Column(DateTime, default=datetime.now)
    localizacao = Column(String(100), nullable=True)
    banco_origem = Column(String(100))
    banco_destino = Column(String(100))
    suspeita = Column(Boolean, default=False)
    motivo_suspeita = Column(String(255), nullable=True)
    codigo = Column(String(50), nullable=True)

class TransacaoCreate(BaseModel):
    user_id: int
    valor: float
    tipo_transacao: str
    forma_pagamento: Optional[str] = None
    localizacao: Optional[str] = None
    banco_origem: str
    banco_destino: str
    ip: Optional[str] = None

# Criação automática das tabelas se não existirem
Base.metadata.create_all(bind=engine)

# Dependência para acesso à sessão do banco
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Endpoints
@app.get("/produtos/")
def listar_produtos(db: Session = Depends(get_db)):
    return db.query(Produto).all()

@app.post("/transacoes/")
def criar_transacao(transacao: TransacaoCreate, db: Session = Depends(get_db)):
    from fraude import avaliar_transacao, registrar_fraude
    
    # Criar dict para análise de fraude
    tx_dict = transacao.dict()
    tx_dict["data_hora"] = datetime.now()
    
    # Avaliar fraude
    suspeita, motivo = avaliar_transacao(tx_dict)
    
    # Inserir transação
    db_transacao = Transacao(**transacao.dict(), data_hora=datetime.now(), suspeita=suspeita, motivo_suspeita=motivo)
    db.add(db_transacao)
    db.commit()
    db.refresh(db_transacao)
    
    # Se for suspeita, registrar na tabela de fraudes
    if suspeita:
        registrar_fraude(db_transacao.id, motivo)
    
    return {
        "id": db_transacao.id,
        "suspeita": suspeita,
        "motivo_suspeita": motivo if suspeita else None
    }

# ------------------------------------------------------------
# Registrar fato genérico
# ------------------------------------------------------------
def registrar_fato(db, user_id:int, acao:str,
                   descricao:str,
                   entidade:str=None, pk:str=None,
                   campo:str=None, de=None, para=None):
    db.execute(
        """
        INSERT INTO fatos_usuarios
              (user_id, acao, descricao, entidade,
               chave_primaria, campo, valor_antigo, valor_novo)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (user_id, acao, descricao,
         entidade, pk, campo,
         str(de) if de is not None else None,
         str(para) if para is not None else None)
    )