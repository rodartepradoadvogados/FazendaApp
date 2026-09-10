-- =====================================================================
-- VALIDAÇÃO DO RLS NO STAGING — item 4 do roteiro (docs/security-audit/
-- roteiro-seguranca.md). Reproduz os ataques da seção 10 de
-- rls-proposta.md, mas contra o schema REAL do Staging (não um Postgres
-- descartável como rls-experimento.sql) — por isso NENHUM DDL, NENHUM
-- DROP/CREATE, e TODO dado de teste é desfeito no final com ROLLBACK.
-- Zero persistência.
--
-- Por que não usar rls-experimento.sql direto: ele faz DROP TABLE/CREATE
-- TABLE de propósito (é para banco descartável), e um dos nomes que usa —
-- `sanidade` — é tabela real de produção. Rodar aquele script contra o
-- Staging apagaria dado de verdade.
--
-- Tabela usada aqui: `estoque` — "dado da fazenda" (não é catálogo
-- global: conferido contra o ARRAY de rls-migracao-proposta.sql), só
-- precisa de `nome` (+ `atualizado_em`, NOT NULL sem default no banco)
-- além de `fazenda_id`. Já tem dado real na fazenda 1 — o teste usa só
-- linhas próprias, marcadas com nome inconfundível
-- (__RLS_TESTE_VALIDACAO...), nunca as reais.
--
-- TESTADO ANTES localmente (10/09/2026), contra um Postgres descartável
-- com o mesmo schema (create_all), o mesmo role cowdata_app (mesmos
-- GRANTs do roteiro railway-staging-passos.md) e o mesmo DDL de RLS —
-- os 7 ataques bateram com o esperado antes deste script encostar no
-- Staging de verdade.
--
-- Ataque 8 (SET sem LOCAL vazando entre requisições) fica de fora aqui
-- de propósito: provar isso exigiria um COMMIT real no meio do roteiro,
-- e esta validação não deve deixar nada gravado no Staging. Já está
-- provado do jeito certo em
-- backend/tests/test_contexto_fazenda_sessao.py::
-- test_contexto_reaplicado_apos_commit_no_meio_da_sessao, contra
-- Postgres de verdade, na suíte automatizada (CI).
--
-- Rodar via railway-agent (a sessão não tem saída TCP direta), pela
-- mesma DATABASE_URL_MANUTENCAO de sempre:
--
--     psql "$DATABASE_URL_MANUTENCAO" -f rls-validacao-staging.sql
-- =====================================================================

BEGIN;

-- Dado de teste, como dono (ignora RLS: sem FORCE, e é o dono das
-- tabelas) — uma linha em cada fazenda real.
INSERT INTO estoque (fazenda_id, nome, atualizado_em) VALUES
  (1, '__RLS_TESTE_VALIDACAO_F1__', now()),
  (2, '__RLS_TESTE_VALIDACAO_F2__', now());

-- Daqui para baixo, tudo roda como a aplicação roda de verdade.
SET ROLE cowdata_app;
SELECT current_user AS rodando_como;

-- ATAQUE 1 — ler sem contexto de fazenda nenhum.
-- ESPERADO: 0 (RLS nega tudo por omissão).
SELECT count(*) AS ataque_1_sem_contexto
FROM estoque WHERE nome LIKE '__RLS_TESTE_VALIDACAO%';

-- ATAQUE 2 — fazenda 1 tenta ler o dado da fazenda 2.
-- ESPERADO: só a linha da fazenda 1.
SET LOCAL app.fazenda_id = '1';
SELECT fazenda_id, nome AS ataque_2_leitura_com_contexto_1
FROM estoque WHERE nome LIKE '__RLS_TESTE_VALIDACAO%';

-- ATAQUE 3 — fazenda 1 tenta GRAVAR em nome da fazenda 2.
-- ESPERADO: ERROR: new row violates row-level security policy
SAVEPOINT antes_ataque_3;
INSERT INTO estoque (fazenda_id, nome, atualizado_em) VALUES (2, '__RLS_TESTE_INVASAO__', now());
ROLLBACK TO SAVEPOINT antes_ataque_3;

-- ATAQUE 4 — fazenda 1 tenta MUDAR a dona do próprio registro para a
-- fazenda 2. ESPERADO: mesmo erro (WITH CHECK vale para a linha DEPOIS
-- do UPDATE).
SAVEPOINT antes_ataque_4;
UPDATE estoque SET fazenda_id = 2 WHERE nome = '__RLS_TESTE_VALIDACAO_F1__';
ROLLBACK TO SAVEPOINT antes_ataque_4;

-- ATAQUE 5 — fazenda 1 tenta criar um registro ÓRFÃO (fazenda_id NULL).
-- ESPERADO: mesmo erro.
SAVEPOINT antes_ataque_5;
INSERT INTO estoque (fazenda_id, nome, atualizado_em) VALUES (NULL, '__RLS_TESTE_ORFAO__', now());
ROLLBACK TO SAVEPOINT antes_ataque_5;

-- ATAQUE 6 — contexto forjado com injeção.
-- ESPERADO: ERROR: invalid input syntax for type integer.
SAVEPOINT antes_ataque_6;
SET LOCAL app.fazenda_id = '1 OR true';
SELECT count(*) FROM estoque WHERE nome LIKE '__RLS_TESTE_VALIDACAO%';
ROLLBACK TO SAVEPOINT antes_ataque_6;

-- (o rollback acima também desfaz o SET LOCAL forjado; o savepoint foi
-- criado com o contexto '1' do ataque 2 em vigor, então já volta sozinho
-- — reafirma só por clareza.)
SET LOCAL app.fazenda_id = '1';

-- ATAQUE 7 — DELETE da fazenda 1 mirando a linha da fazenda 2.
-- ESPERADO: DELETE 0 — a linha alheia nem é enxergada para ser apagada.
SAVEPOINT antes_ataque_7;
DELETE FROM estoque WHERE nome = '__RLS_TESTE_VALIDACAO_F2__';
ROLLBACK TO SAVEPOINT antes_ataque_7;

RESET ROLE;

-- confirma que o DONO viu as duas linhas de teste o tempo todo (prova
-- que a política está ativa — não que os dados sumiram, só que ficam
-- invisíveis para quem não é dono e não tem o contexto certo).
SELECT fazenda_id, nome FROM estoque
WHERE nome LIKE '__RLS_TESTE_VALIDACAO%' ORDER BY fazenda_id;

ROLLBACK;   -- desfaz TUDO — nem as linhas de teste persistem.

-- confirmação final, transação nova e limpa: nada do teste sobrou.
SELECT count(*) AS deve_ser_zero FROM estoque WHERE nome LIKE '__RLS_TESTE%';
