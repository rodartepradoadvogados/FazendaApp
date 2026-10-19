# MilkNews com Firecrawl: coleta automatizada de cotações e notícias

> **Para quem é este documento:** o robô **MilkNews** (skill `.claude/skills/milknews/SKILL.md`,
> rodando como Routine agendada do Claude no repositório FazendaApp/CowData) e o agente que for
> preparar o terreno para ele.
>
> **O que muda:** a coleta na internet lê a página de verdade, em vez de busca solta e snippets.
> **Política de uso do Firecrawl (decidida em 19/10/2026):** a leitura comum (WebFetch, `curl`,
> `pdftotext`) vem primeiro. O Firecrawl é **fonte principal só no Canal Rural**, o único site que
> a leitura comum não abre (403). Em todos os outros é **último recurso**, para não gastar créditos
> à toa. Detalhes na seção 1.1.
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

## 1.1 Política: quando usar o Firecrawl (decidida em 19/10/2026)

O plano tem poucos créditos e eles são compartilhados com o resto do CowData. A regra é:

| Fonte | Como ler | Observação |
|---|---|---|
| **Canal Rural** (`canalrural.com.br`) | **Firecrawl primeiro**, direto no `/scrape`, sem tentar a leitura comum antes | A leitura comum devolve **403** (testado em 19/10/2026, com e sem user-agent de navegador). O Firecrawl devolve 200. É o único site neste caso. |
| **Todos os outros** (MilkPoint, Notícias Agrícolas, USDA AMS, GDT, DairyReporter, DairyNews.today, sites de Alta Genetics/ABS/Semex, MAPA, FAEP, periódicos) | **Leitura comum primeiro**: WebFetch, `curl` pelo proxy, PDF baixado e lido com `pdftotext` | Firecrawl só se a leitura comum falhar de verdade (403, bloqueio, página só com JavaScript, PDF que não abre) |
| **Cepea** (`cepea.org.br`) | Leitura comum primeiro; se falhar, **uma** tentativa com Firecrawl | Em 19/10/2026 o site respondeu **500 até no Firecrawl**: é queda do site, não bloqueio. Se as duas falharem, o indicador fica "não lido nesta rodada" (nunca vale snippet; a cotação do Cepea reproduzida por terceiro só entra com a data de referência conferida e uma segunda fonte). |

**Antes de usar o Firecrawl em qualquer site fora do Canal Rural, registre** (no relatório ou no
PR) qual fonte falhou, com qual erro, na leitura comum. Sem a chave, sem créditos ou com a API fora
do ar: **não insista**, marque a fonte como "não lida nesta rodada" e siga com as outras.

**Descoberta de pauta** usa `WebSearch`, não o `/search` do Firecrawl (resultado de busca nunca é
fonte; o `/search` gasta crédito sem ganho). O Firecrawl `/scrape` só entra para **ler** página.

**Esperado por execução:** 1 a 3 chamadas de Firecrawl (Canal Rural, mais algum fallback). O teto
de 25 continua valendo como trava, não como meta.

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
| Dado | Fonte primária (leitura comum; Firecrawl só pela seção 1.1) | Segunda fonte independente |
|---|---|---|
| Indicador do leite ao produtor (Cepea/Esalq) | `https://www.cepea.org.br/br/indicador/leite.aspx` (alternativa `https://www.cepea.esalq.usp.br/br/indicador/leite.aspx`) | `https://www.noticiasagricolas.com.br/cotacoes/leite` ou a matéria do MilkPoint sobre o mesmo indicador |
| Leite spot / preços regionais | `https://www.noticiasagricolas.com.br/cotacoes/leite` | MilkPoint (achar a matéria com `WebSearch`, depois ler a página) |
| Mercado internacional (EUA) | USDA AMS Dairy Market News, PDF semanal `https://www.ams.usda.gov/mnreports/dywweeklyreport.pdf` (PDF: baixar para diretório novo e vazio e ler com `pdftotext`) | DairyReporter ou DairyNews.today sobre o mesmo relatório |
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
- Descoberta lendo as páginas de listagem (leitura comum; **Canal Rural pelo Firecrawl**, seção 1.1):
  - MilkPoint: `https://www.milkpoint.com.br/`
  - Notícias Agrícolas: `https://www.noticiasagricolas.com.br/noticias/leite/`
  - Canal Rural: `https://www.canalrural.com.br/pecuaria/`
  - DairyReporter: `https://www.dairyreporter.com/`
  - DairyNews.today: `https://dairynews.today/`
- Escolha 1 a 3 pautas. Para cada uma, leia a matéria original **e** uma segunda fonte
  independente sobre o mesmo fato (`WebSearch` com a manchete, depois ler a página).
- **Canal Rural** devolve 403 para leitura comum: leia **direto pelo Firecrawl** (seção 1.1). O
  Cepea está fora da regra "só com Firecrawl" (em 19/10/2026 deu 500 também nele). Se uma página
  não abrir por nenhum meio, ela **não conta** como fonte (regra 5).

### 3.3 Conteúdo técnico (genética e manejo)
- Sites oficiais da **Alta Genetics**, **ABS** e **Semex**: leia a página da novidade (leitura comum).
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
   (= data do arquivo, ≤ hoje) e `fontes` (**as URLs efetivamente lidas**, todas
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

## 5. Frequência e merge: decisões do dono

**Frequência (decidida em 25/09/2026): matéria diária.** Todo dia de execução, o robô publica
**de 1 a 3 posts** quando houver pauta verificada. A regra de ouro não muda: **nunca force post sem
dupla verificação**. Se num dia nada passar na verificação, o robô não publica e explica o motivo no
relatório da execução. Um dia sem post é exceção a ser justificada, não rotina.

**Merge:** a decidir. `SKILL.md` diz "só abre PR"; `docs/milknews-rotina-publicacao.md` diz "abre
e mergeia". Na primeira execução depois deste documento, o robô **pergunta ao dono** qual vale e
registra a resposta no `SKILL.md` (ver `docs/agents/MISSAO-milknews.md`, Etapa 1).

---

## 6. Plano B (Firecrawl indisponível)
Sem `FIRECRAWL_API_KEY`, com saldo zerado ou com a API fora do ar: como a leitura comum já é a
regra, só o **Canal Rural** fica sem leitura ("não lido nesta rodada"); as demais fontes seguem,
**com as mesmas regras de dupla verificação**. Diga no PR: "Canal Rural não lido nesta execução:
<motivo>".

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
- [ ] Firecrawl só no Canal Rural e nos fallbacks da seção 1.1, cada fallback com o erro da leitura
      comum registrado; teto de 25 chamadas respeitado.
- [ ] Cada número com 2 fontes **lidas** e iguais; divergência não publicada.
- [ ] Nenhum snippet de busca usado como fonte.
- [ ] Lote novo validado por `json.load` e pelo `pytest` de formato.
- [ ] PR lista as URLs por número; nenhum valor de chave em arquivo, log ou PR.
