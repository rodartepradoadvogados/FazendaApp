-- =====================================================================
-- ROTEIRO REPRODUZÍVEL — prova o comportamento da política de RLS
-- proposta em docs/security-audit/rls-proposta.md.
--
-- RODE CONTRA UM POSTGRES DESCARTÁVEL. Nunca contra produção: o script
-- cria e apaga tabelas e roles.
--
-- Roda inteiro, de uma vez, num psql só (testado no PostgreSQL 16):
--
--     export PATH=/usr/lib/postgresql/16/bin:$PATH
--     initdb -D /tmp/pgrls -U postgres --auth=trust
--     pg_ctl -D /tmp/pgrls -o '-p 55432 -k /tmp' -l /tmp/pgrls/log start -w
--     psql -h /tmp -p 55432 -U postgres -d postgres -f rls-experimento.sql
--
-- Não é preciso reconectar para trocar de usuário: o script usa `SET ROLE`
-- para virar o role da aplicação na hora dos ataques, e o RLS se aplica ao
-- role EFETIVO (medido — ver a nota antes da seção de ataques).
-- =====================================================================

-- ---------- cenário: as DUAS naturezas de tabela do sistema ----------
DROP TABLE IF EXISTS sanidade, principio_ativo CASCADE;

-- (1) DADO DA FAZENDA — aqui fazenda_id nulo é ÓRFÃO e não deve passar
CREATE TABLE sanidade (id serial PRIMARY KEY, descricao text, fazenda_id int);
INSERT INTO sanidade (descricao, fazenda_id) VALUES
  ('mastite da fazenda 1', 1), ('mastite da fazenda 2', 2), ('ORFÃ sem dono', NULL);

-- (2) CATÁLOGO GLOBAL — aqui fazenda_id nulo é LEGÍTIMO (é de todo mundo)
CREATE TABLE principio_ativo (id serial PRIMARY KEY, nome text, fazenda_id int);
INSERT INTO principio_ativo (nome, fazenda_id) VALUES
  ('Oxitetraciclina (catálogo)', NULL), ('Fórmula própria da 1', 1), ('Fórmula própria da 2', 2);

-- ---------- o role da aplicação: NÃO superusuário, NÃO dono ----------
-- Este é o ponto que decide tudo (ver seção 3 da proposta): superusuário
-- ignora RLS mesmo com FORCE. Se a aplicação conectar como `postgres`, a
-- política inteira vira decoração.
DROP ROLE IF EXISTS cowdata_app;
CREATE ROLE cowdata_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cowdata_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cowdata_app;

-- ---------- as DUAS políticas ----------
-- `current_setting('app.fazenda_id', true)` devolve NULL (em vez de erro)
-- quando a variável não foi setada. Como `coluna = NULL` nunca é verdadeiro
-- em SQL, sem contexto a política NEGA TUDO — seguro por omissão.
-- O NULLIF trata string vazia como não-setado.

-- (1) dado da fazenda: só a própria fazenda. Órfão não passa por ninguém.
ALTER TABLE sanidade ENABLE ROW LEVEL SECURITY;
ALTER TABLE sanidade FORCE ROW LEVEL SECURITY;   -- FORCE também contém o dono da tabela
CREATE POLICY isolamento_fazenda ON sanidade
  USING      (fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int)
  WITH CHECK (fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int);

-- (2) catálogo global: a própria fazenda MAIS as linhas globais na LEITURA;
--     na ESCRITA (WITH CHECK) segue estrito — o tenant nunca grava no
--     catálogo de todo mundo, isso é papel do Painel CowData.
ALTER TABLE principio_ativo ENABLE ROW LEVEL SECURITY;
ALTER TABLE principio_ativo FORCE ROW LEVEL SECURITY;
CREATE POLICY catalogo_global ON principio_ativo
  USING      (fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int
              OR fazenda_id IS NULL)
  WITH CHECK (fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int);


-- =====================================================================
-- OS ATAQUES
--
-- `SET ROLE cowdata_app` abaixo NÃO é detalhe de arrumação: sem ele, tudo
-- daqui para baixo roda como superusuário e TODOS os ataques PASSAM — a
-- invasão é gravada, o órfão é criado, o UPDATE muda a dona. Quem colar só
-- os ataques numa sessão de superusuário vai concluir, erradamente, que a
-- política não funciona. Ela funciona; superusuário é que a ignora.
-- =====================================================================
SET ROLE cowdata_app;
SELECT current_user AS rodando_como;   -- tem que dizer cowdata_app

