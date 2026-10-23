// Sanitário Preventivo v2 — tipos, vocabulário e serializadores PUROS.
//
// Fonte da verdade dos contratos: backend/fazenda/api/routers/sanitario/
// (schemas.py e as rotas). TODOS os schemas de entrada do back usam
// `extra="forbid"`: um campo a mais vira 422. Por isso cada payload que o
// front envia passa por um serializador daqui, que copia SÓ as chaves que o
// schema conhece (listas CAMPOS_* abaixo) — o teste lib/sanitarioTipos.test.ts
// lê o schemas.py e confere que as listas batem com o back.
//
// Este arquivo não importa nada (roda no `node --test` sem bundler) e é
// reaproveitado pelo app de campo.
//
// Datas: sempre "AAAA-MM-DD" (fuso America/Sao_Paulo). Nunca `new Date("AAAA-MM-DD")`
// (que vira meia-noite UTC e cai no dia anterior no Brasil) — use as funções
// de data daqui.

// ════════════════════════════════════════════════════════════════════════════
// Vocabulário fechado (espelha os Literal do schemas.py)
// ════════════════════════════════════════════════════════════════════════════
export const TIPOS_CAIXA = ["vacina", "exame", "vermifugo", "outro"] as const;
export type TipoCaixa = (typeof TIPOS_CAIXA)[number];
export const PRODUTO_MODOS = ["estoque", "sem_estoque", "vazio", "nao_se_aplica"] as const;
export type ProdutoModo = (typeof PRODUTO_MODOS)[number];
export const DOSE_UNIDADES = ["mL", "dose", "g", "comprimido", "mL_por_kg", "mL_por_x_kg"] as const;
export type DoseUnidade = (typeof DOSE_UNIDADES)[number];
export const EVENTO_TIPOS = ["idade", "pre_parto", "entrada_ia", "parto", "secagem", "compra"] as const;
export type EventoTipo = (typeof EVENTO_TIPOS)[number];
export const PERIODO_MODOS = ["meses", "frequencia", "continuo"] as const;
export type PeriodoModo = (typeof PERIODO_MODOS)[number];
export const AO_FECHAR = ["perder", "manter", "descartar"] as const;
export type AoFechar = (typeof AO_FECHAR)[number];
export const CONDICOES = ["prenhe", "pre_parto", "lactacao", "seca", "apta_ia"] as const;
export type Condicao = (typeof CONDICOES)[number];
export const MODOS_LEITE = ["bloqueio", "descarte", "tanque"] as const;
export type ModoLeite = (typeof MODOS_LEITE)[number];
export const RESULTADOS = ["positivo", "negativo", "inconclusivo", "nao_lido"] as const;
export type Resultado = (typeof RESULTADOS)[number];
export const COLUNAS_FICHA = ["brinco", "categoria", "lote", "idade", "peso", "dose", "partida", "aplicado", "resultado",
  "assinatura", "obs"] as const;
export type ColunaFicha = (typeof COLUNAS_FICHA)[number];

export const ROTULO_TIPO: Record<TipoCaixa, string> = { vacina: "Vacina", exame: "Exame", vermifugo: "Vermífugo", outro: "Outro" };
export const ROTULO_UNIDADE: Record<DoseUnidade, string> = {
  mL: "mL", dose: "dose", g: "g", comprimido: "comprimido", mL_por_kg: "mL por kg", mL_por_x_kg: "mL por X kg",
};
export const ROTULO_EVENTO: Record<EventoTipo, string> = {
  idade: "Idade (desde o nascimento)", pre_parto: "Pré-parto (antes do parto previsto)", entrada_ia: "Entrada em IA",
  parto: "Parto", secagem: "Secagem", compra: "Compra",
};
export const ROTULO_CONDICAO: Record<Condicao, string> = {
  prenhe: "Prenhe", pre_parto: "Pré-parto", lactacao: "Em lactação", seca: "Seca", apta_ia: "Apta para IA",
};
export const ROTULO_MODO_LEITE: Record<ModoLeite, string> = {
  bloqueio: "Bloqueio total", descarte: "Confirma com descarte", tanque: "Vai para o tanque",
};
export const AJUDA_MODO_LEITE: Record<ModoLeite, string> = {
  bloqueio: "Não deixa lançar o leite destes animais.",
  descarte: "Lança como descarte, fora do tanque.",
  tanque: "Sob responsabilidade do produtor.",
};
export const ROTULO_RESULTADO: Record<Resultado, string> = {
  positivo: "Reagente", negativo: "Negativo", inconclusivo: "Inconclusivo", nao_lido: "Não lido",
};
export const ROTULO_COLUNA_FICHA: Record<ColunaFicha, string> = {
  brinco: "Brinco", categoria: "Categoria", lote: "Lote", idade: "Idade", peso: "Peso", dose: "Dose",
  partida: "Produto e partida", aplicado: "Aplicado", resultado: "Resultado", assinatura: "Assinatura", obs: "Observação",
};
export const MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"] as const;

/** Situação do animal numa caixa (sanitario_situacao.estado). */
export type EstadoSituacao = "prevista" | "aviso" | "janela" | "atrasada" | "marcada" | "aplicada" | "perdida"
  | "dispensada" | "descartada" | "saiu" | string;
export const ROTULO_SITUACAO: Record<string, string> = {
  prevista: "prevista", aviso: "em aviso", janela: "na janela", atrasada: "atrasada", marcada: "marcada",
  aplicada: "aplicada", perdida: "perdida", dispensada: "dispensada", descartada: "descartada", saiu: "saiu",
};
/** Origem do registro (sanitario_registro.origem). */
export const ROTULO_ORIGEM: Record<string, string> = {
  dia: "Dia marcado", lancamento_simples: "Lançamento simples", ficha: "Ficha de campo", importado: "Planilha importada",
  janela: "Veio pela janela", manual: "Incluído manualmente", curral: "Decisão no curral",
};
export const ROTULO_ESTADO_DIA: Record<string, string> = {
  marcado: "Marcado", em_execucao: "Em andamento", fechado: "Fechado", cancelado: "Cancelado",
};

// ════════════════════════════════════════════════════════════════════════════
// Datas (fuso America/Sao_Paulo, sempre como texto "AAAA-MM-DD")
// ════════════════════════════════════════════════════════════════════════════
export const FUSO = "America/Sao_Paulo";
const DIAS_SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];

