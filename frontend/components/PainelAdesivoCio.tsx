"use client";
// Parâmetros › Reinseminação e observação de cio — o painel do adesivo de detecção de cio de repasse. É a ÚNICA tela que
// edita essa regra (antes ela ficava escondida em Lançamentos › Calendário sanitário): chave mestra, aviso na Agenda
// (vazio = não avisar), produtos vinculados do estoque e a janela da lista "Observação de cio". Quem decide o que cada
// chave faz é o backend (rules/repasse.py): desligada, não há aviso de aplicação, a lista "Observação de cio" some e o
// diagnóstico não oferece o método "Cio de repasse".
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, Loader2, Plus, X } from "lucide-react";
import { atualizarParametro, ehAdmin, fetchRepasseConfig, fetchRepasseProdutos, salvarRepasseConfig, type RepasseConfig } from "@/lib/api";

type ParamItem = { chave: string; valor: number | string | boolean | null };
type Form = { usar: boolean; avisar: string; ids: number[]; repetir: boolean; cada: string; repeticoes: string; quem: RepasseConfig["quem_entra"]; min: string; max: string };

const CHAVES_DO_PAINEL = ["usa_adesivo_deteccao_cio", "dias_adesivo_cio_min", "dias_adesivo_cio_max"];
/** Parâmetros que este painel assume — o card genérico do grupo não os mostra mais. */
export const ehParametroDoPainelAdesivo = (chave: string) => CHAVES_DO_PAINEL.includes(chave);

