# Proposta — Vacinas e exames · Protocolos · Agenda

> Contrato de design. Deriva de `01-critica-consolidada.md`. É a fonte que os mockups clicáveis reproduzem e que a banca do gauntlet-loop confere (`03-gauntlet-loop.md`).
> Restrições de marca (PRODUCT.md / DESIGN.md — não mudam): tokens CowData (`--vinho/--marinho`, `--dourado`, `--cat-*`), cantos 2px, sem sombra pesada, sem gradiente forte, Archivo (site), rótulos em caixa-alta condensada, alvos ≥44px no que for de campo, três temas.
> Decisão de produto tomada aqui (revisável): **o Preventivo sai da Central de Protocolos.** É recorrente e por grupo; protocolo é sequência e por animal/lote. A Central passa a ser só de protocolos de ciclo.

---

## 1. Princípios que guiam as três telas

1. **A primeira dobra responde "o que preciso fazer agora?"** — não "quantos indicadores existem".
2. **Uma coisa, um nome, uma porta.** Um único verbo de execução (**Registrar** na sanidade, **Feito** na agenda), um único lugar de escrita por objeto.
3. **Cor = estado; ícone + texto = tipo.** Nunca só cor.
4. **A tela não se apaga quando o usuário age.** Atualização otimista; a linha sai, a lista fica.
5. **Estado na URL.** Aba, visão, filtro e drawer abertos sobrevivem ao F5 e podem ser enviados por link.
6. **Progressive disclosure de verdade.** O que é análise ou configuração vive em gaveta; a lista de trabalho não carrega o peso.
7. **Nada bloqueia o campo:** avisos (estoque, carência) informam, nunca travam — regra já travada no `redesenho-evento-sanitario.md`.

---

## 2. Vocabulário canônico (glossário do produto)

| Termo hoje (vários) | Termo único | Definição |
|---|---|---|
| Regra · Protocolo cadastrado · Calendário sanitário · Evento sanitário | **Vacina do calendário** (ou **Exame do calendário**) | o que se repete: produto, quem entra, quando |
| Cronograma · Ocorrência · Janela · Rodada | **Aplicação prevista** | uma data concreta de uma vacina para um grupo de animais |
| Aplicação · Aplicado · Agendar aplicação | **Registrar aplicação** | dar baixa: quem, produto/lote do frasco, dose, data |
| Desconsiderar cronograma | **Pular esta aplicação** | com motivo opcional |
| Gatilho · Evento de vida | **Marco do animal** | ex.: "bezerra com 3 meses", "parto" |
| Vencidas · Atrasados · Pendências | **Atrasadas** | data prevista passou e não foi registrada |
| Realizado · Cumpriu? · Confirmar baixa · Dar baixa · Descartar (Agenda) | **Feito** · **Adiar** · **Não vou fazer** | |
| Scratch | **Checar retorno ao cio (14 d pós-inseminação)** | |
| IATF D0/D7/D9/D11 | **Inseminação programada — 1º/7º/9º/11º dia** (sigla IATF entre parênteses na 1ª vez, com tooltip) | |
| PEV | **Fim do período de espera (PEV)** | |
| DEL | **Dias em leite (DEL)** | |
| BST | **Somatotropina (BST)** | |
| Protocolo Customizado · Lida | **Protocolo próprio** · **Tarefa da fazenda** | |
| Estados da aplicação | **Prevista → Confirmada → Registrada** · **Atrasada** · **Pulada** | uma só escala; "Provável/Em edição" fundem em Prevista |

Regra de sincronia: nenhum texto do tipo "vá a X › Y" — sempre um link.

---

## 3. Vacinas e exames (nova casa do calendário preventivo)

Entrada: Sidebar › **Sanidade › Vacinas e exames** (Curativa, Rastreabilidade e Catálogo continuam em Sanidade). Sanidade **abre em Vacinas e exames › Calendário** (o que exige ação), não em Curativa.

### 3.1 Mapa de telas (todas com URL)

