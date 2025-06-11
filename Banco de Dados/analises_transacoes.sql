/*DROP DATABASE IF EXISTS analise_transacoes;*/
CREATE DATABASE IF NOT EXISTS analise_transacoes
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
USE analise_transacoes;

CREATE TABLE administradores (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    username   VARCHAR(100) UNIQUE NOT NULL,
    senha      VARCHAR(255)        NOT NULL,
    nome       VARCHAR(255)        NULL,
    email      VARCHAR(255)        NULL,
    nivel      ENUM('master')      DEFAULT 'master',
    criado_em  DATETIME            DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

/* Seed opcional */
INSERT INTO administradores (username,senha,nome,email)
VALUES ('admin','Master@123','Usuário Master','admin@gmail.com');

/* ================================================================
   2) Usuários – fundamenta quase todas as FKs subsequentes
   ================================================================ */
CREATE TABLE usuarios (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    nome              VARCHAR(255)    NULL,
    email             VARCHAR(255)    NULL,
    banco             VARCHAR(100)    NULL,
    cidade            VARCHAR(100)    NULL,
    estado            CHAR(2)         NULL,
    username          VARCHAR(100) UNIQUE,
    senha             VARCHAR(255)    NULL,
    tipo              VARCHAR(20)     DEFAULT 'normal',
    cpf               VARCHAR(14) UNIQUE,
    rg                VARCHAR(20)     NULL,
    data_nascimento   DATE            NULL,
    endereco          VARCHAR(255)    NULL,
    telefone          VARCHAR(20)     NULL,
    renda             DECIMAL(12,2)   NULL,
    profissao         VARCHAR(100)    NULL,
    estado_civil      VARCHAR(20)     NULL,
    situacao_prof     VARCHAR(50)     NULL,
    data_criacao      DATETIME        DEFAULT CURRENT_TIMESTAMP,

    /* Campos de controle de bloqueio / saldo pendente */
    ativo             TINYINT(1)      DEFAULT 1,
    motivo_inativacao TEXT            NULL,
    data_inativacao   DATETIME        NULL,
    conta_bloqueada   TINYINT(1)      DEFAULT 0,
    saldo_pendente    DECIMAL(15,2)   NULL
) ENGINE=InnoDB;

/* ================================================================
   3) Tabela de limites gerais do usuário
   ================================================================ */
CREATE TABLE limites_usuario (
    user_id          INT PRIMARY KEY,
    limite_pagamento DECIMAL(12,2) NULL,
    atualizado_em    DATETIME      DEFAULT CURRENT_TIMESTAMP,
    limite_dia       DECIMAL(15,2) NOT NULL DEFAULT 10000.00,
    limite_noite     DECIMAL(15,2) NOT NULL DEFAULT  5000.00,
    CONSTRAINT fk_lim_usr_usuario   FOREIGN KEY (user_id)
        REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

/* ================================================================
   5) Transações – coração do sistema
   ================================================================ */

CREATE TABLE transacoes (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    user_id        INT            NOT NULL,
    valor          DECIMAL(10,2)  NOT NULL,
    tipo_transacao VARCHAR(50)    NOT NULL,
    forma_pagamento VARCHAR(20) NULL,
    data_hora      DATETIME       NOT NULL,
    localizacao    VARCHAR(100)   NULL,
    banco          VARCHAR(100)   NULL,
    suspeita       TINYINT(1)     DEFAULT 0,
    codigo         VARCHAR(50)    NULL,
    banco_origem   VARCHAR(100)   NULL,
    banco_destino  VARCHAR(100)   NULL,
    motivo_suspeita VARCHAR(255)  NULL,

    KEY idx_tx_user        (user_id),
    KEY idx_tx_data        (data_hora),
    KEY idx_tx_suspeita    (suspeita),
    CONSTRAINT fk_tx_user  FOREIGN KEY (user_id)
           REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Exemplo: index para acelerar buscas por código de transação
ALTER TABLE transacoes ADD INDEX idx_tx_codigo (codigo);

/* ================================================================
   6) Compras on-line – detalhamento extra
   ================================================================ */

CREATE TABLE compras_online (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT           NOT NULL,
    codigo_tx    VARCHAR(50)   NOT NULL,
    loja         VARCHAR(120)  NULL,
    categoria    VARCHAR(80)   NULL,
    produto      VARCHAR(120)  NULL,
    qtd          INT           NULL,
    valor_unit   DECIMAL(10,2) NULL,
    valor_total  DECIMAL(10,2) NULL,
    data_hora    DATETIME      DEFAULT CURRENT_TIMESTAMP,
    status       VARCHAR(20)   DEFAULT 'Pago',

    KEY idx_compra_user (user_id),

    CONSTRAINT fk_compra_user FOREIGN KEY (user_id)
        REFERENCES usuarios(id)         ON DELETE CASCADE,

    CONSTRAINT fk_compra_tx   FOREIGN KEY (codigo_tx)
        REFERENCES transacoes(codigo)   ON DELETE CASCADE
) ENGINE = InnoDB;

-- Se ainda não existir índice/único em transacoes.codigo
ALTER TABLE transacoes
ADD INDEX idx_codigo (codigo);      -- use UNIQUE idx_codigo (codigo) se cada código for único

/* ================================================================
   7) Empréstimos
   ================================================================ */
CREATE TABLE emprestimos (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT            NOT NULL,
    valor       DECIMAL(12,2)  NOT NULL,
    taxa_juros  DECIMAL(5,2)   NOT NULL,    -- % a.m.
    prazo_meses INT            NOT NULL,
    status      ENUM('oferta','aceito','recusado') DEFAULT 'oferta',
    criado_em   DATETIME       DEFAULT CURRENT_TIMESTAMP,

    KEY idx_emp_user (user_id),
    CONSTRAINT fk_emp_user FOREIGN KEY (user_id)
        REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

/* ================================================================
   8) Histórico de bloqueios
   ================================================================ */
CREATE TABLE historico_bloqueios (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT  NOT NULL,
    acao            ENUM('BLOQUEIO','DESBLOQUEIO') NOT NULL,
    motivo          TEXT,
    data_hora       DATETIME DEFAULT CURRENT_TIMESTAMP,
    administrador_id INT,

    KEY idx_hist_user  (user_id),
    KEY idx_hist_admin (administrador_id),
    CONSTRAINT fk_hist_user  FOREIGN KEY (user_id)
        REFERENCES usuarios(id) ON DELETE CASCADE,
    CONSTRAINT fk_hist_admin FOREIGN KEY (administrador_id)
        REFERENCES administradores(id) ON DELETE SET NULL
) ENGINE=InnoDB;

/* ================================================================
   9) Logs de acesso
   ================================================================ */
CREATE TABLE logs (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT          NULL,
    usuario      VARCHAR(100) NULL,
    admin_user   VARCHAR(100) NULL,
    resultado    ENUM('ok','fail') NULL,
    ip           VARCHAR(45)  NULL,
    user_agent   VARCHAR(255) NULL,
    duracao_seg  SMALLINT     NULL,
    data_hora    DATETIME     DEFAULT CURRENT_TIMESTAMP,

    KEY idx_logs_user  (user_id),
    KEY idx_logs_data  (data_hora),
    KEY idx_logs_res   (resultado),
    CONSTRAINT fk_logs_user FOREIGN KEY (user_id)
        REFERENCES usuarios(id) ON DELETE SET NULL
) ENGINE=InnoDB;

/* ================================================================
   10) Fatos / trilha de auditoria
   ================================================================ */
CREATE TABLE fatos_usuarios (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT          NOT NULL,
    entidade        VARCHAR(40)  NULL,
    chave_primaria  VARCHAR(40)  NULL,
    campo           VARCHAR(40)  NULL,
    valor_antigo    TEXT         NULL,
    valor_novo      TEXT         NULL,
    acao            VARCHAR(100) NULL,
    descricao       TEXT         NULL,
    data_hora       DATETIME DEFAULT CURRENT_TIMESTAMP,

    KEY idx_fatos_ent  (entidade),
    KEY idx_fatos_acao (acao),
    CONSTRAINT fk_fatos_user FOREIGN KEY (user_id)
        REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

/* ================================================================
   11) Tentativas de exceder limite
   ================================================================ */
CREATE TABLE tentativas_limite (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT             NOT NULL,
    valor_tentativa DECIMAL(15,2)   NOT NULL,
    limite          DECIMAL(15,2)   NOT NULL,
    turno           ENUM('dia','noite') NOT NULL,
    data_hora       DATETIME        DEFAULT CURRENT_TIMESTAMP,

    KEY idx_tlim_user (user_id),
    CONSTRAINT fk_tlim_user FOREIGN KEY (user_id)
        REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

/* ================================================================
   12) Fraudes detectadas
   ================================================================ */
CREATE TABLE fraudes_detectadas (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    transacao_id  INT          NOT NULL,
    motivos       TEXT         NOT NULL,
    data_deteccao DATETIME     NOT NULL,
    revisado      BOOLEAN      DEFAULT FALSE,
    acao_tomada   VARCHAR(100) NULL,
    revisado_por  INT          NULL,
    data_revisao  DATETIME     NULL,

    KEY idx_fraud_tx   (transacao_id),
    KEY idx_fraud_data (data_deteccao),
    CONSTRAINT fk_fraud_tx   FOREIGN KEY (transacao_id)
        REFERENCES transacoes(id) ON DELETE CASCADE,
    CONSTRAINT fk_fraud_admin FOREIGN KEY (revisado_por)
        REFERENCES administradores(id) ON DELETE SET NULL
) ENGINE=InnoDB;

/* ================================================================
   13) SELECTS
   ================================================================ */
   
select * from usuarios;
select * from  transacoes;
select * from emprestimos;
select * from tentativas_limite;
select * from administradores;
select * from emprestimos;



















































































/* ================================================================
   05) FRAUDES DE ALTERAÇÕES DE DADOS SENSIVEIS E CASHOUT. -----------======================================================================================================================================================
   ================================================================ */
   
   /* ================================================================
   0) Ajuste: use o banco certo
   ================================================================ */
USE analise_transacoes;

/* ================================================================
   1) Descobre o range de usuários existentes
   ================================================================ */
SELECT MIN(id) INTO @USR_MIN FROM usuarios;
SELECT MAX(id) INTO @USR_MAX FROM usuarios;

/* Se não houver usuários, pare aqui */
SELECT IF(@USR_MIN IS NULL, '❌ Nenhum usuário encontrado', '✔️ OK') AS check_users;

/* ================================================================
   2) Cria 50 alterações de e-mail ou telefone
   --------------------------------------------------------------- */
DROP TEMPORARY TABLE IF EXISTS tmp_alter;
CREATE TEMPORARY TABLE tmp_alter AS
SELECT  /* 50 usuários aleatórios */
       FLOOR(RAND()*(@USR_MAX-@USR_MIN+1))+@USR_MIN        AS user_id,
       NOW() - INTERVAL FLOOR(RAND()*168) HOUR             AS ts_alter,  -- nos últimos 7 d
       IF(RAND()<0.5,'email','telefone')                   AS campo
  FROM information_schema.tables
 LIMIT 50;

/* Insere na trilha de auditoria */
INSERT INTO fatos_usuarios
      (user_id, entidade, campo, valor_antigo, valor_novo, acao, descricao, data_hora)
SELECT  t.user_id,
        'usuarios',
        t.campo,
        CASE 
            WHEN t.campo='email'     THEN CONCAT('old',u.username,'@demo.com')
            ELSE CONCAT('119',LPAD(FLOOR(RAND()*1e8),8,'0'))
        END                                                AS valor_antigo,
        CASE
            WHEN t.campo='email'     THEN CONCAT('new',u.username,'@demo.com')
            ELSE CONCAT('119',LPAD(FLOOR(RAND()*1e8),8,'0'))
        END                                                AS valor_novo,
        'editar_perfil',                                   -- mesma label usada pelo app
        CONCAT('Alteração de ',t.campo),
        t.ts_alter
  FROM tmp_alter t
  JOIN usuarios u ON u.id = t.user_id;

/* ================================================================
   3) Para cada alteração, cria 1 Cash-Out até 24 h depois
   --------------------------------------------------------------- */
INSERT INTO transacoes
      (user_id, valor, tipo_transacao, forma_pagamento,
       data_hora, localizacao, banco, suspeita, motivo_suspeita, codigo)
SELECT  t.user_id,
        ROUND(RAND()*3000 + 200,2)                         AS valor,      -- R$ 200 – R$ 3 200
        'Cash-Out',
        'Pix',
        t.ts_alter + INTERVAL FLOOR(RAND()*1440) MINUTE    AS data_hora,  -- ≤ 24 h depois
        'São Paulo',
        u.banco,
        1,                                                 -- já marcado suspeito
        'Alteração de dados + Cash-Out ≤24h',
        UUID()
  FROM tmp_alter t
  JOIN usuarios u ON u.id = t.user_id;

/* ================================================================
   4) Limpeza opcional
   ================================================================ */
DROP TEMPORARY TABLE IF EXISTS tmp_alter;

/* ================================================================
   5) Verificação rápida
   ================================================================ */
SELECT COUNT(*) AS alteracoes  FROM fatos_usuarios  WHERE campo IN ('email','telefone')
  AND data_hora >= NOW() - INTERVAL 7 DAY;

SELECT COUNT(*) AS cash_outs
  FROM transacoes
 WHERE tipo_transacao='Cash-Out'
   AND data_hora      >= NOW() - INTERVAL 7 DAY
   AND suspeita = 1;

/* ================================================================
   06) ENTRADAS E SAÍDAS <5MIN  -----------======================================================================================================================================================
   ================================================================ */
   
   /* ================================================================
   0) Use o banco alvo
   ================================================================ */
USE analise_transacoes;

/* ================================================================
   1) Descobrir range de usuários
   ================================================================ */
SELECT MIN(id) INTO @U_MIN FROM usuarios;
SELECT MAX(id) INTO @U_MAX FROM usuarios;

/* ================================================================
   2) Gerar 120 pares Entrada-Saída (smurfing)
   --------------------------------------------------------------- */
DROP TEMPORARY TABLE IF EXISTS tmp_smurf;
CREATE TEMPORARY TABLE tmp_smurf AS
SELECT 
       /* usuário aleatório existente */
       FLOOR(RAND()*(@U_MAX-@U_MIN+1)) + @U_MIN        AS user_id,
       /* horário base: últimos 3 dias */
       NOW() - INTERVAL FLOOR(RAND()*72) HOUR           AS ts_in,
       /* valor entre R$ 800 e R$ 9 000 */
       ROUND(RAND()*8200 + 800,2)                       AS valor_in,
       /* delay entre 1-5 min  */
       FLOOR(RAND()*5) + 1                              AS delay_min
FROM information_schema.tables
LIMIT 120;

/* ---------------- 2.1 INSERT Recebimento ----------------------- */
INSERT INTO transacoes
      (user_id, valor, tipo_transacao, forma_pagamento,
       data_hora, localizacao, banco,
       suspeita, motivo_suspeita, codigo, banco_origem, banco_destino)
SELECT 
       s.user_id,
       s.valor_in,
       'Recebimento',
       'Pix',
       s.ts_in,
       'São Paulo',
       u.banco,
       1,
       'Entrada seguida de saída ≤5 min',
       UUID(),
       'Outro Banco',
       u.banco                -- destino é o banco do usuário
  FROM tmp_smurf s
  JOIN usuarios u ON u.id = s.user_id;

/* ---------------- 2.2 INSERT Cash-Out -------------------------- */
INSERT INTO transacoes
      (user_id, valor, tipo_transacao, forma_pagamento,
       data_hora, localizacao, banco,
       suspeita, motivo_suspeita, codigo, banco_origem, banco_destino)
SELECT 
       s.user_id,
       s.valor_in - ROUND(RAND()*50,2),  -- valor quase igual, pequeno spread
       'Cash-Out',
       'Pix',
       s.ts_in + INTERVAL s.delay_min MINUTE,
       'São Paulo',
       u.banco,
       1,
       CONCAT('Cash-Out ',s.delay_min,' min após entrada'),
       UUID(),
       u.banco,
       'Outro Banco'
  FROM tmp_smurf s
  JOIN usuarios u ON u.id = s.user_id;

/* ================================================================
   3) Limpeza
   ================================================================ */
DROP TEMPORARY TABLE IF EXISTS tmp_smurf;

/* ================================================================
   4) Verificação rápida
   --------------------------------------------------------------- */
SELECT COUNT(*) AS recebs
  FROM transacoes
 WHERE tipo_transacao = 'Recebimento'
   AND motivo_suspeita LIKE 'Entrada seguida%';

SELECT COUNT(*) AS cash_outs
  FROM transacoes
 WHERE tipo_transacao = 'Cash-Out'
   AND motivo_suspeita LIKE 'Cash-Out % min após entrada';


/* ================================================================
   07) ALTERAÇÕES DE SENHAS MÚLTIPLAS  -----------======================================================================================================================================================
   ================================================================ */
   
   /* =================================================================
   0) Garantir que estamos no banco correto
   ================================================================= */
USE analise_transacoes;

/* =================================================================
   1) Range de usuários existentes
   ================================================================= */
SELECT MIN(id) INTO @U_MIN FROM usuarios;
SELECT MAX(id) INTO @U_MAX FROM usuarios;

/* =================================================================
   2) Sequência 1-5 (para multiplicar as trocas)
   ================================================================= */
DROP TEMPORARY TABLE IF EXISTS tmp_seq;
CREATE TEMPORARY TABLE tmp_seq (n TINYINT PRIMARY KEY);
INSERT INTO tmp_seq (n)
VALUES (1),(2),(3),(4),(5);

/* =================================================================
   3) Gera 30 usuários aleatórios × 5 trocas de senha cada
   ================================================================= */
DROP TEMPORARY TABLE IF EXISTS tmp_pw;
CREATE TEMPORARY TABLE tmp_pw AS
SELECT 
       u.id                               AS user_id,
       s.n                                AS seq,
       /* horário da troca – últimos 15 dias */
       NOW() - INTERVAL FLOOR(RAND()*360) HOUR  AS ts_change
  FROM (SELECT id FROM usuarios ORDER BY RAND() LIMIT 30) u
  JOIN tmp_seq s;

/* =================================================================
   4) Insere as 150 trocas em fatos_usuarios
   ================================================================= */
INSERT INTO fatos_usuarios
      (user_id, entidade, campo,
       valor_antigo, valor_novo, acao,
       descricao, data_hora)
SELECT 
       p.user_id,
       'usuarios',
       'senha',
       CONCAT('pwd',p.seq-1),          -- hash/placeholder antigo
       CONCAT('pwd',p.seq),            -- hash/placeholder novo
       'alterar_senha',
       CONCAT('Troca de senha #',p.seq),
       p.ts_change
  FROM tmp_pw p;

/* =================================================================
   5) (Opcional) Atualiza a coluna usuarios.senha
   ================================================================= */
UPDATE usuarios u
JOIN (
      SELECT user_id,
             MAX(seq)          AS max_seq,
             MAX(ts_change)    AS ts_last
        FROM tmp_pw
       GROUP BY user_id
     ) x ON x.user_id = u.id
SET u.senha = CONCAT('pwd',x.max_seq);

/* =================================================================
   6) Limpeza dos temporários
   ================================================================= */
DROP TEMPORARY TABLE IF EXISTS tmp_seq;
DROP TEMPORARY TABLE IF EXISTS tmp_pw;

/* =================================================================
   7) Verificação rápida
   ================================================================= */
SELECT user_id,
       COUNT(*) AS qtd_trocas
  FROM fatos_usuarios
 WHERE campo = 'senha'
   AND data_hora >= NOW() - INTERVAL 15 DAY
 GROUP BY user_id
 ORDER BY qtd_trocas DESC
 LIMIT 10;

/* ================================================================
   08) TOP 5 MAIORES ENTRADAS  -----------======================================================================================================================================================
   ================================================================ */
   
   /* ================================================================
   0) Banco alvo
   ================================================================ */
USE analise_transacoes;

/* ================================================================
   1) Descobrir range de usuários
   ================================================================ */
SELECT MIN(id) INTO @U_MIN FROM usuarios;
SELECT MAX(id) INTO @U_MAX FROM usuarios;

/* ================================================================
   2) Inserir 12 entradas atípicas (≥ 20k) nos últimos 10 dias
   --------------------------------------------------------------- */
INSERT INTO transacoes
      (user_id, valor, tipo_transacao, forma_pagamento,
       data_hora, localizacao, banco,
       suspeita, motivo_suspeita, codigo, banco_origem, banco_destino)
SELECT
       FLOOR(RAND()*(@U_MAX-@U_MIN+1))+@U_MIN       AS user_id,
       -- valores de 20.000 a 120.000
       ROUND(RAND()*100000 + 20000, 2)              AS valor,
       IF(RAND()<0.5,'Recebimento','Cash-In')       AS tipo_transacao,
       'TED',                                       -- entrada alta costuma ser TED/DOC
       NOW() - INTERVAL FLOOR(RAND()*240) HOUR      AS data_hora,   -- últimos 10 dias
       'São Paulo',
       (SELECT banco FROM usuarios WHERE id=user_id),
       1,                                           -- já marcamos como suspeito
       'Entrada atípica > R$20k',
       UUID(),
       'Outro Banco',
       (SELECT banco FROM usuarios WHERE id=user_id);

/* ================================================================
   3) Verificação rápida
   --------------------------------------------------------------- */
SELECT tipo_transacao,
       COUNT(*)   AS qtd,
       MAX(valor) AS max_valor,
       MIN(data_hora) AS primeiro,
       MAX(data_hora) AS ultimo
  FROM transacoes
 WHERE (tipo_transacao IN ('Recebimento','Cash-In'))
   AND data_hora >= NOW() - INTERVAL 10 DAY
   AND valor >= 20000
 GROUP BY tipo_transacao;

/* ================================================================
     09) Radar de Risco – popular compras_online + saldo_pendente -----------======================================================================================================================================================
   ================================================================ */
   
   USE analise_transacoes;

/* 1) Usuários que já tiveram alteração de perfil ----------------- */
DROP TEMPORARY TABLE IF EXISTS tmp_usr_radar;
CREATE TEMPORARY TABLE tmp_usr_radar AS
SELECT DISTINCT user_id
  FROM fatos_usuarios
 WHERE campo IN ('email','telefone')
 ORDER BY RAND()
 LIMIT 40;

/* 2) Sequência 1-8 (8 compras por usuário) ----------------------- */
DROP TEMPORARY TABLE IF EXISTS tmp_seq8;
CREATE TEMPORARY TABLE tmp_seq8 (n INT PRIMARY KEY);
INSERT INTO tmp_seq8 (n) VALUES (1),(2),(3),(4),(5),(6),(7),(8);

/* 3) Gerar compras (tmp_buy) ------------------------------------- */
DROP TEMPORARY TABLE IF EXISTS tmp_buy;
CREATE TEMPORARY TABLE tmp_buy AS
SELECT
    u.user_id,
    UUID()                         AS codigo_tx,
    NOW() - INTERVAL FLOOR(RAND()*720) HOUR  AS ts_buy,   -- últimos 30 dias
    ROUND(RAND()*1200 + 100,2)     AS valor,
    -- categorias simples
    ELT(FLOOR(RAND()*5)+1,
        'Eletrônicos','Vestuário','Casa','Games','Mercado') AS categoria,
    ELT(FLOOR(RAND()*5)+1,
        'Amazon','Magazine Luiza','Mercado Livre',
        'Kabum','Steam')           AS loja
  FROM tmp_usr_radar u
  JOIN tmp_seq8 s;

/* 4) Inserir transações ‘Compra’ --------------------------------- */
INSERT INTO transacoes
      (user_id, valor, tipo_transacao, forma_pagamento,
       data_hora, localizacao, banco,
       suspeita, motivo_suspeita, codigo,
       banco_origem, banco_destino)
SELECT
       b.user_id,
       b.valor,
       'Compra',
       'Cartão',
       b.ts_buy,
       'São Paulo',
       (SELECT banco FROM usuarios WHERE id=b.user_id),
       0,                         -- não precisa marcar como suspeita
       NULL,
       b.codigo_tx,
       (SELECT banco FROM usuarios WHERE id=b.user_id),
       (SELECT banco FROM usuarios WHERE id=b.user_id)
  FROM tmp_buy b;

/* 5) Inserir compras_online -------------------------------------- */
INSERT INTO compras_online
      (user_id, codigo_tx, loja, categoria,
       qtd, valor_unit, valor_total, data_hora, status)
SELECT
       b.user_id,
       b.codigo_tx,
       b.loja,
       b.categoria,
       1,
       b.valor,
       b.valor,
       b.ts_buy,
       'Pago'
  FROM tmp_buy b;

/* 6) Atualizar saldo_pendente ------------------------------------ */
UPDATE usuarios u
JOIN tmp_usr_radar r ON r.user_id = u.id
SET u.saldo_pendente = ROUND(RAND()*8500 + 500,2);

/* 7) Limpeza de temporários -------------------------------------- */
DROP TEMPORARY TABLE IF EXISTS tmp_seq8;
DROP TEMPORARY TABLE IF EXISTS tmp_buy;
DROP TEMPORARY TABLE IF EXISTS tmp_usr_radar;

/* 8) Checagem rápida --------------------------------------------- */
SELECT 'Compras inseridas', COUNT(*) AS total
  FROM compras_online
 WHERE data_hora >= NOW() - INTERVAL 30 DAY;

SELECT 'Usuários com saldo_pendente', COUNT(*)
  FROM usuarios
 WHERE saldo_pendente IS NOT NULL;
 
 /* ================================================================
     10) 🔑 Alterações de senha múltiplas vezes -----------======================================================================================================================================================
   ================================================================ */
   
USE analise_transacoes;

-- 1 ▪ Corrigir linhas existentes ------------------------------------
UPDATE fatos_usuarios
   SET acao = 'Alterar senha'
 WHERE campo = 'senha'
   AND acao  = 'alterar_senha';

-- 2 ▪ Inserir novos eventos (40 usuários × 4 trocas) ----------------
/* 2.1  prepara sequência 1-4 */
DROP TEMPORARY TABLE IF EXISTS tmp_seq4;
CREATE TEMPORARY TABLE tmp_seq4 (n TINYINT PRIMARY KEY);
INSERT INTO tmp_seq4 VALUES (1),(2),(3),(4);

/* 2.2  escolhe 40 usuários aleatórios */
DROP TEMPORARY TABLE IF EXISTS tmp_pwd2;
CREATE TEMPORARY TABLE tmp_pwd2 AS
SELECT id AS user_id
  FROM usuarios
 ORDER BY RAND()
 LIMIT 40;

/* 2.3  gera as 160 trocas (últimos 60 dias) */
INSERT INTO fatos_usuarios
      (user_id, entidade, campo,
       valor_antigo, valor_novo,
       acao, descricao, data_hora)
SELECT 
       u.user_id,
       'usuarios',
       'senha',
       CONCAT('hash',s.n-1),
       CONCAT('hash',s.n),
       'Alterar senha',
       CONCAT('Troca de senha #',s.n),
       NOW() - INTERVAL FLOOR(RAND()*1440) HOUR   -- até 60 dias
  FROM tmp_pwd2 u
  JOIN tmp_seq4 s;

/* limpeza temporários */
DROP TEMPORARY TABLE IF EXISTS tmp_seq4;
DROP TEMPORARY TABLE IF EXISTS tmp_pwd2;

/* 3 ▪ Verificação rápida ------------------------------------------ */
SELECT 'Linhas campo=senha, acao=\"Alterar senha\"', COUNT(*)
  FROM fatos_usuarios
 WHERE campo='senha' AND acao='Alterar senha';
 
 
 
 /* ================================================================
     11) Script para simular pares “Recebimento → Saída” em até 5 minutos -----------======================================================================================================================================================
   ================================================================ */
   
   -- Script para simular pares “Recebimento → Saída” em até 5 minutos
USE analise_transacoes;

-- 1) Descobre intervalo de usuários existentes
SELECT MIN(id) INTO @USR_MIN FROM usuarios;
SELECT MAX(id) INTO @USR_MAX FROM usuarios;

-- 2) Cria tabela temporária com 100 pares aleatórios
DROP TEMPORARY TABLE IF EXISTS tmp_fast_pairs;
CREATE TEMPORARY TABLE tmp_fast_pairs AS
SELECT
  FLOOR(RAND() * (@USR_MAX - @USR_MIN + 1)) + @USR_MIN AS user_id,
  -- Horário base: em qualquer momento nos últimos 7 dias
  NOW() - INTERVAL FLOOR(RAND() * 7) DAY 
          - INTERVAL FLOOR(RAND() * 1440) MINUTE    AS ts_base,
  -- Valor de entrada entre R$100 e R$1.100
  ROUND(RAND() * 1000 + 100, 2)                    AS val_in,
  -- Delay de saída entre 0 e 5 minutos
  FLOOR(RAND() * 6)                                AS delay_min
FROM information_schema.columns
LIMIT 100;

-- 3) Insere as transações de “Recebimento”
INSERT INTO transacoes (
  user_id, valor, tipo_transacao, forma_pagamento,
  data_hora, banco, suspeita, codigo
)
SELECT
  f.user_id,
  f.val_in,
  'Recebimento',
  'Pix',
  f.ts_base,
  u.banco,
  0,
  UUID()
FROM tmp_fast_pairs f
JOIN usuarios u ON u.id = f.user_id;

-- 4) Insere as transações de “Saída” até 5 minutos depois
INSERT INTO transacoes (
  user_id, valor, tipo_transacao, forma_pagamento,
  data_hora, banco, suspeita, codigo
)
SELECT
  f.user_id,
  -- pequeno spread na saída
  ROUND(f.val_in * (0.98 + RAND()*0.04), 2)         AS val_out,
  'Saída',
  'Pix',
  f.ts_base + INTERVAL f.delay_min MINUTE,
  u.banco,
  0,
  UUID()
FROM tmp_fast_pairs f
JOIN usuarios u ON u.id = f.user_id;

-- 5) Limpeza da tabela temporária
DROP TEMPORARY TABLE IF EXISTS tmp_fast_pairs;

-- 6) Verificação rápida: quantos pares foram gerados
SELECT
  SUM(CASE WHEN tipo_transacao = 'Recebimento' THEN 1 ELSE 0 END) AS total_recebimentos,
  SUM(CASE WHEN tipo_transacao = 'Saída'       THEN 1 ELSE 0 END) AS total_saidas,
  MIN(data_hora)           AS primeiro_evento,
  MAX(data_hora)           AS ultimo_evento
FROM transacoes
WHERE data_hora >= NOW() - INTERVAL 8 DAY
  AND (tipo_transacao IN ('Recebimento','Saída'));
