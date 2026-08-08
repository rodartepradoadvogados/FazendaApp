"use client";
import { useEffect, useMemo, useState } from "react";
import { Search, Trash2, Pencil, AlertTriangle, X, Check, Clock, ThumbsUp, ThumbsDown } from "lucide-react";
import {
  fetchTiposExclusao, buscarExclusao, impactoExclusao, confirmarExclusao,
  fetchPendentesExclusao, aprovarExclusao, rejeitarExclusao, ehAdmin, formatDate,
} from "@/lib/api";
import { usePaginacao, Paginacao } from "@/components/Paginacao";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

// Para onde mandar o usuário ao clicar "Editar" num registro filtrado — cada
// tipo já tem um lugar próprio no site que permite editar (ou pelo menos
// localizar) aquele lançamento; "todos_lancamentos" resolve pelo tipo_real
// de cada linha (ver DESTINO_EDITAR abaixo, no map de resultados).
const DESTINO_EDITAR: Record<string, string> = {
  animal: "/rebanho?aba=ficha&numero=",
  servico: "/lancamentos?ir=inseminacao",
  parto: "/lancamentos?ir=parto",
  controle: "/lancamentos?ir=controle",
  sanidade: "/lancamentos?ir=sanidade_aplicacao",
  protocolo_sanitario_lancamento: "/lancamentos?ir=protocolo_sanitario",
  protocolo_iatf_lancamento: "/lancamentos?ir=protocolo_iatf",
  financeiro: "/financeiro",
  compra_animal: "/lancamentos?ir=comprar_animal",
  compra_semen: "/lancamentos?ir=comprar_semen",
  venda_animal: "/lancamentos?ir=vender_animal",
  estoque: "/lancamentos?ir=estoque_entradas_saidas",
  evento_manual: "/agenda",
  calendario_sanitario: "/lancamentos?ir=calendario_sanitario",
  lote: "/configuracoes?aba=cadastro",
  fornecedor: "/configuracoes?aba=cadastro",
  motivo_movimentacao: "/configuracoes?aba=cadastro",
  pessoa: "/configuracoes?aba=cadastro",
  principio_ativo: "/configuracoes?aba=cadastro",
  doenca: "/configuracoes?aba=cadastro",
  evento_sanitario: "/configuracoes?aba=cadastro",
  protocolo_sanitario: "/configuracoes?aba=cadastro",
  safra: "/configuracoes?aba=cadastro&sub=safra",
};
// "animal" é o único destino que precisa do id do próprio registro (número
// do animal) anexado à URL — os demais levam à listagem do tipo, onde o
// usuário localiza e edita o lançamento certo.
function destinoEditar(tipoReal: string, id: string): string | null {
  const base = DESTINO_EDITAR[tipoReal];
  if (!base) return null;
  return tipoReal === "animal" ? `${base}${encodeURIComponent(id)}` : base;
}

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};

type Candidato = { id: string; titulo: string; subtitulo: string; tipo_real?: string };
// `sem_filtro_data` vem do backend (GET /exclusoes/tipos) desde a Fase 0 do
// registro extensível de tipos — antes disso era uma lista fixa duplicada
// aqui (TIPOS_SEM_DATA), que ficava desatualizada a cada tipo novo.
type Tipo = { id: string; label: string; sem_filtro_data: boolean };
type Pendente = { id: number; tipo: string; id_alvo: string; titulo: string | null; solicitado_por: string | null; criado_em: string };

/**
 * Aba de Exclusão: escolhe o tipo de registro, busca e seleciona o alvo, e
 * antes de excluir mostra tudo o que será impactado — só então confirma.
 * Administradores excluem na hora; os demais usuários só registram uma
 * solicitação, que fica pendente de aprovação (ver painel abaixo, admin-only).
 */
