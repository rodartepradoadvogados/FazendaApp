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
Registre a leitura no `dossie` da régua (parecer 3.5): `valor_lido` e `pagina_ou_tabela` da fonte BR e da
estrangeira, `metodo_agregacao`, `compilado_por` (a rotina) e `compilado_em`. Isso é compilação; validar
é dos humanos (ver 4.1).

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
| A régua que mudaria já tem `dossie.validado_por` preenchido | **Não altere a faixa no JSON.** Descreva a proposta (antes → depois, fontes) no PR e no relatório. Quem esvazia a validação e revalida é o dono | **Não** |
| Faltam 60 dias ou menos para `valido_ate` ou para algum `dossie.vence_em` | Abra PR de renovação, mesmo sem mudança de número. Renovar é compilar de novo: atualize `dossie.compilado_em`/`vence_em` só junto com a releitura das fontes | **Não.** Só o dono renova a validade |
| Régua nova ou fonte nova | Inclua em `fontes[]`/`reguas[]` e siga as regras acima. Fonte nova nasce com `"ativa": true`, `"caminho_parecer": "verificar_antes"`, `"termos_verificados_em": null` e `"uso_comercial_confirmado_em": null`; régua nova nasce com `"ativa": true` e dossiê com `validado_por: []`, `termos_verificados_em: null` e `pendente_de: ["dono", "Alexandre Scarpa"]` | **Não** |
| Um termo de uso de fonte mudou (passou a proibir uso comercial, sumiu, mudou de licença) | **Não desligue a fonte você mesmo.** Destaque no topo do relatório e no PR: o dono retira (ver "Como retirar uma faixa em minutos") | **Não** |

Verificação do "só data": compare o JSON antigo e o novo; se qualquer chave além de `conferida_em` e
`proxima_conferencia` diferir, **não** mescle sozinho.

### 4.1 Campos que SÓ HUMANOS alteram (o robô nunca toca)
O parecer jurídico de 08/10/2026 (itens 3.3, 3.5 e 6.4) separa quem compila de quem valida. Por isso a
rotina **não altera, em linha nenhuma já existente**:

- `publicacao` (o bloco inteiro: `liberada`, `liberada_por`, `liberada_em`) — interruptor geral;
- `ativa` de qualquer régua ou fonte — interruptores por régua e por fonte;
- `dossie.validado_por`, `dossie.pendente_de` e `dossie.termos_verificados_em`;
- `termos_verificados_em` e `uso_comercial_confirmado_em` de qualquer fonte;
- `backend/fazenda/seed_data/textos_juridicos.json` (textos do alerta, do modal, do rodapé e o bloco
  `empresa`).

O validador (`backend/fazenda/rules/reguas_referencia.py::validar`, rodado pelo CI) recusa os estados
inconsistentes que uma edição automática produziria: faixa diferente da que foi validada, validação feita
por quem compilou, quem validou ainda em `pendente_de`, termos do dossiê marcados como lidos com fonte sem
termos, uso comercial confirmado sem termos lidos, termos lidos com licença `nao_verificada`, liberação
sem `liberada_por`/`liberada_em` ou com a empresa pendente, data humana no futuro. Se o PR da rotina ficar
vermelho por uma dessas mensagens, a correção é **desfazer a edição**, nunca mexer no campo humano.

### 5. Verificar e entregar
1. `cd backend && python3 -m pytest tests/test_reguas_referencia.py tests/test_reguas_parecer_api.py -q`
   precisa passar.
2. Branch novo a partir de `main` (`claude/reguas-referencia-AAAAMM`), commit, push, PR para `main`.
3. O corpo do PR traz: fontes abertas por inteiro (com URL), fontes que falharam e o motivo, se o Firecrawl
   foi usado (e por quê), tabela "antes → depois" das faixas alteradas, e os destaques.
4. Mescle (squash) **somente** o caso "só data" da tabela acima. Qualquer outro PR fica aberto.
5. Termine com um relatório ao dono começando com **"RÉGUAS DE REFERÊNCIA — CONFERÊNCIA DE AAAA-MM"**:
   o que mudou, o que divergiu, o que não foi lido e o que ele precisa decidir. Inclua a saída de
   `GET /painel-cowdata/reguas-referencia/diagnostico` (ou `rr.diagnostico()`): o que falta para cada régua
   ir ao ar.

## Como isso aparece na tela

A tela lê `GET /financeiro/reguas-referencia`. Dele saem a caixa de alerta do topo (texto 7.1 do parecer,
sem lista de fontes e sem Cepea), o modal/pop-up "Como calculamos e quão confiável é" (texto 7.2, com botão
"Entendi" registrado), o selo, as ressalvas e as faixas. Cada régua vem com `situacao`:
`publicada` | `em_validacao` | `retirada` | `vencida` | `sem_faixa`. **Fora de `publicada` não sai número
nenhum** (nem faixa, nem ressalva, nem quadro de fontes), e nada sai enquanto `publicacao.liberada` for
`false` ou o usuário não tiver dado o "Entendi" da versão vigente. Contratos completos:
`docs/reguas-referencia-parecer.md`.

