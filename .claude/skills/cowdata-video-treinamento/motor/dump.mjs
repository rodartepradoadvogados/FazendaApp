import { createRequire } from "module"; import path from "path"; import fs from "fs";
const require = createRequire("/opt/node-tools/node_modules/"); const { chromium } = require("playwright");
const br = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const p = await br.newPage(); await p.goto("file://" + path.resolve(process.argv[2]));
const d = await p.evaluate(() => ({ toques: EP.toques.map(x => x[0]), telas: EP.telas.slice(1).map(x => x[0]), cam: EP.cam.slice(1).map(x => x[0]), fitas: EP.fitas.map(x => x[0]), anot: EP.anot.map(x => x[0]), fim: EP.fimLeg, tl: TL }));
fs.writeFileSync(process.argv[3], JSON.stringify(d)); await br.close();
