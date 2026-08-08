"use client";
// Manual da Fazenda (Configurações > Parâmetros) — seção separada dos demais
// parâmetros: envio semanal por e-mail, responsável pelo manejo reprodutivo
// (+ placeholder de contrato, pronto para o Supabase Storage depois) e o
// cadastro de sugestões customizadas mostradas em Preditivo e sugestões.
import { useEffect, useState } from "react";
import { BookOpen, Mail, FileText, Paperclip, Sparkles, Plus, Pencil, X, Check, AlertTriangle } from "lucide-react";
import {
  fetchParametrosManualFazenda, atualizarParametrosManualFazenda, anexarContratoManejo,
  fetchSugestoesManualFazenda, criarSugestaoManualFazenda, atualizarSugestaoManualFazenda, excluirSugestaoManualFazenda,
  type ParametroManualFazenda, type SugestaoManualFazenda,
} from "@/lib/api";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.82rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

const CATEGORIAS_SUGESTAO = [
  { value: "geral", label: "Geral" },
  { value: "reprodutivo", label: "Reprodutivo" },
  { value: "producao", label: "Produção" },
  { value: "sanidade", label: "Sanidade" },
  { value: "financeiro", label: "Financeiro" },
];
const labelCategoria = (v: string) => CATEGORIAS_SUGESTAO.find((c) => c.value === v)?.label ?? v;

