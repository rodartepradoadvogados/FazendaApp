"use client";
// Farmácia — a aba única que junta o catálogo de INDICAÇÕES (doença/manejo:
// reprodutivo, produtivo, preventivo, suporte) com os PRINCÍPIOS que tratam
// cada uma (ordenados por prioridade) e as MARCAS comerciais de cada
// princípio, já com bula e carência formatada. O catálogo nasce global
// (mesmo documento base para todas as fazendas); quem quer editar bula,
// prioridade ou nota PERSONALIZA a indicação primeiro (clona pra fazenda) —
// ver POST/DELETE /farmacia/indicacoes/{id}/personalizar no backend. Nunca dá
// pra editar a linha global direto (o backend devolve 404).
import { useEffect, useMemo, useState } from "react";
import {
  Search, Lock, Pencil, ChevronDown, ChevronRight, AlertTriangle, Ban, ExternalLink, RotateCcw, Check, X,
} from "lucide-react";
import {
  fetchIndicacoesCatalogo, personalizarIndicacao, despersonalizarIndicacao,
  atualizarMarcaFarmacia, atualizarVinculoIndicacao, fetchFarmaciaDetalhe, restaurarCatalogoPrincipios,
  type IndicacaoCatalogo, type PrincipioIndicacaoCatalogo, type MarcaIndicacaoCatalogo,
} from "@/lib/api";
import { carenciaNaoInformada } from "@/lib/carencia";
import { VIAS_APLICACAO } from "@/lib/constants";

// Normaliza texto para busca insensível a maiúsculas e acentos (mesmo
// critério usado no resto do Cadastro).
const normalizar = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

function num(v?: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
}

const TIPO_INFO: Record<string, { label: string; cor: string }> = {
  doenca: { label: "Doença", cor: "var(--cat-sanidade)" },
  reprodutivo: { label: "Reprodutivo", cor: "var(--cat-reproducao)" },
  produtivo: { label: "Produtivo", cor: "var(--blue)" },
  preventivo: { label: "Preventivo", cor: "var(--dourado-light)" },
  suporte: { label: "Suporte", cor: "var(--cat-acesso)" },
};
const TIPOS_FILTRO: [string, string][] = [
  ["", "Todas"], ["doenca", "Doenças"], ["reprodutivo", "Reprodutivo"],
  ["produtivo", "Produtivo"], ["preventivo", "Preventivo"], ["suporte", "Suporte"],
];

const input: React.CSSProperties = {
  padding: "0.4rem 0.55rem", borderRadius: 6, fontSize: "0.82rem",
  background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)",
};
const labelStyle: React.CSSProperties = { fontSize: "0.68rem", color: "var(--text-muted)" };

function labelPrioridade(p: number): string {
  return p === 1 ? "1ª ESCOLHA" : `${p}ª OPÇÃO`;
}

// Situação de estoque do princípio dentro do card — mesma leitura semafórica
// da Farmácia antiga, com o subconjunto de campos que o catálogo expõe.
function statusEstoque(p: PrincipioIndicacaoCatalogo): { cor: string; label: string } {
  if (p.precisa_inicializar) return { cor: "var(--amber)", label: "Inicializar estoque" };
  if (p.abaixo_minimo) return { cor: "var(--red)", label: "Abaixo do mínimo" };
  if (p.total_apresentacoes > 0) return { cor: "var(--green-light)", label: `${num(p.total_apresentacoes)} em estoque` };
  return { cor: "var(--text-muted)", label: "Sem estoque cadastrado" };
}

