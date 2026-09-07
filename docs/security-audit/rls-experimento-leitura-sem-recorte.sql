-- =====================================================================
-- EXPERIMENTO 2: quem consegue ler o banco INTEIRO sob RLS
--
-- Complementa `rls-experimento.sql` (os 8 ataques contra a política) e
-- responde ao item que a seção 7 da proposta deixou em aberto: o backup
-- automático e os seeds do boot precisam ler sem recorte de fazenda —
-- como conceder isso sem criar um BYPASSRLS de propósito geral.
--
-- COMO RODAR (Postgres descartável, NÃO em produção):
--   psql -U postgres -f rls-experimento-leitura-sem-recorte.sql
--
-- Medido em PostgreSQL 16.13 em 07/09/2026. Os "ESPERADO" abaixo são o que
-- de fato saiu, não o que se imaginava que sairia.
-- =====================================================================

\pset pager off

DROP DATABASE IF EXISTS exp_leitura;
DROP ROLE IF EXISTS cowdata_dono;
DROP ROLE IF EXISTS cowdata_app;
DROP ROLE IF EXISTS cowdata_backup;
DROP ROLE IF EXISTS cowdata_bypass;

CREATE ROLE cowdata_dono   LOGIN NOSUPERUSER;  -- dono das tabelas (migração/seeds)
CREATE ROLE cowdata_app    LOGIN NOSUPERUSER;  -- a aplicação, por requisição
CREATE ROLE cowdata_backup LOGIN NOSUPERUSER;  -- hipótese: leitor por política
CREATE ROLE cowdata_bypass LOGIN NOSUPERUSER BYPASSRLS;  -- hipótese: BYPASSRLS

CREATE DATABASE exp_leitura OWNER cowdata_dono;
\c exp_leitura


-- ---------------------------------------------------------------------
-- Cenário: 3 linhas — fazenda 1, fazenda 2 e uma de catálogo global.
-- ---------------------------------------------------------------------
SET ROLE cowdata_dono;
CREATE TABLE sanidade (id serial PRIMARY KEY, fazenda_id int, descricao text);
INSERT INTO sanidade (fazenda_id, descricao)
VALUES (1, 'mastite f1'), (2, 'carrapato f2'), (NULL, 'catalogo global');

GRANT SELECT, INSERT, UPDATE, DELETE ON sanidade TO cowdata_app, cowdata_backup, cowdata_bypass;
GRANT USAGE, SELECT ON SEQUENCE sanidade_id_seq TO cowdata_app, cowdata_backup;

ALTER TABLE sanidade ENABLE ROW LEVEL SECURITY;
CREATE POLICY isolamento ON sanidade TO cowdata_app
  USING      (fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int)
  WITH CHECK (fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int);
RESET ROLE;


-- =====================================================================
-- 1. O achado que muda a gravidade: RLS não dá erro, dá VAZIO.
-- =====================================================================
-- ESPERADO: 0 linhas, e NENHUMA exceção. É por isso que o backup
-- automático gravaria `sucesso=True` com um ZIP de CSVs só de cabeçalho:
-- `executar_backup_se_necessario` só marca falha quando há exceção.
SET ROLE cowdata_app;
SELECT 'app sem contexto' AS quem, count(*) FROM sanidade;
RESET ROLE;


-- =====================================================================
-- 2. As quatro saídas para "ler o banco inteiro", lado a lado.
-- =====================================================================

-- (a) a própria aplicação, com contexto — ESPERADO: 1 linha (só a da f1)
SET ROLE cowdata_app;
BEGIN; SET LOCAL app.fazenda_id = '1';
  SELECT 'app f1 com contexto' AS quem, count(*) FROM sanidade;
COMMIT;
RESET ROLE;

-- (b) dono das tabelas, COM force — ESPERADO: 0 linhas (não serve p/ backup)
SET ROLE cowdata_dono;
ALTER TABLE sanidade FORCE ROW LEVEL SECURITY;
SELECT 'dono com force' AS quem, count(*) FROM sanidade;

