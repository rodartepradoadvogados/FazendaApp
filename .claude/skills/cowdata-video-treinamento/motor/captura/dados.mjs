// Dados fictícios da Fazenda Boa Esperança (248 animais), coerentes com a Temporada 1. Determinístico.
function rng(a){return()=>{a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;}}
const r = rng(20261017);
const NOMES = `Estrela Mimosa Boneca Pérola Serena Pintada Bonita Faceira Graúna Jóia Garoa Princesa Aurora Violeta Margarida Flor Cereja Malhada Caramelo Chiquita Dengosa Fumaça Gaivota Hortênsia Iracema Jabuticaba Kiara Lavanda Moranga Naná Orquídea Palmira Quitéria Rosinha Safira Tereza Uirapuru Vitória Xuxa Zulmira Açucena Brisa Canela Dalila Esperança Fidalga Guiomar Helena Ipê Janaína Lua Maravilha Neblina Ondina Papoula Quimera Rainha Sereia Tulipa Urca Vênus Alvorada Bela Cigana Doçura Eva Florinda Girassol Hera Íris Jurema Lolita Melodia Nuvem Olinda Pitanga Querida Ruiva Sinhá Tigresa Umbela Valentina Alegria Baunilha Cotia Diamante Esmeralda Ferrugem Galega Heloísa Ingá Jandira Lindoia Mariposa Nega Oliveira Pagu Rubi Sabiá Tapioca Ubirajara Violeta2 Zeferina Acácia Bambina Cecília Doralice Elvira Filó Glória Hilda Iolanda Judite Lourdes Madalena Neusa Odete Prenda Rita Socorro Teresinha Vanda Zilda Amora Bromélia Cacau Dama Encanto Fada Gardênia Harmonia Inês Jasmim Lírio Marfim Neve Opala Pérola2 Réstia Safra Trigueira Urtiga Vaidosa Xaxá Yara Zabumba Alecrim Boêmia Camélia Dália Estação Frésia Gioconda Hortelã Iara Jacira Kátia Lavínia Mangueira Nectarina Oásis Petúnia Quaresma Romã Sálvia Tâmara Ursula Verbena Wanda Ximena Yasmin Zínia Abelha Borboleta Cotovia Dourada Estrelinha Formosa Galinha2 Harpia Ilusão Joaninha Lagoa Mariana Névoa Ostra Pomba Quinquilharia Rolinha Saudade Tempestade Umbu Vagalume Zefa Amada Branquinha Clarice Diva Edite Fartura Gentil Hera2 Ivete Jussara Laura Mel Noêmia Olga Penha Rosália Sol Tina Uva Vera Wilma Alma Berenice Chuvisco Donzela Elis Fiama Gema Hebe Isadora Julieta Lara Márcia Nilza Ofélia Paloma Quênia Regina Sandra Telma Ursa Vilma Zoraide Aldeia Barroca Cascata Duna Enseada Fonte Gruta Horizonte Ilha Jangada Lagoinha Mata Nascente Oca Pradaria Quebrada Restinga Serra Trilha Vale Várzea Aroeira Buriti Cajá Dendê Embaúba Figueira Goiaba Hibisco Imbé Jaca Louro Manga Nogueira`.split(/\s+/).filter(n=>n && !/\d/.test(n));
// séries (T1) + as duas vacas novas do episódio
const EP5 = process.env.EP === "t2e5"; // Ep. 5: protocolo de IATF (herda o Ep. 4 e aplica o parto: 3654 Dolores → 01 - Alta, nasce a 4712; 6 atrasadas; 1 vaca em protocolo D7)
const EP4 = process.env.EP === "t2e4" || EP5; // Ep. 4: parto (herda tudo do Ep. 3; acrescenta no 05 - Pré-parto as matrizes 3654 Dolores e 5611 Lucinda)
const EP3 = process.env.EP === "t2e3" || EP4; // Ep. 3: diagnóstico de gestação (mesmos lotes do Ep. 2 + 9 vacas "a tocar")
const EP2 = process.env.EP === "t2e2" || EP3; // Ep. 2: lotes DEPOIS da troca do Ep. 1 (3990, 4033 e 4078 já no 02 - Média)
// Ep. 3: as 9 vacas inseminadas há ~30 dias que aparecem em "A tocar" (brinco, nome, lote, dias desde a IA, DEL, plano do episódio)
export const TOCAR3 = [
  ["4318","Cereja","01 - Alta",33,118,"retoque"], ["4455","Violeta","01 - Alta",36,127,"retoque"], ["4731","Margarida","01 - Alta",38,139,"negativo"],
  ["4846","Caramelo","01 - Alta",28,112,"espera"], ["4902","Fumaça","01 - Alta",29,121,"espera"],
  ["2127","Dengosa","02 - Média",31,176,"retoque"], ["2263","Gaivota","02 - Média",34,189,"retoque"], ["2342","Iracema","02 - Média",37,203,"retoque"], ["2388","Kiara","02 - Média",40,214,"negativo"],
];
const FIXAS = EP2 ? {
  "01 - Alta": [["4521","Estrela",142],["3877","Mimosa",75],["4102","Boneca",96],["4210","Serena",28],["1502","Jóia",88], ...(EP3 ? TOCAR3.filter(x=>x[2]==="01 - Alta").map(x=>[x[0],x[1],x[4]]) : [])],
  "02 - Média": [["1045","Pintada",187],["3990","Pérola",201],["4033","Garoa",236],["4078","Princesa",254], ...(EP3 ? TOCAR3.filter(x=>x[2]==="02 - Média").map(x=>[x[0],x[1],x[4]]) : [])],
  "03 - Baixa": [["1450","Bonita",262]],
  "04 - Secas": [["1388","Graúna",0]],
  "06 - Novilhas": [["1210","Faceira",0]],
  ...(EP4 ? { "05 - Pré-parto": [["3654","Dolores",0],["5611","Lucinda",0]] } : {}),
} : {
  "01 - Alta": [["4521","Estrela",142],["3877","Mimosa",75],["4102","Boneca",96],["3990","Pérola",201],["4210","Serena",28],["1502","Jóia",88],["4033","Garoa",236],["4078","Princesa",254]],
  "02 - Média": [["1045","Pintada",187]],
  "03 - Baixa": [["1450","Bonita",262]],
  "04 - Secas": [["1388","Graúna",0]],
  "06 - Novilhas": [["1210","Faceira",0]],
};
const TOTAIS = {"01 - Alta":EP2?39:42,"02 - Média":EP2?41:38,"03 - Baixa":30,"04 - Secas":22,"05 - Pré-parto":12,"06 - Novilhas":46,"07 - Bezerras":58};
const FAIXA = {"01 - Alta":[4600,4999],"02 - Média":[2000,2399],"03 - Baixa":[3000,3399],"04 - Secas":[5000,5399],"05 - Pré-parto":[5500,5699],"06 - Novilhas":[6000,6399],"07 - Bezerras":[7000,7399]};
const DELF = {"01 - Alta":[20,190],"02 - Média":[150,260],"03 - Baixa":[240,330],"04 - Secas":[0,0],"05 - Pré-parto":[0,0]};
const CAT = {"01 - Alta":"Vaca","02 - Média":"Vaca","03 - Baixa":"Vaca","04 - Secas":"Vaca seca","05 - Pré-parto":"Vaca seca","06 - Novilhas":"Novilha","07 - Bezerras":"Bezerra"};
const usados = new Set(Object.values(FIXAS).flat().map(x=>x[1]));
const nums = new Set(Object.values(FIXAS).flat().map(x=>x[0]));
const pool = NOMES.filter(n=>!usados.has(n)); // ordem fixa, sem repetir
let pi = 0;
export const animais = [];
for (const [lote, total] of Object.entries(TOTAIS)) {
  const fixas = FIXAS[lote] || [];
  const lista = fixas.map(f=>({numero:f[0],nome:f[1],del:f[2]}));
  const [lo, hi] = FAIXA[lote], [d0, d1] = DELF[lote] || [0,0];
  while (lista.length < total) {
    let n; do { n = String(lo + Math.floor(r()*(hi-lo+1))); } while (nums.has(n)); nums.add(n);
    lista.push({numero:n,nome:pool[pi++],del:d1? d0+Math.floor(r()*(d1-d0)) : 0});
  }
  if (EP4 && lote === "05 - Pré-parto") { r(); r(); pi += 2; } // as 2 fixas substituem 2 geradas: consome o mesmo tanto de sorteio/nome, para os lotes seguintes ficarem idênticos aos do Ep. 3
  for (const a of lista) animais.push({ numero:a.numero, nome:a.nome, grupo_primario:lote, categoria_abrev:CAT[lote], categoria_completa:lote.startsWith("01")||lote.startsWith("02")||lote.startsWith("03")?"Vaca em lactação":CAT[lote], sexo:"F", del_dias:a.del||null, eh_semen:false, raca:"Holandesa" });
}
export const lotes = Object.keys(TOTAIS).map((rot,i)=>({id:i+1,codigo:rot.slice(0,2),nome:rot.slice(5),rotulo:rot,ativo:true}));
export const SEED_MOTIVOS = ["Crescimento","Desmama","Aptidão","Inseminação","Pré-parto","Pós-parto","Aumento de DEL e/ou produção","Final de DEL ou queda de produção","Tratamento/doença","Secagem","Nascimento","Outro motivo"];

