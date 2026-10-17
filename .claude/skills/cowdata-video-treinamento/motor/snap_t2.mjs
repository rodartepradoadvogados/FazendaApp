// Gera assets/kraft.png (papel Kraft da Temporada 2) e, se faltarem, papel.png/grao.png da Temporada 1.  node snap_t2.mjs
import { createRequire } from "module"; import path from "path"; import fs from "fs";
const require = createRequire("/opt/node-tools/node_modules/"); const { chromium } = require("playwright");
const br = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const p = await br.newPage({ viewport: { width: 1080, height: 1920 } });
fs.mkdirSync("assets", { recursive: true });
await p.goto("file://" + path.resolve("papel_kraft.html")); await p.screenshot({ path: "assets/kraft.png" });
if (!fs.existsSync("assets/grao.png")) { await p.goto("file://" + path.resolve("grao.html")); await p.screenshot({ path: "assets/grao.png", omitBackground: true }); }
await br.close(); console.log("ok");
