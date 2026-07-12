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

// Centrais (studs) oficiais da NAAB — o número inicial de um código NAAB
// identifica a central. Ex.: "7HO12345" → central 7 = Select Sires, raça HO,
// touro 12345. Lista oficial: https://www.naab-css.org/naab-icar-stud-codes
// (não há API pública da NAAB; esta tabela reproduz os códigos oficiais das
// principais centrais que operam no Brasil e no exterior).
export const NAAB_STUDS: { codigo: string; nome: string }[] = [
  { codigo: "1", nome: "GENEX Cooperative" },
  { codigo: "7", nome: "Select Sires" },
  { codigo: "9", nome: "Select Sires" },
  { codigo: "11", nome: "Alta Genetics" },
  { codigo: "14", nome: "Select Sires" },
  { codigo: "29", nome: "ABS Global" },
  { codigo: "94", nome: "ABS Global" },
  { codigo: "97", nome: "CRV" },
  { codigo: "200", nome: "Semex" },
  { codigo: "250", nome: "Select Sires" },
  { codigo: "288", nome: "ASCOL" },
  { codigo: "507", nome: "Select Sires" },
  { codigo: "509", nome: "Select Sires" },
  { codigo: "523", nome: "STgenetics" },
  { codigo: "551", nome: "STgenetics" },
  { codigo: "596", nome: "United Sires" },
  { codigo: "599", nome: "Blondin Sires" },
  { codigo: "646", nome: "STgenetics" },
  { codigo: "719", nome: "RuAnn Genetics" },
  { codigo: "777", nome: "Semex" },
  { codigo: "796", nome: "United Sires" },
  { codigo: "799", nome: "Blondin Sires" },
];

// Nome único e ordenado das centrais oficiais (para o seletor de "Central").
export const NAAB_CENTRAIS = Array.from(new Set(NAAB_STUDS.map((s) => s.nome))).sort();

// Detecta a central oficial a partir de um código NAAB (ex.: "7HO12345" → 7 →
// Select Sires). Retorna null quando o prefixo numérico não bate com a tabela.
export function centralPorCodigoNaab(codigo: string): string | null {
  const m = (codigo || "").trim().match(/^(\d{1,3})/);
  if (!m) return null;
  const stud = NAAB_STUDS.find((s) => s.codigo === m[1]);
  return stud ? stud.nome : null;
}

// Motivos de movimentação agora são cadastráveis (Configurações > Cadastro >
// Motivos) — ver fetchMotivosMovimentacao em lib/api.ts.
