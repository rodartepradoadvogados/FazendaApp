// Indução de lactação — regras puras da tela (cronograma, "em andamento", avisos de elegibilidade, payload).
// A tela (components/FormInducaoLactacao.tsx) só desenha; quem valida e monta o corpo do POST é este módulo.
import { diasEntre, somarDias } from "./producaoGerencial.ts";

export type EtapaProtocolo = {
  dia: number; tipo: "medicamento" | "dispositivo" | "manejo"; produto: string;
  dose?: number | null; unidade?: string | null; acao_dispositivo?: "colocar" | "retirar" | null;
};
/** Molde devolvido por GET /producao/protocolos-inducao-lactacao. */
export type ProtocoloInducao = {
  id: number; nome: string; dia_inicial: number; duracao_dias: number; observacao?: string | null; etapas: EtapaProtocolo[];
};
/** Linha devolvida por GET /producao/inducao-lactacao/ativos. */
export type InducaoAtiva = {
  lancamento_id: number; protocolo_id?: number | null; nome_protocolo: string; data_d0: string;
  animais: { numero_matriz: string; etapa_atual: string; data_etapa_atual: string | null }[];
};

/** "Protocolo de Indução de Lactação — 28 dias (Ativos 1)" → "Ativos 1". Sem parênteses, o nome inteiro. */
export function nomeCurto(nome: string): string {
  const m = nome.match(/\(([^()]+)\)\s*$/);
  return (m ? m[1] : nome).trim();
}

export const rotuloD = (p: Pick<ProtocoloInducao, "dia_inicial"> | undefined | null): string => `D${p?.dia_inicial === 1 ? 1 : 0}`;

export const diasDoProtocolo = (p: ProtocoloInducao): number[] =>
  Array.from(new Set(p.etapas.map((e) => e.dia))).sort((a, b) => a - b);

/** O servidor cria UM evento na Agenda por dia do cronograma e por animal (eventos_criados = dias distintos × animais). */
export function eventosNaAgenda(p: ProtocoloInducao, animais: number): number {
  return diasDoProtocolo(p).length * animais;
}

export function faixaDias(de: number, ate: number): number[] {
  return ate < de ? [] : Array.from({ length: ate - de + 1 }, (_, k) => de + k);
}

/** Dia (D0/D1…) em que a ordenha começa: etapa de manejo "COMEÇAR/INICIAR A ORDENHA" (a "Adaptação na ordenha" não conta). */
export function diaInicioOrdenha(p: ProtocoloInducao): number | null {
  const e = p.etapas.filter((x) => x.tipo === "manejo" && /\b(come[cç]ar|iniciar|in[ií]cio)\b.*ordenha/i.test(x.produto)).sort((a, b) => a.dia - b.dia)[0];
  return e ? e.dia : null;
}

export type LinhaCronograma = { chave: string; rotulo: string; unidade: string; tipo: EtapaProtocolo["tipo"]; porDia: Map<number, EtapaProtocolo> };

function rotuloDoProduto(e: EtapaProtocolo): string {
  if (e.tipo === "dispositivo") return "Implante de progesterona";
  if (/somatotropina|\bbst\b/i.test(e.produto)) return "bST (somatotropina)";
  if (/cloprostenol/i.test(e.produto)) return "Cloprostenol";
  return e.produto;
}

/** Uma linha por produto: implante e medicamentos primeiro (na ordem em que aparecem), manejo por último. */
export function linhasDoCronograma(p: ProtocoloInducao): LinhaCronograma[] {
  const m = new Map<string, LinhaCronograma>();
  for (const e of p.etapas) {
    const chave = `${e.tipo}|${e.tipo === "dispositivo" ? "implante" : e.produto}`;
    if (!m.has(chave)) m.set(chave, { chave, rotulo: rotuloDoProduto(e), unidade: "", tipo: e.tipo, porDia: new Map() });
    const l = m.get(chave) as LinhaCronograma;
    l.porDia.set(e.dia, e);
    if (e.tipo === "medicamento" && e.unidade) l.unidade = e.unidade;
  }
  const peso = { dispositivo: 0, medicamento: 1, manejo: 2 } as const;
  return [...m.values()].sort((a, b) => peso[a.tipo] - peso[b.tipo]);
}

export function celulaCronograma(e: EtapaProtocolo): { texto: string; titulo: string } {
  if (e.tipo === "dispositivo") return { texto: e.acao_dispositivo === "colocar" ? "▼" : "▲", titulo: `D${e.dia} · ${e.acao_dispositivo === "colocar" ? "Colocar" : "Retirar"} implante de progesterona` };
  if (e.tipo === "manejo") return { texto: e.produto.toUpperCase() === e.produto ? "▶" : "●", titulo: `D${e.dia} · ${e.produto}` };
  return { texto: e.dose ? String(e.dose) : "●", titulo: `D${e.dia} · ${e.produto}${e.dose ? ` ${e.dose} ${e.unidade ?? ""}` : ""}`.trim() };
}

/** Texto do que acontece num dia do cronograma (mesmo critério da Agenda): "Estradiol 20 ml + Colocar implante…". */
export function descreverDia(p: ProtocoloInducao, dia: number): string {
  const doDia = p.etapas.filter((e) => e.dia === dia);
  const partes = doDia.map((e) =>
    e.tipo === "dispositivo" ? (e.acao_dispositivo === "colocar" ? "Colocar implante de progesterona" : "Retirar implante de progesterona")
    : e.tipo === "manejo" ? e.produto
    : `${e.produto.replace(/\s*\(bST\)\s*$/i, "")}${e.dose ? ` ${e.dose}${e.unidade ? ` ${e.unidade}` : ""}` : ""}`);
  return partes.join(" + ");
}

