# Aprovação do PLANO_v2 e padrões para as decisões pendentes (2026-10-13)
Aprovado pela sessão (autonomia concedida pelo Jairo: implementar sem interferência, abrir PR e relatório).
Padrões adotados nas decisões P1–P16 (recomendação do revisor), salvo ajuste abaixo:
- P1 preço fecha na APROVAÇÃO; trocar de plano recongela. P2 backfill SIM (valor de hoje; nenhum valor cobrado muda).
- P3 upgrade para Estoque sem retroativo. P4 downgrade: dados preservados e ocultos, só o dono executa.
- P5 regras v2 só em fazenda sem lançamentos, e só pelo botão "Preparar financeiro". P6 plano de contas = rascunho genérico (b), rotulado "validar com o contador".
- P7 centro "Agricultura" inativo por padrão no plano Financeiro (não apagar nada existente). P8 site responsivo; fazenda sem rebanho não vai para /app.
- P9 tabela de dependências da 1.1 (agricultura sem dependência). P10 "A receber" card separado, vencidas + 10 dias.
- P11 NÃO alterar a janela de 30 dias de vencidas para nenhum plano; registrar como decisão futura do Jairo.
- P12–P16: NÃO decidir nada comercial/jurídico; listar no relatório como pendências. P14: renomear o rótulo "Financeiro (básico)" para "Financeiro (módulo)".
- Estoque (decisão do Jairo, D1): sem o módulo `estoque` nenhum efeito colateral grava estoque; estoque exige rebanho + financeiro.
- Preço do plano Financeiro: R$ 200,00/mês, editável no Painel CowData (D2).
Escopo desta execução: F0–F4 e PR. F5 (produção) é etapa humana. Nunca tocar Railway/Vercel/Neon/Supabase, CSV/XLSM da raiz ou preço de contrato existente.
