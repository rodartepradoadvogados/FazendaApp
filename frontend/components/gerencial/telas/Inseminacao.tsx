"use client";
// PROPOSTA — Lançamentos › Reprodutivo › Inseminação (variante desktop, só apresentação, dados de exemplo; sem fetch).
// Substitui FormInseminacao.tsx (duas colunas com rolagem própria, matriz escolhida em MODAL e depois vista como pílulas).
//
// O QUE A VERSÃO LIGADA A DADOS PRECISA PRESERVAR (inventário de FormInseminacao.tsx):
//  · Props: animais (AnimalRow[]), motivosInaptidao (Map número→motivo), idadeMinServico, prefill {numeroMatriz, numeros, protocolo}, onSalvo.
//    Também lê a querystring (?numero_matriz=…&protocolo=…) quando não há prefill; `protocolo` força origem "protocolo" + cobertura IATF.
//    Roda na gaveta da Agenda (prefill) e no destino do Diagnóstico Negativo (numeros) — o banner "Pré-marcadas" mostra de onde vieram.
//  · Origem: avulsa (animais ou lote(s) — marcar o lote marca as aptas dele, ajustável na tabela) × Protocolo IATF vigente
//    (fetchProtocolosIatfAtivos, só `pronta_para_inseminar`, não exige estar em D11 hoje). Origem "protocolo" ⇒ cobertura IATF travada.
//  · Touro: categoria convencional/sexado/fazenda; touro com doses em estoque (fetchSemenDisponivel) OU catálogo NAAB completo
//    (fetchTouros + TouroPicker, "Incluir touros sem estoque"); touro da fazenda ⇒ monta natural; alerta de estoque abaixo do mínimo
//    (semen.abaixo_minimo / totais / minimos). Responsável: usePessoasAtivas. Data obrigatória.
//  · Vínculo IATF (só cobertura IATF avulsa): fetchLancamentosIatf + "auto_lancar_iatf" (D0 retroativo = serviço − 11 dias; só registra o
//    protocolo, não gera hormônio). Origem protocolo: vínculo automático quando a seleção pertence a um único lançamento.
//  · Sugestão de acasalamento (fetchSugestaoAcasalamento): só com EXATAMENTE 1 matriz; critérios + touros (TPI, doses, `tem_ancestral_comum`,
//    `motivo`); clicar num touro o escolhe; falha discreta (erroSugestao) sem travar o resto.
//  · Aptidão: lista TODAS as fêmeas; inaptas em cinza com o motivo (idade mínima, baixada, a descartar), ainda marcáveis; peso mínimo e
//    reinseminação de gestante são conferidos AO SALVAR (409 confirmável ⇒ `forcar: true`; idade/sexo/baixada nunca são confirmáveis).
//  · Salvar: POST /reproducao/servico-lote {animais, data_servico, tipo, reprodutor, responsavel, protocolo_lancamento_id,
//    auto_lancar_iatf, tipo_semen (null p/ fazenda), forcar} → {criados, incompativeis}. `incompativeis` voltam marcados, com a mensagem;
//    depois de criar: recarregar semen e protocolos ativos, limpar seleção e touro, chamar onSalvo.
import React, { useMemo, useState } from "react";
import { AlertTriangle, Syringe } from "lucide-react";
import { Aviso, Ajuda, BarraAcao, BotaoOuro, Faixa, Passo, Pilulas, QuadroGaveta, Selo } from "@/components/gerencial/kit";
import {
  EstiloRepro, PilulasX, BuscaMatrizes, TabelaMatrizes, MATRIZES, HOJE_ISO, alterna, alternaAptas, filtraBusca, fmtData, somaDias, type Matriz,
} from "@/components/gerencial/telas/ReprodutivoComum";

type CatTouro = "convencional" | "sexado" | "fazenda";
type Cobertura = "cio_natural" | "iatf" | "monta_natural";
type Origem = "animais" | "lotes" | "protocolo";
type Touro = { nome: string; naab: string; tpi: number; doses: number; cat: CatTouro };

