-- =====================================================================
-- Os dois achados que mudaram o plano das FKs compostas (etapa 2 do RLS).
--
-- COMO RODAR (Postgres descartável, NÃO em produção):
--   psql -U postgres -f fks-compostas-experimento.sql
--
-- Medido em PostgreSQL 16.15 em 08/09/2026. Os "ESPERADO" são o que de fato
-- saiu — inclusive os dois que contrariam o plano original.
-- =====================================================================

\pset pager off

DROP DATABASE IF EXISTS exp_fk;
CREATE DATABASE exp_fk;
\c exp_fk

-- Pai e filha como o schema é HOJE: `fazenda_id` aceita nulo nos dois.
CREATE TABLE lote   (id serial PRIMARY KEY, fazenda_id int, nome text);
CREATE TABLE animal (id serial PRIMARY KEY, fazenda_id int, lote_id int, numero text);

INSERT INTO lote (id, fazenda_id, nome) VALUES
  (10, 1,    'lote da fazenda 1'),
  (20, 2,    'lote da fazenda 2'),
  (30, NULL, 'lote de catálogo global');

ALTER TABLE lote ADD CONSTRAINT lote_id_fazenda_uk UNIQUE (id, fazenda_id);
ALTER TABLE animal ADD CONSTRAINT animal_lote_fk
  FOREIGN KEY (lote_id, fazenda_id) REFERENCES lote(id, fazenda_id);


\echo '=== 1. o que a FK composta existe para fechar ==='
-- ESPERADO: ERRO. Key (lote_id, fazenda_id)=(20, 1) is not present in table "lote".
INSERT INTO animal (fazenda_id, lote_id, numero) VALUES (1, 20, 'aponta pra fazenda 2');

\echo '=== 2. o caso legítimo, que precisa continuar funcionando ==='
-- ESPERADO: INSERT 0 1
INSERT INTO animal (fazenda_id, lote_id, numero) VALUES (1, 10, 'aponta pro proprio lote');


\echo '=== 3. ACHADO 2: filha com fazenda_id NULO fura a FK composta ==='
-- ESPERADO: INSERT 0 1 — e é o problema. MATCH SIMPLE (o padrão do SQL): se
-- QUALQUER coluna da chave estrangeira é nula, a restrição não é verificada.
-- A FK composta só fecha o furo depois de `fazenda_id` virar NOT NULL.
INSERT INTO animal (fazenda_id, lote_id, numero) VALUES (NULL, 20, 'orfa apontando pra fazenda 2');


\echo '=== 4. ACHADO 1: a filha da fazenda 1 NAO consegue usar o catalogo global ==='
-- ESPERADO: ERRO. Key (lote_id, fazenda_id)=(30, 1) is not present in table "lote".
-- A chave do pai global é (30, NULL) e NULL não casa com 1. É por isso que as
-- 31 FKs que apontam para tabela de catálogo global NÃO podem virar compostas:
-- quebrariam a Farmácia, a biblioteca de alimentos e o sanitário.
INSERT INTO animal (fazenda_id, lote_id, numero) VALUES (1, 30, 'usa item do catalogo global');


\echo '=== estado final: entrou o legitimo e entrou a orfa; o resto foi barrado ==='
SELECT numero, fazenda_id, lote_id FROM animal ORDER BY id;


-- =====================================================================
-- OS NÚMEROS, contra o esquema real.
--
-- Rode o bloco abaixo num banco onde `SQLModel.metadata.create_all` tenha
-- criado o schema do projeto:
--
--   python -c "from sqlalchemy import create_engine; import fazenda.models as m; \
--              m.SQLModel.metadata.create_all(create_engine('postgresql://.../fk_real'))"
--
-- Medido em 08/09/2026: 434 FKs no total, 161 entre tabelas que ambas têm
-- fazenda_id, das quais 31 apontam para catálogo global (8 tabelas pai) e 130
-- podem virar compostas, exigindo 53 UNIQUE (id, fazenda_id) novas.
-- =====================================================================
--
-- WITH cols AS (
--   SELECT table_name FROM information_schema.columns
--   WHERE table_schema='public' AND column_name='fazenda_id'
-- ), catalogo AS (
--   SELECT unnest(ARRAY['principio_ativo','doenca','indicacao_terapeutica','medicamento_comercial',
--     'categoria_estoque','finalidade_estoque','unidade_estoque','unidade_embalagem_estoque',
--     'unidade_medida_embalagem_estoque','laboratorio','categoria_medicamento',
--     'classificacao_medicamento_cad','servico_cadastro','parametro_fazenda',
--     'medicamento_principio_ativo','alimento_nutricional','medicamento_categoria',
--     'medicamento_classificacao']) AS t
-- ), fks AS (
--   SELECT c.conrelid::regclass::text AS filha, c.confrelid::regclass::text AS pai
--   FROM pg_constraint c
--   WHERE c.contype='f' AND c.connamespace='public'::regnamespace
--     AND c.conrelid::regclass::text  IN (SELECT table_name FROM cols)
--     AND c.confrelid::regclass::text IN (SELECT table_name FROM cols)
-- )
-- SELECT
--   count(*)                                                          AS total_161,
--   count(*) FILTER (WHERE pai IN (SELECT t FROM catalogo))            AS para_catalogo_global,
--   count(*) FILTER (WHERE pai NOT IN (SELECT t FROM catalogo))        AS podem_virar_compostas,
--   count(DISTINCT pai) FILTER (WHERE pai NOT IN (SELECT t FROM catalogo)) AS uniques_novas,
--   count(*) FILTER (WHERE filha = pai)                                AS auto_referencia
-- FROM fks;
