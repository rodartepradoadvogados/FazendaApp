// Pessoas que podem aparecer como responsável / inseminador nos lançamentos
// (ordem alfabética pelo nome).
export const RESPONSAVEIS = [
  "Alane dos Santos (funcionária)", "Alexandre Rodarte (CEO)", "Alexandre Scarpa (consultor)",
  "Carlos Alpha/ABS (veterinário Alpha/ABS)", "Huerik (veterinário COMIGO)", "Jairo Nasser (proprietário)",
  "Jorbeson Nunes (funcionário)", "Leomir Bonfim (funcionário)", "Valéria Bonfim (funcionária)",
];

// Vias de aplicação de medicamento/vacina (lista fixa para evitar erro de
// digitação) — usada no lançamento e na edição de aplicações de sanidade.
export const VIAS_APLICACAO = [
  "Intramuscular", "Subcutânea", "Intravenosa", "Intramamária", "Oral", "Tópica", "Subdérmica", "Intrauterina",
];

// Motivos de movimentação agora são cadastráveis (Configurações > Cadastro >
// Motivos) — ver fetchMotivosMovimentacao em lib/api.ts.
