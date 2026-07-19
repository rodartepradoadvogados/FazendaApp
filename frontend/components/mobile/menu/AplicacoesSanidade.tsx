"use client";
// Sub-tela: Aplicações de Sanidade (medicamentos/vacinas aplicados).
// Diferente das outras sub-telas do Menu (só leitura), esta PERMITE editar e
// excluir a aplicação direto na lista — só para a conta principal (admin).
// A leitura usa cache offline; editar/excluir são ações online.
import { useEffect, useMemo, useState } from "react";
import { Pencil, Trash2, Check, X, Search } from "lucide-react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import {
  fetchSanidade, editarAplicacaoSanidade, excluirAplicacaoSanidade, ehAdmin, formatDate, fetchMedicamentos,
} from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";
import { RESPONSAVEIS, VIAS_APLICACAO } from "@/lib/constants";

type Aplic = {
  id: number; numero: string; produto: string; categoria: string | null;
  dose: number | null; unidade: string | null; via: string | null;
  responsavel: string | null; obs: string | null; data: string | null;
};

const UNIDADES = ["ml", "L", "unidade", "dose", "kg", "saca 30kg", "saca 60kg"];

const inp: React.CSSProperties = {
  width: "100%", background: "var(--mob-surface-2)", color: "var(--mob-text)",
  border: "1px solid var(--mob-border)", borderRadius: 10, padding: "0.55rem 0.7rem", fontSize: "0.9rem",
};
const rotulo: React.CSSProperties = { display: "block", fontSize: "0.74rem", fontWeight: 600, color: "var(--mob-muted)", marginBottom: "0.2rem" };

