# Relatório — Auditoria e Melhorias de UX/Funcionalidade

**Data:** 10/07/2026 · **Ponto de restauração:** commit `5a5b55e` (tag local `ponto-restauracao-20260710`).
Para desfazer tudo deste pacote: `git reset --hard 5a5b55e` (ou peça "restaurar o ponto de 10/07").

**Metodologia:** diagnóstico, estratégia e plano por Fable 5; execução operacional por agentes Opus 4.8.
**Referências:** DairyComp (densidade organizada, drill-down claro, agenda impecável) como modelo positivo;
Ideagri (telas poluídas, funções desnecessárias, pouca liberdade de extração) como anti-padrão a evitar.

---

## 1. Diagnóstico — problemas sistêmicos encontrados

### 1.1 Intuitividade
- **Tooltips quase inexistentes**: ~15 atributos `title=` em ~13.000 linhas de frontend. Botões só-ícone
  (lixeira, X de fechar, check compacto) sem nenhuma descrição ao passar o mouse, em todas as telas.
- Sidebar sem tooltip em nenhum link; item "Sanidade/Estoque" com rótulo confuso (a página é só Estoque).
- Página Upload: botão "Atualizar relatórios" só recarrega a página, mas o texto sugere processamento;
  guia "Como exportar do Ideagri" cobre só 4 dos 10 tipos de upload.

### 1.2 Affordance de expansão (o que abre com clique vs. o que não abre)
- A classe `row-clickable` (linhas clicáveis) era referenciada em Indicadores mas **não existia no CSS** —
  o destaque visual nunca funcionou.
- Expansíveis sem chevron (ex.: protocolos IATF ativos em Lançamentos); linhas clicáveis sem pista visual
  (seleção de nota em Pagamento/Recebimento, seleção em lote); KPIs clicáveis e não-clicáveis idênticos na Capa.
- Gráficos clicáveis (drill-down) sem a dica "clique para ver" — só a Sanidade tinha, e apenas em um dos três.

### 1.3 Excesso de coisas abertas
- **Produção**: 7 seções pesadas abertas simultaneamente (filtros, últimos controles, qualidade, ITALAC,
  curva de lactação, ranking, registros filtrados).
- **Financeiro**: 14 cards seletores abertos na entrada; Folha de pagamento com 3 blocos simultâneos;
  Fluxo com 2 tabelões + gráfico + KPIs de uma vez.
- **Lançamentos**: formulário + tabela de histórico sempre abertos juntos (Dieta, Calendário sanitário).
- Barra de abas (pills) **reimplementada 16 vezes** — cada página com sua cópia, sem tooltip, com variações.

### 1.4 Comunicação entre ações (botão → resultado)
- Ações de escrita sem feedback de sucesso (Agenda: marcar realizado, adicionar evento; AgendaVeterinário:
  reconfirmação some da lista sem confirmação; Financeiro: "marcar como pago" na Folha mostra erro longe da linha).
- Erros engolidos: `catch(() => {})` em Qualidade do leite e ITALAC (Produção) — falha vira "sem dados";
  Capa idem (Promise.allSettled sem tratamento); Agenda não distingue erro de carga de "sem dados".
- Sino de notificações: itens **não são links** (beco sem saída) e o sino **desaparece** em caso de erro.
- Modal "Anexar recibo" da Folha não recarrega a lista ao salvar (as outras telas recarregam).
- Capa/Indicadores/Rebanho não recarregam dados ao voltar de outra aba (ex.: após baixar/comprar animal).

### 1.5 Bugs e gaps funcionais
- Classe `btn-primario` (com "o") **não existe** — botão Salvar sem estilo em AgendaVeterinário e
  SugestõesMovimentação.
- Sanidade: filtro por período **exclui silenciosamente** aplicações sem data.
- Lançamentos: docstring/textos dizendo "rascunho, nada é gravado" quando tudo já grava; componente morto
  `SalvarEmBreve`; parto engole falha de colostragem/alocação com mensagem de sucesso.
- Reprodução: tabela de serviços é a única não-ordenável do site; `useOrdenacao` duplicado localmente
  no AgendaVeterinário em vez do componente compartilhado.
- Financeiro: dois formatadores de data na mesma página; gráficos de fluxo/livro decimam pontos sem aviso;
  parcelas não recalculam ao editar valores após gerar (só avisa divergência).
- FormDiagnóstico: loop de salvamento por animal sem recuperação de falha parcial.
- Agenda: KPI "BST Excluídos" lê de fonte diferente da lista correspondente; parser de "R$" acoplado ao
  formato do backend.

## 2. Estratégia

Cinco princípios, inspirados no que o DairyComp faz bem e no que o Ideagri faz mal:

1. **Um padrão, uma implementação** — componente único de abas (`TabBar`) e de seção recolhível
   (`SecaoRecolhivel`); fim das 16 cópias.
2. **Nada pesado aberto por padrão** — relatórios e tabelões atrás de um clique claramente sinalizado,
   com contagem no cabeçalho (densidade organizada à la DairyComp, sem a poluição à la Ideagri).
3. **Todo clicável se anuncia** — chevron = expande; alvo = abre lista de animais; `title=` em todo
   controle interativo; `.row-clickable` de verdade no CSS.
4. **Toda ação responde** — sucesso visível perto do botão, lista recarregada, erro nunca engolido.
5. **Beco sem saída zero** — notificações levam à tela de resolução; erro de carga se distingue de vazio.

## 3. Plano de ação (execução Opus 4.8)

- **O1 — Fundação**: `components/ui.tsx` (TabBar + SecaoRecolhivel), `.row-clickable` no CSS,
  Sidebar com tooltips e rótulo corrigido, sino de notificações clicável e resiliente a erro.
- **O2 — Financeiro**: TabBar, tooltips, affordances de seleção de nota, recolher seções pesadas,
  feedback do "marcar como pago" junto à linha, refresh do modal da Folha, formatador de data único.
- **O3 — Lançamentos/Estoque/Upload**: tooltips nas lixeiras/fechar, chevron nos protocolos IATF,
  históricos recolhíveis, textos "rascunho" corrigidos, código morto removido, título do Estoque,
  guia de upload cobrindo os 10 tipos.
- **O4 — Produção/Reprodução**: seções recolhíveis na Produção, erros não engolidos, tabela de
  serviços ordenável, `btn-primario`→`btn-primary`, Ordenavel compartilhado, feedback na reconfirmação.
- **O5 — Agenda/Capa/Indicadores**: banner de erro distinto de vazio, feedback de sucesso, label no
  seletor de data, KPIs da Capa com affordance uniforme e tratamento de erro, botão de atualizar.
- **O6 — Rebanho/Sanidade/Configurações**: TabBar, refetch ao voltar para a visão geral, filtro de
  data da Sanidade sem sumiço silencioso, `btn-primario` em SugestõesMovimentação, tooltips.
- **Final**: typecheck, testes de backend, smoke test, commit, push e este relatório atualizado.

## 4. O que foi alterado (preenchido após a execução)

_(ver seção final)_
