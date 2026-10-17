"use client";
// Lançamento de INDUÇÃO DE CIO — matrizes (tabela com caixas, por lote, com busca) → produto e dose → últimas induções.
// Estímulo hormonal (não é IATF, não é diagnóstico; é diferente de Indução de LACTAÇÃO) aplicado geralmente nos últimos dias do
// PEV para a vaca entrar em cio em 2 a 5 dias: gera histórico próprio e um lembrete "Observar cio" na Agenda, que some sozinho
// quando uma inseminação é lançada para o animal. Mesma língua do Diagnóstico de gestação (kit gerencial).
//
// A aptidão aqui é só INFORMATIVA (o servidor não trava a indução, porque ela não cria Serviço): quem a tela marcaria como
// inapta (idade mínima, a descartar, baixada) aparece com o selo "Confira" e o motivo, e continua marcável — evita mandar
// hormônio numa bezerra por engano sem tirar a decisão de quem está no curral.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Trash2 } from "lucide-react";
import { excluirInducaoCio, fetchInducoesCio, registrarInducaoCio, type InducaoCioLancamento } from "@/lib/api";
import { VIAS_APLICACAO } from "@/lib/constants";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { AnimalRow } from "@/components/AnimalModal";
import { EstoquePicker, type EstoqueItemPicker } from "@/components/EstoquePicker";
import type { EstoqueItem } from "@/components/lancamentos/comumForms";
import { useLinhasFemeas } from "@/components/lancamentos/useFemeasServico";
import { Ajuda, BarraAcao, BotaoOuro, Faixa, Passo, Pilulas } from "@/components/gerencial/kit";
import { BuscaMatrizes, EstiloRepro, PilulasX } from "@/components/gerencial/telas/ReprodutivoComum";
import { TabelaFemeas } from "@/components/gerencial/telas/TabelaFemeas";
import { alterna, alternaAptas, ehApta, filtraLinhas, ordenaNumero } from "@/lib/aptidaoServico";
import { CIO_DIAS_MAX, CIO_DIAS_MIN, PRODUTO_PADRAO_INDUCAO, estatisticasInducao, estoqueDepois, janelaCio, montarInducao, ultimaInducaoPorMatriz } from "@/lib/inducaoCio";
import { fmtData, hojeIso } from "@/lib/iatfCronograma";

const CSS = `
.ic-grade { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 13rem), 1fr)); gap: 0.75rem; align-items: end; }
.ic-cheio { grid-column: 1 / -1; }
`;

