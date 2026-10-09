// Réguas de referência (Relatórios › Leite) — modelo de tela das respostas de
// GET /financeiro/reguas-referencia (faixas, textos jurídicos versionados, aceite)
// e GET /financeiro/reguas-referencia/indicadores-fazenda (o número da fazenda,
// calculado no SERVIDOR com a mesma DRE e o mesmo Resultado por litro).
//
// Parecer jurídico de 08/10/2026 (itens 6 e 7): sem semáforo, sem verde/vermelho,
// sem linguagem de meta ("bom/ruim", "acima/abaixo da média", "alvo", "eficiente",
// "zona de atenção"); faixa cinza neutra e a palavra "referência". Faixa só aparece
// com a régua "publicada", sem aceite pendente e dentro da validade — a API já
// garante isso; aqui repetimos a trava (defesa em camadas). Os textos do alerta,
// do pop-up, do rodapé e da autorização vêm da API, exatamente como estão.
// PURO (sem React, sem fetch) — testes em reguasReferencia.test.ts.

export type SituacaoRegua = "publicada" | "em_validacao" | "retirada" | "vencida" | "sem_faixa";
export type Fidedignidade = "alta" | "media" | "baixa";
export type FaixaRegua = { min?: number | null; max?: number | null; [outro: string]: number | null | undefined };
export type FonteRegua = { id: string; nome: string; ano: number | null; url: string | null; origem: "nacional" | "internacional" | string };
export type Regua = {
  codigo: string; nome: string; unidade: string; definicao_cowdata: string;
  situacao: SituacaoRegua; publicavel: boolean; exibir_faixa: boolean;
  faixa: FaixaRegua | null; fidedignidade: Fidedignidade | null; ressalva: string | null;
  compilado_em: string | null; vence_em: string | null; fontes: FonteRegua[];
};
export type TextoJuridico = {
  chave: string; versao: string; vigente_desde: string; texto: string; sha256: string;
  botao?: string; disponivel_para_aceite?: boolean; pendente?: string | null;
};
export type RespostaReguas = {
  versao: string; versao_reguas: string; revisado_em: string; conferida_em: string; valido_ate: string; proxima_conferencia: string;
  vencida: boolean; publicacao: { liberada: boolean }; empresa_pendente: boolean;
  aceite: { tipo: string; versao: string; sha256: string; pendente: boolean; aceito_em_utc: string | null };
  aceite_pendente: boolean; faixas_ocultas_ate_aceite: boolean;
  textos: { alerta: TextoJuridico; modal: TextoJuridico; compartilhamento_parametro: TextoJuridico; rodape_exportacao: TextoJuridico; exportacao_autorizacao: TextoJuridico };
  reguas: Regua[];
  exportacao?: { permitir_com_reguas: boolean };
};
export type IndicadorFazenda = { valor: number | null; conta: string | null; relatorio: string | null; motivo: string | null };
export type RespostaIndicadoresReguas = {
  periodo: { inicio: string; fim: string }; regime: string; centro_custo: string | null; regras_v2: boolean;
  indicadores: Record<string, IndicadorFazenda>;
};

/** A faixa desta régua pode aparecer? Só publicada, com faixa, sem aceite pendente e na validade. */
export function mostraFaixa(r: Regua, resp: Pick<RespostaReguas, "aceite_pendente" | "vencida">): boolean {
  const f = r.faixa;
  return r.situacao === "publicada" && r.exibir_faixa && !!f && (f.min != null || f.max != null) && !resp.aceite_pendente && !resp.vencida;
}

export function algumaFaixaVisivel(resp: RespostaReguas | null): boolean {
  return !!resp && resp.reguas.some((r) => mostraFaixa(r, resp));
}

export const NOME_SITUACAO: Record<SituacaoRegua, string> = {
  publicada: "Publicada",
  em_validacao: "Em validação, ainda não liberada",
  retirada: "Retirada",
  vencida: "Validade vencida",
  sem_faixa: "Sem faixa",
};

