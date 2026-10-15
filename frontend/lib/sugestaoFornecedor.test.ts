import test from "node:test";
import assert from "node:assert/strict";
import { somarDias, sugestaoDoFornecedor, type LinhaExtrato } from "./sugestaoFornecedor.ts";

const nota = (numero: string, extra: Partial<LinhaExtrato> = {}): LinhaExtrato => ({
  tipo: "despesa", numero_lancamento: numero, fornecedor: "Cooperativa Regional", data_emissao: "2026-09-10", data_vencimento: "2026-10-10",
  parcela_num: 1, centro_custo: "Pecuária Leiteira", classificacao: "Custeio",
  itens: [{ produto: "Sal mineral", tipo_item: "produto", codigo_conta_gerencial: "3.01.01.03", nome_conta_gerencial: "Sal mineral e suplementos" }],
  ...extra,
});

test("pega o último lançamento do fornecedor (por emissão) e calcula o prazo", () => {
  const extrato = [
    nota("LC-1", { data_emissao: "2026-08-01", data_vencimento: "2026-08-11" }),
    nota("LC-2", { itens: [{ produto: "Ração 22%", tipo_item: "produto", codigo_conta_gerencial: "3.01.01.01", nome_conta_gerencial: "Concentrado" }] }),
  ];
  const s = sugestaoDoFornecedor(extrato, "  cooperativa regional ", "despesa");
  assert.ok(s);
  assert.equal(s.numeroLancamento, "LC-2");
  assert.equal(s.produto, "Ração 22%");
  assert.equal(s.codigoConta, "3.01.01.01");
  assert.equal(s.prazoDias, 30);
  assert.equal(s.centroCusto, "Pecuária Leiteira");
});

test("não mistura despesa com receita, nem outro fornecedor, nem notas automáticas", () => {
  const extrato = [
    nota("LC-1", { tipo: "receita" }),
    nota("LC-2", { fornecedor: "Outro" }),
    nota("LC-3", { gerado_por: "folha" }),
  ];
  assert.equal(sugestaoDoFornecedor(extrato, "Cooperativa Regional", "despesa"), null);
  assert.equal(sugestaoDoFornecedor(extrato, "", "despesa"), null);
});

test("ignora item de vale e usa o primeiro item real; prazo absurdo vira null", () => {
  const extrato = [nota("LC-1", {
    data_vencimento: "2027-12-31",
    itens: [
      { produto: "Ração do cachorro", tipo_item: "produto", eh_vale: true },
      { produto: "Serviço de frete", tipo_item: "servico", codigo_conta_gerencial: "3.04.01", nome_conta_gerencial: "Frete" },
    ],
  })];
  const s = sugestaoDoFornecedor(extrato, "Cooperativa Regional", "despesa");
  assert.ok(s);
  assert.equal(s.produto, "Serviço de frete");
  assert.equal(s.tipoItem, "servico");
  assert.equal(s.prazoDias, null);
});

test("'Sem centro de custo' do extrato não vira sugestão", () => {
  const s = sugestaoDoFornecedor([nota("LC-1", { centro_custo: "Sem centro de custo" })], "Cooperativa Regional", "despesa");
  assert.equal(s?.centroCusto, null);
});

test("somarDias atravessa mês e ano", () => {
  assert.equal(somarDias("2026-12-20", 30), "2027-01-19");
  assert.equal(somarDias("2026-10-15", 0), "2026-10-15");
});
