// Testes de frontend/lib/folhaCompetencia.ts — as regras do mês de folha.
// Rodam com o runner nativo do Node (o projeto não tem jest/vitest): `npm test`.
//
// O que estas regras existem para impedir, e que estes testes travam:
//  - a faixa da equação e o recibo divergirem: os dois números têm de sair da
//    MESMA discriminação, nunca de dois cálculos parecidos;
//  - a folha estourada entrar no total a pagar do mês (ela REDUZIA o total —
//    o erro se disfarçava de bom número);
//  - o painel de exceções ganhar cartão de bug que já foi corrigido: retenção
//    digitada sem percentual e folha recorrente sem INSS/IR NÃO são exceção;
//  - a barra do mês achar que governa quando o usuário escolheu um período
//    próprio nos campos de data (é o mesmo filtro).
import { test } from "node:test";
import assert from "node:assert/strict";
import type { LinhaFolhaUnificada, LinhaHolerite } from "./api.ts";
import {
  competenciasDoMes, equacaoDoMes, excecoesDoMes, mesDaLinha, mesDoIntervalo,
  mesInicial, mesesDoLedger, passoMes, primeiroDiaDoMes, resumoOutrosTipos,
  situacaoDoMes, ultimoDiaDoMes,
} from "./folhaCompetencia.ts";

function linha(over: Partial<LinhaHolerite>): LinhaHolerite {
  return {
    label: "x", valor: 0, tipo: "bruto", descricao: "x", referencia: "",
    provento: null, desconto: null, origem: null, ...over,
  } as LinhaHolerite;
}

/** Uma folha de funcionário com discriminação coerente com os totais. */
function folha(over: Partial<LinhaFolhaUnificada> = {}): LinhaFolhaUnificada {
  const detalhe = over.detalhe ?? [
    linha({ tipo: "bruto", descricao: "Salário", referencia: "Mensal", provento: 2000 }),
    linha({
      tipo: "inss", descricao: "INSS", referencia: "7,78% sobre R$ 2.000,00", desconto: 155.68,
      origem: { tipo: "retencao", percentual: 7.78, base: 2000, confere: true, diferenca: 0 },
    }),
  ];
  const proventos = detalhe.reduce((a, d) => a + (d.provento || 0), 0);
  const descontos = detalhe.reduce((a, d) => a + (d.desconto || 0), 0);
  const liquido = Math.round((proventos - descontos) * 100) / 100;
  return {
    tipo: "funcionario", origem_id: 1, origem_subtipo: "folha",
    pessoa_id: 3, pessoa_nome: "Alane Santos de Castro",
    descricao: "Folha — 2026-08", valor: liquido,
    data_vencimento: "2026-09-05", data_pagamento: null,
    status: "pendente", pode_excluir: true, vencido: false,
    competencia: "2026-08",
    detalhe,
    totais: {
      total_proventos: proventos, total_descontos: descontos, liquido,
      liquido_negativo: liquido < 0, excedente: liquido < 0 ? Math.abs(liquido) : 0,
    },
    ...over,
  } as LinhaFolhaUnificada;
}

/** Um lançamento de outro tipo — sem competência e sem discriminação. */
function avulso(over: Partial<LinhaFolhaUnificada> = {}): LinhaFolhaUnificada {
  return {
    tipo: "diaria", origem_id: 90, origem_subtipo: "pagamento",
    pessoa_id: 8, pessoa_nome: "Maria de Fátima Souza",
    descricao: "Diária", valor: 120,
    data_vencimento: "2026-09-10", data_pagamento: "2026-09-10",
    status: "pago", pode_excluir: false, vencido: false,
    ...over,
  } as LinhaFolhaUnificada;
}

// ── O mês de um lançamento ────────────────────────────────────────────────

test("o mês é o do pagamento quando pago, o do vencimento quando pendente", () => {
  assert.equal(mesDaLinha(folha()), "2026-09");
  assert.equal(mesDaLinha(folha({ status: "pago", data_pagamento: "2026-10-02" })), "2026-10");
  assert.equal(mesDaLinha(folha({ data_vencimento: null, data_pagamento: null })), "");
});

