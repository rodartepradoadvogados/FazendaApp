"use client";
// Auditoria da classificação reprodutiva (só administrador) — onde o estado que o sistema dá a um animal não bate com
// os dados dele ou com a outra leitura do sistema (estado ao vivo × roteiro do veterinário). Backend:
// GET /reproducao/auditoria-classificacao e rules/auditoria_classificacao.py. Só leitura: mostra a causa; corrigir o
// dado é por Excluir lançamento / edição do serviço.
import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, Search } from "lucide-react";
import { fetchAuditoriaClassificacao, type AchadoAuditoria, type AuditoriaClassificacao, type FichaAuditoriaAnimal } from "@/lib/api";
import { ROTULO_ESTADO } from "@/lib/estadoReprodutivo";
import { ErroCarregamento, TelaSkeleton } from "@/components/ui";

const ROTULO_CODIGO: Record<string, string> = {
  reconfirmada_nao_gestante: "Prenhez confirmada, estado não é gestante",
  classificadores_divergem: "Estado ao vivo × roteiro do veterinário",
  datas_incoerentes: "Datas ou resultados incoerentes",
  ult_ocorrencia_diverge: "«Último serviço» fora do mais recente",
  gestante_alem_do_parto_previsto: "Gestante além do parto previsto",
};
const ROTULO_LISTA: Record<string, string> = {
  inseminadas_1_29: "Inseminadas 1–29 d", inseminadas_30_59: "Inseminadas 30–59 d", inseminadas_60_mais: "Inseminadas 60+ d",
  novilhas_aptas_vazias: "Novilhas aptas vazias", novilhas_gestantes: "Novilhas gestantes", verificar_pre_parto: "Pré-parto",
  vacas_gestantes: "Vacas gestantes", vazias_por_diagnostico: "Vazias por diagnóstico", pendentes_classificacao: "Pendentes de classificação",
};
const fmtDia = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "sem data");

