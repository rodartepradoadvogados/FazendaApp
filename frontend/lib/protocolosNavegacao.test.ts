// Central de Protocolos: URLs antigas → hierarquia nova, URLs novas de ida e
// volta, e os filtros por grupo (vacina / exame / outros preventivos).
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  diaNoGrupo, grupoDoDia, grupoDoTipo, lerUrlCentral, linkCentral, navParaAba, tipoInicialDoGrupo, tipoNoGrupo, urlCentral,
} from "./protocolosNavegacao.ts";

test("sem querystring abre em Acompanhamento › Todos", () => {
  const r = lerUrlCentral("");
  assert.deepEqual(r.nav, { aba: "acompanhamento", area: "", san: "curativo", grupo: "vacina" });
  assert.equal(r.resolver, null);
});

test("URLs antigas da aba Vacinas e exames viram Cadastro/Aplicar › Sanitário › Preventivo", () => {
  const cad = lerUrlCentral("?aba=vacinas&sub=cadastro");
  assert.deepEqual(cad.nav, { aba: "cadastro", area: "sanitario", san: "preventivo", grupo: "vacina" });
  assert.equal(cad.resolver, null);

  const so = lerUrlCentral("?aba=vacinas");
  assert.equal(so.nav.aba, "cadastro");

  const passo = lerUrlCentral("?aba=vacinas&sub=cadastro&caixa=3&passo=7");
  assert.equal(passo.nav.aba, "cadastro");
  assert.equal(passo.atalho.caixa, 3);
  assert.equal(passo.atalho.passo, 7);
  assert.deepEqual(passo.resolver, { caixa: 3 }, "sem tipo, descobre o grupo pela caixa");

  const marc = lerUrlCentral("?aba=vacinas&sub=marcados");
  assert.deepEqual(marc.nav, { aba: "aplicar", area: "sanitario", san: "preventivo", grupo: "vacina" });

  const dia = lerUrlCentral("?aba=vacinas&sub=marcados&dia=7");
  assert.equal(dia.nav.aba, "aplicar");
  assert.equal(dia.atalho.dia, 7);
  assert.deepEqual(dia.resolver, { dia: 7 });

  const caixas = lerUrlCentral("?aba=vacinas&sub=marcados&caixas=4,5");
  assert.deepEqual(caixas.atalho.caixas, [4, 5]);
  assert.deepEqual(caixas.resolver, { caixa: 4 });

  const pares = lerUrlCentral("?aba=vacinas&sub=marcados&marcar=4-10,4-11,x-2");
  assert.deepEqual(pares.atalho.pares, [{ caixa_id: 4, animal_id: 10 }, { caixa_id: 4, animal_id: 11 }]);
  assert.deepEqual(pares.resolver, { caixa: 4 });

  // dia sem sub também é "marcados" (era assim na página antiga)
  assert.equal(lerUrlCentral("?aba=vacinas&dia=9").nav.aba, "aplicar");
});

test("abas antigas lancamento/historico e o ?tipo=iatf do Cadastro antigo", () => {
  assert.equal(lerUrlCentral("?aba=lancamento").nav.aba, "aplicar");
  assert.equal(lerUrlCentral("?aba=historico").nav.aba, "concluidos");
  const iatf = lerUrlCentral("?aba=cadastro&tipo=iatf");
  assert.equal(iatf.nav.area, "iatf");
  const san = lerUrlCentral("?aba=cadastro&tipo=sanitario");
  assert.equal(san.nav.area, "sanitario");
  assert.equal(san.nav.san, "curativo");
});

