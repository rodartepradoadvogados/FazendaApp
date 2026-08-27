"use client";
// Configurações > Cadastro/Manutenção — ferramenta administrativa, ONE-TIME,
// de correção de dado histórico: `Parto.ordem_parto` (a FONTE do dado, não o
// derivado em ControleLeiteiro — ver OrdemPartoReconstrucaoView, logo abaixo
// desta na tela). Toda matriz cujo primeiro parto veio da importação de
// planilha do Ideagri pode ter `ordem_parto` errado: a planilha usa uma
// convenção base 0 (0 = 1ª cria), diferente da deste app (1 = 1ª cria) — e o
// erro se propagava para todo parto lançado depois pelo app (a versão antiga
// de `proxima_ordem_parto` confiava no `max()` do que já estava gravado).
//
// Mesma trava report-first do irmão de Controles: relatório primeiro,
// sempre; gravação só com confirmação explícita — e só liberada aqui depois
// que o relatório já foi visto pelo menos uma vez.
import { useState } from "react";
import { AlertTriangle, CheckCircle2, History, Loader2, RefreshCcw, ShieldAlert } from "lucide-react";
import {
  fetchDivergenciasOrdemPartoPartos, reconstruirOrdemPartoPartos, type DivergenciasOrdemPartoPartos,
} from "@/lib/api";

function Card({ titulo, icon: Icon, children }: { titulo: string; icon: any; children: React.ReactNode }) {
  return (
    <div className="card" style={{ marginBottom: "1rem" }}>
      <div className="card-header flex items-center gap-2"><Icon size={16} /> {titulo}</div>
      <div style={{ padding: "0.9rem 1rem" }}>{children}</div>
    </div>
  );
}

function formatarData(iso: string | null): string {
  if (!iso) return "—";
  const [ano, mes, dia] = iso.split("-");
  return `${dia}/${mes}/${ano}`;
}

function Ordem({ v }: { v: number | null }) {
  if (v == null) return <span style={{ fontStyle: "italic", color: "var(--text-muted)" }}>sem ordem</span>;
  return <span>{v}ª</span>;
}

