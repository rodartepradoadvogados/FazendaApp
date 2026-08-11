"use client";
// Aba "Biblioteca de referência" — biblioteca padrão CowData (composição
// bromatológica de referência) + os alimentos próprios de cada fazenda,
// editável por ela (copy-on-write no backend: editar um item CowData nunca
// altera o padrão nem afeta as outras fazendas — ver
// backend/fazenda/rules/biblioteca_alimentos.py). CRUD completo, vínculo com
// produto do estoque (reaproveita o EstoquePicker já usado no resto do
// site), importação/exportação de planilha em lote e o mini manual da
// importação.
import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, ChevronDown, ChevronUp, Download, HelpCircle, Pencil, Plus, RotateCcw, Search, Trash2, Upload, X,
} from "lucide-react";
import { fetchEstoque } from "@/lib/api";
import { EstoquePicker, type EstoqueItemPicker } from "@/components/EstoquePicker";
import {
  AlimentoCadastradoResumo, AlimentoNutricionalPayload, CATEGORIAS_NASEM, CampoNutricional, CategoriaNasem,
  EntradaBiblioteca, GRUPOS_CAMPOS_NUTRICIONAIS, ROTULOS_CAMPOS_NUTRICIONAIS,
  atualizarAlimentoNaBiblioteca, baixarModeloBibliotecaAlimentos, excluirAlimentoDaBiblioteca,
  importarBibliotecaAlimentos, listarAlimentos, salvarAlimentoNaBiblioteca,
} from "@/lib/dietas";

