"use client";
import { useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";

const DURACAO_SLIDE_MS = 380;

/** Anima a troca de etapa: a etapa anterior arrasta pra fora (esquerda ao
 * avançar, direita ao voltar) enquanto a nova entra do lado oposto, uma
 * dando lugar à outra — em vez da troca instantânea de antes. `direcao`
 * é 1 ao avançar (Continuar) e -1 ao voltar (Voltar). */
function usePrefereMenosMovimento(): boolean {
  const [reduzido, setReduzido] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduzido(mq.matches);
    const ouvir = (e: MediaQueryListEvent) => setReduzido(e.matches);
    mq.addEventListener("change", ouvir);
    return () => mq.removeEventListener("change", ouvir);
  }, []);
  return reduzido;
}

function useTransicaoDeEtapa(passoAtual: number) {
  const [saindo, setSaindo] = useState<{ idx: number; direcao: 1 | -1 } | null>(null);
  const [ativo, setAtivo] = useState(false);
  const anteriorRef = useRef(passoAtual);

  useEffect(() => {
    if (passoAtual === anteriorRef.current) return;
    const direcao: 1 | -1 = passoAtual > anteriorRef.current ? 1 : -1;
    setSaindo({ idx: anteriorRef.current, direcao });
    setAtivo(false);
    anteriorRef.current = passoAtual;
    // Monta no offset inicial primeiro, só ativa a transição no frame seguinte
    // (senão o navegador não anima — já nasceria na posição final).
    const raf = requestAnimationFrame(() => requestAnimationFrame(() => setAtivo(true)));
    const t = setTimeout(() => setSaindo(null), DURACAO_SLIDE_MS);
    return () => { cancelAnimationFrame(raf); clearTimeout(t); };
  }, [passoAtual]);

  return { saindo, ativo };
}

/**
 * Formato "wizard" do Cadastro de protocolos (redesign "Cooperativa", T5) —
 * componente ÚNICO reaproveitado pelos 6 tipos de molde da Central de
 * Protocolos > Cadastro (Sanitário curativo, Sanitário preventivo/calendário,
 * IATF, Indução de lactação, Customizado, Lida). Os outros dois formatos
 * decididos no redesign (duas colunas para o Financeiro inteiro — T4; gaveta
 * lateral para o resto — T2, GavetaLancamento.tsx) NÃO se aplicam aqui: esta é
 * a área "Protocolos", que tem o seu próprio formato de formulário longo.
 *
 * Este componente só cuida do CASCO do wizard (stepper, navegação, validação
 * por etapa, rascunho em localStorage, rodapé) — os campos de cada etapa
 * continuam sendo os componentes de formulário que já existiam (Campo,
 * EstoquePicker, etc.), só reagrupados em `passos`. Nenhuma validação de
 * negócio que já existia foi removida: a validação de cada `passo.validar`
 * é só um TRAVA A MAIS, adicional, que impede avançar com um campo
 * obrigatório vazio DAQUELA etapa — o `salvar()` de cada tipo continua
 * rodando a validação completa de sempre no fim, como sempre fez.
 *
 * Rodapé "fixo": como a Central de Protocolos usa um layout de 2 colunas
 * (lista à esquerda, formulário à direita, cada um com seu próprio scroll —
 * ver os `overflowY: auto` dos containers em CadastroSanitario.tsx e
 * companhia), `position: fixed` no rodapé prenderia o botão à JANELA inteira,
 * flutuando por cima da coluna da lista também — errado nesse layout (ao
 * contrário da gaveta lateral de T2, que é a tela inteira). Por isso o
 * stepper e o rodapé usam `position: sticky` (top/bottom) dentro do próprio
 * container com scroll: continuam sempre visíveis enquanto o conteúdo da
 * etapa rola por baixo, sem invadir a coluna vizinha.
 */

const RASCUNHO_EXPIRACAO_MS = 7 * 24 * 60 * 60 * 1000; // 7 dias corridos — ver plano do redesign (T5)

type RascunhoSalvo<F> = { form: F; passo: number; salvoEm: number };

function lerRascunho<F>(chave: string): RascunhoSalvo<F> | null {
  try {
    const bruto = window.localStorage.getItem(chave);
    if (!bruto) return null;
    const dados = JSON.parse(bruto) as RascunhoSalvo<F>;
    if (!dados || typeof dados.salvoEm !== "number") return null;
    // Rascunho velho demais — descarta silenciosamente, sem perguntar (é a
    // recomendação já registrada no plano do redesign para esta dúvida).
    if (Date.now() - dados.salvoEm > RASCUNHO_EXPIRACAO_MS) {
      window.localStorage.removeItem(chave);
      return null;
    }
    return dados;
  } catch {
    return null;
  }
}

