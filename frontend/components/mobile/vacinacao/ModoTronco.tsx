"use client";
// Modo TRONCO: um animal por vez, número grande, uma pastilha por vacina/exame
// (toque tira o que não vai aplicar), peso quando a dose é por peso (sem
// pesagem: média da categoria marcada "estimado"), resultado do exame para
// quem pode ler, APLICADO · PRÓXIMO, "não aplicar" com motivo pulável e os
// últimos 3 com desfazer. Tudo vai para a fila do aparelho (funciona sem sinal).
import { useMemo, useState } from "react";
import { Ban, Check, ChevronsRight, Package, Undo2 } from "lucide-react";
import { OrigemIcone } from "@/components/sanitario/comum";
import { MobGaveta } from "@/components/mobile/ui";
import {
  chaveAC, dosePorPeso, pesoParaDose, produtoEfetivo, quantidadeDose, type AlvoDia,
} from "@/lib/sanitarioCampo";
import { ROTULO_RESULTADO, textoProduto, type EuSanitario, type PacoteOffline, type ProdutoIn, type Resultado } from "@/lib/sanitarioTipos";
import { FaixaSan, Rotulo } from "./comum";
import type { ExecDia } from "./estadoExec";

export type LeituraExame = { resultado: Resultado; valor: number | null };
export type AplicacaoTronco = { alvo: AlvoDia; caixas: number[]; peso: { valor: number | null; estimado: boolean } | null;
  resultados: Record<number, LeituraExame> };

const MOTIVOS = ["Não estava no curral", "Doente ou em tratamento", "Não foi possível conter", "Acabou o produto"];
const RESULTADOS_ORDEM: Resultado[] = ["negativo", "positivo", "inconclusivo", "nao_lido"];