/** Hoje no fuso da fazenda, como "AAAA-MM-DD". */
export function hojeISO(agora: Date = new Date()): string {
  // en-CA formata como AAAA-MM-DD.
  return new Intl.DateTimeFormat("en-CA", { timeZone: FUSO, year: "numeric", month: "2-digit", day: "2-digit" }).format(agora);
}
function partes(iso: string): [number, number, number] | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}
/** "2026-10-21" → "21/10/2026" (ou "21/10" com curta). Texto vazio vira "—". */
export function fmtData(iso: string | null | undefined, curta = false): string {
  const p = iso ? partes(iso) : null;
  if (!p) return "—";
  const dd = String(p[2]).padStart(2, "0"), mm = String(p[1]).padStart(2, "0");
  return curta ? `${dd}/${mm}` : `${dd}/${mm}/${p[0]}`;
}
/** Dia da semana curto ("qua") de uma data ISO, sem depender do fuso do navegador. */
export function diaSemana(iso: string): string {
  const p = partes(iso);
  if (!p) return "";
  return DIAS_SEMANA[new Date(Date.UTC(p[0], p[1] - 1, p[2])).getUTCDay()];
}
/** Soma N dias a uma data ISO (aritmética em UTC: sem horário de verão no meio). */
export function somarDias(iso: string, n: number): string {
  const p = partes(iso);
  if (!p) return iso;
  const d = new Date(Date.UTC(p[0], p[1] - 1, p[2] + n));
  return d.toISOString().slice(0, 10);
}
/** b − a em dias (datas ISO). */
export function diferencaDias(a: string, b: string): number {
  const pa = partes(a), pb = partes(b);
  if (!pa || !pb) return 0;
  return Math.round((Date.UTC(pb[0], pb[1] - 1, pb[2]) - Date.UTC(pa[0], pa[1] - 1, pa[2])) / 86400000);
}
/** Data-hora ISO do servidor (UTC, com "Z") → "21/10 07:40" no fuso da fazenda. */
export function fmtDataHora(isoDt: string | null | undefined): string {
  if (!isoDt) return "—";
  const d = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(isoDt) ? isoDt : isoDt + "Z");
  if (Number.isNaN(d.getTime())) return isoDt;
  return new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
    .format(d).replace(",", "");
}
/** Idade em dias → "4 m" / "2 a 3 m". */
export function idadeTexto(dias: number | null | undefined): string {
  if (dias == null) return "—";
  const meses = Math.floor(dias / 30.44);
  if (meses < 24) return `${meses} m`;
  return `${Math.floor(meses / 12)} a ${meses % 12} m`;
}
/** Nome do dia como o back escreve: "Vacina · B19 · 25/12". */
export function tipoDoDia(caixas: { tipo?: string | null }[]): "Vacina" | "Exame" {
  return caixas.length && caixas.every((c) => c.tipo === "exame") ? "Exame" : "Vacina";
}

// ════════════════════════════════════════════════════════════════════════════
// Entradas (espelham schemas.py) — e as listas de chaves que cada uma aceita
// ════════════════════════════════════════════════════════════════════════════
export type AtestadoIn = {
  destinatario_tipo?: "orgao" | "laticinio" | "comprador" | "outro" | null; destinatario_texto?: string | null;
  pessoa_id?: number | null; fornecedor_id?: number | null; quando?: "aplicacao" | "nfe" | "primeiro"; dias?: number;
};
export type ComprovacaoIn = { dias?: number; aviso_dias?: number; push?: boolean; email?: boolean };
export type LeituraIn = { modo?: "so_resultado" | "diferenca" | "medidas"; horas?: number | null; tolerancia?: number | null };
export type SerieDoseIn = { dose: number; apos_dias: number; janela_dias?: number };

export type DefinicaoCaixa = {
  nome: string | null; nome_curto: string | null; tipo: TipoCaixa; obrigatoria: boolean;
  produto_modo: ProdutoModo; estoque_id: number | null; produto_texto: string | null; dose_valor: number | null;
  dose_unidade: DoseUnidade | null; dose_x_kg: number | null; peso_ausente: "exigir" | "estimado";
  pub_sexo: "F" | "M" | "ambos"; pub_cat_modo: "incluir" | "excluir"; categorias: number[];
  pub_idade_min_dias: number | null; pub_idade_max_dias: number | null; pub_condicoes: Condicao[];
  pub_hist_tipo: "ja" | "nunca" | null; pub_hist_caixa_id: number | null;
  jan_usa_evento: boolean; evento_tipo: EventoTipo | null; evento_de_dias: number | null; evento_ate_dias: number | null;
  jan_usa_periodo: boolean; periodo_modo: PeriodoModo | null; periodo_grupos: number[][]; periodo_anos: number | null;
  periodo_ano_base: number | null; data_base_dia: number; comecar_em: string | null; ao_fechar: AoFechar;
  serie: SerieDoseIn[];
  aglo_min: number; aviso_antecedencia_dias: number; aviso_fim_janela_dias: number | null; push_admin: boolean;
  legal_crmv_pedir: boolean; legal_atestado: AtestadoIn | null; legal_comprovacao: ComprovacaoIn | null;
  legal_leitura: LeituraIn | null; legal_reagente_aviso: boolean; legal_marca_texto: string | null;
  car_leite_dias: number | null; car_carne_dias: number | null; car_modo_leite: ModoLeite | null;
  ficha_colunas: ColunaFicha[]; observacao: string | null;
};
/** Definição do catálogo central: a da caixa + referências por nome/chave. */
export type DefinicaoCatalogo = DefinicaoCaixa & {
  categorias_ref: string[]; pub_hist_catalogo_chave: string | null; fallback_idade_min_dias: number | null;
};

export const CAMPOS_DEFINICAO = [
  "nome", "nome_curto", "tipo", "obrigatoria",
  "produto_modo", "estoque_id", "produto_texto", "dose_valor", "dose_unidade", "dose_x_kg", "peso_ausente",
  "pub_sexo", "pub_cat_modo", "categorias", "pub_idade_min_dias", "pub_idade_max_dias", "pub_condicoes",
  "pub_hist_tipo", "pub_hist_caixa_id",
  "jan_usa_evento", "evento_tipo", "evento_de_dias", "evento_ate_dias", "jan_usa_periodo", "periodo_modo",
  "periodo_grupos", "periodo_anos", "periodo_ano_base", "data_base_dia", "comecar_em", "ao_fechar", "serie",
  "aglo_min", "aviso_antecedencia_dias", "aviso_fim_janela_dias", "push_admin",
  "legal_crmv_pedir", "legal_atestado", "legal_comprovacao", "legal_leitura", "legal_reagente_aviso", "legal_marca_texto",
  "car_leite_dias", "car_carne_dias", "car_modo_leite",
  "ficha_colunas", "observacao",
] as const;
export const CAMPOS_CATALOGO_EXTRA = ["categorias_ref", "pub_hist_catalogo_chave", "fallback_idade_min_dias"] as const;
export const CAMPOS_ATESTADO = ["destinatario_tipo", "destinatario_texto", "pessoa_id", "fornecedor_id", "quando", "dias"] as const;
export const CAMPOS_COMPROVACAO = ["dias", "aviso_dias", "push", "email"] as const;
export const CAMPOS_LEITURA = ["modo", "horas", "tolerancia"] as const;
export const CAMPOS_SERIE = ["dose", "apos_dias", "janela_dias"] as const;
export const CAMPOS_PRODUTO = ["modo", "estoque_id", "lote_estoque_id", "texto", "dose_valor", "dose_unidade", "dose_x_kg"] as const;
export const CAMPOS_VETERINARIO = ["pessoa_id", "texto", "crmv"] as const;
export const CAMPOS_CONSENTIMENTO = ["animal_id", "caixa_id", "aceito", "motivo_exibido", "quer_atestado", "atestado_destinatario"] as const;
export const CAMPOS_DIA_CRIAR = ["caixa_ids", "data", "hora", "data_prevista", "veterinario", "produtos", "itens",
  "consentimentos", "decisao_riscos", "observacao"] as const;
