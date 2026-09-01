"use client";
import { useEffect, useState } from "react";
import { Check, Plus, X } from "lucide-react";
import {
  criarItemEstoque, atualizarItemEstoque, fetchFornecedores, fetchOpcoesFinanceiro, fetchPlanoContas, fetchPrincipiosAtivos,
  criarPrincipioAtivo,
  fetchCategoriasEstoqueCadastro, fetchFinalidadesEstoqueCadastro, fetchUnidadesEstoqueCadastro,
  fetchUnidadesEmbalagemEstoqueCadastro, fetchUnidadesMedidaEmbalagemEstoqueCadastro, fetchLocaisArmazenamento,
  fetchLaboratoriosCadastro, fetchCategoriasMedicamentoCadastro, fetchClassificacoesMedicamentoCadastro,
  fetchLotesEstoque, abrirLoteEstoque,
  type ItemCadastroSimples, type LoteEstoque,
} from "@/lib/api";
import { SeletorContaGerencial } from "@/components/SeletorContaGerencial";
import { CampoMoeda } from "@/components/CampoMoeda";
import SeletorMultiploComBusca from "@/components/SeletorMultiploComBusca";
import type { ContaPlano } from "@/lib/contaGerencial";
import { pedirCadastroDeAlimento, pedirReaberturaDeAlimento, type PrefillNovoEstoque } from "@/lib/alimentoEstoqueBridge";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

type Fornecedor = { id: number; nome: string };

const vazio = {
  nome: "", numero_produto: "", categoria: "", finalidade: "", unidade: "", quantidade: "", estoque_minimo: "",
  valor_unitario: "", local_armazenamento: "", fornecedor_id: "",
  unidade_embalagem: "", medida_embalagem: "", quantidade_embalagem: "",
  ativo: true, observacao: "", carencia_dias: "", carencia_leite_dias: "", carencia_carne_dias: "",
  proibido_lactacao: false, centro_custo_padrao: "",
  conta_gerencial_despesa_padrao: "", conta_gerencial_despesa_nome: "",
  conta_gerencial_receita_padrao: "", conta_gerencial_receita_nome: "",
  gera_receita: false, gera_patrimonio: false,
  exibir_necessidade_compra_agenda: false, estocavel: true, data_inicio_controle: "",
  principio_ativo: "", principio_ativo_id: "",
  laboratorio: "", categoriaMedicamentoIds: [] as number[], classificacaoMedicamentoIds: [] as number[],
  tipo_semen: "",
};

type PrincipioAtivo = { id: number; nome: string; ativo?: boolean };

