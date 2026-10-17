// BST (lançamento em lote) — regras puras da tela: segmentos da agenda, filtro/ordenação, alvo de cada ação, previsão do estoque,
// payload e leitura do retorno. A tela (components/PainelLancarBst.tsx) só desenha e chama as props de injeção offline
// (`aplicarBst`, `marcarInapta`); quem valida e monta os corpos dos POST é este módulo.
import { dataBR, lerNumero, plural } from "./producaoGerencial.ts";

export type Seg = "aptas" | "incluir" | "inaptas";

export const SEGMENTOS: { id: Seg; nome: string; sub: string; tom: "ok" | "atencao" | "alerta"; todas: string }[] = [
  { id: "aptas", nome: "Aptas", sub: "chegam aptas na data da próxima aplicação", tom: "ok", todas: "as aptas" },
  { id: "incluir", nome: "Incluir no próximo BST", sub: "nunca aplicadas, indução de lactação ou retiradas", tom: "atencao", todas: "as para incluir" },
  { id: "inaptas", nome: "Inaptas p/ próxima aplicação", sub: "fora por critério (DEL, secagem)", tom: "alerta", todas: "as inaptas" },
];

/** Linha do payload da agenda (bst_elegiveis / bst_nunca_aplicados / bst_excluidos) já no formato da tela. */
export type AnimalBst = {
  numero: string; lote: string; delAtual: number | null; delProjetado: number | null;
  /** motivo_exclusao do servidor (existe em todas as inaptas e nas reanalisadas). */
  motivo: string;
  /** Retirada do BST ou revertida: revisar antes de incluir de novo. */
  reanalise: boolean;
  /** Entrou pelo protocolo de indução de lactação — a notinha "(ind.lact.)". */
  inducao: boolean;
  /** Em "Incluir": nunca recebeu BST (e não é reanálise). */
  nunca: boolean;
  seg: Seg;
};

const SEM_LOTE = "Sem lote";

/** Linha de uma das listas de BST da agenda (GET /agenda/). */
export type LinhaAgendaBst = {
  numero_matriz?: string | null; grupo?: string | null; del_atual?: number | null; del_projetado?: number | null;
  requer_reanalise?: boolean; origem_inducao_lactacao?: boolean; motivo_exclusao?: string | null;
};
export type AgendaBst = {
  bst_elegiveis?: LinhaAgendaBst[]; bst_nunca_aplicados?: LinhaAgendaBst[]; bst_excluidos?: LinhaAgendaBst[];
  proxima_visita_bst?: string | null; intervalo_bst?: number | null;
} | null | undefined;

export function animalDe(b: LinhaAgendaBst | null | undefined, seg: Seg): AnimalBst {
  const reanalise = !!b?.requer_reanalise;
  return {
    numero: String(b?.numero_matriz ?? ""), lote: b?.grupo || SEM_LOTE,
    delAtual: typeof b?.del_atual === "number" ? b.del_atual : null,
    delProjetado: typeof b?.del_projetado === "number" ? b.del_projetado : null,
    motivo: b?.motivo_exclusao || "", reanalise, inducao: !!b?.origem_inducao_lactacao,
    nunca: seg === "incluir" && !reanalise, seg,
  };
}

export function segmentosDaAgenda(agenda: AgendaBst): Record<Seg, AnimalBst[]> {
  const doc = (lista: LinhaAgendaBst[] | undefined, seg: Seg) => (Array.isArray(lista) ? lista : []).map((b) => animalDe(b, seg));
  return { aptas: doc(agenda?.bst_elegiveis, "aptas"), incluir: doc(agenda?.bst_nunca_aplicados, "incluir"), inaptas: doc(agenda?.bst_excluidos, "inaptas") };
}

export type Ordem = { col: "n" | "lote" | "dp" | "da"; dir: 1 | -1 };
const num = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true });

export function ordenarAnimais(lista: AnimalBst[], o: Ordem): AnimalBst[] {
  const valor = (a: AnimalBst) => (o.col === "dp" ? a.delProjetado : a.delAtual);
  return [...lista].sort((a, b) => {
    let c: number;
    if (o.col === "n") c = num(a.numero, b.numero);
    else if (o.col === "lote") c = num(a.lote, b.lote);
    else {
      const va = valor(a), vb = valor(b);
      if (va === null && vb !== null) return 1; // sem DEL vai sempre para o fim, nos dois sentidos
      if (vb === null && va !== null) return -1;
      c = va === null || vb === null ? 0 : va - vb;
    }
    return c * o.dir || num(a.numero, b.numero);
  });
}

