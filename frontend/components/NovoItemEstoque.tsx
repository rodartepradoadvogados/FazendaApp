"use client";
import { useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import { criarItemEstoque, fetchFornecedores, fetchOpcoesFinanceiro } from "@/lib/api";

const UNIDADES = ["ml", "kg", "L", "unidade", "dose", "saca 30kg", "saca 60kg"];

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

type Fornecedor = { id: number; nome: string };
type ContaGerencial = { codigo: string; nome: string };

const vazio = {
  nome: "", numero_produto: "", categoria: "", unidade: "", quantidade: "", estoque_minimo: "",
  valor_unitario: "", local_armazenamento: "", fornecedor_id: "", ensacado: false, kg_por_saco: "",
  ativo: true, observacao: "", carencia_dias: "", centro_custo_padrao: "",
  conta_gerencial_despesa_padrao: "", conta_gerencial_receita_padrao: "",
  exibir_necessidade_compra_agenda: false,
};

export default function NovoItemEstoque({ onCriado, onCancelar }: { onCriado: () => void; onCancelar: () => void }) {
  const [form, setForm] = useState(vazio);
  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [contas, setContas] = useState<ContaGerencial[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    fetchFornecedores().then(setFornecedores).catch(() => {});
    fetchOpcoesFinanceiro().then((d) => setContas(d.contas_gerenciais || [])).catch(() => {});
  }, []);

  const set = (patch: Partial<typeof vazio>) => setForm((p) => ({ ...p, ...patch }));

  async function salvar() {
    if (!form.nome.trim()) { setErro("Nome é obrigatório."); return; }
    setErro(null); setSalvando(true);
    try {
      const num = (v: string) => (v.trim() === "" ? undefined : Number(v));
      const str = (v: string) => (v.trim() === "" ? undefined : v.trim());
      await criarItemEstoque({
        nome: form.nome.trim(),
        numero_produto: str(form.numero_produto),
        categoria: str(form.categoria),
        unidade: str(form.unidade),
        quantidade: num(form.quantidade),
        estoque_minimo: num(form.estoque_minimo),
        valor_unitario: num(form.valor_unitario),
        local_armazenamento: str(form.local_armazenamento),
        fornecedor_id: form.fornecedor_id ? Number(form.fornecedor_id) : undefined,
        ensacado: form.ensacado,
        kg_por_saco: form.ensacado ? num(form.kg_por_saco) : undefined,
        ativo: form.ativo,
        observacao: str(form.observacao),
        carencia_dias: num(form.carencia_dias),
        centro_custo_padrao: str(form.centro_custo_padrao),
        conta_gerencial_despesa_padrao: str(form.conta_gerencial_despesa_padrao),
        conta_gerencial_receita_padrao: str(form.conta_gerencial_receita_padrao),
        exibir_necessidade_compra_agenda: form.exibir_necessidade_compra_agenda,
      });
      setForm(vazio);
      onCriado();
    } catch (e: any) {
      setErro(e.message || "Erro ao cadastrar item");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => set({ nome: e.target.value })} /></div>
        <div><label style={labelStyle}>Número</label><input style={inputStyle} value={form.numero_produto} onChange={(e) => set({ numero_produto: e.target.value })} /></div>
        <div><label style={labelStyle}>Categoria</label><input style={inputStyle} value={form.categoria} onChange={(e) => set({ categoria: e.target.value })} placeholder="ex.: Alimento, Medicamento…" /></div>
        <div><label style={labelStyle}>Unidade</label>
          <select style={inputStyle} value={form.unidade} onChange={(e) => set({ unidade: e.target.value })}>
            <option value="">Selecione…</option>
            {UNIDADES.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
        </div>

        <div><label style={labelStyle}>Saldo inicial</label><input type="number" style={inputStyle} value={form.quantidade} onChange={(e) => set({ quantidade: e.target.value })} /></div>
        <div><label style={labelStyle}>Estoque mínimo</label><input type="number" style={inputStyle} value={form.estoque_minimo} onChange={(e) => set({ estoque_minimo: e.target.value })} /></div>
        <div><label style={labelStyle}>Valor unitário (R$)</label><input type="number" style={inputStyle} value={form.valor_unitario} onChange={(e) => set({ valor_unitario: e.target.value })} /></div>
        <div><label style={labelStyle}>Local de armazenamento</label><input style={inputStyle} value={form.local_armazenamento} onChange={(e) => set({ local_armazenamento: e.target.value })} /></div>

        <div><label style={labelStyle}>Fabricante / fornecedor</label>
          <select style={inputStyle} value={form.fornecedor_id} onChange={(e) => set({ fornecedor_id: e.target.value })}>
            <option value="">—</option>
            {fornecedores.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}
          </select>
        </div>
        <div className="flex items-end gap-3">
          <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
            <input type="checkbox" checked={form.ensacado} onChange={(e) => set({ ensacado: e.target.checked })} /> Ensacado
          </label>
        </div>
        <div><label style={labelStyle}>Kg por saco</label><input type="number" style={inputStyle} value={form.kg_por_saco} onChange={(e) => set({ kg_por_saco: e.target.value })} disabled={!form.ensacado} /></div>
        <div><label style={labelStyle}>Carência (dias)</label><input type="number" style={inputStyle} value={form.carencia_dias} onChange={(e) => set({ carencia_dias: e.target.value })} placeholder="período de carência do leite/carne" /></div>

        <div><label style={labelStyle}>Centro de custo padrão</label><input style={inputStyle} value={form.centro_custo_padrao} onChange={(e) => set({ centro_custo_padrao: e.target.value })} /></div>
        <div><label style={labelStyle}>Conta gerencial padrão — Despesa</label>
          <select style={inputStyle} value={form.conta_gerencial_despesa_padrao} onChange={(e) => set({ conta_gerencial_despesa_padrao: e.target.value })}>
            <option value="">—</option>
            {contas.filter((c) => c.codigo.startsWith("3")).map((c) => <option key={c.codigo} value={c.codigo}>{c.codigo} — {c.nome}</option>)}
          </select>
        </div>
        <div><label style={labelStyle}>Conta gerencial padrão — Receita</label>
          <select style={inputStyle} value={form.conta_gerencial_receita_padrao} onChange={(e) => set({ conta_gerencial_receita_padrao: e.target.value })}>
            <option value="">—</option>
            {contas.filter((c) => c.codigo.startsWith("2")).map((c) => <option key={c.codigo} value={c.codigo}>{c.codigo} — {c.nome}</option>)}
          </select>
        </div>
        <div className="flex items-end gap-3">
          <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
            <input type="checkbox" checked={form.ativo} onChange={(e) => set({ ativo: e.target.checked })} /> Ativo
          </label>
        </div>

        <div style={{ gridColumn: "1 / -1" }}>
          <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
            <input type="checkbox" checked={form.exibir_necessidade_compra_agenda} onChange={(e) => set({ exibir_necessidade_compra_agenda: e.target.checked })} />
            Exibir necessidade de compra na Agenda quando o estoque ficar abaixo do mínimo
          </label>
        </div>
        <div style={{ gridColumn: "1 / -1" }}><label style={labelStyle}>Observação</label>
          <textarea style={{ ...inputStyle, minHeight: "2.4rem" }} value={form.observacao} onChange={(e) => set({ observacao: e.target.value })} /></div>
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{erro}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onCancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );
}
