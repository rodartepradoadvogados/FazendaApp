// T3 · teste 2 (modo explicativo) — Agenda Reprodutiva de frente + gaveta "Novo card" REAIS (DPR 3) e mapa de caixas (px CSS). EP=t3e1 no stub.
import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
const OUT = "shots_t3b/"; fs.mkdirSync(OUT, { recursive: true });
const br = await chromium.launch({ args: ["--lang=pt-BR"], env: { ...process.env, LANGUAGE: "pt_BR", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" } });
const ctx = await novoContexto(br, 844, 3);
await ctx.addInitScript(() => {
  const trocar = () => { for (const p of document.querySelectorAll("header p")) if (p.textContent.includes("Estreito Ponte de Pedra")) p.textContent = "Fazenda Boa Esperança"; };
  new MutationObserver(trocar).observe(document, { childList: true, subtree: true, characterData: true }); document.addEventListener("DOMContentLoaded", trocar);
  try { for (const k of Object.keys(localStorage)) if (k.startsWith("rascunho") || k.startsWith("mob_cache")) localStorage.removeItem(k); } catch {}
});
const p = await pagina(ctx); const esp = (ms = 700) => p.waitForTimeout(ms);
await fetch("http://localhost:8000/__reset");
await p.goto("http://localhost:3000/app/menu", { waitUntil: "networkidle" }); await esp(1200);
await p.locator('button[aria-expanded]', { hasText: "Reprodução" }).first().click(); await esp(700);
await p.locator("button", { hasText: "Agenda Reprodutiva" }).first().click(); await esp(2200);
const topo = async () => { await p.evaluate(() => { document.activeElement?.blur?.(); window.scrollTo(0, 0); document.body.scrollTo(0, 0); document.scrollingElement.scrollTo(0, 0); }); await esp(400); };
await topo();
const box = async (loc) => { const b = await loc.first().boundingBox(); return b && { x: b.x, y: b.y, w: b.width, h: b.height }; };
const mapa = {};
mapa.titulo = await box(p.getByText("Cards configuráveis", { exact: true }));
mapa.novo = await box(p.locator("button", { hasText: "Novo card" }));
mapa.botoes = await box(p.locator("button", { hasText: "A tocar" }));
const dets = p.locator("details"); const n = await dets.count(); mapa.cards = [];
for (let i = 0; i < Math.min(n, 3); i++) { const s = dets.nth(i).locator("summary"); mapa.cards.push({ txt: (await s.innerText()).replace(/\s+/g, " "), ...(await box(dets.nth(i))) }); }
await p.screenshot({ path: OUT + "agenda.png" });
await p.locator("button", { hasText: "Novo card" }).first().click(); await esp(1500);
mapa.gaveta = await box(p.locator('[role="dialog"]'));
mapa.nomeCampo = await box(p.locator('[role="dialog"] input').first());
mapa.nomeLabel = await box(p.locator('[role="dialog"]').getByText("Nome do card", { exact: true }));
mapa.salvar = await box(p.locator("button", { hasText: "Salvar card" }));
await p.screenshot({ path: OUT + "gaveta.png" });
fs.writeFileSync(OUT + "mapa.json", JSON.stringify(mapa, null, 1)); console.log(JSON.stringify(mapa));
await br.close();
