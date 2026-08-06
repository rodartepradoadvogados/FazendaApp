"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import { ClipboardList, Plus, Pencil, AlertTriangle, Check, X, Trash2, Search } from "lucide-react";
import {
  fetchProtocolosCustomizados, criarProtocoloCustomizado, atualizarProtocoloCustomizado, excluirProtocoloCustomizado,
  fetchEstoque, CATEGORIAS_PROTOCOLO_CUSTOM, TIPOS_PROTOCOLO_CUSTOM,
  type ProtocoloCustomizado, type EtapaProtocoloCustomizado,
} from "@/lib/api";
import { VIAS_APLICACAO, UNIDADES_PROTOCOLO } from "@/lib/constants";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { type EstoqueItem } from "@/components/lancamentos/comumForms";

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
const buscaInputStyle: React.CSSProperties = { width: "100%", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "8px", padding: "0.5rem 0.75rem 0.5rem 2rem", fontSize: "0.85rem" };

const normalizar = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

type ProtocoloForm = {
  nome: string; categoria: string; tipo: string; dia_inicial: number; observacao: string; ativo: boolean;
  etapas: EtapaProtocoloCustomizado[];
};
const etapaVazia = (dia: number): EtapaProtocoloCustomizado => ({ dia, descricao_evento: "", insumo_padrao: "", dose: null, unidade: "", via: "", observacao: "" });
// Protocolos novos nascem em D0, mesmo padrão dos demais protocolos do sistema
// (indução de lactação, IATF, sanitário).
const protocoloFormVazio = (): ProtocoloForm => ({ nome: "", categoria: "Atividades", tipo: "", dia_inicial: 0, observacao: "", ativo: true, etapas: [etapaVazia(0)] });

