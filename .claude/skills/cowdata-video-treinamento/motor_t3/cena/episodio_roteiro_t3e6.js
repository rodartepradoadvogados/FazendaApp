// ===== roteiro do Ep. 6 (Produção — Menu › Produção, módulo inteiro): instantes (voz real, beats_t3e6.json), estados da tela, navegador, câmera, legendas =====
const T_INI = 5.6, T_VIRA = 89.85, T_FIM_FRONTAL = T_VIRA, T_SELO = B.pronto + 0.1, T_SELO_FIM = 89.8, T_FIM_TOTAL = 96.9, NAV_FIM = 86.95, T_ETQ_FIM = 87.05;
const SELOS = [{ t0: T_SELO, t1: T_SELO_FIM, l1: "✔ PRODUÇÃO", l2: "EM DIA", cor: 0x1f5a3a, f1: 130, f2: 200 }];
const FOLHAS = []; const SCK = [[0, 0]]; const VISOES = []; const VP = {};
// páginas (todas capturas ALTAS): mp0/mp1 = Menu com Produção aberta (sem/com o subtítulo "x kg no último") · uc0 = Últimos controles (padrão) · uc1 = Lote(s) sem lote marcado · uc1b = só o 01 · uc2 = 01 e 02
// ql0 = Qualidade (Tanque) · ql1 = Individual · se0 = Secagens · bs0 = BST · pe0 = Pesagens. Instantes de troca = toque + 0,1 s.
const PLANO_PG = [[0, "mp0"], [12.05, "uc0"], [38.05, "uc1"], [38.65, "uc1b"], [39.15, "uc2"], [44.3, "mp1"], [44.65, "ql0"], [47.4, "ql1"], [48.72, "ql0"], [55.17, "mp1"], [55.65, "se0"], [63.05, "mp1"], [63.6, "bs0"], [74.05, "mp1"], [74.85, "pe0"]];
// rolagem global; a página que sai fica parada onde estava (STEP: salto em t0 — a que sai ainda usa o valor de t0−0,001)
const STEP = (t0, de, para) => [[t0 - 0.0004, de], [t0, para]];
const SYK = [[0, 0], [5.95, 0], [6.7, 330], [11.9, 330], ...STEP(12.05, 330, 0),
  [39.2, 0], [40.0, 500], [42.85, 500], [43.3, 4300], [43.65, 4300], [44.1, 0],
  [63.15, 0], [63.4, 120], ...STEP(63.6, 120, 0),
  [74.1, 0], [74.5, 330], ...STEP(74.85, 330, 0), [200, 0]];
