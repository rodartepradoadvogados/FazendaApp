"use client";
// Sub-tela: Lançar nova dieta (app) — versão móvel do cadastro de dieta do
// site. Escolhe o lote (mostra nº de animais, DEL médio, média do CL e a última
// dieta), lança os produtos com cálculo automático (por cabeça, total/dia,
// total/trato e kg no vagão), datas de início e provável fim, e salva. Se já
// houver dieta ativa no lote, pergunta se deseja encerrá-la na data de início.
import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { MobVoltar, MobCampo, MobCard, MobAviso } from "@/components/mobile/ui";
import { fetchLotes, fetchAlimentosPadrao, fetchContextoDieta, type ContextoDieta } from "@/lib/api";
import { fetchComCache, enviarOuEnfileirar } from "@/lib/offline";

const NUM_TRATOS = 2;
const UNIDADES = ["kg", "g", "L", "ml", "unidade", "dose", "saca 30kg", "saca 60kg"];
const hoje = () => new Date().toISOString().slice(0, 10);

type LoteRow = { codigo: string; nome?: string | null; qtd_animais?: number };
type Item = { alimento: string; quantidade: string; unidade: string };

function num(v?: number | null, casas = 2): string {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: casas });
}
function fmtData(iso?: string | null): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

export default function LancarDieta({ onVoltar }: { onVoltar: () => void }) {
  const [lotes, setLotes] = useState<LoteRow[]>([]);
  const [alimentos, setAlimentos] = useState<string[]>([]);
  const [loteSel, setLoteSel] = useState("");
  const [ctx, setCtx] = useState<ContextoDieta | null>(null);
  const [dataInicio, setDataInicio] = useState(hoje());
  const [dataFim, setDataFim] = useState("");
  const [itens, setItens] = useState<Item[]>([{ alimento: "", quantidade: "", unidade: "kg" }]);
  const [salvando, setSalvando] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "offline" | "erro"; msg: string } | null>(null);

  // Listas do formulário (lotes, alimentos) e contexto do lote: cache local —
  // sem internet, o funcionário ainda enxerga a última cópia vista e pode
  // lançar a dieta (entra na fila de envio).
  useEffect(() => {
    fetchComCache<LoteRow[]>("menu_lancar_dieta_lotes", () => fetchLotes() as Promise<LoteRow[]>)
      .then((r) => setLotes((r.dados || []).filter((l) => /^\d\d/.test(l.codigo))));
    fetchComCache<string[]>("menu_lancar_dieta_alimentos", () => fetchAlimentosPadrao() as Promise<string[]>)
      .then((r) => setAlimentos(r.dados || []));
  }, []);

  useEffect(() => {
    setCtx(null);
    if (!loteSel) return;
    fetchComCache<ContextoDieta>(`menu_lancar_dieta_ctx_${loteSel}`, () => fetchContextoDieta(Number(loteSel)))
      .then((r) => setCtx(r.dados));
  }, [loteSel]);

  const nAnimais = ctx?.qtd_animais ?? lotes.find((l) => l.codigo.slice(0, 2) === loteSel)?.qtd_animais ?? 0;
  const vagaoKg = itens.reduce((s, it) => (["kg", "g"].includes(it.unidade) ? s + (Number(it.quantidade) || 0) : s), 0);

  const patchItem = (idx: number, patch: Partial<Item>) => setItens((p) => p.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  const addItem = () => setItens((p) => [...p, { alimento: "", quantidade: "", unidade: "kg" }]);
  const delItem = (idx: number) => setItens((p) => (p.length > 1 ? p.filter((_, i) => i !== idx) : p));

  async function salvar() {
    setAviso(null);
    if (!loteSel) return setAviso({ tipo: "erro", msg: "Selecione o lote." });
    const validos = itens.filter((it) => it.alimento && Number(it.quantidade) > 0);
    if (!validos.length) return setAviso({ tipo: "erro", msg: "Adicione ao menos um produto com quantidade." });
    let encerrar = false;
    if (ctx?.ultima_dieta) {
      encerrar = window.confirm(`O lote ${loteSel} já tem uma dieta ativa. Deseja encerrar a atual na data de início desta nova dieta (${fmtData(dataInicio)})?`);
      if (!encerrar) return setAviso({ tipo: "offline", msg: "Cancelado — a dieta ativa foi mantida." });
    }
    setSalvando(true);
    try {
      const { enviado } = await enviarOuEnfileirar("/alimentacao/dietas", {
        lote: Number(loteSel), data_abertura: dataInicio, data_prevista_encerramento: dataFim || undefined,
        itens: validos.map((it) => ({ alimento: it.alimento, quantidade: Number(it.quantidade), unidade: it.unidade })),
        encerrar_anterior: encerrar,
      }, `Dieta lote ${loteSel}`, "POST");
      setAviso(enviado
        ? { tipo: "ok", msg: `Dieta salva para o lote ${loteSel}.` }
        : { tipo: "offline", msg: "Sem internet — guardado, será enviado automaticamente ao conectar." });
      setItens([{ alimento: "", quantidade: "", unidade: "kg" }]);
      setDataFim("");
      if (enviado) fetchContextoDieta(Number(loteSel)).then(setCtx).catch(() => {});
    } catch (e) {
      setAviso({ tipo: "erro", msg: e instanceof Error ? e.message : "Erro ao salvar a dieta." });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div>
      <MobVoltar titulo="Lançar nova dieta" onVoltar={onVoltar} />

      <MobCampo label="Lote">
        <select className="mob-input" value={loteSel} onChange={(e) => setLoteSel(e.target.value)}>
          <option value="">Selecione o lote…</option>
          {lotes.map((l) => <option key={l.codigo} value={l.codigo.slice(0, 2)}>{l.codigo}{l.nome ? ` - ${l.nome}` : ""}</option>)}
        </select>
      </MobCampo>

      {ctx && (
        <MobCard style={{ marginBottom: "0.7rem" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.8rem", fontSize: "0.82rem" }}>
            <span><strong>{nAnimais}</strong> animais</span>
            <span>DEL médio <strong>{ctx.del_medio != null ? `${ctx.del_medio} d` : "—"}</strong></span>
            <span>Média CL <strong>{ctx.media_cl != null ? `${num(ctx.media_cl, 1)} kg` : "—"}</strong></span>
            <span>Últ. CL <strong>{fmtData(ctx.data_ult_cl)}</strong></span>
          </div>
          {ctx.ultima_dieta && ctx.ultima_dieta.itens.length > 0 && (
            <div style={{ marginTop: "0.5rem", fontSize: "0.78rem", color: "var(--mob-muted)" }}>
              Última dieta: {ctx.ultima_dieta.itens.map((it) => `${it.alimento} ${num(it.total_dia)}${it.unidade}/dia`).join(" · ")}
            </div>
          )}
        </MobCard>
      )}

      <div style={{ display: "flex", gap: "0.6rem" }}>
        <div style={{ flex: 1 }}>
          <MobCampo label="Data de início"><input type="date" className="mob-input" value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} /></MobCampo>
        </div>
        <div style={{ flex: 1 }}>
          <MobCampo label="Provável fim"><input type="date" className="mob-input" value={dataFim} onChange={(e) => setDataFim(e.target.value)} /></MobCampo>
        </div>
      </div>

      <datalist id="alimentos-mob-dieta">{alimentos.map((a) => <option key={a} value={a} />)}</datalist>

      {itens.map((it, idx) => {
        const q = Number(it.quantidade) || 0;
        return (
          <MobCard key={idx} style={{ marginBottom: "0.6rem", position: "relative" }}>
            <MobCampo label={`Produto ${idx + 1}`}>
              <input className="mob-input" list="alimentos-mob-dieta" value={it.alimento} onChange={(e) => patchItem(idx, { alimento: e.target.value })} placeholder="ex.: Silagem de milho" />
            </MobCampo>
            <div style={{ display: "flex", gap: "0.6rem" }}>
              <div style={{ flex: 1 }}>
                <MobCampo label="Total/dia (lote)"><input type="number" inputMode="decimal" className="mob-input" value={it.quantidade} onChange={(e) => patchItem(idx, { quantidade: e.target.value })} placeholder="0" /></MobCampo>
              </div>
              <div style={{ flex: 1 }}>
                <MobCampo label="Unidade">
                  <select className="mob-input" value={it.unidade} onChange={(e) => patchItem(idx, { unidade: e.target.value })}>{UNIDADES.map((u) => <option key={u}>{u}</option>)}</select>
                </MobCampo>
              </div>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.9rem", fontSize: "0.8rem", marginTop: "0.2rem" }}>
              <span style={{ color: "var(--mob-verde)", fontWeight: 800 }}>{num(q / NUM_TRATOS)} {it.unidade}/trato</span>
              <span style={{ color: "var(--mob-ambar)", fontWeight: 700 }}>{num(q)} {it.unidade}/dia</span>
              <span style={{ color: "var(--mob-muted)" }}>{nAnimais ? `${num(q / nAnimais, 3)} ${it.unidade}/cab` : "—/cab"}</span>
            </div>
            {itens.length > 1 && (
              <button type="button" onClick={() => delItem(idx)} aria-label="Remover produto"
                style={{ position: "absolute", top: "0.5rem", right: "0.5rem", background: "none", border: "none", color: "var(--mob-vermelho)", cursor: "pointer" }}><Trash2 size={16} /></button>
            )}
          </MobCard>
        );
      })}

      <button type="button" onClick={addItem} className="mob-btn mob-btn-sec" style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "0.4rem", marginBottom: "0.6rem" }}>
        <Plus size={16} /> Acrescentar produto
      </button>

      <div style={{ padding: "0.6rem 0.7rem", background: "var(--mob-surface)", border: "1px solid var(--mob-border)", borderRadius: "var(--r-app)", fontSize: "0.88rem", fontWeight: 800, marginBottom: "0.7rem" }}>
        Vagão: <span style={{ color: "var(--mob-verde)" }}>{num(vagaoKg / NUM_TRATOS)} kg/trato</span> · {num(vagaoKg)} kg/dia
      </div>

      <button className="mob-btn" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar dieta"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </div>
  );
}
