"use client";
// Configurações > Cadastro/Manutenção — ferramenta administrativa, ONE-TIME,
// de correção de dado histórico: `ControleLeiteiro.ordem_parto` nunca foi
// gravado por nenhuma das quatro vias de entrada, então a tela caía num
// atalho (contagem TOTAL de partos do animal, aplicada a todo o histórico
// dele) — uma vaca hoje de 5ª cria aparecia como "5ª" até nos controles de
// quando era primípara, o que contamina qualquer cálculo ajustado por idade/
// ordem de parto (Equivalente Maduro, curva de lactação por ordem).
//
// Mesma trava report-first do script/endpoint que esta tela consome (ver
// fazenda/api/routers/producao.py e scripts/reconstruir_ordem_parto.py):
// relatório primeiro, sempre; gravação só com confirmação explícita — e só
// liberada aqui depois que o relatório já foi visto pelo menos uma vez.
import { useState } from "react";
import { AlertTriangle, CheckCircle2, History, Loader2, RefreshCcw, ShieldAlert } from "lucide-react";
import { fetchDivergenciasOrdemParto, reconstruirOrdemParto, type DivergenciasOrdemParto } from "@/lib/api";

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

export function OrdemPartoReconstrucaoView() {
  const [relatorio, setRelatorio] = useState<DivergenciasOrdemParto | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [jaViuRelatorio, setJaViuRelatorio] = useState(false);
  const [corrigindo, setCorrigindo] = useState(false);
  const [resultado, setResultado] = useState<number | null>(null);

  const carregarRelatorio = async () => {
    setCarregando(true); setErro(null);
    try {
      const r = await fetchDivergenciasOrdemParto();
      setRelatorio(r);
      setJaViuRelatorio(true);
      setResultado(null);
    } catch (e: any) { setErro(e.message); }
    finally { setCarregando(false); }
  };

  const confirmarECorrigir = async () => {
    if (!relatorio) return;
    const aviso = relatorio.muda === 0
      ? "Nenhum controle divergente — não há nada para corrigir. Confirmar mesmo assim?"
      : `Isto vai reescrever a ordem de parto de ${relatorio.muda} controle(s) leiteiro(s) já lançado(s) ` +
        `(${relatorio.vira_desconhecido} deles passará(ão) a ficar "sem ordem", por não terem resposta ` +
        `honesta a gravar). É uma correção de dado histórico — não some pesagem nem produção, só o rótulo ` +
        `de ordem de parto de cada controle. Confirmar e corrigir agora?`;
    if (!confirm(aviso)) return;
    setCorrigindo(true); setErro(null);
    try {
      const r = await reconstruirOrdemParto(true);
      setResultado(r.gravados);
      // Relatório fica desatualizado depois da gravação — busca de novo pra
      // tela sempre refletir o estado real do banco.
      const atualizado = await fetchDivergenciasOrdemParto();
      setRelatorio(atualizado);
    } catch (e: any) { setErro(e.message); }
    finally { setCorrigindo(false); }
  };

  return (
    <Card titulo="Ordem de parto — correção de dado histórico" icon={History}>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.9rem" }}>
        Todo controle leiteiro deveria guardar a ordem de parto vigente NA DATA em que foi feito — não a ordem
        atual do animal. Como isso nunca foi gravado, a tela de Produção mostra hoje a contagem total de partos
        aplicada a todo o histórico (uma vaca de 5ª cria aparece como "5ª" até nos controles de quando era
        primípara), o que distorce o Equivalente Maduro e qualquer cálculo por ordem de parto. Ferramenta
        pontual de correção — normalmente só precisa ser rodada uma vez.
      </p>

      {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}

      {resultado !== null && (
        <div className="card mb-3" style={{ borderLeft: "3px solid var(--green)", color: "var(--green-light)", fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <CheckCircle2 size={16} /> {resultado} controle(s) corrigido(s).
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
              <p style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Controles leiteiros</p>
              <p style={{ fontSize: "1.1rem", fontWeight: 700 }}>{relatorio.controles}</p>
            </div>
            <div>
              <p style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Controles que mudariam</p>
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
              <CheckCircle2 size={14} /> Nenhuma divergência — a ordem de parto já está correta em todos os controles desta fazenda.
            </p>
          ) : (
            <div style={{ overflowX: "auto", marginBottom: "0.9rem" }}>
              <table className="fazenda-table">
                <thead><tr><th>Vaca</th><th>Data do controle</th><th>Mostra hoje</th><th>Correto</th></tr></thead>
                <tbody>
                  {relatorio.amostra.map((a, i) => (
                    <tr key={`${a.numero_matriz}-${a.data_controle}-${i}`}>
                      <td>{a.numero_matriz}</td>
                      <td>{formatarData(a.data_controle)}</td>
                      <td><Ordem v={a.ordem_hoje} /></td>
                      <td><Ordem v={a.ordem_correta} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {relatorio.muda > relatorio.amostra.length && (
                <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                  Mostrando {relatorio.amostra.length} de {relatorio.muda} controle(s) que mudariam.
                </p>
              )}
            </div>
          )}

          <button
            className="btn-primary"
            onClick={confirmarECorrigir}
            disabled={!jaViuRelatorio || corrigindo || relatorio.muda === 0}
            title={relatorio.muda === 0 ? "Nada para corrigir" : "Grava a ordem de parto correta nos controles divergentes"}
          >
            {corrigindo ? <Loader2 size={16} className="animate-spin" /> : <ShieldAlert size={16} />}
            Confirmar e corrigir
          </button>
        </>
      )}
    </Card>
  );
}
