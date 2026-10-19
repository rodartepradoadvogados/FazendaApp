// Dados fictícios da Fazenda Boa Esperança (248 animais), coerentes com a Temporada 1. Determinístico.
function rng(a){return()=>{a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;}}
const r = rng(20261017);
const NOMES = `Estrela Mimosa Boneca Pérola Serena Pintada Bonita Faceira Graúna Jóia Garoa Princesa Aurora Violeta Margarida Flor Cereja Malhada Caramelo Chiquita Dengosa Fumaça Gaivota Hortênsia Iracema Jabuticaba Kiara Lavanda Moranga Naná Orquídea Palmira Quitéria Rosinha Safira Tereza Uirapuru Vitória Xuxa Zulmira Açucena Brisa Canela Dalila Esperança Fidalga Guiomar Helena Ipê Janaína Lua Maravilha Neblina Ondina Papoula Quimera Rainha Sereia Tulipa Urca Vênus Alvorada Bela Cigana Doçura Eva Florinda Girassol Hera Íris Jurema Lolita Melodia Nuvem Olinda Pitanga Querida Ruiva Sinhá Tigresa Umbela Valentina Alegria Baunilha Cotia Diamante Esmeralda Ferrugem Galega Heloísa Ingá Jandira Lindoia Mariposa Nega Oliveira Pagu Rubi Sabiá Tapioca Ubirajara Violeta2 Zeferina Acácia Bambina Cecília Doralice Elvira Filó Glória Hilda Iolanda Judite Lourdes Madalena Neusa Odete Prenda Rita Socorro Teresinha Vanda Zilda Amora Bromélia Cacau Dama Encanto Fada Gardênia Harmonia Inês Jasmim Lírio Marfim Neve Opala Pérola2 Réstia Safra Trigueira Urtiga Vaidosa Xaxá Yara Zabumba Alecrim Boêmia Camélia Dália Estação Frésia Gioconda Hortelã Iara Jacira Kátia Lavínia Mangueira Nectarina Oásis Petúnia Quaresma Romã Sálvia Tâmara Ursula Verbena Wanda Ximena Yasmin Zínia Abelha Borboleta Cotovia Dourada Estrelinha Formosa Galinha2 Harpia Ilusão Joaninha Lagoa Mariana Névoa Ostra Pomba Quinquilharia Rolinha Saudade Tempestade Umbu Vagalume Zefa Amada Branquinha Clarice Diva Edite Fartura Gentil Hera2 Ivete Jussara Laura Mel Noêmia Olga Penha Rosália Sol Tina Uva Vera Wilma Alma Berenice Chuvisco Donzela Elis Fiama Gema Hebe Isadora Julieta Lara Márcia Nilza Ofélia Paloma Quênia Regina Sandra Telma Ursa Vilma Zoraide Aldeia Barroca Cascata Duna Enseada Fonte Gruta Horizonte Ilha Jangada Lagoinha Mata Nascente Oca Pradaria Quebrada Restinga Serra Trilha Vale Várzea Aroeira Buriti Cajá Dendê Embaúba Figueira Goiaba Hibisco Imbé Jaca Louro Manga Nogueira`.split(/\s+/).filter(n=>n && !/\d/.test(n));
// séries (T1) + as duas vacas novas do episódio
const EP9 = process.env.EP === "t2e9"; // Ep. 9: Sanidade — aplicação de medicamentos (herda o Ep. 8; troca o estoque e acrescenta o catálogo de sanidade)
const EP8 = process.env.EP === "t2e8" || EP9; // Ep. 8: BST (herda o Ep. 7; acrescenta a agenda de BST e o produto de BST no estoque)
const EP7 = process.env.EP === "t2e7" || EP8; // Ep. 7: pesagem corporal e secagem (herda o Ep. 6; acrescenta idade_meses, pesagens anteriores e a lista de secagem)
const EP6 = process.env.EP === "t2e6" || EP7; // Ep. 6: controle leiteiro (herda o Ep. 5; acrescenta em_lactacao nos animais e status_lactacao nos lotes)
const EP5 = process.env.EP === "t2e5" || EP6; // Ep. 5: protocolo de IATF (herda o Ep. 4 e aplica o parto: 3654 Dolores → 01 - Alta, nasce a 4712; 6 atrasadas; 1 vaca em protocolo D7)
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
export const lotes = Object.keys(TOTAIS).map((rot,i)=>({id:i+1,codigo:rot.slice(0,2),nome:rot.slice(5),rotulo:rot,ativo:true,...(EP6?{status_lactacao:rot.startsWith("01")||rot.startsWith("02")||rot.startsWith("03")?"lactacao":rot.startsWith("04")||rot.startsWith("05")?"seca":"outro"}:{})}));
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