export const CAMPOS_DIA_EDITAR = ["versao_lock", "data", "hora", "data_prevista", "veterinario", "produtos", "observacao",
  "decisao_riscos"] as const;
export const CAMPOS_REGISTRO = ["chave_idempotencia", "animal_id", "numero_animal", "caixa_id", "data", "hora", "dose_num",
  "produto", "peso_kg", "partida_texto", "fabricante", "validade", "aplicador_pessoa_id", "aplicador_texto",
  "veterinario_pessoa_id", "veterinario_texto", "crmv_texto", "resultado", "resultado_valor", "resultado_detalhe",
  "atestado_numero", "atestado_destinatario", "consentimento", "carencia"] as const;
export const CAMPOS_LANCAMENTO = ["caixa_id", "outro_texto", "data", "retroativo_motivo", "origem", "animal_ids", "numeros",
  "produto", "peso_kg", "aplicador_pessoa_id", "aplicador_texto", "veterinario_pessoa_id", "veterinario_texto",
  "crmv_texto", "atestado", "carencia", "resultados", "consentimentos", "chave_lote"] as const;
export const CAMPOS_PARAMETROS = ["uf", "prazos_legais_ativo", "antecedencia_padrao_dias", "corrigir_ate",
  "dose_externa_sem_data", "peso_estimado", "modo_tuberculina", "aviso_offline_horas"] as const;
export const CAMPOS_CARENCIA_DECISAO = ["modo", "leite_dias", "carne_dias"] as const;

export type ProdutoIn = {
  modo?: ProdutoModo | null; estoque_id?: number | null; lote_estoque_id?: number | null; texto?: string | null;
  dose_valor?: number | null; dose_unidade?: DoseUnidade | null; dose_x_kg?: number | null;
};
export type VeterinarioIn = { pessoa_id?: number | null; texto?: string | null; crmv?: string | null };
export type DiaItemIn = { animal_id: number; caixa_id?: number | null; caixa_ids?: number[] | null };
export type ConsentimentoIn = {
  animal_id: number; caixa_id?: number | null; aceito: boolean; motivo_exibido?: string | null;
  quer_atestado?: boolean | null; atestado_destinatario?: string | null;
};
export type DecisaoRiscos = { decisao: "manter" | "ajustar" | "dividir"; texto?: string | null };
export type CarenciaDecisaoIn = { modo?: ModoLeite | null; leite_dias?: number | null; carne_dias?: number | null };
export type DiaCriarIn = {
  caixa_ids: number[]; data: string; hora?: string | null; data_prevista?: string | null; veterinario?: VeterinarioIn | null;
  produtos?: Record<number, ProdutoIn>; itens?: DiaItemIn[] | null; consentimentos?: ConsentimentoIn[];
  decisao_riscos?: DecisaoRiscos | null; observacao?: string | null;
};
export type DiaEditarIn = {
  versao_lock: number; data?: string | null; hora?: string | null; data_prevista?: string | null;
  veterinario?: VeterinarioIn | null; produtos?: Record<number, ProdutoIn>; observacao?: string | null;
  decisao_riscos?: DecisaoRiscos | null;
};
export type RegistroIn = {
  chave_idempotencia?: string | null; animal_id?: number | null; numero_animal?: string | null; caixa_id?: number | null;
  data?: string | null; hora?: string | null; dose_num?: number | null; produto?: ProdutoIn | null; peso_kg?: number | null;
  partida_texto?: string | null; fabricante?: string | null; validade?: string | null;
  aplicador_pessoa_id?: number | null; aplicador_texto?: string | null; veterinario_pessoa_id?: number | null;
  veterinario_texto?: string | null; crmv_texto?: string | null; resultado?: Resultado | null;
  resultado_valor?: number | null; resultado_detalhe?: Record<string, unknown> | null; atestado_numero?: string | null;
  atestado_destinatario?: string | null;
  consentimento?: { aceito: boolean; motivo_exibido?: string | null; quer_atestado?: boolean | null; atestado_destinatario?: string | null } | null;
  carencia?: CarenciaDecisaoIn | null;
};
export type LancamentoSimplesIn = {
  caixa_id?: number | null; outro_texto?: string | null; data: string; retroativo_motivo?: string | null;
  origem?: "lancamento_simples" | "ficha"; animal_ids?: number[]; numeros?: string[]; produto?: ProdutoIn | null;
  peso_kg?: Record<number, number>; aplicador_pessoa_id?: number | null; aplicador_texto?: string | null;
  veterinario_pessoa_id?: number | null; veterinario_texto?: string | null; crmv_texto?: string | null;
  atestado?: { numero?: string | null; destinatario?: string | null } | null; carencia?: CarenciaDecisaoIn | null;
  resultados?: Record<number, Resultado>; consentimentos?: ConsentimentoIn[]; chave_lote?: string | null;
};
export type ParametrosIn = {
  uf?: string | null; prazos_legais_ativo?: boolean | null; antecedencia_padrao_dias?: number | null;
  corrigir_ate?: "fechar_dia" | null; dose_externa_sem_data?: "contar" | "nao_contar" | null;
  peso_estimado?: "aceitar" | "exigir" | null; modo_tuberculina?: "so_resultado" | "diferenca" | "medidas" | null;
  aviso_offline_horas?: number | null;
};

