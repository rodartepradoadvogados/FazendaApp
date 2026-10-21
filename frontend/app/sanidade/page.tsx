"use client";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Syringe, AlertTriangle, Filter, Search, CalendarClock, ClipboardList, Pencil, Trash2, Check, X, Shield, HeartPulse, Activity, ChevronDown, ChevronRight, ListChecks, Percent, Route, History, FlaskConical, BookOpen, LayoutDashboard } from "lucide-react";
import {
  fetchSanidade, fetchLancamentosProtocolo, editarAplicacaoSanidade, confirmarExclusao, ehAdmin, formatDate, fetchTaxaCura, type CasoTaxaCura, marcarCuraAplicacao, marcarCuraProtocolo, fetchMedicamentos, fetchRastreabilidadeSanitaria, type LinhaRastreabilidadeSanitaria,
} from "@/lib/api";
import { VIAS_APLICACAO } from "@/lib/constants";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { usePaginacao, Paginacao } from "@/components/Paginacao";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line } from "recharts";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { MultiFiltro, Indicador, SecaoRecolhivel, TelaSkeleton } from "@/components/ui";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { LotePicker, opcoesLoteDeAnimais } from "@/components/LotePicker";
import type { AnimalRow } from "@/components/AnimalModal";
import dynamic from "next/dynamic";
import CatalogoFarmaciaConsulta from "@/components/sanidade/CatalogoFarmaciaConsulta";
import RemediosPorDoenca from "@/components/RemediosPorDoenca";
import { casaBusca } from "@/lib/busca";

const COLUNAS_SANIDADE = [
  { header: "Data", key: "data" }, { header: "Animal", key: "numero" }, { header: "Produto", key: "produto" },
  { header: "Categoria", key: "categoria" }, { header: "Dose", key: "dose" }, { header: "Atividade", key: "atividade" },
];

type Aplic = {
  id: number; numero: string; raca: string; produto: string; categoria: string;
  dose: number | null; unidade: string | null; via: string | null; responsavel: string | null;
  atividade: string | null; obs: string | null; ordem_parto: number | null;
  lote: string | null; categoria_animal: string | null; natureza: string | null;
  data: string | null; ano: number | null; mes: string | null;
  usuario_nome?: string | null;
};

const CORES = ["var(--vinho-light, #416180)", "var(--dourado)", "var(--blue)", "var(--amber)", "var(--green-light)", "var(--red)", "#7A5C99", "#4C9AA8"];
const UNIDADES_APLIC = ["ml", "L", "unidade", "dose", "kg", "saca 30kg", "saca 60kg"];

