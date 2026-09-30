# Síntese e roteiro — Vacinas e exames · Protocolos · Agenda

> Resultado final da auditoria. Ordem de leitura da pasta: `01-critica-consolidada.md` (o que está errado hoje) → `02-proposta.md` (o que propomos) → `03-gauntlet-loop.md` (como validamos) → `04-gauntlet-rodadas.md` (o que a banca achou, rodada a rodada) → **este arquivo** (o que decidimos e como implementar) → `mockups/` (as páginas clicáveis).

## 1. Onde abrir os mockups

| Arquivo | O que é |
|---|---|
| `mockups/vacinas-protocolos.html` | **Sanidade › Vacinas e exames** (Calendário, Cobertura, Histórico, Cadastro de vacinas) + **Protocolos** (Em andamento, Novo protocolo, Modelos). Rotas por hash, ex.: `#/sanidade/vacinas`, `#/protocolos`. |
| `mockups/agenda.html` | **Agenda** (Hoje · Semana · Mês; agrupar por tarefa/lote/categoria; gavetas). |
| `mockups/DADOS-CANONICOS.md` | A "fazenda de mentira" que os dois usam (151 animais, lotes, protocolos, estoque, regras de estado). |

Os dois arquivos são **HTML único** (abrem no navegador, sem servidor) e **estão ligados por links reais** (Agenda › "Iniciar protocolo com 11 vacas" abre o Novo protocolo já preenchido). No topo de cada um há uma barra de revisão (tema, "Simular fazenda nova", "Simular erro de rede", cenários, "Reiniciar dados") — ela **não faz parte do produto**.

## 2. Resultado da validação (gauntlet-loop, 4 rodadas, 6 personas)

| | R1 | R2 | R3 | R4 |
|---|---|---|---|---|
| Vacinas e exames + Protocolos | 70,1% | 86,0% | 88,2% | **93,7%** |
| Agenda | 74,1% | 85,6% | 85,7% | **93,1%** |

Critério de saída (média ≥ 90%, nenhuma persona < 80%, zero P0): **atendido na R4**. Notas da Agenda por persona na R4: Zootecnista 100, Veterinário 87,5, Peão 91,7, Produtor 100, Cooperativa 87,5, Pesquisador 92. Vacinas e Protocolos: 93,75 / 93,75 / 100 / 90 / 91,7 / 93.

O que a banca mudou de verdade no desenho (por que valeu a pena iterar):
1. **Rastreabilidade virou requisito de primeira classe:** log imutável (quem, quando, o quê, motivo, frasco, dose, via), **Desfazer nunca apaga** (cria "Estornada"), Corrigir marca a original como "Corrigida".
2. **Cobertura vacinal com um único modelo de estado** por animal × item (`Em dia · Prevista · Atrasada · Sem registro · Não se aplica · Reagente · Inconclusivo`); todo número da tela sai da mesma tabela.
3. **Exame ≠ aplicação:** leitura de TB em 72 h, reagente identificado por animal, banner persistente com notificação registrada, comprovante bloqueado.
4. **Coerência entre telas:** mesma gaveta "Registrar" e mesmo toast nas duas casas; vocabulário único; dias de protocolo contados do **Dia 0**.
5. **Campo primeiro:** toast agregado, "Adiar" em 2 toques, primeira dobra com o que fazer hoje, alvos ≥ 44 px, atualização otimista (a lista não apaga).

## 3. Decisões de produto tomadas (revisáveis)

1. **O Preventivo sai da Central de Protocolos.** Vacinas e exames (recorrente, por grupo) e Protocolos (sequência, por animal/lote) são módulos irmãos.
2. **Uma só porta de escrita** para sanidade: "Registrar aplicação/exame" (drawer). As 5 portas atuais viram atalhos para ele.
3. **Um só verbo de execução na Agenda: "Feito"** (com "Adiar" e "Não vou fazer"). "Decidir" só no trilho *Alertas e decisões*.
4. **Três trilhos na Agenda:** Tarefas de campo (as únicas que contam no "Dia fechado") · Alertas e decisões · Gestão.
5. **Dia 0** como origem dos protocolos (Dia 0/7/9/11 no IATF). O glossário do `02-proposta.md` foi atualizado por essa decisão.
6. **Aftosa sem campanha fixa** embutida: a data vem da defesa sanitária estadual e é editável.
7. **Retorno ao cio (Scratch) = 14 dias** é regra do dono e fica como parâmetro da fazenda (ver pergunta em aberto).
8. **Adiar simples não exige motivo** (log "sem motivo informado"); motivo obrigatório em Não vou fazer, Pular de programa oficial e Excluir; "Adiar tudo" pede um motivo único e **nunca move tarefas críticas** (IATF, leitura de exame, parto, tratamento em curso).

## 4. Perguntas em aberto para o dono

1. **Scratch aos 14 dias:** manter como está (regra validada) ou tornar o intervalo configurável com sugestão de 18–24 d? O veterinário da banca apontou que o retorno ao cio típico é mais tardio.
2. **Regime de aftosa da sua UF:** o produto deve trazer alguma data-padrão ou só o campo editável?
3. **Notificação de exame positivo (TB/brucelose):** basta o registro do aviso, ou a fazenda quer o fluxo completo (isolamento, GTA, prazo de destino)? Hoje está fora de escopo.
4. **Multi-fazenda (cooperativa):** entra num ciclo futuro?

