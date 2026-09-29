"use client";
// Leitura do exame de tuberculina (2ª etapa do aplicar único) e o fechamento do exame na gaveta Aplicar.
// Mockup: docs/agents/auditoria-preventivo-agenda/mockups/fluxo-completo.html (proto-aplicar-dr.js, fase "leitura").
//
// Regras que a tela mostra e o servidor confere: só veterinário habilitado (CRMV) lê; resultado de cada animal
// (negativo / reagente / inconclusivo) e espessura da pele em mm; tipo de teste; leitura entre 72 e 96 h depois da
// inoculação (fora disso fica sinalizado; antes de 72 h pede justificativa); reagente gera banner persistente e
// notificação; inconclusivo agenda o reteste para 60 dias depois.
import React, { useState } from "react";
import { AlertTriangle, Check, ChevronDown, Info } from "lucide-react";
import { aplicarAgendamentoPreventivo, type AplicarAgendamentoPayload, type CanalAplicacao, type ContextoAplicar, type ResultadoAplicar, type ResultadoExame } from "@/lib/api";
import { ResumoCustoFinanceiro } from "./FinanceiroAgendamento";
import { dataHoraLocal, horasTxt, RESULTADOS_ROTULO } from "./exameComum";
import { brl, dataCurta, diaSemana, hojeIso, inputStyle, labelStyle, notaStyle, num, plural } from "./preventivoComum";

