// App de campo do Sanitário Preventivo v2 — regras PURAS (sem React, sem rede,
// sem localStorage), para rodar no `node --test` e ser reaproveitadas pelas
// telas de components/mobile/vacinacao/ e pela fila (lib/filaSanitario.ts).
//
// Contratos (o código do back é a verdade):
//   - POST /sanitario/campo/sincronizar recebe `RegistroSyncIn` (= RegistroIn +
//     dia_id + outro_texto, `extra="forbid"`) e responde POR REGISTRO:
//     gravado | duplicado | conflito | pendente | erro (rules/sanitario/registro.py).
//   - "pendente" = NÃO gravou: falta consentimento (fora da regra) ou a decisão
//     de carência (só para administrador). O registro continua na fila do
//     aparelho até a pessoa decidir.
//   - "conflito" = outro aparelho já registrou o mesmo animal × caixa × ciclo;
//     o servidor guarda o que chegou no log e o aplicador/admin decide em
//     /sanitario/conflitos/{log_id}/decidir. Sai da fila do aparelho.
import {
  CAMPOS_REGISTRO, registroParaEnvio, textoOuNulo, textoProduto, FUSO,
  type CarenciaDecisaoIn, type ConsentimentoIn, type DiaItem, type ItemRegistro, type LancamentoSimplesIn,
  type PacoteOffline, type ProdutoIn, type RegistroIn, type SincronizarOut,
} from "./sanitarioTipos.ts";

type Obj = Record<string, unknown>;

// ════════════════════════════════════════════════════════════════════════════
// Registro que vai pela fila (RegistroSyncIn)
// ════════════════════════════════════════════════════════════════════════════
export type RegistroCampo = RegistroIn & { dia_id?: number | null; outro_texto?: string | null };
/** Chaves de `RegistroSyncIn` (schemas.py) — o teste confere com o back. */
export const CAMPOS_REGISTRO_SYNC = [...CAMPOS_REGISTRO, "dia_id", "outro_texto"] as const;
export const CAMPOS_SINCRONIZAR = ["dispositivo_uid", "nome", "registros", "fila_pendentes_restantes"] as const;
export const CAMPOS_HEARTBEAT = ["dispositivo_uid", "nome", "fila_pendentes", "fila_mais_antigo_em"] as const;

export function registroSyncParaEnvio(r: RegistroCampo): Obj {
  return { ...registroParaEnvio(r), dia_id: r.dia_id ?? null, outro_texto: textoOuNulo(r.outro_texto) };
}

export function corpoSincronizar(dispositivoUid: string, nome: string | null, registros: RegistroCampo[], restantes: number): Obj {
  return {
    dispositivo_uid: dispositivoUid, nome: nome || null, fila_pendentes_restantes: Math.max(0, restantes | 0),
    registros: registros.map(registroSyncParaEnvio),
  };
}

export function corpoHeartbeat(dispositivoUid: string, nome: string | null, pendentes: number, maisAntigoEm: string | null): Obj {
  return { dispositivo_uid: dispositivoUid, nome: nome || null, fila_pendentes: Math.max(0, pendentes | 0),
    fila_mais_antigo_em: pendentes > 0 ? maisAntigoEm : null };
}

// ════════════════════════════════════════════════════════════════════════════
// Item da fila do aparelho (corpo do item tipo "sanitario" do outbox)
// ════════════════════════════════════════════════════════════════════════════
/** fila = espera envio; requer = o servidor pediu uma decisão (consentimento /
 *  carência); erro = o servidor recusou (dado inválido) — a pessoa corrige ou descarta. */
export type EstadoItemSan = "fila" | "requer" | "erro";
export type CorpoSan = {
  v: 1;
  registro: RegistroCampo;
  numero: string;
  caixa: string;
  dia_nome: string | null;
  estado: EstadoItemSan;
  requer?: ("consentimento" | "carencia_decisao")[];
  motivo?: string | null;
  pergunta_atestado?: boolean;
  carencia_sugerida?: CarenciaDecisaoIn | null;
};
export type StatusSan = ItemRegistro["status"];
/** Resultado de um registro na última sincronização (mostrado na tela). */
export type ResultadoSan = {
  chave: string; status: StatusSan; numero: string; caixa: string; dia_id: number | null;
  registro_id: number | null; conflito_log_id: number | null; texto: string; em: string;
};
export type AcaoFila =
  | { id: string; tipo: "remover" }
  | { id: string; tipo: "atualizar"; corpo: CorpoSan; erro: string | null };

export const ROTULO_STATUS_SAN: Record<StatusSan, string> = {
  gravado: "Gravado", duplicado: "Já estava gravado", conflito: "Conflito", pendente: "Precisa de decisão", erro: "Erro",
};