const TOUROS: Touro[] = [
  { nome: "Mogul", naab: "7HO12345", tpi: 2891, doses: 20, cat: "convencional" },
  { nome: "Delta", naab: "7HO13002", tpi: 2812, doses: 6, cat: "convencional" },
  { nome: "Yoda", naab: "7HO11876", tpi: 2754, doses: 10, cat: "convencional" },
  { nome: "Gold Chip FEM", naab: "7HO14420", tpi: 2860, doses: 8, cat: "sexado" },
  { nome: "Mogul FEM", naab: "7HO12345", tpi: 2891, doses: 6, cat: "sexado" },
  { nome: "Rei (touro da fazenda)", naab: "—", tpi: 0, doses: 0, cat: "fazenda" },
];
const MINIMOS = { convencional: 30, sexado: 20 };
const ROTULO_CAT: Record<CatTouro, string> = { convencional: "Convencional", sexado: "Sexado", fazenda: "Touro da fazenda" };
const ROTULO_COB: Record<Cobertura, string> = { cio_natural: "cio natural", iatf: "IATF", monta_natural: "monta natural" };
const RESPONSAVEIS = ["Anderson", "Marcos", "Dr. Paulo (veterinário)", "Jairo"];
const LANCAMENTOS_IATF = ["PROTOCOLO IATF - 06/10/26 A 17/10/26 (D0 A D11 - 12 DIAS)", "PROTOCOLO IATF - 12/10/26 A 23/10/26 (D0 A D11 - 12 DIAS)"];
const SUGESTAO = {
  criterios: [
    "Exclui touros com ancestral em comum com a matriz (até 3 gerações).",
    "Prefere maior TPI entre os touros com sêmen em estoque.",
    "Distribui o uso para não esgotar as doses de um só touro.",
  ],
  sugestoes: [
    { nome: "Mogul", naab: "7HO12345", tpi: 2891, doses: 20, ancestral: false, motivo: "Maior TPI em estoque; sem ancestral comum com 1110." },
    { nome: "Delta", naab: "7HO13002", tpi: 2812, doses: 6, ancestral: false, motivo: "Sem ancestral comum; reforça úbere e saúde de pernas." },
    { nome: "Yoda", naab: "7HO11876", tpi: 2754, doses: 10, ancestral: true, motivo: "Ancestral comum com 1110 (avô materno) — evitar." },
  ],
};

type Estado = "lote" | "uma";
type Retorno = "sucesso" | "confirmar" | "incompativeis" | null;

