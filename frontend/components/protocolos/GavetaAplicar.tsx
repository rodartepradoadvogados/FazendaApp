"use client";
// Gaveta APLICAR — a MESMA em Protocolos › Acompanhamento e na Agenda (mesma
// largura, mesmos campos, mesmo endpoint POST /sanidade/cronogramas/{id}/aplicar;
// só muda o `canal` gravado). Mockup: docs/agents/auditoria-preventivo-agenda/
// mockups/fluxo-completo.html (proto-aplicar-dr.js).
//
// Regras que a tela mostra e o servidor confere: aplicador obrigatório (B19 e
// tuberculose: só veterinário), frasco vencido pede ciência, "Desconsiderar
// estoque" pede motivo e não baixa, itens pendentes do checklist pedem só a
// ciência (nunca bloqueiam), animal não aplicado pede motivo e destino.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, ChevronDown, Info, Syringe, Undo2 } from "lucide-react";
import {
  aplicarAgendamentoPreventivo, desfazerAplicacaoPreventiva, fetchContextoAplicar,
  type AplicarAgendamentoPayload, type ContextoAplicar, type ResultadoAplicar,
} from "@/lib/api";
import { GavetaLancamento } from "@/components/lancamentos/GavetaLancamento";
import { TelaSkeleton } from "@/components/ui";
import {
  brl, Chips, dataCurta, diaSemana, hojeIso, inputStyle, labelStyle, MOTIVOS_CIENCIA, MOTIVOS_ESTOQUE, MOTIVOS_NAO_APLICADO,
  notaStyle, num, Pill, plural, textoMotivo,
} from "./preventivoComum";

type Props = {
  cronogramaId: number;
  canal: "Protocolos" | "Agenda";
  onFechar: () => void;
  /** Depois de aplicar (e também depois de desfazer): quem abriu recarrega a lista. */
  onMudou?: () => void;
  /** Só no canal Protocolos: leva à aba Concluídos. */
  onVerConcluidos?: () => void;
};

const horaAgora = () => {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};
// "1 dose" / "7 doses": a unidade do estoque vem no singular.
const unPl = (un: string, n: number) => (n === 1 || !un ? un : un === "dose" ? "doses" : un === "unidade" ? "unidades" : un);
const novaChave = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `ap-${Date.now()}-${Math.random().toString(16).slice(2)}`);

export function GavetaAplicar({ cronogramaId, canal, onFechar, onMudou, onVerConcluidos }: Props) {
  const [ctx, setCtx] = useState<ContextoAplicar | null>(null);
  const [erroCarga, setErroCarga] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoAplicar | null>(null);
  const [desfeito, setDesfeito] = useState(false);
  const chave = useRef(novaChave());

  const carregar = useCallback(() => {
    fetchContextoAplicar(cronogramaId).then(setCtx).catch((e) => setErroCarga(e.message || "Erro ao abrir o agendamento"));
  }, [cronogramaId]);
  useEffect(() => { carregar(); }, [carregar]);

  const titulo = "Aplicar";
  return (
    <GavetaLancamento aberto onFechar={() => { if (resultado) onMudou?.(); onFechar(); }} titulo={titulo} icone={Syringe}>
      {erroCarga && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erroCarga}</span></div>}
      {!ctx && !erroCarga && <TelaSkeleton kpis={0} />}
      {ctx && !resultado && (
        <FormAplicar
          ctx={ctx} canal={canal} chave={chave.current}
          onAplicado={(r) => { setResultado(r); onMudou?.(); }}
          onFechar={onFechar}
        />
      )}
      {ctx && resultado && (
        <Concluida
          ctx={ctx} r={resultado} canal={canal} desfeito={desfeito}
          onDesfeito={() => { setDesfeito(true); onMudou?.(); }}
          onFechar={onFechar} onVerConcluidos={onVerConcluidos}
        />
      )}
    </GavetaLancamento>
  );
}