function textoAvisos(it: ItemRegistro | null | undefined): string {
  return (it?.avisos || []).map((a) => a.texto).filter(Boolean).join(" ");
}

/** Traduz a resposta do POST /campo/sincronizar em ações sobre a fila do
 *  aparelho (remover / manter com decisão) e em resultados para a tela.
 *  `enviados[i]` corresponde a `resp.itens[i]` (o back devolve `indice`). */
export function interpretarSync(enviados: { id: string; corpo: CorpoSan }[], resp: SincronizarOut, agoraIso: string):
  { acoes: AcaoFila[]; resultados: ResultadoSan[] } {
  const porIndice = new Map<number, ItemRegistro>();
  (resp.itens || []).forEach((it, i) => { if (it) porIndice.set(typeof it.indice === "number" ? it.indice : i, it); });
  const acoes: AcaoFila[] = [];
  const resultados: ResultadoSan[] = [];
  enviados.forEach(({ id, corpo }, i) => {
    const it = porIndice.get(i);
    const base = {
      chave: corpo.registro.chave_idempotencia || id, numero: corpo.numero, caixa: corpo.caixa,
      dia_id: corpo.registro.dia_id ?? null, em: agoraIso,
    };
    if (!it) {
      // Sem resposta para este índice (não deveria acontecer): continua na fila.
      return;
    }
    const avisos = textoAvisos(it);
    if (it.status === "gravado" || it.status === "duplicado") {
      acoes.push({ id, tipo: "remover" });
      resultados.push({ ...base, status: it.status, registro_id: it.registro_id ?? null, conflito_log_id: null,
        texto: it.status === "duplicado" ? `Já estava gravado (reenvio sem duplicar).${avisos ? " " + avisos : ""}` : avisos || "Gravado." });
      return;
    }
    if (it.status === "conflito") {
      acoes.push({ id, tipo: "remover" });
      resultados.push({ ...base, status: "conflito", registro_id: it.registro_id ?? null, conflito_log_id: it.conflito_log_id ?? null,
        texto: avisos || "Outro aparelho já registrou este animal neste ciclo. O aplicador ou o administrador decide qual vale." });
      return;
    }
    if (it.status === "pendente") {
      const requer = (it.requer || []) as CorpoSan["requer"];
      const motivo = requer?.includes("consentimento")
        ? `Fora da regra: ${it.motivo_fora || "não cumpre a regra"}. Precisa do seu consentimento.`
        : requer?.includes("carencia_decisao")
          ? `Carência: ${it.motivo_carencia || "não informada"}. Decida o que fazer com o leite.`
          : avisos || "Precisa de uma decisão.";
      acoes.push({ id, tipo: "atualizar", erro: null, corpo: {
        ...corpo, estado: "requer", requer, motivo, pergunta_atestado: !!it.pergunta_atestado,
        carencia_sugerida: it.carencia_sugerida ? { ...it.carencia_sugerida } : null,
      } });
      resultados.push({ ...base, status: "pendente", registro_id: null, conflito_log_id: null, texto: motivo });
      return;
    }
    const msg = avisos || "O servidor recusou este registro.";
    acoes.push({ id, tipo: "atualizar", erro: msg, corpo: { ...corpo, estado: "erro", motivo: msg } });
    resultados.push({ ...base, status: "erro", registro_id: null, conflito_log_id: null, texto: msg });
  });
  return { acoes, resultados };
}

/** Junta resultados novos na lista guardada (mais novo primeiro, sem repetir a
 *  mesma chave, no máximo `max`). */
export function juntarResultados(antigos: ResultadoSan[], novos: ResultadoSan[], max = 60): ResultadoSan[] {
  const vistos = new Set<string>();
  const out: ResultadoSan[] = [];
  for (const r of [...novos].reverse().concat(antigos)) {
    if (vistos.has(r.chave)) continue;
    vistos.add(r.chave);
    out.push(r);
  }
  return out.slice(0, max);
}

/** Aplica a decisão da pessoa num item "requer" e devolve o corpo pronto para
 *  voltar à fila. */
export function decidirItem(corpo: CorpoSan, d: { consentimento?: { aceito: boolean; motivo_exibido?: string | null;
  quer_atestado?: boolean | null; atestado_destinatario?: string | null } | null; carencia?: CarenciaDecisaoIn | null }): CorpoSan {
  const registro: RegistroCampo = { ...corpo.registro };
  if (d.consentimento) registro.consentimento = { ...d.consentimento };
  if (d.carencia) registro.carencia = { ...d.carencia };
  return { ...corpo, registro, estado: "fila", requer: [], motivo: null };
}

