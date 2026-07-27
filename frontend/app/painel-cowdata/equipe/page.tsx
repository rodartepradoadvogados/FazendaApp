"use client";
import { useEffect, useState } from "react";
import { UserPlus } from "lucide-react";
import { fetchAcessos, criarUsuario, type UsuarioAcesso } from "@/lib/api";

const COR = { cartao: "#0d1220", borda: "#1c2438", mudo: "#7c8aa8", dourado: "#e8c256", vermelho: "#e05c5c", texto: "#e8ecf5" };
const inp: React.CSSProperties = {
  background: "#0a0e1a", color: COR.texto, border: `1px solid ${COR.borda}`, borderRadius: "6px",
  padding: "0.4rem 0.6rem", fontSize: "0.8rem", width: "auto", flex: "1 1 10rem",
};

export default function EquipeCowData() {
  const [usuarios, setUsuarios] = useState<UsuarioAcesso[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [criando, setCriando] = useState(false);
  const [form, setForm] = useState({ username: "", nome: "", senha: "", papel: "operador" });

  function carregar() { fetchAcessos().then(setUsuarios).catch((e) => setErro(e.message)); }
  useEffect(carregar, []);

  async function criar() {
    if (!form.username.trim() || !form.nome.trim() || !form.senha.trim()) {
      setErro("Preencha usuário, nome e senha."); return;
    }
    setCriando(true); setErro(null); setMsg(null);
    try {
      // Sem pessoa_id de propósito — conta da equipe CowData, sem vínculo
      // com o cadastro de Pessoas de nenhuma fazenda (ver auth.py::_validar_pessoa_ou_nome).
      await criarUsuario({ username: form.username.trim(), senha: form.senha, nome: form.nome.trim(), papel: form.papel, permissoes: [] });
      setForm({ username: "", nome: "", senha: "", papel: "operador" });
      setMsg("Usuário criado — já pode ser usado pra entrar no sistema.");
      carregar();
    } catch (e: any) { setErro(e.message); } finally { setCriando(false); }
  }

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.2rem" }}>Equipe CowData</h1>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1rem", maxWidth: "42rem" }}>
        Contas de acesso administrativo sem vínculo com o cadastro de Pessoas de nenhuma fazenda — para
        criar um funcionário/operador de UMA fazenda específica, use "Usuários vinculados" dentro de
        Fazendas (clientes).
      </p>
      {erro && <p style={{ color: COR.vermelho, fontSize: "0.85rem", marginBottom: "1rem" }}>{erro}</p>}
      {msg && <p style={{ color: COR.dourado, fontSize: "0.85rem", marginBottom: "1rem" }}>{msg}</p>}

      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", padding: "1rem", marginBottom: "1.2rem" }}>
        <div className="flex flex-wrap gap-2 mb-2">
          <input placeholder="usuário (login)" style={inp} value={form.username} onChange={(e) => setForm((s) => ({ ...s, username: e.target.value }))} />
          <input placeholder="nome" style={inp} value={form.nome} onChange={(e) => setForm((s) => ({ ...s, nome: e.target.value }))} />
          <input placeholder="senha" type="password" style={inp} value={form.senha} onChange={(e) => setForm((s) => ({ ...s, senha: e.target.value }))} />
          <select style={inp} value={form.papel} onChange={(e) => setForm((s) => ({ ...s, papel: e.target.value }))}>
            <option value="operador">Operador</option>
            <option value="admin">Admin</option>
          </select>
          <button onClick={criar} disabled={criando}
            style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.4rem 0.8rem", borderRadius: "6px", border: `1px solid ${COR.dourado}`, background: "transparent", color: COR.dourado, cursor: "pointer" }}>
            <UserPlus size={14} /> {criando ? "Criando…" : "Criar usuário CowData"}
          </button>
        </div>
      </div>

      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${COR.borda}`, color: COR.mudo, textAlign: "left" }}>
              <th style={{ padding: "0.6rem 1rem" }}>Usuário</th>
              <th style={{ padding: "0.6rem 1rem" }}>Papel</th>
              <th style={{ padding: "0.6rem 1rem" }}>Último acesso</th>
            </tr>
          </thead>
          <tbody>
            {usuarios === null && <tr><td colSpan={3} style={{ padding: "1rem", color: COR.mudo }}>Carregando…</td></tr>}
            {usuarios?.map((u) => (
              <tr key={u.id} style={{ borderBottom: `1px solid ${COR.borda}` }}>
                <td style={{ padding: "0.6rem 1rem" }}>{u.nome || u.username} <span style={{ color: COR.mudo, fontSize: "0.72rem" }}>(@{u.username})</span></td>
                <td style={{ padding: "0.6rem 1rem" }}>
                  <span style={{ color: u.papel === "admin" ? COR.dourado : "#c3cbde", fontWeight: u.papel === "admin" ? 700 : 400 }}>{u.papel}</span>
                </td>
                <td style={{ padding: "0.6rem 1rem", color: COR.mudo }}>{u.ultimo_login ? new Date(u.ultimo_login).toLocaleString("pt-BR") : "nunca"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
