# Fluxo completo — avaliação da banca (R5) e lista única de correções

## Resultado da 1ª avaliação do `fluxo-completo.html`
| Persona | Conformidade | P0 | P1 | Destaque |
|---|---|---|---|---|
| Zootecnista | 69% | 0 | 4 | códigos crus na tela; BST 18×19; DG de 16/10 não projetado; animal de fora sem histórico |
| Veterinário | 77% | 0 | 9 | comprovante de Aftosa sem lote por animal; frasco que vence antes do uso sem aviso; tratador aplica B19/TB só com "ciência"; vendido na lista de espera |
| Peão | ~68% | 0 | 2 | toque duplo marca 2 tarefas; adiar tarefa crítica exige digitar; textos de 12–13 px |
| Produtor | 79% | 0 | 3 | Agenda sem faixa de "sem conexão"; Painel com 18 cards e títulos cortados; custo/conta a pagar só no B19 |
| Cooperativa | 58% | **1** | 12 | "Desconsiderar estoque" ainda baixa o lote (lote falso no registro); ciência não gravada; trilha incompleta |
| Pesquisador | 64% | **2** | 4 | checklist diverge entre Acompanhamento e Agenda; telas 104/105 do roteiro quebradas |
| **Média** | **69,2%** | 3 | 34 | meta: ≥ 90% cada, nenhuma < 80%, zero P0 |

## Decisões que resolvem conflitos entre personas
1. **B19 e exame TB só por veterinário habilitado (CRMV).** Não é mais "aplica com ciência": o botão Aplicar exige aplicador veterinário; se o tratador está em campo, a saída é **"Pedir ao veterinário"** (gera pendência), nunca gravar como se fosse válido. "Exige veterinário" fica **travado** para B19/TB no cadastro. (Nada mais bloqueia: estoque, validade e carência seguem só avisando.)
2. **"Desconsiderar estoque" não baixa nada e não grava lote do sistema.** Registra "frasco fornecido pelo veterinário" (lote e validade digitados, opcionais) e marca no log.
3. **Adiar simples** continua em 2 toques, sem obrigar texto: motivo em **chips de 1 toque** (opcional) e "amanhã" pré-selecionado; tarefa crítica exige um chip (não digitação). Remover animal do agendamento e "Não vou fazer" exigem chip.
4. **Vocabulário do objeto:** **Agendamento** é o objeto; "cronograma" fica só como nome da visão/assistente ("Montar cronograma"); botão de linha na aba Aplicar = **Criar agendamento**; **Desconsiderar** é o único verbo para "não se aplica" no checklist; "janela vencida" → **Atrasada há N dias** (janela ainda aberta), "Na janela" (dentro do prazo).
5. **Datas em dd/mm/aaaa** e decimais com vírgula.
6. **Roteiro renumerado 1…N** (id estável interno), sem telas duplicadas.

## Correções — Construtor P (Store, Protocolos, Sanidade, Lançamentos, apoio, shell)
- **P0** `desconsiderarEstoque` não baixa estoque nem grava lote falso (decisão 2); CSV/concluído/comprovante mostram "fornecido pelo veterinário".
- **P0** roteiro: telas 104/105 (ids `ag-b19`/`ag-verm` → ids existentes), ação inexistente `ajustarEstoque` (tela 15) → criar a action ou trocar o setup; remover duplicatas; renumerar.
- **P0** checklist é fonte única no Store: `Store.select.checklistResumo(agId)` (itens, x/y, selos) usada por Acompanhamento, gaveta e Agenda (Q consome). Selos e contador coerentes (ex.: Vermifugação "Conta ok" em ambos).
- Aplicar com itens pendentes **grava a ciência** (itens pendentes, quem, motivo) em `log`, `excecoes` e CSV.
- Desfazer/estornar: **motivo obrigatório em chips** (nada de texto automático); permitir estornar um concluído mais antigo por **"Estornar" em Concluídos** com motivo (perfil administrador, com caminho visível na UI).
- Cancelar/"pular esta rodada": perguntar o que fazer com **conta a pagar** e **pagamento vinculado** (manter/cancelar/desvincular, cada um logado); "pular rodada" oferece **"Não se aplica"** em vez de devolver tudo à lista de espera.
- Aplicação retroativa: motivo obrigatório + coluna **Retroativo** (log, Concluídos, CSV).
- Log da montagem lista **brincos e motivos**; editar protocolo grava **antes→depois** com o rótulo certo (não "Reativou").
- **Exportar a trilha** (log) + CSV com: agendamento (id legível), veterinário/CRMV, validade do frasco, vínculos financeiros, canal (Agenda/Acompanhamento), aplicador, retroativo, exceções; custo **uma vez por registro** (não repetido por animal).
- Nova action **`tarefaEvento`** ({tipo,id,acao:'feito'|'adiar'|'naoVou'|'excluir',motivo?,...}) para as tarefas **não sanitárias da Agenda** gravarem no `log` e **persistirem** (Q chama). `Store.select.nomeLote/nomeProduto/nomeAgendamento` para eliminar ids/códigos crus.
- **Clínico:** comprovante da Aftosa com **lote e validade por animal (ou por grupo de animais)**; checklist de estoque avisa quando o **frasco vence antes da data de uso** (ex.: AF-2609 vence 15/10, uso 05/11) e sugere AF-2611; só **veterinário habilitado** aplica B19/TB (decisão 1); "exige veterinário" travado para B19/TB; regra do B19 exige **fêmea** (macho como "fora da janela" mostra aviso de sexo); animal **vendido/baixado** sai da lista de espera; reteste de TB = **60 dias** após o inconclusivo (usar inconclusivo em **23/07/2026** → reteste 21/09); comprovante de exame com data da inoculação, data da leitura e nº do laudo; **banner de reagente** persiste depois da notificação e aparece na Agenda; reagente sai do agendamento de Aftosa; leitura fora da janela 72–96 h sinalizada; vermífugo/tuberculina com tipo correto (Antiparasitário/Exame, não "Vacina"); Aftosa "data definida pela defesa sanitária estadual (editável)"; **dose por peso individual** quando houver peso do animal (senão média do lote, marcada como estimativa).
- **Animal fora da janela:** a gaveta mostra o **histórico de doses do animal** e avisa "já tem dose em 01/04/2026"; a **faixa da janela** do passo 2 não conta animais de fora.
- Wizard de cadastro: validar faixa etária invertida e sexo; custo previsto/conta a pagar/link para Contas a pagar em **todos** os protocolos (Conferir e resumo pós-aplicação); remover "Custo registrado em Sanidade".
- Vocabulário e rótulos (decisão 4); **"Criar agendamento"** nos botões; "Atrasada há N dias"; "1 animal"; "Exame TB — reteste" sem repetição; ids/códigos (`ag-3`, `ct-136`, `cp-3`, `pg-1`) fora da tela; três verbos de "não se aplica" → **Desconsiderar**; passo 3 do assistente com menos controles (agrupar ações secundárias); banner "Lista de espera ≠ Agenda" compacto (uma linha, dispensável); estados com a mesma cor/gênero (ex.: "Na janela", "Agendado/a"); contadores coerentes (37 = "na lista de espera" em todos os lugares; "Agendados" iguais em Acompanhamento e Sanidade; selos ×/7).
- Acessibilidade/UX: foco volta ao botão que abriu a gaveta; `inert` no fundo das gavetas; **gaveta Aplicar aberta pela Agenda entra na URL e sobrevive ao F5** (`?aplicar=<id>&de=agenda`); sidebar no padrão do app real (10 px / 28 px); alvos ≥ 44 px; textos de apoio ≥ 14 px no mobile.

