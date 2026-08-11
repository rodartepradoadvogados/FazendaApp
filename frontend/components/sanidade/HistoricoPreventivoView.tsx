"use client";
import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Syringe, Stethoscope, AlertTriangle } from "lucide-react";
import { fetchSanidade, fetchResultadosExame, fetchAnimais, formatDate } from "@/lib/api";
import { MultiFiltro } from "@/components/ui";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { casaBusca } from "@/lib/busca";

type LinhaHistorico = {
  tipo: "vacina" | "exame";
  numero: string;
  categoriaAnimal: string | null;
  lote: string | null;
  produto: string;
  diagnostico: string | null;
  data: string | null;
  responsavel: string | null;
};

/**
 * Sanidade > Preventiva > Histórico — visão objetiva do calendário sanitário
 * já realizado: um quadro por vacina/exame (não por lançamento avulso), que
 * expande para o histórico completo com filtros. Reaproveita os dados já
 * expostos por /sanidade/aplicacoes (vacina) e /sanidade/exames/resultados
 * (exame) — nenhum endpoint novo.
 */
export function HistoricoPreventivoView() {
  const [linhas, setLinhas] = useState<LinhaHistorico[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [expandido, setExpandido] = useState<string | null>(null);

  const [fAnimal, setFAnimal] = useState("");
  const [fLote, setFLote] = useState<string[]>([]);
  const [fCategoria, setFCategoria] = useState<string[]>([]);
  const [fProduto, setFProduto] = useState<string[]>([]);
  const [fDiagnostico, setFDiagnostico] = useState<string[]>([]);

  useEffect(() => {
    Promise.all([fetchSanidade(), fetchResultadosExame(), fetchAnimais()])
      .then(([sanidadeResp, exames, animais]: [any, any[], any[]]) => {
        const animalPorNumero = new Map(animais.map((a: any) => [a.numero, a]));
        const vacinas: LinhaHistorico[] = (sanidadeResp.aplicacoes || [])
          .filter((a: any) => a.natureza === "preventivo" && a.categoria === "Vacina")
          .map((a: any) => ({
            tipo: "vacina" as const, numero: a.numero, categoriaAnimal: a.categoria_animal, lote: a.lote,
            produto: a.produto, diagnostico: null, data: a.data, responsavel: a.responsavel,
          }));
        const examesLinhas: LinhaHistorico[] = exames.map((e: any) => {
          const animal = animalPorNumero.get(e.numero_matriz);
          return {
            tipo: "exame" as const, numero: e.numero_matriz,
            categoriaAnimal: animal?.categoria_abrev || animal?.categoria_completa || null,
            lote: animal?.grupo_primario || null,
            produto: e.evento_sanitario_nome || "Exame",
            diagnostico: e.resultado || e.banda || null,
            data: e.data_exame, responsavel: e.veterinario,
          };
        });
        setLinhas([...vacinas, ...examesLinhas]);
      })
      .catch((e) => setErro(e.message));
  }, []);

  const lotesDisponiveis = useMemo(() => Array.from(new Set((linhas || []).map((l) => l.lote).filter((x): x is string => !!x))).sort(), [linhas]);
  const categoriasDisponiveis = useMemo(() => Array.from(new Set((linhas || []).map((l) => l.categoriaAnimal).filter((x): x is string => !!x))).sort(), [linhas]);
  const produtosDisponiveis = useMemo(() => Array.from(new Set((linhas || []).map((l) => l.produto))).sort(), [linhas]);
  const diagnosticosDisponiveis = useMemo(() => Array.from(new Set((linhas || []).map((l) => l.diagnostico).filter((x): x is string => !!x))).sort(), [linhas]);

  const filtradas = useMemo(() => (linhas || []).filter((l) =>
    casaBusca(l.numero, fAnimal) &&
    (!fLote.length || (l.lote && fLote.includes(l.lote))) &&
    (!fCategoria.length || (l.categoriaAnimal && fCategoria.includes(l.categoriaAnimal))) &&
    (!fProduto.length || fProduto.includes(l.produto)) &&
    (!fDiagnostico.length || (l.diagnostico && fDiagnostico.includes(l.diagnostico)))
  ), [linhas, fAnimal, fLote, fCategoria, fProduto, fDiagnostico]);

  // Um quadro por vacina/exame — agrupado pelo nome do produto/exame.
  const quadros = useMemo(() => {
    const mapa = new Map<string, { tipo: "vacina" | "exame"; produto: string; linhas: LinhaHistorico[] }>();
    for (const l of filtradas) {
      const chave = `${l.tipo}::${l.produto}`;
      if (!mapa.has(chave)) mapa.set(chave, { tipo: l.tipo, produto: l.produto, linhas: [] });
      mapa.get(chave)!.linhas.push(l);
    }
    return Array.from(mapa.values()).sort((a, b) => b.linhas.length - a.linhas.length);
  }, [filtradas]);

  if (erro) return <div className="alert-critico"><AlertTriangle size={18} /><span>Sem dados: {erro}.</span></div>;
  if (!linhas) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;

  return (
    <div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.82rem", marginBottom: "0.8rem" }}>
        Vacinas e exames já realizados pelo calendário sanitário preventivo, agrupados por produto/exame — clique num
        quadro para expandir o histórico completo daquela vacina ou exame.
      </p>
      <div className="card mb-3">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <div>
            <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Animal</label>
            <input value={fAnimal} onChange={(e) => setFAnimal(e.target.value)} placeholder="nº do animal"
              style={{ width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: "0.4rem 0.6rem", fontSize: "0.82rem" }} />
          </div>
          <MultiFiltro label="Lote" opcoes={lotesDisponiveis} selecionados={fLote} onChange={setFLote} />
          <MultiFiltro label="Categoria" opcoes={categoriasDisponiveis} selecionados={fCategoria} onChange={setFCategoria} />
          <MultiFiltro label="Vacina/exame" opcoes={produtosDisponiveis} selecionados={fProduto} onChange={setFProduto} />
          <MultiFiltro label="Diagnóstico/resultado" opcoes={diagnosticosDisponiveis} selecionados={fDiagnostico} onChange={setFDiagnostico} />
        </div>
      </div>

      {!quadros.length && <p style={{ color: "var(--text-muted)" }}>Nenhum registro encontrado com esses filtros.</p>}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {quadros.map((q) => {
          const chave = `${q.tipo}::${q.produto}`;
          const aberto = expandido === chave;
          const ultima = q.linhas.reduce((max, l) => (l.data && (!max || l.data > max) ? l.data : max), "" as string);
          return (
            <div key={chave} className="card" style={{ cursor: "pointer", gridColumn: aberto ? "1 / -1" : undefined }}
              onClick={() => setExpandido(aberto ? null : chave)}>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2" style={{ fontWeight: 700, fontSize: "0.88rem" }}>
                  {q.tipo === "vacina" ? <Syringe size={16} style={{ color: "var(--dourado)" }} /> : <Stethoscope size={16} style={{ color: "var(--dourado)" }} />}
                  {q.produto}
                </span>
                {aberto ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              </div>
              <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginTop: "0.3rem" }}>
                {q.linhas.length} aplicação(ões){ultima ? ` · última em ${formatDate(ultima)}` : ""}
              </p>
              {aberto && <div onClick={(e) => e.stopPropagation()}><TabelaHistorico linhas={q.linhas} /></div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TabelaHistorico({ linhas }: { linhas: LinhaHistorico[] }) {
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(linhas);
  return (
    <div style={{ overflowX: "auto", marginTop: "0.7rem" }}>
      <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
        <thead>
          <tr>
            <ThOrdenavel label="Data" campo="data" coluna={coluna} dir={dir} ordenar={ordenar} />
            <ThOrdenavel label="Animal" campo="numero" coluna={coluna} dir={dir} ordenar={ordenar} />
            <ThOrdenavel label="Lote" campo="lote" coluna={coluna} dir={dir} ordenar={ordenar} />
            <ThOrdenavel label="Categoria" campo="categoriaAnimal" coluna={coluna} dir={dir} ordenar={ordenar} />
            <ThOrdenavel label="Diagnóstico" campo="diagnostico" coluna={coluna} dir={dir} ordenar={ordenar} />
            <ThOrdenavel label="Responsável" campo="responsavel" coluna={coluna} dir={dir} ordenar={ordenar} />
          </tr>
        </thead>
        <tbody>
          {linhasOrdenadas.map((l, i) => (
            <tr key={i}>
              <td>{l.data ? formatDate(l.data) : "—"}</td>
              <td style={{ fontWeight: 700 }}>{l.numero}</td>
              <td>{l.lote || "—"}</td>
              <td>{l.categoriaAnimal || "—"}</td>
              <td>{l.diagnostico || "—"}</td>
              <td>{l.responsavel || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
