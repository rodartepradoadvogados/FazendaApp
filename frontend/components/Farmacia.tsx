"use client";
// Farmácia — o estoque de medicamentos/hormônios/vacinas visto pela hierarquia
// PRINCÍPIO ATIVO → marcas/apresentações. Cada princípio traz o saldo unificado
// (soma dos frascos de tamanhos diferentes), o nº de apresentações vs. o mínimo
// (semáforo) e o alerta de "inicializar estoque" (gatilho de baixas). Prático e
// visual: cartões expansíveis, busca e filtros rápidos.
import { useEffect, useMemo, useState } from "react";
import { Pill, Search, ChevronDown, ChevronRight, AlertTriangle, PackagePlus, FlaskConical } from "lucide-react";
import {
  fetchFarmaciaPrincipios, inicializarEstoqueFarmacia,
  type PrincipioFarmacia, type ApresentacaoFarmacia,
} from "@/lib/api";

function num(v?: number | null, casas = 2): string {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: casas });
}

// Semáforo do mínimo: vermelho abaixo, âmbar perto (< 1,5×), verde ok.
function corMinimo(p: PrincipioFarmacia): string {
  if (!p.qtd_marcas_estoque) return "var(--text-muted)";
  if (p.abaixo_minimo) return "var(--red)";
  if (p.total_apresentacoes < p.estoque_minimo_apresentacoes * 1.5) return "var(--amber)";
  return "var(--green-light)";
}

const input: React.CSSProperties = {
  padding: "0.4rem 0.55rem", borderRadius: 6, fontSize: "0.82rem",
  background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)",
};

type Filtro = "todos" | "abaixo" | "inicializar" | "biologico";

export default function Farmacia() {
  const [dados, setDados] = useState<PrincipioFarmacia[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [aberto, setAberto] = useState<number | null>(null);

  const carregar = () => fetchFarmaciaPrincipios().then(setDados).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); }, []);

  const contadores = useMemo(() => {
    const l = dados || [];
    return {
      abaixo: l.filter((p) => p.abaixo_minimo).length,
      inicializar: l.filter((p) => p.precisa_inicializar).length,
    };
  }, [dados]);

  const lista = useMemo(() => {
    let l = dados || [];
    const q = busca.trim().toLowerCase();
    if (q) l = l.filter((p) =>
      p.nome.toLowerCase().includes(q) || (p.categoria_software || "").toLowerCase().includes(q) ||
      p.itens.some((it) => it.nome.toLowerCase().includes(q) || (it.marca || "").toLowerCase().includes(q)));
    if (filtro === "abaixo") l = l.filter((p) => p.abaixo_minimo);
    else if (filtro === "inicializar") l = l.filter((p) => p.precisa_inicializar);
    else if (filtro === "biologico") l = l.filter((p) => p.eh_biologico);
    return l;
  }, [dados, busca, filtro]);

  const chips: [Filtro, string, number | null][] = [
    ["todos", "Todos", dados?.length ?? null],
    ["abaixo", "Abaixo do mínimo", contadores.abaixo],
    ["inicializar", "Inicializar estoque", contadores.inicializar],
    ["biologico", "Biológicos", null],
  ];

  return (
    <div>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.8rem" }}>
        Estoque de medicamentos, hormônios e vacinas organizado por <strong>princípio ativo</strong>. O saldo de
        frascos de marcas/tamanhos diferentes é somado; o alerta de reposição olha o total do princípio (mínimo
        padrão = 1 apresentação). Itens sem estoque inicial ainda não baixam — registre a primeira compra.
      </p>

      {/* Alertas resumidos */}
      {dados && (contadores.abaixo > 0 || contadores.inicializar > 0) && (
        <div className="flex flex-wrap gap-2 mb-3">
          {contadores.abaixo > 0 && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem", fontWeight: 700, color: "var(--red)", background: "rgba(220,38,38,0.1)", border: "1px solid var(--red)", borderRadius: 999, padding: "0.25rem 0.7rem" }}>
              <AlertTriangle size={13} /> {contadores.abaixo} abaixo do mínimo
            </span>
          )}
          {contadores.inicializar > 0 && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem", fontWeight: 700, color: "var(--amber)", background: "rgba(217,119,6,0.1)", border: "1px solid var(--amber)", borderRadius: 999, padding: "0.25rem 0.7rem" }}>
              <PackagePlus size={13} /> {contadores.inicializar} para inicializar
            </span>
          )}
        </div>
      )}

      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: "1 1 240px", maxWidth: 340 }}>
          <Search size={14} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
          <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar princípio, categoria ou marca…"
            style={{ ...input, width: "100%", paddingLeft: "1.8rem" }} />
        </div>
        {chips.map(([id, label, n]) => (
          <button key={id} onClick={() => setFiltro(id)}
            style={{ fontSize: "0.76rem", padding: "0.32rem 0.75rem", borderRadius: 999, cursor: "pointer",
              border: "1px solid " + (filtro === id ? "var(--dourado)" : "var(--border)"),
              background: filtro === id ? "rgba(94,26,46,0.4)" : "transparent",
              color: filtro === id ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: filtro === id ? 700 : 500 }}>
            {label}{n != null ? ` (${n})` : ""}
          </button>
        ))}
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}
      {!dados ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>
      ) : lista.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum princípio ativo encontrado.</p>
      ) : (
        <div className="space-y-2">
          {lista.map((p) => (
            <CardPrincipio key={p.id} p={p} aberto={aberto === p.id} onToggle={() => setAberto(aberto === p.id ? null : p.id)} onMudou={carregar} />
          ))}
        </div>
      )}
    </div>
  );
}

