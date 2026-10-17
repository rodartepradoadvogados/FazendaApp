"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Settings } from "lucide-react";
import { fetchRepasseConfig, type RepasseConfig } from "@/lib/api";

/**
 * Resumo da "Detecção de cio de repasse" (Lançamentos › Calendário sanitário › tipo Detecção de cio de repasse).
 * Só mostra o que está valendo: a regra mora em Parâmetros › Reinseminação e observação de cio (chave mestra, aviso na
 * Agenda, produtos do estoque), a única tela que a edita. Aqui não há campo para mexer — só o atalho.
 */
export function CartaoRepasse() {
  const [cfg, setCfg] = useState<RepasseConfig | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    fetchRepasseConfig().then(setCfg).catch((e: unknown) => setErro(e instanceof Error ? e.message : "Não foi possível carregar a configuração do repasse."));
  }, []);

  if (erro) return <div className="card mt-3"><p role="alert" style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p></div>;
  if (!cfg) return <div className="card mt-3"><p className="ag2-mudo" role="status">Carregando a configuração do repasse…</p></div>;

  const produtos = (cfg.produtos ?? []).map((p) => p.nome);
  const linhas: [string, string][] = cfg.usar
    ? [
        ["Aviso na Agenda", cfg.avisar_apos_dias == null ? "sem aviso" : `após ${cfg.avisar_apos_dias} dias do serviço`],
        ["Produtos vinculados", produtos.length ? produtos.join(", ") : "nenhum — escolha livre no estoque"],
        ["Repetir a checagem", cfg.repetir ? `a cada ${cfg.repetir_cada_dias} dias, ${cfg.repeticoes} ${cfg.repeticoes === 1 ? "vez" : "vezes"}` : "não"],
        ["Quais serviços entram", (cfg.quem_entra_opcoes ?? []).find((o) => o.valor === cfg.quem_entra)?.rotulo ?? cfg.quem_entra],
      ]
    : [["Adesivo", "desligado — a fazenda não usa adesivo de detecção de cio"]];

  return (
    <div className="card mt-3" aria-label="Detecção de cio de repasse" data-testid="resumo-repasse">
      <div className="card-header mb-2 flex items-center justify-between" style={{ gap: "0.75rem", flexWrap: "wrap" }}>
        <span>Detecção de cio de repasse</span>
        <Link href="/parametros" className="btn-secondary" style={{ fontSize: "0.75rem", display: "inline-flex", alignItems: "center", gap: "0.35rem", textDecoration: "none" }}>
          <Settings size={13} aria-hidden="true" /> Editar em Parâmetros
        </Link>
      </div>
      <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "max-content 1fr", gap: "0.35rem 1.2rem", fontSize: "0.85rem" }}>
        {linhas.map(([rotulo, valor]) => (
          <React.Fragment key={rotulo}>
            <dt style={{ color: "var(--text-muted)" }}>{rotulo}</dt>
            <dd style={{ margin: 0, fontWeight: 600 }}>{valor}</dd>
          </React.Fragment>
        ))}
      </dl>
    </div>
  );
}
