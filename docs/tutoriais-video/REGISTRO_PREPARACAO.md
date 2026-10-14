# Tutoriais em vídeo do Financeiro do CowData — registro de preparação

**Data:** 14/10/2026 · **Etapa:** preparação (sem roteiro, sem vídeo, nada gerado no HeyGen) ·
**Objetivo da etapa:** garantir que o produto que vai aparecer nos vídeos é **real e de qualidade**, e deixar
tudo registrado para a produção (modelo Opus 5.5) começar do ponto certo.

> Disciplina de verificação (AGENTS.md): cada afirmação abaixo traz o seu estado. **Verificado** = rodei e vi o
> resultado nesta sessão. **Não verificado** = não rodei; está dito o que falta. Tela e número vieram do sistema
> rodando com dados fictícios, não da fazenda real.

---

## 1. Resumo executivo

- O **sistema financeiro é real e funciona**: subi o backend e o front, entrei pela tela de login, naveguei as
  22 telas do Financeiro e dos Lançamentos (0 erros de console, ~4 s cada em build de produção), **lancei uma
  despesa e dei baixa em uma conta pelos cliques da interface** e conferi pela API que o dado gravou (saldo do
  banco caiu exatamente o valor pago).
- O **ambiente de demonstração é reproduzível com um comando** (`ambiente-demo/rebuild.sh`): fazenda fictícia
  "Fazenda Vale Verde", ~45 vacas, ~13.000 L/mês, margem do mês anterior de 27%, datas relativas a "hoje".
- A **captura de tela com cursor visível, em 1920×1080, funciona** (Playwright → WebM → ffmpeg H.264). O ffmpeg
  tem `zoompan`, `xfade`, `drawtext`, `overlay`, `loudnorm`, `libx264`.
- A **voz do Jairo está no HeyGen** ("Voz Jairo Rodarte", a do avatar dele) e o áudio é acessível pelo proxy. Uso autorizado
  pelo Jairo (§8). **Não gerei fala** (não verificado: qualidade e custo da fala).
- O refinamento no **HyperFrames local** é viável em tese (pacote npm `hyperframes` 0.8.157 existe, Chromium e
  ffmpeg estão aqui) mas **não foi instalado nem testado**.
- Há **9 armadilhas de gravação observadas** (§6) e **lacunas de dados/produto** (§7). Nenhuma impede a produção; todas têm
  contorno registrado.

## 2. Estado da verificação

| # | Item | Estado | Evidência |
|---|------|--------|-----------|
| 1 | Backend sobe com SQLite local e cria tabelas/seeds | **Verificado** | startup ~1–2 min, `/health` ok |
| 2 | Login pela tela (`#login-usuario`, `#login-senha`) | **Verificado** | Playwright; a sessão persiste e vale nas demais telas (`storageState`). Para onde a tela redireciona logo após o Enter não foi conferido |
| 3 | Fazenda fictícia + contrato + "Preparar financeiro" (73 contas, regras v2 ligadas) | **Verificado** | `setup_fazenda.py` |
| 4 | 28 lançamentos (parcelas), 2 contas, saldos de abertura, extrato OFX | **Verificado** | `seed_demo.py` sem ERRO/FALHOU |
| 5 | 22 telas carregam sem erro | **Verificado** | build de produção, 0 erros de console |
| 6 | Lançar despesa pela interface (campo a campo) e ler de volta pela API | **Verificado** | LC gravado, R$ 840,00, conta e data corretas |
| 7 | Dar baixa pela interface | **Verificado** | saldo Banco Exemplo 83.970 → 68.770 (−15.200), `forma=pix`, conta ligada |
| 8 | Conciliação: importar OFX | **Verificado** | 9 linhas, 8 sugestões exatas, diferença −R$ 29,90 |
| 9 | Custo por litro com litros pela nota | **Verificado** | R$ 1,41/L, 13.000 L, `fonte=nota` (exige item de estoque "Leite") |
| 10 | Gravar vídeo da tela com cursor, converter com ffmpeg | **Verificado** | WebM 1920×1080 25 fps → MP4 30 fps (clipe de teste descartado) |
| 11 | Datas em dd/mm/aaaa na gravação | **Verificado** | exige `LANGUAGE/LC_ALL/LANG=pt_BR` no processo do Chromium |
| 12 | Faixa "AMBIENTE DE TESTE" e selo do modo dev somem | **Verificado** | `eh_teste=False` + `next start` (produção) |
| 13 | Áudio do HeyGen acessível pelo proxy | **Verificado** | `HEAD` na prévia da voz → HTTP 200 |
| 14 | Gerar fala com a voz do Jairo | **Não verificado** | decisão do Jairo: nada gerado no HeyGen nesta etapa |
| 15 | Conciliação pela interface (confirmar sugestões, lançar a tarifa) | **Não verificado** | só a API e a tela de leitura |
| 16 | Receita, lote, folha, cartão, patrimônio, fatura, orçamento, fechar mês, exportar Excel/PDF, pacote do contador (download) | **Não verificado** | as telas abrem; os fluxos de escrita não foram exercitados |
| 17 | App de campo `/app` (mobile) | **Não verificado** | fora do escopo desta etapa |
| 18 | HyperFrames local (instalar, compor, renderizar) | **Não verificado** | só confirmei que o pacote existe no npm |
| 19 | Tela vertical de celular (430×932, escala 2) | **Verificado** | Resumo, Contas a pagar e DRE abrem sem rolagem horizontal; **o botão News e o sino cobrem a faixa de abas** (aparece "CO›" cortado) |
| 20 | Outras resoluções (1366×768) | **Não verificado** | só 1920×1080 e 430×932 |

