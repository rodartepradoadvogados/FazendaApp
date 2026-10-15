# Lançamento financeiro do CowData — crítica, auditoria e o que o mockup decidiu

**Data:** 15/10/2026 · **Alvo:** `/lancamentos?ir=financeiro_despesa` e `?ir=financeiro_receita`
(`frontend/components/FormFinanceiro.tsx` e irmãos) · **Ambiente:** demonstração local com a fazenda
fictícia "Vale Verde" (`docs/tutoriais-video/ambiente-demo/rebuild.sh --front`), build de produção, Chromium.

> Método (Impeccable `critique` + `audit`): três avaliadores isolados em paralelo — **A** revisão de design,
> **B** detector + evidência de navegador, **C** auditoria técnica — sem ver o resultado um do outro.
> Nada foi alterado no código do produto: o resultado desta etapa é o mockup em
> `docs/mockups/lancamento-financeiro/` e este relatório.

## 1. Placar

| Avaliação | Nota | Faixa |
|---|---|---|
| Crítica de design (Nielsen, 10 heurísticas) | **20/40** | aceitável, abaixo do típico |
| Auditoria técnica (a11y, performance, responsivo, tokens, integridade) | **10/20** | aceitável, trabalho significativo |
| Detector estático (`impeccable detect`) | 0 achados no formulário | **não enxerga** contraste, fonte nem rótulos (só 1 callout fora do fluxo) |

Heurísticas mais baixas: **Consistência 1/4**, **Estética e minimalismo 1/4**, **Correspondência com o mundo real 1/4**.

## 2. Diagnóstico em uma frase

O conteúdo é da fazenda (Funrural/Senar, vale de funcionário, compra de sêmen, centro "Pecuária Leiteira"),
mas a **forma é a de um formulário de ERP** e **fala outro idioma** que as telas de controle: o dono lança
"sal mineral" e o Painel mostra "Comida", e nada liga as duas pontas.

## 3. Problemas prioritários (consolidados)

| # | Sev. | Problema | Evidência |
|---|---|---|---|
| 1 | P1 | **26 campos quando 2 bastam**, sem inferir nada. ~37 controles na tela vazia; só produto e valor bloqueiam o salvar | A (DOM + `LC-2026-00020` gravado só com produto e valor) |
| 2 | P1 | **Modelo mental partido**: Classificação × Natureza × Conta gerencial × Centro de custo; "Classificar" no controle significa outra coisa; o rótulo "DRE" da barra fixa só mostra o centro de custo | A §5 |
| 3 | P1 | **Salvar não fala**: linha verde de ~12px, aviso de estoque na cor de sucesso, erro longe do campo, formulário zera até o fornecedor | A §4 |
| 4 | P1 | **Contraste**: `--dourado-light` como texto no claro mede **1,4–2,2:1** (valor líquido, total, "Produto/serviço N", links); erro `--red` no escuro 2,9:1; anel de foco 1,6–1,9:1 | B e C (matriz 3 temas × 3 paletas) |
| 5 | P1 | **Rótulos órfãos** (bug do `Campo`): 5 de 15 controles sem nome acessível; sem `aria-live`/`role=alert`/`aria-invalid`; 5 overlays à mão sem foco nem Esc; seletor de produto/serviço impossível por teclado | C e B |
| 6 | P1 | **App de campo**: "Salvar lançamento" fica atrás da barra inferior (o clique cai em "Lançar") | C (`elementFromPoint`) |
| 7 | P2 | Forma foge do Institucional: 4 painéis pastel, sombra na barra fixa, ouro nos seletores em vez de no Salvar, foto de fundo | A e C |
| 8 | P2 | Rodapé "sticky" não gruda (o `.card` vira o rolo); duas colunas com rolagem própria; offset real 385px em vez de 220px | C |
| 9 | P2 | Rascunho apagado ao montar, sem escopo de usuário/fazenda e sobrevive ao logout; "hoje" em UTC (depois das 21h grava dia seguinte) | C |
| 10 | P2 | 22 de 29 botões <44px; inputs 13,6px (zoom no iOS); 60% dos caracteres <12px | B |
| 11 | P2 | Cada tecla re-renderiza 82 `useState`; 2 blob URLs novas por tecla por imagem, nunca revogadas (pior evento 416ms com foto grande) | C |
| 12 | P3 | `/lancamentos?ir=…` recarrega o documento várias vezes (2–36 cargas), hipótese: corrida entre o efeito de `?ir=` e `useSubNavRegister` | B (causa-raiz **não verificada**) |

## 4. Lançamento × Controle (onde as duas telas divergem)

