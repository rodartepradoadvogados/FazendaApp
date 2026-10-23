// Gera aud/roteiro_t3e6.json (efeitos + camadas de trilha + voz) a partir de beats.json e do roteiro do episódio (WP/TAPS/SELOS/PAPEL).
import fs from "fs";
const B = JSON.parse(fs.readFileSync("cena/tex2/beats.json","utf8"));
const src = fs.readFileSync("cena/episodio_roteiro_t3e6.js","utf8");
const f = new Function("B", "M", "uniao", src + "\nreturn {WP, TAPS, SELOS, T_VIRA, T_FIM_TOTAL, FITAS_TXT};");
const r = f(B, {}, () => ({})); const fx = [];
fx.push([0.30,"rasgo",0],[1.05,"impacto",-4],[1.45,"whoosh",0],[1.45,"rasgo",0],[2.55,"rasgo",0],[3.55,"whoosh",0],[4.27,"toque",0],[4.30,"impacto",-6],[4.85,"whoosh",-4]);
for (let i=1;i<r.WP.length;i++){ const a=r.WP[i-1], b=r.WP[i]; const d=b.ta-a.td; if (d>=0.3) fx.push([+(a.td+d*0.30).toFixed(3),"whoosh",-9]); }
for (const [t] of r.TAPS) fx.push([+t.toFixed(3),"clique",-5]);
for (const o of r.SELOS) fx.push([+(o.t0+0.42).toFixed(3),"carimbo",0]);
for (const o of r.FITAS_TXT) fx.push([+o.t0.toFixed(3),"rasgo",0]);
fx.push([r.T_VIRA,"whoosh",-3],[B.obrigado-0.05,"rasgo",0],[B.obrigado+1.15,"rasgo",0],[B.obrigado,"whoosh",-8]);
fx.sort((a,b)=>a[0]-b[0]);
const roteiro = {total:r.T_FIM_TOTAL, camadas:[[0,["pad"]],[1.0,["pad","baixo","bumbo_leve","shaker"]],[2.4,["pad","baixo","bumbo_leve","shaker","sino"]],[5.6,["pad","baixo","shaker"]],[24.2,["pad","baixo","bumbo_leve","shaker"]],[B.pronto,["pad","baixo","bumbo_leve","palma","shaker","piano_cheio","sino"]],[r.T_VIRA+0.8,["pad","baixo"]]], fx, ganho_musica:0.065, voz:{arquivo:"aud/voz_tratada.wav", segmentos:[[0.0,0.0,92.604]]}};
fs.writeFileSync("aud/roteiro_t3e6.json", JSON.stringify(roteiro));
console.log(fx.length,"fx");