export default function ManualFazendaParametros({ podeEditar }: { podeEditar: boolean }) {
  const [p, setP] = useState<ParametroManualFazenda | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [salvoOk, setSalvoOk] = useState(false);
  const [enviandoAnexo, setEnviandoAnexo] = useState(false);

  const carregar = () => fetchParametrosManualFazenda().then(setP).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const salvar = async (patch: Partial<ParametroManualFazenda>) => {
    if (!p) return;
    const novo = { ...p, ...patch };
    setP(novo);
    setSalvando(true);
    try {
      await atualizarParametrosManualFazenda({
        email_semanal_ativo: novo.email_semanal_ativo,
        responsavel_manejo_nome: novo.responsavel_manejo_nome,
        responsavel_manejo_empresa: novo.responsavel_manejo_empresa,
        tem_contrato_manejo: novo.tem_contrato_manejo,
      });
      setSalvoOk(true);
      setTimeout(() => setSalvoOk(false), 2000);
    } catch (e: any) {
      setError(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const anexar = async (arquivo: File) => {
    setEnviandoAnexo(true);
    try {
      const atualizado = await anexarContratoManejo(arquivo);
      setP(atualizado);
    } catch (e: any) {
      setError(e.message || "Erro ao anexar contrato");
    } finally {
      setEnviandoAnexo(false);
    }
  };

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center gap-2"><BookOpen size={16} /> Manual da Fazenda</div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "1rem" }}>
        Configurações do Manual da Fazenda (rotina automática, resultado, insights e sugestões) — separado dos demais parâmetros.
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>{error}</span></div>}
      {!p && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {p && (
        <>
          <div style={{ background: "var(--surface-2)", borderRadius: "var(--r-sm)", padding: "0.9rem 1rem", marginBottom: "1rem" }}>
            <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", fontWeight: 600, cursor: podeEditar ? "pointer" : "default" }}>
              <input type="checkbox" checked={p.email_semanal_ativo} disabled={!podeEditar}
                onChange={(e) => salvar({ email_semanal_ativo: e.target.checked })} />
              <Mail size={15} /> Enviar por e-mail toda semana
            </label>
            <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.35rem", marginLeft: "1.4rem" }}>
              Toda segunda-feira, às 7h, o Manual da Fazenda (em PDF) é enviado para o e-mail cadastrado de cada administrador da fazenda.
              {p.ultimo_envio_semanal_em && ` Último envio: ${new Date(p.ultimo_envio_semanal_em).toLocaleString("pt-BR")}.`}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
            <div>
              <label style={lbl}>Responsável pelo manejo reprodutivo</label>
              <input style={inputStyle} disabled={!podeEditar} defaultValue={p.responsavel_manejo_nome ?? ""}
                onBlur={(e) => e.target.value !== (p.responsavel_manejo_nome ?? "") && salvar({ responsavel_manejo_nome: e.target.value || null })}
                placeholder="Ex.: Dr. Carlos Mendes" />
            </div>
            <div>
              <label style={lbl}>Empresa responsável (opcional)</label>
              <input style={inputStyle} disabled={!podeEditar} defaultValue={p.responsavel_manejo_empresa ?? ""}
                onBlur={(e) => e.target.value !== (p.responsavel_manejo_empresa ?? "") && salvar({ responsavel_manejo_empresa: e.target.value || null })}
                placeholder="Ex.: VetRepro Consultoria" />
            </div>
          </div>

          <div style={{ borderTop: "1px solid var(--border)", paddingTop: "0.8rem" }}>
            <label className="flex items-center gap-2" style={{ fontSize: "0.82rem", cursor: podeEditar ? "pointer" : "default" }}>
              <input type="checkbox" checked={p.tem_contrato_manejo} disabled={!podeEditar}
                onChange={(e) => salvar({ tem_contrato_manejo: e.target.checked })} />
              <FileText size={15} /> Há contrato de prestação de serviço de manejo reprodutivo
            </label>
            {p.tem_contrato_manejo && (
              <div className="flex items-center gap-3 mt-2" style={{ marginLeft: "1.4rem" }}>
                <label className="btn-ghost" style={{ fontSize: "0.78rem", cursor: podeEditar ? "pointer" : "not-allowed", opacity: podeEditar ? 1 : 0.5, display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                  <Paperclip size={13} /> {enviandoAnexo ? "Enviando…" : "Anexar contrato"}
                  <input type="file" style={{ display: "none" }} disabled={!podeEditar || enviandoAnexo}
                    onChange={(e) => e.target.files?.[0] && anexar(e.target.files[0])} />
                </label>
                {p.contrato_manejo_arquivo_nome && (
                  <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{p.contrato_manejo_arquivo_nome}</span>
                )}
              </div>
            )}
            <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.4rem", marginLeft: "1.4rem" }}>
              O arquivo fica só com o nome salvo por enquanto — o upload/armazenamento real do contrato entra depois (Supabase).
            </p>
          </div>

          {salvoOk && <p style={{ fontSize: "0.7rem", color: "var(--green-light)", marginTop: "0.7rem" }}>Salvo.</p>}
        </>
      )}

      <div className="mt-4" style={{ borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
        <CadastroSugestoes podeEditar={podeEditar} />
      </div>
    </div>
  );
}

const FORM_SUGESTAO_VAZIO = { texto: "", categoria: "geral", ativo: true, ordem: 0 };

function CadastroSugestoes({ podeEditar }: { podeEditar: boolean }) {
  const [sugestoes, setSugestoes] = useState<SugestaoManualFazenda[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState(FORM_SUGESTAO_VAZIO);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => fetchSugestoesManualFazenda().then(setSugestoes).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const abrirNovo = () => { setForm({ ...FORM_SUGESTAO_VAZIO, ordem: sugestoes?.length ?? 0 }); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (s: SugestaoManualFazenda) => { setForm({ texto: s.texto, categoria: s.categoria, ativo: s.ativo, ordem: s.ordem }); setEditando(s.id); setMsg(null); };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.texto.trim()) { setMsg("Escreva o texto da sugestão."); return; }
    setSalvando(true); setMsg(null);
    try {
      if (editando === "novo") await criarSugestaoManualFazenda(form);
      else await atualizarSugestaoManualFazenda(editando as number, form);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const excluir = async (s: SugestaoManualFazenda) => {
    if (!confirm(`Excluir a sugestão "${s.texto}"?`)) return;
    try { await excluirSugestaoManualFazenda(s.id); await carregar(); } catch (e: any) { setError(e.message); }
  };

  const FormSugestao = (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.9rem", marginBottom: "0.8rem" }}>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-2">
        <div style={{ gridColumn: "span 2" }}>
          <label style={lbl}>Texto da sugestão</label>
          <input style={inputStyle} value={form.texto} onChange={(e) => setForm({ ...form, texto: e.target.value })}
            placeholder="Ex.: Revisar dieta do lote de pré-parto a cada troca de estação" />
        </div>
        <div>
          <label style={lbl}>Categoria</label>
          <select style={inputStyle} value={form.categoria} onChange={(e) => setForm({ ...form, categoria: e.target.value })}>
            {CATEGORIAS_SUGESTAO.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </div>
      </div>
      <label className="flex items-center gap-2 mb-2" style={{ fontSize: "0.78rem" }}>
        <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativa
      </label>
      {msg && <p style={{ color: "var(--red)", fontSize: "0.78rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="flex items-center gap-2" style={{ fontSize: "0.85rem", fontWeight: 600 }}><Sparkles size={15} /> Sugestões customizadas</span>
        {podeEditar && (
          <button className="btn-primary" style={{ fontSize: "0.76rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={abrirNovo}>
            <Plus size={13} /> Nova sugestão
          </button>
        )}
      </div>
      <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginBottom: "0.7rem" }}>
        Aparecem em Preditivo e sugestões do Manual da Fazenda, junto com as sugestões automáticas calculadas pelo sistema.
      </p>

      {error && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{error}</p>}
      {!sugestoes && !error && <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Carregando…</p>}

      {podeEditar && editando === "novo" && FormSugestao}

      {sugestoes && (
        <div className="space-y-2">
          {sugestoes.map((s) => (
            <div key={s.id}>
              <div className="flex items-center justify-between gap-2" style={{ background: "var(--surface-2)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.75rem" }}>
                <div>
                  <span style={{ fontSize: "0.82rem" }}>{s.texto}</span>
                  <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginLeft: "0.5rem" }}>
                    {labelCategoria(s.categoria)}{!s.ativo && " · inativa"}
                  </span>
                </div>
                {podeEditar && (
                  <span className="flex items-center gap-2" style={{ flexShrink: 0 }}>
                    <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => abrirEdicao(s)}><Pencil size={12} /></button>
                    <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={() => excluir(s)}><X size={12} /></button>
                  </span>
                )}
              </div>
              {editando === s.id && podeEditar && FormSugestao}
            </div>
          ))}
          {!sugestoes.length && <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Nenhuma sugestão customizada ainda.</p>}
        </div>
      )}
    </div>
  );
}