export function ModoTronco({ pacote, alvos, exec, eu, filaIds, onAplicar, onNaoAplicar, onTrocar, onDesfazer }: {
  pacote: PacoteOffline; alvos: AlvoDia[]; exec: ExecDia; eu: EuSanitario | null; filaIds: Set<string>;
  onAplicar: (a: AplicacaoTronco) => Promise<void>;
  onNaoAplicar: (alvo: AlvoDia, motivo: string | null) => void;
  onTrocar: (caixaId: number) => void;
  onDesfazer: (grupo: string) => Promise<string | null>;
}) {
  const [idx, setIdx] = useState(0);
  const [desl, setDesl] = useState<Set<string>>(() => new Set());
  const [pesoTxt, setPesoTxt] = useState<Record<string, string>>({});
  const [leituras, setLeituras] = useState<Record<string, LeituraExame>>({});
  const [motivoDe, setMotivoDe] = useState<AlvoDia | null>(null);
  const [outro, setOutro] = useState("");
  const [aplicando, setAplicando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [ir, setIr] = useState("");
  const caixas = useMemo(() => new Map(pacote.caixas.map((c) => [c.caixa_id, c])), [pacote.caixas]);
  const estoques = useMemo(() => new Map(pacote.estoques.map((e) => [e.id, e])), [pacote.estoques]);
  const ultimos = useMemo(() => {
    const grupos: { grupo: string; numero: string; caixas: string[]; chaves: string[] }[] = [];
    for (const f of [...exec.feitos].reverse()) {
      let g = grupos.find((x) => x.grupo === f.grupo && x.numero === f.numero);
      if (!g) {
        if (grupos.length >= 3) continue;
        g = { grupo: f.grupo, numero: f.numero, caixas: [], chaves: [] };
        grupos.push(g);
      }
      g.caixas.push(f.caixa);
      g.chaves.push(f.chave);
    }
    return grupos;
  }, [exec.feitos]);

  if (!alvos.length) {
    return (
      <>
        <FaixaSan tipo="ok" role="status">Todos os animais deste dia foram registrados neste celular
          {exec.feitos.some((f) => filaIds.has(f.chave)) ? " (parte esperando sinal para enviar)" : ""}.</FaixaSan>
        <Ultimos ultimos={ultimos} filaIds={filaIds} onDesfazer={onDesfazer} />
      </>
    );
  }
  const i = Math.min(idx, alvos.length - 1);
  const alvo = alvos[i];
  const ligadas = alvo.caixas.filter((c) => !desl.has(chaveAC(alvo.animal, c)));
  const prodDe = (c: number): ProdutoIn => produtoEfetivo(caixas.get(c)?.produto, exec.trocas[String(c)]);
  const porPeso = ligadas.some((c) => caixas.get(c)?.tipo !== "exame" && dosePorPeso(prodDe(c)));
  const pesoAuto = pesoParaDose(alvo, pacote.animais);
  const pesoDigitado = pesoTxt[alvo.animal];
  const pesoValor = pesoDigitado != null && pesoDigitado.trim() !== "" ? Number(pesoDigitado.replace(",", ".")) : pesoAuto.peso;
  const estimado = pesoDigitado == null && pesoAuto.estimado;
  const podeLer = !!eu?.pode.ler_exame;
  const exames = ligadas.filter((c) => caixas.get(c)?.tipo === "exame");

  async function aplicar() {
    if (!ligadas.length || aplicando) return;
    setAplicando(true); setMsg(null);
    try {
      const resultados: Record<number, LeituraExame> = {};
      for (const c of exames) { const l = leituras[chaveAC(alvo.animal, c)]; if (l) resultados[c] = l; }
      await onAplicar({ alvo, caixas: ligadas, peso: porPeso ? { valor: Number.isFinite(pesoValor as number) ? pesoValor : null, estimado } : null, resultados });
      try { navigator.vibrate?.(20); } catch { /* sem vibração */ }
      setIdx(i >= alvos.length - 1 ? 0 : i); // a lista encolhe: o próximo ocupa a mesma posição
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Não foi possível guardar o registro.");
    } finally {
      setAplicando(false);
    }
  }
  function irPara() {
    const n = ir.trim();
    const j = alvos.findIndex((a) => a.numero === n);
    setMsg(j >= 0 ? null : `O brinco ${n} não está na fila deste dia. Use “Adicionar animais”.`);
    if (j >= 0) { setIdx(j); setIr(""); }
  }

  return (
    <div>
      <div className="mob-card" data-estado="normal" style={{ padding: "0.95rem 1rem" }}>
        <span className="mob-san-rotulo" style={{ marginTop: 0 }}>Animal {i + 1} de {alvos.length}</span>
        <div style={{ display: "flex", alignItems: "center", gap: "0.8rem", marginTop: "0.3rem" }}>
          <span className="mob-san-num" aria-label={`Animal ${alvo.numero}`}>{alvo.numero}</span>
          <OrigemIcone origem={alvo.origem} tamanho={18} />
          {alvo.semCadastro && <span className="mob-san-tag atencao">sem cadastro</span>}
        </div>
        <p className="mob-san-txt">{[alvo.categoria, alvo.idade, alvo.lote].filter(Boolean).join(" · ") || "—"}</p>
        {alvo.origem !== "janela" && (
          <p className="mob-san-txt">{alvo.origem === "curral" ? "Incluído no curral" : "Incluído manualmente"}
            {Object.keys(alvo.consent).length ? " com consentimento" : ""}.</p>
        )}
      </div>

      <Rotulo>Toque para tirar o que não vai aplicar</Rotulo>
      <div className="mob-san-chips">
        {alvo.caixas.map((c) => {
          const cx = caixas.get(c);
          const k = chaveAC(alvo.animal, c);
          const on = !desl.has(k);
          const p = prodDe(c);
          const est = p.estoque_id ? estoques.get(p.estoque_id) : undefined;
          const qtd = cx?.tipo !== "exame" && dosePorPeso(p) ? quantidadeDose(p, pesoValor) : null;
          return (
            <div key={c} style={{ display: "flex", gap: "0.4rem" }}>
              <button type="button" className="mob-san-chip" aria-pressed={on} style={{ flex: 1 }}
                onClick={() => setDesl((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; })}>
                <span>{cx?.nome_curto || cx?.nome || `#${c}`}
                  <small>{cx?.tipo === "exame" ? "exame" : textoProduto(p, est?.nome)}
                    {qtd != null ? ` → ${String(qtd).replace(".", ",")} mL` : ""}
                    {exec.trocas[String(c)] ? " · trocado" : ""}
                    {est && est.saldo != null && est.saldo <= 0 ? " · sem saldo" : ""}</small>
                </span>
                {on ? <Check size={22} aria-hidden="true" /> : <Ban size={20} aria-hidden="true" />}
              </button>
              {cx?.tipo !== "exame" && (
                <button type="button" className="mob-btn-2" style={{ width: 64, flexShrink: 0 }} aria-label={`Trocar produto de ${cx?.nome_curto || c}`}
                  onClick={() => onTrocar(c)}><Package size={20} aria-hidden="true" /></button>
              )}
            </div>
          );
        })}
      </div>

      {porPeso && (
        <>
          <Rotulo>Peso para a dose (kg)</Rotulo>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <input className="mob-input" inputMode="decimal" aria-label="Peso em kg" style={{ flex: 1 }}
              value={pesoDigitado ?? (pesoAuto.peso != null ? String(pesoAuto.peso) : "")}
              onChange={(e) => setPesoTxt((s) => ({ ...s, [alvo.animal]: e.target.value }))} placeholder="sem pesagem" />
            {estimado && <span className="mob-san-tag estimado">estimado</span>}
          </div>
          {estimado && <p className="mob-san-txt">Sem pesagem: média da categoria {alvo.categoria}. Fica marcado “estimado” no registro.</p>}
          {pesoValor == null && <p className="mob-san-txt">Sem peso: registra a dose informada, sem cálculo.</p>}
        </>
      )}

      {exames.length > 0 && podeLer && exames.map((c) => {
        const k = chaveAC(alvo.animal, c);
        const modo = ((caixas.get(c)?.regras as { legal_leitura?: { modo?: string } | null })?.legal_leitura?.modo) || "so_resultado";
        const l = leituras[k];
        return (
          <div key={c}>
            <Rotulo>Resultado de {caixas.get(c)?.nome_curto} (opcional)</Rotulo>
            <div className="mob-san-chips duas">
              {RESULTADOS_ORDEM.map((r) => (
                <button key={r} type="button" className="mob-san-chip" aria-pressed={l?.resultado === r}
                  onClick={() => setLeituras((s) => ({ ...s, [k]: { resultado: r, valor: s[k]?.valor ?? null } }))}>
                  <span>{ROTULO_RESULTADO[r]}</span>
                </button>
              ))}
            </div>
            {modo !== "so_resultado" && l && (
              <input className="mob-input" style={{ marginTop: "0.5rem" }} inputMode="decimal" aria-label="Diferença em mm"
                placeholder="diferença (mm)" value={l.valor ?? ""}
                onChange={(e) => setLeituras((s) => ({ ...s, [k]: { ...l, valor: e.target.value === "" ? null : Number(e.target.value.replace(",", ".")) } }))} />
            )}
          </div>
        );
      })}
      {exames.length > 0 && !podeLer && (
        <p className="mob-san-txt">A leitura do exame é lançada pelo veterinário ou pelo administrador.</p>
      )}

      {msg && <FaixaSan tipo="alerta">{msg}</FaixaSan>}
      <button type="button" className="mob-btn mob-san-btn-acao" style={{ marginTop: "0.9rem" }} disabled={!ligadas.length || aplicando} onClick={aplicar}>
        <Check size={22} aria-hidden="true" /> {aplicando ? "Guardando…" : "APLICADO · PRÓXIMO"}
      </button>
      <div className="mob-san-dupla">
        <button type="button" className="mob-btn-2" onClick={() => setMotivoDe(alvo)}><Ban size={18} aria-hidden="true" /> Não aplicar</button>
        <button type="button" className="mob-btn-2" onClick={() => setIdx(i + 1 >= alvos.length ? 0 : i + 1)} disabled={alvos.length < 2}>
          <ChevronsRight size={18} aria-hidden="true" /> Pular para depois</button>
      </div>
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
        <input className="mob-input" inputMode="numeric" value={ir} onChange={(e) => setIr(e.target.value)} placeholder="Ir para o brinco"
          aria-label="Ir para o brinco" onKeyDown={(e) => { if (e.key === "Enter") irPara(); }} />
        <button type="button" className="mob-btn-2" style={{ width: 96 }} onClick={irPara} disabled={!ir.trim()}>Ir</button>
      </div>

      <Ultimos ultimos={ultimos} filaIds={filaIds} onDesfazer={onDesfazer} />

      <MobGaveta aberto={!!motivoDe} titulo={`Não aplicar em ${motivoDe?.numero ?? ""}`} onFechar={() => setMotivoDe(null)}>
        <p className="mob-san-txt" style={{ marginTop: 0 }}>O motivo é opcional. O animal volta para a caixa quando o dia for fechado.</p>
        <div className="mob-san-chips">
          {MOTIVOS.map((m) => (
            <button key={m} type="button" className="mob-san-chip" onClick={() => { onNaoAplicar(motivoDe!, m); setMotivoDe(null); }}>{m}</button>
          ))}
        </div>
        <input className="mob-input" style={{ marginTop: "0.6rem" }} value={outro} onChange={(e) => setOutro(e.target.value)} placeholder="Outro motivo" />
        <div className="mob-san-dupla" style={{ marginTop: "0.6rem" }}>
          <button type="button" className="mob-btn-2" onClick={() => { onNaoAplicar(motivoDe!, null); setMotivoDe(null); }}>Pular o motivo</button>
          <button type="button" className="mob-btn" disabled={!outro.trim()} onClick={() => { onNaoAplicar(motivoDe!, outro.trim()); setOutro(""); setMotivoDe(null); }}>Usar este motivo</button>
        </div>
      </MobGaveta>
    </div>
  );
}

export function Ultimos({ ultimos, filaIds, onDesfazer }: {
  ultimos: { grupo: string; numero: string; caixas: string[]; chaves: string[] }[]; filaIds: Set<string>;
  onDesfazer: (grupo: string) => Promise<string | null>;
}) {
  const [msg, setMsg] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  if (!ultimos.length) return null;
  return (
    <>
      <Rotulo>Últimos registrados</Rotulo>
      <div className="mob-san-ultimos">
        {ultimos.map((u) => {
          const naFila = u.chaves.some((k) => filaIds.has(k));
          return (
            <div key={`${u.grupo}|${u.numero}`} data-fila={naFila ? "1" : "0"}>
              <span style={{ flex: 1, minWidth: 0 }}>
                <b style={{ fontSize: "1.1rem" }}>{u.numero}</b> · {u.caixas.join(", ")}
                <span className="mob-san-txt" style={{ display: "block", marginTop: 0 }}>{naFila ? "no celular, esperando envio" : "enviado"}</span>
              </span>
              <button type="button" className="mob-btn-2" disabled={ocupado === u.grupo + u.numero}
                onClick={async () => { setOcupado(u.grupo + u.numero); setMsg(await onDesfazer(u.grupo + "|" + u.numero)); setOcupado(null); }}>
                <Undo2 size={16} aria-hidden="true" /> Desfazer
              </button>
            </div>
          );
        })}
      </div>
      {msg && <p className="mob-san-txt" role="status">{msg}</p>}
    </>
  );
}

