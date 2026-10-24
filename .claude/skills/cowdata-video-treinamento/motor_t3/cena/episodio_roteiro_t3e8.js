// ===== roteiro do Ep. 8 (Sanidade — Menu › Sanidade, módulo inteiro): instantes (voz real, beats_t3e8.json), estados da tela, navegador, câmera, legendas =====
const T_INI = 5.6, T_VIRA = 97.1, T_FIM_FRONTAL = T_VIRA, T_SELO = B.pronto + 0.1, T_SELO_FIM = 97.05, T_FIM_TOTAL = 103.4, NAV_FIM = 92.4, T_ETQ_FIM = 92.5;
const SELOS = [{ t0: T_SELO, t1: T_SELO_FIM, l1: "✔ SANIDADE", l2: "EM DIA", cor: 0x1f5a3a, f1: 130, f2: 200 }];
const FOLHAS = []; const SCK = [[0, 0]]; const VISOES = [];
// páginas: menu_sanid / na_vp / ex8 = capturas da TELA (viewport: o Menu, a gaveta "Não aplicar em …" e o dia sem sinal, com o aviso laranja real do app); as demais = capturas ALTAS (o motor rola a imagem por trás
// do cabeçalho e da barra reais). vl0 = Vacinas e exames · ex0/ex0a/ex0b/ex1 = preparação (0, 1, 2, 3 conferidos) · ex2/ex3 = quem aplica (sem e com escolha) · ex4 = como vai aplicar · ex5/ex6/ex6b = tronco (1º, 2º, 3º animal)
// ex7 = depois do "Não aplicar" · vl1 = a lista na volta · hs0 = Histórico (padrão) · hs1 = Lote(s) · hs2 = lotes 01 e 02 · hs3 = depois de marcar "Curado" · rm0/rm1 = Remédios por Doença. Instante de troca = toque + 0,1 s.
const VP = { menu_sanid: true, na_vp: true, ex8: true };
const PLANO_PG = [[0, "menu_sanid"], [12.1, "vl0"], [21.05, "ex0"], [22.3, "ex0a"], [22.75, "ex0b"], [23.2, "ex1"], [23.85, "ex2"], [24.65, "ex3"], [25.2, "ex4"], [29.95, "ex5"], [32.05, "ex6"], [33.35, "ex6b"],
  [36.55, "na_vp"], [37.85, "ex7"], [44.1, "ex8"], [45.85, "vl1"], [46.3, "menu_sanid"], [46.75, "hs0"], [57.4, "hs1"], [58.0, "hs2"], [68.9, "hs3"], [76.22, "menu_sanid"], [76.8, "rm0"], [79.4, "rm1"]];
// rolagem global; a página que sai fica parada onde estava (STEP: salto em t0 — a que sai ainda usa o valor de t0−0,001)
const STEP = (t0, de, para) => [[t0 - 0.0004, de], [t0, para]];
const SYK = [[0, 0], [14.5, 0], [15.0, 150], [16.1, 150], [16.6, 0], [20.0, 0], [20.4, 100], ...STEP(21.05, 100, 0), [29.0, 0], ...STEP(29.95, 0, 300), [37.85, 300], [38.3, 300], [38.9, 60], [45.8, 60], ...STEP(45.85, 60, 0),
  [48.4, 0], [48.95, 450], [52.3, 450], [52.9, 0], [58.9, 0], [59.5, 480], [75.5, 480], [75.95, 0], [79.39, 0], ...STEP(79.4, 0, 200), [83.0, 200], [83.6, 120], [87.2, 120], [87.8, 400], [200, 400]];
