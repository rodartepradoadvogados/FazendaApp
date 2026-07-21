// Gera os PNGs de favicon/ícone PWA a partir do SVG-fonte único da marca
// CowData (public/brand/cowdata-mark.svg). Rodar de novo sempre que o
// desenho do ícone mudar: node scripts/gerar-icones-marca.mjs
import sharp from "sharp";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import path from "path";

const dir = path.dirname(fileURLToPath(import.meta.url));
const raiz = path.resolve(dir, "..");
const svg = readFileSync(path.join(raiz, "public/brand/cowdata-mark.svg"));
const svgMaskable = readFileSync(path.join(raiz, "public/brand/cowdata-mark-maskable.svg"));

const alvos = [
  { arquivo: "public/icons/icone-16.png", src: svg, tamanho: 16 },
  { arquivo: "public/icons/icone-32.png", src: svg, tamanho: 32 },
  { arquivo: "public/icons/icone-180.png", src: svg, tamanho: 180 },
  { arquivo: "public/icons/icone-192.png", src: svg, tamanho: 192 },
  { arquivo: "public/icons/icone-512.png", src: svg, tamanho: 512 },
  { arquivo: "public/icons/icone-maskable-512.png", src: svgMaskable, tamanho: 512 },
];

for (const { arquivo, src, tamanho } of alvos) {
  await sharp(src, { density: 384 }).resize(tamanho, tamanho).png().toFile(path.join(raiz, arquivo));
  console.log("gerado:", arquivo);
}

// favicon.ico (multi-tamanho 16+32) a partir dos PNGs já gerados.
const png16 = await sharp(svg, { density: 384 }).resize(16, 16).png().toBuffer();
const png32 = await sharp(svg, { density: 384 }).resize(32, 32).png().toBuffer();
const ico = construirIco([{ tamanho: 16, png: png16 }, { tamanho: 32, png: png32 }]);
await import("fs/promises").then((fs) => fs.writeFile(path.join(raiz, "app/favicon.ico"), ico));
console.log("gerado: app/favicon.ico");

// Empacota PNGs num .ico simples (ICONDIR + ICONDIRENTRY + dados PNG crus —
// suportado por todos os navegadores modernos, sem precisar converter para BMP).
function construirIco(entradas) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(entradas.length, 4);

  let offset = 6 + entradas.length * 16;
  const dirEntries = [];
  const datas = [];
  for (const { tamanho, png } of entradas) {
    const entry = Buffer.alloc(16);
    entry.writeUInt8(tamanho === 256 ? 0 : tamanho, 0);
    entry.writeUInt8(tamanho === 256 ? 0 : tamanho, 1);
    entry.writeUInt8(0, 2);
    entry.writeUInt8(0, 3);
    entry.writeUInt16LE(1, 4);
    entry.writeUInt16LE(32, 6);
    entry.writeUInt32LE(png.length, 8);
    entry.writeUInt32LE(offset, 12);
    offset += png.length;
    dirEntries.push(entry);
    datas.push(png);
  }
  return Buffer.concat([header, ...dirEntries, ...datas]);
}
