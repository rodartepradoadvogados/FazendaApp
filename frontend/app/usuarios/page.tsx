"use client";
import { useEffect, useMemo, useState } from "react";
import { Users, AlertTriangle, UserPlus, Check, Pencil, X, ShieldCheck, Clock, Newspaper, UserSquare2, History, Search } from "lucide-react";
import Link from "next/link";
import {
  fetchUsuarios, criarUsuario, atualizarUsuario, getUsuario, ehDono, fetchAcessos, fetchPessoas, type UsuarioAcesso,
  fetchAuditoriaOpcoes, fetchAuditoriaAtividades, type AuditoriaTipo, type AuditoriaUsuario, type AuditoriaItem,
} from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

const MODULOS = [
  { key: "capa", label: "Capa" }, { key: "indicadores", label: "Indicadores" }, { key: "agenda", label: "Agenda" },
  { key: "lancamentos", label: "Lançamentos" }, { key: "reproducao", label: "Reprodução" }, { key: "analise", label: "Análise Repr." },
  { key: "vet", label: "Agenda do veterinário" },
  { key: "rebanho", label: "Rebanho" }, { key: "producao", label: "Produção" }, { key: "alimentacao", label: "Alimentação" },
  { key: "sanidade", label: "Sanidade" }, { key: "financeiro", label: "Financeiro" }, { key: "estoque", label: "Sanidade/Estoque" },
  { key: "pedidos", label: "Pedidos" },
  { key: "parametros", label: "Parâmetros" }, { key: "upload", label: "Upload" },
];
const TODOS = MODULOS.map((m) => m.key);

const inp: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem" };
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

