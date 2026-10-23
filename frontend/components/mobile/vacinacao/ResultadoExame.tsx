"use client";
// Leitura do exame no celular: lista os exames do dia já registrados e sem
// resultado (precisa de sinal) e lança o resultado no modo da fazenda/caixa
// ("só resultado" ou com a diferença em mm). Veterinário lança pela própria
// pessoa; o administrador informa o veterinário responsável.
import { useState } from "react";
import { lancarResultado, mensagemDoErro, registrosDoDia } from "@/lib/apiSanitario";
import { ROTULO_RESULTADO, type EuSanitario, type PacoteOffline, type Registro, type Resultado } from "@/lib/sanitarioTipos";
import { FaixaSan, Rotulo, useComCopia } from "./comum";

const ORDEM: Resultado[] = ["negativo", "positivo", "inconclusivo", "nao_lido"];

export function ResultadoExame({ pacote, eu }: { pacote: PacoteOffline; eu: EuSanitario | null }) {
  const diaId = pacote.dia.id;
  const exames = new Map(pacote.caixas.filter((c) => c.tipo === "exame").map((c) => [c.caixa_id, c]));
  const regs = useComCopia<Registro[]>(exames.size ? `san_registros_dia_${diaId}` : null, () => registrosDoDia(diaId));
  const [vet, setVet] = useState<{ pessoa_id: number | null; texto: string; crmv: string }>(() => ({
    pessoa_id: pacote.dia.veterinario?.pessoa_id ?? null, texto: pacote.dia.veterinario?.texto || "", crmv: pacote.dia.veterinario?.crmv || "",
  }));
  const [escolha, setEscolha] = useState<Record<number, { resultado: Resultado | null; valor: string }>>({});
  const [msg, setMsg] = useState<Record<number, string>>({});
  const [feitos, setFeitos] = useState<Set<number>>(() => new Set());
  if (!exames.size || !eu?.pode.ler_exame) return null;
  const semResultado = (regs.dados || []).filter((r) => r.caixa_id && exames.has(r.caixa_id) && !r.resultado && r.estado === "valido" && !feitos.has(r.id));
  const ehVet = eu.veterinario_pessoa_id != null;

  async function lancar(r: Registro) {
    const e = escolha[r.id];
    if (!e?.resultado) return;
    if (!ehVet && !vet.pessoa_id && !vet.texto.trim()) { setMsg((m) => ({ ...m, [r.id]: "Informe o veterinário responsável pela leitura." })); return; }
    try {
      await lancarResultado(r.id, {
        resultado: e.resultado, resultado_valor: e.valor ? Number(e.valor.replace(",", ".")) : null,
        veterinario_pessoa_id: ehVet ? null : vet.pessoa_id, veterinario_texto: ehVet ? null : (vet.texto.trim() || null),
        crmv_texto: vet.crmv.trim() || null,
      });
      setFeitos((s) => new Set(s).add(r.id));
    } catch (err) {
      setMsg((m) => ({ ...m, [r.id]: mensagemDoErro(err, "Não foi possível lançar agora (precisa de sinal).") }));
    }
  }

  return (
    <div>
      <Rotulo>Leitura de exame</Rotulo>
      {regs.doCache && <p className="mob-san-txt">Lista da última vez com sinal. Lançar a leitura precisa de sinal.</p>}
      {!ehVet && (
        <div className="mob-card" style={{ padding: "0.8rem", marginBottom: "0.6rem" }}>
          <span className="mob-san-rotulo" style={{ marginTop: 0 }}>Veterinário responsável pela leitura</span>
          <select className="mob-input" value={vet.pessoa_id ?? ""} aria-label="Veterinário"
            onChange={(e) => {
              const p = pacote.veterinarios.find((v) => v.pessoa_id === Number(e.target.value));
              setVet(p ? { pessoa_id: p.pessoa_id, texto: "", crmv: p.crmv || "" } : { pessoa_id: null, texto: vet.texto, crmv: vet.crmv });
            }}>
            <option value="">Outro (escrever)</option>
            {pacote.veterinarios.map((v) => <option key={v.pessoa_id} value={v.pessoa_id}>{v.nome}</option>)}
          </select>
          {!vet.pessoa_id && (
            <input className="mob-input" style={{ marginTop: "0.5rem" }} value={vet.texto} placeholder="Nome do veterinário"
              onChange={(e) => setVet({ ...vet, texto: e.target.value })} />
          )}
          <input className="mob-input" style={{ marginTop: "0.5rem" }} value={vet.crmv} placeholder="CRMV (pedido, não obrigatório)"
            onChange={(e) => setVet({ ...vet, crmv: e.target.value })} />
        </div>
      )}
      {regs.carregando && !regs.dados && <p className="mob-san-txt">Carregando…</p>}
      {!regs.carregando && !semResultado.length && <p className="mob-san-txt">Nenhum exame deste dia esperando leitura.</p>}
      {semResultado.map((r) => {
        const cx = exames.get(r.caixa_id!);
        const modo = ((cx?.regras as { legal_leitura?: { modo?: string } | null })?.legal_leitura?.modo) || "so_resultado";
        const e = escolha[r.id] || { resultado: null, valor: "" };
        return (
          <div key={r.id} className="mob-card" style={{ padding: "0.8rem", marginBottom: "0.6rem" }}>
            <b style={{ fontSize: "1.2rem" }}>{r.numero}</b> · {cx?.nome_curto}
            <div className="mob-san-chips duas" style={{ marginTop: "0.5rem" }}>
              {ORDEM.map((x) => (
                <button key={x} type="button" className="mob-san-chip" aria-pressed={e.resultado === x}
                  onClick={() => setEscolha((s) => ({ ...s, [r.id]: { ...e, resultado: x } }))}>{ROTULO_RESULTADO[x]}</button>
              ))}
            </div>
            {modo !== "so_resultado" && (
              <input className="mob-input" style={{ marginTop: "0.5rem" }} inputMode="decimal" value={e.valor} placeholder="diferença (mm)"
                onChange={(ev) => setEscolha((s) => ({ ...s, [r.id]: { ...e, valor: ev.target.value } }))} />
            )}
            {msg[r.id] && <FaixaSan tipo="alerta">{msg[r.id]}</FaixaSan>}
            <button type="button" className="mob-btn" style={{ marginTop: "0.5rem" }} disabled={!e.resultado} onClick={() => lancar(r)}>Lançar resultado</button>
          </div>
        );
      })}
    </div>
  );
}
