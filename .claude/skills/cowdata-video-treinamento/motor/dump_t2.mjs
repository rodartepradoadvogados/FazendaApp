// node dump_t2.mjs <html> <saida.json> — extrai da página os eventos de SFX, camadas da trilha e o total (beats.json)
import { createRequire } from "module"; import path from "path"; import fs from "fs";
const require = createRequire("/opt/node-tools/node_modules/"); const { chromium } = require("playwright");
const br = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--no-sandbox", "--allow-file-access-from-files"] });
const p = await br.newPage(); await p.goto("file://" + path.resolve(process.argv[2])); await p.evaluate(() => window.__ready);
const d = await p.evaluate(() => ({ sfx: EP.sfx, camadas: EP.camadas, total: TL.total, telas: EP.telas.map(x => x[0]), toques: EP.toques.map(x => x[0]), voz: TL.frases.map(f => [f[1], f[2]]) }));
fs.writeFileSync(process.argv[3], JSON.stringify(d)); await br.close(); console.log("sfx", d.sfx.length);
