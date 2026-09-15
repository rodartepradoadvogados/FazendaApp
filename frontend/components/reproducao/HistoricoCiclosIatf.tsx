"use client";
// Ciclos de IATF (Histórico > Reprodução) — os mesmos quadros gerenciais que
// aparecem na Agenda (IATF atual, D0-D11 dos ciclos passados), mais as
// candidatas à próxima IATF com projeção de aptidão na data do próximo
// serviço (ver GET /reproducao/protocolo-iatf/candidatas).
import { useEffect, useState } from "react";
import { AlertTriangle, CalendarClock, Check, CheckCircle2, History, Syringe } from "lucide-react";
import { fetchProtocolosIatfAtivos, fetchCandidatasIatfProjetadas, type CandidataIatfProjetada } from "@/lib/api";
import { useEstadosReprodutivos } from "@/lib/estadoReprodutivo";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { TelaSkeleton } from "@/components/ui";

type GrupoIatf = {
  lancamento_id: number;
  nome_protocolo: string;
  data_d0: string;
  animais: { numero_matriz: string; etapa_atual: string; data_etapa_atual: string | null; d0_confirmado?: boolean }[];
  concluido: boolean;
  data_d11?: string;
  proxima_visita?: string;
};

const fmtDia = (iso: string | null | undefined) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");

function GrupoAtualCard({ g }: { g: GrupoIatf }) {
  const ord = useOrdenacao(g.animais);
  return (
    <div className="mb-3" style={{ borderBottom: "1px solid var(--border)", paddingBottom: "0.6rem" }}>
      <p style={{ fontSize: "0.82rem", fontWeight: 700, marginBottom: "0.4rem" }}>
        {g.nome_protocolo} — D0 {fmtDia(g.data_d0)} <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>({g.animais.length} animal(is))</span>
      </p>
      <div className="overflow-x-auto">
        <table className="fazenda-table" style={{ margin: 0 }}>
          <thead><tr>
            <ThOrdenavel label="Nº" campo="numero_matriz" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
            <ThOrdenavel label="Etapa atual" campo="etapa_atual" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
            <ThOrdenavel label="Data" campo="data_etapa_atual" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
            <ThOrdenavel label="D0" campo="d0_confirmado" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          </tr></thead>
          <tbody>
            {ord.linhasOrdenadas.map((a) => (
              <tr key={a.numero_matriz}>
                <td style={{ fontWeight: 700 }}>{a.numero_matriz}</td>
                <td style={{ fontSize: "0.8rem" }}>{a.etapa_atual}</td>
                <td style={{ fontSize: "0.8rem" }}>{fmtDia(a.data_etapa_atual)}</td>
                <td style={{ fontSize: "0.78rem" }}>
                  {a.d0_confirmado ? (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", color: "var(--green-light)" }}><Check size={13} /> confirmado</span>
                  ) : (
                    <span title="Pode ter entrado no protocolo sem ter sido implantada de fato — ver Lançamentos › Reprodutivo › Protocolo IATF" style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", color: "var(--amber)" }}><AlertTriangle size={13} /> não confirmado</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function HistoricoCiclosIatf() {
  const [grupos, setGrupos] = useState<GrupoIatf[] | null>(null);
  const [candidatas, setCandidatas] = useState<{ candidatas: CandidataIatfProjetada[]; proxima_visita_iatf: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { rotuloDe } = useEstadosReprodutivos();
  const ordCandidatas = useOrdenacao(candidatas?.candidatas ?? []);

  useEffect(() => {
    fetchProtocolosIatfAtivos().then(setGrupos).catch((e) => setError(e.message));
    fetchCandidatasIatfProjetadas().then(setCandidatas).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="alert-critico"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>;
  if (!grupos || !candidatas) return <TelaSkeleton kpis={0} />;

  const atuais = grupos.filter((g) => !g.concluido);
  const passados = grupos.filter((g) => g.concluido).sort((a, b) => (b.data_d11 || "").localeCompare(a.data_d11 || ""));

  return (
    <div>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Syringe size={16} style={{ color: "var(--dourado-light)" }} /> IATF atual</div>
        {!atuais.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum protocolo IATF em andamento.</p>}
        {atuais.map((g) => <GrupoAtualCard key={g.lancamento_id} g={g} />)}
      </div>

      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><History size={16} style={{ color: "var(--dourado-light)" }} /> Ciclos passados de IATF</div>
        {!passados.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum ciclo concluído ainda.</p>}
        <div className="space-y-2">
          {passados.map((g) => (
            <div key={g.lancamento_id} style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.9rem" }}>
              <p style={{ fontSize: "0.82rem", fontWeight: 700 }}>
                {g.nome_protocolo} — D0 {fmtDia(g.data_d0)} - D11 {fmtDia(g.data_d11)}
              </p>
              <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                {g.animais.length} animal(is) — próxima visita prevista: {fmtDia(g.proxima_visita)}
              </p>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-header mb-3 flex items-center gap-2"><CalendarClock size={16} style={{ color: "var(--dourado-light)" }} /> Candidatas à próxima IATF</div>
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
          Próxima visita reprodutiva prevista: <strong>{fmtDia(candidatas.proxima_visita_iatf)}</strong> — a coluna "Apta na visita" projeta o DEL de cada candidata até essa data (parâmetro de PEV em Configurações &gt; Parâmetros).
        </p>
        {!candidatas.candidatas.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma candidata no momento.</p>}
        {!!candidatas.candidatas.length && (
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead><tr>
                <ThOrdenavel label="Nº" campo="numero_matriz" coluna={ordCandidatas.coluna} dir={ordCandidatas.dir} ordenar={ordCandidatas.ordenar} />
                <ThOrdenavel label="Estado" campo="estado_rotulo" coluna={ordCandidatas.coluna} dir={ordCandidatas.dir} ordenar={ordCandidatas.ordenar} />
                <ThOrdenavel label="Motivo" campo="motivo" coluna={ordCandidatas.coluna} dir={ordCandidatas.dir} ordenar={ordCandidatas.ordenar} />
                <ThOrdenavel label="DEL hoje" campo="del_dias" coluna={ordCandidatas.coluna} dir={ordCandidatas.dir} ordenar={ordCandidatas.ordenar} alinhar="right" />
                <ThOrdenavel label="DEL projetado" campo="del_dias_projetado" coluna={ordCandidatas.coluna} dir={ordCandidatas.dir} ordenar={ordCandidatas.ordenar} alinhar="right" />
                <ThOrdenavel label="Apta na visita" campo="apta_na_proxima_visita" coluna={ordCandidatas.coluna} dir={ordCandidatas.dir} ordenar={ordCandidatas.ordenar} />
              </tr></thead>
              <tbody>
                {ordCandidatas.linhasOrdenadas.map((c) => (
                  <tr key={c.numero_matriz}>
                    <td style={{ fontWeight: 700 }}>{c.numero_matriz}</td>
                    <td style={{ fontSize: "0.8rem" }}>{rotuloDe(c.numero_matriz)}</td>
                    <td style={{ fontSize: "0.8rem" }}>{c.motivo}</td>
                    <td style={{ textAlign: "right" }}>{c.del_dias ?? "—"}</td>
                    <td style={{ textAlign: "right" }}>{c.del_dias_projetado ?? "—"}</td>
                    <td>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.78rem", fontWeight: 700, color: c.apta_na_proxima_visita ? "var(--green-light)" : "var(--amber)" }}>
                        {c.apta_na_proxima_visita ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
                        {c.apta_na_proxima_visita ? "Sim" : "Ainda não"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
