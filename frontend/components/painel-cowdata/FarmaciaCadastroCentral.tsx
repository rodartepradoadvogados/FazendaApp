"use client";
// Painel CowData > Farmácia > Cadastro central — o CowData cria, aqui, o que
// vira PADRÃO para todas as fazendas: categorias (doença/reprodutivo/
// produtivo/preventivo/suporte), princípios ativos (lista fechada) e
// medicamentos (marca comercial + 1 ou mais princípios + 1 ou mais
// categorias). Ao salvar um medicamento, o backend cria automaticamente o
// item de Estoque correspondente em toda fazenda-cliente — inativo e não-
// estocável, pronto pro tenant ativar se quiser (ver painel_cowdata_farmacia.py).
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, Pill, Plus, Stethoscope, Syringe } from "lucide-react";
import {
  atualizarCategoriaFarmaciaCowData, criarCategoriaFarmaciaCowData,
  criarMedicamentoFarmaciaCowData, criarPrincipioFarmaciaCowData, excluirPrincipioFarmaciaCowData,
  fetchCategoriasFarmaciaCowData, fetchMedicamentosFarmaciaCowData, fetchPrincipiosFarmaciaCowData,
  refazerFanoutMedicamentoFarmaciaCowData,
  type CategoriaFarmaciaCowData, type MedicamentoFarmaciaCowData, type PrincipioFarmaciaCowData,
} from "@/lib/api";

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

const ABAS = [
  { chave: "categorias", label: "Categorias", icone: Stethoscope },
  { chave: "principios", label: "Princípios ativos", icone: Pill },
  { chave: "medicamentos", label: "Medicamentos", icone: Syringe },
] as const;
type Aba = (typeof ABAS)[number]["chave"];

export default function FarmaciaCadastroCentral() {
  const { cor: COR } = usePainelCowDataEstilos();
  const [aba, setAba] = useState<Aba>("categorias");

  return (
    <div>
      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        {ABAS.map(({ chave, label, icone: Icone }) => (
          <button key={chave} onClick={() => setAba(chave)}
            style={{
              fontSize: "0.8rem", padding: "0.4rem 0.85rem", borderRadius: "var(--r-sm)", cursor: "pointer",
              display: "inline-flex", alignItems: "center", gap: "0.4rem", fontWeight: 700,
              border: `1px solid ${aba === chave ? COR.dourado : COR.borda}`,
              background: aba === chave ? COR.dourado : "transparent",
              color: aba === chave ? COR.bg : COR.mudo,
            }}>
            <Icone size={14} /> {label}
          </button>
        ))}
      </div>
      {aba === "categorias" && <AbaCategorias />}
      {aba === "principios" && <AbaPrincipios />}
      {aba === "medicamentos" && <AbaMedicamentos />}
    </div>
  );
}

