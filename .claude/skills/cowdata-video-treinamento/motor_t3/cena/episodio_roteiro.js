// ===== roteiro do episódio: instantes (voz real, beats.json), estados da tela, navegador, câmera, legendas =====
const T_INI = 5.6, T_MENU_FIM = B.agendaRep + 0.06, T_FIM_FRONTAL = 89.6, T_VIRA = 89.9, T_SELO = 87.9, T_SELO_FIM = 89.9, T_FIM_TOTAL = 98.6, NAV_FIM = 87.35, T_ETQ_FIM = 87.6;
const PULSO = [60.6, 63.3];
// páginas altas, por instante de troca (dissolve curto)
const t_ = {
  salvar: B.salvar + 0.02, a1: B.aTocar + 0.04, a2: B.aReconf + 0.04, a3: B.reconfirmadas + 0.04, limpa: B.filtram + 1.45, abre: B.abra + 0.06, gest: B.selo + 0.02,
  fecha: 62.55, buscar: B.buscar + 0.04, lista: B.inseminadasLista + 0.1, ficha: B.vaca + 0.08, volta: 83.4, mail: 84.55, fim: 87.4,
};
const PLANO_PG = [[0, "ag0"], [t_.salvar, "ag1"], [t_.a1, "f1"], [t_.a2, "f2"], [t_.a3, "f3"], [t_.limpa, "ag1"], [t_.abre, "ag2"], [t_.gest, "ag3"], [t_.fecha, "ag1"], [t_.buscar, "ag5"], [t_.lista, "ag7"], [t_.mail, "ag8"], [t_.fim, "ag1"]];
// rolagem da página (px CSS), interpolada
const SYK = [[0, 0], [B.abra + 0.1, 0], [B.abra + 0.95, 380], [56.1, 380], [56.7, 190], [57.0, 190], [57.9, 330], [62.3, 330], [62.55, 0], [B.buscar, 0], [B.buscar + 0.9, 480], [72.0, 480], [74.8, 1070], [87.2, 1070], [87.4, 0], [200, 0]];
// folhas: [abre, fecha, [[t, id]...]]
const FOLHAS = [
  [B.novoCard + 0.06, t_.salvar + 0.05, [[0, "d0"], [19.6, "dn1"], [19.75, "dn2"], [19.9, "dn3"], [20.05, "dn4"], [20.2, "dn5"], [20.55, "dcat"], [22.0, "dlote"], [22.95, "dsit"], [B.emInsem + 0.05, "dins"], [34.05, "dde"], [34.9, "date"], [35.95, "dchip"]]],
  [63.4, 64.7, [[0, "dedit"]]],
];
const SCK = [[0, 0], [36.0, 0], [36.4, 58], [300, 58]];
const VISOES = [[21.24, 21.66, "pk0", 0.08], [21.66, 21.98, "pk1", 0.05], [t_.ficha, t_.volta, "ficha_vp", 0.1]];
// toques (instante, alvo) — onda no navegador
const pg = (id, f) => ["pg", id, f], sh = (id, f) => ["sh", id, f], vw = (id, f) => ["vw", id, f];
const det30 = (m) => m.dets.find((d) => /Inseminadas 30–59 dias/.test(d.txt));
const TAPS = [
  [B.agendaRep, vw("menu", (m) => m.items[0])], [B.novoCard, pg("ag0", (m) => m.novo)], [20.55, sh("dcat", (m) => m.categoria)], [21.2, sh("dcat", (m) => m.loteBtn)],
  [21.64, vw("pkx", (m) => m.tr[2])], [21.96, vw("pkx", (m) => m.ok)], [22.9, sh("dlote", (m) => m.situacao)], [B.emInsem, sh("dsit", (m) => m.opcoes[1])],
  [35.9, sh("date", (m) => m.adicionar)], [B.salvar, sh("dchip", (m) => m.salvar)],
  [B.aTocar, pg("ag1", (m) => m.btns[0])], [B.aReconf, pg("f1", (m) => m.btns[1])], [B.reconfirmadas, pg("f2", (m) => m.btns[2])], [B.filtram + 1.45, pg("f3", (m) => m.limpar)],
  [B.abra, pg("ag1", (m) => m.dets[3].sum)], [B.selo, pg("ag2", (m) => m.dets[1].sum)], [63.3, pg("ag1", (m) => m.dets[3].gear)], [64.65, sh("dedit", (m) => m.fechar)],
  [B.buscar, pg("ag1", (m) => m.dets[4].sum)], [B.inseminadasLista + 0.1, pg("ag5", (m) => m.dets[6].sum)], [B.vaca + 0.06, pg("ag7", (m) => m.dets.find((d) => /Inseminadas 30–59 dias/.test(d.txt)).rowsLista[0].link)],
  [83.3, vw("fichaBoxes", (m) => m.voltar)], [84.5, pg("ag7", (m) => det30(m).rowsLista[0].mail)],
];
// navegador: waypoints (chegada, partida, alvo)
const WP = [
  { ta: 6.45, td: 6.45, puck: [350, 215] },
  { ta: 7.35, td: 8.2, spec: vw("menu", (m) => m.items[0]), pad: 5 },
  { ta: 12.55, td: 13.2, spec: pg("ag0", (m) => m.titulo), pad: 7 },
  { ta: 13.55, td: 14.6, spec: pg("ag0", (m) => uniao(m.dets[0], m.dets[1], m.dets[2])), pad: 3 },
  { ta: 14.95, td: 15.7, spec: pg("ag0", (m) => m.dets[0]), pad: 2 },
  { ta: 15.85, td: 16.55, spec: pg("ag0", (m) => m.dets[1]), pad: 2 },
  { ta: 16.7, td: 17.5, spec: pg("ag0", (m) => m.dets[2]), pad: 2 },
  { ta: 17.95, td: 18.5, spec: pg("ag0", (m) => m.novo), pad: 5 },
  { ta: 19.35, td: 20.3, spec: sh("d0", (m) => m.nome), pad: 4 },
  { ta: 20.42, td: 20.95, spec: sh("dcat", (m) => m.categoria), pad: 4 },
  { ta: 21.05, td: 21.45, spec: sh("dcat", (m) => m.loteBtn), pad: 4 },
  { ta: 21.55, td: 21.9, spec: vw("pkx", (m) => m.tr[2]), pad: 2 },
  { ta: 21.9, td: 22.0, spec: vw("pkx", (m) => m.ok), pad: 3 },
  { ta: 22.3, td: 22.95, spec: sh("dlote", (m) => m.situacao), pad: 4 },
  { ta: 23.3, td: 23.8, spec: sh("dsit", (m) => m.opcoes[0]), pad: 1 },
  { ta: 23.9, td: 24.7, spec: sh("dsit", (m) => m.opcoes[1]), pad: 1 },
  { ta: 24.8, td: 25.45, spec: sh("dsit", (m) => m.opcoes[2]), pad: 1 },
  { ta: 25.55, td: 26.1, spec: sh("dsit", (m) => m.opcoes[3]), pad: 1 },
  { ta: 26.2, td: 27.6, spec: sh("dsit", (m) => m.opcoes[4]), pad: 1 },
  { ta: 27.75, td: 28.7, spec: sh("dsit", (m) => m.opcoes[5]), pad: 1 },
  { ta: 29.3, td: 29.7, spec: sh("dsit", (m) => m.opcoes[1]), pad: 1 },
  { ta: 30.6, td: 33.4, spec: sh("dins", (m) => uniao(m.periodoLabel, m.nums[0], m.nums[1])), pad: 5 },
  { ta: 33.7, td: 34.5, spec: sh("dins", (m) => m.nums[0]), pad: 4 },
  { ta: 34.6, td: 35.15, spec: sh("dins", (m) => m.nums[1]), pad: 4 },
  { ta: 35.3, td: 36.2, spec: sh("date", (m) => m.adicionar), pad: 4 },
  { ta: 36.4, td: 37.35, spec: sh("dchip", (m) => m.chips[0]), pad: 4 },
  { ta: 37.65, td: 38.7, spec: sh("dchip", (m) => m.salvar), pad: 4 },
  { ta: 39.3, td: 43.3, spec: pg("ag1", (m) => m.dets[3]), pad: 3 },
  { ta: 43.95, td: 44.75, spec: pg("ag1", (m) => m.btns[0]), pad: 4 },
  { ta: 45.0, td: 45.95, spec: pg("f1", (m) => m.btns[1]), pad: 4 },
  { ta: 46.1, td: 47.15, spec: pg("f2", (m) => m.btns[2]), pad: 4 },
  { ta: 47.4, td: 48.35, spec: pg("f3", (m) => uniao(m.dets[0], m.dets[3])), pad: 3 },
  { ta: 48.55, td: 49.0, spec: pg("f3", (m) => m.limpar), pad: 4 },
  { ta: 49.3, td: 49.95, spec: pg("ag1", (m) => m.dets[3].sum), pad: 3 },
  { ta: 51.5, td: 52.05, spec: pg("ag2", (m) => m.dets[3].rows[1].toque), pad: 4 },
  { ta: 52.15, td: 52.75, spec: pg("ag2", (m) => m.dets[3].rows[1].retoque), pad: 4 },
  { ta: 52.85, td: 54.0, spec: pg("ag2", (m) => m.legenda.itens[0]), pad: 3 },
  { ta: 54.1, td: 55.15, spec: pg("ag2", (m) => m.legenda.itens[1]), pad: 3 },
  { ta: 55.25, td: 56.3, spec: pg("ag2", (m) => m.legenda.itens[2]), pad: 3 },
  { ta: 56.6, td: 56.95, spec: pg("ag2", (m) => m.dets[1].sum), pad: 3 },
  { ta: 57.25, td: 59.65, spec: pg("ag3", (m) => m.dets[1].rows[2].selo), pad: 4 },
  { ta: 59.8, td: 60.4, spec: pg("ag3", (m) => m.dets[1].rows[3].selo), pad: 4 },
  { ta: 60.55, td: 62.5, spec: pg("ag3", (m) => m.dets[1].rows[2].selo), pad: 4 },
  { ta: 63.0, td: 64.0, spec: pg("ag1", (m) => m.dets[3].gear), pad: 3 },
  { ta: 64.35, td: 64.9, spec: sh("dedit", (m) => m.fechar), pad: 3 },
  { ta: 65.3, td: 66.7, spec: pg("ag1", (m) => m.dets[3].trash), pad: 3 },
  { ta: 68.4, td: 69.95, spec: pg("ag1", (m) => m.dets[4].sum), pad: 3 },
  { ta: 70.3, td: 70.75, spec: pg("ag5", (m) => m.busca.selects[0]), pad: 4 },
  { ta: 70.85, td: 71.2, spec: pg("ag5", (m) => m.busca.selects[1]), pad: 4 },
  { ta: 71.3, td: 71.7, spec: pg("ag5", (m) => uniao(m.busca.inputs[0], m.busca.inputs[1])), pad: 4 },
  { ta: 71.8, td: 72.9, spec: pg("ag5", (m) => m.busca.botao), pad: 4 },
  { ta: 73.4, td: 74.6, spec: pg("ag5", (m) => uniao(m.dets[5], m.dets[6])), pad: 3 },
  { ta: 74.95, td: 75.9, spec: pg("ag5", (m) => m.dets[6].sum), pad: 3 },
  { ta: 76.3, td: 77.7, spec: pg("ag7", (m) => det30(m).ordenar), pad: 4 },
  { ta: 78.3, td: 78.9, spec: pg("ag7", (m) => uniao(det30(m).excel, det30(m).pdf)), pad: 5 },
  { ta: 79.0, td: 80.05, spec: pg("ag7", (m) => det30(m).excel), pad: 4 },
  { ta: 80.15, td: 81.6, spec: pg("ag7", (m) => det30(m).pdf), pad: 4 },
  { ta: 81.95, td: 82.4, spec: pg("ag7", (m) => det30(m).rowsLista[0].link), pad: 3 },
  { ta: 83.05, td: 83.45, spec: vw("fichaBoxes", (m) => m.voltar), pad: 3 },
  { ta: 83.85, td: 84.9, spec: pg("ag7", (m) => det30(m).rowsLista[0].mail), pad: 4 },
  { ta: 86.2, td: 87.3, spec: pg("ag8", (m) => m.email), pad: 4 },
];
// câmera: [t, ...F(zoom, foco x, foco y[, y do vídeo])]
const CAM_KF = (F) => [
  [5.6, 1.0, 195, 430],
  [6.9, ...F(1.3, 195, 290, 700)], [8.1, ...F(1.3, 195, 290, 700)], [9.2, ...F(1.1, 195, 190, 700)], [11.9, ...F(1.1, 195, 200, 700)],
  [12.6, ...F(1.35, 195, 215, 640)], [13.5, ...F(1.25, 195, 430, 700)], [17.0, ...F(1.25, 195, 430, 700)], [17.9, ...F(1.4, 215, 215, 640)], [18.8, ...F(1.15, 195, 480, 760)],
  [20.3, ...F(1.25, 195, 520, 720)], [21.0, ...F(1.3, 195, 560, 760)], [21.3, ...F(1.0, 195, 422, 960)], [22.1, ...F(1.3, 195, 560, 720)],
  [23.1, ...F(1.5, 195, 600, 700)], [28.8, ...F(1.5, 195, 600, 700)], [29.6, ...F(1.35, 195, 640, 700)], [33.0, ...F(1.5, 195, 690, 680)], [35.4, ...F(1.5, 195, 720, 680)], [36.3, ...F(1.45, 195, 740, 690)],
  [38.0, ...F(1.3, 195, 700, 700)], [38.9, ...F(1.25, 195, 470, 700)], [43.2, ...F(1.25, 195, 470, 700)], [43.9, ...F(1.5, 195, 268, 640)], [46.9, ...F(1.5, 195, 268, 640)], [47.5, ...F(1.2, 195, 450, 700)], [49.2, ...F(1.2, 195, 450, 700)],
  [49.9, ...F(1.25, 195, 200, 660)], [50.9, ...F(1.55, 195, 440, 640)], [52.7, ...F(1.55, 195, 440, 640)], [53.3, ...F(1.6, 180, 762, 960)], [56.0, ...F(1.6, 180, 762, 960)], [56.7, ...F(1.25, 195, 200, 660)],
  [57.4, ...F(1.7, 150, 660, 640)], [60.2, ...F(1.7, 150, 640, 640)], [62.3, ...F(1.7, 150, 560, 640)], [62.9, ...F(1.5, 245, 598, 700)], [63.45, ...F(1.5, 245, 598, 700)], [63.8, ...F(1.15, 195, 470, 720)], [64.5, ...F(1.15, 195, 470, 720)], [65.1, ...F(1.5, 245, 598, 700)], [66.7, ...F(1.5, 245, 598, 700)],
  [67.6, ...F(1.25, 195, 660, 680)], [69.9, ...F(1.25, 195, 660, 680)], [70.7, ...F(1.5, 195, 320, 640)], [72.6, ...F(1.5, 195, 520, 640)], [73.6, ...F(1.2, 195, 300, 700)], [75.5, ...F(1.25, 195, 200, 680)],
  [76.2, ...F(1.5, 195, 200, 640)], [78.0, ...F(1.8, 245, 255, 640)], [80.5, ...F(1.8, 245, 255, 640)], [81.8, ...F(1.4, 195, 290, 640)], [83.0, ...F(1.4, 195, 150, 640)], [83.9, ...F(1.9, 270, 290, 640)], [86.0, ...F(1.7, 195, 330, 640)],
  [87.3, ...F(1.0, 195, 440, 960)], [89.6, ...F(0.95, 195, 440, 960)],
];
// legendas (zona segura, ≤ 2 linhas)
const LEG = [
  [5.87, 9.4, "No Menu, em <b>Reprodução</b>, toque em <b>Agenda Reprodutiva</b>"], [9.5, 11.7, "É a <b>lista de trabalho</b> da visita do veterinário"],
  [12.35, 14.4, "No topo, os <b>cards configuráveis</b>"], [14.8, 17.3, "Cada card é uma <b>pergunta salva</b> sobre o rebanho"],
  [17.84, 19.1, "Toque em <b>Novo card</b>"], [19.3, 22.95, "Dê um nome, escolha a <b>categoria</b>, o <b>lote</b> e a <b>situação</b>"], [23.4, 28.4, "Escolha a <b>situação reprodutiva</b>"],
  [29.23, 32.4, "Em <b>inseminadas</b>, informe o <b>período</b> em dias"], [32.5, 37.1, "De <b>30 a 59</b> dias: as vacas <b>para tocar</b>"],
  [37.58, 39.2, "Toque em <b>Salvar card</b>"], [39.5, 42.8, "Fica guardado para a fazenda: <b>site e celular</b>"],
  [43.53, 47.2, "Botões <b>A tocar</b>, <b>A reconfirmar</b> e <b>Reconfirmadas</b>"], [47.4, 49.3, "filtram <b>todos os cards</b> de uma vez"],
  [49.55, 50.4, "Abra o <b>card</b>"], [50.6, 52.7, "Cada vaca: <b>toque</b> e <b>retoque</b>"], [52.9, 56.3, "<b>P</b> prenha · <b>V</b> vazia · <b>I</b> indefinida"],
  [56.7, 59.6, "O selo <b>Ainda não</b> marca quem ainda não chegou"], [59.75, 62.1, "no prazo. Com <b>3 dias ou menos</b>, <b>pulsa</b>"],
  [63.16, 66.5, "<b>Engrenagem</b>: edita · <b>Lixeira</b>: remove"], [67.04, 70.9, "Pergunta rápida, sem salvar: <b>Buscar por parâmetro</b>"],
  [71.97, 75.0, "Mais abaixo, as <b>listas fixas</b> do rebanho"], [75.05, 77.7, "Como <b>inseminadas de 30 a 59 dias</b>"], [78.0, 80.7, "Cada lista exporta em <b>Excel</b> ou <b>PDF</b>"],
  [81.7, 83.45, "Toque na <b>vaca</b> para abrir a <b>ficha</b>"], [83.7, 87.0, "No <b>envelope</b>, envie o último diagnóstico por <b>e-mail</b>"],
  [87.58, 89.6, "Pronto: a visita já começa <b>organizada</b>"],
];
const ETQ = [[5.6, "Menu › Reprodução"], [B.agendaRep + 0.15, "Agenda Reprodutiva"], [t_.ficha, "Ficha do animal"], [t_.volta, "Agenda Reprodutiva"]];
