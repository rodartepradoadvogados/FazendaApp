import test from "node:test";
import assert from "node:assert/strict";
import { interpretarLinhas, lerCsv, paraDataISO, paraNumero } from "./planilhaLote.ts";

const contas = [{ codigo: "3.01.02.01", nome: "Combustível" }, { codigo: "3.02.01", nome: "Manutenção" }];
const cab = ["Tipo de documento", "Número", "Data", "Tipo do item", "Produto ou serviço", "Conta gerencial", "Quantidade", "Valor unitário", "Desconto da nota", "Acréscimo da nota"];

test("números e datas no padrão brasileiro e do Excel", () => {
  assert.equal(paraNumero("1.234,56"), 1234.56);
  assert.equal(paraNumero("R$ 5,89"), 5.89);
  assert.equal(paraNumero("12.5"), 12.5);
  assert.equal(paraNumero(""), null);
  assert.equal(paraDataISO("03/10/2026"), "2026-10-03");
  assert.equal(paraDataISO("2026-10-03"), "2026-10-03");
  assert.equal(paraDataISO(46298), "2026-10-03");
  assert.equal(paraDataISO("31/02/2026"), null);
});

test("agrupa linhas em notas e resolve conta por código e por nome", () => {
  const r = interpretarLinhas([cab,
    ["Nota fiscal", "48213", "03/10/2026", "serviço", "Lavagem", "3.02.01", 2, 60, 0, 0],
    ["Nota fiscal", "48390", "05/10/2026", "produto", "Óleo diesel", "combustivel", "40", "5,89", 0, 0],
    ["Nota fiscal", "48390", "05/10/2026", "serviço", "Filtro", "", 1, 80, 10, 0]], contas, ["Óleo diesel"]);
  assert.deepEqual(r.erros, []);
  assert.equal(r.notas.length, 2);
  assert.equal(r.notas[1].itens.length, 2);
  assert.equal(r.notas[1].desconto, 10);
  assert.equal(r.notas[0].itens[0].codigo, "3.02.01");
  assert.equal(r.notas[1].itens[0].codigo, "3.01.02.01");
  assert.equal(r.notas[1].itens[0].qtd, "40");
  assert.equal(r.notas[1].itens[0].unit, 5.89);
});

test("erros: coluna faltando, data, quantidade de produto, nota repetida em blocos", () => {
  assert.match(interpretarLinhas([["Número", "Data"]], contas, []).erros[0], /Faltam colunas/);
  const r = interpretarLinhas([cab,
    ["", "1", "xx", "", "A", "", 1, 10, 0, 0],
    ["", "2", "03/10/2026", "produto", "Óleo", "", "", 10, 0, 0],
    ["", "3", "03/10/2026", "serviço", "B", "", 1, 10, 0, 0],
    ["", "4", "03/10/2026", "serviço", "C", "", 1, 10, 0, 0],
    ["", "3", "03/10/2026", "serviço", "D", "", 1, 10, 0, 0]], contas, ["Óleo"]);
  assert.equal(r.erros.length, 3);
  assert.match(r.erros.join("|"), /data inválida/);
  assert.match(r.erros.join("|"), /quantidade do produto/);
  assert.match(r.erros.join("|"), /dois blocos/);
});

test("avisos: conta e produto não encontrados; número em branco vira sem número", () => {
  const r = interpretarLinhas([cab, ["", "", "03/10/2026", "produto", "Algo", "9.9.9", 1, 10, 0, 0]], contas, []);
  assert.equal(r.notas[0].semNumero, true);
  assert.equal(r.avisos.length, 2);
});

test("csv com ponto e vírgula e aspas", () => {
  const m = lerCsv('Número;Data;Produto ou serviço;Valor unitário\n1;03/10/2026;"Lavagem; completa";60,00\n');
  assert.equal(m[1][2], "Lavagem; completa");
  assert.equal(m[1][3], "60,00");
});
