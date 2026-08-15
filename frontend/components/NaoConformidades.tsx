"use client";

import { useEffect, useState } from "react";
import { AlertOctagon, AlertTriangle, CheckCircle2, PartyPopper } from "lucide-react";
import { fetchNaoConformidades, NaoConformidadeItem, NaoConformidadeSemMeta, NaoConformidadesResp } from "@/lib/api";
import { SecaoRecolhivel, Indicador } from "@/components/ui";

const DOMINIO_LABEL: Record<string, string> = {
  reproducao: "Reprodução", recria: "Recria", financeiro: "Financeiro", manejo: "Manejo",
};
const DOMINIO_ORDEM = ["reproducao", "recria", "financeiro", "manejo"];
const STATUS_COR: Record<string, string> = { critico: "var(--red)", atencao: "var(--amber)", ok: "var(--green-light)" };
const STATUS_LABEL: Record<string, string> = { critico: "Crítico", atencao: "Atenção", ok: "Em dia" };

function fmt(valor: number, unidade: string): string {
  if (unidade === "R$") return (valor < 0 ? "-R$ " : "R$ ") + Math.abs(valor).toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  if (unidade === "R$/L") return "R$ " + valor.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + "/L";
  if (unidade === "R$/ha") return "R$ " + valor.toLocaleString("pt-BR", { maximumFractionDigits: 0 }) + "/ha";
  return valor.toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + unidade;
}

// Posição (0-100) do valor e da meta numa barrinha comparativa — mesma ideia
// de um bullet graph: a janela [lo, hi] sempre enquadra os dois pontos com
// alguma folga, então a barra nunca "estoura" nem fica ilegível quando um
// dos dois é zero.
function bulletPct(valor: number, meta: number): { valorPct: number; metaPct: number } {
  const base = Math.min(valor, meta, 0);
  const topo = Math.max(valor, meta, base + 1) * 1.2;
  const span = topo - base || 1;
  const clamp = (n: number) => Math.max(2, Math.min(100, ((n - base) / span) * 100));
  return { valorPct: clamp(valor), metaPct: clamp(meta) };
}

function LinhaItem({ item }: { item: NaoConformidadeItem }) {
  const cor = STATUS_COR[item.status];
  const bullet = item.meta != null ? bulletPct(item.valor, item.meta) : null;
  return (
    <div style={linhaGrid}>
      <div style={{ alignSelf: "stretch", borderRadius: 3, background: cor, minHeight: "2.2rem" }} />
      <div>
        <div style={{ fontSize: "0.88rem", fontWeight: 650 }}>{item.label}</div>
        <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{item.sublabel}</div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div style={{ fontSize: "1rem", fontWeight: 800, fontVariantNumeric: "tabular-nums", color: item.status === "ok" ? "var(--text)" : cor }}>
          {fmt(item.valor, item.unidade)}
        </div>
        {item.meta != null && (
          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
            meta {item.maior_melhor ? "≥" : "≤"} {fmt(item.meta, item.unidade)}
          </div>
        )}
      </div>
      <div>
        {bullet && (
          <div style={{ position: "relative", height: 7, borderRadius: 999, background: "var(--surface-2)", border: "1px solid var(--border)" }}>
            <div style={{ position: "absolute", top: 0, bottom: 0, left: 0, width: `${bullet.valorPct}%`, borderRadius: 999, background: cor }} />
            <div style={{ position: "absolute", top: -2, bottom: -2, left: `${bullet.metaPct}%`, width: 2, background: "var(--dourado-light)" }} />
          </div>
        )}
      </div>
      <a href={item.rota} style={{ fontSize: "0.74rem", fontWeight: 650, color: "var(--dourado-light)", whiteSpace: "nowrap", textDecoration: "none" }}>
        {item.rota_label} →
      </a>
    </div>
  );
}
const linhaGrid: React.CSSProperties = {
  display: "grid", gridTemplateColumns: "4px 1.8fr 1fr 1fr auto", gap: "0.8rem", alignItems: "center",
  padding: "0.65rem 0.2rem", borderBottom: "1px solid var(--border)",
};

function LinhaSemMeta({ item }: { item: NaoConformidadeSemMeta }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "0.8rem", alignItems: "center", padding: "0.65rem 0.2rem", borderBottom: "1px solid var(--border)" }}>
      <div>
        <div style={{ fontSize: "0.88rem", fontWeight: 650 }}>{item.label}</div>
        <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
          {item.sublabel} · {fmt(item.valor, item.unidade)} — nenhuma meta configurada ainda
        </div>
      </div>
      <a href="/parametros" style={{ fontSize: "0.74rem", fontWeight: 650, color: "var(--text-muted)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.3rem 0.6rem", whiteSpace: "nowrap", textDecoration: "none" }}>
        Configurar meta →
      </a>
    </div>
  );
}

