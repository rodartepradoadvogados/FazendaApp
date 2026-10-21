"use client";
// Lançar › Sanidade › Preventiva › "Vacina ou exame" no celular: o lançamento
// simples "à moda antiga" (também retroativo). O quê (vacina/exame cadastrado
// ou "outro", que só registra), quando (data no passado pede motivo, pulável),
// em quem (seleção de animais), produto (opcional) e quem aplicou.
// Com sinal: POST /sanitario/lancamento-simples (fora da regra → consentimento;
// carência sem decisão → administrador decide; reenvia com a mesma chave).
// Sem sinal: vira registros na fila do aparelho com a MESMA chave por animal
// e é enviado depois pelo POST /sanitario/campo/sincronizar.
import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";
import { MobGaveta } from "@/components/mobile/ui";
import { carregarAnimaisSan, type AnimalSan } from "@/components/sanitario/SeletorAnimais";
import { lancamentoSimples, listarCaixas, mensagemDoErro } from "@/lib/apiSanitario";
import { enfileirarRegistros } from "@/lib/filaSanitario";
import { registrosDoLancamento } from "@/lib/sanitarioCampo";
import {
  ROTULO_RESULTADO, ROTULO_TIPO, hojeISO, intOuNulo, novaChave, textoProduto,
  type CaixaResumo, type CarenciaDecisaoIn, type ConsentimentoIn, type ItemRegistro, type LancamentoSimplesIn,
  type ProdutoIn, type Resultado, type ResultadoRegistro,
} from "@/lib/sanitarioTipos";
import { casaBusca } from "@/lib/busca";
import { TrocarProduto } from "./TrocarProduto";
import {
  CarenciaCampo, ConsentimentoCampo, EscolhaAplicador, FaixaSan, Rotulo, aplicadorEu, camposAplicador, useComCopia, useEuCampo,
  useVeterinariosCampo, type Aplicador, type ParFora,
} from "./comum";

const RESULTADOS: Resultado[] = ["negativo", "positivo", "inconclusivo", "nao_lido"];
const TEMPO_MAX_MS = 15000;

function comTempo<T>(p: Promise<T>): Promise<T> {
  return new Promise((ok, falha) => {
    const t = setTimeout(() => falha(new TypeError("tempo esgotado")), TEMPO_MAX_MS);
    p.then((v) => { clearTimeout(t); ok(v); }, (e) => { clearTimeout(t); falha(e); });
  });
}

