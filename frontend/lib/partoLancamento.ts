// Lógica PURA do lançamento de Parto/nascimento (sem React, sem fetch) — extraída de components/lancamentos/FormParto.tsx
// para ser testável (lib/partoLancamento.test.ts). Regras que moram aqui:
//  · SEXO da cria é OBRIGATÓRIO quando a cria tem número (decisão do dono; o servidor recusa com 422 — ver CriaIn em
//    backend/fazenda/api/routers/reproducao.py). Nunca se assume "F".
//  · Natimorto força "baixada" nas crias (o sexo continua sendo pedido: relatório de % machos/fêmeas).
//  · Aborto não gera cria nem colostro.
//  · Colostro/IgG é um registro POR cria (chave "mãe|1" / "mãe|2").

export type Sexo = "" | "F" | "M";
export type SexosGemelar = "" | "FF" | "FM" | "MM";
export type Tom = "ok" | "atencao" | "bloqueio" | "info" | "neutro";

export const TIPOS_PARTO = ["Normal", "Distócico moderado", "Distócico severo", "Cesariana", "Natimorto", "Aborto"] as const;
/** Tipos oferecidos no modo Lote/Categoria (aborto só existe em "Uma matriz"). */
export const TIPOS_PARTO_LOTE = TIPOS_PARTO.filter((t) => t !== "Aborto");

export type LinhaParto = {
  data: string; tipo: string; placenta: boolean;
  cria: string; sexo: Sexo; baixada: boolean;
  gemelar: boolean; gemSexo: SexosGemelar; cria2: string; sexo2: Sexo; baixada2: boolean;
  /** Só no aborto: "" = ainda não respondeu (o sistema pergunta ao salvar). */
  lact: "" | "sim" | "nao";
};

export const linhaVazia = (data: string): LinhaParto => ({
  data, tipo: "", placenta: false, cria: "", sexo: "", baixada: false,
  gemelar: false, gemSexo: "", cria2: "", sexo2: "", baixada2: false, lact: "",
});

export const ehAborto = (l: Pick<LinhaParto, "tipo">) => l.tipo === "Aborto";
export const ehNatimorto = (l: Pick<LinhaParto, "tipo">) => l.tipo === "Natimorto";

/** Linha que vale no salvamento: no modo Lote/Categoria data e tipo vêm do topo e não há gêmeos. */
export function linhaEfetiva(base: LinhaParto, modoLote: boolean, dataTodas: string, tipoTodas: string): LinhaParto {
  return modoLote ? { ...base, data: dataTodas, tipo: tipoTodas, gemelar: false, cria2: "", sexo2: "", baixada2: false, lact: "" } : base;
}

export const erroSexo = (l: LinhaParto) => !ehAborto(l) && !!l.cria.trim() && !l.sexo;
export const erroSexo2 = (l: LinhaParto) => !ehAborto(l) && l.gemelar && !!l.cria2.trim() && !l.sexo2;

export const baixadaEfetiva = (l: LinhaParto) => ehNatimorto(l) || l.baixada;
export const baixada2Efetiva = (l: LinhaParto) => ehNatimorto(l) || l.baixada2;

export type CriaPayload = { numero: string; sexo: string; nasceu_viva: boolean };

/** Crias a enviar ao servidor (cria 1 só se tiver número; cria 2 só se gemelar e tiver número). Aborto: nenhuma. */
export function criasDaLinha(l: LinhaParto): CriaPayload[] {
  if (ehAborto(l)) return [];
  return [
    ...(l.cria.trim() ? [{ numero: l.cria.trim(), sexo: l.sexo, nasceu_viva: !baixadaEfetiva(l) }] : []),
    ...(l.gemelar && l.cria2.trim() ? [{ numero: l.cria2.trim(), sexo: l.sexo2, nasceu_viva: !baixada2Efetiva(l) }] : []),
  ];
}

export type PartoPayload = {
  numero_matriz: string; data_parto: string; tipo_parto?: string; crias: CriaPayload[];
  retencao_placenta: boolean; gemelar: boolean; gemelar_sexo?: string;
};

export function payloadParto(numeroMatriz: string, l: LinhaParto): PartoPayload {
  return {
    numero_matriz: numeroMatriz, data_parto: l.data, tipo_parto: l.tipo || undefined,
    crias: criasDaLinha(l), retencao_placenta: l.placenta, gemelar: l.gemelar,
    gemelar_sexo: l.gemelar ? (l.gemSexo || undefined) : undefined,
  };
}

