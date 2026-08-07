"use client";
// Remédios por doença — consulta rápida do substituto inteligente: escolhe a
// doença e vê o ranking de princípios ativos indicados (1ª escolha, 2ª opção…)
// já cruzado com o estoque em tempo real. Mesmo padrão visual de Farmacia.tsx.
import { useEffect, useMemo, useState } from "react";
import { Pill, AlertTriangle } from "lucide-react";
import { fetchDoencas, fetchIndicacoesDoenca, type OpcaoIndicacaoDoenca } from "@/lib/api";

// Mesmos tipos de Doenca.TIPOS (backend) — agrupam o seletor em optgroups
// para "lançar por finalidade reprodutiva/produtiva/preventiva/suporte"
// aparecer separado das doenças propriamente ditas.
const GRUPOS_TIPO: [string, string][] = [
  ["doenca", "Doenças"], ["reprodutivo", "Reprodutivo"], ["produtivo", "Produtivo"],
  ["preventivo", "Preventivo"], ["suporte", "Suporte"],
];

function num(v?: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
}

function corStatus(status: OpcaoIndicacaoDoenca["status_estoque"]): string {
  if (status === "out") return "var(--red)";
  if (status === "low") return "var(--amber)";
  return "var(--green-light)";
}

const input: React.CSSProperties = {
  padding: "0.4rem 0.55rem", borderRadius: 6, fontSize: "0.82rem",
  background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)",
};

export default function RemediosPorDoenca() {
  const [doencas, setDoencas] = useState<{ id: number; nome: string; ativo: boolean; tipo?: string | null }[] | null>(null);
  const [doencaId, setDoencaId] = useState<number | "">("");
  const [opcoes, setOpcoes] = useState<OpcaoIndicacaoDoenca[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { fetchDoencas().then(setDoencas).catch((e) => setErro(e.message)); }, []);

  // Agrupa por tipo (Doenças / Reprodutivo / Produtivo / Preventivo / Suporte)
  // — mesma ordem de GRUPOS_TIPO; indicações de tipo desconhecido caem no
  // grupo "Doenças" (comportamento anterior ao campo `tipo` existir).
  const grupos = useMemo(() => {
    const ativas = (doencas || []).filter((d) => d.ativo);
    return GRUPOS_TIPO
      .map(([tipo, label]) => ({
        label,
        itens: ativas.filter((d) => (tipo === "doenca" ? !d.tipo || d.tipo === "doenca" : d.tipo === tipo)),
      }))
      .filter((g) => g.itens.length > 0);
  }, [doencas]);

  useEffect(() => {
    if (doencaId === "") { setOpcoes(null); return; }
    setOpcoes(null);
    setErro(null);
    fetchIndicacoesDoenca(doencaId).then((r) => setOpcoes(r.opcoes)).catch((e) => setErro(e.message));
  }, [doencaId]);

  return (
    <div>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.8rem" }}>
        Escolha a doença e veja o ranking de medicamentos indicados (1ª escolha, 2ª opção…), já cruzado com o
        estoque em tempo real — resposta rápida para "que remédio eu uso para essa doença?".
      </p>

      <div className="mb-3">
        <select style={{ ...input, minWidth: 260 }} value={doencaId}
          onChange={(e) => setDoencaId(e.target.value === "" ? "" : Number(e.target.value))}>
          <option value="">Selecione a doença…</option>
          {grupos.map((g) => (
            <optgroup key={g.label} label={g.label}>
              {g.itens.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
            </optgroup>
          ))}
        </select>
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}

      {doencaId === "" ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Escolha uma doença para ver os remédios indicados.</p>
      ) : opcoes === null ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>
      ) : opcoes.length === 0 ? (
        <p style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.82rem", fontWeight: 600, color: "var(--amber)", background: "rgba(217,119,6,0.1)", border: "1px solid var(--amber)", borderRadius: 8, padding: "0.6rem 0.8rem" }}>
          <AlertTriangle size={15} style={{ flexShrink: 0 }} />
          Nenhum medicamento indicado ainda para esta doença — cadastre em Configurações &gt; Cadastro &gt; Sanitário &gt; Princípio ativo.
        </p>
      ) : (
        <div className="space-y-2">
          {opcoes.map((o) => <CardOpcao key={o.principio_ativo_id} o={o} />)}
        </div>
      )}
    </div>
  );
}

function CardOpcao({ o }: { o: OpcaoIndicacaoDoenca }) {
  const cor = corStatus(o.status_estoque);
  const primeiraEscolha = o.prioridade === 1;
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 10, background: "var(--surface-2)", padding: "0.7rem 0.9rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.7rem" }}>
        <span style={{
          fontSize: "0.66rem", fontWeight: 800, borderRadius: 4, padding: "0.15rem 0.4rem", flexShrink: 0, whiteSpace: "nowrap",
          ...(primeiraEscolha
            ? { border: "1px solid var(--dourado)", color: "var(--dourado-light)" }
            : { border: "1px solid var(--border)", color: "var(--text-muted)" }),
        }}>
          {primeiraEscolha ? "1ª ESCOLHA" : `${o.prioridade}ª OPÇÃO`}
        </span>
        <span style={{ width: 10, height: 10, borderRadius: "50%", background: cor, flexShrink: 0 }} title="Situação do estoque" />
        <span style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontWeight: 700 }}>
            <Pill size={14} style={{ color: "var(--dourado-light)" }} />
            {o.nome}
          </span>
          {o.classificacao && <span style={{ display: "block", fontSize: "0.72rem", color: "var(--text-muted)" }}>{o.classificacao}</span>}
        </span>
        <span style={{ textAlign: "right", flexShrink: 0 }}>
          {o.status_estoque === "out" ? (
            <span style={{ fontWeight: 800, fontSize: "0.85rem", color: "var(--red)" }}>Sem estoque</span>
          ) : (
            <span style={{ fontWeight: 800, fontSize: "0.85rem", color: cor }}>
              {num(o.total_apresentacoes)} {o.unidade_apresentacao || "un"}{o.total_apresentacoes === 1 ? "" : "s"}
            </span>
          )}
        </span>
      </div>
      {o.marcas.length > 0 && (
        <div className="flex flex-wrap gap-1" style={{ marginTop: "0.55rem", paddingLeft: "2.6rem" }}>
          {o.marcas.map((m) => (
            <span key={m} style={{ fontSize: "0.7rem", color: "var(--text-muted)", border: "1px solid var(--border)", borderRadius: 999, padding: "0.1rem 0.55rem" }}>
              {m}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
