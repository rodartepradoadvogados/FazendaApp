"use client";
// Lançamentos › Preventivo — lançamento simples ou retroativo, "à moda antiga"
// (§6): o quê (vacina/exame cadastrado ou "outro" em texto livre — "outro" só
// registra, nunca cria cadastro), quando (data no passado = retroativo, motivo
// pulável), em quem (pop-up de seleção), produto opcional e as perguntas-base
// (quem aplicou, atestado, carência, resultado por animal). Grava no MESMO
// histórico da Central (POST /sanitario/lancamento-simples). Também: lançar a
// partir da ficha vazia e importar planilha (entra como "só registro").
import { useMemo, useState } from "react";
import { Download, Printer, Search, Upload, X } from "lucide-react";
import { useToast } from "@/components/Toast";
import {
  importarPlanilha, lancamentoSimples, listarCaixas, listarVeterinarios, mensagemDoErro, modeloPlanilha, simularDia,
} from "@/lib/apiSanitario";
import {
  DOSE_UNIDADES, MODOS_LEITE, RESULTADOS, ROTULO_MODO_LEITE, ROTULO_RESULTADO, ROTULO_UNIDADE, fmtData, hojeISO, intOuNulo, novaChave,
  numOuNulo, type CarenciaDecisaoIn, type ConsentimentoIn, type ImportacaoPlanilha, type ItemRegistro, type LancamentoSimplesIn,
  type ModoLeite, type ProdutoIn, type Resultado, type ResultadoRegistro,
} from "@/lib/sanitarioTipos";
import { BarraDesfazer, CampoPessoa, Faixa, Seg, carregarEstoqueSan, useCarregar, useEuSanitario, type PessoaEscolhida } from "./comum";
import { SeletorAnimais, type AnimalSan } from "./SeletorAnimais";
import { elegibilidadeDaSimulacao } from "./dias/ModalMarcarDia";
import { ModalConsentimento } from "./ModalConsentimento";
import { ModalCarencia } from "./ModalCarencia";
import { ModalFicha } from "./FichaCampo";

type ModoProduto = "padrao" | "estoque" | "sem_estoque" | "nenhum";
type Form = {
  oque: string; outro: string; data: string; motivo: string; animais: AnimalSan[]; numeros: string;
  modoProduto: ModoProduto; estoqueId: string; produtoTexto: string; dose: string; unidade: string; xkg: string;
  aplicador: PessoaEscolhida; vet: string; vetTxt: string; crmv: string;
  atestado: "nao" | "sim"; atNum: string; atDest: string;
  car: "nao" | "sim" | "naosei"; carL: string; carC: string; carModo: ModoLeite | "";
  res: Record<number, Resultado>; ficha: boolean;
};
const novo = (): Form => ({
  oque: "", outro: "", data: hojeISO(), motivo: "", animais: [], numeros: "", modoProduto: "padrao", estoqueId: "", produtoTexto: "",
  dose: "", unidade: "mL", xkg: "", aplicador: { pessoa_id: null, texto: "" }, vet: "", vetTxt: "", crmv: "",
  atestado: "nao", atNum: "", atDest: "", car: "naosei", carL: "", carC: "", carModo: "", res: {}, ficha: false,
});

