# Rotina automática /milknews → publicação na aba News

> **Especificação vigente:** este documento descreve o mecanismo de dados (arquivo por lote) e o
> fecho da rotina. A fonte de verdade para as regras editoriais, de coleta e de verificação é
> `.claude/skills/milknews/SKILL.md` — a Routine deve invocá-la integralmente. Este arquivo existe
> para quem não tem a skill disponível; nesse caso, siga também
> `docs/agents/milknews-firecrawl.md`.

**Onde isto roda:** cria uma **rotina agendada no claude.ai/code** (agente *Farm app access*),
não uma tarefa local de desktop. A rotina parte sempre de um clone fresco, tem acesso de escrita
ao repo e `gh` para abrir/mergear PR — só assim o timer dispara com o PC do usuário desligado.

**Sob demanda:** o mesmo texto abaixo pode ser colado num chat *Farm app access* para rodar na hora.

**Cadência (decisão 23/07/2026, confirmada em 25/09/2026):** rodar **todos os dias**. Publicar
**no mínimo 1 e no máximo 3** matérias por dia com pauta verificada — nunca mais que 3, e nunca
forçando post num dia sem pauta que passe na dupla verificação (dia sem post é exceção legítima,
não falha).

**Modo (decisão do dono, 26/09/2026): hands-off com trava de teste.** A rotina **faz o merge
sozinha**, mas só depois que `pytest backend/tests/test_milknews_lotes_formato.py` passar verde
para o lote novo — lote que quebra o teste de formato não é mergeado. Essa trava não substitui
revisão editorial humana: o post só aparece em `/news` depois que alguém do CowData marca
"revisado final" em cada matéria (Painel CowData → News → matérias).

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
   - **Veracidade:** todo número/fato sai da leitura da página de verdade via **Firecrawl**
     (`/scrape`, conforme `docs/agents/milknews-firecrawl.md`) — o conhecimento do modelo é
     anterior à data corrente, nunca escrever cotação/decisão de memória, e resultado de `/search`
     (snippet) não conta como fonte lida. **Todo número precisa de 2 fontes independentes lidas**;
     divergindo entre si, o dado não é publicado. `cepea.org.br` e Canal Rural bloqueiam fetch
     automatizado comum (403) — o Firecrawl normalmente passa; sem `FIRECRAWL_API_KEY` disponível,
     use o plano B do mesmo documento (coleta pelo próprio agente) e diga isso no PR.

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

7. Abra PR para `main`. **Antes de mergear, rode `pytest backend/tests/test_milknews_lotes_formato.py`**
   contra o lote novo: só verde autoriza o merge. **Faça o merge** você mesmo (hands-off) só depois
   disso; se o teste falhar, não mergeie — corrija o lote ou não publique. Apague o branch depois.

8. O merge dispara o deploy (Railway/Vercel); o seed `publicar_lotes_milknews` roda 1x no próximo
   boot e publica as matérias. A aba News mostra por padrão só os últimos 3 dias — por isso publicar
   no mesmo dia da `data_publicacao`.

Restrições: conteúdo do robô é autoral (link interno + "Dados: <fonte>"); nunca fingir matéria de
terceiro; um lote roda uma única vez (idempotente por `SeedFlag`, chave = nome do arquivo); nunca
editar/apagar um `.json` já publicado.