export type PassoWizard<F> = {
  id: string;
  titulo: string;
  render: (ctx: { form: F; setForm: (f: F) => void }) => React.ReactNode;
  /** Retorna a mensagem de erro (bloqueia "Continuar") ou null/undefined se a etapa está OK. */
  validar?: (form: F) => string | null | undefined;
};

export function WizardProtocolo<F>({
  chaveRascunho, form, setForm, ehVazio, passos, onCancelar, onConcluir,
  salvando, rotuloConcluir = "Concluir", erro, tituloTopo,
}: {
  /**
   * Chave única POR TIPO de protocolo (ex.: "wizard-protocolo:iatf") — nunca
   * por instância/edição, para trocar de aba não misturar o rascunho de um
   * tipo com o de outro (regra do ticket). Passe `null` para desligar o
   * rascunho por completo — usado ao EDITAR um protocolo já existente: o
   * dado já está salvo no banco, e guardar um rascunho aqui sob a mesma
   * chave do "novo" faria a tela reabrir com os dados errados na próxima vez
   * que alguém for cadastrar um protocolo novo daquele tipo.
   */
  chaveRascunho: string | null;
  form: F;
  setForm: (f: F) => void;
  /** Verdadeiro quando o form está no estado inicial (nada digitado ainda) — usado para não pedir confirmação de descarte à toa, e para não gravar rascunho vazio. */
  ehVazio: (f: F) => boolean;
  passos: PassoWizard<F>[];
  onCancelar: () => void;
  /** Deve devolver `true` só quando salvou de verdade (aciona a limpeza do rascunho) — em caso de erro, devolve `false` e a etapa atual permanece, com o erro já visível (via `erro` ou dentro da própria etapa). */
  onConcluir: () => Promise<boolean> | boolean;
  salvando?: boolean;
  rotuloConcluir?: string;
  erro?: string | null;
  /** Rótulo opcional acima do stepper (ex.: "Editando: <nome>"). */
  tituloTopo?: string;
}) {
  const [passoAtual, setPassoAtual] = useState(0);
  const [erroPasso, setErroPasso] = useState<string | null>(null);
  const restaurado = useRef(false);

  // Restaura o rascunho (se houver e não estiver expirado) só na 1ª montagem.
  useEffect(() => {
    if (restaurado.current) return;
    restaurado.current = true;
    if (!chaveRascunho) return;
    const salvo = lerRascunho<F>(chaveRascunho);
    if (salvo) {
      setForm(salvo.form);
      setPassoAtual(Math.min(Math.max(salvo.passo, 0), passos.length - 1));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persiste a cada mudança de campo ou de etapa — sobrevive à troca de aba
  // (Cadastro/Lançamento/Acompanhamento/Histórico, ou entre tipos dentro do
  // Cadastro) mesmo quando isso desmonta o componente do formulário.
  useEffect(() => {
    if (!restaurado.current || !chaveRascunho) return;
    try {
      if (ehVazio(form)) window.localStorage.removeItem(chaveRascunho);
      else window.localStorage.setItem(chaveRascunho, JSON.stringify({ form, passo: passoAtual, salvoEm: Date.now() } as RascunhoSalvo<F>));
    } catch {
      // localStorage indisponível (modo privado, quota) — degrada para "sem rascunho", sem quebrar o wizard.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, passoAtual, chaveRascunho]);

  const limparRascunho = () => {
    if (!chaveRascunho) return;
    try { window.localStorage.removeItem(chaveRascunho); } catch {}
  };

  const cancelar = () => {
    if (!ehVazio(form) && !window.confirm("Descartar o que foi preenchido até aqui?")) return;
    limparRascunho();
    onCancelar();
  };

  const voltar = () => { setPassoAtual((p) => Math.max(0, p - 1)); setErroPasso(null); };

  const irParaPasso = (idx: number) => {
    if (idx > passoAtual) return; // avançar só pelo botão "Continuar" (precisa validar cada etapa no caminho)
    setPassoAtual(idx);
    setErroPasso(null);
  };

  const continuar = async () => {
    const passo = passos[passoAtual];
    const msg = passo.validar?.(form);
    if (msg) { setErroPasso(msg); return; }
    setErroPasso(null);
    if (passoAtual < passos.length - 1) { setPassoAtual((p) => p + 1); return; }
    const ok = await onConcluir();
    if (ok) limparRascunho();
  };

  const ultimo = passoAtual === passos.length - 1;
  const passoAtualDef = passos[passoAtual];
  const { saindo, ativo } = useTransicaoDeEtapa(passoAtual);
  const menosMovimento = usePrefereMenosMovimento();

  return (
    // Painel com borda/fundo/sombra próprios — deixa claro que esta área
    // (do stepper até Cancelar/Voltar/Continuar) é UM campo de lançamento
    // fechado, separado do resto da tela, e não só mais uma seção da página.
    <div style={{
      border: "1px solid var(--border)", borderRadius: 14,
      background: "var(--surface-2)", boxShadow: "0 2px 10px rgba(0,0,0,0.12)",
      padding: "1.1rem 1.2rem",
    }}>
      <div style={{
        position: "sticky", top: 0, zIndex: 3, background: "var(--surface-2)",
        paddingBottom: "0.7rem", marginBottom: "0.9rem",
      }}>
        {tituloTopo && (
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.5rem", fontWeight: 600 }}>{tituloTopo}</p>
        )}
        <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "0.3rem" }}>
          {passos.map((p, idx) => {
            const concluido = idx < passoAtual;
            const atual = idx === passoAtual;
            return (
              <div key={p.id} style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
                <button
                  type="button" onClick={() => irParaPasso(idx)} disabled={idx > passoAtual}
                  title={`${idx + 1}. ${p.titulo}`}
                  style={{
                    display: "flex", alignItems: "center", gap: "0.4rem", border: "none", background: "none",
                    cursor: idx <= passoAtual ? "pointer" : "default", padding: "0.2rem 0.35rem",
                  }}
                >
                  <span style={{
                    width: 21, height: 21, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: "0.7rem", fontWeight: 700, flexShrink: 0,
                    background: concluido ? "var(--dourado)" : atual ? "var(--pill-active-bg)" : "var(--surface)",
                    color: concluido ? "var(--vinho)" : "var(--dourado-light)",
                    border: `1px solid ${concluido || atual ? "var(--dourado)" : "var(--border)"}`,
                  }}>
                    {concluido ? <Check size={12} /> : idx + 1}
                  </span>
                  <span style={{
                    fontSize: "0.76rem", fontWeight: atual ? 700 : 500, whiteSpace: "nowrap",
                    color: atual ? "var(--dourado-light)" : concluido ? "var(--text)" : "var(--text-muted)",
                  }}>
                    {p.titulo}
                  </span>
                </button>
                {idx < passos.length - 1 && <span style={{ width: 14, height: 1, background: "var(--border)", flexShrink: 0 }} />}
              </div>
            );
          })}
        </div>
      </div>

      <div style={{ position: "relative", overflow: "hidden", minHeight: "12rem" }}>
        {saindo && !menosMovimento && (
          <div style={{
            position: "absolute", inset: 0,
            transform: `translateX(${ativo ? -100 * saindo.direcao : 0}%)`,
            opacity: ativo ? 0 : 1,
            transition: `transform ${DURACAO_SLIDE_MS}ms cubic-bezier(0.4, 0, 0.2, 1), opacity ${DURACAO_SLIDE_MS}ms ease`,
          }}>
            {passos[saindo.idx].render({ form, setForm })}
          </div>
        )}
        <div style={{
          transform: saindo && !menosMovimento ? `translateX(${ativo ? 0 : 100 * saindo.direcao}%)` : undefined,
          opacity: saindo && !menosMovimento ? (ativo ? 1 : 0) : 1,
          transition: saindo && !menosMovimento ? `transform ${DURACAO_SLIDE_MS}ms cubic-bezier(0.4, 0, 0.2, 1), opacity ${DURACAO_SLIDE_MS}ms ease` : undefined,
        }}>
          {passoAtualDef.render({ form, setForm })}
        </div>
      </div>

      {/* `erro` (o erro de submit do onConcluir, no último passo) some ao
          voltar/pular de passo — senão fica preso na tela mesmo depois do
          usuário já ter corrigido o campo, porque só é limpo no início do
          próximo `onConcluir()` (passo final de novo). `erroPasso` (validação
          da própria etapa) sempre pode aparecer, é sempre relevante na hora. */}
      {(erroPasso || (erro && ultimo)) && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.8rem" }}>{erroPasso || erro}</p>}

      <div style={{
        position: "sticky", bottom: 0, zIndex: 3, background: "var(--surface-2)",
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem",
        marginTop: "1rem", paddingTop: "0.8rem", paddingBottom: "0.2rem", borderTop: "1px solid var(--border)",
      }}>
        <button type="button" className="btn-ghost" style={{ fontSize: "0.8rem" }} onClick={cancelar}>Cancelar</button>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {passoAtual > 0 && (
            <button type="button" className="btn-ghost" style={{ fontSize: "0.8rem" }} onClick={voltar}>Voltar</button>
          )}
          <button type="button" className="btn-primary" style={{ fontSize: "0.8rem" }} onClick={continuar} disabled={!!salvando}>
            {salvando ? "Salvando…" : ultimo ? rotuloConcluir : "Continuar"}
          </button>
        </div>
      </div>
    </div>
  );
}
