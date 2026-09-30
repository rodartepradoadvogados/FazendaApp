"use client";
import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check } from "lucide-react";
import {
  fetchRepasseConfig, salvarRepasseConfig, fetchRepasseProdutos, classificarProdutoRepasse, formatDate, today,
  type RepasseConfig,
} from "@/lib/api";
import { Campo, inputStyle, nota } from "@/components/lancamentos/comumForms";

type Produtos = Awaited<ReturnType<typeof fetchRepasseProdutos>>;
type Form = {
  usar: boolean; estoque_id: string; dias_apos_servico: string; repetir: boolean; repetir_cada_dias: string;
  repeticoes: string; mostrar_na_agenda: boolean; quem_entra: "todas" | "iatf" | "monta_natural";
};

const OPCOES_QUEM = [
  { valor: "todas", rotulo: "Todas as inseminações e montas" },
  { valor: "iatf", rotulo: "Só IATF" },
  { valor: "monta_natural", rotulo: "Só monta natural" },
];

const paraForm = (c: RepasseConfig): Form => ({
  usar: c.usar, estoque_id: c.estoque_id ? String(c.estoque_id) : "", dias_apos_servico: String(c.dias_apos_servico),
  repetir: c.repetir, repetir_cada_dias: String(c.repetir_cada_dias), repeticoes: String(c.repeticoes),
  mostrar_na_agenda: c.mostrar_na_agenda, quem_entra: c.quem_entra,
});

function Sim_Nao({ valor, onChange, rotulo }: { valor: boolean; onChange: (v: boolean) => void; rotulo: string }) {
  return (
    <div className="ag2-chips" role="radiogroup" aria-label={rotulo}>
      <button type="button" role="radio" aria-checked={valor} className="ag2-chip" onClick={() => onChange(true)}>Sim</button>
      <button type="button" role="radio" aria-checked={!valor} className="ag2-chip" onClick={() => onChange(false)}>Não</button>
    </div>
  );
}

/**
 * Cartão "Detecção de cio de repasse" (Protocolos > Cadastro > Sanitário >
 * Preventivo). Regra POR FAZENDA, gravada de verdade: usar ou não, produto da
 * categoria de produto "Detecção de cio de repasse", 1ª checagem (dias após o
 * serviço), repetição (ciclo estral: 18 a 24 dias sugerido), indicação no Dia a
 * dia da Agenda e quem entra (todas, só IATF, só monta natural). A projeção
 * (checagens × vacas) aparece no Painel da Agenda.
 */