// ════════════════════════════════════════════════════════════════════════════
// Saídas (o que as rotas devolvem)
// ════════════════════════════════════════════════════════════════════════════
export type CaixaResumo = {
  id: number; nome: string; nome_curto: string | null; tipo: TipoCaixa; estado: "ativa" | "inativa" | "arquivada";
  obrigatoria: boolean; padrao_fabrica: boolean; versao_atual_id: number | null; versao_numero: number | null;
  vigente_desde: string | null; ativada_em: string | null; arquivada_em: string | null; arquivada_motivo: string | null;
  na_caixa: number; aglo_min: number | null; carencia_aceita: boolean;
  catalogo: { id: number; chave: string | null; versao: number | null; versao_central: number | null; nova_versao: boolean } | null;
};
export type CaixaDetalhe = CaixaResumo & {
  definicao: DefinicaoCaixa;
  versoes: { id: number; numero: number; vigente_desde: string; vigente_ate: string | null; criado_em: string | null }[];
  aceite_carencia: { modo_leite: ModoLeite | null; leite_dias: number | null; carne_dias: number | null;
    aceito_por_usuario_id: number | null; aceito_em: string } | null;
};
export type ErroEtapa = { etapa: number; campo: string; mensagem: string };
export type ValidacaoCaixa = { ok: boolean; erros: ErroEtapa[]; etapa: number | null };
export type LinhaPrevia = {
  animal_id: number; numero: string; categoria: string | null; estado: string; texto: string | null;
  motivos: { ok: boolean; texto: string }[]; motivo?: string;
};
export type PreviaCaixa = { data_base: string; entram: LinhaPrevia[]; fora: LinhaPrevia[]; contagem: { entram: number; fora: number } };
export type CatalogoItemFazenda = {
  id: number; chave: string; nome: string; tipo: TipoCaixa; versao_atual: number; versao_id: number | null;
  padrao_fabrica: boolean; uf_sugerida: string | null; nota_mudanca: string | null; base_legal: string | null;
  definicao: Partial<DefinicaoCatalogo> | null;
  caixas_da_fazenda: { caixa_id: number; estado: string; catalogo_versao: number | null; nova_versao: boolean }[];
  nova_versao: boolean;
};
export type Parametros = {
  uf: string | null; prazos_legais_ativo: boolean; antecedencia_padrao_dias: number; corrigir_ate: string;
  dose_externa_sem_data: "contar" | "nao_contar"; peso_estimado: "aceitar" | "exigir";
  modo_tuberculina: "so_resultado" | "diferenca" | "medidas"; aviso_offline_horas: number; atualizado_em: string | null;
};
export type Veterinarios = { pessoas: { pessoa_id: number; nome: string; crmv: string | null }[]; aceita_texto_livre: boolean };
export type EuSanitario = {
  usuario_id: number; administrador: boolean; veterinario_pessoa_id: number | null;
  pode: { cadastrar_caixa: boolean; aceitar_carencia: boolean; decidir_carencia: boolean; estornar: boolean;
    lancar: boolean; ler_exame: boolean; resolver_notas_admin: boolean };
};

