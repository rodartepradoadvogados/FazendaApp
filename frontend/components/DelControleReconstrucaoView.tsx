"use client";
// Configurações > Cadastro/Manutenção — ferramenta administrativa, ONE-TIME,
// de correção de dado histórico: `ControleLeiteiro.del_no_controle` era
// copiado de `Animal.del_dias` (o DEL "ao vivo" do animal no MOMENTO do
// lançamento) em vez de calculado a partir da própria data do controle —
// todo controle lançado no mesmo intervalo "parado" herdava o mesmo DEL
// errado, não importa a data real de cada um. Isso contamina a curva de
// lactação (da vaca e de referência do rebanho/grupo) e o dashboard de
// produção. A gravação de controles novos já está corrigida; esta tela só
// corrige o histórico gravado antes da correção.
//
// Mesma trava report-first do endpoint que esta tela consome (ver
// fazenda/api/routers/producao.py): relatório primeiro, sempre; gravação só
// com confirmação explícita — e só liberada aqui depois que o relatório já
// foi visto pelo menos uma vez.
import { useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, RefreshCcw, ShieldAlert, TrendingUp } from "lucide-react";
import { fetchDivergenciasDelControle, reconstruirDelControle, type DivergenciasDelControle } from "@/lib/api";

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

function Del({ v }: { v: number | null }) {
  if (v == null) return <span style={{ fontStyle: "italic", color: "var(--text-muted)" }}>sem lactação</span>;
  return <span>{v}</span>;
}

export function DelControleReconstrucaoView() {
  const [relatorio, setRelatorio] = useState<DivergenciasDelControle | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [jaViuRelatorio, setJaViuRelatorio] = useState(false);
  const [corrigindo, setCorrigindo] = useState(false);
  const [resultado, setResultado] = useState<number | null>(null);

  const carregarRelatorio = async () => {
    setCarregando(true); setErro(null);
    try {
      const r = await fetchDivergenciasDelControle();
      setRelatorio(r);
      setJaViuRelatorio(true);
      setResultado(null);
    } catch (e: any) { setErro(e.message); }
    finally { setCarregando(false); }
  };

  const confirmarECorrigir = async () => {
    if (!relatorio) return;
    const gravaveis = relatorio.muda - relatorio.sem_lactacao;
    const aviso = relatorio.muda === 0
      ? "Nenhum controle divergente — não há nada para corrigir. Confirmar mesmo assim?"
      : `Isto vai reescrever o DEL de ${gravaveis} controle(s) leiteiro(s) já lançado(s)` +
        (relatorio.sem_lactacao > 0
          ? ` (${relatorio.sem_lactacao} outro(s) não tem lactação aberta na data e ficará(ão) intocado(s), por não ter resposta honesta a gravar)`
          : "") +
        `. É uma correção de dado histórico — não some pesagem nem produção, só o DEL de cada controle. Confirmar e corrigir agora?`;
    if (!confirm(aviso)) return;
    setCorrigindo(true); setErro(null);
    try {
      const r = await reconstruirDelControle(true);
      setResultado(r.gravados);
      // Relatório fica desatualizado depois da gravação — busca de novo pra
      // tela sempre refletir o estado real do banco.
      const atualizado = await fetchDivergenciasDelControle();
      setRelatorio(atualizado);
    } catch (e: any) { setErro(e.message); }
    finally { setCorrigindo(false); }
  };

  return (
    <Card titulo="DEL do Controle Leiteiro — correção de dado histórico" icon={TrendingUp}>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.9rem" }}>
        Todo controle leiteiro deveria guardar o DEL (dias em lactação) vigente NA DATA em que foi feito — não o
        DEL do animal no momento do lançamento. Como isso já foi corrigido só para lançamentos NOVOS, o histórico
        anterior pode ter controles com DEL congelado (dois controles em datas bem diferentes com o mesmo DEL),
        o que distorce a curva de lactação da vaca e as curvas de referência do rebanho. Ferramenta pontual de
        correção — normalmente só precisa ser rodada uma vez.
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
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
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
              <p style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Sem lactação aberta na data</p>
              <p style={{ fontSize: "1.1rem", fontWeight: 700 }}>{relatorio.sem_lactacao}</p>
            </div>
          </div>

          {relatorio.muda === 0 ? (
            <p style={{ fontSize: "0.82rem", color: "var(--green-light)", display: "flex", alignItems: "center", gap: "0.35rem", marginBottom: "0.9rem" }}>
              <CheckCircle2 size={14} /> Nenhuma divergência — o DEL já está correto em todos os controles desta fazenda.
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
                      <td><Del v={a.del_hoje} /></td>
                      <td><Del v={a.del_correto} /></td>
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
            title={relatorio.muda === 0 ? "Nada para corrigir" : "Grava o DEL correto nos controles divergentes"}
          >
            {corrigindo ? <Loader2 size={16} className="animate-spin" /> : <ShieldAlert size={16} />}
            Confirmar e corrigir
          </button>
        </>
      )}
    </Card>
  );
}