// ── Ep. 2: situação reprodutiva de cada animal (a tela de Inseminação lê de /indicadores/estados-reprodutivos) ──
// Rebanho: 18 aptas (4 no 01 - Alta), 6 atrasadas, 9 inseminadas (IA atual). 4521 Estrela gestante (58 dias) no 01 - Alta.
export const estadosEp2 = {};
if (EP2) {
  const r2 = rng(20261018);
  const PLANO = EP3 ? { // Ep. 3: 31 inseminadas no rebanho (9 a tocar + as 4 do Ep. 2 + 18 já com toque)
    "01 - Alta": [["apta",1],["atrasada",1],["pev",2],["inseminada",2],["nao_apta",6],["gestante",17]],
    "02 - Média": [["apta",4],["atrasada",2],["inseminada",5],["nao_apta",8],["gestante",14]],
    "03 - Baixa": [["apta",7],["atrasada",2],["inseminada",11],["nao_apta",4],["gestante",5]],
  } : { // por lote: [estado, quantidade] na ordem em que os animais GERADOS aparecem; fixas têm estado próprio
    "01 - Alta": [["apta",1],["atrasada",2],["pev",2],["inseminada",3],["nao_apta",7],["gestante",19]],
    "02 - Média": [["apta",4],["atrasada",2],["inseminada",3],["nao_apta",8],["gestante",20]],
    "03 - Baixa": [["apta",7],["atrasada",2],["inseminada",3],["nao_apta",4],["gestante",13]],
  };
  const FIXO = { "4521":["gestante",58], "3877":["apta"], "4102":["apta"], "1502":["apta"], "4210":["pev"], "1045":["gestante",120], "3990":["apta"], "4033":["apta"], "4078":["apta"], "1450":["gestante",150] };
  if (EP3) { // as 4 do Ep. 2 foram inseminadas hoje (IA de 17/10); as 9 "a tocar" têm IA de 28 a 40 dias
    for (const n of ["3877","4102","1502","4669"]) FIXO[n] = ["inseminada", null, 0];
    for (const [n, , , ia] of TOCAR3) FIXO[n] = ["inseminada", null, ia];
  }
  const DELS = { apta:[60,150], atrasada:[110,190], pev:[25,40], inseminada:[70,160], nao_apta:[4,22], gestante:[110,260] };
  const usadasFixas = new Set(Object.keys(FIXO));
  for (const lote of Object.keys(TOTAIS)) {
    const doLote = animais.filter(a => a.grupo_primario === lote);
    if (!PLANO[lote]) { for (const a of doLote) estadosEp2[a.numero] = { estado: lote.startsWith("06")||lote.startsWith("07") ? "nao_apta" : "gestante", gest: 230 }; continue; }
    let nIA = 0;
    const fila = PLANO[lote].flatMap(([e, n]) => Array(n).fill(e));
    for (const a of doLote) {
      if (FIXO[a.numero]) { const [e, g, ia] = FIXO[a.numero]; estadosEp2[a.numero] = { estado: e, gest: g || null, ia: ia ?? null }; continue; }
      const e = fila.shift() || "nao_apta"; const [lo, hi] = DELS[e];
      a.del_dias = lo + Math.floor(r2() * (hi - lo));
      estadosEp2[a.numero] = { estado: e, gest: e === "gestante" ? 62 + Math.floor(r2() * 190) : null, ia: e === "inseminada" ? [6, 34, 11][nIA++ % 3] : null };
    }
  }
  // doses em estoque (Convencional: ORION 12 → 8 com as 4 vacas)
  globalThis.__SEMEN = { touros: [
    { nome: "ORION", tipo: "convencional", doses: 12 }, { nome: "ATLAS", tipo: "convencional", doses: 9 }, { nome: "JAGUAR", tipo: "convencional", doses: 6 },
    { nome: "ATLAS", tipo: "sexado", doses: 8 }, { nome: "VULCÃO", tipo: "sexado", doses: 3 } ] };
}