export default function UsuariosPage() {
  const [usuarios, setUsuarios] = useState<any[] | null>(null);
  const [pessoas, setPessoas] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [username, setUsername] = useState("");
  const [pessoaId, setPessoaId] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [papel, setPapel] = useState<"admin" | "operador">("operador");
  const [perms, setPerms] = useState<Set<string>>(new Set(TODOS));
  const [podePublicarBlog, setPodePublicarBlog] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [editando, setEditando] = useState<any | null>(null);

  const carregar = () => fetchUsuarios().then(setUsuarios).catch((e) => setError(e.message));
  const carregarPessoas = () => fetchPessoas().then(setPessoas).catch(() => {});
  useEffect(() => { carregar(); carregarPessoas(); }, []);

  // Pessoas já vinculadas a algum usuário não podem ser escolhidas de novo
  // (regra de 1 pessoa por login, ver auth.py::_validar_pessoa_do_usuario).
  const pessoasDisponiveis = useMemo(() => {
    const vinculadas = new Set((usuarios || []).map((u) => u.pessoa_id).filter(Boolean));
    return (pessoas || []).filter((p) => p.ativo && !vinculadas.has(p.id));
  }, [pessoas, usuarios]);

  const toggle = (k: string) => setPerms((p) => { const s = new Set(p); s.has(k) ? s.delete(k) : s.add(k); return s; });

  const criar = async () => {
    setSalvando(true); setError(null); setMsg(null);
    try {
      await criarUsuario({
        username: username.trim(), senha, pessoa_id: Number(pessoaId), email: email.trim() || undefined, papel,
        permissoes: papel === "admin" ? TODOS : Array.from(perms), pode_publicar_materias_blog: podePublicarBlog,
      });
      setMsg(`Usuário "${username}" criado.`);
      setUsername(""); setPessoaId(""); setEmail(""); setSenha(""); setPapel("operador"); setPerms(new Set(TODOS)); setPodePublicarBlog(false);
      carregar(); carregarPessoas();
    } catch (e: any) { setError(e.message); }
    finally { setSalvando(false); }
  };

  const toggleAtivo = async (u: any) => {
    try { await atualizarUsuario(u.id, { ativo: !u.ativo }); carregar(); }
    catch (e: any) { setError(e.message); }
  };

  const meuId = getUsuario()?.id;

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Users size={22} style={{ color: "var(--dourado-light)" }} /> Usuários</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Cadastre usuários e defina a que cada um tem acesso. Só administradores veem esta tela.</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>{error}</span></div>}
      {msg && <div className="card mb-4" style={{ borderLeft: "3px solid var(--green)", color: "var(--green-light)", fontSize: "0.85rem" }}>{msg}</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Novo usuário */}
        <div className="card">
          <div className="card-header mb-3 flex items-center gap-2"><UserPlus size={14} /> Novo usuário</div>
          <div className="space-y-3">
            <div><label style={lbl}>Usuário (login)</label><input style={inp} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" /></div>
            <div>
              <div className="flex items-center justify-between">
                <label style={lbl}>Pessoa</label>
                <Link href="/configuracoes?aba=cadastro&sub=pessoas" className="btn-ghost" style={{ fontSize: "0.68rem", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                  <UserSquare2 size={12} /> Cadastre a pessoa primeiro
                </Link>
              </div>
              <select style={inp} value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
                <option value="">Selecione…</option>
                {pessoasDisponiveis.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
              </select>
              <p style={{ fontSize: "0.66rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                Todo login precisa ser de uma pessoa já cadastrada em Configurações &gt; Cadastro &gt; Pessoas.
              </p>
            </div>
            <div><label style={lbl}>E-mail (opcional)</label><input style={inp} type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
            <div><label style={lbl}>Senha</label><input style={inp} type="text" value={senha} onChange={(e) => setSenha(e.target.value)} /></div>
            <div><label style={lbl}>Tipo</label>
              <select style={inp} value={papel} onChange={(e) => setPapel(e.target.value as any)}>
                <option value="admin">Administrador (acesso total + gerencia usuários)</option>
                <option value="operador">Operador (você escolhe os módulos)</option>
              </select>
            </div>

            {papel === "operador" && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label style={lbl}>Módulos liberados</label>
                  <div className="flex gap-2">
                    <button className="btn-ghost" style={{ fontSize: "0.68rem" }} onClick={() => setPerms(new Set(TODOS))}>Acesso total</button>
                    <button className="btn-ghost" style={{ fontSize: "0.68rem" }} onClick={() => setPerms(new Set(TODOS.filter((k) => k !== "financeiro")))}>Sem financeiro</button>
                    <button className="btn-ghost" style={{ fontSize: "0.68rem" }} onClick={() => setPerms(new Set(["capa"]))}>Limpar</button>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-1" style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.5rem" }}>
                  {MODULOS.map((m) => (
                    <label key={m.key} className="flex items-center gap-2" style={{ fontSize: "0.8rem", opacity: m.key === "capa" ? 0.7 : 1 }}>
                      <input type="checkbox" checked={perms.has(m.key)} disabled={m.key === "capa"} onChange={() => toggle(m.key)} /> {m.label}
                    </label>
                  ))}
                </div>
                <p style={{ fontSize: "0.66rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>A Capa fica sempre liberada. O Financeiro é bloqueado de verdade (dados e tela) para quem não tiver o módulo.</p>
              </div>
            )}

            <div style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.6rem 0.7rem" }}>
              <label className="flex items-center gap-2" style={{ fontSize: "0.82rem" }}>
                <input type="checkbox" checked={podePublicarBlog} onChange={(e) => setPodePublicarBlog(e.target.checked)} />
                <Newspaper size={14} /> Permitir publicação de matérias no blog (News)
              </label>
              <p style={{ fontSize: "0.66rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                Independente do tipo de acesso — todo usuário nasce sem essa permissão, mesmo administrador.
              </p>
            </div>

            <button className="btn-primary" onClick={criar} disabled={salvando || !username || !senha || !pessoaId} style={{ width: "100%", justifyContent: "center" }}>
              <Check size={16} /> Criar usuário
            </button>
          </div>
        </div>

        {/* Lista */}
        <div className="card">
          <div className="card-header mb-3">Usuários cadastrados</div>
          {!usuarios ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : (
            <table className="fazenda-table">
              <thead><tr><th>Login</th><th>Nome</th><th>Acesso</th><th>Ativo</th><th></th></tr></thead>
              <tbody>
                {usuarios.map((u) => (
                  <tr key={u.id}>
                    <td style={{ fontWeight: 700 }}>{u.username}</td>
                    <td style={{ fontSize: "0.8rem" }}>{u.nome || "—"}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      {u.papel === "admin" ? "Administrador (tudo)" : `${(u.permissoes || []).length} módulos${(u.permissoes || []).includes("financeiro") ? "" : " · sem financeiro"}`}
                    </td>
                    <td>
                      <button onClick={() => toggleAtivo(u)} className="btn-ghost" style={{ fontSize: "0.7rem", color: u.ativo ? "var(--green-light)" : "var(--red)" }} disabled={u.id === meuId}>
                        {u.ativo ? "Ativo" : "Inativo"}
                      </button>
                    </td>
                    <td>
                      <button onClick={() => setEditando(u)} className="btn-ghost" style={{ fontSize: "0.7rem" }}><Pencil size={13} /> Editar</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {ehDono() && <RelatorioAcessos />}
      {ehDono() && <AuditoriaAtividade />}

      {editando && (
        <EditarUsuarioModal
          usuario={editando}
          souEu={editando.id === meuId}
          pessoas={pessoas || []}
          usuarios={usuarios || []}
          onClose={() => setEditando(null)}
          onSalvo={() => { setEditando(null); carregar(); carregarPessoas(); }}
        />
      )}
    </div>
  );
}

// Relatório de últimos acessos — só o proprietário vê esta seção (o backend
// também bloqueia /auth/usuarios/acessos para qualquer outro usuário, mesmo
// admin, então esconder aqui é só para não mostrar um card que sempre erra
// 403 para os demais).
function RelatorioAcessos() {
  const [acessos, setAcessos] = useState<UsuarioAcesso[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { fetchAcessos().then(setAcessos).catch((e) => setErro(e.message)); }, []);

  const fmt = (iso: string | null) => iso ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" }) : "Nunca";

  return (
    <div className="card mt-4" style={{ maxWidth: "40rem" }}>
      <div className="card-header mb-3 flex items-center gap-2"><ShieldCheck size={14} /> Últimos acessos</div>
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
    </div>
  );
}

// Auditoria de atividade — lançamentos feitos por um usuário em qualquer
// módulo do sistema. Igual ao relatório de acessos, restrito ao proprietário
// tanto no frontend (esconder) quanto no backend (ver exigir_dono).
function AuditoriaAtividade() {
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
  const fmtData = (iso: string | null) => iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—";

  return (
    <div className="card mt-4" style={{ maxWidth: "48rem" }}>
      <div className="card-header mb-3 flex items-center gap-2"><History size={14} /> Auditoria de atividade</div>
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
              {tipos.size > 0 && <button className="btn-ghost" style={{ fontSize: "0.68rem" }} onClick={() => setTipos(new Set())}>Limpar seleção</button>}
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
                    {linhasOrdenadas.map((i, idx) => (
                      <tr key={`${i.chave}-${i.id}-${idx}`}>
                        <td style={{ fontSize: "0.8rem" }}>{i.label}</td>
                        <td style={{ fontSize: "0.8rem" }}>{fmtData(i.data)}</td>
                        <td style={{ fontSize: "0.8rem" }}>{i.resumo}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

function EditarUsuarioModal({ usuario, souEu, pessoas, usuarios, onClose, onSalvo }: {
  usuario: any; souEu: boolean; pessoas: any[]; usuarios: any[]; onClose: () => void; onSalvo: () => void;
}) {
  const [username, setUsername] = useState(usuario.username);
  const [pessoaId, setPessoaId] = useState(usuario.pessoa_id ? String(usuario.pessoa_id) : "");
  const [email, setEmail] = useState(usuario.email || "");
  const [papel, setPapel] = useState<"admin" | "operador">(usuario.papel);
  const [perms, setPerms] = useState<Set<string>>(new Set(usuario.papel === "admin" ? TODOS : usuario.permissoes || []));
  const [ativo, setAtivo] = useState<boolean>(usuario.ativo);
  const [podePublicarBlog, setPodePublicarBlog] = useState<boolean>(usuario.pode_publicar_materias_blog === true);
  const [novaSenha, setNovaSenha] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const toggle = (k: string) => setPerms((p) => { const s = new Set(p); s.has(k) ? s.delete(k) : s.add(k); return s; });

  const salvar = async () => {
    setSalvando(true); setErro(null);
    try {
      await atualizarUsuario(usuario.id, {
        username: username.trim(), pessoa_id: pessoaId ? Number(pessoaId) : undefined, email: email.trim() || undefined, papel,
        permissoes: papel === "admin" ? TODOS : Array.from(perms),
        ativo, pode_publicar_materias_blog: podePublicarBlog, ...(novaSenha ? { senha: novaSenha } : {}),
      });
      onSalvo();
    } catch (e: any) { setErro(e.message); }
    finally { setSalvando(false); }
  };

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: "1rem" }}>
      <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "480px", maxWidth: "95vw", maxHeight: "88vh", overflowY: "auto" }}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>Editar usuário</div>
          <button onClick={onClose} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
        </div>
        <div className="space-y-3">
          <div><label style={lbl}>Usuário (login)</label><input style={inp} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" /></div>
          <div>
            <div className="flex items-center justify-between">
              <label style={lbl}>Pessoa</label>
              <Link href="/configuracoes?aba=cadastro&sub=pessoas" className="btn-ghost" style={{ fontSize: "0.68rem", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                <UserSquare2 size={12} /> Cadastre a pessoa primeiro
              </Link>
            </div>
            <select style={inp} value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
              <option value="">Selecione…</option>
              {pessoas
                .filter((p) => p.ativo && (p.id === usuario.pessoa_id || !usuarios.some((u) => u.pessoa_id === p.id)))
                .map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select>
          </div>
          <div><label style={lbl}>E-mail (opcional)</label><input style={inp} type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div><label style={lbl}>Nova senha (deixe em branco para manter)</label><input style={inp} value={novaSenha} onChange={(e) => setNovaSenha(e.target.value)} /></div>
          <div><label style={lbl}>Tipo</label>
            <select style={inp} value={papel} onChange={(e) => setPapel(e.target.value as any)}>
              <option value="admin">Administrador (acesso total + gerencia usuários)</option>
              <option value="operador">Operador (você escolhe os módulos)</option>
            </select>
          </div>

          {papel === "operador" && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <label style={lbl}>Módulos liberados</label>
                <div className="flex gap-2">
                  <button className="btn-ghost" style={{ fontSize: "0.68rem" }} onClick={() => setPerms(new Set(TODOS))}>Acesso total</button>
                  <button className="btn-ghost" style={{ fontSize: "0.68rem" }} onClick={() => setPerms(new Set(TODOS.filter((k) => k !== "financeiro")))}>Sem financeiro</button>
                  <button className="btn-ghost" style={{ fontSize: "0.68rem" }} onClick={() => setPerms(new Set(["capa"]))}>Limpar</button>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-1" style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.5rem" }}>
                {MODULOS.map((m) => (
                  <label key={m.key} className="flex items-center gap-2" style={{ fontSize: "0.8rem", opacity: m.key === "capa" ? 0.7 : 1 }}>
                    <input type="checkbox" checked={perms.has(m.key)} disabled={m.key === "capa"} onChange={() => toggle(m.key)} /> {m.label}
                  </label>
                ))}
              </div>
            </div>
          )}

          <div>
            <label style={{ ...lbl, display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <input type="checkbox" checked={ativo} disabled={souEu} onChange={(e) => setAtivo(e.target.checked)} /> Ativo
            </label>
            {souEu && <p style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Você não pode desativar a si mesmo.</p>}
          </div>

          <div style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.6rem 0.7rem" }}>
            <label className="flex items-center gap-2" style={{ fontSize: "0.82rem" }}>
              <input type="checkbox" checked={podePublicarBlog} onChange={(e) => setPodePublicarBlog(e.target.checked)} />
              <Newspaper size={14} /> Permitir publicação de matérias no blog (News)
            </label>
            <p style={{ fontSize: "0.66rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
              Independente do tipo de acesso — inclusive administrador pode não ter essa permissão.
            </p>
          </div>

          {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}

          <div className="flex items-center gap-3 mt-2">
            <button className="btn-primary" onClick={salvar} disabled={salvando || !username}><Check size={15} /> Salvar</button>
            <button className="btn-ghost" onClick={onClose}>Cancelar</button>
          </div>
        </div>
      </div>
    </div>
  );
}
