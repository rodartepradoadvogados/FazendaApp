"use client";
// Relatório de últimos acessos para usuários com permissão "controle_acesso"
// Mostra apenas os usuários que o usuário logado tem permissão para auditar
// (definidos em usuarios_auditados). Admin/dono usam o RelatorioAcessos completo.
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ShieldCheck, Clock, History, Search, Eye, EyeOff } from "lucide-react";
import { fetchAuditoriaAcessos, type UsuarioAcesso } from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { SecaoRecolhivel } from "@/components/ui";

const inp: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.85rem" };
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

// `defaultAberta` deixa o chamador decidir: na tela dedicada começa aberta;
// em Configurações > Usuários é uma seção secundária, então começa recolhida.
export function RelatorioAuditoriaAcessos({ defaultAberta = false }: { defaultAberta?: boolean }) {
  const [acessos, setAcessos] = useState<UsuarioAcesso[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [filtroTexto, setFiltroTexto] = useState("");

  useEffect(() => {
    fetchAuditoriaAcessos()
      .then(setAcessos)
      .catch((e) => setErro(e.message));
  }, []);

  const fmt = (iso: string | null) => iso ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" }) : "Nunca";

  const acessosFiltrados = useMemo(() => {
    if (!acessos) return [];
    if (!filtroTexto) return acessos;
    const t = filtroTexto.toLowerCase();
    return acessos.filter((a: UsuarioAcesso) =>
      a.username.toLowerCase().includes(t) ||
      (a.nome || "").toLowerCase().includes(t)
    );
  }, [acessos, filtroTexto]);

  return (
    <div style={{ maxWidth: "48rem" }}>
      <SecaoRecolhivel titulo="Últimos acessos (auditoria)" icon={ShieldCheck} defaultAberta={defaultAberta} descricao="Últimos 3 logins dos usuários que você tem permissão para auditar">
        <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.6rem" }}>
          Visível apenas para você (permissão "Controle de Acesso"). Admin/dono veem todos os usuários da fazenda.
        </p>
        {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
        {!acessos && !erro && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
        {acessos && (
          <>
            <div style={{ marginBottom: "0.5rem" }}>
              <label style={lbl}>Filtrar por login ou nome</label>
              <input style={inp} type="text" placeholder="Digite para filtrar…" value={filtroTexto} onChange={(e) => setFiltroTexto(e.target.value)} />
            </div>
            {acessosFiltrados.length === 0 && (
              <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", textAlign: "center", padding: "1rem" }}>
                {filtroTexto ? "Nenhum usuário encontrado com esse filtro." : "Nenhum usuário disponível para auditoria. Configure em Editar usuário → Usuários que pode auditar."}
              </p>
            )}
            {acessosFiltrados.length > 0 && (
              <table className="fazenda-table">
                <thead><tr><th>Login</th><th>Nome</th><th>Papel</th><th>Ativo</th><th><Clock size={12} style={{ display: "inline", marginRight: "0.25rem" }} />Últimos 3 acessos</th></tr></thead>
                <tbody>
                  {acessosFiltrados.map((a) => (
                    <tr key={a.id}>
                      <td style={{ fontWeight: 700, verticalAlign: "top" }}>{a.username}{!a.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                      <td style={{ fontSize: "0.8rem", verticalAlign: "top" }}>{a.nome || "—"}</td>
                      <td style={{ fontSize: "0.75rem", color: "var(--text-muted)", verticalAlign: "top" }}>{a.papel === "admin" ? "Administrador" : "Operador"}</td>
                      <td style={{ verticalAlign: "top" }}>
                        <span className={`st-pill ${a.ativo ? "" : "inativo"}`}>
                          {a.ativo ? "Sim" : "Não"}
                        </span>
                      </td>
                      <td style={{ fontSize: "0.8rem" }}>
                        {a.ultimos_acessos.length === 0 ? (
                          <span style={{ color: "var(--text-muted)" }}>Nunca</span>
                        ) : (
                          a.ultimos_acessos.map((iso: string, i: number) => (
                            <div key={i} style={{ color: i === 0 ? "var(--text)" : "var(--text-muted)", fontWeight: i === 0 ? 700 : 400 }}>{fmt(iso)}</div>
                          ))
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </SecaoRecolhivel>
    </div>
  );
}