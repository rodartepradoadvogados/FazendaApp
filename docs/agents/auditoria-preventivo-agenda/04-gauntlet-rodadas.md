# Gauntlet-loop — registro das rodadas

## Rodada 1 — resultado

| Persona | M1 Vacinas e exames + Protocolos | M2 Agenda | P0 | P1 |
|---|---|---|---|---|
| Zootecnista | 69% | 70% | 0 | 9 |
| Veterinário | 62,5% | 87,5% | 0 | 7 |
| Peão de fazenda | 80% | 66,7% | 0 | 4 |
| Produtor / dono | 80% | 83% | 0 | 3 |
| Dono de cooperativa | 58% | 62,5% | **5** | 4 |
| Pesquisador UX | 71% | 75% | 0 | 5 |
| **Média** | **70,1%** | **74,1%** | 5 | 32 |

Critério de saída: média ≥ 90% em cada mockup, nenhuma persona < 80%, zero P0. **Não passou** → rodada 2.

Leitura: a arquitetura de informação e a acessibilidade passaram (F1 de fidelidade ao shell = 1 quase unânime; teclado/aria sólidos; estado na URL). O que derrubou a nota foi (1) **rastreabilidade** (log sem quem/hora, Desfazer que apaga), (2) **coerência de dados e regras clínicas** entre os dois mockups, (3) **vazamento de vocabulário** banido e verbos além de "Feito", (4) **mobile** (toasts empilhados, Adiar em 4 toques, primeira dobra do M1).

## Decisões de síntese (conflitos resolvidos)

1. **Regra do dono vence sugestão de persona.** O intervalo do "retorno ao cio" (Scratch, 14 d) é regra validada do dono (PRODUCT.md, princípio 1). O Veterinário lembra que biologicamente o retorno se observa em 18–24 d. **Decisão:** mantém 14 d como padrão, rotula "Checar retorno ao cio (Scratch, 14 dias)" e mostra "parâmetro da fazenda" no detalhe; fica registrado como pergunta ao dono, não muda no mockup.
2. **Numeração do protocolo IATF:** o contrato misturava ordinal ("1º dia") com D-número. **Decisão:** usar **"Dia 0 · Dia 7 · Dia 9 · Dia 11"** contados do início (Dia 0 = colocação do implante), igual à linguagem da fazenda. Glossário do `02-proposta.md` será atualizado.
3. **Aftosa:** não fixar "campanha de maio/novembro". A data é definida pela defesa sanitária estadual e é editável; o mockup mostra a vacina como **exemplo**, sem calendário oficial embutido.
4. **Cor do botão da linha:** os 16–19 botões dourados por tela são ruído. Botão de linha (**Feito / Registrar**) passa a **marinho sólido** (botão primário do DESIGN.md); dourado só para a ação primária global do cabeçalho e para o confirmar dentro de gaveta.
5. **Barra da Agenda no desktop = 4 controles:** segmentado Hoje|Semana|Mês · Agrupar (dropdown) · **Filtros** (botão que abre categorias e gavetas) · Busca.
6. **Verbo:** nas tarefas de campo o botão é sempre **"Feito"** (com `›` quando abre gaveta para detalhes). "Inseminar", "Lançar pesos" e "Decidir" deixam de ser verbos de linha; "Decidir" fica restrito ao trilho *Alertas e decisões*. Aplicação sanitária na Agenda abre **a mesma gaveta "Registrar aplicação" do M1**.
7. **Sidebar:** ambos os mockups usam o shell real (10 px), idêntico entre si. Recomendação separada (fora do mockup): subir a sidebar real para 12 px.
8. **Escopo de conformidade oficial:** fluxo regulatório completo de exame positivo (notificação, interdição, GTA) e visão multi-fazenda ficam **fora de escopo**, registrados como pendência; o mockup mostra reagente identificado por animal, nº do laudo e um aviso de notificação obrigatória.

## Lista única de correções — Rodada 2

