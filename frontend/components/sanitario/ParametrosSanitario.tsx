"use client";
// Configurações › Parâmetros › Sanitário (§7): regras gerais do módulo de
// vacinas e exames. O que é de cada vacina (mínimo, antecedência, janela) fica
// no cadastro dela. GET/PUT /sanitario/parametros (só administrador salva).
import { useState } from "react";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { useToast } from "@/components/Toast";
import { listarCaixas, mensagemDoErro, obterParametros, salvarParametros } from "@/lib/apiSanitario";
import { FUSO, fmtDataHora, type Parametros } from "@/lib/sanitarioTipos";
import { linkCentral } from "@/lib/protocolosNavegacao";
import { Faixa, useCarregar, useEuSanitario } from "./comum";

const UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"];

export default function ParametrosSanitario() {
  const toast = useToast();
  const { admin } = useEuSanitario();
  const { dados, erro, recarregar } = useCarregar(() => obterParametros(), []);
  const obrig = useCarregar(() => listarCaixas("todas"), []);
  const [editado, setP] = useState<Parametros | null>(null);
  const p = editado ?? dados;
  const [salvando, setSalvando] = useState(false);
  const [erroSalvar, setErroSalvar] = useState<string | null>(null);
  const set = (x: Partial<Parametros>) => setP((v) => { const base = v ?? dados; return base ? { ...base, ...x } : base; });
  const obrigatorias = (obrig.dados || []).filter((c) => c.obrigatoria && c.estado !== "arquivada");

  async function salvar() {
    if (!p) return;
    setSalvando(true); setErroSalvar(null);
    try { const r = await salvarParametros(p); setP(r); toast("Parâmetros do sanitário salvos. Valem daqui para frente."); }
    catch (e) { setErroSalvar(mensagemDoErro(e)); } finally { setSalvando(false); }
  }

  return (
    <section className="san-bloco" aria-labelledby="parSanTit">
      <div className="san-bloco-cab">
        <h3 id="parSanTit"><ShieldCheck size={13} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 6 }} />Sanitário · vacinas e exames</h3>
        {p?.atualizado_em && <span className="san-nota">salvo em {fmtDataHora(p.atualizado_em)}</span>}
      </div>
      <div className="san-bloco-corpo" style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
        <p className="san-nota" style={{ margin: 0 }}>Regras gerais do módulo. O que é de cada vacina (mínimo, antecedência, janela) fica no cadastro dela.</p>
        {erro ? <Faixa tipo="alerta">{erro} <button type="button" className="san-link" onClick={recarregar}>Tentar de novo</button></Faixa> : !p ? (
          <div className="skeleton" style={{ height: "10rem" }} role="status" aria-label="Carregando os parâmetros do sanitário" />
        ) : (<>
          <fieldset disabled={!admin} style={{ border: 0, padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.8rem" }}>
            <div className="san-linha">
              <div className="san-campo curto"><label htmlFor="psUf">UF da fazenda</label>
                <select id="psUf" className="san-input" value={p.uf || ""} onChange={(e) => set({ uf: e.target.value || null })}>
                  <option value="">—</option>{UFS.map((u) => <option key={u} value={u}>{u}</option>)}
                </select></div>
              <div className="san-campo medio"><label htmlFor="psAnt">Antecedência padrão dos avisos (dias)</label>
                <input id="psAnt" className="san-input" type="number" min={0} value={p.antecedencia_padrao_dias} onChange={(e) => set({ antecedencia_padrao_dias: Number(e.target.value) || 0 })} /></div>
              <div className="san-campo medio"><label htmlFor="psOff">Aviso de celular sem enviar (horas)</label>
                <input id="psOff" className="san-input" type="number" min={1} value={p.aviso_offline_horas} onChange={(e) => set({ aviso_offline_horas: Math.max(1, Number(e.target.value) || 1) })} /></div>
            </div>
            <label className="san-liga">
              <input type="checkbox" checked={p.prazos_legais_ativo} onChange={(e) => set({ prazos_legais_ativo: e.target.checked })} />
              <span><b>Controle de prazos legais</b><small>Com UF definida, o atestado e a comprovação de cada vacina viram prazos no Painel de Sanidade.</small></span>
            </label>
            <div className="san-linha">
              <div className="san-campo medio"><label htmlFor="psExt">Dose externa sem data</label>
                <select id="psExt" className="san-input" value={p.dose_externa_sem_data} onChange={(e) => set({ dose_externa_sem_data: e.target.value as Parametros["dose_externa_sem_data"] })}>
                  <option value="contar">Contar como recebida</option><option value="nao_contar">Não contar</option>
                </select></div>
              <div className="san-campo"><label htmlFor="psPeso">Animal sem peso (dose por peso)</label>
                <select id="psPeso" className="san-input" value={p.peso_estimado} onChange={(e) => set({ peso_estimado: e.target.value as Parametros["peso_estimado"] })}>
                  <option value="aceitar">Usar o peso médio da categoria, marcado “estimado”</option><option value="exigir">Pedir o peso no curral</option>
                </select></div>
              <div className="san-campo medio"><label htmlFor="psTb">Modo da tuberculina</label>
                <select id="psTb" className="san-input" value={p.modo_tuberculina} onChange={(e) => set({ modo_tuberculina: e.target.value as Parametros["modo_tuberculina"] })}>
                  <option value="so_resultado">Só resultado</option><option value="diferenca">Diferença</option><option value="medidas">Medidas completas</option>
                </select></div>
            </div>
          </fieldset>
          <div className="san-params">
            <span>Prazo para corrigir uma aplicação: <b>até fechar o dia</b></span>
            <span>Fuso do módulo: <b>{FUSO}</b></span>
            <span>Obrigatórias (entram na cobertura): <b>{obrigatorias.length ? obrigatorias.map((c) => c.nome_curto || c.nome).join(", ") : "nenhuma"}</b></span>
            <Link href={linkCentral.cadastroPreventivo({}, "vacina")} className="san-link">Marcar no cadastro de cada vacina</Link>
          </div>
          {!admin && <p className="san-nota" style={{ margin: 0 }}>Só administradores podem editar.</p>}
          {erroSalvar && <p className="san-erro-txt" role="alert" style={{ margin: 0 }}>{erroSalvar}</p>}
          {admin && (
            <div className="san-acoes fim">
              <span className="san-nota" style={{ marginRight: "auto" }}>Mudanças valem daqui para frente.</span>
              <button type="button" className="btn-primary-gold" disabled={salvando} onClick={salvar}>{salvando ? "Salvando…" : "Salvar parâmetros"}</button>
            </div>
          )}
        </>)}
      </div>
    </section>
  );
}
