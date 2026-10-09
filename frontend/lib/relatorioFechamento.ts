// Relatórios › Entrega ao contador (Fase C5): modelo de tela do Fechamento do
// mês, da Conciliação bancária e do Pacote do contador. PURO (só import de
// tipo) — testes em relatorioFechamento.test.ts. Os números vêm do servidor;
// aqui só se escolhe a frase, a ordem e o rótulo.
import type {
  ItemChecklist, ItemPacote, LinhaExtrato, MovSistema, SituacaoConciliacao, SituacaoMes, StatusMes,
} from "@/lib/fechamentoApi";

const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

export type Trecho = { t: string; b?: boolean };

export function nomeMes(ym: string): string {
  return `${MESES[Number(ym.slice(5, 7)) - 1]}/${ym.slice(0, 4)}`;
}
export function nomeMesCurto(ym: string): string {
  return `${MESES_CURTOS[Number(ym.slice(5, 7)) - 1]}/${ym.slice(2, 4)}`;
}
const maiuscula = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`;
const somaMes = (ym: string, k: number) => {
  const [a, m] = ym.split("-").map(Number);
  const i = a * 12 + (m - 1) + k;
  return `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`;
};

/** O mês que o Fechamento/Conciliação mostram quando a URL traz outro tipo de período:
 *  o último mês do período, sem passar do mês anterior ao de hoje (o "último fechável"). */
export function mesDoPeriodo(p: { tipo: string; val: string; fim: string }, hoje: string): string {
  if (p.tipo === "m") return p.val;
  const ultimoFechavel = somaMes(hoje.slice(0, 7), -1);
  const doPeriodo = p.fim.slice(0, 7);
  return doPeriodo < ultimoFechavel ? doPeriodo : ultimoFechavel;
}

// ── Fechamento do mês ──────────────────────────────────────────────────────
export function tituloFechamento(mes: string, status: StatusMes): string {
  const n = maiuscula(nomeMes(mes));
  if (status === "fechado") return `${n} está fechado`;
  if (status === "em_curso") return `${n} ainda está em curso`;
  return `${n} está pronto para fechar?`;
}

export function contagemChecklist(cl: ItemChecklist[]) {
  const bloqueiam = cl.filter((c) => c.bloqueia);
  const ok = bloqueiam.filter((c) => c.ok).length;
  return { ok, total: bloqueiam.length, pendentes: bloqueiam.length - ok, avisos: cl.filter((c) => !c.bloqueia && !c.ok).length };
}

export function fraseFechamento(s: SituacaoMes, dataBr: (iso: string) => string): Trecho[] {
  const mes = nomeMes(s.mes);
  if (s.status === "fechado" && s.evento_atual) {
    return [
      { t: `${maiuscula(mes)} foi fechado em ` }, { t: dataBr(s.evento_atual.criado_em || ""), b: true },
      { t: " por " }, { t: s.evento_atual.usuario || "—", b: true },
      { t: ". Os lançamentos com competência ou pagamento no mês estão travados: para corrigir algo, um administrador reabre com motivo — fica na trilha." },
    ];
  }
  const c = contagemChecklist(s.checklist);
  if (c.pendentes === 0) {
    return [{ t: `As ${c.total} conferências estão ok em ${mes}. ` },
      { t: s.status === "em_curso" ? "O mês ainda está em curso: feche depois do último dia." : "Pode fechar e travar o mês." }];
  }
  return [
    { t: `${c.ok} de ${c.total}`, b: true }, { t: ` conferências automáticas estão ok em ${mes}. ` },
    { t: s.status === "em_curso" ? "O mês ainda está em curso; dá para ir resolvendo as pendências." : "Resolva as pendências abaixo para fechar e travar o mês." },
  ];
}

export type EstadoBotaoFechar = { mostra: boolean; habilitado: boolean; comPendencias: boolean; dica: string };

/** O que o botão "Fechar" pode fazer agora, e por quê (texto da dica ao lado). */
export function estadoBotaoFechar(s: SituacaoMes, admin: boolean, dataBr: (iso: string) => string): EstadoBotaoFechar {
  if (s.status === "fechado") return { mostra: false, habilitado: false, comPendencias: false, dica: "" };
  if (!admin) return { mostra: false, habilitado: false, comPendencias: false, dica: "Só um administrador fecha o mês." };
  if (!s.regras_v2) return { mostra: true, habilitado: false, comPendencias: false, dica: "Ligue as regras novas dos relatórios em Parâmetros financeiros para fechar meses." };
  if (s.status === "em_curso") return { mostra: true, habilitado: false, comPendencias: false, dica: `Disponível a partir de ${dataBr(s.pode_fechar_a_partir_de)}.` };
  const c = contagemChecklist(s.checklist);
  if (c.pendentes > 0) return { mostra: true, habilitado: true, comPendencias: true, dica: `Faltam ${plural(c.pendentes, "conferência", "conferências")}: dá para fechar assim mesmo, com motivo.` };
  return { mostra: true, habilitado: true, comPendencias: false, dica: "Depois de fechado, só reabre com motivo." };
}

const reais = (v: unknown) => {
  const n = Number(v) || 0;
  const s = Math.abs(n).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${n < 0 ? "−" : ""}R$ ${s}`;
};