// ── Ep. 6: controle leiteiro. Só as vacas dos lotes 01–03 têm lactação aberta (111 de 249); secas, pré-parto, novilhas e bezerras não (filtro real "só vacas em lactação") ──
if (EP6) for (const a of animais) a.em_lactacao = ["01","02","03"].includes((a.grupo_primario || "").slice(0, 2));

// ── Ep. 7: Pesagem corporal e Secagem ──
// idade_meses em todos os animais; relatório de pesagem (última pesagem de cada animal: novilhas em 17/09, 30 dias antes de hoje; 12 bezerras em 12/08,
// há mais de 60 dias); lista de secagem das 111 vacas em lactação, com 3 vacas a até 30 dias (Hilda, Melodia, Iolanda: gestação ~220 dias).
export const pesagensRel = [];            // linhas de GET /producao/pesagens/relatorio
export const secagemLista = { hoje: "2026-10-17", ultima_secagem: null, animais: [] }; // sem "última secagem": o valor "09/10/2026" é cortado pela faixa do app (390 px)
export const SECAGEM_PLANO = [["3338", 221], ["2305", 217], ["3013", 214]]; // [brinco, dias de gestação]: parto previsto aos 283 dias, secagem 60 dias antes
export const ESTOQUE7 = [
  { nome: "Antibiótico secagem (bisnaga)", quantidade: 20, unidade: "unidade", categoria: "Medicamento", ativo: true, estocavel: true, finalidade: "secagem" },
  { nome: "Selante de teto", quantidade: 24, unidade: "unidade", categoria: "Medicamento", ativo: true, estocavel: true, finalidade: "secagem" },
  { nome: "Ocitocina injetável", quantidade: 180, unidade: "ml", categoria: "Medicamento", ativo: true, estocavel: true },
  { nome: "Vermífugo oral", quantidade: 60, unidade: "ml", categoria: "Medicamento", ativo: true, estocavel: true },
];
if (EP7) {
  const r7 = rng(20261019);
  const FAIXA_IDADE = { "01": [30, 78], "02": [32, 80], "03": [34, 84], "04": [36, 84], "05": [26, 40], "06": [13, 22], "07": [1, 9] };
  for (const a of animais) { const [lo, hi] = FAIXA_IDADE[a.grupo_primario.slice(0, 2)]; a.idade_meses = lo + Math.floor(r7() * (hi - lo + 1)); }
  const porNum = (n) => animais.find((a) => a.numero === n);
  // novilhas: as quatro primeiras da tabela (ordem numérica) têm pesos conhecidos do roteiro: 312→330, 298→315, 340→336 (perdeu), 305→322
  const novilhas = animais.filter((a) => a.grupo_primario === "06 - Novilhas").sort((a, b) => a.numero.localeCompare(b.numero, "pt-BR", { numeric: true }));
  const PESO_ANT = [312, 298, 340, 305], IDADE_FIXA = [17, 15, 19, 16];
  const dataMais = (iso, d) => new Date(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10) + d)).toISOString().slice(0, 10);
  novilhas.forEach((a, i) => {
    if (i < 4) a.idade_meses = IDADE_FIXA[i];
    const peso = i < 4 ? PESO_ANT[i] : Math.round(110 + a.idade_meses * 11 + (r7() - 0.5) * 30);
    const np = 3 + Math.floor(r7() * 3), dias = 150 + Math.floor(r7() * 60), gmd = 0.55 + r7() * 0.3;
    pesagensRel.push({ numero_matriz: a.numero, grupo_primario: a.grupo_primario, primeira_data: dataMais("2026-09-17", -dias), primeira_peso: Math.round(peso - gmd * dias),
      ultima_data: "2026-09-17", ultima_peso: peso, gmd_kg_dia: +gmd.toFixed(3), gpd_kg_dia: +(gmd * 0.97).toFixed(3), num_pesagens: np });
  });
  animais.filter((a) => a.grupo_primario === "07 - Bezerras").slice(0, 12).forEach((a) => {
    const peso = 60 + a.idade_meses * 18, gmd = 0.7 + r7() * 0.25, dias = 70;
    pesagensRel.push({ numero_matriz: a.numero, grupo_primario: a.grupo_primario, primeira_data: dataMais("2026-08-12", -dias), primeira_peso: Math.round(peso - gmd * dias),
      ultima_data: "2026-08-12", ultima_peso: peso, gmd_kg_dia: +gmd.toFixed(3), gpd_kg_dia: +(gmd * 0.98).toFixed(3), num_pesagens: 2 });
  });
  // secagem: as 3 vacas do plano ganham DEL coerente com a gestação (~300 dias); as demais gestantes ficam com secagem prevista depois dos 30 dias
  for (const [n] of SECAGEM_PLANO) porNum(n).del_dias = 296 + (Number(n) % 17);
  for (const a of animais.filter((x) => x.em_lactacao)) {
    const plano = SECAGEM_PLANO.find((p) => p[0] === a.numero);
    const e = estadosEp2[a.numero];
    const gest = plano ? plano[1] : e?.estado === "gestante" ? Math.min(e.gest || 0, 186) : null;
    const dias = gest == null ? null : 283 - 60 - gest;
    secagemLista.animais.push({ numero_matriz: a.numero, grupo_primario: a.grupo_primario, del_atual: a.del_dias, dias_gestacao: gest,
      data_prevista_secagem: dias == null ? null : dataMais("2026-10-17", dias), dias_para_secagem: dias, deve_secar: dias == null ? null : true, motivo_exclusao: null });
  }
}

