// ===== roteiro do Ep. 7 (Alimentação — Lançar nova dieta e Necessidade Mensal; Menu › Alimentação; fecha o módulo): instantes (voz real, beats_t3e7.json), estados da tela, navegador, câmera, legendas =====
const T_INI = 5.6, T_FIM_FRONTAL = 73.3, T_VIRA = 73.3, T_SELO = 70.45, T_SELO_FIM = 73.25, T_FIM_TOTAL = 81.6, NAV_FIM = 70.3, T_ETQ_FIM = 70.4;
const SELOS = [{ t0: T_SELO, t1: T_SELO_FIM, l1: "✔ DIETA", l2: "LANÇADA", cor: 0x1f5a3a, f1: 150, f2: 200 }];
const FOLHAS = []; const SCK = [[0, 0]]; const VISOES = [];
// páginas (capturas altas, exceto o Menu e o seletor de produto, que são capturas da tela) por instante; a rolagem é global (SYK) e vale para a página no ar (na troca, a que sai fica parada onde estava)
// menu_alim = Menu com Alimentação aberta · ld0..ld8 = Lançar nova dieta em estados (0 vazio · 1 lote 02 · 2 provável fim · 3 três tratos · 4 40/30/30 + sobra · 5 produto 1 · 6 produto 1 com total · 7 quatro produtos · 8 depois de salvar)
// pk_vp = seletor de produto aberto · pl0 = Plano por Lote (já com a dieta nova) · cs0 = Consultar dietas · nm0 = Necessidade Mensal
const VP = { menu_alim: true, pk_vp: true };
const PLANO_PG = [[0, "menu_alim"], [9.7, "ld0"], [11.1, "ld1"], [21.05, "ld2"], [23.35, "ld3"], [24.8, "ld4"], [30.05, "pk_vp"], [30.95, "ld5"], [31.95, "ld6"], [33.7, "ld7"], [50.25, "ld8"],
  [51.6, "menu_alim"], [52.0, "pl0"], [54.4, "menu_alim"], [55.0, "cs0"], [57.3, "menu_alim"], [57.7, "nm0"]];