export type DiaCaixa = {
  caixa_id: number; nome: string | null; nome_curto: string | null; tipo: TipoCaixa | null; caixa_versao_id: number | null;
  produto: { modo: ProdutoModo | null; estoque_id: number | null; texto: string | null; dose_valor: number | null;
    dose_unidade: DoseUnidade | null; dose_x_kg: number | null };
  carencia_decisao: { modo: ModoLeite | null; leite_dias: number | null; carne_dias: number | null } | null;
};
export type DiaItem = {
  id: number; animal_id: number; numero: string | null; caixa_id: number; origem: "janela" | "manual" | "curral" | string;
  estado: "pendente" | "feito" | "faltou" | "dispensado" | "removido" | string; consentimento_log_id: number | null;
  registro_id: number | null;
};
export type Dia = {
  id: number; nome: string; tipo: "vacina" | "exame"; data: string; hora: string | null; data_prevista: string | null;
  estado: "marcado" | "em_execucao" | "fechado" | "cancelado"; veterinario: VeterinarioIn; observacao: string | null;
  decisao_riscos: DecisaoRiscos | null; versao_lock: number; fechado_em: string | null; fechamento_auto: boolean;
  motivo_cancelamento: string | null; caixas: DiaCaixa[];
  contagens: { animais: number; pendentes: number; feitos: number; registros_apos_fechamento: number };
  itens?: DiaItem[]; avisos?: Aviso[]; fechamento?: { faltantes: number[]; destino: string };
};
export type Aviso = { codigo: string; texto: string; animal_id?: number; caixa_id?: number };
export type Risco = { kind: string; animal_ids: number[]; numeros: string[]; caixa_ids: number[]; data: string | null; texto: string };
export type Simulacao = {
  data: string; data_prevista: string; riscos: Risco[];
  entram: { animal_id: number; numero: string; caixa_ids: number[] }[];
  animais: { animal_id: number; numero: string; caixa_ids: number[] }[];
};
/** Item pendente de consentimento (409 consentimento_necessario do marcar/adicionar). */
export type ItemForaRegra = { animal_id: number; numero: string; caixa_id: number; caixa: string; motivo: string; kind: string };
export type ItemRegistro = {
  indice: number; status: "gravado" | "duplicado" | "pendente" | "conflito" | "erro"; registro_id: number | null;
  animal_id: number | null; numero: string | null; caixa_id: number | null; avisos: Aviso[];
  requer: ("consentimento" | "carencia_decisao")[]; motivo_fora?: string; pergunta_atestado?: boolean;
  motivo_carencia?: string; carencia_sugerida?: { leite_dias: number | null; carne_dias: number | null; modo: ModoLeite | null };
  chave_idempotencia?: string | null; conflito_log_id?: number;
  carencia?: { modo: string | null; leite_ate: string | null; carne_ate: string | null };
};
export type ResultadoRegistro = {
  itens: ItemRegistro[]; gravados: number; duplicados: number; pendentes: number; conflitos: number; erros: number;
  registro_ids: number[]; desfazer_ate: string | null;
};
export type Registro = {
  id: number; data: string | null; hora: string | null; animal_id: number | null; numero: string | null;
  caixa_id: number | null; caixa: string | null; tipo: TipoCaixa | "outro"; outro_texto: string | null;
  ciclo_chave: string | null; dose_num: number | null; dia_id: number | null; origem: string; canal: string | null;
  so_registro: boolean; decisao_curral: boolean; apos_fechamento: boolean; retroativo: boolean;
  retroativo_motivo: string | null; fora_da_regra: boolean; produto_modo: string | null; estoque_id: number | null;
  produto_texto: string | null; dose_valor: number | null; dose_unidade: string | null; quantidade_baixada: number | null;
  custo: number | null; peso_usado: number | null; peso_estimado: boolean | null; partida_texto: string | null;
  fabricante: string | null; validade: string | null; lote_estoque_id: number | null; dia_item_id: number | null;
  carencia_aceite_id: number | null; aplicador_pessoa_id: number | null; aplicador_texto: string | null;
  veterinario_pessoa_id: number | null; veterinario_texto: string | null; crmv_texto: string | null;
  resultado: Resultado | null; resultado_valor: number | null; resultado_detalhe: Record<string, unknown> | null;
  leitura_em: string | null; carencia_leite_ate: string | null; carencia_carne_ate: string | null;
  carencia_modo: string | null; atestado_numero: string | null; atestado_destinatario: string | null;
  numero_lancamento_vinculado: string | null; estado: "valido" | "estornado" | string; estornado_motivo: string | null;
  criado_em: string | null;
};
export type LogItem = {
  id: number; tipo: string; dia_id: number | null; caixa_id: number | null; animal_id: number | null;
  registro_id: number | null; motivo_exibido: string | null; decisao: string | null; texto: string | null;
  payload: Record<string, unknown> | null; usuario_id: number | null; dispositivo_id: number | null; em: string | null;
};
export type Prazo = {
  id: number; tipo: "atestado" | "comprovacao" | string; caixa_id: number | null; caixa: string | null;
  referencia: string | null; registro_ids: number[]; vence_em: string; destinatario: string | null; estado: string;
  cumprido_em: string | null; documento_numero: string | null;
};
export type ResumoPrevistas = { animais: number; caixas: number; dias: number; periodo_dias: number; link?: string };
export type Painel = {
  parametros: { dias: number; hoje: string; antecedencia_padrao_dias: number; aviso_offline_horas: number; modo_tuberculina: string };
  resumo: ResumoPrevistas;
  cobertura: { caixa_id: number; caixa: string; aplicados: number; devidos: number; pct: number | null }[];
  aglomeradas: { caixa_id: number; caixa: string; animais: number; minimo: number | null }[];
  proximos_7_dias: Dia[];
  atrasadas: { caixa_id: number; caixa: string; animais: number; animal_ids: number[] }[];
  em_carencia: { animais: number; leite: number; carne: number };
  consumo: { estoque_id: number; produto: string | null; unidade: string | null; necessario: number; saldo: number | null;
    sem_peso: number; falta: number; caixas: string[] }[];
  prazos: Prazo[]; custo_periodo: number; carencia_sem_aceite: number[];
};
export type JanelaItem = {
  animal_id: number; numero: string | null; lote: string | null; categoria: string | null; estado: EstadoSituacao;
  texto: string | null; ciclo_chave: string | null; dose_num: number | null; janela_inicio: string | null;
  janela_fim: string | null; data_base: string | null; dia_id: number | null; porque: { ok: boolean; texto: string }[];
};
export type JanelaCaixa = { caixa_id: number; caixa: string; tipo: TipoCaixa; minimo: number | null; animais: number; itens: JanelaItem[] };
export type Calendario = {
  ano: number; nota: string;
  meses: { mes: number; previstos_total: number; aplicados_total: number;
    previstos: { caixa_id: number; caixa: string; animais: number }[];
    aplicados: { caixa_id: number; caixa: string; animais: number }[];
    dias: { id: number; data: string; estado: string }[] }[];
};
export type NotaAgenda = {
  id: number; tipo: string; titulo: string; texto: string | null; dados: Record<string, unknown> | null;
  caixa_id: number | null; ciclo_chave: string | null; dia_id: number | null; so_admin: boolean;
  data_ref: string | null; resolvida_em: string | null; push_enviado_em: string | null;
};
export type LeiteSeparadoItem = {
  origem: "preventivo" | "curativo"; numero: string | null; animal_id: number | null; produto: string | null;
  caixa: string | null; data_aplicacao: string; liberacao_leite: string; modo: ModoLeite | string;
  registro_id?: number; sanidade_id?: number;
};
export type LeiteSeparado = { hoje: string; animais: number; itens: LeiteSeparadoItem[] };
export type SituacaoCaixaAnimal = {
  caixa_id: number; caixa: string; estado: string; texto: string | null; ciclo: string | null; dose: number | null;
  janela_inicio: string | null; janela_fim: string | null; motivos: { ok: boolean; texto: string }[];
};
export type ColunaFichaOut = { chave: string; rotulo: string };
export type FichaDia = {
  tipo: "pre_preenchida"; fazenda: string | null; titulo: string; data: string; hora: string | null; veterinario: VeterinarioIn;
  caixas: { caixa_id: number; nome_curto: string | null; produto: DiaCaixa["produto"] }[];
  colunas: ColunaFichaOut[];
  linhas: { animal_id: number; brinco: string; categoria: string | null; lote: string | null; idade: string | null;
    peso: number | null; caixas: number[] }[];
  linhas_em_branco: number; lembretes: string[]; rodape: string;
};
export type FichaVazia = {
  tipo: "vazia"; fazenda: string | null; titulo: string; caixa_ids: number[]; colunas: ColunaFichaOut[];
  linhas_em_branco: number; campos_cabecalho: string[];
};
export type PacoteOffline = {
  gerado_em: string; data_referencia: string; dia: Dia;
  caixas: { caixa_id: number; nome: string; nome_curto: string; tipo: TipoCaixa; produto: Record<string, unknown>;
    regras: Record<string, unknown> }[];
  estoques: { id: number; nome: string; unidade: string | null; saldo: number | null }[];
  veterinarios: { pessoa_id: number; nome: string; crmv: string | null }[];
  animais: { animal_id: number; brinco: string; categoria?: string | null; lote?: string | null; idade?: string | null;
    peso?: number | null; caixas: Record<string, { elegivel: boolean; motivo: string | null; kind: string | null }> }[];
  regras_aviso: { consentimento_fora_da_regra: boolean; desfazer_segundos: number; aviso_offline_horas: number;
    texto_consentimento: string };
};
export type CampoHoje = { hoje: string; dias: (Dia & { quando: "hoje" | "amanha" })[] };
export type Dispositivo = {
  id: number; dispositivo_uid: string; nome: string | null; usuario_id: number | null; ultimo_contato_em: string | null;
  fila_pendentes: number; fila_mais_antigo_em: string | null; aviso_admin_em: string | null;
};
export type SincronizarOut = {
  dispositivo_id: number; gravados: number; duplicados: number; pendentes: number; conflitos: number; erros: number;
  itens: (ItemRegistro | null)[];
};
export type ModeloPlanilha = { colunas: string[]; exemplo: string[]; nota: string };
export type ImportacaoPlanilha = ResultadoRegistro & { erros_planilha: string[]; linhas: number };
export type CatalogoCentralItem = {
  id: number; chave: string; nome: string; tipo: TipoCaixa; versao_atual: number; padrao_fabrica: boolean; ativo: boolean;
  uf_sugerida: string | null; versao_id: number | null; definicao: Partial<DefinicaoCatalogo> | null;
  nota_mudanca: string | null; base_legal: string | null; fazendas_com_copia: number; copias_desatualizadas: number;
  versoes?: { id: number; versao: number; nota_mudanca: string | null; base_legal: string | null; publicado_em: string | null }[];
};