/** Por que esta régua não mostra faixa (texto curto, sem número de faixa). */
export function porqueSemFaixa(r: Regua, resp: Pick<RespostaReguas, "aceite_pendente" | "vencida">): string | null {
  if (mostraFaixa(r, resp)) return null;
  if (r.situacao === "publicada" && resp.aceite_pendente) return "A faixa aparece depois que você ler e confirmar o aviso desta tela.";
  if (r.situacao === "publicada" && resp.vencida) return "A faixa passou da validade de 12 meses e saiu da tela até a próxima conferência.";
  switch (r.situacao) {
    case "em_validacao":
      return "A faixa desta régua ainda está sendo conferida (fontes, termos de uso e dupla validação). Até ser liberada, mostramos só o número da fazenda.";
    case "retirada":
      return "A faixa foi tirada do ar para revisão. Mostramos só o número da fazenda.";
    case "vencida":
      return "A faixa passou da validade de 12 meses e saiu da tela até a próxima conferência.";
    case "sem_faixa":
      return r.unidade === "R$/L"
        ? "Valores em reais não viram faixa, porque dependem de região, época e moeda. Mostramos só o número da fazenda."
        : "Esta régua não tem faixa nesta versão: as fontes não sustentam uma faixa única para esta conta. Mostramos só o número da fazenda.";
    default:
      return "Sem faixa nesta versão.";
  }
}

const n = (v: number, casas: number) => v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
const sinal = (v: number) => (v < 0 ? "−" : "");

/** O número na unidade da régua ("35,0%", "1,45×", "1,3 mês", "R$ 2,00/L", "362 L"). */
export function formatarValorRegua(unidade: string, v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—";
  const a = Math.abs(v), s = sinal(v);
  switch (unidade) {
    case "%": return `${s}${n(a, 1)}%`;
    case "x": return `${s}${n(a, 2)}×`;
    case "meses": return `${s}${n(a, 1)} ${a >= 2 ? "meses" : "mês"}`;
    case "R$/L": return `${s}R$ ${n(a, 2)}/L`;
    case "L": return `${s}${n(a, 0)} L`;
    case "L/ha": return `${s}${n(a, 0)} L/ha`;
    default: return `${s}${n(a, 1)}`;
  }
}

/** Faixa em palavras, neutra: só os limites da referência (sem "alvo", "eficiente" ou "atenção"). */
export function textoFaixa(r: Regua): string | null {
  const f = r.faixa;
  if (!f) return null;
  if (f.min != null && f.max != null) return `referência de ${limiteFaixa(r.unidade, f.min, false)} a ${limiteFaixa(r.unidade, f.max)}`;
  if (f.max != null) return `referência até ${limiteFaixa(r.unidade, f.max)}`;
  if (f.min != null) return `referência a partir de ${limiteFaixa(r.unidade, f.min)}`;
  return null;
}

/** Limite da faixa como as fontes publicam (sem casas inúteis): "40%", "1,5 mês", "1,25×". */
export function limiteFaixa(unidade: string, v: number, comUnidade = true): string {
  const t = v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
  if (!comUnidade) return t;
  switch (unidade) {
    case "%": return `${t}%`;
    case "x": return `${t}×`;
    case "meses": return `${t} ${Math.abs(v) >= 2 ? "meses" : "mês"}`;
    case "R$/L": return `R$ ${t}/L`;
    case "L": case "L/ha": return `${t} ${unidade}`;
    default: return t;
  }
}

/** Onde o número da fazenda cai em relação à faixa — só posição, nunca juízo. */
export function posicaoEmPalavras(r: Regua, v: number | null | undefined, resp: Pick<RespostaReguas, "aceite_pendente" | "vencida">): string {
  if (v == null || !isFinite(v)) return "sem número no período";
  if (!mostraFaixa(r, resp)) return "sem faixa de referência para comparar";
  const f = r.faixa!;
  if (f.min != null && v < f.min) return "menor que a faixa de referência";
  if (f.max != null && v > f.max) return "maior que a faixa de referência";
  return "dentro da faixa de referência";
}

/** Escala do trilho (só geometria do desenho): inclui o número da fazenda e, se visível, a faixa. */
export function escalaRegua(r: Regua, v: number | null | undefined, resp: Pick<RespostaReguas, "aceite_pendente" | "vencida">): { min: number; max: number } | null {
  const vals: number[] = [];
  if (v != null && isFinite(v)) vals.push(v);
  if (mostraFaixa(r, resp)) for (const x of [r.faixa!.min, r.faixa!.max]) if (x != null) vals.push(x);
  if (!vals.length) return null;
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const min = lo >= 0 ? Math.max(0, lo * 0.7) : lo * 1.3;
  const max = hi > 0 ? hi * 1.25 : hi * 0.7 + 1;
  return { min, max: max > min ? max : min + 1 };
}

