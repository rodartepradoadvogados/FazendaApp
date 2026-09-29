# Dados canônicos dos mockups

Os dois mockups (`vacinas-protocolos.html` e `agenda.html`) representam **a mesma fazenda no mesmo dia**. Qualquer número, nome ou data que apareça nos dois deve ser idêntico. Valores de produto são **exemplos**; em produção vêm da bula/Catálogo.

**Fazenda:** Fazenda Estreito Ponte de Pedra · **Hoje:** terça-feira, 29/09/2026 · usuário logado: Jairo Nasser (gestor). Aplicadores cadastrados: Jairo Nasser (gestor), Dr. Paulo Menezes (veterinário, CRMV-MG 12345), Cícero Alves (tratador), Marcos Lima (tratador).

## Rebanho: 151 animais
| Lote | Animais |
|---|---|
| 01 – Alta produção | 24 |
| 02 – Média | 28 |
| 03 – Baixa | 19 |
| Pré-parto | 9 |
| Secas | 14 |
| Recria 1 | 20 |
| Recria 2 | 22 |
| Bezerreiro | 15 |

Raças: Girolando (maioria) e Holandês. Números de animais no formato real (ex.: 2101, 2164, 4124, 4160).

## Catálogo de vacinas e exames (exemplos)
| Item | Dose / via | Esquema | Carência (exemplo) | Custo/dose |
|---|---|---|---|---|
| Aftosa | 2 mL SC | anual; **data definida pela defesa sanitária estadual, editável** (sem campanha fixa embutida) | leite 0 d · carne 0 d | R$ 3,10 |
| Brucelose B19 | 2 mL SC | **dose única**, fêmeas de 3 a 8 meses; **aplicação de veterinário cadastrado** | 0 · 0 | R$ 6,40 |
| Clostridioses | 5 mL SC | dose 1 → **dose 2 30 dias após a dose 1** → reforço anual | 0 · 0 | R$ 1,90 |
| Raiva | 2 mL IM | anual (reforço) | 0 · 0 | R$ 2,80 |
| IBR/BVD | 5 mL IM | semestral | 0 · 0 | R$ 4,20 |
| Leptospirose | 2 mL SC | semestral | 0 · 0 | R$ 2,10 |
| Vermífugo (ivermectina 1%) | 1 mL / 50 kg SC (**dose por peso**; usa peso médio do lote) | a cada 90 d | **leite: não usar em lactação · carne 35 d** | R$ 0,42/mL |
| Exame TB (tuberculina PPD) | intradérmica; **leitura em 72 h** | anual; inconclusivo → reteste em 60 d | — | R$ 9,00/animal |
| Exame brucelose (sorologia) | coleta | anual | — | R$ 14,00/animal |

## Estoque (frascos)
| Produto | Lote do frasco | Validade | Saldo |
|---|---|---|---|
| Aftosa | AF-2609 | **15/10/2026** (vence em 16 dias → aviso) | 60 doses |
| Aftosa | AF-2611 | 30/04/2027 | 200 doses |
| B19 | BR-2604 | 30/06/2027 | 20 doses |
| Clostridioses | CL-2608 | 31/03/2027 | 120 doses |
| Raiva | RA-2607 | 28/02/2027 | 30 doses |
| IBR/BVD | IB-2606 | 15/02/2027 | 40 doses |
| Ivermectina 1% | IV-2605 | 20/09/2026 (**vencido** → exige ciência) e IV-2610 (31/12/2027) | 500 mL / 1000 mL |
| Implante Sincrogest | SG-2607 | 30/11/2027 | 30 un (gargalo) |
| Sincrodiol (benzoato) 50 mL | SD-2606 | 31/10/2027 | 3 frascos |
| Sincroforte (buserelina) 20 mL | SF-2606 | 31/10/2027 | 2 frascos |
| Estron (cloprostenol) 60 mL | ES-2607 | 30/11/2027 | 2 frascos |
| SincroCP (cipionato) 50 mL | CP-2606 | 31/10/2027 | 1 frasco |

