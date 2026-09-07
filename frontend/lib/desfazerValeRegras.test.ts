// Testes de frontend/lib/desfazerValeRegras.ts — a prévia das duas voltas
// atrás sobre um vale. Rodam com o runner nativo do Node: `npm test`.
//
// O que estes testes travam: a prévia da tela tem de dizer EXATAMENTE o que o
// servidor vai gravar. O caso real é o do dono — 12 parcelas de R$ 985,00 e um
// abatimento de R$ 167,85 lançado por engano, que as deixou em R$ 971,01 (a
// última R$ 971,04). Se a conta daqui divergir da de `_reescalar_parcelas`
// (rh_vale_acoes.py), a tela promete um número e o vale fica com outro — que é
// justamente o tipo de surpresa que fez estas ações existirem.
import { test } from "node:test";
import assert from "node:assert/strict";
import type { ValeAcaoContexto } from "./api.ts";
import {
  competenciaAlvoDoVale, previaEstorno, reescalarParcelas, valorDaReversao,
} from "./desfazerValeRegras.ts";

type Parcela = ValeAcaoContexto["parcelas"][number];

function parcela(over: Partial<Parcela>): Parcela {
  return {
    id: 1, competencia: "2026-08", valor: 985, assumida_pela_fazenda: false,
    motivo_assuncao: null, pendente: true, competencia_paga: false, ...over,
  };
}

function contexto(over: Partial<ValeAcaoContexto>): ValeAcaoContexto {
  const parcelas = over.parcelas ?? [];
  return {
    vale_id: 7, status: "ativo", valor_total: 11820, valor_abatido: 0, valor_assumido_fazenda: 0,
    saldo_pendente: parcelas.filter((p) => p.pendente).reduce((s, p) => s + p.valor, 0),
    parcelas, acoes_disponiveis: [], competencias_revertiveis: [], ...over,
  };
}

/** O vale do caso real, já com o abatimento de R$ 167,85 rateado. */
const DOZE_PARCELAS_ABATIDAS = contexto({
  valor_abatido: 167.85,
  parcelas: Array.from({ length: 12 }, (_, i) => parcela({
    id: i + 1,
    competencia: `2026-${String(i + 8).padStart(2, "0")}`,
    valor: i === 11 ? 971.04 : 971.01,
  })),
});

test("o estorno em branco devolve o abatimento inteiro e reconstitui as parcelas ao centavo", () => {
  const previa = previaEstorno(DOZE_PARCELAS_ABATIDAS, "");
  assert.equal(previa.valor, 167.85);
  assert.equal(previa.saldoAtual, 11652.15);
  assert.equal(previa.saldoNovo, 11820);
  assert.deepEqual(previa.linhas.map((l) => l.para), Array.from({ length: 12 }, () => 985));
  assert.equal(previa.impedimento, null);
});

test("o rateio é proporcional ao peso de hoje, com a última absorvendo o arredondamento", () => {
  // Mesma conta de `_reescalar_parcelas` no servidor, no sentido do abatimento:
  // 12 × 985 → 11.652,15 dá 971,01 em onze e 971,04 na última.
  const pendentes = Array.from({ length: 12 }, (_, i) => parcela({ id: i + 1, valor: 985 }));
  assert.deepEqual(
    reescalarParcelas(pendentes, 11820, 11652.15),
    [...Array.from({ length: 11 }, () => 971.01), 971.04],
  );
});

test("estorno parcial só devolve o pedaço informado", () => {
  const ctx = contexto({
    valor_abatido: 300,
    parcelas: [1, 2, 3].map((i) => parcela({ id: i, competencia: `2026-0${6 + i}`, valor: 200 })),
  });
  const previa = previaEstorno(ctx, "150");
  assert.equal(previa.saldoNovo, 750);
  assert.deepEqual(previa.linhas.map((l) => l.para), [250, 250, 250]);
  assert.equal(previa.impedimento, null);
});

test("parcela já descontada em folha paga não recebe estorno — só as pendentes entram", () => {
  const ctx = contexto({
    valor_abatido: 300,
    parcelas: [
      parcela({ id: 1, competencia: "2026-07", valor: 200, pendente: false, competencia_paga: true }),
      parcela({ id: 2, competencia: "2026-08", valor: 200 }),
      parcela({ id: 3, competencia: "2026-09", valor: 200 }),
    ],
  });
  const previa = previaEstorno(ctx, "200");
  assert.deepEqual(previa.linhas, [
    { competencia: "2026-08", de: 200, para: 300 },
    { competencia: "2026-09", de: 200, para: 300 },
  ]);
});