export const NOME_SELO: Record<Fidedignidade, string> = { alta: "Alta", media: "Média", baixa: "Baixa" };

/** Critério de cada selo, lido do próprio texto do pop-up (linhas "• Alta: …"): nenhum texto jurídico novo no cliente. */
export function criteriosDoSelo(textoModal: string | null | undefined): Partial<Record<Fidedignidade, string>> {
  const out: Partial<Record<Fidedignidade, string>> = {};
  for (const linha of (textoModal || "").split("\n")) {
    const m = linha.match(/^\s*[•\-*]\s*(Alta|Média|Media|Baixa)\s*:\s*(.+)$/i);
    if (!m) continue;
    const k = m[1].toLowerCase().startsWith("a") ? "alta" : m[1].toLowerCase().startsWith("b") ? "baixa" : "media";
    out[k] = m[2].trim();
  }
  return out;
}

/** Parágrafos de um texto jurídico (separados por linha em branco), sem mudar uma letra. */
export function paragrafos(texto: string | null | undefined): string[] {
  return (texto || "").split(/\n{2,}/).map((p) => p.replace(/\s+$/g, "")).filter((p) => p.trim().length > 0);
}

/** O texto de autorização com o destinatário digitado (o modelo da API traz {{destinatario}}). */
export function textoAutorizacao(modelo: string | null | undefined, destinatario: string): string {
  const d = destinatario.trim() || "[destinatário]";
  const base = modelo && modelo.includes("{{destinatario}}") ? modelo : "Autorizo o envio deste relatório a {{destinatario}}.";
  return base.replace(/\{\{\s*destinatario\s*\}\}/g, d);
}

export type LinhaReguaTela = {
  regua: Regua; indicador: IndicadorFazenda | null; faixaVisivel: boolean;
  valorTexto: string; posicao: string; faixaTexto: string | null; porque: string | null;
};

/** As linhas da tela, na ordem da API (a rotina mensal decide a ordem). */
export function linhasReguas(resp: RespostaReguas | null, ind: RespostaIndicadoresReguas | null): LinhaReguaTela[] {
  if (!resp) return [];
  return resp.reguas.map((r) => {
    const i = ind?.indicadores[r.codigo] ?? null;
    const vis = mostraFaixa(r, resp);
    return {
      regua: r, indicador: i, faixaVisivel: vis,
      valorTexto: formatarValorRegua(r.unidade, i?.valor),
      posicao: posicaoEmPalavras(r, i?.valor, resp),
      faixaTexto: vis ? textoFaixa(r) : null,
      porque: porqueSemFaixa(r, resp),
    };
  });
}

/** Frase-resumo da tela, honesta com o estado de hoje (nenhuma faixa publicada). */
export function fraseReguas(linhas: LinhaReguaTela[], periodoLabel: string): string {
  if (!linhas.length) return "";
  const comFaixa = linhas.filter((l) => l.faixaVisivel);
  const comNumero = linhas.filter((l) => l.indicador?.valor != null).length;
  if (!comFaixa.length) {
    return `Nenhuma faixa de referência está liberada nesta versão. Em ${periodoLabel}, a tela mostra os ${comNumero} indicadores da fazenda que o CowData já calcula, cada um com a conta que o gerou.`;
  }
  const dentro = comFaixa.filter((l) => l.posicao === "dentro da faixa de referência").length;
  return `Em ${periodoLabel}, ${dentro} de ${comFaixa.length} indicadores com faixa ficam dentro da faixa de referência. Faixa de referência é estimativa de mercado: não é meta nem recomendação.`;
}

/** Linhas para Excel/PDF. `comReguas`: inclui a coluna da faixa (só com autorização expressa). */
export function linhasExportacaoReguas(linhas: LinhaReguaTela[], comReguas: boolean): (string | null)[][] {
  return linhas.map((l) => [
    l.regua.nome,
    l.indicador?.valor != null ? l.valorTexto : `— (${l.indicador?.motivo || "sem número"})`,
    ...(comReguas ? [l.faixaVisivel ? `${l.faixaTexto} (${l.posicao})` : NOME_SITUACAO[l.regua.situacao]] : []),
    l.indicador?.conta ?? null,
  ]);
}
