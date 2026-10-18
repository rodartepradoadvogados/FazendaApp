import { createRequire } from "module";
const require = createRequire("/opt/node-tools/node_modules/");
export const { chromium } = require("playwright");
export const ESC = 960 / 390;
export async function novoContexto(browser, h = 844) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: h }, deviceScaleFactor: ESC * 1.5, locale: "pt-BR", timezoneId: "America/Sao_Paulo", colorScheme: "light", serviceWorkers: "block" });
  await ctx.addInitScript(() => {
    localStorage.setItem("token", "teste");
    localStorage.setItem("usuario", JSON.stringify({ id: 1, nome: "Teste", papel: "admin", eh_dono: true, permissoes: [] }));
    localStorage.setItem("fazenda_atual", JSON.stringify({ id: 1, nome: "Fazenda Boa Esperança", contrato_status: "ativo", modulos_contratados: ["rebanho", "reproducao", "producao", "sanidade", "financeiro", "alimentacao", "estoque"] }));
    localStorage.setItem("theme", "claro"); localStorage.setItem("tema", "claro");
    localStorage.removeItem("rascunho_lancar_lote_movimentar");
  });
  return ctx;
}
export async function pagina(ctx) {
  const p = await ctx.newPage();
  await p.clock.setFixedTime(new Date("2026-10-17T10:05:00-03:00"));
  p.on("pageerror", (e) => console.log("pageerror", String(e).slice(0, 200)));
  return p;
}