| Rota | Tela | Papel |
|---|---|---|
| `/sanidade/vacinas` (`?filtro=atrasadas\|7d\|30d&modo=lista\|mes\|ano&vacina=`) | **Calendário** | lista de trabalho + mês/ano; ação primária por linha |
| `/sanidade/vacinas/cobertura` (`?por=vacina\|lote\|animal`) | **Cobertura** | % em dia por vacina e lote; carteira por animal; carência; imprimir |
| `/sanidade/vacinas/historico` | **Histórico** | aplicações + exames num só lugar; filtros de data/lote/produto/animal; exportar |
| `/sanidade/vacinas/cadastro` (`?nova=1`, `?editar=ID`) | **Vacinas do calendário** | lista única + wizard de 3 passos em drawer |
| drawer `?prevista=ID` | **Aplicação prevista** | quem entra, produto/dose, quem aplica, mudar data, pular, **Registrar** |
| drawer `?registrar=…` (também aberto da Agenda, Rebanho e app) | **Registrar aplicação** | única porta de escrita |

### 3.2 Calendário (tela padrão)

Primeira dobra, de cima para baixo:
1. **Título + ação global:** "Vacinas e exames" · botão primário **+ Registrar aplicação** (avulsa) · secundário **Nova vacina do calendário** (leva ao cadastro) · **Imprimir folha de campo**.
2. **Faixa de 3 números (clicáveis = filtro):** **Atrasadas N** (vermelho) · **Esta semana N** · **Cobertura NN%** (verde/âmbar). Nada de 8 KPIs.
3. **Barra de visão:** `Lista | Mês | Ano` · filtro de vacina · filtro de lote · busca — numa linha só (máx. 4 controles visíveis).
4. **Lista de trabalho**, agrupada: **Atrasadas** (no topo, "há 6 dias") → **Esta semana** → **Próximas**. Colunas: estado (ícone+texto), vacina/exame, para quem ("38 novilhas · Lote Recria 2"), data prevista, produto/dose padrão, carência ("leite 3 d"), **[Registrar]** (botão dourado na linha) e menu ⋯ (Ver animais · Mudar data · Pular · Ver regra).
5. Clicar na linha abre o drawer **Aplicação prevista** (nunca troca de tela).

Estados da lista (cor + ícone + texto): Prevista (cinza tracejado) · Confirmada (azul-aço) · Registrada (verde) · Atrasada (vermelho + triângulo + "há N d") · Vence em ≤7 d (âmbar, texto âmbar-escuro) · Pulada (riscado). Legenda de uma linha no rodapé da lista.

Modo **Mês**: contagem por dia + legenda; clicar no dia filtra a lista. Modo **Ano**: matriz vacina × mês (campanhas de aftosa etc.).

Estado vazio (fazenda nova): "Monte seu calendário vacinal em 2 minutos" → **Usar modelo padrão brasileiro** (B19, aftosa, clostridioses, raiva, IBR/BVD/Lepto, vermifugação, TB/brucelose), editável, com aviso "ajuste com seu veterinário e a defesa sanitária estadual".

### 3.3 Drawer "Aplicação prevista"
Cabeçalho: vacina · data · estado · **Registrar**. Abas: **Animais** (lista com incluir/remover fora da janela, motivo opcional) · **Checklist** (estoque, veterinário, financeiro — pulável) · **Histórico**. Ações: Mudar data · Pular esta aplicação · Reabrir. Widget financeiro persistente e ficha de carência mantidos do `redesenho-evento-sanitario.md`.

### 3.4 Drawer "Registrar aplicação" (única porta de escrita)
Campos: **quem** (grupo/lote/animais, pré-preenchido da linha) · **produto** (do estoque, com frasco/lote e validade) · **dose e via** · **data real** (hoje/outra) · **quem aplicou** · custo (opcional).
**Antes de confirmar** mostra o resumo de consequência: "38 novilhas · 19 doses · estoque restante 41 · próxima dose 30/11 · leite em carência até 04/10 · R$ 342". **Registrar** → toast com **Desfazer (10 s)** que estorna estoque e aplicação (correção P0 da Agenda incluída). Idempotente (duplo clique/fila offline não duplica).