export default function CadastroProtocolosCustomizados() {
  const [itens, setItens] = useState<ProtocoloCustomizado[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<ProtocoloForm>(protocoloFormVazio());
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");

  const carregar = () => fetchProtocolosCustomizados().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const abrirNovo = () => { setForm(protocoloFormVazio()); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (p: ProtocoloCustomizado) => {
    setForm({
      nome: p.nome, categoria: p.categoria, tipo: p.tipo || "", dia_inicial: p.dia_inicial, observacao: p.observacao || "", ativo: p.ativo,
      etapas: p.etapas.length ? p.etapas.map((e) => ({ ...e })) : [etapaVazia(p.dia_inicial)],
    });
    setEditando(p.id); setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const acrescentarEtapa = () => setForm((f) => ({ ...f, etapas: [...f.etapas, etapaVazia(f.etapas.length)] }));
  const removerEtapa = (idx: number) => setForm((f) => (f.etapas.length > 1 ? { ...f, etapas: f.etapas.filter((_, i) => i !== idx) } : f));
  const atualizarEtapa = (idx: number, patch: Partial<EtapaProtocoloCustomizado>) =>
    setForm((f) => ({ ...f, etapas: f.etapas.map((e, i) => (i === idx ? { ...e, ...patch } : e)) }));

  const excluir = async (p: ProtocoloCustomizado) => {
    if (!window.confirm(`Excluir o protocolo "${p.nome}"?`)) return;
    try { await excluirProtocoloCustomizado(p.id); await carregar(); }
    catch (e: any) { setError(e.message); }
  };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    if (form.etapas.some((e) => e.dia < 0)) { setMsg("O dia da etapa não pode ser negativo (o protocolo pode começar em D0)."); return; }
    if (form.etapas.some((e) => !e.descricao_evento.trim())) { setMsg("Descreva o que fazer em cada etapa."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados = {
        nome: form.nome.trim(), categoria: form.categoria, tipo: form.tipo || null, dia_inicial: form.dia_inicial,
        observacao: form.observacao.trim() || undefined, ativo: form.ativo,
        etapas: form.etapas.map((e) => ({
          ...e, dia: Number(e.dia), descricao_evento: e.descricao_evento.trim(),
          insumo_padrao: e.insumo_padrao?.trim() || undefined, dose: e.dose ? Number(e.dose) : undefined,
          unidade: e.unidade || undefined, via: e.via || undefined, observacao: e.observacao?.trim() || undefined,
        })),
      };
      if (editando === "novo") await criarProtocoloCustomizado(dados);
      else if (typeof editando === "number") await atualizarProtocoloCustomizado(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((p) => !termoBusca || normalizar(`${p.nome} ${p.categoria}`).includes(termoBusca));
  const categoriaLabel = (v: string) => CATEGORIAS_PROTOCOLO_CUSTOM.find(([val]) => val === v)?.[1] || v;
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(filtrados);

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><ClipboardList size={16} /> Protocolos personalizados</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Crie um roteiro próprio de etapas (dia, o que fazer e insumo sugerido) para qualquer rotina que não se encaixe
        nos protocolos prontos do sistema — ex.: um checklist de recepção de bezerras, uma rotina de pastejo rotacionado
        ou um calendário de manutenção. Depois de cadastrado, o protocolo fica disponível em <strong>Lançamentos</strong>
        para aplicar contra animais, um lote ou como tarefa geral da fazenda, e as pendências aparecem na <strong>Agenda</strong>.
        Os dias começam em D0, como os demais protocolos do sistema.
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && (
        <FormProtocoloCustomizado
          form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
          acrescentarEtapa={acrescentarEtapa} removerEtapa={removerEtapa} atualizarEtapa={atualizarEtapa}
        />
      )}

      {itens && (
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar protocolo…" />
          </div>
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr><ThOrdenavel label="Nome" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} /><ThOrdenavel label="Categoria" campo="categoria" coluna={coluna} dir={dir} ordenar={ordenar} /><th>Tipo</th><th>Etapas</th><th></th></tr></thead>
              <tbody>
                {linhasOrdenadas.map((p) => (
                  <Fragment key={p.id}>
                    <tr>
                      <td style={{ fontWeight: 700 }}>{p.nome}{!p.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                      <td style={{ fontSize: "0.78rem" }}>{categoriaLabel(p.categoria)}</td>
                      <td style={{ fontSize: "0.78rem" }}>{p.tipo ? (TIPOS_PROTOCOLO_CUSTOM.find(([v]) => v === p.tipo)?.[1] || p.tipo) : <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                      <td style={{ fontSize: "0.78rem" }}>{p.etapas.map((e) => `D${e.dia - p.dia_inicial}`).join(", ")}</td>
                      <td style={{ textAlign: "right", display: "flex", justifyContent: "flex-end", gap: "0.4rem" }}>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(p)}>
                          <Pencil size={13} /> Editar
                        </button>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => excluir(p)}>
                          <Trash2 size={13} /> Excluir
                        </button>
                      </td>
                    </tr>
                    {editando === p.id && (
                      <tr><td colSpan={5} style={{ padding: 0 }}>
                        <FormProtocoloCustomizado
                          form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
                          acrescentarEtapa={acrescentarEtapa} removerEtapa={removerEtapa} atualizarEtapa={atualizarEtapa}
                        />
                      </td></tr>
                    )}
                  </Fragment>
                ))}
                {!itens.length && !editando && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum protocolo personalizado cadastrado ainda.</td></tr>}
                {!!itens.length && !filtrados.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function FormProtocoloCustomizado({ form, setForm, onSalvar, onCancelar, salvando, msg, acrescentarEtapa, removerEtapa, atualizarEtapa }: {
  form: ProtocoloForm; setForm: (f: ProtocoloForm) => void;
  onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
  acrescentarEtapa: () => void; removerEtapa: (idx: number) => void; atualizarEtapa: (idx: number, patch: Partial<EtapaProtocoloCustomizado>) => void;
}) {
  // Insumo sugerido: cada etapa pode vir do estoque (com opção de mostrar
  // itens sem saldo) ou de texto livre — permanece só informativo (ver nota
  // abaixo), o modo é puramente uma facilidade de preenchimento.
  const [estoque, setEstoque] = useState<EstoqueItem[]>([]);
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  const [modoInsumo, setModoInsumo] = useState<Record<number, "estoque" | "livre">>({});

  useEffect(() => { fetchEstoque().then((d) => setEstoque(d.itens || [])).catch(() => {}); }, []);

  const estoqueVisivel = useMemo(
    () => estoque.filter((it) => incluirSemEstoque || (it.quantidade ?? 0) > 0).sort((a, b) => a.nome.localeCompare(b.nome)),
    [estoque, incluirSemEstoque],
  );
  const modoDaEtapa = (idx: number, valorAtual: string) =>
    modoInsumo[idx] ?? (valorAtual && estoque.some((it) => it.nome === valorAtual) ? "estoque" : "livre");

  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Nome</label>
          <input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder="ex.: Recepção de bezerras" /></div>
        <div><label style={labelStyle}>Categoria</label>
          <select style={inputStyle} value={form.categoria} onChange={(e) => setForm({ ...form, categoria: e.target.value })}>
            {CATEGORIAS_PROTOCOLO_CUSTOM.map(([v, lbl]) => <option key={v} value={v}>{lbl}</option>)}
          </select></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Tipo (Central de Protocolos)</label>
          <select style={inputStyle} value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })}>
            <option value="">Sem tipo — fora de Acompanhamento/Histórico</option>
            {TIPOS_PROTOCOLO_CUSTOM.map(([v, lbl]) => <option key={v} value={v}>{lbl}</option>)}
          </select>
          <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
            Só entra nos filtros por tipo da Central de Protocolos se isto estiver preenchido.
          </p>
        </div>
      </div>
      <div className="mb-3"><label style={labelStyle}>Observação (opcional)</label>
        <input style={inputStyle} value={form.observacao} onChange={(e) => setForm({ ...form, observacao: e.target.value })} placeholder="Contexto geral do protocolo" /></div>

      <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.2rem" }}>Etapas (D0, D1, D2...)</p>
      <label className="flex items-center gap-2" style={{ fontSize: "0.72rem", color: "var(--text-muted)", cursor: "pointer", marginBottom: "0.5rem" }}>
        <input type="checkbox" checked={incluirSemEstoque} onChange={(e) => setIncluirSemEstoque(e.target.checked)} />
        Ao selecionar do estoque, incluir itens sem saldo
      </label>
      <div className="space-y-2 mb-2">
        {form.etapas.map((e, idx) => {
          const modo = modoDaEtapa(idx, e.insumo_padrao || "");
          return (
          <div key={idx} className="grid grid-cols-2 md:grid-cols-8 gap-2 items-end" style={{ background: "var(--surface)", padding: "0.5rem", borderRadius: "6px" }}>
            <div><label style={labelStyle}>Dia (D)</label><input type="number" min={0} style={inputStyle} value={e.dia} onChange={(ev) => atualizarEtapa(idx, { dia: Number(ev.target.value) })} /></div>
            <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>O que fazer</label>
              <input style={inputStyle} value={e.descricao_evento} onChange={(ev) => atualizarEtapa(idx, { descricao_evento: ev.target.value })} placeholder="ex.: Pesar e vermifugar" /></div>
            <div>
              <div className="flex items-center justify-between" style={{ marginBottom: "0.15rem" }}>
                <label style={labelStyle}>Insumo sugerido</label>
                <select
                  style={{ background: "transparent", color: "var(--text-muted)", border: "none", fontSize: "0.68rem", cursor: "pointer" }}
                  value={modo}
                  onChange={(ev) => setModoInsumo((m) => ({ ...m, [idx]: ev.target.value as "estoque" | "livre" }))}
                >
                  <option value="estoque">do estoque</option>
                  <option value="livre">texto livre</option>
                </select>
              </div>
              {modo === "estoque" ? (
                <select style={inputStyle} value={e.insumo_padrao || ""} onChange={(ev) => atualizarEtapa(idx, { insumo_padrao: ev.target.value })}>
                  <option value="">Selecione…</option>
                  {/* Item já salvo que não bate com o estoque visível (fora de linha, ou saldo zerado com o checkbox desmarcado) continua listado para não sumir. */}
                  {e.insumo_padrao && !estoqueVisivel.some((it) => it.nome === e.insumo_padrao) && <option value={e.insumo_padrao}>{e.insumo_padrao}</option>}
                  {estoqueVisivel.map((it) => <option key={it.nome} value={it.nome}>{it.nome}{it.quantidade != null ? ` (${it.quantidade} ${it.unidade || ""})` : ""}</option>)}
                </select>
              ) : (
                <input style={inputStyle} value={e.insumo_padrao || ""} onChange={(ev) => atualizarEtapa(idx, { insumo_padrao: ev.target.value })} placeholder="texto livre — informativo" />
              )}
            </div>
            <div><label style={labelStyle}>Dose</label><input type="number" inputMode="decimal" style={inputStyle} value={e.dose ?? ""} onChange={(ev) => atualizarEtapa(idx, { dose: ev.target.value ? Number(ev.target.value) : null })} /></div>
            <div><label style={labelStyle}>Unidade</label>
              <select style={inputStyle} value={e.unidade || ""} onChange={(ev) => atualizarEtapa(idx, { unidade: ev.target.value })}>
                <option value="">—</option>
                {/* Unidade fora da lista (protocolo antigo) continua visível para não sumir ao editar. */}
                {e.unidade && !UNIDADES_PROTOCOLO.includes(e.unidade) && <option value={e.unidade}>{e.unidade}</option>}
                {UNIDADES_PROTOCOLO.map((u) => <option key={u} value={u}>{u}</option>)}
              </select></div>
            <div><label style={labelStyle}>Via</label>
              <select style={inputStyle} value={e.via || ""} onChange={(ev) => atualizarEtapa(idx, { via: ev.target.value })}>
                <option value="">—</option>{VIAS_APLICACAO.map((v) => <option key={v}>{v}</option>)}
              </select></div>
            <div className="flex items-end gap-1">
              <div style={{ flex: 1 }}><label style={labelStyle}>Observação</label>
                <input style={inputStyle} value={e.observacao || ""} onChange={(ev) => atualizarEtapa(idx, { observacao: ev.target.value })} placeholder="ex.: Se necessário" /></div>
              {form.etapas.length > 1 && <button type="button" className="btn-ghost" style={{ color: "var(--red)" }} onClick={() => removerEtapa(idx)}><Trash2 size={13} /></button>}
            </div>
          </div>
          );
        })}
      </div>
      <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem", marginBottom: "0.8rem" }} onClick={acrescentarEtapa}>
        <Plus size={14} /> Acrescentar etapa
      </button>

      <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.8rem" }}>
        O insumo é apenas informativo — não gera baixa automática de estoque nem evento de Sanidade. Para tratamentos
        que exigem controle de estoque/mastite, use o Protocolo sanitário (Cadastro › Sanitário).
      </p>

      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onSalvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onCancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );
}
