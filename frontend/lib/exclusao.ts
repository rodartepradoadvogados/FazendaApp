// Tipos e helpers PUR0S da exclusão (Fase 2 do "Excluir lançamentos").
// Sem DOM, sem fetch — só o que dá pra testar com o runner nativo do Node.
// O SERVIDOR é a fonte da verdade do risco e das exigências; aqui só espelhamos
// para a tela renderizar a decisão proporcional (motivo / digitar confirmação).

export type LinhaImpacto = {
  titulo: string;
  consequencia: string;
  qtd?: number;
  valor?: number | null;
  filhos?: string[];
  chip?: string | null;
};

export type BloqueioExclusao = {
  titulo: string;
  motivo: string;
  fazer: string;
  acao?: { rota?: string; params?: Record<string, string> };
};

export type ImpactoExclusao = {
  item: { tipo: string; id: string; titulo: string };
  apagar: LinhaImpacto[];
  reverter: LinhaImpacto[];
  bloqueia: BloqueioExclusao[];
  avisos: LinhaImpacto[];
  risco: string | null; // "baixo" | "medio" | "alto" | null (server já calcula)
  porque: string[];
  editar_url: string | null;
  impacto?: string[]; // compat com a tela antiga
};

export type PedidoExclusao = {
  id: number;
  tipo: string;
  id_alvo: string;
  titulo: string | null;
  solicitado_por: string | null;
  criado_em: string;
  status: string;
  motivo: string | null;
  risco: string | null;
  impacto_resumo_json: string | null;
  decidido_por?: string | null;
  decidido_em?: string | null;
  motivo_rejeicao?: string | null;
  alvo_existe?: boolean;
  apoiadores?: string[];
  impacto?: ImpactoExclusao;
};

export type RegistroTrilha = {
  codigo: string;
  acao: string;
  tipo: string | null;
  id_alvo: string | null;
  titulo: string | null;
  usuario: string | null;
  motivo: string | null;
  criado_em: string;
};

export const NIVEIS_RISCO = ["baixo", "medio", "alto"] as const;
export type Risco = (typeof NIVEIS_RISCO)[number];

export const RISCO_TXT: Record<Risco, [string, string]> = {
  baixo: ["Risco baixo", "Um registro isolado. Nada mais muda."],
  medio: ["Risco médio", "Mexe em outras coisas (estoque, contas, lactação) ou apaga mais de um. Diga o motivo."],
  alto: ["Risco alto", "Apaga muita coisa, ou um cadastro em uso. Não dá para desfazer. Confirme digitando."],
};

// ── Para onde mandar o usuário ao clicar "corrigir em vez de apagar" ──
export const DESTINO_EDITAR: Record<string, string> = {
  animal: "/rebanho?aba=ficha&numero=",
  servico: "/lancamentos?ir=inseminacao",
  parto: "/lancamentos?ir=parto",
  controle: "/lancamentos?ir=controle",
  sanidade: "/lancamentos?ir=sanidade_aplicacao",
  protocolo_sanitario_lancamento: "/lancamentos?ir=protocolo_sanitario",
  protocolo_iatf_lancamento: "/lancamentos?ir=protocolo_iatf",
  financeiro: "/financeiro",
  compra_animal: "/lancamentos?ir=comprar_animal",
  compra_semen: "/lancamentos?ir=comprar_semen",
  venda_animal: "/lancamentos?ir=vender_animal",
  estoque: "/lancamentos?ir=estoque_entradas_saidas",
  evento_manual: "/agenda",
  calendario_sanitario: "/protocolos?aba=cadastro&tipo=sanitario&sub=preventivo",
  lote: "/configuracoes?aba=cadastro",
  fornecedor: "/configuracoes?aba=cadastro",
  motivo_movimentacao: "/configuracoes?aba=cadastro",
  pessoa: "/configuracoes?aba=cadastro",
  principio_ativo: "/configuracoes?aba=cadastro",
  doenca: "/configuracoes?aba=cadastro",
  evento_sanitario: "/configuracoes?aba=cadastro",
  protocolo_sanitario: "/configuracoes?aba=cadastro",
  safra: "/configuracoes?aba=cadastro&sub=safra",
};

