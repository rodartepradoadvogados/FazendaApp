// Testes de frontend/lib/linhaTempoPessoa.ts — a linha do tempo de uma pessoa.
// Rodam com o runner nativo do Node (o projeto não tem jest/vitest): `npm test`.
//
// O que estas regras existem para impedir, e que estes testes travam:
//  - a parcela de vale ser datada por um desconto que não aconteceu (quando
//    não há folha naquela competência, ela não pode fingir que foi descontada);
//  - o vale e suas parcelas se soltarem: o que acende junto é o `vale_id`,
//    nunca o valor — dois vales com parcela de mesmo valor no mesmo mês eram
//    exatamente o caso em que a busca antiga terminava em palpite;
//  - "recebido no ano" contar o que ainda não foi pago, o que faria a
//    proporção "quanto do que recebe já está comprometido" mentir para baixo;
//  - a folha estourada aparecer como se a pessoa tivesse recebido.
import { test } from "node:test";
import assert from "node:assert/strict";
import type { LinhaFolhaUnificada } from "./api.ts";
import {
  descricaoVale, eventosDaPessoa, notaDoGrupo, resumoDaPessoa, type ValeDaLinhaTempo,
} from "./linhaTempoPessoa.ts";

/** Formatador injetado — cru, para o teste comparar texto sem depender de Intl. */
const brl = (v: number) => `R$ ${v.toFixed(2)}`;

function folha(over: Partial<LinhaFolhaUnificada> = {}): LinhaFolhaUnificada {
  return {
    tipo: "funcionario", origem_id: 1, origem_subtipo: "folha",
    pessoa_id: 3, pessoa_nome: "Leomir Bonfim",
    descricao: "Folha — 2026-08", valor: 2215,
    data_vencimento: "2026-09-05", data_pagamento: null,
    status: "pendente", pode_excluir: true, vencido: false,
    competencia: "2026-08",
    totais: { total_proventos: 3200, total_descontos: 985, liquido: 2215, liquido_negativo: false, excedente: 0 },
    ...over,
  } as LinhaFolhaUnificada;
}

function vale(over: Partial<ValeDaLinhaTempo> = {}): ValeDaLinhaTempo {
  return {
    id: 12, pessoa_id: 3, valor_total: 12805, data_pagamento: "2026-03-12",
    forma_pagamento: "pix", observacao: "adiantamento",
    numero_lancamento_gerado: "LC-2026-00214",
    parcelas_detalhe: [
      { id: 1, competencia: "2026-06", valor: 985, aplicada: true },
      { id: 2, competencia: "2026-07", valor: 985, aplicada: true },
      { id: 3, competencia: "2026-08", valor: 985, aplicada: false },
    ],
    origem_lancamento: null,
    ...over,
  };
}

test("o vale ganha nome pela nota fiscal quando nasceu de item de nota", () => {
  assert.equal(
    descricaoVale(vale({ origem_lancamento: { numero_documento: "4471", produto: "Kit embreagem", fornecedor_cliente: "Auto Peças" } })),
    "Vale — nota 4471 (Kit embreagem)",
  );
  assert.equal(descricaoVale(vale({ observacao: "mercado", origem_lancamento: null })), "Vale — mercado");
  assert.equal(descricaoVale(vale({ observacao: "  ", origem_lancamento: null })), "Vale");
});

test("a linha do tempo mistura pagamento, vale e parcela, do mais recente ao mais antigo", () => {
  const eventos = eventosDaPessoa([folha()], [vale()], 3, brl);
  // 1 folha + 1 vale + 3 parcelas.
  assert.equal(eventos.length, 5);
  assert.equal(eventos[eventos.length - 1].id, "vale-12"); // março, o mais antigo
  const datas = eventos.map((e) => e.data);
  assert.deepEqual(datas, [...datas].sort().reverse());
});

test("a parcela cai na data da folha que a absorveu", () => {
  const eventos = eventosDaPessoa([folha({ data_pagamento: "2026-09-05", status: "pago" })], [vale()], 3, brl);
  const parcela = eventos.find((e) => e.id === "parcela-3")!;
  assert.equal(parcela.data, "2026-09-05");
  // No mesmo dia, o pagamento vem antes da parcela que ele absorveu.
  assert.ok(eventos.findIndex((e) => e.sentido === "recebe") < eventos.indexOf(parcela));
});