## 3. O sistema financeiro — mapa para quem vai ensinar

Leitura de fundo (obrigatória antes do roteiro): `README.md`, `CONTEXTO_PROJETO_FAZENDA.md`, `PRODUCT.md`,
`DESIGN.md`, `docs/financeiro-regras-v2.md`, `docs/financeiro-fechamento-conciliacao.md`.

**Visual ("Institucional")**: cantos quase retos (2 px), sem gradiente nem sombra, marinho `#0E2A47`, ouro só em
confirmar/destaque, números tabulares, rótulos em caixa-alta condensada; as telas "leem como relatório/extrato".
Fundo de página com a foto das vacas, desfocada. Fonte do app: a carregada pelo próprio Next.

**Menu**: `Resumo · Contas · Consultas · Relatórios · Patrimônio · Cartão de crédito · Documentos`
(sub-abas em Contas e em Relatórios). Lançar fica em `Lançamentos` (menu lateral), não no Financeiro.

### Telas e endereços (todas com `http://localhost:3000` + o caminho)

| Pergunta que a tela responde | Caminho | Estado dos dados de demo |
|---|---|---|
| Como está o financeiro hoje? (vencimentos, saldos, o que pede ação) | `/financeiro?sub=resumo` | rico |
| O que devo pagar? / receber? | `/financeiro?sub=a_pagar` · `a_receber` | rico (1 vencida, 2 a vencer, 1 parcelada) |
| Baixar várias de uma vez | `/financeiro?sub=lote` | usa as mesmas contas em aberto |
| Folha, faturas, caixa dos funcionários | `sub=folha` · `faturas_gestao` · `caixa_funcionarios` | **vazio** |
| Consultar qualquer lançamento (filtros, livro caixa) | `/financeiro?sub=consultas` | rico |
| Como está a fazenda? (4 perguntas do dono) | `/financeiro?sub=painel_dono` | rico |
| Estou ganhando? (DRE, resultado por litro, classificar) | `sub=rel_dre` · `rel_litro` · `classificar` | rico; "Classificar" vazio (tudo classificado) |
| Quando o caixa aperta? | `sub=rel_caixa` · `rel_fluxo` · `rel_livro` | rico |
| Quanto custa meu litro? | `sub=custos` · `rmca` · `reguas_referencia` | rico |
| Gastei o que planejei? | `sub=rel_orcamento` · `rel_cenarios` | **vazio** (orçamento não criado) |
| Compra/venda de animais, sêmen | `sub=compra_venda_animais` · `compra_semen` | **vazio** |
| Está pronto para o contador? | `sub=fechamento_mes` · `conciliacao` · `pacote_contador` | fechamento e conciliação ricos; pacote abre em 2025 (§7) |
| Patrimônio, cartão, documentos | `sub=patrimonio` · `cartao_credito` · `documentos` | **vazio** |
| Lançar despesa / receita | `/lancamentos?ir=financeiro_despesa` · `financeiro_receita` | formulário completo; abas Lançamento, Simplificado, Em lote, Faturas, Compra de sêmen |

Os relatórios aceitam na URL `per=m:AAAA-MM` (mês), `cmp=aa` (comparar com o ano passado) ou `cmp=nada`,
`reg=comp` (mês do gasto) ou `reg=caixa` (dia do pagamento), `cc=<centro de custo>`.

### Conceitos que o vídeo não pode ensinar errado

- **Dois regimes**: "Mês do gasto" (competência) × "Dia do pagamento" (caixa). A DRE e o Resultado por litro
  usam o mês do gasto por padrão; Caixa real, Fluxo e Conciliação usam o dia do pagamento.