// ───────────────────────────── formulário ─────────────────────────────
function FormAplicar({ ctx, canal, chave, onAplicado, onFechar }: {
  ctx: ContextoAplicar; canal: "Protocolos" | "Agenda"; chave: string;
  onAplicado: (r: ResultadoAplicar) => void; onFechar: () => void;
}) {
  const hoje = ctx.hoje || hojeIso();
  const ckEst = ctx.estoque.checklist;
  const desconsiderouNoChecklist = ckEst.estado === "desconsiderado";
  const loteInicial = (() => {
    if (desconsiderouNoChecklist || !ctx.estoque.encontrado) return "";
    if (ckEst.estado === "vinculado" && ckEst.lote_id && ctx.estoque.lotes.some((l) => l.id === ckEst.lote_id && !l.vencido)) return String(ckEst.lote_id);
    return ctx.estoque.lote_sugerido_id ? String(ctx.estoque.lote_sugerido_id) : "";
  })();

  const [marc, setMarc] = useState<Set<string>>(() => new Set(ctx.animais.map((a) => a.numero_matriz)));
  const [naoMotivo, setNaoMotivo] = useState<Record<string, string>>({});
  const [naoOutro, setNaoOutro] = useState<Record<string, string>>({});
  const [naoDestino, setNaoDestino] = useState<Record<string, "espera" | "naoSeAplica">>({});
  const [animAberto, setAnimAberto] = useState(false);
  const [lote, setLote] = useState(loteInicial);
  const [ciente, setCiente] = useState(false);
  const [desconsiderar, setDesconsiderar] = useState(desconsiderouNoChecklist || !ctx.estoque.encontrado);
  const [motEst, setMotEst] = useState(desconsiderouNoChecklist ? (ckEst.motivo || "") : "");
  const [motEstOutro, setMotEstOutro] = useState("");
  const [loteVet, setLoteVet] = useState(desconsiderouNoChecklist ? (ckEst.lote || "") : "");
  const [valVet, setValVet] = useState(desconsiderouNoChecklist ? (ckEst.validade || "") : "");
  const [aplicadorId, setAplicadorId] = useState(ctx.aplicador_sugerido_id ? String(ctx.aplicador_sugerido_id) : "");
  const [dataModo, setDataModo] = useState<"hoje" | "outra">("hoje");
  const [dataOutra, setDataOutra] = useState(hoje);
  const [hora, setHora] = useState(horaAgora());
  const [custo, setCusto] = useState("");
  const [pesos, setPesos] = useState<Record<string, string>>({});
  const [cientePend, setCientePend] = useState(false);
  const [motCiencia, setMotCiencia] = useState("");
  const [resumoAberto, setResumoAberto] = useState(false);
  const [tentou, setTentou] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erroServ, setErroServ] = useState<string | null>(null);

  const dataReal = dataModo === "hoje" ? hoje : dataOutra;
  const pessoa = ctx.pessoas.find((p) => String(p.id) === aplicadorId);
  const frasco = ctx.estoque.lotes.find((l) => String(l.id) === lote);
  const frascoVencido = !desconsiderar && !!frasco?.vencido;
  const pend = ctx.checklist.pendentes;

  const doseDe = (n: string): number | null => {
    const a = ctx.animais.find((x) => x.numero_matriz === n);
    if (!a) return null;
    const p = pesos[n] ? Number(String(pesos[n]).replace(",", ".")) : NaN;
    // Dose por peso: o peso digitado na hora vale mais que a pesagem/estimativa.
    if (ctx.por_peso && !isNaN(p) && p > 0 && ctx.kg_ref && ctx.dose_ref) return (p / ctx.kg_ref) * ctx.dose_ref;
    return a.dose;
  };
  const aplicados = ctx.animais.filter((a) => marc.has(a.numero_matriz));
  const nao = ctx.animais.filter((a) => !marc.has(a.numero_matriz));
  const totalDose = aplicados.reduce((s, a) => s + (doseDe(a.numero_matriz) || 0), 0);
  const un = ctx.unidade || "";
  const custoNum = custo.trim() !== "" && !isNaN(Number(custo.replace(",", "."))) ? Number(custo.replace(",", ".")) : null;
  const semPeso = aplicados.filter((a) => ctx.por_peso && doseDe(a.numero_matriz) == null).map((a) => a.numero_matriz);
  const saldoFrasco = desconsiderar ? null : (frasco ? frasco.saldo : ctx.estoque.saldo);
  const faltam = saldoFrasco != null ? Math.max(0, totalDose - saldoFrasco) : 0;
  const restante = saldoFrasco != null ? Math.max(0, saldoFrasco - totalDose) : null;
  const carenciaCarne = ctx.carencia.carne_dias != null ? somaDias(dataReal, ctx.carencia.carne_dias) : null;
  const carenciaLeite = ctx.carencia.proibido_lactacao ? null : ctx.carencia.leite_dias != null ? somaDias(dataReal, ctx.carencia.leite_dias) : null;
  const foraJanela = aplicados.filter((a) => a.origem === "fora_janela").length;

  const motivoNao = (n: string) => textoMotivo(naoMotivo[n] || "", naoOutro[n] || "");
  let erro = "";
  if (!aplicados.length) erro = "Marque pelo menos 1 animal aplicado.";
  else if (!aplicadorId) erro = "Escolha quem aplicou.";
  else if (dataReal > hoje) erro = "A data real não pode ser futura.";
  else if (ctx.exige_veterinario && !pessoa?.veterinario) erro = `Só veterinário habilitado (CRMV) aplica ${ctx.protocolo_nome}.`;
  else if (desconsiderar && !textoMotivo(motEst, motEstOutro)) erro = "Escolha o motivo para desconsiderar o estoque.";
  else if (!desconsiderar && !ctx.estoque.encontrado) erro = "O produto não está no estoque: desconsidere o estoque com motivo.";
  else if (frascoVencido && !ciente) erro = "Frasco vencido: marque a ciência para usar assim mesmo.";
  else if (semPeso.length) erro = `Informe o peso de: ${semPeso.join(", ")}.`;
  else if (nao.some((a) => !motivoNao(a.numero_matriz))) erro = "Escolha o motivo de cada animal não aplicado.";
  else if (pend.length && !cientePend) erro = `Marque a ciência dos ${pend.length} ${plural(pend.length, "item pendente", "itens pendentes")} do checklist.`;

  async function aplicar() {
    setTentou(true);
    if (erro) return;
    setSalvando(true); setErroServ(null);
    const corpo: AplicarAgendamentoPayload = {
      canal, aplicador_pessoa_id: Number(aplicadorId), animais_aplicados: aplicados.map((a) => a.numero_matriz),
      nao_aplicados: nao.map((a) => ({ numero_matriz: a.numero_matriz, motivo: motivoNao(a.numero_matriz), destino: naoDestino[a.numero_matriz] || "espera" })),
      data_aplicacao: dataReal, hora: hora || null, custo: custoNum,
      ciencia_pendentes: pend.length > 0 && cientePend, ciencia_motivo: cientePend ? (motCiencia || null) : null,
      chave_idempotencia: chave,
    };
    if (desconsiderar) {
      corpo.desconsiderar_estoque = true;
      corpo.motivo_desconsiderar_estoque = textoMotivo(motEst, motEstOutro);
      corpo.lote_veterinario = loteVet.trim() || null;
      corpo.validade_veterinario = valVet || null;
    } else {
      corpo.estoque_id = ctx.estoque.estoque_id;
      corpo.lote_id = lote ? Number(lote) : null;
      corpo.ciente_vencido = frascoVencido && ciente;
    }
    const pesosNum: Record<string, number> = {};
    Object.entries(pesos).forEach(([n, v]) => { const x = Number(String(v).replace(",", ".")); if (x > 0) pesosNum[n] = x; });
    if (ctx.por_peso && Object.keys(pesosNum).length) corpo.pesos = pesosNum;
    try {
      onAplicado(await aplicarAgendamentoPreventivo(ctx.cronograma_id, corpo));
    } catch (e: any) { setErroServ(e.message || "Erro ao aplicar"); } finally { setSalvando(false); }
  }

  const linhaResumo = `${aplicados.length} ${plural(aplicados.length, "animal", "animais")} · ${num(totalDose)} ${unPl(un, totalDose)} · restante ${restante == null ? "—" : `${num(restante)} ${unPl(un, restante)}`}${carenciaCarne ? ` · carne até ${dataCurta(carenciaCarne)}` : ""}${carenciaLeite ? ` · leite até ${dataCurta(carenciaLeite)}` : ""}`;
  const boxAviso = (cor: string, texto: React.ReactNode, icone = <AlertTriangle size={15} />) => (
    <div role="status" style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", fontSize: "0.82rem", border: `1px solid ${cor}`, borderLeft: `4px solid ${cor}`, borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem", background: "var(--surface-2)" }}>
      <span style={{ color: cor, marginTop: 2, display: "inline-flex" }}>{icone}</span><span>{texto}</span>
    </div>
  );

  return (
    <div className="le-raiz" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
      <div>
        <p style={{ ...notaStyle, margin: 0 }}>
          Aberto de: <b>{canal === "Agenda" ? "Agenda" : "Protocolos › Acompanhamento"}</b>
        </p>
        <h2 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--dourado-light)", marginTop: "0.3rem" }}>{ctx.protocolo_nome}</h2>
        <p style={notaStyle}>
          {diaSemana(ctx.data_evento)} {dataCurta(ctx.data_evento)}{ctx.hora ? ` ${ctx.hora}` : ""} · {ctx.responsavel.nome}{ctx.responsavel.crmv ? ` (${ctx.responsavel.crmv})` : ""}
          {ctx.produto ? ` · ${ctx.produto}` : ""}
        </p>
      </div>

      {/* avisos */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {frascoVencido && boxAviso("var(--red)", <><b>Frasco vencido.</b> O frasco {frasco?.numero_lote || `#${frasco?.id}`} venceu em {dataCurta(frasco?.validade)}. É preciso ciência para usar assim mesmo; ela fica registrada com o seu nome e a hora.</>)}
        {!frascoVencido && frasco && frasco.vence_em_dias != null && frasco.vence_em_dias <= 30 && boxAviso("var(--amber)", <><b>Validade próxima.</b> O frasco {frasco.numero_lote || `#${frasco.id}`} vence em {frasco.vence_em_dias} {plural(frasco.vence_em_dias, "dia", "dias")} ({dataCurta(frasco.validade)}).</>)}
        {faltam > 0 && boxAviso("var(--amber)", <><b>Estoque insuficiente.</b> Faltam {num(faltam)} {un}. A aplicação não é bloqueada: o estoque fica negativo e a divergência é avisada. Comunique a compra.</>)}
        {ctx.exige_veterinario && !pessoa?.veterinario && boxAviso("var(--red)", <><b>{ctx.protocolo_nome}: só veterinário habilitado (CRMV) aplica.</b> Escolha o veterinário em “Quem aplicou”.</>)}
        {ctx.carencia.proibido_lactacao && boxAviso("var(--red)", <><b>Não usar em vaca em lactação.</b> Confira os animais antes de aplicar.</>)}
        {dataReal < hoje && boxAviso("var(--dourado-light)", "Aplicação já realizada: confira a data e a hora em que foi feita.", <Info size={15} />)}
        {ctx.data_evento > hoje && boxAviso("var(--dourado-light)", `Aplicando antes da data agendada (${dataCurta(ctx.data_evento)}). Tudo o que estava combinado continua valendo.`, <Info size={15} />)}
        {foraJanela > 0 && boxAviso("var(--amber)", `${foraJanela} ${plural(foraJanela, "animal incluído", "animais incluídos")} fora da janela de aplicação (fica marcado no histórico).`)}
      </div>

      {/* resumo */}
      <details className="card" open={resumoAberto} onToggle={(e) => setResumoAberto((e.currentTarget as HTMLDetailsElement).open)} style={{ padding: "0.6rem 0.9rem" }}>
        <summary style={{ cursor: "pointer", display: "flex", flexDirection: "column", gap: 2, listStyle: "none" }}>
          <span style={{ ...labelStyle, marginBottom: 0, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em" }}>O que acontece ao aplicar</span>
          <span style={{ fontSize: "0.86rem", fontWeight: 600 }}>{linhaResumo}</span>
          <span style={{ ...notaStyle, display: "inline-flex", alignItems: "center", gap: 3 }}><ChevronDown size={13} />Detalhes</span>
        </summary>
        <ul style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "0.6rem", listStyle: "none", margin: "0.7rem 0 0", padding: 0 }}>
          <Item k="Animais" v={String(aplicados.length)} />
          <Item k={ctx.por_peso ? "Volume" : "Doses"} v={`${num(totalDose)} ${unPl(un, totalDose)}`} />
          <Item k="Estoque restante" v={restante == null ? "sem saída" : `${num(restante)} ${unPl(un, restante)}`} />
          <Item k="Carência" v={[carenciaCarne ? `carne até ${dataCurta(carenciaCarne)}` : "", carenciaLeite ? `leite até ${dataCurta(carenciaLeite)}` : "", ctx.carencia.proibido_lactacao ? "leite: não usar em lactação" : ""].filter(Boolean).join(" · ") || "sem carência informada"} />
          <Item k="Custo" v={custoNum != null ? brl(custoNum) : desconsiderar ? "a informar" : "calculado pelo estoque"} />
        </ul>
        <p style={{ ...notaStyle, marginTop: "0.6rem" }}>{ctx.por_peso ? "Dose por peso: cada animal recebe pelo seu peso. " : ""}Cada animal vira uma linha em Sanidade e o registro vai para <b>Concluídos</b>.</p>
      </details>

      {/* animais */}
      <div>
        <span style={labelStyle}>Animais: marque quem foi aplicado</span>
        {/* Até 6 animais aparecem direto; acima disso a lista recolhe (abre sozinha se alguém ficar de fora). */}
        <Recolhivel colapsavel={ctx.animais.length > 6} aberto={animAberto || nao.length > 0} onToggle={setAnimAberto}
                    resumo={<><b>{aplicados.length} de {ctx.animais.length} marcados como aplicados</b> · ver e ajustar os animais</>}>
          <div className="card" style={{ padding: "0.3rem 0.8rem" }}>
            {ctx.animais.map((a) => {
              const mk = marc.has(a.numero_matriz);
              const d = doseDe(a.numero_matriz);
              return (
                <div key={a.numero_matriz} style={{ borderBottom: "1px solid var(--border)", padding: "0.5rem 0" }}>
                  <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
                    <label style={{ display: "flex", gap: "0.6rem", alignItems: "center", cursor: "pointer", flex: "1 1 220px", minWidth: 0 }}>
                      <input type="checkbox" checked={mk} aria-label={`Aplicado em ${a.numero_matriz}`} style={{ width: 18, height: 18 }}
                             onChange={() => setMarc((p) => { const s = new Set(p); if (s.has(a.numero_matriz)) s.delete(a.numero_matriz); else s.add(a.numero_matriz); return s; })} />
                      <span>
                        <b>{a.numero_matriz}{a.nome ? ` ${a.nome}` : ""}</b>
                        <span style={{ ...notaStyle, display: "block" }}>
                          {a.lote || "Sem lote"} · {d != null ? `${num(d)} ${un}` : "sem peso"}
                          {ctx.por_peso && a.peso_kg ? ` (${num(a.peso_kg, 0)} kg${a.peso_estimado ? ", estimativa pelo lote" : ""})` : ""}
                        </span>
                      </span>
                    </label>
                    {a.origem === "fora_janela" && <Pill cor="var(--amber)" title={a.motivo || undefined}>Fora da janela</Pill>}
                    {ctx.por_peso && mk && (a.peso_estimado || a.sem_peso) && (
                      <input inputMode="decimal" style={{ ...inputStyle, width: 120 }} placeholder="peso (kg)" aria-label={`Peso de ${a.numero_matriz} (kg)`} value={pesos[a.numero_matriz] || ""}
                             onChange={(e) => setPesos((p) => ({ ...p, [a.numero_matriz]: e.target.value }))} />
                    )}
                  </div>
                  {!mk && (
                    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", padding: "0.5rem 0 0 2rem" }}>
                      <select style={{ ...inputStyle, flex: "1 1 180px", width: "auto" }} aria-label={`Motivo de ${a.numero_matriz} não ter sido aplicado`}
                              value={naoMotivo[a.numero_matriz] || ""} onChange={(e) => setNaoMotivo((p) => ({ ...p, [a.numero_matriz]: e.target.value }))}>
                        <option value="">Motivo (obrigatório)</option>
                        {MOTIVOS_NAO_APLICADO.map((m) => <option key={m}>{m}</option>)}
                      </select>
                      {naoMotivo[a.numero_matriz] === "Outro" && (
                        <input style={{ ...inputStyle, flex: "1 1 180px", width: "auto" }} aria-label={`Descreva o motivo de ${a.numero_matriz}`} placeholder="Descreva" value={naoOutro[a.numero_matriz] || ""}
                               onChange={(e) => setNaoOutro((p) => ({ ...p, [a.numero_matriz]: e.target.value }))} />
                      )}
                      <select style={{ ...inputStyle, flex: "1 1 200px", width: "auto" }} aria-label={`Destino de ${a.numero_matriz}`} value={naoDestino[a.numero_matriz] || "espera"}
                              onChange={(e) => setNaoDestino((p) => ({ ...p, [a.numero_matriz]: e.target.value as "espera" | "naoSeAplica" }))}>
                        <option value="espera">Volta à lista de espera</option>
                        <option value="naoSeAplica">Desconsiderar</option>
                      </select>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Recolhivel>
        <p style={{ ...notaStyle, marginTop: "0.3rem" }}>
          <button type="button" className="btn-ghost" style={{ padding: 0, border: "none", textDecoration: "underline" }}
                  onClick={() => setMarc(marc.size === ctx.animais.length ? new Set() : new Set(ctx.animais.map((a) => a.numero_matriz)))}>
            {marc.size === ctx.animais.length ? "Desmarcar todos" : "Marcar todos como aplicados"}
          </button>
          {nao.length > 0 && ` · ${nao.length} ${plural(nao.length, "animal fica fora", "animais ficam fora")}`}
        </p>
      </div>

      {/* frasco e estoque */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label htmlFor="ap-fr" style={labelStyle}>Frasco / lote (validade)</label>
          <select id="ap-fr" style={inputStyle} value={lote} disabled={desconsiderar || !ctx.estoque.encontrado || !ctx.estoque.lotes.length}
                  onChange={(e) => { setLote(e.target.value); setCiente(false); }}>
            {desconsiderar ? <option>Estoque desconsiderado (sem baixa){loteVet ? ` · lote ${loteVet}` : ""}</option>
              : !ctx.estoque.encontrado ? <option>Sem produto no estoque</option>
              : <>
                {!ctx.estoque.lotes.length && <option value="">Sem frascos abertos: baixa no saldo do item</option>}
                {ctx.estoque.lotes.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.numero_lote || `#${l.id}`} · validade {dataCurta(l.validade)} · saldo {num(l.saldo)}{l.vencido ? " · VENCIDO" : l.vence_em_dias != null && l.vence_em_dias <= 30 ? ` · vence em ${l.vence_em_dias} dias` : ""}
                  </option>
                ))}
              </>}
          </select>
          <span style={notaStyle}>{desconsiderar ? "Nada é baixado do estoque." : `${ctx.estoque.nome || ctx.produto || ""} · o frasco vencido nunca vem escolhido`}</span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div><label htmlFor="ap-dose" style={labelStyle}>Dose</label><input id="ap-dose" style={inputStyle} readOnly aria-readonly="true" value={ctx.dose_texto} /></div>
          <div><label htmlFor="ap-via" style={labelStyle}>Via</label><input id="ap-via" style={inputStyle} readOnly aria-readonly="true" value={ctx.via || "—"} /><span style={notaStyle}>Via aprovada; não pode ser trocada.</span></div>
        </div>
      </div>
      {frascoVencido && (
        <label style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", cursor: "pointer", fontSize: "0.85rem" }}>
          <input type="checkbox" checked={ciente} onChange={(e) => setCiente(e.target.checked)} style={{ width: 18, height: 18, marginTop: 2 }} />
          <span><b>Ciente, usar assim mesmo.</b> O frasco está vencido e a ciência fica registrada com o meu nome e a hora.</span>
        </label>
      )}
      <label style={{ display: "flex", gap: "0.6rem", alignItems: "center", cursor: "pointer", fontSize: "0.85rem" }}>
        <input type="checkbox" checked={desconsiderar} disabled={!ctx.estoque.encontrado} onChange={(e) => setDesconsiderar(e.target.checked)} style={{ width: 18, height: 18 }} />
        <span>Desconsiderar estoque (frasco do veterinário: nada é baixado)</span>
      </label>
      {desconsiderar && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: "0.7rem", padding: "0.8rem 1rem" }}>
          <Chips idBase="ap-me" rotulo="Motivo (obrigatório; nada vem marcado)" opcoes={MOTIVOS_ESTOQUE} valor={motEst} onChange={setMotEst}
                 erro={tentou && !textoMotivo(motEst, motEstOutro) ? "Escolha o motivo para desconsiderar o estoque." : null} />
          {motEst === "Outro" && <input style={inputStyle} aria-label="Descreva o motivo" placeholder="Descreva o motivo" value={motEstOutro} onChange={(e) => setMotEstOutro(e.target.value)} />}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div><label htmlFor="ap-lv" style={labelStyle}>Lote do frasco</label><input id="ap-lv" style={inputStyle} value={loteVet} onChange={(e) => setLoteVet(e.target.value)} placeholder="ex.: VET-778" /></div>
            <div><label htmlFor="ap-vv" style={labelStyle}>Validade</label><input id="ap-vv" type="date" style={inputStyle} value={valVet} onChange={(e) => setValVet(e.target.value)} /></div>
          </div>
        </div>
      )}

      {/* quem, quando, custo */}
      <div>
        <label htmlFor="ap-quem" style={labelStyle}>Quem aplicou</label>
        <select id="ap-quem" style={inputStyle} value={aplicadorId} onChange={(e) => setAplicadorId(e.target.value)}>
          <option value="">Escolha quem aplicou</option>
          {ctx.pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.veterinario ? "veterinário" : (p.tipo || "pessoa").toLowerCase()}{p.crmv ? `, ${p.crmv}` : ""})</option>)}
        </select>
        {!aplicadorId && <span style={notaStyle}>Obrigatório: escolha quem aplicou para liberar o botão.</span>}
      </div>
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend style={{ ...labelStyle, marginBottom: "0.3rem" }}>Data e hora reais</legend>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
          {(["hoje", "outra"] as const).map((m) => (
            <label key={m} style={{ display: "inline-flex", gap: 6, alignItems: "center", cursor: "pointer", fontSize: "0.82rem", padding: "0.35rem 0.8rem", borderRadius: 999,
                                    border: `1px solid ${dataModo === m ? "var(--pill-active-border)" : "var(--border)"}`, background: dataModo === m ? "var(--pill-active-bg)" : "transparent",
                                    color: dataModo === m ? "var(--pill-active-fg)" : "var(--text)", fontWeight: dataModo === m ? 700 : 500 }}>
              <input type="radio" name="ap-dt" checked={dataModo === m} onChange={() => { setDataModo(m); if (m === "hoje") setDataOutra(hoje); }} />
              {m === "hoje" ? `Hoje · ${dataCurta(hoje)}` : "Outra data"}
            </label>
          ))}
          {dataModo === "outra" && <input type="date" style={{ ...inputStyle, width: "auto" }} aria-label="Outra data" value={dataOutra} max={hoje} onChange={(e) => setDataOutra(e.target.value)} />}
          <input type="time" style={{ ...inputStyle, width: "auto" }} aria-label="Hora" value={hora} onChange={(e) => setHora(e.target.value)} />
        </div>
      </fieldset>
      <div>
        <label htmlFor="ap-custo" style={labelStyle}>Custo (opcional)</label>
        <input id="ap-custo" inputMode="decimal" style={inputStyle} value={custo} onChange={(e) => setCusto(e.target.value)}
               placeholder={desconsiderar ? "Informe o custo do frasco ou deixe a informar" : "Em branco: doses × preço do estoque"} />
      </div>

      {/* ciência dos pendentes */}
      {pend.length > 0 && (
        <div className="card" style={{ padding: "0.8rem 1rem", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          <label style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", cursor: "pointer", fontSize: "0.85rem" }}>
            <input type="checkbox" checked={cientePend} onChange={(e) => setCientePend(e.target.checked)} style={{ width: 18, height: 18, marginTop: 2 }} />
            <span>
              <b>Ciente dos {pend.length} {plural(pend.length, "item pendente", "itens pendentes")} do checklist.</b> Aplicar não é bloqueado; a ciência (itens, quem e quando) fica gravada no registro.
              <span style={{ ...notaStyle, display: "block" }}>{pend.map((p) => p.nome).join(" · ")}</span>
            </span>
          </label>
          {cientePend && <Chips idBase="ap-mc" rotulo="Motivo (opcional)" opcoes={MOTIVOS_CIENCIA} valor={motCiencia} onChange={setMotCiencia} />}
        </div>
      )}

      {erroServ && <p role="alert" style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erroServ}</p>}

      {/* rodapé fixo */}
      <div style={{
        position: "sticky", bottom: "-0.9rem", margin: "0 -0.9rem -0.9rem", padding: "0.75rem 0.9rem", background: "var(--surface)",
        borderTop: "1px solid var(--border)", display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap", zIndex: 2,
      }}>
        <button type="button" id="ap-ok" className="btn-primary-gold" aria-disabled={!!erro || salvando} disabled={salvando || !aplicadorId}
                title={!aplicadorId ? "Escolha quem aplicou" : undefined} onClick={aplicar}>
          <Check size={14} /> {salvando ? "Aplicando…" : `Aplicar (${aplicados.length} ${plural(aplicados.length, "animal", "animais")})`}
        </button>
        <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
        <span id="ap-erro" role="status" style={{ ...notaStyle, color: "var(--amber)", flex: "1 1 200px" }}>{erro}</span>
      </div>
    </div>
  );
}

