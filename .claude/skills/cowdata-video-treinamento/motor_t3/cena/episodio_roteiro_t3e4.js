// ===== roteiro do Ep. 4 (Ciclos de 21 dias — Menu › Reprodução; fecha o módulo Reprodução): instantes (voz real, beats_t3e4.json), estados da tela, navegador, câmera, legendas =====
const T_INI = 5.6, T_MENU_FIM = 7.7, T_FIM_FRONTAL = 68.6, T_VIRA = 68.6, T_SELO = B.pronto + 0.1, T_SELO_FIM = 68.55, T_FIM_TOTAL = 77.0, NAV_FIM = 64.4, T_ETQ_FIM = 64.5;
const PULSO = [-9, -8]; // (sem pulso neste episódio)
const SELOS = [{ t0: T_SELO, t1: T_SELO_FIM, l1: "✔ REPRODUÇÃO", l2: "EM DIA", cor: 0x1f5a3a, f1: 120, f2: 200 }];
const FOLHAS = []; const SCK = [[0, 0]];
// páginas (capturas altas) por instante; a rolagem é global (SYK) e vale para a página que estiver no ar (na troca, a página que sai fica parada onde estava)
const PLANO_PG = [[0, "ci0"], [55.9, "cd0"], [60.95, "ci0"]];
const SYK = [[0, 0], [29.7, 0], [30.35, 700], [47.9, 700], [48.5, 906], [54.1, 906], [54.85, 700], [55.88, 700], [55.9, 0], [58.3, 0], [58.85, 250], [59.6, 250], [60.2, 389], [60.93, 389], [60.95, 0], [200, 0]];
// fita 3D das três taxas (F5–F7): fórmulas com os números REAIS do cartão do ciclo 4 (lidos de mapa.json); cada linha acende na voz, e cada termo também
const FITA_TX = {
  t0: 30.38, t1: 42.85, py: 300, titulo: "Ciclo 4 · exemplo do cartão",
  linhas: [
    { rot: "Serviço", partes: [["inseminadas", B.inseminadas], [" ÷ "], ["aptas", B.aptas]], t: B.taxaServico, calc: [["ins", B.inseminadas], [" ÷ "], ["apt", B.aptas], [" = "], ["tS"]] },
    { rot: "Prenhez", partes: [["prenhes", B.prenhes], [" ÷ "], ["aptas p/ prenhez", B.aptasPrenhez]], t: B.taxaPrenhez, calc: [["preg", B.prenhes], [" ÷ "], ["aptP", B.aptasPrenhez], [" = "], ["tP"]] },
    { rot: "Concepção", partes: [["prenhes", B.deramPrenhez], [" ÷ "], ["inseminações com resultado", B.comResultado]], t: B.concepcaoDef, calc: [["preg", B.deramPrenhez], [" ÷ "], ["ins", B.comResultado], [" = "], ["tC"]] },
  ],
};
FITA_TX.eventos = FITA_TX.linhas.flatMap((l) => [l.t, ...l.partes.map((p) => p[1]).filter((x) => x != null)]);
const VISOES = [];
const pg = (id, f) => ["pg", id, f], vw = (id, f) => ["vw", id, f];
// ── caixas reais (mapa.json): cartões de resumo, cartões de ciclo, barras, grupos do detalhe ──
const RES = (m, i) => m.cards[i];                                  // 0 Serviço · 1 Prenhez · 2 Concepção
const CIC = (m, i) => m.cards[3 + i];                              // ciclo i+1
const BSV = (m, i) => CIC(m, i).barras[0], BPR = (m, i) => CIC(m, i).barras[1];
const VAL = (c) => c.folhas[0], METAF = (c) => c.folhas.find((f) => /^meta/.test(f.txt));
const BARRA = (b) => uniao(b.linha, b.trilha);
const ITEM_CICLOS = (m) => m.menu.find((i) => /^Ciclos de 21 dias/.test(i.txt));
const DATAS = (m) => m.ps.find((q) => /\d{2}\/\d{2}\/\d{4} a /.test(q.txt));
const TAPS = [
  [7.55, vw("menu_repro", (m) => ITEM_CICLOS(m))], [55.7, pg("ci0", (m) => CIC(m, 3))], [60.85, pg("cd0", (m) => m.voltar)],
];
// navegador: waypoints (chegada, partida, alvo)
const WP = [
  { ta: 5.75, td: 5.75, puck: [330, 200] },
  { ta: 5.95, td: 6.15, spec: vw("menu_repro", (m) => m.heads[0]), pad: 4 },
  { ta: 6.5, td: 7.65, spec: vw("menu_repro", (m) => ITEM_CICLOS(m)), pad: 5 },
  // F2 (tela): a eficiência reprodutiva da fazenda, ciclo a ciclo
  { ta: 8.3, td: 10.85, spec: pg("ci0", (m) => m.titulo), pad: 8 },
  // F3: filtros
  { ta: 12.3, td: 13.35, spec: pg("ci0", (m) => uniao(m.labels[0].span, m.labels[0].input)), pad: 4 },
  { ta: 13.5, td: 13.95, spec: pg("ci0", (m) => uniao(m.rotulos[2], m.pills[0], m.pills[1])), pad: 4 },
  { ta: 14.0, td: 14.55, spec: pg("ci0", (m) => m.pills[0]), pad: 4 },
  { ta: 14.62, td: 15.3, spec: pg("ci0", (m) => m.pills[1]), pad: 4 },
  { ta: 15.68, td: 16.75, spec: pg("ci0", (m) => uniao(m.labels[1].span, m.labels[1].input)), pad: 4 },
  { ta: 17.05, td: 17.95, spec: pg("ci0", (m) => uniao(m.rotulos[3], m.pills[2], m.pills[3], m.pills[4])), pad: 4 },
  { ta: 18.02, td: 18.5, spec: pg("ci0", (m) => m.pills[2]), pad: 4 },
  { ta: 18.66, td: 19.15, spec: pg("ci0", (m) => m.pills[3]), pad: 4 },
  { ta: 19.25, td: 19.95, spec: pg("ci0", (m) => m.pills[4]), pad: 4 },
  // F4: três taxas, verde (bate a meta) e âmbar (abaixo)
  { ta: 21.62, td: 22.5, spec: pg("ci0", (m) => uniao(RES(m, 0), RES(m, 1), RES(m, 2))), pad: 5 },
  { ta: 22.6, td: 23.3, spec: pg("ci0", (m) => RES(m, 0)), pad: 4 },
  { ta: 23.36, td: 23.95, spec: pg("ci0", (m) => RES(m, 1)), pad: 4 },
  { ta: 24.0, td: 25.1, spec: pg("ci0", (m) => RES(m, 2)), pad: 4 },
  { ta: 25.17, td: 25.5, spec: pg("ci0", (m) => VAL(RES(m, 0))), pad: 6 },
  { ta: 25.58, td: 26.25, spec: pg("ci0", (m) => VAL(RES(m, 2))), pad: 6 },
  { ta: 26.4, td: 27.2, spec: pg("ci0", (m) => uniao(VAL(RES(m, 2)), METAF(RES(m, 2)))), pad: 5 },
  { ta: 27.8, td: 28.4, spec: pg("ci0", (m) => VAL(RES(m, 1))), pad: 6 },
  { ta: 28.5, td: 29.4, spec: pg("ci0", (m) => uniao(VAL(RES(m, 1)), METAF(RES(m, 1)))), pad: 5 },
  // F5: taxa de serviço no cartão do ciclo 4 (26 ÷ 44)
  { ta: 30.45, td: 32.15, spec: pg("ci0", (m) => CIC(m, 3).servico), pad: 5 },
  { ta: 32.2, td: 32.9, spec: pg("ci0", (m) => BSV(m, 3).den), pad: 5 },
  { ta: 32.95, td: 34.3, spec: pg("ci0", (m) => BSV(m, 3).num), pad: 5 },
  // F6: taxa de prenhez (10 ÷ 42)
  { ta: 34.8, td: 36.35, spec: pg("ci0", (m) => CIC(m, 3).prenhez), pad: 5 },
  { ta: 36.4, td: 37.9, spec: pg("ci0", (m) => BPR(m, 3).den), pad: 5 },
  { ta: 37.95, td: 39.35, spec: pg("ci0", (m) => BPR(m, 3).num), pad: 5 },
  // F7: concepção (10 ÷ 26: prenhes ÷ inseminações com resultado)
  { ta: 39.4, td: 40.3, spec: pg("ci0", (m) => BPR(m, 3).num), pad: 5 },
  { ta: 40.35, td: 41.9, spec: pg("ci0", (m) => BSV(m, 3).num), pad: 5 },
  { ta: 41.95, td: 42.85, spec: pg("ci0", (m) => BPR(m, 3).num), pad: 5 },
  // F8: cada ciclo vira um cartão, com duas barras
  { ta: 43.02, td: 44.95, spec: pg("ci0", (m) => CIC(m, 3)), pad: 4 },
  { ta: 45.12, td: 45.72, spec: pg("ci0", (m) => uniao(BARRA(BSV(m, 3)), BARRA(BPR(m, 3)))), pad: 4 },
  { ta: 45.78, td: 46.62, spec: pg("ci0", (m) => BARRA(BSV(m, 3))), pad: 4 },
  { ta: 46.68, td: 47.85, spec: pg("ci0", (m) => BARRA(BPR(m, 3))), pad: 4 },
  // F9: o ciclo mais recente, em apuração (a prenhez é parcial)
  { ta: 48.5, td: 49.5, spec: pg("ci0", (m) => CIC(m, 5)), pad: 4 },
  { ta: 49.6, td: 50.7, spec: pg("ci0", (m) => CIC(m, 5).selo), pad: 6 },
  { ta: 50.78, td: 52.78, spec: pg("ci0", (m) => BARRA(BPR(m, 5))), pad: 4 },
  { ta: 52.85, td: 53.35, spec: pg("ci0", (m) => CIC(m, 5).prenhez), pad: 5 },
  { ta: 53.4, td: 53.9, spec: pg("ci0", (m) => CIC(m, 5).parcial), pad: 5 },
  // F10: toque no ciclo → os quatro grupos de vacas
  { ta: 54.95, td: 55.65, spec: pg("ci0", (m) => CIC(m, 3)), pad: 4 },
  { ta: 56.05, td: 56.45, spec: pg("cd0", (m) => uniao(m.titulo, DATAS(m))), pad: 6 },
  { ta: 56.55, td: 57.3, spec: pg("cd0", (m) => uniao(m.grupos[0].card, m.grupos[1].card)), pad: 4 },
  { ta: 57.36, td: 57.92, spec: pg("cd0", (m) => m.grupos[0].card), pad: 4 },
  { ta: 57.98, td: 58.86, spec: pg("cd0", (m) => m.grupos[1].card), pad: 4 },
  { ta: 58.92, td: 60.22, spec: pg("cd0", (m) => m.grupos[2].card), pad: 4 },
  { ta: 60.28, td: 60.7, spec: pg("cd0", (m) => m.grupos[3].card), pad: 4 },
  { ta: 60.76, td: 60.93, spec: pg("cd0", (m) => m.voltar), pad: 4 },
  // F11: exportar em Excel ou PDF
  { ta: 61.5, td: 62.25, spec: pg("ci0", (m) => m.exportUniao), pad: 5 },
  { ta: 62.32, td: 62.88, spec: pg("ci0", (m) => m.export[0]), pad: 5 },
  { ta: 62.93, td: 64.3, spec: pg("ci0", (m) => m.export[1]), pad: 5 },
];
// câmera: [t, ...F(zoom, foco x, foco y[, y do vídeo])]
const CAM_KF = (F) => {
  return [
    [5.60, 1.0, 195, 430],
    [6.05, ...F(1.2, 195, 300, 700)], [7.6, ...F(1.2, 195, 300, 700)],
    [8.1, ...F(1.2, 195, 215, 640)], [10.9, ...F(1.2, 195, 215, 640)],
    [11.8, ...F(1.2, 195, 300, 700)], [19.9, ...F(1.2, 195, 300, 700)],
    [20.8, ...F(1.2, 195, 520, 740)], [29.3, ...F(1.2, 195, 520, 740)],
    [30.3, ...F(1.2, 195, 433, 920)], [47.9, ...F(1.2, 195, 433, 920)],
    [48.5, ...F(1.2, 195, 480, 780)], [54.0, ...F(1.2, 195, 480, 780)],
    [54.85, ...F(1.2, 195, 433, 920)], [55.85, ...F(1.2, 195, 433, 920)],
    [56.0, ...F(1.0, 195, 330, 830)], [59.6, ...F(1.0, 195, 330, 830)], [60.2, ...F(1.0, 195, 330, 650)], [60.9, ...F(1.0, 195, 330, 650)],
    [61.3, ...F(1.2, 195, 465, 760)], [64.3, ...F(1.2, 195, 465, 760)],
    [64.7, ...F(0.95, 195, 440, 960)], [68.6, ...F(0.95, 195, 440, 960)],
  ];
};
// legendas (zona segura, ≤ 2 linhas)
const LEG = [
  [5.62, 7.75, "No <b>Menu</b>, em <b>Reprodução</b>:<br>toque em <b>Ciclos de 21 dias</b>"], [8.0, 11.0, "A <b>eficiência reprodutiva</b><br>da fazenda, <b>ciclo a ciclo</b>"],
  [12.1, 13.45, "Escolha a <b>data de referência</b>"], [13.5, 15.4, "Ela é o <b>início</b> ou o <b>fim</b> dos ciclos"], [15.6, 16.85, "Quantos <b>ciclos</b> quer ver"], [17.0, 19.9, "E a <b>categoria</b>:<br><b>todas</b>, <b>vacas</b> ou <b>novilhas</b>"],
  [21.0, 24.8, "Três taxas: <b>serviço</b>,<br><b>prenhez</b> e <b>concepção</b>"], [25.0, 27.4, "<b>Verde</b>: bate a meta da fazenda"], [27.7, 29.4, "<b>Âmbar</b>: fica abaixo da meta"],
  [30.4, 34.3, "<b>Serviço</b>: aptas que foram inseminadas"], [34.7, 38.6, "<b>Prenhez</b>: aptas que ficaram prenhes"], [39.3, 42.9, "<b>Concepção</b>: inseminações<br>que deram prenhez"],
  [43.0, 47.9, "Cada ciclo é um <b>cartão</b><br>com duas barras"], [48.4, 54.1, "Ciclo <b>em apuração</b>:<br>a prenhez é <b>parcial</b>"],
  [54.9, 57.3, "Toque no <b>ciclo</b> para ver as vacas"], [57.35, 60.8, "<b>Aptas</b> · <b>Inseminadas</b> ·<br><b>Aptas p/ prenhez</b> · <b>Prenhes</b>"],
  [61.3, 63.5, "Exporte em <b>Excel</b> ou <b>PDF</b>"], [64.7, 68.5, "Pronto: <b>reprodução</b> acompanhada<br>a cada 21 dias"],
];
const ETQ = [[5.6, "Menu › Reprodução"], [7.7, "Ciclos de 21 dias"], [55.9, "Ciclo 4"], [60.95, "Ciclos de 21 dias"]];
