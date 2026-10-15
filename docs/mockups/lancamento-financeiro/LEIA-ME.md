# Mockup navegável — Lançar no financeiro

> **Adaptação na tela real (15/10/2026):** ver `COMPARACAO_tela_real.md` (campo a campo, antes/depois, o que falta) e `capturas/`.

HTML/CSS/JS puros, **sem build e sem dependências**. Abra `index.html` no navegador (funciona por `file://`).
Dados **fictícios** da Fazenda Vale Verde (os mesmos do ambiente de demonstração), "hoje" = **15/10/2026**.
Nada aqui grava no produto: é uma simulação para decidir direção, copy e fluxo.

## Como percorrer

A barra escura no topo **não é do produto** (só controla o mockup):

| Controle | O que faz |
|---|---|
| **Cenário** | Carrega 14 situações prontas: do zero · nota lida do documento · compra parcelada · já paguei com desconto · possível duplicado · vale de funcionário · compra de bem · erro de validação · mês fechado · venda de leite · lote · faturas · sêmen · Contas a pagar |
| **Tela** | Computador ou celular (moldura 390×844 que rola; no celular de verdade vira tela cheia com a barra Salvar acima da navegação) |
| **Perfil** | Dono ou Funcionário (o funcionário não pode autorizar vale acima de 40% do salário) |
| **Tema / Paleta** | Claro/Escuro × Azul/Vinho/Verde (mesmos papéis de cor do produto) |

Navegação dentro do mockup: menu **Lançamentos**, **Contas a pagar** e **Contas a receber** (o que você grava
aparece lá, nas faixas "Vencidas / Até 7 dias / De 8 a 14 dias / Depois de 14 dias"; "Dar baixa" abre a janela
de baixa; a aba **Pagas** mostra o que já saiu).

## Roteiro de 5 minutos

1. **Despesa › Uma conta.** Clique no chip *Nutrimix*: item, conta, preço, prazo e forma chegam sugeridos
   ("sugerido pelo último lançamento"). Digite **120** na quantidade e veja a coluna **O que muda ao salvar**
   (Contas a pagar › faixa, Resultado › Comida, Caixa, Estoque). `Ctrl + Enter` salva.
2. **Salvar** → cartão de confirmação com **Ver em Contas a pagar**, **Lançar outro igual** e **Desfazer**.
3. Cenário **Nota lida do documento** → os campos chegam marcados "lido da nota" para conferir.
4. Cenário **Possível duplicado** → *Salvar* abre o aviso (a ação segura é a principal).
5. Cenário **Venda de leite** → litros × preço, retenção Funrural/Senar, conferência com o controle leiteiro.
6. Cenário **Lote de notas** (tudo ou nada) e **Compra parcelada** (editar uma parcela ajusta a última).
7. Em **Contas a pagar**, "Dar baixa" com valor menor mostra o desconto e o efeito no saldo.

## Decisões de design (resumo)

- **4 elementos bastam**: fornecedor, item, valor, vencimento. O fornecedor sugere o resto.
- **"Vai para Comida · Sal mineral e suplementos 3.01.01.03"**: o nome que o dono reconhece (Comida / Gente /
  Outros custeios, como no Resultado por litro) com a conta técnica em letra menor.
- **Natureza, competência, centro, OS, boleto, pedido, entrega** ficam em "Para o contador e detalhes raros".
- **Efeito antes de salvar** usa o vocabulário do Controle (faixas de vencimento, selos de situação).
- Direção **Institucional** (DESIGN.md): cantos 2px, sem gradiente, sem sombra, marinho estrutura, **ouro só
  confirma**, números tabulares, cor só com semântica.
- Contraste medido: texto ≥ 6:1, bordas de campo ≥ 3:1, botão ouro 4,9:1 (claro) / 6,9:1 (escuro); axe-core 0 violações.

## O que o mockup NÃO faz (de propósito ou por falta de decisão)

- Não é código de produção: os achados técnicos (rótulos órfãos do `Campo`, overlays à mão, rascunho,
  datas em UTC, re-render por tecla, `?ir=` recarregando) continuam a corrigir em `frontend/` — ver
  `RELATORIO_critique_audit.md`.
- **Natureza, centro de custo e descrição por item** (a regra v2 grava no item) estão só na nota.
- Leite só em litros (a regra v2 §14 também converte kg ÷ 1,029); a alíquota de retenção é um campo, não vem do cadastro.
- "Dar baixa" não cobre baixa em lote, juros/desconto contábil detalhado nem conciliação.
- Sem rascunho para lote, sêmen e faturas; sem fila offline (o app de campo real precisa dela).
- Resumo, Consultas e Relatórios do Controle são abas desabilitadas.
- Fonte Archivo carrega do Google Fonts; sem internet cai em Inter/sistema.