test("meses do ledger saem do mais recente para o mais antigo, sem repetir", () => {
  const meses = mesesDoLedger([
    folha({ origem_id: 1, data_vencimento: "2026-07-05" }),
    folha({ origem_id: 2, data_vencimento: "2026-09-05" }),
    folha({ origem_id: 3, data_vencimento: "2026-07-05" }),
  ]);
  assert.deepEqual(meses, ["2026-09", "2026-07"]);
});

test("a tela abre no mês corrente quando ele tem lançamento", () => {
  const linhas = [folha({ data_vencimento: "2026-09-05" }), folha({ origem_id: 2, data_vencimento: "2026-08-05" })];
  assert.equal(mesInicial(linhas, "2026-09"), "2026-09");
});

test("sem lançamento no mês corrente, abre no mês mais recente que tem — nunca vazia", () => {
  const linhas = [folha({ data_vencimento: "2026-07-05" }), folha({ origem_id: 2, data_vencimento: "2026-08-05" })];
  assert.equal(mesInicial(linhas, "2026-12"), "2026-08");
  // Ledger vazio: fica no mês corrente, e a barra é que diz que não há nada.
  assert.equal(mesInicial([], "2026-12"), "2026-12");
});

test("passo de mês atravessa a virada do ano nos dois sentidos", () => {
  assert.equal(passoMes("2026-12", 1), "2027-01");
  assert.equal(passoMes("2026-01", -1), "2025-12");
  assert.equal(passoMes("2026-09", 0), "2026-09");
});

test("o intervalo do mês cobre fevereiro bissexto e os meses de 30 dias", () => {
  assert.equal(primeiroDiaDoMes("2026-09"), "2026-09-01");
  assert.equal(ultimoDiaDoMes("2026-09"), "2026-09-30");
  assert.equal(ultimoDiaDoMes("2026-02"), "2026-02-28");
  assert.equal(ultimoDiaDoMes("2024-02"), "2024-02-29");
});

test("a barra só se diz dona do filtro quando o intervalo é um mês inteiro", () => {
  assert.equal(mesDoIntervalo("2026-09-01", "2026-09-30"), "2026-09");
  // Período escolhido à mão nos campos de data: a barra não governa.
  assert.equal(mesDoIntervalo("2026-09-03", "2026-09-30"), null);
  assert.equal(mesDoIntervalo("2026-09-01", "2026-10-31"), null);
  assert.equal(mesDoIntervalo("", ""), null);
});

test("as competências do mês saem das folhas de verdade, sem supor 'mês anterior'", () => {
  const linhas = [
    folha({ origem_id: 1, competencia: "2026-08" }),
    // Dia de vencimento configurável faz duas competências caírem no mesmo mês.
    folha({ origem_id: 2, competencia: "2026-07", data_vencimento: "2026-09-20" }),
    avulso(),
  ];
  assert.deepEqual(competenciasDoMes(linhas), ["2026-07", "2026-08"]);
});

// ── A equação do mês ──────────────────────────────────────────────────────

test("a equação lê a discriminação, e as quatro parcelas fecham no líquido", () => {
  const eq = equacaoDoMes([
    folha({ origem_id: 1 }),
    folha({
      origem_id: 2, pessoa_nome: "José Aparecido Lima",
      detalhe: [
        linha({ tipo: "bruto", descricao: "Salário", provento: 2400 }),
        linha({ tipo: "vale", descricao: "Vale — adiantamento", desconto: 320 }),
        linha({ tipo: "outros", descricao: "Outros descontos", desconto: 40 }),
      ],
    }),
    avulso(),
  ]);
  assert.equal(eq.vencimentos, 4400);
  assert.equal(eq.retencoes, 155.68);
  assert.equal(eq.vales, 320);
  assert.equal(eq.outros, 40);
  assert.equal(eq.folhas, 2);
  assert.equal(eq.parcelasVale, 1);
  // A identidade: Vencimentos − Retenções − Vales − Outros = A pagar.
  assert.equal(Math.round((eq.vencimentos - eq.retencoes - eq.vales - eq.outros) * 100) / 100, eq.aPagar);
  assert.equal(eq.divergencia, 0);
});