/** Filtro por lote (vazio = todos) e busca pelo número (contém, sem diferenciar caixa). */
export function filtrarAnimais(lista: AnimalBst[], lotes: string[], busca: string): AnimalBst[] {
  const q = busca.trim().toLowerCase();
  return lista.filter((a) => (!lotes.length || lotes.includes(a.lote)) && (!q || a.numero.toLowerCase().includes(q)));
}

export type Marcadas = Record<Seg, Set<string>>;

/** Quem recebe a ação do pé da tela: em Inaptas, só as inaptas marcadas; nos outros segmentos, aptas + incluir marcadas (nunca mistura inaptas). */
export function alvoDaAcao(seg: Seg, marcadas: Marcadas, segs: Record<Seg, AnimalBst[]>): AnimalBst[] {
  const dos = (s: Seg) => segs[s].filter((a) => marcadas[s].has(a.numero));
  return seg === "inaptas" ? dos("inaptas") : [...dos("aptas"), ...dos("incluir")];
}

/** "Marcar como apta" em Incluir vale só para as marcadas com selo Reanalisar (as nunca aplicadas já são aptas). */
export function reanalisadasMarcadas(marcadas: Marcadas, segs: Record<Seg, AnimalBst[]>): AnimalBst[] {
  return segs.incluir.filter((a) => a.reanalise && marcadas.incluir.has(a.numero));
}

export type ParamsAplicacao = { data: string; produto: string; dose: string; unidade: string; porAnimal: boolean; resp: string };
export type ItemEstoque = { nome: string; unidade?: string | null; quantidade?: number | null };

const arred = (v: number) => Math.round(v * 10000) / 10000;

/** Dose total a baixar: por animal × n, ou o total do lote informado. `null` se a dose está em branco ou inválida. */
export function doseTotal(p: Pick<ParamsAplicacao, "dose" | "porAnimal">, n: number): number | null {
  const d = lerNumero(p.dose);
  if (d === null || Number.isNaN(d) || d <= 0) return null;
  return arred(p.porAnimal ? d * n : d);
}

export type Previsao =
  | { tipo: "agendar"; n: number; data: string }
  | { tipo: "registrar"; n: number; data: string; motivo: "sem_dose" | "sem_unidade" }
  | { tipo: "baixar"; n: number; data: string; total: number; unidade: string; produto: string; restam: number | null; saldo: number | null };

/** O que vai acontecer com o estoque antes de confirmar. Data futura = agenda (nada baixa agora); só baixa com dose E unidade. */
export function preverEstoque(p: ParamsAplicacao, n: number, hoje: string, estoque: ItemEstoque[]): Previsao {
  if (p.data > hoje) return { tipo: "agendar", n, data: p.data };
  const total = doseTotal(p, n);
  if (total === null) return { tipo: "registrar", n, data: p.data, motivo: "sem_dose" };
  const un = p.unidade.trim();
  if (!un) return { tipo: "registrar", n, data: p.data, motivo: "sem_unidade" };
  const item = estoque.find((i) => i.nome === p.produto);
  const mesma = !!item && (item.unidade || "").trim().toLowerCase() === un.toLowerCase() && typeof item.quantidade === "number";
  return {
    tipo: "baixar", n, data: p.data, total, unidade: un, produto: p.produto,
    saldo: mesma ? (item!.quantidade as number) : null, restam: mesma ? arred((item!.quantidade as number) - total) : null,
  };
}

export function textoPrevisao(v: Previsao): string {
  const nb = (x: number) => x.toLocaleString("pt-BR", { maximumFractionDigits: 4 });
  if (v.tipo === "agendar") return `Vai agendar ${v.n} ${plural(v.n, "aplicação", "aplicações")} para ${dataBR(v.data)} — ficam pendentes na Agenda; nada baixa do estoque agora.`;
  if (v.tipo === "registrar") {
    return `Vai registrar ${v.n} ${plural(v.n, "aplicação", "aplicações")} em ${dataBR(v.data)} — ${v.motivo === "sem_dose" ? "sem dose informada" : "sem unidade informada"}, o estoque não baixa.`;
  }
  const resta = v.restam === null ? "" : v.restam >= 0 ? ` (restam ${nb(v.restam)})` : ` — o estoque tem só ${nb(v.saldo ?? 0)}`;
  return `Vai baixar ${nb(v.total)} ${v.unidade} de ${v.produto} do estoque${resta}.`;
}

export type DadosAplicarBst = {
  numeros_matriz: string[]; data_aplicacao: string; aplicado?: boolean; produto?: string;
  dose?: number | null; unidade?: string | null; responsavel?: string; dose_por_animal?: boolean;
};