// ── Ep. 8: BST. O rebanho DEPOIS da secagem do Ep. 7 (2305 Melodia e 3338 Hilda no 04 - Secas: 40 + 40 + 29 = 109 vacas em lactação) e a agenda de BST ──
// Aptas 18 · Incluir no próximo BST 4 (nunca aplicadas) · Inaptas 6 (DEL < 60 dias, ou poucos dias para secar: a 3013 Iolanda do Ep. 7). Próxima aplicação = hoje (17/10/2026), intervalo 14 dias.
export const ESTOQUE8 = [
  { nome: "Somatotropina bovina 500 mg", quantidade: 40, unidade: "seringa", categoria: "Medicamento", ativo: true, estocavel: true, finalidade: "Medicamento", conta_gerencial_despesa_padrao: "3.01.04.02" },
  ...ESTOQUE7,
];
export const PESSOAS8 = [{ id: 1, nome: "Adelino", tipos: ["Funcionário"], ativo: true }, { id: 2, nome: "Bernadete", tipos: ["Funcionário"], ativo: true }, { id: 3, nome: "Cláudio", tipos: ["Funcionário"], ativo: true }];
export const bst = { proxima: "2026-10-17", intervalo: 14, aptas: [], incluir: [], inaptas: [] };
export const BST_PLANO = {
  aptas: ["1502", "3877", "4102", "4318", "4455", "4521", "4613", "4652", "1045", "2014", "2020", "2025", "2027", "2039", "1450", "3005", "3025", "3032"],
  incluir: ["4669", "4769", "2098", "2371"],
  inaptas: [["3654", null], ["4210", null], ["4605", null], ["4623", null], ["2103", null], ["3013", "Faltam apenas 9 dias para secar (mínimo 15)"]],
};
if (EP8) {
  for (const n of ["2305", "3338"]) { const a = animais.find((x) => x.numero === n); a.grupo_primario = "04 - Secas"; a.categoria_abrev = "Vaca seca"; a.categoria_completa = "Vaca seca"; a.del_dias = null; a.em_lactacao = false; }
  const lin = (n) => { const a = animais.find((x) => x.numero === n); return { numero_matriz: n, grupo: a.grupo_primario, del_atual: a.del_dias }; };
  bst.aptas = BST_PLANO.aptas.map(lin);
  bst.incluir = BST_PLANO.incluir.map((n) => ({ ...lin(n), requer_reanalise: false, origem_inducao_lactacao: false, motivo_exclusao: null }));
  bst.inaptas = BST_PLANO.inaptas.map(([n, m]) => { const l = lin(n); return { ...l, motivo_exclusao: m || `DEL ${l.del_atual} < 60 dias` }; });
}

