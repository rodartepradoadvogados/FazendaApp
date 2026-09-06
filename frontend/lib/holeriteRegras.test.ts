// Testes de frontend/lib/holeriteRegras.ts — as regras do documento de folha.
// Rodam com o runner nativo do Node (o projeto não tem jest/vitest): `npm test`.
//
// O que estas regras existem para impedir, e que estes testes travam:
//  - a tela de Contas montar um "holerite" a partir de um lançamento que não
//    tem discriminação nenhuma (empreita, contrato, diária são pagamentos de
//    valor único — um documento de colunas fixas sairia vazio);
//  - emitir recibo de uma folha em que os descontos passam os vencimentos: o
//    que existe ali não é um líquido, é um excedente;
//  - o cartão de origem de uma pessoa sobreviver à troca de documento (por
//    isso a chave viaja junto).
import { test } from "node:test";
import assert from "node:assert/strict";
import type { LinhaFolhaUnificada, LinhaHolerite } from "./api.ts";
import {
  competenciaExtenso, dataBR, ehOrigemRetencao, ehOrigemVale, holeriteDaLinha,
  linhasDoCorpo, podeEmitir, seloDocumento,
} from "./holeriteRegras.ts";

function linha(over: Partial<LinhaHolerite>): LinhaHolerite {
  return {
    label: "x", valor: 0, tipo: "bruto", descricao: "x", referencia: "",
    provento: null, desconto: null, origem: null, ...over,
  } as LinhaHolerite;
}

function ledger(over: Partial<LinhaFolhaUnificada> = {}): LinhaFolhaUnificada {
  return {
    tipo: "funcionario", origem_id: 7, origem_subtipo: "folha",
    pessoa_id: 3, pessoa_nome: "Leomir Bonfim",
    descricao: "Folha — 2026-07", valor: 2417.68,
    data_vencimento: "2026-08-05", data_pagamento: null,
    status: "pendente", pode_excluir: true, vencido: false,
    competencia: "2026-07",
    detalhe: [
      linha({ tipo: "bruto", descricao: "Salário", referencia: "Mensal", provento: 3200 }),
      linha({
        tipo: "vale", descricao: "Vale — mercado", referencia: "Parcela 3 de 13 · vale de 12/03/2026",
        desconto: 782.32,
        origem: {
          tipo: "vale", vale_id: 11, parcela_id: 42, parcela: 3, parcelas_total: 13,
          valor_total: 12805, data_pagamento: "2026-03-12", forma_pagamento: "pix",
          observacao: "mercado", numero_documento_pagamento: null,
          numero_lancamento_gerado: "LC-2026-00214", sem_saida_de_caixa: false,
          origem_lancamento: null, aplicada: true,
        },
      }),
      linha({ tipo: "liquido", descricao: "Líquido", referencia: "", valor: 2417.68 }),
    ],
    totais: {
      total_proventos: 3200, total_descontos: 782.32, liquido: 2417.68,
      liquido_negativo: false, excedente: 0,
    },
    bases: {
      salario_base: 3200, base_inss: null, base_ir: null,
      fgts_projetado: null, percentual_fgts: null, dctf_projetado: null,
    },
    ...over,
  };
}

test("competenciaExtenso escreve o mês por extenso, e devolve o cru quando não é competência", () => {
  assert.equal(competenciaExtenso("2026-07"), "Julho / 2026");
  assert.equal(competenciaExtenso("2026-03"), "Março / 2026");
  assert.equal(competenciaExtenso(""), "—");
  assert.equal(competenciaExtenso("qualquer coisa"), "qualquer coisa");
});

test("dataBR nunca inventa data quando não há data", () => {
  assert.equal(dataBR("2026-03-12"), "12/03/2026");
  assert.equal(dataBR(null), "—");
  assert.equal(dataBR(undefined), "—");
});

test("o líquido é rodapé, não linha do corpo do documento", () => {
  const doc = holeriteDaLinha(ledger())!;
  const corpo = linhasDoCorpo(doc.linhas);
  assert.equal(corpo.length, 2);
  assert.ok(!corpo.some((l) => l.tipo === "liquido"));
});

