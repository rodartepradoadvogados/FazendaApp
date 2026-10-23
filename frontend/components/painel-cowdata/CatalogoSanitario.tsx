"use client";
// Cockpit CowData › Catálogo sanitário — catálogo CENTRAL de vacinas e exames
// (versionado). Cada fazenda ativa (copia) o que quiser; publicar versão nova
// NUNCA muda a cópia da fazenda: ela recebe a nota "catálogo mudou" e decide.
// Rotas: /painel-cowdata/sanitario/catalogo (listar, criar, editar, versões).
// Usa o tema próprio do Painel CowData (usePainelCowDataEstilos).
import { useState, type CSSProperties } from "react";
import { BookOpen, Plus } from "lucide-react";
import {
  criarCatalogoCentral, editarCatalogoCentral, listarCatalogoCentral, mensagemDoErro, obterCatalogoCentral, publicarVersaoCatalogo,
} from "@/lib/apiSanitario";
import {
  CONDICOES, DOSE_UNIDADES, EVENTO_TIPOS, MESES_CURTOS, MODOS_LEITE, ROTULO_CONDICAO, ROTULO_EVENTO, ROTULO_MODO_LEITE, ROTULO_TIPO,
  ROTULO_UNIDADE, TIPOS_CAIXA, definicaoCompleta, fmtDataHora, intOuNulo, numOuNulo, textoJanela,
  type CatalogoCentralItem, type DefinicaoCatalogo, type TipoCaixa,
} from "@/lib/sanitarioTipos";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";
import { useCarregar } from "@/components/sanitario/comum";

type Edicao = { modo: "novo" } | { modo: "versao"; item: CatalogoCentralItem };
type FormCat = {
  chave: string; nome: string; tipo: TipoCaixa; padrao: boolean; uf: string; nota: string; base: string;
  def: DefinicaoCatalogo; categoriasRef: string;
};

function formDe(item?: CatalogoCentralItem): FormCat {
  const d = definicaoCompleta(item?.definicao) as DefinicaoCatalogo;
  const extra = (item?.definicao || {}) as Partial<DefinicaoCatalogo>;
  return {
    chave: item?.chave || "", nome: item?.nome || "", tipo: item?.tipo || "vacina", padrao: !!item?.padrao_fabrica, uf: item?.uf_sugerida || "",
    nota: "", base: item?.base_legal || "",
    def: { ...d, categorias: [], categorias_ref: extra.categorias_ref || [], pub_hist_catalogo_chave: extra.pub_hist_catalogo_chave ?? null,
      fallback_idade_min_dias: extra.fallback_idade_min_dias ?? null },
    categoriasRef: (extra.categorias_ref || []).join(", "),
  };
}

