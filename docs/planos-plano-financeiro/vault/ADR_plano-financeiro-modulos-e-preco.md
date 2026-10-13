---
projeto: 04_CowData/Milk
tipo: adr
data: 2026-10-13
status: rascunho
---
# ADR — Plano Financeiro: dependências de módulos, preço congelado e estoque condicionado
Contexto: queremos vender o Financeiro (Controle Financeiro + Cotações + Pedidos) sem Rebanho. O contrato exigia Rebanho e o preço do plano era lido ao vivo do código.
Decisões:
1. Todo contrato exige um módulo base (rebanho ou financeiro) e valida dependências entre módulos (`DEPENDENCIAS_MODULOS`).
2. O preço do plano mora em `preco_plano` (editável, só o dono); o do contrato fecha na aprovação e sobrevive a reajuste do catálogo; uma função única (`preco_mensal_do_contrato`) serve contrato, MRR, Asaas e cobrança.
3. Módulo `estoque` não contratado ⇒ Pedidos e Financeiro não gravam estoque (parâmetro `exigir_modulo_estoque`); demais módulos inalterados para não mudar fazendas existentes.
4. Visibilidade no front por tabela única (`lib/modulos.ts`), contrato relido do servidor; página inicial calculada por `rotaInicial()`.
Consequências: migração nova no boot; plano de contas padrão é rascunho; upgrade para Estoque é sem retroativo (inventário inicial datado, a decidir); downgrade preserva e oculta dados (a decidir).
Alternativas descartadas: gate global de estoque em `movimentar` (alteraria Standard/Silver); reler preço ao vivo do catálogo (reajuste silencioso de contratos assinados).
