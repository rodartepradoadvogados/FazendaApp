# Fluxo completo — R7 (banca final) e pendências

| Persona | R5 | R6 | R7 | P0 | P1 |
|---|---|---|---|---|---|
| Zootecnista | 69% | 81% | 75% | 0 | 1 |
| Veterinário | 77% | 83% | 94% | 0 | 1 |
| Peão | 68% | 71% | ~90% | 0 | 0 |
| Produtor | 79% | 83% | 93% | 0 | 0 |
| Cooperativa | 58% | 84% | 97% | 0 | 0 |
| Pesquisador UX | 62% | 76% | 82% | 0 | 0 |
| **Média** | 69,2% | 79,7% | **88,5%** | 0 | 2 |

Critério (média ≥ 90%, nenhuma < 80%, zero P0): **não atingido** na R7 (zootecnista 75%).
Após a R7 foi feita uma rodada curta de correção (commit f30129f5): cobertura B19, "NaN mL", vendido fora da lista,
macho bloqueado no B19, comprovante do TB só bloqueia reagente, reforço, log com aplicador, motivo ao editar protocolo,
"2 checagens · 20 vacas". Testes fio/extra/r5/r6/r7 passam. **Não reavaliada pela banca.**

## Pendências (módulo Agenda e outros)
- Agenda: "janela vencida" na gaveta Lista de espera do Painel; "R$ 14,7 mil" quebrando linha; prévia do repasse 13/10 no Painel padrão;
  unificar toast (#toasts × .ag-toast) e cores de estado; texto 14 px em botões/chips no mobile; nomes de lote cortados; "+" sem rótulo em Nova tarefa; título "Agenda".
- Cobertura/carteira: fora-da-janela com histórico; Painel "Leptospirose 151 animais" × 5 na lista de Aplicar; coluna DEL vazia.
- Estados: "Atrasada" com 3 sentidos; passo 3 do assistente com 19 controles; pills de tipo (5); selos 4 itens × contador x/7.
- Clínico: Sanidade › Rastreabilidade é stub; exame concluído com selo "Aplicado".
- Decisões do dono em aberto: "Em sanidade, curativo" = Preventivo?; Scratch configurável (18–24 d)?; "Montar cronograma" mantido por vocabulário.