if (EP4) { estadosEp2["3654"].gest = 276; estadosEp2["5611"].gest = 272; } // gestantes a termo

// ── Ep. 3: candidatas ao diagnóstico (GET /reproducao/diagnostico/candidatas) ──
// A tocar = as 9 de TOCAR3 (7 no prazo + 2 AINDA NÃO, prazo de 30 dias); A reconfirmar = 6 e Reconfirmadas = 14, sorteadas entre as gestantes.
export const DATA_REF = "2026-10-17";
const iso = (dias) => { const d = new Date(Date.UTC(2026, 9, 17 - dias)); return d.toISOString().slice(0, 10); };
export const candidatasEp3 = { a_tocar: [], a_reconfirmar: [], reconfirmada: [] };
if (EP3) {
  const DIAS_TOQUE = 30;
  const item = (num, ia, extra) => {
    const a = animais.find((x) => x.numero === num);
    return { numero_matriz: num, categoria: "Vaca", lote_atual: a.grupo_primario, estado: "inseminada", del_dias: a.del_dias, dias_gestacao: null, dias_desde_servico: ia,
      data_servico: iso(ia), parto_previsto: null, diagnostico: null, data_diagnostico: null, diagnostico_reconfirmacao: null, data_reconfirmacao: null, retoque: null,
      fase: "a_tocar", ainda_nao: false, dias_para_prazo: null, prazo_tipo: null, ...extra };
  };
  for (const [num, , , ia, , plano] of TOCAR3) {
    const espera = ia < DIAS_TOQUE;
    candidatasEp3.a_tocar.push(item(num, ia, espera ? { ainda_nao: true, dias_para_prazo: DIAS_TOQUE - ia, prazo_tipo: "toque" } : {}));
  }
  const gestantes = animais.filter((a) => ["01","02","03"].includes(a.grupo_primario.slice(0, 2)) && estadosEp2[a.numero]?.estado === "gestante" && !TOCAR3.some((t) => t[0] === a.numero)).map((a) => a.numero);
  gestantes.slice(0, 6).forEach((num, i) => { const ia = 41 + i * 3; estadosEp2[num].gest = ia;
    candidatasEp3.a_reconfirmar.push(item(num, ia, { estado: "gestante", dias_gestacao: ia, fase: "a_reconfirmar", diagnostico: "POSITIVO", data_diagnostico: iso(ia - 31), retoque: true })); });
  gestantes.slice(6, 20).forEach((num, i) => { const ia = 75 + i * 6; estadosEp2[num].gest = ia;
    candidatasEp3.reconfirmada.push(item(num, ia, { estado: "gestante", dias_gestacao: ia, fase: "reconfirmada", diagnostico: "POSITIVO", data_diagnostico: iso(ia - 31), diagnostico_reconfirmacao: "POSITIVO", data_reconfirmacao: iso(ia - 62), retoque: true })); });
}

