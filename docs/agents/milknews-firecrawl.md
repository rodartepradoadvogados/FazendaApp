# MilkNews com Firecrawl: coleta automatizada de cotações e notícias

> **Para quem é este documento:** o robô **MilkNews** (skill `.claude/skills/milknews/SKILL.md`,
> rodando como Routine agendada do Claude no repositório FazendaApp/CowData) e o agente que for
> preparar o terreno para ele.
>
> **O que muda:** a coleta na internet (cotações, notícias, conteúdo técnico) passa a ser feita
> pelo **Firecrawl**, que lê a página de verdade (inclusive PDF e sites que hoje devolvem 403 para
> acesso automatizado), em vez de busca solta e snippets.
>
> **O que NÃO muda:** as regras editoriais e de verificação do `SKILL.md` ("inegociáveis"), o
> formato do lote JSON, a pasta `backend/fazenda/seed_data/milknews_lotes/` e o teste de formato do
> CI. O MilkNews continua sendo um bot do Claude, e este documento **não** o substitui.
>
> Levantamento feito sobre `main` em 25/09/2026.

---

## 1. Pré-requisito do dono (uma vez)

A Routine do MilkNews roda num ambiente do Claude Code na nuvem. A chave precisa estar **nesse
ambiente**, não no repositório:

1. claude.ai → Claude Code → **Environments** → ambiente usado pela Routine do MilkNews →
   **Environment variables**.
2. Adicionar `FIRECRAWL_API_KEY` com a chave nova (a mesma já cadastrada no Railway).
3. Salvar. As próximas execuções da Routine enxergam a variável.

**Regra para o robô:** nunca imprima, logue, grave em arquivo ou coloque em commit o valor da
chave. Se `FIRECRAWL_API_KEY` não estiver no ambiente, **não invente outro caminho**: siga a coleta
antiga (seção 6) e diga no PR que o Firecrawl não estava disponível.

---

## 2. Como chamar o Firecrawl de dentro da Routine

API REST v2, base `https://api.firecrawl.dev/v2`, header `Authorization: Bearer $FIRECRAWL_API_KEY`.

**Ler uma página (HTML ou PDF) em markdown. Isto conta como "fonte lida":**
```bash
curl -sS -m 90 https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" -H "Content-Type: application/json" \
  -d '{"url":"https://www.cepea.org.br/br/indicador/leite.aspx","formats":["markdown"],"onlyMainContent":true}' \
  > /tmp/milknews/cepea.json
```
A resposta traz `data.markdown`, `data.metadata.title` e `data.metadata.sourceURL`. Leia o número
**no markdown**.

**Buscar páginas (descoberta; snippet NÃO é fonte):**
```bash
curl -sS -m 60 https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" -H "Content-Type: application/json" \
  -d '{"query":"preço do leite ao produtor Cepea setembro 2026","limit":5}'
```
Resultados em `data.web[] = {url, title, description}`. Toda URL escolhida daqui **precisa** ser
lida com `/scrape` antes de virar fonte.

**Alternativa em Python** (mesmo cliente do backend, fail-closed):
```bash
cd backend && python -c "from fazenda.rules.firecrawl import ler_pagina; print(ler_pagina('https://...').markdown[:3000])"
```

**Orçamento:** o plano tem **1.000 créditos/mês**, compartilhados com o resto do CowData. Teto do
MilkNews: **25 chamadas por execução**. Antes de começar, consulte o saldo:
```bash
curl -sS https://api.firecrawl.dev/v2/team/credit-usage -H "Authorization: Bearer $FIRECRAWL_API_KEY"
```
Com menos de 100 créditos restantes, colete só as cotações (seção 3.1) e registre isso no PR.

Pastas de trabalho: use `/tmp/milknews/`. **Nada coletado vai para o git** além do lote JSON final.

---

## 3. Roteiro de coleta por tipo de informação

### 3.1 Cotações (prioridade 1, todo dia que houver execução)
| Dado | Fonte primária (ler com `/scrape`) | Segunda fonte independente |
|---|---|---|
| Indicador do leite ao produtor (Cepea/Esalq) | `https://www.cepea.org.br/br/indicador/leite.aspx` (alternativa `https://www.cepea.esalq.usp.br/br/indicador/leite.aspx`) | `https://www.noticiasagricolas.com.br/cotacoes/leite` ou a matéria do MilkPoint sobre o mesmo indicador |
| Leite spot / preços regionais | `https://www.noticiasagricolas.com.br/cotacoes/leite` | MilkPoint (achar a matéria com `/search`, depois `/scrape`) |
| Mercado internacional (EUA) | USDA AMS Dairy Market News, PDF semanal `https://www.ams.usda.gov/mnreports/dywweeklyreport.pdf` (o `/scrape` lê PDF) | DairyReporter ou DairyNews.today sobre o mesmo relatório |
| Leilão GDT (Global Dairy Trade) | Resultado do evento em `https://www.globaldairytrade.info/` | DairyReporter ou DairyNews.today |

**Como extrair um número:**
1. Leia a página primária. Localize no markdown o valor, a unidade (R$/litro, US$/t, %) e a
   **data de referência**.
2. Leia a segunda fonte e confira o **mesmo** valor, com a mesma unidade e a mesma data de
   referência.
