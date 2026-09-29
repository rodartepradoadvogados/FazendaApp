"use client";
// Checklist do agendamento preventivo (passo "Checklist" do assistente Criar
// agendamento, "Continuar montando" e aba Checklist do agendamento):
// veterinário confirmado ou Desconsiderar (com motivo), estoque vinculado ou
// Desconsiderar (com motivo e lote/validade do veterinário), data e "outros"
// itens da fazenda. Nada bloqueia: o que ficar pendente pede só a ciência ao
// Aplicar.
import { useEffect, useState } from "react";
import { AlertTriangle, Check, Plus, RotateCcw, SkipForward, X } from "lucide-react";
import {
  fetchEstoque, fetchLotesEstoque, type ChecklistAgendamentoPayload, type ItemChecklistAg, type LoteEstoque, type VeterinarioChecklist,
} from "@/lib/api";
import { Chips, dataCurta, dataHoraCurta, inputStyle, labelStyle, MOTIVOS_ESTOQUE, MOTIVOS_VET, notaStyle, textoMotivo } from "./preventivoComum";
import { financeiroParaPayload, financeiroVazio, FinanceiroRascunho, type FinanceiroDraft } from "./FinanceiroAgendamento";

/** "agora" no formato do <input type="datetime-local"> (hora local). */
export function agoraLocal(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}
/** Hora local digitada -> instante em UTC (o servidor grava em UTC). */
export const localParaUtcIso = (v: string): string | null => { const d = new Date(v); return isNaN(d.getTime()) ? null : d.toISOString(); };

export type ChecklistDraft = {
  vet: { estado: "pendente" | "confirmado" | "desconsiderado"; pessoaId: string; motivo: string; outro: string; quando: string; nota: string };
  financeiro: FinanceiroDraft;
  estoque: { estado: "pendente" | "vinculado" | "desconsiderado"; estoqueId: string; loteId: string; motivo: string; outro: string; lote: string; validade: string };
  data: boolean;
  extras: string[];
};

export const checklistVazio = (): ChecklistDraft => ({
  vet: { estado: "pendente", pessoaId: "", motivo: "", outro: "", quando: "", nota: "" },
  financeiro: financeiroVazio(),
  estoque: { estado: "pendente", estoqueId: "", loteId: "", motivo: "", outro: "", lote: "", validade: "" },
  data: false,
  extras: [],
});

/** Erro de preenchimento (motivo obrigatório ao desconsiderar) ou null. */
export function validarChecklist(d: ChecklistDraft): string | null {
  if (d.vet.estado === "confirmado" && !d.vet.pessoaId) return "Escolha o veterinário confirmado ou desconsidere o item.";
  if (d.vet.estado === "desconsiderado" && !textoMotivo(d.vet.motivo, d.vet.outro)) return "Escolha o motivo para desconsiderar o veterinário.";
  if (d.estoque.estado === "vinculado" && !d.estoque.estoqueId) return "Escolha o produto do estoque ou desconsidere o item.";
  if (d.estoque.estado === "desconsiderado" && !textoMotivo(d.estoque.motivo, d.estoque.outro)) return "Escolha o motivo para desconsiderar o estoque.";
  return null;
}

export function checklistParaPayload(d: ChecklistDraft): ChecklistAgendamentoPayload | null {
  const p: ChecklistAgendamentoPayload = {};
  if (d.vet.estado === "confirmado") {
    p.veterinario = { estado: "confirmado", pessoa_id: Number(d.vet.pessoaId), quando: d.vet.quando ? localParaUtcIso(d.vet.quando) : null, observacao: d.vet.nota.trim() || null };
  }
  const fin = financeiroParaPayload(d.financeiro);
  if (fin) p.financeiro = fin;
  if (d.vet.estado === "desconsiderado") p.veterinario = { estado: "desconsiderado", motivo: textoMotivo(d.vet.motivo, d.vet.outro) };
  if (d.estoque.estado === "vinculado") {
    p.estoque = { estado: "vinculado", estoque_id: Number(d.estoque.estoqueId), lote_id: d.estoque.loteId ? Number(d.estoque.loteId) : null };
  }
  if (d.estoque.estado === "desconsiderado") {
    p.estoque = {
      estado: "desconsiderado", motivo: textoMotivo(d.estoque.motivo, d.estoque.outro),
      lote: d.estoque.lote.trim() || null, validade: d.estoque.validade || null,
    };
  }
  if (d.data) p.data = { estado: "confirmado" };
  const extras = d.extras.map((t) => t.trim()).filter(Boolean);
  if (extras.length) p.extras = extras.map((texto) => ({ texto }));
  return Object.keys(p).length ? p : null;
}