// ════════════════════════════════════════════════════════════════════════════
// Serializadores (o que sai do front tem só as chaves que o back conhece)
// ════════════════════════════════════════════════════════════════════════════
type Obj = Record<string, unknown>;

/** Copia só as chaves listadas que estão DEFINIDAS (undefined some; null fica). */
export function escolher(obj: Obj | null | undefined, chaves: readonly string[]): Obj {
  const out: Obj = {};
  if (!obj) return out;
  for (const k of chaves) if (obj[k] !== undefined) out[k] = obj[k];
  return out;
}
/** "" / null / undefined / texto não numérico → null; "2,5" → 2.5. */
export function numOuNulo(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const s = String(v).trim().replace(",", ".");
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}
export function intOuNulo(v: unknown): number | null {
  const n = numOuNulo(v);
  return n === null ? null : Math.trunc(n);
}
/** Texto aparado; vazio vira null. */
export function textoOuNulo(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  return s ? s : null;
}

const NUM_DEF = ["estoque_id", "dose_valor", "dose_x_kg", "pub_idade_min_dias", "pub_idade_max_dias", "pub_hist_caixa_id",
  "evento_de_dias", "evento_ate_dias", "periodo_anos", "periodo_ano_base", "aviso_fim_janela_dias", "car_leite_dias",
  "car_carne_dias", "fallback_idade_min_dias"];
const INT_DEF = new Set(["estoque_id", "pub_idade_min_dias", "pub_idade_max_dias", "pub_hist_caixa_id", "evento_de_dias",
  "evento_ate_dias", "periodo_anos", "periodo_ano_base", "aviso_fim_janela_dias", "car_leite_dias", "car_carne_dias",
  "fallback_idade_min_dias"]);
const TXT_DEF = ["nome", "nome_curto", "produto_texto", "legal_marca_texto", "observacao", "comecar_em", "pub_hist_catalogo_chave"];

/**
 * Definição da caixa (wizard) → `CaixaDefinicaoIn` (ou `CatalogoDefinicaoIn`
 * com `catalogo: true`). Aceita o objeto que o GET devolveu (mesmo formato) e
 * descarta chaves que o schema não conhece.
 */
export function definicaoParaEnvio(d: Partial<DefinicaoCatalogo> & Obj, opts: { catalogo?: boolean } = {}): Obj {
  const chaves: string[] = [...CAMPOS_DEFINICAO, ...(opts.catalogo ? CAMPOS_CATALOGO_EXTRA : [])];
  const out = escolher(d, chaves);
  for (const k of NUM_DEF) if (k in out) out[k] = INT_DEF.has(k) ? intOuNulo(out[k]) : numOuNulo(out[k]);
  for (const k of ["aglo_min", "aviso_antecedencia_dias", "data_base_dia"]) {
    if (k in out) { const n = intOuNulo(out[k]); if (n === null) delete out[k]; else out[k] = n; }
  }
  for (const k of TXT_DEF) if (k in out) out[k] = textoOuNulo(out[k]);
  if ("categorias" in out) out.categorias = ((out.categorias as unknown[]) || []).map((c) => Number(c)).filter(Number.isFinite);
  if ("periodo_grupos" in out) {
    out.periodo_grupos = ((out.periodo_grupos as unknown[]) || [])
      .map((g) => (Array.isArray(g) ? g.map(Number).filter((m) => Number.isInteger(m)) : []))
      .filter((g) => g.length);
  }
  if ("serie" in out) out.serie = ((out.serie as Obj[]) || []).map((s) => escolher(s, CAMPOS_SERIE));
  if ("legal_atestado" in out) out.legal_atestado = out.legal_atestado ? escolher(out.legal_atestado as Obj, CAMPOS_ATESTADO) : null;
  if ("legal_comprovacao" in out) out.legal_comprovacao = out.legal_comprovacao ? escolher(out.legal_comprovacao as Obj, CAMPOS_COMPROVACAO) : null;
  if ("legal_leitura" in out) out.legal_leitura = out.legal_leitura ? escolher(out.legal_leitura as Obj, CAMPOS_LEITURA) : null;
  if (out.dose_unidade === "") out.dose_unidade = null;
  if (out.car_modo_leite === "") out.car_modo_leite = null;
  if (out.evento_tipo === "") out.evento_tipo = null;
  if (out.periodo_modo === "") out.periodo_modo = null;
  if (out.pub_hist_tipo === "") out.pub_hist_tipo = null;
  if (!out.pub_hist_tipo) out.pub_hist_caixa_id = null;
  return out;
}

/** Definição em branco (o "criar do zero" do wizard). */
export function definicaoVazia(tipo: TipoCaixa = "vacina"): DefinicaoCaixa {
  return {
    nome: "", nome_curto: "", tipo, obrigatoria: false,
    produto_modo: tipo === "exame" ? "nao_se_aplica" : "vazio", estoque_id: null, produto_texto: null, dose_valor: null,
    dose_unidade: tipo === "exame" ? null : "mL", dose_x_kg: null, peso_ausente: "estimado",
    pub_sexo: "ambos", pub_cat_modo: "incluir", categorias: [], pub_idade_min_dias: null, pub_idade_max_dias: null,
    pub_condicoes: [], pub_hist_tipo: null, pub_hist_caixa_id: null,
    jan_usa_evento: false, evento_tipo: null, evento_de_dias: null, evento_ate_dias: null,
    jan_usa_periodo: true, periodo_modo: "meses", periodo_grupos: [], periodo_anos: null, periodo_ano_base: null,
    data_base_dia: 15, comecar_em: null, ao_fechar: "manter", serie: [],
    aglo_min: 4, aviso_antecedencia_dias: 30, aviso_fim_janela_dias: null, push_admin: true,
    legal_crmv_pedir: false, legal_atestado: null, legal_comprovacao: null, legal_leitura: null,
    legal_reagente_aviso: false, legal_marca_texto: null,
    car_leite_dias: null, car_carne_dias: null, car_modo_leite: null,
    ficha_colunas: ["brinco", "categoria", "dose", "aplicado", "obs"], observacao: null,
  };
}