## Plano IATF real da fazenda (mesmo em M1 e M2) — dias contados do início (Dia 0)
- **Dia 0:** 1 implante (Sincrogest ou CIDR) + 2 mL Sincrodiol (benzoato) + 2,5 mL Sincroforte (buserelina)
- **Dia 7:** 2 mL Estron (cloprostenol)
- **Dia 9:** retirar implante + 2 mL Estron + 1 mL SincroCP (cipionato)
- **Dia 11:** inseminação
Nomes de tela: "Dia 0", "Dia 7", "Dia 9", "Dia 11" (sem "1º/7º/9º/11º dia").

## Protocolos em andamento
1. **IATF Recria 2** — 12 novilhas, Dia 0 em 20/09 → **hoje é o Dia 9** (Estron + SincroCP + retirar implante), Dia 11 = 01/10.
2. **IATF Lote 02 – Média** — 8 vacas, Dia 0 em 27/09 → Dia 7 = 04/10.
3. **Tratamento de mastite clínica** — 3 vacas (Lote 01), ceftiofur, 5 dias, iniciado 26/09 (dia 4 de 5 hoje); **carência leite 4 d após o último dia · carne 4 d**.
4. **Protocolo próprio "Adaptação pré-parto"** — Pré-parto, 9 vacas, 7 dias.
5. **Indução de lactação** — 2 novilhas, em andamento.

## Calendário de vacinas e exames (referência para M1 e para os itens sanitários de M2)
| Estado | Item | Para quem | Data prevista |
|---|---|---|---|
| **Atrasada** | Raiva — reforço | 6 animais, Lote 03 – Baixa | 27/09 (há 2 d) |
| **Atrasada** | Clostridioses — dose 2 | 22 animais, Recria 2 | 25/09 (há 4 d) |
| **Atrasada** | Exame TB — reteste (inconclusivo em 31/03) | 3 animais, Lote 02 – Média | 21/09 (há 8 d) |
| Hoje | Vermifugação (ivermectina) | 20 novilhas, Recria 1 | 29/09 |
| Esta semana | IBR/BVD | 14 vacas, Secas | 01/10 |
| Esta semana | B19 | 6 bezerras elegíveis (3–8 m), Bezerreiro | 02/10 |
| Próximas | Aftosa (data estadual, editável) | 136 animais | 05/11 |
| Próximas | Leptospirose | 151 animais | 15/11 |

**Cobertura:** 120 de 151 animais com **todas** as vacinas aplicáveis em dia = **79%** (31 animais com alguma pendência atrasada). Por vacina: Aftosa 100%, B19 88%, Clostridioses 82%, Raiva 96%, IBR/BVD 99%, Leptospirose 97%.
**Faixa do Calendário (M1):** Atrasadas **3** · Esta semana **3** (Vermifugação hoje + IBR/BVD + B19) · Cobertura **79%**.
**Agenda (M2):** Atrasadas **4** (as 3 sanitárias acima + 1 pesagem) · Hoje **15** tarefas de campo · Próximos 7 dias conforme a lista; a Agenda contém as tarefas sanitárias acima com os **mesmos** nomes, contagens e datas.

## Financeiro (Gestão)
1 conta vence hoje: **Fornecedor Agro Vet — R$ 12.480,00**. Mais 2 itens de gestão (compra de implantes; documento fiscal pendente).

## Regras da fazenda que não mudam nos mockups
- Retorno ao cio (Scratch): **14 dias** após a inseminação (parâmetro da fazenda), rótulo "Checar retorno ao cio (Scratch, 14 dias)".
- PEV: 45 dias; rótulo "Fim do período de espera voluntário (PEV)".
- BST: aptas com **DEL ≥ 60**.
- Gestação por raça: Holandês 280 d / Girolando 287 d / Gir-Zebu 295 d.
