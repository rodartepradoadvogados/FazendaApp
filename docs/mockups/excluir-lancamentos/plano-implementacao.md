# Plano de implementação — Excluir lançamentos (v2)

Base: origin/main 472b7f73. Mockup de referência: `docs/mockups/excluir-lancamentos/mockup-excluir.html` (fontes em `docs/mockups/excluir-lancamentos/fonte/`).
Nada deste plano foi aplicado ao app.

## Ordem de entrega (cada fase mergeável sozinha)

| Fase | O que | Por quê primeiro |
|------|-------|------------------|
| 0 | Correções multi-tenant e de FK (B1, B2) | Risco de apagar/vazar dado de outra fazenda. Não depende de UI. |
| 1 | Impacto estruturado, puro, risco, bloqueios, motivo/palavra no servidor, trilha (B3 a B7) | Base de tudo. Mantém `impacto: list[str]` para a UI antiga. |
| 2 | UI nova (F1 a F5), atrás de flag | Consome a fase 1. |
| 3 | Seleção em lote, busca de financeiro agrupada/paginada, cascata completa do financeiro (B8 a B10) | Maior esforço; fase 2 funciona sem. |
| 4 (opcional) | "Restaurar" a partir do snapshot da trilha | Só depois de usar a trilha por um tempo. |

## Parte 1 — Backend

Arquivos principais: `backend/fazenda/api/routers/exclusoes.py` (1506 linhas), `backend/fazenda/rules/exclusao_tipos/{_base,estoque,pessoal,producao,rebanho,sanidade,agricultura}.py`, `backend/fazenda/models/sistema.py` (`SolicitacaoExclusao`, l.169).

### B1. Correções multi-tenant (Fase 0)
Todas em `exclusoes.py`, cada uma com teste em `backend/tests/test_isolamento_exclusoes.py`.
1. **l.738-751** (fallback de Sanidade do Protocolo IATF): a query `select(Sanidade).where(data_aplicacao >= d0)` não filtra fazenda. Acrescentar `Sanidade.fazenda_id == lancamento.fazenda_id`. Hoje, com `numero_matriz` repetido entre fazendas, pode listar e apagar Sanidade de outra fazenda. Mesmo cuidado já aplicado no ramo do protocolo sanitário (l.712-718).
2. **l.975** (contagem de lote): `select(Animal).where(Animal.grupo_primario == rotulo)` sem fazenda. Acrescentar `Animal.fazenda_id == fazenda_id`. Hoje o número "23 animais" pode incluir animais de outra fazenda com lote de mesmo código.
3. Mesma família, mais barata de fechar junto: `_buscar_um` l.217 e l.223 (`ProtocoloSanitario` e `ProtocoloSanitarioAplicacao` lidos sem fazenda), l.446-447 (`EventoSanitario` e `Doenca` do calendário sem fazenda), l.985 (`Estoque.fornecedor_id`), l.1029-1030 (`CalendarioSanitario`/`ProtocoloSanitario` por `doenca_id`), l.1004-1005 (folha/vale por `pessoa_id`; ok porque a pessoa já é da fazenda, mas filtrar por defesa).
4. Testes: criar duas fazendas com mesmo `numero_matriz`/código de lote; excluir na A; afirmar que nada da B muda e que as contagens do impacto não somam a B. Seguir o desenho de `test_isolamento_exclusao_cascata_animal.py`.

### B2. Risco de FK na cascata do financeiro (Fase 0)
`ContaGerencial.id` é FK de `folha_rubrica.conta_gerencial_id` e de `caixa_movimento.lancamento_id` / `caixa_time_movimento.lancamento_id`. `_alvos("financeiro")` não inclui essas linhas. Em Postgres isso deve gerar o mesmo "500 sem CORS / Failed to fetch" já visto no animal (comentário l.559-569). **Verificar primeiro** com teste SQLite `PRAGMA foreign_keys=ON`. Se confirmar: tratar como bloqueio ("a conta tem lançamento no caixa do funcionário / linha de folha") até B9 cobrir a cascata.