/** Fêmea + macho: a fêmea pode ser freemartin (aviso, não bloqueia). */
export function avisoFreemartin(l: LinhaParto): boolean {
  return l.gemelar && !ehAborto(l) && (l.gemSexo === "FM" || (!!l.sexo && !!l.sexo2 && l.sexo !== l.sexo2));
}

export type EfetivaParto = { n: string; l: LinhaParto };

/** Problemas que impedem salvar (a tela mostra o motivo; o servidor repete a regra do sexo). */
export function problemasDeSalvar(efetivas: EfetivaParto[]): { semSexo: string[]; semData: string[]; repetidas: string[] } {
  const semSexo = efetivas.filter((e) => erroSexo(e.l) || erroSexo2(e.l)).map((e) => e.n);
  const semData = efetivas.filter((e) => !e.l.data).map((e) => e.n);
  const vistos = new Map<string, number>();
  efetivas.forEach((e) => criasDaLinha(e.l).forEach((c) => vistos.set(c.numero, (vistos.get(c.numero) ?? 0) + 1)));
  const repetidas = [...vistos.entries()].filter(([, q]) => q > 1).map(([numero]) => numero);
  return { semSexo, semData, repetidas };
}

export function resumoDosPartos(efetivas: EfetivaParto[]) {
  const abortos = efetivas.filter((e) => ehAborto(e.l)).length;
  return { registros: efetivas.length, abortos, partos: efetivas.length - abortos, crias: efetivas.reduce((s, e) => s + criasDaLinha(e.l).length, 0) };
}

/** Abortos sem resposta à pergunta "abrir lactação?" (o PopupAborto pergunta, um a um, ao salvar). */
export const abortosSemResposta = (efetivas: EfetivaParto[]) => efetivas.filter((e) => ehAborto(e.l) && !e.l.lact).map((e) => e.n);

/* ───────────────────────────── colostro / IgG (um registro por cria) ───────────────────────────── */
export type Colostro = {
  horaParto: string; horaColostro: string; peso: string; tomou: "" | "Sim" | "Não"; litros: string; brix: string; enriq: string;
  soro: string; prot: string; po: boolean;
};
export const colostroVazio = (): Colostro => ({ horaParto: "", horaColostro: "", peso: "", tomou: "", litros: "", brix: "", enriq: "25", soro: "", prot: "", po: false });

export const chaveCria = (mae: string, slot: 1 | 2) => `${mae}|${slot}`;

const num = (s: string): number | undefined => {
  const t = (s ?? "").trim().replace(",", ".");
  if (!t) return undefined;
  const n = Number(t);
  return Number.isFinite(n) ? n : undefined;
};

/** Algum dado do colostro/IgG foi informado? (o "Enriquecer até" é só cálculo de tela e não conta.) */
export function colostroTemDado(c: Colostro | undefined): boolean {
  if (!c) return false;
  return !!(c.tomou || c.litros || c.brix || c.soro || c.prot || c.horaParto || c.horaColostro || c.peso || c.po);
}
export function colostroPreenchidos(c: Colostro | undefined): number {
  if (!c) return 0;
  return [c.horaParto, c.horaColostro, c.peso, c.litros, c.brix, c.soro, c.prot].filter(Boolean).length;
}

export type ColostragemPayload = {
  numero_animal: string; tomou_colostro?: boolean; litros_colostro?: number; brix_colostro?: number; data_colostro?: string;
  hora_parto?: string; hora_colostro?: string; peso_nascer_kg?: number; brix_soro?: number; proteina_serica?: number;
  apenas_colostro_po?: boolean; data_teste_sangue?: string;
};

/** Mesmos campos que o formulário sempre enviou a POST /sanidade/colostragem, agora montados por cria. */
export function payloadColostragem(numeroAnimal: string, c: Colostro, dataParto: string): ColostragemPayload {
  const brix = num(c.brix); const soro = num(c.soro); const litros = num(c.litros);
  return {
    numero_animal: numeroAnimal,
    tomou_colostro: c.tomou ? c.tomou === "Sim" : undefined,
    litros_colostro: litros || undefined,
    brix_colostro: brix,
    data_colostro: c.brix ? dataParto : undefined,
    hora_parto: c.horaParto || undefined,
    hora_colostro: c.horaColostro || undefined,
    peso_nascer_kg: num(c.peso),
    brix_soro: soro,
    proteina_serica: num(c.prot),
    apenas_colostro_po: c.po || undefined,
    data_teste_sangue: c.soro ? dataParto : undefined,
  };
}