3. Iguais → pode publicar. Diferentes → regra 3 do `SKILL.md`: **não publica** o número e relata a
   divergência no PR.
4. Data de referência posterior a hoje → erro, descarta (regra 4).

### 3.2 Notícias de mercado (nacional e internacional)
- Descoberta com `/scrape` nas páginas de listagem:
  - MilkPoint: `https://www.milkpoint.com.br/`
  - Notícias Agrícolas: `https://www.noticiasagricolas.com.br/noticias/leite/`
  - Canal Rural: `https://www.canalrural.com.br/pecuaria/`
  - DairyReporter: `https://www.dairyreporter.com/`
  - DairyNews.today: `https://dairynews.today/`
- Escolha 1 a 3 pautas. Para cada uma, leia a matéria original **e** uma segunda fonte
  independente sobre o mesmo fato (`/search` com a manchete, depois `/scrape`).
- Canal Rural e cepea.org.br costumam devolver 403 para acesso automatizado comum. O Firecrawl
  normalmente passa. Se falhar, a página **não conta** como fonte (regra 5).

### 3.3 Conteúdo técnico (genética e manejo)
- Sites oficiais da **Alta Genetics**, **ABS** e **Semex**: leia a página da novidade com `/scrape`.
  O site oficial da empresa prevalece sobre terceiros (regra 2).
- Artigo científico (Journal of Dairy Science / Journal of Animal Science): leia o resumo na página
  da revista.

---

## 4. Da coleta ao lote (sem mudança de formato)

Siga o `SKILL.md` à risca. Resumo operacional:
1. Liste as `manchete` existentes em `backend/fazenda/seed_data/milknews_lotes/` para não repetir
   pauta.
2. Escreva 1 a 3 posts, cada um com `manchete`, `resumo` (lead de 1 a 2 frases, ≤ 800 caracteres),
   `materia` (2 a 3 parágrafos separados por `\n\n`, ≤ 350 palavras, paráfrase, citação inline sem
   link: "segundo o Cepea/Esalq…"), `link` (`/news#milknews-AAAA-MM-DD-NN`), `data_publicacao`
   (= data do arquivo, ≤ hoje) e `fontes` (**as URLs efetivamente lidas com `/scrape`**, todas
   começando com `http`).
3. Novo arquivo `milknews_AAAAMMDD.json` (segundo lote do dia: `milknews_AAAAMMDD_b.json`). Nunca
   edite nem apague lote existente.
4. Valide antes do commit:
   ```bash
   python -c "import json;json.load(open('backend/fazenda/seed_data/milknews_lotes/milknews_AAAAMMDD.json'))"
   cd backend && pytest -q tests/test_milknews_lotes_formato.py
   ```
   Lote que quebra esse teste **impede o app de subir**.
5. No corpo do PR, liste para **cada número publicado** as duas URLs lidas que o sustentam.

**Visibilidade:** o lote vira post no próximo boot (`publicar_lotes_milknews`), mas o post **só
aparece em `/news` depois que alguém do CowData marca "revisado final"**
(`POST /news/materias/{id}/revisar-final`). O robô não faz essa marcação.

---

## 5. Divergência entre documentos que o dono precisa decidir

`SKILL.md` e `docs/milknews-rotina-publicacao.md` discordam:

| Ponto | `SKILL.md` | `milknews-rotina-publicacao.md` |
|---|---|---|
| Frequência | 3 a 5 posts por semana; dias sem post são normais | todo dia, mínimo 1 e máximo 3 |
| Merge | só abre PR | abre o PR **e mergeia** |

**Até o dono decidir, o robô segue o `SKILL.md`**, que é a versão que a Routine lê. Não force post
em dia sem pauta verificada.

---

## 6. Plano B (Firecrawl indisponível)
Sem `FIRECRAWL_API_KEY`, com saldo zerado ou com a API fora do ar: use a coleta antiga (busca e
leitura pelo próprio agente), **com as mesmas regras de dupla verificação**. Diga no PR: "coleta
sem Firecrawl nesta execução: <motivo>".

---

## 7. Evolução opcional (só com aprovação do dono)
Hoje **não existe tabela de cotações** no backend. Os números vivem só no texto dos posts, e o
card de cotação em `frontend/app/news/page.tsx` extrai o primeiro R$/US$/% por regex. Se o dono
quiser cotações estruturadas (gráfico histórico, série do Cepea), a proposta é:
- um modelo `CotacaoLeite` (fonte, indicador, valor, unidade, data_referencia, url_fonte_1,
  url_fonte_2), com migração Alembic no padrão do repositório;
- o MilkNews gravar a cotação validada num arquivo de seed separado
  (`seed_data/cotacoes/cotacoes_AAAAMMDD.json`), com o mesmo mecanismo de `SeedFlag`.

**Não implemente sem pedido explícito.** É mudança de schema e de tela.

## 8. Checklist de cada execução
- [ ] Saldo do Firecrawl consultado; teto de 25 chamadas respeitado.
- [ ] Cada número com 2 fontes **lidas** (`/scrape`) e iguais; divergência não publicada.
- [ ] Nenhum snippet de busca usado como fonte.
- [ ] Lote novo validado por `json.load` e pelo `pytest` de formato.
- [ ] PR lista as URLs por número; nenhum valor de chave em arquivo, log ou PR.