export function Inseminacao({ estado = "lote" }: { estado?: Estado }) {
  const uma = estado === "uma";
  const prefillNums = useMemo(() => new Set(uma ? ["1110"] : ["11153", "3335", "075", "9378"]), [uma]);
  const matrizes: Matriz[] = useMemo(() => MATRIZES.map((m) => ({ ...m, diag: prefillNums.has(m.n) })), [prefillNums]);

  const [origem, setOrigem] = useState<Origem>("animais");
  const [lotesSel, setLotesSel] = useState<string[]>([]);
  const [sel, setSel] = useState<Set<string>>(() => new Set(uma ? ["1110"] : ["11153", "3335", "075", "9378", "7120", "4821", "4790", "1087", "1092", "13180", "4802", "1110"]));
  const [busca, setBusca] = useState("");
  const [cat, setCat] = useState<CatTouro>("convencional");
  const [cob, setCob] = useState<Cobertura>(uma ? "iatf" : "cio_natural");
  const [touro, setTouro] = useState<string>(uma ? "Mogul" : "Mogul");
  const [semEstoque, setSemEstoque] = useState(false);
  const [textoCatalogo, setTextoCatalogo] = useState("");
  const [data, setData] = useState(HOJE_ISO);
  const [resp, setResp] = useState(uma ? "Dr. Paulo (veterinário)" : "Anderson");
  const [vinculo, setVinculo] = useState("");
  const [autoD0, setAutoD0] = useState(uma);
  const [sugAberta, setSugAberta] = useState(uma);
  const [retorno, setRetorno] = useState<Retorno>(uma ? "confirmar" : "sucesso");
  const [prefillVisivel, setPrefillVisivel] = useState(true);

  const cobEf: Cobertura = origem === "protocolo" ? "iatf" : cat === "fazenda" ? "monta_natural" : cob;
  const lotes = useMemo(() => {
    const m = new Map<string, number>();
    matrizes.forEach((x) => m.set(x.lote, (m.get(x.lote) ?? 0) + 1));
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b, "pt-BR", { numeric: true }));
  }, [matrizes]);
  const prontas = matrizes.filter((m) => m.protocolo);
  const aptas = matrizes.filter((m) => m.apt === "apta");
  const inaptas = matrizes.filter((m) => m.apt === "inapta");

  const base = origem === "animais" ? matrizes : origem === "lotes" ? matrizes.filter((m) => lotesSel.includes(m.lote)) : prontas;
  const visiveis = filtraBusca(base, busca);
  const marcadas = matrizes.filter((m) => sel.has(m.n));
  const nSel = marcadas.length;
  const nPedemConfirmacao = marcadas.filter((m) => m.apt !== "apta").length;

  const tourosCat = TOUROS.filter((t) => t.cat === cat);
  const touroSel = tourosCat.find((t) => t.nome === touro);
  const dosesTotais = { convencional: TOUROS.filter((t) => t.cat === "convencional").reduce((s, t) => s + t.doses, 0), sexado: TOUROS.filter((t) => t.cat === "sexado").reduce((s, t) => s + t.doses, 0) };
  const abaixo = (["convencional", "sexado"] as const).filter((c) => dosesTotais[c] < MINIMOS[c]);

  function trocaOrigem(o: Origem) {
    setOrigem(o); setBusca(""); setLotesSel([]); setPrefillVisivel(false);
    setSel(o === "protocolo" ? new Set(prontas.map((m) => m.n)) : new Set());
  }
  function alternaLote(lote: string) {
    const ativo = lotesSel.includes(lote);
    setLotesSel(ativo ? lotesSel.filter((l) => l !== lote) : [...lotesSel, lote]);
    const doLote = matrizes.filter((m) => m.lote === lote && m.apt === "apta");
    setSel((p) => { const s = new Set(p); doLote.forEach((m) => (ativo ? s.delete(m.n) : s.add(m.n))); return s; });
  }
  function escolheCat(c: CatTouro) {
    setCat(c); setSemEstoque(false);
    setTouro(TOUROS.find((t) => t.cat === c)?.nome ?? "");
  }

  // Resumo da barra
  const doseTxt = (() => {
    if (cat === "fazenda") return touroSel ? `${touroSel.nome} (monta natural)` : "touro da fazenda";
    if (!touro) return "sem touro escolhido";
    if (!touroSel) return `${touro} (catálogo, sem estoque)`;
    const restam = touroSel.doses - nSel;
    return `${touroSel.nome} (−${nSel} ${nSel === 1 ? "dose" : "doses"}, ${restam >= 0 ? `restam ${restam}` : `faltam ${-restam}`})`;
  })();
  const resumo = `${nSel} ${nSel === 1 ? "matriz" : "matrizes"} · ${ROTULO_CAT[cat]} · ${doseTxt}`;
  const detalhe = !nSel ? "Marque ao menos uma matriz na tabela do passo 2"
    : !data ? "Falta a data da inseminação"
    : `${ROTULO_COB[cobEf][0].toUpperCase()}${ROTULO_COB[cobEf].slice(1)} em ${fmtData(data)}${resp ? ` · ${resp}` : ""}${nPedemConfirmacao ? ` · ${nPedemConfirmacao} pede(m) confirmação` : ""}`;

  const faixa = [
    { rotulo: "Fêmeas na lista", valor: matrizes.length },
    { rotulo: "Aptas a servir", valor: aptas.length, tom: "ok" as const },
    { rotulo: "Inaptas", valor: inaptas.length },
    { rotulo: "Prontas do protocolo IATF", valor: prontas.length },
    { rotulo: "Sêmen convencional", valor: `${dosesTotais.convencional}/${MINIMOS.convencional}`, tom: "ok" as const },
    { rotulo: "Sêmen sexado", valor: `${dosesTotais.sexado}/${MINIMOS.sexado}`, tom: "alerta" as const },
  ];

  return (
    <QuadroGaveta titulo="Lançar › Reprodutivo › Inseminação" icone={Syringe} largura={1320}>
      <EstiloRepro />
      <Faixa itens={faixa} />
      {abaixo.length > 0 && (
        <div style={{ marginBottom: "0.9rem" }}>
          <Aviso tom="erro">
            <AlertTriangle size={15} style={{ marginTop: "0.1rem", flexShrink: 0 }} aria-hidden="true" />
            <span>
              Estoque de sêmen abaixo do mínimo:{" "}
              {abaixo.map((c) => `${c} ${dosesTotais[c]}/${MINIMOS[c]}`).join(" · ")}. Registre a compra na NF. Você ainda pode lançar com o que há.
            </span>
          </Aviso>
        </div>
      )}

      <Passo n={1} id="ins-p1" titulo="De onde vêm as matrizes">
        <Pilulas<Origem> rotulo="Origem da inseminação" valor={origem} onChange={trocaOrigem} opcoes={[
          { id: "animais", nome: "Animais", titulo: "Escolher animal por animal na tabela" },
          { id: "lotes", nome: "Lotes", n: lotes.length, titulo: "Escolher um ou mais lotes — entram as aptas de cada um" },
          { id: "protocolo", nome: "Protocolo IATF vigente", n: prontas.length, titulo: "Matrizes de protocolo IATF vigente ainda sem inseminação lançada — não importa em que etapa do hormônio estão hoje" },
        ]} />
        {origem === "lotes" && (
          <Pilulas<string> rotulo="Lotes" valor={lotesSel} onChange={alternaLote} opcoes={lotes.map(([l, n]) => ({ id: l, nome: l, n }))} />
        )}
        {origem === "protocolo" && (
          <p className="gv-ajuda">
            Só matrizes de protocolo vigente <strong>sem inseminação lançada</strong> (prontas), mesmo que a etapa de hoje não seja a D11. A cobertura passa a ser
            <strong> IATF</strong>. Protocolo em uso: <strong>PROTOCOLO IATF - 06/10/26 A 17/10/26</strong> · {prontas.length} prontas.
          </p>
        )}
        {prefillVisivel && prefillNums.size > 0 && (
          <div className="rp-tarja" role="status">
            <Selo tom="info">{uma ? "Veio da Agenda" : "Vieram do diagnóstico"}</Selo>
            <span><strong>{prefillNums.size}</strong> {prefillNums.size === 1 ? "matriz já marcada" : "matrizes já marcadas"} na tabela abaixo:</span>
            {[...prefillNums].map((n) => <span key={n} className="rp-chip">{n}</span>)}
            <button type="button" className="btn-ghost" onClick={() => { setSel(new Set()); setPrefillVisivel(false); }}>Desmarcar tudo</button>
          </div>
        )}
      </Passo>

      <Passo n={2} id="ins-p2" titulo="Matrizes" direita={
        <span className="rp-contagem" aria-live="polite">{nSel} de {visiveis.length} {nSel === 1 ? "marcada" : "marcadas"}{nPedemConfirmacao > 0 && ` · ${nPedemConfirmacao} pede(m) confirmação`}</span>
      }>
        <div className="rp-ferr">
          <BuscaMatrizes valor={busca} onChange={setBusca} />
          <button type="button" className="btn-ghost" onClick={() => setSel((p) => alternaAptas(p, visiveis))}>Marcar / desmarcar as aptas</button>
          <button type="button" className="btn-ghost" onClick={() => setSel(new Set())} disabled={!nSel}>Limpar seleção</button>
        </div>
        <TabelaMatrizes matrizes={visiveis} sel={sel} mostrarProtocolo altura="48rem"
          vazio={origem === "lotes" ? "Marque um ou mais lotes acima." : "Nenhuma fêmea bate com a busca."}
          onToggle={(n) => setSel((p) => alterna(p, n))} onToggleAptas={() => setSel((p) => alternaAptas(p, visiveis))}
          onToggleLote={(_l, itens) => setSel((p) => alternaAptas(p, itens))} />
        <Ajuda>
          A lista mostra <strong>todas as fêmeas</strong>. As <strong>inaptas ficam em cinza</strong>, com o motivo ao lado (idade mínima de {14} meses, animal baixado ou marcado a descartar) e
          ainda podem ser marcadas: o servidor pede confirmação. Peso mínimo da novilha e reinseminação de matriz que consta gestante são conferidos ao salvar.
        </Ajuda>
      </Passo>

      <Passo n={3} id="ins-p3" titulo="Sêmen e touro">
        <div className="rp-grade-2">
          <div className="rp-col">
            <div className="gv-rotulo">Categoria do sêmen</div>
            <PilulasX<CatTouro> rotulo="Categoria do touro / sêmen" valor={cat} onChange={escolheCat} opcoes={[
              { id: "convencional", nome: "Convencional", n: dosesTotais.convencional, titulo: "Doses em estoque" },
              { id: "sexado", nome: "Sexado", n: dosesTotais.sexado, titulo: "Doses em estoque" },
              { id: "fazenda", nome: "Touro da fazenda", titulo: "Monta natural" },
            ]} />
            <div className="gv-rotulo" style={{ marginTop: "0.4rem" }}>Tipo de cobertura</div>
            <PilulasX<Cobertura> rotulo="Tipo de cobertura" valor={cobEf} onChange={setCob} opcoes={[
              { id: "cio_natural", nome: "Cio natural", travada: cat === "fazenda" || origem === "protocolo", titulo: "Inseminação de cio natural (sem protocolo)" },
              { id: "iatf", nome: "IATF", travada: cat === "fazenda", titulo: "Inseminação de um protocolo IATF" },
              { id: "monta_natural", nome: "Monta natural", travada: cat !== "fazenda" || origem === "protocolo", titulo: "Cobertura por touro" },
            ]} />
            {cat === "fazenda" && <p className="gv-ajuda">Touro da fazenda escolhido: registrado como <strong>monta natural</strong>.</p>}
            {origem === "protocolo" && <p className="gv-ajuda">Origem “Protocolo IATF vigente”: sempre registrada como <strong>IATF</strong>.</p>}
          </div>

          <div className="rp-col">
            <div className="gv-rotulo">{cat === "fazenda" ? "Touro (monta natural)" : semEstoque ? "Touro (catálogo NAAB completo)" : "Touro (em estoque)"}</div>
            {!semEstoque ? (
              <div className="gv-tabela-moldura rp-tab" style={{ ["--gv-altura-tabela" as string]: "12rem" }}>
                <table className="gv-tabela">
                  <thead><tr>
                    <th scope="col" style={{ width: "2.4rem" }}><span className="sr-only" style={{ position: "absolute", left: "-9999px" }}>Escolher</span></th>
                    <th scope="col">Touro</th><th scope="col">NAAB</th><th scope="col" className="gv-dir">TPI</th>
                    <th scope="col" className="gv-dir">Doses</th><th scope="col" className="gv-dir">Depois de lançar</th>
                  </tr></thead>
                  <tbody>
                    {tourosCat.length === 0 && <tr className="rp-tab-vazia"><td colSpan={6}>Nenhum touro {ROTULO_CAT[cat].toLowerCase()} em estoque.</td></tr>}
                    {tourosCat.map((t) => {
                      const restam = t.doses - nSel;
                      return (
                        <tr key={t.nome} className={touro === t.nome ? "gv-linha-marcada" : undefined}>
                          <td><input type="radio" name="ins-touro" checked={touro === t.nome} onChange={() => setTouro(t.nome)} aria-label={`Usar ${t.nome}`} /></td>
                          <td className="gv-forte">{t.nome}</td>
                          <td className="gv-num">{t.naab}</td>
                          <td className="gv-num gv-dir">{t.tpi ? t.tpi : "—"}</td>
                          <td className="gv-num gv-dir">{t.cat === "fazenda" ? "—" : t.doses}</td>
                          <td className="gv-num gv-dir">
                            {t.cat === "fazenda" ? "monta natural" : touro !== t.nome ? <span className="rp-mudo">—</span> : restam >= 0 ? <>−{nSel} · restam <b>{restam}</b></> : <span className="rp-err">faltam {-restam}</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="gv-campo">
                <label htmlFor="ins-catalogo">Buscar touro no catálogo NAAB</label>
                <input id="ins-catalogo" className="rp-input" value={textoCatalogo} onChange={(e) => { setTextoCatalogo(e.target.value); setTouro(e.target.value); }} placeholder="Nome, NAAB ou central…" />
              </div>
            )}
            {cat !== "fazenda" && (
              <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem", color: "var(--text-muted)", cursor: "pointer" }}>
                <input type="checkbox" checked={semEstoque} onChange={(e) => { setSemEstoque(e.target.checked); setTouro(""); setTextoCatalogo(""); }} />
                Incluir touros sem estoque (catálogo NAAB completo)
              </label>
            )}
          </div>
        </div>

        <div className="rp-recolher">
          <button type="button" className="rp-recolher-topo" aria-expanded={sugAberta && nSel === 1} disabled={nSel !== 1} onClick={() => setSugAberta((a) => !a)}>
            <span aria-hidden="true">{sugAberta && nSel === 1 ? "▾" : "▸"}</span>
            Sugestão de acasalamento
            <span className="rp-recolher-sub">
              {nSel === 1 ? `para a matriz ${marcadas[0].n} — critérios e touros em estoque` : `só com 1 matriz marcada (agora ${nSel}) — a sugestão pula a seleção em lote`}
            </span>
          </button>
          {sugAberta && nSel === 1 && (
            <div className="rp-recolher-corpo">
              <ul className="rp-lista">{SUGESTAO.criterios.map((c) => <li key={c}>{c}</li>)}</ul>
              <div className="rp-grade-3">
                {SUGESTAO.sugestoes.map((s) => (
                  <button key={s.nome} type="button" className="rp-sug" data-alerta={s.ancestral} aria-pressed={touro === s.nome} title="Clique para usar este touro na inseminação" onClick={() => setTouro(s.nome)}>
                    <span className="rp-sug-topo"><span>{s.nome} · {s.naab}</span><span>TPI {s.tpi} · {s.doses} doses</span></span>
                    <p>{s.ancestral && <AlertTriangle size={12} aria-hidden="true" style={{ verticalAlign: "-1px", marginRight: "0.25rem" }} />}{s.motivo}</p>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </Passo>

      <Passo n={4} id="ins-p4" titulo="Data, responsável e vínculo">
        <div className="gv-grade" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
          <div className="gv-campo">
            <label htmlFor="ins-data">Data da inseminação</label>
            <input id="ins-data" type="date" className="rp-input" value={data} onChange={(e) => setData(e.target.value)} />
          </div>
          <div className="gv-campo">
            <label htmlFor="ins-resp">Responsável / inseminador</label>
            <select id="ins-resp" className="rp-select" value={resp} onChange={(e) => setResp(e.target.value)}>
              <option value="">Selecione…</option>
              {RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
          {cobEf === "iatf" && origem !== "protocolo" && (
            <>
              <div className="gv-campo">
                <label htmlFor="ins-vinculo">Vincular ao protocolo IATF</label>
                <select id="ins-vinculo" className="rp-select" value={vinculo} onChange={(e) => setVinculo(e.target.value)}>
                  <option value="">Automático (o protocolo pendente do animal)</option>
                  {LANCAMENTOS_IATF.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </div>
              <div className="gv-campo">
                <label htmlFor="ins-d0b">Se o animal não estiver em protocolo</label>
                <div>
                  <label style={{ display: "inline-flex", alignItems: "center", gap: "0.45rem", fontSize: "0.82rem", padding: "0.4rem 0", cursor: "pointer", textTransform: "none", letterSpacing: 0, fontWeight: 400, color: "var(--text)" }}>
                    <input id="ins-d0b" type="checkbox" checked={autoD0} onChange={(e) => setAutoD0(e.target.checked)} /> Lançar D0 retroativo (serviço − 11 dias)
                  </label>
                </div>
              </div>
            </>
          )}
        </div>
        {cobEf === "iatf" && origem !== "protocolo" && (
          <Ajuda>
            {autoD0
              ? <>O D0 será lançado em <strong>{fmtData(somaDias(data, -11))}</strong> (data do serviço − 11 dias). Só registra o protocolo — não gera aplicação de hormônio nem baixa de estoque.</>
              : "Sem D0 retroativo, matriz fora de protocolo volta como incompatível e fica marcada para você vincular a um protocolo existente."}
          </Ajuda>
        )}
        {cobEf === "iatf" && origem === "protocolo" && (
          <Ajuda>{vinculo ? <>Vinculado ao protocolo <strong>{vinculo}</strong>.</> : "Cada matriz será vinculada ao seu próprio protocolo IATF em andamento (detectado automaticamente)."}</Ajuda>
        )}
        {cobEf !== "iatf" && <Ajuda>O vínculo com protocolo IATF e o D0 retroativo aparecem quando a cobertura é IATF.</Ajuda>}
      </Passo>

      <BarraAcao
        resumo={resumo}
        detalhe={detalhe}
        retorno={retorno && (
          <div className="rp-retorno-linha">
            {retorno === "sucesso" && (
              <>
                <span className="rp-ok">✓ 5 inseminações registradas (cio natural) · Yoda: −5 doses, restam 10.</span>
                <span className="rp-mudo">Matrizes já inseminadas saíram da lista de prontas do protocolo.</span>
              </>
            )}
            {retorno === "confirmar" && (
              <>
                <span className="rp-err" role="alert">Novilha 1110 sem pesagem registrada: o peso mínimo não pôde ser conferido.</span>
                <span className="gv-espaco" style={{ flex: 1 }} />
                <button type="button" className="btn-secondary" onClick={() => setRetorno("sucesso")} title="Registra a inseminação assumindo a situação descrita ao lado">Confirmar e lançar mesmo assim</button>
              </>
            )}
            {retorno === "incompativeis" && (
              <span className="rp-err" role="alert">3335, 075 não estão em nenhum protocolo IATF. Vincule a um protocolo existente ou marque “Lançar D0 retroativo” e salve de novo. As outras 10 foram registradas.</span>
            )}
          </div>
        )}
        secundaria={<button type="button" className="btn-ghost" onClick={() => setSel(new Set())} disabled={!nSel}>Limpar</button>}
        acao={<BotaoOuro desabilitado={!nSel || !data} onClick={() => setRetorno("sucesso")}>{`Lançar ${nSel || ""} ${nSel === 1 ? "inseminação" : "inseminações"}`.replace("  ", " ")}</BotaoOuro>}
      />
    </QuadroGaveta>
  );
}