## 5. Roteiro de implementação (do menor risco ao maior)

Cada item cita o achado da crítica (`01`) e a tela dos mockups. **Antes de qualquer redesenho, a Fase 0** (integridade), porque erros de dado pesam mais que qualquer layout.

### Fase 0 — Integridade (sem mudança visual)
1. **Desfazer com estorno completo** de `protocolo_sanitario_`, `aplic_agendada_`, `vacina_pre_parto_` (estoque + aplicação) e **baixa idempotente e transacional** (`agenda.py`, `marcar_realizado`).
2. **Escrita evento+regra em uma transação** (`FormCalendarioSanitario`); remover `.catch(() => {})` na baixa da Agenda (`FormPreventivoAplicacao`).
3. **Escopo por fazenda+usuário** no cache offline (`lib/offline.ts`) e no rascunho do wizard (`WizardProtocolo`); limpar no logout.
4. **Fuso local** (America/Sao_Paulo) no front (`today()`) e no back (`date.today()`, `utcnow`); corrigir o default de parâmetro `data: date = date.today()`.
5. **Falha de rede ≠ logout** (`AuthShell` + `lib/api.ts`); `GET /agenda` sem escrita no banco.
6. **Protocolo Customizado exige Tipo** (senão some da Central).

### Fase 1 — Estrutura sem risco (o que o usuário nota primeiro)
7. **URLs reais** em Sanidade/Protocolos/Agenda (aba, visão, filtro, drawer) e Sanidade abrindo em Vacinas e exames.
8. **Glossário e textos** (tabela do `02-proposta.md` §2), remover "Fase 2"/`usa_cronograma`/"gatilho"; trocar `window.confirm/prompt/alert` por confirmação inline.
9. **Atrasadas** visíveis no Calendário; resgatar o KPI "Vencidas"; remover `OcorrenciasView` e a aba oculta.
10. **Agenda: Hoje primeiro**, 3 números, barra de 4 controles, "Feito" único, atualização otimista (sem skeleton total), `resolucao` por evento (`realizar|navegar|informativo`).
11. **Acessibilidade mínima:** `<tr>` com `role`/teclado, drawers com `role=dialog`+Esc+trap, `aria-live` nos toasts, `label htmlFor`, alvos ≥ 44 px.

### Fase 2 — Registrar aplicação unificado e auditoria
12. **Drawer "Registrar aplicação/exame"** (código do mockup como referência): frasco/lote/validade, dose por peso, via fixa por produto, aplicador, carência, resumo antes de confirmar, Desfazer com estorno sem apagar.
13. **Log de auditoria imutável** + Histórico unificado (Aplicações + Histórico + Exames) com Aplicador/Registrado por/lote do frasco e filtros de exceção/recall; exportação respeitando filtros.
14. **Exame** com fluxo próprio (leitura 72 h, reagente por animal, banner de notificação, retestes).
15. Cadastro **"Vacinas do calendário"** (evento+regra fundidos; wizard de 3 passos; multidose; carência do Catálogo).

### Fase 3 — Funcionalidade nova
16. **Cobertura vacinal** e **carteira do animal** (modelo de estado único) + carência de leite/carne.
17. **Modelos de protocolo com versão** (snapshot por lançamento) e **Novo protocolo** com elegibilidade e conferência de consequências.
18. Folha de campo com brincos/CRMV; visão anual; lembretes; estoque previsto × necessário.

### Fase 4 — Reestruturação
19. **Central → Protocolos** (Em andamento · Novo · Modelos); retirar o Preventivo dela; redirecionar o cadastro duplicado de Configurações.
20. **Quebrar o monólito da Agenda** (`app/agenda/page.tsx`, 2.816 linhas) em `components/agenda/*`; extrair `BotaoRealizado`, `PainelConfirmarBaixa`, `BotaoAgendar`, `ExportarAgendaBotoes` do render; endpoints leves `/agenda/resumo` e `/agenda/eventos`.

## 6. Pendências registradas (não bloqueiam)
Ver lista no final de `04-gauntlet-rodadas.md` (baixa de protocolo no Histórico geral, recall com lista de brincos, folha de campo com brincos/CRMV, log de edição antes→depois, gaveta da Mastite unificada, sidebar 10 → 12 px, e os fora de escopo declarados).

## 7. Limitações dos mockups
- Dados de exemplo (a fazenda é fictícia, os valores de produto vêm do `DADOS-CANONICOS.md`); dois arquivos estáticos **não compartilham estado** entre si.
- Impressão/PDF e exportações são simulações (o CSV é real).
- Navegação para telas que não fazem parte do escopo (Dieta, Estoque etc.) mostra aviso.
- A fonte Archivo depende de internet; offline cai para a fonte do sistema.
- O mockup não passa por Next.js/React: serve de **referência visual e comportamental**, não de código a copiar.