export function resumoChecklistDraft(d: ChecklistDraft, temHora: boolean): { resolvidos: number; total: number; linhas: string[] } {
  const linhas: string[] = [];
  let resolvidos = 0;
  if (d.vet.estado === "confirmado") { resolvidos++; linhas.push("Veterinário confirmado"); }
  else if (d.vet.estado === "desconsiderado") { resolvidos++; linhas.push("Veterinário desconsiderado"); }
  else linhas.push("Veterinário: pendente");
  if (d.estoque.estado === "vinculado") { resolvidos++; linhas.push("Estoque vinculado"); }
  else if (d.estoque.estado === "desconsiderado") { resolvidos++; linhas.push("Estoque desconsiderado (sem baixa)"); }
  else linhas.push("Estoque: pendente");
  if (d.data && temHora) { resolvidos++; linhas.push("Data e hora confirmadas"); } else linhas.push("Data: pendente");
  if (d.financeiro.compra) { resolvidos++; linhas.push(d.financeiro.compra.modo === "ja_comprei" ? "Compra: já comprei" : `Compra: ${d.financeiro.compra.modo === "pedido" ? "pedido" : "cotação"} a criar`); }
  else if (d.estoque.estado === "desconsiderado") { resolvidos++; linhas.push("Compra: não necessária (estoque desconsiderado)"); }
  else linhas.push("Compra: pendente");
  if (d.financeiro.pagamento || d.financeiro.contas.length) {
    resolvidos++;
    linhas.push([d.financeiro.pagamento ? "pagamento já realizado a vincular" : "", d.financeiro.contas.length ? `${d.financeiro.contas.length} ${d.financeiro.contas.length === 1 ? "conta a pagar" : "contas a pagar"} a lançar` : ""].filter(Boolean).join(" e "));
  } else linhas.push("Financeiro: pendente");
  return { resolvidos, total: 5 + d.extras.filter((t) => t.trim()).length, linhas };
}

type PessoaVet = { id: number; nome: string; crmv?: string | null };

