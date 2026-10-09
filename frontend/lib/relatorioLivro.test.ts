import { test } from "node:test";
import assert from "node:assert/strict";
import { documentoDe, fraseLivro, historicoDe, secoesLivro, temLivro, type LinhaLivro, type RespostaLivro } from "./relatorioLivro.ts";
import { brl, periodoDe } from "./relatorioContexto.ts";

const L = (data: string, o: Partial<LinhaLivro> = {}): LinhaLivro => ({
  data, id: 1, numero_lancamento: "LC-1", documento: null, historico: "Ração", fornecedor: "Coop", conta: null,
  receita: 0, despesa: 100, custeio: 100, investimento: 0, categoria: "custeio", saldo: -100, ...o,
});
const RESP = (o: Partial<RespostaLivro> = {}): RespostaLivro => ({
  periodo: { inicio: "2026-07-01", fim: "2026-09-30" }, regras_v2: true, separacao_fiscal: true,
  linhas: [L("2026-07-05"), L("2026-09-02", { receita: 1000, despesa: 0, custeio: 0, categoria: "receita", saldo: 900 })],
  meses: [
    { competencia: "2026-07", receitas: 0, custeio: 100, investimentos: 0, despesas: 100, resultado: -100, quantidade: 1 },
    { competencia: "2026-08", receitas: 0, custeio: 0, investimentos: 0, despesas: 0, resultado: 0, quantidade: 0 },
    { competencia: "2026-09", receitas: 1000, custeio: 0, investimentos: 0, despesas: 0, resultado: 1000, quantidade: 1 },
  ],
  totais: { receitas: 1000, custeio: 100, investimentos: 0, despesas: 100, resultado: 900, quantidade: 2 },
  presumido_20: 200, fora_do_livro: null, ponte_dre: null, avisos: [], ...o,
});

test("histórico e documento no formato do contador", () => {
  assert.equal(historicoDe({ fornecedor: "Coop", historico: "Ração" }), "Coop — Ração");
  assert.equal(historicoDe({ fornecedor: "Coop", historico: "coop" }), "Coop");
  assert.equal(historicoDe({ fornecedor: "", historico: "" }), "—");
  assert.equal(documentoDe({ documento: "NF 12", numero_lancamento: "LC-1" }), "NF 12");
  assert.equal(documentoDe({ documento: null, numero_lancamento: "LC-1" }), "LC-1");
});

test("seções por mês: só meses com lançamento, cada uma com o subtotal; filtro de um mês", () => {
  const s = secoesLivro(RESP());
  assert.deepEqual(s.map((x) => [x.mes.competencia, x.linhas.length, x.mes.resultado]), [["2026-07", 1, -100], ["2026-09", 1, 1000]]);
  assert.deepEqual(secoesLivro(RESP(), "2026-09").map((x) => x.mes.competencia), ["2026-09"]);
  assert.equal(temLivro(RESP({ linhas: [] })), false);
});

test("frase: regra fiscal com os 20% — e, sem as regras novas, o livro de antes", () => {
  const per = periodoDe("t:2026-T3")!;
  assert.equal(fraseLivro(per, RESP(), (v) => brl(v, 0)).map((t) => t.t).join(""),
    "Em 3º trimestre de 2026, pela regra do livro caixa, a atividade rural teve R$ 1.000 de receitas recebidas e R$ 100 de despesas pagas — " +
    "resultado de R$ 900. Pela opção de 20% da receita bruta, a base seria R$ 200.");
  assert.match(fraseLivro(per, RESP({ separacao_fiscal: false, presumido_20: null }), (v) => brl(v, 0)).map((t) => t.t).join(""), /separação fiscal chega com as regras novas\.$/);
});
