# Redesenho do Evento Sanitário — modelo, gaps e plano de implementação

> Documento de referência para implementação — qualquer agente (humano ou Claude Code) deve conseguir executar a partir daqui, sem precisar reler o histórico da conversa que o originou. Gerado em 11/09/2026, a partir de: (1) uma entrevista completa (`/grill-me`) com o dono da fazenda fechando a arquitetura; (2) um gauntlet-loop de 6 personas (zootecnista, veterinário, peão de fazenda, produtor de leite, dono de cooperativa, pesquisador de gestão de pecuária leiteira) refinando o modelo de telas do site (91% de conformidade, 3 rodadas) e do app mobile (90% de conformidade, 2 rodadas); (3) um protótipo clicável publicado como Artifact ("Ocorrência Sanitária").
>
> **Por que este redesenho existe**: o usuário relatou dados errados e inconsistentes no cadastro/cronograma sanitário atual (regra antiga sobrepondo edição nova, cronograma travado com veterinário/data de meses atrás, contagem de animais incluídos sem ninguém ter incluído nada). A investigação encontrou a causa raiz: o "evento sanitário" (uma ocorrência real — data, veterinário, animais, o que aplicar) está fragmentado hoje em três tabelas que não se sincronizam (`Sanidade`, `CronogramaSanitario`, `AplicacaoAgendada`), e um ciclo de cronograma já aberto nunca se atualiza quando a regra por trás dele é editada. Este documento substitui patches pontuais por um modelo novo e único.
>
> **Decisão explícita do usuário**: não há migração dos cronogramas hoje abertos (dado de teste/antigo) — eles serão recriados do zero quando a implementação estiver pronta. Não gastar esforço de engenharia com migração de dados.

---

## 1. Arquitetura travada (decisões do usuário — não revisitar sem ele)

Fechadas em entrevista `/grill-me` de 4 rodadas. Resumo executivo (a especificação completa de telas está nas seções 3 e 4):

1. **Entidade única "Ocorrência"** — generaliza o `CronogramaSanitario` que já existe hoje (não cria tabela nova). Toda regra do calendário sanitário passa a gerar Ocorrências automaticamente — `usa_cronograma` deixa de existir como opt-in; **todo** evento passa pelo fluxo novo.
2. **4 estados**: `Provável` → `Em edição` → `Confirmado` → `Realizado`. De `Confirmado` pode-se **reabrir** para `Em edição` a qualquer momento, sem limite, até `Realizado`. `Realizado` é terminal quanto ao registro em `Sanidade` (só aceita observação aditiva depois).
3. **"Desconsiderar cronograma"** é uma decisão **por Ocorrência** (nunca muda o cadastro da regra) — pula o checklist inteiro e confirma o agendamento com um único clique/toque.
4. **Sugestão automática de animais por projeção** — tanto para regra por evento de vida (gatilho) quanto por época (frequência/categoria): o motor projeta a categoria/idade do animal **na data futura da Ocorrência**, não no estado atual. Ex.: regra "vacinar >2 anos" daqui a 4 meses já sugere hoje quem tem 1 ano e 10 meses.
5. **Inclusão manual fora da janela/critério** sempre disponível (flag explícita + motivo opcional), em qualquer Ocorrência, com ou sem checklist.
6. **Checklist por template**, automático por tipo de evento (vacina tem item de estoque; exame não), editável por ocorrência. Todo item aceita **Cumprido** ou **Pulado** (confirmação explícita) — sem excecão, inclusive o item financeiro. Verificação de estoque **nunca bloqueia**, só avisa.
7. **Financeiro é um item do checklist**, pulável, mas também um **widget persistente** na tela da Ocorrência: enquanto não preenchido, mostra convite pequeno; uma vez preenchido, mostra resumo + link, sempre acessível (não só na vez do item).
8. **Relatório de eventos vencidos** (data prevista passada, ainda não `Realizado`) com botão **Dispensar** por ocorrência (não em massa), motivo opcional, registrado para auditoria.
9. **Mobile nunca cadastra** vacina/exame/regra — só opera dentro do que já existe no site: agendar, acompanhar, cumprir checklist, confirmar, consultar, calendário, realizar.
10. **Sem migração** dos cronogramas hoje abertos.

---

## 2. De-Para — o que muda em cada peça do sistema atual