const linha: React.CSSProperties = { display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 20rem)", gap: "1.2rem", alignItems: "center", padding: "0.7rem 0", borderBottom: "1px solid var(--border)" };
const titulo: React.CSSProperties = { fontSize: "0.88rem", fontWeight: 600 };
const dica: React.CSSProperties = { fontSize: "0.76rem", lineHeight: 1.5, color: "var(--text-muted)", marginTop: "0.15rem", maxWidth: "62ch" };
const campo: React.CSSProperties = { width: "6rem", textAlign: "right", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.85rem" };

function SimNao({ valor, onChange, rotulo, desabilitado }: { valor: boolean; onChange: (v: boolean) => void; rotulo: string; desabilitado: boolean }) {
  const botao = (v: boolean, texto: string) => (
    <button type="button" aria-pressed={valor === v} disabled={desabilitado} onClick={() => onChange(v)}
      style={{ padding: "0.4rem 1.1rem", fontSize: "0.8rem", fontWeight: 700, border: 0, cursor: desabilitado ? "default" : "pointer",
        background: valor === v ? "var(--pill-active-bg, var(--surface-2))" : "transparent", color: valor === v ? "var(--pill-active-fg, var(--ft-ouro-txt))" : "var(--text-muted)" }}>{texto}</button>
  );
  return <div role="group" aria-label={rotulo} style={{ display: "inline-flex", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", overflow: "hidden" }}>{botao(true, "Sim")}{botao(false, "Não")}</div>;
}

export function PainelAdesivoCio({ itens }: { itens: ParamItem[] }) {
  const podeEditar = ehAdmin();
  const valorParam = useCallback((chave: string, padrao: number) => { const v = itens.find((i) => i.chave === chave)?.valor; return typeof v === "number" ? v : padrao; }, [itens]);

  const [cfg, setCfg] = useState<RepasseConfig | null>(null);
  const [catalogo, setCatalogo] = useState<{ id: number; nome: string }[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [escolha, setEscolha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [avisos, setAvisos] = useState<string[]>([]);
  const [salvando, setSalvando] = useState(false);

  const paraForm = useCallback((c: RepasseConfig): Form => ({
    usar: c.usar, avisar: c.avisar_apos_dias == null ? "" : String(c.avisar_apos_dias), ids: c.estoque_ids ?? [],
    repetir: c.repetir, cada: String(c.repetir_cada_dias), repeticoes: String(c.repeticoes), quem: c.quem_entra,
    min: String(valorParam("dias_adesivo_cio_min", 15)), max: String(valorParam("dias_adesivo_cio_max", 28)),
  }), [valorParam]);

  const carregar = useCallback(async () => {
    try {
      const [c, p] = await Promise.all([fetchRepasseConfig(), fetchRepasseProdutos()]);
      const todos = [...p.produtos.map((x) => ({ id: x.id, nome: x.nome })), ...p.outros_itens.map((x) => ({ id: x.id, nome: x.nome }))]
        .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
      setCfg(c); setCatalogo(todos); setForm(paraForm(c)); setErro(null);
    } catch (e) { setErro(e instanceof Error ? e.message : "Não foi possível carregar a configuração do adesivo."); }
  }, [paraForm]);
  useEffect(() => { carregar(); }, [carregar]);

  const nomeDe = useMemo(() => {
    const m = new Map(catalogo.map((x) => [x.id, x.nome]));
    (cfg?.produtos ?? []).forEach((x) => m.set(x.id, x.nome));
    return (id: number) => m.get(id) ?? `Item ${id}`;
  }, [catalogo, cfg]);

  if (erro && !cfg) return <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>{erro}</span></div>;
  if (!cfg || !form) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;

  const set = (parcial: Partial<Form>) => { setForm({ ...form, ...parcial }); setOk(null); };
  const disponiveis = catalogo.filter((x) => !form.ids.includes(x.id));

  async function salvar() {
    if (!form || !cfg) return;
    setErro(null); setOk(null);
    const avisar = form.avisar.trim();
    if (form.usar && avisar !== "" && !(Number.isInteger(Number(avisar)) && Number(avisar) >= 1 && Number(avisar) <= 60)) { setErro("Avisar na agenda após: use um número de dias entre 1 e 60, ou deixe vazio para não avisar."); return; }
    const min = Number(form.min), max = Number(form.max);
    if (!Number.isInteger(min) || !Number.isInteger(max) || min < 1 || max < min) { setErro("Observação de cio: o mínimo precisa ser um número de dias e não pode passar do máximo."); return; }
    setSalvando(true);
    try {
      const salvo = await salvarRepasseConfig({
        usar: form.usar, avisar_apos_dias: avisar === "" ? null : Number(avisar), estoque_ids: form.ids,
        repetir: form.repetir, repetir_cada_dias: Number(form.cada) || cfg.repetir_cada_dias, repeticoes: Number(form.repeticoes) || cfg.repeticoes, quem_entra: form.quem,
      });
      if (min !== valorParam("dias_adesivo_cio_min", 15)) await atualizarParametro("dias_adesivo_cio_min", min);
      if (max !== valorParam("dias_adesivo_cio_max", 28)) await atualizarParametro("dias_adesivo_cio_max", max);
      setAvisos(salvo.avisos ?? []);
      setOk("Salvo — já vale para a Agenda, a lista Observação de cio e o diagnóstico.");
      window.dispatchEvent(new Event("parametros-salvos"));
      await carregar();
    } catch (e) { setErro(e instanceof Error ? e.message : "Erro ao salvar."); } finally { setSalvando(false); }
  }

  const desab = !podeEditar || salvando;
  return (
    <div className="card" aria-label="Detecção de cio de repasse (adesivo)" data-testid="painel-adesivo-cio">
      <div className="card-header mb-1">Detecção de cio de repasse (adesivo)</div>

      <div style={linha}>
        <div>
          <div style={titulo} id="lab-adesivo">Utiliza adesivos para detecção de cio de repasse?</div>
          <div style={dica}>É a chave mestra: ligada, valem o aviso na Agenda, a lista Observação de cio e o método “Cio de repasse” no diagnóstico. Desligada, nenhum dos três aparece.</div>
        </div>
        <div style={{ textAlign: "right" }}><SimNao valor={form.usar} onChange={(v) => set({ usar: v })} rotulo="Utiliza adesivos para detecção de cio de repasse" desabilitado={desab} /></div>
      </div>

      {form.usar ? (
        <>
          <div style={linha}>
            <div>
              <label htmlFor="adesivo-avisar" style={titulo}>Avisar na agenda a aplicação do adesivo após</label>
              <div style={dica}>Dias depois de cada inseminação ou monta. Deixe vazio para não avisar.</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <input id="adesivo-avisar" type="number" min={1} max={60} value={form.avisar} disabled={desab} onChange={(e) => set({ avisar: e.target.value })} style={campo} placeholder="não avisar" />
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginLeft: "0.4rem" }}>dias</span>
            </div>
          </div>

          <div style={linha}>
            <div>
              <div style={titulo}>Produtos vinculados</div>
              <div style={dica}>Itens de estoque usados como adesivo. Com produtos escolhidos, a aplicação só aceita esses. Sem nenhum, a lista é livre (todo o estoque).</div>
            </div>
            <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", justifyContent: "flex-end", alignItems: "center" }}>
              {form.ids.map((id) => (
                <span key={id} style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", padding: "0.25rem 0.3rem 0.25rem 0.7rem", border: "1px solid var(--ft-ouro)", background: "var(--ft-ouro-tint)", color: "var(--ft-ouro-txt)", borderRadius: 999, fontSize: "0.8rem", fontWeight: 600 }}>
                  {nomeDe(id)}
                  {!desab && <button type="button" aria-label={`Remover ${nomeDe(id)}`} onClick={() => set({ ids: form.ids.filter((x) => x !== id) })} style={{ background: "transparent", border: 0, color: "inherit", cursor: "pointer", display: "inline-flex", padding: "0.1rem" }}><X size={13} aria-hidden="true" /></button>}
                </span>
              ))}
              {form.ids.length === 0 && <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Nenhum — escolha livre</span>}
              {!desab && (
                <span style={{ display: "inline-flex", gap: "0.3rem" }}>
                  <select aria-label="Produto do estoque" value={escolha} onChange={(e) => setEscolha(e.target.value)} style={{ ...campo, width: "11rem", textAlign: "left" }}>
                    <option value="">Adicionar do estoque…</option>
                    {disponiveis.map((x) => <option key={x.id} value={x.id}>{x.nome}</option>)}
                  </select>
                  <button type="button" className="btn-ghost" disabled={!escolha} onClick={() => { set({ ids: [...form.ids, Number(escolha)] }); setEscolha(""); }} aria-label="Adicionar produto" style={{ padding: "0.3rem 0.5rem" }}><Plus size={14} aria-hidden="true" /></button>
                </span>
              )}
            </div>
          </div>

          <div style={linha}>
            <div><label htmlFor="adesivo-min" style={titulo}>Observação de cio (adesivo) — dias mínimo</label><div style={dica}>Início da janela da lista Observação de cio, na Agenda do veterinário.</div></div>
            <div style={{ textAlign: "right" }}><input id="adesivo-min" type="number" min={1} value={form.min} disabled={desab} onChange={(e) => set({ min: e.target.value })} style={campo} /><span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginLeft: "0.4rem" }}>dias</span></div>
          </div>
          <div style={linha}>
            <div><label htmlFor="adesivo-max" style={titulo}>Observação de cio (adesivo) — dias máximo</label><div style={dica}>Fim da janela. Não decide se o método “Cio de repasse” aparece no diagnóstico: quem decide é a chave mestra.</div></div>
            <div style={{ textAlign: "right" }}><input id="adesivo-max" type="number" min={1} value={form.max} disabled={desab} onChange={(e) => set({ max: e.target.value })} style={campo} /><span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginLeft: "0.4rem" }}>dias</span></div>
          </div>

          <details style={{ padding: "0.6rem 0" }}>
            <summary style={{ cursor: "pointer", fontSize: "0.82rem", fontWeight: 700, color: "var(--text-muted)" }}>Opções avançadas do aviso</summary>
            <div style={linha}>
              <div><div style={titulo}>Repetir a checagem</div><div style={dica}>Ciclo estral: {cfg.ciclo_sugerido?.[0] ?? 18} a {cfg.ciclo_sugerido?.[1] ?? 24} dias é o sugerido.</div></div>
              <div style={{ textAlign: "right", display: "flex", gap: "0.5rem", justifyContent: "flex-end", alignItems: "center", flexWrap: "wrap" }}>
                <SimNao valor={form.repetir} onChange={(v) => set({ repetir: v })} rotulo="Repetir a checagem" desabilitado={desab} />
                {form.repetir && (<>
                  <input type="number" aria-label="Repetir a cada (dias)" value={form.cada} disabled={desab} onChange={(e) => set({ cada: e.target.value })} style={{ ...campo, width: "4.5rem" }} />
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>dias, </span>
                  <input type="number" aria-label="Quantidade de repetições" value={form.repeticoes} disabled={desab} onChange={(e) => set({ repeticoes: e.target.value })} style={{ ...campo, width: "3.5rem" }} />
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>vezes</span>
                </>)}
              </div>
            </div>
            <div style={{ ...linha, borderBottom: 0 }}>
              <div style={titulo}><label htmlFor="adesivo-quem">Quais serviços entram</label></div>
              <div style={{ textAlign: "right" }}>
                <select id="adesivo-quem" value={form.quem} disabled={desab} onChange={(e) => set({ quem: e.target.value as Form["quem"] })} style={{ ...campo, width: "16rem", textAlign: "left" }}>
                  {(cfg.quem_entra_opcoes ?? []).map((o) => <option key={o.valor} value={o.valor}>{o.rotulo}</option>)}
                </select>
              </div>
            </div>
          </details>
        </>
      ) : (
        <p style={{ ...dica, padding: "0.7rem 0" }}>Sem adesivo: a agenda não avisa aplicação, a lista Observação de cio fica oculta e o diagnóstico não oferece o método “Cio de repasse”.</p>
      )}

      {!cfg.configurado && (
        <p style={{ ...dica, padding: "0.5rem 0", maxWidth: "none" }}>
          <strong style={{ color: "var(--text)" }}>Fazenda sem configuração anterior:</strong> quem nunca configurou o adesivo e deixa esta chave em “Não” deixa de receber o aviso automático de 14 dias.
          Quem já tinha a configuração salva mantém os valores.
        </p>
      )}
      {avisos.length > 0 && <p role="status" style={{ fontSize: "0.78rem", color: "var(--ft-ambar)", margin: "0.4rem 0" }}>{avisos.join(" ")}</p>}
      {erro && <p role="alert" style={{ fontSize: "0.8rem", color: "var(--red)", margin: "0.4rem 0" }}>{erro}</p>}
      {ok && <p role="status" style={{ fontSize: "0.78rem", color: "var(--ft-verde)", margin: "0.4rem 0", display: "flex", alignItems: "center", gap: "0.3rem" }}><Check size={14} aria-hidden="true" />{ok}</p>}
      <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "0.5rem", gap: "0.6rem", alignItems: "center" }}>
        {!podeEditar && <span style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>Somente administradores editam.</span>}
        {podeEditar && (
          <button type="button" className="btn-primary-gold" disabled={salvando} onClick={salvar} style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
            {salvando ? <><Loader2 size={14} className="animate-spin" aria-hidden="true" /> Salvando…</> : "Salvar adesivo"}
          </button>
        )}
      </div>
    </div>
  );
}
