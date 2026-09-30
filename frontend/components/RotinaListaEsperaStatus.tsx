"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, ClipboardList, Loader2, Play } from "lucide-react";
import {
  ehAdmin, executarRotinaListaEsperaAgora, fetchStatusRotinaListaEspera, type StatusRotinaListaEspera,
} from "@/lib/api";

const ORIGEM: Record<string, string> = { diaria: "rotina diária", parametros: "ao salvar os parâmetros", manual: "executada pelo gestor" };

function quando(iso: string | null) {
  if (!iso) return "ainda não executou";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

// Situação da rotina da lista de espera em Parâmetros: última execução, quantos
// animais entraram na lista de espera e o botão "Executar agora" (só do gestor).
// Os três parâmetros em si (ativar, dias de antecedência, aviso diário) ficam no
// cartão "Rotina da lista de espera" da grade de Parâmetros.
export default function RotinaListaEsperaStatus() {
  const [st, setSt] = useState<StatusRotinaListaEspera | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [rodando, setRodando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const podeExecutar = ehAdmin();

  const carregar = () => fetchStatusRotinaListaEspera().then(setSt).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); }, []);
  // Quem salva os parâmetros na grade ao lado dispara a rotina no servidor; reler ao voltar o foco/clique.
  useEffect(() => {
    const aoClicar = () => setTimeout(carregar, 1200);
    document.addEventListener("click", aoClicar);
    return () => document.removeEventListener("click", aoClicar);
  }, []);

  const executar = async () => {
    setRodando(true); setMsg(null); setErro(null);
    try {
      const r = await executarRotinaListaEsperaAgora();
      setSt(r.status);
      setMsg(r.resultado.motivo === "em_execucao" ? "A rotina já está em execução; aguarde alguns instantes."
        : r.resultado.entraram > 0 ? `${r.resultado.entraram} animal(is) entraram na lista de espera.`
        : "Nenhum animal novo para a lista de espera agora.");
    } catch (e: any) { setErro(e.message); }
    finally { setRodando(false); }
  };

  return (
    <div className="card" data-testid="rotina-lista-espera-status">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><ClipboardList size={15} style={{ color: "var(--dourado-light)" }} /> Rotina da lista de espera</span>
        {podeExecutar && st?.ativa && (
          <button onClick={executar} disabled={rodando} className="btn-secondary"
            style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.75rem", minHeight: "2rem" }}>
            {rodando ? <><Loader2 size={13} className="animate-spin" /> Executando…</> : <><Play size={13} /> Executar agora</>}
          </button>
        )}
      </div>
      {erro && <div className="alert-critico mb-2"><AlertTriangle size={16} /><span>{erro}</span></div>}
      {!st && !erro && <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Carregando…</p>}
      {st && (
        <div style={{ fontSize: "0.82rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          <p style={{ color: "var(--text-muted)" }}>
            Coloca na lista de espera os animais que se aproximam da janela de aplicação das regras de vacina e exame já
            cadastradas, {st.dias_antecedencia} dia(s) antes. Não aplica, não baixa estoque e não cria agendamento.
          </p>
          <p><strong>Situação:</strong> {st.ativa ? "ligada" : "desligada"}
            {st.ativa && !st.tem_regras && " — sem regras de vacina ou exame cadastradas, nada é feito"}</p>
          <p><strong>Última execução:</strong> {quando(st.ultima_execucao_em)}
            {st.ultima_execucao_origem && ` (${ORIGEM[st.ultima_execucao_origem] ?? st.ultima_execucao_origem})`}</p>
          {st.ultima_execucao_em && (
            <p><strong>Entraram na lista de espera:</strong> {st.entraram} · regras avaliadas: {st.regras_avaliadas} · na janela: {st.regras_na_janela}</p>
          )}
          <p><strong>Na lista de espera agora:</strong> {st.na_lista_de_espera} animal(is)</p>
          {st.ultimo_erro && <p style={{ color: "var(--vermelho, #c0392b)" }}>Erro na última execução: {st.ultimo_erro}</p>}
          {msg && <p role="status" style={{ color: "var(--dourado-light)" }}>{msg}</p>}
        </div>
      )}
    </div>
  );
}