const SYK = [[0, 0], [22.0, 0], [22.5, 400], [28.4, 400], [29.0, 700], [35.0, 700], [35.4, 900], [39.0, 900], [39.7, 1546], [50.2, 1546], [50.25, 659], [50.95, 659], [51.35, 0], [52.0, 0], [52.5, 400], [54.0, 400], [54.3, 0], [200, 0]];
// placa 3D com o texto REAL do window.confirm (capturado por page.on("dialog") e gravado em mapa.confirm.msg) e os botões como texto
const CONF = (typeof M !== "undefined" && M.confirm && M.confirm.msg) || "";
const FITAS_TXT = [{ t0: 45.0, t1: 50.15, py: 400, corpo: CONF, botoes: ["Cancelar", "OK"], larg: 8.4, alt: 4.5, py2: 0 }];
const pg = (id, f) => ["pg", id, f], vw = (id, f) => ["vw", id, f];
// ── caixas reais (mapa.json) ──
const ITEM = (re) => (m) => m.menuItens.find((i) => re.test(i.txt));
const I_LANCAR = ITEM(/^Lançar nova dieta/), I_PLANO = ITEM(/^Plano por Lote/), I_CONSULTAR = ITEM(/^Consultar dietas/), I_NECESS = ITEM(/^Necessidade Mensal/);
const CL = (f) => (m) => { const b = f(m); return { ...b, w: Math.min(b.x + b.w, 376) - b.x }; }; // o campo de data do app passa da borda da tela (390 px): o contorno para na borda
const PROD = (i) => (m) => m.ld.produtos[i];
const FL = (c, re) => c.folhas.find((f) => re.test(f.txt));
const TAPS = [
  [9.6, vw("menu_alim", I_LANCAR)], [11.0, pg("ld0", (m) => m.ld.loteSelect)], [21.0, pg("ld1", CL((m) => m.ld.fim.campo))], [23.3, pg("ld2", (m) => m.editor.pills[2])], [24.75, pg("ld3", (m) => m.editor.labels[0])],
  [27.65, pg("ld4", (m) => m.editor.pillsSobra[2])], [30.0, pg("ld4", (m) => PROD(0)(m).botao)], [30.9, vw("pk_vp", (m) => m.pk.linhas[4])], [31.9, pg("ld5", (m) => PROD(0)(m).inputTotal)],
  [33.55, pg("ld6", (m) => m.ld.acrescentar)], [44.4, pg("ld7", (m) => m.ld.salvar)], [51.55, pg("ld8", (m) => m.voltar)], [51.95, vw("menu_alim", I_PLANO)],
  [54.32, pg("pl0", (m) => m.voltar)], [54.9, vw("menu_alim", I_CONSULTAR)], [57.25, pg("cs0", (m) => m.voltar)], [57.62, vw("menu_alim", I_NECESS)],
];
// navegador: waypoints (chegada, partida, alvo)
const WP = [
  { ta: 5.75, td: 5.75, puck: [330, 200] },
  // F2: No Menu, em Alimentação, toque em Lançar nova dieta
  { ta: 6.4, td: 7.9, spec: vw("menu_alim", (m) => m.heads[2]), pad: 4 },
  { ta: 8.3, td: 9.65, spec: vw("menu_alim", I_LANCAR), pad: 5 },
  // F3: escolha o lote; o app mostra animais, DEL médio, média de leite e a última dieta
  { ta: 10.15, td: 11.05, spec: pg("ld0", (m) => m.ld.loteSelect), pad: 5 },
  { ta: 12.5, td: 13.55, spec: pg("ld1", (m) => m.ld.ctx.animais), pad: 5 },
  { ta: 13.65, td: 14.7, spec: pg("ld1", (m) => m.ld.ctx.del), pad: 5 },
  { ta: 14.8, td: 15.9, spec: pg("ld1", (m) => m.ld.ctx.media), pad: 5 },
  { ta: 15.98, td: 17.3, spec: pg("ld1", (m) => m.ld.ctx.ultDieta), pad: 5 },
  // F4: data de início e provável fim
  { ta: 17.85, td: 20.3, spec: pg("ld1", (m) => m.ld.inicio.campo), pad: 4 },
  { ta: 20.4, td: 21.1, spec: pg("ld1", CL((m) => m.ld.fim.campo)), pad: 4 },
  // F5: tratos por dia, percentual de cada um, entre quais tratos a sobra é lida
  { ta: 22.1, td: 22.9, spec: pg("ld2", (m) => m.editor.titulo), pad: 6 },
  { ta: 23.0, td: 23.4, spec: pg("ld2", (m) => m.editor.pills[2]), pad: 4 },
  { ta: 23.85, td: 24.45, spec: pg("ld3", (m) => m.editor.rotuloPct), pad: 5 },
  { ta: 24.5, td: 24.78, spec: pg("ld3", (m) => m.editor.labels[0]), pad: 4 },
  { ta: 24.86, td: 25.0, spec: pg("ld4", (m) => m.editor.labels[1]), pad: 4 },
  { ta: 25.06, td: 25.3, spec: pg("ld4", (m) => m.editor.labels[2]), pad: 4 },
  { ta: 25.75, td: 26.6, spec: pg("ld4", (m) => m.editor.rotuloSobra), pad: 5 },
  { ta: 26.7, td: 27.5, spec: pg("ld4", (m) => m.editor.pillsSobraUniao), pad: 4 },
  { ta: 27.6, td: 27.8, spec: pg("ld4", (m) => m.editor.pillsSobra[2]), pad: 4 },
  // F6: para cada produto, o alimento, o total por dia do lote e a unidade
  { ta: 28.95, td: 29.55, spec: pg("ld4", (m) => PROD(0)(m).card), pad: 4 },
  { ta: 29.62, td: 30.05, spec: pg("ld4", (m) => PROD(0)(m).botao), pad: 4 },
  { ta: 30.35, td: 30.95, spec: vw("pk_vp", (m) => m.pk.linhas[4]), pad: 4 },
  { ta: 31.2, td: 31.95, spec: pg("ld5", (m) => PROD(0)(m).campoTotal), pad: 4 },
  { ta: 32.5, td: 33.35, spec: pg("ld6", (m) => PROD(0)(m).campoUnidade), pad: 4 },
  { ta: 33.42, td: 33.62, spec: pg("ld6", (m) => m.ld.acrescentar), pad: 4 },
  // F7: o app calcula na hora: por trato, total do dia, por cabeça
  { ta: 33.95, td: 35.3, spec: pg("ld7", (m) => PROD(0)(m).card), pad: 4 },
  { ta: 35.45, td: 36.7, spec: pg("ld7", (m) => PROD(0)(m).calcT), pad: 5 },
  { ta: 36.85, td: 37.95, spec: pg("ld7", (m) => PROD(0)(m).calcDia), pad: 5 },
  { ta: 38.2, td: 39.2, spec: pg("ld7", (m) => PROD(0)(m).calcCab), pad: 5 },
  // F8: no fim, o vagão soma tudo, trato a trato
  { ta: 40.2, td: 41.4, spec: pg("ld7", (m) => m.ld.vagao.caixa), pad: 4 },
  { ta: 41.45, td: 42.6, spec: pg("ld7", (m) => m.ld.vagao.t), pad: 5 },
  // F9: Salvar dieta (pulso) — a placa 3D traz o texto real do confirm
  { ta: 43.3, td: 50.15, spec: pg("ld7", (m) => m.ld.salvar), pad: 4 },
  // F10: aviso de salvo, Plano por lote (02 - Média com 3 tratos) e Consultar dietas (a anterior encerrada)
  { ta: 50.4, td: 51.0, spec: pg("ld8", (m) => m.ld.aviso.caixa), pad: 4 },
  { ta: 51.4, td: 51.6, spec: pg("ld8", (m) => m.voltar), pad: 5 },
  { ta: 51.72, td: 51.98, spec: vw("menu_alim", I_PLANO), pad: 5 },
  { ta: 52.45, td: 53.1, spec: pg("pl0", (m) => FL(m.cards[1], /^Lote 2/)), pad: 5 },
  { ta: 53.15, td: 53.85, spec: pg("pl0", (m) => m.cards[1].tratos), pad: 5 },
  { ta: 53.92, td: 54.15, spec: pg("pl0", (m) => m.cards[1].folhas.find((f) => /^T1 /.test(f.txt))), pad: 5 },
  { ta: 54.28, td: 54.36, spec: pg("pl0", (m) => m.voltar), pad: 5 },
  { ta: 54.55, td: 54.95, spec: vw("menu_alim", I_CONSULTAR), pad: 5 },
  { ta: 55.15, td: 55.9, spec: pg("cs0", (m) => m.cards[0]), pad: 4 },
  { ta: 55.95, td: 57.05, spec: pg("cs0", (m) => m.cards[3]), pad: 4 },
  { ta: 57.15, td: 57.3, spec: pg("cs0", (m) => m.voltar), pad: 5 },
  { ta: 57.4, td: 57.68, spec: vw("menu_alim", I_NECESS), pad: 5 },
  // F11: Necessidade Mensal: quanto de cada alimento no mês = consumo do dia × 30
  { ta: 58.0, td: 59.0, spec: pg("nm0", (m) => m.titulo), pad: 8 },
  { ta: 59.9, td: 60.7, spec: pg("nm0", (m) => m.nm.itens[0].valor), pad: 5 },
  { ta: 60.8, td: 61.4, spec: pg("nm0", (m) => m.nm.itens[1].valor), pad: 5 },
  { ta: 61.5, td: 62.1, spec: pg("nm0", (m) => m.nm.itens[2].valor), pad: 5 },
  { ta: 62.4, td: 64.1, spec: pg("nm0", (m) => m.nm.frase1b), pad: 5 },
  // F12: ensacado = também em sacas; a silagem fica sempre a granel
  { ta: 65.0, td: 66.4, spec: pg("nm0", (m) => m.nm.itens[1].card), pad: 4 },
  { ta: 66.5, td: 67.2, spec: pg("nm0", (m) => m.nm.itens[1].sacas), pad: 5 },
  { ta: 67.25, td: 67.9, spec: pg("nm0", (m) => m.nm.itens[3].sacas), pad: 5 },
  { ta: 68.0, td: 69.0, spec: pg("nm0", (m) => m.nm.itens[0].card), pad: 4 },
  { ta: 69.1, td: 70.2, spec: pg("nm0", (m) => m.nm.nota), pad: 4 },
];
// câmera: [t, ...F(zoom, foco x, foco y[, y do vídeo])]
const MENU_C = (F) => F(1.2, 195, 525, 900);
const CAM_KF = (F) => [
  [5.60, 1.0, 195, 430],
  [6.05, ...MENU_C(F)], [9.65, ...MENU_C(F)],
  [10.0, ...F(1.2, 195, 300, 760)], [11.8, ...F(1.2, 195, 300, 760)],
  [12.2, ...F(1.4, 195, 340, 740)], [17.3, ...F(1.4, 195, 340, 740)],
  [17.8, ...F(1.4, 195, 450, 740)], [21.3, ...F(1.4, 195, 450, 740)],
  [21.9, ...F(1.4, 195, 330, 740)], [28.4, ...F(1.4, 195, 330, 740)],
  [28.9, ...F(1.4, 195, 450, 760)], [34.0, ...F(1.4, 195, 450, 760)],
  [35.5, ...F(1.4, 195, 350, 740)], [39.0, ...F(1.4, 195, 350, 740)],
  [39.8, ...F(1.4, 195, 650, 760)], [51.0, ...F(1.4, 195, 650, 760)],
  [51.75, ...MENU_C(F)], [51.95, ...MENU_C(F)],
  [52.4, ...F(1.4, 195, 300, 740)], [54.0, ...F(1.4, 195, 300, 740)],
  [54.5, ...MENU_C(F)], [54.95, ...MENU_C(F)],
  [55.15, ...F(1.2, 195, 420, 720)], [57.2, ...F(1.2, 195, 420, 720)],
  [57.35, ...MENU_C(F)], [57.65, ...MENU_C(F)],
  [58.0, ...F(1.4, 195, 390, 740)], [69.9, ...F(1.4, 195, 390, 740)],
  [70.4, ...F(0.95, 195, 440, 960)], [73.3, ...F(0.95, 195, 440, 960)],
];
// legendas (zona segura, ≤ 2 linhas)
const LEG = [
  [6.35, 8.2, "No <b>Menu</b>, em <b>Alimentação</b>"], [8.25, 9.7, "Toque em<br><b>Lançar nova dieta</b>"],
  [10.3, 11.7, "<b>Escolha o lote</b>"], [11.75, 13.6, "O <b>número de animais</b>"], [13.65, 14.8, "O <b>DEL médio</b>"], [14.85, 15.95, "A <b>média de leite</b>"], [16.0, 17.35, "E a <b>última dieta</b> do lote"],
  [17.6, 20.3, "A <b>data de início</b>"], [20.4, 21.6, "E, se quiser, o <b>provável fim</b>"],
  [22.0, 23.9, "Os <b>tratos por dia</b>"], [24.0, 25.6, "O <b>percentual</b> de cada um"], [25.7, 28.0, "Entre quais tratos a<br><b>sobra do cocho</b> é lida"],
  [28.6, 30.0, "Para cada <b>produto</b>"], [30.05, 31.2, "Escolha o <b>alimento</b>"], [31.3, 32.7, "O <b>total por dia</b> do lote"], [32.75, 33.9, "Com a <b>unidade</b>"],
  [34.4, 35.5, "O app <b>calcula na hora</b>"], [35.55, 36.9, "Quanto vai em <b>cada trato</b>"], [36.95, 38.1, "O <b>total do dia</b>"], [38.15, 39.3, "E quanto dá por <b>cabeça</b>"],
  [39.7, 41.3, "No fim, o <b>vagão</b> soma tudo"], [41.4, 42.7, "<b>Trato a trato</b>"],
  [43.3, 44.9, "Toque em <b>Salvar dieta</b>"], [45.0, 47.0, "Se o lote já tem <b>dieta ativa</b>"], [47.1, 50.2, "<b>Encerra a atual</b> na data<br>de início da nova?"],
  [50.3, 51.9, "<b>Dieta salva</b>"], [52.1, 54.3, "A nova vale no <b>Plano por lote</b>"], [54.45, 55.3, "A anterior vai para o <b>histórico</b>"], [55.35, 57.2, "Em <b>Consultar dietas</b>"],
  [57.9, 59.9, "<b>Necessidade Mensal</b>"], [60.0, 62.3, "Quanto de <b>cada alimento</b><br>a fazenda gasta no mês"], [62.4, 64.3, "Consumo do dia <b>× 30</b>"],
  [64.9, 66.5, "O que é <b>ensacado</b>"], [66.55, 67.95, "Aparece também em <b>sacas</b>"], [68.0, 69.9, "<b>Silagem</b>: sempre a <b>granel</b>"],
  [70.5, 73.2, "<b>Dieta lançada</b><br>e compra planejada"],
];
const ETQ = [[5.6, "Menu › Alimentação"], [9.7, "Lançar nova dieta"], [51.6, "Menu › Alimentação"], [52.0, "Plano por Lote"], [54.4, "Menu › Alimentação"], [55.0, "Consultar dietas"], [57.3, "Menu › Alimentação"], [57.7, "Necessidade Mensal"]];