-- ATAQUE 1 — ler sem contexto de fazenda nenhum.
-- ESPERADO: sanidade = 0 linhas; principio_ativo = 1 (só a global, que é
-- pública por definição).
SELECT 'sanidade' AS t, count(*) FROM sanidade
UNION ALL SELECT 'principio_ativo', count(*) FROM principio_ativo;

-- ATAQUE 2 — a fazenda 1 tenta enxergar a fazenda 2.
-- ESPERADO: só "mastite da fazenda 1", "Fórmula própria da 1" e o catálogo.
BEGIN; SET LOCAL app.fazenda_id = '1';
  SELECT 'sanidade' AS tabela, descricao AS linha FROM sanidade
  UNION ALL SELECT 'principio_ativo', nome FROM principio_ativo ORDER BY 1,2;
COMMIT;

-- ATAQUE 3 — a fazenda 1 tenta GRAVAR na fazenda 2.
-- ESPERADO: ERROR: new row violates row-level security policy
BEGIN; SET LOCAL app.fazenda_id = '1';
  INSERT INTO sanidade (descricao, fazenda_id) VALUES ('invasao', 2);
COMMIT;

-- ATAQUE 4 — a fazenda 1 tenta MUDAR a dona de um registro seu.
-- ESPERADO: mesmo erro. O WITH CHECK vale para a linha DEPOIS do UPDATE.
BEGIN; SET LOCAL app.fazenda_id = '1';
  UPDATE sanidade SET fazenda_id = 2 WHERE fazenda_id = 1;
COMMIT;

-- ATAQUE 5 — a fazenda 1 tenta criar um ÓRFÃO novo.
-- ESPERADO: mesmo erro. É a política fechando a torneira que gerou os
-- órfãos que existem hoje.
BEGIN; SET LOCAL app.fazenda_id = '1';
  INSERT INTO sanidade (descricao, fazenda_id) VALUES ('novo orfao', NULL);
COMMIT;

-- ATAQUE 6 — contexto forjado com injeção.
-- ESPERADO: ERROR: invalid input syntax for type integer: "1 OR true".
-- O cast ::int é a defesa: a variável nunca vira pedaço de SQL.
BEGIN; SET LOCAL app.fazenda_id = '1 OR true';
  SELECT count(*) FROM sanidade;
COMMIT;

-- ATAQUE 7 — DELETE da fazenda 1 mirando linha da fazenda 2.
-- ESPERADO: DELETE 0 — a linha alheia nem é enxergada para ser apagada.
BEGIN; SET LOCAL app.fazenda_id = '1';
  DELETE FROM sanidade WHERE descricao = 'mastite da fazenda 2';
ROLLBACK;

-- ATAQUE 8 — `SET` sem `LOCAL` vaza entre requisições pelo pool.
-- ESPERADO: a segunda consulta, que não seta nada, HERDA o contexto da
-- primeira. É um vazamento entre inquilinos criado pela própria proteção —
-- por isso a implementação precisa de SET LOCAL, sempre.
BEGIN; SET app.fazenda_id = '1';       -- sem LOCAL: vale até o fim da CONEXÃO
  SELECT descricao FROM sanidade;
COMMIT;
SELECT current_setting('app.fazenda_id', true) AS contexto_herdado,
       descricao AS linha_vazada FROM sanidade;
RESET app.fazenda_id;


-- =====================================================================
-- O RESULTADO QUE DECIDE A VIABILIDADE — de volta ao superusuário.
-- =====================================================================
RESET ROLE;

-- ESPERADO: as 3 linhas originais, de TODAS as fazendas, inclusive a órfã,
-- com a política ativa e com FORCE. Superusuário ignora RLS.
-- É por isso que a aplicação NÃO pode conectar como `postgres`.
SELECT current_user AS rodando_como, usesuper AS eh_superusuario
FROM pg_user WHERE usename = current_user;
SELECT descricao, fazenda_id FROM sanidade ORDER BY id;
