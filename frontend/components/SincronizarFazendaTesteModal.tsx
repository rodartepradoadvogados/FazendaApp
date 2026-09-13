"use client";
// Confirmação + execução da sincronização destrutiva Jairo Nasser → Fazenda
// Teste (ver FazendaTesteBanner.tsx, que abre este componente, e
// sincronizarFazendaTeste em lib/api.ts). Overlay bespoke (mesmo padrão do
// popup de exclusão em FormExclusao.tsx) em vez do <Modal> genérico: aquele
// sempre desenha um X que fecha incondicionalmente — aqui a fase
// "executando" não pode ser interrompida por engano no meio de uma cópia que
// já apagou o destino e está recopiando (ver comentário na fase abaixo).
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, Check, Loader2, X } from "lucide-react";
import { sincronizarFazendaTeste, type ResultadoSincronizacaoFazendaTeste } from "@/lib/api";

// Frase (não só uma palavra solta) que a pessoa precisa digitar sem erro
// pra habilitar o botão de confirmar — pedido explícito: um clique de "ok"
// não basta para uma ação destrutiva e irreversível. Citar o destino na
// própria frase (não só "CONFIRMAR") também funciona como uma segunda
// checagem: quem copia/cola sem ler ao menos precisa ver "FAZENDA TESTE"
// no meio do caminho.
const FRASE_CONFIRMACAO = "APAGAR FAZENDA TESTE";

type Fase = "confirmar" | "executando" | "resultado" | "erro";

function formatarDuracao(s: number): string {
  if (s < 60) return `${s.toFixed(1)}s`;
  const min = Math.floor(s / 60);
  const seg = Math.round(s % 60);
  return `${min}min ${seg}s`;
}

