# Planejamento unificado — Protocolo sanitário preventivo + Agenda (2 sub-abas)

Fusão dos 4 planos (`prev-A-codigo-primeiro`, `prev-B-usuario-primeiro`, `agenda-A-codigo-primeiro`, `agenda-B-usuario-primeiro`) contra o pedido do dono (`00-PEDIDO-DO-DONO.md`). **O mockup anterior estava errado em relação ao fluxo do dono** (preventivo fora da Central, "Registrar" em Sanidade, sem lista de espera nem agendamento, atrasadas na Agenda). Este documento corrige e é o contrato do novo mockup.

## 1. O fluxo do dono (uma página)

```
CADASTRO (Protocolos › Cadastro) ── protocolo preventivo (vacina ou exame): produto, quem entra, janela, frequência, checklist-modelo
        │  a regra calcula quem entra na JANELA DE APLICAÇÃO
        ▼
JANELA DE APLICAÇÃO ── animais elegíveis por época/marco do animal
        ▼
LISTA DE ESPERA (Protocolos › Aplicar)  ◄── AQUI FICAM os animais da janela. NUNCA aparecem na Agenda.
        │  "Aplicar protocolo" = montar o CRONOGRAMA e AGENDAR
        │  (escolher animais DA janela E FORA da janela — motivo — data/hora/responsável — checklist)
        ▼
CRONOGRAMA + AGENDAMENTO (uma entidade, dois estágios: em montagem → agendado) ──► CHECKLIST
        ▼                                          (veterinário · estoque ou desconsiderar · data · compra/cotação ·
ACOMPANHAMENTO (Protocolos › Acompanhamento)        pagamento já feito · conta a pagar · outros)
   "o que já está agendado"  ── botão APLICAR ──┐
        ▼                                        │  (mesma gaveta, dois lugares)
AGENDA no dia da aplicação  ── botão APLICAR ──┘
        ▼
CONCLUÍDOS (Protocolos › Concluídos) = histórico
```
Regras: (R1) animal na janela só aparece na lista de espera; (R2) só o **agendamento** entra na Agenda, no dia; (R3) **Lançamentos não contempla** o preventivo; (R4) **Sanidade só lê** (calendário, em andamento, concluídos, cobertura) e leva a Protocolos/Agenda para agir; (R5) aplicar = só em Protocolos › Acompanhamento e na Agenda; (R6) inserir animal **fora da janela** = flag + motivo, sempre possível; (R7) aplicação **retroativa** = Protocolos › Aplicar, criando o agendamento e aplicando num passo só; (R8) um animal fica em **uma** lista de espera/agendamento ativo por protocolo; (R9) adiar mantém os animais; cancelar devolve à lista de espera.

## 2. Decisões de síntese (onde os 4 planos divergiam ou perguntaram)
1. **Vocabulário do dono volta:** *janela de aplicação · lista de espera · cronograma · agendamento · aplicar · concluídos*. Cortei apenas o jargão técnico (usa_cronograma, gatilho, Ocorrência).
2. **Cronograma = agendamento: uma entidade, dois estágios** (em montagem → agendado). Na tela aparece como "**Agendamento**" (o cartão que vai para a Agenda) e o assistente de montagem se chama "Montar cronograma".
3. **Dois verbos para "aplicar", separados:** na aba **Aplicar** o botão é **Criar agendamento** (nome da aba fixo pelo dono); em **Acompanhamento** e na **Agenda** o botão é **Aplicar** (dar a baixa real). Nada de "Registrar".
4. **Abas de Protocolos = as do dono:** Cadastro · Aplicar · Acompanhamento · Concluídos (tipo vira filtro: IATF, Sanitário preventivo, Sanitário curativo, Indução, Próprio). Sem "Visão geral" extra.
5. **Sanidade › Preventivo (somente leitura):** Calendário · Em andamento · Concluídos · Cobertura, com "Abrir em Protocolos / Agenda". *(Entendi "Em sanidade, curativo" como Sanidade › Preventivo — o dono confirma.)*
6. **Lançamentos:** sai a sub-aba Preventiva (fica curativo, BST etc.) com aviso e link "Aplicar vacina/exame → Protocolos".
7. **Agendamento com checklist incompleto aparece na Agenda** com selo "checklist pendente" (não some; aplicar pede ciência dos pendentes; nunca bloqueia — regra já travada).
8. **Aviso de "animais na janela que ninguém agendou"** fica no **Painel** da Agenda e na aba Aplicar — nunca na lista do dia.
9. **Agenda: 2 sub-abas:** **Dia a dia** (só lista + calendário Semana/Mês, uma linha fina de contagem) e **Painel** (todos os cards do print + concluídos no período + projeção de repasse, BST, IATF, vacinas, exames, alertas de estoque, pendências; cards **compactos ~72 px**, 6 por linha).
10. **Repasse (Scratch):** configurável (decisão anterior mantida): categoria de produto, usar ou não, produto, frequência, mostrar na Agenda. Vive em Protocolos › Cadastro (cartão "Detecção de cio de repasse") e alimenta Dia a dia/Painel.
11. **Sem atraso artificial:** a 1ª renderização é síncrona e completa; skeleton só por ação explícita (defeito relatado pelo dono).
12. **Integrações do checklist:** veterinário (Pessoa; CRMV), estoque (frasco/lote/validade ou "desconsiderar" com motivo), data/hora, **compra/cotação** (se saldo insuficiente → criar pedido/cotação), **pagamento já realizado** (vincular lançamento), **conta a pagar** (honorário do veterinário, produtos) — todos com link para as telas de Financeiro/Estoque/Cotações.
13. **Exame** segue o mesmo fluxo (janela → lista de espera → agendamento → aplicar), com fase de leitura (TB 72 h) e resultado por animal, reagente persistente (decisões anteriores).