function Editor({ edicao, onFechar, onSalvo }: { edicao: Edicao; onFechar: () => void; onSalvo: (msg: string) => void }) {
  const { cor, inputStyle, labelStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [f, setF] = useState<FormCat>(() => formDe(edicao.modo === "versao" ? edicao.item : undefined));
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const d = f.def;
  const setD = (p: Partial<DefinicaoCatalogo>) => setF((x) => ({ ...x, def: { ...x.def, ...p } }));
  const linha: CSSProperties = { display: "flex", flexWrap: "wrap", gap: "0.7rem", alignItems: "flex-end" };
  const campo = (w = 200): CSSProperties => ({ display: "flex", flexDirection: "column", flex: `1 1 ${w}px`, minWidth: 0 });
  const marcados = new Set(d.periodo_grupos.flat());

  async function salvar() {
    setErro(null);
    const def: Partial<DefinicaoCatalogo> = {
      ...d, nome: d.nome || f.nome, tipo: f.tipo,
      categorias_ref: f.categoriasRef.split(",").map((x) => x.trim()).filter(Boolean),
    };
    setSalvando(true);
    try {
      if (edicao.modo === "novo") {
        if (!/^[a-z0-9_]+$/.test(f.chave)) { setErro("Chave: só letras minúsculas, números e _ (ex.: brucelose_b19)."); return; }
        if (!f.nome.trim()) { setErro("Dê um nome ao item."); return; }
        const r = await criarCatalogoCentral({ chave: f.chave, nome: f.nome.trim(), tipo: f.tipo, padrao_fabrica: f.padrao, uf_sugerida: f.uf || null,
          definicao: def, nota_mudanca: f.nota || null, base_legal: f.base || null });
        onSalvo(`${r.nome} criado no catálogo (v1).`);
      } else {
        const r = await publicarVersaoCatalogo(edicao.item.id, def, f.nota || null, f.base || null);
        onSalvo(`${r.nome}: versão ${r.versao_atual} publicada. As fazendas com cópia recebem o aviso.`);
      }
    } catch (e) {
      setErro(mensagemDoErro(e, "Não foi possível salvar."));
    } finally { setSalvando(false); }
  }

  return (
    <div style={{ background: cor.painelAlt, border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", padding: "1rem", display: "flex", flexDirection: "column", gap: "0.8rem" }}>
      <h3 style={{ margin: 0, fontSize: "0.9rem", color: cor.texto }}>{edicao.modo === "novo" ? "Novo item do catálogo" : `Nova versão de ${edicao.item.nome} (v${edicao.item.versao_atual + 1})`}</h3>
      <div style={linha}>
        {edicao.modo === "novo" && (<>
          <div style={campo(160)}><label style={labelStyle} htmlFor="ctChave">Chave</label><input id="ctChave" style={inputStyle} value={f.chave} onChange={(e) => setF({ ...f, chave: e.target.value.toLowerCase() })} placeholder="brucelose_b19" /></div>
          <div style={campo(220)}><label style={labelStyle} htmlFor="ctNome">Nome</label><input id="ctNome" style={inputStyle} value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} /></div>
          <div style={campo(140)}><label style={labelStyle} htmlFor="ctTipo">Tipo</label>
            <select id="ctTipo" style={inputStyle} value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value as TipoCaixa })}>{TIPOS_CAIXA.map((t) => <option key={t} value={t}>{ROTULO_TIPO[t]}</option>)}</select></div>
          <div style={campo(80)}><label style={labelStyle} htmlFor="ctUf">UF sugerida</label><input id="ctUf" style={inputStyle} value={f.uf} maxLength={2} onChange={(e) => setF({ ...f, uf: e.target.value.toUpperCase() })} /></div>
          <label style={{ ...labelStyle, display: "flex", gap: 6, alignItems: "center" }}><input type="checkbox" checked={f.padrao} onChange={(e) => setF({ ...f, padrao: e.target.checked })} />Padrão de fábrica (vem inativo em toda fazenda nova)</label>
        </>)}
        <div style={campo(160)}><label style={labelStyle} htmlFor="ctCurto">Nome curto</label><input id="ctCurto" style={inputStyle} value={d.nome_curto || ""} onChange={(e) => setD({ nome_curto: e.target.value })} /></div>
      </div>
      {f.tipo !== "exame" && (
        <div style={linha}>
          <div style={campo(110)}><label style={labelStyle} htmlFor="ctDose">Dose</label><input id="ctDose" style={inputStyle} type="number" step="0.1" value={d.dose_valor ?? ""} onChange={(e) => setD({ dose_valor: numOuNulo(e.target.value) })} /></div>
          <div style={campo(140)}><label style={labelStyle} htmlFor="ctUn">Unidade</label>
            <select id="ctUn" style={inputStyle} value={d.dose_unidade || ""} onChange={(e) => setD({ dose_unidade: (e.target.value || null) as DefinicaoCatalogo["dose_unidade"] })}>
              <option value="">—</option>{DOSE_UNIDADES.map((u) => <option key={u} value={u}>{ROTULO_UNIDADE[u]}</option>)}</select></div>
          <div style={campo(110)}><label style={labelStyle} htmlFor="ctCL">Carência leite (d)</label><input id="ctCL" style={inputStyle} type="number" min={0} value={d.car_leite_dias ?? ""} onChange={(e) => setD({ car_leite_dias: intOuNulo(e.target.value) })} /></div>
          <div style={campo(110)}><label style={labelStyle} htmlFor="ctCC">Carência carne (d)</label><input id="ctCC" style={inputStyle} type="number" min={0} value={d.car_carne_dias ?? ""} onChange={(e) => setD({ car_carne_dias: intOuNulo(e.target.value) })} /></div>
          <div style={campo(170)}><label style={labelStyle} htmlFor="ctCM">Leite na carência</label>
            <select id="ctCM" style={inputStyle} value={d.car_modo_leite || ""} onChange={(e) => setD({ car_modo_leite: (e.target.value || null) as DefinicaoCatalogo["car_modo_leite"] })}>
              <option value="">Não definido</option>{MODOS_LEITE.map((m) => <option key={m} value={m}>{ROTULO_MODO_LEITE[m]}</option>)}</select></div>
        </div>
      )}
      <div style={linha}>
        <div style={campo(120)}><label style={labelStyle} htmlFor="ctSexo">Sexo</label>
          <select id="ctSexo" style={inputStyle} value={d.pub_sexo} onChange={(e) => setD({ pub_sexo: e.target.value as DefinicaoCatalogo["pub_sexo"] })}>
            <option value="F">Fêmeas</option><option value="M">Machos</option><option value="ambos">Ambos</option></select></div>
        <div style={campo(240)}><label style={labelStyle} htmlFor="ctCat">Categorias (trechos do nome, separados por vírgula)</label>
          <input id="ctCat" style={inputStyle} value={f.categoriasRef} onChange={(e) => setF({ ...f, categoriasRef: e.target.value })} placeholder="ex.: bezerr" /></div>
        <div style={campo(140)}><label style={labelStyle} htmlFor="ctCatM">As categorias</label>
          <select id="ctCatM" style={inputStyle} value={d.pub_cat_modo} onChange={(e) => setD({ pub_cat_modo: e.target.value as DefinicaoCatalogo["pub_cat_modo"] })}>
            <option value="incluir">entram</option><option value="excluir">ficam de fora</option></select></div>
        <div style={campo(110)}><label style={labelStyle} htmlFor="ctImin">Idade mín. (d)</label><input id="ctImin" style={inputStyle} type="number" min={0} value={d.pub_idade_min_dias ?? ""} onChange={(e) => setD({ pub_idade_min_dias: intOuNulo(e.target.value) })} /></div>
        <div style={campo(110)}><label style={labelStyle} htmlFor="ctImax">Idade máx. (d)</label><input id="ctImax" style={inputStyle} type="number" min={0} value={d.pub_idade_max_dias ?? ""} onChange={(e) => setD({ pub_idade_max_dias: intOuNulo(e.target.value) })} /></div>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.6rem" }}>
        {CONDICOES.map((c) => (
          <label key={c} style={{ ...labelStyle, display: "flex", gap: 6, alignItems: "center", marginBottom: 0 }}>
            <input type="checkbox" checked={d.pub_condicoes.includes(c)} onChange={() => setD({ pub_condicoes: d.pub_condicoes.includes(c) ? d.pub_condicoes.filter((x) => x !== c) : [...d.pub_condicoes, c] })} />{ROTULO_CONDICAO[c]}
          </label>
        ))}
      </div>
      <div style={linha}>
        <label style={{ ...labelStyle, display: "flex", gap: 6, alignItems: "center" }}><input type="checkbox" checked={d.jan_usa_evento} onChange={(e) => setD({ jan_usa_evento: e.target.checked, evento_tipo: d.evento_tipo || "idade" })} />Janela por evento de vida</label>
        {d.jan_usa_evento && (<>
          <div style={campo(200)}><label style={labelStyle} htmlFor="ctEv">Evento</label>
            <select id="ctEv" style={inputStyle} value={d.evento_tipo || "idade"} onChange={(e) => setD({ evento_tipo: e.target.value as DefinicaoCatalogo["evento_tipo"] })}>{EVENTO_TIPOS.map((t) => <option key={t} value={t}>{ROTULO_EVENTO[t]}</option>)}</select></div>
          <div style={campo(90)}><label style={labelStyle} htmlFor="ctDe">De (d)</label><input id="ctDe" style={inputStyle} type="number" value={d.evento_de_dias ?? ""} onChange={(e) => setD({ evento_de_dias: intOuNulo(e.target.value) })} /></div>
          <div style={campo(90)}><label style={labelStyle} htmlFor="ctAte">Até (d)</label><input id="ctAte" style={inputStyle} type="number" value={d.evento_ate_dias ?? ""} onChange={(e) => setD({ evento_ate_dias: intOuNulo(e.target.value) })} /></div>
        </>)}
      </div>
      <div style={linha}>
        <label style={{ ...labelStyle, display: "flex", gap: 6, alignItems: "center" }}><input type="checkbox" checked={d.jan_usa_periodo} onChange={(e) => setD({ jan_usa_periodo: e.target.checked, periodo_modo: d.periodo_modo || "meses" })} />Janela por período do ano</label>
        {d.jan_usa_periodo && (<>
          <div style={campo(150)}><label style={labelStyle} htmlFor="ctPm">Período</label>
            <select id="ctPm" style={inputStyle} value={d.periodo_modo || "meses"} onChange={(e) => setD({ periodo_modo: e.target.value as DefinicaoCatalogo["periodo_modo"] })}>
              <option value="meses">Meses do ano</option><option value="frequencia">A cada N anos</option><option value="continuo">Contínuo</option></select></div>
          {d.periodo_modo === "frequencia" && (<>
            <div style={campo(90)}><label style={labelStyle} htmlFor="ctPa">A cada (anos)</label><input id="ctPa" style={inputStyle} type="number" min={1} value={d.periodo_anos ?? ""} onChange={(e) => setD({ periodo_anos: intOuNulo(e.target.value) })} /></div>
            <div style={campo(90)}><label style={labelStyle} htmlFor="ctPb">Ano-base</label><input id="ctPb" style={inputStyle} type="number" value={d.periodo_ano_base ?? ""} onChange={(e) => setD({ periodo_ano_base: intOuNulo(e.target.value) })} /></div>
          </>)}
          {d.periodo_modo !== "continuo" && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }} role="group" aria-label="Meses">
              {MESES_CURTOS.map((m, i) => (
                <button key={m} type="button" aria-pressed={marcados.has(i)} style={{ ...btnGhost, ...(marcados.has(i) ? { background: cor.dourado, color: cor.bg } : {}) }}
                  onClick={() => setD({ periodo_grupos: marcados.has(i) ? d.periodo_grupos.map((g) => g.filter((x) => x !== i)).filter((g) => g.length) : [...d.periodo_grupos, [i]].sort((a, b) => a[0] - b[0]) })}>{m}</button>
              ))}
            </div>
          )}
        </>)}
      </div>
      <div style={linha}>
        <div style={campo(110)}><label style={labelStyle} htmlFor="ctMin">Mínimo para avisar</label><input id="ctMin" style={inputStyle} type="number" min={1} value={d.aglo_min} onChange={(e) => setD({ aglo_min: intOuNulo(e.target.value) ?? 1 })} /></div>
        <div style={campo(110)}><label style={labelStyle} htmlFor="ctAnt">Antecedência (d)</label><input id="ctAnt" style={inputStyle} type="number" min={0} value={d.aviso_antecedencia_dias} onChange={(e) => setD({ aviso_antecedencia_dias: intOuNulo(e.target.value) ?? 0 })} /></div>
        <label style={{ ...labelStyle, display: "flex", gap: 6, alignItems: "center" }}><input type="checkbox" checked={d.legal_crmv_pedir} onChange={(e) => setD({ legal_crmv_pedir: e.target.checked })} />Pedir CRMV</label>
        <label style={{ ...labelStyle, display: "flex", gap: 6, alignItems: "center" }}><input type="checkbox" checked={d.legal_reagente_aviso} onChange={(e) => setD({ legal_reagente_aviso: e.target.checked })} />Aviso de reagente</label>
        <label style={{ ...labelStyle, display: "flex", gap: 6, alignItems: "center" }}><input type="checkbox" checked={!!d.legal_atestado} onChange={(e) => setD({ legal_atestado: e.target.checked ? { destinatario_tipo: "orgao", quando: "primeiro", dias: 30 } : null })} />Atestado</label>
        {d.legal_atestado && (<>
          <div style={campo(180)}><label style={labelStyle} htmlFor="ctAtD">Destinatário do atestado</label><input id="ctAtD" style={inputStyle} value={d.legal_atestado.destinatario_texto || ""} onChange={(e) => setD({ legal_atestado: { ...d.legal_atestado, destinatario_texto: e.target.value || null } })} /></div>
          <div style={campo(80)}><label style={labelStyle} htmlFor="ctAtN">Em (dias)</label><input id="ctAtN" style={inputStyle} type="number" min={0} value={d.legal_atestado.dias ?? 30} onChange={(e) => setD({ legal_atestado: { ...d.legal_atestado, dias: intOuNulo(e.target.value) ?? 0 } })} /></div>
        </>)}
        <label style={{ ...labelStyle, display: "flex", gap: 6, alignItems: "center" }}><input type="checkbox" checked={!!d.legal_comprovacao} onChange={(e) => setD({ legal_comprovacao: e.target.checked ? { dias: 180, aviso_dias: 30, push: true, email: false } : null })} />Comprovação periódica</label>
        {d.legal_comprovacao && <div style={campo(90)}><label style={labelStyle} htmlFor="ctCpD">A cada (dias)</label><input id="ctCpD" style={inputStyle} type="number" min={1} value={d.legal_comprovacao.dias ?? 180} onChange={(e) => setD({ legal_comprovacao: { ...d.legal_comprovacao, dias: intOuNulo(e.target.value) ?? 1 } })} /></div>}
        <div style={campo(200)}><label style={labelStyle} htmlFor="ctMk">Lembrete de marcação</label><input id="ctMk" style={inputStyle} value={d.legal_marca_texto || ""} onChange={(e) => setD({ legal_marca_texto: e.target.value || null })} /></div>
      </div>
      <div style={linha}>
        <div style={campo(260)}><label style={labelStyle} htmlFor="ctNota">O que mudou (aparece para as fazendas)</label><input id="ctNota" style={inputStyle} value={f.nota} onChange={(e) => setF({ ...f, nota: e.target.value })} /></div>
        <div style={campo(220)}><label style={labelStyle} htmlFor="ctBase">Base legal</label><input id="ctBase" style={inputStyle} value={f.base} onChange={(e) => setF({ ...f, base: e.target.value })} placeholder="ex.: IN Agrodefesa 2/2025" /></div>
      </div>
      <p style={{ margin: 0, fontSize: "0.75rem", color: cor.mudo }}>Janela: {textoJanela(d)}. Os demais campos da definição seguem como estão.</p>
      {erro && <p role="alert" style={{ margin: 0, color: cor.vermelho, fontSize: "0.8rem" }}>{erro}</p>}
      <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
        <button type="button" style={btnGhost} onClick={onFechar}>Cancelar</button>
        <button type="button" style={btnPrimario} disabled={salvando} onClick={salvar}>{salvando ? "Publicando…" : edicao.modo === "novo" ? "Criar item" : "Publicar versão"}</button>
      </div>
    </div>
  );
}

