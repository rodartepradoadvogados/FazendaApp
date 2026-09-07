-- =====================================================================
-- TRIAGEM DOS ÓRFÃOS — quantos dá para consertar SEM ADIVINHAR
--
-- Banco: PostgreSQL de produção no RAILWAY (projeto ravishing-smile,
-- serviço `Postgres`, ambiente production; current_database() = "railway").
--
-- SOMENTE LEITURA. Conta linhas e lê `fazenda_id`; não lê o conteúdo de
-- nenhum registro. A saída é nome de tabela, nome de coluna e números.
--
-- POR QUE ISTO EXISTE: a contagem de órfãos (orfaos-railway.sql) responde
-- "quantos são". Ela sozinha não decide nada, porque a pergunta que muda a
-- decisão do dono é outra: **quantos desses dá para recuperar sem chutar o
-- dono do registro?**
--
-- A migração 029227481e9e já fixou a estratégia certa, nesta ordem:
--   (a) DERIVAR DO PAI — a linha tem FK para uma tabela que já sabe a sua
--       fazenda. É a fonte confiável: não depende de quantas fazendas
--       existem.
--   (b) FAZENDA ÚNICA — se a instalação tem exatamente UMA fazenda real,
--       atribui essa. Deixa de valer no dia em que entra a segunda
--       fazenda-cliente, e é por isso que a consulta 1 abaixo existe.
--   (c) NÃO ADIVINHA — o resto fica pendente e vira decisão do dono.
--
-- A lista de pais daquela migração foi escrita à mão. Aqui a relação
-- filha→pai sai do CATÁLOGO do banco (pg_constraint), então nenhuma FK fica
-- de fora por esquecimento.
--
-- LIMITE CONHECIDO DA CONTA: quando uma tabela tem MAIS DE UM pai possível,
-- `recuperaveis_pelo_pai` usa o melhor elo isolado (`max`), não a soma. Somar
-- contaria em dobro a linha que tem dois pais preenchidos; usar o melhor
-- subestima quando os elos cobrem linhas diferentes. Ou seja, o número é um
-- PISO: o total recuperável é esse ou mais, nunca menos. Para as tabelas onde
-- isso pesar, a conta exata sai depois, olhando os elos daquela tabela — não
-- vale complicar a consulta inteira por causa disso antes de saber se há
-- órfão nessas tabelas.
--
-- CONFERIDO EM CENÁRIO CONTROLADO (PostgreSQL 16, esquema real do repositório
-- montado por SQLModel.metadata.create_all, órfãos sintéticos):
--   6 etapas órfãs — 5 com pai que sabe a fazenda, 1 com pai também órfão
--   4 linhas de sanidade órfãs, sem pai preenchido
--   1 protocolo órfão
-- A triagem devolveu exatamente: etapa 6 órfãs / 5 recuperáveis / 1 sem
-- saída; sanidade 4 / 0 / 4; protocolo 1 / 0 / 1; consolidado 11 órfãos,
-- 5 recuperáveis, 6 precisam de decisão. E `fazendas_reais = 2`, que é o
-- caso em que a estratégia (b) da migração deixa de valer.
-- =====================================================================


-- ---------------------------------------------------------------------
-- CONSULTA 1 — a estratégia (b) ainda serve?
-- Uma linha. Se `fazendas_reais` for maior que 1, "atribuir a fazenda
-- única" deixou de ser possível e todo órfão sem pai vira decisão do dono.
-- ---------------------------------------------------------------------
SELECT count(*) FILTER (WHERE NOT coalesce(eh_empresa_cowdata, false)) AS fazendas_reais,
       count(*)                                                        AS fazendas_no_total
FROM fazenda;