/** O aviso local de "N h sem enviar" (o servidor avisa o administrador; o app
 *  avisa o próprio usuário, mesmo sem sinal). */
export function filaAtrasada(maisAntigoIso: string | null | undefined, agoraMs: number, horas = 24): boolean {
  if (!maisAntigoIso) return false;
  const t = Date.parse(maisAntigoIso);
  return Number.isFinite(t) && agoraMs - t >= horas * 3600000;
}

// ════════════════════════════════════════════════════════════════════════════
// Execução do dia (tronco / grupo)
// ════════════════════════════════════════════════════════════════════════════
export type AnimalPacote = PacoteOffline["animais"][number];
export type OrigemAlvo = "janela" | "manual" | "curral" | string;
export type ConsentLocal = { aceito: boolean; motivo_exibido: string | null; quer_atestado?: boolean | null; atestado_destinatario?: string | null };
/** Animal incluído no curral (fora do que o dia já tinha). `animal_id` null =
 *  brinco sem cadastro (registra assim; o back marca "sem cadastro"). */
export type ExtraDia = {
  animal_id: number | null; numero: string; caixas: number[]; consent: Record<string, ConsentLocal>;
};
export type FeitoLocal = {
  chave: string; animal: string; numero: string; caixa_id: number; em: string; registro_id?: number | null;
  nao_aplicado?: boolean;
};
export type AlvoDia = {
  /** "a:<id>" ou "n:<brinco>" */
  animal: string; animal_id: number | null; numero: string; origem: OrigemAlvo; caixas: number[];
  consent: Record<string, ConsentLocal>; categoria: string | null; lote: string | null; idade: string | null;
  peso: number | null; semCadastro: boolean;
};

export function chaveAnimal(animalId: number | null | undefined, numero: string): string {
  return animalId != null ? `a:${animalId}` : `n:${String(numero).trim()}`;
}
export function chaveAC(animal: string, caixaId: number): string {
  return `${animal}|${caixaId}`;
}

/** Quem ainda falta aplicar no dia: itens pendentes do dia (janela/manual/
 *  curral) + incluídos no curral, sem os pares já feitos neste aparelho e sem
 *  quem foi marcado "não aplicar". Ordem: a do dia (brinco), depois os extras. */
export function alvosPendentes(pacote: Pick<PacoteOffline, "dia" | "animais">, extras: ExtraDia[], feitos: Iterable<string>,
  naoAplicar: Iterable<string> = []): AlvoDia[] {
  const feito = new Set(feitos);
  const fora = new Set(naoAplicar);
  const info = new Map<number, AnimalPacote>();
  for (const a of pacote.animais || []) info.set(a.animal_id, a);
  const alvos = new Map<string, AlvoDia>();
  const itens = ((pacote.dia.itens || []) as DiaItem[]).filter((i) => i.estado === "pendente");
  for (const i of itens) {
    const a = info.get(i.animal_id);
    const chave = chaveAnimal(i.animal_id, i.numero || a?.brinco || String(i.animal_id));
    let alvo = alvos.get(chave);
    if (!alvo) {
      alvo = {
        animal: chave, animal_id: i.animal_id, numero: i.numero || a?.brinco || `#${i.animal_id}`, origem: i.origem,
        caixas: [], consent: {}, categoria: a?.categoria ?? null, lote: a?.lote ?? null, idade: a?.idade ?? null,
        peso: a?.peso ?? null, semCadastro: false,
      };
      alvos.set(chave, alvo);
    } else if (alvo.origem === "janela" && i.origem !== "janela") {
      alvo.origem = i.origem; // o ícone mostra a inclusão manual quando houver
    }
    if (!alvo.caixas.includes(i.caixa_id)) alvo.caixas.push(i.caixa_id);
  }
  for (const e of extras) {
    const chave = chaveAnimal(e.animal_id, e.numero);
    const a = e.animal_id != null ? info.get(e.animal_id) : undefined;
    let alvo = alvos.get(chave);
    if (!alvo) {
      alvo = {
        animal: chave, animal_id: e.animal_id, numero: e.numero, origem: "curral", caixas: [], consent: {},
        categoria: a?.categoria ?? null, lote: a?.lote ?? null, idade: a?.idade ?? null, peso: a?.peso ?? null,
        semCadastro: e.animal_id == null,
      };
      alvos.set(chave, alvo);
    }
    for (const c of e.caixas) if (!alvo.caixas.includes(c)) alvo.caixas.push(c);
    alvo.consent = { ...alvo.consent, ...e.consent };
  }
  const out: AlvoDia[] = [];
  for (const alvo of alvos.values()) {
    if (fora.has(alvo.animal)) continue;
    alvo.caixas = alvo.caixas.filter((c) => !feito.has(chaveAC(alvo.animal, c)));
    if (alvo.caixas.length) out.push(alvo);
  }
  return out;
}