/** Completa uma definição vinda do back (ou do catálogo) com os padrões que faltarem. */
export function definicaoCompleta(d: Partial<DefinicaoCatalogo> | null | undefined): DefinicaoCaixa {
  const base = definicaoVazia((d?.tipo as TipoCaixa) || "vacina");
  const out = { ...base } as Obj;
  for (const k of CAMPOS_DEFINICAO) {
    const v = (d as Obj | null | undefined)?.[k];
    if (v !== undefined) out[k] = v;
  }
  return out as DefinicaoCaixa;
}

export function produtoParaEnvio(p: ProdutoIn | Obj | null | undefined): Obj | null {
  if (!p) return null;
  const out = escolher(p as Obj, CAMPOS_PRODUTO);
  for (const k of ["estoque_id", "lote_estoque_id"]) if (k in out) out[k] = intOuNulo(out[k]);
  for (const k of ["dose_valor", "dose_x_kg"]) if (k in out) out[k] = numOuNulo(out[k]);
  if ("texto" in out) out.texto = textoOuNulo(out.texto);
  if (out.dose_unidade === "") out.dose_unidade = null;
  return out;
}

/** Veterinário escolhido na tela → `VeterinarioIn` (ou null quando nada foi informado). */
export function veterinarioParaEnvio(v: { pessoa_id?: number | string | null; texto?: string | null; crmv?: string | null } | null | undefined): VeterinarioIn | null {
  if (!v) return null;
  const pessoa = intOuNulo(v.pessoa_id);
  const texto = textoOuNulo(v.texto), crmv = textoOuNulo(v.crmv);
  if (pessoa) return { pessoa_id: pessoa, ...(crmv ? { crmv } : {}) };
  if (texto || crmv) return { texto, crmv };
  return null;
}

export function consentimentoParaEnvio(c: ConsentimentoIn): Obj {
  return escolher(c as unknown as Obj, CAMPOS_CONSENTIMENTO);
}

export function diaCriarParaEnvio(d: DiaCriarIn): Obj {
  const out = escolher(d as unknown as Obj, CAMPOS_DIA_CRIAR);
  out.caixa_ids = (d.caixa_ids || []).map(Number);
  out.hora = textoOuNulo(d.hora);
  out.observacao = textoOuNulo(d.observacao);
  if (d.veterinario !== undefined) out.veterinario = veterinarioParaEnvio(d.veterinario);
  out.produtos = produtosParaEnvio(d.produtos);
  if (d.itens) out.itens = d.itens.map((i) => escolher(i as unknown as Obj, ["animal_id", "caixa_id", "caixa_ids"]));
  out.consentimentos = (d.consentimentos || []).map(consentimentoParaEnvio);
  if (d.decisao_riscos) out.decisao_riscos = escolher(d.decisao_riscos as unknown as Obj, ["decisao", "texto"]);
  return out;
}

export function diaEditarParaEnvio(d: DiaEditarIn): Obj {
  const out = escolher(d as unknown as Obj, CAMPOS_DIA_EDITAR);
  if ("hora" in out) out.hora = textoOuNulo(out.hora);
  if ("observacao" in out) out.observacao = textoOuNulo(out.observacao);
  if (d.veterinario !== undefined) out.veterinario = veterinarioParaEnvio(d.veterinario);
  if (d.produtos) out.produtos = produtosParaEnvio(d.produtos);
  if (d.decisao_riscos) out.decisao_riscos = escolher(d.decisao_riscos as unknown as Obj, ["decisao", "texto"]);
  return out;
}

function produtosParaEnvio(p: Record<number, ProdutoIn> | undefined): Record<string, Obj> {
  const out: Record<string, Obj> = {};
  for (const [k, v] of Object.entries(p || {})) {
    const prod = produtoParaEnvio(v);
    if (prod && Object.keys(prod).length) out[String(Number(k))] = prod;
  }
  return out;
}

export function carenciaParaEnvio(c: CarenciaDecisaoIn | null | undefined): Obj | null {
  if (!c) return null;
  const out = escolher(c as unknown as Obj, CAMPOS_CARENCIA_DECISAO);
  for (const k of ["leite_dias", "carne_dias"]) if (k in out) out[k] = intOuNulo(out[k]);
  return out;
}

export function registroParaEnvio(r: RegistroIn): Obj {
  const out = escolher(r as unknown as Obj, CAMPOS_REGISTRO);
  if (r.produto !== undefined) out.produto = produtoParaEnvio(r.produto);
  if (r.carencia !== undefined) out.carencia = carenciaParaEnvio(r.carencia);
  if (r.consentimento) out.consentimento = escolher(r.consentimento as Obj, ["aceito", "motivo_exibido", "quer_atestado", "atestado_destinatario"]);
  for (const k of ["peso_kg", "resultado_valor"]) if (k in out) out[k] = numOuNulo(out[k]);
  return out;
}

export function lancamentoParaEnvio(l: LancamentoSimplesIn): Obj {
  const out = escolher(l as unknown as Obj, CAMPOS_LANCAMENTO);
  out.outro_texto = textoOuNulo(l.outro_texto);
  out.retroativo_motivo = textoOuNulo(l.retroativo_motivo);
  out.aplicador_texto = textoOuNulo(l.aplicador_texto);
  out.veterinario_texto = textoOuNulo(l.veterinario_texto);
  out.crmv_texto = textoOuNulo(l.crmv_texto);
  if (l.produto !== undefined) out.produto = produtoParaEnvio(l.produto);
  if (l.carencia !== undefined) out.carencia = carenciaParaEnvio(l.carencia);
  if (l.atestado) {
    const at = { numero: textoOuNulo(l.atestado.numero), destinatario: textoOuNulo(l.atestado.destinatario) };
    out.atestado = at.numero || at.destinatario ? at : null;
  }
  out.animal_ids = (l.animal_ids || []).map(Number);
  out.numeros = (l.numeros || []).map((n) => String(n).trim()).filter(Boolean);
  out.consentimentos = (l.consentimentos || []).map(consentimentoParaEnvio);
  return out;
}

export function parametrosParaEnvio(p: Partial<Parametros> | ParametrosIn): Obj {
  const out = escolher(p as Obj, CAMPOS_PARAMETROS);
  if ("uf" in out) out.uf = textoOuNulo(out.uf)?.toUpperCase() ?? null;
  for (const k of ["antecedencia_padrao_dias", "aviso_offline_horas"]) if (k in out) out[k] = intOuNulo(out[k]);
  return out;
}