// ── Ep. 9: Sanidade › aplicação de medicamentos (curativa e preventiva). Estoque com nomes genéricos (princípio ativo + apresentação), nunca marca comercial ──
// Mastite: Cefalexina intramamária está BAIXA (2 bisnagas, abaixo do mínimo) → o app mostra o aviso de substituto; Cloxacilina intramamária (36) é o substituto disponível.
// O servidor real esconde do filtro por doença os itens com saldo <= 0, por isso o gatilho do aviso na tela é "Estoque baixo" (e não "zerado").
const med = (nome, quantidade, unidade, categoria, extra = {}) => ({ nome, quantidade, unidade, categoria, ativo: true, estocavel: true, finalidade: "Medicamento", ...extra });
export const ESTOQUE9 = [
  med("Cefalexina intramamária (bisnaga)", 2, "unidade", "Antibiótico", { abaixo_minimo: true, estoque_minimo: 10 }),
  med("Cloxacilina intramamária (bisnaga)", 36, "unidade", "Antibiótico", { abaixo_minimo: false, estoque_minimo: 10 }),
  med("Ceftiofur injetável 100 ml", 400, "ml", "Antibiótico"),
  med("Flunixina injetável 100 ml", 250, "ml", "Anti-inflamatório"),
  med("Vacina reprodutiva polivalente", 600, "ml", "Vacina"),
  med("Vermífugo injetável", 500, "ml", "Antiparasitário"),
  ...ESTOQUE8,
];
export const DOENCAS9 = ["Mastite", "Metrite", "Pneumonia", "Diarreia", "Laminite", "Retenção de placenta", "Tristeza parasitária"].map((nome, i) => ({ id: i + 1, nome, ativo: true }));
export const PRINCIPIOS9 = ["Cefalexina", "Cloxacilina", "Ceftiofur", "Flunixina", "Ivermectina", "Oxitetraciclina"].map((nome, i) => ({ id: i + 1, nome, ativo: true }));
// medicamentos (itens de estoque) indicados por doença: GET /estoque/medicamentos?doenca=...
export const MED_POR_DOENCA = { "Mastite": ["Cefalexina intramamária (bisnaga)", "Cloxacilina intramamária (bisnaga)", "Ceftiofur injetável 100 ml", "Flunixina injetável 100 ml"] };
// GET /sanidade/indicacoes-doenca/1 (Mastite): Cloxacilina = disponível agora; Cefalexina (a escolhida, baixa) aparece em "Precisa comprar"
export const INDICACOES_MASTITE = { doenca_id: 1, doenca: "Mastite", opcoes: [
  { principio_ativo_id: 1, nome: "Cefalexina", classificacao: "Antibiótico", prioridade: 1, status_estoque: "low", total_apresentacoes: 2, unidade_apresentacao: "unidade", marcas: ["Cefalexina intramamária (bisnaga)"] },
  { principio_ativo_id: 2, nome: "Cloxacilina", classificacao: "Antibiótico", prioridade: 2, status_estoque: "ok", total_apresentacoes: 36, unidade_apresentacao: "unidade", marcas: ["Cloxacilina intramamária (bisnaga)"] },
] };
// eventos preventivos do calendário (GET /cadastro/eventos-sanitarios): todos agendados por época (sem gatilho) → o modo "Na janela" não aparece
export const EVENTOS9 = [
  { id: 1, nome: "Vacina reprodutiva", ativo: true, categoria_preventiva: "vacina", produto_padrao: "Vacina reprodutiva polivalente", dose_padrao: 5, unidade_padrao: "ml", tipo_agendamento: "epoca", gatilho: null },
  { id: 2, nome: "Vermifugação estratégica", ativo: true, categoria_preventiva: "vermifugo", produto_padrao: "Vermífugo injetável", dose_padrao: 10, unidade_padrao: "ml", tipo_agendamento: "epoca", gatilho: null },
  { id: 3, nome: "Exame de brucelose", ativo: true, categoria_preventiva: "exame", produto_padrao: null, dose_padrao: null, unidade_padrao: null, tipo_agendamento: "epoca", gatilho: null },
];