test("URL nova: ida e volta", () => {
  const casos = [
    { aba: "cadastro", area: "sanitario", san: "preventivo", grupo: "vacina" },
    { aba: "cadastro", area: "sanitario", san: "curativo", grupo: "vacina" },
    { aba: "cadastro", area: "lida", san: "curativo", grupo: "vacina" },
    { aba: "aplicar", area: "sanitario", san: "preventivo", grupo: "exame" },
    { aba: "aplicar", area: "iatf", san: "curativo", grupo: "vacina" },
    { aba: "acompanhamento", area: "", san: "curativo", grupo: "vacina" },
    { aba: "acompanhamento", area: "sanitario", san: "preventivo", grupo: "outros" },
    { aba: "concluidos", area: "sanitario", san: "preventivo", grupo: "exame" },
  ] as const;
  for (const c of casos) {
    const url = urlCentral(c);
    assert.deepEqual(lerUrlCentral(url).nav, c, url);
  }
  assert.equal(urlCentral({ aba: "cadastro", area: "sanitario", san: "preventivo", grupo: "vacina" }, { caixa: 3, passo: 7 }),
    "/protocolos?aba=cadastro&area=sanidade&san=preventiva&tipo=vacina&caixa=3&passo=7");
  assert.equal(urlCentral({ aba: "aplicar", area: "sanitario", san: "preventivo", grupo: "exame" }, { dia: 7 }),
    "/protocolos?aba=aplicar&area=sanitario&san=preventivo&tipo=exame&dia=7");
  // com tipo explícito, não precisa resolver pela API
  assert.equal(lerUrlCentral("?aba=aplicar&area=sanitario&san=preventivo&tipo=exame&dia=7").resolver, null);
  // tipo sozinho já implica Sanitário › Preventivo
  assert.deepEqual(lerUrlCentral("?aba=aplicar&tipo=outros").nav, { aba: "aplicar", area: "sanitario", san: "preventivo", grupo: "outros" });
  // "Todos" não existe em Cadastro/Aplicar
  assert.equal(lerUrlCentral("?aba=cadastro&area=todos").nav.area, "sanitario");
  assert.equal(lerUrlCentral("?aba=concluidos&area=todos").nav.area, "");
});

test("linkCentral: sem grupo a URL sai sem tipo e a página resolve", () => {
  const u = linkCentral.aplicarPreventivo({ dia: 12 });
  assert.equal(u, "/protocolos?aba=aplicar&area=sanitario&san=preventivo&dia=12");
  assert.deepEqual(lerUrlCentral(u).resolver, { dia: 12 });
  const c = linkCentral.cadastroPreventivo({ caixa: 5, passo: 7 });
  assert.equal(c, "/protocolos?aba=cadastro&area=sanidade&san=preventiva&caixa=5&passo=7");
  assert.deepEqual(lerUrlCentral(c).resolver, { caixa: 5 });
  assert.equal(linkCentral.cadastroPreventivo({}, "exame"), "/protocolos?aba=cadastro&area=sanidade&san=preventiva&tipo=exame");
  const m = linkCentral.aplicarPreventivo({ pares: [{ caixa_id: 2, animal_id: 9 }] });
  assert.deepEqual(lerUrlCentral(m).atalho.pares, [{ caixa_id: 2, animal_id: 9 }]);
});

test("navParaAba mantém o lugar e troca Todos por Sanitário onde Todos não existe", () => {
  const n = { aba: "acompanhamento", area: "", san: "preventivo", grupo: "exame" } as const;
  assert.deepEqual(navParaAba(n, "cadastro"), { aba: "cadastro", area: "sanitario", san: "preventivo", grupo: "exame" });
  assert.deepEqual(navParaAba({ ...n, area: "iatf" }, "concluidos"), { aba: "concluidos", area: "iatf", san: "preventivo", grupo: "exame" });
});

test("filtros por grupo: vacina, exame e outros (vermífugo, outro e qualquer tipo novo)", () => {
  assert.equal(grupoDoTipo("vacina"), "vacina");
  assert.equal(grupoDoTipo("exame"), "exame");
  assert.equal(grupoDoTipo("vermifugo"), "outros");
  assert.equal(grupoDoTipo("outro"), "outros");
  assert.equal(grupoDoTipo("carrapaticida"), "outros");
  assert.equal(grupoDoTipo(null), "outros");
  assert.ok(tipoNoGrupo("vacina", "vacina"));
  assert.ok(!tipoNoGrupo("exame", "vacina"));
  assert.ok(tipoNoGrupo("exame", null), "sem grupo = sem filtro");

  const misto = { tipo: "vacina", caixas: [{ tipo: "vacina" }, { tipo: "vermifugo" }] };
  assert.ok(diaNoGrupo(misto, "vacina"));
  assert.ok(diaNoGrupo(misto, "outros"));
  assert.ok(!diaNoGrupo(misto, "exame"));
  assert.ok(diaNoGrupo({ tipo: "exame", caixas: [] }, "exame"), "sem caixas, vale o tipo do dia");
  assert.equal(grupoDoDia(misto), "vacina");
  assert.equal(grupoDoDia({ tipo: "exame", caixas: [{ tipo: "exame" }] }), "exame");

  assert.equal(tipoInicialDoGrupo("vacina"), "vacina");
  assert.equal(tipoInicialDoGrupo("exame"), "exame");
  assert.equal(tipoInicialDoGrupo("outros"), "vermifugo");
});
