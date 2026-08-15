"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import { ClipboardList, Plus, Pencil, AlertTriangle, Check, X, Trash2, Search } from "lucide-react";
import {
  fetchLidas, criarLida, atualizarLida, excluirLida, fetchEstoque,
  type Lida, type EtapaLida,
} from "@/lib/api";
import { UNIDADES_PROTOCOLO } from "@/lib/constants";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { type EstoqueItem } from "@/components/lancamentos/comumForms";
import { normalizarBusca as normalizar } from "@/lib/busca";

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
const buscaInputStyle: React.CSSProperties = { width: "100%", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.75rem 0.5rem 2rem", fontSize: "0.85rem" };

type LidaForm = {
  nome: string; modo: "periodo" | "frequencia"; dia_inicial: number;
  frequencia_dias: number | null; descricao_evento: string;
  insumo_padrao: string; insumo_dose: number | null; insumo_unidade: string;
  foto_obrigatoria: boolean; dar_baixa_estoque: boolean; vincular_financeiro: boolean;
  observacao: string; ativo: boolean; etapas: EtapaLida[];
};
const etapaVazia = (dia: number): EtapaLida => ({
  dia_inicio: dia, dia_fim: null, descricao_evento: "", insumo_padrao: "", insumo_dose: null, insumo_unidade: "", foto_obrigatoria: false,
});
const lidaFormVazio = (): LidaForm => ({
  nome: "", modo: "frequencia", dia_inicial: 0, frequencia_dias: 15, descricao_evento: "",
  insumo_padrao: "", insumo_dose: null, insumo_unidade: "", foto_obrigatoria: false,
  dar_baixa_estoque: false, vincular_financeiro: false, observacao: "", ativo: true, etapas: [etapaVazia(0)],
});

export default function CadastroLida() {
  const [itens, setItens] = useState<Lida[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<LidaForm>(lidaFormVazio());
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [estoque, setEstoque] = useState<EstoqueItem[]>([]);

  const carregar = () => fetchLidas().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); fetchEstoque().then((d) => setEstoque(d.itens || [])).catch(() => {}); }, []);

  const abrirNovo = () => { setForm(lidaFormVazio()); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (l: Lida) => {
    setForm({
      nome: l.nome, modo: l.modo, dia_inicial: l.dia_inicial,
      frequencia_dias: l.frequencia_dias, descricao_evento: l.descricao_evento || "",
      insumo_padrao: l.insumo_padrao || "", insumo_dose: l.insumo_dose, insumo_unidade: l.insumo_unidade || "",
      foto_obrigatoria: l.foto_obrigatoria, dar_baixa_estoque: l.dar_baixa_estoque, vincular_financeiro: l.vincular_financeiro,
      observacao: l.observacao || "", ativo: l.ativo,
      etapas: l.etapas.length ? l.etapas.map((e) => ({ ...e })) : [etapaVazia(l.dia_inicial)],
    });
    setEditando(l.id); setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const acrescentarEtapa = () => setForm((f) => ({ ...f, etapas: [...f.etapas, etapaVazia(f.etapas.length)] }));
  const removerEtapa = (idx: number) => setForm((f) => (f.etapas.length > 1 ? { ...f, etapas: f.etapas.filter((_, i) => i !== idx) } : f));
  const atualizarEtapa = (idx: number, patch: Partial<EtapaLida>) =>
    setForm((f) => ({ ...f, etapas: f.etapas.map((e, i) => (i === idx ? { ...e, ...patch } : e)) }));

  const excluir = async (l: Lida) => {
    if (!window.confirm(`Excluir a lida "${l.nome}"?`)) return;
    try { await excluirLida(l.id); await carregar(); }
    catch (e: any) { setError(e.message); }
  };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    if (form.modo === "frequencia") {
      if (!form.frequencia_dias || form.frequencia_dias <= 0) { setMsg("Informe a cada quantos dias esta lida se repete."); return; }
      if (!form.descricao_evento.trim()) { setMsg("Descreva o que fazer nesta lida."); return; }
      if (form.dar_baixa_estoque && !(form.insumo_padrao.trim() && form.insumo_dose && form.insumo_unidade)) {
        setMsg("Para dar baixa no estoque, informe o produto, a dose e a unidade."); return;
      }
    } else {
      if (form.etapas.some((e) => e.dia_inicio < 0)) { setMsg("O dia de uma etapa não pode ser negativo."); return; }
      if (form.etapas.some((e) => !e.descricao_evento.trim())) { setMsg("Descreva o que fazer em cada etapa."); return; }
      if (form.dar_baixa_estoque && form.etapas.some((e) => e.insumo_padrao && !(e.insumo_dose && e.insumo_unidade))) {
        setMsg("Para dar baixa no estoque, informe dose e unidade do insumo de cada etapa que tiver um."); return;
      }
    }
    setSalvando(true); setMsg(null);
    try {
      const dados = {
        nome: form.nome.trim(), modo: form.modo, dia_inicial: form.dia_inicial,
        frequencia_dias: form.modo === "frequencia" ? form.frequencia_dias : undefined,
        descricao_evento: form.modo === "frequencia" ? form.descricao_evento.trim() : undefined,
        insumo_padrao: form.modo === "frequencia" ? (form.insumo_padrao.trim() || undefined) : undefined,
        insumo_dose: form.modo === "frequencia" ? form.insumo_dose : undefined,
        insumo_unidade: form.modo === "frequencia" ? (form.insumo_unidade || undefined) : undefined,
        foto_obrigatoria: form.modo === "frequencia" ? form.foto_obrigatoria : false,
        dar_baixa_estoque: form.dar_baixa_estoque, vincular_financeiro: form.vincular_financeiro,
        observacao: form.observacao.trim() || undefined, ativo: form.ativo,
        etapas: form.modo === "periodo" ? form.etapas.map((e) => ({
          ...e, dia_inicio: Number(e.dia_inicio), dia_fim: e.dia_fim != null ? Number(e.dia_fim) : undefined,
          descricao_evento: e.descricao_evento.trim(), insumo_padrao: e.insumo_padrao?.trim() || undefined,
          insumo_dose: e.insumo_dose || undefined, insumo_unidade: e.insumo_unidade || undefined,
        })) : [],
      };
      if (editando === "novo") await criarLida(dados);
      else if (typeof editando === "number") await atualizarLida(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((l) => !termoBusca || normalizar(l.nome).includes(termoBusca));
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(filtrados);

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><ClipboardList size={16} /> Lida — tarefas gerais da fazenda</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Nova
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Trabalho da fazenda que não é protocolo de animal — limpar um cocho a cada tantos dias, acompanhar uma obra
        com foto diária, manutenção. Sem Tipo produtivo/reprodutivo/sanitário: fica sempre fora desses filtros da
        Central de Protocolos, mas aparece normalmente na Agenda e no Acompanhamento/Histórico.
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && (
        <FormLida
          form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
          acrescentarEtapa={acrescentarEtapa} removerEtapa={removerEtapa} atualizarEtapa={atualizarEtapa} estoque={estoque}
        />
      )}

      {itens && (
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar lida…" />
          </div>
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr><ThOrdenavel label="Nome" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} /><th>Modo</th><th>Detalhe</th><th></th></tr></thead>
              <tbody>
                {linhasOrdenadas.map((l) => (
                  <Fragment key={l.id}>
                    <tr>
                      <td style={{ fontWeight: 700 }}>{l.nome}{!l.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativa)</span>}</td>
                      <td style={{ fontSize: "0.78rem" }}>{l.modo === "frequencia" ? "Por frequência" : "Por período"}</td>
                      <td style={{ fontSize: "0.78rem" }}>
                        {l.modo === "frequencia" ? `A cada ${l.frequencia_dias} dias` : `D0 a D${l.duracao_dias ?? "?"}`}
                      </td>
                      <td style={{ textAlign: "right", display: "flex", justifyContent: "flex-end", gap: "0.4rem" }}>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(l)}>
                          <Pencil size={13} /> Editar
                        </button>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => excluir(l)}>
                          <Trash2 size={13} /> Excluir
                        </button>
                      </td>
                    </tr>
                    {editando === l.id && (
                      <tr><td colSpan={4} style={{ padding: 0 }}>
                        <FormLida
                          form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
                          acrescentarEtapa={acrescentarEtapa} removerEtapa={removerEtapa} atualizarEtapa={atualizarEtapa} estoque={estoque}
                        />
                      </td></tr>
                    )}
                  </Fragment>
                ))}
                {!itens.length && !editando && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma lida cadastrada ainda.</td></tr>}
                {!!itens.length && !filtrados.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function SeletorInsumo({ valor, dose, unidade, onChange, estoque }: {
  valor: string; dose: number | null; unidade: string;
  onChange: (patch: { insumo_padrao?: string; insumo_dose?: number | null; insumo_unidade?: string }) => void;
  estoque: EstoqueItem[];
}) {
  const [modo, setModo] = useState<"estoque" | "livre">(
    valor && estoque.some((it) => it.nome === valor) ? "estoque" : "livre",
  );
  const estoqueOrdenado = useMemo(() => [...estoque].sort((a, b) => a.nome.localeCompare(b.nome)), [estoque]);
  return (
    <div>
      <div className="flex items-center justify-between" style={{ marginBottom: "0.15rem" }}>
        <label style={labelStyle}>Insumo (opcional)</label>
        <select style={{ background: "transparent", color: "var(--text-muted)", border: "none", fontSize: "0.68rem", cursor: "pointer" }}
          value={modo} onChange={(ev) => setModo(ev.target.value as "estoque" | "livre")}>
          <option value="estoque">do estoque</option>
          <option value="livre">texto livre</option>
        </select>
      </div>
      {modo === "estoque" ? (
        <select style={inputStyle} value={valor} onChange={(ev) => {
          const item = estoque.find((it) => it.nome === ev.target.value);
          onChange({ insumo_padrao: ev.target.value, insumo_unidade: item?.unidade || unidade });
        }}>
          <option value="">Selecione…</option>
          {valor && !estoqueOrdenado.some((it) => it.nome === valor) && <option value={valor}>{valor}</option>}
          {estoqueOrdenado.map((it) => <option key={it.nome} value={it.nome}>{it.nome}{it.quantidade != null ? ` (${it.quantidade} ${it.unidade || ""})` : ""}</option>)}
        </select>
      ) : (
        <input style={inputStyle} value={valor} onChange={(ev) => onChange({ insumo_padrao: ev.target.value })} placeholder="ex.: Detergente para cochos" />
      )}
      <div className="grid grid-cols-2 gap-2" style={{ marginTop: "0.4rem" }}>
        <div><label style={labelStyle}>Dose consumida</label>
          <input type="number" inputMode="decimal" style={inputStyle} value={dose ?? ""} onChange={(ev) => onChange({ insumo_dose: ev.target.value ? Number(ev.target.value) : null })} placeholder="0" /></div>
        <div><label style={labelStyle}>Unidade</label>
          <select style={inputStyle} value={unidade} onChange={(ev) => onChange({ insumo_unidade: ev.target.value })}>
            <option value="">—</option>
            {unidade && !UNIDADES_PROTOCOLO.includes(unidade) && <option value={unidade}>{unidade}</option>}
            {UNIDADES_PROTOCOLO.map((u) => <option key={u} value={u}>{u}</option>)}
          </select></div>
      </div>
    </div>
  );
}

function FormLida({ form, setForm, onSalvar, onCancelar, salvando, msg, acrescentarEtapa, removerEtapa, atualizarEtapa, estoque }: {
  form: LidaForm; setForm: (f: LidaForm) => void;
  onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
  acrescentarEtapa: () => void; removerEtapa: (idx: number) => void; atualizarEtapa: (idx: number, patch: Partial<EtapaLida>) => void;
  estoque: EstoqueItem[];
}) {
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Nome</label>
          <input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder="ex.: Limpar cocho de água" /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativa</label></div>
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3" style={{ maxWidth: 460 }}>
        {(["frequencia", "periodo"] as const).map((m) => {
          const ativo = form.modo === m;
          return (
            <button key={m} type="button" onClick={() => setForm({ ...form, modo: m })}
              style={{ textAlign: "left", padding: "0.6rem 0.75rem", borderRadius: "var(--r-sm)", cursor: "pointer",
                border: `1px solid ${ativo ? "var(--dourado)" : "var(--border)"}`,
                background: ativo ? "var(--pill-active-bg)" : "transparent",
                color: ativo ? "var(--dourado-light)" : "var(--text)" }}>
              <span style={{ display: "block", fontWeight: 700, fontSize: "0.85rem" }}>{m === "frequencia" ? "Por frequência" : "Por período"}</span>
              <span style={{ display: "block", fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
                {m === "frequencia" ? "Repete a cada N dias, entre início e fim" : "Uma etapa por dia (D0, D1…)"}
              </span>
            </button>
          );
        })}
      </div>

      {form.modo === "frequencia" ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <div><label style={labelStyle}>A cada quantos dias</label>
              <input type="number" min={1} style={inputStyle} value={form.frequencia_dias ?? ""} onChange={(e) => setForm({ ...form, frequencia_dias: e.target.value ? Number(e.target.value) : null })} /></div>
            <div style={{ gridColumn: "span 3" }}><label style={labelStyle}>O que fazer</label>
              <input style={inputStyle} value={form.descricao_evento} onChange={(e) => setForm({ ...form, descricao_evento: e.target.value })} placeholder="ex.: Limpar cocho de água" /></div>
          </div>
          <div className="mb-3" style={{ maxWidth: 460 }}>
            <SeletorInsumo
              valor={form.insumo_padrao} dose={form.insumo_dose} unidade={form.insumo_unidade}
              onChange={(patch) => setForm({ ...form, ...patch } as LidaForm)}
              estoque={estoque}
            />
          </div>
          <label className="flex items-center gap-2 mb-2" style={{ fontSize: "0.78rem" }}>
            <input type="checkbox" checked={form.foto_obrigatoria} onChange={(e) => setForm({ ...form, foto_obrigatoria: e.target.checked })} /> Exigir foto ao confirmar
          </label>
        </>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <div><label style={labelStyle}>Dia inicial</label>
              <select style={inputStyle} value={form.dia_inicial} onChange={(e) => setForm({ ...form, dia_inicial: Number(e.target.value) })}>
                <option value={0}>D0</option><option value={1}>D1</option>
              </select></div>
          </div>
          <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.4rem" }}>Etapas</p>
          <div className="space-y-2 mb-2">
            {form.etapas.map((e, idx) => (
              <div key={idx} style={{ background: "var(--surface)", padding: "0.6rem", borderRadius: "var(--r-sm)", marginBottom: "0.4rem" }}>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
                  <div><label style={labelStyle}>Dia início</label><input type="number" min={0} style={inputStyle} value={e.dia_inicio} onChange={(ev) => atualizarEtapa(idx, { dia_inicio: Number(ev.target.value) })} /></div>
                  <div><label style={labelStyle}>Dia fim (opcional)</label><input type="number" min={0} style={inputStyle} value={e.dia_fim ?? ""} onChange={(ev) => atualizarEtapa(idx, { dia_fim: ev.target.value ? Number(ev.target.value) : null })} placeholder="repete até este dia" /></div>
                  <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>O que fazer</label>
                    <input style={inputStyle} value={e.descricao_evento} onChange={(ev) => atualizarEtapa(idx, { descricao_evento: ev.target.value })} placeholder="ex.: Enviar foto da cerca" /></div>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <label className="flex items-center gap-2" style={{ fontSize: "0.76rem" }}>
                    <input type="checkbox" checked={e.foto_obrigatoria} onChange={(ev) => atualizarEtapa(idx, { foto_obrigatoria: ev.target.checked })} /> Exigir foto
                  </label>
                  {form.etapas.length > 1 && <button type="button" className="btn-ghost" style={{ color: "var(--red)" }} onClick={() => removerEtapa(idx)}><Trash2 size={13} /></button>}
                </div>
                <div style={{ marginTop: "0.4rem", maxWidth: 460 }}>
                  <SeletorInsumo
                    valor={e.insumo_padrao || ""} dose={e.insumo_dose ?? null} unidade={e.insumo_unidade || ""}
                    onChange={(patch) => atualizarEtapa(idx, patch)}
                    estoque={estoque}
                  />
                </div>
              </div>
            ))}
          </div>
          <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem", marginBottom: "0.8rem" }} onClick={acrescentarEtapa}>
            <Plus size={14} /> Acrescentar etapa
          </button>
        </>
      )}

      <div className="mb-3"><label style={labelStyle}>Observação (opcional)</label>
        <input style={inputStyle} value={form.observacao} onChange={(e) => setForm({ ...form, observacao: e.target.value })} placeholder="Contexto geral" /></div>

      <div style={{ borderTop: "1px solid var(--border)", paddingTop: "0.6rem", marginBottom: "0.6rem" }}>
        <label className="flex items-center gap-2 mb-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.dar_baixa_estoque} onChange={(e) => setForm({ ...form, dar_baixa_estoque: e.target.checked })} />
          Dar baixa no estoque ao confirmar (usa a dose/unidade do insumo informado)
        </label>
        <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.vincular_financeiro} onChange={(e) => setForm({ ...form, vincular_financeiro: e.target.checked })} />
          Vincular ao financeiro
        </label>
        {form.vincular_financeiro && (
          <p style={{ fontSize: "0.7rem", color: "var(--amber)", marginTop: "0.2rem" }}>
            A intenção fica salva, mas a geração automática do lançamento financeiro ainda não está implementada — por enquanto, lance manualmente em Financeiro.
          </p>
        )}
      </div>

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