export default function AplicacoesSanidade({ onVoltar }: { onVoltar: () => void }) {
  const admin = ehAdmin();
  const { dados, doCache, carregando, recarregar } = useCarregar<{ aplicacoes: Aplic[] }>(
    "menu_aplicacoes_sanidade", () => fetchSanidade()
  );

  const [busca, setBusca] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [vals, setVals] = useState({ data: "", produto: "", dose: "", unidade: "", via: "", responsavel: "", obs: "" });
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [produtosCatalogo, setProdutosCatalogo] = useState<string[]>([]);

  useEffect(() => {
    fetchMedicamentos({ incluir_sem_estoque: true }).then((m: any[]) => setProdutosCatalogo(m.map((x) => x.nome))).catch(() => setProdutosCatalogo([]));
  }, []);

  const lista = useMemo(() => {
    const todas = (dados?.aplicacoes || []).slice();
    // Mais recentes primeiro (aplicações sem data vão para o fim).
    todas.sort((a, b) => (b.data || "").localeCompare(a.data || ""));
    const q = busca.trim().toLowerCase();
    const filt = q
      ? todas.filter((a) => a.numero.toLowerCase().includes(q) || a.produto.toLowerCase().includes(q))
      : todas;
    return filt.slice(0, 200);
  }, [dados, busca]);

  const iniciar = (a: Aplic) => {
    setEditId(a.id);
    setVals({
      data: a.data ?? "", produto: a.produto ?? "", dose: a.dose == null ? "" : String(a.dose),
      unidade: a.unidade ?? "", via: a.via ?? "", responsavel: a.responsavel ?? "", obs: a.obs ?? "",
    });
    setErro(null);
  };

  const salvar = async (a: Aplic) => {
    setOcupado(a.id); setErro(null);
    try {
      await editarAplicacaoSanidade(a.id, {
        data_aplicacao: vals.data || undefined,
        produto: vals.produto.trim() || undefined,
        dose: vals.dose.trim() === "" ? null : Number(vals.dose),
        unidade: vals.unidade || null,
        via: vals.via.trim() || null,
        responsavel: vals.responsavel.trim() || null,
        obs: vals.obs.trim() || null,
      });
      setEditId(null);
      await recarregar();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(null); }
  };

  const excluir = async (a: Aplic) => {
    if (!window.confirm(`Excluir a aplicação de "${a.produto}" no animal ${a.numero}? Não dá para desfazer.`)) return;
    setOcupado(a.id); setErro(null);
    try {
      await excluirAplicacaoSanidade(a.id);
      await recarregar();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(null); }
  };

  return (
    <div>
      <MobVoltar titulo="Aplicações" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_aplicacoes_sanidade" mostrar={doCache} />

      {!admin && (
        <Vazio>Só a conta principal pode editar ou excluir aplicações aqui.</Vazio>
      )}

      {admin && (
        <>
          <div style={{ position: "relative", marginBottom: "0.9rem" }}>
            <Search size={16} style={{ position: "absolute", left: 12, top: 13, color: "var(--mob-muted)" }} />
            <input style={{ ...inp, paddingLeft: "2.2rem" }} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por animal ou produto" />
          </div>

          {erro && <p style={{ color: "var(--mob-vermelho)", fontSize: "0.85rem", marginBottom: "0.6rem", fontWeight: 600 }}>{erro}</p>}

          {carregando && !dados ? (
            <Carregando />
          ) : !dados ? (
            <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
          ) : lista.length === 0 ? (
            <Vazio>Nenhuma aplicação encontrada.</Vazio>
          ) : (
            lista.map((a) => {
              const editando = editId === a.id;
              return (
                <MobCard key={a.id} style={{ marginBottom: "0.6rem" }}>
                  {!editando ? (
                    <>
                      <div style={{ display: "flex", alignItems: "baseline", gap: "0.6rem" }}>
                        <span style={{ fontWeight: 800, fontSize: "1.05rem" }}>{a.numero}</span>
                        <span style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginLeft: "auto" }}>{a.data ? formatDate(a.data) : "sem data"}</span>
                      </div>
                      <div style={{ fontSize: "0.9rem", fontWeight: 600, marginTop: "0.2rem" }}>{a.produto}</div>
                      <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>
                        {a.categoria || "Outros"}
                        {a.dose != null ? ` · ${a.dose}${a.unidade ? " " + a.unidade : ""}` : ""}
                        {a.via ? ` · ${a.via}` : ""}
                      </div>
                      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.7rem" }}>
                        <button type="button" onClick={() => iniciar(a)}
                          style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: "0.4rem", fontSize: "0.85rem", fontWeight: 700, color: "var(--mob-text)", background: "var(--mob-surface-2)", border: "1px solid var(--mob-border)", borderRadius: 10, padding: "0.55rem", cursor: "pointer" }}>
                          <Pencil size={15} /> Editar
                        </button>
                        <button type="button" disabled={ocupado === a.id} onClick={() => excluir(a)}
                          style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: "0.4rem", fontSize: "0.85rem", fontWeight: 700, color: "var(--mob-vermelho)", background: "transparent", border: "1px solid var(--mob-vermelho)", borderRadius: 10, padding: "0.55rem", cursor: "pointer" }}>
                          <Trash2 size={15} /> Excluir
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <div style={{ fontWeight: 800, fontSize: "1rem", marginBottom: "0.6rem" }}>Animal {a.numero}</div>
                      <div style={{ marginBottom: "0.6rem" }}><label style={rotulo}>Data</label>
                        <input type="date" style={inp} value={vals.data} onChange={(e) => setVals((s) => ({ ...s, data: e.target.value }))} /></div>
                      <div style={{ marginBottom: "0.6rem" }}><label style={rotulo}>Produto</label>
                        <select style={inp} value={vals.produto} onChange={(e) => setVals((s) => ({ ...s, produto: e.target.value }))}>
                          <option value="">Selecione...</option>
                          {!produtosCatalogo.includes(vals.produto) && vals.produto && <option value={vals.produto}>{vals.produto}</option>}
                          {produtosCatalogo.map((p) => <option key={p} value={p}>{p}</option>)}
                        </select></div>
                      <div style={{ display: "flex", gap: "0.6rem", marginBottom: "0.6rem" }}>
                        <div style={{ flex: 1 }}><label style={rotulo}>Dose</label>
                          <input type="number" inputMode="decimal" style={inp} value={vals.dose} onChange={(e) => setVals((s) => ({ ...s, dose: e.target.value }))} /></div>
                        <div style={{ flex: 1 }}><label style={rotulo}>Unidade</label>
                          <select style={inp} value={vals.unidade} onChange={(e) => setVals((s) => ({ ...s, unidade: e.target.value }))}>
                            <option value="">—</option>
                            {!UNIDADES.includes(vals.unidade) && vals.unidade && <option value={vals.unidade}>{vals.unidade}</option>}
                            {UNIDADES.map((u) => <option key={u} value={u}>{u}</option>)}
                          </select></div>
                      </div>
                      <div style={{ marginBottom: "0.6rem" }}><label style={rotulo}>Via</label>
                        <select style={inp} value={vals.via} onChange={(e) => setVals((s) => ({ ...s, via: e.target.value }))}>
                          <option value="">—</option>
                          {!VIAS_APLICACAO.includes(vals.via) && vals.via && <option value={vals.via}>{vals.via}</option>}
                          {VIAS_APLICACAO.map((v) => <option key={v} value={v}>{v}</option>)}
                        </select></div>
                      <div style={{ marginBottom: "0.6rem" }}><label style={rotulo}>Responsável</label>
                        <select style={inp} value={vals.responsavel} onChange={(e) => setVals((s) => ({ ...s, responsavel: e.target.value }))}>
                          <option value="">—</option>
                          {!RESPONSAVEIS.includes(vals.responsavel) && vals.responsavel && <option value={vals.responsavel}>{vals.responsavel}</option>}
                          {RESPONSAVEIS.map((r) => <option key={r} value={r}>{r}</option>)}
                        </select></div>
                      <div style={{ marginBottom: "0.2rem" }}><label style={rotulo}>Observação</label>
                        <input style={inp} value={vals.obs} onChange={(e) => setVals((s) => ({ ...s, obs: e.target.value }))} /></div>
                      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.7rem" }}>
                        <button type="button" disabled={ocupado === a.id} onClick={() => salvar(a)}
                          style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: "0.4rem", fontSize: "0.9rem", fontWeight: 700, color: "#fff", background: "var(--mob-verde)", border: "none", borderRadius: 10, padding: "0.6rem", cursor: "pointer" }}>
                          <Check size={16} /> {ocupado === a.id ? "…" : "Salvar"}
                        </button>
                        <button type="button" disabled={ocupado === a.id} onClick={() => setEditId(null)}
                          style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: "0.4rem", fontSize: "0.9rem", fontWeight: 700, color: "var(--mob-text)", background: "var(--mob-surface-2)", border: "1px solid var(--mob-border)", borderRadius: 10, padding: "0.6rem", cursor: "pointer" }}>
                          <X size={16} /> Cancelar
                        </button>
                      </div>
                    </>
                  )}
                </MobCard>
              );
            })
          )}
        </>
      )}
    </div>
  );
}