export default function AuditoriaClassificacao() {
  const [dados, setDados] = useState<AuditoriaClassificacao | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [filtro, setFiltro] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [ficha, setFicha] = useState<FichaAuditoriaAnimal | null>(null);
  const [erroFicha, setErroFicha] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true); setErro(null);
    try { setDados(await fetchAuditoriaClassificacao()); }
    catch (e) { setErro(e instanceof Error ? e.message : "Erro ao auditar"); }
    finally { setCarregando(false); }
  }, []);
  useEffect(() => { carregar(); }, [carregar]);

  const abrirFicha = useCallback(async (numero: string) => {
    setErroFicha(null);
    try { setFicha((await fetchAuditoriaClassificacao(numero)).animal ?? null); }
    catch (e) { setFicha(null); setErroFicha(e instanceof Error ? e.message : "Erro ao abrir o animal"); }
  }, []);

  const linhas = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return (dados?.achados ?? []).filter((a) => (!filtro || a.codigo === filtro) && (!q || a.numero.toLowerCase().includes(q)));
  }, [dados, filtro, busca]);

  if (erro && !dados) return <ErroCarregamento mensagem={erro} onRetry={carregar} />;
  if (!dados) return <TelaSkeleton />;

  return (
    <div>
      <div className="mb-4">
        <h2 style={{ fontSize: "1.05rem", fontWeight: 700 }}>Auditoria da classificação</h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", maxWidth: "70ch" }}>
          Compara, animal a animal, o estado reprodutivo ao vivo, o roteiro do veterinário e os registros brutos (serviços, partos,
          lactações). Só mostra o que não bate, com a causa. {dados.total_animais} animais auditados em {fmtDia(dados.data_referencia)}.
        </p>
      </div>

      <div className="flex items-center gap-2" style={{ flexWrap: "wrap", marginBottom: "0.8rem" }} role="group" aria-label="Tipo de achado">
        <button type="button" className="ft-pilula" aria-pressed={filtro === null} onClick={() => setFiltro(null)}>Todos<b>{dados.total_achados}</b></button>
        {Object.entries(dados.resumo).map(([codigo, n]) => (
          <button key={codigo} type="button" className="ft-pilula" aria-pressed={filtro === codigo} onClick={() => setFiltro(filtro === codigo ? null : codigo)}>
            {ROTULO_CODIGO[codigo] ?? codigo}<b>{n}</b>
          </button>
        ))}
        <span style={{ flex: 1 }} />
        <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8rem" }}>
          <Search size={14} aria-hidden="true" />
          <input type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Animal nº" aria-label="Filtrar por número do animal"
            onKeyDown={(e) => { if (e.key === "Enter" && busca.trim()) abrirFicha(busca.trim()); }}
            style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.5rem", width: "9rem" }} />
        </label>
        <button type="button" className="btn-ghost" onClick={() => busca.trim() && abrirFicha(busca.trim())} disabled={!busca.trim()} title="Abrir a linha do tempo e o passo a passo deste animal">Ver animal</button>
        <button type="button" className="btn-ghost" onClick={carregar} disabled={carregando} aria-label="Reler" title="Reler"><RefreshCw size={14} aria-hidden="true" /></button>
      </div>

      {erroFicha && <p role="alert" style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erroFicha}</p>}
      {ficha && <FichaAnimal ficha={ficha} onFechar={() => setFicha(null)} />}

      {dados.total_achados === 0 ? (
        <p style={{ fontSize: "0.85rem", color: "var(--ft-verde)", fontWeight: 700 }}>Nenhuma inconsistência: a classificação bate com os registros de todos os animais.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="tabela-compacta" style={{ width: "100%" }}>
            <thead><tr>
              <th scope="col">Animal</th><th scope="col">Estado ao vivo</th><th scope="col">Roteiro do veterinário</th><th scope="col">Achado</th><th scope="col">Por quê</th>
            </tr></thead>
            <tbody>
              {linhas.map((a: AchadoAuditoria, i) => (
                <tr key={`${a.numero}-${a.codigo}-${i}`}>
                  <td style={{ fontWeight: 800 }}>
                    <button type="button" className="btn-ghost" style={{ padding: "0.1rem 0.4rem", fontWeight: 800 }} onClick={() => abrirFicha(a.numero)} title="Ver a linha do tempo deste animal">{a.numero}</button>
                  </td>
                  <td>{a.estado ? (ROTULO_ESTADO[a.estado] ?? a.estado) : "—"}</td>
                  <td style={{ whiteSpace: "normal" }}>{a.roteiro.length ? a.roteiro.map((l) => ROTULO_LISTA[l] ?? l).join(", ") : "nenhuma lista"}</td>
                  <td style={{ whiteSpace: "normal" }}>
                    <span style={{ color: a.severidade === "alta" ? "var(--ft-verm)" : "var(--ft-ambar)", fontWeight: 700, fontSize: "0.7rem", letterSpacing: "0.06em", textTransform: "uppercase" }}>{a.severidade === "alta" ? "Alta" : "Média"}</span>{" "}
                    {a.titulo}
                  </td>
                  <td style={{ whiteSpace: "normal", minWidth: "22rem", color: "var(--text-muted)" }}>{a.explicacao}</td>
                </tr>
              ))}
              {linhas.length === 0 && <tr><td colSpan={5} style={{ padding: "0.8rem", color: "var(--text-muted)" }}>Nenhum achado com este filtro.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function FichaAnimal({ ficha, onFechar }: { ficha: FichaAuditoriaAnimal; onFechar: () => void }) {
  return (
    <section aria-label={`Como o sistema classificou o animal ${ficha.numero}`} style={{ border: "1px solid var(--border)", background: "var(--surface)", padding: "0.8rem 1rem", margin: "0 0 1rem" }}>
      <div className="flex items-center" style={{ justifyContent: "space-between", gap: "1rem" }}>
        <strong style={{ fontSize: "0.95rem" }}>Animal {ficha.numero} — como o sistema chegou ao estado dele</strong>
        <button type="button" className="btn-ghost" onClick={onFechar} style={{ fontSize: "0.75rem" }}>Fechar</button>
      </div>
      <ol style={{ margin: "0.6rem 0 0.8rem 1.1rem", fontSize: "0.82rem", lineHeight: 1.55 }}>
        {ficha.passos.map((p, i) => <li key={i}>{p}</li>)}
      </ol>
      <div style={{ fontSize: "0.7rem", fontWeight: 600, letterSpacing: "0.13em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: "0.3rem" }}>Linha do tempo</div>
      <ul style={{ listStyle: "none", margin: 0, padding: 0, fontSize: "0.82rem" }}>
        {ficha.linha_do_tempo.map((l, i) => (
          <li key={i} style={{ display: "flex", gap: "0.75rem", padding: "0.25rem 0", borderTop: i ? "1px solid var(--border)" : 0 }}>
            <span style={{ width: "5.5rem", flex: "none", fontVariantNumeric: "tabular-nums", color: "var(--text-muted)" }}>{fmtDia(l.data)}</span>
            <span style={{ width: "4.5rem", flex: "none", fontWeight: 700, textTransform: "uppercase", fontSize: "0.68rem", letterSpacing: "0.06em", color: l.tipo === "parto" ? "var(--ft-verde)" : l.tipo === "lactacao" ? "var(--ft-ambar)" : "var(--ft-aco)" }}>{l.tipo === "servico" ? "Serviço" : l.tipo === "parto" ? "Parto" : "Lactação"}</span>
            <span>{l.texto}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
