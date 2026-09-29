"use client";
// Peças do fluxo de EXAME no aplicar único (fatia 9b): banner persistente de reagentes (com o registro da
// notificação: quem/quando), comprovante (bloqueado só para o reagente) e rótulos de fase.
// Mockup: docs/agents/auditoria-preventivo-agenda/mockups/fluxo-completo.html (proto-aplicar-dr.js, proto-concl.js).
import React, { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, Bell, Check, ChevronDown, Lock, Printer, X } from "lucide-react";
import {
  fetchComprovanteAplicacao, fetchReagentes, notificarReagente, type ComprovanteAplicacao, type FaseExame, type ReagenteItem,
} from "@/lib/api";
import { dataCurta, dataHoraCurta, inputStyle, labelStyle, notaStyle, num, Pill, plural } from "./preventivoComum";

export const RESULTADOS_ROTULO: Record<string, string> = {
  negativo: "Negativo", reagente: "Reagente", inconclusivo: "Inconclusivo", coletado: "Coletado",
};
export const FASE_ROTULO: Record<FaseExame, string> = { inoculacao: "Inoculação", leitura: "Leitura (72 h)", coleta: "Coleta" };
export const VERBO_APLICAR: Record<FaseExame, string> = { inoculacao: "Inocular", leitura: "Registrar leitura", coleta: "Registrar coleta" };

/** Data e hora locais de um instante ISO sem fuso ("2026-10-02T08:30:00"). */
export function dataHoraLocal(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [d, h] = iso.split("T");
  return `${dataCurta(d)} ${(h || "").slice(0, 5)}`.trim();
}

export function horasTxt(h: number | null | undefined): string {
  return h == null ? "—" : `${num(Math.round(h), 0)} h`;
}

// ───────────────────────── banner persistente de reagentes ─────────────────────────
/** Banner que NÃO some depois de notificado: enquanto o reagente estiver no rebanho, o aviso fica, com o registro
 * de quem notificou e quando. `aplicacaoId` restringe aos reagentes de um registro (tela de fechamento da leitura). */