function AbaCategorias() {
  const { cor: COR, inputStyle, labelStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [lista, setLista] = useState<CategoriaFarmaciaCowData[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState("doenca");
  const [descricao, setDescricao] = useState("");
  const [editando, setEditando] = useState<number | null>(null);
  const [salvando, setSalvando] = useState(false);

  const carregar = () => fetchCategoriasFarmaciaCowData().then(setLista).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); }, []);

  async function salvar() {
    const nomeLimpo = nome.trim();
    if (!nomeLimpo) { setErro("Informe o nome."); return; }
    setErro(null); setSalvando(true);
    try {
      if (editando != null) await atualizarCategoriaFarmaciaCowData(editando, { nome: nomeLimpo, tipo, descricao: descricao || null });
      else await criarCategoriaFarmaciaCowData({ nome: nomeLimpo, tipo, descricao: descricao || null });
      setNome(""); setDescricao(""); setEditando(null);
      carregar();
    } catch (e) { setErro(msgErro(e)); } finally { setSalvando(false); }
  }

  function editar(c: CategoriaFarmaciaCowData) {
    setEditando(c.id); setNome(c.nome); setTipo(c.tipo); setDescricao(c.descricao || "");
  }

  return (
    <div>
      <p style={{ fontSize: "0.8rem", color: COR.mudo, marginBottom: "0.8rem" }}>
        Doença, Reprodutivo, Produtivo, Preventivo e Suporte — a categoria que organiza a Farmácia de toda fazenda-cliente.
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
          <button style={btnGhost} onClick={() => { setEditando(null); setNome(""); setDescricao(""); }}>Cancelar</button>
        )}
      </div>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem" }}><AlertTriangle size={13} style={{ display: "inline", marginRight: 4 }} />{erro}</p>}
      {!lista ? <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Carregando…</p> : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {lista.map((c) => {
            const t = TIPOS.find((x) => x.valor === c.tipo);
            return (
              <div key={c.id} onClick={() => editar(c)} style={{
                display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.7rem", cursor: "pointer",
                borderRadius: "var(--r-sm)", border: `1px solid ${COR.borda}`, background: COR.painelAlt,
              }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: t?.cor || COR.mudo, flexShrink: 0 }} />
                <strong style={{ fontSize: "0.85rem", color: COR.texto }}>{c.nome}</strong>
                <span style={{ fontSize: "0.72rem", color: COR.mudo }}>{t?.label || c.tipo}</span>
                {!c.ativo && <span style={{ fontSize: "0.7rem", color: "var(--red)" }}>Inativa</span>}
                {c.descricao && <span style={{ fontSize: "0.75rem", color: COR.mudo, marginLeft: "auto" }}>{c.descricao}</span>}
              </div>
            );
          })}
          {lista.length === 0 && <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Nenhuma categoria cadastrada ainda.</p>}
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
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  const [nomeComercial, setNomeComercial] = useState("");
  const [laboratorio, setLaboratorio] = useState("");
  const [principioIds, setPrincipioIds] = useState<Set<number>>(new Set());
  const [doencaIds, setDoencaIds] = useState<Set<number>>(new Set());
  const [doseTexto, setDoseTexto] = useState("");
  const [carenciaLeite, setCarenciaLeite] = useState("");
  const [carenciaCarne, setCarenciaCarne] = useState("");

  function carregar() {
    Promise.all([fetchMedicamentosFarmaciaCowData(), fetchPrincipiosFarmaciaCowData(), fetchCategoriasFarmaciaCowData()])
      .then(([m, p, c]) => { setLista(m); setPrincipios(p); setCategorias(c); })
      .catch((e) => setErro(e.message));
  }
  useEffect(() => { carregar(); }, []);

  function alternar(set: Set<number>, atualizar: (s: Set<number>) => void, id: number) {
    const novo = new Set(set);
    if (novo.has(id)) novo.delete(id); else novo.add(id);
    atualizar(novo);
  }

  async function salvar() {
    const nome = nomeComercial.trim();
    if (!nome) { setErro("Informe o nome comercial."); return; }
    if (principioIds.size === 0) { setErro("Selecione ao menos um princípio ativo."); return; }
    setErro(null); setMensagem(null); setSalvando(true);
    try {
      const resultado = await criarMedicamentoFarmaciaCowData({
        nome_comercial: nome, laboratorio: laboratorio || null,
        principio_ativo_ids: [...principioIds], doenca_ids: [...doencaIds],
        dose_texto: doseTexto || null,
        carencia_leite_dias: carenciaLeite ? Number(carenciaLeite) : null,
        carencia_carne_dias: carenciaCarne ? Number(carenciaCarne) : null,
      });
      setMensagem(
        `"${nome}" cadastrado — item de estoque criado em ${resultado.fan_out.criados} fazenda(s)` +
        (resultado.fan_out.ja_existiam ? `, ${resultado.fan_out.ja_existiam} já tinha(m) um item com esse nome (mantido intocado)` : "") +
        ". Inativo e não-estocável até cada fazenda decidir ativar."
      );
      setNomeComercial(""); setLaboratorio(""); setPrincipioIds(new Set()); setDoencaIds(new Set());
      setDoseTexto(""); setCarenciaLeite(""); setCarenciaCarne("");
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
        classificação &ldquo;Medicamentos&rdquo; e o(s) princípio(s) já preenchido(s), mas <strong>inativo e não-estocável</strong> até o
        tenant decidir usar.
      </p>

      <div style={{ border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "0.8rem", marginBottom: "1.2rem", background: COR.painelAlt }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem", marginBottom: "0.6rem" }}>
          <div>
            <label style={labelStyle}>Nome comercial</label>
            <input style={{ ...inputStyle, width: "100%" }} value={nomeComercial} onChange={(e) => setNomeComercial(e.target.value)} placeholder="Ex.: Maxicam 2%" />
          </div>
          <div>
            <label style={labelStyle}>Laboratório (opcional)</label>
            <input style={{ ...inputStyle, width: "100%" }} value={laboratorio} onChange={(e) => setLaboratorio(e.target.value)} placeholder="Ex.: Ourofino" />
          </div>
        </div>

        <label style={labelStyle}>Princípio(s) ativo(s) — pode marcar mais de um (medicamento combinado)</label>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", marginBottom: "0.6rem" }}>
          {principios.map((p) => (
            <button key={p.id} onClick={() => alternar(principioIds, setPrincipioIds, p.id)}
              style={{
                fontSize: "0.76rem", padding: "0.3rem 0.6rem", borderRadius: 999, cursor: "pointer",
                border: `1px solid ${principioIds.has(p.id) ? COR.dourado : COR.borda}`,
                background: principioIds.has(p.id) ? COR.dourado : "transparent",
                color: principioIds.has(p.id) ? COR.bg : COR.mudo, fontWeight: principioIds.has(p.id) ? 700 : 500,
                display: "inline-flex", alignItems: "center", gap: "0.25rem",
              }}>
              {principioIds.has(p.id) && <Check size={11} />}{p.nome}
            </button>
          ))}
          {principios.length === 0 && <span style={{ fontSize: "0.78rem", color: COR.mudo }}>Cadastre ao menos um princípio ativo na aba anterior.</span>}
        </div>

        <label style={labelStyle}>Categoria(s)/indicação(ões) — para onde este medicamento aparece sugerido</label>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", marginBottom: "0.6rem" }}>
          {categorias.map((c) => (
            <button key={c.id} onClick={() => alternar(doencaIds, setDoencaIds, c.id)}
              style={{
                fontSize: "0.76rem", padding: "0.3rem 0.6rem", borderRadius: 999, cursor: "pointer",
                border: `1px solid ${doencaIds.has(c.id) ? COR.dourado : COR.borda}`,
                background: doencaIds.has(c.id) ? COR.dourado : "transparent",
                color: doencaIds.has(c.id) ? COR.bg : COR.mudo, fontWeight: doencaIds.has(c.id) ? 700 : 500,
              }}>
              {c.nome}
            </button>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.6rem", marginBottom: "0.8rem" }}>
          <div>
            <label style={labelStyle}>Dose (texto pronto)</label>
            <input style={{ ...inputStyle, width: "100%" }} value={doseTexto} onChange={(e) => setDoseTexto(e.target.value)} placeholder="Ex.: 1 mL/50 kg SC" />
          </div>
          <div>
            <label style={labelStyle}>Carência leite (dias)</label>
            <input type="number" style={{ ...inputStyle, width: "100%" }} value={carenciaLeite} onChange={(e) => setCarenciaLeite(e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Carência carne (dias)</label>
            <input type="number" style={{ ...inputStyle, width: "100%" }} value={carenciaCarne} onChange={(e) => setCarenciaCarne(e.target.value)} />
          </div>
        </div>

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
