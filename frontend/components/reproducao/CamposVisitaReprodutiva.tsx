"use client";
// Os dois campos da rotina de visita reprodutiva — "data da última visita" e "data da próxima visita" — num lugar só:
// aparecem fixos na Agenda Reprodutiva (Insights › Listas) e dentro do diálogo "Definir nova data da visita" da Agenda.
// Gravam os parâmetros únicos lidos por todos (backend rules/visita_reprodutiva.py; ver também Administração › Parâmetros).
// A última visita é a âncora da contagem dos dias entre visitas: última visita + intervalo (Parâmetros) = próxima visita,
// a menos que você defina a próxima à mão.
import { useId, useState } from "react";
import { CalendarPlus } from "lucide-react";
import { definirVisitaReprodutiva, today, type VisitaReprodutivaResposta } from "@/lib/api";

const fmtDia = (iso: string | null | undefined) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");

function somaDias(iso: string, n: number): string {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Mesma regra do backend (proxima_visita): última visita + intervalo, saltando os ciclos já vencidos. */
function proximaPelaUltima(ultima: string, intervalo: number, hoje: string): string {
  let proxima = somaDias(ultima, intervalo);
  while (proxima < hoje) proxima = somaDias(proxima, intervalo);
  return proxima;
}

const inputStyle = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.88rem",
} as const;
const labelStyle = { fontSize: "0.78rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" } as const;

export function CamposVisitaReprodutiva({ ultimaInformada, proximaDefinida, proximaAtual, origem, intervalo, ultimoServico, onSalvo, onCancelar }: {
  /** Última visita informada por você (null = nunca informada). */
  ultimaInformada: string | null;
  /** Próxima visita definida por você (só quando origem === "definida"). */
  proximaDefinida: string | null;
  /** Próxima visita em vigor hoje (definida ou calculada); null = sem visita. */
  proximaAtual: string | null;
  origem: "definida" | "calculada" | null;
  /** Intervalo automático em dias (Administração › Parâmetros). */
  intervalo?: number | null;
  /** Último serviço lançado no rebanho: se for mais novo que a última visita informada, é ele que ancora a contagem. */
  ultimoServico?: string | null;
  onSalvo: (r: VisitaReprodutivaResposta) => void;
  /** Quando informado, mostra o botão "Cancelar" (uso dentro do diálogo). */
  onCancelar?: () => void;
}) {
  const idUltima = useId();
  const idProxima = useId();
  const hoje = today();
  const proximaInicial = proximaDefinida && proximaDefinida >= hoje ? proximaDefinida : "";
  const [ultima, setUltima] = useState(ultimaInformada ?? "");
  const [proxima, setProxima] = useState(proximaInicial);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const mudouUltima = ultima !== (ultimaInformada ?? "");
  const mudouProxima = proxima !== proximaInicial && proxima !== "";
  const ultimaValida = !ultima || ultima <= hoje;
  const proximaValida = !proxima || proxima >= hoje;
  const podeSalvar = !salvando && ultimaValida && proximaValida && (mudouUltima || mudouProxima);

  // O que vai valer para a próxima se você só informar a última visita (e não definir a próxima à mão).
  const previa = ultima && ultimaValida && intervalo && intervalo > 0 && !proxima
    ? proximaPelaUltima(ultima, intervalo, hoje) : null;
  const ultimoServicoMaisNovo = !!ultimoServico && !!ultima && ultimoServico > ultima;

  async function salvar(campos: { data?: string | null; ultima?: string | null }) {
    setSalvando(true); setErro(null);
    try {
      onSalvo(await definirVisitaReprodutiva(campos));
    } catch (e) { setErro(e instanceof Error ? e.message : "Erro ao salvar."); } finally { setSalvando(false); }
  }

  return (
    <div data-testid="campos-visita-reprodutiva">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: "0.8rem" }}>
        <div>
          <label htmlFor={idUltima} style={labelStyle}>Data da última visita reprodutiva</label>
          <input id={idUltima} type="date" max={hoje} value={ultima} onChange={(e) => setUltima(e.target.value)} style={inputStyle}
            data-testid="ultima-visita-reprodutiva" />
        </div>
        <div>
          <label htmlFor={idProxima} style={labelStyle}>Data da próxima visita reprodutiva</label>
          <input id={idProxima} type="date" min={hoje} value={proxima} onChange={(e) => setProxima(e.target.value)} style={inputStyle}
            data-testid="proxima-visita-reprodutiva" />
        </div>
      </div>
      <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", margin: "0.55rem 0 0" }}>
        {proximaAtual
          ? <>Próxima visita hoje: <strong style={{ color: "var(--text)" }}>{fmtDia(proximaAtual)}</strong>{" "}
              ({origem === "definida" ? "data definida por você" : `calculada: última visita + ${intervalo ?? "N"} dias`}).</>
          : "Não há próxima visita reprodutiva agendada."}
        {previa && <> Com a última visita em {fmtDia(ultima)}, a próxima passa a ser <strong style={{ color: "var(--text)" }}>{fmtDia(previa)}</strong>.</>}
      </p>
      <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", margin: "0.4rem 0 0.8rem" }}>
        A última visita é a referência para contar os dias entre visitas (intervalo em Administração › Parâmetros); a Agenda avisa na véspera e
        no dia. Deixe a próxima em branco para o sistema calcular; preencha para marcar uma data específica.
        {ultimoServicoMaisNovo && <> Há serviço lançado em {fmtDia(ultimoServico)}, mais recente que essa data — ele é quem vale como última visita.</>}
      </p>
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{erro}</p>}
      <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
        <button type="button" className="btn-primary" disabled={!podeSalvar} data-testid="salvar-visitas-reprodutivas"
          onClick={() => salvar({ ...(mudouUltima ? { ultima: ultima || null } : {}), ...(mudouProxima ? { data: proxima } : {}) })}>
          <CalendarPlus size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        {origem === "definida" && (
          <button type="button" className="btn-ghost" disabled={salvando} onClick={() => salvar({ data: null })}>Voltar ao cálculo automático</button>
        )}
        {onCancelar && <button type="button" className="btn-ghost" onClick={onCancelar}>Cancelar</button>}
      </div>
    </div>
  );
}