test("folha estourada sai do 'a pagar' e vira número próprio, em valor absoluto", () => {
  const estourada = folha({
    origem_id: 9, pessoa_nome: "Leomir Bonfim",
    detalhe: [
      linha({ tipo: "bruto", descricao: "Salário", provento: 3200 }),
      linha({ tipo: "vale", descricao: "Vale — ração", desconto: 4880.54 }),
    ],
  });
  const eq = equacaoDoMes([folha({ origem_id: 1 }), estourada]);
  // 2000 − 155,68 = 1844,32 — a folha de −1.680,54 NÃO abate o total do mês.
  assert.equal(eq.aPagar, 1844.32);
  assert.equal(eq.foraDaConta, 1680.54);
  assert.equal(eq.folhasForaDaConta, 1);
});

test("a equação denuncia o líquido gravado que não bate com a discriminação", () => {
  // Folha paga cujo valor gravado ficou para trás de uma parcela de vale nova.
  const eq = equacaoDoMes([folha({ status: "pago", data_pagamento: "2026-09-05", valor: 2000 })]);
  assert.equal(eq.divergencia, 155.68);
  assert.equal(eq.pagas, 1);
});

test("pagas, a vencer e vencidas são contadas separadamente", () => {
  const eq = equacaoDoMes([
    folha({ origem_id: 1, status: "pago", data_pagamento: "2026-09-05" }),
    folha({ origem_id: 2 }),
    folha({ origem_id: 3, vencido: true }),
  ]);
  assert.deepEqual([eq.pagas, eq.aVencer, eq.vencidas], [1, 1, 1]);
});

test("os outros quatro tipos ficam fora da equação e viram resumo próprio", () => {
  const resumo = resumoOutrosTipos([
    folha(),
    avulso({ origem_id: 1, valor: 120 }),
    avulso({ origem_id: 2, valor: 200 }),
    avulso({ origem_id: 3, tipo: "empreita", valor: 6400, status: "pendente", data_pagamento: null, vencido: true }),
  ]);
  assert.deepEqual(resumo.map((r) => r.tipo), ["empreita", "diaria"]);
  assert.deepEqual(resumo[1], { tipo: "diaria", quantidade: 2, total: 320, pagos: 2, vencidos: 0 });
  assert.equal(resumo[0].vencidos, 1);
});

// ── As exceções ───────────────────────────────────────────────────────────

test("folha estourada é exceção que bloqueia o fechamento", () => {
  const exc = excecoesDoMes([
    folha({
      origem_id: 9, pessoa_nome: "Leomir Bonfim",
      detalhe: [
        linha({ tipo: "bruto", descricao: "Salário", provento: 3200 }),
        linha({ tipo: "vale", descricao: "Vale — ração", desconto: 4880.54 }),
      ],
    }),
  ]);
  assert.equal(exc.length, 1);
  assert.equal(exc[0].gravidade, "bloqueia");
  assert.deepEqual(exc[0].folhaIds, [9]);
  assert.equal(exc[0].valor, 1680.54);
});

test("recibo que não soma o líquido pago é exceção — o achado mais grave, ainda vivo", () => {
  const exc = excecoesDoMes([folha({ origem_id: 4, status: "pago", data_pagamento: "2026-09-05", valor: 2000 })]);
  assert.equal(exc.length, 1);
  assert.equal(exc[0].id, "nao-soma-4");
  assert.equal(exc[0].gravidade, "bloqueia");
  assert.equal(exc[0].valor, 155.68);
});

test("um centavo de diferença não vira exceção — é a tolerância do arredondamento", () => {
  assert.deepEqual(excecoesDoMes([folha({ valor: 1844.31 })]), []);
});

