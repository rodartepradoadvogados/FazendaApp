import { test } from "node:test";
import assert from "node:assert/strict";
import {
  anoAnterior, brl, brlSinal, comparacaoDe, delta, deslocar, escreverContexto, ESTADO_INICIAL, formatar, formatarDelta,
  lerContexto, opcoesPeriodo, pct, periodoDe, periodoPadrao, resumoContexto, somaMeses,
} from "./relatorioContexto.ts";

const HOJE = "2026-10-09";

test("período: mês, trimestre, safra jul–jun, ano e livre", () => {
  assert.deepEqual(periodoDe("m:2026-02"), {
    tipo: "m", val: "2026-02", cod: "m:2026-02", ini: "2026-02-01", fim: "2026-02-28", label: "fevereiro/2026", curto: "fev/26",
  });
  const t = periodoDe("t:2026-T3")!;
  assert.equal(t.ini, "2026-07-01"); assert.equal(t.fim, "2026-09-30"); assert.equal(t.label, "3º trimestre de 2026");
  const s = periodoDe("s:2025")!;
  assert.equal(s.ini, "2025-07-01"); assert.equal(s.fim, "2026-06-30"); assert.equal(s.label, "safra 2025/26"); assert.equal(s.curto, "safra 25/26");
  assert.equal(periodoDe("a:2024")!.fim, "2024-12-31");
  // Livre: datas invertidas são reordenadas; data impossível é recusada.
  assert.equal(periodoDe("l:2026-09-30~2026-08-01")!.cod, "l:2026-08-01~2026-09-30");
  assert.equal(periodoDe("l:2026-02-30~2026-03-01"), null);
  for (const ruim of ["", "m:2026-13", "t:2026-T5", "x:2026", "m2026-01", null]) assert.equal(periodoDe(ruim as string), null, String(ruim));
});

test("padrões: o último período fechado de cada tipo a partir de hoje", () => {
  assert.equal(periodoPadrao("m", HOJE).cod, "m:2026-09");
  assert.equal(periodoPadrao("t", HOJE).cod, "t:2026-T3");
  assert.equal(periodoPadrao("t", "2026-02-10").cod, "t:2025-T4");
  assert.equal(periodoPadrao("s", HOJE).cod, "s:2025"); // safra 2025/26 fechou em jun/26
  assert.equal(periodoPadrao("s", "2026-03-01").cod, "s:2024");
  assert.equal(periodoPadrao("a", HOJE).cod, "a:2025");
  assert.equal(periodoPadrao("l", HOJE).cod, "l:2026-08-01~2026-09-30");
  assert.equal(periodoPadrao("m", "2026-01-15").cod, "m:2025-12"); // vira o ano
});

test("comparação: período anterior, ano passado, outro e orçado", () => {
  const set = periodoDe("m:2026-09")!;
  assert.equal(deslocar(set, -1).cod, "m:2026-08");
  assert.equal(anoAnterior(set).cod, "m:2025-09");
  assert.equal(deslocar(periodoDe("t:2026-T1")!, -1).cod, "t:2025-T4");
  assert.equal(anoAnterior(periodoDe("t:2026-T1")!).cod, "t:2025-T1");
  assert.equal(anoAnterior(periodoDe("s:2025")!).cod, "s:2024");
  // Livre: o bloco imediatamente anterior, do mesmo tamanho; ano passado com fim de mês ajustado.
  const livre = periodoDe("l:2026-03-01~2026-03-31")!;
  assert.equal(deslocar(livre, -1).cod, "l:2026-01-29~2026-02-28");
  assert.equal(anoAnterior(periodoDe("l:2024-02-29~2024-03-10")!).cod, "l:2023-02-28~2023-03-10");

  const ant = comparacaoDe(set, "ant");
  assert.ok(ant && ant.tipo === "periodo" && ant.periodo.cod === "m:2026-08" && ant.rotulo === "ago/26");
  const aa = comparacaoDe(set, "aa");
  assert.ok(aa && aa.tipo === "periodo" && aa.periodo.cod === "m:2025-09" && !aa.escolhido);
  const outro = comparacaoDe(set, "outro", "m:2026-03");
  assert.ok(outro && outro.tipo === "periodo" && outro.periodo.cod === "m:2026-03" && outro.escolhido);
  // "Outro" sem período escolhido cai no anterior (nunca compara com nada).
  const semEscolha = comparacaoDe(set, "outro", "");
  assert.ok(semEscolha && semEscolha.tipo === "periodo" && semEscolha.periodo.cod === "m:2026-08");
  assert.deepEqual(comparacaoDe(set, "orc"), { tipo: "orcado", rotulo: "orçado" });
  assert.equal(comparacaoDe(set, "nada"), null);
});

