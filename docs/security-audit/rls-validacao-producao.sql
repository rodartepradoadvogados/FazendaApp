-- =====================================================================
-- VALIDAÇÃO DO RLS EM PRODUÇÃO — mesma bateria de 7 ataques já rodada
-- contra o Staging (rls-validacao-staging.sql), agora contra o schema
-- REAL de produção. NENHUM DDL, NENHUM DROP/CREATE, e TODO dado de
-- teste é desfeito no final com ROLLBACK. Zero persistência.
--
-- Fazendas reais de produção (confirmado via SELECT direto em
-- 12/09/2026, antes de rodar este script):
--   id=1 Jairo Nasser      (cliente real, eh_teste=false, ativa=true)
--   id=2 Fazenda Teste     (eh_teste=true, ativa=true)
--   id=3 CowData (empresa) (eh_empresa_cowdata=true, ativa=true)
-- Os mesmos IDs 1 e 2 usados no script de Staging já são os corretos
-- aqui — nenhuma renumeração foi necessária.
--
-- ATENÇÃO: a fazenda 1 é cliente real com dado de produção de verdade.
-- O teste usa só linhas próprias, marcadas com nome inconfundível
-- (__RLS_TESTE_VALIDACAO...), nunca toca nas reais, e tudo roda dentro
-- de uma única transação com ROLLBACK final — nada é commitado.
--
-- Ataque 8 (SET sem LOCAL vazando entre requisições) fica de fora aqui
-- de propósito, pelo mesmo motivo do script de Staging: provar isso
-- exigiria um COMMIT real no meio do roteiro. Já está provado do jeito
-- certo em backend/tests/test_contexto_fazenda_sessao.py::
-- test_contexto_reaplicado_apos_commit_no_meio_da_sessao, contra
-- Postgres de verdade, na suíte automatizada (CI).
--
-- Rodar via railway-agent (a sessão não tem saída TCP direta), pela
-- mesma DATABASE_URL_MANUTENCAO de sempre:
--
--     psql "$DATABASE_URL_MANUTENCAO" -f rls-validacao-producao.sql
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