export function LancamentoPreventivo() {
  const caixasQ = useComCopia<CaixaResumo[]>("san_caixas_ativas", () => listarCaixas("ativa"));
  const animaisQ = useComCopia<AnimalSan[]>("san_animais", () => carregarAnimaisSan());
  const vets = useVeterinariosCampo();
  const eu = useEuCampo();
  const [caixaId, setCaixaId] = useState<number | "outro" | null>(null);
  const [outro, setOutro] = useState("");
  const [data, setData] = useState(hojeISO());
  const [motivoRetro, setMotivoRetro] = useState("");
  const [sel, setSel] = useState<AnimalSan[]>([]);
  const [escolhendo, setEscolhendo] = useState(false);
  const [produto, setProduto] = useState<ProdutoIn | null>(null);
  const [trocandoProduto, setTrocandoProduto] = useState(false);
  const [aplicador, setAplicador] = useState<Aplicador | null>(() => aplicadorEu());
  const [resultados, setResultados] = useState<Record<number, Resultado>>({});
  const [carLeite, setCarLeite] = useState("");
  const [carCarne, setCarCarne] = useState("");
  const [temAtestado, setTemAtestado] = useState(false);
  const [atNumero, setAtNumero] = useState("");
  const [atDest, setAtDest] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "atencao" | "alerta" | "info"; texto: string } | null>(null);
  const [chaveLote, setChaveLote] = useState(() => novaChave("lanc"));
  const [consentimentos, setConsentimentos] = useState<ConsentimentoIn[]>([]);
  const [carencia, setCarencia] = useState<CarenciaDecisaoIn | null>(null);
  const [pedirConsentimento, setPedirConsentimento] = useState<{ itens: ParFora[]; atestado: boolean } | null>(null);
  const [pedirCarencia, setPedirCarencia] = useState<ItemRegistro | null>(null);
  const [resumo, setResumo] = useState<ResultadoRegistro | null>(null);

  const caixa = typeof caixaId === "number" ? (caixasQ.dados || []).find((c) => c.id === caixaId) : null;
  const ehExame = caixa?.tipo === "exame";
  const hoje = hojeISO();
  const retro = data < hoje;

  function montar(extra: { consentimentos?: ConsentimentoIn[]; carencia?: CarenciaDecisaoIn | null } = {}): LancamentoSimplesIn {
    const dias = { leite_dias: intOuNulo(carLeite), carne_dias: intOuNulo(carCarne) };
    const car = extra.carencia ?? carencia ?? (dias.leite_dias != null || dias.carne_dias != null ? dias : null);
    return {
      caixa_id: typeof caixaId === "number" ? caixaId : null, outro_texto: caixaId === "outro" ? outro : null, data,
      retroativo_motivo: retro ? motivoRetro : null, origem: "lancamento_simples", animal_ids: sel.map((a) => a.id),
      produto: ehExame ? null : produto, ...camposAplicador(aplicador),
      atestado: temAtestado ? { numero: atNumero, destinatario: atDest } : null, carencia: ehExame ? null : car,
      resultados: ehExame ? resultados : {}, consentimentos: extra.consentimentos ?? consentimentos, chave_lote: chaveLote,
    };
  }

  function validar(): string | null {
    if (caixaId == null) return "Escolha a vacina/exame ou “Outro”.";
    if (caixaId === "outro" && !outro.trim()) return "Escreva o que foi feito.";
    if (!sel.length) return "Escolha ao menos um animal.";
    if (data > hoje) return "A data não pode ser no futuro.";
    if (aplicador?.tipo === "texto" && !aplicador.nome.trim()) return "Escreva o nome de quem aplicou.";
    return null;
  }

  async function enviar(extra: { consentimentos?: ConsentimentoIn[]; carencia?: CarenciaDecisaoIn | null } = {}) {
    const erro = validar();
    if (erro) { setAviso({ tipo: "alerta", texto: erro }); return; }
    setEnviando(true); setAviso(null);
    const l = montar(extra);
    try {
      const r = await comTempo(lancamentoSimples(l));
      setResumo(r);
      const pendCons = r.itens.filter((i) => i.status === "pendente" && i.requer.includes("consentimento"));
      const pendCar = r.itens.find((i) => i.status === "pendente" && i.requer.includes("carencia_decisao"));
      if (pendCons.length) {
        setPedirConsentimento({ atestado: pendCons.some((i) => i.pergunta_atestado), itens: pendCons.map((i) => ({
          chave: String(i.animal_id), numero: i.numero || `#${i.animal_id}`, caixa: caixa?.nome_curto || caixa?.nome || "", motivo: i.motivo_fora || "não cumpre a regra",
        })) });
      } else if (pendCar) {
        setPedirCarencia(pendCar);
      } else {
        concluir(`${r.gravados} ${r.gravados === 1 ? "registro gravado" : "registros gravados"}${r.duplicados ? `, ${r.duplicados} já estavam` : ""}${r.erros ? `, ${r.erros} com erro` : ""}.`,
          r.erros ? "atencao" : "ok");
      }
    } catch (e) {
      if (e instanceof TypeError) {
        // Sem sinal (ou rede travada): vai para a fila do aparelho.
        const regs = registrosDoLancamento(l, chaveLote);
        const nomes = new Map(sel.map((a) => [a.id, a.numero]));
        await enfileirarRegistros(regs.map((reg) => ({
          registro: reg, numero: reg.animal_id != null ? nomes.get(reg.animal_id) || `#${reg.animal_id}` : reg.numero_animal || "",
          caixa: caixa?.nome_curto || caixa?.nome || outro || "Outro", dia_nome: null,
        })));
        concluir(`Sem sinal: ${regs.length} ${regs.length === 1 ? "registro guardado" : "registros guardados"} neste celular. Enviam sozinhos quando houver sinal.`, "info");
      } else {
        setAviso({ tipo: "alerta", texto: mensagemDoErro(e, "Não foi possível gravar.") });
      }
    } finally {
      setEnviando(false);
    }
  }

  function concluir(texto: string, tipo: "ok" | "atencao" | "info") {
    setAviso({ tipo, texto });
    try { navigator.vibrate?.(20); } catch { /* sem vibração */ }
    setSel([]); setResultados({}); setConsentimentos([]); setCarencia(null); setChaveLote(novaChave("lanc"));
  }

  const caixas = (caixasQ.dados || []).filter((c) => c.estado === "ativa");
  return (
    <div>
      <Rotulo>1. O quê</Rotulo>
      {caixasQ.carregando && !caixasQ.dados && <p className="mob-san-txt">Carregando…</p>}
      <div className="mob-san-chips">
        {caixas.map((c) => (
          <button key={c.id} type="button" className="mob-san-chip" aria-pressed={caixaId === c.id} onClick={() => { setCaixaId(c.id); setResumo(null); }}>
            <span>{c.nome_curto || c.nome}<small>{ROTULO_TIPO[c.tipo]}</small></span>
          </button>
        ))}
        <button type="button" className="mob-san-chip" aria-pressed={caixaId === "outro"} onClick={() => setCaixaId("outro")}>
          <span>Outro<small>Escrever o que foi feito (só registra no histórico)</small></span>
        </button>
      </div>
      {caixaId === "outro" && (
        <input className="mob-input" style={{ marginTop: "0.5rem" }} value={outro} onChange={(e) => setOutro(e.target.value)} placeholder="ex.: vermífugo da loja" aria-label="O que foi feito" />
      )}

      <Rotulo>2. Quando</Rotulo>
      <input className="mob-input" type="date" max={hoje} value={data} onChange={(e) => setData(e.target.value)} aria-label="Data" />
      {retro && (
        <input className="mob-input" style={{ marginTop: "0.5rem" }} value={motivoRetro} onChange={(e) => setMotivoRetro(e.target.value)}
          placeholder="Motivo do lançamento retroativo (pode pular)" aria-label="Motivo do retroativo" />
      )}

      <Rotulo>3. Em quem</Rotulo>
      <button type="button" className="mob-btn-2" onClick={() => setEscolhendo(true)}>
        {sel.length ? `${sel.length} ${sel.length === 1 ? "animal escolhido" : "animais escolhidos"} · alterar` : "Escolher animais"}
      </button>
      {sel.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginTop: "0.5rem" }}>
          {sel.map((a) => (
            <button key={a.id} type="button" className="mob-pill" style={{ minHeight: 48 }} aria-label={`Tirar ${a.numero}`}
              onClick={() => setSel((s) => s.filter((x) => x.id !== a.id))}>{a.numero} <X size={14} aria-hidden="true" /></button>
          ))}
        </div>
      )}

      {!ehExame && (
        <>
          <Rotulo>4. Produto (opcional)</Rotulo>
          <button type="button" className="mob-btn-2" onClick={() => setTrocandoProduto(true)}>
            {produto ? textoProduto(produto) : caixaId === "outro" ? "Informar o produto" : "Produto do cadastro"}
          </button>
        </>
      )}
      {ehExame && eu?.pode.ler_exame && sel.length > 0 && (
        <>
          <Rotulo>4. Resultado por animal (opcional)</Rotulo>
          {sel.map((a) => (
            <div key={a.id} style={{ marginBottom: "0.5rem" }}>
              <b>{a.numero}</b>
              <div className="mob-san-chips duas" style={{ marginTop: "0.3rem" }}>
                {RESULTADOS.map((r) => (
                  <button key={r} type="button" className="mob-san-chip" aria-pressed={resultados[a.id] === r}
                    onClick={() => setResultados((s) => ({ ...s, [a.id]: r }))}>{ROTULO_RESULTADO[r]}</button>
                ))}
              </div>
            </div>
          ))}
        </>
      )}

      <Rotulo>5. Quem aplicou</Rotulo>
      <EscolhaAplicador valor={aplicador} onChange={setAplicador} vets={vets?.pessoas || []} />

      {!ehExame && (
        <>
          <Rotulo>Carência (dias, se souber)</Rotulo>
          <div className="mob-san-dupla" style={{ marginTop: 0 }}>
            <input className="mob-input" type="number" min={0} inputMode="numeric" value={carLeite} onChange={(e) => setCarLeite(e.target.value)} placeholder="Leite" aria-label="Carência do leite em dias" />
            <input className="mob-input" type="number" min={0} inputMode="numeric" value={carCarne} onChange={(e) => setCarCarne(e.target.value)} placeholder="Carne" aria-label="Carência da carne em dias" />
          </div>
        </>
      )}
      <label className="mob-san-linha" style={{ marginTop: "0.8rem" }}>
        <input type="checkbox" checked={temAtestado} onChange={(e) => setTemAtestado(e.target.checked)} />
        <span>Tem atestado</span>
      </label>
      {temAtestado && (
        <div className="mob-san-dupla" style={{ marginTop: 0 }}>
          <input className="mob-input" value={atNumero} onChange={(e) => setAtNumero(e.target.value)} placeholder="Nº do atestado" />
          <input className="mob-input" value={atDest} onChange={(e) => setAtDest(e.target.value)} placeholder="Para quem" />
        </div>
      )}

      {aviso && <div style={{ marginTop: "0.8rem" }}><FaixaSan tipo={aviso.tipo} role="status">{aviso.texto}</FaixaSan></div>}
      {resumo && resumo.itens.some((i) => i.avisos.length) && (
        <ul className="mob-san-txt" style={{ paddingLeft: "1.1rem" }}>
          {resumo.itens.flatMap((i) => i.avisos.map((a, k) => <li key={`${i.indice}-${k}`}>{a.texto}</li>))}
        </ul>
      )}
      <button type="button" className="mob-btn mob-san-btn-acao" style={{ marginTop: "0.9rem" }} disabled={enviando} onClick={() => enviar()}>
        {enviando ? "Gravando…" : "Gravar"}
      </button>

      <MobGaveta aberto={escolhendo} titulo="Escolher animais" onFechar={() => setEscolhendo(false)}>
        <EscolherAnimais animais={animaisQ.dados} carregando={animaisQ.carregando} inicial={sel}
          onConfirmar={(l) => { setSel(l); setEscolhendo(false); }} onVoltar={() => setEscolhendo(false)} />
      </MobGaveta>
      <MobGaveta aberto={trocandoProduto} titulo="Produto" onFechar={() => setTrocandoProduto(false)}>
        {trocandoProduto && (
          <TrocarProduto titulo="Produto usado neste lançamento." atual={produto} permitirPadrao={caixaId !== "outro"}
            padraoTexto="O produto do cadastro da vacina" onVoltar={() => setTrocandoProduto(false)}
            onAplicar={(p) => { setProduto(p); setTrocandoProduto(false); }} />
        )}
      </MobGaveta>
      <MobGaveta aberto={!!pedirConsentimento} titulo="Fora da regra" onFechar={() => setPedirConsentimento(null)}>
        {pedirConsentimento && (
          <ConsentimentoCampo itens={pedirConsentimento.itens} perguntarAtestado={pedirConsentimento.atestado}
            onVoltar={() => setPedirConsentimento(null)}
            onConfirmar={(r) => {
              const novos: ConsentimentoIn[] = r.aceitos.map((k) => {
                const p = pedirConsentimento.itens.find((x) => x.chave === k)!;
                return { animal_id: Number(k), caixa_id: typeof caixaId === "number" ? caixaId : null, aceito: true, motivo_exibido: p.motivo,
                  quer_atestado: r.quer_atestado, atestado_destinatario: r.destinatario };
              });
              const todos = [...consentimentos, ...novos];
              setConsentimentos(todos);
              if (r.recusados.length) setSel((s) => s.filter((a) => !r.recusados.includes(String(a.id))));
              setPedirConsentimento(null);
              if (novos.length) enviar({ consentimentos: todos });
              else concluir("Os animais fora da regra ficaram de fora. Os demais foram gravados.", "ok");
            }} />
        )}
      </MobGaveta>
      <MobGaveta aberto={!!pedirCarencia} titulo="Carência" onFechar={() => setPedirCarencia(null)}>
        {pedirCarencia && (
          <CarenciaCampo nome={caixa?.nome_curto || caixa?.nome || "o produto"} motivo={pedirCarencia.motivo_carencia}
            sugestao={pedirCarencia.carencia_sugerida} onVoltar={() => setPedirCarencia(null)}
            onDecidir={(d) => { setCarencia(d); setPedirCarencia(null); enviar({ carencia: d }); }} />
        )}
      </MobGaveta>
    </div>
  );
}