// Classificação padrão ouro/prata/bronze (manual da fazenda): > 25% ouro · 18–25% prata · < 18% bronze.
export function classeColostro(b: number): { txt: string; tom: Tom } {
  if (b > 25) return { txt: "Ouro — excelente", tom: "ok" };
  if (b >= 18) return { txt: "Prata — médio, enriquecer", tom: "atencao" };
  return { txt: "Bronze — ruim, descartar 1ª mamada", tom: "bloqueio" };
}
// Brix do soro (teste de IgG): >= 8,4 sucesso; 8,1–8,3 alerta; <= 8,0 falha.
export function classeSoro(b: number): { txt: string; tom: Tom } {
  if (b >= 8.4) return { txt: "Sucesso — bezerra protegida", tom: "ok" };
  if (b >= 8.1) return { txt: "Alerta — monitorar, revisar colostro", tom: "atencao" };
  return { txt: "Falha — bezerra desprotegida (ação urgente)", tom: "bloqueio" };
}
// Eficiência de colostragem em 4 níveis por Brix sérico (%) OU proteína sérica (g/dL); o Brix tem prioridade.
export function classeEficiencia(brix: number | null | undefined, prot: number | null | undefined): { txt: string; tom: Tom } | null {
  if (brix != null && !Number.isNaN(brix)) {
    return brix > 9.4 ? { txt: "Excelente", tom: "ok" } : brix >= 8.9 ? { txt: "Boa", tom: "info" } : brix >= 8.1 ? { txt: "Aceitável", tom: "atencao" } : { txt: "Ruim — bezerra desprotegida", tom: "bloqueio" };
  }
  if (prot != null && !Number.isNaN(prot)) {
    return prot > 6.2 ? { txt: "Excelente", tom: "ok" } : prot >= 5.8 ? { txt: "Boa", tom: "info" } : prot >= 5.1 ? { txt: "Aceitável", tom: "atencao" } : { txt: "Ruim — bezerra desprotegida", tom: "bloqueio" };
  }
  return null;
}

/** Horas entre o parto e o colostro ("HH:MM"), tratando a virada de dia. */
export function intervaloColostroHoras(horaParto: string, horaColostro: string): number | null {
  if (!horaParto || !horaColostro) return null;
  const [hp, mp] = horaParto.split(":").map(Number); const [hc, mc] = horaColostro.split(":").map(Number);
  if ([hp, mp, hc, mc].some((n) => Number.isNaN(n))) return null;
  let d = hc * 60 + mc - (hp * 60 + mp);
  if (d < 0) d += 24 * 60;
  return d / 60;
}

/** Colostro em pó: medidas por litro = Brix alvo − Brix atual (15 g por medida). */
export function enriquecimento(brix: number | null, alvo: number, litros: number): { porLitro: number; total: number; gramas: number } | null {
  if (brix == null || brix >= 25) return null;
  const porLitro = Math.max(0, alvo - brix);
  const total = porLitro * (litros || 1);
  return { porLitro, total, gramas: total * 15 };
}

/* ───────────────────────────── datas e sugestões ───────────────────────────── */
export function relativoPrevisto(prev: string, hoje: string): string {
  const [a, m, d] = prev.split("-").map(Number); const [a2, m2, d2] = hoje.split("-").map(Number);
  const dif = Math.round((Date.UTC(a, m - 1, d) - Date.UTC(a2, m2 - 1, d2)) / 86400000);
  return dif === 0 ? "hoje" : dif === -1 ? "ontem" : dif === 1 ? "amanhã" : dif < 0 ? `${-dif} d atrás` : `em ${dif} d`;
}

/** DEL da mãe NO MOMENTO do lançamento: dias entre a data do parto e hoje (parto retroativo de 2 dias = DEL 2, não 0).
 *  O motor de critérios de lote (POST /producao/sugestao-lote-evento) usa isto para escolher o lote "Pós-parto" certo. */
export function delDesdeParto(dataParto: string, hoje: string): number {
  const [a, m, d] = dataParto.split("-").map(Number); const [a2, m2, d2] = hoje.split("-").map(Number);
  if (![a, m, d, a2, m2, d2].every(Number.isFinite)) return 0;
  return Math.max(0, Math.round((Date.UTC(a2, m2 - 1, d2) - Date.UTC(a, m - 1, d)) / 86400000));
}