export default function Farmacia() {
  const [catalogo, setCatalogo] = useState<IndicacaoCatalogo[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [tipoFiltro, setTipoFiltro] = useState("");
  const [soPersonalizadas, setSoPersonalizadas] = useState(false);
  const [restaurando, setRestaurando] = useState(false);
  const [msgRestaurar, setMsgRestaurar] = useState<string | null>(null);

  const carregar = () => fetchIndicacoesCatalogo().then(setCatalogo).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); }, []);

  const restaurar = async () => {
    setRestaurando(true); setMsgRestaurar(null);
    try {
      const r = await restaurarCatalogoPrincipios();
      await carregar();
      setMsgRestaurar(`Catálogo restaurado: ${r.criados} adicionado(s), ${r.total} no total.`);
    } catch (e: any) {
      setMsgRestaurar(e.message || "Erro ao restaurar catálogo");
    } finally {
      setRestaurando(false);
    }
  };

  const lista = useMemo(() => {
    let l = catalogo || [];
    if (tipoFiltro) l = l.filter((i) => i.tipo === tipoFiltro);
    if (soPersonalizadas) l = l.filter((i) => i.personalizada);
    const q = normalizar(busca.trim());
    if (q) {
      l = l.filter((i) =>
        normalizar(i.nome).includes(q) ||
        i.principios.some((p) => normalizar(p.nome).includes(q) || p.marcas.some((m) => normalizar(m.nome_comercial).includes(q))));
    }
    return l;
  }, [catalogo, tipoFiltro, soPersonalizadas, busca]);

  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-2" style={{ flexWrap: "wrap" }}>
        <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", flex: "1 1 320px", margin: 0 }}>
          Uma indicação (doença ou finalidade de manejo) por card, com os princípios ativos indicados — em ordem de
          prioridade — e as marcas comerciais de cada um, com bula e carência. O catálogo é o mesmo para todas as
          fazendas; personalize uma indicação para editar bula, prioridade ou nota sem afetar as demais.
        </p>
        <button className="btn-ghost" style={{ fontSize: "0.75rem", display: "inline-flex", alignItems: "center", gap: "0.35rem", whiteSpace: "nowrap" }}
          onClick={restaurar} disabled={restaurando}
          title="(Re)carrega o catálogo padrão de princípios ativos (documento base) — só adiciona o que estiver faltando, nunca sobrescreve edições.">
          <RotateCcw size={13} /> {restaurando ? "Restaurando…" : "Restaurar catálogo"}
        </button>
      </div>
      {msgRestaurar && <p style={{ color: "var(--green-light)", fontSize: "0.78rem", marginBottom: "0.6rem" }}>{msgRestaurar}</p>}

      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: "1 1 240px", maxWidth: 340 }}>
          <Search size={14} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
          <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar indicação, princípio ou marca…"
            style={{ ...input, width: "100%", paddingLeft: "1.8rem" }} />
        </div>
        {TIPOS_FILTRO.map(([id, label]) => (
          <button key={id || "todas"} onClick={() => setTipoFiltro(id)}
            style={{ fontSize: "0.76rem", padding: "0.32rem 0.75rem", borderRadius: 999, cursor: "pointer",
              border: "1px solid " + (tipoFiltro === id ? "var(--dourado)" : "var(--border)"),
              background: tipoFiltro === id ? "rgba(94,26,46,0.4)" : "transparent",
              color: tipoFiltro === id ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: tipoFiltro === id ? 700 : 500 }}>
            {label}
          </button>
        ))}
        <button onClick={() => setSoPersonalizadas((v) => !v)}
          style={{ fontSize: "0.76rem", padding: "0.32rem 0.75rem", borderRadius: 999, cursor: "pointer",
            display: "inline-flex", alignItems: "center", gap: "0.3rem",
            border: "1px solid " + (soPersonalizadas ? "var(--dourado)" : "var(--border)"),
            background: soPersonalizadas ? "rgba(94,26,46,0.4)" : "transparent",
            color: soPersonalizadas ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: soPersonalizadas ? 700 : 500 }}>
          <Pencil size={12} /> Só personalizadas
        </button>
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}
      {!catalogo ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>
      ) : lista.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma indicação encontrada.</p>
      ) : (
        <div className="space-y-2">
          {lista.map((ind) => <CardIndicacao key={ind.id} ind={ind} onMudou={carregar} />)}
        </div>
      )}
    </div>
  );
}