| Peça atual | Arquivo(s) | O que muda |
|---|---|---|
| `CalendarioSanitario.usa_cronograma` (bool, opt-in) | `backend/fazenda/models/sanidade.py:618` | **Removido como opt-in.** Toda regra passa a gerar Ocorrência. Campo pode ser removido ou mantido como legado ignorado — decidir na implementação (ver risco R-3). |
| `CronogramaSanitario` / `CronogramaSanitarioAnimal` | `backend/fazenda/models/sanidade.py:636-679` | **Generalizado** para ser a entidade "Ocorrência" universal (não só para regras que tinham o opt-in). Ganha: `checklist` (nova tabela filha), estado `provavel` explícito (hoje o "provável" nem materializa linha — só existe como projeção calculada; precisa decidir se `Provável` ganha linha própria ou continua sendo só a leitura de `montar_calendario_visual` até o usuário abrir — ver seção 5, Fase 1). |
| `cronograma_aberto()` (reaproveita ciclo já aberto, nunca atualiza) | `backend/fazenda/rules/cronograma_sanitario.py:40-70` | Continua reaproveitando o ciclo aberto **por design** (é o comportamento certo agora — "Confirmado" preserva o que já foi decidido), mas passa a expor **Reabrir** de verdade (hoje não existe reabertura — só `adiar`, que muda a data mas não devolve pro estado de edição do checklist). |
| `EventoSanitario.tipo_agendamento` (época/evento/nenhum) | `backend/fazenda/models/sanidade.py:511` | Sem mudança de schema — mas agora **toda** regra com `tipo_agendamento` em `epoca` ou `evento` passa a gerar Ocorrência (hoje só quem tinha `usa_cronograma=True`). |
| Sugestão de animal só por gatilho (evento de vida) | `backend/fazenda/rules/eventos_sanitarios.py` (`_datas_gatilho`) | **Estende-se para época**: hoje regra por época não sugere ninguém automaticamente (o lançamento manual escolhe lote/categoria na hora). Precisa um motor novo (ou generalização do existente) que projete "quem vai estar na categoria-alvo na data X" também para época. |
| `AplicacaoAgendada` | `backend/fazenda/models/sanidade.py:66-93` | Só sobrevive para o "avulso puro" (sem regra nenhuma — decisão R2.6/R3.2). Deixa de ser usada por regras recorrentes. |
| Checklist | **Não existe hoje.** | Tabela nova: itens por Ocorrência, com template por tipo de evento. Ver seção 3.4/4.3 para a redação exata dos itens. |
| Financeiro vinculado ao evento | `frontend/components/lancamentos/PopupVinculoFinanceiro.tsx`, `lib/vinculoSanitarioFinanceiroBridge.ts` | Hoje só dispara **depois** de aplicado, como popup pontual de 3 opções. Passa a ser um **item de checklist + widget persistente**, disponível durante todo o planejamento (antes de `Realizado`). Reaproveita o modal, mas muda o gatilho (abre a qualquer momento, não só pós-salvar) e adiciona o estado "pendente/preenchido" refletido na tela da Ocorrência. |
| `frontend/components/lancamentos/FormCalendarioSanitario.tsx` (wizard "Identificação → Critérios → Roteiro → Revisão", hoje em `/protocolos` — Central de Protocolos › Cadastro › Sanitário › Preventivo) | Todo o arquivo | Este é o wizard que causou o bug relatado — `regraVinculadaEventoVida` (linha ~290) resolve qualquer regra já vinculada ao evento e sobrescreve os campos do formulário no efeito de auto-preenchimento (linhas 207-240), sem revalidar quando `regras` termina de carregar depois do `eventoId` já estar setado (condição de corrida). **Será substituído** por um novo wizard no **mesmo local de hoje** (Central de Protocolos, não Configurações — ver seção 3.7), com um passo "Tipo" (Vacina/Exame) antes de "Identificação" e o passo "Critérios" corrigido (banner em vez de sobrescrita). |
| `frontend/components/CadastroSanitario.tsx` — abas "Evento sanitário" (`CadastroEventosSanitarios`) e "Exames" (`CadastroExames`), hoje também espelhadas em Configurações › Cadastro › Sanitário | Todo o arquivo | Hoje já são cadastros **separados** — `EventoSanitario` (catálogo único vacina/exame, campo `categoria_preventiva`) e `ExameDefinicao` (só decide o formato do resultado: diagnóstico ou numérico+faixa, nunca produto/dose/via). O redesenho **mantém essa separação** (ver seção 3.7) — o erro do protótipo inicial foi ter desenhado uma tabela única; corrigido. |
| `ExameResultado` (`backend/fazenda/models/sanidade.py:464-492`) | Sem mudança de schema | Continua sendo o destino do resultado de exame — **nunca** `Sanidade`, nunca baixa estoque. A tela nova "Realizar Exame" (seção 3.1, Tela 8b) grava aqui; "Realizar Evento" (vacina/tratamento) continua gravando em `Sanidade`. |
| `frontend/app/sanidade/page.tsx` — `CalendarioSanitarioView`, `CronogramasSanitariosView`, `RelatorioEventosVidaView`, `HistoricoPreventivoView`, `AplicacoesView` | Todo o arquivo | Consolidam nas 10 telas não-cadastro da seção 3 (1-9 + 8b). `RelatorioEventosVidaView` (que ganhou o painel de agendamento em lote nesta mesma sessão, PR #759) é o embrião da aba **Animais** da tela **Detalhe da Ocorrência** — muito do código já escrito (seleção de animais, marcar/desmarcar todos, veterinário) é reaproveitável quase directo. |
| Mobile: `FormSanidade.tsx`, `CalendarioSanitario.tsx`, `Cronogramas.tsx`, `AplicacoesSanidade.tsx` | `frontend/components/mobile/**` | Consolidam nas 10 telas mobile da seção 4 (1-9 + 8b). `Cronogramas.tsx` (Acompanhamento, construído nesta mesma sessão) já implementa boa parte do padrão "cartão expansível com decisão inline" que o novo modelo pede — mesma base, precisa do checklist e dos 4 estados por cima. |
| `backend/fazenda/api/routers/agenda.py` — dispatch `cronograma_sanitario_*` | Linhas ~2379-2390 | O dispatch por prefixo de `evento_id` continua sendo o mecanismo de decisão (incluir/excluir animal, decidir modo, aplicar) — só precisa de um prefixo novo para as ações de checklist (marcar item cumprido/pulado) e para reabrir. |
| Estoque / lote (FIFO) | `backend/fazenda/models/estoque.py`, `rules/farmacia.py` | **Verificar antes de implementar** (ver Risco R-7): confirmar que o modelo de lote de compra (Fase G, FIFO) já grava data de validade — é pré-requisito do gate "lote vencido bloqueia" da Tela Realizar Evento. |

---

## 3. Modelo final — Site (Sanidade › Preventiva)

*(Texto integral produzido pela síntese do gauntlet-loop, conformidade estrutural ~91%. Reproduzido sem edição — é a especificação de implementação.)*

### 3.1 Lista de telas

| # | Tela | Propósito |
|---|------|-----------|
| 1 | **Calendário Sanitário (lista)** | Porta de entrada: todas as Regras e a Ocorrência vigente de cada uma, com badge de estado, atraso, indicador financeiro, carência, adesão e alertas. |
| 2 | **Detalhe da Ocorrência** | Tela de trabalho central — abas *Animais*, *Checklist*, *Resumo*, *Histórico* — cabeçalho fixo com estado, veterinário, widget financeiro e ficha de carência. |
| 3 | **Modal — Incluir animal fora da janela** | Inclusão manual fora da sugestão automática, com flag obrigatória e motivo opcional. Serve também ao "Desconsiderar cronograma". |
| 4 | **Modal — Pular item do checklist** | Confirmação explícita por item, sem exceção. |
| 5 | **Modal — Desconsiderar cronograma** | Confirma a Ocorrência em 1 clique, sem checklist, com card financeiro embutido. |
| 6 | **Modal — Lançamento Financeiro da Ocorrência** | Janela suspensa de contas a pagar vinculada à Ocorrência. |
| 7 | **Modal — Reabrir ocorrência** | Confirmado → Em edição, a qualquer momento até Realizado. |
| 8 | **Tela — Realizar Evento** (Vacina/Tratamento) | Decisão por animal (com atalho de massa), lote do medicamento com checagem de validade, dose, via, responsável, carência, observação clínica; gera `Sanidade`, baixa estoque. |
| 8b | **Tela — Realizar Exame** | Decisão por animal, resultado **diagnóstico** (positivo/negativo/indefinido) ou **numérico** (valor + faixa/conduta do `ExameDefinicao` vinculado), veterinário, observação. Sem lote, dose, via ou estoque — gera `ExameResultado`, nunca `Sanidade`, nunca baixa estoque. Tela própria porque o formulário é outro, não um "Realizar Evento" com campos condicionais. |
| 9 | **Relatório de Eventos Vencidos** | Ocorrências vencidas e não Realizadas, com indicadores de adesão e Dispensar por linha. |
| 10 | **Cadastro — Vacinas e Exames + Regras** (Central de Protocolos › Cadastro › Sanitário › Preventivo) | **Mesmo local de hoje** — substitui o wizard atual (`FormCalendarioSanitario.tsx`) por um wizard de 5 passos (Tipo → Identificação → Critérios → Checklist → Revisão), com transição animada (slide) entre passos. Evento (`EventoSanitario`, vacina ou exame) e Regra (`CalendarioSanitario`) continuam cadastrados juntos, num fluxo só — ver seção 3.7. |
| 11 | **Cadastro — Template de Checklist por Tipo** (mesmo caminho) | Define os itens padrão que toda Ocorrência nova de Vacina/Exame já traz — editável (adicionar/remover item), ponto de partida para a Ocorrência (que ainda pode ajustar item a item, ver seção 3.2.2). |

13 telas no total (8b conta como tela própria por ter formulário e destino de dados diferentes de 8). As telas de Cadastro (10-11) existem **só no site**, no mesmo lugar de hoje — Central de Protocolos, não Configurações — e nunca no app mobile.

### 3.2 Campos e ações por tela

#### 3.2.1 Calendário Sanitário (lista)

**Indicadores agregados (topo, fixos)**:
- Nº de ocorrências vencidas (atalho para o Relatório de Vencidos)
- Nº de ocorrências em Provável nos próximos 30 dias
- Valor total **pendente** de lançamento financeiro (item ainda não preenchido)
- Valor de lançamentos financeiros **já lançados e vencidos** (contas a pagar com vencimento passado, vinculadas a Ocorrências) — indicador separado do "pendente"
- Nº de ocorrências Confirmado aguardando Realizar evento
- **Adesão ao calendário (12 meses)**: % de Ocorrências que chegaram a Realizado dentro do prazo previsto, sobre o total do período
- Nº de Ocorrências com alerta clínico ativo (item do veterinário respondido "Não" e não revisado)

Todo indicador agregado é clicável e leva à lista filtrada de ocorrências que o compõe.

**Tabela**: Regra · tipo (Vacina/Exame) · categoria/critério-alvo · data prevista · badge de estado · nº animais sugeridos/incluídos · veterinário (com CRMV) · indicador financeiro · atraso (dias) · ícone de carência (tooltip leite/carne e via de administração, quando cadastrada) · **% de adesão da própria Regra nos últimos 12 meses** · ícone de alerta clínico quando houver resposta "Não" registrada no item de confirmação veterinária.

**Ordenação padrão**: por atraso (decrescente), com destaque visual (não bloqueio, não abertura automática) para Ocorrências Prováveis dentro da janela de antecedência recomendada para abrir.

**Filtros**: tipo, estado, categoria/lote de manejo, período, Regra, veterinário.

**Ações**: abrir Detalhe · "Abrir ocorrência" quando Provável · atalho para o Relatório de Vencidos.

#### 3.2.2 Detalhe da Ocorrência

**Cabeçalho fixo (todas as abas)**: evento · tipo · categoria-alvo · data prevista (editável até Confirmado) · Regra de origem (link) · badge de estado com histórico de transições · veterinário selecionado, com **CRMV sempre visível ao lado do nome** · widget financeiro (seção 3.5) · contador de animais que atingiram o critério desde a abertura · ficha de carência (só Vacina, quando cadastrada): *"Carência deste produto: leite X dias / carne Y dias — valor definitivo fixado na Realização, a partir da data real de aplicação."*

**Botões por estado**:
- **Provável** → Abrir ocorrência / Desconsiderar cronograma
- **Em edição** → Desconsiderar cronograma / Confirmar ocorrência (habilita só com checklist 100% Cumprido/Pulado)
- **Confirmado** → Reabrir para edição / Realizar evento
- **Realizado** → somente leitura + link Sanidade + "Adicionar observação"

**Aba Animais**: Tabela: nº/nome · categoria/idade **hoje** e categoria/idade **projetada na data da Ocorrência**, lado a lado · lote de manejo · origem (Sugerido automático / Incluído manual / Incluído manual fora da janela) · status. Motivo textual concreto para quem está fora da janela (ex.: "faltam 3 meses para completar a categoria-alvo").

Quando o critério da Regra for de natureza **reprodutiva** (ex.: "vacas entre 60–90 dias pré-parto", "novilhas confirmadas prenhes"), em vez do badge fixo de janela, a projeção exibe selo **"Projeção estimada — revisar perto da data"** (a data de parto/confirmação pode mudar até lá); para critério puramente etário o badge normal se mantém.

Selo quando o status cadastral do animal mudar (inativo/vendido/morto) entre a sugestão e a data — remove da contagem automática; inclusões manuais permanecem. Ações em massa: incluir todos sugeridos, excluir selecionados. Botão "Incluir animal fora da janela" (modal 3.2.3). Rodapé: contadores (sugeridos/incluídos/excluídos/fora da janela).

**Aba Checklist**: Itens na ordem da seção 3.4, cada um com estado (Pendente/Cumprido/Pulado)/responsável/timestamp.

No item **"Confirmação com o veterinário selecionado"**:
- Resposta **Sim/Não** obrigatória (não é só "marcar como visto"); exibe lado a lado quem marcou o item (operador) e o veterinário pré-preenchido (nome + CRMV).
- **Se a resposta for "Não"**: abre automaticamente campo de **justificativa obrigatória** inline (diferente do modal de "Pular" — aqui o item foi respondido, só que negativamente). O item fica com badge vermelho **"Veterinário não confirmou"**, que se propaga para a aba Resumo, o Histórico, a linha da Ocorrência no Calendário Sanitário e o Relatório de Vencidos, caso a Ocorrência fique parada. Continua contando como item "Cumprido" (não bloqueia a Confirmação da Ocorrência) — mas nunca some silenciosamente: o alerta só desaparece se a resposta mudar para "Sim" ou o item for reaberto.
- Botão "Pular" continua disponível e segue o modal 3.2.4 normalmente (recusa de responder é diferente de responder "Não").

Demais itens (estoque, horário, lotes de manejo, financeiro) sem alteração de comportamento. Pular sempre abre o modal 3.2.4. Barra de progresso. Rodapé: "Confirmar ocorrência", habilitado só com tudo Cumprido/Pulado.

**Aba Resumo**: Lista final de animais, status de cada item do checklist (ou "Cronograma desconsiderado"), veterinário, horário, link financeiro, carência estimada (rótulo "estimado, confirma na Realização") + badge vermelho quando o item de confirmação veterinária estiver com resposta "Não". Quando Realizada: seção **"Animais não aplicados nesta Ocorrência"** com motivo e atalho "Incluir na próxima Ocorrência" (pré-marca como sugerido quando a próxima Ocorrência nascer).

**Aba Histórico**: Linha do tempo imutável: materialização, inclusões/exclusões com motivo, itens pulados com motivo, justificativa de "Não" do item veterinário como entrada própria, aberturas/edições do financeiro, confirmações (via checklist ou desconsiderar — inclusive as duas transições geradas por um único clique em "Desconsiderar cronograma" a partir de Provável), reaberturas, dispensa do relatório de vencidos, realização, observações pós-realização. Quem e quando em cada entrada. Botão **"Exportar histórico (PDF)"** (rodapé com fazenda, Regra e período, pronto para anexar em auditoria/fiscalização). Botão "Adicionar observação" (só a partir de Realizado): texto livre obrigatório + animal opcional; puramente aditivo, não reabre nada, não edita Sanidade, não devolve estoque, não muda estado.

#### 3.2.3 Modal — Incluir animal fora da janela
Busca no rebanho ativo. Categoria/idade projetada + motivo clínico/concreto de estar fora do critério. Checkbox obrigatório "Incluir mesmo fora da janela/critério" (habilita o botão). Motivo opcional. Incluir / Cancelar. Mesmo modal serve ao "Desconsiderar cronograma".

#### 3.2.4 Modal — Pular item do checklist
*"Pular '[item]'? Confirme que não se aplica a esta ocorrência."* Motivo opcional. Sim, pular / Cancelar. No item do veterinário, complementa: *"Para medicamentos de controle especial isso pode ter implicação de responsabilidade técnica."* — texto de alerta, não bloqueia.

#### 3.2.5 Modal — Desconsiderar cronograma
*"Esta ocorrência será confirmada sem passar pelo checklist (estoque, veterinário, horário, financeiro). Vale só para esta ocorrência."* Quando o nome/categoria da Regra sugerir programa sanitário oficial (checagem simples por palavra-chave, ex.: "aftosa", "brucelose", "PNCEBT", "raiva"), exibe aviso textual reforçado adicional: *"Esta Regra parece vinculada a um programa sanitário oficial — confirme que a ausência de checklist não compromete a conformidade regulatória deste evento."* — aviso, não bloqueia. Card financeiro embutido. Campos opcionais: data, veterinário, horário. Confirmar agendamento sem checklist / Cancelar.

#### 3.2.6 Modal — Lançamento Financeiro
Fornecedor/serviço, descrição (pré-preenchida), valor, centro de custo, vencimento, forma de pagamento, observação. Salvar e fechar / Cancelar. Salvar marca o item do checklist como Cumprido automaticamente.

#### 3.2.7 Modal — Reabrir ocorrência
Aviso de que estoque/lotes podem precisar revisão. Motivo opcional. Reabrir / Cancelar.

#### 3.2.8 Tela — Realizar Evento

Disponível só a partir de Confirmado.

**Ação em massa no topo**: "Marcar todos como Aplicado = Sim" — pré-preenche lote/horário/data padrão; exceção manual linha a linha.

**Por animal**:
- **Aplicado? Sim/Não** — se Não, motivo obrigatório (chips: Vendido, Doente, Não localizado, Outro + texto livre).
- **Lote do medicamento** (só Vacina), pré-selecionado por FIFO, editável, **validade exibida ao lado do código**.
  - Lote **já vencido**: **bloqueia a linha** — não aceita confirmação; o usuário precisa trocar o lote (imunobiológico/medicamento vencido não tem eficácia/garantia sanitária assegurada e pode invalidar o registro em programas oficiais).
  - Lote **a vencer em até 7 dias**: **soft-block** — exige confirmação explícita adicional antes de aceitar a linha (decisão do responsável técnico), mas não bloqueia.
  - **Confirmação/bloqueio por LOTE, não por linha**: quando o mesmo lote for usado em múltiplas linhas (pela ação em massa ou por seleção manual repetida), o sistema trata o grupo de uma vez — para "a vencer", uma única confirmação agregada (*"Este lote está a vencer em [data] — X animais usarão este lote. Confirmar uso para todos?"*); para "já vencido", o bloqueio e a troca de lote também se resolvem de uma vez para todas as linhas daquele lote. O registro individual por animal em Sanidade (lote, dose, via, carência) permanece gravado linha a linha, inalterado.
- **Dose/volume administrado** — numérico + unidade, pré-sugerido pelo cadastro do produto quando houver dose padrão, editável por categoria/peso.
- **Via de administração** — seleção (IM/SC/IV/oral/outra).
- **Responsável pela aplicação** — seleção de usuário/funcionário já cadastrado no sistema (mesmo cadastro do veterinário); opção "Outro" habilita texto livre só em caso excepcional.
- **Horário real** e **data real** (default = prevista, ambos editáveis).
- **Observação clínica** (opcional, por animal) — vai para o registro de Sanidade.
- **Carência até [data real + X dias leite / Y dias carne]**, calculada a partir da data real, gravada no registro de Sanidade.

Rodapé: "Confirmar realização" — gera 1 registro em Sanidade por animal com Aplicado=Sim (lote, dose, via, carência, observação clínica), baixa estoque pelos lotes informados, muda a Ocorrência para Realizado. Alerta visível se algum animal ficou Aplicado=Não.

#### 3.2.8b Tela — Realizar Exame

Disponível só a partir de Confirmado, quando `EventoSanitario.categoria_preventiva == "exame"`. **Tela própria, não uma variação de 3.2.8** — o formulário e o destino do registro são outros: sem lote de medicamento, sem dose, sem via, sem estoque; nunca gera `Sanidade`.

**Por animal**, conforme o `tipo_resultado` do `ExameDefinicao` vinculado ao evento (cadastrado no passo 2 do wizard, seção 3.7.0 — decide isso por evento, não se escolhe na hora):
- **Diagnóstico**: botões **Positivo / Negativo / Indefinido**.
  - Positivo marca o animal para descarte (`a_descartar`) automaticamente — aviso visível na hora.
  - Indefinido marca para repetir o exame — só informativo, não bloqueia a Ocorrência.
  - Negativo é só informativo ("liberado").
- **Numérico**: campo de valor + banda calculada automaticamente contra a faixa do `ExameDefinicao` (abaixo/dentro/acima) — mostra o texto de conduta cadastrado para aquela banda (ex.: *"Acima de 200.000 — investigar mastite subclínica."*).
- **Veterinário** — pré-preenchido (nome + CRMV), mesmo padrão do checklist.
- **Observação clínica** (opcional, por animal).
- **Data/hora real** (default = prevista, editável).

Rodapé: "Confirmar realização" — gera 1 registro em `ExameResultado` por animal (resultado ou valor+banda, veterinário, observação), muda a Ocorrência para Realizado. **Nunca baixa estoque** — texto fixo na tela reforça isso, porque é o oposto do hábito criado pela Tela 8 (vacina).

#### 3.2.9 Relatório de Eventos Vencidos
Ver seção 3.6.

### 3.3 Fluxo entre os 4 estados

```
Provável ──[usuário clica "Abrir ocorrência"]──► Em edição
                                                     │
                         ┌───────────────────────────┤
                         │                           │
           (checklist 100% Cumprido/Pulado      (usuário clica "Desconsiderar
            + clique em "Confirmar ocorrência")   cronograma" a partir de
                         │                          Provável ou Em edição)
                         ▼                           ▼
                         └────────► Confirmado ◄─────┘
                                       │  ▲
                         "Reabrir para edição" (sem limite,
                          sem motivo obrigatório, até Realizado)
                                       │
                          "Realizar evento" (Vacina: decisão por
                           animal, ação em massa, lote já vencido
                           BLOQUEIA a linha/lote, lote a vencer em
                           7 dias exige confirmação agregada por
                           lote, dose/via/responsável capturados —
                           ver 3.2.8) ou "Realizar exame" (Exame:
                           resultado diagnóstico ou numérico por
                           animal, sem lote/dose/via — ver 3.2.8b)
                                       ▼
                                   Realizado
                 Vacina: gera Sanidade por animal aplicado (lote,
                 dose, via, carência, observação clínica), baixa
                 estoque · Exame: gera ExameResultado por animal
                 (resultado/valor+banda), NUNCA baixa estoque —
                 ambos terminais quanto ao próprio registro
                                       │
                         "Adicionar observação" (aditivo, não
                          edita/reabre Sanidade, não muda estado)
```

Regras de transição:
- **Abrir ocorrência** é sempre ato explícito do usuário; nunca automático por proximidade de data.
- **Desconsiderar cronograma** é decisão por Ocorrência, nunca altera a Regra; disparável de Provável ou Em edição (se de Provável, materializa Em edição e confirma na mesma ação — duas transições no Histórico, um clique do usuário).
- **Em edição → Confirmado**: checklist completo só habilita o botão — a transição exige o clique.
- **Confirmado → Em edição**: "Reabrir" disponível a qualquer momento até Realizado, sem motivo obrigatório; preserva tudo já respondido; se a lista de animais mudar, o item de estoque é sinalizado para revisão.
- **Confirmado → Realizado**: única transição irreversível no registro de Sanidade, decidida por animal; é onde lote, dose, via, carência e responsável ficam definitivos.
- **Pós-Realizado**: sem edição do registro de Sanidade; só anotação aditiva via "Adicionar observação" no Histórico.

### 3.4 Redação exata do checklist padrão

**Vacina (5 itens, nesta ordem)**

1. **"Estoque suficiente?"** — auto-verifica dose × nº de animais incluídos contra o saldo do produto. **Nunca bloqueia a confirmação**; se insuficiente: *"Estoque insuficiente — faltam **X** [unidade] de [produto]."* com atalho **"Incluir mesmo sem estoque"**. Quando o produto tem carência cadastrada, linha informativa fixa: *"Este produto tem carência de leite/carne — será registrada por animal na Realização."*
   Pular: *"Pular verificação de estoque? Confirme que não precisa verificar para esta aplicação."*

2. **"Confirmação com o veterinário selecionado"** — resposta **Sim/Não** obrigatória para marcar o item como respondido; exibe lado a lado quem marcou e o veterinário (com CRMV) pré-preenchido. **Se a resposta for "Não"**: exige justificativa obrigatória no próprio item e mantém alerta visual vermelho **"Veterinário não confirmou"** propagado por toda a Ocorrência (Resumo, Histórico, Calendário Sanitário, Relatório de Vencidos) até a resposta mudar para "Sim" ou o item ser reaberto — isso não bloqueia a Confirmação da Ocorrência, mas nunca fica silencioso.
   Pular: *"Pular confirmação com o veterinário? Confirme que não precisa. Para medicamentos de controle especial isso pode ter implicação de responsabilidade técnica."*

3. **"Horário da aplicação"** — **não é um toggle de "cumprido"**: exige preencher o campo de hora primeiro. O item mostra um `<input type="time">` inline; o botão "Confirmar horário" só habilita depois de um valor preenchido, e é ele que marca o item como Cumprido (o horário confirmado fica visível no próprio item — "Cumprido — 09:30" — e vai para a aba Resumo/Histórico). Sem valor preenchido, só resta "Pular".
   Pular: *"Pular registro de horário da aplicação? Confirme que não precisa."*

4. **"Lotes de manejo atuais"** — **não é um toggle de "cumprido"**: o item expande, ali mesmo, a distribuição real dos animais incluídos por lote de manejo (tabela lote → nº de animais — não é o lote do medicamento, que é capturado por animal na Tela Realizar Evento). O usuário precisa ver essa distribuição antes de poder confirmar; o botão só existe depois da tabela, com o rótulo **"Marcar como revisado"** (nunca "cumprido" genérico, porque não há nada a "cumprir" — é uma conferência).
   Pular: *"Pular revisão dos lotes de manejo? Confirme que não precisa."*

5. **"Lançamento financeiro"** — abre o modal 3.2.6.
   Pular: *"Pular lançamento financeiro? Confirme que não haverá lançamento para esta aplicação."*

**Exame (4 itens — os mesmos, menos estoque)**

1. **"Confirmação com o veterinário selecionado"** — idêntico ao de vacina, inclusive o tratamento da resposta "Não".
2. **"Horário da coleta/realização do exame"** — mesmo padrão do item de vacina: exige preencher a hora antes de confirmar.
   Pular: *"Pular registro de horário da coleta/realização? Confirme que não precisa."*
3. **"Lotes de manejo atuais"** — idêntico ao de vacina (mostra a distribuição real antes de permitir "Marcar como revisado").
4. **"Lançamento financeiro"** — idêntico ao de vacina.

Todo item aceita Cumprido ou Pulado, sem exceção (inclusive financeiro), sempre via modal 3.2.4. Não existe item de "funcionários em serviço" — o sistema não controla escala/turno.

### 3.5 Widget financeiro na Ocorrência

Fixo no cabeçalho do Detalhe, visível em todas as abas, replicado no modal "Desconsiderar cronograma".

**Pendente**: *"Lançamento financeiro ainda não foi feito."* + botão **"Lançar agora"**. Some automaticamente quando salvo corretamente.

**Preenchido**: resumo (valor, fornecedor/centro de custo, vencimento) + link **"Ver lançamento"**, reabrindo o mesmo modal sem navegar para fora.

É o mesmo objeto e a mesma fonte de dados do item "Lançamento financeiro" do checklist — preencher por um lado preenche o outro. Pular o item não apaga o convite do widget (pular não é "não precisa lançar"). Alimenta os indicadores "Valor total pendente de lançamento financeiro" e "Valor de lançamentos já vencidos" do Calendário Sanitário.

### 3.6 Relatório de Eventos Vencidos

**Critério de entrada**: data prevista passada e estado ainda não é Realizado (Provável, Em edição ou Confirmado) — não importa em qual estado a Ocorrência estava parada.

**Indicadores agregados (topo)**: total vencidas no período · atraso médio em dias · distribuição % por estado parado · nº de vencidas com carência longa cadastrada (destaque próprio) · nº de vencidas com alerta clínico ativo (item do veterinário em "Não") · **distribuição % por motivo de dispensa** (quando houver motivo registrado), calculada sobre o histórico de dispensados.

**Colunas**: evento + tipo · categoria/critério-alvo · data prevista · dias de atraso · estado parado (badge) · nº animais incluídos/afetados · veterinário · indicador de carência · alerta clínico (quando houver) · botão Abrir ocorrência · botão Dispensar.

**Filtros**: tipo, categoria, Regra, veterinário, faixa de atraso.

**Dispensar**: um clique, mini-modal/popover inline, motivo **opcional** + chips ("Animal saiu do rebanho", "Erro de cadastro da regra", "Decisão do veterinário", "Outro") + texto livre. Ao confirmar, a linha some da lista ativa; fica registrado quem dispensou e quando, mesmo sem motivo escrito. Dispensar é sempre por Ocorrência, nunca "dispensar tudo", e não altera a Regra nem o estado da Ocorrência.

**Toggle "Mostrar dispensados"**: histórico de auditoria (data original, quem, quando, motivo se houver) — base dos percentuais por motivo do cabeçalho.

Ao reabrir a Ocorrência pelo Detalhe, a aba Histórico mostra: *"Dispensada do relatório de vencidos em [data] por [usuário]."*

### 3.7 Cadastro (Central de Protocolos › Cadastro › Sanitário › Preventivo)

**Correção de localização** (o protótipo inicial e uma versão anterior deste documento erravam isso — colocavam o cadastro em "Configurações"): cadastro de evento (vacina/exame) e de regra **já ficam hoje**, e continuam ficando, em `/protocolos` — **Central de Protocolos › Cadastro › Sanitário › Preventivo** (`SUBS_SANITARIO`/`SUBS_SANITARIO_LANCAMENTO` em `frontend/app/protocolos/page.tsx`) — não em Configurações. Configurações › Cadastro › Sanitário (`CadastroSanitario.tsx`) hoje é só um **espelho** das mesmas abas Evento/Exame (mesmo componente, mesmo endpoint) — o redesenho não precisa manter esse espelho, mas também não o remove por si (fora de escopo).

O usuário confirmou explicitamente **manter o cadastro no mesmo lugar de hoje** (Central de Protocolos), como um **wizard único** com transição animada (slide) entre passos — substituindo em bloco o wizard atual de 4 passos (`FormCalendarioSanitario.tsx`: Identificação → Critérios → Roteiro → Revisão), que é a origem direta do bug relatado (sobrescrita silenciosa de frequência/data/veterinário no passo "Critérios").

**Correção de modelo** (o protótipo inicial também errava isso — desenhava Vacina e Exame como uma tabela única): o cadastro de evento continua sendo **um catálogo único** (`EventoSanitario`, com `categoria_preventiva` = vacina/exame/tratamento), mas **Exame nunca tem produto/dose/via/janela próprios** — quem decide como o *resultado* do exame é lançado é o `ExameDefinicao` vinculado (`exame_definicao_id`), cadastrado e mantido como entidade **separada** (nome, `tipo_resultado` diagnóstico/numérico, faixa min/máx e conduta abaixo/dentro/acima quando numérico). Isto é o modelo real de hoje (`backend/fazenda/models/sanidade.py:433-492`), não uma simplificação — mantido sem mudança de schema.

#### 3.7.0 Wizard único — 5 passos, com slide

Substitui o wizard de 4 passos de hoje. Cada passo entra com uma transição de slide (curva suave, ~220ms) — nunca "pisca" ao trocar de passo, e nunca perde o que já foi digitado ao voltar.

1. **Tipo** — Vacina/Tratamento ou Exame. Decide os campos do passo 2 e qual checklist-padrão (3.7.3/3.4) a Ocorrência herda.
2. **Identificação** — nome do evento (ou selecionar um já cadastrado do mesmo tipo) + doença.
   - **Vacina**: produto padrão, dose padrão, via padrão (opcionais — Regra e Realização ainda podem sobrescrever).
   - **Exame**: vincular um `ExameDefinicao` já cadastrado, **ou** criar um novo inline (nome do exame + tipo de resultado diagnóstico/numérico + faixa min/máx quando numérico) — sem sair do wizard.
3. **Critérios** — categoria-alvo, disparo (**época**: frequência valor+unidade; **evento de vida**: gatilho, reaproveita a janela do evento), veterinário padrão. **Aqui mora o fix do bug**: escolher um evento que já tem regra vinculada mostra um banner — *"Este evento já tem uma regra cadastrada — [detalhe], próxima ocorrência [data]. Nada foi alterado. Você quer: **Editar essa regra** / **Criar uma regra nova mesmo assim**"* — em vez de pré-preencher e sobrescrever os campos em silêncio. Nenhum dado da regra existente é copiado para o formulário de criação até o usuário escolher um dos dois caminhos.
4. **Checklist** — nasce do template padrão do tipo (3.7.3), ajustável só para esta regra (adicionar/remover item), sem afetar o template nem outras regras.
5. **Revisão** — resumo (evento, critérios, veterinário, nº de itens do checklist) + Salvar.

Salvar uma regra nova ou editada **nunca** toca numa Ocorrência já materializada (Provável/Em edição/Confirmado) — só passa a valer a partir da próxima vez que o motor de projeção (R-2) gerar uma Ocorrência.

Ponto de entrada antes do wizard: uma tela de lista com duas tabelas — **Eventos cadastrados** (nome · tipo · doença · produto padrão ou exame vinculado · veterinário padrão · Editar) e **Regras cadastradas** (evento · categoria-alvo · disparo · detalhe · próxima ocorrência · Editar) — e o botão "+ Nova regra do calendário sanitário", que abre o wizard no passo 1.

#### 3.7.3 Cadastro — Template de Checklist por Tipo

Tela separada (não um passo do wizard, porque é global — não pertence a uma regra específica). Duas listas lado a lado, Vacina e Exame, com os itens padrão da seção 3.4 (mesma redação) — cada item com botão Remover e um campo "Novo item…" + "+ Adicionar" por lista. É o ponto de partida: toda regra nova nasce com esses itens (passo 4 do wizard), mas cada regra ainda pode ajustar item a item sem afetar o template nem outras regras.

Não existe (nem aqui, nem em nenhuma tela) item de "funcionários em serviço" — confirmado na seção R2.3: a fazenda se organiza internamente, o sistema não controla escala/turno.

---

## 4. Modelo final — App mobile (Sanidade › Preventiva)

*(Texto integral produzido pela síntese do gauntlet-loop, conformidade comportamental ~90%. Reproduzido sem edição.)*

### 4.0 Princípios de interação no celular (convergência total)

- Toque grande (mínimo 56px; os botões **Sim/Não** de aplicação por animal são maiores, 72px).
- Sem gestos obrigatórios. Swipe, quando existe, é sempre atalho — nunca o único caminho, e nunca destrutivo (exclusão/dispensa sempre por botão + confirmação explícita).
- Redação dos itens de checklist e textos de aviso idêntica à do site — nenhuma abreviação de responsabilidade técnica no celular.
- Cadastro de vacina/exame, criação de Regra do calendário sanitário e template de checklist **não existem no app** — qualquer tentativa redireciona para "Abra no site".
- Offline-first cobre todo o registro de campo: Checklist, Incluir animal fora da janela, Realizar Evento e Realizar Exame (incluindo a foto de nota/boleto do financeiro rápido).

### 4.1 Lista de telas

| # | Tela | Propósito no celular |
|---|------|------------------------|
| 1 | **Calendário Sanitário (cards) — Home** | Porta de entrada: chips-indicador + cards por Ocorrência, priorizando visualmente atraso e alerta clínico, sem exigir nenhum toque extra para ver o que importa. |
| 2 | **Detalhe da Ocorrência** | Cabeçalho compacto (estado · evento · data · veterinário com CRMV · chips de financeiro/carência) + abas por chip (Animais · Checklist · Resumo · Histórico) + 1 botão de ação fixo no rodapé, já certo para o estado. |
| 3 | **Folha — Incluir animal fora da janela** | Inclusão manual com motivo por chip + checkbox obrigatório, serve também ao atalho de "Desconsiderar cronograma". |
| 4 | **Folha — Pular item do checklist** | Confirmação explícita por item, com aviso reforçado no item do veterinário. |
| 5 | **Folha — Desconsiderar cronograma** | Confirma a Ocorrência em 1 toque, com card financeiro embutido e aviso reforçado para programa sanitário oficial. |
| 6 | **Chip + Folha — Financeiro rápido** | Lançamento nativo limitado a Valor + Vencimento + foto do boleto; "Completar no site" via webview para o resto. |
| 7 | **Folha — Reabrir ocorrência** | Aviso de 1 linha (estoque/lote pode precisar revisão) + motivo opcional. |
| 8 | **Realizar Evento** (Vacina/Tratamento) | Tela central e mais crítica do app — cartão de tela cheia por animal, lote/dose/via/carência definitivos, offline-first total. |
| 8b | **Realizar Exame** | Cartão de tela cheia por animal — chips grandes Positivo/Negativo/Indefinido (diagnóstico) ou stepper numérico com banda calculada (numérico), veterinário pré-preenchido, observação. Sem lote/dose/via — grava `ExameResultado`, nunca `Sanidade`, nunca estoque. |
| 9 | **Relatório de Eventos Vencidos** | Cards no mesmo padrão da Home, Dispensar sempre por card (nunca em massa). |

Nenhuma tela nova além destas 10 (contando 8b) — mesma regra do site: 8b é tela própria porque o formulário e o destino do dado são outros, não uma variação de 8.

### 4.2 Campos e ações por tela

**Calendário Sanitário (cards) — Home**: chips-indicador fixos no topo (Atrasadas · Próx. 30 dias · Confirmadas p/ realizar · **Alerta clínico ativo**), 1 linha de texto tocável resumindo financeiro e adesão (*"R$ 1.240 pendente · R$ 380 vencido · adesão 92%"*). Card por Ocorrência: tipo · nome da Regra · data prevista (contagem regressiva para o fim da janela recomendada) · badge de estado grande e colorido · nº de animais · atraso em vermelho · ícone de carência · **selo vermelho fixo de alerta clínico** · % de adesão da própria Regra. Ordenação fixa por atraso decrescente; destaque discreto (borda, nunca animação) para quem está na janela recomendada — nunca abre sozinho. Card "Realizado" fica visualmente apagado. Sem grade de mês, sem tabela, sem swipe na lista.

**Detalhe da Ocorrência**: cabeçalho fixo mínimo (estado + evento + data em 1 linha; veterinário "Nome + CRMV" sempre visível; financeiro e carência como chips tocáveis). Quando passou do meio da janela recomendada sem abrir, o botão do rodapé troca para a cor de "atraso" do badge. Abas por chip, navegação livre. **1 único botão grande fixo no rodapé**, certo para o estado (mesmo mapeamento da seção 3.3).

*Aba Animais*: cards (não tabela) — nº/nome · **"Hoje: X → Na data: Y"** · tag de origem · status. Critério reprodutivo recebe selo "Projeção estimada". Busca por **número de caravana em teclado numérico** ou QR/chip. Botão flutuante "+ Incluir fora da janela". Exclusão só com seleção + botão + confirmação em folha — nunca swipe.

*Aba Checklist* — ver seção 4.3.

*Aba Resumo*: cards por animal com ícone por item (✓/↷/✗). Banner vermelho fixo no topo quando houver alerta clínico ativo, com contador de dias em aberto.

*Aba Histórico*: lista cronológica só leitura, mais recente no topo, incluindo manutenção/troca do responsável (seção 4.4) e texto integral de avisos exibidos. Botão "Adicionar observação" (chips + voz + texto + foto), só a partir de Realizado. Botão "Compartilhar" com export padrão não configurável.

**Folha — Incluir animal fora da janela**: busca por caravana ou QR/chip. Motivo por chips prontos (incluindo motivos biológicos, ex. "catch-up de categoria atrasada") — texto livre só em "Outro". Checkbox obrigatório habilita o botão. Mesma folha serve ao atalho "Desconsiderar cronograma".

**Folha — Pular item**: pergunta em 1 linha + chips de motivo opcional (voz/texto curto). No item do veterinário, aviso em destaque sobre responsabilidade técnica.

**Folha — Desconsiderar cronograma**: aviso curto em negrito + link "Ver texto completo" quando a Regra tocar palavra-chave de programa sanitário oficial — o texto integral (exibido ou só disponível via expansão) é sempre gravado verbatim no Histórico. Card financeiro compacto embutido. Campos opcionais atrás de "Ajustar".

**Chip + Folha — Financeiro rápido**: chip de status (Pendente amarelo / Parcial amarelo-claro / Completo verde com valor). Toque abre folha rápida só com Valor + Vencimento + "Tirar foto da nota/boleto" (fila offline-first). "Completar no site" via webview para o resto — nunca reconstruído nativamente. Enquanto não completado, fica "Parcial", nunca "Completo".

**Folha — Reabrir**: aviso de 1 linha + motivo opcional. Histórico conta quantas vezes já foi reaberta e por quem.

**Realizar Evento**: disponível só a partir de Confirmado. 100% offline-first, indicador "N pendentes de sincronizar" + botão explícito "Sincronizar agora". Faixa-resumo no topo com status por animal, tocável para saltar; para ~50+ animais ganha busca por caravana, contadores tocáveis por status e botão "Ir para o próximo pendente". Ação em massa "Marcar todos como Aplicado = Sim". Cartão de tela cheia por animal, navegação Próximo/Anterior (swipe só como atalho):
- Aplicado? Sim/Não (72px) — se Não, chip de motivo obrigatório.
- Lote do medicamento (só Vacina): botões "Escanear" e "Selecionar da lista" com mesmo tamanho/peso, lado a lado (lista = lotes já no estoque do produto, mesma fonte do FIFO, validade em destaque); digitação manual só como terceira opção.
  - Lote já vencido: card vermelho, **bloqueia o avanço**.
  - Lote a vencer em ≤7 dias: soft-block com **1 confirmação agregada por lote**.
  - Botão "Aplicar este lote ao restante do grupo".
- Dose/volume — stepper com incremento vindo do cadastro do produto (mL fino vs. doses/UI inteiras).
- Via — chips (IM/SC/IV/oral/outra).
- Responsável pela aplicação — ver seção 4.4.
- Horário/data real — pré-preenchido "agora".
- Observação clínica — ver seção 4.5.
- Carência — só leitura, calculada a partir da data real, nunca editável no app.

Confirmação final: "Confirmar realização" com contador "X de Y" → folha explícita, ação não pode ser desfeita.

**Realizar Exame**: mesmo padrão de navegação e offline-first de "Realizar Evento", mas tela própria. Cartão de tela cheia por animal:
- **Diagnóstico**: 3 chips grandes — Positivo / Negativo / Indefinido. Positivo mostra aviso inline (descarte automático); Indefinido mostra aviso de repetição.
- **Numérico**: stepper/input do valor + texto de conduta calculado na hora contra a faixa do `ExameDefinicao` (abaixo/dentro/acima).
- Veterinário — só leitura (nome + CRMV), mesmo padrão do checklist.
- Observação clínica — mesmo padrão da seção 4.5.
- **Nunca** mostra lote, dose, via ou estoque — texto fixo de rodapé reforça "sem baixa de estoque" (o padrão mental do usuário treinado em "Realizar Evento" é o oposto).

Confirmação final: "Confirmar realização" → gera `ExameResultado` por animal, mesma folha de confirmação não-desfazível de "Realizar Evento".

**Relatório de Eventos Vencidos**: cards no padrão da Home, atraso em destaque, chips-indicador + "Motivos mais comuns" (top 3, só leitura). Dispensar por card, nunca em massa. Toggle "Mostrar dispensados" como aba secundária.

### 4.3 Como o checklist aparece no celular

Pilha vertical de cartões, **todos visíveis ao rolar** (nunca 1 item por tela cheia isolado). Card pendente expande no próprio toque. Redação idêntica à do site.

No item "Confirmação com o veterinário selecionado": nome + CRMV em destaque, dois botões grandes Sim/Não, "Pular" abaixo (três caminhos distintos). Se "Não": abre no mesmo card o campo de justificativa obrigatória (chip + nota complementar por voz/texto); card com faixa vermelha fixa "Veterinário não confirmou", propagada para Resumo/Histórico/Home/Vencidos — só desaparece se a resposta mudar ou o item for reaberto.

Barra de progresso fina fixa no topo ("3 de 5 itens"). "Confirmar ocorrência" só habilita com 100% Cumprido/Pulado.

### 4.4 Responsável pela aplicação e autenticação em dispositivo compartilhado

- **Login**: PIN numérico grande é a opção principal e sempre visível (luva/mão suja não usa biometria); biometria é só atalho opcional, nunca único caminho.
- **Responsável**: pré-preenchido pelo usuário autenticado na sessão (autenticação por sessão, não por ação). Controle de troca com o **mesmo destaque visual** dos botões Sim/Não — nunca um link pequeno secundário. Lista de funcionários cadastrados com "últimos usados" no topo; "Outro" só em caso excepcional.
- Ao reabrir "Realizar Evento" após inatividade (>30 min) ou avançar para novo animal depois desse intervalo: confirmação rápida de 1 toque **"Continuar como [Nome]?"** — não pede login de novo.
- Toda manutenção ou troca do responsável é **registrada no Histórico** (quem, quando, manteve ou trocou).

### 4.5 Observação clínica, foto financeira e offline-first

- **Observação clínica**: abre primeiro com **chips de achados comuns** (Sem alterações, Reação local, Febre, Abscesso/nódulo, Outro). Voz e texto digitado em igual destaque para o resto. Opcional, nunca bloqueia.
- **Foto da nota/boleto**: mesma fila offline-first de Checklist/Incluir fora da janela/Realizar Evento — captura sem sinal, envia ao sincronizar.
- **Sincronização**: indicador "N pendentes" + botão explícito "Sincronizar agora", além da tentativa automática em segundo plano.
- **Conflito entre dispositivos**: saldo do lote recalculado no servidor na sincronização, nunca debitado otimisticamente em paralelo. Se a soma das baixas de dois dispositivos ultrapassar o saldo, a Ocorrência recebe alerta **"Divergência de estoque a revisar"** no Histórico — nenhum registro de aplicação é descartado; resolução manual no site.

### 4.6 Fluxo entre os 4 estados

Idêntico à seção 3.3, adaptado a toque em vez de clique — ver diagrama da seção 3.3 (a arquitetura de estados é uma só, compartilhada entre site e app).

### 4.7 Widget financeiro no celular

Nunca o formulário completo do site dentro do app. Chip de status (Pendente amarelo / Parcial amarelo-claro / Completo verde) no cabeçalho, no checklist e no Resumo. Lançamento rápido nativo limitado a Valor + Vencimento + foto do boleto. "Completar no site" via webview. Pular o item não apaga o chip.

### 4.8 Calendário com os 4 estados

| Estado | Cor | Rótulo | O que o card oferece |
|---|---|---|---|
| Provável | Cinza/azul claro | "A abrir" | Botão "Abrir" + contagem regressiva da janela recomendada |
| Em edição | Amarelo | "Em checklist" | Abre direto na aba Checklist; selo vermelho se veterinário já respondeu "Não" |
| Confirmado | **Azul** | "Pronto p/ realizar" | Abre com "Realizar evento" destacado; alerta de lote a vencer/vencido se já souber pelo estoque |
| Realizado | **Verde** + check | "Concluído" | Card apagado, só "Ver resumo"; ícone de carência ativa sobrevive ao estado apagado enquanto a carência não vencer |

Azul para Confirmado e verde para Realizado (nunca dois tons da mesma cor) — reconhecer o estado por cor, sem ler texto, sob sol forte no curral. Camadas sobrepostas em qualquer estado não terminal: atraso (vermelho), alerta clínico (ícone vermelho fixo), financeiro pendente/parcial (ícone laranja), carência ativa (ícone de gota). Ordenação fixa por atraso decrescente.

---

## 5. Gaps e riscos — por nível

### 🔴 Alto risco

**R-1 — Migrar `usa_cronograma` de opt-in para universal muda o comportamento de TODAS as regras já cadastradas de uma vez.**
- *Gap*: hoje regras sem `usa_cronograma=True` nunca passam por cronograma — vão direto para `AplicacaoAgendada`/`Sanidade` no lançamento manual. No dia do deploy, todas ganham Ocorrência automaticamente.
- *Risco*: usuários que já têm o hábito de lançar preventivo "direto" (sem cronograma) são pegos de surpresa; pode haver dado incompleto (regras sem produto/dose cadastrado, por exemplo) que quebra a geração automática da Ocorrência.
- *Mitigação*: (a) feature flag por fazenda (`fazenda.parametros.usar_ocorrencia_universal`), ligada só depois de o usuário confirmar que revisou o cadastro de Regras; (b) rotina de "saúde do cadastro" que lista Regras sem produto/dose antes de habilitar; (c) comunicar a mudança explicitamente (changelog/aviso na primeira tela) — não é um patch silencioso.

**R-2 — Sugestão automática por projeção para regras por ÉPOCA não existe hoje — é motor novo.**
- *Gap*: `_datas_gatilho` (evento de vida) já sabe projetar por animal; época nunca teve sugestão automática (é lote/categoria escolhido manualmente no lançamento).
- *Risco*: é a peça de maior esforço de engenharia do pacote — precisa calcular, para cada animal, "ele vai estar na categoria/idade-alvo na data da próxima ocorrência?" cruzando `data_nasc`, categoria atual e as mesmas regras de categorização que já existem em `rules/categorizacao` (ou equivalente) — mas projetadas no tempo, não no presente.
- *Mitigação*: escrever esse motor como função pura, testável isoladamente (dado um conjunto de animais + a categoria-alvo + a data futura, devolve quem entra) antes de acoplar à Ocorrência; cobrir com os mesmos testes de categorização por idade que já existem, só trocando "hoje" por uma data arbitrária no futuro.

**R-3 — Divergência de estoque entre dois dispositivos offline (mobile) exige lógica de conciliação no servidor que não existe hoje.**
- *Gap*: hoje a baixa de estoque é síncrona (dentro da mesma request). Offline-first com fila introduz a possibilidade real de dois tablets baixarem o mesmo lote sem saber um do outro.
- *Risco*: saldo de estoque incorreto sem ninguém perceber, se a conciliação não for implementada corretamente.
- *Mitigação*: a baixa nunca é otimista no cliente — o servidor recalcula o saldo do lote na sincronização e gera o alerta "Divergência de estoque a revisar" (já especificado na seção 4.5) em vez de tentar resolver automaticamente. Implementar e testar esse caminho ANTES de liberar uso em mais de um dispositivo por fazenda.

### 🟠 Médio risco

**R-4 — O wizard `FormCalendarioSanitario.tsx` tem usuários acostumados com o fluxo atual (mesmo com bug).**
- *Mitigação*: substituir de uma vez (não incrementalmente) — o bug relatado é justamente fruto de incrementos em cima de um modelo que não aguenta mais peso. Comunicar a mudança de UI claramente no changelog.

**R-5 — Checklist com item "Financeiro" pulável (decisão do usuário) pode reduzir a cobertura de lançamentos financeiros vs. hoje (onde o popup pós-aplicação pelo menos pergunta sempre).**
- *Mitigação*: o widget persistente (visível em toda tela da Ocorrência até Realizado) compensa — é mais visível que o popup atual, que aparece uma vez só. Medir taxa de preenchimento financeiro pós-lançamento como indicador de sucesso.

**R-6 — Motivo obrigatório para Pular/Dispensar em eventos de programa sanitário oficial (aftosa, PNCEBT, raiva) ficou registrado como pendência (seção 6) — sem isso, o gate regulatório fica só no aviso textual, não em trava real.**
- *Mitigação*: priorizado pela persona Cooperativa/Veterinário como a PRÓXIMA rodada de cadastro de Regra (adicionar metadado "programa oficial" na Regra). Não bloqueante para o lançamento inicial, mas deveria entrar na Fase 5 (seção 7).

### 🟡 Baixo risco

**R-7 — Verificar se o cadastro de lote de compra (Estoque, Fase G/FIFO) já grava data de validade — pré-requisito do gate "lote vencido bloqueia".**
- *Ação*: 1 investigação de 15 minutos antes de começar a Fase 4 (Realizar Evento) — ler `backend/fazenda/models/estoque.py` e confirmar o campo. Se não existir, é um campo a mais no cadastro de lote (baixo esforço), não redesenho.

**R-8 — Motivo do "não-conformidade de 100%" da banca de personas (91%/90%) já foi resolvido no texto final — não é risco de implementação, é registro de decisão de produto.**
- *Ação nenhuma*: os pontos de divergência (seção 3 do resultado do gauntlet-loop, já incorporados nos textos das seções 3 e 4 deste documento) foram todos resolvidos antes de chegar aqui.

---

## 6. Pendências registradas (fora desta rodada, deliberadamente)

- Motivo condicionalmente obrigatório em Pular/Dispensar para eventos de programa sanitário oficial (depende de metadado de Regra ainda não criado).
- Verificação de intervalo mínimo entre aplicações do mesmo produto/classe (protocolo clínico) — lê o histórico de `Sanidade`, sem campo de cadastro novo.
- Painel consolidado de adesão entre fazendas-cliente (visão multi-tenant para cooperativas) — fora da arquitetura multi-tenant isolada atual.
- Taxa real de uso do scanner de lote em campo (mobile) — monitorar pós-lançamento.
- Sem migração dos cronogramas hoje abertos — recriação manual pelo usuário.

---

## 7. Passo a passo — sequência de implementação

Ordem pensada para nunca deixar o sistema num estado pior do que o atual entre fases — cada fase entrega algo utilizável e testável isoladamente.

### Fase 0 — Preparação (sem mudança de comportamento visível)
1. Investigar R-7 (validade de lote no Estoque).
2. Escrever o motor de projeção por época (R-2) como função pura + testes, sem acoplar a nada ainda.
3. Desenhar a tabela de Checklist (item, tipo de template, status, responsável, timestamp, motivo) e migração Alembic — sem preencher dado ainda.
4. Adicionar campo "Reabrir" ao motor de `cronograma_sanitario.py` (estado `confirmado → em_edicao`, preservando checklist).

### Fase 1 — Backend: universalizar a Ocorrência
5. Generalizar `cronograma_aberto()`/`eventos_agenda()` para rodar em TODA regra (`tipo_agendamento` em `epoca` ou `evento`), não só `usa_cronograma=True` — atrás de feature flag por fazenda (R-1).
6. Acoplar o motor de projeção por época (passo 2) na geração de `CronogramaSanitarioAnimal` "sugerido" para regras por época.
7. Implementar a tabela/API de Checklist: gerar template por `categoria_preventiva` (vacina/exame) ao abrir a Ocorrência; endpoints marcar cumprido/pulado (reaproveitar o dispatch de `POST /agenda/realizados`, prefixo novo `cronograma_sanitario_checklist_`).
8. Implementar "Desconsiderar cronograma" (endpoint que confirma sem exigir checklist completo).
9. Testes de backend cobrindo os 4 estados + reabertura + desconsiderar, espelhando o padrão de testes já existente (`backend/tests/test_cronograma_sanitario.py`, `test_calendario_sanitario.py`).

### Fase 2 — Site: telas 1-2 (Calendário + Detalhe)
10. Substituir `FormCalendarioSanitario.tsx` (cadastro de Regra) — remover o efeito de auto-preenchimento que causa o bug relatado; sem "usa_cronograma" como checkbox.
11. Reescrever `CalendarioSanitarioView` como a tela 1 (indicadores + tabela com os 4 estados coloridos).
12. Construir a tela 2 (Detalhe da Ocorrência) reaproveitando o painel de seleção de animais já existente em `RelatorioEventosVidaView` (construído nesta mesma sessão) para a aba Animais.
13. Construir a aba Checklist (consumindo a API da Fase 1) com o item do veterinário (Sim/Não + alerta persistente).

### Fase 3 — Site: financeiro + modais
14. Adaptar `PopupVinculoFinanceiro`/`vinculoSanitarioFinanceiroBridge` para o widget persistente (novo gatilho: qualquer momento, não só pós-aplicação).
15. Modais: Incluir fora da janela, Pular item, Desconsiderar cronograma, Reabrir (a maioria é CRUD simples sobre o que já existe nas Fases 1-2).

### Fase 4 — Site: Realizar Evento + Vencidos
16. Tela Realizar Evento: campos de dose/via/responsável por animal (novos no registro de `Sanidade` — migração de coluna), gate de lote vencido/a vencer (depende de R-7).
17. Relatório de Eventos Vencidos (query simples: data prevista passada + estado ≠ realizado) + Dispensar.

### Fase 5 — Mobile
18. Reaproveitar `Cronogramas.tsx` (Acompanhamento, já construído nesta sessão) como base da tela 2 mobile — adicionar checklist e os 4 estados por cima.
19. Home mobile (cards com os 4 estados coloridos) — reaproveitar `CalendarioSanitario.tsx` mobile como base.
20. Realizar Evento mobile (cartão cheio por animal) + offline-first (checklist, incluir fora da janela, realizar evento, foto financeira) — depende de R-3 (conciliação de estoque) estar pronta no backend.
21. Login por PIN (se ainda não existir no app) — verificar mecanismo de autenticação atual antes de estimar esforço.

### Fase 6 — Corte e comunicação
22. Ligar a feature flag por fazenda (R-1) depois de rodar a "saúde do cadastro" (Regras sem produto/dose).
23. Comunicar a mudança ao usuário (changelog) — não é incremento silencioso, é um modelo novo.
24. Usuário recria manualmente os cronogramas de teste que hoje estão travados (decisão já tomada — sem migração).

### Fase 7 (depois, não bloqueante)
25. Metadado "programa sanitário oficial" na Regra + motivo obrigatório condicional (R-6, pendência da seção 6).
26. Verificação de intervalo mínimo entre aplicações (pendência da seção 6).
