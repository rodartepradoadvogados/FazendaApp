"use client";
// Peças do app de campo › Vacinação (Sanitário Preventivo v2), no sistema
// .mob-* (DESIGN.md "App de campo"): faixas de aviso, leitura com cópia local
// (fetchComCache), papel do usuário, consentimento e carência em tela grande,
// "quem aplica" e o painel da fila do aparelho (resultado por registro,
// pendências, conflitos).
import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, CloudUpload, Info, RefreshCw, Trash2 } from "lucide-react";
import { getUsuario } from "@/lib/api";
import { fetchComCache } from "@/lib/offline";
import { decidirConflito, listarConflitos, listarVeterinarios, meuPapel, mensagemDoErro } from "@/lib/apiSanitario";
import {
  AJUDA_MODO_LEITE, MODOS_LEITE, ROTULO_MODO_LEITE, fmtDataHora, intOuNulo,
  type CarenciaDecisaoIn, type EuSanitario, type LogItem, type ModoLeite, type Veterinarios,
} from "@/lib/sanitarioTipos";
import { ROTULO_STATUS_SAN, type ResultadoSan } from "@/lib/sanitarioCampo";
import {
  atualizarResultado, decidirPendencia, descartarDaFila, reenviarItem, sincronizarSanitario, useFilaSanitario,
  type ItemFilaSan,
} from "@/lib/filaSanitario";
import { MobGaveta } from "@/components/mobile/ui";

// ── faixa de aviso ──
export function FaixaSan({ tipo = "info", children, role }: { tipo?: "info" | "atencao" | "alerta" | "ok"; children: ReactNode; role?: string }) {
  const Icone = tipo === "ok" ? CheckCircle2 : tipo === "info" ? Info : AlertTriangle;
  return (
    <div className={`mob-san-faixa ${tipo}`} role={role ?? (tipo === "alerta" ? "alert" : undefined)}>
      <Icone size={18} aria-hidden="true" />
      <div style={{ minWidth: 0 }}>{children}</div>
    </div>
  );
}

export function Rotulo({ children }: { children: ReactNode }) {
  return <span className="mob-san-rotulo">{children}</span>;
}