function Recolhivel({ colapsavel, aberto, onToggle, resumo, children }: {
  colapsavel: boolean; aberto: boolean; onToggle: (aberto: boolean) => void; resumo: React.ReactNode; children: React.ReactNode;
}) {
  if (!colapsavel) return <>{children}</>;
  return (
    <details open={aberto} onToggle={(e) => onToggle((e.currentTarget as HTMLDetailsElement).open)}>
      <summary style={{ cursor: "pointer", fontSize: "0.85rem", marginBottom: "0.4rem" }}>{resumo}</summary>
      {children}
    </details>
  );
}

function Item({ k, v }: { k: string; v: string }) {
  return (
    <li style={{ background: "var(--surface-2)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem" }}>
      <span style={{ ...notaStyle, display: "block" }}>{k}</span>
      <b style={{ fontSize: v.length > 14 ? "0.85rem" : "1rem" }}>{v}</b>
    </li>
  );
}

function somaDias(iso: string, dias: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + dias);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// ───────────────────────── Aplicação concluída ─────────────────────────
function Concluida({ ctx, r, canal, desfeito, onDesfeito, onFechar, onVerConcluidos }: {
  ctx: ContextoAplicar; r: ResultadoAplicar; canal: "Protocolos" | "Agenda"; desfeito: boolean;
  onDesfeito: () => void; onFechar: () => void; onVerConcluidos?: () => void;
}) {
  const ap = r.aplicacao;
  const [restante, setRestante] = useState(r.desfazer_segundos);
  const [erro, setErro] = useState<string | null>(null);
  const [desfazendo, setDesfazendo] = useState(false);
  useEffect(() => {
    if (desfeito || restante <= 0) return;
    const t = setTimeout(() => setRestante((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [restante, desfeito]);
  const aplicados = ap.animais.filter((a) => a.resultado === "aplicado");
  const nao = ap.animais.filter((a) => a.resultado === "nao_aplicado");

  async function desfazer() {
    setDesfazendo(true); setErro(null);
    try { await desfazerAplicacaoPreventiva(ap.id); onDesfeito(); }
    catch (e: any) { setErro(e.message || "Não foi possível desfazer"); setRestante(0); }
    finally { setDesfazendo(false); }
  }

  if (desfeito) {
    return (
      <div className="le-raiz" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }} role="status">
        <div className="card">
          <div className="card-header mb-2 flex items-center gap-2"><Undo2 size={16} /> Desfeito na hora</div>
          <p style={{ fontSize: "0.9rem" }}>A aplicação foi desfeita: o estoque voltou e o agendamento continua Agendado. A original fica preservada como Estornada.</p>
        </div>
        <div><button type="button" className="btn-secondary" onClick={onFechar}>Fechar</button></div>
      </div>
    );
  }
  return (
    <div className="le-raiz" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
      <div className="card" role="status">
        <div className="card-header mb-2 flex items-center gap-2"><Check size={16} /> Aplicado · {ctx.protocolo_nome} · {aplicados.length} {plural(aplicados.length, "animal", "animais")} · {dataCurta(ap.data_aplicacao)} {ap.hora || ""}</div>
        <p style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.4rem" }}>O que o sistema fez sozinho</p>
        <ul style={{ margin: 0, paddingLeft: "1.1rem", fontSize: "0.86rem", lineHeight: 1.7 }}>
          <li>{aplicados.length} {plural(aplicados.length, "aplicação registrada", "aplicações registradas")} em Sanidade (natureza preventiva).</li>
          <li>{ap.estoque_desconsiderado ? `Estoque desconsiderado (${ap.estoque_motivo}): nada foi baixado.` : `Estoque baixado: ${num(ap.dose_total)} ${unPl(ap.unidade || "", ap.dose_total || 0)}${ap.lote_texto ? ` do lote ${ap.lote_texto}` : ""}.`}</li>
          {(ap.carencia_carne_ate || ap.carencia_leite_ate) && <li>Carência: {[ap.carencia_carne_ate ? `carne até ${dataCurta(ap.carencia_carne_ate)}` : "", ap.carencia_leite_ate ? `leite até ${dataCurta(ap.carencia_leite_ate)}` : ""].filter(Boolean).join(" · ")}.</li>}
          <li>Registrado por {ap.aplicador_nome ? `${ap.aplicador_nome} (aplicador)` : "—"} pelo canal {ap.canal}.</li>
          {ap.ciencia_itens.length > 0 && <li>Ciência de {ap.ciencia_itens.length} {plural(ap.ciencia_itens.length, "item pendente", "itens pendentes")} gravada com o seu nome e a hora.</li>}
          <li>Foi para <b>Concluídos</b>{ap.excecoes.length ? `, com selo de exceção: ${ap.excecoes.join("; ")}` : ""}.</li>
        </ul>
        {r.avisos.map((a) => <p key={a} role="alert" style={{ color: "var(--amber)", fontSize: "0.82rem", marginTop: "0.4rem", display: "flex", gap: 6 }}><AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 2 }} />{a}</p>)}
      </div>
      {nao.length > 0 && (
        <div className="card">
          <div className="card-header mb-2">{nao.length} {plural(nao.length, "animal não foi aplicado", "animais não foram aplicados")}</div>
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {nao.map((n) => (
              <li key={n.numero_matriz} style={{ display: "flex", gap: "0.6rem", padding: "0.35rem 0", borderBottom: "1px solid var(--border)", fontSize: "0.85rem" }}>
                <b style={{ flex: 1 }}>{n.numero_matriz}<span style={{ ...notaStyle, display: "block", fontWeight: 400 }}>{n.motivo_nao}</span></b>
                <span style={notaStyle}>{n.destino_nao === "naoSeAplica" ? "Desconsiderado" : "Voltou à lista de espera"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}
      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "center" }}>
        {canal === "Protocolos" && onVerConcluidos && <button type="button" className="btn-primary-gold" onClick={() => { onFechar(); onVerConcluidos(); }}>Ver em Concluídos</button>}
        {restante > 0 && ap.pode_desfazer && (
          <button type="button" className="btn-secondary" disabled={desfazendo} onClick={desfazer}>
            <Undo2 size={14} /> Desfazer ({restante} s)
          </button>
        )}
        <button type="button" className="btn-ghost" onClick={onFechar}>{canal === "Agenda" ? "Voltar à Agenda" : "Voltar ao Acompanhamento"}</button>
      </div>
      {restante <= 0 && <p style={notaStyle}>Depois de 10 segundos, corrigir só pelo administrador, em Concluídos › Estornar, com motivo.</p>}
    </div>
  );
}