test("lançamento sem discriminação não vira documento", () => {
  // Empreita, contrato e diária: valor único, sem composição. Forçá-los no
  // formato de colunas fixas produziria um holerite vazio.
  assert.equal(holeriteDaLinha(ledger({ tipo: "empreita", detalhe: undefined, totais: undefined })), null);
  assert.equal(holeriteDaLinha(ledger({ detalhe: [] })), null);
});

test("a chave do documento distingue tipo, subtipo e origem", () => {
  // É ela que o estado da linha aberta carrega: sem isso, o cartão de origem
  // de uma pessoa continuaria aberto sob o nome de outra.
  assert.equal(holeriteDaLinha(ledger())!.chave, "funcionario-folha-7");
  assert.equal(
    holeriteDaLinha(ledger({ origem_subtipo: "ferias", origem_id: 9 }))!.chave,
    "funcionario-ferias-9",
  );
});

test("férias/13º são recibo, não holerite, e mantêm o próprio título", () => {
  const doc = holeriteDaLinha(ledger({
    tipo: "ferias_decimo", origem_subtipo: "ferias",
    descricao: "Férias — 2026-07-01 a 2026-07-20", competencia: undefined,
  }))!;
  assert.equal(doc.especie, "recibo");
  assert.equal(doc.competenciaLabel, "Férias — 2026-07-01 a 2026-07-20");
});

test("descontos maiores que vencimentos bloqueiam a emissão", () => {
  // A conta do print do dono: bruto 3.200,00 contra 4.880,54 de vales.
  const estourada = holeriteDaLinha(ledger({
    valor: -1680.54,
    totais: {
      total_proventos: 3200, total_descontos: 4880.54, liquido: -1680.54,
      liquido_negativo: true, excedente: 1680.54,
    },
  }))!;
  const veredito = podeEmitir(estourada);
  assert.equal(veredito.ok, false);
  assert.equal(veredito.ok === false && veredito.excedente, 1680.54);
  assert.equal(seloDocumento(estourada).texto, "NÃO EMITIDO");
});

test("selo do documento reflete o estado real, e pago vence estourado nunca", () => {
  assert.equal(seloDocumento(holeriteDaLinha(ledger())!).texto, "PRÉVIA");
  assert.equal(seloDocumento(holeriteDaLinha(ledger({ status: "pago", data_pagamento: "2026-08-05" }))!).texto, "PAGO");
  assert.equal(seloDocumento(holeriteDaLinha(ledger({ vencido: true }))!).texto, "VENCIDO");
  // Um documento que não fecha nunca é "PAGO" na tela, mesmo com status pago:
  // o número que aparece nele não é um líquido válido.
  const pagoEEstourado = holeriteDaLinha(ledger({
    status: "pago",
    totais: { total_proventos: 100, total_descontos: 300, liquido: -200, liquido_negativo: true, excedente: 200 },
  }))!;
  assert.equal(seloDocumento(pagoEEstourado).texto, "NÃO EMITIDO");
});

test("a origem do desconto é reconhecida por tipo, não por texto do rótulo", () => {
  // Era `/vale/i.test(d.label)`: um "Outros descontos — vale do mercado"
  // digitado à mão passaria por parcela de vale, e uma parcela sem a palavra
  // "vale" no rótulo sumiria.
  const doc = holeriteDaLinha(ledger())!;
  const parcela = doc.linhas.find((l) => l.tipo === "vale")!;
  assert.ok(ehOrigemVale(parcela.origem));
  assert.equal(ehOrigemVale(parcela.origem) && parcela.origem.vale_id, 11);
  assert.ok(!ehOrigemRetencao(parcela.origem));

  const bruto = doc.linhas.find((l) => l.tipo === "bruto")!;
  assert.ok(!ehOrigemVale(bruto.origem));
  assert.ok(!ehOrigemRetencao(bruto.origem));
});

test("competência ausente cai para o mês do vencimento em vez de ficar vazia", () => {
  const doc = holeriteDaLinha(ledger({ competencia: undefined, data_vencimento: "2026-08-05" }))!;
  assert.equal(doc.competencia, "2026-08");
});
