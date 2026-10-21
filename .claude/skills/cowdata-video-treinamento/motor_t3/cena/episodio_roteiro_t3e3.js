// ===== roteiro do Ep. 3 (Baixa e aplicação do protocolo — Menu › Protocolos): instantes (voz real, beats_t3e3.json), estados da tela, navegador, câmera, legendas =====
const T_INI = 5.6, T_MENU_FIM = 6.5, T_FIM_FRONTAL = 62.5, T_VIRA = 62.5, T_SELO = B.pronto + 0.1, T_SELO_FIM = 62.5, T_FIM_TOTAL = 70.3, NAV_FIM = 59.6, T_ETQ_FIM = 59.7;
const PULSO = [-9, -8]; // (sem pulso neste episódio)
const SELOS = [{ t0: T_SELO, t1: T_SELO_FIM, l1: "✔ PROTOCOLO", l2: "EM DIA", cor: 0x1f5a3a, f1: 130, f2: 200 }];
const FOLHAS = []; const SCK = [[0, 0]];
// páginas (capturas altas) por instante; a rolagem é global (SYK) e vale para a página que estiver no ar
const PLANO_PG = [[0, "pl0"], [12.0, "pd0"], [19.62, "pb0"], [27.62, "pb1"], [37.17, "pb_fr"], [38.0, "pb2"], [38.5, "ps2"], [40.2, "ps_lote"], [42.3, "pb2"], [43.75, "pd1"]];
const SYK = [[0, 0], [6.7, 0], [7.5, 100], [11.9, 100], [12.4, 0], [28.9, 0], [29.7, 249], [43.6, 249], [44.1, 0], [53.0, 0], [53.9, 219], [200, 219]];
// fita 3D da baixa (F8): "Ao confirmar a baixa" + duas pílulas que acendem na voz (sanidade de cada vaca / estoque descontado)
const FITA_PROT = { t0: 44.45, t1: 48.45, py: 215, dias: [B.sanidade, B.estoque] };
const VISOES = [];
const pg = (id, f) => ["pg", id, f], vw = (id, f) => ["vw", id, f];
const PROT_ITEM = (m) => m.menu.find((i) => /^Protocolos /.test(i.txt));
const ultimaP = (m, ini) => m.ps.find((q) => q.txt.startsWith(ini));
const TAPS = [
  [6.45, vw("menuMod", (m) => PROT_ITEM(m))], [11.85, pg("pl0", (m) => m.cards[0])], [19.45, pg("pd0", (m) => m.cards[1])],
  [27.55, pg("pb0", (m) => m.labels[6].check)], [37.12, pg("pb0", (m) => m.selects[0])], [37.95, pg("pb_fr", (m) => m.selects[0].opts[1])],
  [40.15, pg("ps2", (m) => m.selects[1])], [43.45, pg("pb2", (m) => m.btns[0])],
];
const SEL_FR = () => (m) => uniao(m.labels.find((l) => /De qual frasco/.test(l.txt)), m.selects[0]);
// navegador: waypoints (chegada, partida, alvo)
const WP = [
  { ta: 5.95, td: 5.95, puck: [350, 330] },
  { ta: 6.12, td: 6.55, spec: vw("menuMod", (m) => PROT_ITEM(m)), pad: 5 },
  { ta: 7.0, td: 8.1, spec: pg("pl0", (m) => m.pills[0]), pad: 4 },
  { ta: 8.45, td: 9.45, spec: pg("pl0", (m) => uniao(...m.cards[0].kids[0].spans)), pad: 4 },
  { ta: 9.55, td: 10.35, spec: pg("pl0", (m) => uniao(...m.cards[1].kids[0].spans)), pad: 4 },
  { ta: 10.45, td: 11.25, spec: pg("pl0", (m) => uniao(...m.cards[2].kids[0].spans)), pad: 4 },
  { ta: 11.45, td: 11.98, spec: pg("pl0", (m) => m.cards[0]), pad: 4 },
  { ta: 12.9, td: 13.95, spec: pg("pd0", (m) => uniao(...m.cards.slice(0, 3))), pad: 4 },
  { ta: 14.1, td: 14.85, spec: pg("pd0", (m) => m.titulo), pad: 4 },
  { ta: 14.95, td: 15.6, spec: pg("pd0", (m) => m.cards[0]), pad: 4 },
  { ta: 15.75, td: 16.3, spec: pg("pd0", (m) => m.cards[0].kids[0].spans[1]), pad: 4 },
  { ta: 16.4, td: 16.95, spec: pg("pd0", (m) => m.cards[1].kids[0].spans[1]), pad: 4 },
  { ta: 17.15, td: 17.75, spec: pg("pd0", (m) => m.cards[0].kids.find((k) => /\d+\/\d+/.test(k.txt))), pad: 4 },
  { ta: 17.85, td: 18.45, spec: pg("pd0", (m) => m.cards[1].kids.find((k) => /\d+\/\d+/.test(k.txt))), pad: 4 },
  { ta: 18.55, td: 19.5, spec: pg("pd0", (m) => m.cards[1]), pad: 4 },
  { ta: 20.55, td: 22.7, spec: pg("pb0", (m) => uniao(m.labels[0], m.inputs[0])), pad: 4 },
  { ta: 23.05, td: 24.6, spec: pg("pb0", (m) => m.inputs[0]), pad: 4 },
  { ta: 24.75, td: 26.0, spec: pg("pb0", (m) => m.dataReal), pad: 4 },
  { ta: 26.15, td: 26.8, spec: pg("pb0", (m) => m.labels[1]), pad: 4 },
  { ta: 26.95, td: 27.58, spec: pg("pb0", (m) => m.labels[6]), pad: 4 },
  { ta: 27.9, td: 29.2, spec: pg("pb1", (m) => m.labels[1]), pad: 4 },
  { ta: 29.9, td: 31.3, spec: pg("pb2", (m) => m.oQue), pad: 4 },
  { ta: 31.6, td: 32.75, spec: pg("pb2", (m) => m.cards[0].kids[0]), pad: 4 },
  { ta: 32.85, td: 33.55, spec: pg("pb2", (m) => m.cards[0].dose), pad: 4 },
  { ta: 33.62, td: 34.3, spec: pg("pb2", (m) => m.cards[0].via), pad: 4 },
  { ta: 34.5, td: 36.0, spec: pg("pb2", (m) => m.cards[0]), pad: 4 },
  { ta: 36.4, td: 37.1, spec: pg("pb2", SEL_FR("pb2")), pad: 4 },
  { ta: 37.35, td: 37.97, spec: pg("pb_fr", (m) => m.selects[0].opts[1]), pad: 3 },
  { ta: 38.9, td: 40.0, spec: pg("ps2", (m) => uniao(m.labels.find((l) => /De qual lote/.test(l.txt)), m.selects[1])), pad: 4 },
  { ta: 40.4, td: 42.2, spec: pg("ps_lote", (m) => m.selects[1].opts[0]), pad: 3 },
  { ta: 42.55, td: 43.5, spec: pg("pb2", (m) => m.btns[0]), pad: 4 },
  { ta: 44.0, td: 45.0, spec: pg("pd1", (m) => m.cards[1].kids.find((k) => /\d+\/\d+/.test(k.txt))), pad: 4 },
  { ta: 49.35, td: 52.95, spec: pg("pd1", (m) => ultimaP(m, "Estoque de")), pad: 5 },
  { ta: 53.55, td: 55.95, spec: pg("pd1", (m) => m.cards[3]), pad: 4 },
  { ta: 56.1, td: 57.15, spec: pg("pd1", (m) => m.cards[3].kids[m.cards[3].kids.length - 1]), pad: 4 },
  { ta: 57.3, td: 59.3, spec: pg("pd1", (m) => m.cards[3].nota), pad: 3 },
];
// câmera: [t, ...F(zoom, foco x, foco y[, y do vídeo])]
const CAM_KF = (F) => {
  return [
    [5.60, 1.0, 195, 430],
    [6.05, ...F(1.15, 195, 472, 600)], [6.55, ...F(1.15, 195, 472, 600)],
    [7.30, ...F(1.2, 195, 330, 560)], [9.40, ...F(1.2, 195, 330, 560)], [9.90, ...F(1.2, 195, 500, 560)], [11.60, ...F(1.2, 195, 500, 560)],
    [12.45, ...F(1.2, 195, 292, 260)], [13.9, ...F(1.2, 195, 292, 260)], [14.1, ...F(1.2, 195, 200, 400)], [14.85, ...F(1.2, 195, 200, 400)], [15.1, ...F(1.2, 195, 292, 260)], [19.50, ...F(1.2, 195, 292, 260)],
    [20.20, ...F(1.4, 195, 350, 560)], [29.0, ...F(1.4, 195, 350, 560)],
    [29.8, ...F(1.4, 195, 440, 560)], [42.4, ...F(1.4, 195, 440, 560)],
    [42.7, ...F(1.3, 195, 520, 560)], [43.6, ...F(1.3, 195, 520, 560)],
    [44.3, ...F(1.1, 195, 400, 760)], [48.6, ...F(1.1, 195, 400, 760)],
    [49.2, ...F(1.4, 195, 300, 520)], [52.9, ...F(1.4, 195, 300, 520)],
    [53.6, ...F(1.35, 195, 650, 640)], [59.0, ...F(1.35, 195, 650, 640)],
    [59.7, ...F(0.95, 195, 440, 960)], [62.5, ...F(0.95, 195, 440, 960)],
  ];
};
// legendas (zona segura, ≤ 2 linhas)
const LEG = [
  [5.62, 6.9, "No <b>Menu</b>, toque em <b>Protocolos</b>"], [7.0, 11.5, "Em <b>andamento</b>: IATF, sanitários e produtivos"], [11.55, 12.45, "Toque no <b>protocolo</b>"],
  [13.1, 17.4, "Cada <b>dia</b> vira um <b>cartão</b>"], [17.5, 19.8, "Toque no <b>dia de hoje</b> para dar baixa"],
  [20.7, 22.9, "Confira o <b>dia</b> da aplicação"], [23.1, 26.0, "Baixa atrasada? Use a <b>data real</b>"],
  [26.15, 29.0, "Desmarque quem <b>não recebeu</b>"], [29.5, 31.3, "<b>O que aplicar</b> neste dia"], [31.4, 35.8, "<b>Medicamento</b>, <b>dose</b> e <b>via</b><br>como no protocolo cadastrado"],
  [36.3, 38.4, "De qual <b>frasco</b> saiu?"], [38.5, 42.4, "No <b>sanitário</b>, escolha o <b>lote</b><br>ou o <b>mais antigo</b> primeiro"],
  [42.7, 44.3, "Toque em <b>Confirmar baixa</b>"], [44.5, 48.4, "Entra na <b>sanidade</b> de cada vaca<br>e o <b>estoque</b> é descontado"],
  [49.3, 52.9, "Estoque <b>baixo</b> ou zerado:<br>o app <b>avisa</b>"], [53.6, 59.0, "Inseminação: <b>sem baixa</b> aqui<br>use <b>Lançar › Inseminação</b>"],
  [59.9, 62.3, "Pronto: <b>protocolo em dia</b>"],
];
const ETQ = [[5.6, "Menu › Módulos"], [6.55, "Protocolos"], [12.0, "Protocolo IATF"], [19.62, "Baixa do D7"], [38.5, "Protocolo sanitário (exemplo)"], [42.3, "Baixa do D7"], [43.75, "Protocolo IATF"]];