const horaAgora = () => {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};
const somaDiasIso = (iso: string, dias: number) => {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + dias);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export function FormLeitura({ ctx, canal, chave, onAplicado, onFechar }: {
  ctx: ContextoAplicar; canal: CanalAplicacao; chave: string; onAplicado: (r: ResultadoAplicar) => void; onFechar: () => void;
}) {
  const ex = ctx.exame!;
  const ino = ex.inoculacao!;
  const hoje = ctx.hoje;
  const [res, setRes] = useState<Record<string, ResultadoExame | "">>({});
  const [mm, setMm] = useState<Record<string, string>>({});
  const [tipoTeste, setTipoTeste] = useState(ino.tipo_teste || "");
  const [laudo, setLaudo] = useState("");
  const [aplicadorId, setAplicadorId] = useState(ctx.aplicador_sugerido_id ? String(ctx.aplicador_sugerido_id) : "");
  const [data, setData] = useState(hoje);
  const [hora, setHora] = useState(horaAgora());
  const [justif, setJustif] = useState("");
  const [aberto, setAberto] = useState(false);
  const [tentou, setTentou] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erroServ, setErroServ] = useState<string | null>(null);

  const pessoa = ctx.pessoas.find((p) => String(p.id) === aplicadorId);
  const inocEm = new Date(`${ino.data}T${ino.hora || "00:00"}:00`);
  const lidoEm = new Date(`${data}T${hora || "00:00"}:00`);
  const horas = (lidoEm.getTime() - inocEm.getTime()) / 36e5;
  const antes72 = !isNaN(horas) && horas >= 0 && horas < (ex.janela_leitura_horas?.[0] ?? 72);
  const depois96 = !isNaN(horas) && horas > (ex.janela_leitura_horas?.[1] ?? 96);
  const anterior = !isNaN(horas) && horas < 0;
  const numeros = ctx.animais.map((a) => a.numero_matriz);
  const respondidos = numeros.filter((n) => res[n]);
  const conta = (r: ResultadoExame) => numeros.filter((n) => res[n] === r).length;
  const mmNum = (n: string) => { const v = Number(String(mm[n] ?? "").replace(",", ".")); return mm[n] && !isNaN(v) && v >= 0 ? v : null; };
  const semMm = numeros.filter((n) => mmNum(n) == null);

  let erro = "";
  if (!aplicadorId) erro = "Escolha quem fez a leitura.";
  else if (data > hoje) erro = "A data real não pode ser futura.";
  else if (ctx.exige_veterinario && !pessoa?.veterinario) erro = `Só veterinário habilitado (CRMV) faz a leitura de ${ctx.protocolo_nome}.`;
  else if (respondidos.length < numeros.length) erro = "Informe o resultado de cada animal.";
  else if (semMm.length) erro = "Informe a espessura da pele (mm) de cada animal.";
  else if (!tipoTeste) erro = "Escolha o tipo de teste da tuberculina.";
  else if (anterior) erro = "A leitura não pode ser anterior à inoculação.";
  else if (antes72 && !justif.trim()) erro = "Leitura antes de 72 h: escreva a justificativa.";

  async function salvar() {
    setTentou(true);
    if (erro) return;
    setSalvando(true); setErroServ(null);
    const corpo: AplicarAgendamentoPayload = {
      canal, aplicador_pessoa_id: Number(aplicadorId), animais_aplicados: [], data_aplicacao: data, hora: hora || null,
      resultados: Object.fromEntries(numeros.map((n) => [n, res[n] as ResultadoExame])),
      espessuras_mm: Object.fromEntries(numeros.map((n) => [n, mmNum(n) as number])),
      tipo_teste: tipoTeste, laudo: laudo.trim() || null, justificativa_leitura: antes72 ? justif.trim() : null, chave_idempotencia: chave,
    };
    try { onAplicado(await aplicarAgendamentoPreventivo(ctx.cronograma_id, corpo)); }
    catch (e: any) { setErroServ(e.message || "Erro ao salvar a leitura"); } finally { setSalvando(false); }
  }

  const boxAviso = (cor: string, texto: React.ReactNode, icone = <AlertTriangle size={15} />) => (
    <div role="status" style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", fontSize: "0.82rem", border: `1px solid ${cor}`, borderLeft: `4px solid ${cor}`, borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem", background: "var(--surface-2)" }}>
      <span style={{ color: cor, marginTop: 2, display: "inline-flex" }}>{icone}</span><span>{texto}</span>
    </div>
  );
  const reteste = conta("inconclusivo") > 0 ? `em ${dataCurta(somaDiasIso(data, ex.reteste_dias || 60))}` : "não precisa";
  const linhaResumo = `${numeros.length} ${plural(numeros.length, "animal", "animais")} · ${conta("negativo")} negativos · ${conta("reagente")} reagentes · ${conta("inconclusivo")} inconclusivos · reteste ${reteste} · custo ${ino.custo != null ? brl(ino.custo) : "a informar"}`;

  return (
    <div className="le-raiz" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }} data-testid="form-leitura">
      <div>
        <p style={{ ...notaStyle, margin: 0 }}>Aberto de: <b>{canal === "Agenda" ? "Agenda" : canal === "Curral" ? "Curral" : "Protocolos › Acompanhamento"}</b></p>
        <h2 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--dourado-light)", marginTop: "0.3rem" }}>{ctx.protocolo_nome} · leitura</h2>
        <p style={notaStyle}>{diaSemana(ctx.data_evento)} {dataCurta(ctx.data_evento)}{ctx.hora ? ` ${ctx.hora}` : ""} · {ctx.responsavel.nome}{ctx.responsavel.crmv ? ` (${ctx.responsavel.crmv})` : ""}</p>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {boxAviso("var(--dourado-light)", <>Inoculação em <b>{dataCurta(ino.data)} {ino.hora || ""}</b> · <b>leitura a partir de {dataHoraLocal(ex.leitura_prevista_em)}</b> (72 h) e até {dataHoraLocal(ex.leitura_limite_em)}. Tuberculina: frasco {ino.lote_texto || "—"}. Resultado reagente grava o reagente, mostra o aviso persistente e bloqueia o comprovante “animal em dia” só para ele.</>, <Info size={15} />)}
        {ctx.exige_veterinario && !pessoa?.veterinario && boxAviso("var(--red)", <><b>{ctx.protocolo_nome}: só veterinário habilitado (CRMV) faz a leitura.</b> Escolha o veterinário em “Quem fez a leitura”.</>)}
        {depois96 && boxAviso("var(--amber)", <><b>Leitura fora da janela de 72–96 h</b> ({horasTxt(horas)} após a inoculação). Fica sinalizado no registro.</>)}
        {antes72 && boxAviso("var(--amber)", <><b>Leitura antes de 72 h da inoculação.</b> Escreva a justificativa; ela fica registrada.</>)}
        {anterior && boxAviso("var(--red)", "A data e a hora da leitura são anteriores à inoculação.")}
      </div>

      <details className="card" open={aberto} onToggle={(e) => setAberto((e.currentTarget as HTMLDetailsElement).open)} style={{ padding: "0.6rem 0.9rem" }}>
        <summary style={{ cursor: "pointer", display: "flex", flexDirection: "column", gap: 2, listStyle: "none" }}>
          <span style={{ ...labelStyle, marginBottom: 0, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em" }}>O que acontece ao salvar a leitura</span>
          <span style={{ fontSize: "0.86rem", fontWeight: 600 }}>{linhaResumo}</span>
          <span style={{ ...notaStyle, display: "inline-flex", alignItems: "center", gap: 3 }}><ChevronDown size={13} />Detalhes</span>
        </summary>
        <p style={{ ...notaStyle, marginTop: "0.6rem" }}>Cada resultado vira uma linha em Sanidade › Exames; reagente fica “a descartar”, sai dos demais agendamentos (ex.: aftosa) e pede a notificação ao serviço veterinário oficial; inconclusivo volta para a lista de espera em {ex.reteste_dias || 60} dias. O registro vai para <b>Concluídos</b> como “Exame realizado”.</p>
        {ctx.financeiro && <div style={{ marginTop: "0.6rem" }}><ResumoCustoFinanceiro bloco={{ ...ctx.financeiro, custo_motivo: null }} custo={ino.custo} rotuloCusto="Custo (da inoculação)" /></div>}
      </details>

      <div>
        <span style={labelStyle}>Resultado por animal (obrigatório)</span>
        <div className="card" style={{ padding: "0.3rem 0.8rem" }}>
          {ctx.animais.map((a) => (
            <div key={a.numero_matriz} style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap", borderBottom: "1px solid var(--border)", padding: "0.5rem 0" }}>
              <span style={{ flex: "1 1 160px", minWidth: 0 }}>
                <b>{a.numero_matriz}{a.nome ? ` ${a.nome}` : ""}</b>
                <span style={{ ...notaStyle, display: "block" }}>{a.lote || "Sem lote"}{a.origem === "fora_janela" ? " · fora da janela" : ""}</span>
              </span>
              <select style={{ ...inputStyle, width: 160, minHeight: 40 }} aria-label={`Resultado de ${a.numero_matriz}`} value={res[a.numero_matriz] || ""}
                      onChange={(e) => setRes((p) => ({ ...p, [a.numero_matriz]: e.target.value as ResultadoExame | "" }))}>
                <option value="">Escolha</option>
                {ex.resultados.map((r) => <option key={r} value={r}>{RESULTADOS_ROTULO[r]}</option>)}
              </select>
              <input inputMode="decimal" style={{ ...inputStyle, width: 100, minHeight: 40 }} placeholder="mm" aria-label={`Espessura da pele de ${a.numero_matriz} (mm)`}
                     value={mm[a.numero_matriz] || ""} onChange={(e) => setMm((p) => ({ ...p, [a.numero_matriz]: e.target.value }))} />
            </div>
          ))}
        </div>
        <p style={{ ...notaStyle, marginTop: "0.3rem" }}>
          Espessura da pele em milímetros, medida na leitura, para cada animal.{" "}
          <button type="button" className="btn-ghost" style={{ padding: 0, border: "none", textDecoration: "underline" }}
                  onClick={() => setRes(Object.fromEntries(numeros.map((n) => [n, "negativo" as ResultadoExame])))}>Marcar todos negativos</button>
          {" "}({respondidos.length}/{numeros.length} com resultado)
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label htmlFor="ex-tt" style={labelStyle}>Tipo de teste (obrigatório)</label>
          <select id="ex-tt" style={inputStyle} value={tipoTeste} onChange={(e) => setTipoTeste(e.target.value)}>
            <option value="">Escolha</option>
            {ex.tipos_teste.map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="ex-laudo" style={labelStyle}>Nº do laudo (opcional)</label>
          <input id="ex-laudo" style={inputStyle} value={laudo} onChange={(e) => setLaudo(e.target.value)} />
        </div>
      </div>

      <div>
        <label htmlFor="ex-quem" style={labelStyle}>Quem fez a leitura</label>
        <select id="ex-quem" style={inputStyle} value={aplicadorId} onChange={(e) => setAplicadorId(e.target.value)}>
          <option value="">Escolha quem fez a leitura</option>
          {ctx.pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.veterinario ? "veterinário" : (p.tipo || "pessoa").toLowerCase()}{p.crmv ? `, ${p.crmv}` : ""})</option>)}
        </select>
        {!aplicadorId && <span style={notaStyle}>Obrigatório: escolha quem fez a leitura para liberar o botão.</span>}
      </div>

      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend style={{ ...labelStyle, marginBottom: "0.3rem" }}>Data e hora da leitura</legend>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
          <input type="date" style={{ ...inputStyle, width: "auto" }} aria-label="Data da leitura" value={data} max={hoje || hojeIso()} onChange={(e) => setData(e.target.value)} />
          <input type="time" style={{ ...inputStyle, width: "auto" }} aria-label="Hora da leitura" value={hora} onChange={(e) => setHora(e.target.value)} />
        </div>
      </fieldset>
      {antes72 && (
        <div>
          <label htmlFor="ex-just" style={labelStyle}>Justificativa da leitura antes de 72 h (obrigatória)</label>
          <input id="ex-just" style={inputStyle} value={justif} onChange={(e) => setJustif(e.target.value)} />
        </div>
      )}

      {tentou && erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}
      {erroServ && <p role="alert" style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erroServ}</p>}

      <div style={{ position: "sticky", bottom: "-0.9rem", margin: "0 -0.9rem -0.9rem", padding: "0.75rem 0.9rem", background: "var(--surface)", borderTop: "1px solid var(--border)", display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap", zIndex: 2 }}>
        <button type="button" id="ap-ok" className="btn-primary-gold" aria-disabled={!!erro || salvando} disabled={salvando || !aplicadorId} title={!aplicadorId ? "Escolha quem fez a leitura" : undefined} onClick={salvar}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar leitura"}
        </button>
        <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
        <span id="ap-erro" role="status" style={{ ...notaStyle, color: "var(--amber)", flex: "1 1 200px" }}>{erro}</span>
      </div>
    </div>
  );
}