## 3. Dados canônicos v2 (substituem o que colide com `mockups/DADOS-CANONICOS.md`; o resto permanece)
- Data/hora fixas: **terça 29/09/2026, 14:05**. Fazenda Estreito Ponte de Pedra, 151 animais, lotes e brincos por lote como no canônico.
- **Fio condutor: B19** (dose única, fêmeas 3–8 meses, veterinário obrigatório): janela com 20 bezerras elegíveis no Bezerreiro (6104–6123); 6 já na lista de espera há 5 dias; fora da janela: 6110 e 6112 (motivo "aproveitar a visita do veterinário").
- **Lista de espera (total calculado, nunca digitado):** Raiva reforço (6, Lote 03), Clostridioses dose 2 (22, Recria 2), reteste de TB (3, Lote 02), B19 (6 na janela + 2 fora), IBR/BVD (14, Secas), Leptospirose (5, Recria 2). As três "atrasadas" do canônico antigo **viram lista de espera "com janela vencida"** e **saem da Agenda**.
- **Agendamentos:** (a) **Vermifugação — Recria 1, 20 novilhas, hoje 29/09 às 15:30, veterinário Dr. Paulo (checklist completo)** → aparece na Agenda hoje; (b) **IBR/BVD — Secas, 14 vacas, 01/10 09:00** (checklist: vet pendente, estoque ok); (c) **B19 — Bezerreiro, 6+2, 02/10 08:00**, com compra pendente (saldo B19 = 20 doses, ok) e conta a pagar do honorário; (d) **Aftosa — 136 doses, 05/11**, com cotação em andamento.
- **Financeiro:** pagamento já realizado R$ 128,00 (20 doses de B19, Agro Vet) vinculável; honorário do veterinário R$ 350,00 a pagar; conta R$ 12.480,00 vence hoje (gestão).
- **Agenda hoje:** Atrasadas **1** (pesagem de leite, 5 dias) — as sanitárias saem; Hoje **15 de campo** (inclui a Vermifugação agendada); Próximos 7 dias recalculado do conjunto (deve incluir IBR/BVD 01/10 e B19 02/10).
- **Cobertura vacinal:** conta só animais com item `Atrasada`/`Reagente`/`Inconclusivo`; a lista de espera "com janela vencida" (22+6+3+1) mantém 119/151 = 79% (32 pendentes).
- Demais regras (Dia 0 dos protocolos, vias por produto, TU-2608 saldo 100, repasse configurável, etapas dos protocolos) como no canônico.

## 4. Telas do novo mockup (storyboard = `prev-B` telas 1–33, com estes ajustes)
Blocos: **A** Cadastro (2–7) · **B** Lista de espera (8–10) · **C** Montar cronograma e agendar (11–18) · **D** Acompanhamento/Agenda/Aplicar (19–26) · **E** Concluídos, Sanidade (só leitura), Lançamentos (27–32) · **F** Exceções (33) · **G** Agenda nova (Dia a dia lista/Semana/Mês; Painel topo; Painel projeção 30 d; gavetas de card: candidatas IATF, BST, alertas de estoque; concluídos no período; mobile) — do plano `agenda-B` (14 telas).
Ajustes ao `prev-B`: tela 1 "Visão geral" **fora** (a entrada de Protocolos abre em Acompanhamento); telas 8–10 usam "lista de espera"; **tela 25 "Aplicação concluída"** com resumo e link para Concluídos; toda tela do fluxo com o **nº da etapa no topo** ("Etapa 4 de 8") na barra de revisão (não no produto).

