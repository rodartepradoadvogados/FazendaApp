# Tela real × mockup — comparação campo a campo

**Data:** 15/10/2026 · **Tela:** Lançamentos › Financeiro › *Contas a pagar (despesa)* e *Contas a receber (receita)*
· **Código:** `frontend/components/FormFinanceiro.tsx`, `EstoquePicker.tsx`, `app/globals.css`, `app/lancamentos/page.tsx`
· **Ambiente de teste:** fazenda fictícia "Vale Verde", banco SQLite descartável (nada da fazenda real).

Capturas (2000×1125): `capturas/real_ANTES_{misto,escuro}.png` e `capturas/real_DEPOIS_{misto,escuro,claro}.png`.

## 1. O que você pediu e não estava no mockup: unidade do produto

O mockup não tinha onde escolher pacote/frasco/ml. A **tela real também não tinha**: o backend já aceitava
`apresentacao_id` em cada item (e convertia nº de embalagens → unidade do estoque, abrindo um lote), mas o
formulário nunca enviava o campo. Agora existe:

| Elemento (por item de produto, só **despesa**, só **produto do estoque**) | Como funciona |
|---|---|
| **Comprado em (unidade do produto)** | `Direto em <unidade do estoque>` ou uma embalagem cadastrada no item: `frasco de 50 mililitros`, `frasco de 100 mililitros`… (vêm de `GET /estoque/{id}/embalagens`; só ativas) |
| Rótulos que mudam | Com embalagem: **Quantidade (nº de frascos)** e **Valor por frasco (R$)**. Sem: *Quantidade* / *Valor unitário* (como antes) |
| Linha de conversão | `6 frasco(s) × 100 mililitros = 600 ml entram no estoque · saldo vai de 0 para 600 ml · custo R$ 0,80/ml` |
| Trocar de produto | zera a embalagem (ela pertence ao produto anterior) |
| Payload | `apresentacao_id` = id da embalagem, ou `null` |

Texto livre, serviço e **receita** não mostram o seletor (não dão entrada em estoque).

**Verificado no app real (ida e volta):** 6 frascos de 100 ml a R$ 80,00 → POST enviou `apresentacao_id: 2, quantidade: 6, valor_unitario: 80`
→ backend gravou lote `quantidade_comprada=600`, `apresentacao_id=2`, `apresentacao_quantidade=100` e o saldo do item foi a **600 ml**.
Direto em ml (250 ml, já pago) → `apresentacao_id: null`, 201. Parcelado 3× com frasco de 50 ml → 3 parcelas, `apresentacao_id: 1`, 201.
Receita → `apresentacao_id: null`, 201. Backend já tinha teste da compra com embalagem (`backend/tests/test_embalagens_estoque.py`).

> **Atenção (já era assim, não mexi):** `LoteEstoque.valor_unitario` guarda o valor **por embalagem** (R$ 80) enquanto
> `quantidade_comprada` está na unidade do estoque (600 ml). É o mesmo comportamento da rota manual de lotes.
> Se algum relatório de custo usa esse campo como "R$ por ml", ele está 100× maior. **Não verificado nesta sessão** — precisa de decisão.

## 2. Todos os campos da tela real hoje (nenhum foi removido)

| Bloco | Campo | Situação nesta entrega |
|---|---|---|
| Nota | Fornecedor/Cliente (+ Novo), Centro de custo, Classificação (+ Nova), Natureza, Data de emissão, Data de vencimento, Valor líquido (calculado) | mantidos |
| Nota › Mais detalhes | Responsável, Tipo de documento, Nº do documento, Nº da OS/Orçamento, Nº do boleto, Data prevista de entrada, Data do pedido, Vincular a um pedido, Entregue?, Desconto, Acréscimo | mantidos |
| Documentos | Arrastar/selecionar/foto/colar XML, categoria, leitura automática e conferência de divergências | mantidos |
| Item | Produto \| Serviço, Produto (estoque ou texto livre), Conta gerencial, Centro de custo do item, Descrição, modo valor unitário/total, Quantidade, Valor unitário, Valor total, É vale de funcionário? | mantidos |
| Item | **Comprado em (unidade do produto)** | **NOVO** |
| Item | Adicionar produto/serviço/conta novo(a), Acrescentar produto ou serviço | mantidos |
| Parcelamento | Qtd de parcelas; por parcela: vencimento, valor, nº do boleto, Pago + 5 campos de baixa | mantidos |
| Pagamento | Já foi pago/recebido + data, valor pago, conta bancária, nº do documento, forma | mantidos |
| Rodapé fixo | Total, Parcelas, 1º vencimento, Estoque, Pedido, DRE + **Salvar lançamento** | mantidos (sem sombra) |
| Fora da tela | duplicado (popup), vínculo sanitário, pedidos em aberto, patrimônio | mantidos |