### B3. Impacto estruturado
- Novo `backend/fazenda/rules/exclusao_impacto.py` com dataclasses:
  - `Linha(titulo, consequencia, qtd=1, valor=None, filhos=[], chip=None)`
  - `Bloqueio(titulo, motivo, fazer, acao={rota, params})`
  - `Impacto(item={tipo,id,titulo}, apagar[], reverter[], bloqueia[], avisos[], risco, porque[], editar_url)`
- Resposta de `POST /exclusoes/impacto`: o `Impacto` completo **mais** `impacto: list[str]` (títulos de `apagar`) por uma versão, para a UI atual não quebrar.
- Cada helper de reversão vira par `descrever` (sem escrever, devolve `Linha[]`) + `aplicar`:
  `_restaurar_ult_ocorrencia_dos_alvos`, `_reverter_perda_prenhez_causada_pelos_alvos`, `_remover_lactacao_dos_partos_excluidos` (lactação removida e anterior reaberta), `_reabrir_lactacao_das_secagens_excluidas`, `_reajustar_del_dias_apos_excluir_parto` (DEL antes → depois), `_estornar_estoque_dos_alvos` (saldo antes → depois e aviso de saldo negativo, usando `estoque_baixa` em modo prévia), `_desvincular_vales_dos_alvos`.
  Hoje o impacto só lista o que apaga; o que reverte aparece só no resultado (`avisos`, descartados pelo front).
- Avisos novos de domínio (cada um com teste): leite em carência some ao apagar tratamento (`sanidade.py`), cria perde a mãe (animal), pesagens sem lactação (parto), fatura aberta muda total, relatório do mês muda, agenda de IA das vacas do IATF some.

### B4. `/impacto` puro
Hoje a pureza depende de `get_session` não commitar (database.py l.587-623) — `_alvos` muta a sessão em `compra_semen` (movimentar_dose_semen), `fornecedor`, `doenca`, `principio_ativo`, `movimento_estoque`. Tornar explícito: `impacto()` termina com `session.rollback()` num `try/finally`, e as mutações saem de `_alvos` para o `aplicar`. Teste: snapshot das tabelas antes/depois de `/impacto` para os 5 tipos acima; nada muda.

### B5. Risco e confirmação no servidor
- `rules/exclusao_risco.py::calcular(impactos) -> "baixo"|"medio"|"alto"` (função pura):
  - baixo: 1 item, sem reversão, sem dinheiro em aberto, 1 registro.
  - médio: tem reversão (estoque, lactação, DEL, saldo), ou dinheiro em aberto, ou 2 a 9 itens.
  - alto: ficha de animal, cadastro em uso, 10 ou mais registros no lote, ou `Impacto.risco` forçado pelo tipo.
- `POST /exclusoes/confirmar` passa a aceitar `motivo` e `confirmacao`. Servidor recalcula o risco e recusa com 422 se: admin com risco ≥ médio sem `motivo`; risco alto sem `confirmacao == "APAGAR"`; não-admin sem `motivo` (sempre). A UI só mostra; não é ela que protege.

### B6. Bloqueios (preflight)
- `planejar()` preenche `bloqueia`. `confirmar`/`aprovar` recalculam e respondem **409** com o `Impacto` quando há bloqueio (hoje alguns casos são `HTTPException(400)` com texto solto: pessoa l.1007, evento sanitário l.1048, protocolo l.1063, empreitada/contrato/diária em `pessoal.py`, movimento de estoque com origem em `estoque.py`).
- Novos bloqueios: parcela com `data_pagamento`/`valor_pago` (ação: `POST /financeiro/lancamentos/{id}/estornar`, financeiro.py l.5213); parcela de vale descontada em folha paga; folha paga; lote com animais; fatura **fechada ou paga** (aberta = aviso; `FaturaFornecedor`: aberta → fechada → paga, total congelado no fechamento); comissão paga.

