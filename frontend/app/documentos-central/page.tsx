"use client";
// Central de Documentos (Administração) — busca unificada e só-leitura sobre
// o Arquivo fiscal-contábil (Configurações/Financeiro > Documentos, aqui só
// pra quem é admin) e os anexos de lançamentos financeiros (fatura, boleto,
// nota fiscal, ordem de serviço, comprovante, orçamento — aqui só pra quem
// tem o módulo financeiro). O backend (GET /documentos-central) decide o que
// cada usuário vê — esta tela só mostra o que voltou, nunca filtra
// visibilidade no cliente.
import { useEffect, useMemo, useState } from "react";
import { FileSearch, Filter, ExternalLink, Landmark, Wallet } from "lucide-react";
import { fetchCentralDocumentos, abrirLinhaCentralDocumento, formatDate, type LinhaCentralDocumento } from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { usePaginacao, Paginacao } from "@/components/Paginacao";

const CATEGORIAS = ["Nota fiscal", "Fatura", "Boleto", "Ordem de serviço", "Comprovante", "Orçamento", "Recibo", "Contrato", "Outros"];

const selStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%",
};

export default function CentralDocumentosPage() {
  const [linhas, setLinhas] = useState<LinhaCentralDocumento[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [categoria, setCategoria] = useState("");
  const [numeroDocumento, setNumeroDocumento] = useState("");
  const [dataDe, setDataDe] = useState("");
  const [dataAte, setDataAte] = useState("");

  const carregar = () => {
    fetchCentralDocumentos({
      categoria: categoria || undefined, numero_documento: numeroDocumento || undefined,
      data_de: dataDe || undefined, data_ate: dataAte || undefined,
    }).then(setLinhas).catch((e) => setError(e.message));
  };

  // Busca no servidor a cada mudança de filtro — a lista já vem filtrada e
  // com o controle de acesso aplicado (nunca filtra no cliente).
  useEffect(() => {
    const t = setTimeout(carregar, numeroDocumento ? 350 : 0);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoria, numeroDocumento, dataDe, dataAte]);

  const ord = useOrdenacao(linhas ?? []);
  const pag = usePaginacao(ord.linhasOrdenadas);

  const limparFiltros = () => { setCategoria(""); setNumeroDocumento(""); setDataDe(""); setDataAte(""); };
  const temFiltro = categoria || numeroDocumento || dataDe || dataAte;

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <FileSearch size={22} style={{ color: "var(--dourado-light)" }} /> Central de Documentos
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Busca por tipo, data ou número — fatura, boleto, nota fiscal, ordem de serviço, comprovante, orçamento e
          demais documentos fiscais, mesmo estando cada um no seu próprio local de origem.
        </p>
      </div>

      {error && <div className="alert-critico mb-4"><span>Sem dados: {error}.</span></div>}

      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Tipo</label>
            <select style={selStyle} value={categoria} onChange={(e) => setCategoria(e.target.value)}>
              <option value="">Todos</option>
              {CATEGORIAS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Número do documento</label>
            <input style={selStyle} value={numeroDocumento} onChange={(e) => setNumeroDocumento(e.target.value)} placeholder="ex.: BOL-00123" /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Período — de</label>
            <input type="date" style={selStyle} value={dataDe} onChange={(e) => setDataDe(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>até</label>
            <input type="date" style={selStyle} value={dataAte} onChange={(e) => setDataAte(e.target.value)} /></div>
        </div>
        {temFiltro && <button className="btn-ghost" style={{ marginTop: "0.75rem", fontSize: "0.75rem" }} onClick={limparFiltros}>Limpar filtros</button>}
      </div>

      <div className="card">
        <div className="card-header mb-3 flex items-center justify-between">
          <span>Documentos</span>
          <span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{linhas?.length ?? 0} no filtro</span>
        </div>
        {!linhas && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
        {linhas && (
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr>
                <ThOrdenavel label="Data" campo="data_documento" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Tipo" campo="categoria" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Documento" campo="nome_arquivo" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Número" campo="numero_documento" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <th>Lançamento</th>
                <th>Origem</th>
                <th style={{ textAlign: "right" }}>Ação</th>
              </tr></thead>
              <tbody>
                {pag.linhasPagina.map((l) => (
                  <tr key={`${l.origem}-${l.id}`}>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{l.data_documento ? formatDate(l.data_documento) : "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{l.categoria || "—"}</td>
                    <td style={{ fontSize: "0.82rem" }}>
                      {l.nome_arquivo}
                      {(l.fornecedor_cliente || l.descricao) && (
                        <div style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>{l.fornecedor_cliente || l.descricao}</div>
                      )}
                    </td>
                    <td style={{ fontSize: "0.78rem" }}>{l.numero_documento || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>
                      {l.numero_lancamento ? (
                        <span title="Número do lançamento financeiro vinculado">{l.numero_lancamento}</span>
                      ) : "—"}
                    </td>
                    <td>
                      <span
                        title={l.origem === "fiscal" ? "Arquivo fiscal-contábil — só administradores" : "Anexo de lançamento — quem tem o módulo financeiro"}
                        style={{
                          display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.7rem",
                          padding: "0.1rem 0.5rem", borderRadius: "999px",
                          background: l.origem === "fiscal" ? "rgba(94,26,46,0.15)" : "rgba(46,125,82,0.12)",
                          color: l.origem === "fiscal" ? "var(--dourado-light)" : "var(--green-light)",
                        }}>
                        {l.origem === "fiscal" ? <Landmark size={11} /> : <Wallet size={11} />}
                        {l.origem === "fiscal" ? "Fiscal" : "Financeiro"}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <a href={abrirLinhaCentralDocumento(l)} target="_blank" rel="noreferrer" title="Abrir documento numa aba nova"
                        style={{ color: "var(--dourado-light)", display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.78rem" }}>
                        Abrir <ExternalLink size={12} />
                      </a>
                    </td>
                  </tr>
                ))}
                {!linhas.length && (
                  <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1.5rem" }}>
                    Nenhum documento encontrado com esses filtros.
                  </td></tr>
                )}
              </tbody>
            </table>
            <Paginacao pagina={pag.pagina} totalPaginas={pag.totalPaginas} totalLinhas={pag.totalLinhas}
              tamanhoPagina={pag.tamanhoPagina} onMudarPagina={pag.setPagina} onMudarTamanho={pag.setTamanhoPagina} />
          </div>
        )}
      </div>
    </div>
  );
}