// Aplicações curativas (editar/excluir). O preventivo antigo saiu (Sanitário
// Preventivo v2); registros com natureza="preventivo" que sobram são de BST e
// Indução de cio, que têm relatórios próprios e por isso não entram aqui.
function AplicacoesView() {
  const [regs, setRegs] = useState<Aplic[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [avisoExclusao, setAvisoExclusao] = useState<string | null>(null);
  const [fCat, setFCat] = useState("");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [buscaProd, setBuscaProd] = useState("");
  const [fOrdemParto, setFOrdemParto] = useState<string[]>([]);
  // Filtro por animal(is)/lote(s)/categoria(s) do animal — mesmo padrão de
  // seleção "todos ou vários" do lançamento de Aplicação: escolher lote(s) ou
  // categoria(s) abre a lista dos animais correspondentes para afinar a seleção.
  const [animaisSel, setAnimaisSel] = useState<Set<string>>(new Set());
  const [lotesSel, setLotesSel] = useState<string[]>([]);
  const [selDosLotes, setSelDosLotes] = useState<Set<string>>(new Set());
  const [categoriasAnimalSel, setCategoriasAnimalSel] = useState<string[]>([]);
  const [selDasCategorias, setSelDasCategorias] = useState<Set<string>>(new Set());
  const [editId, setEditId] = useState<number | null>(null);
  const [editVals, setEditVals] = useState<{ data: string; produto: string; dose: string; unidade: string; via: string; responsavel: string; obs: string }>({ data: "", produto: "", dose: "", unidade: "", via: "", responsavel: "", obs: "" });
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [produtosCatalogo, setProdutosCatalogo] = useState<{ nome: string; quantidade: number | null; unidade: string | null }[]>([]);
  const [soComEstoque, setSoComEstoque] = useState(false);
  const admin = ehAdmin();

  // Exclusão múltipla — marca vários registros (individuais ou dentro de um
  // card de lote expandido) e exclui de uma vez. `expandidos` controla quais
  // cards de lote (BST, protocolo... qualquer grupo de aplicações lançadas
  // juntas) estão abertos para seleção individual, em vez do card recolhido.
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [expandidos, setExpandidos] = useState<Set<string>>(new Set());
  const [excluindoLote, setExcluindoLote] = useState(false);

  useEffect(() => {
    fetchMedicamentos({ incluir_sem_estoque: true })
      .then((m: any[]) => setProdutosCatalogo(m.map((x) => ({ nome: x.nome, quantidade: x.quantidade, unidade: x.unidade }))))
      .catch(() => setProdutosCatalogo([]));
  }, []);

  // Opções do filtro = união dos produtos que APARECEM nas aplicações carregadas
  // com o catálogo da farmácia (que traz o saldo). Sem a primeira parte, uma
  // aplicação antiga de produto já removido do estoque ficaria impossível de
  // filtrar; sem a segunda, não dava para escolher um produto ainda não usado.
  // `quantidade === null` = produto que não está no catálogo de estoque atual.
  const catalogoFiltrado = useMemo(() => {
    const porNome = new Map(produtosCatalogo.map((p) => [p.nome, p]));
    for (const r of regs || []) {
      if (r.produto && !porNome.has(r.produto)) porNome.set(r.produto, { nome: r.produto, quantidade: null, unidade: null });
    }
    const lista = Array.from(porNome.values());
    const visiveis = soComEstoque ? lista.filter((p) => (p.quantidade ?? 0) > 0) : lista;
    return visiveis.sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
  }, [produtosCatalogo, regs, soComEstoque]);
  // Se o produto selecionado sumir da lista ao marcar o checkbox, limpa o filtro para não deixar seleção invisível.
  useEffect(() => {
    if (soComEstoque && buscaProd && !catalogoFiltrado.some((p) => p.nome === buscaProd)) setBuscaProd("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [soComEstoque]);

  // Legado/importado (natureza=null) conta como curativo (ver Sanidade.natureza).
  const carregar = () => fetchSanidade().then((d) => setRegs(
    (d.aplicacoes as Aplic[]).filter((a) => a.natureza !== "preventivo")
  )).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const iniciarEdicao = (a: Aplic) => {
    setEditId(a.id);
    setEditVals({
      data: a.data ?? "", produto: a.produto ?? "", dose: a.dose == null ? "" : String(a.dose),
      unidade: a.unidade ?? "", via: a.via ?? "", responsavel: a.responsavel ?? "", obs: a.obs ?? "",
    });
    setError(null);
  };

  const salvarEdicao = async (a: Aplic) => {
    setOcupado(a.id); setError(null);
    try {
      await editarAplicacaoSanidade(a.id, {
        data_aplicacao: editVals.data || undefined,
        produto: editVals.produto.trim() || undefined,
        dose: editVals.dose.trim() === "" ? null : Number(editVals.dose),
        unidade: editVals.unidade || null,
        via: editVals.via.trim() || null,
        responsavel: editVals.responsavel.trim() || null,
        obs: editVals.obs.trim() || null,
      });
      setEditId(null);
      await carregar();
    } catch (e: any) { setError(e.message); }
    finally { setOcupado(null); }
  };

  // Passa pelo fluxo central e auditado de exclusão (POST /exclusoes/confirmar)
  // em vez do DELETE direto — admin ainda exclui na hora, mas agora QUALQUER
  // usuário logado pode pedir (operador vira uma SolicitacaoExclusao pendente
  // de aprovação, igual a qualquer outra exclusão do sistema). Isso também
  // conecta com o mesmo estorno de estoque e a mesma trilha de auditoria que
  // o painel de Exclusões já usa — antes o botão (só visível pra admin) batia
  // direto em DELETE /sanidade/aplicacoes/{id}, sem gerar esse rastro.
  const excluir = async (a: Aplic) => {
    const msg = admin
      ? `Excluir a aplicação de "${a.produto}" no animal ${a.numero}? Isso não pode ser desfeito.`
      : `Solicitar a exclusão da aplicação de "${a.produto}" no animal ${a.numero}? Um administrador precisa aprovar antes de ser excluída de fato.`;
    if (!window.confirm(msg)) return;
    setOcupado(a.id); setError(null); setAvisoExclusao(null);
    try {
      const r = await confirmarExclusao("sanidade", String(a.id));
      if (r.status === "excluido") {
        await carregar();
      } else {
        setAvisoExclusao(`Solicitação de exclusão enviada — aguardando aprovação de um administrador.`);
      }
    } catch (e: any) { setError(e.message); }
    finally { setOcupado(null); }
  };

  const excluirVarias = async (ids: number[]) => {
    if (!ids.length) return;
    const msg = admin
      ? `Excluir ${ids.length} aplicação(ões)? Isso não pode ser desfeito.`
      : `Solicitar a exclusão de ${ids.length} aplicação(ões)? Um administrador precisa aprovar antes de serem excluídas de fato.`;
    if (!window.confirm(msg)) return;
    setExcluindoLote(true); setError(null); setAvisoExclusao(null);
    let excluidas = 0, pendentes = 0;
    for (const id of ids) {
      try {
        const r = await confirmarExclusao("sanidade", String(id));
        if (r.status === "excluido") excluidas++; else pendentes++;
      } catch (e: any) { setError(e.message); }
    }
    setSelecionados(new Set());
    setExcluindoLote(false);
    if (excluidas) await carregar();
    if (pendentes) setAvisoExclusao(`${pendentes} solicitação(ões) de exclusão enviada(s) — aguardando aprovação de um administrador.`);
  };

  const toggleSelecionado = (id: number) => setSelecionados((prev) => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n;
  });
  const toggleExpandido = (chave: string) => setExpandidos((prev) => {
    const n = new Set(prev); n.has(chave) ? n.delete(chave) : n.add(chave); return n;
  });

  const opc = (f: (a: Aplic) => string | null) => {
    const s = new Set<string>(); (regs ?? []).forEach((a) => { const v = f(a); if (v) s.add(v); });
    return Array.from(s).sort();
  };

  // Animais distintos já lançados (com lote/categoria) — dá para montar os
  // pickers padrão (AnimalPickerModal/LotePicker) sem precisar do cadastro
  // completo do rebanho, já que cada aplicação já carrega lote/categoria_animal.
  const animaisDeAplic = useMemo<AnimalRow[]>(() => {
    const porNumero = new Map<string, AnimalRow>();
    (regs ?? []).forEach((a) => {
      if (!porNumero.has(a.numero)) porNumero.set(a.numero, { numero: a.numero, grupo_primario: a.lote, categoria_abrev: a.categoria_animal });
    });
    return Array.from(porNumero.values());
  }, [regs]);
  const codigosLotesTodos = useMemo(
    () => Array.from(new Set(animaisDeAplic.map((a) => a.grupo_primario).filter((c): c is string => !!c))).sort(),
    [animaisDeAplic]
  );
  const animaisDosLotesSel = useMemo(() => {
    if (!lotesSel.length) return [];
    const cods = new Set(lotesSel);
    return animaisDeAplic.filter((a) => a.grupo_primario && cods.has(a.grupo_primario));
  }, [animaisDeAplic, lotesSel]);
  useEffect(() => {
    setSelDosLotes(new Set(animaisDosLotesSel.map((a) => a.numero)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lotesSel.join("|")]);
  const categoriasAnimalTodas = useMemo(
    () => Array.from(new Set(animaisDeAplic.map((a) => a.categoria_abrev).filter((c): c is string => !!c))).sort(),
    [animaisDeAplic]
  );
  const animaisDasCategoriasSel = useMemo(() => {
    if (!categoriasAnimalSel.length) return [];
    const cats = new Set(categoriasAnimalSel);
    return animaisDeAplic.filter((a) => a.categoria_abrev && cats.has(a.categoria_abrev));
  }, [animaisDeAplic, categoriasAnimalSel]);
  useEffect(() => {
    setSelDasCategorias(new Set(animaisDasCategoriasSel.map((a) => a.numero)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoriasAnimalSel.join("|")]);

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((a) =>
      (!fCat || a.categoria === fCat) &&
      (!ini || (a.data ? a.data >= ini : false)) &&
      (!fim || (a.data ? a.data <= fim : false)) &&
      (!buscaProd || a.produto === buscaProd) &&
      (animaisSel.size === 0 || animaisSel.has(a.numero)) &&
      (lotesSel.length === 0 || selDosLotes.has(a.numero)) &&
      (categoriasAnimalSel.length === 0 || selDasCategorias.has(a.numero)) &&
      (fOrdemParto.length === 0 || (a.ordem_parto !== null && fOrdemParto.includes(String(a.ordem_parto))))
    );
  }, [regs, fCat, ini, fim, buscaProd, animaisSel, lotesSel, selDosLotes, categoriasAnimalSel, selDasCategorias, fOrdemParto]);

  // Agrupa em "cards de lote" as aplicações que vieram do MESMO lançamento em
  // lote (BST, protocolo...) — mesma data/produto/atividade/responsável/dose/
  // unidade/usuário, ≥2 animais. Não há um id de lote explícito no banco;
  // esta é a mesma combinação de campos que só bate por coincidência entre
  // duas ações manuais DIFERENTES na prática (data+produto+responsável+dose
  // exatamente iguais). Um card recolhido oferece excluir tudo de uma vez;
  // expandido, mostra cada linha para marcar/excluir uma por uma.
  type ItemAplic = { tipo: "grupo"; chave: string; linhas: Aplic[] } | { tipo: "individual"; linha: Aplic };
  const itensExibicao = useMemo<ItemAplic[]>(() => {
    const porChave = new Map<string, Aplic[]>();
    for (const a of filtrados) {
      const chave = [a.data, a.produto, a.atividade, a.responsavel, a.dose, a.unidade, a.usuario_nome].join("␟");
      const lista = porChave.get(chave) || [];
      lista.push(a);
      porChave.set(chave, lista);
    }
    const itens: ItemAplic[] = [];
    for (const [chave, linhas] of porChave.entries()) {
      if (linhas.length > 1) itens.push({ tipo: "grupo", chave, linhas });
      else itens.push({ tipo: "individual", linha: linhas[0] });
    }
    // Mantém a ordem geral por data desc (mesma ordem que `filtrados`/`regs`
    // já trazem) — usa a posição do primeiro item de cada grupo/individual.
    const posicao = new Map(filtrados.map((a, i) => [a.id, i]));
    itens.sort((x, y) => {
      const px = x.tipo === "grupo" ? Math.min(...x.linhas.map((l) => posicao.get(l.id) ?? 0)) : (posicao.get(x.linha.id) ?? 0);
      const py = y.tipo === "grupo" ? Math.min(...y.linhas.map((l) => posicao.get(l.id) ?? 0)) : (posicao.get(y.linha.id) ?? 0);
      return px - py;
    });
    return itens;
  }, [filtrados]);
  const pagAplicacoes = usePaginacao(itensExibicao);

  // Quando há filtro por período (de/até), as linhas SEM data ficam de fora — conta quantas para avisar o usuário.
  const semDataExcluidas = useMemo(() => {
    if (!regs || (!ini && !fim)) return 0;
    return regs.filter((a) =>
      (!fCat || a.categoria === fCat) &&
      (!buscaProd || a.produto === buscaProd) &&
      (animaisSel.size === 0 || animaisSel.has(a.numero)) &&
      (lotesSel.length === 0 || selDosLotes.has(a.numero)) &&
      (categoriasAnimalSel.length === 0 || selDasCategorias.has(a.numero)) &&
      !a.data
    ).length;
  }, [regs, fCat, ini, fim, buscaProd, animaisSel, lotesSel, selDosLotes, categoriasAnimalSel, selDasCategorias]);

  const porCategoria = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((a) => by.set(a.categoria, (by.get(a.categoria) ?? 0) + 1));
    return Array.from(by.entries()).map(([cat, n]) => ({ cat, n })).sort((a, b) => b.n - a.n);
  }, [filtrados]);

  const porMes = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((a) => { if (a.mes) by.set(a.mes, (by.get(a.mes) ?? 0) + 1); });
    return Array.from(by.keys()).sort().map((mes) => ({ mes, n: by.get(mes)! }));
  }, [filtrados]);

  const animaisTratados = new Set(filtrados.map((a) => a.numero)).size;
  const produtos = new Set(filtrados.map((a) => a.produto)).size;
  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };
  const tip = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", color: "var(--text)", fontSize: "0.8rem" };

  return (
    <>
      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/configuracoes?aba=importar" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Importe os dados sanitários</a>.</span></div>}
      {!regs && !error && <TelaSkeleton kpis={0} />}

      {regs && <>
        <div className="card mb-4">
          <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Categoria</label>
              <select style={selStyle} value={fCat} onChange={(e) => setFCat(e.target.value)}><option value="">Todas</option>{opc((a) => a.categoria).map((o) => <option key={o}>{o}</option>)}</select></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label>
              <input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} /></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label>
              <input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Produto</label>
              <select style={selStyle} value={buscaProd} onChange={(e) => setBuscaProd(e.target.value)}>
                <option value="">Todos</option>
                {!catalogoFiltrado.some((p) => p.nome === buscaProd) && buscaProd && <option value={buscaProd}>{buscaProd}</option>}
                {catalogoFiltrado.map((p) => (
                  <option key={p.nome} value={p.nome}>
                    {p.nome}{p.quantidade == null ? "" : ` — ${p.quantidade > 0 ? `${p.quantidade}${p.unidade ? ` ${p.unidade}` : ""}` : "sem estoque"}`}
                  </option>
                ))}
              </select>
              <label title="Mostrar no seletor apenas produtos com saldo em estoque" style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.7rem", color: "var(--text-muted)", cursor: "pointer", marginTop: "0.3rem" }}>
                <input type="checkbox" checked={soComEstoque} onChange={(e) => setSoComEstoque(e.target.checked)} /> Só com saldo em estoque
              </label>
            </div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal(is)</label>
              <AnimalPickerModal
                animais={animaisDeAplic} selecionados={animaisSel} onToggle={(n) => setAnimaisSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; })}
                placeholder="Todos" titulo="Filtrar por animal(is)"
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  { header: "Categoria", render: (a) => a.categoria_abrev || "—" },
                ]}
              />
            </div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Lote(s)</label>
              <LotePicker opcoes={opcoesLoteDeAnimais(animaisDeAplic, codigosLotesTodos)} selecionados={lotesSel} onChange={setLotesSel} placeholder="Todos" />
            </div>
            <MultiFiltro label="Categoria do animal" opcoes={categoriasAnimalTodas} selecionados={categoriasAnimalSel} onChange={setCategoriasAnimalSel} />
            <MultiFiltro label="Ordem de parto" opcoes={opc((a) => a.ordem_parto == null ? null : String(a.ordem_parto))} selecionados={fOrdemParto} onChange={setFOrdemParto} formatar={(v) => `${v}ª`} />
          </div>
          {lotesSel.length > 0 && (
            <div style={{ marginTop: "0.6rem" }}>
              <AnimalPickerModal
                animais={animaisDosLotesSel} selecionados={selDosLotes} onToggle={(n) => setSelDosLotes((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; })}
                titulo="Ajustar animais do(s) lote(s) selecionado(s)" placeholder="Ajustar animais do(s) lote(s)…"
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  { header: "Categoria", render: (a) => a.categoria_abrev || "—" },
                ]}
              />
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                {selDosLotes.size} de {animaisDosLotesSel.length} animal(is) no(s) lote(s) selecionado(s) — desmarque na janela acima para excluir algum.
              </p>
            </div>
          )}
          {categoriasAnimalSel.length > 0 && (
            <div style={{ marginTop: "0.6rem" }}>
              <AnimalPickerModal
                animais={animaisDasCategoriasSel} selecionados={selDasCategorias} onToggle={(n) => setSelDasCategorias((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; })}
                titulo="Ajustar animais das categorias selecionadas" placeholder="Ajustar animais das categorias…"
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  { header: "Categoria", render: (a) => a.categoria_abrev || "—" },
                ]}
              />
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                {selDasCategorias.size} de {animaisDasCategoriasSel.length} animal(is) na(s) categoria(s) selecionada(s) — desmarque na janela acima para excluir algum.
              </p>
            </div>
          )}
        </div>

        {semDataExcluidas > 0 && (
          <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.75rem" }}>
            {semDataExcluidas} aplicaç{semDataExcluidas === 1 ? "ão" : "ões"} sem data não {semDataExcluidas === 1 ? "é exibida" : "são exibidas"} no filtro por período.
          </p>
        )}

        {/* Aplicações é o volume de atividade real da tela — vira a métrica-âncora
            em vez de competir em pé de igualdade com Animais tratados/Produtos
            distintos/Categorias, que continuam do lado, menores. */}
        <div className="card mb-4" style={{ padding: "1.1rem 1.3rem" }}>
          <div style={{ fontSize: ".68rem", fontWeight: 700, letterSpacing: ".13em", textTransform: "uppercase", color: "var(--text-muted)" }}>Aplicações</div>
          <div style={{ fontFamily: "var(--font-heading)", fontSize: "2.6rem", fontWeight: 800, lineHeight: 1, color: "var(--dourado-light)", marginTop: ".25rem", fontVariantNumeric: "tabular-nums" }}>
            {filtrados.length}
          </div>
          <div style={{ display: "flex", gap: "1.6rem", marginTop: ".9rem", paddingTop: ".8rem", borderTop: "1px solid var(--border)", flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--green-light)", fontVariantNumeric: "tabular-nums" }}>{animaisTratados}</div>
              <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Animais tratados</div>
            </div>
            <div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{produtos}</div>
              <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Produtos distintos</div>
            </div>
            <div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{porCategoria.length}</div>
              <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Categorias</div>
            </div>
          </div>
        </div>

        <SecaoRecolhivel titulo="Aplicações por Categoria e por Mês" descricao="Clique numa barra para filtrar as aplicações por categoria">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="card-header mb-3">Aplicações por Categoria <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>(clique para filtrar)</span></div>
              <div title="Clique numa barra para filtrar as aplicações por categoria">
              <ResponsiveContainer width="100%" height={Math.max(180, porCategoria.length * 34)}>
                <BarChart data={porCategoria} layout="vertical" margin={{ left: 8 }}>
                  <XAxis type="number" tick={{ fill: "var(--text-muted)", fontSize: 10 }} allowDecimals={false} />
                  <YAxis type="category" dataKey="cat" tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={130} />
                  <Tooltip contentStyle={tip} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                  <Bar dataKey="n" name="Aplicações" radius={[0, 3, 3, 0]} style={{ cursor: "pointer" }} onClick={(e: any) => e?.cat && setFCat((c) => c === e.cat ? "" : e.cat)}>
                    {porCategoria.map((_, i) => <Cell key={i} fill={CORES[i % CORES.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              </div>
            </div>
            <div>
              <div className="card-header mb-3">Aplicações por Mês</div>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={porMes}>
                  <XAxis dataKey="mes" tick={{ fill: "var(--text-muted)", fontSize: 9 }} tickFormatter={(m) => m.slice(2)} />
                  <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} allowDecimals={false} width={30} />
                  <Tooltip contentStyle={tip} />
                  <Line type="monotone" dataKey="n" name="Aplicações" stroke="var(--dourado-light)" strokeWidth={2} dot={{ r: 2 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </SecaoRecolhivel>

        <SecaoRecolhivel titulo="Aplicações" badge={<span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length} registro(s)</span>}
          descricao="Lista completa das aplicações que atendem aos filtros acima">
          {avisoExclusao && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{avisoExclusao}</p>}
          <div className="flex justify-between items-center mb-2" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
            <button className="btn-ghost" style={{ fontSize: "0.78rem", color: "var(--red)" }}
              disabled={!selecionados.size || excluindoLote}
              onClick={() => excluirVarias(Array.from(selecionados))}>
              <Trash2 size={14} /> {excluindoLote ? "Excluindo…" : `Excluir selecionados (${selecionados.size})`}
            </button>
            <ExportarBotoes titulo="Sanidade — Aplicações" nomeArquivoBase="sanidade" colunas={COLUNAS_SANIDADE} linhas={filtrados} />
          </div>
          <div>
            <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
              <table className="fazenda-table">
                <thead><tr><th></th><th>Data</th><th>Animal</th><th>Produto</th><th>Categoria</th><th style={{ textAlign: "right" }}>Dose</th>{admin && <th style={{ textAlign: "left" }}>Usuário</th>}<th style={{ textAlign: "right" }}>Ações</th></tr></thead>
                <tbody>
                  {pagAplicacoes.linhasPagina.map((item) => {
                    if (item.tipo === "grupo") {
                      const { chave, linhas } = item;
                      const aberto = expandidos.has(chave);
                      const primeira = linhas[0];
                      const idsDoGrupo = linhas.map((l) => l.id);
                      const todasMarcadas = idsDoGrupo.every((id) => selecionados.has(id));
                      if (!aberto) {
                        return (
                          <tr key={chave} style={{ background: "var(--surface-2)", cursor: "pointer" }} onClick={() => toggleExpandido(chave)}>
                            <td onClick={(e) => e.stopPropagation()}>
                              <input type="checkbox" checked={todasMarcadas} onChange={() => setSelecionados((prev) => {
                                const n = new Set(prev);
                                if (todasMarcadas) idsDoGrupo.forEach((id) => n.delete(id)); else idsDoGrupo.forEach((id) => n.add(id));
                                return n;
                              })} />
                            </td>
                            <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{primeira.data ? new Date(primeira.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                            <td colSpan={2} style={{ fontWeight: 700 }}>
                              <span className="flex items-center gap-1"><ChevronRight size={13} /> {primeira.produto}{primeira.atividade ? ` — ${primeira.atividade}` : ""}
                                <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: "0.75rem" }}> · {linhas.length} animais (lançados juntos)</span></span>
                            </td>
                            <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{primeira.categoria}</td>
                            <td style={{ textAlign: "right" }}>{primeira.dose ?? "—"}{primeira.unidade ? ` ${primeira.unidade}` : ""}</td>
                            {admin && <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{primeira.usuario_nome ?? "—"}</td>}
                            <td style={{ textAlign: "right", whiteSpace: "nowrap" }} onClick={(e) => e.stopPropagation()}>
                              <button title={admin ? "Excluir todos deste lote" : "Solicitar exclusão de todos deste lote"} disabled={excluindoLote}
                                onClick={() => excluirVarias(idsDoGrupo)}
                                style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)", padding: 2 }}>
                                <Trash2 size={14} />
                              </button>
                            </td>
                          </tr>
                        );
                      }
                      return (
                        <Fragment key={chave}>
                          <tr style={{ background: "var(--surface-2)", cursor: "pointer" }} onClick={() => toggleExpandido(chave)}>
                            <td colSpan={(admin ? 8 : 7)} style={{ fontSize: "0.78rem", fontWeight: 600 }}>
                              <span className="flex items-center gap-1"><ChevronDown size={13} /> {primeira.produto}{primeira.atividade ? ` — ${primeira.atividade}` : ""} · {linhas.length} animais — clique para recolher</span>
                            </td>
                          </tr>
                          {linhas.map((a) => (
                            <tr key={a.id}>
                              <td><input type="checkbox" checked={selecionados.has(a.id)} onChange={() => toggleSelecionado(a.id)} /></td>
                              <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{a.data ? new Date(a.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                              <td style={{ fontWeight: 700 }}>{a.numero}</td>
                              <td style={{ fontSize: "0.75rem" }}>{a.produto}</td>
                              <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{a.categoria}</td>
                              <td style={{ textAlign: "right" }}>{a.dose ?? "—"}{a.unidade ? ` ${a.unidade}` : ""}</td>
                              {admin && <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{a.usuario_nome ?? "—"}</td>}
                              <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                                <button title={admin ? "Excluir" : "Solicitar exclusão"} disabled={ocupado === a.id} onClick={() => excluir(a)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)", padding: 2 }}><Trash2 size={14} /></button>
                              </td>
                            </tr>
                          ))}
                        </Fragment>
                      );
                    }

                    const a = item.linha;
                    const editando = editId === a.id;
                    const inp: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.25rem 0.4rem", fontSize: "0.75rem", width: "100%" };
                    return (
                    <Fragment key={a.id}>
                      <tr>
                        <td><input type="checkbox" checked={selecionados.has(a.id)} onChange={() => toggleSelecionado(a.id)} /></td>
                        <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{a.data ? new Date(a.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                        <td style={{ fontWeight: 700 }}>{a.numero}</td>
                        <td style={{ fontSize: "0.75rem" }}>{a.produto}</td>
                        <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{a.categoria}</td>
                        <td style={{ textAlign: "right" }}>{a.dose ?? "—"}{a.unidade ? ` ${a.unidade}` : ""}</td>
                        {admin && <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{a.usuario_nome ?? "—"}</td>}
                        <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                          {!editando && (
                            <span style={{ display: "inline-flex", gap: "0.3rem" }}>
                              {admin && <button title="Editar" onClick={() => iniciarEdicao(a)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 2 }}><Pencil size={14} /></button>}
                              <button title={admin ? "Excluir" : "Solicitar exclusão"} disabled={ocupado === a.id} onClick={() => excluir(a)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)", padding: 2 }}><Trash2 size={14} /></button>
                            </span>
                          )}
                        </td>
                      </tr>
                      {editando && (
                        <tr>
                          <td colSpan={admin ? 8 : 7} style={{ background: "var(--surface-2)", padding: "0.6rem" }}>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                              <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Data</label>
                                <input type="date" style={inp} value={editVals.data} onChange={(e) => setEditVals((s) => ({ ...s, data: e.target.value }))} /></div>
                              <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Produto</label>
                                <select style={inp} value={editVals.produto} onChange={(e) => setEditVals((s) => ({ ...s, produto: e.target.value }))}>
                                  <option value="">Selecione...</option>
                                  {!produtosCatalogo.some((p) => p.nome === editVals.produto) && editVals.produto && <option value={editVals.produto}>{editVals.produto}</option>}
                                  {produtosCatalogo.map((p) => <option key={p.nome} value={p.nome}>{p.nome}</option>)}
                                </select></div>
                              <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Dose</label>
                                <input type="number" step="any" style={inp} value={editVals.dose} onChange={(e) => setEditVals((s) => ({ ...s, dose: e.target.value }))} /></div>
                              <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Unidade</label>
                                <select style={inp} value={editVals.unidade} onChange={(e) => setEditVals((s) => ({ ...s, unidade: e.target.value }))}>
                                  <option value="">—</option>
                                  {!UNIDADES_APLIC.includes(editVals.unidade) && editVals.unidade && <option value={editVals.unidade}>{editVals.unidade}</option>}
                                  {UNIDADES_APLIC.map((u) => <option key={u} value={u}>{u}</option>)}
                                </select></div>
                              <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Via</label>
                                <select style={inp} value={editVals.via} onChange={(e) => setEditVals((s) => ({ ...s, via: e.target.value }))}>
                                  <option value="">—</option>
                                  {!VIAS_APLICACAO.includes(editVals.via) && editVals.via && <option value={editVals.via}>{editVals.via}</option>}
                                  {VIAS_APLICACAO.map((v) => <option key={v} value={v}>{v}</option>)}
                                </select></div>
                              <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Responsável</label>
                                <select style={inp} value={editVals.responsavel} onChange={(e) => setEditVals((s) => ({ ...s, responsavel: e.target.value }))}>
                                  <option value="">—</option>
                                  {!nomesResponsaveis.includes(editVals.responsavel) && editVals.responsavel && <option value={editVals.responsavel}>{editVals.responsavel}</option>}
                                  {nomesResponsaveis.map((r) => <option key={r} value={r}>{r}</option>)}
                                </select></div>
                              <div style={{ gridColumn: "span 2" }}><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Observação</label>
                                <input style={inp} value={editVals.obs} onChange={(e) => setEditVals((s) => ({ ...s, obs: e.target.value }))} /></div>
                            </div>
                            <div className="flex gap-2 mt-2">
                              <button className="btn-primary" disabled={ocupado === a.id} onClick={() => salvarEdicao(a)} style={{ fontSize: "0.78rem" }}><Check size={13} /> {ocupado === a.id ? "…" : "Salvar"}</button>
                              <button className="btn-ghost" disabled={ocupado === a.id} onClick={() => setEditId(null)} style={{ fontSize: "0.78rem" }}><X size={13} /> Cancelar</button>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                    );
                  })}
                </tbody>
              </table>
              <Paginacao pagina={pagAplicacoes.pagina} totalPaginas={pagAplicacoes.totalPaginas} totalLinhas={pagAplicacoes.totalLinhas}
                tamanhoPagina={pagAplicacoes.tamanhoPagina} onMudarPagina={pagAplicacoes.setPagina} onMudarTamanho={pagAplicacoes.setTamanhoPagina} />
            </div>
          </div>
        </SecaoRecolhivel>
      </>}
    </>
  );
}

// ─────────────────────────── Doença / Motivo (curativa) ───────────────────────────
// Resumo dos tratamentos curativos agrupados pelo motivo (atividade) — cada
// doença/motivo é clicável e expande os casos, filtráveis por animal, lote,
// período e categoria do animal.
function DoencaMotivoView() {
  const [regs, setRegs] = useState<Aplic[] | null>(null);
  const [aberto, setAberto] = useState<string | null>(null);
  const [buscaAnimal, setBuscaAnimal] = useState("");
  const [fLote, setFLote] = useState("");
  const [fCategoria, setFCategoria] = useState("");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");

  useEffect(() => { fetchSanidade().then((d) => setRegs(d.aplicacoes)).catch(() => setRegs([])); }, []);

  // A aba "Curativa" mostra o que não é preventivo (BST/Indução) — dados
  // legados/importados (natureza=null) são tratados como curativo.
  const curativos = useMemo(() => (regs || []).filter((r) => r.natureza !== "preventivo"), [regs]);

  const filtrados = useMemo(() => curativos.filter((r) =>
    casaBusca(r.numero, buscaAnimal) &&
    (!fLote || r.lote === fLote) &&
    (!fCategoria || r.categoria_animal === fCategoria) &&
    (!ini || (r.data ? r.data >= ini : false)) &&
    (!fim || (r.data ? r.data <= fim : false))
  ), [curativos, buscaAnimal, fLote, fCategoria, ini, fim]);

  const lotesOpc = useMemo(() => Array.from(new Set(curativos.map((r) => r.lote).filter(Boolean))).sort() as string[], [curativos]);
  const categoriasOpc = useMemo(() => Array.from(new Set(curativos.map((r) => r.categoria_animal).filter(Boolean))).sort() as string[], [curativos]);

  const grupos = useMemo(() => {
    const m = new Map<string, { motivo: string; casos: Aplic[]; ultima: string | null }>();
    for (const r of filtrados) {
      const motivo = (r.atividade || r.categoria || "Não informado") as string;
      const g = m.get(motivo) || { motivo, casos: [], ultima: null };
      g.casos.push(r);
      if (!g.ultima || (r.data && r.data > g.ultima)) g.ultima = r.data || g.ultima;
      m.set(motivo, g);
    }
    return Array.from(m.values()).sort((a, b) => b.casos.length - a.casos.length);
  }, [filtrados]);

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };
  const filtroAtivo = !!(buscaAnimal || fLote || fCategoria || ini || fim);

  return (
    <>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal</label>
            <div style={{ position: "relative" }}><Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} /><input style={{ ...selStyle, paddingLeft: "1.6rem" }} value={buscaAnimal} onChange={(e) => setBuscaAnimal(e.target.value)} placeholder="ex.: 068" /></div></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Lote</label>
            <select style={selStyle} value={fLote} onChange={(e) => setFLote(e.target.value)}><option value="">Todos</option>{lotesOpc.map((l) => <option key={l} value={l}>{l}</option>)}</select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Categoria do animal</label>
            <select style={selStyle} value={fCategoria} onChange={(e) => setFCategoria(e.target.value)}><option value="">Todas</option>{categoriasOpc.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label>
            <input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label>
            <input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
        </div>
      </div>

      <div className="card">
        <div className="card-header mb-3 flex items-center gap-2"><HeartPulse size={16} /> Doença / Motivo dos tratamentos</div>
        {!regs ? <TelaSkeleton kpis={0} /> : !grupos.length ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{filtroAtivo ? "Nenhum caso encontrado com esses filtros." : "Nenhum tratamento curativo lançado ainda."}</p>
        ) : (
          <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
            {grupos.map((g) => {
              const expandido = aberto === g.motivo;
              return (
                <Fragment key={g.motivo}>
                  <div
                    className="flex items-center justify-between"
                    style={{ padding: "0.55rem 0.8rem", borderBottom: "1px solid var(--border)", cursor: "pointer", background: expandido ? "var(--surface-2)" : "transparent" }}
                    onClick={() => setAberto(expandido ? null : g.motivo)}
                  >
                    <span className="flex items-center gap-2" style={{ fontSize: "0.86rem", fontWeight: 600 }}>
                      {expandido ? <ChevronDown size={14} /> : <ChevronRight size={14} />} {g.motivo}
                    </span>
                    <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{g.casos.length} caso(s){g.ultima ? ` · último ${formatDate(g.ultima)}` : ""}</span>
                  </div>
                  {expandido && (
                    <div style={{ borderBottom: "1px solid var(--border)", padding: "0.5rem 0.8rem", background: "var(--surface-1, var(--surface))" }}>
                      <div className="overflow-x-auto">
                        <table className="fazenda-table">
                          <thead><tr><th>Data</th><th>Animal</th><th>Lote</th><th>Categoria</th><th>Produto</th><th style={{ textAlign: "right" }}>Dose</th><th>Obs.</th></tr></thead>
                          <tbody>
                            {g.casos.slice().sort((a, b) => (b.data || "").localeCompare(a.data || "")).map((c) => (
                              <tr key={c.id}>
                                <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{c.data ? formatDate(c.data) : "—"}</td>
                                <td style={{ fontWeight: 700 }}>{c.numero}</td>
                                <td style={{ fontSize: "0.75rem" }}>{c.lote || "—"}</td>
                                <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{c.categoria_animal || "—"}</td>
                                <td style={{ fontSize: "0.75rem" }}>{c.produto}</td>
                                <td style={{ textAlign: "right", fontSize: "0.75rem" }}>{c.dose ?? "—"}{c.unidade ? ` ${c.unidade}` : ""}</td>
                                <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{c.obs || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </Fragment>
              );
            })}
          </div>
        )}
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
          O cadastro de doenças e princípios ativos fica em Configurações › Cadastro › Sanitário.
        </p>
      </div>
    </>
  );
}

// ─────────────────────────── Protocolos sanitários (curativa) ───────────────────────────
type EtapaProtocolo = { id: number; dia: number; produto: string; dosagem: number; unidade: string; via: string | null; observacao: string | null };
type AplicacaoProtocolo = { id: number; data_prevista: string; produto: string | null; realizada: boolean; data_realizacao: string | null; etapa: EtapaProtocolo | null };
type StatusProtocolo = "ativo" | "concluido" | "encerrado" | "cancelado";
type LancamentoProtocolo = {
  id: number; protocolo_id: number; protocolo_nome: string; protocolo_dia_inicial?: number; numero_matriz: string; data_inicio: string;
  responsavel: string | null; observacao: string | null;
  classificacao_mastite: string | null; grau_mastite: number | null; agente: string | null;
  resultado_cmt: string | null; tetos_afetados: string | null; usuario_nome?: string | null;
  // Estado do lote (cancelar/encerrar na Central) — vem do backend.
  status?: StatusProtocolo; encerrado_em?: string | null; encerrado_motivo?: string | null;
  aplicacoes: AplicacaoProtocolo[];
};

function ProtocolosSanitariosView() {
  const [lancs, setLancs] = useState<LancamentoProtocolo[] | null>(null);
  const [aberto, setAberto] = useState<number | null>(null);
  const [buscaAnimal, setBuscaAnimal] = useState("");
  const [fProtocolo, setFProtocolo] = useState("");
  const [fStatus, setFStatus] = useState<"" | "andamento" | "concluido" | "encerrado" | "cancelado">("");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");

  useEffect(() => { fetchLancamentosProtocolo().then(setLancs).catch(() => setLancs([])); }, []);

  const protocolosOpc = useMemo(() => Array.from(new Set((lancs || []).map((l) => l.protocolo_nome))).sort(), [lancs]);

  // Cancelado/encerrado NUNCA é "em andamento" (o estado vem do lote no backend).
  const statusDe = (l: LancamentoProtocolo): "andamento" | "concluido" | "encerrado" | "cancelado" => {
    if (l.status === "cancelado" || l.status === "encerrado") return l.status;
    return l.aplicacoes.length && l.aplicacoes.every((a) => a.realizada) ? "concluido" : "andamento";
  };
  const ROTULO_STATUS = { andamento: "Em andamento", concluido: "Concluído", encerrado: "Encerrado", cancelado: "Cancelado" } as const;
  const COR_STATUS = { andamento: "var(--amber)", concluido: "var(--green-light)", encerrado: "var(--text-muted)", cancelado: "var(--red, #dc2626)" } as const;

  const filtrados = useMemo(() => (lancs || []).filter((l) =>
    casaBusca(l.numero_matriz, buscaAnimal) &&
    (!fProtocolo || l.protocolo_nome === fProtocolo) &&
    (!fStatus || statusDe(l) === fStatus) &&
    (!ini || l.data_inicio >= ini) &&
    (!fim || l.data_inicio <= fim)
  ), [lancs, buscaAnimal, fProtocolo, fStatus, ini, fim]);

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

  return (
    <>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal</label>
            <div style={{ position: "relative" }}><Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} /><input style={{ ...selStyle, paddingLeft: "1.6rem" }} value={buscaAnimal} onChange={(e) => setBuscaAnimal(e.target.value)} placeholder="ex.: 068" /></div></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Protocolo</label>
            <select style={selStyle} value={fProtocolo} onChange={(e) => setFProtocolo(e.target.value)}><option value="">Todos</option>{protocolosOpc.map((p) => <option key={p} value={p}>{p}</option>)}</select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Status</label>
            <select style={selStyle} value={fStatus} onChange={(e) => setFStatus(e.target.value as typeof fStatus)}>
              <option value="">Todos</option><option value="andamento">Em andamento</option><option value="concluido">Concluído</option><option value="encerrado">Encerrado</option><option value="cancelado">Cancelado</option>
            </select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label>
            <input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label>
            <input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
        </div>
      </div>

      <div className="card">
        <div className="card-header mb-3 flex items-center gap-2"><ListChecks size={16} /> Protocolos sanitários lançados ({filtrados.length})</div>
        {!lancs ? <TelaSkeleton kpis={0} /> : !filtrados.length ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum protocolo lançado com esses filtros.</p>
        ) : (
          <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
            {filtrados.map((l) => {
              const expandido = aberto === l.id;
              const status = statusDe(l);
              return (
                <Fragment key={l.id}>
                  <div
                    className="flex items-center justify-between"
                    style={{ padding: "0.55rem 0.8rem", borderBottom: "1px solid var(--border)", cursor: "pointer", background: expandido ? "var(--surface-2)" : "transparent" }}
                    onClick={() => setAberto(expandido ? null : l.id)}
                  >
                    <span className="flex items-center gap-2" style={{ fontSize: "0.86rem", fontWeight: 600 }}>
                      {expandido ? <ChevronDown size={14} /> : <ChevronRight size={14} />} {l.protocolo_nome} <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>— animal {l.numero_matriz}</span>
                    </span>
                    <span className="flex items-center gap-3" style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {formatDate(l.data_inicio)}
                      <span style={{ fontWeight: 700, color: COR_STATUS[status] }} title={l.encerrado_motivo || undefined}>
                        {ROTULO_STATUS[status]}
                      </span>
                    </span>
                  </div>
                  {expandido && (
                    <div style={{ borderBottom: "1px solid var(--border)", padding: "0.5rem 0.8rem", background: "var(--surface-1, var(--surface))" }}>
                      {(l.classificacao_mastite || l.responsavel) && (
                        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
                          {l.classificacao_mastite && <>Mastite {l.classificacao_mastite}{l.grau_mastite ? ` (grau ${l.grau_mastite})` : ""}{l.tetos_afetados ? ` · tetos: ${l.tetos_afetados}` : ""}{l.agente ? ` · agente: ${l.agente}` : ""} · </>}
                          {l.responsavel && <>Responsável: {l.responsavel}</>}
                        </p>
                      )}
                      <div className="overflow-x-auto">
                        <table className="fazenda-table">
                          <thead><tr><th>Dia</th><th>Data prevista</th><th>Produto</th><th style={{ textAlign: "right" }}>Dose</th><th>Via</th><th>Realizada?</th><th>Data realização</th></tr></thead>
                          <tbody>
                            {l.aplicacoes.slice().sort((a, b) => (a.etapa?.dia ?? 0) - (b.etapa?.dia ?? 0)).map((a) => (
                              <tr key={a.id}>
                                <td>{a.etapa ? `D${a.etapa.dia - (l.protocolo_dia_inicial ?? 1)}` : "—"}</td>
                                <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{formatDate(a.data_prevista)}</td>
                                <td style={{ fontSize: "0.75rem" }}>{a.produto || a.etapa?.produto || "—"}</td>
                                <td style={{ textAlign: "right", fontSize: "0.75rem" }}>{a.etapa ? `${a.etapa.dosagem} ${a.etapa.unidade}` : "—"}</td>
                                <td style={{ fontSize: "0.75rem" }}>{a.etapa?.via || "—"}</td>
                                <td style={{ fontSize: "0.75rem", fontWeight: 700, color: a.realizada ? "var(--green-light)" : "var(--text-muted)" }}>{a.realizada ? "Sim" : "Não"}</td>
                                <td style={{ fontSize: "0.75rem" }}>{a.data_realizacao ? formatDate(a.data_realizacao) : "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </Fragment>
              );
            })}
          </div>
        )}
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
          Lance um novo protocolo em Lançamentos › Sanitário › Curativa › Protocolo sanitário.
        </p>
      </div>
    </>
  );
}

// ─────────────────────────── Taxa de cura (curativa) ───────────────────────────
const LABEL_CATEGORIA: Record<string, string> = { vaca: "Vaca", novilha: "Novilha", bezerra: "Bezerra" };
const LABEL_LACTACAO: Record<string, string> = { lactacao: "Lactação", seca: "Seca" };

function TaxaCuraView() {
  const [dados, setDados] = useState<{
    casos: CasoTaxaCura[]; total: number; total_avaliados: number; curados: number; nao_curados: number;
    total_nao_avaliados: number; taxa_cura_pct: number | null; cobertura_avaliacao_pct: number | null;
  } | null>(null);
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [fLotes, setFLotes] = useState<string[]>([]);
  const [fCategorias, setFCategorias] = useState<string[]>([]);
  const [fLactacao, setFLactacao] = useState<string[]>([]);
  const [marcando, setMarcando] = useState<Set<string>>(new Set());

  const carregar = useCallback(() => {
    fetchTaxaCura().then(setDados).catch(() => setDados({
      casos: [], total: 0, total_avaliados: 0, curados: 0, nao_curados: 0,
      total_nao_avaliados: 0, taxa_cura_pct: null, cobertura_avaliacao_pct: null,
    }));
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  // Responde "curado? sim/não" para um caso já com o protocolo encerrado mas
  // sem avaliação — o mesmo POST que a Agenda usa, só que aqui fora dela
  // (Defeito 4: a Agenda esconde o evento depois de 60 dias sem resposta, mas
  // o caso nunca deixa de poder ser avaliado — só passa a responder por aqui).
  const marcar = async (c: CasoTaxaCura, curada: boolean) => {
    const chave = `${c.origem}-${c.id}`;
    setMarcando((p) => new Set(p).add(chave));
    try {
      if (c.origem === "protocolo") await marcarCuraProtocolo(c.id, curada);
      else await marcarCuraAplicacao(c.id, curada);
      carregar();
    } catch (err: any) {
      alert(err.message || "Erro ao marcar cura");
    } finally {
      setMarcando((p) => { const n = new Set(p); n.delete(chave); return n; });
    }
  };

  const lotesOpc = useMemo(() => Array.from(new Set((dados?.casos || []).map((c) => c.lote).filter((v): v is string => !!v))).sort(), [dados]);

  const dentroDoFiltro = useCallback((c: CasoTaxaCura) =>
    (!ini || (c.data || "") >= ini) && (!fim || (c.data || "") <= fim) &&
    (fLotes.length === 0 || (c.lote != null && fLotes.includes(c.lote))) &&
    (fCategorias.length === 0 || fCategorias.includes(c.categoria)) &&
    (fLactacao.length === 0 || fLactacao.includes(c.status_lactacao))
  , [ini, fim, fLotes, fCategorias, fLactacao]);

  // Casos já avaliados (curada true/false) — só eles entram no cálculo da
  // taxa de cura. Os não avaliados (protocolo encerrado, ninguém respondeu)
  // ficam à parte, listados abaixo com botões Sim/Não.
  const filtrados = useMemo(() => (dados?.casos || []).filter((c) => c.avaliado && dentroDoFiltro(c)), [dados, dentroDoFiltro]);
  const naoAvaliados = useMemo(() => (dados?.casos || []).filter((c) => !c.avaliado && dentroDoFiltro(c)), [dados, dentroDoFiltro]);

  const totalFiltro = filtrados.length;
  const curadosFiltro = filtrados.filter((c) => c.curada).length;
  const taxaFiltro = totalFiltro ? Math.round((1000 * curadosFiltro) / totalFiltro) / 10 : null;
  const totalComPendentesFiltro = totalFiltro + naoAvaliados.length;
  const coberturaFiltro = totalComPendentesFiltro ? Math.round((1000 * totalFiltro) / totalComPendentesFiltro) / 10 : null;

  // Comparação do próprio animal ao longo da vida: agrupa por número, mostra
  // a taxa de cura individual — só faz sentido comparar quem já teve mais de 1 caso.
  const porAnimal = useMemo(() => {
    const by = new Map<string, CasoTaxaCura[]>();
    filtrados.forEach((c) => { (by.get(c.numero) ?? by.set(c.numero, []).get(c.numero)!).push(c); });
    return Array.from(by.entries())
      .map(([numero, casos]) => {
        const curados = casos.filter((c) => c.curada).length;
        return { numero, casos: casos.length, curados, taxa: Math.round((1000 * curados) / casos.length) / 10 };
      })
      .filter((a) => a.casos > 1)
      .sort((a, b) => a.taxa - b.taxa);
  }, [filtrados]);

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

  return (
    <>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Período — de</label>
            <input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>até</label>
            <input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
          <MultiFiltro label="Lote" opcoes={lotesOpc} selecionados={fLotes} onChange={setFLotes} />
          <MultiFiltro label="Categoria" opcoes={["vaca", "novilha", "bezerra"]} selecionados={fCategorias} onChange={setFCategorias} formatar={(v) => LABEL_CATEGORIA[v] || v} />
          <MultiFiltro label="Lactação/Seca" opcoes={["lactacao", "seca"]} selecionados={fLactacao} onChange={setFLactacao} formatar={(v) => LABEL_LACTACAO[v] || v} />
        </div>
      </div>

      {!dados ? <TelaSkeleton kpis={0} /> : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <Indicador categoria="sanidade" valor={totalFiltro} rotulo="Casos avaliados" />
            <Indicador categoria="sanidade" valor={curadosFiltro} cor="var(--green-light)" rotulo="Curados" />
            <Indicador
              categoria="sanidade"
              valor={taxaFiltro != null ? `${taxaFiltro}%` : "—"}
              cor={taxaFiltro != null && taxaFiltro < 70 ? "var(--red)" : "var(--green-light)"}
              rotulo="Taxa de cura"
              title="Calculada só sobre os casos já avaliados (curado? sim/não respondido) — quem nunca respondeu não entra na conta, pra não inflar a taxa artificialmente."
              extra={
                <span style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>
                  {totalComPendentesFiltro > 0
                    ? `calculada sobre ${totalFiltro} de ${totalComPendentesFiltro} caso${totalComPendentesFiltro === 1 ? "" : "s"} avaliados`
                    : "sem casos no filtro"}
                </span>
              }
            />
            <Indicador
              categoria="sanidade"
              valor={naoAvaliados.length}
              cor={naoAvaliados.length > 0 ? "var(--red)" : "var(--green-light)"}
              rotulo="Não avaliados"
              title="Protocolos já encerrados (todas as aplicações do último dia realizadas) sem resposta 'curado?' — some da Agenda depois de 60 dias, mas continua respondível aqui embaixo."
              extra={
                coberturaFiltro != null ? (
                  <span style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>cobertura de avaliação: {coberturaFiltro}%</span>
                ) : null
              }
            />
          </div>

          <SecaoRecolhivel
            titulo="Casos não avaliados"
            badge={<span style={{ fontSize: "0.8rem", color: naoAvaliados.length ? "var(--red)" : "var(--dourado-light)", fontWeight: 400 }}>{naoAvaliados.length}</span>}
            descricao="Protocolos já encerrados sem resposta 'curado? sim/não' — enquanto não forem respondidos, ficam de fora do cálculo da taxa de cura acima. Responda aqui os casos que já saíram da Agenda (mais de 60 dias sem resposta)."
          >
            <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr>
                  <th>Animal</th><th>Tratamento</th><th>Data</th><th>Lote</th><th>Categoria</th><th>Lactação/Seca</th><th>Curado?</th>
                </tr></thead>
                <tbody>
                  {naoAvaliados.slice().sort((a, b) => (b.data || "").localeCompare(a.data || "")).map((c) => {
                    const chave = `${c.origem}-${c.id}`;
                    return (
                      <tr key={chave}>
                        <td style={{ fontWeight: 700 }}>{c.numero}</td>
                        <td style={{ fontSize: "0.8rem" }}>{c.tratamento}</td>
                        <td style={{ fontSize: "0.78rem" }}>{c.data ? formatDate(c.data) : "—"}</td>
                        <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{c.lote || "—"}</td>
                        <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{LABEL_CATEGORIA[c.categoria] || "—"}</td>
                        <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{LABEL_LACTACAO[c.status_lactacao] || "—"}</td>
                        <td>
                          <span className="flex items-center gap-1" style={{ fontSize: "0.72rem" }}>
                            <button className="btn-ghost" style={{ color: "var(--green-light)", padding: "0.1rem 0.4rem" }} disabled={marcando.has(chave)} onClick={() => marcar(c, true)}>Sim</button>
                            <button className="btn-ghost" style={{ color: "var(--red)", padding: "0.1rem 0.4rem" }} disabled={marcando.has(chave)} onClick={() => marcar(c, false)}>Não</button>
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                  {!naoAvaliados.length && <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum caso pendente de avaliação com esses filtros.</td></tr>}
                </tbody>
              </table>
            </div>
          </SecaoRecolhivel>

          <SecaoRecolhivel titulo="Casos" badge={<span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length}</span>}
            descricao="Lista completa dos casos avaliados que atendem aos filtros acima">
            <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr>
                  <th>Animal</th><th>Tratamento</th><th>Data</th><th>Lote</th><th>Categoria</th><th>Lactação/Seca</th><th>Curado?</th>
                </tr></thead>
                <tbody>
                  {filtrados.slice().sort((a, b) => (b.data || "").localeCompare(a.data || "")).map((c) => (
                    <tr key={`${c.origem}-${c.id}`}>
                      <td style={{ fontWeight: 700 }}>{c.numero}</td>
                      <td style={{ fontSize: "0.8rem" }}>{c.tratamento}</td>
                      <td style={{ fontSize: "0.78rem" }}>{c.data ? formatDate(c.data) : "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{c.lote || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{LABEL_CATEGORIA[c.categoria] || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{LABEL_LACTACAO[c.status_lactacao] || "—"}</td>
                      <td style={{ fontWeight: 700, color: c.curada ? "var(--green-light)" : "var(--red)" }}>{c.curada ? "Sim" : "Não"}</td>
                    </tr>
                  ))}
                  {!filtrados.length && <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum caso avaliado com esses filtros.</td></tr>}
                </tbody>
              </table>
            </div>
          </SecaoRecolhivel>

          <SecaoRecolhivel titulo="Comparação do próprio animal ao longo da vida"
            descricao="Só animais com mais de um caso avaliado no filtro atual — a taxa de cura individual ajuda a identificar quem tem recidiva frequente">
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
              Só animais com mais de um caso avaliado no filtro atual — a taxa de cura individual ajuda a identificar quem tem recidiva frequente.
            </p>
            {porAnimal.length ? (
              <table className="fazenda-table">
                <thead><tr><th>Animal</th><th style={{ textAlign: "right" }}>Casos</th><th style={{ textAlign: "right" }}>Curados</th><th style={{ textAlign: "right" }}>Taxa individual</th></tr></thead>
                <tbody>
                  {porAnimal.map((a) => (
                    <tr key={a.numero}>
                      <td style={{ fontWeight: 700 }}>{a.numero}</td>
                      <td style={{ textAlign: "right" }}>{a.casos}</td>
                      <td style={{ textAlign: "right", color: "var(--green-light)" }}>{a.curados}</td>
                      <td style={{ textAlign: "right", fontWeight: 700, color: a.taxa < 70 ? "var(--red)" : "var(--green-light)" }}>{a.taxa}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum animal com mais de um caso no filtro atual.</p>
            )}
          </SecaoRecolhivel>
        </>
      )}
    </>
  );
}

const inputStyleRastreabilidade: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem",
};
const COLUNAS_RASTREABILIDADE = [
  { header: "Animal", key: "numero_animal" }, { header: "Nome", key: "nome_animal" },
  { header: "Tipo de evento", key: "tipo_evento" }, { header: "Data", key: "dataFmt" },
  { header: "GTA", key: "gta" }, { header: "Descrição", key: "descricao" },
  { header: "Produto", key: "produto" }, { header: "Resultado", key: "resultado" },
  { header: "Doença", key: "doenca" }, { header: "Responsável", key: "responsavel" },
  { header: "Contraparte", key: "contraparte" },
];

/**
 * Rastreabilidade sanitária (Sanidade > Rastreabilidade) — a resposta a "esse
 * animal, com essa GTA, teve qual histórico sanitário?": linha do tempo com
 * as GTAs de compra/venda do animal, aplicações, protocolos sanitários,
 * exames e doenças/ocorrências clínicas, filtrável por animal, período ou
 * número de GTA. Não emite GTA (documento oficial do órgão estadual) — só
 * consulta o que já foi lançado em Lançamentos > Compra/Venda de animal e
 * nas telas de Sanidade.
 */
function RastreabilidadeSanitariaView() {
  const [numero, setNumero] = useState("");
  const [gta, setGta] = useState("");
  const [dataDe, setDataDe] = useState("");
  const [dataAte, setDataAte] = useState("");
  const [linhas, setLinhas] = useState<LinhaRastreabilidadeSanitaria[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [buscou, setBuscou] = useState(false);

  const buscar = () => {
    setCarregando(true); setErro(null); setBuscou(true);
    fetchRastreabilidadeSanitaria({ numero, gta, dataDe, dataAte })
      .then(setLinhas)
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  };

  const linhasExport = useMemo(() => (linhas ?? []).map((l) => ({ ...l, dataFmt: formatDate(l.data) })), [linhas]);
  const animaisDistintos = useMemo(() => new Set((linhas ?? []).map((l) => l.numero_animal)).size, [linhas]);
  const gtasEncontrados = useMemo(() => Array.from(new Set((linhas ?? []).map((l) => l.gta).filter(Boolean))) as string[], [linhas]);

  const CORES_EVENTO: Record<string, string> = {
    "Compra": "var(--red)", "Venda": "var(--green-light)", "Aplicação sanitária": "var(--dourado-light)",
    "Protocolo sanitário": "var(--blue)", "Exame": "var(--amber)", "Doença (ocorrência clínica)": "var(--red)", "Baixa": "var(--text-muted)",
  };

  return (
    <>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
          Reconstrói a cadeia sanitária de um animal (ou de uma GTA): compra/venda com GTA, aplicações
          sanitárias, protocolos, exames e doenças registradas — em ordem cronológica. Informe ao menos
          o número do animal, a GTA ou um período.
        </p>
        <div className="flex flex-wrap gap-3 items-end">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Número do animal</label>
            <input style={inputStyleRastreabilidade} value={numero} onChange={(e) => setNumero(e.target.value)} placeholder="ex.: 950" /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>GTA</label>
            <input style={inputStyleRastreabilidade} value={gta} onChange={(e) => setGta(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>De</label>
            <input type="date" style={inputStyleRastreabilidade} value={dataDe} onChange={(e) => setDataDe(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Até</label>
            <input type="date" style={inputStyleRastreabilidade} value={dataAte} onChange={(e) => setDataAte(e.target.value)} /></div>
          <button className="btn-primary" style={{ fontSize: "0.8rem" }} onClick={buscar} disabled={carregando}>
            <Search size={13} /> {carregando ? "Buscando…" : "Buscar"}
          </button>
        </div>
      </div>

      {erro && <div className="alert-critico mb-4"><span>{erro}</span></div>}

      {!buscou && !erro && (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Informe um filtro e clique em Buscar.</p>
      )}

      {linhas && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
            <Indicador categoria="geral" valor={String(linhas.length)} rotulo="Eventos" />
            <Indicador categoria="geral" valor={String(animaisDistintos)} rotulo="Animais" />
            <Indicador categoria="geral" valor={String(gtasEncontrados.length)} rotulo="GTAs distintas" />
          </div>
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>Linha do tempo sanitária</div>
              <ExportarBotoes titulo="Rastreabilidade sanitária" colunas={COLUNAS_RASTREABILIDADE} linhas={linhasExport} nomeArquivoBase="rastreabilidade_sanitaria" disabled={!linhas.length} />
            </div>
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead><tr>
                  <th>Animal</th><th>Evento</th><th>Data</th><th>GTA</th><th>Descrição</th><th>Produto</th>
                  <th>Resultado</th><th>Doença</th><th>Responsável</th><th>Contraparte</th>
                </tr></thead>
                <tbody>
                  {linhas.map((l, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 700 }}>{l.numero_animal}{l.nome_animal ? ` · ${l.nome_animal}` : ""}</td>
                      <td>
                        <span style={{
                          fontSize: "0.72rem", padding: "0.15rem 0.5rem", borderRadius: "999px", fontWeight: 700,
                          color: CORES_EVENTO[l.tipo_evento] || "var(--text)",
                        }}>{l.tipo_evento}</span>
                      </td>
                      <td style={{ fontSize: "0.8rem" }}>{formatDate(l.data)}</td>
                      <td style={{ fontSize: "0.78rem", fontWeight: l.gta ? 700 : 400, color: l.gta ? "var(--dourado-light)" : "var(--text-muted)" }}>{l.gta || "—"}</td>
                      <td style={{ fontSize: "0.8rem" }}>{l.descricao || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.produto || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.resultado || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.doenca || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.responsavel || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.contraparte || "—"}</td>
                    </tr>
                  ))}
                  {!linhas.length && <tr><td colSpan={10} style={{ color: "var(--text-muted)", padding: "1rem" }}>Nenhum evento sanitário encontrado para o filtro.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  );
}

type AbaSanidade = "curativa" | "preventiva" | "rastreabilidade" | "catalogo";
const ABAS_SANIDADE = [
  { id: "curativa", label: "Curativa", icon: HeartPulse, title: "Tratamentos curativos: aplicações, doença/motivo e protocolos" },
  { id: "preventiva", label: "Preventiva", icon: Shield, title: "Vacinas e exames (somente leitura): painel, animais na janela, calendário sanitário, aplicações e histórico" },
  { id: "rastreabilidade", label: "Rastreabilidade", icon: Route, title: "Rastreabilidade sanitária/GTA: linha do tempo por animal ou por GTA" },
  { id: "catalogo", label: "Catálogo", icon: BookOpen, title: "Catálogo de farmácia mantido pelo Painel CowData — indicações, princípios ativos e marcas, com bula e carência (somente consulta)" },
] as const satisfies readonly { id: AbaSanidade; label: string; icon: any; title: string }[];

type AbaCurativa = "curativo" | "doenca" | "remedios" | "protocolos" | "taxa_cura";
const ABAS_CURATIVA = [
  { id: "curativo", label: "Curativo (aplicações)", icon: ClipboardList, title: "Medicamentos aplicados no rebanho" },
  { id: "doenca", label: "Doença / Motivo", icon: Activity, title: "Tratamentos por doença/motivo" },
  { id: "remedios", label: "Remédios por doença", icon: FlaskConical, title: "Ranking de medicamentos indicados por doença, com estoque ao vivo" },
  { id: "protocolos", label: "Protocolos sanitários", icon: ListChecks, title: "Protocolos multi-etapa lançados (mastite e outros)" },
  { id: "taxa_cura", label: "Taxa de cura", icon: Percent, title: "Taxa de cura dos tratamentos (aplicações e protocolos)" },
] as const satisfies readonly { id: AbaCurativa; label: string; icon: any; title: string }[];

// Sanidade › Preventiva — Sanitário Preventivo v2 (vacinas e exames). As cinco
// abas são só consulta; agendar e executar fica na Central de Protocolos ›
// Vacinas e exames. Atalho: /sanidade?aba=preventiva&sub=janela&caixa=3.
const PainelPreventivo = dynamic(() => import("@/components/sanitario/consulta/PainelPreventivo").then((m) => m.PainelPreventivo), { ssr: false });
const AnimaisNaJanela = dynamic(() => import("@/components/sanitario/consulta/AnimaisNaJanela").then((m) => m.AnimaisNaJanela), { ssr: false });
const CalendarioPreventivo = dynamic(() => import("@/components/sanitario/consulta/CalendarioPreventivo").then((m) => m.CalendarioPreventivo), { ssr: false });
const AplicacoesPreventivas = dynamic(() => import("@/components/sanitario/consulta/AplicacoesPreventivas").then((m) => m.AplicacoesPreventivas), { ssr: false });
const HistoricoPreventivo = dynamic(() => import("@/components/sanitario/consulta/HistoricoPreventivo").then((m) => m.HistoricoPreventivo), { ssr: false });
type AbaPreventiva = "painel" | "janela" | "calendario" | "aplicacoes" | "historico";
const ABAS_PREVENTIVA = [
  { id: "painel", label: "Painel", icon: LayoutDashboard, title: "Resumo dos próximos 30 dias: cobertura, atrasadas, carência e prazos legais" },
  { id: "janela", label: "Animais na janela", icon: ListChecks, title: "Animais dentro da janela de cada vacina ou exame" },
  { id: "calendario", label: "Calendário sanitário", icon: CalendarClock, title: "Vacinas e exames previstos, em lista ou por mês" },
  { id: "aplicacoes", label: "Aplicações", icon: ClipboardList, title: "Vacinas e exames já registrados" },
  { id: "historico", label: "Histórico", icon: History, title: "Histórico por animal ou por vacina/exame" },
] as const satisfies readonly { id: AbaPreventiva; label: string; icon: any; title: string }[];

export default function SanidadePage() {
  const [aba, setAba] = useState<AbaSanidade>("curativa");
  const [abaCur, setAbaCur] = useState<AbaCurativa>("curativo");
  const [abaPrev, setAbaPrev] = useState<AbaPreventiva>("painel");
  const [caixaJanela, setCaixaJanela] = useState<number | null>(null);
  // Atalho de fora (?aba=preventiva&sub=painel|janela|calendario|aplicacoes|historico&caixa=ID) —
  // o card "Vacinas previstas" da Agenda e a Central apontam para cá.
  useEffect(() => {
    // fora do corpo síncrono do efeito: só aplica a escolha vinda do link
    const t = setTimeout(() => {
      const q = new URLSearchParams(window.location.search);
      const a = q.get("aba");
      if (a && ABAS_SANIDADE.some((x) => x.id === a)) setAba(a as AbaSanidade);
      const sub = q.get("sub");
      if (a === "preventiva" && sub && ABAS_PREVENTIVA.some((x) => x.id === sub)) setAbaPrev(sub as AbaPreventiva);
      const cx = Number(q.get("caixa"));
      if (Number.isInteger(cx) && cx > 0) setCaixaJanela(cx);
    }, 0);
    return () => clearTimeout(t);
  }, []);

  const subNavTree: SubNavNode[] = useMemo(() => ABAS_SANIDADE.map((a) => ({
    id: a.id, label: a.label, icon: a.icon,
    children: a.id === "curativa"
      ? ABAS_CURATIVA.map((c) => ({ id: c.id, label: c.label, icon: c.icon }))
      : a.id === "preventiva"
        ? ABAS_PREVENTIVA.map((p) => ({ id: p.id, label: p.label, icon: p.icon }))
        : undefined,
  })), []);
  const onSelectSubNav = useCallback((id: string) => {
    if (ABAS_CURATIVA.some((c) => c.id === id)) { setAba("curativa"); setAbaCur(id as AbaCurativa); }
    else if (ABAS_PREVENTIVA.some((p) => p.id === id)) { setAba("preventiva"); setAbaPrev(id as AbaPreventiva); }
    else setAba(id as AbaSanidade);
  }, []);
  useSubNavRegister(useMemo(() => ({
    tree: subNavTree,
    activeId: aba === "curativa" ? abaCur : aba === "preventiva" ? abaPrev : aba,
    onSelect: onSelectSubNav,
  }), [subNavTree, aba, abaCur, abaPrev, onSelectSubNav]));

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Syringe size={22} style={{ color: "var(--dourado)" }} /> Sanidade</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Sanidade curativa e preventiva. O relatório de BST fica em Produção › Relatórios de BST; para lançar/agendar uma aplicação, use Lançamentos › Produção › BST.</p>
      </div>

      {aba === "curativa" && (
        <>
          {abaCur === "curativo" && <AplicacoesView />}
          {abaCur === "doenca" && <DoencaMotivoView />}
          {abaCur === "remedios" && <RemediosPorDoenca />}
          {abaCur === "protocolos" && <ProtocolosSanitariosView />}
          {abaCur === "taxa_cura" && <TaxaCuraView />}
        </>
      )}
      {aba === "preventiva" && (
        <>
          <p style={{ color: "var(--text-muted)", fontSize: "0.82rem", marginBottom: "0.8rem" }}>
            Só consulta. Para marcar ou aplicar uma vacina ou exame, use a Central de Protocolos › Vacinas e exames.
          </p>
          {abaPrev === "painel" && <PainelPreventivo />}
          {abaPrev === "janela" && <AnimaisNaJanela key={caixaJanela ?? 0} caixaInicial={caixaJanela} />}
          {abaPrev === "calendario" && <CalendarioPreventivo />}
          {abaPrev === "aplicacoes" && <AplicacoesPreventivas />}
          {abaPrev === "historico" && <HistoricoPreventivo />}
        </>
      )}
      {aba === "rastreabilidade" && <RastreabilidadeSanitariaView />}
      {aba === "catalogo" && <CatalogoFarmaciaConsulta />}
    </div>
  );
}