function CardPrincipio({ p, aberto, onToggle, onMudou }: { p: PrincipioFarmacia; aberto: boolean; onToggle: () => void; onMudou: () => void }) {
  const cor = corMinimo(p);
  return (
    <div style={{ border: "1px solid " + (p.abaixo_minimo ? "var(--red)" : "var(--border)"), borderRadius: 10, overflow: "hidden" }}>
      <button onClick={onToggle}
        style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.7rem", padding: "0.7rem 0.9rem", background: "var(--surface-2)", border: "none", cursor: "pointer", color: "var(--text)", textAlign: "left" }}>
        {aberto ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <span style={{ width: 10, height: 10, borderRadius: "50%", background: cor, flexShrink: 0 }} title="Situação do estoque mínimo" />
        <span style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontWeight: 700 }}>
            {p.eh_biologico ? <FlaskConical size={14} style={{ color: "var(--dourado-light)" }} /> : <Pill size={14} style={{ color: "var(--dourado-light)" }} />}
            {p.nome}
          </span>
          {p.categoria_software && <span style={{ display: "block", fontSize: "0.72rem", color: "var(--text-muted)" }}>{p.categoria_software}</span>}
        </span>
        <span style={{ textAlign: "right", flexShrink: 0 }}>
          <span style={{ display: "block", fontWeight: 800, fontSize: "0.9rem", color: cor }}>
            {num(p.total_apresentacoes)} {p.unidade_apresentacao || "un"}{p.total_apresentacoes === 1 ? "" : "s"}
          </span>
          <span style={{ display: "block", fontSize: "0.72rem", color: "var(--text-muted)" }}>
            {p.total_base != null ? `${num(p.total_base)} ${p.unidade_base || ""}` : "—"} · mín {num(p.estoque_minimo_apresentacoes)}
          </span>
        </span>
      </button>

      {aberto && (
        <div style={{ padding: "0.85rem" }}>
          {(p.uso_principal || p.justificativa) && (
            <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.7rem" }}>
              {p.uso_principal && <div><strong style={{ color: "var(--text)" }}>Uso:</strong> {p.uso_principal}</div>}
              {p.justificativa && <div>{p.justificativa}</div>}
            </div>
          )}
          {p.itens.length === 0 ? (
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
              Nenhum item de estoque vinculado a este princípio ainda. Cadastre uma apresentação em Itens de estoque
              e vincule o princípio.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="fazenda-table" style={{ margin: 0, fontSize: "0.8rem" }}>
                <thead><tr>
                  <th>Apresentação</th><th>Marca/Lab.</th>
                  <th style={{ textAlign: "right" }}>Saldo</th><th style={{ textAlign: "right" }}>Frascos</th><th></th>
                </tr></thead>
                <tbody>
                  {p.itens.map((it) => <LinhaApresentacao key={it.estoque_id} it={it} onMudou={onMudou} />)}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function LinhaApresentacao({ it, onMudou }: { it: ApresentacaoFarmacia; onMudou: () => void }) {
  const [abrindo, setAbrindo] = useState(false);
  const [qtd, setQtd] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function inicializar() {
    setErro(null);
    if (!(Number(qtd) >= 0) || qtd === "") { setErro("Informe a quantidade."); return; }
    setSalvando(true);
    try {
      await inicializarEstoqueFarmacia(it.estoque_id, { quantidade: Number(qtd) });
      setAbrindo(false); setQtd("");
      onMudou();
    } catch (e: any) { setErro(e.message); } finally { setSalvando(false); }
  }

  return (
    <>
      <tr>
        <td style={{ fontWeight: 600 }}>
          {it.nome}
          {!it.estoque_inicializado && (
            <span title="Sem estoque inicial — ainda não baixa" style={{ marginLeft: "0.4rem", fontSize: "0.66rem", fontWeight: 800, color: "var(--amber)", background: "rgba(217,119,6,0.12)", border: "1px solid var(--amber)", borderRadius: 4, padding: "0.05rem 0.3rem" }}>
              inicializar
            </span>
          )}
        </td>
        <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{it.marca || "—"}</td>
        <td style={{ textAlign: "right" }}>
          {num(it.saldo)} {it.unidade || ""}
          {it.volume_por_apresentacao ? <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}> · {num(it.volume_por_apresentacao)}{it.volume_unidade}/un</span> : null}
        </td>
        <td style={{ textAlign: "right" }}>{it.apresentacoes != null ? num(it.apresentacoes) : "—"}</td>
        <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
          <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} onClick={() => setAbrindo((v) => !v)}>
            <PackagePlus size={13} /> {it.estoque_inicializado ? "Repor" : "Estoque inicial"}
          </button>
        </td>
      </tr>
      {abrindo && (
        <tr><td colSpan={5} style={{ padding: 0 }}>
          <div style={{ background: "var(--surface-2)", padding: "0.6rem 0.75rem", display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
            <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              {it.estoque_inicializado ? "Novo saldo total" : "Estoque inicial / primeira compra"} ({it.unidade}):
            </span>
            <input type="number" inputMode="decimal" style={{ ...input, width: 120 }} value={qtd} onChange={(e) => setQtd(e.target.value)} placeholder="0" />
            <button className="btn-primary" style={{ fontSize: "0.75rem" }} onClick={inicializar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
            <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => setAbrindo(false)}>Cancelar</button>
            {erro && <span style={{ color: "var(--red)", fontSize: "0.75rem" }}>{erro}</span>}
          </div>
        </td></tr>
      )}
    </>
  );
}