### A. Rastreabilidade e auditoria (Cooperativa P0 + Veterinário P1) — ambos os mockups
- **A1.** Todo registro/estorno/pulo/reabertura/inativação grava um **evento de auditoria imutável**: quem, data **e hora**, o quê, motivo, frasco, dose, via, aplicador. Visível na aba Histórico do drawer e no Histórico geral (coluna "Quem/Quando").
- **A2.** **Desfazer nunca apaga**: cria entrada "Estornada por X em dd/mm hh:mm" mantendo a original (riscada). Desfazer de "Pular" também gera entrada.
- **A3.** **Pular** exige motivo (lista única compartilhada M1/M2: Sem insumo · Animal fora do lote · Adiada por manejo · Decisão do veterinário · Outro+texto); para vacinas de programa oficial (B19, aftosa) o motivo é obrigatório e mostra aviso. A Observação digitada é gravada. "Não vou fazer" **não vem com motivo pré-marcado**.
- **A4.** **Registrar pela Agenda grava** frasco, aplicador, via, dose e data real (mesma gaveta do M1); Concluídos mostra "Feito às hh:mm por Fulano · Frasco …".
- **A5.** **Exportar** (CSV) respeita Visão/Filtros e inclui concluídas com quem/hora/motivo/frasco/lote; PDF idem.
- **A6.** **Inativar/Editar vacina do calendário** pede confirmação com "N aplicações previstas serão removidas", motivo e gera log; "Corrigir/via auditada" abre uma tela mínima (não só toast).
- **A7.** Campo **aplicador** (Nome + função; CRMV opcional). Para **B19**: aviso "aplicação exclusiva de veterinário cadastrado" e checagem de faixa 3–8 meses (aviso, não bloqueio).
- **A8.** **Exame com resultado positivo**: registrar **animal reagente** (identificado), nº do laudo (opcional) e aviso destacado "Notifique o serviço veterinário oficial"; sem contagem anônima por lote.

### B. Regras clínicas e de manejo (Veterinário/Zootecnista)
- **B1.** Validade do frasco: **aviso a ≤30 dias** ("vence em 16 dias") e **vencido exige ciência registrada** (checkbox "Ciente, usar assim mesmo" + log). Não bloqueia.
- **B2.** **Carência** também nos protocolos curativos e na baixa (leite e carne).
- **B3.** **Multidose**: rótulo "dias após a dose anterior"; preview mostra datas absolutas; "recorrência" e "multidose" mutuamente exclusivas ou explicadas.
- **B4.** **Exame ≠ aplicação**: fluxo próprio "Registrar exame" (tipo, animais, data da inoculação/coleta, **leitura em 72 h** para TB, resultado por animal, reteste com data); exames pendentes/retestes atrasados aparecem no Calendário e no Histórico.
- **B5.** **Carteira do animal** consistente: B19 é dose única; data passada nunca é "Em dia" (vira "Atrasada"); última dose conhecida nunca é "Nunca tomada".
- **B6.** **BST**: aptas só com DEL ≥ 60 (regra da fazenda), coerente com a aba Excluídos.
- **B7.** **Cobertura**: uma definição única ("% de animais com **todas** as vacinas aplicáveis em dia") + % por vacina; unidade sempre explícita ("47 animais", "3 aplicações previstas"); cores de limiar únicas; **filtro de lote aplica à faixa e à página inteira** ou avisa que a faixa é global.
- **B8.** **Novo protocolo**: animais já em outro protocolo ficam marcados/indisponíveis com aviso; mostra elegibilidade (DEL, prenhez, PEV); estoque previsto desconta protocolos abertos; editor de modelo aceita **vários produtos por etapa**; rótulos de dia sem duplicação; "Dia 4 de 4" corrigido.
- **B9.** **Baixa de protocolo** pede data real e oferece reprogramar as etapas seguintes.
- **B10.** **Dose por peso** onde couber (ivermectina): usa peso médio do lote; nunca "1 dose por animal" cego.
- **B11.** Rótulos: "Checar retorno ao cio (Scratch, 14 dias)"; "Fim do período de espera voluntário (PEV)"; glossário acessível por **toque/foco** (botão ⓘ com popover), não só hover.
- **B12.** Gaveta **Reprodução › "Agendar 1º dia"** vira "Iniciar protocolo" → abre **Novo protocolo** pré-preenchido (lote, modelo), não cria tarefa por vaca; tabela ganha coluna Lote e Motivo.

### C. Mobile (Peão)
- **C1.** **Toast agregado** único e largo ("3 tarefas feitas · Desfazer última"), nunca empilha nem cobre a próxima linha.
- **C2.** **Adiar para amanhã em 2 toques**: o ⋯ já mostra "Adiar p/ amanhã" e "Escolher data…".
- **C3.** Gavetas **sem rolagem interna aninhada**; inputs e selects ≥ 44 px.
- **C4.** **Anti-toque duplo**: mantém o espaço da linha durante a saída (≥250 ms) e afasta Feito de ⋯ (≥ 8 px).
- **C5.** **M1 primeira dobra a 390 px**: cabeçalho compacto e **grupo "Hoje"** visível; primeira aplicação acima de y≈520; sub-navegação em **uma linha** (ou seletor) sem esconder itens.
- **C6.** Texto principal ≥ 16 px no mobile (apoio ≥ 14). Datas **dd/mm/aaaa**; "kg" sem duplicar; remover copy de desenvolvedor ("Única porta de escrita…", "TRILHO GESTÃO").