test("URL: lê com padrão para o que faltar, escreve preservando os outros parâmetros", () => {
  const padrao = ESTADO_INICIAL(HOJE, "Pecuária Leiteira");
  assert.deepEqual(padrao, { per: "m:2026-09", cmp: "aa", cmpp: "", reg: "comp", cc: "Pecuária Leiteira" });
  assert.deepEqual(lerContexto("?sub=rel_dre", padrao), padrao);
  const e = lerContexto("?sub=rel_dre&per=t:2026-T2&cmp=outro&cmpp=t:2025-T2&reg=caixa&cc=todos", padrao);
  assert.deepEqual(e, { per: "t:2026-T2", cmp: "outro", cmpp: "t:2025-T2", reg: "caixa", cc: "todos" });
  // Lixo na URL não quebra a tela: volta o padrão campo a campo.
  assert.deepEqual(lerContexto("?per=m:2026-99&cmp=xyz&reg=foo&cmpp=nada", padrao), padrao);
  const qs = escreverContexto("sub=rel_dre&per=m:2020-01", { ...e, cc: "Pecuária Leiteira" });
  const q = new URLSearchParams(qs);
  assert.equal(q.get("sub"), "rel_dre");
  assert.equal(q.get("per"), "t:2026-T2");
  assert.equal(q.get("cc"), "Pecuária Leiteira");
  assert.equal(q.get("cmpp"), "t:2025-T2");
  // Ida e volta: o que se escreve é o que se lê.
  assert.deepEqual(lerContexto(`?${qs}`, padrao), { ...e, cc: "Pecuária Leiteira" });
  // cmpp só vai para a URL com "outro".
  assert.equal(new URLSearchParams(escreverContexto("", { ...e, cmp: "aa" })).get("cmpp"), null);
});

test("opções do seletor: mais recente primeiro, em curso marcado e o atual sempre presente", () => {
  const meses = opcoesPeriodo("m", HOJE);
  assert.equal(meses[0].v, "m:2026-10"); assert.equal(meses[0].rotulo, "outubro/2026 (em curso)");
  assert.equal(meses[1].v, "m:2026-09");
  assert.equal(meses.length, 37);
  assert.equal(opcoesPeriodo("t", HOJE)[0].v, "t:2026-T4");
  assert.equal(opcoesPeriodo("s", HOJE)[0].v, "s:2026");
  // Link compartilhado com um mês fora da lista (ex.: 2031) continua selecionável.
  assert.equal(opcoesPeriodo("m", HOJE, "m:2031-03")[0].v, "m:2031-03");
  assert.equal(somaMeses("2026-01", -1), "2025-12");
});

test("variação com sentido: custo que sobe é pior, receita que sobe é melhor, empate é igual", () => {
  assert.deepEqual(delta(110, 100, "sobe"), { abs: 10, pct: 0.1, igual: false, melhor: true });
  assert.equal(delta(110, 100, "desce")!.melhor, false);
  assert.equal(delta(110, 100, "neutro")!.melhor, null);
  assert.equal(delta(100, 100)!.igual, true);
  assert.equal(delta(5, 0)!.pct, null);
  assert.equal(delta(null, 3), null);
  assert.equal(delta(-50, -100, "sobe")!.melhor, true); // prejuízo menor é melhor
});

test("formatação pt-BR com sinal de menos tipográfico", () => {
  assert.equal(brl(-1234.5), "−R$ 1.234,50");
  assert.equal(brl(-0.001), "R$ 0,00");
  assert.equal(brlSinal(10), "+R$ 10,00");
  assert.equal(pct(0.0749), "7,5%");
  assert.equal(formatar(-2.5, "pct"), "−2,5%");
  assert.equal(formatar(10320, "litros"), "10.320 L");
  assert.equal(formatarDelta(-1.2, "pct"), "−1,2 p.p.");
  assert.equal(formatarDelta(462.1, "brl0"), "+R$ 462");
  const set = periodoDe("m:2026-09")!;
  assert.equal(resumoContexto(set, comparacaoDe(set, "aa"), "comp", "Pecuária Leiteira"), "set/26 · vs set/25 · mês do gasto · Pecuária Leiteira");
  assert.equal(resumoContexto(set, null, "caixa", "todos"), "set/26 · dia do pagamento · todos os centros");
});