## 3. O que do mockup já está na tela real

| Decisão do mockup | Na tela real |
|---|---|
| Cor só com semântica (sem 4 painéis pastel) | **feito** — os 4 tokens `--fin-*-bg` viraram a superfície neutra nos 3 temas |
| "O que muda ao salvar" | **feito, só leitura** (coluna da esquerda, que sobrava vazia): em que lista aparece e em que faixa (*Vence em N dias / Vencida há N dias / Paga*), valor e nº de parcelas, linha do resultado (centro · classificação · **Comida** quando a conta é de custo de alimentação), efeito no caixa, entrada no estoque por item (ex.: `Antibiótico injetável: +600 ml`) e pedido |
| Sem ouro como texto / sem sombra | **feito** (valor líquido, "Produto/serviço N", total do rodapé, barra fixa) |
| Rótulos acessíveis | **feito** — `Campo` agora liga o rótulo ao primeiro controle real (antes 5 de 15 controles ficavam sem nome); axe-core no tema claro: **0 violações** na página |
| Faixa "Financeiro já grava de verdade…" | **trocada** por uma frase útil (só na aba financeira; as outras abas não foram tocadas) |

## 4. O que veio do mockup depois da 1ª entrega (15/10/2026, 2ª rodada) e o que ainda falta

| Item do mockup | Situação |
|---|---|
| Os 4 campos essenciais no topo | **feito** — a nota mostra só Fornecedor, Vencimento e Valor; centro de custo, classificação, natureza e emissão ficam em "Mais detalhes" (abre sozinho quando já têm valor); centro e descrição do item ficam em "Detalhes do item". Emissão em branco = hoje (antes ia nula) |
| Fornecedor sugere o resto | **feito** — último lançamento do fornecedor sugere produto, conta, centro, classificação e prazo, **só em campo vazio**, marcado "Sugerido pelo último lançamento de …" e com "Desfazer sugestões". Usa o extrato que o app já carrega (sem endpoint novo) |
| Confirmação com **Desfazer** e "Lançar outro igual" | **feito** — cartão com número, valor, vencimento, avisos, "Ver em Controle Financeiro", "Lançar outro igual" e "Desfazer" (mesmo fluxo de Excluir lançamento: impacto, motivo, trilha; operador gera pedido ao administrador) |
| "Para onde vai" como frase editável (Comida/Gente/Outros) | só leitura no cartão "O que muda ao salvar" |
| Mês fechado / vale > 40% / investimento sem bem **antes** de salvar | ainda recusado só ao salvar |
| Unificar "Lançamento" e "Lançamento simplificado"; aba própria para venda de leite | decisão de produto, não feito |
| Natureza **por item** (o backend aceita; a tela real não oferece) | não feito |
| Rascunho com escopo de usuário/fazenda; data "hoje" em UTC; re-render a cada tecla | não feito (achados P2 da auditoria) |
| Sub-aba **Faturas › Lançar notas** | refeita na 2ª rodada — ver `docs/auditoria-faturas-lancar-notas.md` |

## 5. Verificação desta entrega

- `tsc --noEmit`: sem erros · `npm test`: 298 aprovados, 0 falhas · `eslint` em `FormFinanceiro.tsx`: 27 → 25 erros (nenhum novo; os demais já existiam).
- Navegador (Chromium, app real, dev server): despesa direta, despesa parcelada com embalagem, despesa já paga, receita — todos 201; **0 erros de console**.
- **Não verificado:** celular real / app de campo (`FormFinanceiroApp`), leitor de tela, Safari/iOS, abas Lote/Faturas/Sêmen com os tokens novos, build de produção (`next build`), deploy Vercel/Railway.
- Armadilha de ambiente: o cache do Turbopack (`.next/dev/cache`) serviu o CSS antigo depois de editar `globals.css`; foi preciso limpar o cache e reiniciar o `next dev`.
