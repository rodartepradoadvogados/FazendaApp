"use client";
// Painel CowData > Parâmetros — parâmetros de manejo/metas/agenda/RH/
// financeiro (ParametroFazenda) aplicáveis a todas as fazendas-cliente de
// uma vez, ou só às selecionadas, sem precisar entrar em cada uma via modo
// suporte (ver backend/fazenda/api/routers/painel_cowdata_parametros.py).
// "Aplicar em todas as fazendas ativas" é literal — sobrescreve inclusive
// quem já tinha personalizado (mesma semântica de Cadastros globais) e
// também atualiza o padrão global, para fazenda nova já nascer com o valor
// novo. Não inclui a aba "Parâmetros financeiros" da fazenda (contas
// correntes, plano de contas, centro de custo) — aquilo é dado de
// identidade por fazenda (nº de conta bancária), nunca faz sentido replicar.
import { useEffect, useState } from "react";
import { Check, Pencil, SlidersHorizontal } from "lucide-react";
import {
  fetchFazendasParametroCowData, fetchParametrosCowData, aplicarParametroCowData,
  type FazendaCadastroCowData, type ItemParametroCowData,
} from "@/lib/api";
import { usePainelCowDataCor } from "@/lib/painelCowDataTema";

export default function ParametrosCowData() {
  const COR = usePainelCowDataCor();
  const inputStyle: React.CSSProperties = {
    background: COR.bg, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "0.4rem 0.55rem",
    color: COR.texto, fontSize: "0.82rem",
  };
  const btnPrimario: React.CSSProperties = {
    background: COR.dourado, color: COR.bg, border: "none", borderRadius: "var(--r-sm)", padding: "0.4rem 0.75rem",
    fontSize: "0.78rem", fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: "0.35rem",
  };
  const btnGhost: React.CSSProperties = {
    background: "transparent", color: COR.mudo, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)",
    padding: "0.35rem 0.6rem", fontSize: "0.75rem", cursor: "pointer",
  };
  const [grupos, setGrupos] = useState<Record<string, { titulo: string; itens: ItemParametroCowData[] }>>({});
  const [fazendas, setFazendas] = useState<FazendaCadastroCowData[]>([]);
  const [grupoAtivo, setGrupoAtivo] = useState<string>("");
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const [alvoTodas, setAlvoTodas] = useState(true);
  const [selecionadas, setSelecionadas] = useState<Set<number>>(new Set());
  const [mostrarSeletor, setMostrarSeletor] = useState(false);

  const [editando, setEditando] = useState<string | null>(null);
  const [novoValor, setNovoValor] = useState<string>("");
  const [aplicando, setAplicando] = useState(false);

  function carregar() {
    setCarregando(true); setErro(null);
    Promise.all([fetchParametrosCowData(), fetchFazendasParametroCowData()])
      .then(([p, f]) => {
        setGrupos(p.grupos);
        setFazendas(f);
        setGrupoAtivo((atual) => atual && p.grupos[atual] ? atual : Object.keys(p.grupos)[0] || "");
      })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  }
  useEffect(() => { carregar(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  function fazendaIdsAlvo(): number[] | null {
    if (alvoTodas) return null;
    return [...selecionadas];
  }
  function toggleSelecionada(id: number) {
    setSelecionadas((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }

  function comecarEdicao(item: ItemParametroCowData) {
    setEditando(item.chave);
    setNovoValor(item.valor_global == null ? "" : String(item.valor_global));
    setAviso(null);
  }

  async function aplicar(item: ItemParametroCowData) {
    setAplicando(true); setErro(null); setAviso(null);
    try {
      const valor: number | boolean | string =
        item.tipo === "bool" ? novoValor === "true" :
        item.tipo === "float" ? Number(novoValor) :
        item.tipo === "int" ? Number(novoValor) : novoValor;
      const r = await aplicarParametroCowData(item.chave, { valor, fazenda_ids: fazendaIdsAlvo() });
      setAviso(
        r.global_atualizado
          ? `Padrão global atualizado e aplicado em ${r.atualizados} fazenda(s) ativa(s).`
          : `Aplicado em ${r.atualizados} fazenda(s) selecionada(s), sem mudar o padrão global.`
      );
      setEditando(null);
      carregar();
    } catch (e: any) { setErro(e.message); }
    finally { setAplicando(false); }
  }

  const grupoAtual = grupos[grupoAtivo];

  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <SlidersHorizontal size={18} style={{ color: COR.dourado }} />
        <h1 style={{ fontSize: "1.2rem", fontWeight: 700, color: COR.texto, margin: 0 }}>Parâmetros</h1>
      </div>
      <p style={{ fontSize: "0.82rem", color: COR.mudo, marginBottom: "1rem" }}>
        Metas e configurações de manejo, agenda, RH e financeiro (padrão que toda fazenda usa até personalizar). "Todas as
        fazendas ativas" sobrescreve inclusive quem já tinha personalizado — para mudar só onde ainda ninguém mexeu, use
        "Selecionar fazendas específicas".
      </p>

      {erro && <p style={{ color: COR.vermelho, fontSize: "0.82rem", marginBottom: "0.6rem" }}>{erro}</p>}
      {aviso && <p style={{ color: COR.verde, fontSize: "0.82rem", marginBottom: "0.6rem" }}>{aviso}</p>}

      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        {Object.entries(grupos).map(([id, g]) => (
          <button key={id} onClick={() => { setGrupoAtivo(id); setEditando(null); }}
            style={{ fontSize: "0.76rem", padding: "0.32rem 0.75rem", borderRadius: 999, cursor: "pointer",
              border: "1px solid " + (grupoAtivo === id ? COR.dourado : COR.borda),
              background: grupoAtivo === id ? "rgba(107,127,153,0.25)" : "transparent",
              color: grupoAtivo === id ? COR.texto : COR.mudo, fontWeight: grupoAtivo === id ? 700 : 500 }}>
            {g.titulo}
          </button>
        ))}
      </div>

      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: 10, padding: "0.9rem 1rem", marginBottom: "1rem" }}>
        <p style={{ fontSize: "0.7rem", color: COR.mudo, marginBottom: "0.5rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Aplicar em</p>
        <div className="flex items-center gap-4" style={{ flexWrap: "wrap" }}>
          <label className="flex items-center gap-2" style={{ fontSize: "0.82rem", color: COR.texto, cursor: "pointer" }}>
            <input type="radio" checked={alvoTodas} onChange={() => setAlvoTodas(true)} /> Todas as fazendas ativas ({fazendas.length})
          </label>
          <label className="flex items-center gap-2" style={{ fontSize: "0.82rem", color: COR.texto, cursor: "pointer" }}>
            <input type="radio" checked={!alvoTodas} onChange={() => { setAlvoTodas(false); setMostrarSeletor(true); }} /> Selecionar fazendas específicas
          </label>
          {!alvoTodas && (
            <button style={btnGhost} onClick={() => setMostrarSeletor((v) => !v)}>
              {mostrarSeletor ? "Esconder lista" : "Escolher fazendas"} {selecionadas.size > 0 && `(${selecionadas.size})`}
            </button>
          )}
        </div>
        {!alvoTodas && mostrarSeletor && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-1" style={{ marginTop: "0.6rem", maxHeight: 160, overflowY: "auto" }}>
            {fazendas.map((f) => (
              <label key={f.id} className="flex items-center gap-2" style={{ fontSize: "0.78rem", color: COR.texto, cursor: "pointer" }}>
                <input type="checkbox" checked={selecionadas.has(f.id)} onChange={() => toggleSelecionada(f.id)} /> {f.nome}
              </label>
            ))}
          </div>
        )}
      </div>

      {carregando ? (
        <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Carregando…</p>
      ) : !grupoAtual ? (
        <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Nenhum parâmetro encontrado.</p>
      ) : (
        <div style={{ border: `1px solid ${COR.borda}`, borderRadius: 10, overflow: "hidden" }}>
          {grupoAtual.itens.map((item, i) => (
            <div key={item.chave} style={{
              display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.65rem 0.9rem",
              borderTop: i === 0 ? "none" : `1px solid ${COR.borda}`, background: COR.cartao, flexWrap: "wrap",
            }}>
              <div style={{ flex: "1 1 220px", minWidth: 0 }}>
                <span style={{ color: COR.texto, fontSize: "0.85rem", fontWeight: 600 }}>{item.label}</span>
                {item.total_personalizados > 0 && (
                  <span style={{ marginLeft: "0.5rem", fontSize: "0.68rem", color: COR.mudo }}>
                    · {item.total_personalizados} fazenda(s) personalizaram
                  </span>
                )}
              </div>
              {editando === item.chave ? (
                <div className="flex items-center gap-2" style={{ flex: "0 0 auto" }}>
                  {item.tipo === "bool" ? (
                    <select style={inputStyle} value={novoValor} onChange={(e) => setNovoValor(e.target.value)}>
                      <option value="true">Sim</option>
                      <option value="false">Não</option>
                    </select>
                  ) : (
                    <input
                      style={{ ...inputStyle, width: item.tipo === "date" ? 160 : 100 }}
                      type={item.tipo === "date" ? "date" : "number"}
                      step={item.tipo === "float" ? "0.01" : "1"}
                      value={novoValor}
                      onChange={(e) => setNovoValor(e.target.value)}
                    />
                  )}
                  {item.unidade && <span style={{ color: COR.mudo, fontSize: "0.76rem" }}>{item.unidade}</span>}
                  <button style={{ ...btnPrimario, opacity: aplicando ? 0.6 : 1 }} onClick={() => aplicar(item)} disabled={aplicando}>
                    <Check size={13} /> {aplicando ? "Aplicando…" : "Aplicar"}
                  </button>
                  <button style={btnGhost} onClick={() => setEditando(null)}>Cancelar</button>
                </div>
              ) : (
                <div className="flex items-center gap-2" style={{ flex: "0 0 auto" }}>
                  <span style={{ color: COR.texto, fontSize: "0.85rem", fontWeight: 700 }}>
                    {item.tipo === "bool" ? (item.valor_global ? "Sim" : "Não") : String(item.valor_global ?? "—")}
                    {item.unidade && <span style={{ color: COR.mudo, fontWeight: 400 }}> {item.unidade}</span>}
                  </span>
                  <button style={btnGhost} onClick={() => comecarEdicao(item)}>
                    <Pencil size={12} /> Editar
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
