// ===== roteiro do Ep. 5 (Alimentação — Plano por lote e Consultar dietas; Menu › Alimentação): instantes (voz real, beats_t3e5.json), estados da tela, navegador, câmera, legendas =====
const T_INI = 5.6, T_FIM_FRONTAL = 62.95, T_VIRA = 62.95, T_SELO = B.pronto + 0.1, T_SELO_FIM = 62.9, T_FIM_TOTAL = 69.6, NAV_FIM = 57.45, T_ETQ_FIM = 57.55;
const SELOS = [{ t0: T_SELO, t1: T_SELO_FIM, l1: "✔ PLANO", l2: "EM DIA", cor: 0x1f5a3a, f1: 150, f2: 200 }];
const FOLHAS = []; const SCK = [[0, 0]]; const VISOES = [];
// páginas (capturas altas, exceto o Menu, que é uma captura da tela) por instante; a rolagem é global (SYK) e vale para a página que estiver no ar (na troca, a página que sai fica parada onde estava)
// menu_alim = Menu com "Alimentação" aberta · pl0 = Plano por Lote · ld0 = Lançar nova dieta (editor "Tratos por dia" em 3 tratos 40/30/30) · cs0 = Consultar dietas · cs1 = a dieta encerrada do 01 - Alta aberta
const VP = { menu_alim: true };
const PLANO_PG = [[0, "menu_alim"], [10.8, "pl0"], [27.55, "menu_alim"], [28.8, "ld0"], [39.22, "menu_alim"], [39.72, "pl0"], [43.9, "menu_alim"], [45.02, "cs0"], [53.0, "cs1"]];
const SYK = [[0, 0], [35.0, 0], [35.8, 300], [38.55, 300], [39.05, 0], [39.8, 0], [40.6, 627], [43.2, 627], [43.7, 0], [53.0, 0], [53.9, 335], [200, 335]];
// fitas 3D de texto (presas à câmera, na zona livre do alto): [t0, t1, py(px do vídeo), linha 1, linha 2]
const FITAS_TXT = [
  { t0: 24.35, t1: 27.5, py: 300, l1: "ATENÇÃO", l2: "o cálculo por trato depende do cadastro na dieta", larg: 8.2, alt: 2.0, f1: 150, f2: 62 },
  { t0: 29.0, t1: 35.5, py: 300, l1: "NO SITE", l2: "Insumos e sanidade › Alimentação › Lançar nova dieta", larg: 8.2, alt: 2.0, f1: 120, f2: 62 },
  { t0: 39.8, t1: 43.3, py: 300, l1: "SEM CADASTRO", l2: "= 2 tratos, de 50% cada", larg: 8.2, alt: 2.0, f1: 140, f2: 80 },
];
const pg = (id, f) => ["pg", id, f], vw = (id, f) => ["vw", id, f];
// ── caixas reais (mapa.json) ──
const ITEM = (re) => (m) => m.menuItens.find((i) => re.test(i.txt));
const I_PLANO = ITEM(/^Plano por Lote/), I_LANCAR = ITEM(/^Lançar nova dieta/), I_CONSULTAR = ITEM(/^Consultar dietas/);
const PC = (m, i) => m.cards[i];                                              // cartão do lote i (Plano) / da dieta i (Consultar)
const FL = (c, re) => c.folhas.find((f) => re.test(f.txt));                   // primeira folha de texto que casa (a 1ª = Silagem)
const TIT = (c) => FL(c, /^Lote/), SIL = (c) => c.linhas[1], T_LIN = (c) => FL(c, /^T1 /), DIA = (c) => c.dia, CAB = (c) => c.cab;
const PARAGRAFO = (m) => m.ps.find((q) => /^T1, T2/.test(q.txt));
const ED = (m) => m.editor, LAB = (m, i) => m.editor.labels[i];
const ATIVA = (c) => { const f = FL(c, /^(Ativa|Encerrada)$/); return { x: f.x, y: f.y, w: f.txt === "Ativa" ? 33 : 63, h: f.h }; }, DATAS = (c) => FL(c, /^Início/);
const TAPS = [
  [10.7, vw("menu_alim", I_PLANO)], [27.4, pg("pl0", (m) => m.voltar)], [28.65, vw("menu_alim", I_LANCAR)], [39.1, pg("ld0", (m) => m.voltar)],
  [39.55, vw("menu_alim", I_PLANO)], [43.78, pg("pl0", (m) => m.voltar)], [44.9, vw("menu_alim", I_CONSULTAR)], [52.9, pg("cs0", (m) => PC(m, 3).linhas[0])],
];
// navegador: waypoints (chegada, partida, alvo)
const WP = [
  { ta: 5.75, td: 5.75, puck: [330, 200] },
  // F2: no Menu, em Alimentação, ficam o Plano por lote e o Consultar dietas
  { ta: 6.4, td: 7.95, spec: vw("menu_alim", (m) => m.heads[2]), pad: 4 },
  { ta: 8.38, td: 9.35, spec: vw("menu_alim", I_PLANO), pad: 5 },
  { ta: 9.44, td: 10.5, spec: vw("menu_alim", I_CONSULTAR), pad: 5 },
  { ta: 10.62, td: 10.75, spec: vw("menu_alim", I_PLANO), pad: 5 },
  // F3: o Plano por lote mostra o que vale hoje: a dieta ativa de cada lote, com o número de animais
  { ta: 11.2, td: 12.5, spec: pg("pl0", (m) => m.titulo), pad: 8 },
  { ta: 12.6, td: 13.85, spec: pg("pl0", (m) => PC(m, 0)), pad: 4 },
  { ta: 13.95, td: 14.7, spec: pg("pl0", (m) => PC(m, 0).tratos), pad: 5 },
  { ta: 14.76, td: 15.55, spec: pg("pl0", (m) => TIT(PC(m, 0))), pad: 6 },
  { ta: 15.66, td: 17.0, spec: pg("pl0", (m) => PC(m, 0).efetivo), pad: 5 },
  // F4: para cada alimento: quantidade por cabeça, total do dia, quanto vai em cada trato
  { ta: 17.45, td: 19.35, spec: pg("pl0", (m) => SIL(PC(m, 0))), pad: 3 },
  { ta: 19.46, td: 20.9, spec: pg("pl0", (m) => CAB(PC(m, 0))), pad: 5 },
  { ta: 20.97, td: 22.05, spec: pg("pl0", (m) => DIA(PC(m, 0))), pad: 5 },
  { ta: 22.12, td: 24.9, spec: pg("pl0", (m) => T_LIN(PC(m, 0))), pad: 5 },
  // F5: atenção: o cálculo por trato depende do cadastro na dieta (a própria tela diz: "pelo % cadastrado na dieta do lote")
  { ta: 25.1, td: 27.3, spec: pg("pl0", (m) => PARAGRAFO(m)), pad: 5 },
  { ta: 27.34, td: 27.42, spec: pg("pl0", (m) => m.voltar), pad: 5 },
  { ta: 27.78, td: 28.64, spec: vw("menu_alim", I_LANCAR), pad: 5 },
  // Lançar nova dieta: tratos por dia (1 a 4), % de cada um, soma 100%
  { ta: 29.55, td: 31.15, spec: pg("ld0", (m) => ED(m).titulo), pad: 6 },
  { ta: 31.24, td: 32.3, spec: pg("ld0", (m) => ED(m).pillsUniao), pad: 4 },
  { ta: 32.36, td: 32.75, spec: pg("ld0", (m) => LAB(m, 0)), pad: 4 },
  { ta: 32.82, td: 33.0, spec: pg("ld0", (m) => LAB(m, 1)), pad: 4 },
  { ta: 33.06, td: 33.42, spec: pg("ld0", (m) => LAB(m, 2)), pad: 4 },
  { ta: 33.5, td: 34.9, spec: pg("ld0", (m) => ED(m).soma), pad: 6 },
  // F6: ali também se informa entre quais tratos a sobra do cocho é lida
  { ta: 35.9, td: 37.6, spec: pg("ld0", (m) => ED(m).rotuloSobra), pad: 5 },
  { ta: 37.68, td: 38.3, spec: pg("ld0", (m) => ED(m).pillsSobraUniao), pad: 4 },
  { ta: 38.36, td: 38.55, spec: pg("ld0", (m) => ED(m).pillsSobra[2]), pad: 4 },
  { ta: 39.04, td: 39.12, spec: pg("ld0", (m) => m.voltar), pad: 5 },
  // F7: sem esse cadastro, o app considera dois tratos de 50% (lote 05 - Pré-parto, sem cadastro)
  { ta: 39.3, td: 39.6, spec: vw("menu_alim", I_PLANO), pad: 5 },
  { ta: 40.5, td: 41.08, spec: pg("pl0", (m) => TIT(PC(m, 2))), pad: 6 },
  { ta: 41.12, td: 41.9, spec: pg("pl0", (m) => PC(m, 2).tratosN), pad: 5 },
  { ta: 41.96, td: 43.25, spec: pg("pl0", (m) => PC(m, 2).tratosPct), pad: 5 },
  { ta: 43.74, td: 43.82, spec: pg("pl0", (m) => m.voltar), pad: 5 },
  // F8: Consultar dietas = histórico completo (todas as dietas de cada lote, ativas e encerradas, com início e fim)
  { ta: 44.05, td: 44.95, spec: vw("menu_alim", I_CONSULTAR), pad: 5 },
  { ta: 45.25, td: 46.75, spec: pg("cs0", (m) => m.titulo), pad: 8 },
  { ta: 47.1, td: 48.8, spec: pg("cs0", (m) => uniao(PC(m, 0), PC(m, 4))), pad: 4 },
  { ta: 48.9, td: 49.12, spec: pg("cs0", (m) => ATIVA(PC(m, 0))), pad: 6 },
  { ta: 49.17, td: 49.32, spec: pg("cs0", (m) => ATIVA(PC(m, 1))), pad: 6 },
  { ta: 49.36, td: 49.58, spec: pg("cs0", (m) => ATIVA(PC(m, 2))), pad: 6 },
  { ta: 49.66, td: 49.92, spec: pg("cs0", (m) => ATIVA(PC(m, 3))), pad: 6 },
  { ta: 49.97, td: 50.3, spec: pg("cs0", (m) => ATIVA(PC(m, 4))), pad: 6 },
  { ta: 50.42, td: 51.75, spec: pg("cs0", (m) => DATAS(PC(m, 3))), pad: 5 },
  // F9: toque numa dieta: alimentos, tratos daquela época, total do vagão
  { ta: 52.45, td: 52.88, spec: pg("cs0", (m) => PC(m, 3).linhas[0]), pad: 4 },
  { ta: 53.6, td: 54.72, spec: pg("cs1", (m) => uniao(m.apres.itens[0], m.apres.itens[3])), pad: 4 },
  { ta: 54.8, td: 56.25, spec: pg("cs1", (m) => m.apres.tratosTrecho), pad: 5 },
  { ta: 56.33, td: 57.3, spec: pg("cs1", (m) => m.apres.vagao), pad: 4 },
];
// câmera: [t, ...F(zoom, foco x, foco y[, y do vídeo])]
const MENU_C = (F) => F(1.2, 195, 525, 900);
const CAM_KF = (F) => [
  [5.60, 1.0, 195, 430],
  [6.05, ...MENU_C(F)], [10.65, ...MENU_C(F)],
  [11.0, ...F(1.2, 195, 330, 800)], [16.9, ...F(1.2, 195, 330, 800)],
  [17.4, ...F(1.4, 195, 345, 760)], [23.9, ...F(1.4, 195, 345, 760)],
  [24.3, ...F(1.4, 195, 270, 760)], [27.3, ...F(1.4, 195, 270, 760)],
  [27.9, ...MENU_C(F)], [28.7, ...MENU_C(F)],
  [29.3, ...F(1.4, 195, 590, 880)], [31.9, ...F(1.4, 195, 590, 880)],
  [32.2, ...F(1.4, 195, 740, 960)], [34.7, ...F(1.4, 195, 740, 960)],
  [35.2, ...F(1.4, 195, 600, 900)], [38.5, ...F(1.4, 195, 600, 900)],
  [38.95, ...F(1.2, 195, 525, 900)], [39.6, ...MENU_C(F)],
  [40.0, ...F(1.4, 195, 470, 760)], [43.2, ...F(1.4, 195, 470, 760)],
  [43.75, ...MENU_C(F)], [44.9, ...MENU_C(F)],
  [45.2, ...F(1.2, 195, 300, 520)], [46.9, ...F(1.2, 195, 300, 520)],
  [47.4, ...F(1.2, 195, 455, 720)], [52.6, ...F(1.2, 195, 455, 720)],
  [53.6, ...F(1.4, 195, 440, 880)], [57.4, ...F(1.4, 195, 440, 880)],
  [58.0, ...F(0.95, 195, 440, 960)], [62.95, ...F(0.95, 195, 440, 960)],
];
// legendas (zona segura, ≤ 2 linhas)
const LEG = [
  [6.2, 8.3, "No <b>Menu</b>, em <b>Alimentação</b>"], [8.35, 10.6, "<b>Plano por lote</b> e<br><b>Consultar dietas</b>"],
  [11.2, 13.4, "O <b>Plano por lote</b> mostra<br>o que <b>vale hoje</b>"], [13.5, 15.6, "A <b>dieta ativa</b> de cada lote"], [15.65, 17.4, "Com o <b>número de animais</b>"],
  [17.5, 19.4, "Para cada <b>alimento</b>:"], [19.45, 20.95, "<b>Quantidade por cabeça</b>"], [21.0, 22.3, "<b>Total do dia</b>"], [22.35, 24.0, "E quanto vai em <b>cada trato</b>"],
  [24.3, 27.45, "<b>Atenção</b>: o cálculo por trato<br>depende do <b>cadastro na dieta</b>"], [27.8, 29.5, "Menu › <b>Lançar nova dieta</b>"],
  [29.7, 31.2, "Quantos <b>tratos por dia</b>"], [31.25, 32.3, "De <b>1 a 4</b>"], [32.35, 33.45, "O <b>percentual</b> de cada trato"], [33.5, 35.0, "Somando <b>100%</b>"],
  [35.9, 38.9, "Entre quais tratos a<br><b>sobra do cocho</b> é lida"],
  [39.55, 41.1, "<b>Sem cadastro</b>..."], [41.15, 43.25, "O app considera <b>2 tratos</b><br>de <b>50%</b> cada"],
  [44.1, 45.6, "<b>Consultar dietas</b>"], [45.7, 47.0, "É o <b>histórico completo</b>"], [47.15, 48.9, "<b>Todas</b> as dietas de cada lote"], [48.95, 50.5, "<b>Ativas</b> e <b>encerradas</b>"], [50.55, 52.4, "Com <b>início</b> e <b>fim</b>"],
  [52.5, 53.9, "Toque numa <b>dieta</b>"], [53.95, 54.75, "Os <b>alimentos</b>"], [54.8, 56.3, "Os <b>tratos</b> daquela época"], [56.35, 57.4, "E o total do <b>vagão</b>"],
  [58.1, 62.7, "<b>Plano</b> = o que vale hoje<br><b>Consulta</b> = o histórico"],
];
const ETQ = [[5.6, "Menu › Alimentação"], [10.8, "Plano por Lote"], [27.55, "Menu › Alimentação"], [28.8, "Lançar nova dieta"], [39.22, "Menu › Alimentação"], [39.72, "Plano por Lote"], [43.9, "Menu › Alimentação"], [45.02, "Consultar dietas"]];