| Dimensão | Lançamento (hoje) | Controle | Decisão do mockup |
|---|---|---|---|
| Nome | "Contas a pagar (despesa)" é formulário; no Controle é lista | lista | abas **Despesa → conta a pagar** / **Receita → conta a receber** |
| Situação | checkbox "Já foi pago" + "Entregue?" | Vencida / Vence em N dias / Em aberto / Paga | selos **idênticos** aos do Controle, e o efeito diz em qual faixa a conta vai aparecer |
| Datas | emissão, vencimento, "prevista", "do pedido" | Competência × Caixa ("mês do gasto"/"dia do pagamento") | emissão + vencimento + **mês do gasto** explícito |
| Destino | "Conta gerencial — só o galho mais baixo" (3.01.01.03) | "Comida / Gente / Outros custeios" | **"Vai para Comida · Sal mineral e suplementos 3.01.01.03"** |
| Natureza | dropdown com tooltip | "fora da DRE tem motivo" | texto do **efeito** ("Sai do resultado; só a depreciação entra") |
| Cor | quatro painéis decorativos | cor só com semântica | cor só semântica; ouro só confirma |
| Linguagem | "Financeiro já grava de verdade…" | voz do dono | faixa removida |

## 5. O que o mockup decide (e por quê)

1. **Quatro elementos para gravar** — fornecedor, item, valor, vencimento. Emissão = hoje; centro = padrão.
2. **O fornecedor sugere o resto** (item, conta, prazo, forma, banco, último preço), sempre marcado
   "sugerido pelo último lançamento de …" e editável.
3. **"Para onde vai"** é uma frase editável com o nome do dono (Comida/Gente/Outros custeios) e o código
   técnico em letra menor. Natureza, competência, centro, OS, boleto e pedido ficam em
   **"Para o contador e detalhes raros"**.
4. **"O que muda ao salvar"** (coluna à direita; no celular, antes da barra de ação): onde a conta aparece
   (Contas a pagar › faixa), em qual linha do resultado cai (mês do gasto), efeito no caixa e no estoque.
5. **Salvar conversa**: confirmação com Nº, resumo, "Ver em Contas a pagar", "Lançar outro igual",
   **Desfazer**; avisos de estoque em âmbar; erros inline + resumo com `role=alert` e links para o campo.
6. **Um único formulário que cresce** (parcelar, já pago, desconto) em vez de "Lançamento" × "Simplificado".
   Lote e Faturas ficam como abas separadas (tarefas diferentes); Venda de leite ganha aba própria
   (litros × preço, retenção, conferência com o controle leiteiro).
7. **Mês fechado**, **duplicado**, **vale acima de 40%**, **investimento sem bem** viram prevenção visível.

## 6. Rodadas de crítica independente sobre o mockup

Um crítico que **não participou da construção** e não viu este relatório testou o mockup no Chromium
(1440, 1024, 430, moldura de celular, claro/escuro, 3 paletas, teclado, axe-core).

| Versão | Nota geral | Nielsen | Situação |
|---|---|---|---|
| v1.1 | **5,5 / 10** | 25/40 | 5 P0 (conta e preço presos ao item errado, unitário que mente, quantidade implícita = 1, Enter que salva, mês fechado furado) e mais de 30 achados |
| v2 | **7,5 / 10** | 31/40 | todos os P0 e quase todos os P1 corrigidos; axe 0 violações |
| v2.1 (final) | corrigidos os 14 resíduos N1–N14 e confirmação ao desfazer nota com parcela paga | — | **não reavaliado pelo crítico**: verificado por 40+ testes automatizados de regressão e axe-core nos dois temas |

**Verificação automatizada da v2.1** (scripts em `scratchpad`, não versionados): 40 asserções passam
(troca de item, quantidade obrigatória, Enter, meses fechados em 7 campos, duplicado por documento e por mês de
leite, pagamento agendado, baixa com janela, "lançar outro", fornecedor sem cadastro, parcelas, lote, foco após
diálogos, alvos ≥44px no toque, barra Salvar acima da navegação); **0 erros de console**; **axe-core 0 violações**
em 11 cenários × 2 temas e na janela de baixa; contraste medido: texto ≥ 6,2:1, borda de campo 3,1:1 (claro) / 4,5:1
(escuro), botão ouro 4,9:1 / 6,9:1, placeholder 4,7:1.

**Limites desta verificação:** leitor de tela real, Safari/iOS e teclado virtual **não foram testados**; a fonte
Archivo não carregou no sandbox (as capturas usam a fonte de reserva); o número 7,5 é da v2, não da v2.1.

## 7. Fora do escopo do mockup (precisa de decisão ou de código)

- Os achados **P1-5/P2-2/P2-3/P2-4** (Campo órfão, overlays, rascunho, UTC) são **correções no código de
  produção** e valem independentemente do redesenho; ver `RELATORIO` do avaliador C na sessão.
- A causa-raiz do recarregamento múltiplo de `?ir=` **não foi verificada**.
- Leitores de tela reais, Safari/iOS, zoom 200–400% e `forced-colors`: **não verificados**.
- Vínculo sanitário e Pedidos em aberto: auditados só por leitura (os dados de demonstração não disparam).