### 3.5 Cobertura
Faixa "Rebanho em dia: 94%". Tabela vacina × lote com % e "quem falta" (drill em lista). Aba **Por animal** = carteira de vacinação (tomadas, em dia, atrasadas, nunca tomadas) — também exposta na ficha do animal. Bloco **Carência**: "Leite em carência: 6 vacas até dd/mm · Carne: 2 animais". Ação: imprimir folha de campo / comprovante "animal em dia".

### 3.6 Histórico
Aplicações + exames (resultados numéricos/diagnóstico) num só grid; filtros data, lote, produto, animal; paginação servidor; exportar Excel/PDF; editar só admin, por via auditada.

### 3.7 Vacinas do calendário (cadastro)
Lista única (evento+regra fundidos), colunas: nome · tipo (vacina/exame/tratamento) · quem entra · frequência · próxima · usado por N · ativo. Ações: Editar · Duplicar · Ativar/Inativar; exclusão só pela via auditada e com "usado por N" visível.
**Wizard de 3 passos em drawer** (não 5): **1 O quê e para quem** (nome, tipo, produto, dose/via, categoria/lote-alvo, marco do animal opcional) · **2 Quando** (a cada N / na época / por marco; multidose: "dose 1 → +30 d dose 2 → anual") · **3 Conferir** (mostra "próximas 3 datas" e "N animais alcançados hoje"; texto de consequência). Escrita evento+regra **em uma transação**. Rascunho com chave por fazenda+usuário e faixa "Retomamos seu rascunho [Descartar]". `usa_cronograma` não aparece (sempre ligado).

---

## 4. Protocolos (Central reestruturada — só ciclos)

Entrada: Sidebar › **Protocolos**. Três telas, tipo vira filtro:

| Rota | Tela | Papel |
|---|---|---|
| `/protocolos` (`?tipo=&lote=&status=`) | **Em andamento** | tabela full-width; atrasados no topo; busca com debounce; abrir → drawer com grade animal × dia e baixa (o modal atual, que é o melhor componente do módulo) |
| `/protocolos/novo?tipo=` | **Novo protocolo** | um fluxo: 1 escolher modelo → 2 animais/lote/data (D0) → 3 **conferir consequências** (nº de animais, hormônio/estoque a debitar, dias na Agenda) → lançar |
| `/protocolos/modelos` | **Modelos** | lista + Duplicar + Ativar/Inativar + "usado por N"; wizard **Dados · Etapas · Conferir** |

Tipos: **Inseminação programada (IATF)** · **Indução de lactação** · **Tratamento (curativo)** · **Protocolo próprio**. **Tarefa da fazenda** (antiga Lida) vive em Modelos com marca própria. Estados: **Em andamento · Concluído · Interrompido · Lançado por engano**. Correções: Protocolo próprio exige Tipo; confirmação de compromisso no lançamento IATF; folha de campo PDF/Excel no drawer; link direto para Reprodução no dia da inseminação; sem `window.confirm`.

---

## 5. Agenda

### 5.1 Anatomia (de cima para baixo)
1. **Cabeçalho:** "Agenda" · data · **+ Nova tarefa** (global, não escondido) · Exportar (Excel/PDF) · Atualizado há N min.
2. **Faixa de 3 números:** **Atrasadas N** · **Hoje N de M** · **Próximos 7 dias N** (clicáveis).
3. **Barra de visão:** `Hoje | Semana | Mês` (na URL) · **Agrupar: Tarefa | Lote | Categoria** · filtro de categoria (chips) · busca.
4. **HOJE** — bloco dominante. Atrasadas primeiro, dentro do bloco ("há 3 dias"). Cada linha: ícone+cor de categoria · o quê ("Inseminação programada — 7º dia") · para quem/onde ("Lote Pré-parto · 12 vacas") · insumo ("Ovulação: 2 frascos") · **[Feito]** primário · ⋯ (Adiar · Não vou fazer · Ver animais · Abrir origem). Uma ação primária por linha.
5. **Amanhã** recolhido; **Concluídos hoje** recolhido (com **Desfazer** unificado).
6. **Lateral direita:** mini-calendário do mês (pontos por dia; clicar filtra) · **Precisa de insumo** (lista curta) · **Fechar o dia**.
7. **Gavetas** (não ocupam a dobra): **Reprodução** (candidatas IATF, IATF atual, última IATF) · **BST** (`PainelLancarBst`) · **Estoque** · **Comunicados** (faixa dispensável). Chips "Reprodução ▸ · BST ▸ · Estoque ▸" na barra abrem as gavetas.