export function destinoEditar(tipoReal: string, id: string): string | null {
  const base = DESTINO_EDITAR[tipoReal];
  if (!base) return null;
  return tipoReal === "animal" ? `${base}${encodeURIComponent(id)}` : base;
}

// ── Totais e risco (espelha o servidor; a tela só mostra) ──
export function totaisImp(imp: ImpactoExclusao) {
  const n = (imp.apagar || []).reduce((s, x) => s + (x.qtd ?? 1), 0);
  const din = (imp.apagar || []).reduce((s, x) => s + (typeof x.valor === "number" ? x.valor : 0), 0);
  const rev = (imp.reverter || []).length;
  const av = (imp.avisos || []).length;
  return { n, din, rev, av };
}

const ORDEM: Record<string, number> = { baixo: 0, medio: 1, alto: 2 };

export function riscoItem(imp: ImpactoExclusao): Risco {
  if (imp.risco === "medio" || imp.risco === "alto") return imp.risco;
  const t = totaisImp(imp);
  if (t.n >= 10) return "alto";
  if (t.rev > 0 || t.din > 0 || t.n > 1) return "medio";
  return "baixo";
}

export function riscoDe(itens: ImpactoExclusao[]): Risco {
  let r: Risco = "baixo";
  for (const i of itens) {
    const x = riscoItem(i);
    if (ORDEM[x] > ORDEM[r]) r = x;
  }
  if (itens.length >= 10) return "alto";
  if (itens.length >= 2 && r === "baixo") return "medio";
  return r;
}

export function porqueDe(itens: ImpactoExclusao[]): string[] {
  const p = new Set<string>();
  for (const i of itens) {
    for (const r of i.porque || []) p.add(r);
    const t = totaisImp(i);
    if (t.din > 0) p.add("tem dinheiro em aberto");
    if (t.rev > 0) p.add("mexe em outros dados (estoque, lactação, saldos)");
    if (t.n > 1) p.add(`apaga ${t.n} registros`);
  }
  if (itens.length >= 2) p.add(`${itens.length} itens de uma vez`);
  return [...p];
}

// ── Exigências da confirmação ──
export function exigeMotivo(risco: Risco, ehAdmin: boolean): boolean {
  return !ehAdmin || risco === "medio" || risco === "alto";
}

export function exigeConfirmacao(risco: Risco): boolean {
  return risco === "alto";
}

// Decisão do dono #3: ficha de animal pede o número; demais tipos pedem "APAGAR".
export function confirmacaoEsperada(tipo: string, id: string): string {
  return tipo === "animal" ? (id || "").trim() : "APAGAR";
}

// ── Agregações para a tela ──
export function somarImpacto(itens: ImpactoExclusao[]) {
  return itens.reduce(
    (acc, i) => {
      const t = totaisImp(i);
      acc.n += t.n;
      acc.din += t.din;
      acc.rev += t.rev;
      acc.av += t.av;
      return acc;
    },
    { n: 0, din: 0, rev: 0, av: 0 },
  );
}

// Financeiro: parcela como filha da nota (busca agrupada, Fase 3). Campo que
// identifica a nota (ex.: "numero_lancamento"). Mantém a ordem de entrada.
export function agruparPorNota<T extends Record<string, any>>(linhas: T[], campo: string): Record<string, T[]> {
  const out: Record<string, T[]> = {};
  for (const l of linhas) {
    const k = l?.[campo] ?? "";
    (out[k] ||= []).push(l);
  }
  return out;
}

// Chave estável de duplicidade (tipo + alvo) para dedup de pedidos no cliente.
export function chaveDuplicidade(tipo: string, id: string): string {
  return `${tipo}:${id}`;
}

// Resumo de uma linha para listas/comparativos.
export function fraseResumo(imp: ImpactoExclusao): string {
  const t = totaisImp(imp);
  const partes: string[] = [];
  if (imp.bloqueia?.length) partes.push("bloqueado");
  if (t.n) partes.push(`${t.n} apagado(s)`);
  if (t.rev) partes.push(`${t.rev} revertido(s)`);
  if (t.av) partes.push(`${t.av} aviso(s)`);
  return partes.join(" · ") || "nada muda";
}