# Roteiro de implementação: Excluir lançamentos

Mockup aprovado ("perfeito e aprovado"; arquivo local: `docs/mockups/excluir-lancamentos/mockup-excluir.html`): https://claude.ai/artifact/Ngg3pcLSgJx8mzhA1DXUPh
Plano técnico completo (backend e frontend, arquivo a arquivo): `docs/mockups/excluir-lancamentos/plano-implementacao.md`.
Antes de implementar (terça 13/10, 02:30): rodar `/impeccable layout` e `animate` e apresentar a versão final. Fechar com o dono as 5 decisões abaixo e só então executar.

## Decisões a fechar na terça
1. Fatura aberta com nota: só avisar (plano) ou bloquear? (fechada/paga sempre bloqueia.)
2. Admin dá motivo também no risco médio? (plano: sim.)
3. Risco alto: digitar APAGAR (plano) ou o número do animal?
4. Quanto tempo guardar o registro do apagado na trilha? (plano: sem expurgo.)
5. Vale e folha entram agora ou na segunda etapa? (plano: fase 3.)

## Ordem de entrega (um PR por fase; cada uma funciona sozinha)

### Fase 0. Correções de segurança (primeiro PR, sem tela)
Arquivo: `backend/fazenda/api/routers/exclusoes.py`.
1. Linhas 738-751: o fallback de Sanidade do Protocolo IATF não filtra `fazenda_id`. Acrescentar `Sanidade.fazenda_id == lancamento.fazenda_id` (como já está no protocolo sanitário, l.707-717).
2. Linha 975: contagem de animais do lote sem fazenda. Acrescentar o filtro.
3. Mesma família: linhas 217, 223, 446-447, 985, 1004-1005, 1029-1030 (leituras sem fazenda).
4. FK da cascata do financeiro: confirmar com teste SQLite `PRAGMA foreign_keys=ON` se apagar uma conta com `caixa_movimento.lancamento_id` ou `folha_rubrica.conta_gerencial_id` dá erro; se der, tratar como bloqueio até a Fase 3.
5. Testes: `backend/tests/test_isolamento_exclusoes.py` (duas fazendas com mesmo `numero_matriz` e mesmo código de lote; apagar na A não toca B; contagens não somam B).

### Fase 1. Backend: impacto estruturado, risco, trilha
1. `rules/exclusao_impacto.py` (`Linha`, `Bloqueio`, `Impacto`); `POST /exclusoes/impacto` devolve o objeto completo e mantém `impacto: list[str]` para a tela antiga.
2. `/impacto` puro: termina com `session.rollback()` em `try/finally`; as mutações saem de `_alvos` para o `aplicar`.
3. `rules/exclusao_risco.py::calcular` (baixo | médio | alto); o servidor exige `motivo` (médio, e sempre para não-admin) e `confirmacao == "APAGAR"` (alto), com 422.
4. Bloqueios com 409: parcela paga (ação: estornar), vale descontado em folha paga, folha paga, lote com animais, fatura fechada/paga, comissão paga.
5. Tabela `exclusao_registro` (trilha, também para admin) com código `EX-AAAA-NNNN`, resumo e snapshot SEM CPF nem dado de saúde de pessoa; migração aditiva (a cabeça atual é `d4a8e1b7c935`; conferir com `python3 backend/scripts/check_alembic_heads.py`).
6. Rotas: `GET /exclusoes/trilha`, `GET /exclusoes/comprovante/{codigo}`.
7. Pedidos: colunas `motivo`, `risco`, `impacto_resumo_json`; status `arquivada` e `cancelada`; deduplicação (índice único parcial); alvo sumiu → 410 e `arquivar`; rejeição com motivo obrigatório; `GET /exclusoes/meus` e cancelar.
8. Testes novos listados no plano (B11). Manter verdes os testes de exclusão existentes.

### Fase 2. Frontend: tela nova atrás de flag
1. Criar `frontend/components/exclusao/*` (EscolherTipo, FiltrosTipo, ListaResultados, PainelImpacto, DecisaoExclusao, ResultadoExclusao, PedidosAdmin, MeusPedidos, TrilhaExclusao, `useExclusao.ts`).
2. `FormExclusao.tsx` vira wrapper fino; os 3 usos (`app/lancamentos/page.tsx`, `components/mobile/lancar/LancarTela.tsx`, `components/Cadastro.tsx`) não mudam. Flag por fazenda (parâmetro) até o dono validar.
3. Funções puras em `frontend/lib/exclusao.ts` + `exclusao.test.ts` (`npm test`).
4. Estilo: só tokens do app, classes `.exc-*` em `app/globals.css`; movimento ≤300 ms, `prefers-reduced-motion`; acessível (tablist, aria-live, alvos ≥44 px).
5. Caveman só nas explicações ao dono; a tela usa linguagem de fazendeiro.

### Fase 3. Lote, busca, cascata completa
1. Busca do financeiro agrupada por nota (parcelas como filhas), filtros em SQL (situação, fornecedor, valor, período) e paginação no servidor.
2. Lote (até 50 itens): bloqueados são pulados e reportados; os demais numa transação.
3. Cascata completa: anexos (e arquivo no Storage), caixa do funcionário/times, rubrica da folha, fatura, documentos arquivados, comissão.
4. Tipos `vale` e `folha` no hub (se o dono decidir na terça).

### Fase 4 (opcional). Restaurar a partir do snapshot da trilha, depois de usar a trilha por um tempo.

## Verificação (cada fase)
Suíte completa do backend UMA vez sob `flock`; `npx tsc --noEmit`, `npm test`, eslint nos arquivos tocados; Playwright em 1440 e 390 px, claro e escuro, estados vazio/erro/carregando e movimento reduzido; PR aberto sem mesclar (o dono mescla e avisa; depois recriar a branch de `origin/main`).