function EscolherAnimais({ animais, carregando, inicial, onConfirmar, onVoltar }: {
  animais: AnimalSan[] | null; carregando: boolean; inicial: AnimalSan[]; onConfirmar: (l: AnimalSan[]) => void; onVoltar: () => void;
}) {
  const [busca, setBusca] = useState("");
  const [lote, setLote] = useState("");
  const [marc, setMarc] = useState<Set<number>>(() => new Set(inicial.map((a) => a.id)));
  const lotes = useMemo(() => [...new Set((animais || []).map((a) => a.lote).filter(Boolean) as string[])].sort(), [animais]);
  const visiveis = (animais || []).filter((a) => (!busca.trim() || casaBusca(a.numero, busca)) && (!lote || a.lote === lote)).slice(0, 100);
  if (!animais) return <p className="mob-san-txt">{carregando ? "Carregando os animais…" : "Sem a lista de animais neste celular. Abra com sinal uma vez."}</p>;
  return (
    <div>
      <div style={{ position: "relative" }}>
        <Search size={18} aria-hidden="true" style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--mob-muted)" }} />
        <input className="mob-input" style={{ paddingLeft: "2.6rem" }} inputMode="numeric" value={busca} onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar brinco" aria-label="Buscar brinco" />
      </div>
      <select className="mob-input" style={{ marginTop: "0.5rem" }} value={lote} onChange={(e) => setLote(e.target.value)} aria-label="Lote">
        <option value="">Todos os lotes</option>
        {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
      </select>
      <button type="button" className="mob-btn-2" style={{ marginTop: "0.5rem" }}
        onClick={() => setMarc((p) => { const n = new Set(p); visiveis.forEach((a) => n.add(a.id)); return n; })}>Marcar todos os visíveis</button>
      <div style={{ marginTop: "0.5rem" }}>
        {visiveis.map((a) => (
          <label key={a.id} className="mob-san-linha" data-estado={marc.has(a.id) ? "ok" : undefined}>
            <input type="checkbox" checked={marc.has(a.id)} aria-label={`Escolher ${a.numero}`}
              onChange={() => setMarc((p) => { const n = new Set(p); if (n.has(a.id)) n.delete(a.id); else n.add(a.id); return n; })} />
            <span><b style={{ fontSize: "1.1rem" }}>{a.numero}</b> · {a.categoria || "—"}{a.lote ? ` · ${a.lote}` : ""}</span>
          </label>
        ))}
      </div>
      <div className="mob-san-dupla" style={{ position: "sticky", bottom: 0, background: "var(--mob-surface)", paddingTop: "0.5rem" }}>
        <button type="button" className="mob-btn-2" onClick={onVoltar}>Cancelar</button>
        <button type="button" className="mob-btn" onClick={() => onConfirmar((animais || []).filter((a) => marc.has(a.id)))}>Usar ({marc.size})</button>
      </div>
    </div>
  );
}
