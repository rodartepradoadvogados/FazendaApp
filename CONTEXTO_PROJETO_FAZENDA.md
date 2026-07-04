# PROJETO PAINEL FAZENDA JAIRO NASSER — Contexto para continuidade (Claude Code / Antigravity)

> Documento vivo para dar continuidade ao projeto sem perder a linha de raciocínio.
> Última atualização automática pelo assistente. Fazenda: **Estreito Ponte de Pedra** — pecuária leiteira (Girolando/Holandês).

---

## 1. Objetivo do projeto
Painel gerencial único (hoje em Excel com macro `.xlsm`) que consolida **produção, dieta, reprodução, rebanho, estoque, financeiro (conta gerencial)** e uma **agenda preditiva diária** de eventos e tarefas — puxando dados de relatórios do **Ideagri** (CSV) com **o mínimo de digitação manual**. Próximo passo do dono: migrar essa lógica para um **software próprio**, desenvolvido no **Claude Code + Antigravity (Google)**. Este documento é a ponte.

**Identidade visual:** cor vinho `#5E1A2E` (principal), dourado `#B8860B`, logo "Fazenda Jairo Nasser". Fonte Calibri.

---

## 2. Arquivo atual
- `PAINEL_FAZENDA_v4.xlsm` (renomeado pelo dono; era v3) na pasta **G:\Meu Drive\FAZENDA\Fazenda\CLAUDE - RELATÓRIOS**.
- Macros: **Módulo1** (refresh de dados) + **Módulo2** (motor da agenda). Senha de proteção de planilha: `fazenda`.
- Botão **CAPA › ATUALIZAR DADOS** → roda `AtualizarDados` (lê os CSV e reescreve as abas de dados).
- Botão **8·AGENDA › ATUALIZAR AGENDA** → roda `AtualizarAgenda` (recalcula a agenda a partir das abas já carregadas). **NÃO** relê os CSV.

### Abas
CAPA · 1·PRODUÇÃO · 2·DIETA · 3·REPRODUÇÃO · 3.1·REP-RESUMO · 4·REBANHO · 5·ESTOQUE · 6·FINANCEIRO · 6.1·LIVRO CAIXA · 7·RESULTADOS · 8·AGENDA · (dados) REPRODUTIVO, LEITE, GERAL, DIETA, ESTOQUE, CURVA_ABC, FLUXO, DRE, CONTA_GER · (oculta) AGENDA_MANUAL.

---

## 3. Fontes de dados (CSV na pasta) — de onde tirar no Ideagri
| Arquivo (.csv) | Origem no Ideagri | Observação |
|---|---|---|
| FC | Fluxo de caixa | sempre desde 12/2025 |
| ABC | Curva ABC | sempre desde 12/2025 |
| DIETA | padrão | só muda se mudar a dieta |
| ESTOQUE | Inventário | data atual |
| GERAL | Meus Relatórios ▸ Geral | situação atual por animal |
| CONTA_GERENCIAL | Relatórios ▸ Gestão ▸ Movimentação financeira por conta gerencial | filtrar desde 12/2025 |
| 1 - Consulta_SQL_Dados_Reprodutivos_e_Produtivos_Versao_8 | Utilitários ▸ Consulta SQL (colar o SQL da pasta IDEAGRI/SQL) | exportar .csv |
| Lista_de_controles_leiteiros... | Utilitários ▸ Consulta SQL (arrastar o arquivo) | exportar .csv |

Encoding dos CSV: **Windows-1252 (Latin-1)**, separador `;`, decimal com vírgula.

---

## 4. Esquema das abas de dados (colunas 1-based)
- **GERAL** (17): 1 N animal · 2 Dt nasc · 3 Idade meses · 4 Grupos atuais · 5 Categoria completa · 6 Cat. abrev · 7 **Sit. rep.** · 8 DEL · 9 Dt últ leite · 10 lt CL kg · ... · 16 Dt últ diag · 17 Diag. — *é a foto atual por animal.*
  - Sit. rep. observadas: `Ges.` (prenhe), `Vaz. apt.` (vazia apta), `Vaz. atr.` (vazia em atraso), `Vaz. pev` (em PEV), `Ins.` (inseminada).
  - Grupos: `01 - NOV. ALTA`, `02 - VACAS ALTA`, `03 - MÉDIA`, `04 - PRÉ-PARTO`, `05 - SECAS`, `06/07/08 - BEZ 1/2/3`, `09 - DESMAMA`, `10/11 - RECRIA 1/2`, `12 - NOV. PRENHES`, `13 - NOV. HOLANDESAS`, `14 - NOV. 7/8`. **Atenção: há registros sujos com 2 grupos separados por vírgula** (ex.: `03 - Média,01 - NOV. ALTA`) — precisa limpeza na origem (Ideagri).