/** Uma linha legível para cada item de uma conferência (o servidor manda o dado cru). */
export function descreverItem(idConferencia: string, i: Record<string, unknown>): { titulo: string; sub: string } {
  switch (idConferencia) {
    case "sem_conta": return { titulo: `${i.codigo ?? ""} ${i.nome ?? "(sem conta)"}`.trim(), sub: `receita ${reais(i.receita)} · despesa ${reais(i.despesa)}` };
    case "natureza": return { titulo: `${i.fornecedor ?? i.descricao ?? "Lançamento"} · ${reais(i.valor)}`, sub: `${i.numero_lancamento ?? ""} · ${i.motivo ?? ""}`.replace(/^ · /, "") };
    case "contas_automaticas": return { titulo: String(i.rotulo ?? "Origem automática"), sub: `${plural(Number(i.lancamentos) || 0, "lançamento", "lançamentos")} · ${reais(i.valor)} sem conta` };
    case "saldo_abertura": return { titulo: String(i.conta ?? "Conta corrente"), sub: "sem saldo de abertura conferido com o extrato" };
    case "cartao": return { titulo: `${i.cartao ?? "Cartão"} · fatura de ${nomeMes(String(i.competencia ?? "2000-01"))}`, sub: `fecha em ${String(i.data_fechamento ?? "").split("-").reverse().join("/")} e ainda está aberta` };
    case "folha": return { titulo: `Folha nº ${i.folha_id}`, sub: `líquido ${reais(i.valor_liquido)} · ${i.status === "pendente" ? "não paga" : i.status}` };
    case "conciliacao": return { titulo: String(i.conta ?? "Conta"), sub: !i.importado ? "extrato do mês não importado" : `${plural(Number(i.pendentes) || 0, "linha pendente", "linhas pendentes")}${i.diferenca != null ? ` · diferença ${reais(i.diferenca)}` : ""}` };
    case "depreciacao": return { titulo: String(i.item ?? "Bem"), sub: String(i.motivo ?? "sem dados para depreciar") };
    default: return { titulo: JSON.stringify(i), sub: "" };
  }
}

// ── Conciliação bancária ───────────────────────────────────────────────────
export type SituacaoLinha = "conciliado" | "sugerido" | "so_extrato" | "sem_lancamento" | "so_sistema" | "valor_diferente";
export type LinhaTela = {
  chave: string; data: string; descricao: string; sub: string | null; extrato: number | null; sistema: number | null;
  situacao: SituacaoLinha; linha: LinhaExtrato | null; mov: MovSistema | null;
};

export const ROTULO_SITUACAO: Record<SituacaoLinha, string> = {
  conciliado: "conciliado", sugerido: "par sugerido", so_extrato: "só no extrato", sem_lancamento: "sem lançamento",
  so_sistema: "só no sistema", valor_diferente: "valor diferente",
};

const ORDEM: Record<SituacaoLinha, number> = { so_extrato: 0, valor_diferente: 1, sugerido: 2, so_sistema: 3, sem_lancamento: 4, conciliado: 5 };

