# Réguas de referência: conferência mensal (tarefa do robô MilkNews)

> **Para quem é este documento:** a Routine **"Milknews: checar fontes do simulador de preço do
> leite"** (segunda-feira, 12h UTC). Uma vez por mês, na **primeira segunda-feira do mês** (dia 1 a 7),
> ela executa também esta tarefa. Nas demais segundas, ignore este documento.

## O que é

As réguas de referência são as faixas cinzas da tela Relatórios › Réguas de referência (ex.: comida ÷
receita do leite 40–55%). Cada faixa é uma **estimativa de mercado** compilada de fontes públicas
nacionais e internacionais. Os dados ficam em **`backend/fazenda/seed_data/reguas_referencia.json`**
(fontes, faixas, selo de fidedignidade, validade). O código que valida o arquivo é
`backend/fazenda/rules/reguas_referencia.py`, e o CI roda `backend/tests/test_reguas_referencia.py`.

Nada aqui é dado de cliente. O arquivo é igual para todas as fazendas.

## Como ler as fontes (importante)

1. **Leia sempre primeiro pelos meios comuns:** `WebFetch`, `WebSearch` e `curl` pelo proxy do ambiente
   (PDF: baixar para um diretório novo e vazio, ler com `pdftotext` ou `python3 -I`, nunca rodando código
   de dentro do diretório baixado).
2. **O Firecrawl só entra quando a leitura comum for impossível** (resposta 403/bloqueio do site, página
   que só carrega por JavaScript, PDF que não abre). Antes de usá-lo, registre no relatório qual fonte
   falhou e por quê. Sem `FIRECRAWL_API_KEY` ou sem créditos, **não insista**: marque a fonte como "não
   lida nesta rodada" e siga.
3. Resultado de busca **nunca** vale como fonte lida. O número tem de estar na página aberta.

## Passo a passo

### 1. Triagem (barata, todo mês)
Para cada fonte de `fontes[]` do JSON, abra a URL e veja se a página ainda existe, se o conteúdo
publicado mudou (nova edição, novo ano, nova versão do PDF) e se a **licença** continua a mesma.
Procure também publicação nova das mesmas instituições: CNA/Campo Futuro, Anuário Leite
(Embrapa/Labor Rural), PDPL/MilkPoint, DairyNZ, Minnesota FBM, UMN/UW Extension, Dairy Australia.

### 2. Releitura funda (só das fontes que mudaram)
Releia as fontes que tiveram edição nova e recalcule as réguas que dependem delas. Extraia o número e a
**definição** (alimentação inclui volumoso? mão de obra inclui a família? receita inclui venda de
animais?). A definição pesa tanto quanto o número.

### 3. Regras de decisão (inegociáveis)
- Cada faixa precisa de **uma fonte nacional e uma internacional, independentes**, lidas por inteiro. Sem
  isso a régua é `PARCIAL` ou `NAO_VALIDADA` e não pode ser promovida.
- Selo `alta`: 2 nacionais + 2 internacionais, fontes com no máximo 3 anos. `media`: 1 + 1 ou ajuste de
  definição documentado. `baixa`: um lado só ou conversão. `NAO_VALIDADA`: nunca exibe faixa.
- **Divergência real entre fontes** (não complementar): **não altere a faixa**. Descreva o impasse no
  relatório. Silêncio é melhor que número incerto.
- **Data no futuro** é erro, não achado. Recuse.
- **Fontes proibidas:** AHDB, IFCN e qualquer dado do Cepea (licença que não permite uso comercial).
  Cepea só pode ser citado em texto com link, sem reproduzir dado. O validador recusa esses domínios.
- Nunca copie tabelas de obra com direitos reservados (Anuário Leite, NW Farm Credit): cite o número com
  link.
- Mudança de classe, de selo, de licença ou de faixa maior que **5 pontos percentuais** (ou 20% do valor,
  nas razões e nos meses) vai **destacada** no topo do relatório.
- Nunca grave no banco de produção. Nunca use credenciais.

### 4. O que o robô altera no JSON
| Situação | O que fazer | Mescla sozinho? |
|---|---|---|
| Tudo confirmado, nenhum número mudou | Atualize só `conferida_em` (hoje) e `proxima_conferencia` (primeira segunda-feira do mês seguinte) | **Sim**, se o diff tocar somente esses dois campos |
| Faixa, classe, selo, fonte, licença, ressalva ou condição mudou | Altere o que mudou, `revisado_em` = hoje, `conferida_em` = hoje, `versao` = `AAAA-MM`; **não** mude `valido_ate` | **Não.** Abra o PR e espere o dono |
| Faltam 60 dias ou menos para `valido_ate` | Abra PR de renovação (`valido_ate` = revisado_em + 12 meses), mesmo sem mudança de número | **Não.** Só o dono renova a validade |
| Régua nova ou fonte nova | Inclua em `fontes[]`/`reguas[]` e siga as regras acima | **Não** |

Verificação do "só data": compare o JSON antigo e o novo; se qualquer chave além de `conferida_em` e
`proxima_conferencia` diferir, **não** mescle sozinho.

### 5. Verificar e entregar
1. `cd backend && python3 -m pytest tests/test_reguas_referencia.py -q` precisa passar.
2. Branch novo a partir de `main` (`claude/reguas-referencia-AAAAMM`), commit, push, PR para `main`.
3. O corpo do PR traz: fontes abertas por inteiro (com URL), fontes que falharam e o motivo, se o Firecrawl
   foi usado (e por quê), tabela "antes → depois" das faixas alteradas, e os destaques.
4. Mescle (squash) **somente** o caso "só data" da tabela acima. Qualquer outro PR fica aberto.
5. Termine com um relatório ao dono começando com **"RÉGUAS DE REFERÊNCIA — CONFERÊNCIA DE AAAA-MM"**:
   o que mudou, o que divergiu, o que não foi lido e o que ele precisa decidir.

## Como isso aparece na tela

A tela lê `GET /financeiro/reguas-referencia` (somente leitura). Dele saem a caixa de alerta do topo
(versão, última conferência, próxima), o pop-up "Como calculamos e quão confiável é" (fontes, selo por
régua, ressalvas) e as faixas. Se `valido_ate` passou, o endpoint não devolve nenhuma faixa e a tela mostra
"sem referência atualizada". Régua com `exibir_faixa: false` mostra o número da fazenda sem faixa.

## Pendências antes de mostrar a clientes (decisão do dono, fora do alcance do robô)
1. Corrigir os cálculos: comida só das vacas em lactação (ou avisar a diferença), cobertura da dívida
   descontando a retirada da família, reserva em meses de custeio por capital de giro.
2. Parecer jurídico sobre as licenças e o texto de responsabilidade.
3. Autorização do Cepea (CC BY-NC 4.0) antes de qualquer dado dele.
4. Revisão por zootecnista ou economista rural.