export function SincronizarFazendaTesteModal({ fazendaTesteId, onClose }: { fazendaTesteId: number; onClose: () => void }) {
  const [fase, setFase] = useState<Fase>("confirmar");
  const [digitado, setDigitado] = useState("");
  const [resultado, setResultado] = useState<ResultadoSincronizacaoFazendaTeste | null>(null);
  const [mensagemErro, setMensagemErro] = useState("");
  // Cronômetro só visual (a duração real de verdade vem em resultado.duracao_s)
  // — mostra que o sistema está vivo numa espera de dezenas de segundos.
  const [segundosDecorridos, setSegundosDecorridos] = useState(0);
  const emCurso = useRef(false); // trava de duplo clique — ver onClick abaixo

  useEffect(() => {
    if (fase !== "executando") return;
    const t = setInterval(() => setSegundosDecorridos((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [fase]);

  async function confirmar() {
    // `emCurso` (ref, não state) pega o clique duplo que aconteceria ANTES do
    // primeiro re-render trocar `fase` — um `disabled={fase!=="confirmar"}`
    // sozinho ainda deixa passar o segundo clique disparado no mesmo evento.
    if (emCurso.current) return;
    emCurso.current = true;
    setSegundosDecorridos(0);
    setFase("executando");
    try {
      const r = await sincronizarFazendaTeste(fazendaTesteId);
      setResultado(r);
      setFase("resultado");
    } catch (e) {
      // ErroApi (409/403 — ver sincronizarFazendaTeste) já chega com a
      // mensagem certa para cada caso; qualquer outro erro (rede de verdade,
      // 500) usa a mensagem própria que a função já monta — nunca um genérico
      // "algo deu errado" que esconderia o motivo real.
      setMensagemErro(e instanceof Error ? e.message : String(e));
      setFase("erro");
    } finally {
      emCurso.current = false;
    }
  }

  // Fechar só é permitido fora da fase "executando" — nem o X, nem clique no
  // fundo escuro, nem Esc derrubam a tela no meio de uma cópia que já apagou
  // o destino (ver comentário no topo do arquivo).
  function tentarFechar() {
    if (fase === "executando") return;
    onClose();
  }

  const digitadoOk = digitado.trim().toUpperCase() === FRASE_CONFIRMACAO;

  return createPortal(
    <div
      role="dialog" aria-modal="true"
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200, padding: "1rem" }}
      onClick={tentarFechar}
    >
      <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "480px", maxWidth: "95vw", maxHeight: "90vh", overflowY: "auto" }}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0, color: "var(--red)", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <AlertTriangle size={16} /> Sincronizar Fazenda Teste
          </div>
          {fase !== "executando" && (
            <button onClick={onClose} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
          )}
        </div>

        {fase === "confirmar" && (
          <>
            <div style={{ border: "1px solid var(--red)", borderRadius: "var(--r-sm)", padding: "0.7rem 0.8rem", marginBottom: "0.8rem", background: "color-mix(in srgb, var(--red) 12%, transparent)" }}>
              <p style={{ fontSize: "0.86rem", fontWeight: 700, marginBottom: "0.3rem" }}>Isto apaga TUDO da Fazenda Teste agora mesmo.</p>
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                Todos os dados atuais da Fazenda Teste (qualquer coisa lançada, editada ou testada nela) serão
                apagados e substituídos por uma cópia nova da fazenda real Jairo Nasser. Não tem como desfazer —
                o que foi testado no sandbox se perde de vez.
              </p>
            </div>
            <label style={{ display: "block", fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.35rem" }}>
              Para confirmar, digite exatamente <strong style={{ color: "var(--text)" }}>{FRASE_CONFIRMACAO}</strong>:
            </label>
            <input
              type="text" value={digitado} onChange={(e) => setDigitado(e.target.value)}
              placeholder={FRASE_CONFIRMACAO} autoFocus
              style={{ width: "100%", padding: "0.5rem 0.7rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)", fontSize: "0.85rem", marginBottom: "0.9rem", textTransform: "uppercase" }}
            />
            <div className="flex items-center gap-3">
              <button className="btn-primary" style={{ background: "var(--red)", borderColor: "var(--red)" }} disabled={!digitadoOk} onClick={confirmar}>
                <Check size={14} /> Apagar e sincronizar
              </button>
              <button className="btn-ghost" onClick={onClose}>Cancelar</button>
            </div>
          </>
        )}

        {fase === "executando" && (
          <div style={{ textAlign: "center", padding: "1.5rem 0.5rem" }}>
            <Loader2 size={28} className="animate-spin" style={{ color: "var(--red)", marginBottom: "0.7rem" }} />
            <p style={{ fontWeight: 700, marginBottom: "0.3rem" }}>Sincronizando… ({segundosDecorridos}s)</p>
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
              Pode levar dezenas de segundos (cópia completa da fazenda real). Não feche nem recarregue esta página.
            </p>
          </div>
        )}

        {fase === "resultado" && resultado && (
          <>
            <div style={{ border: "1px solid var(--green-light)", borderRadius: "var(--r-sm)", padding: "0.7rem 0.8rem", marginBottom: "0.8rem", background: "color-mix(in srgb, var(--green-light) 12%, transparent)" }}>
              <p style={{ fontWeight: 700, marginBottom: "0.3rem" }}>Sincronização concluída.</p>
              <p style={{ fontSize: "0.82rem" }}>
                {resultado.origem} → {resultado.destino}: {resultado.tabelas} tabelas, {resultado.linhas_copiadas.toLocaleString("pt-BR")} linhas
                copiadas em {formatarDuracao(resultado.duracao_s)}.
              </p>
            </div>
            {resultado.avisos.length > 0 && (
              <div style={{ marginBottom: "0.9rem" }}>
                <p style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--amber)", marginBottom: "0.3rem" }}>Avisos:</p>
                <ul style={{ fontSize: "0.78rem", color: "var(--text-muted)", paddingLeft: "1.1rem" }}>
                  {resultado.avisos.map((a, i) => <li key={i} style={{ marginBottom: "0.15rem" }}>{a}</li>)}
                </ul>
              </div>
            )}
            <button className="btn-primary" onClick={onClose}>Fechar</button>
          </>
        )}

        {fase === "erro" && (
          <>
            <p style={{ color: "var(--red)", fontSize: "0.86rem", marginBottom: "0.9rem" }}>{mensagemErro}</p>
            <div className="flex items-center gap-3">
              <button className="btn-primary" style={{ background: "var(--red)", borderColor: "var(--red)" }} onClick={() => setFase("confirmar")}>Tentar de novo</button>
              <button className="btn-ghost" onClick={onClose}>Fechar</button>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body
  );
}