export function montarPayloadAplicar(p: ParamsAplicacao, numeros: string[]): { erro: string } | { dados: DadosAplicarBst } {
  if (!numeros.length) return { erro: "Marque ao menos um animal." };
  if (!p.data) return { erro: "Informe a data da aplicação." };
  const d = lerNumero(p.dose);
  if (d !== null && (Number.isNaN(d) || d <= 0)) return { erro: "A dose precisa ser um número maior que zero (ou deixe em branco)." };
  return {
    dados: {
      numeros_matriz: numeros, data_aplicacao: p.data, aplicado: true, produto: p.produto.trim() || "Lactotropin",
      dose: d, unidade: p.unidade.trim() || null, responsavel: p.resp.trim() || undefined, dose_por_animal: p.porAnimal,
    },
  };
}

export type RetornoAplicar = { tipo: "ok" | "offline"; texto: string; avisos: string[]; agendou: boolean };

/**
 * Lê a resposta de aplicarBst. Online: { aplicados, agendados, programado, proxima_aplicacao_calculada, avisos[] }.
 * Fila offline do app: { enviado } (sem contagem) — `enviado: false` = guardado, sem internet.
 */
export function interpretarRetornoAplicar(resposta: unknown, n: number, p: ParamsAplicacao, hoje: string, estoque: ItemEstoque[]): RetornoAplicar {
  const r = (typeof resposta === "object" && resposta !== null ? resposta : {}) as { enviado?: boolean; avisos?: unknown; agendados?: unknown; aplicados?: unknown; proxima_aplicacao_calculada?: unknown };
  if (r.enviado === false) {
    return { tipo: "offline", texto: "Sem internet — guardado, será enviado quando conectar.", avisos: [], agendou: p.data > hoje };
  }
  const avisos: string[] = Array.isArray(r.avisos) ? r.avisos.filter((x: unknown): x is string => typeof x === "string") : [];
  const agendados = typeof r.agendados === "number" ? r.agendados : null;
  const aplicados = typeof r.aplicados === "number" ? r.aplicados : null;
  if ((agendados !== null && agendados > 0) || (aplicados === null && p.data > hoje)) {
    const k = agendados ?? n;
    return { tipo: "ok", texto: `${k} ${plural(k, "agendada", "agendadas")} para ${dataBR(p.data)} — ficam pendentes na Agenda até a visita ser confirmada. Nada baixou do estoque.`, avisos, agendou: true };
  }
  const k = aplicados ?? n;
  const prev = preverEstoque(p, k, hoje, estoque);
  const baixa = prev.tipo === "baixar"
    ? ` Estoque baixou ${prev.total.toLocaleString("pt-BR", { maximumFractionDigits: 4 })} ${prev.unidade} de ${prev.produto}${prev.restam !== null ? ` (restam ${prev.restam.toLocaleString("pt-BR", { maximumFractionDigits: 4 })})` : ""}.`
    : " Sem dose e unidade informadas: o estoque não baixou.";
  const prox = typeof r.proxima_aplicacao_calculada === "string" ? ` Próxima aplicação calculada: ${dataBR(r.proxima_aplicacao_calculada)}.` : "";
  return { tipo: "ok", texto: `${k} ${plural(k, "aplicada", "aplicadas")} em ${dataBR(p.data)}.${baixa}${prox}`, avisos, agendou: false };
}

/** Texto do retorno de marcar inapta / marcar apta (a API devolve só a contagem; offline devolve { enviado }). */
export function textoRetornoMarcar(resposta: unknown, n: number, inapta: boolean): { tipo: "ok" | "offline"; texto: string } {
  const r = (typeof resposta === "object" && resposta !== null ? resposta : {}) as { enviado?: boolean; atualizados?: unknown };
  if (r.enviado === false) return { tipo: "offline", texto: "Sem internet — guardado, será enviado quando conectar." };
  const k = typeof r.atualizados === "number" ? r.atualizados : n;
  return inapta
    ? { tipo: "ok", texto: `${k} ${plural(k, "marcada como inapta", "marcadas como inaptas")}. Agora ${plural(k, "está", "estão")} em “Incluir no próximo BST” com o selo Reanalisar. Estoque não mexeu.` }
    : { tipo: "ok", texto: `${k} ${plural(k, "marcada como apta", "marcadas como aptas")}. ${plural(k, "Ficou", "Ficaram")} em “Incluir no próximo BST” e só ${plural(k, "conta", "contam")} como ${plural(k, "apta", "aptas")} depois de uma nova aplicação.` };
}