/** Elegibilidade (vinda do pacote, calculada no servidor) de um animal para as
 *  caixas do dia: quem está fora traz o motivo do pop-up de consentimento. */
export function foraDaRegra(animal: AnimalPacote | undefined, caixaIds: number[]): { caixa_id: number; motivo: string }[] {
  if (!animal) return [];
  const out: { caixa_id: number; motivo: string }[] = [];
  for (const c of caixaIds) {
    const e = animal.caixas?.[String(c)];
    if (e && !e.elegivel) out.push({ caixa_id: c, motivo: e.motivo || "não cumpre a regra" });
  }
  return out;
}

// ── produto, dose e peso ──
export function dosePorPeso(p: { dose_unidade?: string | null } | null | undefined): boolean {
  return p?.dose_unidade === "mL_por_kg" || p?.dose_unidade === "mL_por_x_kg";
}

/** Peso médio da categoria entre os animais do pacote (com pesagem). */
export function pesoMedioCategoria(animais: AnimalPacote[], categoria: string | null | undefined): number | null {
  if (!categoria) return null;
  const pesos = animais.filter((a) => a.categoria === categoria && typeof a.peso === "number" && (a.peso as number) > 0)
    .map((a) => a.peso as number);
  if (!pesos.length) return null;
  return Math.round(pesos.reduce((s, p) => s + p, 0) / pesos.length);
}

/** Peso para a dose: o da última pesagem; sem ela, a média da categoria
 *  marcada como ESTIMADO (o back também estima e marca, quando o peso não vai). */
export function pesoParaDose(alvo: { peso: number | null; categoria: string | null }, animais: AnimalPacote[]):
  { peso: number | null; estimado: boolean } {
  if (typeof alvo.peso === "number" && alvo.peso > 0) return { peso: alvo.peso, estimado: false };
  const m = pesoMedioCategoria(animais, alvo.categoria);
  return m != null ? { peso: m, estimado: true } : { peso: null, estimado: false };
}

/** Quantidade aplicada (mL) quando a dose é por peso; senão a própria dose. */
export function quantidadeDose(p: { dose_valor?: number | null; dose_unidade?: string | null; dose_x_kg?: number | null } | null | undefined,
  peso: number | null | undefined): number | null {
  if (!p || p.dose_valor == null) return null;
  if (p.dose_unidade === "mL_por_kg") return peso ? Math.round(p.dose_valor * peso * 10) / 10 : null;
  if (p.dose_unidade === "mL_por_x_kg") return peso && p.dose_x_kg ? Math.round((p.dose_valor * peso / p.dose_x_kg) * 10) / 10 : null;
  return p.dose_valor;
}

/** Produto efetivo de uma caixa: o do dia, trocado na hora se houver troca. */
export function produtoEfetivo(base: Record<string, unknown> | null | undefined, troca: ProdutoIn | null | undefined): ProdutoIn {
  const b = (base || {}) as ProdutoIn;
  if (!troca) return { ...b };
  return { ...b, ...troca };
}

// ── preparação (pré-curral) ──
export type ItemPreparacao = { id: string; texto: string; detalhe?: string | null };

/** Lista de conferência gerada pelo cadastro das vacinas/exames do dia.
 *  O que não for marcado pede ciência nominal antes de começar. */