### B7. Trilha de auditoria (também para admin)
- Tabela `exclusao_registro` (migration Alembic em `backend/alembic/versions/`, modelo em `models/sistema.py`, export em `models/__init__.py`):
  `id, codigo "EX-AAAA-NNNN" (sequência por fazenda e ano), fazenda_id (index), usuario_id, username, papel, acao (apagou|aprovou|rejeitou|arquivou|cancelou), tipo, id_alvo, titulo, motivo, resumo_json {apagado[], revertido[], avisos[]}, snapshot_json, solicitacao_id, solicitado_por, criado_em`. Índice `(fazenda_id, criado_em desc)`.
- `snapshot_json`: linhas apagadas serializadas, **sem** CPF e sem dado de saúde de pessoa (LGPD; seguir `AGENTS.md`).
- Gravar dentro da mesma transação do `commit` em `confirmar` (admin), `aprovar_pendente`, `rejeitar_pendente`, e nos novos `arquivar`/`cancelar`.
- Rotas: `GET /exclusoes/trilha?acao=&tipo=&q=&limite=&deslocamento=` (admin); `GET /exclusoes/comprovante/{codigo}`.

### B8. Pedidos (não-admin e admin)
- Colunas novas em `SolicitacaoExclusao`: `motivo`, `risco`, `impacto_resumo_json` (foto na hora do pedido), status `arquivada` e `cancelada`.
- **Deduplicar:** índice único parcial `(fazenda_id, tipo, id_alvo) WHERE status='pendente'`. Mesmo usuário pedindo de novo: 200 `{status:"ja_pedido", id}`. Outro usuário: linha em `solicitacao_exclusao_apoio(solicitacao_id, username, motivo, criado_em)`; o admin vê um pedido com N pessoas.
- **Alvo sumiu:** `GET /pendentes` devolve por pedido `alvo_existe`, `impacto` calculado agora (rollback) e `mudou_desde` (diferença contra `impacto_resumo_json`). Quando o alvo não existe, `aprovar` responde **410** com texto claro (hoje cai no 404 genérico "não encontrada ou já decidida", que confunde) e existe `POST /pendentes/{id}/arquivar`.
- `rejeitar`: `motivo` obrigatório (mín. 3 caracteres); hoje é opcional.
- `aprovar`: exige `confirmacao == "APAGAR"` se o risco calculado agora for alto; recalcula bloqueio.
- Solicitante: `GET /exclusoes/meus` (status, `decidido_por/em`, `motivo_rejeicao`) e `POST /pendentes/{id}/cancelar`. Hoje o solicitante nunca vê o resultado.
- Opcional: push ao solicitante na decisão (`PushNotificacaoEnviada` já existe).

### B9. Cascata completa do financeiro (Fase 3)
`_alvos("financeiro")` passa a incluir ou tratar: `LancamentoAnexo` (linhas e objeto no Storage, com a regra "só remove o arquivo na última referência" de `excluir_anexo`, financeiro.py l.5724-5755); `CaixaMovimento` e `CaixaTimeMovimento` por `lancamento_id`; `FolhaRubrica.conta_gerencial_id`; `FaturaFornecedor` (recalcular total se aberta; bloquear se fechada/paga) e `FaturaFornecedorEvento`; `DocumentoArquivado.numero_lancamento` (desvincular); `Patrimonio`/`Pedido` ligados (aviso); `ComissaoCorretagem`. Parcela paga = bloqueio (B6).

