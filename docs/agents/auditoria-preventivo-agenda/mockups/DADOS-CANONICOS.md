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

**Cobertura:** **119 de 151** animais com **todas** as vacinas aplicáveis em dia = **79%** (32 animais com alguma pendência atrasada: 22 Clostridioses + 6 Raiva + 3 reteste TB + 1 IBR/BVD da 4101 Mimosa). *Regra:* "Sem registro" com aplicação **prevista no futuro** aparece como "Prevista" e não conta como atrasada. Por vacina: Aftosa 100%, B19 88%, Clostridioses 82%, Raiva 96%, IBR/BVD 99%, Leptospirose 97%.
**Faixa do Calendário (M1):** Atrasadas **3** · Esta semana **3** (Vermifugação hoje + IBR/BVD + B19) · Cobertura **79%**.
**Agenda (M2):** Atrasadas **4** (as 3 sanitárias acima + 1 pesagem) · Hoje **15** tarefas de campo · Próximos 7 dias conforme a lista; a Agenda contém as tarefas sanitárias acima com os **mesmos** nomes, contagens e datas.

## Financeiro (Gestão)
1 conta vence hoje: **Fornecedor Agro Vet — R$ 12.480,00**. Mais 2 itens de gestão (compra de implantes; documento fiscal pendente).

## Regras da fazenda que não mudam nos mockups
- Retorno ao cio (Scratch): **14 dias** após a inseminação (parâmetro da fazenda), rótulo "Checar retorno ao cio (Scratch, 14 dias)".
- PEV: 45 dias; rótulo "Fim do período de espera voluntário (PEV)".
- BST: aptas com **DEL ≥ 60**.
- Gestação por raça: Holandês 280 d / Girolando 287 d / Gir-Zebu 295 d.

---

## Extensão (rodada 3) — animais, doses e dias nomeados (fonte única; nada pode divergir entre M1 e M2)

**Numeração de brincos por lote:** Lote 01 → 41xx · Lote 02 → 42xx · Lote 03 → 21xx · Pré-parto → 43xx · Secas → 44xx · Recria 1 → 51xx · Recria 2 → 52xx · Bezerreiro → 61xx.

**Contagem de dias dos protocolos:** *todos* os modelos contam **Dia 0 = início** e mostram "Dia N".
| Protocolo | Início (Dia 0) | Hoje (29/09) | Última etapa |
|---|---|---|---|
| IATF Recria 2 (12 novilhas: 5201–5212) | 20/09 | **Dia 9** | Dia 11 = 01/10 |
| IATF Lote 02 – Média (8 vacas: 4210–4214, 4216–4218) | 27/09 | Dia 2 (próxima etapa: Dia 7 = 04/10) | Dia 11 = 08/10 |
| Mastite clínica — ceftiofur **5 mL IM por vaca por dia** (vacas 4105, 4112, 4131; Lote 01) | 26/09 | **Dia 3** (15 mL hoje no total; frasco CF-5510, saldo 200 mL) | Dia 4 = 30/09; carência leite/carne 4 d após = 04/10 |
| Adaptação pré-parto (9 vacas, Pré-parto: 4301–4309) | 25/09 | **Dia 4** | Dia 6 = 01/10 |
| Indução de lactação (2 novilhas: 5108, 5117) | 22/09 | **Dia 7** | Dia 20 = 12/10 |
Portanto a Agenda de hoje tem **4 tarefas de protocolo**: IATF Recria 2 Dia 9; Mastite Dia 3; Adaptação pré-parto Dia 4; Indução Dia 7. (O IATF Lote 02 não tem etapa hoje.)

**Vermifugação (ivermectina 1%)** Recria 1: 20 novilhas, **peso médio 230 kg → 4,6 mL por animal → 92 mL** no total, frasco IV-2610 (o IV-2605 está vencido e **nunca vem pré-selecionado**).

**Aftosa (05/11):** 136 doses = 60 do frasco AF-2609 (vence 15/10 — aviso) + 76 do AF-2611; o resumo divide entre os dois frascos e **nunca mostra estoque negativo**.

**Atrasadas sanitárias (animais):** Raiva reforço → 2101, 2117, 2133, 2140, 2152, 2166 (Lote 03 – Baixa). Clostridioses dose 2 → 5201–5222 (Recria 2). Reteste TB → **4201 Serena, 4207 Estrela, 4215 Bonita** (Lote 02 – Média).
**Esta semana:** IBR/BVD → 14 vacas das Secas (4401–4414). B19 → 6 bezerras (6104–6109), todas entre 3 e 8 meses.
**BST:** aptas com DEL ≥ 60; **4160 (DEL 40) e 4124 (DEL 48) excluídas**.
**Candidatas IATF (gaveta Reprodução):** 11 vacas do Lote 02 – Média (4219–4229). "Iniciar protocolo" leva ao **Novo protocolo** com essas vacas e o lote pré-selecionados.

**Carteira do animal (regras):** vacina **sem nenhuma dose registrada = "Sem registro" (conta como pendente)**, nunca "Em dia"; B19 fora da faixa de idade = "Não se aplica"; data prevista passada = "Atrasada". Ex.: 4101 Mimosa: IBR/BVD semestral, última 20/03 → previsto 20/09 → **Atrasada**; Clostridioses com reforço anual.
**Cobertura:** os percentuais são **calculados pelo mesmo conjunto de dados** (não digitados); animal com qualquer pendência atrasada ou "sem registro" não conta como em dia.

**Exame TB com resultado positivo (fluxo obrigatório nos dois mockups):** o reagente (ex.: 4207 Estrela) é gravado **por animal** com nº do laudo opcional; aparece **no Histórico, no CSV e na carteira** ("Reagente — notificar serviço veterinário oficial"); a cobertura sinaliza o animal; o comprovante "animal em dia" fica **bloqueado** para ele; o aviso é um **banner persistente** com checkbox "Notificação ao serviço veterinário oficial registrada" (com quem/quando), não um toast. O exame de TB exige **aplicador médico veterinário habilitado** (aviso igual ao da B19) e informa produto/frasco/validade da tuberculina. Leitura só a partir de 72 h após a inoculação (ou justificativa registrada).

**Relógio fixo dos mockups:** terça 29/09/2026, **14:05** (mesmo em M1 e M2). **Formatos:** "há 8 dias" (por extenso), "Dia 4", dinheiro `R$ 1.234,56`, volumes `92 mL`, datas `dd/mm/aaaa`; CSV com 2 casas decimais.
**Sidebar:** item **"Protocolos"** nos dois; sub-marca sob o logo: **Fazenda Estreito Ponte de Pedra**; usuário Jairo Nasser no rodapé. Corpo de texto 16 px (desktop e mobile); h1 28 px.
**Ligação entre mockups:** os itens "Agenda" (no M1) e "Protocolos" / "Sanidade › Vacinas e exames" (no M2) são **links reais** entre `agenda.html` e `vacinas-protocolos.html` (mesma pasta), com as rotas corretas por hash. "Abrir origem"/"Iniciar protocolo" usam esses links.
