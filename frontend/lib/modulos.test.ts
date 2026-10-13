import { test } from "node:test";
import assert from "node:assert/strict";
import {
  type CtxModulos, ITENS_MENU, ROTA_MODULO, ROTA_MODULOS, MODULO_CONTRATO, contratoBloqueia, itensDoMenu, moduloContratado,
  moduloFrontContratado, podeModuloCtx, rotaInicial, temCapaUtil, temInsights, visivel, visivelNoMenu,
} from "./modulos.ts";

// Planos do catálogo (backend/fazenda/models/planos.py) + o novo Financeiro.
const STANDARD = ["rebanho", "reprodutivo"];
const GOLD = ["rebanho", "reprodutivo", "produtivo", "sanitario", "financeiro", "planejamento", "pedidos", "estoque", "alimentacao", "agricultura"];
const FINANCEIRO = ["financeiro", "pedidos"];

const ADMIN = ["capa", "agenda", "financeiro"]; // irrelevante para admin (tudo liberado)
function ctx(modulos: string[] | null, extra: Partial<CtxModulos> = {}): CtxModulos {
  return { papel: "admin", permissoes: ADMIN, modulosContratados: modulos, contratoStatus: "ativo", suporte: false, ...extra };
}
function operador(modulos: string[] | null, permissoes: string[], extra: Partial<CtxModulos> = {}): CtxModulos {
  return ctx(modulos, { papel: "operador", permissoes, ...extra });
}
const rotasMenu = (c: CtxModulos) => itensDoMenu(c).map((i) => i.href);

test("[financeiro,pedidos]: menu = Agenda, Controle Financeiro, Cotações, Pedidos; sem Capa/Insights", () => {
  const c = ctx(FINANCEIRO);
  assert.deepEqual(rotasMenu(c), ["/agenda", "/financeiro", "/cotacoes", "/pedidos"]);
  assert.equal(temCapaUtil(c), false);
  assert.equal(temInsights(c), false);
  for (const r of ["/", "/lancamentos", "/protocolos", "/rebanho", "/historico", "/estoque", "/indicadores", "/analise-reprodutiva", "/analise-relatorios", "/sanidade"]) {
    assert.equal(visivel(r, c), false, r);
  }
  assert.equal(visivel("/portal", c), true);
  assert.equal(visivel("/configuracoes", c), true);
});

test("[financeiro,pedidos]: página inicial é a Agenda (e nunca /app ou Capa)", () => {
  assert.equal(rotaInicial(ctx(FINANCEIRO)), "/agenda");
});

test("Standard: Capa, Rebanho, Histórico (reprodução) e Insights; sem Financeiro/Estoque/Pedidos", () => {
  const c = ctx(STANDARD, { permissoes: [] });
  assert.equal(temCapaUtil(c), true);
  assert.equal(rotaInicial(c), "/");
  for (const r of ["/", "/agenda", "/lancamentos", "/protocolos", "/rebanho", "/historico", "/reproducao", "/ciclos-21-dias", "/analise-reprodutiva", "/indicadores"]) {
    assert.equal(visivel(r, c), true, r);
  }
  for (const r of ["/financeiro", "/estoque", "/pedidos", "/cotacoes", "/producao", "/recria", "/sanidade", "/alimentacao"]) {
    assert.equal(visivel(r, c), false, r);
  }
  assert.equal(temInsights(c), true);
});

test("Gold: tudo do menu aparece", () => {
  const c = ctx(GOLD);
  assert.deepEqual(rotasMenu(c), ITENS_MENU.map((i) => i.href));
  assert.equal(rotaInicial(c), "/");
  assert.equal(temInsights(c), true);
});

test("sem dado (null) não restringe nada", () => {
  const c = ctx(null);
  assert.equal(temCapaUtil(c), true);
  assert.equal(moduloContratado("estoque", c), true);
  assert.equal(visivel("/financeiro", c), true);
  assert.equal(visivel("/rebanho", c), true);
  assert.equal(rotaInicial(c), "/");
});

test("lista vazia É restrição de verdade", () => {
  const c = ctx([]);
  assert.equal(moduloContratado("financeiro", c), false);
  assert.equal(temCapaUtil(c), false);
  assert.equal(visivel("/financeiro", c), false);
  assert.equal(rotaInicial(c), "/agenda"); // Agenda não depende de módulo comercial
});

test("qualquer-de: Histórico com só produção, Lançamentos com só produtivo", () => {
  const c = ctx(["produtivo", "financeiro"]);
  assert.equal(visivel("/historico", c), true);
  assert.equal(visivel("/reproducao", c), false);
  assert.equal(visivel("/lancamentos", c), true);
  assert.equal(visivel("/analise-reprodutiva", c), false);
  assert.equal(temCapaUtil(c), true);
});

test("operador sem permissão: não vê a rota, mesmo com contrato; anti-laço no pouso", () => {
  const c = operador(GOLD, ["rebanho"]);
  assert.equal(visivel("/rebanho", c), true);
  assert.equal(visivel("/financeiro", c), false);
  assert.equal(visivel("/agenda", c), false);
  // Capa útil: "/" abre mesmo sem a permissão "capa" (Home nunca foi barrada), mas o item some do menu.
  assert.equal(visivel("/", c), true);
  assert.equal(visivelNoMenu("/", c), false);
  assert.equal(rotaInicial(c), "/");
});