export function CartaoRepasse() {
  const [cfg, setCfg] = useState<RepasseConfig | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [produtos, setProdutos] = useState<Produtos | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const [avisos, setAvisos] = useState<string[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [classificar, setClassificar] = useState("");
  const [classificando, setClassificando] = useState(false);

  const carregar = async () => {
    try {
      const [c, p] = await Promise.all([fetchRepasseConfig(), fetchRepasseProdutos()]);
      setCfg(c); setProdutos(p); setForm((atual) => atual ?? paraForm(c)); setErro(null);
    } catch (e: any) { setErro(e?.message || "Não foi possível carregar a configuração do repasse."); }
  };
  useEffect(() => { carregar(); }, []);

  const dias = Number(form?.dias_apos_servico) || 14;
  const cada = Number(form?.repetir_cada_dias) || 21;
  const reps = Number(form?.repeticoes) || 1;
  const exemplo = useMemo(() => {
    if (!form) return [] as string[];
    const base = new Date(today() + "T00:00:00");
    const somar = (n: number) => { const d = new Date(base); d.setDate(d.getDate() + n); return formatDate(d.toISOString().slice(0, 10)); };
    const datas = [somar(dias)];
    if (form.repetir) for (let k = 1; k <= Math.min(reps, 4); k++) datas.push(somar(dias + k * cada));
    return datas;
  }, [form, dias, cada, reps]);

  if (erro && !cfg) {
    return (
      <div className="card mt-3" role="alert">
        <p style={{ color: "var(--alert-fg)" }}>{erro}</p>
        <button type="button" className="btn-secondary" style={{ marginTop: "0.5rem" }} onClick={carregar}>Tentar de novo</button>
      </div>
    );
  }
  if (!cfg || !form || !produtos) return <div className="card mt-3"><p className="ag2-mudo" role="status">Carregando a configuração do repasse…</p></div>;

  const set = <K extends keyof Form>(k: K, v: Form[K]) => { setForm({ ...form, [k]: v }); setSucesso(null); };
  const desligado = !form.usar;
  const sel = (rot: string, ativo: boolean, onClick: () => void) => (
    <button key={rot} type="button" role="radio" aria-checked={ativo} className="ag2-chip" onClick={onClick}>{rot}</button>
  );

  async function classificarItem() {
    if (!classificar) return;
    setClassificando(true); setErro(null);
    try {
      await classificarProdutoRepasse(Number(classificar));
      setClassificar("");
      setForm((f) => (f ? { ...f, estoque_id: String(Number(classificar)) } : f));
      await carregar();
    } catch (e: any) { setErro(e?.message || "Erro ao classificar o produto."); }
    finally { setClassificando(false); }
  }

  async function salvar() {
    if (salvando) return;
    setSalvando(true); setErro(null); setSucesso(null);
    try {
      const salvo = await salvarRepasseConfig({
        usar: form!.usar, estoque_id: form!.estoque_id ? Number(form!.estoque_id) : null,
        dias_apos_servico: Number(form!.dias_apos_servico), repetir: form!.repetir,
        repetir_cada_dias: Number(form!.repetir_cada_dias), repeticoes: Number(form!.repeticoes),
        mostrar_na_agenda: form!.mostrar_na_agenda, quem_entra: form!.quem_entra,
      });
      setCfg((antes) => ({ ...antes, ...salvo, quem_entra_opcoes: antes?.quem_entra_opcoes, ciclo_sugerido: antes?.ciclo_sugerido })); setForm(paraForm(salvo)); setAvisos(salvo.avisos || []);
      await carregar();
      setSucesso("Configuração salva. A Agenda já usa esta regra.");
    } catch (e: any) { setErro(e?.message || "Erro ao salvar a configuração."); }
    finally { setSalvando(false); }
  }

  return (
    <div className="card mt-3 ag2-form" aria-label="Detecção de cio de repasse">
      <div className="card-header mb-2" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", flexWrap: "wrap" }}>
        <span>Detecção de cio de repasse</span>
        <span style={{ fontSize: "0.75rem", fontWeight: 700, padding: "0.15rem 0.6rem", borderRadius: 999, border: "1px solid var(--border-strong)", color: "var(--text-muted)" }}>
          {cfg.configurado ? (cfg.usar ? "Ligada" : "Desligada") : "Padrão (ainda não configurada)"}
        </span>
      </div>
      <p style={{ ...nota, marginLeft: 0, marginBottom: "0.75rem" }}>
        Uma regra por fazenda: checa o retorno ao cio depois da inseminação ou monta. Sem configurar, vale o padrão de sempre
        (ligada, 14 dias, todas, com aviso na Agenda).
      </p>

      <div style={{ display: "grid", gap: "0.9rem", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
        <Campo label="Usar detecção de cio de repasse?"><Sim_Nao rotulo="Usar detecção de cio de repasse" valor={form.usar} onChange={(v) => set("usar", v)} /></Campo>

        <fieldset disabled={desligado} style={{ border: 0, padding: 0, margin: 0, display: "contents" }} aria-disabled={desligado}>
          <Campo label={`Produto vinculado (categoria "${produtos.categoria}")`}>
            <select style={inputStyle} value={form.estoque_id} onChange={(e) => set("estoque_id", e.target.value)}>
              <option value="">Sem produto vinculado</option>
              {produtos.produtos.map((p) => <option key={p.id} value={p.id}>{p.nome}{p.quantidade != null ? ` — saldo ${p.quantidade} ${p.unidade || ""}` : ""}</option>)}
            </select>
            {produtos.produtos.length === 0 && (
              <span style={{ ...nota, display: "block", marginTop: "0.3rem", marginLeft: 0 }}>
                Nenhum item de estoque está nesta categoria ainda. Classifique um abaixo ou cadastre o produto em Estoque.
              </span>
            )}
          </Campo>

          <Campo label="Classificar um item de estoque nesta categoria">
            <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
              <select style={{ ...inputStyle, flex: 1, minWidth: 160 }} value={classificar} onChange={(e) => setClassificar(e.target.value)} aria-label="Item de estoque a classificar">
                <option value="">Escolha o item…</option>
                {produtos.outros_itens.map((i) => <option key={i.id} value={i.id}>{i.nome}{i.categoria ? ` (${i.categoria})` : ""}</option>)}
              </select>
              <button type="button" className="btn-secondary" disabled={!classificar || classificando} onClick={classificarItem}>{classificando ? "Classificando…" : "Classificar"}</button>
            </div>
          </Campo>

          <Campo label="1ª checagem: dias depois da inseminação ou monta">
            <input type="number" min={1} max={60} inputMode="numeric" style={inputStyle} value={form.dias_apos_servico} onChange={(e) => set("dias_apos_servico", e.target.value)} />
            <span style={{ ...nota, display: "block", marginTop: "0.25rem", marginLeft: 0 }}>Padrão 14 dias. Vale de 1 a 60.</span>
          </Campo>

          <Campo label="Repetir a checagem?">
            <Sim_Nao rotulo="Repetir a checagem" valor={form.repetir} onChange={(v) => set("repetir", v)} />
          </Campo>

          {form.repetir && (
            <Campo label="Repetir a cada (dias) e quantas vezes">
              <div className="ag2-chips" role="radiogroup" aria-label="Intervalo sugerido do ciclo estral" style={{ marginBottom: "0.4rem" }}>
                {[18, 21, 24].map((n) => sel(`${n} dias`, Number(form.repetir_cada_dias) === n, () => set("repetir_cada_dias", String(n))))}
              </div>
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
                <input type="number" min={7} max={45} inputMode="numeric" style={{ ...inputStyle, width: "6rem" }} value={form.repetir_cada_dias} onChange={(e) => set("repetir_cada_dias", e.target.value)} aria-label="Repetir a cada quantos dias" />
                <span>dias, por</span>
                <input type="number" min={1} max={4} inputMode="numeric" style={{ ...inputStyle, width: "5rem" }} value={form.repeticoes} onChange={(e) => set("repeticoes", e.target.value)} aria-label="Quantidade de repetições" />
                <span>{reps === 1 ? "vez" : "vezes"}</span>
              </div>
              <span style={{ ...nota, display: "block", marginTop: "0.25rem", marginLeft: 0 }}>O ciclo estral costuma ser de {cfg.ciclo_sugerido?.[0] ?? 18} a {cfg.ciclo_sugerido?.[1] ?? 24} dias.</span>
            </Campo>
          )}

          <Campo label="Aparece como tarefa na Agenda (Dia a dia)?">
            <Sim_Nao rotulo="Aparece na Agenda" valor={form.mostrar_na_agenda} onChange={(v) => set("mostrar_na_agenda", v)} />
            <span style={{ ...nota, display: "block", marginTop: "0.25rem", marginLeft: 0 }}>Se não, a projeção continua no Painel da Agenda.</span>
          </Campo>

          <Campo label="Quem entra">
            <div className="ag2-chips" role="radiogroup" aria-label="Quem entra na detecção de repasse">
              {(cfg.quem_entra_opcoes?.length ? cfg.quem_entra_opcoes : OPCOES_QUEM).map((o) => sel(o.rotulo, form.quem_entra === o.valor, () => set("quem_entra", o.valor as Form["quem_entra"])))}
            </div>
          </Campo>
        </fieldset>
      </div>

      {form.usar && (
        <p style={{ ...nota, marginLeft: 0, marginTop: "0.9rem", fontSize: "0.8rem" }}>
          Exemplo: inseminação hoje → {exemplo.length === 1 ? "checagem em" : "checagens em"} <strong>{exemplo.join(", ")}</strong>.
        </p>
      )}

      {erro && <p role="alert" style={{ color: "var(--alert-fg)", marginTop: "0.6rem", display: "flex", gap: "0.4rem", alignItems: "center" }}><AlertTriangle size={15} aria-hidden="true" /> {erro}</p>}
      {sucesso && <p role="status" style={{ color: "var(--green-light)", marginTop: "0.6rem", display: "flex", gap: "0.4rem", alignItems: "center" }}><Check size={15} aria-hidden="true" /> {sucesso}</p>}
      {avisos.length > 0 && <ul style={{ marginTop: "0.4rem", color: "var(--amber)", fontSize: "0.8rem" }}>{avisos.map((a) => <li key={a}>{a}</li>)}</ul>}

      <div style={{ marginTop: "0.9rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <button type="button" className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar configuração"}</button>
        <a className="btn-ghost" href="/agenda?visao=painel">Ver no Painel da Agenda</a>
      </div>
    </div>
  );
}
