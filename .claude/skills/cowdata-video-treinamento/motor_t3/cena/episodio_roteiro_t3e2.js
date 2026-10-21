// ===== roteiro do Ep. 2 (Protocolos IATF em andamento): instantes (voz real, beats.json), estados da tela, navegador, câmera, legendas =====
const T_INI = 5.6, T_MENU_FIM = B.protIatf + 0.06, T_FIM_FRONTAL = 64.8, T_VIRA = 65.1, T_SELO = B.pronto + 0.1, T_SELO_FIM = 65.1, T_FIM_TOTAL = 73.8, NAV_FIM = 62.02, T_ETQ_FIM = 62.1;
const PULSO = [-9, -8]; // (sem pulso neste episódio)
const SELOS = [ // carimbos 3D que descem sobre a tela
  { t0: 57.85, t1: 59.15, l1: "SÓ", l2: "CONSULTA", cor: 0x1d3557, f1: 150, f2: 180, saida: true },
  { t0: T_SELO, t1: T_SELO_FIM, l1: "✔ PROTOCOLO", l2: "EM DIA", cor: 0x1f5a3a, f1: 130, f2: 200 },
];
// folha de papel (página real do PDF): plano 500 px CSS de largura, centrado em (195, 440) do vidro do celular
const PP = { w: 500, cx: 195, cy: 440 }; PP.h = PP.w * M.pdf.h / M.pdf.w;
const PAPEL = [B.pdf + 0.03, 44.24, 44.85]; // [pousa, começa a sair, saiu]
const t_ger = 38.98, t_fimger = 44.29;
const PLANO_PG = [[0, "pi0"], [t_ger, "pi_ger"], [t_fimger, "pi0"]];
const SYK = [[0, 0], [44.65, 0], [45.52, 458], [200, 458]]; // rolagem até o protocolo concluído
const FOLHAS = []; const SCK = [[0, 0]];
// fita 3D do F4 (2ª frase): "Conforme o protocolo cadastrado — neste exemplo: D0 · D7 · D9 · D11"; cada dia acende no instante em que a voz diz (d0/d7/d9/d11)
const FITA_PROT = { t0: 21.3, t1: 28.1, py: 222, dias: [B.d0, B.d7, B.d9, B.d11] };
const VISOES = [[59.21, 61.51, "menuMod", 0.12]]; // relance do Menu (Módulos › Protocolos), sem entrar
// ---- caixas do PDF (px da imagem) a partir das palavras reais do pdftotext ----
const PW_ = (t, minY = 0) => M.pdf.palavras.filter((w) => w.t === t && w.y > minY)[0];
const ULT = PW_("3344"), YTOP = PW_("ANIMAL").y - 14, YBAI = ULT.y + ULT.h + 14;
const pdfLinha = (num) => { const w = PW_(num); return { x: 121, y: w.y - 9, w: 1582, h: w.h + 18 }; };
const pdfCol = (h, larg) => { const w = PW_(h, 300); return { x: w.x - 14, y: YTOP, w: larg, h: YBAI - YTOP }; };
const ppx = (ix) => PP.cx + (ix / M.pdf.w - 0.5) * PP.w, ppy = (iy) => PP.cy + (iy / M.pdf.h - 0.5) * PP.h;
const pp = (f) => ["pp", "pdf", f];
const pg = (id, f) => ["pg", id, f], sh = (id, f) => ["sh", id, f], vw = (id, f) => ["vw", id, f];
const C0 = (m) => m.cards[0], C1 = (m) => m.cards[1];
const etapas = (m) => uniao(...C0(m).linhas.map((l) => l.etapa));
const TAPS = [
  [B.protIatf, vw("menu", (m) => m.items[1])], [38.88, pg("pi0", (m) => C0(m).botao)],
];
// navegador: waypoints (chegada, partida, alvo)
const WP = [
  { ta: 6.45, td: 6.45, puck: [350, 215] },
  { ta: B.protIatf - 0.3, td: B.protIatf + 0.25, spec: vw("menu", (m) => m.items[1]), pad: 5 },
  { ta: 9.50, td: 10.70, spec: pg("pi0", (m) => C0(m).box), pad: 4 },
  { ta: 10.95, td: 13.50, spec: pg("pi0", etapas), pad: 4 },
  { ta: 14.30, td: 14.95, spec: pg("pi0", (m) => C0(m).nome), pad: 4 },
  { ta: 15.15, td: 16.50, spec: pg("pi0", (m) => C0(m).d0), pad: 4 },
  { ta: 17.30, td: 18.30, spec: pg("pi0", (m) => uniao(...C0(m).linhas.map((l) => l.box))), pad: 3 },
  { ta: 18.45, td: 19.70, spec: pg("pi0", etapas), pad: 4 }, // 1ª frase do F4: etapa e data de cada vaca
  { ta: 19.78, td: 20.40, spec: pg("pi0", (m) => C0(m).linhas[0].data), pad: 4 },
  { ta: 21.15, td: 28.00, spec: pg("pi0", (m) => C0(m).nome), pad: 4 }, // 2ª frase: o protocolo CADASTRADO (nome real, "(D0 A D11 - 12 DIAS)")
  { ta: 28.92, td: 30.05, spec: pg("pi0", (m) => C0(m).linhas[0].selo), pad: 4 },
  { ta: 30.30, td: 31.39, spec: pg("pi0", (m) => C0(m).linhas[1].selo), pad: 4 },
  { ta: 31.64, td: 32.89, spec: pg("pi0", (m) => C0(m).linhas[2].selo), pad: 4 },
  { ta: 33.19, td: 37.45, spec: pg("pi0", (m) => C0(m).linhas[3].selo), pad: 5 },
  { ta: 38.11, td: 39.44, spec: pg("pi0", (m) => C0(m).botao), pad: 4 },
  { ta: 40.93, td: 41.58, spec: pp(() => pdfLinha("3054")), pad: 4 },
  { ta: 41.71, td: 42.28, spec: pp(() => pdfCol("D0", 150)), pad: 3 },
  { ta: 42.38, td: 42.86, spec: pp(() => pdfCol("D7", 150)), pad: 3 },
  { ta: 42.96, td: 43.44, spec: pp(() => pdfCol("D9", 125)), pad: 3 },
  { ta: 43.54, td: 44.19, spec: pp(() => pdfCol("D11", 130)), pad: 3 },
  { ta: 45.80, td: 47.62, spec: pg("pi0", (m) => C1(m).nome), pad: 4 },
  { ta: 47.94, td: 48.78, spec: pg("pi0", (m) => C1(m).box), pad: 4 },
  { ta: 48.92, td: 51.15, spec: pg("pi0", (m) => C1(m).concluido), pad: 4 },
  { ta: 51.46, td: 52.93, spec: pg("pi0", (m) => C1(m).proxima), pad: 3 },
  { ta: 53.15, td: 54.48, spec: pg("pi0", (m) => C1(m).candTit), pad: 3 },
  { ta: 54.58, td: 55.52, spec: pg("pi0", (m) => uniao(...C1(m).cands.map((c) => c.box))), pad: 3 },
  { ta: 55.63, td: 58.92, spec: pg("pi0", (m) => uniao(...C1(m).cands.map((c) => c.motivoBox))), pad: 4 },
  { ta: 60.11, td: 61.64, spec: vw("menuMod", (m) => m.items[2]), pad: 4 },
];
// câmera: [t, ...F(zoom, foco x, foco y[, y do vídeo])]
const CAM_KF = (F) => {
// G: como F, mas sobe o dolly para que a linha de baixo do conteúdo relevante (yb, px CSS da tela) fique acima da legenda (topo ≈ y 1375 do vídeo)
const G = (z, fx, fy, ay, yb) => F(z, fx, fy, Math.min(ay, 1330 - (yb - fy) * PXCSS(z)));
return [
  [5.60, 1.0, 195, 430],
  [6.90, ...F(1.3, 195, 340, 700)], [8.30, ...F(1.3, 195, 340, 700)], [9.30, ...F(1.25, 195, 420, 700)], [13.40, ...F(1.25, 195, 420, 700)],
  [14.00, ...F(1.4, 195, 255, 640)], [16.40, ...F(1.4, 195, 255, 640)], [17.20, ...F(1.3, 195, 520, 700)], [20.30, ...F(1.3, 195, 520, 700)], [21.50, ...G(0.95, 195, 240, 700, 722)], [28.00, ...G(0.95, 195, 240, 700, 722)],
  [28.65, ...G(1.55, 150, 548, 800, 722)], [37.45, ...G(1.55, 150, 548, 800, 722)],
  [37.92, ...F(1.3, 195, 330, 700)], [39.34, ...F(1.3, 195, 330, 700)],
  [39.83, ...F(0.85, 195, 440, 960)], [40.41, ...F(0.85, 195, 440, 960)], [41.32, ...F(2.25, ppx(430), ppy(560), 640)], [41.58, ...F(2.25, ppx(430), ppy(560), 640)], [42.23, ...F(2.25, ppx(800), ppy(560), 640)], [44.09, ...F(2.25, ppx(800), ppy(560), 640)],
  [45.00, ...F(1.25, 195, 420, 700)], [45.56, ...F(1.3, 195, 500, 700)], [51.05, ...F(1.3, 195, 500, 700)], [51.66, ...F(1.4, 195, 540, 700)], [56.56, ...F(1.4, 195, 540, 700)],
  [57.24, ...F(1.0, 195, 440, 960)], [59.03, ...F(1.0, 195, 440, 960)], [59.87, ...F(1.3, 195, 472, 700)], [61.64, ...F(1.3, 195, 472, 700)], [62.21, ...F(1.0, 195, 440, 960)],
  [64.8, ...F(0.95, 195, 440, 960)],
];
};
// legendas (zona segura, ≤ 2 linhas)
const LEG = [
  [5.62, 8.90, "No Menu, em <b>Reprodução</b>, toque em <b>Protocolos IATF</b>"], [9.30, 12.15, "Aqui: os protocolos com <b>etapa por fazer</b>"],
  [13.30, 16.20, "Cada protocolo mostra o <b>nome</b> e a data do <b>D0</b>"],
  [16.75, 20.40, "Cada vaca: <b>etapa</b> e <b>data</b>"], [21.30, 28.10, "Etapas do <b>protocolo cadastrado</b><br>neste exemplo <b>D0, D7, D9, D11</b>"],
  [28.83, 33.09, "<b>Selo verde</b>: o D0 já teve <b>baixa</b>"], [33.19, 37.08, "<b>Amarelo</b>: D0 não confirmado — <b>confira</b> a baixa"],
  [38.11, 40.28, "Toque em <b>Folha de campo</b> para gerar o <b>PDF</b>"], [40.67, 43.88, "<b>Linha</b> por vaca, <b>coluna</b> por dia: anote no <b>curral</b>"],
  [44.75, 47.94, "Todas as etapas feitas: o protocolo <b>continua aqui</b>"], [48.03, 49.60, "por mais um ciclo, como <b>concluído</b>"],
  [50.74, 53.15, "A data da <b>próxima visita</b>"], [53.20, 55.94, "e as vacas <b>provavelmente inseminadas</b> nesse dia"],
  [56.91, 59.63, "Esta tela é <b>só de consulta</b>"], [59.75, 61.59, "A baixa é em <b>Menu › Protocolos</b>"],
  [62.21, 65.06, "Pronto: você sabe o <b>dia de cada vaca</b>"],
];
const ETQ = [[5.6, "Menu › Reprodução"], [B.protIatf + 0.15, "Protocolos IATF"], [39.83, "Folha de campo (PDF)"], [44.39, "Protocolos IATF"], [59.21, "Menu"], [61.47, "Protocolos IATF"]];