- **Regras novas (`financeiro_regras_v2`)**: ligadas na fazenda demo. Só o operacional entra no resultado;
  investimento entra por depreciação; folha pelo bruto; juros/desconto da baixa vão para "Outras receitas e
  despesas"; litros do leite vêm da **nota** (exige item de estoque "Leite" marcado como produto de leite).
- **Contas a pagar ≠ DRE**: conta em aberto aparece em "a pagar" desde o lançamento, mas pesa na DRE pelo mês do
  gasto, não pelo vencimento.
- **Fechar o mês** trava lançamentos nesse mês (só com as regras novas) e grava um retrato com SHA-256; a trava
  ainda não cobre folha, cartão, compra de animal/sêmen e importação de CSV (docs/financeiro-fechamento-conciliacao.md §2).
- **Conciliação**: compara o extrato do banco (OFX/CSV) com o que foi pago no sistema, conta a conta; casa por
  valor ao centavo e data ±3 dias.

### Fluxos exercitados com cliques reais (seletores que funcionaram)

- **Login**: `#login-usuario`, `#login-senha`, Enter. A página inicial do app é a Capa (tem o nome da fazenda real fixo, §6); depois do login, navegar direto por URL.
- **Lançar despesa** (`/lancamentos?ir=financeiro_despesa`): 1º `select` = Fornecedor (já lista os que existem nos
  lançamentos); 1º `input[type=date]` = emissão, 2º = vencimento; o `select` de Produto tem "do estoque" / "texto
  livre"; botão "Escolha a conta (só o galho mais baixo)…" abre uma busca (digitar e clicar no texto da conta);
  botão "Informar valor total"; o campo de dinheiro é **máscara de centavos** (digitar `84000` → R$ 840,00);
  botão "Salvar lançamento"; sucesso = "Lançamento LC-AAAA-NNNNN salvo com sucesso." no rodapé e formulário zerado.