export function OrdemPartoPartosReconstrucaoView() {
  const [relatorio, setRelatorio] = useState<DivergenciasOrdemPartoPartos | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [jaViuRelatorio, setJaViuRelatorio] = useState(false);
  const [corrigindo, setCorrigindo] = useState(false);
  const [resultado, setResultado] = useState<number | null>(null);

  const carregarRelatorio = async () => {
    setCarregando(true); setErro(null);
    try {
      const r = await fetchDivergenciasOrdemPartoPartos();
      setRelatorio(r);
      setJaViuRelatorio(true);
      setResultado(null);
    } catch (e: any) { setErro(e.message); }
    finally { setCarregando(false); }
  };

  const confirmarECorrigir = async () => {
    if (!relatorio) return;
    const aviso = relatorio.muda === 0
      ? "Nenhum parto divergente — não há nada para corrigir. Confirmar mesmo assim?"
      : `Isto vai reescrever a ordem de parto de ${relatorio.muda} parto(s) já lançado(s) ` +
        `(${relatorio.vira_desconhecido} deles passará(ão) a ficar "sem ordem", por não terem resposta ` +
        `honesta a gravar — abortos sem abertura de lactação). É uma correção de dado histórico — não some ` +
        `cria nem lactação, só o rótulo de ordem de parto de cada parto. Confirmar e corrigir agora?`;
    if (!confirm(aviso)) return;
    setCorrigindo(true); setErro(null);
    try {
      const r = await reconstruirOrdemPartoPartos(true);
      setResultado(r.gravados);
      // Relatório fica desatualizado depois da gravação — busca de novo pra
      // tela sempre refletir o estado real do banco.
      const atualizado = await fetchDivergenciasOrdemPartoPartos();
      setRelatorio(atualizado);
    } catch (e: any) { setErro(e.message); }
    finally { setCorrigindo(false); }
  };

  return (
    <Card titulo="Ordem de parto — correção de dado histórico (Partos)" icon={History}>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.9rem" }}>
        Todo parto importado de planilha (Ideagri) traz a coluna "ORDEM DE PARTO" na convenção de origem
        (0 = 1ª cria), diferente da deste app (1 = 1ª cria) — e esse erro se propagava para todo parto
        lançado depois pelo app. Esta ferramenta recalcula, para cada matriz, a ordem de parto CONTANDO os
        partos produtivos dela em ordem cronológica, do zero, ignorando qualquer valor já gravado. Rode
        esta ferramenta ANTES da de "Controles" logo abaixo: ela lê a ordem de parto gravada aqui como
        fonte de verdade — uma vez os Partos corrigidos, a de Controles volta a mostrar os números certos
        na próxima vez que rodar, sem precisar de nenhuma mudança nela. Ferramenta pontual de correção —
        normalmente só precisa ser rodada uma vez.
      </p>

      {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}

      {resultado !== null && (
        <div className="card mb-3" style={{ borderLeft: "3px solid var(--green)", color: "var(--green-light)", fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <CheckCircle2 size={16} /> {resultado} parto(s) corrigido(s).
        </div>
      )}

      <button className="btn-ghost" onClick={carregarRelatorio} disabled={carregando} style={{ marginBottom: "0.9rem" }}>
        {carregando ? <Loader2 size={14} className="animate-spin" /> : <RefreshCcw size={14} />}
        {relatorio ? "Atualizar relatório" : "Ver divergências"}
      </button>

      {relatorio && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <div>
              <p style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Partos no histórico</p>
              <p style={{ fontSize: "1.1rem", fontWeight: 700 }}>{relatorio.partos}</p>
            </div>
            <div>
              <p style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Matrizes com parto</p>
              <p style={{ fontSize: "1.1rem", fontWeight: 700 }}>{relatorio.matrizes_com_parto}</p>
            </div>
            <div>
              <p style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Partos que mudariam</p>
              <p style={{ fontSize: "1.1rem", fontWeight: 700, color: relatorio.muda > 0 ? "var(--dourado-light)" : "var(--text)" }}>
                {relatorio.muda}
              </p>
            </div>
            <div>
              <p style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Virariam "sem ordem"</p>
              <p style={{ fontSize: "1.1rem", fontWeight: 700 }}>{relatorio.vira_desconhecido}</p>
            </div>
          </div>

          {relatorio.muda === 0 ? (
            <p style={{ fontSize: "0.82rem", color: "var(--green-light)", display: "flex", alignItems: "center", gap: "0.35rem", marginBottom: "0.9rem" }}>
              <CheckCircle2 size={14} /> Nenhuma divergência — a ordem de parto já está correta em todos os partos desta fazenda.
            </p>
          ) : (
            <div style={{ overflowX: "auto", marginBottom: "0.9rem" }}>
              <table className="fazenda-table">
                <thead><tr><th>Vaca</th><th>Data do parto</th><th>Mostra hoje</th><th>Correto</th></tr></thead>
                <tbody>
                  {relatorio.amostra.map((a, i) => (
                    <tr key={`${a.numero_matriz}-${a.data_parto}-${i}`}>
                      <td>{a.numero_matriz}</td>
                      <td>{formatarData(a.data_parto)}</td>
                      <td><Ordem v={a.ordem_hoje} /></td>
                      <td><Ordem v={a.ordem_correta} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {relatorio.muda > relatorio.amostra.length && (
                <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                  Mostrando {relatorio.amostra.length} de {relatorio.muda} parto(s) que mudariam.
                </p>
              )}
            </div>
          )}

          <button
            className="btn-primary"
            onClick={confirmarECorrigir}
            disabled={!jaViuRelatorio || corrigindo || relatorio.muda === 0}
            title={relatorio.muda === 0 ? "Nada para corrigir" : "Grava a ordem de parto correta nos partos divergentes"}
          >
            {corrigindo ? <Loader2 size={16} className="animate-spin" /> : <ShieldAlert size={16} />}
            Confirmar e corrigir
          </button>
        </>
      )}
    </Card>
  );
}
