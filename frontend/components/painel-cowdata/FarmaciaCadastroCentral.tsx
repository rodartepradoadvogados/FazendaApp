"use client";
// Painel CowData > Farmácia > Cadastro central — o CowData cria, aqui, o que
// vira PADRÃO para todas as fazendas: categorias (doença/reprodutivo/
// produtivo/preventivo/suporte), princípios ativos (lista fechada) e
// medicamentos (marca comercial + 1 ou mais princípios + 1 ou mais
// categorias). Ao salvar um medicamento, o backend cria automaticamente o
// item de Estoque correspondente em toda fazenda-cliente — inativo e não-
// estocável, pronto pro tenant ativar se quiser (ver painel_cowdata_farmacia.py).
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Beaker, Building2, Pill, Plus, Stethoscope, Syringe, Tags } from "lucide-react";
import {
  atualizarCategoriaFarmaciaCowData, criarCategoriaFarmaciaCowData,
  criarMedicamentoFarmaciaCowData, criarPrincipioFarmaciaCowData, excluirPrincipioFarmaciaCowData,
  fetchCategoriasFarmaciaCowData, fetchMedicamentosFarmaciaCowData, fetchPrincipiosFarmaciaCowData,
  refazerFanoutMedicamentoFarmaciaCowData,
  fetchLaboratoriosFarmaciaCowData, criarLaboratorioFarmaciaCowData, atualizarLaboratorioFarmaciaCowData,
  fetchCategoriasMedicamentoFarmaciaCowData, criarCategoriaMedicamentoFarmaciaCowData, atualizarCategoriaMedicamentoFarmaciaCowData,
  fetchClassificacoesMedicamentoFarmaciaCowData, criarClassificacaoMedicamentoFarmaciaCowData, atualizarClassificacaoMedicamentoFarmaciaCowData,
  type CategoriaFarmaciaCowData, type MedicamentoFarmaciaCowData, type PrincipioFarmaciaCowData, type ItemCadastroSimples,
} from "@/lib/api";
import SeletorMultiploComBusca from "@/components/SeletorMultiploComBusca";

function msgErro(e: unknown): string {
  return e instanceof Error ? e.message : "Erro inesperado";
}
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";

const TIPOS: { valor: string; label: string; cor: string }[] = [
  { valor: "doenca", label: "Doença", cor: "var(--cat-sanidade)" },
  { valor: "reprodutivo", label: "Reprodutivo", cor: "var(--cat-reproducao)" },
  { valor: "produtivo", label: "Produtivo", cor: "var(--blue)" },
  { valor: "preventivo", label: "Preventivo", cor: "var(--dourado-light)" },
  { valor: "suporte", label: "Suporte", cor: "var(--cat-acesso)" },
];

// Hierarquia pedida pelo usuário (01/09/2026), na ordem exata: Seção 1
// (Doenças/Reprodutivo/Produtivo/Preventivo/Suporte/Todas — filtro por
// Doenca.tipo) e Seção 2 (Medicamentos/Princípios ativos/Categorias/
// Classificação do medicamento/Laboratórios — o catálogo de farmácia
// propriamente dito). "Categorias" aqui é a Fase B ("Categoria (medicamento)":
// antimicrobiano/antibiótico...) — não confundir com Doenca.tipo acima.
const SECAO1_ABAS = [
  { chave: "doenca", label: "Doenças" },
  { chave: "reprodutivo", label: "Reprodutivo" },
  { chave: "produtivo", label: "Produtivo" },
  { chave: "preventivo", label: "Preventivo" },
  { chave: "suporte", label: "Suporte" },
  { chave: "todas", label: "Todas" },
] as const;
const SECAO2_ABAS = [
  { chave: "medicamentos", label: "Medicamentos", icone: Syringe },
  { chave: "principios", label: "Princípios ativos", icone: Pill },
  { chave: "categoriasMedicamento", label: "Categorias", icone: Tags },
  { chave: "classificacoesMedicamento", label: "Classificação do medicamento", icone: Beaker },
  { chave: "laboratorios", label: "Laboratórios", icone: Building2 },
] as const;
type Aba = (typeof SECAO1_ABAS)[number]["chave"] | (typeof SECAO2_ABAS)[number]["chave"];