-- ...e o force não segura o próprio dono: ESPERADO: aceito, e volta a 3 linhas
ALTER TABLE sanidade NO FORCE ROW LEVEL SECURITY;
SELECT 'dono depois de NO FORCE' AS quem, count(*) FROM sanidade;
ALTER TABLE sanidade FORCE ROW LEVEL SECURITY;
RESET ROLE;

-- (c) role de backup com política de leitura sem recorte
SET ROLE cowdata_dono;
CREATE POLICY backup_le_tudo ON sanidade FOR SELECT TO cowdata_backup USING (true);
RESET ROLE;

SET ROLE cowdata_backup;
SELECT 'backup com politica SELECT' AS quem, count(*) FROM sanidade;  -- ESPERADO: 3
-- e a escrita fica contida — ESPERADO: UPDATE 0, DELETE 0, INSERT com erro
UPDATE sanidade SET descricao = 'adulterado' WHERE id = 1;
DELETE FROM sanidade WHERE id = 2;
INSERT INTO sanidade (fazenda_id, descricao) VALUES (9, 'inserido pelo backup');
RESET ROLE;

-- (d) role com BYPASSRLS — ESPERADO: 3 linhas, e escrita sem limite nenhum
SET ROLE cowdata_bypass;
SELECT 'bypassrls' AS quem, count(*) FROM sanidade;
RESET ROLE;


-- =====================================================================
-- 3. O custo escondido da opção (c): tabela nova sem política.
-- =====================================================================
SET ROLE cowdata_dono;
CREATE TABLE tabela_nova (id serial PRIMARY KEY, fazenda_id int, valor text);
INSERT INTO tabela_nova (fazenda_id, valor) VALUES (1, 'a'), (2, 'b');
GRANT SELECT ON tabela_nova TO cowdata_app, cowdata_backup, cowdata_bypass;
ALTER TABLE tabela_nova ENABLE ROW LEVEL SECURITY;
CREATE POLICY isolamento ON tabela_nova TO cowdata_app
  USING (fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int);
RESET ROLE;

-- ESPERADO: 0 — o backup fica cego nessa tabela, sem erro nenhum. Depende de
-- alguém lembrar de criar uma política por tabela nova, para sempre.
SET ROLE cowdata_backup; SELECT 'backup na tabela nova' AS quem, count(*) FROM tabela_nova; RESET ROLE;
-- ESPERADO: 2 — BYPASSRLS cobre tabela nova sozinho (e é esse o seu perigo).
SET ROLE cowdata_bypass; SELECT 'bypassrls na tabela nova' AS quem, count(*) FROM tabela_nova; RESET ROLE;


-- =====================================================================
-- 4. O desenho recomendado: RLS ligado, SEM force.
--    Backup e seeds pela conexão de dono; nenhum role BYPASSRLS existe.
-- =====================================================================
SET ROLE cowdata_dono;
ALTER TABLE sanidade    NO FORCE ROW LEVEL SECURITY;
ALTER TABLE tabela_nova NO FORCE ROW LEVEL SECURITY;

-- o seed do boot grava catálogo global sem contexto — ESPERADO: aceito
INSERT INTO sanidade (fazenda_id, descricao) VALUES (NULL, 'seed de catalogo global');
SELECT 'dono le tudo'        AS quem, count(*) FROM sanidade;     -- ESPERADO: 4
SELECT 'dono le tabela nova' AS quem, count(*) FROM tabela_nova;  -- ESPERADO: 2
RESET ROLE;

-- e a aplicação continua contida do mesmo jeito
SET ROLE cowdata_app;
BEGIN; SET LOCAL app.fazenda_id = '1';
  SELECT 'app f1' AS quem, count(*) FROM sanidade;                -- ESPERADO: 1
  -- ESPERADO: ERROR: new row violates row-level security policy
  INSERT INTO sanidade (fazenda_id, descricao) VALUES (2, 'invasao');
COMMIT;
RESET ROLE;