export function ChecklistMontagem({
  draft, onChange, veterinarios, produto, dataEvento, hora, tentou, calendarioId, animais,
}: {
  draft: ChecklistDraft; onChange: (d: ChecklistDraft) => void; veterinarios: PessoaVet[];
  produto: string | null; dataEvento: string; hora: string; tentou?: boolean;
  /** Assistente Criar agendamento: mostra o financeiro (compra, pagamento, conta a pagar) deste passo. */
  calendarioId?: number; animais?: string[];
}) {
  const [itens, setItens] = useState<any[]>([]);
  const [lotes, setLotes] = useState<LoteEstoque[]>([]);
  const [novo, setNovo] = useState("");
  useEffect(() => { fetchEstoque().then((d) => setItens((d.itens || []).filter((i: any) => i.id != null))).catch(() => setItens([])); }, []);
  // Sugere o produto do protocolo assim que o estoque carrega (nunca vem marcado sozinho).
  const sugerido = itens.find((i) => i.nome === produto);
  useEffect(() => {
    if (!draft.estoque.estoqueId) { setLotes([]); return; }
    fetchLotesEstoque(Number(draft.estoque.estoqueId)).then((l) => setLotes(l.filter((x) => x.quantidade_restante > 0))).catch(() => setLotes([]));
  }, [draft.estoque.estoqueId]);

  const set = (parcial: Partial<ChecklistDraft>) => onChange({ ...draft, ...parcial });
  const erroVet = tentou && draft.vet.estado === "desconsiderado" && !textoMotivo(draft.vet.motivo, draft.vet.outro) ? "Escolha o motivo." : null;
  const erroEst = tentou && draft.estoque.estado === "desconsiderado" && !textoMotivo(draft.estoque.motivo, draft.estoque.outro) ? "Escolha o motivo." : null;
  const itemBox: React.CSSProperties = { borderBottom: "1px solid var(--border)", padding: "0.8rem 0", display: "flex", flexDirection: "column", gap: "0.6rem" };
  const cab = (titulo: string, ok: boolean, sub?: string) => (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
      <span style={{ color: ok ? "var(--green-light)" : "var(--amber)", display: "inline-flex" }}>{ok ? <Check size={16} /> : <AlertTriangle size={16} />}</span>
      <b style={{ fontSize: "0.9rem" }}>{titulo}</b>
      {sub && <span style={notaStyle}>{sub}</span>}
    </div>
  );

  return (
    <div className="card" style={{ padding: "0.4rem 1rem" }}>
      {/* Veterinário */}
      <div style={itemBox}>
        {cab("Veterinário", draft.vet.estado !== "pendente", draft.vet.estado === "pendente" ? "pendente" : draft.vet.estado === "confirmado" ? "confirmado" : "desconsiderado")}
        <Chips
          idBase="ck-vet" rotulo="Situação" valor={draft.vet.estado === "confirmado" ? "Confirmado" : draft.vet.estado === "desconsiderado" ? "Desconsiderar" : "Deixar pendente"}
          opcoes={["Confirmado", "Desconsiderar", "Deixar pendente"]}
          onChange={(v) => set({ vet: { ...draft.vet, estado: v === "Confirmado" ? "confirmado" : v === "Desconsiderar" ? "desconsiderado" : "pendente" } })}
        />
        {draft.vet.estado === "confirmado" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label htmlFor="ck-vet-p" style={labelStyle}>Confirmado com (veterinário cadastrado em Pessoas)</label>
                <select id="ck-vet-p" style={inputStyle} value={draft.vet.pessoaId} onChange={(e) => set({ vet: { ...draft.vet, pessoaId: e.target.value } })}>
                  <option value="">Escolha o veterinário</option>
                  {veterinarios.map((v) => <option key={v.id} value={v.id}>{v.nome}{v.crmv ? ` (${v.crmv})` : ""}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="ck-vet-q" style={labelStyle}>Confirmado em (quando combinou)</label>
                <input id="ck-vet-q" type="datetime-local" style={inputStyle} value={draft.vet.quando || agoraLocal()} max={agoraLocal()} onChange={(e) => set({ vet: { ...draft.vet, quando: e.target.value } })} />
              </div>
            </div>
            <div>
              <label htmlFor="ck-vet-n" style={labelStyle}>Como confirmou (opcional)</label>
              <input id="ck-vet-n" style={inputStyle} value={draft.vet.nota} onChange={(e) => set({ vet: { ...draft.vet, nota: e.target.value } })} placeholder="ex.: por telefone, pelo WhatsApp" />
            </div>
            {!veterinarios.length && <p style={{ ...notaStyle, marginTop: "0.1rem" }}>Nenhum veterinário cadastrado. Cadastre em Configurações › Cadastro › Pessoas (com o CRMV).</p>}
            {(() => { const v = veterinarios.find((x) => String(x.id) === draft.vet.pessoaId); return v ? <p style={{ ...notaStyle, margin: 0 }}>Fica registrado: {v.nome}{v.crmv ? ` · ${v.crmv}` : " · sem CRMV cadastrado"}, quem registrou e quando.</p> : null; })()}
          </div>
        )}
        {draft.vet.estado === "desconsiderado" && (
          <>
            <Chips idBase="ck-vet-m" rotulo="Por que desconsiderar? (obrigatório)" opcoes={MOTIVOS_VET} valor={draft.vet.motivo} onChange={(v) => set({ vet: { ...draft.vet, motivo: v } })} erro={erroVet} />
            {draft.vet.motivo === "Outro" && <input style={inputStyle} aria-label="Descreva o motivo" placeholder="Descreva o motivo" value={draft.vet.outro} onChange={(e) => set({ vet: { ...draft.vet, outro: e.target.value } })} />}
          </>
        )}
      </div>

      {/* Estoque */}
      <div style={itemBox}>
        {cab("Estoque", draft.estoque.estado !== "pendente", draft.estoque.estado === "pendente" ? "pendente" : draft.estoque.estado === "vinculado" ? "vinculado" : "desconsiderado")}
        <Chips
          idBase="ck-est" rotulo="Situação" valor={draft.estoque.estado === "vinculado" ? "Vincular produto" : draft.estoque.estado === "desconsiderado" ? "Desconsiderar" : "Deixar pendente"}
          opcoes={["Vincular produto", "Desconsiderar", "Deixar pendente"]}
          onChange={(v) => set({
            estoque: {
              ...draft.estoque, estado: v === "Vincular produto" ? "vinculado" : v === "Desconsiderar" ? "desconsiderado" : "pendente",
              estoqueId: v === "Vincular produto" && !draft.estoque.estoqueId && sugerido ? String(sugerido.id) : draft.estoque.estoqueId,
            },
          })}
        />
        {draft.estoque.estado === "vinculado" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label htmlFor="ck-est-p" style={labelStyle}>Produto do estoque{produto ? ` (protocolo: ${produto})` : ""}</label>
              <select id="ck-est-p" style={inputStyle} value={draft.estoque.estoqueId} onChange={(e) => set({ estoque: { ...draft.estoque, estoqueId: e.target.value, loteId: "" } })}>
                <option value="">Escolha o produto</option>
                {itens.map((i) => <option key={i.id} value={i.id}>{i.nome} · saldo {i.quantidade ?? 0} {i.unidade || ""}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="ck-est-l" style={labelStyle}>Frasco / lote (validade)</label>
              <select id="ck-est-l" style={inputStyle} value={draft.estoque.loteId} onChange={(e) => set({ estoque: { ...draft.estoque, loteId: e.target.value } })} disabled={!lotes.length}>
                <option value="">{lotes.length ? "O mais antigo dentro da validade" : "Sem frascos abertos"}</option>
                {lotes.map((l) => <option key={l.id} value={l.id}>{l.numero_lote || `#${l.id}`} · validade {dataCurta(l.validade)} · saldo {l.quantidade_restante}</option>)}
              </select>
            </div>
          </div>
        )}
        {draft.estoque.estado === "desconsiderado" && (
          <>
            <Chips idBase="ck-est-m" rotulo="Por que desconsiderar o estoque? (obrigatório)" opcoes={MOTIVOS_ESTOQUE} valor={draft.estoque.motivo} onChange={(v) => set({ estoque: { ...draft.estoque, motivo: v } })} erro={erroEst} />
            {draft.estoque.motivo === "Outro" && <input style={inputStyle} aria-label="Descreva o motivo" placeholder="Descreva o motivo" value={draft.estoque.outro} onChange={(e) => set({ estoque: { ...draft.estoque, outro: e.target.value } })} />}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div><label htmlFor="ck-est-lv" style={labelStyle}>Lote do frasco (do veterinário)</label><input id="ck-est-lv" style={inputStyle} value={draft.estoque.lote} onChange={(e) => set({ estoque: { ...draft.estoque, lote: e.target.value } })} placeholder="ex.: VET-778" /></div>
              <div><label htmlFor="ck-est-vv" style={labelStyle}>Validade</label><input id="ck-est-vv" type="date" style={inputStyle} value={draft.estoque.validade} onChange={(e) => set({ estoque: { ...draft.estoque, validade: e.target.value } })} /></div>
            </div>
            <p style={notaStyle}>Nada é baixado do estoque. O lote e a validade ficam no registro da aplicação.</p>
          </>
        )}
      </div>

      {/* Data */}
      <div style={itemBox}>
        {cab("Data e hora", draft.data && !!hora, draft.data && hora ? `${dataCurta(dataEvento)} às ${hora}` : "pendente")}
        <label style={{ display: "flex", gap: "0.6rem", alignItems: "center", cursor: "pointer", fontSize: "0.85rem" }}>
          <input type="checkbox" checked={draft.data} onChange={(e) => set({ data: e.target.checked })} style={{ width: 18, height: 18 }} disabled={!hora} />
          <span>Data e hora combinadas com quem vai aplicar{!hora ? " (informe a hora no passo anterior)" : ""}</span>
        </label>
      </div>

      {/* Financeiro: compra, pagamento já realizado, conta a pagar */}
      {calendarioId != null && (
        <div style={itemBox}>
          {cab("Compra e financeiro", !!draft.financeiro.compra || !!draft.financeiro.pagamento || draft.financeiro.contas.length > 0)}
          <FinanceiroRascunho
            calendarioId={calendarioId} animais={animais || []} dataEvento={dataEvento}
            vetNome={veterinarios.find((v) => String(v.id) === draft.vet.pessoaId)?.nome || null}
            draft={draft.financeiro} onChange={(financeiro) => set({ financeiro })}
          />
        </div>
      )}

      {/* Outros */}
      <div style={{ ...itemBox, borderBottom: "none" }}>
        {cab("Outros itens da fazenda", draft.extras.length > 0)}
        <p style={notaStyle}>Os demais itens do checklist do protocolo ficam pendentes; você resolve no Acompanhamento.</p>
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {draft.extras.map((t, i) => (
            <li key={i} style={{ display: "flex", gap: "0.5rem", alignItems: "center", padding: "0.2rem 0" }}>
              <span style={{ flex: 1 }}>{t}</span>
              <button type="button" className="btn-ghost" aria-label={`Tirar “${t}”`} onClick={() => set({ extras: draft.extras.filter((_, j) => j !== i) })}><X size={14} /></button>
            </li>
          ))}
        </ul>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input style={inputStyle} aria-label="Novo item do checklist" placeholder="ex.: separar os animais no curral" value={novo} onChange={(e) => setNovo(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter" && novo.trim()) { e.preventDefault(); set({ extras: [...draft.extras, novo.trim()] }); setNovo(""); } }} />
          <button type="button" className="btn-secondary" disabled={!novo.trim()} onClick={() => { set({ extras: [...draft.extras, novo.trim()] }); setNovo(""); }}><Plus size={14} /> Adicionar</button>
        </div>
      </div>
    </div>
  );
}

// ─────────────── itens já existentes (aba Checklist do agendamento) ───────────────
export function ChecklistItensExistentes({ itens, onAcao, ocupado, veterinario, veterinarios, onConfirmarVet }: {
  itens: ItemChecklistAg[]; ocupado?: boolean;
  onAcao: (item: ItemChecklistAg, acao: "cumprir" | "pular" | "reabrir", motivo?: string) => void;
  /** Veterinário já confirmado (Pessoa/CRMV, quem e quando) e como confirmar pelo próprio item. */
  veterinario?: VeterinarioChecklist | null; veterinarios?: PessoaVet[];
  onConfirmarVet?: (v: { pessoaId: number; quando: string | null; nota: string | null }) => void;
}) {
  const [pulando, setPulando] = useState<number | null>(null);
  const [motivo, setMotivo] = useState("");
  const [confirmandoVet, setConfirmandoVet] = useState(false);
  const [vetId, setVetId] = useState("");
  const [vetQuando, setVetQuando] = useState("");
  const [vetNota, setVetNota] = useState("");
  const visiveis = itens.filter((i) => i.chave !== "compra" && i.chave !== "financeiro");   // vivem no bloco Financeiro
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {visiveis.map((i) => (
        <li key={i.id} style={{ padding: "0.55rem 0", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ color: i.status === "cumprido" ? "var(--green-light)" : i.status === "pulado" ? "var(--text-muted)" : "var(--amber)", display: "inline-flex" }}>
              {i.status === "cumprido" ? <Check size={16} /> : i.status === "pulado" ? <SkipForward size={16} /> : <AlertTriangle size={16} />}
            </span>
            <span style={{ flex: 1, minWidth: 0 }}>
              <b style={{ fontSize: "0.88rem" }}>{i.nome}</b>
              <span style={{ ...notaStyle, display: "block" }}>
                {i.status === "cumprido" ? "Resolvido" : i.status === "pulado" ? `Desconsiderado${i.observacao ? `: ${i.observacao}` : ""}` : "Pendente"}
                {i.chave === "horario" && i.resposta ? ` · ${i.resposta}` : ""}
              </span>
              {i.chave === "vet" && veterinario?.estado === "confirmado" && (
                <span style={{ ...notaStyle, display: "block", color: "var(--text)" }}>
                  Confirmado com <b>{veterinario.nome || "veterinário"}</b>{veterinario.crmv ? ` (${veterinario.crmv})` : ""} em {dataHoraCurta(veterinario.confirmado_em)}
                  {veterinario.registrado_por ? ` · registrado por ${veterinario.registrado_por}` : ""}{veterinario.observacao ? ` · ${veterinario.observacao}` : ""}
                </span>
              )}
            </span>
            {i.chave === "vet" && onConfirmarVet && i.status !== "pulado" && (
              <button type="button" className={i.status === "pendente" ? "btn-primary" : "btn-ghost"} disabled={ocupado} onClick={() => { setConfirmandoVet(true); setVetQuando(agoraLocal()); }}>
                <Check size={14} /> {veterinario?.estado === "confirmado" ? "Confirmar de novo" : "Confirmar com o veterinário"}
              </button>
            )}
            {i.status === "pendente" ? (
              <>
                {!(i.chave === "vet" && onConfirmarVet) && <button type="button" className="btn-secondary" disabled={ocupado} onClick={() => onAcao(i, "cumprir")}><Check size={14} /> Resolver</button>}
                <button type="button" className="btn-ghost" disabled={ocupado} onClick={() => { setPulando(i.id); setMotivo(""); }}><SkipForward size={14} /> Desconsiderar…</button>
              </>
            ) : (
              <button type="button" className="btn-ghost" disabled={ocupado} onClick={() => onAcao(i, "reabrir")}><RotateCcw size={14} /> Reabrir</button>
            )}
          </div>
          {i.chave === "vet" && confirmandoVet && onConfirmarVet && (
            <div className="card" style={{ marginTop: "0.5rem", padding: "0.6rem 0.8rem", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label htmlFor="ckx-vet" style={labelStyle}>Confirmado com</label>
                  <select id="ckx-vet" style={inputStyle} value={vetId} onChange={(e) => setVetId(e.target.value)}>
                    <option value="">Escolha o veterinário</option>
                    {(veterinarios || []).map((v) => <option key={v.id} value={v.id}>{v.nome}{v.crmv ? ` (${v.crmv})` : ""}</option>)}
                  </select>
                </div>
                <div>
                  <label htmlFor="ckx-q" style={labelStyle}>Confirmado em</label>
                  <input id="ckx-q" type="datetime-local" style={inputStyle} value={vetQuando} max={agoraLocal()} onChange={(e) => setVetQuando(e.target.value)} />
                </div>
              </div>
              <div><label htmlFor="ckx-n" style={labelStyle}>Como confirmou (opcional)</label><input id="ckx-n" style={inputStyle} value={vetNota} onChange={(e) => setVetNota(e.target.value)} placeholder="ex.: por telefone" /></div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button type="button" className="btn-primary" disabled={!vetId || ocupado} onClick={() => { onConfirmarVet({ pessoaId: Number(vetId), quando: vetQuando ? localParaUtcIso(vetQuando) : null, nota: vetNota.trim() || null }); setConfirmandoVet(false); }}>Confirmar</button>
                <button type="button" className="btn-ghost" onClick={() => setConfirmandoVet(false)}>Voltar</button>
              </div>
            </div>
          )}
          {pulando === i.id && (
            <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
              <input style={{ ...inputStyle, flex: "1 1 220px", width: "auto" }} aria-label={`Motivo para desconsiderar ${i.nome}`} placeholder="Motivo (obrigatório)" value={motivo} onChange={(e) => setMotivo(e.target.value)} />
              <button type="button" className="btn-primary" disabled={!motivo.trim() || ocupado} onClick={() => { onAcao(i, "pular", motivo.trim()); setPulando(null); }}>Desconsiderar</button>
              <button type="button" className="btn-ghost" onClick={() => setPulando(null)}>Voltar</button>
            </div>
          )}
        </li>
      ))}
      {!visiveis.length && <li style={notaStyle}>Este agendamento não tem outros itens no checklist.</li>}
    </ul>
  );
}
