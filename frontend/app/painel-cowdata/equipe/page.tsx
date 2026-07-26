"use client";
import { useEffect, useState } from "react";
import { fetchAcessos, type UsuarioAcesso } from "@/lib/api";

const COR = { cartao: "#0d1220", borda: "#1c2438", mudo: "#7c8aa8", dourado: "#e8c256", vermelho: "#e05c5c" };

export default function EquipeCowData() {
  const [usuarios, setUsuarios] = useState<UsuarioAcesso[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { fetchAcessos().then(setUsuarios).catch((e) => setErro(e.message)); }, []);

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.2rem" }}>Equipe CowData</h1>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1rem", maxWidth: "42rem" }}>
        Quem tem acesso administrativo hoje. O cadastro de usuário ainda é único para a fazenda e para o
        software (não há, ainda, uma conta "funcionário da CowData" separada de "usuário da fazenda") —
        é um item pendente da separação fazenda/empresa (Fase 1).
      </p>
      {erro && <p style={{ color: COR.vermelho, fontSize: "0.85rem", marginBottom: "1rem" }}>{erro}</p>}

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
