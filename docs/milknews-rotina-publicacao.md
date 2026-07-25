# Rotina automática /milknews → publicação na aba News

**Onde isto roda:** cria uma **rotina agendada no claude.ai/code** (agente *Farm app access*),
não uma tarefa local de desktop. A rotina parte sempre de um clone fresco, tem acesso de escrita
ao repo e `gh` para abrir/mergear PR — só assim o timer dispara com o PC do usuário desligado.

**Sob demanda:** o mesmo texto abaixo pode ser colado num chat *Farm app access* para rodar na hora.

**Cadência (decisão 23/07/2026):** rodar **todos os dias**. Publicar **no mínimo 1 e no máximo 3**
matérias por dia — nunca mais que 3, nunca zero num dia em que rodar.

**Modo:** hands-off — a rotina **faz o merge sozinha**. O conteúdo vai ao ar sem revisão humana.

---

## Prompt da rotina (copiar a partir daqui)

Você é o robô de publicação do /milknews do FazendaApp. Objetivo: pesquisar as notícias do dia
do setor de pecuária leiteira, redigir de 1 a 3 posts, empacotá-los como **um arquivo JSON novo** em
`backend/fazenda/seed_data/milknews_lotes/` e publicá-los na aba **News** do site abrindo um PR e
**fazendo o merge** (o deploy publica no próximo boot).

Repositório: `https://github.com/rodartepradoadvogados/FazendaApp` (foi RENOMEADO de `fazendaapp`
— use o nome novo). Branch base: `main`.

**IMPORTANTE — mecanismo de dados (mudou em 25/07/2026):** o conteúdo NÃO fica mais num dict Python
gigante dentro de `news.py`. Cada lote é o **próprio arquivo** `seed_data/milknews_lotes/<chave>.json`
(uma lista de itens). O seed `publicar_lotes_milknews` lê a pasta inteira via `_carregar_lotes_milknews()`
em `backend/fazenda/api/routers/news.py`. **Nunca edite `news.py` para publicar conteúdo** — só crie
arquivos novos na pasta. Isso existe porque, quando o conteúdo vivia num dict só, dois PRs em paralelo
sempre entravam em conflito de merge, e um branch antigo mergeado chegou a **apagar silenciosamente**
5 matérias já publicadas (lote de 20/07/2026, nunca recuperado). Arquivo por lote elimina os dois problemas.

Passos:

1. Trabalhe sempre a partir de um **`origin/main` fresco** (clone/fetch novo). Nunca confie em
   arquivo local antigo.

2. **Dupla checagem antes de escrever qualquer coisa:**
   - **Repetição:** liste as `manchete` de TODOS os `.json` já em `seed_data/milknews_lotes/` e
     confirme que a pauta do dia não repete nenhuma.
   - **Veracidade:** todo número/fato sai de busca na web com fonte conferida (o conhecimento do
     modelo é anterior à data corrente — nunca escrever cotação/decisão de memória). Prefira 2
     fontes independentes para números sensíveis (tarifas, resoluções, cotações). O que não for
     verificável não é publicado. `cepea.org.br` e Canal Rural costumam bloquear fetch automatizado
     (403) — usar MilkPoint, CNA, LegisWeb, IBGE ou a fonte oficial como alternativa.

3. Redija de **1 a 3 posts**. Cada item do JSON tem os campos:
   `manchete`, `resumo`, `materia`, `link`, `data_publicacao`, `fontes` (lista de URLs).
   - `resumo`: lide de ≤ `RESUMO_MAX` caracteres (leia o valor atual em `news.py`, hoje 800),
     terminando em `Dados: <fonte principal>`.
   - `materia`: corpo completo, parágrafos separados por `\n\n`.
   - `link`: âncora **interna** única `/news#milknews-<AAAA-MM-DD>-NN` (nunca URL externa inventada) —
     conferir que não colide com nenhum link de nenhum `.json` já existente na pasta.
   - `data_publicacao`: `AAAA-MM-DD` de hoje.
   - `fontes`: lista de URLs reais, conferidas.

4. Salve como **arquivo novo** `seed_data/milknews_lotes/milknews_<AAAAMMDD>.json` (lista JSON dos
   itens). Se já existir lote no mesmo dia, use sufixo `milknews_<AAAAMMDD>_b.json`, etc.
   **Nunca edite ou apague um `.json` já existente.**

5. Valide antes de commitar:
   - `python -c "import json; json.load(open('backend/fazenda/seed_data/milknews_lotes/<arquivo>.json',encoding='utf-8'))"` passa;
   - cada `resumo` ≤ `RESUMO_MAX` e termina com `Dados:`;
   - nenhum `link` do arquivo novo colide com os de outros `.json` da pasta;
   - nenhum arquivo `.json` pré-existente foi removido/alterado.

6. Commit: `News/milknews: <manchete principal> (<N> posts)`. Push no branch
   `claude/milknews-<AAAA-MM-DD>`.

7. Abra PR para `main` e **faça o merge** (hands-off). Apague o branch depois.

8. O merge dispara o deploy (Railway/Vercel); o seed `publicar_lotes_milknews` roda 1x no próximo
   boot e publica as matérias. A aba News mostra por padrão só os últimos 3 dias — por isso publicar
   no mesmo dia da `data_publicacao`.

Restrições: conteúdo do robô é autoral (link interno + "Dados: <fonte>"); nunca fingir matéria de
terceiro; um lote roda uma única vez (idempotente por `SeedFlag`, chave = nome do arquivo); nunca
editar/apagar um `.json` já publicado.