// ── leitura com cópia no aparelho ──
/** GET com cópia local: online atualiza a cópia; sem sinal usa a última. */
export function useComCopia<T>(chave: string | null, buscar: () => Promise<T>): {
  dados: T | null; doCache: boolean; carregando: boolean; recarregar: () => void;
} {
  const [n, setN] = useState(0);
  const [st, setSt] = useState<{ chave: string | null; dados: T | null; doCache: boolean }>({ chave: null, dados: null, doCache: false });
  const pedida = chave ? `${chave}#${n}` : null;
  useEffect(() => {
    if (!chave) return;
    let vivo = true;
    fetchComCache<T>(chave, buscar).then((r) => { if (vivo) setSt({ chave: `${chave}#${n}`, dados: r.dados, doCache: r.doCache }); });
    return () => { vivo = false; };
    // `buscar` muda a cada render; a chave identifica a leitura.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave, n]);
  return { dados: st.dados, doCache: st.doCache, carregando: !!pedida && st.chave !== pedida, recarregar: () => setN((x) => x + 1) };
}

/** Papel do usuário no sanitário (cópia local: funciona sem sinal). */
export function useEuCampo(): EuSanitario | null {
  return useComCopia<EuSanitario>("san_eu", meuPapel).dados;
}
export function useVeterinariosCampo(): Veterinarios | null {
  return useComCopia<Veterinarios>("san_veterinarios", listarVeterinarios).dados;
}

/** "CRMV-GO 1234" já traz o prefixo; "GO 1234" ganha "CRMV ". */
export function rotuloCrmv(c: string | null | undefined): string {
  const t = (c || "").trim();
  return !t ? "" : /^crmv/i.test(t) ? t : `CRMV ${t}`;
}

// ── quem aplica ──
export type Aplicador = { tipo: "eu" | "vet" | "texto"; pessoa_id: number | null; nome: string; crmv: string };

export function aplicadorEu(): Aplicador {
  const u = getUsuario();
  const pid = typeof u?.pessoa_id === "number" ? u.pessoa_id : null;
  return { tipo: "eu", pessoa_id: pid, nome: (u?.nome || u?.username || "Eu") as string, crmv: "" };
}

/** Campos do registro a partir de "quem aplica" (vet do cadastro = aplicador e
 *  veterinário; texto livre com CRMV = veterinário por texto). */
export function camposAplicador(a: Aplicador | null | undefined): {
  aplicador_pessoa_id: number | null; aplicador_texto: string | null; veterinario_pessoa_id?: number | null;
  veterinario_texto?: string | null; crmv_texto?: string | null;
} {
  if (!a) return { aplicador_pessoa_id: null, aplicador_texto: null };
  const crmv = a.crmv.trim() || null;
  if (a.tipo === "vet") return { aplicador_pessoa_id: a.pessoa_id, aplicador_texto: null, veterinario_pessoa_id: a.pessoa_id, crmv_texto: crmv };
  if (a.tipo === "texto") {
    return { aplicador_pessoa_id: null, aplicador_texto: a.nome.trim() || null,
      ...(crmv ? { veterinario_texto: a.nome.trim() || null, crmv_texto: crmv } : {}) };
  }
  return { aplicador_pessoa_id: a.pessoa_id, aplicador_texto: a.pessoa_id ? null : (a.nome.trim() || null) };
}

export function EscolhaAplicador({ valor, onChange, vets, pedeCrmv }: {
  valor: Aplicador | null; onChange: (a: Aplicador) => void;
  vets: { pessoa_id: number; nome: string; crmv: string | null }[]; pedeCrmv?: boolean;
}) {
  const eu = aplicadorEu();
  const [texto, setTexto] = useState(valor?.tipo === "texto" ? valor.nome : "");
  const ativo = (a: Aplicador) => valor?.tipo === a.tipo && (a.tipo !== "vet" || valor.pessoa_id === a.pessoa_id);
  return (
    <div>
      <div className="mob-san-chips">
        <button type="button" className="mob-san-chip" aria-pressed={ativo(eu)} onClick={() => onChange(eu)}>
          <span>{eu.nome}<small>Eu mesmo</small></span>
        </button>
        {vets.map((v) => {
          const a: Aplicador = { tipo: "vet", pessoa_id: v.pessoa_id, nome: v.nome, crmv: v.crmv || "" };
          return (
            <button key={v.pessoa_id} type="button" className="mob-san-chip" aria-pressed={ativo(a)}
              onClick={() => onChange(ativo(a) && valor ? valor : a)}>
              <span>{v.nome}<small>Veterinário{v.crmv ? ` · ${rotuloCrmv(v.crmv)}` : ""}</small></span>
            </button>
          );
        })}
        <button type="button" className="mob-san-chip" aria-pressed={valor?.tipo === "texto"}
          onClick={() => onChange({ tipo: "texto", pessoa_id: null, nome: texto, crmv: valor?.tipo === "texto" ? valor.crmv : "" })}>
          <span>Outra pessoa<small>Escrever o nome</small></span>
        </button>
      </div>
      {valor?.tipo === "texto" && (
        <label style={{ display: "block", marginTop: "0.6rem" }}>
          <span className="mob-san-rotulo" style={{ marginTop: 0 }}>Nome de quem aplica</span>
          <input className="mob-input" value={texto} autoComplete="off"
            onChange={(e) => { setTexto(e.target.value); onChange({ ...valor, nome: e.target.value }); }} />
        </label>
      )}
      {valor && valor.tipo !== "eu" && (
        <label style={{ display: "block", marginTop: "0.6rem" }}>
          <span className="mob-san-rotulo" style={{ marginTop: 0 }}>CRMV (pedido, não obrigatório)</span>
          <input className="mob-input" value={valor.crmv} inputMode="text" autoComplete="off" placeholder="ex.: GO 1234"
            onChange={(e) => onChange({ ...valor, crmv: e.target.value })} />
        </label>
      )}
      {pedeCrmv && (!valor || valor.tipo === "eu" || !valor.crmv.trim()) && (
        <p className="mob-san-txt">O cadastro desta vacina/exame pede o CRMV do veterinário. Dá para registrar sem ele.</p>
      )}
    </div>
  );
}

// ── consentimento em tela grande (nunca trava) ──
export type ParFora = { chave: string; numero: string; caixa: string; motivo: string };
export type RespostaCons = { aceitos: string[]; recusados: string[]; quer_atestado: boolean | null; destinatario: string | null };

export function ConsentimentoCampo({ itens, perguntarAtestado, texto, onConfirmar, onVoltar }: {
  itens: ParFora[]; perguntarAtestado?: boolean; texto?: string;
  onConfirmar: (r: RespostaCons) => void; onVoltar: () => void;
}) {
  const [incluir, setIncluir] = useState<Set<string>>(() => new Set(itens.map((i) => i.chave)));
  const [ciente, setCiente] = useState(false);
  const [atestado, setAtestado] = useState<boolean | null>(null);
  const [dest, setDest] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const marcados = itens.filter((i) => incluir.has(i.chave));
  const animais = new Set(itens.map((i) => i.numero)).size;
  function confirmar() {
    if (marcados.length && !ciente) { setErro("Marque “Estou ciente” para incluir, ou desmarque esses animais."); return; }
    onConfirmar({
      aceitos: marcados.map((i) => i.chave), recusados: itens.filter((i) => !incluir.has(i.chave)).map((i) => i.chave),
      quer_atestado: perguntarAtestado ? !!atestado : null, destinatario: atestado && dest.trim() ? dest.trim() : null,
    });
  }
  return (
    <div>
      <FaixaSan tipo="atencao">
        <b>{animais} {animais > 1 ? "animais não cumprem" : "animal não cumpre"} a regra.</b> O sistema avisa e pede o seu consentimento. Não trava.
      </FaixaSan>
      {itens.map((i) => (
        <label key={i.chave} className="mob-san-linha" data-estado="atencao">
          <input type="checkbox" checked={incluir.has(i.chave)} onChange={(e) => {
            setIncluir((p) => { const n = new Set(p); if (e.target.checked) n.add(i.chave); else n.delete(i.chave); return n; });
          }} />
          <span style={{ minWidth: 0 }}>
            <b style={{ fontSize: "1.15rem" }}>{i.numero}</b> · {i.caixa}
            <span className="mob-san-txt" style={{ display: "block", marginTop: 0 }}>{i.motivo}</span>
          </span>
        </label>
      ))}
      {perguntarAtestado && marcados.length > 0 && (
        <>
          <Rotulo>Quer fazer atestado destes animais?</Rotulo>
          <div className="mob-san-chips duas">
            <button type="button" className="mob-san-chip" aria-pressed={atestado === true} onClick={() => setAtestado(true)}>Sim</button>
            <button type="button" className="mob-san-chip" aria-pressed={atestado === false} onClick={() => setAtestado(false)}>Não</button>
          </div>
          {atestado && (
            <input className="mob-input" style={{ marginTop: "0.5rem" }} value={dest} onChange={(e) => setDest(e.target.value)}
              placeholder="Para quem (opcional): Agrodefesa, laticínio…" />
          )}
        </>
      )}
      {marcados.length > 0 && (
        <label className="mob-san-linha" style={{ marginTop: "0.8rem" }}>
          <input type="checkbox" checked={ciente} onChange={(e) => { setCiente(e.target.checked); setErro(null); }} />
          <span><b>Estou ciente e quero incluir mesmo assim.</b>
            <span className="mob-san-txt" style={{ display: "block", marginTop: 0 }}>
              {(texto || "").replace(/^Estou ciente e quero incluir mesmo assim\.\s*/i, "") || "O seu nome, a data e o motivo ficam no registro."}</span></span>
        </label>
      )}
      {erro && <FaixaSan tipo="alerta">{erro}</FaixaSan>}
      <div className="mob-san-dupla">
        <button type="button" className="mob-btn-2" onClick={onVoltar}>Voltar</button>
        <button type="button" className="mob-btn" onClick={confirmar}>{marcados.length ? "Incluir" : "Seguir sem eles"}</button>
      </div>
    </div>
  );
}

// ── carência: o que fazer com o leite ──
export function CarenciaCampo({ nome, motivo, sugestao, onDecidir, onVoltar }: {
  nome: string; motivo?: string | null; sugestao?: CarenciaDecisaoIn | null;
  onDecidir: (d: { modo: ModoLeite; leite_dias: number | null; carne_dias: number | null }) => void; onVoltar: () => void;
}) {
  const [modo, setModo] = useState<ModoLeite>((sugestao?.modo as ModoLeite) || "descarte");
  const [leite, setLeite] = useState(sugestao?.leite_dias != null ? String(sugestao.leite_dias) : "");
  const [carne, setCarne] = useState(sugestao?.carne_dias != null ? String(sugestao.carne_dias) : "");
  return (
    <div>
      <p className="mob-san-txt" style={{ marginTop: 0 }}>{motivo ? `${motivo} ` : ""}A decisão vale para o dia e fica no registro.</p>
      <Rotulo>Carência de {nome}: o leite…</Rotulo>
      {MODOS_LEITE.map((m) => (
        <label key={m} className="mob-san-linha">
          <input type="radio" name="carModo" checked={modo === m} onChange={() => setModo(m)} />
          <span><b>{ROTULO_MODO_LEITE[m]}</b><span className="mob-san-txt" style={{ display: "block", marginTop: 0 }}>{AJUDA_MODO_LEITE[m]}</span></span>
        </label>
      ))}
      <div className="mob-san-dupla">
        <label><span className="mob-san-rotulo" style={{ marginTop: 0 }}>Leite (dias)</span>
          <input className="mob-input" type="number" min={0} inputMode="numeric" value={leite} onChange={(e) => setLeite(e.target.value)} placeholder="não sei" /></label>
        <label><span className="mob-san-rotulo" style={{ marginTop: 0 }}>Carne (dias)</span>
          <input className="mob-input" type="number" min={0} inputMode="numeric" value={carne} onChange={(e) => setCarne(e.target.value)} placeholder="não sei" /></label>
      </div>
      <div className="mob-san-dupla" style={{ marginTop: "0.8rem" }}>
        <button type="button" className="mob-btn-2" onClick={onVoltar}>Voltar</button>
        <button type="button" className="mob-btn" onClick={() => onDecidir({ modo, leite_dias: intOuNulo(leite), carne_dias: intOuNulo(carne) })}>Decidir</button>
      </div>
    </div>
  );
}

// ── painel da fila do aparelho ──
const COR_STATUS: Record<string, "ok" | "atencao" | "alerta" | "fila"> = {
  gravado: "ok", duplicado: "ok", conflito: "atencao", pendente: "atencao", erro: "alerta",
};

/** Resumo da fila + o que precisa de decisão + resultado por registro da última
 *  sincronização. `diaId` filtra para um dia (tela de execução). */
export function PainelFila({ diaId, eu, partes = { aviso: true, decisoes: true, resultados: true } }: {
  diaId?: number | null; eu: EuSanitario | null; partes?: { aviso?: boolean; decisoes?: boolean; resultados?: boolean };
}) {
  const fila = useFilaSanitario();
  const [enviando, setEnviando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [decidindo, setDecidindo] = useState<ItemFilaSan | null>(null);
  const [conflitosServidor, setConflitosServidor] = useState<LogItem[] | null>(null);
  const doDia = <T extends { corpo?: { registro: { dia_id?: number | null } }; dia_id?: number | null }>(x: T) =>
    diaId == null || (x.corpo ? x.corpo.registro.dia_id === diaId : x.dia_id === diaId);
  const itens = fila.itens.filter(doDia);
  const requer = fila.requer.filter(doDia);
  const erros = fila.erros.filter(doDia);
  const resultados = fila.resultados.filter((r) => diaId == null || r.dia_id === diaId);
  const conflitos = resultados.filter((r) => r.status === "conflito" && r.conflito_log_id);

  useEffect(() => {
    if (!partes.decisoes) return;
    let vivo = true;
    listarConflitos().then((l) => { if (vivo) setConflitosServidor(l); }).catch(() => { if (vivo) setConflitosServidor(null); });
    return () => { vivo = false; };
  }, [partes.decisoes, fila.resultados.length]);

  async function enviarAgora() {
    setEnviando(true); setMsg(null);
    try {
      const r = await sincronizarSanitario(true);
      setMsg(r.semRede ? "Sem sinal agora. Os registros continuam guardados neste celular."
        : r.enviados ? `${r.enviados} ${r.enviados > 1 ? "registros enviados" : "registro enviado"}.` : "Nada novo para enviar.");
    } finally { setEnviando(false); }
  }
  async function decidirConflitoAqui(r: { chave?: string; logId: number }, manter: "existente" | "novo") {
    setMsg(null);
    try {
      await decidirConflito(r.logId, manter);
      if (r.chave) atualizarResultado(r.chave, { status: manter === "novo" ? "gravado" : "duplicado",
        texto: manter === "novo" ? "Conflito decidido: vale este registro." : "Conflito decidido: vale o registro do outro aparelho." });
      setConflitosServidor((l) => (l || []).filter((x) => x.id !== r.logId));
    } catch (e) {
      setMsg(mensagemDoErro(e, "Não foi possível decidir agora (precisa de sinal)."));
    }
  }

  const locaisIds = new Set(conflitos.map((c) => c.conflito_log_id));
  const outrosConflitos = (conflitosServidor || []).filter((c) => !locaisIds.has(c.id) && (diaId == null || c.dia_id === diaId));

  return (
    <div>
      {partes.aviso && fila.atrasada && (
        <FaixaSan tipo="alerta" role="alert">
          <b>Há mais de {fila.horas} h sem enviar:</b> {fila.itens.length} {fila.itens.length > 1 ? "registros guardados" : "registro guardado"} neste
          celular desde {fmtDataHora(fila.maisAntigoEm)}. Procure sinal para enviar.
        </FaixaSan>
      )}
      {partes.aviso && itens.length > 0 && (
        <FaixaSan tipo="info" role="status">
          <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><CloudUpload size={16} aria-hidden="true" />
            <b>{itens.length} {itens.length > 1 ? "registros guardados" : "registro guardado"} neste celular.</b></span>
          {fila.naFila > 0 && <span>Enviam sozinhos quando houver sinal. </span>}
          <button type="button" className="mob-btn-2" style={{ marginTop: "0.5rem" }} onClick={enviarAgora} disabled={enviando}>
            <RefreshCw size={16} aria-hidden="true" /> {enviando ? "Enviando…" : "Enviar agora"}
          </button>
        </FaixaSan>
      )}
      {msg && <p className="mob-san-txt" role="status" style={{ marginBottom: "0.6rem" }}>{msg}</p>}

      {partes.decisoes && requer.length > 0 && (
        <>
          <Rotulo>Precisam de decisão ({requer.length})</Rotulo>
          {requer.map((i) => {
            const podeCarencia = i.corpo.requer?.includes("carencia_decisao");
            return (
              <div key={i.id} className="mob-san-linha" data-estado="atencao" style={{ display: "block", cursor: "default" }}>
                <b>{i.corpo.numero}</b> · {i.corpo.caixa}
                <p className="mob-san-txt">{i.corpo.motivo}</p>
                <div className="mob-san-dupla">
                  <button type="button" className="mob-btn-2 mob-san-btn-perigo" onClick={() => descartarDaFila([i.id])}>
                    <Trash2 size={16} aria-hidden="true" /> Não registrar
                  </button>
                  <button type="button" className="mob-btn" onClick={() => setDecidindo(i)} disabled={podeCarencia && !eu?.pode.decidir_carencia}>
                    {podeCarencia ? "Decidir carência" : "Consentir"}
                  </button>
                </div>
              </div>
            );
          })}
        </>
      )}
      {partes.decisoes && erros.length > 0 && (
        <>
          <Rotulo>Recusados pelo servidor ({erros.length})</Rotulo>
          {erros.map((i) => (
            <div key={i.id} className="mob-san-linha" data-estado="alerta" style={{ display: "block", cursor: "default" }}>
              <b>{i.corpo.numero}</b> · {i.corpo.caixa}
              <p className="mob-san-txt">{i.corpo.motivo || i.erro}</p>
              <div className="mob-san-dupla">
                <button type="button" className="mob-btn-2 mob-san-btn-perigo" onClick={() => descartarDaFila([i.id])}>Descartar</button>
                <button type="button" className="mob-btn-2" onClick={() => reenviarItem(i)}>Tentar de novo</button>
              </div>
            </div>
          ))}
        </>
      )}
      {partes.decisoes && (conflitos.length > 0 || outrosConflitos.length > 0) && (
        <>
          <Rotulo>Conflitos entre aparelhos</Rotulo>
          {conflitos.map((r) => (
            <div key={r.chave} className="mob-san-linha" data-estado="atencao" style={{ display: "block", cursor: "default" }}>
              <b>{r.numero}</b> · {r.caixa}
              <p className="mob-san-txt">{r.texto}</p>
              <div className="mob-san-dupla">
                <button type="button" className="mob-btn-2" onClick={() => decidirConflitoAqui({ chave: r.chave, logId: r.conflito_log_id! }, "existente")}>Vale o outro</button>
                <button type="button" className="mob-btn" onClick={() => decidirConflitoAqui({ chave: r.chave, logId: r.conflito_log_id! }, "novo")}>Vale este</button>
              </div>
            </div>
          ))}
          {outrosConflitos.map((c) => (
            <div key={c.id} className="mob-san-linha" data-estado="atencao" style={{ display: "block", cursor: "default" }}>
              <p className="mob-san-txt" style={{ marginTop: 0 }}>{c.texto}</p>
              <div className="mob-san-dupla">
                <button type="button" className="mob-btn-2" onClick={() => decidirConflitoAqui({ logId: c.id }, "existente")}>Manter o existente</button>
                <button type="button" className="mob-btn" onClick={() => decidirConflitoAqui({ logId: c.id }, "novo")}>Vale o novo</button>
              </div>
            </div>
          ))}
        </>
      )}
      {partes.resultados && resultados.length > 0 && (
        <>
          <Rotulo>Último envio, por registro</Rotulo>
          {resultados.slice(0, 12).map((r: ResultadoSan) => (
            <div key={r.chave} className="mob-san-linha" data-estado={COR_STATUS[r.status] || "fila"} style={{ cursor: "default" }}>
              <span style={{ flex: 1, minWidth: 0 }}>
                <b>{r.numero}</b> · {r.caixa}
                <span className="mob-san-txt" style={{ display: "block", marginTop: 0 }}>{r.texto}</span>
              </span>
              <span className={`mob-san-tag ${COR_STATUS[r.status] === "ok" ? "ok" : COR_STATUS[r.status] === "alerta" ? "alerta" : "atencao"}`}>
                {ROTULO_STATUS_SAN[r.status]}
              </span>
            </div>
          ))}
        </>
      )}

      <MobGaveta aberto={!!decidindo} titulo={decidindo?.corpo.requer?.includes("carencia_decisao") ? "Carência" : "Consentimento"}
        onFechar={() => setDecidindo(null)}>
        {decidindo && (decidindo.corpo.requer?.includes("carencia_decisao") ? (
          <CarenciaCampo nome={decidindo.corpo.caixa} motivo={decidindo.corpo.motivo} sugestao={decidindo.corpo.carencia_sugerida}
            onVoltar={() => setDecidindo(null)}
            onDecidir={async (d) => { await decidirPendencia(decidindo, { carencia: d }); setDecidindo(null); }} />
        ) : (
          <ConsentimentoCampo
            itens={[{ chave: decidindo.id, numero: decidindo.corpo.numero, caixa: decidindo.corpo.caixa,
              motivo: (decidindo.corpo.motivo || "").replace(/^Fora da regra: /, "").replace(/\. Precisa do seu consentimento\.$/, "") }]}
            perguntarAtestado={decidindo.corpo.pergunta_atestado}
            onVoltar={() => setDecidindo(null)}
            onConfirmar={async (r) => {
              if (!r.aceitos.length) await descartarDaFila([decidindo.id]);
              else await decidirPendencia(decidindo, { consentimento: { aceito: true, motivo_exibido: decidindo.corpo.motivo || null,
                quer_atestado: r.quer_atestado, atestado_destinatario: r.destinatario } });
              setDecidindo(null);
            }} />
        ))}
      </MobGaveta>
    </div>
  );
}

/** Aviso local no cabeçalho do app (funciona sem sinal): registros de vacina/
 *  exame guardados há mais de N horas (Parâmetros › Sanitário, padrão 24 h). */
export function AvisoAtrasoSanitario() {
  const fila = useFilaSanitario();
  if (!fila.atrasada) return null;
  return (
    <a href="/app/menu#vacinacao" className="mob-faixa-conexao mob-faixa-offline" role="alert" style={{ textDecoration: "none" }}>
      <AlertTriangle size={13} aria-hidden="true" />
      {fila.itens.length} {fila.itens.length > 1 ? "registros de vacina" : "registro de vacina"} há mais de {fila.horas} h sem enviar. Procure sinal.
    </a>
  );
}
