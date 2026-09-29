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