function Versoes({ id }: { id: number }) {
  const { cor } = usePainelCowDataEstilos();
  const { dados, erro } = useCarregar(() => obterCatalogoCentral(id), [id]);
  if (erro) return <p style={{ color: cor.vermelho, fontSize: "0.78rem", margin: 0 }}>{erro}</p>;
  if (!dados) return <p style={{ color: cor.mudo, fontSize: "0.78rem", margin: 0 }}>Carregando versões…</p>;
  return (
    <ul style={{ margin: 0, paddingLeft: "1.1rem", fontSize: "0.78rem", color: cor.texto }}>
      {(dados.versoes || []).slice().reverse().map((v) => <li key={v.id}>v{v.versao} · {fmtDataHora(v.publicado_em)} · {v.nota_mudanca || "sem nota"}{v.base_legal ? ` · ${v.base_legal}` : ""}</li>)}
    </ul>
  );
}

export default function CatalogoSanitario() {
  const { cor, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const { dados, erro, recarregar } = useCarregar(() => listarCatalogoCentral(), []);
  const [edicao, setEdicao] = useState<Edicao | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [aberto, setAberto] = useState<number | null>(null);
  const [ocupado, setOcupado] = useState<number | null>(null);
  const th: CSSProperties = { textAlign: "left", padding: "0.45rem 0.6rem", fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.08em", color: cor.mudo, borderBottom: `1px solid ${cor.borda}` };
  const td: CSSProperties = { padding: "0.5rem 0.6rem", fontSize: "0.8rem", color: cor.texto, borderBottom: `1px solid ${cor.borda}`, verticalAlign: "top" };

  async function alternar(item: CatalogoCentralItem, campo: "ativo" | "padrao_fabrica") {
    setOcupado(item.id); setAviso(null);
    try { await editarCatalogoCentral(item.id, { [campo]: !item[campo] }); recarregar(); }
    catch (e) { setAviso(mensagemDoErro(e)); } finally { setOcupado(null); }
  }

  return (
    <section style={{ background: cor.painel, border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", padding: "1rem", display: "flex", flexDirection: "column", gap: "0.8rem" }} aria-labelledby="catSanTit">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
        <div>
          <h2 id="catSanTit" style={{ margin: 0, fontSize: "0.8rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: cor.texto, display: "flex", gap: 6, alignItems: "center" }}>
            <BookOpen size={14} aria-hidden="true" />Catálogo sanitário
          </h2>
          <p style={{ margin: "0.2rem 0 0", fontSize: "0.78rem", color: cor.mudo, maxWidth: "75ch" }}>Itens prontos e versionados de vacinas e exames. Cada fazenda ativa (copia) o que quiser. Publicar versão nova não muda a cópia da fazenda: ela recebe o aviso e decide atualizar.</p>
        </div>
        {!edicao && <button type="button" style={btnPrimario} onClick={() => setEdicao({ modo: "novo" })}><Plus size={14} aria-hidden="true" />Novo item</button>}
      </div>
      {aviso && <p role="status" style={{ margin: 0, fontSize: "0.8rem", color: cor.verde }}>{aviso}</p>}
      {edicao && <Editor edicao={edicao} onFechar={() => setEdicao(null)} onSalvo={(msg) => { setEdicao(null); setAviso(msg); recarregar(); }} />}
      {erro ? <p role="alert" style={{ margin: 0, color: cor.vermelho, fontSize: "0.8rem" }}>{erro} <button type="button" style={btnGhost} onClick={recarregar}>Tentar de novo</button></p>
        : !dados ? <p style={{ margin: 0, color: cor.mudo, fontSize: "0.8rem" }}>Carregando o catálogo…</p>
          : dados.length ? (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead><tr><th style={th}>Item</th><th style={th}>Versão</th><th style={th}>O que mudou</th><th style={th}>Fazendas</th><th style={th}>Situação</th><th style={th}><span className="san-sr">Ações</span></th></tr></thead>
                <tbody>{dados.map((c) => (
                  <tr key={c.id}>
                    <td style={td}><b>{c.nome}</b><div style={{ color: cor.mudo, fontSize: "0.72rem" }}>{ROTULO_TIPO[c.tipo] || c.tipo} · {c.chave}{c.uf_sugerida ? ` · ${c.uf_sugerida}` : ""}</div>
                      {aberto === c.id && <div style={{ marginTop: 6 }}><Versoes id={c.id} /></div>}</td>
                    <td style={td}>v{c.versao_atual}</td>
                    <td style={{ ...td, minWidth: 220 }}>{c.nota_mudanca || "—"}{c.base_legal ? <div style={{ color: cor.mudo, fontSize: "0.72rem" }}>{c.base_legal}</div> : null}</td>
                    <td style={td}>{c.fazendas_com_copia} com cópia{c.copias_desatualizadas ? <div style={{ color: cor.dourado, fontSize: "0.72rem" }}>{c.copias_desatualizadas} em versão antiga</div> : null}</td>
                    <td style={td}>
                      <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: "0.75rem" }}><input type="checkbox" checked={c.ativo} disabled={ocupado === c.id} onChange={() => alternar(c, "ativo")} />Disponível</label>
                      <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: "0.75rem" }}><input type="checkbox" checked={c.padrao_fabrica} disabled={ocupado === c.id} onChange={() => alternar(c, "padrao_fabrica")} />Padrão de fábrica</label>
                    </td>
                    <td style={td}>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <button type="button" style={btnGhost} onClick={() => setEdicao({ modo: "versao", item: c })}>Nova versão</button>
                        <button type="button" style={btnGhost} aria-expanded={aberto === c.id} onClick={() => setAberto(aberto === c.id ? null : c.id)}>{aberto === c.id ? "Esconder versões" : "Versões"}</button>
                      </div>
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          ) : <p style={{ margin: 0, color: cor.mudo, fontSize: "0.8rem" }}>O catálogo ainda não tem itens. Crie o primeiro.</p>}
    </section>
  );
}