- **Dar baixa** (`/financeiro?sub=a_pagar`): botão "Dar baixa" da linha → gaveta `role=dialog` ("Dar baixa ·
  <fornecedor>"); valor já vem preenchido; 1º `select` = Conta corrente, 2º = Forma; botão "Confirmar baixa de R$ …".
- Os rótulos do formulário **não têm `for`/`id`** ligados aos campos (acessibilidade): `getByLabel` falha; use
  posição (`nth`) ou o texto do botão.

## 4. Ambiente de demonstração

**Subir (um comando, do zero):**

```bash
bash docs/tutoriais-video/ambiente-demo/rebuild.sh --front     # backend :8000 + build de produção do front :3000
```

Faz: venv fora do repo (`/tmp/cowdata-demo`) → SQLite descartável → usuário `teste_local` com **senha aleatória
em `/tmp/cowdata-demo/cred.txt`** (nunca no repositório, nunca em nota, nunca na tela) → fazenda "Vale Verde"
(`eh_teste=False`, usuário exibido como "Administrador") → plano de contas e regras v2 → `seed_demo.py`.
Leva alguns minutos (o build do front é o mais demorado). Recusa rodar fora de SQLite.

**Números de referência** (rodando em 14/10/2026; devem se repetir com a mesma estrutura em qualquer dia, pois as
datas são relativas a "hoje"; confira antes de gravar):

| O quê | Valor |
|---|---|
| DRE do mês anterior (set/2026), regime competência, centro Pecuária Leiteira | receita líquida R$ 41.150 · despesas R$ 29.940 · resultado R$ 11.210 · margem 27,2% |
| Mesmo mês do ano anterior (comparação) | receita R$ 33.040 · despesas R$ 26.930 · resultado R$ 6.110 · margem 18,5% |
| Resultado por litro (set/2026) | preço líquido R$ 2,95 · custeio R$ 2,30 · sobra R$ 0,65 (13.000 L; comida R$ 1,41) |
| Saldos hoje | Banco Exemplo R$ 83.970 · Cooperativa Exemplo R$ 6.200 (total R$ 90.170) |
| Contas a pagar em aberto | 7 · total R$ 23.070 (vencida R$ 15.200; vence em 7 dias R$ 2.840) · a receber R$ 18.000 |
| Conciliação set/2026, Banco Exemplo | 9 linhas, 8 sugestões exatas, diferença R$ −29,90 (tarifa que só está no extrato) |
| Fechamento set/2026 | 7 de 8 conferências ok; falta "Conciliação bancária feita" |

**Dados fictícios** (nomes inventados; confira que nenhum coincide com empresa real antes de publicar):
Laticínio Serra Azul, Agropecuária Boa Safra, Nutrimix Minerais, Silagem do Vale, Vet Exemplo Medicamentos, Posto
Rota 10, Energia Elétrica Exemplo, Oficina Ordenha Exemplo, Contabilidade Exemplo, Cliente Exemplo, Banco Exemplo,
Cooperativa Exemplo. **Nenhum dado, nome ou CSV da fazenda real** entra nos vídeos.

**Depois de gravar um fluxo que escreve** (lançar, dar baixa), os números mudam: rode `rebuild.sh` de novo antes
do próximo fluxo, ou grave tudo a partir de um mesmo estado inicial reconstruído.

## 5. Pipeline de produção (proposta, sem roteiro)

| Fase | O que | Ferramenta | Gate (quem aprova) |
|---|---|---|---|
| 0 | Reproduzir o ambiente e conferir os números de §4 | `rebuild.sh` | automático |
| 1 | Teste de voz: **uma frase curta** com a "Voz Jairo Rodarte" | HeyGen `create_speech` | Jairo ouve e confirma |
| 2 | Adaptar o **roteiro do Jairo** (carrossel animado 9:16) em cenas com tela/clique/zoom | Opus 5.5 | **Jairo aprova** |
| 3 | Locução (áudio) do piloto; medir a duração real | `create_speech` + ffprobe | Jairo ouve |
| 4 | Gravar a tela casando o ritmo dos cliques com a locução | Playwright (`gravar_exemplo.mjs`) | revisão visual |
| 5 | Motion simples: zoom, destaque, legenda, transições, áudio nivelado | ffmpeg (`zoompan`, `xfade`, `drawtext`, `loudnorm`) | Jairo aprova a rodada 1 |
| 6 | Refinamento de motion | HyperFrames local (pacote npm `hyperframes`; o MCP do HyperFrames indica `npx skills add heygen-com/hyperframes` — nenhum dos dois foi executado) | Jairo aprova a rodada 2 |
| 7 | Série: repetir para os demais temas | — | por vídeo |

**Voz**: usar a **"Voz Jairo Rodarte"** (`b7ab856295e947bab979a893cad2b326`; motor padrão Orca; voz padrão do avatar
"Jairo Rodarte"), autorizada pelo Jairo na conta conectada (conta correta; plano Creator, 600 créditos premium até
12/11/2026). Cada `create_speech` é uma geração e consome crédito; texto de 1 a 5.000 caracteres; aceita pausas
`<break time="0.35s"/>` e `speed` 0,5–2,0. **Nada de vídeo/avatar no HeyGen**: só áudio. O áudio volta como URL
(precisa baixar para o ffmpeg). Em caso de erro ou timeout, perguntar antes de tentar de novo.

**Gravação**: Playwright grava a 25 fps em WebM; converter a 30 fps. Gravar com **login feito antes** e o vídeo
começando já no Financeiro. Cursor desenhado por script (padrão ouro/marinho do sistema). Gravar o clique e a
navegação em tempo "humano" (movimento em 20–30 passos, pausa de 250 ms antes do clique).

**LGPD / segredos**: sem CPF, dados de saúde, tokens ou senhas em vídeo, nota ou repositório. Credencial do usuário
de teste só em `/tmp/cowdata-demo/cred.txt`.

**Registro**: ao fim de cada sessão, nota datada em `04_CowData/Milk/Sessoes/AAAA-MM-DD_assunto.md` (o Claude Code
só escreve em `*/Sessoes/`; o conector do Drive só cria arquivo novo). Aprovação é do Jairo (`status: aprovado`).

## 6. Armadilhas de gravação (todas observadas no app rodando) e o contorno

1. **Datas em formato americano** (`mm/dd/yyyy`, `10/14/2026`) mesmo com `--lang=pt-BR`: exige `LANGUAGE=pt_BR:pt`,
   `LC_ALL=pt_BR.UTF-8`, `LANG=pt_BR.UTF-8` no processo do Chromium (já em `gravar_exemplo.mjs`).
2. **Faixa vermelha "AMBIENTE DE TESTE — cópia da fazenda real Jairo Nasser"** em todas as telas quando `eh_teste=True`:
   o `setup_fazenda.py` põe `False` na fazenda de demonstração.
3. **Selo "N" e "Compiling…"** do Next em modo dev: gravar só com `next start` (build de produção).
4. **Tela de login e cabeçalho institucional citam a fazenda real** ("Estreito Ponte de Pedra · Jairo Nasser",
   `components/institucional/PublicShell.tsx`): login fora da gravação (storageState).
5. **A Capa (`/`) tem o título fixo "Fazenda Estreito Ponte de Pedra"** (`app/page.tsx:320`), não acompanha a fazenda
   ativa: nunca gravar a Capa; começar em `/financeiro?...`. O item "Capa" do menu lateral aparece, não clicar.
6. **Rodapé do menu mostra o nome do usuário** (aqui "Administrador") e "API conectada": ok, mas conferir antes de gravar.
7. **Sino com "2" e botão "News"** sempre no canto superior direito: origem não investigada; decidir se mantém.
8. **Rótulos sem `for`/`id`**: seletores por posição ou por texto de botão.
9. **Texto em caixa-alta é CSS**: no DOM é "Contas", não "CONTAS" (o seletor por texto falha com a caixa errada).

## 7. Lacunas de dados e de produto (contexto; as decisões estão no §8)

**Telas sem dados, vazias por decisão do Jairo (§8.6), não semear** — tutoriais desses temas (o sistema tem as telas; a demo não tem os dados): Orçamento
(planilha não criada), Patrimônio, Cartão de crédito, Folha/holerites, Gestão de faturas, Compra/venda de animais e
sêmen, Pedidos, Documentos, Classificação do lançamento (lista vazia no formulário), produtos de estoque além do
"Leite", Classificar (nada pendente), Conta corrente da Cooperativa sem movimento. **Cada tema novo pede um passo de
seed** — acrescentar a `seed_demo.py`.

**Produto (observações, nada corrigido nesta etapa):**
- Capa com nome de fazenda fixo (§6.5) e cabeçalho público com o nome real (§6.4).
- Rótulos de formulário sem associação a campo (acessibilidade) — afeta leitores de tela e automação.
- "Pacote do contador" abre no ano **anterior** (`per=a:2025`), vazio para esta demo: escolher o período antes.
- A comparação padrão é "mesmo período do ano passado": sem histórico do ano anterior mostra "melhor que set/25,
  quando ganhou R$ 0" (a demo já tem o mês do ano passado semeado; outros meses não).
- Mês corrente em andamento mostra resultado negativo (só uma quinzena de leite faturada): não usar para "estou
  ganhando?"; usar o mês anterior.
- O "Fôlego de 258 dias" do Caixa real sai de uma média de saída de poucos meses de dados: não comentar o número.

## 8. Decisões do Jairo (14/10/2026) — valem para toda a produção

1. **Voz**: autorizado o uso da voz dele no HeyGen, na conta conectada (a conta é a correta). É a voz do avatar
   "Jairo Rodarte": **"Voz Jairo Rodarte", `b7ab856295e947bab979a893cad2b326`** (voz padrão do avatar, verificada
   na listagem de avatares). A outra voz ("Jairo Rodarte", `43ccb854…`) **não** será usada. Só **áudio**; nada de
   vídeo ou avatar gerado no HeyGen.
2. **Sino e botão "News"**: **mantidos** visíveis.
3. **Faixa vermelha de teste**: **removida** (já resolvido no ambiente de demonstração: `eh_teste=False`).
4. **Formato**: **Instagram, stories e reels** (vertical **9:16, 1080×1920**), em **carrossel animado**. O Jairo
   tem um roteiro breve e o entregará no prompt de produção. (Duração de 1 minuto segue como referência dele.)
5. **Rótulos sem `for`/`id` e demais ajustes de produto**: **não corrigir**. Contornar na gravação (§6). Capa e
   cabeçalho público com o nome da fazenda real: **também só contornar** (nunca gravar a Capa nem o login).
6. **Telas vazias ficam vazias** (Orçamento, Patrimônio, Cartão, Folha, Faturas, Compra/venda de animais, Pedidos,
   Documentos): ele não vai usá-las agora. **Não semear dados para elas.** Os vídeos usam só as telas com dado.

### Consequência para o vertical 9:16 (a decidir na produção, com o roteiro dele)
O app é um site: em 1920×1080 tem barra lateral, abas e muito espaço; em celular (430 px) ele reorganiza, mas o
News e o sino sobrepõem a faixa de abas. Duas formas de montar o carrossel:
- **A (recomendada)**: gravar em 1920×1080 (cliques reais, tudo legível) e montar cada slide 1080×1920 recortando e
  ampliando a região que importa (card, tabela, gráfico), com título e legenda no padrão do CowData. Mantém o
  News/sino quando o recorte pega o canto superior direito.
- **B**: gravar a versão responsiva (430×932, escala 2 → 860×1864) e usar quase em tela cheia. Mais "cara de
  celular", mas as abas ficam parcialmente cobertas e a barra superior ocupa espaço.
Combinar A e B por slide também é possível. A escolha depende do roteiro; **não foi gravado nada em vertical ainda**.