function fmt(v: number | null | undefined, casas = 1): string {
  return v == null || Number.isNaN(v) ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

function formularioVazio(): AlimentoNutricionalPayload {
  return {
    alimento_id: null, nome: "", categoria_nasem: "Outros", conc_pct: 0, fonte: "", observacao: "",
    inclusao_min_pct: null, inclusao_max_pct: null, valores: {},
  };
}

function formularioDeEntrada(e: EntradaBiblioteca): AlimentoNutricionalPayload {
  return {
    alimento_id: e.alimento_id, nome: e.nome, categoria_nasem: e.categoria_nasem as CategoriaNasem, conc_pct: e.conc_pct,
    fonte: e.fonte || "", observacao: e.observacao || "", inclusao_min_pct: e.inclusao_min_pct, inclusao_max_pct: e.inclusao_max_pct,
    valores: { ...e.valores },
  };
}

export function BibliotecaAlimentos() {
  const [lista, setLista] = useState<EntradaBiblioteca[] | null>(null);
  const [cadastrados, setCadastrados] = useState<AlimentoCadastradoResumo[]>([]);
  const [estoque, setEstoque] = useState<EstoqueItemPicker[]>([]);
  const [busca, setBusca] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [editando, setEditando] = useState<EntradaBiblioteca | "novo" | null>(null);
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [importando, setImportando] = useState(false);
  const [resultadoImportacao, setResultadoImportacao] = useState<{ criados: number; atualizados: number; avisos: string[]; erros: string[] } | null>(null);
  const [manualAberto, setManualAberto] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function carregar() {
    setErro(null);
    listarAlimentos(busca)
      .then((r) => { setLista(r.biblioteca); setCadastrados(r.cadastrados); })
      .catch((e) => setErro(e.message));
  }

  useEffect(() => {
    const t = setTimeout(carregar, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busca]);

  useEffect(() => { fetchEstoque().then((d) => setEstoque(d.itens || [])).catch(() => {}); }, []);

  // Um "produto" pra vincular é um Alimento cadastrado (Configurações >
  // Cadastro > Alimentação > Alimentos) — reaproveita o EstoquePicker
  // apontado pra essa lista (em vez da lista de Estoque) porque é o Alimento,
  // não o item de Estoque em si, que AlimentoNutricional.alimento_id
  // referencia (um Alimento pode ter mais de um item de Estoque vinculado,
  // ver docstring de `Alimento`). A coluna "Estoque atual" do seletor mostra
  // a soma da quantidade dos itens de Estoque vinculados a cada Alimento —
  // é isso que dá "preço e disponibilidade" pra formulação puxar depois.
  const opcoesProduto: (EstoqueItemPicker & { id: number })[] = useMemo(() => {
    return cadastrados.map((a) => {
      const vinculados = estoque.filter((e: any) => e.alimento_id === a.id);
      const quantidade = vinculados.reduce((s, e) => s + (Number(e.quantidade) || 0), 0);
      const comPreco = vinculados.find((e: any) => e.valor_unitario != null) as any;
      return {
        id: a.id, nome: a.nome, alimento_id: a.id, quantidade: vinculados.length ? quantidade : null,
        unidade: vinculados[0]?.unidade || undefined,
        categoria: comPreco ? `R$ ${Number(comPreco.valor_unitario).toFixed(2)}/${vinculados[0]?.unidade || "kg"}` : (vinculados.length ? "sem preço cadastrado" : "sem item de estoque vinculado"),
      };
    });
  }, [cadastrados, estoque]);

  async function onSalvarModal(dados: AlimentoNutricionalPayload, id: number | null) {
    if (id == null) await salvarAlimentoNaBiblioteca(dados);
    else await atualizarAlimentoNaBiblioteca(id, dados);
    setEditando(null);
    carregar();
  }

  async function onExcluir(item: EntradaBiblioteca) {
    const pergunta = item.eh_copia_editada
      ? `Restaurar "${item.nome}" ao padrão CowData? Suas edições neste item se perdem, mas ele volta a aparecer com os valores padrão.`
      : item.eh_mestre
        ? `Remover "${item.nome}" da sua biblioteca? Ele continua disponível para as outras fazendas — você pode trazê-lo de volta depois.`
        : `Excluir "${item.nome}" da sua biblioteca? Esta ação não pode ser desfeita.`;
    if (!confirm(pergunta)) return;
    setOcupado(item.id);
    try {
      const r = await excluirAlimentoDaBiblioteca(item.id);
      carregar();
      // feedback rápido sem travar a tela com mais um modal
      setResultadoImportacao(null);
      setErro(null);
      alert(r.mensagem);
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setOcupado(null);
    }
  }

  async function onImportar(file: File) {
    setImportando(true);
    setErro(null);
    setResultadoImportacao(null);
    try {
      const r = await importarBibliotecaAlimentos(file);
      setResultadoImportacao(r);
      carregar();
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setImportando(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "0.8rem", marginBottom: "1rem" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "1.3rem", fontWeight: 800, color: "var(--text)" }}>Biblioteca de referência</h1>
          <p style={{ margin: "0.2rem 0 0", fontSize: "0.85rem", color: "var(--text-muted)", maxWidth: "48rem" }}>
            Composição bromatológica padrão CowData, editável pela fazenda — os itens marcados <BadgeCowData /> vêm prontos e podem ser
            ajustados sem afetar as outras fazendas; edite um deles e ele vira uma cópia sua. Alimenta a Etapa 1 (grade de alimentos) da
            Formulação de Dietas.
          </p>
        </div>
        <button type="button" className="btn-primary-gold" onClick={() => setEditando("novo")}>
          <Plus size={16} /> Adicionar alimento
        </button>
      </div>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <button type="button" onClick={() => setManualAberto((v) => !v)}
          style={{ display: "flex", alignItems: "center", gap: "0.5rem", background: "none", border: "none", padding: 0, cursor: "pointer", color: "var(--text)", fontWeight: 700, fontSize: "0.88rem" }}>
          <HelpCircle size={16} /> Como importar sua própria planilha (mini manual)
          {manualAberto ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
        {manualAberto && <ManualDeImportacao />}
      </div>

      <div className="card" style={{ marginBottom: "1rem", display: "flex", flexWrap: "wrap", gap: "0.6rem", alignItems: "center" }}>
        <div style={{ position: "relative", flex: "1 1 16rem", minWidth: "14rem" }}>
          <Search size={14} style={{ position: "absolute", left: "0.6rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
          <input
            value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar alimento…"
            style={{ width: "100%", padding: "0.45rem 0.6rem 0.45rem 2rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }}
          />
        </div>
        <button type="button" className="btn-ghost" onClick={() => baixarModeloBibliotecaAlimentos().catch((e) => setErro(e.message))}>
          <Download size={14} /> Baixar modelo (.xlsx)
        </button>
        <button type="button" className="btn-ghost" disabled={importando} onClick={() => fileRef.current?.click()}>
          <Upload size={14} /> {importando ? "Importando…" : "Importar planilha"}
        </button>
        <input ref={fileRef} type="file" accept=".xlsx,.xlsm,.csv" style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onImportar(f); }} />
      </div>

      {erro && <div className="alert-critico" style={{ marginBottom: "1rem" }}>{erro}</div>}

      {resultadoImportacao && (
        <div className="card" style={{ marginBottom: "1rem" }}>
          <p style={{ margin: "0 0 0.4rem", fontSize: "0.85rem", color: "var(--text)" }}>
            Importação concluída: <strong>{resultadoImportacao.criados}</strong> alimento(s) novo(s), <strong>{resultadoImportacao.atualizados}</strong> atualizado(s).
          </p>
          {resultadoImportacao.erros.length > 0 && (
            <div style={{ marginBottom: "0.4rem" }}>
              {resultadoImportacao.erros.map((e, i) => <p key={i} style={{ margin: "0.15rem 0", fontSize: "0.78rem", color: "var(--red)" }}>{e}</p>)}
            </div>
          )}
          {resultadoImportacao.avisos.length > 0 && (
            <details>
              <summary style={{ cursor: "pointer", fontSize: "0.8rem", color: "var(--amber)" }}>{resultadoImportacao.avisos.length} aviso(s) — clique para ver</summary>
              {resultadoImportacao.avisos.map((a, i) => <p key={i} style={{ margin: "0.15rem 0", fontSize: "0.76rem", color: "var(--text-muted)" }}>{a}</p>)}
            </details>
          )}
        </div>
      )}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="fazenda-table">
          <thead>
            <tr>
              <th>Alimento</th><th>Categoria</th><th>MS %</th><th>PB %</th><th>Custo (R$/kg MN)</th>
              <th>Inclusão sugerida</th><th>Produto vinculado</th><th></th>
            </tr>
          </thead>
          <tbody>
            {lista === null && <tr><td colSpan={8} style={{ textAlign: "center", color: "var(--text-muted)" }}>Carregando…</td></tr>}
            {lista !== null && lista.length === 0 && (
              <tr><td colSpan={8}><div className="empty-state">Nenhum alimento encontrado.</div></td></tr>
            )}
            {lista?.map((item) => {
              const produto = cadastrados.find((a) => a.id === item.alimento_id);
              return (
                <tr key={item.id}>
                  <td style={{ fontWeight: 600 }}>
                    {item.nome} {item.eh_mestre && <BadgeCowData />} {item.eh_copia_editada && <BadgeEditado />}
                  </td>
                  <td style={{ fontSize: "0.78rem" }}>{item.categoria_nasem}</td>
                  <td>{fmt(item.valores.ms_pct)}</td>
                  <td>{fmt(item.valores.pb_pct)}</td>
                  <td>{fmt(item.valores.custo_kg_mn, 2)}</td>
                  <td style={{ fontSize: "0.78rem" }}>
                    {item.inclusao_min_pct != null || item.inclusao_max_pct != null
                      ? `${item.inclusao_min_pct ?? "?"}–${item.inclusao_max_pct ?? "?"}%`
                      : "—"}
                  </td>
                  <td style={{ fontSize: "0.78rem" }}>
                    {produto ? produto.nome : <span style={{ color: "var(--text-muted)" }}>não vinculado</span>}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: "0.25rem", justifyContent: "flex-end" }}>
                      <button type="button" title="Editar" className="btn-ghost" style={{ padding: "0.25rem 0.4rem" }} onClick={() => setEditando(item)}>
                        <Pencil size={13} />
                      </button>
                      <button
                        type="button" title={item.eh_copia_editada ? "Restaurar padrão CowData" : "Excluir"} disabled={ocupado === item.id}
                        className="btn-ghost" style={{ padding: "0.25rem 0.4rem", color: item.eh_copia_editada ? "var(--gold-deep)" : "var(--red)" }}
                        onClick={() => onExcluir(item)}
                      >
                        {item.eh_copia_editada ? <RotateCcw size={13} /> : <Trash2 size={13} />}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {editando !== null && (
        <ModalAlimento
          inicial={editando === "novo" ? formularioVazio() : formularioDeEntrada(editando)}
          idExistente={editando === "novo" ? null : editando.id}
          ehMestre={editando !== "novo" && editando.eh_mestre}
          opcoesProduto={opcoesProduto}
          onFechar={() => setEditando(null)}
          onSalvar={onSalvarModal}
        />
      )}
    </div>
  );
}

function BadgeCowData() {
  return (
    <span style={{ display: "inline-block", marginLeft: "0.35rem", padding: "0.05rem 0.4rem", borderRadius: "999px", background: "color-mix(in srgb, var(--gold-deep) 16%, transparent)", color: "var(--gold-deep)", fontSize: "0.62rem", fontWeight: 700, verticalAlign: "middle" }}>
      CowData
    </span>
  );
}
function BadgeEditado() {
  return (
    <span style={{ display: "inline-block", marginLeft: "0.35rem", padding: "0.05rem 0.4rem", borderRadius: "999px", background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text-muted)", fontSize: "0.62rem", fontWeight: 700, verticalAlign: "middle" }}>
      editado
    </span>
  );
}

function ManualDeImportacao() {
  const th: React.CSSProperties = { textAlign: "left", padding: "0.3rem 0.5rem", fontSize: "0.72rem", color: "var(--text-muted)", borderBottom: "1px solid var(--border)" };
  const td: React.CSSProperties = { padding: "0.3rem 0.5rem", fontSize: "0.78rem", borderBottom: "1px solid var(--border)" };
  return (
    <div style={{ marginTop: "0.8rem", fontSize: "0.85rem", color: "var(--text)", lineHeight: 1.55 }}>
      <p>
        O jeito mais simples de carregar vários alimentos de uma vez é baixar o modelo do sistema (botão "Baixar modelo"), preencher por
        cima da linha de exemplo e reimportar. Se preferir usar uma planilha própria (do seu laboratório, de outro sistema, etc.), o
        sistema aceita — desde que ela siga estas regras:
      </p>
      <ul style={{ margin: "0.5rem 0", paddingLeft: "1.2rem" }}>
        <li><strong>Só duas colunas são obrigatórias</strong>: o nome do alimento e a categoria. Sem elas, a linha inteira é ignorada (aparece na lista de erros depois de importar).</li>
        <li>
          <strong>O sistema reconhece nomes de coluna parecidos, não só os do modelo</strong> — por exemplo, uma coluna chamada "MS", "% MS" ou
          "Matéria seca" é lida do mesmo jeito. Maiúscula/minúscula e acento não fazem diferença. Se uma coluna não for reconhecida, ela
          simplesmente não entra (não trava a importação).
        </li>
        <li>
          <strong>Cada coluna espera uma unidade específica</strong> — ver tabela abaixo. Os valores bromatológicos são sempre <strong>% da matéria
          seca (MS)</strong>, exceto o próprio teor de MS, que é <strong>% da matéria natural</strong> (o alimento "como ele está", com a água).
        </li>
        <li>
          <strong>Coluna que falta na planilha</strong>: o campo correspondente fica em branco no alimento importado — na hora de calcular
          uma dieta, o sistema completa automaticamente com um valor padrão da categoria (ex.: "Forragem", "Concentrado proteico"), do
          mesmo jeito que faz para qualquer alimento cadastrado sem laudo completo.
        </li>
        <li>
          <strong>Valor fora da faixa esperada</strong> (ex.: MS acima de 100%, um percentual negativo): aquele valor específico é
          ignorado — a linha continua sendo importada com o restante dos dados, só aquele campo fica em branco (e completado pelo padrão
          da categoria), e um aviso aponta exatamente qual célula foi descartada e por quê.
        </li>
        <li>
          <strong>Categoria não reconhecida</strong>: o alimento entra classificado como "Outros" (categoria genérica), com um aviso — nunca
          trava a importação.
        </li>
        <li>Um alimento com o mesmo nome de um item já existente na SUA biblioteca é atualizado, não duplicado. Se o nome bater com um item padrão CowData que você ainda não editou, ele vira automaticamente sua cópia editável (mesma regra de quando você edita pela tela).</li>
        <li>Formatos aceitos: <strong>.xlsx</strong> (Excel) e <strong>.csv</strong>. Limite de 500 linhas por arquivo.</li>
      </ul>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "0.4rem" }}>
          <thead><tr><th style={th}>Coluna</th><th style={th}>Obrigatória?</th><th style={th}>Unidade esperada</th></tr></thead>
          <tbody>
            <tr><td style={td}>Nome do alimento</td><td style={td}>Sim</td><td style={td}>texto livre</td></tr>
            <tr><td style={td}>Categoria NASEM</td><td style={td}>Sim (senão vira "Outros")</td><td style={td}>uma das 11 categorias do sistema (ex.: Forragem, Concentrado proteico)</td></tr>
            <tr><td style={td}>MS — matéria seca</td><td style={td}>Não</td><td style={td}>% da matéria NATURAL</td></tr>
            <tr><td style={td}>PB, FDN, FDA, Lignina, Amido, Açúcares, EE, Cinzas</td><td style={td}>Não</td><td style={td}>% da matéria seca (MS)</td></tr>
            <tr><td style={td}>Ca, P, Mg, K, Na, Cl, S (minerais)</td><td style={td}>Não</td><td style={td}>% da matéria seca (MS)</td></tr>
            <tr><td style={td}>Concentrado</td><td style={td}>Não</td><td style={td}>% da MS do próprio alimento (0 = volumoso puro, 100 = concentrado puro)</td></tr>
            <tr><td style={td}>Custo</td><td style={td}>Não</td><td style={td}>R$ por kg de matéria natural</td></tr>
            <tr><td style={td}>Inclusão mínima/máxima sugerida</td><td style={td}>Não</td><td style={td}>% da MS TOTAL da dieta (não do alimento) — só orientação, não entra no cálculo</td></tr>
            <tr><td style={td}>Fonte/observação</td><td style={td}>Não</td><td style={td}>texto livre</td></tr>
          </tbody>
        </table>
      </div>
      <p style={{ marginTop: "0.6rem", fontSize: "0.76rem", color: "var(--text-muted)" }}>
        Campos mais técnicos (fracionamento da proteína em frações A/B/C, digestibilidades de referência, coeficientes de absorção de
        mineral) não entram na planilha — eles continuam sendo completados pelo padrão da categoria, e podem ser digitados na tela de
        edição de cada alimento se você tiver o laudo completo.
      </p>
    </div>
  );
}

function ModalAlimento({
  inicial, idExistente, ehMestre, opcoesProduto, onFechar, onSalvar,
}: {
  inicial: AlimentoNutricionalPayload; idExistente: number | null; ehMestre: boolean;
  opcoesProduto: (EstoqueItemPicker & { id: number })[];
  onFechar: () => void; onSalvar: (dados: AlimentoNutricionalPayload, id: number | null) => Promise<void>;
}) {
  const [form, setForm] = useState<AlimentoNutricionalPayload>(inicial);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const produtoVinculadoNome = opcoesProduto.find((p) => p.alimento_id === form.alimento_id)?.nome || "";

  function atualizarCampo(campo: CampoNutricional, valorTexto: string) {
    setForm((f) => ({ ...f, valores: { ...f.valores, [campo]: valorTexto === "" ? null : Number(valorTexto) } }));
  }

  async function salvar() {
    if (!form.nome.trim()) { setErro("Informe o nome do alimento."); return; }
    setSalvando(true);
    setErro(null);
    try {
      await onSalvar(form, idExistente);
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--overlay)" }} onClick={onFechar}>
      <div onClick={(e) => e.stopPropagation()} className="card" style={{ width: "min(44rem, 94vw)", maxHeight: "88vh", display: "flex", flexDirection: "column" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.8rem" }}>
          <h3 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 700, color: "var(--text)" }}>
            {idExistente == null ? "Adicionar alimento" : "Editar alimento"}
          </h3>
          <button type="button" className="btn-ghost" onClick={onFechar}><X size={16} /></button>
        </div>

        {ehMestre && (
          <div className="alert-critico" style={{ marginBottom: "0.8rem", background: "color-mix(in srgb, var(--gold-deep) 12%, transparent)", borderColor: "var(--gold-deep)", color: "var(--text)" }}>
            <AlertTriangle size={15} style={{ flexShrink: 0 }} />
            Este é um item padrão CowData. Salvar cria uma cópia só para a sua fazenda — o padrão continua igual para todo mundo.
          </div>
        )}

        <div style={{ overflowY: "auto", flex: 1, paddingRight: "0.3rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "0.6rem", marginBottom: "0.6rem" }}>
            <label style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
              Nome
              <input value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })}
                style={{ width: "100%", marginTop: "0.15rem", padding: "0.4rem 0.55rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }} />
            </label>
            <label style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
              Categoria NASEM
              <select value={form.categoria_nasem} onChange={(e) => setForm({ ...form, categoria_nasem: e.target.value as CategoriaNasem })}
                style={{ width: "100%", marginTop: "0.15rem", padding: "0.4rem 0.55rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }}>
                {CATEGORIAS_NASEM.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.6rem", marginBottom: "0.6rem" }}>
            <label style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
              Concentrado (% da MS do alimento)
              <input type="number" step="1" min={0} max={100} value={form.conc_pct} onChange={(e) => setForm({ ...form, conc_pct: Number(e.target.value) })}
                style={{ width: "100%", marginTop: "0.15rem", padding: "0.4rem 0.55rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }} />
            </label>
            <label style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
              Inclusão mínima sugerida (% da MS da dieta)
              <input type="number" step="0.5" min={0} max={100} value={form.inclusao_min_pct ?? ""} onChange={(e) => setForm({ ...form, inclusao_min_pct: e.target.value === "" ? null : Number(e.target.value) })}
                style={{ width: "100%", marginTop: "0.15rem", padding: "0.4rem 0.55rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }} />
            </label>
            <label style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
              Inclusão máxima sugerida (% da MS da dieta)
              <input type="number" step="0.5" min={0} max={100} value={form.inclusao_max_pct ?? ""} onChange={(e) => setForm({ ...form, inclusao_max_pct: e.target.value === "" ? null : Number(e.target.value) })}
                style={{ width: "100%", marginTop: "0.15rem", padding: "0.4rem 0.55rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }} />
            </label>
          </div>

          <div style={{ marginBottom: "0.8rem" }}>
            <span style={{ fontSize: "0.76rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>
              Produto vinculado (estoque da fazenda) — de onde a formulação puxa preço e disponibilidade
            </span>
            <EstoquePicker
              itens={opcoesProduto} value={produtoVinculadoNome} incluirNaoEstocaveis todasFinalidades
              placeholder="Nenhum produto vinculado — clique para escolher"
              onChange={(nome) => setForm({ ...form, alimento_id: opcoesProduto.find((p) => p.nome === nome)?.alimento_id ?? null })}
            />
            {form.alimento_id != null && (
              <button type="button" onClick={() => setForm({ ...form, alimento_id: null })} className="btn-ghost" style={{ marginTop: "0.3rem", fontSize: "0.74rem", padding: "0.15rem 0.4rem" }}>
                Remover vínculo
              </button>
            )}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem", marginBottom: "0.8rem" }}>
            <label style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
              Fonte
              <input value={form.fonte || ""} onChange={(e) => setForm({ ...form, fonte: e.target.value })}
                style={{ width: "100%", marginTop: "0.15rem", padding: "0.4rem 0.55rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }} />
            </label>
            <label style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
              Observação
              <input value={form.observacao || ""} onChange={(e) => setForm({ ...form, observacao: e.target.value })}
                style={{ width: "100%", marginTop: "0.15rem", padding: "0.4rem 0.55rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }} />
            </label>
          </div>

          {GRUPOS_CAMPOS_NUTRICIONAIS.map((grupo) => (
            <div key={grupo.titulo} style={{ marginBottom: "0.9rem" }}>
              <h4 style={{ fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--gold-deep)", margin: "0 0 0.4rem" }}>{grupo.titulo}</h4>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem" }}>
                {grupo.campos.map((campo) => (
                  <label key={campo} style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                    {ROTULOS_CAMPOS_NUTRICIONAIS[campo]}
                    <input type="number" step="0.01" value={form.valores[campo] ?? ""} onChange={(e) => atualizarCampo(campo, e.target.value)} placeholder="—"
                      style={{ width: "100%", marginTop: "0.1rem", padding: "0.3rem 0.45rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)", fontSize: "0.78rem" }} />
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>

        {erro && <div className="alert-critico" style={{ marginTop: "0.6rem" }}>{erro}</div>}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginTop: "0.9rem" }}>
          <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
          <button type="button" className="btn-primary-gold" disabled={salvando} onClick={salvar}>
            {salvando ? "Salvando…" : "Salvar"}
          </button>
        </div>
      </div>
    </div>
  );
}
