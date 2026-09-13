# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Dono/gestor da fazenda** (hoje: Jairo Nasser, Fazenda Estreito Ponte de Pedra) — usuário primário do painel web: acompanha indicadores, agenda preditiva, financeiro e aprova o que a fazenda faz.
- **Funcionários de campo** (vaqueiros/tratadores) — lançam dados no app móvel (PWA/Capacitor, rotas `/app/*`) direto no curral: peso, saúde, eventos reprodutivos, tarefas da agenda.
- **Veterinário/zootecnista** — consulta reprodução, sanidade e a agenda (protocolos IATF, BST, scratch/PEV) para decisões técnicas.
- **Contador** — acessa a área financeira/DRE (rota dedicada `/contador`).
- **Operador da plataforma CowData** (dono do negócio SaaS) — usa o `painel-cowdata` (cockpit interno) para MRR, contratos, aprovações e financeiro do próprio negócio, separado dos dados operacionais de cada fazenda-cliente.

## Product Purpose

Substituir a planilha Excel/VBA (`PAINEL_FAZENDA_v4.xlsm`) que hoje consolida produção, dieta, reprodução, rebanho, estoque e financeiro de uma fazenda leiteira, por um software próprio que:

- importa os relatórios do Ideagri (CSV) com o mínimo de digitação manual;
- calcula uma **agenda preditiva diária** de eventos e tarefas a partir de regras de negócio reais da fazenda (não genéricas);
- disponibiliza um app de campo para lançamento de dados direto no curral, sem depender de planilha.

Sucesso = a fazenda opera o dia a dia (reprodução, sanidade, estoque, financeiro) inteiramente pelo software, sem voltar à planilha, com a agenda substituindo o controle manual de prazos.

Em paralelo, o mesmo software é oferecido como produto SaaS (**CowData**) para outras fazendas leiteiras, hoje em fase de piloto com poucas fazendas-clientes pagantes.

## Positioning

Não é um dashboard genérico de gestão agropecuária: o diferencial é um **motor de agenda** que codifica regras de negócio específicas de pecuária leiteira, validadas com o dono da fazenda de origem — gestação por raça (Holandês 280d / Girolando 287d / Gir-Zebu 295d), secagem (60d, só vacas em lactação), scratch (14d, cancelado por diagnóstico negativo), PEV (45d), protocolo IATF (D0/D7/D9/D11 com insumos e estoque de hormônios), elegibilidade de BST. Essas regras hoje vivem presas numa macro VBA; o produto as versiona e testa (`backend/fazenda/rules/`, com testes automatizados).

Multi-tenant desde a base (isolamento por `fazenda_id`), permitindo operar tanto a fazenda de origem quanto fazendas-clientes do CowData sob o mesmo software.

## Operating Context

- Fonte de dados primária: exportações CSV do **Ideagri** (Windows-1252, separador `;`, decimal com vírgula) — Geral, Reprodutivo, Estoque, Conta Gerencial, Dieta, Fluxo de Caixa, Curva ABC.
- Upload manual (tela `/upload`) ou automático via `sync_agent.py`, que vigia uma pasta local e envia os CSV (criado para eliminar o cache do Google Drive, que causava dados desatualizados no painel Excel).
- Uso em ambiente de curral/campo: conectividade instável, sol forte, mãos sujas/com luva — o app móvel já reflete isso (alto contraste no claro, modo escuro OLED, alvos de toque ≥44px, fonte ≥16px para não disparar zoom no iOS).
- Deploy: backend FastAPI + Postgres no Railway; frontend Next.js no Vercel; app de campo via PWA/Capacitor (Android).
- Pagamentos e contratos do negócio SaaS via integrações Asaas (cobrança) e ZapSign (contratos).

## Capabilities and Constraints

- Backend FastAPI + SQLModel, parsers dedicados por tipo de CSV do Ideagri, camada de regras pura/testável, motor de agenda que orquestra tudo em lista cronológica.
- Multi-tenant com isolamento por `fazenda_id` nos módulos centrais (Sistema, Lote, Animais, Estoque, Financeiro).
- Dados sujos conhecidos: registros de animal podem ter múltiplos grupos separados por vírgula (ex. `03 - Média,01 - NOV. ALTA`) — hoje sem tratamento completo na camada de agregação.
- Sem captura de peso por animal ainda; transições de lote por peso (Recria 1/2, novilha apta) são hoje manuais no Ideagri, não automatizadas no software.
- Regime de competência × caixa e centro de custo já modelados via Conta Gerencial (coluna 14: PL / C|26 / ARR).

## Brand Commitments

Identidade **CowData** já estabelecida e em uso em produção (não é decisão em aberto):

- Paleta de marca fixa: tinta (`--ink`), vinho (`--wine`), dourado (`--gold`), creme (`--cream`), pasto (`--pasture`) — origem na identidade histórica da Fazenda Jairo Nasser (vinho `#5E1A2E`, dourado `#B8860B`), carregada deliberadamente para a marca CowData.
- Três temas (claro/escuro/misto) e paletas alternativas selecionáveis pelo usuário (vinho padrão, verde, azul) — direção visual "Institucional": cantos quase retos, sem gradientes fortes, sem sombra pesada.
- Tipografia: Barlow/Barlow Condensed no site; Inter no app de campo (`/app`), deliberadamente distinto.
- App de campo tem identidade visual própria (`.mob-*`), separada do site desktop, otimizada para uso a sol forte e bateria.
- Cores de categoria fixas em todo o produto (Reprodutivo, Sanidade, Alimentação, Gestão, Financeiro, Estoque, Recria, Acesso) — não variam por tema ou paleta.

## Evidence on Hand

- CSV reais de produção da Fazenda Estreito Ponte de Pedra (GERAL, REPRODUTIVO, ESTOQUE, CONTA_GERENCIAL, DIETA, FC, ABC) na raiz do repo.
- Planilha de origem `PAINEL_FAZENDA_v4.xlsm` e documento vivo `CONTEXTO_PROJETO_FAZENDA.md` com as regras de negócio validadas pelo dono.
- 27+ testes automatizados das regras de negócio (`backend/tests/test_rules.py`).
- Sem depoimentos, cases ou benchmarks de fazendas-clientes publicáveis ainda — piloto tem poucas fazendas, não usar como prova social até confirmação.

## Product Principles

1. A regra de negócio da fazenda é a fonte da verdade — o software formaliza e testa o que hoje está preso em VBA, nunca simplifica a regra por conveniência de UI.
2. Menos digitação manual sempre vence — importar do Ideagri e capturar em campo substituem preenchimento manual em planilha.
3. O app de campo é um produto à parte do site: otimizado para curral (sol, luva, conectividade), não uma versão reduzida do desktop.
4. Multi-tenant por padrão — toda funcionalidade nova assume que pode existir mais de uma fazenda no mesmo banco.
5. A camada CowData (SaaS) e a operação da fazenda de origem são contextos distintos (cockpit interno vs. operação da fazenda) e não devem se misturar na mesma tela.