/** Extrato e sistema numa lista só: o que pede atenção primeiro, depois por data. */
export function linhasConciliacao(s: SituacaoConciliacao | null): LinhaTela[] {
  if (!s) return [];
  const out: LinhaTela[] = s.linhas.map((l) => {
    const par = l.status === "pareado" ? l.par : null;
    const sug = l.status === "pendente" ? l.sugestao : null;
    const alt = l.status === "pendente" && !sug ? l.alternativas.find((a) => !a.exata) ?? null : null;
    const situacao: SituacaoLinha = l.status === "pareado" ? "conciliado" : l.status === "sem_lancamento" ? "sem_lancamento"
      : sug ? "sugerido" : alt ? "valor_diferente" : "so_extrato";
    const mov = par ?? sug ?? alt;
    return {
      chave: `x${l.id}`, data: l.data, descricao: l.historico || "(sem histórico)",
      sub: mov && mov.descricao ? `${mov.numero_lancamento ? mov.numero_lancamento + " · " : ""}${mov.fornecedor ? mov.fornecedor + " · " : ""}${mov.descricao}` : l.observacao,
      extrato: l.valor, sistema: mov ? mov.valor : null, situacao, linha: l, mov,
    };
  });
  const mostrados = new Set(out.filter((l) => l.mov).map((l) => `${l.mov!.tipo}${l.mov!.id}`));
  for (const m of s.so_no_sistema) {
    if (mostrados.has(`${m.tipo}${m.id}`)) continue; // já aparece ao lado da linha do extrato
    out.push({
      chave: `s${m.tipo}${m.id}`, data: m.data, descricao: [m.fornecedor, m.descricao].filter(Boolean).join(" · ") || "Lançamento",
      sub: m.numero_lancamento, extrato: null, sistema: m.valor, situacao: "so_sistema", linha: null, mov: m,
    });
  }
  return out.sort((a, b) => ORDEM[a.situacao] - ORDEM[b.situacao] || (a.data < b.data ? -1 : a.data > b.data ? 1 : 0));
}

/** Σ (extrato − sistema) das linhas da lista: tem de dar o movimento do extrato − o do sistema no mês
 *  (a conferência da tela). Par confirmado com o mesmo valor soma zero. */
export function somaDiferencas(linhas: LinhaTela[]): number {
  return Math.round(linhas.reduce((t, l) => t + (l.extrato ?? 0) - (l.sistema ?? 0), 0) * 100) / 100;
}

export function fraseConciliacao(s: SituacaoConciliacao | null, mes: string, brl: (v: number) => string): Trecho[] {
  if (!s) return [{ t: "Cadastre uma conta corrente para conciliar." }];
  const m = nomeMes(mes);
  if (!s.importado) {
    return [{ t: `O extrato de ${m} desta conta ainda não foi importado. ` },
      { t: s.so_no_sistema.length ? `${plural(s.so_no_sistema.length, "movimento do sistema espera", "movimentos do sistema esperam")} o extrato para conferir.` : "Também não há movimento no sistema." }];
  }
  const pend = s.contagem.pendentes;
  const dif = s.saldos.diferenca;
  if (dif != null && Math.abs(dif) < 0.005 && pend === 0) {
    return [{ t: `Em ${m} o extrato do ${s.banco} e o sistema batem centavo a centavo.` }];
  }
  const out: Trecho[] = [];
  if (dif != null) out.push({ t: `Em ${m} o extrato e o sistema diferem em ` }, { t: brl(Math.abs(dif)), b: true }, { t: ". " });
  else out.push({ t: `Em ${m}, sem saldo informado no extrato, a comparação é pelo movimento do mês. ` });
  out.push({ t: pend ? `${plural(pend, "linha do extrato precisa", "linhas do extrato precisam")} de atenção` : "Todas as linhas do extrato estão conciliadas" });
  if (s.contagem.sugestoes_exatas) out.push({ t: ` (${plural(s.contagem.sugestoes_exatas, "par sugerido", "pares sugeridos")} na fila)` });
  out.push({ t: `; ${plural(s.contagem.pareadas, "está conciliada", "estão conciliadas")}.` });
  return out;
}

// ── Pacote do contador ─────────────────────────────────────────────────────
export function frasePacote(itens: ItemPacote[], emCurso: boolean): Trecho[] {
  const ok = itens.filter((i) => i.ok).length;
  const falta = itens.length - ok;
  return [
    { t: `${ok} de ${itens.length}`, b: true }, { t: " itens estão prontos para o contador" },
    { t: emCurso ? ". Como o período ainda não acabou, o pacote é uma prévia" : "" },
    { t: falta ? ". O que falta está marcado e vai junto, no arquivo de pendências." : ". Tudo pronto." },
  ];
}

/** Nome de arquivo previsível para o pacote (o servidor manda o definitivo). */
export function nomePacote(fazenda: string, ini: string, fim: string): string {
  const slug = fazenda.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "fazenda";
  return `pacote-contador_${slug}_${ini}_${fim}.zip`;
}