test("retenção editada à mão que não bate com o percentual pede conferência", () => {
  const exc = excecoesDoMes([
    folha({
      origem_id: 5,
      detalhe: [
        linha({ tipo: "bruto", descricao: "Salário", provento: 2000 }),
        linha({
          tipo: "inss", descricao: "INSS", referencia: "7,78% sobre R$ 2.000,00 · valor ajustado à mão",
          desconto: 200,
          origem: { tipo: "retencao", percentual: 7.78, base: 2000, confere: false, diferenca: 44.32 },
        }),
      ],
    }),
  ]);
  assert.equal(exc.length, 1);
  assert.equal(exc[0].gravidade, "conferir");
  assert.equal(exc[0].valor, 200);
});

test("retenção SEM percentual não é exceção — a linha não some mais do recibo", () => {
  // Era o cartão nº 3 do desenho aprovado; o bug foi corrigido no backend
  // (`_detalhe_folha` testa o VALOR, não o percentual). Construir o cartão
  // ensinaria o usuário a ignorar o painel.
  const exc = excecoesDoMes([
    folha({
      detalhe: [
        linha({ tipo: "bruto", descricao: "Salário", provento: 2000 }),
        linha({
          tipo: "inss", descricao: "INSS", referencia: "Valor informado, sem percentual", desconto: 155.68,
          origem: { tipo: "retencao", percentual: null, base: null, confere: null, diferenca: null },
        }),
      ],
    }),
  ]);
  assert.deepEqual(exc, []);
});

test("folha em dia, com retenção que confere, não gera exceção nenhuma", () => {
  assert.deepEqual(excecoesDoMes([folha(), avulso()]), []);
});

test("vencidos de todos os tipos entram num cartão só, com o total", () => {
  const exc = excecoesDoMes([
    folha({ origem_id: 1, vencido: true }),
    avulso({ origem_id: 2, tipo: "empreita", pessoa_nome: "Zé da Obra", valor: 6400, status: "pendente", data_pagamento: null, vencido: true }),
  ]);
  assert.equal(exc.length, 1);
  assert.equal(exc[0].id, "vencidos");
  assert.equal(exc[0].valor, 8244.32);
  assert.deepEqual(exc[0].folhaIds, [1]);
});

test("o que bloqueia vem antes do que é só conferência, e o maior valor primeiro", () => {
  const exc = excecoesDoMes([
    folha({ origem_id: 1, vencido: true }),
    folha({
      origem_id: 2, pessoa_nome: "Leomir Bonfim",
      detalhe: [
        linha({ tipo: "bruto", descricao: "Salário", provento: 3200 }),
        linha({ tipo: "vale", descricao: "Vale — ração", desconto: 4880.54 }),
      ],
    }),
  ]);
  assert.deepEqual(exc.map((e) => e.gravidade), ["bloqueia", "conferir"]);
});

// ── A situação do mês ─────────────────────────────────────────────────────

test("mês sem lançamento não é 'fechado', é vazio — o sistema não guarda fechamento", () => {
  assert.equal(situacaoDoMes([], []).estado, "vazio");
});

test("erro que bloqueia domina o selo, mesmo com tudo pago", () => {
  const estourada = folha({
    origem_id: 9, status: "pago", data_pagamento: "2026-09-05",
    detalhe: [
      linha({ tipo: "bruto", descricao: "Salário", provento: 3200 }),
      linha({ tipo: "vale", descricao: "Vale", desconto: 4880.54 }),
    ],
  });
  const s = situacaoDoMes([estourada], excecoesDoMes([estourada]));
  assert.equal(s.estado, "bloqueado");
});

test("tudo pago e sem exceção é o estado verde; com pendência, 'em aberto'", () => {
  const paga = folha({ status: "pago", data_pagamento: "2026-09-05" });
  assert.equal(situacaoDoMes([paga], []).estado, "pago");
  assert.equal(situacaoDoMes([paga, folha({ origem_id: 2 })], []).estado, "aberto");
  assert.match(situacaoDoMes([paga, folha({ origem_id: 2 })], []).texto, /1 de 2 pagos/);
});
