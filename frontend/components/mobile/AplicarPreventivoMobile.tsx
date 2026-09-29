"use client";
// APLICAR do preventivo no app do curral/mobile — usa o endpoint ÚNICO POST /sanidade/cronogramas/{id}/aplicar (o mesmo de
// Protocolos › Acompanhamento e da Agenda do site), com canal "Curral" (Modo Curral) ou "Agenda" (Agenda do app).
// Substitui o caminho antigo (POST /agenda/realizados com id cronograma_sanitario_aplicar_*), que não gravava em
// Concluídos nem no log. Fatia 9b, item B do planejamento unificado.
//
// Peão: o 1º toque abre o cartão; escolher quem aplicou é UM toque (sem digitar, aplicador obrigatório); "Aplicar" é um
// botão grande. Sem estoque cadastrado, um segundo toque usa o frasco do veterinário. Funciona offline: o pedido entra
// na fila com a mesma chave de idempotência (reenvio nunca duplica).
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Check, ShieldAlert, Undo2 } from "lucide-react";
import { desfazerAplicacaoPreventiva, fetchReagentes, type CanalAplicacao, type FaseExame, type Reagentes } from "@/lib/api";
import { enviarOuEnfileirar } from "@/lib/offline";

export type AplicadorMob = { id: number; nome: string; crmv?: string | null; veterinario: boolean };
export type EventoAplicarMob = {
  id: string; cronograma_id?: number | null; descricao: string; animais?: string[] | null;
  checklist_total?: number; checklist_resolvidos?: number; fase?: FaseExame | null; tipo_protocolo?: string | null;
  exige_veterinario?: boolean; aplicadores?: AplicadorMob[]; aplicador_sugerido_id?: number | null;
};

