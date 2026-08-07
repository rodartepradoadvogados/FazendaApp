"use client";
// Sub-tela: Remédios por Doença — consulta rápida do "substituto inteligente"
// (mesmo recurso do site, versão campo): escolhe a doença e vê os princípios
// ativos indicados, em ordem de prioridade clínica, com status de estoque.
// Só leitura — mesmo padrão de fetch/loading/vazio das outras sub-telas do Menu.
import { useEffect, useMemo, useState } from "react";
import { FlaskConical } from "lucide-react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchDoencas, fetchIndicacoesDoenca, type OpcaoIndicacaoDoenca } from "@/lib/api";
import { Carregando, Vazio } from "@/components/mobile/menu/comum";

const COR_STATUS: Record<OpcaoIndicacaoDoenca["status_estoque"], string> = {
  ok: "var(--mob-verde)", low: "var(--mob-ambar)", out: "var(--mob-vermelho)",
};
const TEXTO_STATUS: Record<OpcaoIndicacaoDoenca["status_estoque"], string> = {
  ok: "Em estoque", low: "Estoque baixo", out: "Sem estoque",
};

// Mesmos tipos de Doenca.TIPOS (backend) — agrupam o seletor em optgroups,
// espelhando components/RemediosPorDoenca.tsx (versão site).
const GRUPOS_TIPO: [string, string][] = [
  ["doenca", "Doenças"], ["reprodutivo", "Reprodutivo"], ["produtivo", "Produtivo"],
  ["preventivo", "Preventivo"], ["suporte", "Suporte"],
];

export default function RemediosPorDoenca({ onVoltar }: { onVoltar: () => void }) {
  const [doencas, setDoencas] = useState<{ id: number; nome: string; tipo?: string | null }[]>([]);
  const [doencaId, setDoencaId] = useState("");
  const [opcoes, setOpcoes] = useState<OpcaoIndicacaoDoenca[] | null>(null);
  const [carregando, setCarregando] = useState(false);

  useEffect(() => {
    fetchDoencas().then((d: any[]) => setDoencas(d.filter((x) => x.ativo))).catch(() => setDoencas([]));
  }, []);

  const grupos = useMemo(() => GRUPOS_TIPO
    .map(([tipo, label]) => ({
      label,
      itens: doencas.filter((d) => (tipo === "doenca" ? !d.tipo || d.tipo === "doenca" : d.tipo === tipo)),
    }))
    .filter((g) => g.itens.length > 0), [doencas]);

  useEffect(() => {
    if (!doencaId) { setOpcoes(null); return; }
    setCarregando(true);
    fetchIndicacoesDoenca(Number(doencaId))
      .then((r) => setOpcoes(r.opcoes))
      .catch(() => setOpcoes([]))
      .finally(() => setCarregando(false));
  }, [doencaId]);

  return (
    <div>
      <MobVoltar titulo="Remédios por Doença" onVoltar={onVoltar} />

      <label style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--mob-muted)", marginBottom: "0.3rem" }}>
        Doença
      </label>
      <select className="mob-input" value={doencaId} onChange={(e) => setDoencaId(e.target.value)} style={{ marginBottom: "1rem" }}>
        <option value="">Selecione…</option>
        {grupos.map((g) => (
          <optgroup key={g.label} label={g.label}>
            {g.itens.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
          </optgroup>
        ))}
      </select>

      {!doencaId ? (
        <Vazio icon={FlaskConical}>Escolha uma doença para ver os remédios indicados.</Vazio>
      ) : carregando ? (
        <Carregando />
      ) : !opcoes || opcoes.length === 0 ? (
        <Vazio icon={FlaskConical}>Nenhuma indicação cadastrada para essa doença.</Vazio>
      ) : (
        opcoes.map((o) => (
          <MobCard key={o.principio_ativo_id} style={{ marginBottom: "0.6rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span style={{
                fontSize: "0.72rem", fontWeight: 800, padding: "0.15rem 0.55rem", borderRadius: "999px", flexShrink: 0,
                background: o.prioridade === 1 ? "var(--mob-verde)" : "var(--mob-surface-2)",
                color: o.prioridade === 1 ? "#fff" : "var(--mob-muted)",
                border: o.prioridade === 1 ? "none" : "1px solid var(--mob-border)",
              }}>
                {o.prioridade}ª escolha
              </span>
              <span style={{ width: 9, height: 9, borderRadius: "50%", background: COR_STATUS[o.status_estoque], flexShrink: 0, marginLeft: "auto" }} />
              <span style={{ fontSize: "0.78rem", fontWeight: 600, color: COR_STATUS[o.status_estoque] }}>{TEXTO_STATUS[o.status_estoque]}</span>
            </div>
            <div style={{ fontWeight: 800, fontSize: "1rem", marginTop: "0.4rem" }}>{o.nome}</div>
            {o.classificacao && <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)" }}>{o.classificacao}</div>}
            <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>
              {o.total_apresentacoes != null ? `${o.total_apresentacoes} ${o.unidade_apresentacao || ""} em estoque` : "Sem apresentações cadastradas"}
            </div>
            {o.marcas.length > 0 && (
              <div style={{ fontSize: "0.8rem", color: "var(--mob-text)", marginTop: "0.3rem" }}>Marcas: {o.marcas.join(", ")}</div>
            )}
          </MobCard>
        ))
      )}
    </div>
  );
}