export default function NaoConformidades() {
  const [dados, setDados] = useState<NaoConformidadesResp | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [dominio, setDominio] = useState<string>("todos");
  const [mostrarTudo, setMostrarTudo] = useState(false);

  useEffect(() => {
    let vivo = true;
    fetchNaoConformidades()
      .then((d) => { if (vivo) setDados(d); })
      .catch((e) => { if (vivo) setErro(e?.message || "Erro ao carregar"); });
    return () => { vivo = false; };
  }, []);

  if (erro) return <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>;
  if (!dados) return <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>;

  const naoConformes = dados.itens.filter((i) => i.status !== "ok");
  const visiveis = dados.itens.filter((i) => (mostrarTudo || i.status !== "ok") && (dominio === "todos" || i.dominio === dominio));

  const contagemPorDominio = (d: string) => naoConformes.filter((i) => d === "todos" || i.dominio === d).length;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem", marginBottom: "1.1rem" }}>
        <div>
          <h2 style={{ fontSize: "1.15rem", fontWeight: 700, margin: "0 0 0.25rem" }}>Relatório de Não Conformidades</h2>
          <p style={{ color: "var(--text-muted)", fontSize: "0.84rem", margin: 0, maxWidth: "52ch" }}>
            Tudo o que está fora da meta, do parâmetro ou do padrão cadastrado na fazenda — reunido em um só lugar.
          </p>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "0.7rem", marginBottom: "1.2rem" }}>
        <Indicador categoria="geral" icon={AlertOctagon} cor="var(--red)" valor={dados.resumo.critico} rotulo="Crítico" />
        <Indicador categoria="geral" icon={AlertTriangle} cor="var(--amber)" valor={dados.resumo.atencao} rotulo="Atenção" />
        <Indicador categoria="geral" icon={CheckCircle2} cor="var(--green-light)" valor={dados.resumo.ok} rotulo="Em dia" />
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem", marginBottom: "1.2rem" }}>
        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
          {["todos", ...DOMINIO_ORDEM].map((d) => (
            <button
              key={d}
              onClick={() => setDominio(d)}
              style={{
                fontSize: "0.78rem", fontWeight: 600, padding: "0.35rem 0.7rem", borderRadius: 999,
                border: `1px solid ${dominio === d ? "var(--dourado)" : "var(--border)"}`,
                background: dominio === d ? "var(--dourado)" : "var(--surface)",
                color: dominio === d ? "var(--vinho-dark, #0A1F36)" : "var(--text-muted)",
                cursor: "pointer",
              }}
            >
              {d === "todos" ? "Todos" : DOMINIO_LABEL[d]} · {contagemPorDominio(d)}
            </button>
          ))}
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8rem", color: "var(--text-muted)", cursor: "pointer" }}>
          <input type="checkbox" checked={mostrarTudo} onChange={(e) => setMostrarTudo(e.target.checked)} />
          Mostrar todos os indicadores
        </label>
      </div>

      {!visiveis.length ? (
        <div style={{ textAlign: "center", padding: "2.5rem 1rem", color: "var(--text-muted)", fontSize: "0.88rem", background: "var(--surface)", border: "1px dashed var(--border)", borderRadius: 12, display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem" }}>
          <PartyPopper size={22} />
          Nenhuma não conformidade nesse filtro.
        </div>
      ) : (
        DOMINIO_ORDEM.filter((d) => dominio === "todos" || dominio === d).map((d) => {
          const linhas = visiveis.filter((i) => i.dominio === d);
          if (!linhas.length) return null;
          const criticos = linhas.filter((i) => i.status === "critico").length;
          const atencoes = linhas.filter((i) => i.status === "atencao").length;
          return (
            <SecaoRecolhivel
              key={d}
              titulo={DOMINIO_LABEL[d]}
              defaultAberta
              badge={
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                  {criticos > 0 && <span style={{ color: "var(--red)", fontWeight: 700 }}>{criticos} crítico{criticos > 1 ? "s" : ""}</span>}
                  {criticos > 0 && atencoes > 0 && " · "}
                  {atencoes > 0 && <span style={{ color: "var(--amber)", fontWeight: 700 }}>{atencoes} atenção</span>}
                  {criticos === 0 && atencoes === 0 && "em dia"}
                </span>
              }
            >
              {linhas.map((item) => <LinhaItem key={item.chave} item={item} />)}
            </SecaoRecolhivel>
          );
        })
      )}

      {dados.sem_meta.length > 0 && (
        <div style={{ marginTop: "1.5rem" }}>
          <div style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700, color: "var(--text-muted)", marginBottom: "0.5rem" }}>
            Sem meta cadastrada
          </div>
          <div className="card" style={{ padding: "0.2rem 0.8rem" }}>
            {dados.sem_meta.map((item) => <LinhaSemMeta key={item.chave} item={item} />)}
          </div>
        </div>
      )}

      <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "1rem" }}>
        Atualizado em {new Date(dados.atualizado_em + "T00:00:00").toLocaleDateString("pt-BR")}
      </p>
    </div>
  );
}
