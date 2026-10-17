import { createRequire } from "module"; import path from "path";
const require = createRequire("/opt/node-tools/node_modules/"); const { chromium } = require("playwright");
const br = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const p = await br.newPage({ viewport: { width: 1080, height: 1920 } });
await p.goto("file://" + path.resolve("papel.html")); await p.screenshot({ path: "assets/papel.png" });
await p.goto("file://" + path.resolve("grao.html")); await p.screenshot({ path: "assets/grao.png", omitBackground: true });
await br.close();