test("operador só-financeiro sem agenda: pousa em /financeiro; sem nada: /portal", () => {
  assert.equal(rotaInicial(operador(FINANCEIRO, ["financeiro"])), "/financeiro");
  assert.equal(rotaInicial(operador(FINANCEIRO, ["pedidos"])), "/cotacoes");
  const nada = operador(FINANCEIRO, ["rebanho"]);
  assert.equal(rotaInicial(nada), "/portal");
  // a rota de pouso é sempre aberta pelo próprio usuário
  assert.equal(visivel(rotaInicial(nada), nada), true);
});

test("rotaInicial nunca devolve rota que o usuário não abre (varredura)", () => {
  const modulos = [null, [], STANDARD, GOLD, FINANCEIRO, ["financeiro"], ["pedidos"], ["estoque"]];
  const perms = [[], ["agenda"], ["financeiro"], ["pedidos"], ["rebanho", "capa"], ["agenda", "financeiro", "pedidos", "capa"]];
  for (const m of modulos) for (const p of perms) for (const status of ["ativo", null, "suspenso", "aguardando_aprovacao"]) {
    const c = operador(m, p, { contratoStatus: status });
    assert.equal(visivel(rotaInicial(c), c), true, JSON.stringify({ m, p, status }));
  }
});

test("contrato suspenso/aguardando: nada abre, pouso na tela de contrato inativo", () => {
  for (const status of ["suspenso", "aguardando_aprovacao"]) {
    const c = ctx(GOLD, { contratoStatus: status });
    assert.equal(contratoBloqueia(c), true);
    assert.equal(visivel("/agenda", c), false);
    assert.equal(visivel("/", c), false);
    assert.equal(moduloContratado("financeiro", c), false);
    assert.equal(temCapaUtil(c), false);
    assert.equal(rotaInicial(c), "/contrato-inativo");
    assert.equal(visivel("/contrato-inativo", c), true);
    assert.deepEqual(rotasMenu(c), []);
  }
});

test("contrato inativo: suporte, dono e equipe passam", () => {
  const susp = { contratoStatus: "suspenso" };
  assert.equal(contratoBloqueia(ctx(GOLD, { ...susp, suporte: true })), false);
  assert.equal(contratoBloqueia(ctx(GOLD, { ...susp, isento: true })), false);
  assert.equal(visivel("/financeiro", ctx(GOLD, { ...susp, isento: true })), true);
  assert.equal(rotaInicial(ctx(GOLD, { ...susp, isento: true })), "/");
});

test("sessão de suporte libera módulos que a fazenda não contratou", () => {
  const c = ctx(FINANCEIRO, { suporte: true });
  assert.equal(moduloContratado("rebanho", c), true);
  assert.equal(visivel("/rebanho", c), true);
  assert.equal(temCapaUtil(c), true);
});

test("sem usuário (papel null) nada é visível", () => {
  const c = ctx(GOLD, { papel: null, permissoes: [] });
  assert.equal(visivel("/agenda", c), false);
  assert.equal(podeModuloCtx("agenda", c), false);
});

test("chaves de contrato desconhecidas/transversais não restringem o módulo do front", () => {
  const c = ctx(FINANCEIRO);
  assert.equal(moduloFrontContratado("agenda", c), true);
  assert.equal(moduloFrontContratado("parametros", c), true);
  assert.equal(moduloFrontContratado("qualquer-coisa", c), true);
  assert.equal(moduloFrontContratado("estoque", c), false);
});

test("tabela única: ROTA_MODULO deriva de ROTA_MODULOS e todo módulo citado tem entrada de contrato", () => {
  for (const [rota, mods] of Object.entries(ROTA_MODULOS)) {
    assert.equal(ROTA_MODULO[rota], mods[0]);
    for (const m of mods) assert.ok(m in MODULO_CONTRATO, `${rota} -> ${m}`);
  }
  // todo item do menu está na tabela de rotas
  for (const i of ITENS_MENU) assert.ok(i.href in ROTA_MODULOS, i.href);
});

test("contextoAtual lê usuario/fazenda_atual/modo_suporte do localStorage (e é 'ninguém' no servidor)", async () => {
  const { contextoAtual } = await import("./modulos.ts");
  assert.equal(contextoAtual().papel, null); // sem window
  const g = globalThis as unknown as Record<string, unknown>;
  const guardado: Record<string, string> = {
    usuario: JSON.stringify({ papel: "operador", permissoes: ["agenda"], eh_dono: false }),
    fazenda_atual: JSON.stringify({ id: 1, nome: "X", modulos_contratados: ["financeiro"], contrato_status: "suspenso" }),
  };
  g.window = {};
  g.localStorage = { getItem: (k: string) => guardado[k] ?? null };
  try {
    const c = contextoAtual();
    assert.deepEqual(c, { papel: "operador", permissoes: ["agenda"], modulosContratados: ["financeiro"], contratoStatus: "suspenso", suporte: false, isento: false });
    guardado.modo_suporte = JSON.stringify({ sessaoId: 1 });
    assert.equal(contextoAtual().suporte, true);
    delete guardado.fazenda_atual; // sem fazenda: sem dado, não restringe
    assert.equal(contextoAtual().modulosContratados, null);
  } finally {
    delete g.window; delete g.localStorage;
  }
});