- **REPRODUTIVO** (43, uma linha por serviço): 1 MATRIZ · 2 RAÇA · 3 DATA NASC · 4 DT ÚLT PARTO · 5 ORDEM PARTO · 10 DT SERVIÇO · 11 TIPO SERVIÇO · 20 DT DIAGNÓST · 21 **DIAGNÓSTICO** (POSITIVO/NEGATIVO/ABERTO) · 24 PEV · 39 DEL SERVIÇO · **41 ÚLT OCORR (1 = última ocorrência do animal)** · 42 CATEGORIA · 43 IDADE. Também tem ORD TENTATIVA e outras.
- **CONTA_GER** (15): 1 Conta gerencial (hierárquico, ex. 3.01.03.01) · 2 Descrição · 3 Dt venc · 4 Dt pag/receb · 5 Dt comp · 6 Fornecedor/cliente · 9 Vlr total · 12 Vlr pago · 14 **Centro de custo** (PL=Pecuária Leiteira, C|26=Custeio 2026, ARR=Arrendamento) · 15 Dt emissão.
- **ESTOQUE** (9): 1 CATEGORIA · 3 PRODUTO · 4 QTD · 5 EST MÍN · 6 UN · 7 VLR UNIT · 8 VLR TOTAL · 9 ABAIXO. Hormônios (categoria "Produtos veterinários - Hormônios/similares"): Sincrogest (implante), CIDR, Sincrodiol 50ml, Sincroforte 20ml, Estron 60ml, SincroCP 50ml, Lactotropin 500mg. **QTD = unidades (1 = 1 unidade; caixa de 10 é lançada como 10).**

---

## 5. Regras de negócio (validadas com o dono)
- **Gestação por raça:** Holandês 280, Girolando ~287, Gir/Zebu/GO 295 dias. Parto provável = DT SERVIÇO da prenhez + gestação.
- **Pré-parto:** 35 dias antes do parto provável (vacas e novilhas prenhas).
- **Secagem:** 60 dias antes do parto provável — **somente vaca em lactação (que já pariu); novilha de 1ª cria não seca.**
- **Scratch (adesivo):** 14 dias após o **último** serviço (novo cio zera o anterior). **Diagnóstico NEGATIVO cancela o scratch** (a inseminação não conta).
- **PEV:** 45 dias (liberação para inseminar).
- **IATF:** protocolo D0/D7/D9 + IA no D11. D0: 1 implante (Sincrogest ou CIDR) + 2ml Sincrodiol (Benzoato) + 2,5ml Sincroforte (Buserelina). D7: 2ml Estron (Cloprostenol). D9: 2ml Estron + 1ml SincroCP (Cipionato). **Candidatas** = vazias aptas/atrasadas (e diagnosticadas negativo). **O implante costuma ser o gargalo de estoque.**
- **BST (Lactotropin/Boostin):** a cada 12 dias (próxima 02/07/2026), **só lactantes (grupos 01/02/03) com DEL ≥ 60 e faltando > 15 dias para secar.** Listar quem NÃO recebe.
- **Desmama:** 90 dias de nascido (bezerreiros → desmama).
- **Transições por peso (não há peso na base ainda):** Recria 1 a 160kg, Recria 2 a 250kg, novilha apta à IA 280-300kg. Hoje só se agenda a pesagem; a transição é manual (o dono altera no Ideagri).
- **Pesagens:** leite toda quinta; bezerros (Bez 1/2/3 e Desmama) a cada 15 dias na terça; Recria 1/2 a cada 2 meses na terça.
- **Visita reprodutiva Alpha/ABS (Carlos):** a cada 21 dias, sexta (próxima 03/07/2026).
- **Lotes:** 1 = novilhas alta lactação; 2 = vacas alta; 3 = média/final de lactação/baixa/tratamento (mastite, leite fora do tanque). Sobe de lote com ≥ 20 DEL e boa produção.

---

## 6. Motor da agenda (Módulo2 — arquivo `MODULO_AGENDA_v2.txt`)
Subs principais: `AtualizarAgenda` (recalcula tudo p/ hoje), `AdicionarEvento` (linha manual I3:M3 → aba AGENDA_MANUAL oculta), `SetupAgenda` (cria abas/botões, corrige capa), `CorrigirCapa`, `ChecarHormonios`, `SecHdr`, `CorCat`, `Botao`, `Gest`.
Categorias e cores claras: Reprodutivo, Sanidade, Produção, Gestão/Financeiro, Atividades. Blocos fixos no topo: **Candidatas à IATF**, **Checagem de hormônios** (doses necessárias × estoque), **BST** (elegíveis + exclusões com DEL), **Contas a pagar 10 dias**, e a **tabela cronológica** com filtro.

---

## 7. SINDICÂNCIA (RESOLVIDA nesta rodada) — por que a dieta/trato não atualiza

**Sintoma:** painel mostra **18** animais no lote 1; fisicamente são 8.