test("a prévia recusa antes do clique o que o servidor recusaria depois", () => {
  const semAbatimento = contexto({ parcelas: [parcela({ valor: 300 })] });
  assert.match(previaEstorno(semAbatimento, "").impedimento || "", /não tem abatimento/);

  const ctx = contexto({ valor_abatido: 300, parcelas: [parcela({ valor: 200 })] });
  assert.match(previaEstorno(ctx, "0").impedimento || "", /maior que zero/);
  assert.match(previaEstorno(ctx, "500").impedimento || "", /300\.00 disponíveis/);

  // Abatimento que zerou o vale: as parcelas foram apagadas e não há onde
  // devolver o valor — a tela diz isso em vez de deixar o dono levar o 400.
  const semPendentes = contexto({ valor_abatido: 900, parcelas: [] });
  assert.match(previaEstorno(semPendentes, "").impedimento || "", /reparcele/i);
});

test("o valor da reversão é o das parcelas assumidas daquele mês, não do vale inteiro", () => {
  const ctx = contexto({
    valor_assumido_fazenda: 500,
    parcelas: [
      parcela({ id: 1, competencia: "2026-07", valor: 300, assumida_pela_fazenda: true, pendente: false }),
      parcela({ id: 2, competencia: "2026-08", valor: 200, assumida_pela_fazenda: true, pendente: false }),
      parcela({ id: 3, competencia: "2026-09", valor: 400 }),
    ],
  });
  assert.equal(valorDaReversao(ctx, "2026-07"), 300);
  assert.equal(valorDaReversao(ctx, "2026-09"), 0, "mês não assumido não tem o que reverter");
});

// ── Qual mês "Desconsiderar" marca quando o menu é aberto pelo card de vales ──
// O menu de ações passou a ter duas portas: o painel de descontos de uma folha
// (onde o mês é o daquela linha) e o card "Vales de funcionário" (onde a linha
// é o vale inteiro e não há mês implícito). A segunda porta é a que faltava —
// era ela que o dono foi procurar —, e a escolha do mês ali não pode ser um
// palpite da tela: tem de ser o mês que o servidor aceitaria.

test("aberto pela folha, o mês é o daquela linha — mesmo que já esteja pago", () => {
  // A competência da linha manda porque a decisão é sobre AQUELE holerite; se
  // o mês não puder receber a ação, quem recusa (com a explicação certa) é o
  // servidor — a tela não desvia para outro mês por conta própria.
  const ctx = contexto({
    parcelas: [
      parcela({ id: 1, competencia: "2026-07", valor: 300, pendente: false, competencia_paga: true }),
      parcela({ id: 2, competencia: "2026-08", valor: 300 }),
    ],
  });
  assert.equal(competenciaAlvoDoVale(ctx, "2026-07"), "2026-07");
});

test("aberto pelo card de vales, o mês é a primeira parcela PENDENTE", () => {
  // Julho já caiu em folha paga e agosto foi assumido pela fazenda: nenhum dos
  // dois aceita "desconsiderar". O alvo é setembro.
  const ctx = contexto({
    parcelas: [
      parcela({ id: 1, competencia: "2026-07", valor: 300, pendente: false, competencia_paga: true }),
      parcela({
        id: 2, competencia: "2026-08", valor: 300, pendente: false,
        assumida_pela_fazenda: true, motivo_assuncao: "trator",
      }),
      parcela({ id: 3, competencia: "2026-09", valor: 300 }),
    ],
  });
  assert.equal(competenciaAlvoDoVale(ctx), "2026-09");
});

test("sem parcela pendente, cai na primeira parcela e deixa a recusa com o servidor", () => {
  // Vale inteiro descontado/assumido: não há mês a oferecer. A tela escreve o
  // primeiro só para ter rótulo; inventar um mês "livre" seria pior — o dono
  // confirmaria achando que ia funcionar.
  const ctx = contexto({
    parcelas: [
      parcela({ id: 1, competencia: "2026-07", valor: 300, pendente: false, assumida_pela_fazenda: true }),
      parcela({ id: 2, competencia: "2026-08", valor: 300, pendente: false, assumida_pela_fazenda: true }),
    ],
  });
  assert.equal(competenciaAlvoDoVale(ctx), "2026-07");
});

test("vale sem parcela nenhuma não quebra a tela", () => {
  // Abater o saldo inteiro apaga as parcelas (parcela de R$ 0,00 é ruído no
  // holerite) — e o card de vales continua mostrando o vale, com o botão.
  assert.equal(competenciaAlvoDoVale(contexto({ parcelas: [] })), "");
});
