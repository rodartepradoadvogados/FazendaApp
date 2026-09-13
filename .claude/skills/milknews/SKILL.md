---
name: milknews
description: >
  Pesquisa diária em fontes de pecuária leiteira (cotação, mercado, notícia
  setorial, genética e ciência) e PUBLICA os posts do blog criando um lote novo
  em backend/fazenda/seed_data/milknews_lotes/ e abrindo um pull request. Use
  quando o usuário disser "/milknews", pedir a pauta do dia ou da semana, ou
  quando esta skill for acionada por uma Routine agendada.
---

# Milknews — pauta e publicação do blog

Versão **versionada no repositório**, feita para rodar **sem ninguém presente**
(Routine agendada). Existe uma skill de mesmo nome nas configurações do usuário,
para uso interativo; esta é a que uma Routine enxerga, porque a sessão de
Routine só carrega skills commitadas no repositório clonado.

A diferença entre as duas está no fecho: a interativa termina em e-mail para
revisão; **esta termina em pull request**. Todo o resto — as regras de
verificação — é idêntico, e é a parte que não pode ser afrouxada por estar
rodando sozinha. Sozinha é justamente quando não há ninguém para pegar o erro.

## Fontes

- **Cotação/mercado (primária)**: Cepea/Esalq — https://www.cepea.esalq.usp.br/br/indicador/leite.aspx e https://www.cepea.org.br/br/indicador/leite.aspx
- **Notícia nacional**: MilkPoint, Notícias Agrícolas, Canal Rural
- **Internacional**: DairyReporter, DairyNews.today, USDA/AMS Dairy Market News
- **Técnica** (prioridade sobre notícia em pautas de genética/manejo): sites oficiais de Alta Genetics, ABS, Semex
- **Científica**: Journal of Dairy Science, Journal of Animal Science

## Regras de verificação — inegociáveis

1. **Todo número tem duas fontes independentes.** Se só uma fonte sustenta um
   dado numérico, o dado não entra no post. Cortar o número é sempre preferível
   a publicá-lo sem confirmação.
2. **Hierarquia quando as fontes divergem**: Cepea > agregador de notícia para
   mercado; site oficial da empresa > notícia de terceiro para dado
   técnico/institucional; periódico revisado por pares > fonte não revisada
   para achado científico.
3. **Divergência real entre fontes → NÃO PUBLICA.** Não escreve o JSON, não abre
   PR, não publica com ressalva. Encerra relatando o impasse, dizendo qual
   número divergiu e o que cada fonte afirmava. **Silêncio é a resposta certa** —
   um post com ressalva ainda é um post publicado.
4. **Data no futuro é sinal de erro, não de furo.** Recusar qualquer dado cuja
   data de referência seja posterior a hoje. Já aconteceu: um resumo de busca
   citou dado de 28 de agosto num dia 20 de agosto. Conferir a data antes de
   usar o número.
5. **Resumo de busca não é fonte.** A busca serve para *encontrar* a matéria; o
   número tem de ser lido na página da fonte. Se a fonte não abrir (bloqueio de
   rede, site fora do ar), ela não conta como uma das duas — e sem duas, não
   publica.
6. **Nunca reproduzir texto de fonte verbatim.** Parafrasear sempre; no máximo
   expressões-chave curtas.

## Formato do post

- Título (`manchete`), lide de 1–2 frases (`resumo`), 2–3 parágrafos de
  desenvolvimento (`materia`)
- **Máximo 350 palavras**, tom estritamente informativo, sem opinião do autor e
  sem promoção do software
- Citação inline sem link ("segundo o Cepea/Esalq…"); links completos só em
  `fontes`

## Publicação

Criar **um arquivo novo** em `backend/fazenda/seed_data/milknews_lotes/`,
chamado `milknews_AAAAMMDD.json`. **Nunca editar nem apagar um lote já
publicado** — o histórico do blog é imutável; correção vira post novo.

O arquivo é uma **lista** de 1 a 3 posts. Ler o lote mais recente do diretório
antes de escrever e replicar o schema exatamente. Hoje ele é:

```json
[
  {
    "manchete": "…",
    "resumo": "…",
    "materia": "…",
    "link": "/news#milknews-AAAA-MM-DD-01",
    "data_publicacao": "AAAA-MM-DD",
    "fontes": ["https://…", "https://…"]
  }
]
```

`link` segue `/news#milknews-<data com hífens>-<sequencial 01, 02, 03>`, e o
sequencial reinicia a cada dia. `fontes` traz **todas** as fontes que
sustentam o post — é o registro de auditoria de quem conferiu o quê.

Validar o JSON (`json.load`) antes de commitar. Um lote malformado quebra o
seed do blog.

## Fecho

Commit e **pull request**. O corpo do PR diz, para cada número publicado, quais
fontes o sustentam — é o que permite a alguém auditar sem refazer a pesquisa.

Se nada verificou, **não abrir PR**: relatar o impasse e encerrar. Uma execução
que termina sem publicar nada é um resultado legítimo e frequente.

## Cadência

3 a 5 posts por semana, variando entre mercado/cotação, notícia setorial,
técnica e científica. Rodando diariamente, é esperado — e correto — que alguns
dias não rendam post.