**Diagnóstico definitivo (testado ao vivo):**
- O arquivo **G:\...\CLAUDE - RELATÓRIOS\GERAL.csv em disco** tem **151 animais** e **14** no grupo `01 - NOV. ALTA` (16 contando grupo secundário). Confirmado por leitura direta do arquivo.
- A aba **GERAL dentro do .xlsm** termina na linha **129 (128 animais)** e conta **18** em `01`. Ou seja, é uma **importação antiga**, diferente do CSV atual.
- Cliquei **CAPA › ATUALIZAR DADOS** → "sucesso"; **reexecutei** → mesmo resultado (128/18). Forcei recálculo total (Ctrl+Alt+F9) → não muda. **Não é botão errado, nem fórmula, nem recálculo.**
- **Causa-raiz:** o VBA lê o CSV com `Open ... For Input` (função `Linhas`), e no **Google Drive (G:, File Stream)** essa leitura clássica pega uma **cópia local em cache/desatualizada** do arquivo, enquanto o conteúdo novo já está na nuvem. O painel processa o CSV velho → 128/18.
- A fórmula de consumo por lote (`CONT.SE(GERAL!D:D;"01 - *")`) está correta; ela conta a aba GERAL, que é que está desatualizada.

**CORREÇÃO (fazer no Drive — resolve todo o pipeline):**
1. No Explorer/Google Drive, clicar com o botão direito na pasta **CLAUDE - RELATÓRIOS** → **"Disponível off-line"** (Available offline). Isso materializa os arquivos localmente e o VBA passa a ler a versão real e atual.
2. Após importar novos CSV do Ideagri, **aguardar o ícone de sincronização do Drive ficar "concluído"** antes de clicar ATUALIZAR DADOS.
3. Alternativa mais robusta: manter os CSV numa **pasta local** (fora do Drive) e apontar `PASTA` da macro para lá — elimina o problema de cache de vez. **(Recomendado para o software novo: ler os CSV de pasta local ou via API do Ideagri, não do Drive espelhado.)**
4. Ponto de dado separado (Ideagri): mesmo corrigido o cache, o Ideagri tem 14 no grupo `01` vs 8 físicos → **reclassificar os grupos no Ideagri** e reexportar. O painel sempre reflete o Ideagri (fonte da verdade).
5. Melhoria de fórmula p/ o software: tratar **múltiplos grupos por animal** (campo com vírgula, ex. `03 - Média,01 - NOV. ALTA`) — hoje o COUNTIF só pega o grupo primário.

---

## 8. Pendências / próximos passos (backlog)
- [ ] **3·REPRODUÇÃO:** adicionar filtros por **ordem de parto** (REPRODUTIVO col 5) e **ordem de tentativa** (ORD TENTATIVA) — tabelas/dashboards passam a respeitá-los.
- [ ] **Layout mais profissional** (menos "cara de Excel", mesmas cores): cabeçalhos com faixas, espaçamento, sem sobreposição de gráficos/tabelas; pensar como o Ideagri. Ideal já mirando o software próprio (web/app) no Claude Code + Antigravity.
- [x] **Agenda DEPLOYADA no .xlsm** (Módulo2 reinjetado, compilado sem erro, `SetupAgenda` rodado = 130 eventos, arquivo salvo): diagnóstico NEGATIVO cancela scratch e o serviço não conta prazo (nem candidata à IATF); novilha não seca; não agenda tarefa se já está no grupo-alvo; cores claras por categoria; botões iguais/travados; cabeçalhos destacados; nº das vacas em negrito no BST; AGENDA_MANUAL oculta; área de inclusão destacada; "ADICIONAR À AGENDA". Código-fonte de referência: `MODULO_AGENDA_v2.txt`.
  - Obs.: os números atuais da agenda (17 candidatas IATF, 23 BST, Implante FALTA 16) foram calculados sobre a GERAL **em cache**; após aplicar a correção do item 7, rodar ATUALIZAR DADOS + ATUALIZAR AGENDA para números reais.
- [ ] **Peso por animal:** integrar uma fonte de pesagens (CSV do Ideagri) para as transições automáticas Recria/novilha apta.
- [ ] **Regime de competência × caixa** e **centro de custos** no Financeiro já implementados via CONTA_GER (Dt comp × Dt pag; coluna 14).

---

## 9. Como continuar no Claude Code
1. Abrir a pasta **G:\Meu Drive\FAZENDA\Fazenda\CLAUDE - RELATÓRIOS** no Claude Code.
2. Ler este `CONTEXTO_PROJETO_FAZENDA.md` (histórico e regras) + `MODULO_AGENDA_v2.txt` (motor da agenda) + os CSV.
3. Recomendação de arquitetura para o software próprio: separar **camada de dados** (parsers dos CSV/Ideagri → modelos: Animal, Servico, ContaGerencial, Estoque), **camada de regras** (as da seção 5, testáveis), **camada de visão** (agenda, financeiro, reprodução). Assim as regras da fazenda ficam versionadas e testadas — o que hoje está preso na macro VBA.
4. Manter este documento como fonte de contexto e atualizá-lo a cada decisão.