const MOTIVOS = ["Vendido", "Doente", "Não localizado"] as const;
const CHAVE_ULTIMO = "aplicador_curral";
const novaChave = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `mob-${Date.now()}-${Math.random().toString(16).slice(2)}`);
const horaAgora = () => { const d = new Date(); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
const hojeLocal = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const lerUltimo = (): number | null => { try { const v = localStorage.getItem(CHAVE_ULTIMO); return v ? Number(v) : null; } catch { return null; } };
const guardarUltimo = (id: number) => { try { localStorage.setItem(CHAVE_ULTIMO, String(id)); } catch { /* sem armazenamento: segue */ } };

export function AplicarPreventivoMobile({ e, canal, onFeito, onErro }: {
  e: EventoAplicarMob; canal: CanalAplicacao; onFeito?: (msg: string, offline: boolean) => void; onErro?: (msg: string) => void;
}) {
  const animais = e.animais || [];
  const todos = e.aplicadores || [];
  const lista = e.exige_veterinario ? todos.filter((p) => p.veterinario) : todos;
  const pend = Math.max(0, (e.checklist_total ?? 0) - (e.checklist_resolvidos ?? 0));
  const [quem, setQuem] = useState<number | null>(null);
  const [deFora, setDeFora] = useState(false);
  const [marc, setMarc] = useState<Set<string>>(() => new Set(animais));
  const [motivo, setMotivo] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [semEstoque, setSemEstoque] = useState(false);
  const [feito, setFeito] = useState<{ aplicacaoId: number | null; offline: boolean } | null>(null);
  const [restante, setRestante] = useState(0);
  const [desfeito, setDesfeito] = useState(false);
  const chave = useRef(novaChave());

  // Já vem escolhido quem aplicou: o veterinário do agendamento, ou quem aplicou por último neste aparelho.
  useEffect(() => {
    if (quem != null) return;
    const ids = new Set(lista.map((p) => p.id));
    const sug = e.aplicador_sugerido_id && ids.has(e.aplicador_sugerido_id) ? e.aplicador_sugerido_id : null;
    const ult = lerUltimo();
    setQuem(sug ?? (ult && ids.has(ult) ? ult : lista.length === 1 ? lista[0].id : null));
  }, [lista.length]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!feito || feito.offline || desfeito || restante <= 0) return;
    const t = setTimeout(() => setRestante((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [feito, restante, desfeito]);

  const fase = e.fase || null;
  const rotuloBotao = (n: number) => fase === "inoculacao" ? `Inoculei (${n})` : fase === "coleta" ? `Coletei (${n})` : `Aplicar (${n} ${n === 1 ? "animal" : "animais"})`;
  const aplicados = animais.filter((n) => marc.has(n));
  const fora = animais.filter((n) => !marc.has(n));
  const faltaMotivo = fora.some((n) => !motivo[n]);
  const bloqueio = !e.cronograma_id ? "Agendamento sem identificação — abra na Agenda completa."
    : !lista.length ? (e.exige_veterinario ? "Nenhum veterinário (CRMV) cadastrado: só o veterinário aplica este protocolo." : "Nenhuma pessoa cadastrada para aplicar.")
    : quem == null ? "Escolha quem aplicou."
    : !aplicados.length ? "Marque pelo menos 1 animal."
    : faltaMotivo ? "Escolha o motivo de cada animal que ficou de fora."
    : "";

  async function enviar(frascoVet = false) {
    if (bloqueio || salvando || quem == null || !e.cronograma_id) return;
    setSalvando(true); setErro(null); setSemEstoque(false);
    const corpo: Record<string, unknown> = {
      canal, aplicador_pessoa_id: quem, animais_aplicados: aplicados, data_aplicacao: hojeLocal(), hora: horaAgora(),
      nao_aplicados: fora.map((n) => ({ numero_matriz: n, motivo: motivo[n], destino: "espera" })),
      ciencia_pendentes: pend > 0, ciencia_motivo: pend > 0 ? "Aplicado no curral (app)" : null, chave_idempotencia: chave.current,
    };
    if (frascoVet) { corpo.desconsiderar_estoque = true; corpo.motivo_desconsiderar_estoque = "Frasco do veterinário"; }
    try {
      guardarUltimo(quem);
      const r = await enviarOuEnfileirar(`/sanidade/cronogramas/${e.cronograma_id}/aplicar`, corpo, `${fase === "inoculacao" ? "Inocular" : fase === "coleta" ? "Coletar" : "Aplicar"} ${e.descricao}`, "POST");
      const aplicacaoId: number | null = r.enviado ? (r.resposta?.aplicacao?.id ?? null) : null;
      setFeito({ aplicacaoId, offline: !r.enviado });
      setRestante(r.enviado ? Number(r.resposta?.desfazer_segundos ?? 10) : 0);
      onFeito?.(r.enviado ? (fase === "inoculacao" ? "Inoculação registrada · leitura em 72 h." : "Aplicação registrada.") : "Guardado — será enviado quando conectar.", !r.enviado);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Não foi possível salvar.";
      if (/não está no estoque/i.test(msg)) setSemEstoque(true);
      setErro(msg); onErro?.(msg);
    } finally { setSalvando(false); }
  }

  async function desfazer() {
    if (!feito?.aplicacaoId) return;
    setSalvando(true);
    try { await desfazerAplicacaoPreventiva(feito.aplicacaoId); setDesfeito(true); }
    catch (err) { setErro(err instanceof Error ? err.message : "Não foi possível desfazer."); setRestante(0); }
    finally { setSalvando(false); }
  }

  if (fase === "leitura") {
    return (
      <div data-testid="mob-leitura" style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
        <p style={{ fontSize: "1rem", lineHeight: 1.45 }}><b>Leitura da tuberculina.</b> O resultado de cada animal (negativo, reagente ou inconclusivo) e a espessura da pele são registrados pelo veterinário no site, em Protocolos › Acompanhamento.</p>
        <Link href="/protocolos?aba=acompanhamento" className="mob-btn mob-btn-sec" style={{ textDecoration: "none" }}>Abrir Protocolos no site</Link>
      </div>
    );
  }

  if (feito) {
    return (
      <div role="status" data-testid="mob-aplicado" style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
        {desfeito ? (
          <p style={{ fontSize: "1rem", fontWeight: 700 }}><Undo2 size={16} style={{ display: "inline", marginRight: 6 }} />Desfeito. O agendamento continua Agendado.</p>
        ) : (
          <>
            <p style={{ fontSize: "1.05rem", fontWeight: 800, color: "var(--mob-verde)", display: "flex", alignItems: "center", gap: 8 }}>
              <Check size={20} strokeWidth={3} /> {feito.offline ? "Guardado — será enviado quando conectar" : fase === "inoculacao" ? "Inoculação registrada · leitura em 72 h" : "Registrado em Concluídos"}
            </p>
            {restante > 0 && feito.aplicacaoId && (
              <button type="button" className="mob-btn mob-btn-sec" disabled={salvando} onClick={desfazer}><Undo2 size={18} /> Desfazer ({restante} s)</button>
            )}
          </>
        )}
        {erro && <p role="alert" style={{ color: "var(--mob-vermelho)", fontSize: "0.9rem" }}>{erro}</p>}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }} data-testid="mob-aplicar">
      <div>
        <p style={{ fontSize: "0.95rem", fontWeight: 700, margin: "0 0 0.4rem" }}>Quem {fase === "coleta" ? "coletou" : fase === "inoculacao" ? "inoculou" : "aplicou"}?</p>
        <div role="radiogroup" aria-label="Quem aplicou" style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
          {lista.map((p) => {
            const ativo = quem === p.id;
            return (
              <button key={p.id} type="button" role="radio" aria-checked={ativo} onClick={() => setQuem(p.id)}
                      style={{ minHeight: 56, padding: "0.6rem 1rem", borderRadius: "var(--r-app)", cursor: "pointer", fontSize: "1rem", fontWeight: ativo ? 800 : 600,
                               border: `2px solid ${ativo ? "var(--mob-verde)" : "var(--mob-border)"}`, background: ativo ? "color-mix(in srgb, var(--mob-verde) 16%, transparent)" : "var(--mob-surface)", color: "var(--mob-text)" }}>
                {ativo && <Check size={16} style={{ display: "inline", marginRight: 6 }} />}{p.nome}{p.veterinario ? " (vet)" : ""}
              </button>
            );
          })}
        </div>
        {e.exige_veterinario && <p style={{ fontSize: "0.85rem", color: "var(--mob-muted)", margin: "0.4rem 0 0" }}><ShieldAlert size={14} style={{ display: "inline", marginRight: 4 }} />Só veterinário habilitado (CRMV) aplica este protocolo.</p>}
      </div>

      {pend > 0 && <p style={{ fontSize: "0.88rem", color: "var(--mob-ambar)" }}>Checklist com {pend} {pend === 1 ? "item pendente" : "itens pendentes"}: aplicar não é bloqueado; a ciência fica registrada.</p>}

      {deFora && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {animais.map((n) => (
            <div key={n} style={{ borderBottom: "1px solid var(--mob-border)", padding: "0.3rem 0" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "0.7rem", minHeight: 56, cursor: "pointer", fontWeight: 800, fontSize: "1.05rem" }}>
                <input type="checkbox" checked={marc.has(n)} onChange={() => setMarc((p) => { const s = new Set(p); if (s.has(n)) s.delete(n); else s.add(n); return s; })}
                       style={{ width: 26, height: 26 }} aria-label={`Aplicado em ${n}`} />
                {n}
              </label>
              {!marc.has(n) && (
                <div role="radiogroup" aria-label={`Motivo de ${n}`} style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", padding: "0 0 0.4rem 2.4rem" }}>
                  {MOTIVOS.map((m) => (
                    <button key={m} type="button" role="radio" aria-checked={motivo[n] === m} onClick={() => setMotivo((p) => ({ ...p, [n]: m }))}
                            style={{ minHeight: 48, padding: "0.4rem 0.9rem", borderRadius: 999, fontSize: "0.95rem", cursor: "pointer", fontWeight: motivo[n] === m ? 800 : 600,
                                     border: `2px solid ${motivo[n] === m ? "var(--mob-ambar)" : "var(--mob-border)"}`, background: "var(--mob-surface)", color: "var(--mob-text)" }}>{m}</button>
                  ))}
                </div>
              )}
            </div>
          ))}
          <p style={{ fontSize: "0.82rem", color: "var(--mob-muted)" }}>Quem ficar de fora volta para a lista de espera, com o motivo.</p>
        </div>
      )}

      {erro && (
        <div role="alert" style={{ color: "var(--mob-vermelho)", fontSize: "0.92rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <span style={{ display: "flex", gap: 6 }}><AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />{erro}</span>
          {semEstoque && <button type="button" className="mob-btn mob-btn-sec" disabled={salvando || !!bloqueio} onClick={() => enviar(true)}>Usar frasco do veterinário (sem baixar estoque)</button>}
        </div>
      )}

      <button type="button" className="mob-btn" data-testid="mob-aplicar-ok" disabled={salvando || !!bloqueio} onClick={() => enviar(false)} aria-describedby={bloqueio ? "mob-aplicar-bloqueio" : undefined}>
        <Check size={20} strokeWidth={3} /> {salvando ? "Salvando…" : rotuloBotao(aplicados.length)}
      </button>
      {bloqueio && <p id="mob-aplicar-bloqueio" style={{ fontSize: "0.88rem", color: "var(--mob-muted)", margin: 0 }}>{bloqueio}</p>}
      {animais.length > 1 && (
        <button type="button" className="mob-btn mob-btn-sec" onClick={() => setDeFora((v) => !v)}>{deFora ? "Aplicar em todos" : "Algum animal ficou de fora?"}</button>
      )}
    </div>
  );
}

/** Aviso de reagente no app: fica enquanto o animal estiver no rebanho; a notificação se registra no site. */
export function AvisoReagentesMobile() {
  const [d, setD] = useState<Reagentes | null>(null);
  useEffect(() => { fetchReagentes().then(setD).catch(() => setD(null)); }, []);
  if (!d || !d.total) return null;
  return (
    <section role="alert" data-testid="mob-reagentes" style={{ margin: "0 0 0.9rem", padding: "0.8rem 0.9rem", borderRadius: "var(--r-app)", border: "2px solid var(--mob-vermelho)", background: "color-mix(in srgb, var(--mob-vermelho) 10%, transparent)" }}>
      <p style={{ fontWeight: 800, fontSize: "1rem", display: "flex", gap: 8, alignItems: "center", margin: 0 }}>
        <AlertTriangle size={20} style={{ color: "var(--mob-vermelho)" }} /> {d.total} {d.total === 1 ? "animal reagente" : "animais reagentes"} em exame
      </p>
      <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.1rem", fontSize: "0.95rem", lineHeight: 1.6 }}>
        {d.itens.map((i) => (
          <li key={`${i.aplicacao_id}-${i.numero_matriz}`}>
            <b>{i.numero_matriz}</b> · {i.protocolo_nome} · {i.pendente_notificacao ? <b style={{ color: "var(--mob-vermelho)" }}>notificar o serviço veterinário oficial</b> : `notificado por ${i.notificado_por || "—"}`}
          </li>
        ))}
      </ul>
      <p style={{ fontSize: "0.82rem", color: "var(--mob-muted)", margin: "0.4rem 0 0" }}>O registro da notificação é feito no site (Protocolos › Concluídos). Este aviso fica enquanto o animal estiver no rebanho.</p>
    </section>
  );
}
