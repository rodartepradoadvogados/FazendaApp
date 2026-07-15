"use client";
import { useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import { criarItemEstoque, fetchFornecedores, fetchOpcoesFinanceiro, fetchPlanoContas, fetchPrincipiosAtivos, CLASSIFICACOES_MEDICAMENTO, FINALIDADES_ESTOQUE, CATEGORIAS_ESTOQUE } from "@/lib/api";
import { SeletorContaGerencial } from "@/components/SeletorContaGerencial";
import type { ContaPlano } from "@/lib/contaGerencial";

const UNIDADES = ["ml", "kg", "L", "unidade", "dose", "metro", "saca 30kg", "saca 60kg"];

const UNIDADES_EMBALAGEM = ["Saca", "Pote", "Frasco", "Pacote", "Bag", "Fardo", "Garrafa", "Unidade"];
const MEDIDAS_EMBALAGEM = ["kg/saca", "litros/garrafa", "mililitros/frasco", "unidades/fardo", "potes/caixa", "unidades"];

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

type Fornecedor = { id: number; nome: string };

const vazio = {
  nome: "", numero_produto: "", categoria: "", finalidade: "", unidade: "", quantidade: "", estoque_minimo: "",
  valor_unitario: "", local_armazenamento: "", fornecedor_id: "",
  unidade_embalagem: "", medida_embalagem: "", quantidade_embalagem: "",
  ativo: true, observacao: "", carencia_dias: "", centro_custo_padrao: "",
  conta_gerencial_despesa_padrao: "", conta_gerencial_despesa_nome: "",
  conta_gerencial_receita_padrao: "", conta_gerencial_receita_nome: "",
  gera_receita: false,
  exibir_necessidade_compra_agenda: false, estocavel: true, data_inicio_controle: "",
  principio_ativo: "", principio_ativo_id: "", classificacao_medicamento: "",
};

type PrincipioAtivo = { id: number; nome: string; ativo?: boolean };

export default function NovoItemEstoque({ onCriado, onCancelar }: { onCriado: (item?: any) => void; onCancelar: () => void }) {
  const [form, setForm] = useState(vazio);
  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [centrosCusto, setCentrosCusto] = useState<string[]>([]);
  const [planoContas, setPlanoContas] = useState<ContaPlano[]>([]);
  const [principiosAtivos, setPrincipiosAtivos] = useState<PrincipioAtivo[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    fetchFornecedores().then(setFornecedores).catch(() => {});
    fetchOpcoesFinanceiro().then((d) => setCentrosCusto(d.centros_custo || [])).catch(() => {});
    fetchPlanoContas().then(setPlanoContas).catch(() => {});
    fetchPrincipiosAtivos().then((lista: PrincipioAtivo[]) => setPrincipiosAtivos(lista.filter((p) => p.ativo !== false))).catch(() => {});
  }, []);

  const set = (patch: Partial<typeof vazio>) => setForm((p) => ({ ...p, ...patch }));

  async function salvar() {
    if (!form.nome.trim()) { setErro("Nome é obrigatório."); return; }
    setErro(null); setSalvando(true);
    try {
      const num = (v: string) => (v.trim() === "" ? undefined : Number(v));
      const str = (v: string) => (v.trim() === "" ? undefined : v.trim());
      const criado = await criarItemEstoque({
        nome: form.nome.trim(),
        numero_produto: str(form.numero_produto),
        categoria: str(form.categoria),
        finalidade: str(form.finalidade),
        unidade: str(form.unidade),
        quantidade: form.estocavel ? num(form.quantidade) : undefined,
        estoque_minimo: form.estocavel ? num(form.estoque_minimo) : undefined,
        valor_unitario: num(form.valor_unitario),
        local_armazenamento: form.estocavel ? str(form.local_armazenamento) : undefined,
        fornecedor_id: form.fornecedor_id ? Number(form.fornecedor_id) : undefined,
        unidade_embalagem: str(form.unidade_embalagem),
        medida_embalagem: str(form.medida_embalagem),
        quantidade_embalagem: num(form.quantidade_embalagem),
        ativo: form.ativo,
        observacao: str(form.observacao),
        carencia_dias: num(form.carencia_dias),
        centro_custo_padrao: str(form.centro_custo_padrao),
        conta_gerencial_despesa_padrao: str(form.conta_gerencial_despesa_padrao),
        conta_gerencial_receita_padrao: str(form.conta_gerencial_receita_padrao),
        gera_receita: form.gera_receita,
        exibir_necessidade_compra_agenda: form.estocavel ? form.exibir_necessidade_compra_agenda : false,
        estocavel: form.estocavel,
        data_inicio_controle: form.estocavel && form.data_inicio_controle.trim() !== "" ? form.data_inicio_controle : null,
        principio_ativo: str(form.principio_ativo),
        principio_ativo_id: form.principio_ativo_id ? Number(form.principio_ativo_id) : undefined,
        classificacao_medicamento: str(form.classificacao_medicamento),
      });
      setForm(vazio);
      onCriado(criado);
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
        <div><label style={labelStyle}>Categoria</label>
          <select style={inputStyle} value={form.categoria} onChange={(e) => set({ categoria: e.target.value })}>
            <option value="">—</option>{CATEGORIAS_ESTOQUE.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div><label style={labelStyle}>Finalidade</label>
          <select style={inputStyle} value={form.finalidade} onChange={(e) => set({ finalidade: e.target.value })}>
            <option value="">—</option>{FINALIDADES_ESTOQUE.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          <span style={{ display: "block", fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
            Decide se o item aparece nos seletores de aplicação de medicamento/hormônio.
          </span>
        </div>
        {form.finalidade === "Medicamento" && (
          <div><label style={labelStyle}>Princípio ativo (medicamento)</label>
            <select
              style={inputStyle}
              value={form.principio_ativo_id}
              onChange={(e) => {
                const id = e.target.value;
                const encontrado = principiosAtivos.find((p) => String(p.id) === id);
                set({ principio_ativo_id: id, principio_ativo: encontrado?.nome || "" });
              }}
            >
              <option value="">—</option>
              {principiosAtivos.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select>
          </div>
        )}
        {form.finalidade === "Medicamento" && (
          <div><label style={labelStyle}>Classificação (medicamento)</label>
            <select style={inputStyle} value={form.classificacao_medicamento} onChange={(e) => set({ classificacao_medicamento: e.target.value })}>
              <option value="">—</option>{CLASSIFICACOES_MEDICAMENTO.map((c) => <option key={c} value={c}>{c}</option>)}
            </select></div>
        )}
        <div><label style={labelStyle}>Unidade</label>
          <select style={inputStyle} value={form.unidade} onChange={(e) => set({ unidade: e.target.value })}>
            <option value="">Selecione…</option>
            {UNIDADES.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
        </div>

        {form.estocavel && (
          <div><label style={labelStyle}>Saldo inicial</label><input type="number" style={inputStyle} value={form.quantidade} onChange={(e) => set({ quantidade: e.target.value })} /></div>
        )}
        {form.estocavel && (
          <div><label style={labelStyle}>Estoque mínimo</label><input type="number" style={inputStyle} value={form.estoque_minimo} onChange={(e) => set({ estoque_minimo: e.target.value })} /></div>
        )}
        <div><label style={labelStyle}>Valor unitário (R$)</label><input type="number" style={inputStyle} value={form.valor_unitario} onChange={(e) => set({ valor_unitario: e.target.value })} /></div>
        {form.estocavel && (
          <div><label style={labelStyle}>Local de armazenamento</label><input style={inputStyle} value={form.local_armazenamento} onChange={(e) => set({ local_armazenamento: e.target.value })} /></div>
        )}
        {form.estocavel && (
          <div>
            <label style={labelStyle}>Data de início do controle de estoque</label>
            <input type="date" style={inputStyle} value={form.data_inicio_controle} onChange={(e) => set({ data_inicio_controle: e.target.value })} />
            <span style={{ display: "block", fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
              A partir desta data o item passa a ser controlado; lançamentos anteriores não afetam o estoque.
            </span>
          </div>
        )}

        <div><label style={labelStyle}>Fornecedor principal</label>
          <select style={inputStyle} value={form.fornecedor_id} onChange={(e) => set({ fornecedor_id: e.target.value })}>
            <option value="">—</option>
            {fornecedores.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}
          </select>
        </div>
        <div><label style={labelStyle}>Unidade (embalagem)</label>
          <select style={inputStyle} value={form.unidade_embalagem} onChange={(e) => set({ unidade_embalagem: e.target.value })}>
            <option value="">—</option>
            {UNIDADES_EMBALAGEM.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
        </div>
        <div><label style={labelStyle}>Unidade de medida</label>
          <select style={inputStyle} value={form.medida_embalagem} onChange={(e) => set({ medida_embalagem: e.target.value })}>
            <option value="">—</option>
            {MEDIDAS_EMBALAGEM.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <div><label style={labelStyle}>Quantidade por embalagem</label><input type="number" style={inputStyle} value={form.quantidade_embalagem} onChange={(e) => set({ quantidade_embalagem: e.target.value })} /></div>
        <div><label style={labelStyle}>Carência (dias)</label><input type="number" style={inputStyle} value={form.carencia_dias} onChange={(e) => set({ carencia_dias: e.target.value })} placeholder="período de carência do leite/carne" /></div>

        <div><label style={labelStyle}>Centro de custo padrão</label>
          <select style={inputStyle} value={form.centro_custo_padrao} onChange={(e) => set({ centro_custo_padrao: e.target.value })}>
            <option value="">Selecione…</option>
            {centrosCusto.map((c) => <option key={c} value={c}>{c}</option>)}
            {form.centro_custo_padrao && !centrosCusto.includes(form.centro_custo_padrao) && (
              <option value={form.centro_custo_padrao}>{form.centro_custo_padrao}</option>
            )}
          </select>
        </div>
        <div><label style={labelStyle}>Conta gerencial padrão — Despesa</label>
          <SeletorContaGerencial
            contas={planoContas}
            tipo="despesa"
            codigo={form.conta_gerencial_despesa_padrao}
            nome={form.conta_gerencial_despesa_nome}
            onSelect={(codigo, nome) => set({ conta_gerencial_despesa_padrao: codigo, conta_gerencial_despesa_nome: nome })}
            placeholder="Escolha a conta de despesa…"
          />
        </div>
        <div><label style={labelStyle}>Conta gerencial padrão — Receita</label>
          <SeletorContaGerencial
            contas={planoContas}
            tipo="receita"
            codigo={form.conta_gerencial_receita_padrao}
            nome={form.conta_gerencial_receita_nome}
            onSelect={(codigo, nome) => set({ conta_gerencial_receita_padrao: codigo, conta_gerencial_receita_nome: nome })}
            placeholder="Escolha a conta de receita…"
          />
        </div>
        <div className="flex items-end gap-3">
          <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
            <input type="checkbox" checked={form.ativo} onChange={(e) => set({ ativo: e.target.checked })} /> Ativo
          </label>
        </div>
        <div className="flex items-end gap-3">
          <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }} title="Produto de venda (leite, animal, esterco…) — usado nos relatórios de receita.">
            <input type="checkbox" checked={form.gera_receita} onChange={(e) => set({ gera_receita: e.target.checked })} /> Gera receita
          </label>
        </div>
        <div className="flex items-end gap-3">
          <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
            <input type="checkbox" checked={form.estocavel} onChange={(e) => set({ estocavel: e.target.checked })} /> Estocável
          </label>
        </div>

        {form.estocavel && (
          <div style={{ gridColumn: "1 / -1" }}>
            <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
              <input type="checkbox" checked={form.exibir_necessidade_compra_agenda} onChange={(e) => set({ exibir_necessidade_compra_agenda: e.target.checked })} />
              Exibir necessidade de compra na Agenda quando o estoque ficar abaixo do mínimo
            </label>
          </div>
        )}
        {!form.estocavel && (
          <div style={{ gridColumn: "1 / -1", fontSize: "0.72rem", color: "var(--text-muted)" }}>
            Item não estocável: só serve para lançamento financeiro (produto de nota). Não participa de baixa automática
            por aplicação/consumo, nem pode ser doado ou recebido de cortesia.
          </div>
        )}
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
