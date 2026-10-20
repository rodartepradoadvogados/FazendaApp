// ===== roteiro do Ep. 2 (Protocolos IATF em andamento): instantes (voz real, beats.json), estados da tela, navegador, câmera, legendas =====
const T_INI = 5.6, T_MENU_FIM = B.protIatf + 0.06, T_FIM_FRONTAL = 60.3, T_VIRA = 60.6, T_SELO = B.pronto + 0.1, T_SELO_FIM = 60.6, T_FIM_TOTAL = 69.3, NAV_FIM = 57.3, T_ETQ_FIM = 57.4;
const PULSO = [-9, -8]; // (sem pulso neste episódio)
const SELOS = [ // carimbos 3D que descem sobre a tela
  { t0: 53.25, t1: 54.5, l1: "SÓ", l2: "CONSULTA", cor: 0x1d3557, f1: 150, f2: 180, saida: true },
  { t0: T_SELO, t1: T_SELO_FIM, l1: "✔ PROTOCOLO", l2: "EM DIA", cor: 0x1f5a3a, f1: 130, f2: 200 },
];
// folha de papel (página real do PDF): plano 500 px CSS de largura, centrado em (195, 440) do vidro do celular
const PP = { w: 500, cx: 195, cy: 440 }; PP.h = PP.w * M.pdf.h / M.pdf.w;
const PAPEL = [B.pdf + 0.03, 39.35, 39.95]; // [pousa, começa a sair, saiu]
const t_ger = 34.15, t_fimger = 39.4;
const PLANO_PG = [[0, "pi0"], [t_ger, "pi_ger"], [t_fimger, "pi0"]];
const SYK = [[0, 0], [39.75, 0], [40.65, 458], [200, 458]]; // rolagem até o protocolo concluído
const FOLHAS = []; const SCK = [[0, 0]];
const VISOES = [[54.55, 56.65, "menuMod", 0.12]]; // relance do Menu (Módulos › Protocolos), sem entrar
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
  [B.protIatf, vw("menu", (m) => m.items[1])], [34.05, pg("pi0", (m) => C0(m).botao)],
];
// navegador: waypoints (chegada, partida, alvo)
const WP = [
  { ta: 6.45, td: 6.45, puck: [350, 215] },
  { ta: B.protIatf - 0.3, td: B.protIatf + 0.25, spec: vw("menu", (m) => m.items[1]), pad: 5 },
  { ta: 9.5, td: 10.7, spec: pg("pi0", (m) => C0(m).box), pad: 4 },
  { ta: 10.95, td: 13.5, spec: pg("pi0", etapas), pad: 4 },
  { ta: 14.3, td: 14.95, spec: pg("pi0", (m) => C0(m).nome), pad: 4 },
  { ta: 15.15, td: 16.5, spec: pg("pi0", (m) => C0(m).d0), pad: 4 },
  { ta: 17.2, td: 18.25, spec: pg("pi0", (m) => uniao(...C0(m).linhas.map((l) => l.box))), pad: 3 },
  { ta: 18.45, td: 19.35, spec: pg("pi0", etapas), pad: 4 },
  { ta: 19.5, td: 20.3, spec: pg("pi0", (m) => C0(m).linhas[0].etapa), pad: 4 },
  { ta: 20.45, td: 21.2, spec: pg("pi0", (m) => C0(m).linhas[4].etapa), pad: 4 },
  { ta: 21.3, td: 22.1, spec: pg("pi0", (m) => C0(m).nome), pad: 4 },
  { ta: 22.3, td: 23.5, spec: pg("pi0", (m) => C0(m).linhas[0].data), pad: 4 },
  { ta: 24.2, td: 25.35, spec: pg("pi0", (m) => C0(m).linhas[0].selo), pad: 4 },
  { ta: 25.6, td: 26.7, spec: pg("pi0", (m) => C0(m).linhas[1].selo), pad: 4 },
  { ta: 26.95, td: 28.2, spec: pg("pi0", (m) => C0(m).linhas[2].selo), pad: 4 },
  { ta: 28.5, td: 32.6, spec: pg("pi0", (m) => C0(m).linhas[3].selo), pad: 5 },
  { ta: 33.3, td: 34.6, spec: pg("pi0", (m) => C0(m).botao), pad: 4 },
  { ta: 35.85, td: 36.6, spec: pp(() => pdfLinha("3054")), pad: 4 },
  { ta: 36.75, td: 37.35, spec: pp(() => pdfCol("D0", 150)), pad: 3 },
  { ta: 37.45, td: 37.95, spec: pp(() => pdfCol("D7", 150)), pad: 3 },
  { ta: 38.05, td: 38.55, spec: pp(() => pdfCol("D9", 125)), pad: 3 },
  { ta: 38.65, td: 39.3, spec: pp(() => pdfCol("D11", 130)), pad: 3 },
  { ta: 40.95, td: 42.95, spec: pg("pi0", (m) => C1(m).nome), pad: 4 },
  { ta: 43.3, td: 44.2, spec: pg("pi0", (m) => C1(m).box), pad: 4 },
  { ta: 44.35, td: 46.7, spec: pg("pi0", (m) => C1(m).concluido), pad: 4 },
  { ta: 47.0, td: 48.4, spec: pg("pi0", (m) => C1(m).proxima), pad: 3 },
  { ta: 48.6, td: 49.9, spec: pg("pi0", (m) => C1(m).candTit), pad: 3 },
  { ta: 50.0, td: 50.9, spec: pg("pi0", (m) => uniao(...C1(m).cands.map((c) => c.box))), pad: 3 },
  { ta: 51.0, td: 54.3, spec: pg("pi0", (m) => uniao(...C1(m).cands.map((c) => c.motivoBox))), pad: 4 },
  { ta: 55.3, td: 56.8, spec: vw("menuMod", (m) => m.items[2]), pad: 4 },
];
// câmera: [t, ...F(zoom, foco x, foco y[, y do vídeo])]
const CAM_KF = (F) => [
  [5.6, 1.0, 195, 430],
  [6.9, ...F(1.3, 195, 340, 700)], [8.3, ...F(1.3, 195, 340, 700)], [9.3, ...F(1.25, 195, 420, 700)], [13.4, ...F(1.25, 195, 420, 700)],
  [14.0, ...F(1.4, 195, 255, 640)], [16.4, ...F(1.4, 195, 255, 640)], [17.2, ...F(1.3, 195, 520, 700)], [23.2, ...F(1.3, 195, 520, 700)],
  [24.0, ...F(1.8, 150, 393, 700)], [25.0, ...F(1.8, 150, 393, 700)], [25.6, ...F(1.8, 150, 455, 700)], [26.4, ...F(1.8, 150, 455, 700)], [27.0, ...F(1.8, 150, 516, 700)], [27.9, ...F(1.8, 150, 516, 700)], [28.4, ...F(1.8, 150, 578, 700)], [32.6, ...F(1.8, 150, 578, 700)],
  [33.1, ...F(1.3, 195, 330, 700)], [34.5, ...F(1.3, 195, 330, 700)],
  [34.95, ...F(0.85, 195, 440, 960)], [35.4, ...F(0.85, 195, 440, 960)], [36.3, ...F(2.25, ppx(430), ppy(560), 640)], [36.6, ...F(2.25, ppx(430), ppy(560), 640)], [37.3, ...F(2.25, ppx(800), ppy(560), 640)], [39.2, ...F(2.25, ppx(800), ppy(560), 640)],
  [40.1, ...F(1.25, 195, 420, 700)], [40.7, ...F(1.3, 195, 500, 700)], [46.6, ...F(1.3, 195, 500, 700)], [47.2, ...F(1.4, 195, 540, 700)], [51.9, ...F(1.4, 195, 540, 700)],
  [52.6, ...F(1.0, 195, 440, 960)], [54.4, ...F(1.0, 195, 440, 960)], [55.1, ...F(1.3, 195, 472, 700)], [56.8, ...F(1.3, 195, 472, 700)], [57.5, ...F(1.0, 195, 440, 960)],
  [60.3, ...F(0.95, 195, 440, 960)],
];
// legendas (zona segura, ≤ 2 linhas)
const LEG = [
  [5.62, 8.9, "No Menu, em <b>Reprodução</b>, toque em <b>Protocolos IATF</b>"], [9.3, 12.15, "Aqui: os protocolos com <b>etapa por fazer</b>"],
  [13.3, 16.2, "Cada protocolo mostra o <b>nome</b> e a data do <b>D0</b>"],
  [16.8, 19.9, "Abaixo, <b>cada vaca</b>, com a <b>etapa</b> em que está"], [19.95, 23.0, "<b>D7</b>, <b>D9</b> ou <b>D11</b>, e a <b>data</b> dela"],
  [24.1, 28.4, "<b>Selo verde</b>: o D0 já teve <b>baixa</b>"], [28.5, 32.2, "<b>Amarelo</b>: D0 não confirmado — <b>confira</b> a baixa"],
  [33.3, 35.3, "Toque em <b>Folha de campo</b> para gerar o <b>PDF</b>"], [35.6, 39.0, "<b>Linha</b> por vaca, <b>coluna</b> por dia: anote no <b>curral</b>"],
  [39.85, 43.3, "Todas as etapas feitas: o protocolo <b>continua aqui</b>"], [43.4, 45.1, "por mais um ciclo, como <b>concluído</b>"],
  [46.3, 48.6, "A data da <b>próxima visita</b>"], [48.65, 51.3, "e as vacas <b>provavelmente inseminadas</b> nesse dia"],
  [52.25, 54.9, "Esta tela é <b>só de consulta</b>"], [55.0, 56.75, "A baixa é em <b>Menu › Protocolos</b>"],
  [57.5, 60.5, "Pronto: você sabe o <b>dia de cada vaca</b>"],
];
const ETQ = [[5.6, "Menu › Reprodução"], [B.protIatf + 0.15, "Protocolos IATF"], [34.95, "Folha de campo (PDF)"], [39.5, "Protocolos IATF"], [54.55, "Menu"], [56.6, "Protocolos IATF"]];