## Como liberar e como retirar (só o dono)
- **Liberar:** PR revisado pelo dono que, depois do checklist abaixo, (1) preenche o bloco `empresa` em
  `textos_juridicos.json`, (2) registra a dupla validação e os termos no dossiê e nas fontes de cada régua e
  (3) liga `publicacao.liberada` com `liberada_por` e `liberada_em`. Nunca por parâmetro de cliente, nunca
  pela API, nunca pela rotina.
- **Retirar uma faixa em minutos:** PR de UMA linha — `"ativa": false` na régua (só ela sai) ou na fonte
  (a fonte some de todas as réguas; régua que ficar sem fonte nacional ou internacional ativa, ou sem a
  fonte base do dossiê, sai do ar sozinha). Para tirar tudo: `"liberada": false` em `publicacao`. Mescle e
  o deploy leva a mudança; a API passa a responder `retirada`/`em_validacao` sem número. Registre o motivo
  no PR (política 7.4 do parecer).
- **Por que não um botão no Painel CowData:** o repositório não tem padrão de parâmetro de plataforma
  "só desliga"; os parâmetros do Painel ligam e desligam. Criar um interruptor que só desliga exigiria
  tabela nova e uma segunda fonte da verdade além do JSON versionado — avaliado e deixado de fora. Se o
  prazo de "retirar em até 2 dias úteis" (política 7.4) não couber no ciclo de PR + deploy, esse é o
  próximo passo.

## Checklist de lançamento do parecer (item 10) — pendências HUMANAS
Nada abaixo é tarefa da rotina; fica aqui para o relatório mensal lembrar o que ainda falta.

- [ ] Empresa constituída (razão social, CNPJ) e campos dos Termos preenchidos (bloco `empresa`).
- [ ] Marca "CowData" pesquisada no INPI.
- [ ] Termos de cada fonte lidos por pessoa, com PDF/print datado (`termos_verificados_em` por fonte).
- [ ] Confirmação escrita da CNA/Senar; autorização do Anuário Leite (ou exclusão); decisão sobre Northwest
      Farm Credit (`uso_comercial_confirmado_em` ou `ativa: false`).
- [ ] Origem de cada número do Campo Futuro checada (nenhum dado do Cepea).
- [ ] Dossiê completo por faixa; **dupla validação** feita pelo dono e pelo Alexandre Scarpa
      (`validado_por`, `pendente_de: []`).
- [x] Alerta e pop-up substituídos pelos textos do item 7 (sem "Cepea", sem alegação não provada) —
      `textos_juridicos.json`; o trecho "uma fonte brasileira e uma estrangeira" só entra com dossiê comprovado.
- [ ] Aceite clickwrap com log imutável, hash, versão e comprovante (item 6.1) — infraestrutura pronta
      (`aceite_termos`, `POST /aceites`, `GET /aceites/comprovante`); falta o texto dos Termos de Uso.
- [x] Modal "Entendi" no primeiro acesso às réguas, registrado (backend pronto; a tela é do front).
- [x] Exportação desligada por padrão; autorização por envio; rodapé obrigatório; log (item 6.2) — backend
      pronto (`permitir_exportar_com_reguas`, `POST /relatorios/exportacoes`); a tela é do front.
- [ ] Sem semáforo; selo de confiabilidade e validade visíveis (front).
- [x] Kill switch por indicador e por fonte testado (`tests/test_reguas_referencia.py`,
      `tests/test_reguas_parecer_api.py`).
- [ ] Política de atualização e retratação publicada; e-mail do responsável ativo.
- [ ] Política de Privacidade com controlador, bases legais e canal do titular.
- [ ] Validação jurídica final dos artigos [CONFERIR] e da jurisprudência (dupla fonte).
- [ ] Avaliar seguro de responsabilidade civil.

## Outras pendências antes de mostrar a clientes (decisão do dono, fora do alcance do robô)
1. Corrigir os cálculos: comida só das vacas em lactação (ou avisar a diferença), cobertura da dívida
   descontando a retirada da família, reserva em meses de custeio por capital de giro.
2. Autorização do Cepea (CC BY-NC 4.0) antes de qualquer dado dele.
3. Revisão por zootecnista ou economista rural (a dupla validação do dossiê).
4. Coe ÷ receita: a fonte brasileira base do dossiê (SIA/Feed&Food) só serve como corroboração (parecer
   3.3); falta uma base nacional que não seja só corroboração.
5. Vacas em lactação ÷ vacas: a fonte estrangeira foi lida numa adaptação brasileira; sem o original da
   Virginia Cooperative Extension, a independência não se prova.
