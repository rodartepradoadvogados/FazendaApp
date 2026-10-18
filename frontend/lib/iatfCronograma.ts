// Datas e cronograma do protocolo IATF na tela de Lançamentos. Funções puras (sem fuso: tudo em UTC sobre "AAAA-MM-DD").
// Espelham o backend, que é quem manda: o nome do lançamento é calculado em fazenda/rules/nomenclatura_protocolo.py e o dia
// da inseminação em fazenda/rules/protocolo_iatf.py::dia_inseminacao (último dia de hormônio + 2; padrão D11). Aqui é só
// pré-visualização para o usuário ver o que vai para a Agenda ANTES de salvar.

export const DIA_INSEMINACAO_PADRAO = 11;

/** Último dia de hormônio + 2; sem hormônio cadastrado, o padrão D11. */
export function diaInseminacao(diasHormonio: readonly number[]): number {
  return diasHormonio.length ? Math.max(...diasHormonio) + 2 : DIA_INSEMINACAO_PADRAO;
}

export function hojeIso(d: Date = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function somaDias(iso: string, dias: number): string {
  if (!iso) return "";
  const [a, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(a, m - 1, d + dias)).toISOString().slice(0, 10);
}

export function fmtData(iso: string, curto = false): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return curto ? `${d}/${m}` : `${d}/${m}/${a}`;
}

export function diaSemana(iso: string): string {
  if (!iso) return "";
  const [a, m, d] = iso.split("-").map(Number);
  return ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"][new Date(Date.UTC(a, m - 1, d)).getUTCDay()];
}

/** "PROTOCOLO IATF - 06/10/26 A 17/10/26 (D0 A D11 - 12 DIAS)" — mesma regra de nomenclatura_protocolo.py. */
export function nomeProtocoloAuto(d0: string, nomeBase: string, diaFinal: number): string {
  if (!d0) return "";
  const f = (iso: string) => { const [a, m, d] = iso.split("-"); return `${d}/${m}/${a.slice(2)}`; };
  return `${nomeBase.toUpperCase()} - ${f(d0)} A ${f(somaDias(d0, diaFinal))} (D0 A D${diaFinal} - ${diaFinal + 1} DIAS)`;
}

export type EtapaMolde = { dia: number; produto: string; dose?: number | null; unidade?: string | null };
export type HormonioDigitado = { dia: number; produto: string; dose?: number | null; unidade?: string | null };
export type NoTempo = { dia: number; data: string; linhas: string[]; subtitulo?: string; fim?: boolean };

/** Cronograma clássico (sem molde): D0/D7/D9, depois a inseminação. */
export const CLASSICO = [
  { dia: 0, texto: "Implante de progesterona + benzoato de estradiol + acetato de buserelina" },
  { dia: 7, texto: "Cloprostenol" },
  { dia: 9, texto: "Retirar implante + cipionato de estradiol + cloprostenol" },
];

const un = (u?: string | null) => (u === "unidade" ? "un" : u || "");
const doseTxt = (h: { dose?: number | null; unidade?: string | null; produto: string }) =>
  [h.dose != null && h.dose !== 0 ? String(h.dose) : "", h.dose ? un(h.unidade) : "", h.produto].filter(Boolean).join(" ");

/** Nós da linha do tempo: do molde (dias livres, etapa por etapa) ou clássico + hormônios digitados. */
export function nosDoCronograma(d0: string, molde: readonly EtapaMolde[] | null, hormonios: readonly HormonioDigitado[]): NoTempo[] {
  if (molde) {
    const dias = [...new Set(molde.map((e) => e.dia))].sort((a, b) => a - b);
    const ia = diaInseminacao(dias);
    return [
      ...dias.map((dia) => ({ dia, data: somaDias(d0, dia), linhas: molde.filter((e) => e.dia === dia).map(doseTxt) })),
      { dia: ia, data: somaDias(d0, ia), linhas: ["Inseminação (IATF)"], fim: true },
    ];
  }
  return [
    ...CLASSICO.map((c) => ({
      dia: c.dia, data: somaDias(d0, c.dia), subtitulo: c.texto,
      linhas: hormonios.filter((h) => h.dia === c.dia && h.produto).map(doseTxt),
    })),
    { dia: DIA_INSEMINACAO_PADRAO, data: somaDias(d0, DIA_INSEMINACAO_PADRAO), linhas: ["Inseminação (IATF)"], fim: true },
  ];
}

/** Dias do molde (ordenados, sem repetir). */
export function diasDoMolde(molde: readonly EtapaMolde[]): number[] {
  return [...new Set(molde.map((e) => e.dia))].sort((a, b) => a - b);
}

/** O D0 retroativo que o servidor cria numa IATF avulsa sem protocolo: data do serviço − 11 dias. */
export const d0Retroativo = (dataServico: string) => somaDias(dataServico, -DIA_INSEMINACAO_PADRAO);