// ── Ep. 5: o rebanho DEPOIS do parto do Ep. 4 (249 animais) e a situação para o Protocolo IATF ──
// 01 - Alta 40 · 05 - Pré-parto 11 · 07 - Bezerras 59. Atrasadas = 6 (como no Ep. 2). Uma vaca do 03 - Baixa está em protocolo (D0 10/10, hoje D7).
export const EP5_INFO = {};
if (EP5) {
  const mae = animais.find((a) => a.numero === "3654");
  mae.grupo_primario = "01 - Alta"; mae.categoria_abrev = "Vaca"; mae.categoria_completa = "Vaca em lactação"; mae.del_dias = 1;
  estadosEp2["3654"] = { estado: "nao_apta", gest: null, ia: null };
  animais.push({ numero: "4712", nome: null, grupo_primario: "07 - Bezerras", categoria_abrev: "Bezerra", categoria_completa: "Bezerra", sexo: "F", del_dias: null, eh_semen: false, raca: "Holandesa" });
  estadosEp2["4712"] = { estado: "nao_apta", gest: null, ia: null };
  // a 6ª atrasada: a primeira gestante gerada do 01 - Alta (nem fixa nem "a tocar") vira vaca vazia com DEL alto
  const fixas = new Set(Object.values(FIXAS).flat().map((x) => x[0]));
  const nova = animais.find((a) => a.grupo_primario === "01 - Alta" && !fixas.has(a.numero) && estadosEp2[a.numero]?.estado === "gestante");
  estadosEp2[nova.numero] = { estado: "atrasada", gest: null, ia: null }; nova.del_dias = 168;
  // vaca em protocolo: a primeira apta gerada do 03 - Baixa
  const prot = animais.find((a) => a.grupo_primario === "03 - Baixa" && !fixas.has(a.numero) && estadosEp2[a.numero]?.estado === "apta");
  estadosEp2[prot.numero] = { estado: "em_protocolo", gest: null, ia: null, prot: 7, d0: "2026-10-10" };
  EP5_INFO.atrasadaNova = nova.numero; EP5_INFO.protocolo = prot.numero;
}