## Correções — Construtor Q (módulo Agenda)
- **P0** ler o **checklist do Store** (`checklistResumo`) — selos e contadores idênticos aos de Protocolos.
- **P0** ids de storyboard: usar ids do Store; entregar `agenda-storyboard.json` sem duplicatas.
- Tarefas não sanitárias (BST, mastite, pesagem etc.): "Feito/Aplicar/Adiar/Não vou fazer" via **`Store.dispatch('tarefaEvento', …)`** (persistem, entram no log/CSV); nada só em memória.
- **Sem ids/códigos crus** na tela (`r1`, `se`, `bz`, `ver:`, `ibr:`, `b19:`, `cp-3`): usar `Store.select.nomeLote/nomeProduto`.
- **Painel:** reduzir de **18 para ~12 cards** agrupando (ex.: Reprodução 4 · Sanidade 4 · Estoque e gestão 4), **títulos sem truncar** (2 linhas ou rótulo curto); manter tudo que o dono pediu (candidatas IATF, IATF atual, última IATF, BST aptos/excluídos/incluir, pendências, alertas de estoque, concluídos no período, projeção de repasse/BST/IATF/vacinas/exames) — os itens extras entram em **detalhe de card**, não em card próprio.
- **BST**: uma única contagem (18 × 19 → calcular de um só lugar). **DG de 16/10** (5 vacas da última IATF) projetado na Agenda, Mês, mapa de calor e programação projetada.
- **Faixa persistente de "sem conexão"** na Agenda (dados de HH:MM, botão Tentar de novo) e tela de erro própria no roteiro; "Atualizado" coerente com o estado.
- **Toque duplo:** a linha mantém o espaço ≥ 250 ms e bloqueia toque na linha seguinte; Feito e ⋯ afastados ≥ 8 px.
- **Adiar/Não vou fazer** com **chips de motivo** (sem digitar), "amanhã" pré-selecionado; data em dd/mm/aaaa (seletor próprio).
- Mobile: texto principal ≥ 16 px, apoio ≥ 14 px, botões ≥ 44 px, chips de resumo ≥ 44 px, títulos em até 3 linhas (sem "…"), toast curto, mapa de calor sem corte (rolagem horizontal visível com indicador) e chip **"Lista de espera"** visível também no mobile; "Fechar o dia" sem corte.
- Dia a dia: **"o que vem"** nomeado (próximas 2–3 linhas de amanhã, incluindo "IBR/BVD 01/10 · veterinário pendente"); a linha "37 em lista de espera" vira **atalho para Protocolos › Aplicar** (não é contagem de trabalho).
- Selos de checklist ×/7 coerentes com o Acompanhamento.
- Foco volta ao botão de origem; `inert` no fundo das gavetas; heatmap e links ≥ 44 px de área de toque.
- Abrir o drawer **Aplicar** pela Agenda grava `?aplicar=<id>&de=agenda` (P trata a URL).
- Decimais com vírgula.

## Critério de saída
Média ≥ 90% e nenhuma persona < 80% e **zero P0** (mesmo critério das rodadas anteriores), com até 3 rodadas de correção.
