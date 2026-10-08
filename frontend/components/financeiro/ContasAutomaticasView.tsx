"use client";
// Configurações > Parâmetros financeiros > Contas automáticas (Fase A, PR 2).
// A conta gerencial padrão de cada origem de lançamento que o sistema cria
// sozinho (folha, férias, 13º, rescisão, encargos, contrato, empreita, diária,
// vale, caixa do funcionário). Com as regras novas dos relatórios ligadas, a
// nota nasce com itens nessas contas (a folha pelo bruto) em vez de cair em
// "não classificado" na DRE. A sugestão pelo nome do plano nunca é aplicada
// sozinha: a conta errada jogaria a folha inteira na linha errada.
import { useEffect, useMemo, useState } from "react";
import { Workflow, AlertTriangle, Check } from "lucide-react";
import { fetchContasAutomaticas, fetchPlanoContas, salvarContaAutomatica, type OrigemContaAutomatica } from "@/lib/api";
import { rotuloNatureza } from "@/lib/naturezaFin";

type ContaPlano = { codigo: string; nome: string; ativa: boolean };

const selStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem",
};

export default function ContasAutomaticasView() {
  const [origens, setOrigens] = useState<OrigemContaAutomatica[] | null>(null);
  const [regrasV2, setRegrasV2] = useState(false);
  const [plano, setPlano] = useState<ContaPlano[]>([]);
  const [salvando, setSalvando] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [salvo, setSalvo] = useState<string | null>(null);

  useEffect(() => {
    fetchContasAutomaticas().then((d) => { setOrigens(d.origens); setRegrasV2(d.regras_v2); }).catch((e) => setErro(e.message));
    fetchPlanoContas().then((c: ContaPlano[]) => setPlano(
      [...c].filter((x) => x.ativa !== false).sort((a, b) => a.codigo.localeCompare(b.codigo, undefined, { numeric: true })),
    )).catch(() => setPlano([]));
  }, []);

  const rotuloOrigem = useMemo(
    () => Object.fromEntries((origens ?? []).map((o) => [o.origem, o.rotulo])),
    [origens],
  );

  const salvar = async (origem: string, codigo: string | null) => {
    setSalvando(origem); setErro(null); setSalvo(null);
    try {
      const d = await salvarContaAutomatica(origem, codigo);
      setOrigens(d.origens); setRegrasV2(d.regras_v2); setSalvo(origem);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Erro ao salvar");
    } finally {
      setSalvando(null);
    }
  };

  return (
    <div className="card">
      <div className="card-header mb-2 flex items-center gap-2"><Workflow size={14} /> Contas automáticas</div>
      <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
        Em que conta gerencial entram os lançamentos que o sistema cria sozinho. A folha entra pelo{" "}
        <strong>bruto</strong>: salário e encargos em Gastos com pessoal; INSS e IRRF retidos, vale e FGTS a recolher
        ficam fora da DRE (já estão no custo). Origem sem conta usa a conta indicada em “usa a de”, ou vira pendência
        na DRE.
      </p>
      {!regrasV2 && (
        <p style={{ fontSize: "0.76rem", color: "var(--amber)", marginBottom: "0.75rem" }}>
          <AlertTriangle size={12} aria-hidden style={{ display: "inline", marginRight: 4, verticalAlign: "-2px" }} />
          As regras novas dos relatórios ainda estão desligadas nesta fazenda: a configuração fica guardada e passa a
          valer quando forem ligadas (aba Parâmetros). O histórico ganha as contas pelo backfill.
        </p>
      )}
      {erro && <div className="alert-critico mb-3"><span>{erro}</span></div>}
      {!origens && !erro && <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Carregando…</p>}
      {origens && (
        <div className="overflow-x-auto">
          <table className="fazenda-table" style={{ margin: 0 }}>
            <thead>
              <tr><th>Origem</th><th style={{ width: "20rem" }}>Conta gerencial</th><th>Situação</th></tr>
            </thead>
            <tbody>
              {origens.map((o) => {
                const fora = o.natureza_padrao !== "OPERACIONAL";
                return (
                  <tr key={o.origem}>
                    <td style={{ fontSize: "0.78rem" }}>
                      <div style={{ fontWeight: 600 }}>{o.rotulo}</div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{o.ajuda}</div>
                    </td>
                    <td>
                      <select
                        style={selStyle}
                        value={o.codigo_conta_gerencial ?? ""}
                        disabled={salvando === o.origem}
                        onChange={(e) => salvar(o.origem, e.target.value || null)}
                        aria-label={`Conta de ${o.rotulo}`}
                      >
                        <option value="">{o.reserva ? `Usar a de ${rotuloOrigem[o.reserva] ?? o.reserva}` : "Sem conta"}</option>
                        {plano.map((c) => <option key={c.codigo} value={c.codigo}>{c.codigo} — {c.nome}</option>)}
                      </select>
                    </td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                      {salvo === o.origem && <span style={{ color: "var(--green-light)", marginRight: "0.4rem" }}><Check size={12} aria-hidden style={{ display: "inline", verticalAlign: "-2px" }} /> salvo</span>}
                      {fora && <div>Fora da DRE: {rotuloNatureza(o.natureza_fin || o.natureza_padrao)}</div>}
                      {!o.codigo_conta_gerencial && o.conta_efetiva && o.conta_efetiva_de && (
                        <div>Usa a de {rotuloOrigem[o.conta_efetiva_de] ?? o.conta_efetiva_de} ({o.conta_efetiva})</div>
                      )}
                      {!o.conta_efetiva && !fora && (
                        <div style={{ color: "var(--amber)" }}>Sem conta: cai em “não classificado” na DRE</div>
                      )}
                      {o.sugestao && (
                        <button
                          type="button"
                          onClick={() => salvar(o.origem, o.sugestao!.codigo)}
                          disabled={salvando === o.origem}
                          style={{ background: "transparent", border: "1px solid var(--border)", borderRadius: "var(--r-sm)",
                            color: "var(--text)", fontSize: "0.7rem", padding: "0.15rem 0.45rem", marginTop: "0.2rem", cursor: "pointer" }}
                        >
                          Usar sugestão: {o.sugestao.codigo} — {o.sugestao.nome}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
