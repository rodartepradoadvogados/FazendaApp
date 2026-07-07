"use client";
import { useEffect, useMemo, useState } from "react";
import { Users, AlertTriangle, UserPlus, Check } from "lucide-react";
import { fetchUsuarios, criarUsuario, atualizarUsuario } from "@/lib/api";

const MODULOS = [
  { key: "capa", label: "Capa" }, { key: "indicadores", label: "Indicadores" }, { key: "agenda", label: "Agenda" },
  { key: "lancamentos", label: "Lançamentos" }, { key: "reproducao", label: "Reprodução" }, { key: "analise", label: "Análise Repr." },
  { key: "rebanho", label: "Rebanho" }, { key: "producao", label: "Produção" }, { key: "alimentacao", label: "Alimentação" },
  { key: "sanidade", label: "Sanidade" }, { key: "financeiro", label: "Financeiro" }, { key: "estoque", label: "Sanidade/Estoque" },
  { key: "parametros", label: "Parâmetros" }, { key: "upload", label: "Upload" },
];
const TODOS = MODULOS.map((m) => m.key);

const inp: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem" };
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

export default function UsuariosPage() {
  const [usuarios, setUsuarios] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [username, setUsername] = useState("");
  const [nome, setNome] = useState("");
  const [senha, setSenha] = useState("");
  const [papel, setPapel] = useState<"admin" | "operador">("operador");
  const [perms, setPerms] = useState<Set<string>>(new Set(TODOS));
  const [salvando, setSalvando] = useState(false);

  const carregar = () => fetchUsuarios().then(setUsuarios).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const toggle = (k: string) => setPerms((p) => { const s = new Set(p); s.has(k) ? s.delete(k) : s.add(k); return s; });

  const criar = async () => {
    setSalvando(true); setError(null); setMsg(null);
    try {
      await criarUsuario({ username: username.trim(), senha, nome: nome.trim() || undefined, papel, permissoes: papel === "admin" ? TODOS : Array.from(perms) });
      setMsg(`Usuário "${username}" criado.`);
      setUsername(""); setNome(""); setSenha(""); setPapel("operador"); setPerms(new Set(TODOS));
      carregar();
    } catch (e: any) { setError(e.message); }
    finally { setSalvando(false); }
  };

  const toggleAtivo = async (u: any) => {
    try { await atualizarUsuario(u.id, { ativo: !u.ativo }); carregar(); }
    catch (e: any) { setError(e.message); }
  };

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
            <div><label style={lbl}>Nome</label><input style={inp} value={nome} onChange={(e) => setNome(e.target.value)} /></div>
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

            <button className="btn-primary" onClick={criar} disabled={salvando || !username || !senha} style={{ width: "100%", justifyContent: "center" }}>
              <Check size={16} /> Criar usuário
            </button>
          </div>
        </div>

        {/* Lista */}
        <div className="card">
          <div className="card-header mb-3">Usuários cadastrados</div>
          {!usuarios ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : (
            <table className="fazenda-table">
              <thead><tr><th>Login</th><th>Nome</th><th>Acesso</th><th>Ativo</th></tr></thead>
              <tbody>
                {usuarios.map((u) => (
                  <tr key={u.id}>
                    <td style={{ fontWeight: 700 }}>{u.username}</td>
                    <td style={{ fontSize: "0.8rem" }}>{u.nome || "—"}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      {u.papel === "admin" ? "Administrador (tudo)" : `${(u.permissoes || []).length} módulos${(u.permissoes || []).includes("financeiro") ? "" : " · sem financeiro"}`}
                    </td>
                    <td>
                      <button onClick={() => toggleAtivo(u)} className="btn-ghost" style={{ fontSize: "0.7rem", color: u.ativo ? "var(--green-light)" : "var(--red)" }}>
                        {u.ativo ? "Ativo" : "Inativo"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