### 5.2 Três trilhos (o que conta para "Dia fechado")
- **Tarefas de campo** (contam): inseminações, BST, vacinas, secagem, partos, pesagens, desmama, checar retorno ao cio…
- **Alertas e decisões** (não contam): candidatas, análise de dieta, sugestão de movimentação, perda de prenhez a motivar.
- **Gestão** (fora da lista de campo): contas a pagar, compras, patrimônio, documentos → vão para as respectivas telas; na Agenda só um resumo "3 itens de gestão ▸".

### 5.3 Contrato do evento: `resolucao`
Todo evento declara `realizar | navegar | informativo`. **Nenhum evento mostra "Feito" se o backend recusa** (fim do `patrimonio_*` → 400). `navegar` → botão com o destino correto ("Ir para Dieta", "Abrir pedido"); `informativo` → dispensar. "Importar" só para `/upload`.

### 5.4 Comportamento
- **Feito**: a linha some com transição curta e toast **"Feito · Desfazer"** (10 s). Confirmações ricas (frasco, animais, dose) abrem **gaveta**, não painel no meio da lista.
- **Adiar** genérico (hoje/amanhã/data) para qualquer tarefa; **editar/excluir** tarefa manual.
- **Baixa em lote** com progresso "12 de 38…" e retomada.
- **Dia fechado**: total do dia vem do servidor (não do maior N visto na sessão); persiste ao reabrir; equivalente no app.
- Semana: 7 colunas/dias com contagem e "críticos"; Mês: grade com pontos e legenda.
- Estado (visão, agrupamento, filtros, gaveta) na URL.
- Dia vazio: informa a próxima tarefa e oferece "Ver semana" / "+ Nova tarefa".
- Mobile-web: mesma ordem; alvos ≥44px; primeira tela = 3 números + Hoje.

---

## 6. Dependências técnicas (para a implementação, não para o mockup)

| Necessidade | Origem |
|---|---|
| Endpoints leves: `/agenda/resumo` (3 números) e `/agenda/eventos` (paginado, sem escrita) | corrige skeleton total, 26 requests, escrita em GET |
| Desfazer com estorno completo (`protocolo_sanitario_`, `aplic_agendada_`, `vacina_pre_parto_`) + baixa idempotente e transacional | P0 Agenda |
| Fuso local (America/Sao_Paulo) no front e no back | P1 |
| `/sanidade/vacinas/cobertura`, carteira por animal, carência leite/carne, multidose | novos |
| Endpoint transacional evento+regra | P0 Preventivo |
| Chaves de cache/rascunho por fazenda+usuário; limpar no logout | P0 segurança |
| Extrair `BotaoRealizado`, `PainelConfirmarBaixa`, `BotaoAgendar`, `ExportarAgendaBotoes` do render; quebrar o monólito em `components/agenda/*` | P1 |
| Acessibilidade: `<tr>` com `role`/teclado, drawers com `role=dialog`+Esc+trap, `aria-live` nos toasts, `label htmlFor` | P1 |

## 7. Fora de escopo desta rodada (registrado)
Integração com calendário oficial estadual de aftosa (data segue editável); painel multi-fazenda para cooperativas; push/lembretes reais (só desenhados); selo "animal em dia" imprimível (desenhado como ação, sem PDF final).