### B10. Tipos, domínios, busca e lote
- `TipoExclusao` ganha `dominio`, `plural`, `dica`, `filtros[]`, `cadastro: bool`. Os 23 tipos de `TIPOS` (l.71-95) ganham metadados num dicionário `META_TIPOS` primeiro; migrar os ramos de `_buscar_um` para o registro aos poucos. `GET /exclusoes/tipos` devolve domínio, nome em linguagem de fazenda, dica e **contagem** (COUNT escopado por fazenda). `todos_lancamentos` vira `GET /exclusoes/buscar-tudo`.
- Novos tipos no registro: `vale` e `folha` (reaproveitam `rh_vale_item.desvincular_vale_do_item` e a lógica de `rh_folha.py`; hoje têm endpoint próprio).
- `GET /exclusoes/buscar`: financeiro agrupado por `numero_lancamento` com `parcelas[]`, filtros em SQL (`situacao`, `fornecedor`, `valor_min/max`, período, `q`) e paginação no servidor (`limite/deslocamento`, `total`). Hoje carrega a tabela inteira, filtra em Python e corta em 200, uma linha por parcela. Mesma troca para controle, sanidade e animal (maiores tabelas).
- Lote: `POST /exclusoes/impacto` e `/confirmar` aceitam `{itens:[{tipo,id}], motivo, confirmacao}` (máx. 50). Bloqueados são pulados e reportados; os demais rodam numa transação; erro em qualquer um desfaz tudo.

### B11. Testes do backend (`backend/tests/`)
Novos: `test_exclusao_impacto_estruturado.py` (formato por tipo; JSON de referência para animal, parto, financeiro, secagem, movimento_estoque), `test_exclusao_impacto_puro.py`, `test_exclusao_risco.py` (tabela de casos), `test_exclusao_bloqueios.py` (parcela paga, vale em folha paga, lote em uso, pessoa com folha; 409 com corpo), `test_exclusao_financeiro_cascata_completa.py` (anexo + Storage, caixa, rubrica, fatura; `PRAGMA foreign_keys=ON`), `test_exclusao_trilha.py` (admin direto, aprovação, rejeição; snapshot sem CPF), `test_exclusao_pedidos_dedup.py` (mesmo usuário, outro usuário, alvo sumiu → 410/arquivar, rejeitar sem motivo → 422, cancelar, `/meus`), `test_exclusao_lote.py`, `test_exclusao_motivo_confirmacao_servidor.py`.
Ampliar: `test_isolamento_exclusoes.py` (B1). Manter verdes: `test_exclusoes.py`, `test_exclusao_aprovacao.py`, `test_exclusao_recusa_sem_fazenda.py`, `test_isolamento_exclusao_cascata_animal.py`, `test_exclusao_secagem.py`, `test_exclusao_pessoal.py`, `test_exclusao_movimento_lote.py`.

## Parte 2 — Frontend

Hoje: `frontend/components/FormExclusao.tsx` (316 linhas, tudo num arquivo) usado em `app/lancamentos/page.tsx:153/577`, `components/mobile/lancar/LancarTela.tsx:101`, `components/Cadastro.tsx:140` (com `ocultarTipos={["animal"]}`). API em `frontend/lib/api.ts` l.8803-8840.

### F1. Estrutura
Criar `frontend/components/exclusao/`:
`ExclusaoPage.tsx` (abas Apagar / Pedidos ou Meus pedidos / Trilha, etapas), `EscolherTipo.tsx` (domínios, busca, cadastros separados, "procurar em tudo"), `FiltrosTipo.tsx`, `ListaResultados.tsx` + `LinhaFinanceiro.tsx` (parcelas como filhas), `BandejaSelecao.tsx`, `PainelImpacto.tsx` + `BlocoImpacto.tsx` + `LinhaImpacto.tsx`, `DecisaoExclusao.tsx` (risco, motivo, digitar APAGAR), `ResultadoExclusao.tsx` (comprovante), `PedidosAdmin.tsx`, `MeusPedidos.tsx`, `TrilhaExclusao.tsx`, `useExclusao.ts` (reducer: escolher → impacto → pronto).
`FormExclusao.tsx` vira wrapper fino (`<ExclusaoPage ocultarTipos=… />`); os três pontos de uso não mudam. Flag para ligar a v2 por fazenda (`ParametroFazenda`) até a validação do dono.