function CardIndicacao({ ind, onMudou }: { ind: IndicacaoCatalogo; onMudou: () => void }) {
  const [aberto, setAberto] = useState(false);
  const [processando, setProcessando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const tipoInfo = TIPO_INFO[ind.tipo] || { label: ind.tipo, cor: "var(--text-muted)" };

  const personalizar = async () => {
    setProcessando(true); setErro(null);
    try { await personalizarIndicacao(ind.id); onMudou(); }
    catch (e: any) { setErro(e.message || "Erro ao personalizar"); }
    finally { setProcessando(false); }
  };
  const voltarPadrao = async () => {
    if (!window.confirm(`Voltar "${ind.nome}" ao padrão? Isso descarta as edições de bula/prioridade feitas para a sua fazenda nesta indicação.`)) return;
    setProcessando(true); setErro(null);
    try { await despersonalizarIndicacao(ind.id); onMudou(); }
    catch (e: any) { setErro(e.message || "Erro ao voltar ao padrão"); }
    finally { setProcessando(false); }
  };

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.7rem 0.9rem", background: "var(--surface-2)" }}>
        <button onClick={() => setAberto((v) => !v)}
          style={{ display: "flex", alignItems: "center", gap: "0.6rem", flex: 1, minWidth: 0, background: "none", border: "none", cursor: "pointer", color: "var(--text)", textAlign: "left", padding: 0 }}>
          {aberto ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          <span style={{
            fontSize: "0.64rem", fontWeight: 800, letterSpacing: "0.03em", textTransform: "uppercase",
            color: tipoInfo.cor, border: "1px solid " + tipoInfo.cor, borderRadius: 4, padding: "0.1rem 0.4rem", flexShrink: 0,
          }}>
            {tipoInfo.label}
          </span>
          <span style={{ flex: 1, minWidth: 0 }}>
            <span style={{ fontWeight: 700 }}>{ind.nome}</span>
            {ind.descricao && <span style={{ display: "block", fontSize: "0.72rem", color: "var(--text-muted)" }}>{ind.descricao}</span>}
          </span>
          <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", flexShrink: 0 }}>
            {ind.principios.length} princípio{ind.principios.length === 1 ? "" : "s"}
          </span>
        </button>
        <span style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: "0.4rem" }}>
          {ind.personalizada ? (
            <>
              <span title="Personalizada para a sua fazenda" style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.68rem", fontWeight: 700, color: "var(--dourado-light)" }}>
                <Pencil size={12} /> Personalizada
              </span>
              <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={voltarPadrao} disabled={processando}>
                {processando ? "Aguarde…" : "Voltar ao padrão"}
              </button>
            </>
          ) : (
            <>
              <span title="Catálogo padrão — compartilhado por todas as fazendas" style={{ display: "inline-flex", color: "var(--text-muted)" }}>
                <Lock size={14} />
              </span>
              <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={personalizar} disabled={processando}>
                {processando ? "Aguarde…" : "Personalizar para minha fazenda"}
              </button>
            </>
          )}
        </span>
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.78rem", padding: "0.4rem 0.9rem 0" }}>{erro}</p>}

      {aberto && (
        <div style={{ padding: "0.85rem" }}>
          {ind.principios.length === 0 ? (
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Nenhum princípio ativo indicado ainda para esta indicação.</p>
          ) : (
            <div className="space-y-3">
              {ind.principios.map((p) => (
                <PrincipioBloco key={p.id} p={p} indicacaoPersonalizada={ind.personalizada} onMudou={onMudou} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PrincipioBloco({ p, indicacaoPersonalizada, onMudou }: {
  p: PrincipioIndicacaoCatalogo; indicacaoPersonalizada: boolean; onMudou: () => void;
}) {
  const [editandoVinculo, setEditandoVinculo] = useState(false);
  const [prioridade, setPrioridade] = useState(String(p.prioridade));
  const [nota, setNota] = useState(p.nota || "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const status = statusEstoque(p);
  const primeiraEscolha = p.prioridade === 1;

  const salvarVinculo = async () => {
    setSalvando(true); setErro(null);
    try {
      await atualizarVinculoIndicacao(p.indicacao_id, { prioridade: Number(prioridade) || 1, nota: nota.trim() || null });
      setEditandoVinculo(false);
      onMudou();
    } catch (e: any) { setErro(e.message || "Erro ao salvar"); }
    finally { setSalvando(false); }
  };

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-2)", padding: "0.65rem 0.8rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
        <span style={{
          fontSize: "0.66rem", fontWeight: 800, borderRadius: 4, padding: "0.15rem 0.4rem", flexShrink: 0, whiteSpace: "nowrap",
          ...(primeiraEscolha
            ? { border: "1px solid var(--dourado)", color: "var(--dourado-light)", background: "rgba(184,134,11,0.12)" }
            : { border: "1px solid var(--border)", color: "var(--text-muted)" }),
        }}>
          {labelPrioridade(p.prioridade)}
        </span>
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: status.cor, flexShrink: 0 }} title={status.label} />
        <span style={{ flex: 1, minWidth: 0, fontWeight: 700 }}>
          {p.nome}
          {p.categoria_software && <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: "0.72rem" }}> · {p.categoria_software}</span>}
        </span>
        <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", flexShrink: 0 }}>{status.label}</span>
        {indicacaoPersonalizada && (
          <button className="btn-ghost" style={{ fontSize: "0.68rem", padding: "0.15rem 0.5rem" }} onClick={() => setEditandoVinculo((v) => !v)} title="Editar prioridade/nota">
            <Pencil size={11} />
          </button>
        )}
      </div>
      {p.nota && !editandoVinculo && <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", margin: "0.3rem 0 0" }}>{p.nota}</p>}

      {editandoVinculo && (
        <div className="flex items-end gap-2" style={{ marginTop: "0.5rem", flexWrap: "wrap" }}>
          <div><label style={labelStyle}>Prioridade</label>
            <input type="number" min={1} style={{ ...input, width: 80 }} value={prioridade} onChange={(e) => setPrioridade(e.target.value)} /></div>
          <div style={{ flex: "1 1 200px" }}><label style={labelStyle}>Nota</label>
            <input style={{ ...input, width: "100%" }} value={nota} onChange={(e) => setNota(e.target.value)} placeholder="opcional" /></div>
          <button className="btn-primary" style={{ fontSize: "0.72rem" }} onClick={salvarVinculo} disabled={salvando}>
            <Check size={12} /> {salvando ? "Salvando…" : "Salvar"}
          </button>
          <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setEditandoVinculo(false)}><X size={12} /></button>
          {erro && <span style={{ color: "var(--red)", fontSize: "0.74rem" }}>{erro}</span>}
        </div>
      )}

      {p.marcas.length === 0 ? (
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>Nenhuma marca comercial cadastrada para este princípio.</p>
      ) : (
        <div className="space-y-2" style={{ marginTop: "0.55rem" }}>
          {p.marcas.map((m) => <MarcaLinha key={m.id} m={m} principioId={p.id} onMudou={onMudou} />)}
        </div>
      )}
    </div>
  );
}

function MarcaLinha({ m, principioId, onMudou }: { m: MarcaIndicacaoCatalogo; principioId: number; onMudou: () => void }) {
  const [editando, setEditando] = useState(false);
  const semInfo = carenciaNaoInformada(m.carencia);

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--surface)", padding: "0.55rem 0.7rem" }}>
      <div className="flex items-start justify-between gap-2" style={{ flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 220px", minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
            {m.nome_comercial}
            {m.laboratorio && <span style={{ fontWeight: 400, fontSize: "0.72rem", color: "var(--text-muted)" }}>— {m.laboratorio}</span>}
            {m.link_bula && (
              <a href={m.link_bula} target="_blank" rel="noopener noreferrer" title="Ver bula"
                style={{ color: "var(--dourado-light)", display: "inline-flex" }}>
                <ExternalLink size={12} />
              </a>
            )}
          </div>
          {m.uso_principal && <div style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>{m.uso_principal}</div>}
          <div style={{ fontSize: "0.76rem", color: "var(--text)", marginTop: "0.15rem" }}>
            {m.dose_texto || (m.dose_padrao != null ? `${num(m.dose_padrao)} ${m.unidade_dose || ""}` : "Dose não informada")}
            {m.via_padrao && <span style={{ color: "var(--text-muted)" }}> · {m.via_padrao}</span>}
          </div>
        </div>

        {m.editavel && (
          <button className="btn-ghost" style={{ fontSize: "0.7rem", flexShrink: 0 }} onClick={() => setEditando((v) => !v)}>
            <Pencil size={12} /> {editando ? "Fechar" : "Editar bula"}
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 flex-wrap" style={{ marginTop: "0.45rem" }}>
        {m.carencia.proibido_lactacao ? (
          <span style={{
            display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.72rem", fontWeight: 800,
            color: "#fff", background: "var(--red)", border: "1px solid var(--red)", borderRadius: 999, padding: "0.2rem 0.65rem",
          }}>
            <Ban size={12} /> NÃO USAR EM LACTAÇÃO
          </span>
        ) : (
          <span style={{ fontSize: "0.72rem", fontWeight: semInfo ? 500 : 600, color: semInfo ? "var(--text-muted)" : "var(--text)", fontStyle: semInfo ? "italic" : "normal" }}>
            {m.carencia.texto}
          </span>
        )}
        {(m.alerta_gestacao || m.alerta) && (
          <span title={m.alerta || undefined} style={{
            display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.7rem", fontWeight: 700,
            color: "var(--amber)", background: "rgba(217,119,6,0.1)", border: "1px solid var(--amber)", borderRadius: 999, padding: "0.15rem 0.55rem",
          }}>
            <AlertTriangle size={11} /> {m.alerta_gestacao ? "Atenção — gestação" : "Alerta"}
          </span>
        )}
      </div>

      {editando && (
        <FormEdicaoMarca principioId={principioId} marcaId={m.id}
          onSalvo={() => { setEditando(false); onMudou(); }} onCancelar={() => setEditando(false)} />
      )}
    </div>
  );
}

// Formulário de bula — carrega o registro COMPLETO da marca (via
// /farmacia/principios/{id}, que devolve todos os campos de MedicamentoComercial)
// antes de editar, porque o PUT /farmacia/medicamentos/{id} substitui a marca
// inteira: usar só os campos do catálogo (que não inclui dose_base/
// dose_referencia_kg/ativo) apagaria esses campos ao salvar.
function FormEdicaoMarca({ principioId, marcaId, onSalvo, onCancelar }: {
  principioId: number; marcaId: number; onSalvo: () => void; onCancelar: () => void;
}) {
  const [form, setForm] = useState<Record<string, any> | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    fetchFarmaciaDetalhe(principioId)
      .then((d: any) => {
        if (cancelado) return;
        const full = (d.marcas || []).find((mm: any) => mm.id === marcaId);
        if (!full) { setErro("Marca não encontrada"); return; }
        setForm({ ...full });
      })
      .catch((e: any) => !cancelado && setErro(e.message || "Erro ao carregar a marca"))
      .finally(() => !cancelado && setCarregando(false));
    return () => { cancelado = true; };
  }, [principioId, marcaId]);

  const salvar = async () => {
    if (!form) return;
    setSalvando(true); setErro(null);
    try {
      await atualizarMarcaFarmacia(marcaId, {
        ...form,
        dose_padrao: form.dose_padrao === "" ? null : Number(form.dose_padrao),
        dose_referencia_kg: form.dose_referencia_kg === "" ? null : Number(form.dose_referencia_kg),
        carencia_leite_dias: form.carencia_leite_dias === "" || form.carencia_leite_dias == null ? null : Number(form.carencia_leite_dias),
        carencia_carne_dias: form.carencia_carne_dias === "" || form.carencia_carne_dias == null ? null : Number(form.carencia_carne_dias),
      });
      onSalvo();
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar a bula");
    } finally {
      setSalvando(false);
    }
  };

  if (carregando) return <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>Carregando…</p>;
  if (!form) return <p style={{ fontSize: "0.76rem", color: "var(--red)", marginTop: "0.5rem" }}>{erro || "Não foi possível carregar."}</p>;

  const set = (k: string, v: any) => setForm((f) => (f ? { ...f, [k]: v } : f));

  return (
    <div style={{ marginTop: "0.6rem", padding: "0.6rem", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 6 }}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-2">
        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Uso principal</label>
          <input style={{ ...input, width: "100%" }} value={form.uso_principal || ""} onChange={(e) => set("uso_principal", e.target.value)} /></div>
        <div><label style={labelStyle}>Concentração</label>
          <input style={{ ...input, width: "100%" }} value={form.concentracao || ""} onChange={(e) => set("concentracao", e.target.value)} /></div>

        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Dose (texto exibido)</label>
          <input style={{ ...input, width: "100%" }} value={form.dose_texto || ""} onChange={(e) => set("dose_texto", e.target.value)} placeholder="ex.: 1 ml/50kg PV" /></div>
        <div><label style={labelStyle}>Via</label>
          <select style={{ ...input, width: "100%" }} value={form.via_padrao || ""} onChange={(e) => set("via_padrao", e.target.value)}>
            <option value="">—</option>{VIAS_APLICACAO.map((v) => <option key={v} value={v}>{v}</option>)}
          </select></div>

        <div><label style={labelStyle}>Dose padrão</label>
          <input type="number" inputMode="decimal" style={{ ...input, width: "100%" }} value={form.dose_padrao ?? ""} onChange={(e) => set("dose_padrao", e.target.value)} /></div>
        <div><label style={labelStyle}>Unidade da dose</label>
          <input style={{ ...input, width: "100%" }} value={form.unidade_dose || ""} onChange={(e) => set("unidade_dose", e.target.value)} placeholder="ml, unidade…" /></div>
        <div><label style={labelStyle}>Laboratório</label>
          <input style={{ ...input, width: "100%" }} value={form.laboratorio || ""} onChange={(e) => set("laboratorio", e.target.value)} /></div>

        <div style={{ gridColumn: "span 3" }}><label style={labelStyle}>Link da bula</label>
          <input style={{ ...input, width: "100%" }} value={form.link_bula || ""} onChange={(e) => set("link_bula", e.target.value)} placeholder="https://…" /></div>

        <div><label style={labelStyle}>Carência do leite (dias)</label>
          <input type="number" min={0} style={{ ...input, width: "100%" }} value={form.carencia_leite_dias ?? ""} onChange={(e) => set("carencia_leite_dias", e.target.value)} disabled={!!form.proibido_lactacao} /></div>
        <div><label style={labelStyle}>Carência da carne (dias)</label>
          <input type="number" min={0} style={{ ...input, width: "100%" }} value={form.carencia_carne_dias ?? ""} onChange={(e) => set("carencia_carne_dias", e.target.value)} /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.76rem" }}>
          <input type="checkbox" checked={!!form.proibido_lactacao} onChange={(e) => set("proibido_lactacao", e.target.checked)} /> Não usar em lactação</label></div>

        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Alerta (texto)</label>
          <input style={{ ...input, width: "100%" }} value={form.alerta || ""} onChange={(e) => set("alerta", e.target.value)} placeholder="opcional" /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.76rem" }}>
          <input type="checkbox" checked={!!form.alerta_gestacao} onChange={(e) => set("alerta_gestacao", e.target.checked)} /> Alerta de gestação</label></div>
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.76rem", marginBottom: "0.4rem" }}>{erro}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.74rem" }} onClick={salvar} disabled={salvando}>
          <Check size={13} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.74rem" }} onClick={onCancelar}>
          <X size={13} /> Cancelar
        </button>
      </div>
    </div>
  );
}
