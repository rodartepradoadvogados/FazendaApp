-- =====================================================================
-- DDL PARAMETRIZADO DA ATIVAÇÃO DE RLS — PROPOSTA, NÃO APLICADA
--
-- POR QUE ISTO É UM .sql AVULSO E NÃO UMA MIGRAÇÃO ALEMBIC:
-- `database.py::_aplicar_alembic()` roda `upgrade head` no BOOT da API. Uma
-- revisão colocada em `alembic/versions/` seria aplicada em produção no
-- próximo deploy, sozinha, sem ninguém decidir nada. Enquanto a decisão do
-- dono não existir, este arquivo fica FORA da cadeia de migração de
-- propósito. Vira revisão Alembic no dia da decisão, não antes.
--
-- PRÉ-REQUISITOS, na ordem (ver docs/security-audit/rls-proposta.md):
--   1. contagem de órfãos feita em produção;
--   2. órfãos recuperados ou explicitamente marcados como inacessíveis;
--   3. role de aplicação criado e DATABASE_URL trocada para ele;
--   4. a aplicação já emitindo `SET LOCAL app.fazenda_id` por requisição.
-- Rodar isto sem o passo 4 derruba o sistema inteiro: sem contexto, a
-- política nega tudo, e é assim que ela foi desenhada.
-- =====================================================================

-- ---------------------------------------------------------------------
-- PASSO 0 — o role da aplicação. Sem superusuário, e as tabelas NÃO são
-- dele. Superusuário ignora RLS mesmo com FORCE (medido); manter a aplicação
-- fora da posse das tabelas é a defesa que de fato sustenta a política.
-- A senha entra por variável de ambiente no momento de rodar, nunca aqui.
-- ---------------------------------------------------------------------
-- CREATE ROLE cowdata_app LOGIN PASSWORD :'senha_do_app';
-- GRANT USAGE ON SCHEMA public TO cowdata_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cowdata_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cowdata_app;
-- -- e para as tabelas que vierem depois:
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public
--   GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cowdata_app;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public
--   GRANT USAGE, SELECT ON SEQUENCES TO cowdata_app;

-- ---------------------------------------------------------------------
-- PASSO 1 — as políticas, geradas para TODA tabela com `fazenda_id`.
--
-- Percorrer o catálogo do banco (e não uma lista escrita à mão) é
-- deliberado: tabela nova com `fazenda_id` que alguém criar amanhã entra
-- sozinha quando este bloco for rodado de novo, em vez de ficar de fora em
-- silêncio — que é exatamente como nascem os furos que a auditoria achou.
--
-- As duas naturezas ganham políticas DIFERENTES:
--   • catálogo global (18 tabelas — reconferido em 10/09/2026 contra o
--     esquema real pós-#744/#745: bate exatamente com a lista de
--     alembic/versions/c8e2a4f70b13_fazenda_id_not_null.py::_CATALOGO_GLOBAL,
--     nenhuma tabela nova nem removida) — na LEITURA, a fazenda atual OU as
--     linhas globais (`fazenda_id IS NULL`); na ESCRITA, só a fazenda
--     atual. O tenant lê o catálogo de todos, mas nunca escreve nele.
--   • dado da fazenda (as outras 167) — só a fazenda atual, na leitura e na
--     escrita. `fazenda_id IS NULL` ali é órfão e não passa por ninguém.
-- ---------------------------------------------------------------------
DO $$
DECLARE
    t record;
    catalogo_global text[] := ARRAY[
        'principio_ativo', 'doenca', 'indicacao_terapeutica',
        'medicamento_comercial', 'categoria_estoque', 'finalidade_estoque',
        'unidade_estoque', 'unidade_embalagem_estoque',
        'unidade_medida_embalagem_estoque', 'laboratorio',
        'categoria_medicamento', 'classificacao_medicamento_cad',
        'servico_cadastro', 'parametro_fazenda',
        -- as duas achadas ao conferir a contagem de produção (copy-on-write,
        -- não `visivel()`): sem elas, a política ESTRITA esconderia as linhas
        -- mestre do catálogo e quebraria a Farmácia e a biblioteca de alimentos.
        'medicamento_principio_ativo', 'alimento_nutricional',
        -- Ligações N-N do catálogo: o modelo AVISA que o NULL nelas espelha o
        -- NULL do pai e tem que continuar global — "senão ele passaria a
        -- pertencer à primeira fazenda que o backfill encontrasse e sumiria
        -- do catálogo global de todas as outras".
        'medicamento_categoria', 'medicamento_classificacao'
    ];
    ctx constant text := 'NULLIF(current_setting(''app.fazenda_id'', true), '''')::int';
    leitura text;
    n_catalogo int := 0;
    n_dado int := 0;
BEGIN
    FOR t IN
        SELECT DISTINCT c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables tb
          ON tb.table_schema = c.table_schema AND tb.table_name = c.table_name
        WHERE c.table_schema = 'public'
          AND c.column_name = 'fazenda_id'
          AND tb.table_type = 'BASE TABLE'
        ORDER BY c.table_name
    LOOP
        IF t.table_name = ANY (catalogo_global) THEN
            leitura := format('fazenda_id = %s OR fazenda_id IS NULL', ctx);
            n_catalogo := n_catalogo + 1;
        ELSE
            leitura := format('fazenda_id = %s', ctx);
            n_dado := n_dado + 1;
        END IF;

        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t.table_name);
        -- Sem FORCE, de propósito: o FORCE só alcança o dono das tabelas, e o dono
        -- pode removê-lo sozinho (medido, seção 8 da proposta) — não restringe
        -- ninguém. Deixá-lo de fora é o que dá ao backup automático e aos seeds do
        -- boot a leitura sem recorte de que precisam, pela conexão de dono, sem
        -- criar nenhum role BYPASSRLS.
        EXECUTE format('DROP POLICY IF EXISTS isolamento_fazenda ON %I', t.table_name);
        EXECUTE format(
            'CREATE POLICY isolamento_fazenda ON %I USING (%s) WITH CHECK (fazenda_id = %s)',
            t.table_name, leitura, ctx
        );
    END LOOP;

    RAISE NOTICE 'Políticas criadas: % de catálogo global, % de dado da fazenda (total %)',
                 n_catalogo, n_dado, n_catalogo + n_dado;
END $$;

-- ---------------------------------------------------------------------
-- PASSO 2 — conferência. Toda tabela com `fazenda_id` tem que aparecer com
-- rowsecurity = true e exatamente uma política.
-- ---------------------------------------------------------------------
SELECT count(*) FILTER (WHERE c.relrowsecurity)     AS com_rls_ligada,
       count(*) FILTER (WHERE NOT c.relrowsecurity) AS SEM_RLS_ligada,
       count(*)                                     AS total_tabelas_multitenant
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
  AND EXISTS (SELECT 1 FROM information_schema.columns col
              WHERE col.table_schema = 'public' AND col.table_name = c.relname
                AND col.column_name = 'fazenda_id');

-- ---------------------------------------------------------------------
-- REVERSÃO (o `downgrade` da futura migração)
-- ---------------------------------------------------------------------
-- DO $$
-- DECLARE t record;
-- BEGIN
--     FOR t IN SELECT DISTINCT table_name FROM information_schema.columns
--              WHERE table_schema='public' AND column_name='fazenda_id'
--     LOOP
--         EXECUTE format('DROP POLICY IF EXISTS isolamento_fazenda ON %I', t.table_name);
--         EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', t.table_name);
--         EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', t.table_name);
--     END LOOP;
-- END $$;
