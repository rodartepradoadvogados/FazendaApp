"use client";
// Últimos acessos + auditoria de atividade — extraído de app/usuarios/page.tsx
// para ser reaproveitado também no app (ver components/mobile/menu/ControleAcesso.tsx).
// Ambas as seções são restritas ao proprietário (ver ehDono() e, no backend,
// fazenda.auth.exigir_dono) — o backend bloqueia qualquer outro usuário, então
// esconder aqui é só para não mostrar um card que sempre erra 403.
import { useEffect, useState } from "react";
import { AlertTriangle, ShieldCheck, Clock, History, Search } from "lucide-react";
import {
  fetchAcessos, fetchAuditoriaOpcoes, fetchAuditoriaAtividades,
  type UsuarioAcesso, type AuditoriaTipo, type AuditoriaUsuario, type AuditoriaItem,
} from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { usePaginacao, Paginacao } from "@/components/Paginacao";
import { SecaoRecolhivel } from "@/components/ui";

const inp: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem" };
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

// `defaultAberta` deixa o chamador decidir: no app (tela dedicada "Acessos e
// Auditoria") o conteúdo é a própria razão da tela e começa aberto; em
// Configurações > Usuários é uma seção secundária abaixo do cadastro de
// usuários, então começa recolhida (ver app/usuarios/page.tsx).
export function RelatorioAcessos({ defaultAberta = true }: { defaultAberta?: boolean }) {
  const [acessos, setAcessos] = useState<UsuarioAcesso[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { fetchAcessos().then(setAcessos).catch((e) => setErro(e.message)); }, []);

  const fmt = (iso: string | null) => iso ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" }) : "Nunca";

  return (
    <div style={{ maxWidth: "40rem" }}>
      <SecaoRecolhivel titulo="Últimos acessos" icon={ShieldCheck} defaultAberta={defaultAberta} descricao="Visível só para você">
        <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.6rem" }}>Visível só para você.</p>
        {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
        {!acessos && !erro && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
        {acessos && (
          <table className="fazenda-table">
            <thead><tr><th>Login</th><th>Nome</th><th><Clock size={12} style={{ display: "inline", marginRight: "0.25rem" }} />Últimos 3 acessos</th></tr></thead>
            <tbody>
              {acessos.map((a) => (
                <tr key={a.id}>
                  <td style={{ fontWeight: 700, verticalAlign: "top" }}>{a.username}{!a.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                  <td style={{ fontSize: "0.8rem", verticalAlign: "top" }}>{a.nome || "—"}</td>
                  <td style={{ fontSize: "0.8rem" }}>
                    {a.ultimos_acessos.length === 0 ? (
                      <span style={{ color: "var(--text-muted)" }}>Nunca</span>
                    ) : (
                      a.ultimos_acessos.map((iso, i) => (
                        <div key={i} style={{ color: i === 0 ? "var(--text)" : "var(--text-muted)", fontWeight: i === 0 ? 700 : 400 }}>{fmt(iso)}</div>
                      ))
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </SecaoRecolhivel>
    </div>
  );
}

export function AuditoriaAtividade({ defaultAberta = true }: { defaultAberta?: boolean }) {
  const [opcoes, setOpcoes] = useState<{ tipos: AuditoriaTipo[]; usuarios: AuditoriaUsuario[] } | null>(null);
  const [erroOpcoes, setErroOpcoes] = useState<string | null>(null);
  useEffect(() => { fetchAuditoriaOpcoes().then(setOpcoes).catch((e) => setErroOpcoes(e.message)); }, []);

  const [usuarioId, setUsuarioId] = useState("");
  const [tipos, setTipos] = useState<Set<string>>(new Set());
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<{ usuario: AuditoriaUsuario; total: number; itens: AuditoriaItem[] } | null>(null);

  const toggleTipo = (chave: string) => setTipos((p) => { const s = new Set(p); s.has(chave) ? s.delete(chave) : s.add(chave); return s; });

  const buscar = async () => {
    if (!usuarioId) return;
    setBuscando(true); setErro(null); setResultado(null);
    try {
      const r = await fetchAuditoriaAtividades({
        usuario_id: Number(usuarioId), data_inicio: dataInicio || undefined, data_fim: dataFim || undefined,
        chaves: tipos.size ? Array.from(tipos) : undefined,
      });
      setResultado(r);
    } catch (e: any) { setErro(e.message); }
    finally { setBuscando(false); }
  };

  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(resultado?.itens || []);
  const pagAtividades = usePaginacao(linhasOrdenadas);
  const fmtData = (iso: string | null) => iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—";

  return (
    <div style={{ maxWidth: "48rem" }}>
      <SecaoRecolhivel titulo="Auditoria de atividade" icon={History} defaultAberta={defaultAberta}
        descricao="Lançamentos feitos por um usuário, em qualquer módulo — visível só para você">
      <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.6rem" }}>Lançamentos feitos por um usuário, em qualquer módulo. Visível só para você.</p>
      {erroOpcoes && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erroOpcoes}</span></div>}
      {!opcoes && !erroOpcoes && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      {opcoes && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
            <div>
              <label style={lbl}>Usuário</label>
              <select style={inp} value={usuarioId} onChange={(e) => setUsuarioId(e.target.value)}>
                <option value="">Selecione…</option>
                {opcoes.usuarios.map((u) => <option key={u.id} value={u.id}>{u.nome || u.username}{!u.ativo ? " (inativo)" : ""}</option>)}
              </select>
            </div>
            <div><label style={lbl}>De</label><input style={inp} type="date" value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} /></div>
            <div><label style={lbl}>Até</label><input style={inp} type="date" value={dataFim} onChange={(e) => setDataFim(e.target.value)} /></div>
          </div>

          <div className="mb-3">
            <div className="flex items-center justify-between mb-1">
              <label style={lbl}>Tipos de lançamento (vazio = todos)</label>
              <div className="flex items-center gap-2">
                {tipos.size < opcoes.tipos.length && <button className="btn-ghost" style={{ fontSize: "0.68rem" }} onClick={() => setTipos(new Set(opcoes.tipos.map((t) => t.chave)))}>Marcar todos</button>}
                {tipos.size > 0 && <button className="btn-ghost" style={{ fontSize: "0.68rem" }} onClick={() => setTipos(new Set())}>Limpar seleção</button>}
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-1" style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.5rem", maxHeight: "9rem", overflowY: "auto" }}>
              {opcoes.tipos.map((t) => (
                <label key={t.chave} className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
                  <input type="checkbox" checked={tipos.has(t.chave)} onChange={() => toggleTipo(t.chave)} /> {t.label}
                </label>
              ))}
            </div>
          </div>

          <button className="btn-primary" onClick={buscar} disabled={!usuarioId || buscando} style={{ marginBottom: "0.8rem" }}>
            <Search size={15} /> {buscando ? "Buscando…" : "Buscar"}
          </button>

          {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}

          {resultado && (
            <>
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
                {resultado.total} lançamento{resultado.total !== 1 ? "s" : ""} de {resultado.usuario.nome || resultado.usuario.username}
                {resultado.total > resultado.itens.length ? ` — mostrando os ${resultado.itens.length} mais recentes` : ""}.
              </p>
              {resultado.itens.length === 0 ? (
                <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum lançamento encontrado no período/filtro.</p>
              ) : (
                <table className="fazenda-table">
                  <thead>
                    <tr>
                      <ThOrdenavel label="Tipo" campo="label" coluna={coluna} dir={dir} ordenar={ordenar} />
                      <ThOrdenavel label="Data" campo="data" coluna={coluna} dir={dir} ordenar={ordenar} />
                      <ThOrdenavel label="Resumo" campo="resumo" coluna={coluna} dir={dir} ordenar={ordenar} />
                    </tr>
                  </thead>
                  <tbody>
                    {pagAtividades.linhasPagina.map((i, idx) => (
                      <tr key={`${i.chave}-${i.id}-${idx}`}>
                        <td style={{ fontSize: "0.8rem" }}>{i.label}</td>
                        <td style={{ fontSize: "0.8rem" }}>{fmtData(i.data)}</td>
                        <td style={{ fontSize: "0.8rem" }}>{i.resumo}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {resultado.itens.length > 0 && (
                <Paginacao pagina={pagAtividades.pagina} totalPaginas={pagAtividades.totalPaginas} totalLinhas={pagAtividades.totalLinhas}
                  tamanhoPagina={pagAtividades.tamanhoPagina} onMudarPagina={pagAtividades.setPagina} onMudarTamanho={pagAtividades.setTamanhoPagina} />
              )}
            </>
          )}
        </>
      )}
      </SecaoRecolhivel>
    </div>
  );
}