// ── leitura de erros estruturados (409 / 422) ──
/** Código do 409 de decisão (`consentimento_necessario`, `decisao_riscos_necessaria`, `versao_desatualizada`...). */
export function codigoDoDetalhe(detalhe: unknown): string | null {
  if (detalhe && typeof detalhe === "object" && "codigo" in (detalhe as Obj)) return String((detalhe as Obj).codigo);
  if (detalhe && typeof detalhe === "object" && "erro" in (detalhe as Obj)) return String((detalhe as Obj).erro);
  return null;
}
/** Erros por etapa do 422 `{"codigo": "validacao", "erros": [...]}` do salvar caixa. */
export function errosDoDetalhe(detalhe: unknown): ErroEtapa[] {
  if (detalhe && typeof detalhe === "object" && Array.isArray((detalhe as Obj).erros)) return (detalhe as { erros: ErroEtapa[] }).erros;
  return [];
}

// ── textos que várias telas repetem ──
export function textoProduto(p: { modo?: string | null; texto?: string | null; dose_valor?: number | null;
  dose_unidade?: string | null; dose_x_kg?: number | null } | null | undefined, nomeEstoque?: string | null): string {
  if (!p || !p.modo || p.modo === "vazio") return "produto a escolher no dia";
  if (p.modo === "nao_se_aplica") return "sem produto";
  const nome = p.modo === "estoque" ? (nomeEstoque || "item do estoque") : (p.texto || "produto sem estoque");
  return `${nome}${p.modo === "sem_estoque" ? " (sem estoque)" : ""}${textoDose(p) ? " · " + textoDose(p) : ""}`;
}
export function textoDose(p: { dose_valor?: number | null; dose_unidade?: string | null; dose_x_kg?: number | null } | null | undefined): string {
  if (!p || p.dose_valor == null) return "";
  const v = String(p.dose_valor).replace(".", ",");
  if (p.dose_unidade === "mL_por_x_kg") return `${v} mL por ${p.dose_x_kg ?? "X"} kg`;
  if (p.dose_unidade === "mL_por_kg") return `${v} mL por kg`;
  return `${v} ${p.dose_unidade || ""}`.trim();
}
export function textoPublico(d: Partial<DefinicaoCaixa>, nomesCategorias?: Map<number, string>): string {
  const partesTxt: string[] = [];
  partesTxt.push(d.pub_sexo === "F" ? "fêmeas" : d.pub_sexo === "M" ? "machos" : "machos e fêmeas");
  if (d.categorias?.length) {
    const nomes = d.categorias.map((c) => nomesCategorias?.get(c) || `#${c}`).join(", ");
    partesTxt.push(`${d.pub_cat_modo === "excluir" ? "exceto " : ""}${nomes}`);
  }
  if (d.pub_idade_min_dias != null || d.pub_idade_max_dias != null) {
    const mi = d.pub_idade_min_dias != null ? `${Math.round(d.pub_idade_min_dias / 30)} m` : "0";
    const ma = d.pub_idade_max_dias != null ? `${Math.round(d.pub_idade_max_dias / 30)} m` : "sem limite";
    partesTxt.push(`idade ${mi} a ${ma}`);
  }
  if (d.pub_condicoes?.length) partesTxt.push(d.pub_condicoes.map((c) => ROTULO_CONDICAO[c] || c).join(", ").toLowerCase());
  return partesTxt.join(" · ");
}
export function textoJanela(d: Partial<DefinicaoCaixa>): string {
  const p: string[] = [];
  if (d.jan_usa_evento && d.evento_tipo) {
    const ev = ROTULO_EVENTO[d.evento_tipo]?.split(" (")[0] || d.evento_tipo;
    if (d.evento_tipo === "idade" && d.evento_de_dias != null && d.evento_ate_dias != null) {
      p.push(`idade de ${Math.round(d.evento_de_dias / 30)} a ${Math.round(d.evento_ate_dias / 30)} meses`);
    } else if (d.evento_tipo === "pre_parto" && d.evento_de_dias != null) {
      p.push(`pré-parto: de ${Math.abs(d.evento_de_dias)} dias antes até o parto`);
    } else {
      p.push(`${ev.toLowerCase()}: dia ${d.evento_de_dias ?? "?"} a ${d.evento_ate_dias ?? "?"}`);
    }
  }
  if (d.jan_usa_periodo && d.periodo_modo) {
    if (d.periodo_modo === "continuo") p.push("contínuo (todo mês)");
    else {
      const grupos = (d.periodo_grupos || []).map((g) => g.map((m) => MESES_CURTOS[m] || m).join("/")).join(", ");
      p.push(d.periodo_modo === "frequencia"
        ? `a cada ${d.periodo_anos ?? "?"} anos${d.periodo_ano_base ? ` desde ${d.periodo_ano_base}` : ""}${grupos ? ` em ${grupos}` : ""}`
        : grupos ? `meses ${grupos}` : "meses a escolher");
    }
  }
  if (d.comecar_em) p.push(`começa em ${fmtData(d.comecar_em)}`);
  return p.join(" · ") || "janela não definida";
}

/** Chave de idempotência (uuid v4 quando o navegador tem; senão um equivalente). */
export function novaChave(prefixo = "san"): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  const id = c?.randomUUID ? c.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `${prefixo}:${id}`;
}

/**
 * Item do estoque que pode ir num cadastro/lançamento preventivo: só o que é
 * da Farmácia (medicamento, vacina, vermífugo, exame/tuberculina), nunca
 * ração/material/equipamento/sêmen. Mesmo critério de `_eh_medicamento` no
 * back (routers/estoque.py), mais a categoria de compra:
 *   - finalidade preenchida decide sozinha ("Medicamento" entra, o resto sai);
 *   - vínculo de farmácia (princípio ativo, classificação, categoria de medicamento) entra;
 *   - categoria "Medicamentos e produtos veterinários" entra; outra categoria sai;
 *   - item sem nenhuma classificação só entra se o nome diz o que é (vacina, vermífugo, tuberculina…).
 */
export type ItemEstoqueClassificavel = {
  nome?: string | null; finalidade?: string | null; categoria?: string | null; classificacao_medicamento?: string | null;
  principio_ativo?: string | null; principio_ativo_id?: number | null; medicamento_comercial_id?: number | null;
  categoria_medicamento_ids?: number[] | null; categoria_alimento_id?: number | null;
};
const semAcento = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
export function ehItemFarmacia(i: ItemEstoqueClassificavel): boolean {
  const fin = semAcento(i.finalidade || "");
  if (fin) return fin === "medicamento";
  if (i.categoria_alimento_id != null) return false;
  if ((i.classificacao_medicamento || "").trim() || (i.principio_ativo || "").trim() || i.principio_ativo_id != null
    || i.medicamento_comercial_id != null || (i.categoria_medicamento_ids || []).length) return true;
  const cat = semAcento(i.categoria || "");
  if (cat) return cat.includes("medicament") || cat.includes("produtos veterinarios") || cat.includes("farmacia");
  return /\b(vacina|vermifug|tuberculin|antigeno|medicament|brucel)/.test(semAcento(i.nome || ""));
}