export function FormInducaoCio({ animais, estoque, motivosInaptidao, onSalvo }: {
  animais: AnimalRow[]; estoque: EstoqueItem[];
  // numero -> motivo de inaptidão a serviço. Aqui é só informativo (a indução de cio não cria Servico, então o backend não a
  // trava), mas a mesma marcação evita mandar hormônio numa bezerra por engano.
  motivosInaptidao?: Map<string, string>;
  onSalvo?: () => void;
}) {
  const [origem, setOrigem] = useState<"animais" | "lotes">("animais");
  const [lotesSel, setLotesSel] = useState<string[]>([]);
  const [filtro, setFiltro] = useState<"todas" | "pev">("todas");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [busca, setBusca] = useState("");

  const [dataAplicacao, setDataAplicacao] = useState(() => hojeIso());
  const [produto, setProduto] = useState(PRODUTO_PADRAO_INDUCAO);
  const [dose, setDose] = useState("");
  const [unidade, setUnidade] = useState("ml");
  const [via, setVia] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
  const [observacao, setObservacao] = useState("");

  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const [historico, setHistorico] = useState<InducaoCioLancamento[]>([]);
  const carregarHistorico = useCallback(() => fetchInducoesCio().then(setHistorico).catch(() => {}), []);
  useEffect(() => { carregarHistorico(); }, [carregarHistorico]);

  const estoqueParaPicker: EstoqueItemPicker[] = useMemo(
    () => estoque.map((e) => ({ nome: e.nome, unidade: e.unidade ?? null, quantidade: e.quantidade ?? null, finalidade: e.finalidade ?? null })),
    [estoque],
  );

  // ── fêmeas (aptidão só informativa) ───────────────────────────────────────────────────────────────────────────
  const linhas = useLinhasFemeas({ animais, api: null, motivosInaptidao, usarServidor: false });
  const ultimaInducao = useMemo(() => ultimaInducaoPorMatriz(historico), [historico]);
  const lotes = useMemo(() => {
    const m = new Map<string, number>();
    linhas.forEach((l) => m.set(l.lote, (m.get(l.lote) ?? 0) + 1));
    return [...m.entries()].sort(([a], [b]) => ordenaNumero(a, b));
  }, [linhas]);
  const nPev = useMemo(() => linhas.filter((l) => l.emPev).length, [linhas]);
  const base = useMemo(() => {
    const porLote = origem === "lotes" ? linhas.filter((l) => lotesSel.includes(l.lote)) : linhas;
    return filtro === "pev" ? porLote.filter((l) => l.emPev) : porLote;
  }, [origem, linhas, lotesSel, filtro]);
  const visiveis = useMemo(() => filtraLinhas(base, busca), [base, busca]);
  const nSel = sel.size;
  const nConfira = useMemo(() => linhas.filter((l) => sel.has(l.numero) && l.aptidao.nivel !== "apta").length, [linhas, sel]);
  const hoje = hojeIso();
  const stats = useMemo(() => estatisticasInducao(historico, hoje), [historico, hoje]);

  function alternaLote(lote: string) {
    const ativo = lotesSel.includes(lote);
    setLotesSel(ativo ? lotesSel.filter((l) => l !== lote) : [...lotesSel, lote]);
    // Escolher um lote marca as aptas dele (ajustável na tabela); tirar o lote desmarca as dele.
    const doLote = linhas.filter((l) => l.lote === lote);
    setSel((p) => {
      const s = new Set(p);
      doLote.forEach((l) => { if (ativo) s.delete(l.numero); else if (ehApta(l)) s.add(l.numero); });
      return s;
    });
  }

  async function salvar() {
    setErro(null); setSucesso(null);
    const m = montarInducao({ numeros: [...sel].sort(ordenaNumero), dataAplicacao, produto, dose, unidade, via, responsavel, observacao });
    if ("erro" in m) { setErro(m.erro); return; }
    setSalvando(true);
    try {
      const r = await registrarInducaoCio(m.payload);
      setSucesso(`${r.aplicados} ${r.aplicados === 1 ? "aplicação lançada" : "aplicações lançadas"} com sucesso.${r.avisos?.length ? " " + r.avisos.join(" ") : ""} Cio esperado em ${CIO_DIAS_MIN} a ${CIO_DIAS_MAX} dias — a Agenda vai lembrar de observar.`);
      setSel(new Set()); setLotesSel([]); setObservacao("");
      carregarHistorico();
      onSalvo?.();
    } catch (e) {
      setErro(e instanceof Error && e.message ? e.message : "Erro ao registrar indução de cio");
    } finally {
      setSalvando(false);
    }
  }

  async function excluir(id: number) {
    if (!confirm("Excluir este lançamento de indução de cio?")) return;
    try { await excluirInducaoCio(id); carregarHistorico(); } catch (e) { setErro(e instanceof Error ? e.message : "Erro ao excluir lançamento"); }
  }

  // ── resumo da barra ───────────────────────────────────────────────────────────────────────────────────────────
  const janela = janelaCio(dataAplicacao);
  const baixa = estoqueDepois(estoque, produto, dose, nSel);
  const resumo = `${nSel} ${nSel === 1 ? "matriz" : "matrizes"} · ${produto || "sem produto"}${dose ? ` ${dose} ${unidade}` : ""}`;
  const detalhe = !nSel ? "Marque ao menos uma matriz na tabela do passo 1"
    : !dataAplicacao ? "Falta a data da aplicação"
    : `Aplicação em ${fmtData(dataAplicacao)}${janela ? ` · cio esperado de ${fmtData(janela.de, true)} a ${fmtData(janela.ate, true)}` : ""}${baixa ? ` · baixa ${baixa.total} ${baixa.unidade} do estoque` : ""}${nConfira ? ` · ${nConfira} para conferir` : ""}`;

  const faixa = [
    { rotulo: "Fêmeas na lista", valor: linhas.length },
    { rotulo: "Em PEV", valor: nPev, tom: nPev ? ("ok" as const) : undefined },
    { rotulo: `Observando cio (até ${CIO_DIAS_MAX} dias)`, valor: stats.observando, tom: stats.observando ? ("atencao" as const) : undefined },
    { rotulo: "Induzidas em 30 dias", valor: stats.ultimos30 },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <EstiloRepro />
      <style>{CSS}</style>
      <Faixa itens={faixa} />
      <div style={{ marginBottom: "0.9rem" }}>
        <Ajuda>
          Estímulo hormonal (não é IATF, não é diagnóstico) aplicado geralmente nos últimos dias do PEV para a vaca entrar em cio em {CIO_DIAS_MIN} a {CIO_DIAS_MAX} dias — gera
          histórico próprio e um lembrete “Observar cio” na Agenda, que some sozinho assim que uma inseminação for lançada para o animal.
        </Ajuda>
      </div>

      <Passo n={1} id="ic-p1" titulo="Matrizes" direita={
        <span className="rp-contagem" aria-live="polite">{nSel} de {visiveis.length} {nSel === 1 ? "marcada" : "marcadas"}{nConfira > 0 && ` · ${nConfira} para conferir`}</span>
      }>
        <div className="rp-ferr">
          <PilulasX<"animais" | "lotes"> rotulo="Escolher por" valor={origem} onChange={(o) => { setOrigem(o); setLotesSel([]); }}
            opcoes={[{ id: "animais", nome: "Animais" }, { id: "lotes", nome: "Lotes", n: lotes.length }]} />
          <PilulasX<"todas" | "pev"> rotulo="Mostrar" valor={filtro} onChange={setFiltro}
            opcoes={[{ id: "todas", nome: "Todas", n: linhas.length }, { id: "pev", nome: "Só em PEV", n: nPev, titulo: "Vacas no período de espera voluntário — a indução costuma ser nos últimos dias dele" }]} />
          <BuscaMatrizes valor={busca} onChange={setBusca} />
          <button type="button" className="btn-ghost" onClick={() => setSel((p) => alternaAptas(p, visiveis))}>Marcar / desmarcar as aptas</button>
          <button type="button" className="btn-ghost" onClick={() => setSel(new Set())} disabled={!nSel}>Limpar</button>
        </div>
        {origem === "lotes" && (
          <Pilulas<string> rotulo="Lotes" valor={lotesSel} onChange={alternaLote} opcoes={lotes.map(([l, n]) => ({ id: l, nome: l, n }))} />
        )}
        <TabelaFemeas
          linhas={visiveis} sel={sel} altura="30rem" tituloAptidao="Conferência" rotuloConfirmar="Confira" carregando={!animais.length}
          colunaExtra={{ titulo: "Última indução", valor: (l) => (ultimaInducao.has(l.numero) ? fmtData(ultimaInducao.get(l.numero)!) : "—") }}
          vazio={origem === "lotes" && !lotesSel.length ? "Marque um ou mais lotes acima." : filtro === "pev" && !busca ? "Nenhuma vaca em PEV agora." : busca ? "Nenhuma fêmea bate com a busca." : "Nenhuma fêmea na lista."}
          onToggle={(n) => setSel((p) => alterna(p, n))}
          onToggleAptas={() => setSel((p) => alternaAptas(p, visiveis))}
          onToggleLote={(_l, itens) => setSel((p) => alternaAptas(p, itens))}
        />
        <Ajuda>
          A lista mostra <strong>todas as fêmeas</strong>. “Confira” marca quem o cadastro indica como inapta a serviço (idade mínima, a descartar, baixada) ou que consta gestante (PGF2α em vaca prenhe provoca aborto): é só informativo — a indução não é
          travada pelo servidor —, mas vale olhar antes de aplicar hormônio.
        </Ajuda>
      </Passo>

      <Passo n={2} id="ic-p2" titulo="Produto e dose">
        <div className="ic-grade">
          <div className="gv-campo">
            <label htmlFor="ic-data">Data da aplicação</label>
            <input id="ic-data" type="date" className="rp-input" value={dataAplicacao} onChange={(e) => setDataAplicacao(e.target.value)} />
          </div>
          <div className="gv-campo" role="group" aria-label="Produto">
            <span className="gv-rotulo" style={{ fontSize: "0.7rem" }}>Produto</span>
            <EstoquePicker itens={estoqueParaPicker} value={produto} onChange={setProduto} placeholder="Cloprostenol / PGF2α…" />
          </div>
          <div className="gv-campo">
            <label htmlFor="ic-dose">Dose (opcional)</label>
            <input id="ic-dose" type="number" inputMode="decimal" className="rp-input" value={dose} onChange={(e) => setDose(e.target.value)} />
          </div>
          <div className="gv-campo">
            <label htmlFor="ic-unidade">Unidade</label>
            <select id="ic-unidade" className="rp-select" value={unidade} onChange={(e) => setUnidade(e.target.value)} disabled={!dose}>
              <option value="ml">ml</option><option value="unidade">unidade</option><option value="dose">dose</option>
            </select>
          </div>
          <div className="gv-campo">
            <label htmlFor="ic-via">Via</label>
            <select id="ic-via" className="rp-select" value={via} onChange={(e) => setVia(e.target.value)}>
              <option value="">Selecione…</option>
              {VIAS_APLICACAO.map((o) => <option key={o}>{o}</option>)}
            </select>
          </div>
          <div className="gv-campo">
            <label htmlFor="ic-resp">Responsável</label>
            <select id="ic-resp" className="rp-select" value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
              <option value="">Selecione…</option>
              {nomesResponsaveis.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
          <div className="gv-campo ic-cheio">
            <label htmlFor="ic-obs">Observação (opcional)</label>
            <input id="ic-obs" className="rp-input" value={observacao} onChange={(e) => setObservacao(e.target.value)} />
          </div>
        </div>
        <Ajuda>
          Se dose e unidade forem informadas, dá baixa no estoque do produto ao salvar (a dose vale para cada matriz).
          {baixa && (
            <> Estoque de <strong>{produto}</strong>: <strong>{baixa.atual} {baixa.unidade}</strong> → depois de {nSel} {nSel === 1 ? "matriz" : "matrizes"}:{" "}
              <strong style={{ color: baixa.depois < 0 ? "var(--ft-verm)" : "var(--ft-verde)" }}>{baixa.depois} {baixa.unidade}</strong>
              {baixa.depois < 0 && <span style={{ color: "var(--ft-verm)" }}> (estoque insuficiente)</span>}.</>
          )}
        </Ajuda>
      </Passo>

      {historico.length > 0 && (
        <Passo n={3} id="ic-p3" titulo="Últimas induções lançadas">
          <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "16rem" }}>
            <table className="gv-tabela">
              <thead><tr>
                <th scope="col">Matriz</th><th scope="col">Data</th><th scope="col">Produto</th><th scope="col">Dose</th><th scope="col">Via</th><th scope="col">Responsável</th>
                <th scope="col" className="gv-dir"><span style={{ position: "absolute", left: "-9999px" }}>Excluir</span></th>
              </tr></thead>
              <tbody>
                {historico.slice(0, 10).map((h) => (
                  <tr key={h.id}>
                    <td className="gv-forte">{h.numero_matriz}</td>
                    <td className="gv-num">{h.data_aplicacao ? fmtData(h.data_aplicacao) : "—"}</td>
                    <td>{h.produto}</td>
                    <td className="gv-num">{h.dose != null ? `${h.dose} ${h.unidade || ""}` : "—"}</td>
                    <td>{h.via || "—"}</td>
                    <td>{h.responsavel || "—"}</td>
                    <td className="gv-dir">
                      <button type="button" className="rp-seta" title="Excluir este lançamento" aria-label={`Excluir a indução de ${h.numero_matriz} em ${h.data_aplicacao ?? "data não informada"}`}
                        onClick={() => excluir(h.id)} style={{ minWidth: "2rem", minHeight: "2rem", justifyContent: "center", alignItems: "center" }}>
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {historico.length > 10 && <Ajuda>Mostrando as 10 mais recentes de {historico.length}.</Ajuda>}
        </Passo>
      )}

      <BarraAcao
        resumo={resumo}
        detalhe={detalhe}
        retorno={(erro || sucesso) ? (
          <div className="rp-retorno-linha">
            {sucesso && <span className="rp-ok" role="status">✓ {sucesso}</span>}
            {erro && <span className="rp-err" role="alert">{erro}</span>}
          </div>
        ) : undefined}
        secundaria={<button type="button" className="btn-ghost" onClick={() => setSel(new Set())} disabled={!nSel}>Limpar</button>}
        acao={<BotaoOuro desabilitado={salvando || !nSel} onClick={salvar}>
          {salvando ? "Salvando…" : `Lançar ${nSel || ""} ${nSel === 1 ? "indução" : "induções"}`.replace("  ", " ")}
        </BotaoOuro>}
      />
    </div>
  );
}