export function itensPreparacao(pacote: Pick<PacoteOffline, "caixas" | "estoques" | "dia">): ItemPreparacao[] {
  const itens: ItemPreparacao[] = [];
  const estoque = new Map((pacote.estoques || []).map((e) => [e.id, e]));
  const animais = pacote.dia.contagens?.animais ?? null;
  let temVacina = false, pedeCrmv = false;
  for (const c of pacote.caixas || []) {
    const r = (c.regras || {}) as Obj;
    const prod = (c.produto || {}) as ProdutoIn;
    if (c.tipo === "exame") {
      const leitura = r.legal_leitura as { horas?: number | null } | null;
      itens.push({ id: `exame:${c.caixa_id}`, texto: `Material do exame ${c.nome_curto || c.nome}`,
        detalhe: leitura?.horas ? `Leitura em ${leitura.horas} h: combinar a volta ao curral.` : null });
    } else {
      temVacina = true;
      const est = prod.estoque_id ? estoque.get(prod.estoque_id) : undefined;
      const saldo = est && est.saldo != null ? `Saldo no estoque: ${String(est.saldo).replace(".", ",")} ${est.unidade || ""}`.trim() : null;
      itens.push({ id: `produto:${c.caixa_id}`, texto: `Separar ${textoProduto(prod, est?.nome)}`,
        detalhe: [c.nome_curto || c.nome, saldo, est && (est.saldo ?? 0) <= 0 ? "sem saldo: registra mesmo assim" : null]
          .filter(Boolean).join(" · ") });
    }
    if (r.legal_crmv_pedir) pedeCrmv = true;
    if (r.legal_marca_texto) itens.push({ id: `marca:${c.caixa_id}`, texto: `Marcação: ${String(r.legal_marca_texto)}`, detalhe: c.nome_curto || c.nome });
    if (r.tem_atestado) itens.push({ id: `atestado:${c.caixa_id}`, texto: `Atestado de ${c.nome_curto || c.nome}`, detalhe: "Conferir os dados para o atestado." });
    if (r.carencia_precisa_decisao) itens.push({ id: `carencia:${c.caixa_id}`, texto: `Carência de ${c.nome_curto || c.nome} sem decisão`,
      detalhe: String(r.carencia_precisa_decisao) });
  }
  if (temVacina) itens.push({ id: "material", texto: "Seringas, agulhas e caixa térmica", detalhe: "Vacina refrigerada fica na caixa térmica até a aplicação." });
  if (pedeCrmv) itens.push({ id: "crmv", texto: "Veterinário com CRMV presente", detalhe: "Pedido pelo cadastro (não é exigido para registrar)." });
  itens.push({ id: "animais", texto: "Animais apartados no curral", detalhe: animais != null ? `${animais} ${animais === 1 ? "animal" : "animais"} no dia.` : null });
  return itens;
}

// ════════════════════════════════════════════════════════════════════════════
// Lançamento simples (Lançar › Preventiva) sem sinal → registros da fila
// ════════════════════════════════════════════════════════════════════════════
/** Converte o lançamento simples nos registros da fila, com a MESMA chave por
 *  animal que o back usa no POST /lancamento-simples (`<chave_lote>:<id>` /
 *  `<chave_lote>:n<brinco>`): se a mesma tela também conseguir enviar online,
 *  nada duplica. O motivo do retroativo não cabe no registro da fila
 *  (RegistroSyncIn não tem o campo) — vai junto só quando há sinal. */
export function registrosDoLancamento(l: LancamentoSimplesIn, chaveLote: string): RegistroCampo[] {
  const base: RegistroCampo = {
    dia_id: null, caixa_id: l.caixa_id ?? null, outro_texto: l.caixa_id ? null : textoOuNulo(l.outro_texto), data: l.data,
    produto: l.produto ?? null, aplicador_pessoa_id: l.aplicador_pessoa_id ?? null, aplicador_texto: textoOuNulo(l.aplicador_texto),
    veterinario_pessoa_id: l.veterinario_pessoa_id ?? null, veterinario_texto: textoOuNulo(l.veterinario_texto),
    crmv_texto: textoOuNulo(l.crmv_texto), atestado_numero: textoOuNulo(l.atestado?.numero),
    atestado_destinatario: textoOuNulo(l.atestado?.destinatario), carencia: l.carencia ?? null,
  };
  const cons = new Map<string, ConsentimentoIn>();
  for (const c of l.consentimentos || []) if (c.aceito) cons.set(`${c.animal_id}|${c.caixa_id ?? ""}`, c);
  const out: RegistroCampo[] = [];
  for (const aid of [...new Set((l.animal_ids || []).map(Number))]) {
    const c = cons.get(`${aid}|${l.caixa_id ?? ""}`) || cons.get(`${aid}|`);
    out.push({
      ...base, animal_id: aid, chave_idempotencia: `${chaveLote}:${aid}`,
      peso_kg: l.peso_kg?.[aid] ?? null, resultado: l.resultados?.[aid] ?? null,
      consentimento: c ? { aceito: true, motivo_exibido: c.motivo_exibido ?? null, quer_atestado: c.quer_atestado ?? null,
        atestado_destinatario: c.atestado_destinatario ?? null } : null,
    });
  }
  for (const n of [...new Set((l.numeros || []).map((x) => String(x).trim()).filter(Boolean))]) {
    out.push({ ...base, numero_animal: n, chave_idempotencia: `${chaveLote}:n${n}` });
  }
  return out;
}

// ── data/hora local da fazenda ──
export function horaAgora(agora: Date = new Date()): string {
  return new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, hour: "2-digit", minute: "2-digit", hour12: false }).format(agora);
}