const FITAS_TXT = [
  { t0: 25.05, t1: 29.2, py: 300, l1: "LOTE DA DATA", l2: "onde a vaca estava naquele dia", larg: 8.2, alt: 2.0, f1: 150, f2: 80 },
  { t0: 84.2, t1: 86.85, py: 300, l1: "EXCEL E PDF", l2: "filtros usados + resumo por lote", larg: 8.2, alt: 2.0, f1: 150, f2: 80 },
];
const pg = (id, f) => ["pg", id, f], vw = (id, f) => ["vw", id, f];
// ── caixas reais (mapa.json) ──
const MI = (i) => (m) => m.menuItens[i];
const PER = (m) => m.periodo.uniao, DE = (m) => m.periodo.de, ATE = (m) => m.periodo.ate, FILTROS = (m) => uniao(m.periodo.uniao, m.escopo.caixa);
const EB = (i) => (m) => m.escopo.btns[i], ESC = (m) => m.escopo.caixa;
const GR = (m) => m.grupos[0].comRotulo, GP = (i) => (m) => m.grupos[0].pills[i];
const R0 = (m) => m.regs[0], TR = (k) => (m) => m.regs[0].tr[k], CELULA = (i) => (m) => m.regs[0].tr.grade[i];
const LP = (i) => (m) => m.lotePills[i], BL = (i) => (m) => m.blocos[i], BLK = (i, k) => (m) => m.blocos[i][k];
const VOLTAR = (m) => m.voltar, TIT = (m) => m.tituloTight, EXP = (m) => m.exportar.uniao;
const TAPS = [
  [11.93, pg("mp0", MI(0))], [37.95, pg("uc0", EB(1))], [38.55, pg("uc1", LP(0))], [39.05, pg("uc1b", LP(1))],
  [44.15, pg("uc2", VOLTAR)], [44.55, pg("mp1", MI(1))], [47.3, pg("ql0", GP(1))], [48.62, pg("ql1", GP(0))],
  [55.07, pg("ql0", VOLTAR)], [55.55, pg("mp1", MI(2))], [63.0, pg("se0", VOLTAR)], [63.5, pg("mp1", MI(3))],
  [74.0, pg("bs0", VOLTAR)], [74.75, pg("mp1", MI(4))],
];
// navegador: waypoints (chegada, partida, alvo)
const WP = [
  { ta: 5.75, td: 5.75, puck: [330, 200] },
  // F2: no Menu, em Produção, ficam cinco consultas
  { ta: 6.25, td: 6.7, spec: pg("mp0", (m) => m.heads[3]), pad: 4 },
  { ta: 6.78, td: 8.1, spec: pg("mp0", MI(0)), pad: 5 }, { ta: 8.2, td: 9.3, spec: pg("mp0", MI(1)), pad: 5 }, { ta: 9.4, td: 10.08, spec: pg("mp0", MI(2)), pad: 5 },
  { ta: 10.12, td: 10.9, spec: pg("mp0", MI(3)), pad: 5 }, { ta: 10.95, td: 11.55, spec: pg("mp0", MI(4)), pad: 5 }, { ta: 11.8, td: 11.98, spec: pg("mp0", MI(0)), pad: 5 },
  // F3: o período e o escopo são iguais em todas as consultas
  { ta: 12.5, td: 14.15, spec: pg("uc0", FILTROS), pad: 4 }, { ta: 14.25, td: 15.9, spec: pg("uc0", PER), pad: 4 },
  { ta: 15.95, td: 16.55, spec: pg("uc0", DE), pad: 4 }, { ta: 16.6, td: 17.4, spec: pg("uc0", ATE), pad: 4 }, { ta: 17.5, td: 19.0, spec: pg("uc0", ESC), pad: 4 },
  // F4: rebanho, lote(s), animal(is)
  { ta: 20.0, td: 21.1, spec: pg("uc0", EB(0)), pad: 4 }, { ta: 21.2, td: 22.25, spec: pg("uc0", EB(1)), pad: 4 }, { ta: 22.3, td: 24.5, spec: pg("uc0", EB(2)), pad: 4 },
  // F5: o lote é o da data do registro
  { ta: 25.2, td: 26.4, spec: pg("uc0", TR("lote")), pad: 5 }, { ta: 26.45, td: 27.4, spec: pg("uc0", TR("data")), pad: 5 },
  { ta: 27.45, td: 29.3, spec: pg("uc0", (m) => uniao(m.regs[0].tr.data, m.regs[0].tr.lote)), pad: 5 },
  // F6: quantos controles por vaca
  { ta: 29.65, td: 31.45, spec: pg("uc0", TIT), pad: 6 }, { ta: 31.6, td: 33.95, spec: pg("uc0", GR), pad: 4 },
  { ta: 34.02, td: 34.55, spec: pg("uc0", GP(0)), pad: 4 }, { ta: 34.65, td: 35.3, spec: pg("uc0", GP(1)), pad: 4 }, { ta: 35.4, td: 36.2, spec: pg("uc0", GP(2)), pad: 4 }, { ta: 36.3, td: 37.2, spec: pg("uc0", GP(3)), pad: 4 },
  // F7: com mais de um lote, a tela separa por lote, com nº de vacas e média
  { ta: 37.5, td: 37.97, spec: pg("uc0", EB(1)), pad: 4 }, { ta: 38.3, td: 38.57, spec: pg("uc1", LP(0)), pad: 4 }, { ta: 38.85, td: 39.07, spec: pg("uc1b", LP(1)), pad: 4 },
  { ta: 39.5, td: 40.45, spec: pg("uc2", BLK(0, "titulo")), pad: 7 }, { ta: 40.55, td: 41.85, spec: pg("uc2", BLK(0, "vacas")), pad: 6 }, { ta: 41.95, td: 42.9, spec: pg("uc2", BLK(0, "media")), pad: 6 },
  { ta: 43.0, td: 43.7, spec: pg("uc2", BL(1)), pad: 4 },
  { ta: 44.1, td: 44.2, spec: pg("uc2", VOLTAR), pad: 5 }, { ta: 44.4, td: 44.58, spec: pg("mp1", MI(1)), pad: 5 },
  // F8: qualidade do leite — tanque, individuais e os 8 indicadores
  { ta: 44.85, td: 45.7, spec: pg("ql0", GR), pad: 4 }, { ta: 45.78, td: 46.45, spec: pg("ql0", R0), pad: 4 }, { ta: 46.5, td: 47.0, spec: pg("ql0", GP(0)), pad: 4 }, { ta: 47.05, td: 47.32, spec: pg("ql0", GP(1)), pad: 4 },
  { ta: 47.5, td: 48.5, spec: pg("ql1", R0), pad: 4 }, { ta: 48.55, td: 48.67, spec: pg("ql1", GP(0)), pad: 4 },
  { ta: 48.95, td: 49.7, spec: pg("ql0", CELULA(0)), pad: 5 }, { ta: 49.75, td: 50.45, spec: pg("ql0", CELULA(1)), pad: 5 }, { ta: 50.5, td: 51.15, spec: pg("ql0", CELULA(2)), pad: 5 }, { ta: 51.2, td: 52.0, spec: pg("ql0", CELULA(3)), pad: 5 },
  { ta: 52.05, td: 52.7, spec: pg("ql0", CELULA(4)), pad: 5 }, { ta: 52.75, td: 53.55, spec: pg("ql0", CELULA(5)), pad: 5 }, { ta: 53.6, td: 54.4, spec: pg("ql0", CELULA(6)), pad: 5 }, { ta: 54.45, td: 54.9, spec: pg("ql0", CELULA(7)), pad: 5 },
  { ta: 55.0, td: 55.1, spec: pg("ql0", VOLTAR), pad: 5 }, { ta: 55.3, td: 55.58, spec: pg("mp1", MI(2)), pad: 5 },
  // F9: secagens — histórico, lote ao secar, motivo, filtro
  { ta: 56.7, td: 58.4, spec: pg("se0", R0), pad: 4 }, { ta: 58.5, td: 60.35, spec: pg("se0", TR("lote")), pad: 6 }, { ta: 60.5, td: 61.4, spec: pg("se0", TR("motivo")), pad: 6 }, { ta: 61.55, td: 62.8, spec: pg("se0", GR), pad: 4 },
  { ta: 62.95, td: 63.05, spec: pg("se0", VOLTAR), pad: 5 }, { ta: 63.35, td: 63.52, spec: pg("mp1", MI(3)), pad: 5 },
  // F10: BST — aplicações do período, DEL na aplicação e DEL de hoje, faixa de DEL, origem
  { ta: 64.85, td: 66.4, spec: pg("bs0", (m) => m.resumo), pad: 4 }, { ta: 66.45, td: 67.95, spec: pg("bs0", TR("delAp")), pad: 6 }, { ta: 68.0, td: 68.75, spec: pg("bs0", TR("delHoje")), pad: 6 },
  { ta: 69.3, td: 70.95, spec: pg("bs0", (m) => m.delUniao), pad: 4 }, { ta: 71.1, td: 71.95, spec: pg("bs0", GR), pad: 4 }, { ta: 72.0, td: 73.0, spec: pg("bs0", GP(1)), pad: 4 }, { ta: 73.2, td: 73.9, spec: pg("bs0", GP(2)), pad: 4 },
  { ta: 73.98, td: 74.08, spec: pg("bs0", VOLTAR), pad: 5 }, { ta: 74.55, td: 74.77, spec: pg("mp1", MI(4)), pad: 5 },
  // F11: pesagens — último peso e GMD de cada animal
  { ta: 75.1, td: 75.95, spec: pg("pe0", R0), pad: 4 }, { ta: 76.05, td: 76.95, spec: pg("pe0", TR("ultimo")), pad: 6 }, { ta: 77.05, td: 78.3, spec: pg("pe0", TR("gmd")), pad: 6 }, { ta: 78.4, td: 79.4, spec: pg("pe0", (m) => m.contagem), pad: 6 },
  // F12: Excel e PDF
  { ta: 80.5, td: 81.5, spec: pg("pe0", EXP), pad: 5 }, { ta: 81.55, td: 82.25, spec: pg("pe0", (m) => m.exportar.excel), pad: 5 }, { ta: 82.3, td: 83.0, spec: pg("pe0", (m) => m.exportar.pdf), pad: 5 }, { ta: 83.1, td: 86.85, spec: pg("pe0", EXP), pad: 5 },
];
// câmera: [t, ...F(zoom, foco x, foco y[, y do vídeo])]
const CM_MENU0 = (F) => F(1.3, 195, 340, 760), CM_MENUR = (F) => F(1.2, 195, 600, 800), CM_MENUP = (F) => F(1.2, 195, 500, 800), CM_VOLTA = (F) => F(1.2, 195, 250, 600);
const CAM_KF = (F) => [
  [5.60, 1.0, 195, 430],
  [6.15, ...CM_MENU0(F)], [11.9, ...CM_MENU0(F)],
  [12.5, ...F(1.3, 195, 330, 780)], [24.6, ...F(1.3, 195, 330, 780)],
  [25.1, ...F(1.4, 195, 690, 800)], [29.4, ...F(1.4, 195, 690, 800)],
  [29.9, ...F(1.4, 195, 280, 800)], [37.3, ...F(1.4, 195, 280, 800)],
  [37.7, ...F(1.3, 195, 480, 820)], [39.3, ...F(1.3, 195, 480, 820)],
  [39.9, ...F(1.4, 195, 360, 720)], [42.7, ...F(1.4, 195, 360, 720)],
  [43.1, ...F(1.4, 195, 230, 720)], [43.7, ...F(1.4, 195, 230, 720)],
  [43.95, ...CM_VOLTA(F)], [44.25, ...CM_VOLTA(F)], [44.4, ...CM_MENUR(F)], [44.6, ...CM_MENUR(F)],
  [44.8, ...F(1.3, 195, 380, 780)], [54.85, ...F(1.3, 195, 380, 780)],
  [54.95, ...CM_VOLTA(F)], [55.12, ...CM_VOLTA(F)], [55.25, ...CM_MENUR(F)], [55.6, ...CM_MENUR(F)],
  [55.95, ...F(1.4, 195, 700, 800)], [61.2, ...F(1.4, 195, 700, 800)],
  [61.5, ...F(1.3, 195, 410, 800)], [62.8, ...F(1.3, 195, 410, 800)],
  [62.88, ...CM_VOLTA(F)], [63.1, ...CM_VOLTA(F)], [63.3, ...CM_MENUR(F)], [63.55, ...CM_MENUR(F)],
  [63.9, ...F(1.4, 195, 660, 800)], [69.0, ...F(1.4, 195, 660, 800)],
  [69.25, ...F(1.3, 195, 380, 800)], [72.95, ...F(1.3, 195, 380, 800)],
  [73.15, ...F(1.3, 195, 520, 800)], [73.9, ...F(1.3, 195, 520, 800)],
  [73.93, ...CM_VOLTA(F)], [74.1, ...CM_VOLTA(F)], [74.3, ...CM_MENUP(F)], [74.8, ...CM_MENUP(F)],
  [75.0, ...F(1.4, 195, 470, 800)], [79.6, ...F(1.4, 195, 470, 800)],
  [80.1, ...F(1.4, 195, 350, 720)], [87.0, ...F(1.4, 195, 350, 720)],
  [87.5, ...F(0.95, 195, 440, 960)], [89.9, ...F(0.95, 195, 440, 960)],
];
// legendas (zona segura, ≤ 2 linhas)
const LEG = [
  [6.1, 6.7, "<b>Cinco consultas</b>"], [6.75, 8.15, "<b>Últimos controles</b><br>leiteiros"], [8.2, 9.35, "<b>Qualidade</b> do leite"], [9.4, 10.1, "<b>Secagens</b>"], [10.12, 10.9, "<b>BST</b>"], [10.95, 11.8, "<b>Pesagens</b>"],
  [12.3, 14.2, "Todas funcionam<br>do <b>mesmo jeito</b>"], [14.25, 15.9, "Escolha o <b>período</b>"], [15.95, 17.45, "Já vem com os<br><b>últimos 60 dias</b>"], [17.5, 19.1, "E depois: <b>quem</b><br>você quer ver"],
  [19.95, 21.15, "O <b>rebanho</b>"], [21.2, 22.3, "Um ou mais <b>lotes</b>"], [22.35, 24.4, "Um ou mais <b>animais</b>,<br>pelo <b>número</b>"],
  [25.0, 26.5, "O <b>lote</b> é sempre o da<br><b>data do registro</b>"], [26.55, 29.3, "Onde a vaca estava<br><b>naquele dia</b>"],
  [29.6, 31.5, "<b>Últimos controles</b> leiteiros"], [31.6, 34.0, "Quantos <b>controles por vaca</b>"], [34.02, 34.6, "O <b>último</b>"], [34.65, 35.35, "Os <b>dois</b>"], [35.4, 36.25, "Os <b>três</b> últimos"], [36.3, 37.3, "Ou <b>todos</b>"],
  [37.5, 39.0, "Com <b>mais de um lote</b>"], [39.1, 40.5, "A tela <b>separa por lote</b>"], [40.55, 41.9, "Com o <b>número de vacas</b>"], [41.95, 43.0, "E a <b>média de produção</b>"], [43.05, 43.7, "De <b>cada lote</b>"],
  [44.75, 45.7, "<b>Qualidade</b> do leite"], [45.75, 47.0, "Coletas do <b>tanque</b>"], [47.05, 48.6, "Ou <b>individuais</b>, por vaca"],
  [48.9, 49.72, "<b>CCS</b>"], [49.74, 50.47, "<b>CBT</b>"], [50.48, 51.17, "<b>Gordura</b>"], [51.18, 52.02, "<b>Proteína</b>"], [52.04, 52.72, "<b>Sólidos</b>"], [52.74, 53.57, "<b>ESD</b>"], [53.58, 54.42, "<b>Lactose</b>"], [54.44, 54.95, "<b>NUL</b>"],
  [55.7, 56.7, "<b>Secagens</b>"], [56.75, 58.45, "O <b>histórico</b> das vacas secas"], [58.5, 60.4, "Com o <b>lote</b> em que<br>estavam ao secar"], [60.5, 61.45, "E o <b>motivo</b>"], [61.5, 62.85, "Dá para <b>filtrar</b><br>pelo motivo"],
  [63.75, 64.85, "<b>BST</b>"], [64.85, 66.4, "As <b>aplicações</b> do período"], [66.45, 67.95, "<b>DEL</b> no dia da aplicação"], [68.0, 68.8, "E o <b>DEL de hoje</b>"],
  [69.3, 71.0, "Filtre por <b>faixa de DEL</b>"], [71.1, 72.0, "E pela <b>origem</b>"], [72.05, 73.05, "<b>Rotina</b> de BST"], [73.2, 73.95, "Ou <b>sanidade</b>"],
  [75.0, 76.0, "<b>Pesagens</b>"], [76.05, 77.0, "O <b>último peso</b>"], [77.05, 78.3, "E o <b>ganho médio diário</b>"], [78.4, 79.5, "De cada <b>animal</b>"],
  [80.1, 81.5, "Em <b>todas</b> as consultas"], [81.55, 82.28, "<b>Excel</b>"], [82.3, 83.05, "<b>PDF</b>"], [83.1, 84.15, "Exportam o <b>relatório</b>"], [84.2, 86.8, "Com os <b>filtros usados</b><br>e o <b>resumo por lote</b>"],
  [87.45, 89.8, "<b>Produção</b> da fazenda<br>na palma da mão"],
];
const ETQ = [[5.6, "Menu › Produção"], [12.05, "Últimos controles leiteiros"], [44.3, "Menu › Produção"], [44.65, "Qualidade do leite"], [55.17, "Menu › Produção"], [55.65, "Secagens"], [63.05, "Menu › Produção"], [63.6, "BST — aplicações"], [74.05, "Menu › Produção"], [74.85, "Pesagens"]];