test("parcela sem folha na competência não finge desconto — fica na competência e diz que falta", () => {
  // Sem nenhuma folha lançada: a parcela de 2026-08 não tem data de desconto.
  const eventos = eventosDaPessoa([], [vale()], 3, brl);
  const parcela = eventos.find((e) => e.id === "parcela-3")!;
  assert.equal(parcela.data, "2026-08-01");
  assert.equal(parcela.selo, "A descontar");
  assert.match(parcela.sub, /ainda não descontada/);
});

test("o que acende junto é o vale_id — nunca o valor da parcela", () => {
  const outro = vale({
    id: 99, valor_total: 985, data_pagamento: "2026-08-02", observacao: "mercado",
    // Mesmo valor de parcela, mesma competência: era o caso sem desempate.
    parcelas_detalhe: [{ id: 90, competencia: "2026-08", valor: 985, aplicada: false }],
  });
  const eventos = eventosDaPessoa([folha()], [vale(), outro], 3, brl);
  const grupos = eventos.filter((e) => e.grupo === "vale-99").map((e) => e.id);
  assert.deepEqual(grupos.sort(), ["parcela-90", "vale-99"]);
  assert.ok(eventos.filter((e) => e.grupo === "vale-12").length === 4);
});

test("folha estourada mostra o excedente, não um recebimento", () => {
  const estourada = folha({
    valor: -1680.54,
    totais: { total_proventos: 3200, total_descontos: 4880.54, liquido: -1680.54, liquido_negativo: true, excedente: 1680.54 },
  });
  const evento = eventosDaPessoa([estourada], [], 3, brl)[0];
  assert.equal(evento.tom, "estourada");
  assert.equal(evento.valor, 1680.54);
  assert.match(evento.sub, /descontos passam os vencimentos/);
});

test("vale de desconto integral em folha diz que não houve saída de caixa", () => {
  const eventos = eventosDaPessoa([], [vale({ forma_pagamento: "desconto_integral_folha", numero_lancamento_gerado: null })], 3, brl);
  assert.match(eventos.find((e) => e.id === "vale-12")!.sub, /sem saída de caixa/);
});

test("a linha do tempo é de UMA pessoa — nada de outra entra", () => {
  const eventos = eventosDaPessoa(
    [folha(), folha({ origem_id: 2, pessoa_id: 8 })],
    [vale(), vale({ id: 44, pessoa_id: 8 })],
    3, brl,
  );
  assert.ok(!eventos.some((e) => e.id === "funcionario-folha-2" || e.id === "vale-44"));
});

test("recebido no ano conta só o que foi PAGO — o previsto mentiria para baixo", () => {
  const r = resumoDaPessoa(
    [
      folha({ origem_id: 1, status: "pago", data_pagamento: "2026-08-05", valor: 2215 }),
      folha({ origem_id: 2, status: "pendente", valor: 2215 }),
      folha({ origem_id: 3, status: "pago", data_pagamento: "2025-08-05", valor: 2000 }),
    ],
    [vale()], 3, "2026",
  );
  assert.equal(r.recebidoNoAno, 2215);
  assert.equal(r.pagamentosNoAno, 1);
  assert.equal(r.valeTiradoNoAno, 12805);
  assert.equal(r.valesNoAno, 1);
  assert.equal(r.proporcaoValeSobreRecebido, 5.78);
});

test("o saldo de vale em aberto é só o que ainda não foi descontado", () => {
  const r = resumoDaPessoa([], [vale()], 3, "2026");
  assert.equal(r.saldoValesAberto, 985);
  assert.equal(r.parcelasAberto, 1);
  assert.equal(r.proporcaoValeSobreRecebido, null);
});

test("competência estourada é listada com o excedente", () => {
  const r = resumoDaPessoa(
    [folha({ valor: -1680.54, totais: { total_proventos: 3200, total_descontos: 4880.54, liquido: -1680.54, liquido_negativo: true, excedente: 1680.54 } })],
    [], 3, "2026",
  );
  assert.deepEqual(r.competenciasEstouradas, [{ competencia: "2026-08", excedente: 1680.54 }]);
});

test("a nota do grupo conta o que já saiu, o que falta e em que meses", () => {
  const nota = notaDoGrupo([vale()], "vale-12", brl)!;
  assert.match(nota.titulo, /Vale — adiantamento de R\$ 12805\.00/);
  assert.match(nota.texto, /Tirado em 12\/03\/2026/);
  assert.match(nota.texto, /2 de 3 já foram descontadas/);
  assert.match(nota.texto, /Faltam 1 \(R\$ 985\.00 a descontar\), em ago\/2026/);
  assert.equal(notaDoGrupo([vale()], "vale-999", brl), null);
});