function BotaoAba({ ativo, onClick, children, icone: Icone }: { ativo: boolean; onClick: () => void; children: React.ReactNode; icone?: React.ComponentType<{ size?: number }> }) {
  const { cor: COR } = usePainelCowDataEstilos();
  return (
    <button onClick={onClick}
      style={{
        fontSize: "0.8rem", padding: "0.4rem 0.85rem", borderRadius: "var(--r-sm)", cursor: "pointer",
        display: "inline-flex", alignItems: "center", gap: "0.4rem", fontWeight: 700,
        border: `1px solid ${ativo ? COR.dourado : COR.borda}`,
        background: ativo ? COR.dourado : "transparent",
        color: ativo ? COR.bg : COR.mudo,
      }}>
      {Icone && <Icone size={14} />} {children}
    </button>
  );
}

export default function FarmaciaCadastroCentral() {
  const { cor: COR } = usePainelCowDataEstilos();
  const [aba, setAba] = useState<Aba>("doenca");

  return (
    <div>
      <p style={{ fontSize: "0.68rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: COR.mudo, margin: "0 0 0.4rem" }}>
        Seção 1 — Indicações
      </p>
      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        {SECAO1_ABAS.map(({ chave, label }) => (
          <BotaoAba key={chave} ativo={aba === chave} onClick={() => setAba(chave)}>{label}</BotaoAba>
        ))}
      </div>
      <p style={{ fontSize: "0.68rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: COR.mudo, margin: "0 0 0.4rem" }}>
        Seção 2 — Catálogo de farmácia
      </p>
      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        {SECAO2_ABAS.map(({ chave, label, icone }) => (
          <BotaoAba key={chave} ativo={aba === chave} onClick={() => setAba(chave)} icone={icone}>{label}</BotaoAba>
        ))}
      </div>
      <div style={{ borderTop: `1px solid ${COR.borda}`, paddingTop: "1rem" }}>
        {(aba === "doenca" || aba === "reprodutivo" || aba === "produtivo" || aba === "preventivo" || aba === "suporte") && (
          <AbaCategorias tipoFiltro={aba} />
        )}
        {aba === "todas" && <AbaCategorias />}
        {aba === "principios" && <AbaPrincipios />}
        {aba === "medicamentos" && <AbaMedicamentos />}
        {aba === "categoriasMedicamento" && (
          <AbaCatalogoSimples
            titulo="Categoria (medicamento)"
            descricao="Antimicrobiano, anti-inflamatório, antibiótico... — a classificação médica do medicamento (cumulativa: um medicamento pode ter mais de uma). Cadastrada aqui, vira padrão em todas as fazendas."
            fetch={fetchCategoriasMedicamentoFarmaciaCowData} criar={criarCategoriaMedicamentoFarmaciaCowData} atualizar={atualizarCategoriaMedicamentoFarmaciaCowData}
            placeholder="Ex.: Antiparasitário" />
        )}
        {aba === "classificacoesMedicamento" && (
          <AbaCatalogoSimples
            titulo="Classificação do medicamento"
            descricao="Eixo próprio, independente de Categoria — cadastre os valores que fizerem sentido (ex.: controlado, genérico, uso interno/externo). Cumulativo, mesmo padrão de Categoria."
            fetch={fetchClassificacoesMedicamentoFarmaciaCowData} criar={criarClassificacaoMedicamentoFarmaciaCowData} atualizar={atualizarClassificacaoMedicamentoFarmaciaCowData}
            placeholder="Ex.: Genérico" />
        )}
        {aba === "laboratorios" && (
          <AbaCatalogoSimples
            titulo="Laboratório"
            descricao="Fabricante do medicamento — alimenta o seletor tanto aqui quanto no cadastro de item de estoque do tenant."
            fetch={fetchLaboratoriosFarmaciaCowData} criar={criarLaboratorioFarmaciaCowData} atualizar={atualizarLaboratorioFarmaciaCowData}
            placeholder="Ex.: Ourofino" />
        )}
      </div>
    </div>
  );
}

// Cadastro "nome + ativo" genérico — reutilizado por Categoria (medicamento),
// Classificação do medicamento e Laboratório (Fase B, 01/09/2026): mesma
// interação de sempre (lista de pílulas + adicionar), sem repetir a mesma
// tela 3 vezes.
function AbaCatalogoSimples({ titulo, descricao, fetch, criar, atualizar, placeholder }: {
  titulo: string; descricao: string; placeholder: string;
  fetch: () => Promise<ItemCadastroSimples[]>;
  criar: (dados: { nome: string; ativo?: boolean }) => Promise<ItemCadastroSimples>;
  atualizar: (id: number, dados: { nome: string; ativo: boolean }) => Promise<ItemCadastroSimples>;
}) {
  const { cor: COR, inputStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [lista, setLista] = useState<ItemCadastroSimples[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [nome, setNome] = useState("");
  const [salvando, setSalvando] = useState(false);

  const carregar = () => fetch().then(setLista).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function adicionar() {
    const nomeLimpo = nome.trim();
    if (!nomeLimpo) { setErro("Informe o nome."); return; }
    setErro(null); setSalvando(true);
    try { await criar({ nome: nomeLimpo }); setNome(""); carregar(); }
    catch (e) { setErro(msgErro(e)); } finally { setSalvando(false); }
  }

  async function alternarAtivo(item: ItemCadastroSimples) {
    setErro(null);
    try { await atualizar(item.id, { nome: item.nome, ativo: !item.ativo }); carregar(); }
    catch (e) { setErro(msgErro(e)); }
  }

  return (
    <div>
      <p style={{ fontSize: "0.8rem", color: COR.mudo, marginBottom: "0.8rem" }}>{descricao}</p>
      <div style={{ display: "flex", gap: "0.6rem", marginBottom: "1rem" }}>
        <input style={{ ...inputStyle, width: 260 }} value={nome} onChange={(e) => setNome(e.target.value)} placeholder={placeholder}
          onKeyDown={(e) => { if (e.key === "Enter") adicionar(); }} />
        <button style={btnPrimario} onClick={adicionar} disabled={salvando}><Plus size={14} /> Adicionar</button>
      </div>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem" }}><AlertTriangle size={13} style={{ display: "inline", marginRight: 4 }} />{erro}</p>}
      {!lista ? <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Carregando…</p> : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
          {lista.map((item) => (
            <span key={item.id} onClick={() => alternarAtivo(item)} title={item.ativo ? "Clique para desativar" : "Clique para reativar"} style={{
              display: "inline-flex", alignItems: "center", gap: "0.4rem", padding: "0.3rem 0.65rem", cursor: "pointer",
              borderRadius: 999, border: `1px solid ${COR.borda}`, background: COR.painelAlt, fontSize: "0.8rem",
              color: item.ativo ? COR.texto : COR.mudo, opacity: item.ativo ? 1 : 0.6,
            }}>
              {item.nome}{!item.ativo && " (inativa)"}
            </span>
          ))}
          {lista.length === 0 && <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Nada cadastrado ainda — {titulo.toLowerCase()} começa vazio.</p>}
        </div>
      )}
    </div>
  );
}

function AbaCategorias({ tipoFiltro }: { tipoFiltro?: string } = {}) {
  const { cor: COR, inputStyle, labelStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [lista, setLista] = useState<CategoriaFarmaciaCowData[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState(tipoFiltro || "doenca");
  const [descricao, setDescricao] = useState("");
  const [editando, setEditando] = useState<number | null>(null);
  const [salvando, setSalvando] = useState(false);

  const carregar = () => fetchCategoriasFarmaciaCowData().then(setLista).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); }, []);
  // Ao trocar de aba (Doenças/Reprodutivo/...), a nova categoria já nasce
  // com o tipo daquela aba — evita cadastrar em Reprodutivo e o item cair
  // sem querer em Doenças por esquecer de trocar o seletor.
  useEffect(() => { if (!editando) setTipo(tipoFiltro || "doenca"); }, [tipoFiltro]); // eslint-disable-line react-hooks/exhaustive-deps

  const listaFiltrada = useMemo(
    () => (tipoFiltro ? (lista || []).filter((c) => c.tipo === tipoFiltro) : lista || []),
    [lista, tipoFiltro],
  );

  async function salvar() {
    const nomeLimpo = nome.trim();
    if (!nomeLimpo) { setErro("Informe o nome."); return; }
    setErro(null); setSalvando(true);
    try {
      if (editando != null) await atualizarCategoriaFarmaciaCowData(editando, { nome: nomeLimpo, tipo, descricao: descricao || null });
      else await criarCategoriaFarmaciaCowData({ nome: nomeLimpo, tipo, descricao: descricao || null });
      setNome(""); setDescricao(""); setEditando(null); setTipo(tipoFiltro || "doenca");
      carregar();
    } catch (e) { setErro(msgErro(e)); } finally { setSalvando(false); }
  }

  function editar(c: CategoriaFarmaciaCowData) {
    setEditando(c.id); setNome(c.nome); setTipo(c.tipo); setDescricao(c.descricao || "");
  }

  return (
    <div>
      <p style={{ fontSize: "0.8rem", color: COR.mudo, marginBottom: "0.8rem" }}>
        Doença, Reprodutivo, Produtivo, Preventivo e Suporte — a indicação que organiza a Farmácia de toda fazenda-cliente.
        Cadastrada aqui, aparece automaticamente em todos os tenants.
      </p>
      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", marginBottom: "1rem", alignItems: "flex-end" }}>
        <div>
          <label style={labelStyle}>Nome</label>
          <input style={{ ...inputStyle, width: 220 }} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: Mastite" />
        </div>
        <div>
          <label style={labelStyle}>Tipo</label>
          <select style={{ ...inputStyle, width: 170 }} value={tipo} onChange={(e) => setTipo(e.target.value)}>
            {TIPOS.map((t) => <option key={t.valor} value={t.valor}>{t.label}</option>)}
          </select>
        </div>
        <div style={{ flex: "1 1 240px" }}>
          <label style={labelStyle}>Descrição (opcional)</label>
          <input style={{ ...inputStyle, width: "100%" }} value={descricao} onChange={(e) => setDescricao(e.target.value)} placeholder="Nota explicativa desta categoria" />
        </div>
        <button style={btnPrimario} onClick={salvar} disabled={salvando}>
          <Plus size={14} /> {editando != null ? "Salvar" : "Adicionar"}
        </button>
        {editando != null && (
          <button style={btnGhost} onClick={() => { setEditando(null); setNome(""); setDescricao(""); setTipo(tipoFiltro || "doenca"); }}>Cancelar</button>
        )}
      </div>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem" }}><AlertTriangle size={13} style={{ display: "inline", marginRight: 4 }} />{erro}</p>}
      {!lista ? <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Carregando…</p> : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {listaFiltrada.map((c) => {
            const t = TIPOS.find((x) => x.valor === c.tipo);
            return (
              <div key={c.id} onClick={() => editar(c)} style={{
                display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.7rem", cursor: "pointer",
                borderRadius: "var(--r-sm)", border: `1px solid ${COR.borda}`, background: COR.painelAlt,
              }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: t?.cor || COR.mudo, flexShrink: 0 }} />
                <strong style={{ fontSize: "0.85rem", color: COR.texto }}>{c.nome}</strong>
                {!tipoFiltro && <span style={{ fontSize: "0.72rem", color: COR.mudo }}>{t?.label || c.tipo}</span>}
                {!c.ativo && <span style={{ fontSize: "0.7rem", color: "var(--red)" }}>Inativa</span>}
                {c.descricao && <span style={{ fontSize: "0.75rem", color: COR.mudo, marginLeft: "auto" }}>{c.descricao}</span>}
              </div>
            );
          })}
          {listaFiltrada.length === 0 && <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Nenhuma categoria cadastrada ainda.</p>}
        </div>
      )}
    </div>
  );
}

function AbaPrincipios() {
  const { cor: COR, inputStyle, btnPrimario } = usePainelCowDataEstilos();
  const [lista, setLista] = useState<PrincipioFarmaciaCowData[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [nome, setNome] = useState("");
  const [salvando, setSalvando] = useState(false);

  const carregar = () => fetchPrincipiosFarmaciaCowData().then(setLista).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); }, []);

  async function adicionar() {
    const nomeLimpo = nome.trim();
    if (!nomeLimpo) { setErro("Informe o nome."); return; }
    setErro(null); setSalvando(true);
    try { await criarPrincipioFarmaciaCowData({ nome: nomeLimpo }); setNome(""); carregar(); }
    catch (e) { setErro(msgErro(e)); } finally { setSalvando(false); }
  }

  async function excluir(id: number, nomePrincipio: string) {
    if (!confirm(`Excluir o princípio ativo "${nomePrincipio}"? Isso só é permitido se nenhum medicamento o usar.`)) return;
    setErro(null);
    try { await excluirPrincipioFarmaciaCowData(id); carregar(); }
    catch (e) { setErro(msgErro(e)); }
  }

  return (
    <div>
      <p style={{ fontSize: "0.8rem", color: COR.mudo, marginBottom: "0.8rem" }}>
        Lista fechada — só o que estiver aqui pode ser selecionado ao cadastrar um medicamento (Painel CowData ou tenant).
        Um medicamento pode combinar mais de um princípio.
      </p>
      <div style={{ display: "flex", gap: "0.6rem", marginBottom: "1rem" }}>
        <input style={{ ...inputStyle, width: 260 }} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: Meloxicam" />
        <button style={btnPrimario} onClick={adicionar} disabled={salvando}><Plus size={14} /> Adicionar</button>
      </div>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem" }}><AlertTriangle size={13} style={{ display: "inline", marginRight: 4 }} />{erro}</p>}
      {!lista ? <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Carregando…</p> : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
          {lista.map((p) => (
            <span key={p.id} style={{
              display: "inline-flex", alignItems: "center", gap: "0.4rem", padding: "0.3rem 0.65rem",
              borderRadius: 999, border: `1px solid ${COR.borda}`, background: COR.painelAlt, fontSize: "0.8rem", color: COR.texto,
            }}>
              {p.nome}
              <button onClick={() => excluir(p.id, p.nome)} title="Excluir" style={{ background: "none", border: "none", color: COR.mudo, cursor: "pointer", padding: 0, lineHeight: 1 }}>×</button>
            </span>
          ))}
          {lista.length === 0 && <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Nenhum princípio ativo cadastrado ainda.</p>}
        </div>
      )}
    </div>
  );
}