-- ---------------------------------------------------------------------
-- CONSULTA 2 — a triagem, tabela por tabela.
--
-- Para cada tabela com órfãos, percorre as FKs que apontam para outra
-- tabela que também tem `fazenda_id`, e conta quantos órfãos têm um pai
-- que SABE a sua fazenda. Esses são recuperáveis por (a), com uma
-- atualização determinística e sem adivinhação.
--
-- `orfaos_sem_saida` é o número que interessa ao dono: são as linhas que
-- ninguém consegue reatribuir sem chutar.
-- ---------------------------------------------------------------------
WITH catalogo_global(table_name) AS (VALUES
    ('principio_ativo'),('doenca'),('indicacao_terapeutica'),('medicamento_comercial'),
    ('categoria_estoque'),('finalidade_estoque'),('unidade_estoque'),('unidade_embalagem_estoque'),
    ('unidade_medida_embalagem_estoque'),('laboratorio'),('categoria_medicamento'),
    ('classificacao_medicamento_cad'),('servico_cadastro'),('parametro_fazenda'),
    ('medicamento_principio_ativo'),('alimento_nutricional')
),
multitenant AS (
    SELECT DISTINCT table_name
    FROM information_schema.columns
    WHERE table_schema = 'public' AND column_name = 'fazenda_id'
),
-- as FKs filha→pai onde AMBAS as pontas têm fazenda_id
elos AS (
    SELECT c.conrelid::regclass::text  AS filha,
           a.attname                   AS coluna_fk,
           c.confrelid::regclass::text AS pai,
           af.attname                  AS coluna_pai
    FROM pg_constraint c
    JOIN pg_attribute a  ON a.attrelid  = c.conrelid  AND a.attnum = c.conkey[1]
    JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = c.confkey[1]
    WHERE c.contype = 'f'
      AND c.connamespace = 'public'::regnamespace
      AND array_length(c.conkey, 1) = 1
      AND c.conrelid::regclass::text  IN (SELECT table_name FROM multitenant)
      AND c.confrelid::regclass::text IN (SELECT table_name FROM multitenant)
),
-- quantos órfãos cada tabela tem
orfaos AS (
    SELECT m.table_name,
           (xpath('/row/c/text()', query_to_xml(
              format('SELECT count(*) AS c FROM %I WHERE fazenda_id IS NULL', m.table_name),
              false, true, '')))[1]::text::bigint AS total_orfaos
    FROM multitenant m
    WHERE m.table_name NOT IN (SELECT table_name FROM catalogo_global)
),
-- e quantos deles têm pai que sabe a fazenda, por elo
recuperaveis AS (
    SELECT e.filha, e.coluna_fk, e.pai,
           (xpath('/row/c/text()', query_to_xml(format(
              'SELECT count(*) AS c FROM %I f JOIN %I p ON p.%I = f.%I
               WHERE f.fazenda_id IS NULL AND p.fazenda_id IS NOT NULL',
              e.filha, e.pai, e.coluna_pai, e.coluna_fk), false, true, '')))[1]::text::bigint AS n
    FROM elos e
    JOIN orfaos o ON o.table_name = e.filha AND o.total_orfaos > 0
)
SELECT o.table_name                              AS tabela,
       o.total_orfaos                            AS orfaos,
       coalesce(max(r.n), 0)                     AS recuperaveis_pelo_pai,
       o.total_orfaos - coalesce(max(r.n), 0)    AS orfaos_sem_saida,
       string_agg(DISTINCT r.pai, ', ')          AS pais_disponiveis
FROM orfaos o
LEFT JOIN recuperaveis r ON r.filha = o.table_name
WHERE o.total_orfaos > 0
GROUP BY o.table_name, o.total_orfaos
ORDER BY orfaos_sem_saida DESC, o.total_orfaos DESC, o.table_name;


-- ---------------------------------------------------------------------
-- CONSULTA 3 — o consolidado, para a conversa de decisão. Uma linha.
-- ---------------------------------------------------------------------
WITH catalogo_global(table_name) AS (VALUES
    ('principio_ativo'),('doenca'),('indicacao_terapeutica'),('medicamento_comercial'),
    ('categoria_estoque'),('finalidade_estoque'),('unidade_estoque'),('unidade_embalagem_estoque'),
    ('unidade_medida_embalagem_estoque'),('laboratorio'),('categoria_medicamento'),
    ('classificacao_medicamento_cad'),('servico_cadastro'),('parametro_fazenda'),
    ('medicamento_principio_ativo'),('alimento_nutricional')
),
multitenant AS (
    SELECT DISTINCT table_name FROM information_schema.columns
    WHERE table_schema = 'public' AND column_name = 'fazenda_id'
),
elos AS (
    SELECT c.conrelid::regclass::text AS filha, a.attname AS coluna_fk,
           c.confrelid::regclass::text AS pai, af.attname AS coluna_pai
    FROM pg_constraint c
    JOIN pg_attribute a  ON a.attrelid  = c.conrelid  AND a.attnum = c.conkey[1]
    JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = c.confkey[1]
    WHERE c.contype='f' AND c.connamespace='public'::regnamespace
      AND array_length(c.conkey,1)=1
      AND c.conrelid::regclass::text IN (SELECT table_name FROM multitenant)
      AND c.confrelid::regclass::text IN (SELECT table_name FROM multitenant)
),
orfaos AS (
    SELECT m.table_name,
           (xpath('/row/c/text()', query_to_xml(
              format('SELECT count(*) AS c FROM %I WHERE fazenda_id IS NULL', m.table_name),
              false, true, '')))[1]::text::bigint AS total_orfaos
    FROM multitenant m WHERE m.table_name NOT IN (SELECT table_name FROM catalogo_global)
),
recuperaveis AS (
    SELECT e.filha,
           (xpath('/row/c/text()', query_to_xml(format(
              'SELECT count(*) AS c FROM %I f JOIN %I p ON p.%I = f.%I
               WHERE f.fazenda_id IS NULL AND p.fazenda_id IS NOT NULL',
              e.filha, e.pai, e.coluna_pai, e.coluna_fk), false, true, '')))[1]::text::bigint AS n
    FROM elos e JOIN orfaos o ON o.table_name = e.filha AND o.total_orfaos > 0
),
por_tabela AS (
    SELECT o.table_name, o.total_orfaos, coalesce(max(r.n), 0) AS rec
    FROM orfaos o LEFT JOIN recuperaveis r ON r.filha = o.table_name
    WHERE o.total_orfaos > 0
    GROUP BY o.table_name, o.total_orfaos
)
SELECT count(*)                            AS tabelas_com_orfaos,
       sum(total_orfaos)                   AS orfaos_no_total,
       sum(rec)                            AS recuperaveis_pelo_pai,
       sum(total_orfaos) - sum(rec)        AS precisam_de_decisao
FROM por_tabela;