/** Resumo de uma linha do protocolo para o cartão de escolha (produtos usados e dia da ordenha). */
export function resumoDoProtocolo(p: ProtocoloInducao): string {
  const nomes = linhasDoCronograma(p).filter((l) => l.tipo !== "manejo").map((l) => l.rotulo.replace(/\s*\(.*\)$/, ""));
  const lista = nomes.length > 5 ? `${nomes.slice(0, 5).join(", ")}…` : nomes.join(", ");
  const ord = diaInicioOrdenha(p);
  return [lista, ord !== null ? `a ordenha começa no D${ord}` : ""].filter(Boolean).join(" · ");
}

/** "D11" → 11 (sem número: null). */
export function diaDaEtapa(etapaAtual: string): number | null {
  const m = etapaAtual.match(/\d+/);
  return m ? Number(m[0]) : null;
}

export type LinhaAndamento = {
  numero: string; etapa: string; descricao: string; dataEtapa: string | null; diaProtocolo: string; ordenha: string | null;
};

/** Monta as linhas da aba "Em andamento", casando o lançamento com o molde quando ele ainda está ativo (senão só o que a API devolve). */
export function linhasEmAndamento(a: InducaoAtiva, molde: ProtocoloInducao | undefined): LinhaAndamento[] {
  const ordDia = molde ? diaInicioOrdenha(molde) : null;
  const ordenha = molde && ordDia !== null ? somarDias(a.data_d0, ordDia - molde.dia_inicial) : null;
  return a.animais.map((x) => {
    const dia = diaDaEtapa(x.etapa_atual);
    const desc = molde && dia !== null ? descreverDia(molde, dia) : "";
    return {
      numero: x.numero_matriz,
      etapa: x.etapa_atual,
      descricao: desc,
      dataEtapa: x.data_etapa_atual,
      diaProtocolo: molde && dia !== null ? `D${dia} de ${molde.dia_inicial + molde.duracao_dias}` : x.etapa_atual,
      ordenha,
    };
  });
}

export type AnimalElegibilidade = { em_lactacao?: boolean | null; del_dias?: number | null };

/**
 * Avisos de elegibilidade (só INFORMAM — o animal marcado é lançado mesmo assim; critérios sugeridos, a confirmar com o dono):
 * já em outra indução, prenha, em lactação. Vazio = sem aviso.
 */
export function avisosElegibilidade(
  a: AnimalElegibilidade, estado: { estado: string; dias_gestacao: number | null } | undefined, emInducao: { nome: string; etapa: string } | undefined,
): string[] {
  const avisos: string[] = [];
  if (emInducao) avisos.push(`Já em indução (${nomeCurto(emInducao.nome)} · ${emInducao.etapa})`);
  if (estado?.estado === "gestante") avisos.push(`Prenha${estado.dias_gestacao != null ? ` há ${estado.dias_gestacao} dias` : ""}`);
  if (a.em_lactacao) avisos.push(`Em lactação${a.del_dias != null ? ` (${a.del_dias} DEL)` : ""}`);
  return avisos;
}

/** Mapa número → indução em andamento (a mais recente por D0 vence, se o animal estiver em mais de uma). */
export function indexarAtivosPorAnimal(ativos: InducaoAtiva[]): Map<string, { nome: string; etapa: string }> {
  const m = new Map<string, { nome: string; etapa: string; d0: string }>();
  for (const a of ativos) {
    for (const x of a.animais) {
      const atual = m.get(x.numero_matriz);
      if (!atual || a.data_d0 > atual.d0) m.set(x.numero_matriz, { nome: a.nome_protocolo, etapa: x.etapa_atual, d0: a.data_d0 });
    }
  }
  return new Map([...m].map(([k, v]) => [k, { nome: v.nome, etapa: v.etapa }]));
}

/** 27 → "27 meses"; a partir de 48 meses, em anos ("6 anos"). */
export function formatarIdade(meses: number | null | undefined): string {
  if (meses == null) return "—";
  if (meses >= 48) { const anos = Math.floor(meses / 12); return `${anos} ${anos === 1 ? "ano" : "anos"}`; }
  return `${meses} ${meses === 1 ? "mês" : "meses"}`;
}

/** Primeira data (de hoje em diante) entre as de início de ordenha das induções em andamento. */
export function proximaOrdenha(datas: (string | null)[], hoje: string): string | null {
  return datas.filter((d): d is string => !!d && diasEntre(hoje, d) >= 0).sort()[0] ?? null;
}

export type DadosInducaoLactacao = { protocolo_id: number; animais: string[]; data_d0: string; responsavel?: string; observacao?: string };

export function montarPayloadInducao(e: {
  protocoloId: string; protocolo: ProtocoloInducao | undefined; animais: string[]; dataD0: string; responsavel: string; observacao: string;
}): { erro: string } | { dados: DadosInducaoLactacao } {
  if (!e.protocoloId || !e.protocolo) return { erro: "Selecione o protocolo de indução." };
  if (!e.animais.length) return { erro: "Selecione ao menos uma matriz (ou lote)." };
  if (!e.dataD0) return { erro: `Informe a data do ${rotuloD(e.protocolo)}.` };
  return {
    dados: {
      protocolo_id: Number(e.protocoloId), animais: e.animais, data_d0: e.dataD0,
      responsavel: e.responsavel || undefined, observacao: e.observacao.trim() || undefined,
    },
  };
}