const FITAS_TXT = [
  { t0: 44.25, t1: 45.7, py: 300, l1: "FUNCIONA SEM SINAL", l2: "o dia fica guardado neste celular", larg: 8.2, alt: 2.0, f1: 130, f2: 80 },
  { t0: 73.0, t1: 75.9, py: 300, l1: "EXCEL E PDF", l2: "filtros usados + resumo por lote", larg: 8.2, alt: 2.0, f1: 150, f2: 80 },
  // o que vem do cadastro nunca é regra fixa: dose e carência mostradas são os do cadastro deste exemplo (F9 no alto; F12 embaixo, para não cobrir o aviso e as linhas contornadas)
  { t0: 61.5, t1: 69.5, py: 300, l1: "CONFORME O CADASTRO DA FAZENDA", l2: "dose e carência — neste exemplo", larg: 8.2, alt: 2.0, f1: 70, f2: 80 },
  { t0: 83.7, t1: 91.4, py: 1090, l1: "CONFORME O CADASTRO DA FAZENDA", l2: "dose e carência — neste exemplo", larg: 8.2, alt: 2.0, f1: 70, f2: 80 },
];
const pg = (id, f) => ["pg", id, f], vw = (id, f) => ["vw", id, f];
// ── caixas reais (mapa.json) ──
const acha = (lista, re, n, nome) => { const l = lista.filter((x) => re.test(x.txt)); if (!l[n || 0]) throw new Error("sem " + nome + " " + re + " #" + (n || 0)); return l[n || 0]; };
const BT = (re, n) => (m) => acha(m.botoes, re, n, "botão");                 // botão (caixa inteira)
const FO = (re, n) => (m) => acha(m.folhas, re, n, "texto").tight;          // folha de texto (caixa justa do texto)
const RO = (n) => (m) => m.rotulos[n || 0].tight;
const FX = (n) => (m) => m.faixas[n || 0];
const LS = (i) => (m) => m.linhasSan[i];
const CA = (re, n) => (m) => acha(m.cartoes, re, n, "cartão");
const LL = (i) => (m) => m.linhasLista[i];
const MI = (i) => (m) => m.menuItens[i];
const R0 = (m) => m.regs[0];
const un = (...bs) => { const x0 = Math.min(...bs.map((q) => q.x)), y0 = Math.min(...bs.map((q) => q.y)), x1 = Math.max(...bs.map((q) => q.x + q.w)), y1 = Math.max(...bs.map((q) => q.y + q.h)); return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }; };
const TAPS = [
  [12.0, vw("menu_sanid", MI(0))], [20.95, pg("vl0", LL(1))], [22.2, pg("ex0", LS(0))], [22.65, pg("ex0a", LS(1))], [23.1, pg("ex0b", LS(2))], [23.75, pg("ex1", BT(/^Tudo conferido/))],
  [24.55, pg("ex2", BT(/^Dra\. Ana/))], [25.1, pg("ex3", BT(/^Continuar$/))], [29.85, pg("ex4", BT(/^Tronco/))], [31.95, pg("ex5", BT(/APLICADO/))], [33.25, pg("ex6", BT(/APLICADO/))],
  [36.45, pg("ex6b", BT(/^Não aplicar/))], [37.75, vw("na_vp", BT(/^Doente ou em tratamento/))], [44.0, pg("ex7", BT(/Atualizar/))], [45.75, vw("ex8", (m) => m.voltar)], [46.2, pg("vl1", (m) => m.voltar)],
  [46.65, vw("menu_sanid", MI(1))], [57.3, pg("hs0", (m) => m.escopo.btns[1])], [57.68, pg("hs1", (m) => m.lotePills[0])], [57.88, pg("hs1", (m) => m.lotePills[1])],
  [68.8, pg("hs2", (m) => R0(m).botoes[0])], [76.12, pg("hs3", (m) => m.voltar)], [76.7, vw("menu_sanid", MI(2))], [79.3, pg("rm0", (m) => m.selects[0])],
];
// navegador: waypoints (chegada, partida, alvo)
const WP = [
  { ta: 5.75, td: 5.75, puck: [330, 200] },
  // F2: no Menu, em Sanidade, ficam três consultas
  { ta: 6.0, td: 6.65, spec: vw("menu_sanid", (m) => m.heads[1]), pad: 4 },
  { ta: 6.75, td: 8.0, spec: vw("menu_sanid", MI(0)), pad: 5 }, { ta: 8.2, td: 10.2, spec: vw("menu_sanid", MI(1)), pad: 5 }, { ta: 10.4, td: 11.3, spec: vw("menu_sanid", MI(2)), pad: 5 },
  { ta: 11.65, td: 12.02, spec: vw("menu_sanid", MI(0)), pad: 5 },
  // F3: Vacinas e exames — hoje e amanhã; atrasados no topo
  { ta: 12.4, td: 13.5, spec: pg("vl0", FO(/^Vacinas e exames$/)), pad: 6 }, { ta: 13.7, td: 14.4, spec: pg("vl0", FO(/^Marcados para hoje e amanhã$/)), pad: 6 },
  { ta: 15.35, td: 16.3, spec: pg("vl0", (m) => un(m.rotulos[2], m.linhasLista[1], m.linhasLista[2])), pad: 4 },
  { ta: 16.9, td: 18.5, spec: pg("vl0", LL(0)), pad: 4 }, { ta: 18.6, td: 19.5, spec: pg("vl0", RO(0)), pad: 6 }, { ta: 19.6, td: 20.3, spec: pg("vl0", FO(/^14\/10 · atrasado há 10 dias/)), pad: 6 },
  // F4: toque no dia → preparação → quem aplica → como aplicar
  { ta: 20.55, td: 20.97, spec: pg("vl0", LL(1)), pad: 4 },
  { ta: 21.5, td: 22.1, spec: pg("ex0", RO(0)), pad: 6 }, { ta: 22.15, td: 22.28, spec: pg("ex0", LS(0)), pad: 4 }, { ta: 22.55, td: 22.68, spec: pg("ex0a", LS(1)), pad: 4 }, { ta: 23.0, td: 23.12, spec: pg("ex0b", LS(2)), pad: 4 },
  { ta: 23.4, td: 23.78, spec: pg("ex1", BT(/^Tudo conferido/)), pad: 4 },
  { ta: 23.95, td: 24.35, spec: pg("ex2", RO(0)), pad: 6 }, { ta: 24.4, td: 24.57, spec: pg("ex2", BT(/^Dra\. Ana/)), pad: 4 }, { ta: 24.8, td: 25.12, spec: pg("ex3", BT(/^Continuar$/)), pad: 4 },
  { ta: 25.45, td: 26.9, spec: pg("ex4", RO(0)), pad: 6 }, { ta: 27.1, td: 28.7, spec: pg("ex4", BT(/^Tronco/)), pad: 4 }, { ta: 28.85, td: 29.5, spec: pg("ex4", BT(/^Grupo/)), pad: 4 }, { ta: 29.62, td: 29.9, spec: pg("ex4", BT(/^Tronco/)), pad: 4 },
  // F5: tronco — APLICADO · PRÓXIMO a cada animal; Não aplicar + motivo
  { ta: 30.2, td: 31.1, spec: pg("ex5", CA(/^ANIMAL 1 DE 5/i)), pad: 4 }, { ta: 31.25, td: 32.0, spec: pg("ex5", BT(/APLICADO/)), pad: 4 },
  { ta: 32.3, td: 32.9, spec: pg("ex6", CA(/^ANIMAL 1 DE 4/i)), pad: 4 }, { ta: 33.0, td: 33.3, spec: pg("ex6", BT(/APLICADO/)), pad: 4 },
  { ta: 33.7, td: 35.3, spec: pg("ex6b", CA(/^ANIMAL 1 DE 3/i)), pad: 4 }, { ta: 35.7, td: 36.5, spec: pg("ex6b", BT(/^Não aplicar/)), pad: 4 },
  { ta: 36.75, td: 37.4, spec: vw("na_vp", (m) => un(BT(/^Não estava/)(m), BT(/^Doente/)(m), BT(/^Não foi possível/)(m), BT(/^Acabou/)(m))), pad: 4 }, { ta: 37.5, td: 37.78, spec: vw("na_vp", BT(/^Doente ou em tratamento/)), pad: 4 },
  // F6: animal vendido ou morto sai da fila; o app avisa; funciona sem sinal
  { ta: 39.05, td: 41.5, spec: pg("ex7", FX(0)), pad: 4 }, { ta: 41.65, td: 43.7, spec: pg("ex7", FO(/^1 animal saiu do rebanho$/)), pad: 6 }, { ta: 43.75, td: 44.02, spec: pg("ex7", BT(/Atualizar/)), pad: 4 },
  { ta: 44.2, td: 45.6, spec: vw("ex8", (m) => m.ps[0]), pad: 5 }, { ta: 45.62, td: 45.8, spec: vw("ex8", (m) => m.voltar), pad: 5 }, { ta: 46.05, td: 46.22, spec: pg("vl1", (m) => m.voltar), pad: 5 },
  { ta: 46.45, td: 46.68, spec: vw("menu_sanid", MI(1)), pad: 5 },
  // F7: histórico — curativos e vacinas, cada um com sua etiqueta
  { ta: 46.95, td: 48.4, spec: pg("hs0", FO(/^Histórico de tratamentos e vacinas$/)), pad: 6 },
  { ta: 49.0, td: 49.7, spec: pg("hs0", (m) => m.regs[2].etiqueta), pad: 6 }, { ta: 49.8, td: 50.7, spec: pg("hs0", (m) => m.regs[1].etiqueta), pad: 6 },
  { ta: 50.8, td: 52.2, spec: pg("hs0", (m) => un(m.regs[1].etiqueta, m.regs[2].etiqueta)), pad: 6 },
  // F8: filtros — período, tipo, doença, rebanho / lotes / animais; o lote é o da data da aplicação
  { ta: 53.2, td: 54.3, spec: pg("hs0", (m) => m.periodo.uniao), pad: 4 }, { ta: 54.4, td: 55.2, spec: pg("hs0", (m) => m.grupos[0].comRotulo), pad: 4 },
  { ta: 55.3, td: 56.3, spec: pg("hs0", (m) => un(m.selects[0].label, m.selects[0])), pad: 4 }, { ta: 56.35, td: 57.1, spec: pg("hs0", (m) => m.escopo.btns[0]), pad: 4 },
  { ta: 57.2, td: 57.32, spec: pg("hs0", (m) => m.escopo.btns[1]), pad: 4 }, { ta: 57.42, td: 57.5, spec: pg("hs1", (m) => m.lotePills[0]), pad: 4 },
  { ta: 57.6, td: 57.7, spec: pg("hs1", (m) => m.lotePills[0]), pad: 4 }, { ta: 57.8, td: 57.9, spec: pg("hs1", (m) => m.lotePills[1]), pad: 4 },
  { ta: 58.2, td: 58.85, spec: pg("hs2", (m) => m.escopo.btns[2]), pad: 4 },
  { ta: 59.4, td: 60.0, spec: pg("hs2", FO(/^Lote 01 - Alta$/)), pad: 6 }, { ta: 60.05, td: 61.0, spec: pg("hs2", (m) => R0(m).lote), pad: 6 },
  // F9: cada linha mostra produto, dose, via, responsável e carência; no curativo, marque se curou
  { ta: 62.0, td: 63.3, spec: pg("hs2", (m) => R0(m).produto), pad: 6 }, { ta: 63.5, td: 64.15, spec: pg("hs2", (m) => R0(m).dose), pad: 6 }, { ta: 64.25, td: 64.8, spec: pg("hs2", (m) => R0(m).via), pad: 6 },
  { ta: 64.95, td: 65.85, spec: pg("hs2", (m) => R0(m).responsavel), pad: 6 }, { ta: 65.95, td: 66.8, spec: pg("hs2", (m) => R0(m).carencia), pad: 4 },
  { ta: 66.95, td: 67.9, spec: pg("hs2", (m) => R0(m).etiqueta), pad: 6 }, { ta: 67.95, td: 68.5, spec: pg("hs2", (m) => R0(m).grupoBotoes), pad: 4 }, { ta: 68.55, td: 68.82, spec: pg("hs2", (m) => R0(m).botoes[0]), pad: 4 },
  { ta: 69.05, td: 69.9, spec: pg("hs3", (m) => R0(m).curadoTxt), pad: 6 }, { ta: 69.95, td: 70.5, spec: pg("hs3", (m) => m.msgCura), pad: 5 },
  // F10: Excel e PDF — filtros e resumo por lote
  { ta: 70.9, td: 71.65, spec: pg("hs3", (m) => m.exportar.excel), pad: 5 }, { ta: 71.7, td: 72.3, spec: pg("hs3", (m) => m.exportar.pdf), pad: 5 }, { ta: 72.4, td: 75.7, spec: pg("hs3", (m) => m.exportar.uniao), pad: 5 },
  { ta: 75.9, td: 76.14, spec: pg("hs3", (m) => m.voltar), pad: 5 }, { ta: 76.35, td: 76.7, spec: vw("menu_sanid", MI(2)), pad: 5 },
  // F11: Remédios por Doença — escolher a doença; remédios na ordem de escolha, com o estoque de cada um
  { ta: 76.95, td: 78.0, spec: pg("rm0", FO(/^Remédios por Doença$/)), pad: 6 }, { ta: 78.2, td: 79.32, spec: pg("rm0", (m) => un(m.selects[0].label, m.selects[0])), pad: 4 },
  { ta: 79.7, td: 80.4, spec: pg("rm1", (m) => m.opcoes[0].escolha), pad: 5 }, { ta: 80.5, td: 81.0, spec: pg("rm1", (m) => m.opcoes[1].escolha), pad: 5 }, { ta: 81.05, td: 81.6, spec: pg("rm1", (m) => m.opcoes[2].escolha), pad: 5 },
  { ta: 81.7, td: 82.1, spec: pg("rm1", (m) => m.opcoes[0].status), pad: 5 }, { ta: 82.15, td: 82.5, spec: pg("rm1", (m) => m.opcoes[1].status), pad: 5 }, { ta: 82.55, td: 82.95, spec: pg("rm1", (m) => m.opcoes[2].status), pad: 5 },
  // F12: sem estoque da 1ª escolha → o app avisa qual usar; observação, dose, via e carência
  { ta: 84.0, td: 85.7, spec: pg("rm1", (m) => m.opcoes[0].status), pad: 5 }, { ta: 85.8, td: 87.1, spec: pg("rm1", (m) => m.aviso), pad: 4 },
  { ta: 88.05, td: 89.4, spec: pg("rm1", (m) => m.opcoes[1].obsTrecho.todo), pad: 5 }, { ta: 89.5, td: 90.15, spec: pg("rm1", (m) => m.opcoes[1].dose), pad: 5 },
  { ta: 90.25, td: 90.7, spec: pg("rm1", (m) => m.opcoes[1].via), pad: 5 }, { ta: 90.8, td: 91.55, spec: pg("rm1", (m) => m.opcoes[1].carencia), pad: 5 },
];
// câmera: [t, ...F(zoom, foco x, foco y[, y do vídeo])]
const MENU_C = (F) => F(1.2, 195, 420, 760);
const CAM_KF = (F) => [
  [5.60, 1.0, 195, 430],
  [6.05, ...MENU_C(F)], [12.05, ...MENU_C(F)],
  [12.35, ...F(1.3, 195, 230, 720)], [14.0, ...F(1.3, 195, 230, 720)],
  [15.0, ...F(1.2, 195, 560, 700)], [16.1, ...F(1.2, 195, 560, 700)],
  [16.65, ...F(1.3, 195, 270, 720)], [20.2, ...F(1.3, 195, 270, 720)],
  [20.45, ...F(1.2, 195, 540, 700)], [20.97, ...F(1.2, 195, 540, 700)],
  [21.15, ...F(1.2, 195, 480, 720)], [23.8, ...F(1.2, 195, 480, 720)],
  [23.95, ...F(1.15, 195, 520, 720)], [25.15, ...F(1.15, 195, 520, 720)],
  [25.3, ...F(1.3, 195, 440, 720)], [29.9, ...F(1.3, 195, 440, 720)],
  [30.05, ...F(1.2, 195, 380, 740)], [36.6, ...F(1.2, 195, 380, 740)],
  [36.7, ...F(1.15, 195, 540, 720)], [37.8, ...F(1.15, 195, 540, 720)],
  [38.0, ...F(1.3, 195, 250, 720)], [44.0, ...F(1.3, 195, 250, 720)],
  [44.15, ...F(1.3, 195, 320, 720)], [45.8, ...F(1.3, 195, 320, 720)],
  [45.9, ...F(1.2, 195, 260, 700)], [46.2, ...F(1.2, 195, 260, 700)],
  [46.32, ...MENU_C(F)], [46.7, ...MENU_C(F)],
  [46.85, ...F(1.3, 195, 240, 700)], [48.4, ...F(1.3, 195, 240, 700)],
  [48.95, ...F(1.3, 195, 320, 700)], [52.3, ...F(1.3, 195, 320, 700)],
  [52.9, ...F(1.3, 195, 345, 760)], [57.2, ...F(1.3, 195, 345, 760)],
  [57.4, ...F(1.3, 195, 520, 740)], [58.9, ...F(1.3, 195, 520, 740)],
  [59.3, ...F(1.4, 195, 400, 720)], [70.6, ...F(1.4, 195, 400, 720)],
  [70.8, ...F(1.4, 195, 330, 700)], [75.5, ...F(1.4, 195, 330, 700)],
  [75.9, ...F(1.2, 195, 250, 640)], [76.15, ...F(1.2, 195, 250, 640)],
  [76.25, ...MENU_C(F)], [76.7, ...MENU_C(F)],
  [76.85, ...F(1.3, 195, 260, 700)], [79.3, ...F(1.3, 195, 260, 700)],
  [79.45, ...F(1.05, 195, 430, 700)], [83.3, ...F(1.05, 195, 430, 700)],
  [83.8, ...F(1.3, 195, 300, 720)], [87.2, ...F(1.3, 195, 300, 720)],
  [87.8, ...F(1.4, 195, 380, 700)], [91.6, ...F(1.4, 195, 380, 700)],
  [92.9, ...F(0.95, 195, 440, 960)], [97.1, ...F(0.95, 195, 440, 960)],
];
// legendas (zona segura, ≤ 2 linhas)
const LEG = [
  [6.0, 6.7, "<b>Sanidade</b>"], [6.75, 8.1, "<b>Vacinas</b> e exames"], [8.2, 10.3, "O <b>histórico</b> de tratamentos<br>e vacinas"], [10.4, 11.4, "<b>Remédios</b> por doença"],
  [12.35, 14.0, "<b>Vacinas e exames</b>"], [14.0, 15.0, "Os dias marcados"], [15.05, 16.4, "Para <b>hoje e amanhã</b>"], [16.8, 18.5, "Dia que passou e<br>não foi fechado"], [18.55, 20.3, "Fica em <b>Atrasados</b>,<br>no topo"],
  [20.5, 21.3, "Toque no <b>dia</b>"], [21.5, 23.6, "Confira a <b>preparação</b><br>antes do curral"], [23.9, 25.2, "Diga <b>quem está aplicando</b>"], [25.4, 27.0, "E escolha<br><b>como vai aplicar</b>"], [27.1, 28.75, "No <b>tronco</b>:<br>um animal por vez"], [28.85, 29.6, "Ou em <b>grupo</b>"],
  [30.2, 31.2, "No <b>tronco</b>"], [31.25, 32.2, "Toque em <b>Aplicado</b>"], [32.25, 32.9, "<b>Próximo</b>"], [33.0, 33.9, "A <b>cada animal</b>"], [34.0, 35.5, "Animal que não vai receber"],
  [35.7, 36.5, "<b>Não aplicar</b>"], [36.75, 37.9, "E escolha o <b>motivo</b>"],
  [39.0, 41.5, "Vendido ou morto <b>sai da fila</b><br>sozinho"], [41.65, 43.75, "O app avisa:<br><b>saiu do rebanho</b>"], [44.2, 45.7, "Funciona <b>até sem sinal</b>"],
  [46.9, 48.5, "<b>Histórico</b> de tratamentos<br>e vacinas"], [48.9, 49.75, "Os <b>curativos</b>"], [49.8, 50.75, "E as <b>vacinas</b>"], [50.8, 52.3, "Cada um com sua <b>etiqueta</b>"],
  [53.2, 54.35, "Filtre pelo <b>período</b>"], [54.4, 55.25, "Pelo <b>tipo</b>"], [55.3, 56.3, "Pela <b>doença</b>"], [56.35, 57.2, "Pelo <b>rebanho</b>"], [57.22, 58.1, "Por <b>lotes</b>"], [58.15, 58.95, "Ou por <b>animais</b>"],
  [59.3, 61.0, "O <b>lote</b> é o da<br><b>data da aplicação</b>"],
  [62.0, 63.35, "Cada linha mostra<br>o <b>produto</b>"], [63.4, 64.2, "A <b>dose</b>"], [64.22, 64.85, "A <b>via</b>"], [64.9, 65.9, "O <b>responsável</b>"], [65.92, 66.85, "E a <b>carência</b>"],
  [66.95, 67.95, "No <b>curativo</b>"], [67.97, 69.8, "Marque se o animal<br><b>curou</b> ou não"], [69.9, 70.6, "<b>Curado</b>"],
  [70.8, 71.7, "<b>Excel</b>"], [71.72, 72.4, "<b>PDF</b>"], [72.45, 73.0, "Exportam o <b>relatório</b>"], [73.05, 75.9, "Com os <b>filtros</b> e o<br><b>resumo por lote</b>"],
  [76.95, 78.1, "<b>Remédios</b> por doença"], [78.2, 79.4, "Escolha a <b>doença</b>"], [79.65, 81.6, "Os remédios na <b>ordem<br>de escolha</b>"], [81.65, 83.0, "Com o <b>estoque</b> de cada um"],
  [84.0, 85.75, "<b>1ª escolha</b> sem estoque"], [85.8, 87.2, "O app avisa<br><b>qual usar</b>"], [88.0, 89.45, "A <b>observação</b>"], [89.5, 90.2, "A <b>dose</b>"], [90.25, 90.75, "A <b>via</b>"], [90.8, 91.7, "E a <b>carência</b>"],
  [92.95, 97.0, "Rebanho <b>vacinado</b>,<br>tratamento <b>registrado</b>"],
];
const ETQ = [[5.6, "Menu › Sanidade"], [12.1, "Vacinas e exames"], [46.3, "Menu › Sanidade"], [46.75, "Histórico de tratamentos e vacinas"], [76.22, "Menu › Sanidade"], [76.8, "Remédios por Doença"]];