### F2. API (`lib/api.ts`)
Tipos `ImpactoExclusao`, `LinhaImpacto`, `BloqueioExclusao`, `TipoExclusaoMeta`, `PedidoExclusao`, `RegistroTrilha`. Funções: `fetchTiposExclusao` (domínio/contagem), `buscarExclusao(params)`, `impactoExclusao(itens)`, `confirmarExclusao({itens, motivo, confirmacao})`, `fetchPendentesExclusao`, `aprovarExclusao(id, confirmacao)`, `rejeitarExclusao(id, motivo)`, `cancelarPedidoExclusao`, `arquivarPedidoExclusao`, `fetchMeusPedidosExclusao`, `fetchTrilhaExclusao`. Tratar 409 (bloqueio) e 410 (alvo sumiu) com mensagem própria; nada de `e.message` cru na tela.

### F3. Comportamento (igual ao mockup)
- Sem modal: o impacto é um passo da página (foco vai para o título; `aria-live` anuncia o resumo). Acaba o modal sem `role="dialog"`.
- Impacto: BLOQUEIA (se houver, primeiro), APAGADO, REVERTIDO, AVISOS; cada bloco com contagem, itens e consequência em frase simples; bloco vazio vira uma linha ("Nada será revertido").
- Confirmação proporcional: baixo = botão; médio = motivo; alto = motivo + digitar APAGAR; não-admin = motivo sempre. O servidor repete a checagem (B5).
- Resultado: comprovante com código, quem, quando, motivo, o que foi apagado e ajustado; não-admin vê "pedido enviado" e acompanha em Meus pedidos.
- Admin: Analisar abre o mesmo impacto calculado agora, mostra "mudou desde o pedido", pedido repetido agrupado, alvo sumiu → Arquivar; Rejeitar exige motivo.
- Atalho "Corrigir em vez de apagar" usa `destinoEditar` (hoje `DESTINO_EDITAR` em FormExclusao.tsx l.15-47), movido para `lib/exclusao.ts`.

### F4. Estilo, movimento e acessibilidade
Só tokens do app (`--vinho`, `--dourado`, `--red`, `--amber`, `--blue`, `--green-light`, `--border`, `--surface*`, `--alert-fg`) e classes existentes (`.card`, `.btn-primary`, `.btn-ghost`, `.fazenda-table`, `.check-tracado`, `.toast-*`); novas classes `.exc-*` num bloco único em `app/globals.css`. Raio 2 px, sem gradiente, hover só cor, sem faixa lateral colorida. Movimento ≤300 ms, só `transform`/`opacity`, `prefers-reduced-motion` troca por fade. Abas com `role=tablist`, etapas em `<ol aria-current>`, motivo como `radiogroup`, alvos de toque ≥44 px, campos ≥16 px no celular. Dentro do app de campo (`LancarTela`, `.mob`) conferir as variáveis (`--mob-*`) e usar a variante compacta.

### F5. Testes do frontend
`npm test` roda `node --experimental-strip-types --test lib/**/*.test.ts`. Criar `lib/exclusao.ts` (funções puras) e `lib/exclusao.test.ts`: risco e exigências de confirmação, frase-resumo, agrupar parcelas por nota, soma de dinheiro, chave de duplicidade. Rodar `npm run lint` e `npx tsc --noEmit`. Verificação visual: scripts Playwright como os capturados para o mockup, 1440 e 390 px, claro e escuro, paleta azul.

## Decisões que dependem do dono
1. Fatura aberta é aviso ou bloqueio? (plano: aviso; fechada/paga bloqueia.)
2. Admin precisa dar motivo em risco médio? (plano: sim.)
3. Digitar APAGAR no risco alto, ou digitar o número do animal? (plano: APAGAR, igual para todos.)
4. Quanto tempo guardar o snapshot na trilha? (plano: sem expurgo; restaurar só na fase 4.)
5. Vale e folha entram no hub agora ou depois? (plano: fase 3.)
