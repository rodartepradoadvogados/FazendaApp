// Gera aud/roteiro_t3e2.json (efeitos + camadas de trilha + voz) a partir de beats.json e do roteiro do episódio (WP/TAPS/SELOS/PAPEL).
import fs from "fs";
const B = JSON.parse(fs.readFileSync("cena/tex2/beats.json","utf8"));
const M = { pdf: { w: 1819, h: 2573, palavras: [{ t: "3344", y: 700, h: 20, x: 140, w: 50 }, { t: "ANIMAL", y: 330, h: 20, x: 140, w: 80 }, { t: "3054", y: 400, h: 20, x: 140, w: 50 }, { t: "D0", y: 334, h: 20, x: 410, w: 27 }, { t: "D7", y: 334, h: 20, x: 680, w: 27 }, { t: "D9", y: 334, h: 20, x: 951, w: 27 }, { t: "D11", y: 334, h: 20, x: 1096, w: 39 }] } }; // só para o roteiro avaliar; o áudio usa apenas os instantes
const src = fs.readFileSync("cena/episodio_roteiro_t3e2.js","utf8");
const f = new Function("B", "M", "uniao", src + "\nreturn {WP, TAPS, SELOS, PAPEL, T_VIRA, T_FIM_TOTAL, FITA_PROT};");
const r = f(B, M, () => ({})); const fx = [];
fx.push([0.30,"rasgo",0],[1.05,"impacto",-4],[1.45,"whoosh",0],[1.45,"rasgo",0],[2.64,"rasgo",0],[3.55,"whoosh",0],[4.27,"toque",0],[4.30,"impacto",-6],[4.85,"whoosh",-4]);
for (let i=1;i<r.WP.length;i++){ const a=r.WP[i-1], b=r.WP[i]; const d=b.ta-a.td; if (d>=0.3) fx.push([+(a.td+d*0.30).toFixed(3),"whoosh",-9]); }
for (const [t] of r.TAPS) fx.push([+t.toFixed(3),"clique",-5]);
for (const o of r.SELOS) fx.push([+(o.t0+0.42).toFixed(3),"carimbo",0]);
fx.push([+(r.FITA_PROT.t0).toFixed(3),"rasgo",0]); for (const d of r.FITA_PROT.dias) fx.push([+d.toFixed(3),"toque",-4]);
fx.push([+(r.PAPEL[0]+0.55).toFixed(3),"toque",-2],[+r.PAPEL[1].toFixed(3),"whoosh",-6]);
fx.push([r.T_VIRA,"whoosh",-3],[B.proximo-0.05,"rasgo",0],[B.baixaAplic-0.05,"rasgo",0],[B.baixaAplic+0.85,"rasgo",0],[B.baixaAplic+1.85,"rasgo",0],[B.proximo,"whoosh",-8]);
fx.sort((a,b)=>a[0]-b[0]);
const roteiro = {total:r.T_FIM_TOTAL, camadas:[[0,["pad"]],[1.0,["pad","baixo","bumbo_leve","shaker"]],[2.4,["pad","baixo","bumbo_leve","shaker","sino"]],[5.6,["pad","baixo","shaker"]],[34.5,["pad","baixo","bumbo_leve","shaker"]],[B.pronto,["pad","baixo","bumbo_leve","palma","shaker","piano_cheio","sino"]],[r.T_VIRA+0.8,["pad","baixo"]]], fx, ganho_musica:0.065, voz:{arquivo:"aud/voz_tratada.wav", segmentos:[[0.0,0.0,69.43]]}};
fs.writeFileSync("aud/roteiro_t3e2.json", JSON.stringify(roteiro));
console.log(fx.length,"fx");
