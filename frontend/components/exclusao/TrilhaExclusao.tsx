"use client";
// Trilha (Fase 2) — histórico de exclusões para o admin (quem, quando, o quê).
import { useEffect, useState } from "react";
import { fetchTrilhaExclusao } from "@/lib/api";
import type { RegistroTrilha } from "@/lib/exclusao";

const ACAO_TXT: Record<string, string> = {
  apagou: "Apagou", aprovou: "Aprovou", rejeitou: "Rejeitou", arquivou: "Arquivou", cancelou: "Cancelou",
};

export function TrilhaExclusao() {
  const [regs, setRegs] = useState<RegistroTrilha[]>([]);
  const [q, setQ] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  const carregar = () => fetchTrilhaExclusao({ q }).then(setRegs).catch((e: any) => setErro(e.message));
  useEffect(() => { carregar(); /* eslint-disable-line react-hooks/exhaustive-deps */ }, [q]);

  return (
    <section className="exc-aba">
      <input className="exc-input" placeholder="Filtrar por código, título ou usuário…" value={q} onChange={(e) => setQ(e.target.value)} />
      {erro && <p className="exc-bloqueado">{erro}</p>}
      {regs.length === 0 && <p className="muted">Nada registrado ainda.</p>}
      <ul className="exc-trilha">
        {regs.map((r) => (
          <li key={r.codigo} className="exc-trilha-item">
            <span className="exc-trilha-codigo">{r.codigo}</span>
            <strong>{ACAO_TXT[r.acao] ?? r.acao} · {r.titulo}</strong>
            <span className="muted">{r.criado_em?.slice(0, 16).replace("T", " ")} · {r.motivo ? `motivo: ${r.motivo}` : ""}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}