export function FormExclusao({ ocultarTipos }: { ocultarTipos?: string[] } = {}) {
  const [tipos, setTipos] = useState<Tipo[]>([]);
  const [tipo, setTipo] = useState("");
  const [termo, setTermo] = useState("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [resultados, setResultados] = useState<Candidato[]>([]);
  const [buscando, setBuscando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [alvo, setAlvo] = useState<Candidato | null>(null);
  const [tipoAlvo, setTipoAlvo] = useState<string>("");
  const [impacto, setImpacto] = useState<string[] | null>(null);
  const [carregandoImpacto, setCarregandoImpacto] = useState(false);
  const [excluindo, setExcluindo] = useState(false);

  const [souAdmin, setSouAdmin] = useState(false);
  const [pendentes, setPendentes] = useState<Pendente[] | null>(null);
  const [decidindo, setDecidindo] = useState<number | null>(null);

  const ordResultados = useOrdenacao(resultados);
  const pagResultados = usePaginacao(ordResultados.linhasOrdenadas);

  const carregarPendentes = () => {
    if (!ehAdmin()) return;
    fetchPendentesExclusao().then(setPendentes).catch(() => {});
  };
  useEffect(() => {
    setSouAdmin(ehAdmin());
    carregarPendentes();
  }, []);

  const aprovar = async (id: number) => {
    setDecidindo(id);
    try { await aprovarExclusao(id); carregarPendentes(); }
    catch (e: any) { setErro(e.message); }
    finally { setDecidindo(null); }
  };
  const rejeitar = async (id: number) => {
    setDecidindo(id);
    try { await rejeitarExclusao(id); carregarPendentes(); }
    catch (e: any) { setErro(e.message); }
    finally { setDecidindo(null); }
  };

  useEffect(() => {
    fetchTiposExclusao().then((t) => setTipos(ocultarTipos ? t.filter((x: Tipo) => !ocultarTipos.includes(x.id)) : t)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const TIPOS_SEM_DATA = useMemo(
    () => new Set(tipos.filter((t) => t.sem_filtro_data).map((t) => t.id)),
    [tipos],
  );
  const temFiltroData = tipo && !TIPOS_SEM_DATA.has(tipo);

  const buscar = async (t: string, q: string, ini: string, fim: string) => {
    if (!t) { setResultados([]); return; }
    setBuscando(true); setErro(null);
    try { setResultados(await buscarExclusao(t, q, TIPOS_SEM_DATA.has(t) ? "" : ini, TIPOS_SEM_DATA.has(t) ? "" : fim)); }
    catch (e: any) { setErro(e.message); }
    finally { setBuscando(false); }
  };

  useEffect(() => {
    if (!tipo) return;
    const h = setTimeout(() => buscar(tipo, termo, dataInicio, dataFim), 250);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tipo, termo, dataInicio, dataFim]);

  const escolher = async (c: Candidato) => {
    const tipoReal = c.tipo_real || tipo;
    setAlvo(c); setTipoAlvo(tipoReal); setImpacto(null); setErro(null); setMsg(null); setCarregandoImpacto(true);
    try { setImpacto((await impactoExclusao(tipoReal, String(c.id))).impacto); }
    catch (e: any) { setErro(e.message); setAlvo(null); }
    finally { setCarregandoImpacto(false); }
  };

  const excluir = async () => {
    if (!alvo) return;
    setExcluindo(true); setErro(null);
    try {
      const r = await confirmarExclusao(tipoAlvo, String(alvo.id));
      setMsg(r.status === "excluido" ? `Excluído: ${alvo.titulo}` : `Solicitação enviada: ${alvo.titulo}. Aguarda aprovação de um administrador.`);
      setAlvo(null); setImpacto(null);
      buscar(tipo, termo, dataInicio, dataFim);
    } catch (e: any) { setErro(e.message); }
    finally { setExcluindo(false); }
  };

  return (
    <>
      <div className="alert-critico mb-3" style={{ alignItems: "flex-start" }}>
        <AlertTriangle size={16} style={{ marginTop: "0.1rem", flexShrink: 0 }} />
        <span>
          {souAdmin
            ? "Exclusão é permanente. Escolha o tipo, encontre o registro e confira o impacto antes de confirmar."
            : "Escolha o tipo, encontre o registro e confira o impacto — a exclusão fica pendente de aprovação de um administrador."}
        </span>
      </div>

      {souAdmin && (
        <div className="card mb-3">
          <div className="card-header mb-2 flex items-center gap-2"><Clock size={14} /> Pendências de exclusão {pendentes ? `(${pendentes.length})` : ""}</div>
          {!pendentes?.length ? (
            <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Nenhuma solicitação pendente.</p>
          ) : (
            <div className="space-y-2">
              {pendentes.map((p) => (
                <div key={p.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", padding: "0.5rem 0.7rem", border: "1px solid var(--border)", borderRadius: "var(--r-sm)" }}>
                  <div>
                    <div style={{ fontSize: "0.85rem", fontWeight: 700 }}>{p.titulo || `${p.tipo} #${p.id_alvo}`}</div>
                    <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                      Solicitado por {p.solicitado_por || "—"} em {formatDate(p.criado_em.slice(0, 10))}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button className="btn-primary" style={{ fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
                      onClick={() => aprovar(p.id)} disabled={decidindo === p.id}>
                      <ThumbsUp size={13} /> Aprovar
                    </button>
                    <button className="btn-ghost" style={{ fontSize: "0.75rem", color: "var(--red)", display: "flex", alignItems: "center", gap: "0.3rem" }}
                      onClick={() => rejeitar(p.id)} disabled={decidindo === p.id}>
                      <ThumbsDown size={13} /> Rejeitar
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        <div>
          <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Tipo de lançamento</label>
          <select style={inputStyle} value={tipo} onChange={(e) => { setTipo(e.target.value); setTermo(""); setDataInicio(""); setDataFim(""); setAlvo(null); setImpacto(null); }}>
            <option value="">Selecione…</option>
            {tipos.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
        </div>
        {temFiltroData && (
          <>
            <div>
              <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Data de</label>
              <input type="date" style={inputStyle} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} />
            </div>
            <div>
              <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Data até</label>
              <input type="date" style={inputStyle} value={dataFim} onChange={(e) => setDataFim(e.target.value)} />
            </div>
          </>
        )}
      </div>

      {tipo && (
        <div className="mb-3" style={{ maxWidth: "420px" }}>
          <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Buscar (refina o resultado acima)</label>
          <div style={{ position: "relative" }}>
            <Search size={14} style={{ position: "absolute", left: 9, top: 10, color: "var(--text-muted)" }} />
            <input style={{ ...inputStyle, paddingLeft: "2rem" }} value={termo} onChange={(e) => setTermo(e.target.value)} placeholder="lote, medicamento, ação, número, nome…" />
          </div>
        </div>
      )}

      {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.6rem" }}>{erro}</p>}
      {msg && <p style={{ color: "var(--green-light)", fontSize: "0.82rem", marginBottom: "0.6rem" }}>{msg}</p>}

      {tipo && (
        <div className="card" style={{ padding: 0 }}>
          <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead><tr><ThOrdenavel label="Registro" campo="titulo" coluna={ordResultados.coluna} dir={ordResultados.dir} ordenar={ordResultados.ordenar} /><th></th></tr></thead>
              <tbody>
                {pagResultados.linhasPagina.map((c) => (
                  <tr key={`${c.tipo_real || tipo}-${c.id}`}>
                    <td>
                      <div style={{ fontWeight: 700, fontSize: "0.85rem" }}>{c.titulo}</div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        {c.tipo_real && <span style={{ color: "var(--dourado-light)", fontWeight: 600 }}>{tipos.find((t) => t.id === c.tipo_real)?.label || c.tipo_real} · </span>}
                        {c.subtitulo}
                      </div>
                    </td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {(() => {
                        const href = destinoEditar(c.tipo_real || tipo, String(c.id));
                        return href ? (
                          <a href={href} className="btn-ghost" style={{ fontSize: "0.75rem", marginRight: "0.4rem", display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
                            <Pencil size={13} /> Editar
                          </a>
                        ) : null;
                      })()}
                      <button className="btn-ghost" style={{ color: "var(--red)", fontSize: "0.75rem" }} onClick={() => escolher(c)}>
                        <Trash2 size={13} /> Excluir
                      </button>
                    </td>
                  </tr>
                ))}
                {!buscando && !resultados.length && (
                  <tr><td colSpan={2} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1.5rem" }}>Nenhum registro encontrado.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          {resultados.length > 0 && (
            <div style={{ padding: "0 0.7rem 0.6rem" }}>
              <Paginacao pagina={pagResultados.pagina} totalPaginas={pagResultados.totalPaginas} totalLinhas={pagResultados.totalLinhas}
                tamanhoPagina={pagResultados.tamanhoPagina} onMudarPagina={pagResultados.setPagina} onMudarTamanho={pagResultados.setTamanhoPagina} />
            </div>
          )}
        </div>
      )}

      {alvo && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "460px", maxWidth: "95vw" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0, color: "var(--red)" }}>{souAdmin ? "Confirmar exclusão" : "Solicitar exclusão"}</div>
              <button onClick={() => { setAlvo(null); setImpacto(null); }} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
            </div>
            <div style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.7rem", marginBottom: "0.7rem", background: "var(--surface-2)" }}>
              <div style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "0.3rem" }}>Confira o lançamento</div>
              <p style={{ fontSize: "0.86rem", fontWeight: 700, marginBottom: "0.15rem" }}>{alvo.titulo}</p>
              {alvo.subtitulo && <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{alvo.subtitulo}</p>}
            </div>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
              {souAdmin ? "Isto vai excluir permanentemente:" : "Se aprovado por um administrador, isto vai excluir permanentemente:"}
            </p>
            {carregandoImpacto ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Calculando impacto…</p>
            ) : (
              <ul style={{ fontSize: "0.82rem", paddingLeft: "1.1rem", marginBottom: "0.8rem" }}>
                {(impacto || []).map((i, idx) => <li key={idx} style={{ marginBottom: "0.2rem" }}>{i}</li>)}
              </ul>
            )}
            {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{erro}</p>}
            <div className="flex items-center gap-3">
              <button className="btn-primary" style={{ background: "var(--red)" }} onClick={excluir} disabled={excluindo || carregandoImpacto}>
                <Check size={14} /> {excluindo ? "Enviando…" : souAdmin ? "Confirmar exclusão" : "Solicitar exclusão"}
              </button>
              <button className="btn-ghost" onClick={() => { setAlvo(null); setImpacto(null); }}>Cancelar</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