function baixarCsv(nome: string, linhas: string[][]) {
  const csv = "﻿" + linhas.map((l) => l.map((c) => (/[;"\n]/.test(c) ? `"${c.replace(/"/g, '""')}"` : c)).join(";")).join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url; a.download = nome; document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

function ImportarPlanilha() {
  const toast = useToast();
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [res, setRes] = useState<ImportacaoPlanilha | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  async function modelo() {
    try {
      const m = await modeloPlanilha();
      baixarCsv("modelo_vacinas_exames.csv", [m.colunas, m.exemplo]);
    } catch (e) { toast(mensagemDoErro(e, "Não foi possível baixar o modelo."), "erro"); }
  }
  return (
    <section className="san-bloco">
      <div className="san-bloco-cab"><h3>Importar planilha</h3>
        <button type="button" className="btn-ghost san-btn-sm" onClick={modelo}><Download size={12} aria-hidden="true" style={{ verticalAlign: "-1px", marginRight: 4 }} />Baixar modelo</button></div>
      <div className="san-bloco-corpo" style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
        <p className="san-nota" style={{ margin: 0 }}>Entra como <b>só registro</b>: aparece no histórico, não conta para cobertura nem tira o animal da caixa. Nada lançado no CowData é apagado. Colunas: brinco, data, vacina/exame, dose, unidade, aplicador, resultado, obs.</p>
        <div className="san-linha">
          <div className="san-campo">
            <label htmlFor="lPlan">Arquivo (.xlsx ou .csv)</label>
            <input id="lPlan" className="san-input" type="file" accept=".xlsx,.xls,.csv" onChange={(e) => { setArquivo(e.target.files?.[0] || null); setRes(null); setErro(null); }} />
          </div>
          <button type="button" className="btn-primary-gold" disabled={!arquivo || enviando} onClick={async () => {
            if (!arquivo) return;
            setEnviando(true); setErro(null);
            try { const r = await importarPlanilha(arquivo); setRes(r); toast(`${r.gravados} ${r.gravados === 1 ? "linha importada" : "linhas importadas"}.`); }
            catch (e) { setErro(mensagemDoErro(e)); } finally { setEnviando(false); }
          }}><Upload size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />{enviando ? "Importando…" : "Importar"}</button>
        </div>
        {erro && <Faixa tipo="alerta">{erro}</Faixa>}
        {res && (
          <Faixa tipo={res.erros_planilha.length || res.erros ? "atencao" : "ok"}>
            {res.linhas} linhas lidas · <b>{res.gravados}</b> gravadas · {res.duplicados} já existiam{res.erros ? ` · ${res.erros} com erro` : ""}.
            {res.erros_planilha.length > 0 && <ul>{res.erros_planilha.slice(0, 12).map((x) => <li key={x}>{x}</li>)}</ul>}
          </Faixa>
        )}
      </div>
    </section>
  );
}

export function LancamentoSimples() {
  const toast = useToast();
  const { admin } = useEuSanitario();
  const [f, setF] = useState<Form>(novo);
  const [chaveLote, setChaveLote] = useState(() => novaChave("lanc"));
  const [seletor, setSeletor] = useState(false);
  const [ficha, setFicha] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [avisos, setAvisos] = useState<string[]>([]);
  const [desfazer, setDesfazer] = useState<{ ids: number[]; ate: string | null; texto: string } | null>(null);
  const [consent, setConsent] = useState<ItemRegistro[] | null>(null);
  const [carencia, setCarencia] = useState<ItemRegistro | null>(null);
  const [consentimentos, setConsentimentos] = useState<ConsentimentoIn[]>([]);
  const caixas = useCarregar(() => listarCaixas(), []);
  const estoque = useCarregar(() => carregarEstoqueSan(), []);
  const vets = useCarregar(() => listarVeterinarios(), []);
  const hoje = hojeISO();
  const cx = useMemo(() => (caixas.dados || []).find((c) => String(c.id) === f.oque) || null, [caixas.dados, f.oque]);
  const exame = cx?.tipo === "exame";
  const retro = f.data < hoje;
  const set = (p: Partial<Form>) => setF((x) => ({ ...x, ...p }));

  function montar(car?: CarenciaDecisaoIn | null, cons: ConsentimentoIn[] = consentimentos, animais: AnimalSan[] = f.animais): LancamentoSimplesIn {
    let produto: ProdutoIn | null = null;
    if (!exame && f.modoProduto !== "padrao") {
      const dose = { dose_valor: numOuNulo(f.dose), dose_unidade: (f.unidade || null) as ProdutoIn["dose_unidade"], dose_x_kg: f.unidade === "mL_por_x_kg" ? numOuNulo(f.xkg) : null };
      produto = f.modoProduto === "estoque" ? { modo: "estoque", estoque_id: intOuNulo(f.estoqueId), ...dose }
        : f.modoProduto === "sem_estoque" ? { modo: "sem_estoque", texto: f.produtoTexto, ...dose } : { modo: "nao_se_aplica" };
    }
    const carencia: CarenciaDecisaoIn | null = car !== undefined ? car : exame ? null
      : f.car === "nao" ? { modo: null, leite_dias: 0, carne_dias: 0 }
        : f.car === "sim" ? { modo: admin && f.carModo ? f.carModo : null, leite_dias: intOuNulo(f.carL), carne_dias: intOuNulo(f.carC) } : null;
    const vetPessoa = f.vet && f.vet !== "__txt" ? Number(f.vet) : null;
    return {
      caixa_id: cx ? cx.id : null, outro_texto: f.oque === "outro" ? f.outro : null, data: f.data,
      retroativo_motivo: retro ? f.motivo : null, origem: f.ficha ? "ficha" : "lancamento_simples",
      animal_ids: animais.map((a) => a.id), numeros: f.numeros.split(/[,;\s]+/).filter(Boolean), produto,
      aplicador_pessoa_id: f.aplicador.pessoa_id, aplicador_texto: f.aplicador.texto || null,
      veterinario_pessoa_id: vetPessoa, veterinario_texto: f.vet === "__txt" ? f.vetTxt : null, crmv_texto: f.vet === "__txt" ? f.crmv : null,
      atestado: f.atestado === "sim" ? { numero: f.atNum, destinatario: f.atDest } : null, carencia,
      resultados: exame ? Object.fromEntries(Object.entries(f.res)) as Record<number, Resultado> : {},
      consentimentos: cons, chave_lote: chaveLote,
    };
  }

  async function gravar(car?: CarenciaDecisaoIn | null, cons?: ConsentimentoIn[], animais: AnimalSan[] = f.animais) {
    setErro(null);
    if (!f.oque) { setErro("Escolha a vacina ou exame, ou “Outro”."); return; }
    if (f.oque === "outro" && !f.outro.trim()) { setErro("Escreva o que foi feito."); return; }
    if (!animais.length && !f.numeros.trim()) { setErro("Escolha ao menos um animal."); return; }
    if (f.data > hoje) { setErro("A data não pode ser no futuro. Para marcar um dia, use a Central de Protocolos."); return; }
    setSalvando(true);
    try {
      const r: ResultadoRegistro = await lancamentoSimples(montar(car, cons, animais));
      const textos = new Set<string>();
      r.itens.forEach((i) => i.avisos.forEach((a) => { if (!["fora_da_regra", "carencia_decisao"].includes(a.codigo)) textos.add(a.texto); }));
      setAvisos([...textos]);
      if (r.registro_ids.length) setDesfazer({ ids: r.registro_ids, ate: r.desfazer_ate, texto: `${r.gravados} ${r.gravados > 1 ? "registros gravados" : "registro gravado"} no histórico` });
      const pendCar = r.itens.find((i) => i.status === "pendente" && i.requer.includes("carencia_decisao"));
      const pendCons = r.itens.filter((i) => i.status === "pendente" && i.requer.includes("consentimento"));
      if (pendCar) { setCarencia(pendCar); return; }
      if (pendCons.length) { setConsent(pendCons); return; }
      if (r.erros) setErro(`${r.erros} ${r.erros > 1 ? "animais não foram gravados" : "animal não foi gravado"}: ${r.itens.filter((i) => i.status === "erro").map((i) => `${i.numero || "?"} (${i.avisos.map((a) => a.texto).join("; ")})`).join(", ")}.`);
      if (!r.pendentes) {
        if (!r.gravados && r.duplicados) toast("Nada novo: já estava no histórico.");
        else toast(`${r.gravados} ${r.gravados > 1 ? "registros gravados" : "registro gravado"}.`);
        setF((x) => ({ ...novo(), oque: x.oque, data: x.data, modoProduto: x.modoProduto, estoqueId: x.estoqueId, dose: x.dose, unidade: x.unidade }));
        setConsentimentos([]); setChaveLote(novaChave("lanc"));
      }
    } catch (e) {
      setErro(mensagemDoErro(e, "Não foi possível gravar."));
    } finally { setSalvando(false); }
  }

  const listaCaixas = (caixas.dados || []).filter((c) => c.estado !== "arquivada");
  return (
    <div className="san-pagina" style={{ maxWidth: 940 }}>
      <div className="san-cab">
        <div>
          <h2>Lançamentos › Preventivo</h2>
          <p>Lançamento simples ou retroativo, à moda antiga: diga o que foi feito, em quem e quando. Grava no mesmo histórico da Central.</p>
        </div>
        <button type="button" className="btn-ghost" disabled={!cx} title={cx ? undefined : "Escolha a vacina ou exame primeiro"} onClick={() => setFicha(true)}>
          <Printer size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />Imprimir ficha vazia
        </button>
      </div>
      {caixas.erro && <Faixa tipo="alerta">{caixas.erro}</Faixa>}
      <section className="san-bloco">
        <div className="san-bloco-cab"><h3>O quê</h3></div>
        <div className="san-bloco-corpo san-linha">
          <div className="san-campo" style={{ flex: "2 1 260px" }}>
            <label htmlFor="lOque">Vacina ou exame</label>
            <select id="lOque" className="san-input" value={f.oque} onChange={(e) => set({ oque: e.target.value, res: {} })}>
              <option value="">Escolha…</option>
              {listaCaixas.map((c) => <option key={c.id} value={c.id}>{c.nome}{c.estado === "ativa" ? "" : " (inativa)"}</option>)}
              <option value="outro">Outro (escrever)</option>
            </select>
          </div>
          {f.oque === "outro" && (
            <div className="san-campo" style={{ flex: "2 1 240px" }}>
              <label htmlFor="lOutro">O que foi feito</label>
              <input id="lOutro" className="san-input" value={f.outro} onChange={(e) => set({ outro: e.target.value })} placeholder="ex.: vacina contra carbúnculo" />
            </div>
          )}
          {f.oque === "outro" && <p className="san-nota" style={{ flexBasis: "100%", margin: 0 }}>“Outro” só registra no histórico. Não cria cadastro nem caixa.</p>}
          <label className="san-liga" style={{ flexBasis: "100%" }}>
            <input type="checkbox" checked={f.ficha} onChange={(e) => set({ ficha: e.target.checked })} />
            <span><b>Estou lançando uma ficha de campo preenchida no papel</b><small>Fica registrado que veio da ficha.</small></span>
          </label>
        </div>
      </section>
      <section className="san-bloco">
        <div className="san-bloco-cab"><h3>Quando</h3></div>
        <div className="san-bloco-corpo san-linha">
          <div className="san-campo medio">
            <label htmlFor="lData">Data</label>
            <input id="lData" className="san-input" type="date" value={f.data} max={hoje} onChange={(e) => set({ data: e.target.value })} />
          </div>
          {retro && (
            <div className="san-campo" style={{ flex: "2 1 260px" }}>
              <label htmlFor="lMot">Motivo do lançamento retroativo (pode pular)</label>
              <input id="lMot" className="san-input" value={f.motivo} onChange={(e) => set({ motivo: e.target.value })} placeholder="ex.: ficha do curral lançada depois" />
            </div>
          )}
        </div>
      </section>
      <section className="san-bloco">
        <div className="san-bloco-cab"><h3>Em quem</h3>
          <button type="button" className="btn-primary san-btn-sm" onClick={() => setSeletor(true)}><Search size={12} aria-hidden="true" style={{ verticalAlign: "-1px", marginRight: 4 }} />Escolher animais</button></div>
        <div className="san-bloco-corpo" style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          {f.animais.length ? (
            <div className="san-acoes">
              {f.animais.map((a) => (
                <span key={a.id} className="san-chip k-janela"><i aria-hidden="true" />{a.numero}
                  <button type="button" className="san-link" aria-label={`Tirar ${a.numero}`} onClick={() => set({ animais: f.animais.filter((x) => x.id !== a.id) })}><X size={12} aria-hidden="true" /></button></span>
              ))}
            </div>
          ) : <p className="san-nota" style={{ margin: 0 }}>Nenhum animal escolhido. Use “Escolher animais”: busca, filtros e seleção múltipla.</p>}
          <div className="san-campo">
            <label htmlFor="lNum">Brincos sem cadastro (opcional, separados por vírgula)</label>
            <input id="lNum" className="san-input" value={f.numeros} onChange={(e) => set({ numeros: e.target.value })} placeholder="ex.: 2501, 2502" />
          </div>
        </div>
      </section>
      {exame ? (
        <section className="san-bloco">
          <div className="san-bloco-cab"><h3>Resultado por animal</h3></div>
          <div className="san-bloco-corpo" style={{ display: "flex", flexDirection: "column", gap: "0.45rem" }}>
            {f.animais.length ? f.animais.map((a) => (
              <div key={a.id} className="san-linha" style={{ alignItems: "center" }}>
                <b className="san-num" style={{ width: 70 }}>{a.numero}</b>
                <Seg<Resultado> rotulo={`Resultado de ${a.numero}`} valor={f.res[a.id] || "nao_lido"} onChange={(v) => set({ res: { ...f.res, [a.id]: v } })}
                  opcoes={RESULTADOS.map((r) => ({ id: r, label: ROTULO_RESULTADO[r] }))} />
              </div>
            )) : <p className="san-nota" style={{ margin: 0 }}>Escolha os animais primeiro.</p>}
            <p className="san-nota" style={{ margin: 0 }}>Reagente gera só um aviso (sem pendência).</p>
          </div>
        </section>
      ) : (
        <section className="san-bloco">
          <div className="san-bloco-cab"><h3>Produto (opcional)</h3></div>
          <div className="san-bloco-corpo" style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            <div className="san-opcs" role="radiogroup" aria-label="Produto">
              {([...(cx ? [["padrao", "O da vacina", "Usa o produto e a dose do cadastro."]] : []), ["estoque", "Do estoque", "Baixa a cada animal."],
                ["sem_estoque", "Produto sem estoque", "Só registra o nome."], ["nenhum", "Sem produto", "Registra sem produto."]] as [ModoProduto, string, string][]).map(([k, t, s]) => (
                <label key={k} className="san-opc"><input type="radio" name="lProd" checked={f.modoProduto === k} onChange={() => set({ modoProduto: k })} /><span><b>{t}</b><small>{s}</small></span></label>
              ))}
            </div>
            {f.modoProduto === "estoque" && (
              <div className="san-campo"><label htmlFor="lEstq">Item do estoque</label>
                <select id="lEstq" className="san-input" value={f.estoqueId} onChange={(e) => set({ estoqueId: e.target.value })}>
                  <option value="">Escolha…</option>
                  {(estoque.dados || []).map((e) => <option key={e.id} value={e.id}>{e.nome}{e.quantidade != null ? ` · saldo ${e.quantidade} ${e.unidade || ""}` : ""}</option>)}
                </select></div>
            )}
            {f.modoProduto === "sem_estoque" && (
              <div className="san-campo"><label htmlFor="lPtxt">Nome do produto</label><input id="lPtxt" className="san-input" value={f.produtoTexto} onChange={(e) => set({ produtoTexto: e.target.value })} /></div>
            )}
            {(f.modoProduto === "estoque" || f.modoProduto === "sem_estoque") && (
              <div className="san-linha">
                <div className="san-campo curto"><label htmlFor="lDose">Dose</label><input id="lDose" className="san-input" type="number" step="0.1" min={0} value={f.dose} onChange={(e) => set({ dose: e.target.value })} /></div>
                <div className="san-campo medio"><label htmlFor="lUn">Unidade</label>
                  <select id="lUn" className="san-input" value={f.unidade} onChange={(e) => set({ unidade: e.target.value })}>
                    {DOSE_UNIDADES.map((u) => <option key={u} value={u}>{ROTULO_UNIDADE[u]}</option>)}
                  </select></div>
                {f.unidade === "mL_por_x_kg" && <div className="san-campo curto"><label htmlFor="lX">X (kg)</label><input id="lX" className="san-input" type="number" min={1} value={f.xkg} onChange={(e) => set({ xkg: e.target.value })} /></div>}
              </div>
            )}
          </div>
        </section>
      )}
      <section className="san-bloco">
        <div className="san-bloco-cab"><h3>Perguntas rápidas</h3></div>
        <div className="san-bloco-corpo" style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
          <CampoPessoa id="lApl" rotulo="Quem aplicou?" valor={f.aplicador} onChange={(v) => set({ aplicador: v })} />
          <div className="san-linha">
            <div className="san-campo medio"><label htmlFor="lVet">Veterinário (opcional)</label>
              <select id="lVet" className="san-input" value={f.vet} onChange={(e) => set({ vet: e.target.value })}>
                <option value="">Não informar</option>
                {(vets.dados?.pessoas || []).map((p) => <option key={p.pessoa_id} value={p.pessoa_id}>{p.nome}{p.crmv ? ` · ${p.crmv}` : ""}</option>)}
                <option value="__txt">Outro (escrever)</option>
              </select></div>
            {f.vet === "__txt" && (<>
              <div className="san-campo medio"><label htmlFor="lVetT">Nome</label><input id="lVetT" className="san-input" value={f.vetTxt} onChange={(e) => set({ vetTxt: e.target.value })} /></div>
              <div className="san-campo curto"><label htmlFor="lCrmv">CRMV</label><input id="lCrmv" className="san-input" value={f.crmv} onChange={(e) => set({ crmv: e.target.value })} /></div>
            </>)}
          </div>
          <div className="san-campo">
            <span className="san-rot">Tem atestado?</span>
            <Seg<"nao" | "sim"> rotulo="Tem atestado" valor={f.atestado} onChange={(v) => set({ atestado: v })} opcoes={[{ id: "nao", label: "Não" }, { id: "sim", label: "Sim" }]} />
            {f.atestado === "sim" && (
              <div className="san-linha" style={{ marginTop: "0.4rem" }}>
                <div className="san-campo"><label htmlFor="lAtN">Nº do atestado</label><input id="lAtN" className="san-input" value={f.atNum} onChange={(e) => set({ atNum: e.target.value })} /></div>
                <div className="san-campo"><label htmlFor="lAtD">Destinatário</label><input id="lAtD" className="san-input" value={f.atDest} onChange={(e) => set({ atDest: e.target.value })} placeholder="ex.: Agrodefesa / SIDAGO" /></div>
              </div>
            )}
          </div>
          {!exame && (
            <div className="san-campo">
              <span className="san-rot">Tem carência?</span>
              <Seg<"nao" | "sim" | "naosei"> rotulo="Tem carência" valor={f.car} onChange={(v) => set({ car: v })}
                opcoes={[{ id: "nao", label: "Não" }, { id: "sim", label: "Sim" }, { id: "naosei", label: cx ? "A da vacina / não sei" : "Não sei" }]} />
              {f.car === "sim" && (
                <div className="san-linha" style={{ marginTop: "0.4rem" }}>
                  <div className="san-campo curto"><label htmlFor="lCL">Leite (dias)</label><input id="lCL" className="san-input" type="number" min={0} value={f.carL} onChange={(e) => set({ carL: e.target.value })} /></div>
                  <div className="san-campo curto"><label htmlFor="lCC">Carne (dias)</label><input id="lCC" className="san-input" type="number" min={0} value={f.carC} onChange={(e) => set({ carC: e.target.value })} /></div>
                  {admin && (
                    <div className="san-campo medio"><label htmlFor="lCM">Leite durante a carência</label>
                      <select id="lCM" className="san-input" value={f.carModo} onChange={(e) => set({ carModo: e.target.value as ModoLeite | "" })}>
                        <option value="">Regra da vacina</option>{MODOS_LEITE.map((m) => <option key={m} value={m}>{ROTULO_MODO_LEITE[m]}</option>)}
                      </select></div>
                  )}
                </div>
              )}
              {f.car === "naosei" && <p className="san-nota" style={{ margin: "0.3rem 0 0" }}>Se a carência não for conhecida, ao gravar o sistema pergunta o que fazer com o leite (bloquear, descartar ou tanque) e grava a decisão.</p>}
            </div>
          )}
        </div>
      </section>
      {desfazer && <BarraDesfazer registroIds={desfazer.ids} ate={desfazer.ate} texto={desfazer.texto}
        onDesfeito={() => { setDesfazer(null); toast("Desfeito: nada ficou no histórico."); }} onFim={() => setDesfazer(null)} />}
      {avisos.length > 0 && <Faixa tipo="atencao"><ul style={{ margin: 0 }}>{avisos.map((a) => <li key={a}>{a}</li>)}</ul></Faixa>}
      <div className="san-acoes fim">
        <span className="san-nota" role="status" style={{ marginRight: "auto" }}>
          {erro ? <span className="san-erro-txt">{erro}</span> : cx && !exame ? `Os animais saem da caixa ${cx.nome_curto || cx.nome} neste ciclo.` : f.oque === "outro" ? "Só registra no histórico." : ""}
          {retro && !erro ? ` Lançamento retroativo (${fmtData(f.data)}).` : ""}
        </span>
        <button type="button" className="btn-ghost" onClick={() => { setF(novo()); setErro(null); setAvisos([]); setConsentimentos([]); setChaveLote(novaChave("lanc")); }}>Limpar</button>
        <button type="button" className="btn-primary-gold" disabled={salvando} onClick={() => gravar()}>{salvando ? "Gravando…" : "Gravar no histórico"}</button>
      </div>

      <ImportarPlanilha />

      {seletor && (
        <SeletorAnimais titulo="Em quem" rotuloOk="Usar" jaSelecionados={f.animais.map((a) => a.id)}
          subtitulo={cx ? `Conferindo a regra de ${cx.nome_curto || cx.nome} em ${fmtData(f.data, true)}. Quem está fora pode entrar com o seu consentimento.` : undefined}
          checar={cx ? async (ids) => elegibilidadeDaSimulacao(await simularDia([cx.id], f.data, f.data, ids), ids) : undefined}
          onFechar={() => setSeletor(false)} onConfirmar={(_, animais) => { setSeletor(false); set({ animais }); }} />
      )}
      {ficha && cx && <ModalFicha caixaIds={[cx.id]} onFechar={() => setFicha(false)} />}
      {consent && (
        <ModalConsentimento itens={consent.map((i) => ({ animal_id: i.animal_id || 0, numero: i.numero, caixa_id: i.caixa_id, caixa: cx?.nome_curto || cx?.nome, motivo: i.motivo_fora || "fora da regra" }))}
          perguntarAtestado={consent.some((i) => i.pergunta_atestado)} onVoltar={() => setConsent(null)}
          onConfirmar={(r) => {
            setConsent(null);
            const cons = [...consentimentos, ...r.aceitos];
            setConsentimentos(cons);
            const fora = new Set(r.recusados.map((x) => x.animal_id));
            const restantes = f.animais.filter((a) => !fora.has(a.id));
            if (fora.size) set({ animais: restantes });
            if (r.aceitos.length) gravar(undefined, cons, restantes);
          }} />
      )}
      {carencia && (
        <ModalCarencia nome={cx?.nome_curto || cx?.nome || "vacina"} motivo={carencia.motivo_carencia} sugestao={carencia.carencia_sugerida as CarenciaDecisaoIn | undefined}
          onCancelar={() => setCarencia(null)}
          onDecidir={(d) => { setCarencia(null); gravar({ modo: d.modo, leite_dias: d.leite_dias, carne_dias: d.carne_dias }); }} />
      )}
    </div>
  );
}