### D. Visão do dono (Produtor)
- **D1.** **Chip de Gestão** perto do topo: "Gestão: 1 conta vence hoje · R$ 12.480".
- **D2.** **Erro de rede** mantém o último estado conhecido + faixa "Sem conexão · dados de 14:02 · Tentar de novo"; números não viram "—".
- **D3.** **Custo**: rótulo "Custo previsto / realizado"; coluna **Custo** e **total do mês** no Histórico; drawer de aplicação **pulada** não mostra custo lançado.
- **D4.** Um **total único** na Agenda ("19 = 15 de hoje + 4 atrasadas"); o "0" grande não pode ler como zero tarefas.
- **D5.** Resumo sticky do Registrar não cobre o campo Custo (layout em 1440×900).
- **D6.** "Dia fechado" cita conta vencendo e decisões pendentes.
- **D7.** Botão "Nova vacina do calendário" → **"Cadastrar vacina"**.

### E. Vocabulário, consistência e sistema (Pesquisador)
- **E1.** **Varredura de vocabulário** no DOM: eliminar "baixa/baixar/dar baixa", "janela", "pendências", "Incluir animal fora da janela" (→ "Incluir animal fora do grupo previsto"), "Baixar coluna" (→ "Marcar coluna como feita"), "Atrasado · 12 baixas" (→ "12 marcações atrasadas" ou "Atrasado · 12 dias"). **Script de auditoria de texto** roda antes de entregar.
- **E2.** **Uma escala de estados** para aplicação (Prevista/Confirmada/Registrada/Atrasada/Pulada/**Estornada**) e outra para tarefa (A fazer/Feita/Adiada/Atrasada); Protocolos reusa "Prevista/Feita/Atrasada" — sem terceira escala.
- **E3.** **Wizard de vacina**: validação por passo; `?passo=3` sem dados volta ao passo 1; rascunho gravado a cada passo; "Salvar" desabilitado sem nome.
- **E4.** Navegação: um só "Histórico" por módulo (renomear o de protocolos para "Concluídos"); "Tratamento" sem duplo sentido; "Calendário" ≠ "Vacinas do calendário" (→ "Cadastro de vacinas").
- **E5.** **Shell do M1 idêntico ao do M2 e ao app real** (sidebar 10/28 px, rótulos de seção em 1 linha, News/sino e FAB do assistente presentes); h1 28 px.
- **E6.** **Barra da Agenda = 4 controles** (decisão 5); verbos (decisão 6).
- **E7.** DESIGN.md: **sem sombra pesada** em drawer/dialog (borda + fundo); contraste ≥ 4,5:1 nos chips (corrigir 4,37); "Fechar o dia" sem quebra torta; links reais (não texto) em "Financeiro › Sanidade".
- **E8.** Botões de linha marinho (decisão 4).

### F. Dados canônicos (todos)
- **F1.** **Um único conjunto de dados** nos dois mockups (ver `mockups/DADOS-CANONICOS.md`): mesma fazenda, lotes, contagens, produtos, carências, datas, plano IATF. Nenhuma contradição entre M1 e M2.

## Divergências que ficam como pendência (não bloqueiam)
Visão multi-fazenda; fluxo regulatório completo de exame positivo (notificação/interdição/GTA); calendário oficial estadual; impressão/PDF reais; regime de aftosa por UF.

---

## Rodada 2 — resultado

| Persona | M1 | M2 | P0 | Situação |
|---|---|---|---|---|
| Zootecnista | 87,5% (69) | 80% (70) | 0 | 10 resolvidas, 6 parciais; 4 P1 novos (coerência de dados) |
| Veterinário | 87,5% (62,5) | 87,5% (87,5) | 0 | 7 resolvidas, 5 parciais; exame TB positivo e ceftiofur 5×10 mL |
| Peão | 90% (80) | 83,3% (66,7) | 0 | 8 de 10 resolvidas; toast agregado quebra palavras a 390 px |
| Produtor | 90% (80) | 83% (83) | 0 | 8 de 12 resolvidas; Hoje antes de Atrasadas no M1 mobile |
| Cooperativa | 75% (58) | 87,5% (62,5) | **1** | 7 resolvidas; exame positivo só num toast |
| Pesquisador | 86% (71) | 92% (75) | 0 | 10 de 19 resolvidas; cópia do drawer Registrar diverge |
| **Média** | **86,0%** (era 70,1) | **85,6%** (era 74,1) | 1 | **Não passou** → rodada 3 |

Causas remanescentes: (1) dados divergentes entre M1 e M2 (92×96 mL, brincos, dia dos protocolos); (2) exame positivo sem persistência auditável; (3) drawer "Registrar" com rótulos diferentes nos dois; (4) detalhes de mobile (toast, ordem Hoje×Atrasadas, folha de campo); (5) carteira/cobertura com casos de borda.

## Lista única — Rodada 3

**Decisão de síntese:** dados nomeados passam a vir de uma **fonte única** (`mockups/DADOS-CANONICOS.md`, seção "Extensão (rodada 3)"), e os dois mockups ficam **ligados por links reais**. Toda contagem (cobertura, Semana, Próximos 7 dias) é **calculada** a partir do conjunto de dados, nunca digitada.

**Ambos (X)**
- X1 Adotar integralmente a extensão canônica (brincos por lote, Dia 0 para todos os protocolos, doses, frascos, relógio 14:05, formatos, sidebar "Protocolos", 16 px, sub-marca).
- X2 Toast agregado sem quebra de palavra (largura ≥ 280 px, ≤ 92 vw); "Desfazer" com rótulo verdadeiro (desfaz só a última) e mensagem de confirmação "Desfeito".
- X3 **Drawer "Registrar aplicação" idêntico** em M1 e M2: mesmos campos e rótulos (**Quem aplicou**, **Registrado por**, **Custo**, CTA **Salvar registro** / **Salvar exame**), mesma ordem; frasco vencido nunca pré-selecionado; via padrão fixa com aviso ao trocar.
- X4 **Exame TB positivo persistente** (Histórico, CSV, carteira, cobertura, comprovante bloqueado, banner persistente com checkbox de notificação), aplicador veterinário obrigatório com aviso, produto/frasco/validade da tuberculina, leitura ≥ 72 h.
- X5 Carteira/cobertura: "Sem registro" ≠ "Em dia"; cobertura calculada; B19 fora da faixa = "Não se aplica".
- X6 "Registrado por" e "Aplicador" separados na tela, no Concluído/Histórico e no CSV (2 casas decimais).
- X7 Links: "Sanidade › Vacinas e exames" e "Protocolos › Em andamento" como links reais; chip de Gestão **só na Agenda**; um único "Histórico" por módulo ("Histórico do dia" → "Feito hoje").
- X8 Mini-calendário com células ≥ 44 px; "Fechar o dia" sem quebra torta; Esc após F5 devolve foco a um elemento útil; atalho "F" documentado no menu ou removido; filete 3px por linha → ícone de categoria em quadrado colorido (sem borda lateral).
- X9 Shell idêntico e igual ao real: item "Protocolos" nos dois, sino e FAB do assistente também a 390 px, mesma sub-marca.

**Só M1**
- M1a Corrigir: a entrada original vira **"Corrigida (substituída por #n)"**, não pode ser corrigida de novo, custo recalculado sem dupla contagem.
- M1b Histórico: colunas **Aplicador** e **Registrado por**, **lote do frasco**, marca de exceção (B19 por não-veterinário; frasco vencido com ciência); filtros por aplicador e por lote do frasco (recall).
- M1c Modelos: Editar/Duplicar/Ativar geram log e mantêm histórico de versões.
- M1d Mobile 390: **Atrasadas antes de Hoje** (sem reordenar por CSS); "Cadastrar vacina" e "Imprimir folha de campo" alcançáveis na 1ª tela (menu ⋯ do cabeçalho); folha de campo em cards sem estouro horizontal.
- M1e Drawer Registrar: resumo não cobre o Custo (resumo compacto no topo do formulário, expansível).
- M1f Novo protocolo: legenda de elegibilidade por categoria (novilha: idade/peso; vaca: DEL/PEV/prenhez), passo na URL.
- M1g Cobertura: lote 01 e demais recalculados; casos "sem a dose" contam como pendentes.

**Só M2**
- M2a "Próximos 7 dias" e visão Semana/Mês **fecham entre si**; etapas dos 4 protocolos de hoje/semana aparecem (IATF Dia 9, Mastite Dia 3, Adaptação Dia 4, Indução Dia 7).
- M2b Erro de rede: o Feito offline **entra na fila** ("guardado neste aparelho, envia ao reconectar"), sidebar mostra "Sem conexão" (âmbar) e "Atualizado às 13:52".
- M2c "Registrar exame" na Agenda usa o mesmo drawer do M1 (tuberculina com frasco/validade, veterinário habilitado).
- M2d Adiar e Excluir tarefa pedem motivo (lista única).
- M2e Gaveta Reprodução: seleção múltipla + "Iniciar protocolo com N vacas" → **link real** ao Novo protocolo do M1 com lote/vacas pré-selecionados; coluna Lote e Motivo.
- M2f Secagem mostra o lote de origem; rótulo "Checar retorno ao cio (14 dias)" (Scratch só dentro do ⓘ).
- M2g "Concluídos hoje" e "Dia fechado" com a mesma conta.

---

## Rodada 3 — resultado

| Persona | M1 | M2 | P0 | Situação |
|---|---|---|---|---|
| Zootecnista | 87,5% (=R2) | 80% (=R2) | 0 | 2 P1: Cobertura contradiz "82 sem registro"; M2 com etapas de protocolo em dias que o M1 não tem; "undefined" na carteira |
| Veterinário | **93,75%** (87,5) | 87,5% (=R2) | 0 | TB positivo resolvido de ponta a ponta; 1 P1 na Cobertura; falso "sem registro" numa sorologia do Histórico |
| Peão | 90% (=R2) | **75%** (83,3) | 0 | Toast M2 estreito a 390 px; Adiar virou 5 toques com o motivo obrigatório |
| Produtor | 90% (=R2) | **92%** (83) | 0 | tabela de Cobertura estoura a 1440 px; 11 candidatas × 15 elegíveis |
| Cooperativa | 75% (=R2) | 87,5% (=R2) | **1** | KPI "80% em dia" conta "sem registro" como em dia; modelo editado altera protocolos em andamento; "Adiar tudo" com motivo que ninguém escolheu |
| Pesquisador | **93%** (86) | 92% (=R2) | 0 | drawer "Registrar" ainda diferente entre M1 e M2; "Desfazer última" do M2 desfaz tudo |
| **Média** | **88,2%** (era 86,0) | **85,7%** (era 85,6) | 1 | **Não passou** → rodada 4 (última) |

Causas remanescentes, todas com fonte única de correção na extensão da rodada 4 dos dados canônicos: (1) Cobertura sem modelo de estado único; (2) etapas dos protocolos divergentes; (3) gaveta "Registrar" duplicada em vez de idêntica; (4) conflito auditabilidade × velocidade no Adiar; (5) modelos sem versão; (6) detalhes de layout (toast M2, tabela de Cobertura, FAB, cards altos).

## Lista única — Rodada 4 (última)
**Ambos:** (a) modelo de estado único por animal × item e cobertura **calculada** (extensão §1); (b) etapas dos protocolos idênticas (§2), 11 elegíveis de 28 (§3), TU-2608 nos dois, vias por produto (§4), sino 3, título de protocolo (§8); (c) **gaveta "Registrar" e o toast são o MESMO código nos dois**: o construtor do M2 copia literalmente o drawer e o toast do M1 (HTML/CSS/JS), incluindo o exame com Custo e Via; (d) "Desfazer só a última" com rótulo verdadeiro e desabilitado quando não desfazível; (e) textos da extensão §7; (f) "undefined" impossível (`Não se aplica`).
**M1:** modelo com versão/snapshot e log com quem/quando, Inativar com motivo (§6); Cobertura sem estouro a 1440 px e sem contradição; carteira com 4207 `Inconclusivo`; comprovante funcional (pré-visualização); calendário com coluna "Para quem" legível; mobile: Atrasadas compactas para o "Hoje" aparecer sem duas telas de rolagem; Esc após F5; "Outro" não pré-selecionado; leitura TB padrão = inoculação + 72 h; "pular" do checklist gera log; carência no resumo compacto.
**M2:** Adiar simples em 2 toques sem motivo obrigatório; "Adiar tudo" com motivo único e sem tarefas críticas (§5); toast largo a 390 px (mesmo componente); cards de tarefa sem título em 4 linhas (ação abaixo do texto); FAB sem cobrir ⋯ (padding inferior e FAB 44 px); links reais na gaveta de detalhes; tarefa excluída e movimentação no CSV/log; plural correto ("1 peso registrado").
