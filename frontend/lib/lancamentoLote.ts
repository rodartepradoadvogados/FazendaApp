// Regras puras do LANÇAMENTO EM LOTE no app de campo (Movimentar animais, Inseminação e Protocolo IATF): seleção que
// persiste entre filtros, projeção de contagens por lote, situação de cada vaca diante de um serviço, doses por touro,
// linha do tempo do IATF e leitura da recusa de aptidão do servidor. Nada aqui toca rede nem React — as telas
// (components/mobile/lancar/lote/*, rebanho/Movimentar.tsx) só desenham o que estas funções decidem, e os testes
// (lancamentoLote.test.ts) travam as regras que o dono aprovou nos mockups.

export type OrigemLote = "animais" | "lotes" | "agenda";

export function plural(n: number, um: string, varios: string): string {
  return n === 1 ? um : varios;
}

/** Sem acento, sem caixa — para a busca tolerar "joão" e "JOAO". */
export function normalizar(s: string | null | undefined): string {
  return (s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

/** Ordem natural do brinco/lote: "9" antes de "10", "01 - Alta" antes de "13 - …". */
export function comparaNumero(a: string, b: string): number {
  return a.localeCompare(b, "pt-BR", { numeric: true });
}

// ── Seleção ───────────────────────────────────────────────────────────────────
// Regra única das três telas: a seleção PERSISTE ao trocar origem, situação, lote ou busca; nada vem marcado sozinho.
// Quem fica fora do que se está vendo continua marcado e a barra avisa ("k fora deste filtro").

export function alternarItem(sel: ReadonlySet<string>, id: string): Set<string> {
  const novo = new Set(sel);
  if (novo.has(id)) novo.delete(id); else novo.add(id);
  return novo;
}

export function definirVarios(sel: ReadonlySet<string>, ids: readonly string[], marcar: boolean): Set<string> {
  const novo = new Set(sel);
  for (const id of ids) { if (marcar) novo.add(id); else novo.delete(id); }
  return novo;
}

export function todosMarcados(sel: ReadonlySet<string>, ids: readonly string[]): boolean {
  return ids.length > 0 && ids.every((id) => sel.has(id));
}

/** Quantos marcados NÃO estão na lista que se vê agora (outro filtro, outra busca, outro lote). */
export function contarForaDoFiltro(sel: ReadonlySet<string>, visiveis: readonly string[]): number {
  const vistos = new Set(visiveis);
  let fora = 0;
  for (const id of sel) if (!vistos.has(id)) fora++;
  return fora;
}

/** Tira da seleção o que não existe mais (rascunho antigo de um animal que saiu do rebanho, por exemplo). */
export function podarSelecao(sel: ReadonlySet<string>, validos: ReadonlySet<string>): Set<string> {
  const novo = new Set<string>();
  for (const id of sel) if (validos.has(id)) novo.add(id);
  return novo;
}

export function textoMarcados(n: number, fora: number): string {
  return `${n} ${plural(n, "marcado", "marcados")}${fora > 0 ? ` (${fora} fora deste filtro)` : ""}`;
}

// ── Datas (sempre "AAAA-MM-DD", sem fuso: o dia que a pessoa escolheu é o dia que vale) ─────────────────────────

const SEMANA = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado"];

function partesIso(iso: string): [number, number, number] | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}

export function somarDiasIso(iso: string, dias: number): string {
  const p = partesIso(iso);
  if (!p) return "";
  const d = new Date(Date.UTC(p[0], p[1] - 1, p[2] + dias));
  return d.toISOString().slice(0, 10);
}

/** "23/10" — usado na linha do tempo e na frase de resultado. */
export function dataCurta(iso: string): string {
  const p = partesIso(iso);
  return p ? `${String(p[2]).padStart(2, "0")}/${String(p[1]).padStart(2, "0")}` : "";
}

export function dataBr(iso: string): string {
  const p = partesIso(iso);
  return p ? `${String(p[2]).padStart(2, "0")}/${String(p[1]).padStart(2, "0")}/${p[0]}` : "";
}

/** "sexta-feira, 16/10/2026" — a linha abaixo do campo de data (o navegador mostra o formato dele no próprio campo). */
export function dataPorExtenso(iso: string): string {
  const p = partesIso(iso);
  if (!p) return "";
  const dow = new Date(Date.UTC(p[0], p[1] - 1, p[2])).getUTCDay();
  return `${SEMANA[dow]}, ${dataBr(iso)}`;
}

// ── Movimentar animais ────────────────────────────────────────────────────────

export type AnimalMovivel = {
  numero: string;
  nome?: string | null;
  grupo_primario?: string | null;
  categoria_abrev?: string | null;
  categoria_completa?: string | null;
  sexo?: string | null;
  eh_semen?: boolean | null;
  del_dias?: number | null;
};
export type LoteBasico = { codigo: string; nome?: string | null; rotulo?: string | null };
export const SEM_LOTE = "Sem lote";

export function rotuloDoLote(l: LoteBasico): string {
  return l.rotulo || (l.nome ? `${l.codigo} - ${l.nome}` : l.codigo);
}

/** Palito de sêmen não é animal: nunca entra numa lista de movimentação. */
export function soAnimais<T extends AnimalMovivel>(lista: readonly T[]): T[] {
  return lista.filter((a) => !a.eh_semen);
}

function semZeros(codigo: string): string {
  return /^\d+$/.test(codigo) ? String(Number(codigo)) : codigo;
}

/** Código do lote em que o animal está hoje. O backend grava o lote como texto ("01 - Alta"): casa pelo rótulo inteiro
 * e, se o cadastro do lote mudou de nome, pelo número do começo ("01"). `null` = sem lote reconhecido. */
export function codigoDoGrupo(grupo: string | null | undefined, lotes: readonly LoteBasico[]): string | null {
  const g = (grupo ?? "").trim();
  if (!g) return null;
  const exato = lotes.find((l) => rotuloDoLote(l) === g);
  if (exato) return exato.codigo;
  const m = /^(\d+)/.exec(g);
  if (m) {
    const achado = lotes.find((l) => semZeros(l.codigo) === semZeros(m[1]));
    if (achado) return achado.codigo;
  }
  return null;
}

/** Texto do lote atual para mostrar no cartão e agrupar a lista. */
export function rotuloDoGrupo(grupo: string | null | undefined): string {
  return (grupo ?? "").trim() || SEM_LOTE;
}

/** Quantos animais há em cada lote hoje (chave = código do lote; "" = sem lote reconhecido). */
export function contagemPorLote(animais: readonly AnimalMovivel[], lotes: readonly LoteBasico[]): Map<string, number> {
  const m = new Map<string, number>();
  for (const a of animais) {
    const c = codigoDoGrupo(a.grupo_primario, lotes) ?? "";
    m.set(c, (m.get(c) ?? 0) + 1);
  }
  return m;
}

export function ehBezerro(a: AnimalMovivel): boolean {
  return /bezerr/i.test(`${a.categoria_completa ?? ""} ${a.categoria_abrev ?? ""} ${a.grupo_primario ?? ""}`);
}

export function loteEhDeBezerras(l: LoteBasico): boolean {
  return /bezerr/i.test(rotuloDoLote(l));
}

/** Quem não é bezerra(o) mas foi marcado para um lote de bezerras — só para AVISAR, nunca para barrar. */
export function adultosParaLoteDeBezerras(animais: readonly AnimalMovivel[], destino: LoteBasico): AnimalMovivel[] {
  return loteEhDeBezerras(destino) ? animais.filter((a) => !ehBezerro(a)) : [];
}

export type ProjecaoMovimentacao = {
  /** Vão de fato mudar de lote. */
  movem: AnimalMovivel[];
  /** Já estão no lote escolhido: aparecem riscados e não são enviados. */
  jaAqui: AnimalMovivel[];
  /** De onde saem, com a contagem de cada lote antes → depois. */
  porOrigem: { codigo: string; rotulo: string; animais: AnimalMovivel[]; antes: number; depois: number }[];
  destinoAntes: number;
  destinoDepois: number;
};

export function projetarMovimentacao(
  marcados: readonly AnimalMovivel[], destino: LoteBasico, lotes: readonly LoteBasico[], contagem: ReadonlyMap<string, number>,
): ProjecaoMovimentacao {
  const movem: AnimalMovivel[] = [];
  const jaAqui: AnimalMovivel[] = [];
  const grupos = new Map<string, AnimalMovivel[]>();
  for (const a of marcados) {
    const c = codigoDoGrupo(a.grupo_primario, lotes) ?? "";
    if (c === destino.codigo) { jaAqui.push(a); continue; }
    movem.push(a);
    grupos.set(c, [...(grupos.get(c) ?? []), a]);
  }
  const porOrigem = [...grupos.entries()]
    .sort(([a], [b]) => comparaNumero(a, b))
    .map(([codigo, animais]) => {
      const lote = lotes.find((l) => l.codigo === codigo);
      const antes = contagem.get(codigo) ?? 0;
      return { codigo, rotulo: lote ? rotuloDoLote(lote) : SEM_LOTE, animais, antes, depois: Math.max(0, antes - animais.length) };
    });
  const destinoAntes = contagem.get(destino.codigo) ?? 0;
  return { movem, jaAqui, porOrigem, destinoAntes, destinoDepois: destinoAntes + movem.length };
}

/** Contagem de cada lote depois de mover `brincos` para `destino` (para o quadro do resultado). */
export function contagemDepois(
  animais: readonly AnimalMovivel[], lotes: readonly LoteBasico[], brincos: ReadonlySet<string>, destino: LoteBasico,
): Map<string, number> {
  const m = new Map<string, number>();
  for (const a of animais) {
    const c = brincos.has(a.numero) ? destino.codigo : (codigoDoGrupo(a.grupo_primario, lotes) ?? "");
    m.set(c, (m.get(c) ?? 0) + 1);
  }
  return m;
}

export type SugestaoMov = {
  numero_matriz: string;
  lote_atual?: string | null;
  motivo?: string | null;
  lotes_sugeridos?: { codigo: string; nome?: string | null; rotulo?: string | null; motivo?: string | null }[];
};

/** Sugestões agrupadas pelo lote que o sistema indica primeiro (o mesmo que a Agenda pré-seleciona). */
export function agruparSugestoesPorDestino(sugestoes: readonly SugestaoMov[]): { codigo: string; rotulo: string; itens: SugestaoMov[] }[] {
  const m = new Map<string, { codigo: string; rotulo: string; itens: SugestaoMov[] }>();
  for (const s of sugestoes) {
    const d = s.lotes_sugeridos?.[0];
    if (!d) continue;
    const g = m.get(d.codigo) ?? { codigo: d.codigo, rotulo: d.rotulo || d.nome || d.codigo, itens: [] };
    g.itens.push(s);
    m.set(d.codigo, g);
  }
  return [...m.values()].sort((a, b) => comparaNumero(a.codigo, b.codigo));
}

/** Destino que a Agenda já indicou, quando TODOS os marcados são sugestões e apontam para o mesmo lote. */
export function destinoSugeridoPara(marcados: readonly AnimalMovivel[], sugestoes: readonly SugestaoMov[]): string | null {
  if (!marcados.length) return null;
  const destinos = new Set<string>();
  for (const a of marcados) {
    const s = sugestoes.find((x) => x.numero_matriz === a.numero);
    const d = s?.lotes_sugeridos?.[0]?.codigo;
    if (!d) return null;
    destinos.add(d);
  }
  return destinos.size === 1 ? [...destinos][0] : null;
}

/** "sugestao_passiva" quando TODOS os que vão mudar foram sugeridos para o lote escolhido (aceitou sem alterar);
 * qualquer outra coisa é troca "manual" — mesmo critério do card da Agenda e do site. */
export function origemDoEnvio(movem: readonly AnimalMovivel[], destinoCodigo: string, sugestoes: readonly SugestaoMov[]): "manual" | "sugestao_passiva" {
  if (!movem.length) return "manual";
  const todos = movem.every((a) => sugestoes.find((s) => s.numero_matriz === a.numero)?.lotes_sugeridos?.some((l) => l.codigo === destinoCodigo));
  return todos ? "sugestao_passiva" : "manual";
}

/** Resposta de POST /movimentacoes/mover: um 200 não quer dizer que todos mudaram — brinco errado vem em `nao_encontrados`. */
export function interpretarRespostaMover(
  enviados: readonly string[], resposta: { movidos?: number; nao_encontrados?: string[] } | null | undefined,
): { movidos: string[]; naoEncontrados: string[] } {
  const nao = new Set(resposta?.nao_encontrados ?? []);
  const naoEncontrados = enviados.filter((n) => nao.has(n));
  // Resposta sem nada (corpo vazio) com `movidos: 0` também é "ninguém mudou".
  if (resposta && resposta.movidos === 0 && !naoEncontrados.length) return { movidos: [], naoEncontrados: [...enviados] };
  return { movidos: enviados.filter((n) => !nao.has(n)), naoEncontrados };
}

// ── Inseminação e Protocolo IATF: quem pode entrar ────────────────────────────

export type ModoServico = "ia" | "iatf";
export type FiltroSituacao = "aptas" | "atrasadas" | "d11" | "pev" | "todas";
export type TomChip = "apta" | "atrasada" | "pev" | "insem" | "prot" | "neutra";

/** Inseminada há menos que isto só entra por confirmação individual. */
export const LIMITE_INSEMINADA_RECENTE = 18;
/** Dia do protocolo em que a vaca pode ser inseminada (D11). */
export const DIA_INSEMINACAO_IATF = 11;

/** O que o estado reprodutivo ao vivo (GET /indicadores/estados-reprodutivos) diz de cada fêmea. */
export type EstadoReproBase = {
  numero: string;
  estado: string;
  del_dias?: number | null;
  dias_desde_servico?: number | null;
  dias_gestacao?: number | null;
  protocolo_dia_atual?: number | null;
};

export type StatusServico = {
  /** Fora da lista: bezerra, novilha ainda não apta. Quem é macho ou está baixada o servidor recusa ao enviar. */
  duro: boolean;
  /** Pronta: aparece como candidata sem alerta nenhum. */
  pronta: boolean;
  /** Com observação (PEV, inseminada há mais tempo), mas se marca direto. */
  info: boolean;
  /** Só entra marcando uma a uma, depois de ler o aviso num sheet (gestante, inseminada recente). */
  confirmar: boolean;
  /** Não dá para marcar (em protocolo antes do D11, ou já em protocolo no IATF). */
  travada: boolean;
  /** É o D11 de um IATF: a inseminação fecha a etapa da Agenda. */
  d11: boolean;
  chip?: { tom: TomChip; rotulo: string };
  /** Texto do sheet de confirmação / da nota da vaca. */
  texto?: string;
  /** Frase curta que aparece no cartão enquanto ele não está marcado. */
  curto?: string;
  /** Rótulo curto do que a confirmação aceita ("Gestante", "Inseminada"). */
  acao?: string;
};

const FORA: StatusServico = { duro: true, pronta: false, info: false, confirmar: false, travada: false, d11: false };
const base = (): StatusServico => ({ duro: false, pronta: false, info: false, confirmar: false, travada: false, d11: false });

export function statusServico(e: EstadoReproBase, modo: ModoServico): StatusServico {
  switch (e.estado) {
    case "apta": return { ...base(), pronta: true, chip: { tom: "apta", rotulo: "Apta" } };
    case "atrasada": return { ...base(), pronta: true, chip: { tom: "atrasada", rotulo: "Atrasada" } };
    case "pev":
      return { ...base(), info: true, chip: { tom: "pev", rotulo: "PEV" }, texto: "No período de espera voluntário (PEV). Dá para lançar; confira." };
    case "inseminada": {
      const dias = e.dias_desde_servico;
      const consequencia = modo === "iatf"
        ? "Entrar em protocolo troca o resultado da inseminação anterior para negativo."
        : "Lançar de novo troca o resultado daquela inseminação para negativo.";
      const texto = `Foi inseminada${dias != null ? ` há ${dias} dias` : ""}. ${consequencia}`;
      const recente = dias == null || dias < LIMITE_INSEMINADA_RECENTE;
      return {
        ...base(), confirmar: recente, info: !recente, chip: { tom: "insem", rotulo: "Inseminada" }, texto,
        curto: recente ? `Inseminada${dias != null ? ` há ${dias} d` : ""}: toque para confirmar` : undefined, acao: "Inseminada",
      };
    }
    case "gestante": {
      const gest = e.dias_gestacao != null ? ` (${e.dias_gestacao} dias de gestação)` : "";
      const texto = modo === "iatf"
        ? `Consta como gestante${gest}. Só entra no protocolo com a sua confirmação.`
        : `Consta como gestante${gest}. Lançar agora registra a perda da prenhez.`;
      return { ...base(), confirmar: true, chip: { tom: "neutra", rotulo: "Gestante" }, texto, curto: "Gestante: toque para confirmar", acao: "Gestante" };
    }
    case "em_protocolo": {
      const dia = e.protocolo_dia_atual;
      if (modo === "ia" && dia === DIA_INSEMINACAO_IATF) {
        return { ...base(), pronta: true, d11: true, chip: { tom: "prot", rotulo: "IATF · D11 hoje" } };
      }
      return {
        ...base(), travada: true, chip: { tom: "prot", rotulo: `Em protocolo${dia != null ? ` · D${dia}` : ""}` },
        curto: modo === "ia" ? "A inseminação só no D11 do protocolo" : "Já está em protocolo: termine o atual antes",
      };
    }
    default: return FORA; // nao_apta, vazia (nunca produzido) e qualquer estado novo: não é candidata
  }
}

export type CandidataServico = {
  numero: string;
  nome: string;
  lote: string;
  categoria: string;
  del: number | null;
  diasIA: number | null;
  estado: string;
  status: StatusServico;
};

export type AnimalDaLista = { numero: string; nome?: string | null; grupo_primario?: string | null; categoria_abrev?: string | null; categoria_completa?: string | null };

/** Junta a lista de animais (nome, lote) com o estado ao vivo e devolve só quem pode ser candidata. */
export function montarCandidatas(animais: readonly AnimalDaLista[], estados: ReadonlyMap<string, EstadoReproBase>, modo: ModoServico): CandidataServico[] {
  const saida: CandidataServico[] = [];
  for (const a of animais) {
    const e = estados.get(a.numero);
    if (!e) continue;
    const status = statusServico(e, modo);
    if (status.duro) continue;
    saida.push({
      numero: a.numero, nome: (a.nome ?? "").trim(), lote: rotuloDoGrupo(a.grupo_primario),
      categoria: a.categoria_abrev || a.categoria_completa || "",
      del: e.del_dias ?? null, diasIA: e.dias_desde_servico ?? null, estado: e.estado, status,
    });
  }
  return saida;
}

export const FILTROS_SITUACAO: Record<ModoServico, { id: FiltroSituacao; rotulo: string }[]> = {
  ia: [{ id: "aptas", rotulo: "Aptas" }, { id: "atrasadas", rotulo: "Atrasadas" }, { id: "d11", rotulo: "IATF D11" }, { id: "todas", rotulo: "Todas" }],
  iatf: [{ id: "aptas", rotulo: "Aptas" }, { id: "atrasadas", rotulo: "Atrasadas" }, { id: "pev", rotulo: "PEV" }, { id: "todas", rotulo: "Todas" }],
};

export const NOTA_SITUACAO_SERVICO: Record<FiltroSituacao, string> = {
  aptas: "Passaram do período de espera (PEV) ou tiveram diagnóstico negativo, e ainda sem serviço.",
  atrasadas: "Seriam aptas, mas passaram do prazo para o primeiro serviço. Entram primeiro na fila.",
  pev: "Ainda no período de espera voluntário (PEV). Dá para lançar; confira.",
  d11: "Vacas em protocolo IATF que chegaram ao D11: dia da inseminação.",
  todas: "Todas as candidatas. Quem exige confirmação não vem marcada.",
};

export function passaFiltro(c: CandidataServico, f: FiltroSituacao): boolean {
  switch (f) {
    case "aptas": return c.estado === "apta";
    case "atrasadas": return c.estado === "atrasada";
    case "pev": return c.estado === "pev";
    case "d11": return c.status.d11;
    default: return true;
  }
}

export type RecorteOrigem = { origem: OrigemLote; lotes: ReadonlySet<string>; numerosAgenda: ReadonlySet<string> };

/** Só a origem (sem situação nem busca): Animais = todas; Lotes = os lotes tocados; Agenda = quem está nos cards tocados. */
export function recortarPorOrigem(cs: readonly CandidataServico[], r: RecorteOrigem): CandidataServico[] {
  if (r.origem === "lotes") return cs.filter((c) => r.lotes.has(c.lote));
  if (r.origem === "agenda") return cs.filter((c) => r.numerosAgenda.has(c.numero));
  return [...cs];
}

/** Contagem de cada situação, escopada pela origem — o número no botão é o que aparece ao tocar nele. */
export function contagensPorSituacao(naOrigem: readonly CandidataServico[]): Record<FiltroSituacao, number> {
  const n = (f: FiltroSituacao) => naOrigem.filter((c) => passaFiltro(c, f)).length;
  return { aptas: n("aptas"), atrasadas: n("atrasadas"), pev: n("pev"), d11: n("d11"), todas: naOrigem.length };
}

export function buscarCandidatas(cs: readonly CandidataServico[], texto: string): CandidataServico[] {
  const q = normalizar(texto);
  if (!q) return [...cs];
  return cs.filter((c) => normalizar(c.numero).includes(q) || normalizar(c.nome).includes(q) || normalizar(c.lote).includes(q));
}

function prioridade(c: CandidataServico): number {
  const s = c.status;
  return s.pronta ? 0 : s.info ? 1 : s.confirmar ? 2 : 3;
}

/** Lotes em ordem do código; dentro do lote, quem está pronta primeiro, as atrasadas antes das aptas, depois o brinco. */
export function agruparCandidatasPorLote(cs: readonly CandidataServico[]): { lote: string; itens: CandidataServico[] }[] {
  const m = new Map<string, CandidataServico[]>();
  for (const c of cs) m.set(c.lote, [...(m.get(c.lote) ?? []), c]);
  return [...m.entries()]
    .sort(([a], [b]) => comparaNumero(a, b))
    .map(([lote, itens]) => ({
      lote,
      itens: [...itens].sort((p, q) =>
        prioridade(p) - prioridade(q) || (p.estado === "atrasada" ? 0 : 1) - (q.estado === "atrasada" ? 0 : 1) || comparaNumero(p.numero, q.numero)),
    }));
}

/** "Selecionar todas": só quem se marca sem ler aviso. Em "Todas" só as prontas (PEV e inseminadas ficam para o toque um a um). */
export function marcaveisEmBloco(visiveis: readonly CandidataServico[], filtro: FiltroSituacao): CandidataServico[] {
  return visiveis.filter((c) => !c.status.confirmar && !c.status.travada && (filtro === "todas" ? c.status.pronta : true));
}

export function rotuloMarcarTodas(filtro: FiltroSituacao): string {
  return {
    aptas: "Selecionar todas as aptas", atrasadas: "Selecionar todas as atrasadas", d11: "Selecionar todas do D11",
    pev: "Selecionar todas em PEV", todas: "Selecionar as sem alerta",
  }[filtro];
}

/** Lotes que têm candidata para o filtro de hoje, com a contagem de vacas que podem receber serviço. */
export function lotesComCandidatas(naSituacao: readonly CandidataServico[]): [string, number][] {
  const m = new Map<string, number>();
  for (const c of naSituacao) {
    if (c.status.confirmar || c.status.travada) continue;
    m.set(c.lote, (m.get(c.lote) ?? 0) + 1);
  }
  return [...m.entries()].sort(([a], [b]) => comparaNumero(a, b));
}

/** Busca por brinco que não aparece no filtro de hoje: devolve quem existe mas está em outra situação. */
export function existeEmOutraSituacao(todas: readonly CandidataServico[], naLista: readonly CandidataServico[], texto: string, limite = 3): CandidataServico[] {
  const q = normalizar(texto);
  if (!q) return [];
  const vistos = new Set(naLista.map((c) => c.numero));
  return todas.filter((c) => !vistos.has(c.numero) && (normalizar(c.numero).includes(q) || normalizar(c.nome).includes(q))).slice(0, limite);
}

/** Frase "4521 existe, mas está gestante". */
export function frasePertenceOutraSituacao(c: CandidataServico): string {
  return `${c.numero}${c.nome ? ` ${c.nome}` : ""} existe, mas está ${(c.status.chip?.rotulo ?? "em outra situação").toLowerCase()}.`;
}

/** Texto do resumo de origem no Passo 2 ("Lotes 01, 02"). */
export function resumoOrigem(origem: OrigemLote, lotes: ReadonlySet<string>, nomesCards: readonly string[]): string {
  if (origem === "lotes") return `Lotes ${[...lotes].sort(comparaNumero).join(", ")}`;
  if (origem === "agenda") return `Agenda do vet.: ${nomesCards.join(", ")}`;
  return "Escolhidas por busca";
}

// ── Inseminação: touro e doses ────────────────────────────────────────────────

export type CategoriaSemen = "convencional" | "sexado" | "fazenda";
export type OpcaoTouro = { nome: string; doses: number | null; catalogo?: boolean };

/** Quantas vacas vão usar cada touro (considerando as trocas feitas vaca a vaca). */
export function usoPorTouro(numeros: readonly string[], touroDe: (numero: string) => string): Record<string, number> {
  const uso: Record<string, number> = {};
  for (const n of numeros) {
    const t = touroDe(n);
    if (t) uso[t] = (uso[t] ?? 0) + 1;
  }
  return uso;
}

export function dosesQueSobram(doses: number, uso: number): number {
  return Math.max(0, doses - uso);
}

export function dosesQueFaltam(doses: number, uso: number): number {
  return Math.max(0, uso - doses);
}

/** Corpo de POST /reproducao/servico para UMA vaca (um envio por animal — decisão do dono). */
export function corpoServico(opts: {
  numero: string; data: string; categoria: CategoriaSemen; touro: string; protocolo?: string | null; confirmada: boolean;
}): Record<string, unknown> {
  const fazenda = opts.categoria === "fazenda";
  return {
    numero_matriz: opts.numero,
    data_servico: opts.data,
    tipo_servico: fazenda ? "Monta natural" : "IA",
    reprodutor: opts.touro || undefined,
    tipo_semen: fazenda ? undefined : opts.categoria,
    // Só no D11 de um IATF: o servidor fecha sozinho a etapa de inseminação do protocolo na Agenda.
    protocolo: opts.protocolo || undefined,
    // Só em quem a pessoa confirmou no sheet; nunca em lote.
    forcar: opts.confirmada ? true : undefined,
  };
}

// ── Protocolo IATF ────────────────────────────────────────────────────────────

// Cronograma do protocolo IATF — mesmos hormônios do backend (fazenda/api/routers/reproducao.py → PASSOS_PROTOCOLO_IATF).
// O D0 é o que está sendo aplicado agora; as demais etapas entram na agenda.
export const ETAPAS_IATF: { dia: number; hormonios: string }[] = [
  { dia: 0, hormonios: "Implante de progesterona + Benzoato de estradiol + Acetato de buserelina" },
  { dia: 7, hormonios: "Cloprostenol" },
  { dia: 9, hormonios: "Retirar implante + Cipionato de estradiol + Cloprostenol" },
  { dia: 11, hormonios: "Inseminação (IATF)" },
];

export type EtapaComData = { dia: number; hormonios: string; dataIso: string; dataCurta: string };

export function etapasComData(d0Iso: string): EtapaComData[] {
  return ETAPAS_IATF.map((e) => {
    const dataIso = d0Iso ? somarDiasIso(d0Iso, e.dia) : "";
    return { ...e, dataIso, dataCurta: dataIso ? dataCurta(dataIso) : "" };
  });
}

export type RecusaAptidao = { mensagem: string; motivo: string | null; confirmavel: boolean; animais: string[] };

/** Lê o 409 de aptidão do servidor (`{erro:"aptidao", msg, motivo, confirmavel, animais}`). `null` = outro tipo de erro. */
export function lerRecusaAptidao(status: number | null | undefined, detalhe: unknown, mensagemPadrao: string): RecusaAptidao | null {
  if (status !== 409 || !detalhe || typeof detalhe !== "object") return null;
  const d = detalhe as { erro?: unknown; msg?: unknown; motivo?: unknown; confirmavel?: unknown; animais?: unknown };
  if (d.erro !== "aptidao") return null;
  return {
    mensagem: typeof d.msg === "string" && d.msg.trim() ? d.msg : mensagemPadrao,
    motivo: typeof d.motivo === "string" ? d.motivo : null,
    confirmavel: d.confirmavel === true,
    animais: Array.isArray(d.animais) ? d.animais.filter((x): x is string => typeof x === "string") : [],
  };
}