// Lotes/frascos de compra (Fase G, 01/09/2026) — pedido do usuário:
// "registrar/comprar um medicamento escolhendo um tamanho de frasco/
// embalagem específico com sua própria dosagem, rastrear múltiplos lotes de
// tamanhos diferentes do mesmo medicamento em estoque". Só aparece editando
// um item já existente (um lote pertence a um item que já tem id) e só faz
// sentido pra item estocável.
function PainelLotesEstoque({ estoqueId }: { estoqueId: number }) {
  const [lotes, setLotes] = useState<LoteEstoque[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [abrindo, setAbrindo] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [novo, setNovo] = useState({ quantidade: "", data_compra: new Date().toISOString().slice(0, 10), valor_unitario: "", numero_lote: "" });

  const carregar = () => fetchLotesEstoque(estoqueId).then(setLotes).catch((e: any) => setErro(e.message));
  useEffect(() => { carregar(); }, [estoqueId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function salvarLote() {
    const quantidade = Number(novo.quantidade);
    if (!quantidade || quantidade <= 0) { setErro("Informe a quantidade comprada."); return; }
    setSalvando(true); setErro(null);
    try {
      await abrirLoteEstoque(estoqueId, {
        quantidade, data_compra: novo.data_compra,
        valor_unitario: novo.valor_unitario ? Number(novo.valor_unitario) : undefined,
        numero_lote: novo.numero_lote || undefined,
      });
      setNovo({ quantidade: "", data_compra: new Date().toISOString().slice(0, 10), valor_unitario: "", numero_lote: "" });
      setAbrindo(false);
      carregar();
    } catch (e: any) {
      setErro(e.message || "Erro ao abrir lote");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div style={{ gridColumn: "1 / -1", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.75rem", marginTop: "0.3rem" }}>
      <div className="flex items-center justify-between" style={{ marginBottom: "0.5rem" }}>
        <label style={{ ...labelStyle, fontWeight: 700 }}>
          Lotes de compra (frascos) — a baixa consome o mais antigo primeiro (FIFO), a não ser que se escolha um lote específico na aplicação
        </label>
        {!abrindo && (
          <button type="button" className="btn-ghost" style={{ fontSize: "0.7rem", display: "flex", alignItems: "center", gap: "0.25rem" }} onClick={() => setAbrindo(true)}>
            <Plus size={12} /> Registrar compra
          </button>
        )}
      </div>

      {abrindo && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2" style={{ marginBottom: "0.6rem" }}>
          <div><label style={labelStyle}>Quantidade comprada</label>
            <input type="number" style={inputStyle} value={novo.quantidade} onChange={(e) => setNovo((n) => ({ ...n, quantidade: e.target.value }))} /></div>
          <div><label style={labelStyle}>Data da compra</label>
            <input type="date" style={inputStyle} value={novo.data_compra} onChange={(e) => setNovo((n) => ({ ...n, data_compra: e.target.value }))} /></div>
          <div><label style={labelStyle}>Valor unitário (R$)</label>
            <input type="number" style={inputStyle} value={novo.valor_unitario} onChange={(e) => setNovo((n) => ({ ...n, valor_unitario: e.target.value }))} /></div>
          <div><label style={labelStyle}>Nº do lote (opcional)</label>
            <input style={inputStyle} value={novo.numero_lote} onChange={(e) => setNovo((n) => ({ ...n, numero_lote: e.target.value }))} /></div>
          <div style={{ gridColumn: "1 / -1", display: "flex", gap: "0.4rem" }}>
            <button type="button" className="btn-primary" style={{ fontSize: "0.72rem" }} disabled={salvando} onClick={salvarLote}>
              <Check size={12} /> {salvando ? "Salvando…" : "Salvar lote"}
            </button>
            <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setAbrindo(false)}><X size={12} /></button>
          </div>
        </div>
      )}

      {erro && <p style={{ color: "var(--red)", fontSize: "0.72rem", marginBottom: "0.4rem" }}>{erro}</p>}
      {!lotes ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Carregando…</p>
      ) : lotes.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Nenhum lote registrado ainda — o saldo do item continua sendo controlado de forma agregada.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
          {lotes.map((l) => (
            <div key={l.id} style={{
              display: "flex", alignItems: "center", gap: "0.6rem", fontSize: "0.76rem",
              padding: "0.35rem 0.55rem", borderRadius: 6, background: "var(--surface)",
              opacity: l.quantidade_restante > 0 ? 1 : 0.55,
            }}>
              <strong>{l.numero_lote ? `Lote ${l.numero_lote}` : `Compra de ${l.data_compra}`}</strong>
              <span style={{ color: "var(--text-muted)" }}>comprado em {l.data_compra}</span>
              <span style={{ marginLeft: "auto" }}>
                {l.quantidade_restante} / {l.quantidade_comprada} restante
                {l.quantidade_restante <= 0 && " — esgotado"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Item já cadastrado, para editar em vez de criar — mesmo formato do
 * model_dump() de Estoque (GET /estoque/). */
export type ItemEstoqueEditando = { id: number } & Record<string, any>;

export default function NovoItemEstoque({ onCriado, onCancelar, prefill, editando }: { onCriado: (item?: any) => void; onCancelar: () => void; prefill?: PrefillNovoEstoque | null; editando?: ItemEstoqueEditando | null }) {
  const [form, setForm] = useState(vazio);
  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [centrosCusto, setCentrosCusto] = useState<string[]>([]);
  const [planoContas, setPlanoContas] = useState<ContaPlano[]>([]);
  const [principiosAtivos, setPrincipiosAtivos] = useState<PrincipioAtivo[]>([]);
  const [novoPrincipioAberto, setNovoPrincipioAberto] = useState(false);
  const [novoPrincipioNome, setNovoPrincipioNome] = useState("");
  const [salvandoPrincipio, setSalvandoPrincipio] = useState(false);
  const [erroPrincipio, setErroPrincipio] = useState<string | null>(null);
  const [categorias, setCategorias] = useState<ItemCadastroSimples[]>([]);
  const [finalidades, setFinalidades] = useState<ItemCadastroSimples[]>([]);
  const [unidades, setUnidades] = useState<ItemCadastroSimples[]>([]);
  const [unidadesEmbalagem, setUnidadesEmbalagem] = useState<ItemCadastroSimples[]>([]);
  const [medidasEmbalagem, setMedidasEmbalagem] = useState<ItemCadastroSimples[]>([]);
  const [locaisArmazenamento, setLocaisArmazenamento] = useState<ItemCadastroSimples[]>([]);
  const [laboratorios, setLaboratorios] = useState<ItemCadastroSimples[]>([]);
  const [categoriasMedicamento, setCategoriasMedicamento] = useState<ItemCadastroSimples[]>([]);
  const [classificacoesMedicamento, setClassificacoesMedicamento] = useState<ItemCadastroSimples[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    fetchFornecedores().then(setFornecedores).catch(() => {});
    fetchOpcoesFinanceiro().then((d) => setCentrosCusto(d.centros_custo || [])).catch(() => {});
    fetchPlanoContas().then(setPlanoContas).catch(() => {});
    fetchPrincipiosAtivos().then((lista: PrincipioAtivo[]) => setPrincipiosAtivos(lista.filter((p) => p.ativo !== false))).catch(() => {});
    // Cadastros de apoio (Configurações > Cadastro > Estoque) — substituem as
    // antigas listas fixas em código (CATEGORIAS_ESTOQUE, FINALIDADES_ESTOQUE,
    // UNIDADES, UNIDADES_EMBALAGEM, MEDIDAS_EMBALAGEM) e o texto livre de
    // local de armazenamento.
    fetchCategoriasEstoqueCadastro().then((l) => setCategorias(l.filter((i) => i.ativo))).catch(() => {});
    fetchFinalidadesEstoqueCadastro().then((l) => setFinalidades(l.filter((i) => i.ativo))).catch(() => {});
    fetchUnidadesEstoqueCadastro().then((l) => setUnidades(l.filter((i) => i.ativo))).catch(() => {});
    fetchUnidadesEmbalagemEstoqueCadastro().then((l) => setUnidadesEmbalagem(l.filter((i) => i.ativo))).catch(() => {});
    fetchUnidadesMedidaEmbalagemEstoqueCadastro().then((l) => setMedidasEmbalagem(l.filter((i) => i.ativo))).catch(() => {});
    fetchLocaisArmazenamento().then((l) => setLocaisArmazenamento(l.filter((i) => i.ativo))).catch(() => {});
    // Catálogos globais do Painel CowData (ver rules/visibilidade.py) —
    // laboratório e categoria/classificação (medicamento).
    fetchLaboratoriosCadastro().then((l) => setLaboratorios(l.filter((i) => i.ativo))).catch(() => {});
    fetchCategoriasMedicamentoCadastro().then((l) => setCategoriasMedicamento(l.filter((i) => i.ativo))).catch(() => {});
    fetchClassificacoesMedicamentoCadastro().then((l) => setClassificacoesMedicamento(l.filter((i) => i.ativo))).catch(() => {});
  }, []);

  const set = (patch: Partial<typeof vazio>) => setForm((p) => ({ ...p, ...patch }));

  useEffect(() => {
    if (prefill) set({ nome: prefill.nome, finalidade: prefill.finalidade || "Ração/Alimento" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill]);

  // Pré-preenche todos os campos ao editar um item já cadastrado — os nomes
  // das contas gerenciais são resolvidos abaixo assim que o plano de contas carregar.
  useEffect(() => {
    if (!editando) return;
    const s = (v: any) => (v == null ? "" : String(v));
    set({
      nome: s(editando.nome), numero_produto: s(editando.numero_produto), categoria: s(editando.categoria),
      finalidade: s(editando.finalidade), unidade: s(editando.unidade), quantidade: s(editando.quantidade),
      estoque_minimo: s(editando.estoque_minimo), valor_unitario: s(editando.valor_unitario),
      local_armazenamento: s(editando.local_armazenamento), fornecedor_id: s(editando.fornecedor_id),
      unidade_embalagem: s(editando.unidade_embalagem), medida_embalagem: s(editando.medida_embalagem),
      quantidade_embalagem: s(editando.quantidade_embalagem), ativo: editando.ativo !== false,
      observacao: s(editando.observacao), carencia_dias: s(editando.carencia_dias),
      carencia_leite_dias: s(editando.carencia_leite_dias), carencia_carne_dias: s(editando.carencia_carne_dias),
      proibido_lactacao: editando.proibido_lactacao === true,
      centro_custo_padrao: s(editando.centro_custo_padrao),
      conta_gerencial_despesa_padrao: s(editando.conta_gerencial_despesa_padrao),
      conta_gerencial_receita_padrao: s(editando.conta_gerencial_receita_padrao),
      gera_receita: editando.gera_receita === true,
      gera_patrimonio: editando.gera_patrimonio === true,
      exibir_necessidade_compra_agenda: editando.exibir_necessidade_compra_agenda === true,
      estocavel: editando.estocavel !== false, data_inicio_controle: s(editando.data_inicio_controle),
      principio_ativo: s(editando.principio_ativo), principio_ativo_id: s(editando.principio_ativo_id),
      laboratorio: s(editando.laboratorio),
      categoriaMedicamentoIds: Array.isArray(editando.categoria_medicamento_ids) ? editando.categoria_medicamento_ids : [],
      classificacaoMedicamentoIds: Array.isArray(editando.classificacao_medicamento_ids) ? editando.classificacao_medicamento_ids : [],
      tipo_semen: s(editando.tipo_semen) || "convencional",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editando]);

  // Resolve o nome de exibição das contas gerenciais já salvas assim que o
  // plano de contas carrega (o cadastro só guarda o código).
  useEffect(() => {
    if (!editando || !planoContas.length) return;
    const acharNome = (codigo: string) => planoContas.find((c) => c.codigo === codigo)?.nome || "";
    if (form.conta_gerencial_despesa_padrao && !form.conta_gerencial_despesa_nome) {
      set({ conta_gerencial_despesa_nome: acharNome(form.conta_gerencial_despesa_padrao) });
    }
    if (form.conta_gerencial_receita_padrao && !form.conta_gerencial_receita_nome) {
      set({ conta_gerencial_receita_nome: acharNome(form.conta_gerencial_receita_padrao) });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editando, planoContas]);

  // Cadastra um princípio ativo novo sem sair do formulário do item — o
  // backend já suportava (POST /cadastro/principios-ativos), só faltava
  // esta UI (antes só dava para escolher entre os já existentes).
  async function criarNovoPrincipio() {
    if (!novoPrincipioNome.trim()) { setErroPrincipio("Nome é obrigatório."); return; }
    setSalvandoPrincipio(true); setErroPrincipio(null);
    try {
      const criado = await criarPrincipioAtivo({ nome: novoPrincipioNome.trim() });
      const lista = await fetchPrincipiosAtivos();
      setPrincipiosAtivos(lista.filter((p: PrincipioAtivo) => p.ativo !== false));
      set({ principio_ativo_id: String(criado.id), principio_ativo: criado.nome });
      setNovoPrincipioAberto(false);
      setNovoPrincipioNome("");
    } catch (e: any) {
      setErroPrincipio(e.message || "Erro ao criar princípio ativo");
    } finally {
      setSalvandoPrincipio(false);
    }
  }

  async function salvar() {
    if (!form.nome.trim()) { setErro("Nome é obrigatório."); return; }
    setErro(null); setSalvando(true);
    try {
      const num = (v: string) => (v.trim() === "" ? undefined : Number(v));
      const str = (v: string) => (v.trim() === "" ? undefined : v.trim());
      const payload = {
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
        carencia_leite_dias: num(form.carencia_leite_dias),
        carencia_carne_dias: num(form.carencia_carne_dias),
        proibido_lactacao: form.finalidade === "Medicamento" ? form.proibido_lactacao : undefined,
        centro_custo_padrao: str(form.centro_custo_padrao),
        conta_gerencial_despesa_padrao: str(form.conta_gerencial_despesa_padrao),
        conta_gerencial_receita_padrao: str(form.conta_gerencial_receita_padrao),
        gera_receita: form.gera_receita,
        gera_patrimonio: form.gera_patrimonio,
        exibir_necessidade_compra_agenda: form.estocavel ? form.exibir_necessidade_compra_agenda : false,
        estocavel: form.estocavel,
        data_inicio_controle: form.estocavel && form.data_inicio_controle.trim() !== "" ? form.data_inicio_controle : null,
        principio_ativo: str(form.principio_ativo),
        principio_ativo_id: form.principio_ativo_id ? Number(form.principio_ativo_id) : undefined,
        laboratorio: str(form.laboratorio),
        categoria_medicamento_ids: form.finalidade === "Medicamento" ? form.categoriaMedicamentoIds : [],
        classificacao_medicamento_ids: form.finalidade === "Medicamento" ? form.classificacaoMedicamentoIds : [],
        tipo_semen: form.categoria === "Sêmen e genética" ? str(form.tipo_semen) : undefined,
        alimento_id: prefill?.alimentoId,
      };
      if (editando) {
        const atualizado = await atualizarItemEstoque(editando.id, payload);
        onCriado(atualizado);
        return;
      }
      const criado = await criarItemEstoque(payload);
      setForm(vazio);
      // Se o item é ração/alimento e ainda não veio de um Alimento já
      // cadastrado (prefill.alimentoId), pergunta se quer criar o Alimento
      // correspondente — vínculo inverso do "converter em produto".
      if (form.finalidade === "Ração/Alimento" && !prefill?.alimentoId) {
        const converter = window.confirm(`Deseja também cadastrar "${criado.nome}" como Alimento (Configurações > Cadastro > Alimentação > Alimentos), para uso em dietas?`);
        if (converter) pedirCadastroDeAlimento({ nome: criado.nome, estoqueId: criado.id });
      }
      // Veio de "Cadastrar novo item de estoque vinculado" (Alimento já
      // salvo) — volta sozinho pra edição daquele alimento, já mostrando o
      // vínculo, em vez de deixar o usuário preso na tela de Estoque sem
      // nenhum jeito de conferir se deu certo.
      if (prefill?.alimentoId) pedirReaberturaDeAlimento(prefill.alimentoId);
      onCriado(criado);
    } catch (e: any) {
      setErro(e.message || "Erro ao cadastrar item");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => set({ nome: e.target.value })} /></div>
        <div><label style={labelStyle}>Número</label><input style={inputStyle} value={form.numero_produto} onChange={(e) => set({ numero_produto: e.target.value })} /></div>
        <div><label style={labelStyle}>Classificação</label>
          <select style={inputStyle} value={form.categoria} onChange={(e) => set({ categoria: e.target.value })}>
            <option value="">—</option>
            {form.categoria && !categorias.some((c) => c.nome === form.categoria) && <option value={form.categoria}>{form.categoria}</option>}
            {categorias.map((c) => <option key={c.id} value={c.nome}>{c.nome}</option>)}
          </select>
        </div>
        <div><label style={labelStyle}>Finalidade</label>
          <select style={inputStyle} value={form.finalidade} onChange={(e) => set({ finalidade: e.target.value })}>
            <option value="">—</option>
            {form.finalidade && !finalidades.some((f) => f.nome === form.finalidade) && <option value={form.finalidade}>{form.finalidade}</option>}
            {finalidades.map((f) => <option key={f.id} value={f.nome}>{f.nome}</option>)}
          </select>
          <span style={{ display: "block", fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
            Decide se o item aparece nos seletores de aplicação de medicamento/hormônio.
          </span>
        </div>
        {form.finalidade === "Medicamento" && (
          <div>
            <div className="flex items-center justify-between">
              <label style={labelStyle}>Princípio ativo (medicamento)</label>
              <button type="button" className="btn-ghost" title="Cadastrar um princípio ativo que ainda não existe na lista"
                style={{ fontSize: "0.68rem", display: "flex", alignItems: "center", gap: "0.2rem", padding: "0.1rem 0.4rem" }}
                onClick={() => { setNovoPrincipioAberto(true); setErroPrincipio(null); }}>
                <Plus size={12} /> Novo
              </button>
            </div>
            {!novoPrincipioAberto ? (
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
                {form.principio_ativo_id && !principiosAtivos.some((p) => String(p.id) === form.principio_ativo_id) && (
                  <option value={form.principio_ativo_id}>{form.principio_ativo || `Princípio #${form.principio_ativo_id}`}</option>
                )}
                {principiosAtivos.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
              </select>
            ) : (
              <div>
                <div className="flex items-center gap-1">
                  <input style={inputStyle} value={novoPrincipioNome} onChange={(e) => setNovoPrincipioNome(e.target.value)}
                    placeholder="Nome do princípio ativo" autoFocus />
                  <button type="button" className="btn-ghost" title="Salvar" style={{ padding: "0.3rem" }}
                    disabled={salvandoPrincipio} onClick={criarNovoPrincipio}>
                    <Check size={14} />
                  </button>
                  <button type="button" className="btn-ghost" title="Cancelar" style={{ padding: "0.3rem" }}
                    onClick={() => { setNovoPrincipioAberto(false); setNovoPrincipioNome(""); setErroPrincipio(null); }}>
                    <X size={14} />
                  </button>
                </div>
                {erroPrincipio && <p style={{ color: "var(--red)", fontSize: "0.7rem", marginTop: "0.2rem" }}>{erroPrincipio}</p>}
              </div>
            )}
          </div>
        )}
        {form.finalidade === "Medicamento" && (
          <div>
            <SeletorMultiploComBusca
              label="Categoria (medicamento) — pode marcar mais de uma"
              opcoes={categoriasMedicamento.map((c) => ({ id: c.id, nome: c.nome }))}
              selecionados={form.categoriaMedicamentoIds} onChange={(ids) => set({ categoriaMedicamentoIds: ids })}
              placeholder="Ex.: Antibiótico" />
          </div>
        )}
        {form.finalidade === "Medicamento" && (
          <div>
            <SeletorMultiploComBusca
              label="Classificação do medicamento — pode marcar mais de uma"
              opcoes={classificacoesMedicamento.map((c) => ({ id: c.id, nome: c.nome }))}
              selecionados={form.classificacaoMedicamentoIds} onChange={(ids) => set({ classificacaoMedicamentoIds: ids })}
              placeholder="Ex.: Genérico, uso controlado…" />
          </div>
        )}
        {form.finalidade === "Medicamento" && (
          <div><label style={labelStyle}>Laboratório</label>
            <select style={inputStyle} value={form.laboratorio} onChange={(e) => set({ laboratorio: e.target.value })}>
              <option value="">—</option>
              {form.laboratorio && !laboratorios.some((l) => l.nome === form.laboratorio) && <option value={form.laboratorio}>{form.laboratorio}</option>}
              {laboratorios.map((l) => <option key={l.id} value={l.nome}>{l.nome}</option>)}
            </select></div>
        )}
        {form.categoria === "Sêmen e genética" && (
          <div><label style={labelStyle}>Sêmen sexado ou convencional?</label>
            <select style={inputStyle} value={form.tipo_semen || "convencional"} onChange={(e) => set({ tipo_semen: e.target.value })}>
              <option value="convencional">Convencional</option>
              <option value="sexado">Sexado</option>
            </select>
          </div>
        )}
        <div><label style={labelStyle}>Unidade</label>
          <select style={inputStyle} value={form.unidade} onChange={(e) => set({ unidade: e.target.value })}>
            <option value="">Selecione…</option>
            {form.unidade && !unidades.some((u) => u.nome === form.unidade) && <option value={form.unidade}>{form.unidade}</option>}
            {unidades.map((u) => <option key={u.id} value={u.nome}>{u.nome}</option>)}
          </select>
        </div>

        {form.estocavel && (
          <div><label style={labelStyle}>Saldo inicial</label><input type="number" style={inputStyle} value={form.quantidade} onChange={(e) => set({ quantidade: e.target.value })} /></div>
        )}
        {form.estocavel && (
          <div><label style={labelStyle}>Estoque mínimo</label><input type="number" style={inputStyle} value={form.estoque_minimo} onChange={(e) => set({ estoque_minimo: e.target.value })} /></div>
        )}
        <div><label style={labelStyle}>Valor unitário (R$)</label><CampoMoeda style={inputStyle} value={Number(form.valor_unitario) || 0} onChange={(v) => set({ valor_unitario: v ? String(v) : "" })} /></div>
        {form.estocavel && (
          <div><label style={labelStyle}>Local de armazenamento</label>
            <select style={inputStyle} value={form.local_armazenamento} onChange={(e) => set({ local_armazenamento: e.target.value })}>
              <option value="">—</option>
              {form.local_armazenamento && !locaisArmazenamento.some((l) => l.nome === form.local_armazenamento) && <option value={form.local_armazenamento}>{form.local_armazenamento}</option>}
              {locaisArmazenamento.map((l) => <option key={l.id} value={l.nome}>{l.nome}</option>)}
            </select>
          </div>
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
            {form.unidade_embalagem && !unidadesEmbalagem.some((u) => u.nome === form.unidade_embalagem) && <option value={form.unidade_embalagem}>{form.unidade_embalagem}</option>}
            {unidadesEmbalagem.map((u) => <option key={u.id} value={u.nome}>{u.nome}</option>)}
          </select>
        </div>
        <div><label style={labelStyle}>Unidade de medida</label>
          <select style={inputStyle} value={form.medida_embalagem} onChange={(e) => set({ medida_embalagem: e.target.value })}>
            <option value="">—</option>
            {form.medida_embalagem && !medidasEmbalagem.some((m) => m.nome === form.medida_embalagem) && <option value={form.medida_embalagem}>{form.medida_embalagem}</option>}
            {medidasEmbalagem.map((m) => <option key={m.id} value={m.nome}>{m.nome}</option>)}
          </select>
        </div>
        <div><label style={labelStyle}>Quantidade por embalagem</label><input type="number" style={inputStyle} value={form.quantidade_embalagem} onChange={(e) => set({ quantidade_embalagem: e.target.value })} /></div>
        {form.finalidade === "Medicamento" ? (
          <>
            <div><label style={labelStyle}>Carência do leite (dias)</label>
              <input type="number" style={inputStyle} value={form.carencia_leite_dias} disabled={form.proibido_lactacao}
                onChange={(e) => set({ carencia_leite_dias: e.target.value })} placeholder={form.proibido_lactacao ? "não se aplica" : "dias"} /></div>
            <div><label style={labelStyle}>Carência da carne (dias)</label>
              <input type="number" style={inputStyle} value={form.carencia_carne_dias} onChange={(e) => set({ carencia_carne_dias: e.target.value })} placeholder="dias" /></div>
            <div className="flex items-end gap-3">
              <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }} title="Este medicamento não deve ser aplicado em vaca em lactação — aparece como aviso no lançamento de aplicação sanitária.">
                <input type="checkbox" checked={form.proibido_lactacao} onChange={(e) => set({ proibido_lactacao: e.target.checked, carencia_leite_dias: e.target.checked ? "" : form.carencia_leite_dias })} />
                Não usar em vaca em lactação
              </label>
            </div>
          </>
        ) : (
          <div><label style={labelStyle}>Carência (dias)</label><input type="number" style={inputStyle} value={form.carencia_dias} onChange={(e) => set({ carencia_dias: e.target.value })} placeholder="período de carência do leite/carne" /></div>
        )}

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
        <div className="flex items-end gap-3">
          <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }} title="Item de patrimônio (ex.: trator, benfeitoria) — uma compra deste item sugere vincular/criar um registro em Controle Financeiro > Patrimônio.">
            <input type="checkbox" checked={form.gera_patrimonio} onChange={(e) => set({ gera_patrimonio: e.target.checked })} /> Patrimônio
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

        {editando && form.estocavel && <PainelLotesEstoque estoqueId={editando.id} />}
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{erro}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : editando ? "Salvar alterações" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onCancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );
}