## 5. Contrato de estado compartilhado (para dois construtores em um único HTML)
Arquivo único `mockups/fluxo-completo.html`. Um `store.js` central (o construtor **P** o define primeiro e publica no início do arquivo dentro de `/* STORE:START/END */`; o construtor **Q** consome sem alterar).
```
state = { hoje:'2026-09-29', hora:'14:05', animais:{id:{nome,lote,categoria,del,...}},
  pessoas:{id:{nome,funcao,crmv?}}, estoque:{sku:{nome,categoria,lotes:[{lote,validade,saldo}]}},
  protocolos:[{id,tipo:'vacina'|'exame',nome,produto,dose,via,carencia,janela:{regra,de,ate},checklistModelo:[keys],ativo}],
  listaEspera:[{id,protocoloId,animalId,desde,janelaAte,situacao:'na_janela'|'janela_vencida'}],
  agendamentos:[{id,protocoloId,data,hora,responsavelId,estado:'em_montagem'|'agendado'|'aplicado'|'cancelado',
     animais:[{animalId,origem:'janela'|'fora_janela',motivo?,aplicado?:bool}],
     checklist:{veterinario:{estado,pessoaId?},estoque:{estado:'ok'|'pendente'|'desconsiderado',lote?,motivo?},
       data:{estado},compra:{estado,cotacaoId?,pedidoId?},pagamento:{estado,lancamentoId?},contaPagar:{estado,contaId?}},
     criadoEm,criadoPor}],
  concluidos:[...], log:[...], financeiro:{contasPagar:[...],pagamentos:[...]}, cotacoes:[...] }
Store.subscribe(fn) · Store.dispatch(type,payload) · Store.select.*
Actions: cadastrarProtocolo · alterarProtocolo · criarAgendamento({protocoloId,animais}) · incluirForaJanela({agId,animalId,motivo}) ·
  removerAnimal({agId,animalId,motivo}) · checklist({agId,item,estado,dados}) · agendar({agId,data,hora,responsavelId}) ·
  adiar({agId,data,motivo?}) · cancelar({agId,motivo}) · aplicar({agId,animaisAplicados,frasco,dose,via,aplicadorId,custo?,ciente?}) ·
  desfazer({logId}) · vincularPagamento · criarContaPagar · criarCotacao · classificarProduto · configurarRepasse
```
Agenda (**Q**) lê `Store.select.agendaDia(data)` (os agendamentos do dia + seus próprios eventos não sanitários) e usa as actions `aplicar`, `adiar`, `cancelar`. **Nenhum animal em `listaEspera` pode ser renderizado na Agenda.** Log imutável (quem, hora, motivo, frasco) em toda action.

## 6. Cronograma de entrega
1. **Construtor P** (`fluxo-completo.html`): shell fiel, store, dados v2, Protocolos (4 abas + wizard de cadastro + lista de espera + montar cronograma + checklist + aplicar + exceções), Sanidade (leitura), Lançamentos (sem preventivo), stubs navegáveis de Financeiro/Estoque/Cotações.
2. **Construtor Q**: módulo Agenda (Dia a dia + Painel) consumindo o `Store`.
3. **Capturas**: sequência numerada de imagens (≈40) do início ao fim, no mesmo fio (B19), em desktop e telas-chave no mobile.
4. **Pontuação pela banca** (rápida, só Zootecnista, Veterinário, Cooperativa e Pesquisador) sobre o fluxo completo, depois da entrega ao dono.

## 7. Backend/implementação (resumo dos planos A)
- Sem tabela nova de agendamento: `CronogramaSanitario` (+ `CronogramaSanitarioAnimal.status`: `sugerido`=lista de espera → `incluido` → `aplicado`); migrações: `origem`/`motivo` do animal, hora/estoque/cancelamento no cronograma, `cronograma_sanitario_vinculo` (pagamento, conta, cotação, pedido), `Pessoa.crmv`.
- Endpoint único `POST /sanidade/preventivo/agendamentos/{id}/aplicar` para Protocolos e Agenda; `lista-espera`, `agendamentos*`, `materializar`.
- **Antes de qualquer tela** (integridade): Agenda hoje mostra animais da janela e o card `modo_` desde `criado_em` (viola R1/R2); flag `usar_ocorrencia_universal` duplica a pendência antiga; `GET /agenda` escreve; época não dedupe animal já vacinado.
- Agenda: shell + `components/agenda/*`, `/agenda/dia`, `/agenda/painel`, `/agenda/projecao`, `/agenda/resumo`, `?aba=dia|painel`; mount de 9 → 1 request; flag `agenda_v2`; mobile só troca o endpoint.
- Dependência: configuração de repasse hoje só no mockup (backend: `DIAS_SCRATCH=14` fixo, `usa_adesivo_deteccao_cio`).