function AbaMedicamentos() {
  const { cor: COR, inputStyle, labelStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [lista, setLista] = useState<MedicamentoFarmaciaCowData[] | null>(null);
  const [principios, setPrincipios] = useState<PrincipioFarmaciaCowData[]>([]);
  const [categorias, setCategorias] = useState<CategoriaFarmaciaCowData[]>([]);
  const [categoriasMedicamento, setCategoriasMedicamento] = useState<ItemCadastroSimples[]>([]);
  const [classificacoesMedicamento, setClassificacoesMedicamento] = useState<ItemCadastroSimples[]>([]);
  const [laboratorios, setLaboratorios] = useState<ItemCadastroSimples[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  const [nomeComercial, setNomeComercial] = useState("");
  const [laboratorio, setLaboratorio] = useState("");
  const [principioIds, setPrincipioIds] = useState<number[]>([]);
  const [doencaIds, setDoencaIds] = useState<number[]>([]);
  const [doseTexto, setDoseTexto] = useState("");
  const [carenciaLeite, setCarenciaLeite] = useState("");
  const [carenciaCarne, setCarenciaCarne] = useState("");
  const [proibidoLactacao, setProibidoLactacao] = useState(false);
  const [categoriaMedicamentoIds, setCategoriaMedicamentoIds] = useState<number[]>([]);
  const [classificacaoMedicamentoIds, setClassificacaoMedicamentoIds] = useState<number[]>([]);

  function carregar() {
    Promise.all([
      fetchMedicamentosFarmaciaCowData(), fetchPrincipiosFarmaciaCowData(), fetchCategoriasFarmaciaCowData(),
      fetchCategoriasMedicamentoFarmaciaCowData(), fetchClassificacoesMedicamentoFarmaciaCowData(), fetchLaboratoriosFarmaciaCowData(),
    ])
      .then(([m, p, c, catMed, classMed, lab]) => {
        setLista(m); setPrincipios(p); setCategorias(c);
        setCategoriasMedicamento(catMed.filter((i) => i.ativo)); setClassificacoesMedicamento(classMed.filter((i) => i.ativo));
        setLaboratorios(lab.filter((i) => i.ativo));
      })
      .catch((e) => setErro(e.message));
  }
  useEffect(() => { carregar(); }, []);

  async function salvar() {
    const nome = nomeComercial.trim();
    if (!nome) { setErro("Informe o nome comercial."); return; }
    if (principioIds.length === 0) { setErro("Selecione ao menos um princípio ativo."); return; }
    setErro(null); setMensagem(null); setSalvando(true);
    try {
      const resultado = await criarMedicamentoFarmaciaCowData({
        nome_comercial: nome, laboratorio: laboratorio || null,
        principio_ativo_ids: [...principioIds], doenca_ids: [...doencaIds],
        dose_texto: doseTexto || null,
        carencia_leite_dias: carenciaLeite ? Number(carenciaLeite) : null,
        carencia_carne_dias: carenciaCarne ? Number(carenciaCarne) : null,
        proibido_lactacao: proibidoLactacao,
        categoria_medicamento_ids: [...categoriaMedicamentoIds],
        classificacao_medicamento_ids: [...classificacaoMedicamentoIds],
      });
      setMensagem(
        `"${nome}" cadastrado — item de estoque criado em ${resultado.fan_out.criados} fazenda(s)` +
        (resultado.fan_out.ja_existiam ? `, ${resultado.fan_out.ja_existiam} já tinha(m) um item com esse nome (mantido intocado)` : "") +
        ". Inativo e não-estocável até cada fazenda decidir ativar."
      );
      setNomeComercial(""); setLaboratorio(""); setPrincipioIds([]); setDoencaIds([]);
      setDoseTexto(""); setCarenciaLeite(""); setCarenciaCarne(""); setProibidoLactacao(false);
      setCategoriaMedicamentoIds([]); setClassificacaoMedicamentoIds([]);
      carregar();
    } catch (e) { setErro(msgErro(e)); } finally { setSalvando(false); }
  }

  async function refazerFanout(id: number, nome: string) {
    setErro(null); setMensagem(null);
    try {
      const r = await refazerFanoutMedicamentoFarmaciaCowData(id);
      setMensagem(`"${nome}": ${r.criados} fazenda(s) nova(s) receberam o item, ${r.ja_existiam} já tinham.`);
      carregar();
    } catch (e) { setErro(msgErro(e)); }
  }

  const nomesPrincipios = useMemo(() => new Map(principios.map((p) => [p.id, p.nome])), [principios]);
  const nomesCategorias = useMemo(() => new Map(categorias.map((c) => [c.id, c.nome])), [categorias]);

  return (
    <div>
      <p style={{ fontSize: "0.8rem", color: COR.mudo, marginBottom: "0.8rem" }}>
        Ao salvar, um item de Estoque é criado automaticamente em toda fazenda-cliente — com finalidade &ldquo;Medicamento&rdquo;,
        categoria &ldquo;Medicamentos&rdquo;, e já com o(s) princípio(s), categoria (medicamento), laboratório e carência
        preenchidos, mas <strong>inativo e não-estocável</strong> até o tenant decidir usar.
      </p>

      <div style={{ border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "0.8rem", marginBottom: "1.2rem", background: COR.painelAlt }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem", marginBottom: "0.6rem" }}>
          <div>
            <label style={labelStyle}>Nome comercial</label>
            <input style={{ ...inputStyle, width: "100%" }} value={nomeComercial} onChange={(e) => setNomeComercial(e.target.value)} placeholder="Ex.: Maxicam 2%" />
          </div>
          <div>
            <label style={labelStyle}>Laboratório (opcional)</label>
            <select style={{ ...inputStyle, width: "100%" }} value={laboratorio} onChange={(e) => setLaboratorio(e.target.value)}>
              <option value="">—</option>
              {laboratorio && !laboratorios.some((l) => l.nome === laboratorio) && <option value={laboratorio}>{laboratorio}</option>}
              {laboratorios.map((l) => <option key={l.id} value={l.nome}>{l.nome}</option>)}
            </select>
            {laboratorios.length === 0 && <span style={{ fontSize: "0.72rem", color: COR.mudo }}>Cadastre em Seção 2 › Laboratórios.</span>}
          </div>
        </div>

        <div style={{ marginBottom: "0.7rem" }}>
          <SeletorMultiploComBusca
            label="Princípio(s) ativo(s) — pode marcar mais de um (medicamento combinado)"
            opcoes={principios.map((p) => ({ id: p.id, nome: p.nome }))}
            selecionados={principioIds} onChange={setPrincipioIds}
            placeholder="Clique para selecionar…" cor={COR} />
          {principios.length === 0 && <span style={{ fontSize: "0.78rem", color: COR.mudo }}>Cadastre ao menos um princípio ativo na aba anterior.</span>}
        </div>

        <div style={{ marginBottom: "0.7rem" }}>
          <SeletorMultiploComBusca
            label="Indicações — doenças/finalidades para onde este medicamento aparece sugerido"
            opcoes={categorias.map((c) => ({ id: c.id, nome: c.nome, grupo: TIPOS.find((t) => t.valor === c.tipo)?.label }))}
            selecionados={doencaIds} onChange={setDoencaIds}
            placeholder="Clique para selecionar…" cor={COR} />
        </div>

        <div style={{ marginBottom: "0.7rem" }}>
          <SeletorMultiploComBusca
            label="Categoria (medicamento) — pode marcar mais de uma"
            opcoes={categoriasMedicamento.map((c) => ({ id: c.id, nome: c.nome }))}
            selecionados={categoriaMedicamentoIds} onChange={setCategoriaMedicamentoIds}
            placeholder="Ex.: Antibiótico" cor={COR} />
          {categoriasMedicamento.length === 0 && <span style={{ fontSize: "0.72rem", color: COR.mudo }}>Cadastre em Seção 2 › Categorias.</span>}
        </div>

        <div style={{ marginBottom: "0.7rem" }}>
          <SeletorMultiploComBusca
            label="Classificação do medicamento — pode marcar mais de uma"
            opcoes={classificacoesMedicamento.map((c) => ({ id: c.id, nome: c.nome }))}
            selecionados={classificacaoMedicamentoIds} onChange={setClassificacaoMedicamentoIds}
            placeholder="Ex.: Genérico, uso controlado…" cor={COR} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.6rem", marginBottom: "0.8rem" }}>
          <div>
            <label style={labelStyle}>Dose (texto pronto)</label>
            <input style={{ ...inputStyle, width: "100%" }} value={doseTexto} onChange={(e) => setDoseTexto(e.target.value)} placeholder="Ex.: 1 mL/50 kg SC" />
          </div>
          <div>
            <label style={labelStyle}>Carência leite (dias)</label>
            <input type="number" style={{ ...inputStyle, width: "100%" }} value={carenciaLeite} disabled={proibidoLactacao}
              onChange={(e) => setCarenciaLeite(e.target.value)} placeholder={proibidoLactacao ? "não se aplica" : undefined} />
          </div>
          <div>
            <label style={labelStyle}>Carência carne (dias)</label>
            <input type="number" style={{ ...inputStyle, width: "100%" }} value={carenciaCarne} onChange={(e) => setCarenciaCarne(e.target.value)} />
          </div>
        </div>

        <label className="flex items-center gap-2" style={{ fontSize: "0.8rem", color: COR.texto, marginBottom: "0.8rem" }}>
          <input type="checkbox" checked={proibidoLactacao} onChange={(e) => { setProibidoLactacao(e.target.checked); if (e.target.checked) setCarenciaLeite(""); }} />
          Não usar em vaca em lactação
        </label>

        <button style={btnPrimario} onClick={salvar} disabled={salvando}><Plus size={14} /> {salvando ? "Salvando…" : "Cadastrar medicamento"}</button>
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem" }}><AlertTriangle size={13} style={{ display: "inline", marginRight: 4 }} />{erro}</p>}
      {mensagem && <p style={{ color: "var(--green-light)", fontSize: "0.82rem" }}>{mensagem}</p>}

      {!lista ? <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Carregando…</p> : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {lista.map((m) => (
            <div key={m.id} style={{
              display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.7rem",
              borderRadius: "var(--r-sm)", border: `1px solid ${COR.borda}`, background: COR.painelAlt, flexWrap: "wrap",
            }}>
              <strong style={{ fontSize: "0.85rem", color: COR.texto }}>{m.nome_comercial}</strong>
              <span style={{ fontSize: "0.75rem", color: COR.mudo }}>
                {m.principio_ativo_ids.map((id: number) => nomesPrincipios.get(id) || id).join(" + ")}
              </span>
              {m.doenca_ids.length > 0 && (
                <span style={{ fontSize: "0.72rem", color: COR.mudo }}>
                  · {m.doenca_ids.map((id: number) => nomesCategorias.get(id) || id).join(", ")}
                </span>
              )}
              <span style={{ fontSize: "0.72rem", color: m.fan_out_fazendas >= m.fan_out_total_fazendas ? "var(--green-light)" : "var(--amber)", marginLeft: "auto" }}>
                em {m.fan_out_fazendas}/{m.fan_out_total_fazendas} fazenda(s)
              </span>
              {m.fan_out_fazendas < m.fan_out_total_fazendas && (
                <button style={btnGhost} onClick={() => refazerFanout(m.id, m.nome_comercial)}>Propagar às faltantes</button>
              )}
            </div>
          ))}
          {lista.length === 0 && <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Nenhum medicamento cadastrado ainda.</p>}
        </div>
      )}
    </div>
  );
}