export function BannerReagentes({ aplicacaoId, onMudou, recarga = 0 }: { aplicacaoId?: number; onMudou?: () => void; recarga?: number }) {
  const [itens, setItens] = useState<ReagenteItem[] | null>(null);
  const [aberto, setAberto] = useState<boolean | null>(null);
  const [notificando, setNotificando] = useState<string | null>(null);
  const [ref, setRef] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(() => {
    fetchReagentes().then((d) => setItens(aplicacaoId ? d.itens.filter((i) => i.aplicacao_id === aplicacaoId) : d.itens)).catch(() => setItens([]));
  }, [aplicacaoId]);
  useEffect(() => { carregar(); }, [carregar, recarga]);

  if (!itens || !itens.length) return null;
  const pend = itens.filter((i) => i.pendente_notificacao);
  const abre = aberto ?? pend.length > 0;

  async function registrar(i: ReagenteItem) {
    setSalvando(true); setErro(null);
    try {
      await notificarReagente(i.aplicacao_id, [i.numero_matriz], ref.trim() || null);
      setNotificando(null); setRef(""); carregar(); onMudou?.();
    } catch (e: any) { setErro(e.message || "Não foi possível registrar a notificação"); } finally { setSalvando(false); }
  }

  return (
    <section role="alert" aria-label="Animais reagentes" data-testid="banner-reagentes"
             style={{ border: "1px solid var(--red)", borderLeft: "4px solid var(--red)", borderRadius: "var(--r-sm)", background: "var(--surface-2)", padding: "0.6rem 0.9rem", marginBottom: "0.9rem" }}>
      <button type="button" onClick={() => setAberto(!abre)} aria-expanded={abre}
              style={{ display: "flex", gap: "0.6rem", alignItems: "center", width: "100%", background: "transparent", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left", padding: 0, minHeight: 36 }}>
        <AlertTriangle size={18} style={{ color: "var(--red)", flexShrink: 0 }} />
        <span style={{ flex: 1, fontWeight: 700, fontSize: "0.9rem" }}>
          {itens.length} {plural(itens.length, "animal reagente", "animais reagentes")} em exame
          <span style={{ ...notaStyle, display: "block", fontWeight: 400 }}>
            {pend.length > 0 ? `${pend.length} ${plural(pend.length, "notificação pendente", "notificações pendentes")} ao serviço veterinário oficial` : "Notificação ao serviço veterinário oficial registrada — o aviso fica enquanto o animal estiver no rebanho"}
          </span>
        </span>
        <ChevronDown size={16} style={{ transform: abre ? "rotate(180deg)" : "none", transition: "transform .15s" }} />
      </button>
      {abre && (
        <ul style={{ listStyle: "none", margin: "0.6rem 0 0", padding: 0 }}>
          {itens.map((i) => (
            <li key={`${i.aplicacao_id}-${i.numero_matriz}`} style={{ padding: "0.5rem 0", borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "center" }}>
                <b style={{ fontSize: "0.9rem" }}>{i.numero_matriz}{i.nome ? ` ${i.nome}` : ""}</b>
                <span style={notaStyle}>{i.lote || "Sem lote"} · {i.protocolo_nome} · leitura {dataCurta(i.data)}{i.laudo ? ` · laudo ${i.laudo}` : ""}{i.espessura_mm != null ? ` · ${num(i.espessura_mm)} mm` : ""}</span>
                <span style={{ flex: 1 }} />
                {i.pendente_notificacao ? (
                  <>
                    <Pill cor="var(--red)"><Bell size={12} />Notificação pendente</Pill>
                    <button type="button" className="btn-secondary" style={{ minHeight: 36 }} onClick={() => { setNotificando(notificando === i.numero_matriz ? null : i.numero_matriz); setErro(null); }}>
                      Registrar notificação
                    </button>
                  </>
                ) : (
                  <Pill cor="var(--green-light)" title={i.notificacao_ref || undefined}><Check size={12} />Notificado por {i.notificado_por || "—"} em {dataHoraCurta(i.notificado_em)}</Pill>
                )}
              </div>
              {!i.pendente_notificacao && i.notificacao_ref && <span style={notaStyle}>Referência: {i.notificacao_ref}</span>}
              {notificando === i.numero_matriz && i.pendente_notificacao && (
                <div className="card" style={{ padding: "0.7rem 0.9rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  <label htmlFor={`nt-${i.numero_matriz}`} style={labelStyle}>Órgão e/ou nº do protocolo (opcional)</label>
                  <input id={`nt-${i.numero_matriz}`} style={inputStyle} value={ref} placeholder="ex.: serviço veterinário estadual · protocolo 2026/8891" onChange={(e) => setRef(e.target.value)} />
                  <p style={notaStyle}>Grava quem registrou e a hora. A notificação em si é feita ao serviço veterinário oficial; aqui fica o registro.</p>
                  {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button type="button" className="btn-primary-gold" disabled={salvando} onClick={() => registrar(i)}><Check size={14} /> {salvando ? "Registrando…" : "Confirmar notificação"}</button>
                    <button type="button" className="btn-ghost" onClick={() => setNotificando(null)}>Cancelar</button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ───────────────────────── comprovante (visão de impressão) ─────────────────────────
/** Comprovante de vacina/exame em tela cheia, pronto para imprimir. Reagente não recebe o “animal em dia”; os negativos
 * emitem normalmente. Estornado ou todos reagentes: bloqueado (o servidor recusa com 409). */
export function ComprovanteAplicacaoView({ aplicacaoId, onFechar }: { aplicacaoId: number; onFechar: () => void }) {
  const [c, setC] = useState<ComprovanteAplicacao | null>(null);
  const [bloqueio, setBloqueio] = useState<string | null>(null);
  const [montado, setMontado] = useState(false);
  useEffect(() => { setMontado(true); }, []);
  useEffect(() => { fetchComprovanteAplicacao(aplicacaoId).then(setC).catch((e) => setBloqueio(e.message || "Comprovante indisponível")); }, [aplicacaoId]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onFechar(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onFechar]);
  if (!montado) return null;
  const exame = c?.tipo === "exame";
  return createPortal(
    <div className="cp-root" role="dialog" aria-modal="true" aria-label="Comprovante" data-testid="comprovante"
         style={{ position: "fixed", inset: 0, zIndex: 90, background: "var(--bg, #111)", overflow: "auto", padding: "1rem" }}>
      <style>{`@media print { body > *:not(.cp-root) { display: none !important; } .cp-root { position: static !important; background: #fff !important; padding: 0 !important; } .cp-bar { display: none !important; } .cp-paper { box-shadow: none !important; border: none !important; } }`}</style>
      <div className="cp-bar" style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap", maxWidth: 860, margin: "0 auto 0.8rem" }}>
        <b style={{ flex: 1, color: "var(--text)" }}>Comprovante{c ? ` · ${c.protocolo_nome}` : ""}</b>
        <button type="button" className="btn-primary-gold" onClick={() => window.print()} disabled={!c}><Printer size={14} /> Imprimir</button>
        <button type="button" className="btn-ghost" onClick={onFechar} data-first><X size={14} /> Fechar</button>
      </div>
      {bloqueio && (
        <div className="card" role="alert" style={{ maxWidth: 860, margin: "0 auto", padding: "1rem", display: "flex", gap: "0.6rem", alignItems: "flex-start" }}>
          <Lock size={18} style={{ color: "var(--red)", flexShrink: 0, marginTop: 2 }} />
          <div><b>Comprovante bloqueado</b><p style={{ ...notaStyle, marginTop: 4 }}>{bloqueio}</p></div>
        </div>
      )}
      {c && (
        <article className="cp-paper" style={{ maxWidth: 860, margin: "0 auto", background: "#fff", color: "#1a1a1a", borderRadius: 6, padding: "1.4rem 1.6rem", fontSize: "0.92rem", lineHeight: 1.5, boxShadow: "0 2px 14px rgba(0,0,0,.35)" }}>
          <h2 style={{ fontSize: "1.15rem", fontWeight: 700, marginBottom: "0.4rem" }}>Comprovante de {exame ? "exame" : "aplicação"} — {c.protocolo_nome}</h2>
          <p>{c.fazenda_nome || "Fazenda"} · {dataCurta(c.data)} {c.hora || ""} · {exame && c.fase === "leitura" ? "Leitura feita por" : "Aplicador"}: {c.aplicador_nome || "—"}{c.aplicador_crmv ? ` (${c.aplicador_crmv})` : ""} · Registrado por: {c.registrado_por || "—"}</p>
          <p>Agendamento: {c.agendamento} · Canal: {c.canal}{c.retroativo ? " · Lançamento retroativo" : ""}</p>
          <p>
            {c.fornecido_pelo_veterinario ? `Frasco fornecido pelo veterinário${c.lote_texto ? `: ${c.lote_texto}` : ""}` : `Frasco/lote: ${c.lote_texto || "—"}`}
            {c.validade ? ` · val. ${dataCurta(c.validade)}` : ""}{c.via ? ` · Via: ${c.via}` : ""}{c.custo != null ? ` · Custo do registro: ${c.custo.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}` : ""}
          </p>
          {exame && c.inoculacao && <p>Inoculação: {dataCurta(c.inoculacao.data)} {c.inoculacao.hora || ""} · Leitura: {c.leitura ? `${dataCurta(c.leitura.data)} ${c.leitura.hora || ""}` : "—"}{c.leitura?.horas != null ? ` (${horasTxt(c.leitura.horas)} após a inoculação${c.leitura.fora_janela ? ", fora da janela de 72–96 h" : ""})` : ""} · Nº do laudo: {c.laudo || "não informado"}</p>}
          {exame && !c.inoculacao && <p>Coleta: {dataCurta(c.data)} {c.hora || ""} · Nº do laudo: {c.laudo || "não informado"}</p>}
          {exame && c.tipo_teste && <p>Tipo de teste: {c.tipo_teste}</p>}
          {c.excecoes.length > 0 && <p style={{ color: "#b3261e" }}><b>Exceções registradas:</b> {c.excecoes.join("; ")}</p>}
          {(c.carencia_carne_ate || c.carencia_leite_ate) && <p>Carência: {[c.carencia_carne_ate ? `carne até ${dataCurta(c.carencia_carne_ate)}` : "", c.carencia_leite_ate ? `leite até ${dataCurta(c.carencia_leite_ate)}` : ""].filter(Boolean).join(" · ")}</p>}
          <table style={{ width: "100%", borderCollapse: "collapse", margin: "0.8rem 0", fontSize: "0.86rem" }}>
            <thead><tr>{["Animal", "Lote", exame ? "Resultado" : "Dose", "Origem"].map((h) => <th key={h} style={{ textAlign: "left", borderBottom: "2px solid #333", padding: "0.3rem 0.4rem" }}>{h}</th>)}</tr></thead>
            <tbody>
              {c.animais.map((a) => (
                <tr key={a.numero_matriz}>
                  <td style={{ padding: "0.3rem 0.4rem", borderBottom: "1px solid #ccc" }}>{a.numero_matriz}{a.nome ? ` ${a.nome}` : ""}</td>
                  <td style={{ padding: "0.3rem 0.4rem", borderBottom: "1px solid #ccc" }}>{a.lote || "—"}</td>
                  <td style={{ padding: "0.3rem 0.4rem", borderBottom: "1px solid #ccc" }}>
                    {exame ? `${RESULTADOS_ROTULO[a.resultado || ""] || a.resultado || "—"}${a.espessura_mm != null ? ` · ${num(a.espessura_mm)} mm` : ""}${a.reteste_em ? ` · reteste em ${dataCurta(a.reteste_em)}` : ""}` : (a.dose != null ? `${num(a.dose)} ${a.unidade || ""}` : "—")}
                  </td>
                  <td style={{ padding: "0.3rem 0.4rem", borderBottom: "1px solid #ccc" }}>{a.origem === "fora_janela" ? "Fora da janela" : "Na janela"}</td>
                </tr>
              ))}
              {c.bloqueados.map((b) => (
                <tr key={b.numero_matriz}>
                  <td style={{ padding: "0.3rem 0.4rem", borderBottom: "1px solid #ccc" }}>{b.numero_matriz}{b.nome ? ` ${b.nome}` : ""}</td>
                  <td style={{ padding: "0.3rem 0.4rem", borderBottom: "1px solid #ccc" }}>{b.lote || "—"}</td>
                  <td colSpan={2} style={{ padding: "0.3rem 0.4rem", borderBottom: "1px solid #ccc", color: "#b3261e", fontWeight: 700 }}>REAGENTE: sem comprovante “animal em dia” para este animal</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ display: "flex", gap: "3rem", marginTop: "2.2rem" }}>
            <div style={{ flex: 1, borderTop: "1px solid #333", paddingTop: 4 }}>{exame && c.fase === "leitura" ? "Veterinário responsável pela leitura" : "Aplicador"}</div>
            <div style={{ flex: 1, borderTop: "1px solid #333", paddingTop: 4 }}>Responsável técnico</div>
          </div>
        </article>
      )}
    </div>,
    document.body,
  );
}
