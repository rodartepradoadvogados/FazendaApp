import fs from "fs";
const B = JSON.parse(fs.readFileSync("cena/tex2/beats.json","utf8"));
const src = fs.readFileSync("cena/episodio_roteiro.js","utf8");
const f = new Function("B", src + "\nreturn {WP, TAPS, T_SELO, T_VIRA};");
const r = f(B); const fx = [];
// aberturas
fx.push([0.30,"rasgo",0],[1.05,"impacto",-4],[1.45,"whoosh",0],[3.02,"rasgo",0],[3.55,"whoosh",0],[3.92,"rasgo",0],[4.27,"toque",0],[4.30,"impacto",-6],[4.85,"whoosh",-4]);
for (let i=1;i<r.WP.length;i++){ const a=r.WP[i-1], b=r.WP[i]; const d=b.ta-a.td; if (d>=0.3) fx.push([+(a.td+d*0.30).toFixed(3),"whoosh",-9]); }
for (const [t] of r.TAPS) fx.push([+t.toFixed(3),"clique",-5]);
fx.push([r.T_SELO+0.42,"carimbo",0],[r.T_VIRA,"whoosh",-3],[B.proximo-0.05,"rasgo",0],[B.protocolos-0.05,"rasgo",0],[B.protocolos+0.65,"rasgo",0],[B.protocolos+1.55,"rasgo",0],[B.proximo,"whoosh",-8]);
fx.sort((a,b)=>a[0]-b[0]);
const roteiro = {total:98.6, camadas:[[0,["pad"]],[1.0,["pad","baixo","bumbo_leve","shaker"]],[2.4,["pad","baixo","bumbo_leve","shaker","sino"]],[5.6,["pad","baixo","shaker"]],[50,["pad","baixo","bumbo_leve","shaker"]],[87.4,["pad","baixo","bumbo_leve","palma","shaker","piano_cheio","sino"]],[90.4,["pad","baixo"]]], fx, ganho_musica:0.065, voz:{arquivo:"aud/voz_tratada.wav", segmentos:[[0.0,0.0,94.12]]}};
fs.writeFileSync("aud/roteiro_t3e1.json", JSON.stringify(roteiro));
console.log(fx.length,"fx");
