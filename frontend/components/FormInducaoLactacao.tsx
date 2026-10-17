"use client";
// Lançamentos › Produção › Indução de lactação — tela gerencial (kit components/gerencial/kit.tsx).
// Também roda no app de campo e em Protocolos: `salvarInducao` é a prop de injeção offline
// (retorno `{ enviado: false }` = "guardado, sem internet"; `{ criado: false, aviso }` = o servidor reaproveitou um lançamento idêntico).
// Regras puras (cronograma, em andamento, avisos de elegibilidade, payload) em lib/inducaoLactacao.ts, com testes.
//  · Os avisos de elegibilidade (já em indução, prenha, em lactação) só INFORMAM: não existe regra no servidor e o animal marcado é lançado.
//  · "gera N eventos na Agenda" é a conta que o servidor faz (dias distintos do cronograma × animais).
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { fetchProtocolosInducaoLactacao, lancarInducaoLactacao, fetchInducaoLactacaoAtivos } from "@/lib/api";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { useEstadosReprodutivos } from "@/lib/estadoReprodutivo";
import { casaBusca } from "@/lib/busca";
import { AnimalRow } from "@/components/AnimalModal";
import { Ajuda, Aviso, BarraAcao, BotaoOuro, Campo, Faixa, Passo, Pilulas, Selo } from "@/components/gerencial/kit";
import { CSS_RAIZ } from "@/components/gerencial/producaoCss";
import { dataBR, diasEntre, hojeLocal, mensagemDe, nb, plural, somarDias } from "@/lib/producaoGerencial";
import {
  avisosElegibilidade, celulaCronograma, diaInicioOrdenha, eventosNaAgenda, faixaDias, formatarIdade, indexarAtivosPorAnimal,
  linhasDoCronograma, linhasEmAndamento, montarPayloadInducao, nomeCurto, proximaOrdenha, resumoDoProtocolo, rotuloD,
  type DadosInducaoLactacao, type InducaoAtiva, type ProtocoloInducao,
} from "@/lib/inducaoLactacao";

type SalvarInducaoLactacao = (dados: DadosInducaoLactacao) => Promise<{ criado?: boolean; aviso?: string; animais?: number; eventos_criados?: number; enviado?: boolean }>;
type Aba = "lancar" | "andamento";
type Origem = "animal" | "lote";
type Retorno = { tipo: "ok" | "repetido" | "erro"; texto: string };
type Candidata = { a: AnimalRow; lote: string; categoria: string; avisos: string[] };

const SEM_LOTE = "Sem lote";
const ordemNumerica = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true });

const CSS = `
.gi-topo { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 0.2rem; }
.gi-cartoes { display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); gap: 0.6rem; }
.gi-cartoes .gv-cartao-opcao span { white-space: normal; }
.gi-linhatempo-moldura { border: 1px solid var(--border-strong, var(--border)); background: var(--surface); overflow-x: auto; }
.gi-tl { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 0.72rem; font-variant-numeric: tabular-nums; }
.gi-tl col.gi-rot { width: 16rem; }
.gi-tl thead th { background: var(--thead-bg); color: var(--thead-fg); font-size: 0.66rem; font-weight: 700; letter-spacing: 0.02em; padding: 0.3rem 0; text-align: center; border-left: 1px solid var(--border); }
.gi-tl thead tr:nth-child(2) th { font-weight: 400; padding-top: 0; padding-bottom: 0.3rem; font-size: 0.66rem; border-bottom: 1px solid var(--border-strong, var(--border)); }
.gi-tl thead th:first-child { text-align: left; padding-left: 0.6rem; border-left: 0; letter-spacing: 0.08em; text-transform: uppercase; }
.gi-tl thead th.gi-ordenha { box-shadow: inset 0 -2px 0 var(--ft-ouro); }
.gi-tl tbody th { text-align: left; font-weight: 600; font-size: 0.78rem; padding: 0.3rem 0.6rem; border-bottom: 1px solid var(--border); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gi-tl tbody th small { font-weight: 400; color: var(--text-muted); font-size: 0.7rem; margin-left: 0.25rem; }
.gi-tl tbody td { text-align: center; padding: 0.3rem 0; border-bottom: 1px solid var(--border); border-left: 1px solid var(--border); height: 1.9rem; }
.gi-tl td[data-tipo="medicamento"] { color: var(--ft-aco); font-weight: 800; background: color-mix(in srgb, var(--ft-aco) 9%, transparent); }
.gi-tl td[data-tipo="dispositivo"], .gi-tl td[data-tipo="manejo"] { color: var(--ft-ouro-txt); font-weight: 800; background: var(--ft-ouro-tint); }
.gi-legenda { display: flex; flex-wrap: wrap; gap: 0.3rem 1.2rem; font-size: 0.74rem; color: var(--text-muted); }
.gi-legenda b { font-weight: 800; color: var(--text); }
.gi-campos { display: grid; grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); gap: 0.75rem; align-items: start; max-width: 62rem; }
.gi-avisotxt { font-size: 0.78rem; color: var(--ft-ouro-txt); margin-left: 0.4rem; white-space: normal; }
.gi-botao-mini { min-height: 2.1rem; }
.gi-etapa { white-space: normal !important; }
`;

function Cronograma({ p, d0 }: { p: ProtocoloInducao; d0: string }) {
  const linhas = linhasDoCronograma(p);
  const ultimo = Math.max(p.dia_inicial, ...p.etapas.map((e) => e.dia));
  const dias = faixaDias(p.dia_inicial, ultimo);
  const ord = diaInicioOrdenha(p);
  return (
    <>
      <div className="gi-linhatempo-moldura">
        <table className="gi-tl" style={{ minWidth: `${16 + dias.length * 2}rem` }}>
          <colgroup><col className="gi-rot" />{dias.map((d) => <col key={d} />)}</colgroup>
          <thead>
            <tr>
              <th scope="col">Vai para a Agenda</th>
              {dias.map((d) => <th key={d} scope="col" className={d === ord ? "gi-ordenha" : undefined}>D{d}</th>)}
            </tr>
            <tr>
              <th scope="col" style={{ textTransform: "none", letterSpacing: 0, fontWeight: 400 }}>{d0 ? "Data de cada dia" : `Escolha a data do ${rotuloD(p)} para ver as datas`}</th>
              {dias.map((d) => <th key={d} scope="col">{d0 ? dataBR(somarDias(d0, d - p.dia_inicial), true) : ""}</th>)}
            </tr>
          </thead>
          <tbody>
            {linhas.map((l) => (
              <tr key={l.chave}>
                <th scope="row" title={l.rotulo}>{l.rotulo}{l.unidade && <small>({l.unidade})</small>}</th>
                {dias.map((d) => {
                  const e = l.porDia.get(d);
                  if (!e) return <td key={d} />;
                  const c = celulaCronograma(e);
                  return <td key={d} data-tipo={e.tipo} title={c.titulo} aria-label={c.titulo}>{c.texto}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="gi-legenda">
        <span><b>30</b> número = dose · <b>●</b> aplicação (uma dose)</span>
        <span><b>▼</b> colocar implante · <b>▲</b> retirar implante</span>
        <span><b>●</b> manejo · <b>▶</b> início da ordenha (sublinhado em ouro)</span>
      </div>
    </>
  );
}

function EmAndamento({ ativos, erro, protocolos, hoje, onTentar }: {
  ativos: InducaoAtiva[] | null; erro: boolean; protocolos: ProtocoloInducao[]; hoje: string; onTentar: () => void;
}) {
  if (erro) {
    return (
      <div className="gp-vazio" role="alert">
        <b>Não foi possível carregar as induções em andamento</b>
        <span>Confira a conexão e tente de novo.</span>
        <button type="button" className="btn-ghost" onClick={onTentar}>Tentar de novo</button>
      </div>
    );
  }
  if (!ativos) return <p className="gv-ajuda" role="status">Carregando as induções em andamento…</p>;
  if (!ativos.length) return <div className="gp-vazio"><b>Nenhuma indução de lactação em andamento</b><span>Lance a primeira na aba “Lançar indução”.</span></div>;
  const total = ativos.reduce((s, a) => s + a.animais.length, 0);
  return (
    <>
      <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "none" }}>
        <table className="gv-tabela">
          <thead>
            <tr>
              <th scope="col">Nº</th>
              <th scope="col" title="Primeira etapa ainda não confirmada na Agenda">Etapa atual</th>
              <th scope="col">Data da etapa</th><th scope="col">Dia do protocolo</th><th scope="col">Início da ordenha</th>
            </tr>
          </thead>
          <tbody>
            {ativos.map((a) => {
              const molde = protocolos.find((p) => p.id === a.protocolo_id);
              const linhas = linhasEmAndamento(a, molde);
              return (
                <React.Fragment key={a.lancamento_id}>
                  <tr className="gv-grupo"><th scope="rowgroup" colSpan={5}>{a.nome_protocolo} · D0 em {dataBR(a.data_d0)} · {a.animais.length} {plural(a.animais.length, "animal", "animais")}</th></tr>
                  {linhas.map((l) => (
                    <tr key={l.numero}>
                      <td className="gv-forte gv-num">{l.numero}</td>
                      <td className="gi-etapa">{l.etapa}{l.descricao ? ` · ${l.descricao}` : ""}</td>
                      <td className="gv-num">{l.dataEtapa ? dataBR(l.dataEtapa) : "—"}</td>
                      <td className="gv-num">{l.diaProtocolo}</td>
                      <td className="gv-num">
                        {l.ordenha ? (
                          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
                            {dataBR(l.ordenha)}
                            {diasEntre(hoje, l.ordenha) <= 0 ? <Selo tom="ok">Já começou</Selo> : diasEntre(hoje, l.ordenha) <= 3 ? <Selo tom="atencao">Em {diasEntre(hoje, l.ordenha)} {plural(diasEntre(hoje, l.ordenha), "dia", "dias")}</Selo> : null}
                          </span>
                        ) : "—"}
                      </td>
                    </tr>
                  ))}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <Ajuda>{ativos.length} {plural(ativos.length, "indução em andamento", "induções em andamento")}, {total} {plural(total, "animal", "animais")}. A etapa atual é a primeira que ainda não foi confirmada na Agenda; o que vem a seguir está lá.</Ajuda>
    </>
  );
}

export function FormInducaoLactacao({ animais, salvarInducao = lancarInducaoLactacao }: { animais: AnimalRow[]; salvarInducao?: SalvarInducaoLactacao }) {
  const hoje = hojeLocal();
  const [aba, setAba] = useState<Aba>("lancar");
  const [protocolos, setProtocolos] = useState<ProtocoloInducao[]>([]);
  const [protocolosCarregados, setProtocolosCarregados] = useState(false);
  const [protocoloId, setProtocoloId] = useState("");
  const [dataD0, setDataD0] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [observacao, setObservacao] = useState("");
  const [origem, setOrigem] = useState<Origem>("lote");
  const [lotes, setLotes] = useState<Set<string>>(new Set());
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [busca, setBusca] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [retorno, setRetorno] = useState<Retorno | null>(null);
  const [ativos, setAtivos] = useState<InducaoAtiva[] | null>(null);
  const [erroAtivos, setErroAtivos] = useState(false);
  const { pessoas: pessoasAtivas } = usePessoasAtivas();
  const { porNumero, rotuloDe } = useEstadosReprodutivos();

  const carregarAtivos = useCallback(() => {
    fetchInducaoLactacaoAtivos()
      .then((d) => { setAtivos(Array.isArray(d) ? d : []); setErroAtivos(false); })
      .catch(() => { setAtivos((a) => a ?? []); setErroAtivos(true); });
  }, []);
  useEffect(() => {
    fetchProtocolosInducaoLactacao().then((d) => setProtocolos(Array.isArray(d) ? d : [])).catch(() => setProtocolos([])).finally(() => setProtocolosCarregados(true));
    carregarAtivos();
  }, [carregarAtivos]);

  const protocolo = protocolos.find((p) => String(p.id) === protocoloId);
  const rotulo = rotuloD(protocolo);
  const emInducao = useMemo(() => indexarAtivosPorAnimal(ativos ?? []), [ativos]);

  const candidatas: Candidata[] = useMemo(() => animais.map((a) => ({
    a, lote: a.grupo_primario || SEM_LOTE, categoria: a.categoria_completa || a.categoria_abrev || "—",
    avisos: avisosElegibilidade(a, porNumero.get(a.numero), emInducao.get(a.numero)),
  })), [animais, porNumero, emInducao]);

  const todosLotes = useMemo(() => {
    const c = new Map<string, number>();
    candidatas.forEach((x) => c.set(x.lote, (c.get(x.lote) ?? 0) + 1));
    return [...c.entries()].sort((a, b) => ordemNumerica(a[0], b[0]));
  }, [candidatas]);

  const visiveis = useMemo(() => candidatas.filter((x) =>
    (origem === "animal" || lotes.has(x.lote)) && casaBusca(`${x.a.numero} ${x.lote} ${x.categoria}`, busca)), [candidatas, origem, lotes, busca]);
  const grupos = useMemo(() => {
    const m = new Map<string, Candidata[]>();
    visiveis.forEach((x) => m.set(x.lote, [...(m.get(x.lote) ?? []), x]));
    return [...m.entries()].sort((a, b) => ordemNumerica(a[0], b[0]));
  }, [visiveis]);

  const marcados = candidatas.filter((x) => sel.has(x.a.numero));
  const n = marcados.length;
  const comAviso = marcados.filter((x) => x.avisos.length).length;
  const semAvisoTotal = candidatas.filter((x) => !x.avisos.length).length;
  const visSemAviso = visiveis.filter((x) => !x.avisos.length);
  const todosSemAvisoMarcados = visSemAviso.length > 0 && visSemAviso.every((x) => sel.has(x.a.numero));

  const alternar = (num: string) => setSel((p) => { const s = new Set(p); if (s.has(num)) s.delete(num); else s.add(num); return s; });
  const alternarLote = (lote: string) => {
    const doLote = candidatas.filter((x) => x.lote === lote).map((x) => x.a.numero);
    const ativo = lotes.has(lote);
    setLotes((p) => { const s = new Set(p); if (ativo) s.delete(lote); else s.add(lote); return s; });
    setSel((p) => { const s = new Set(p); doLote.forEach((num) => (ativo ? s.delete(num) : s.add(num))); return s; });
  };
  const alternarTodosSemAviso = () => setSel((p) => { const s = new Set(p); visSemAviso.forEach((x) => (todosSemAvisoMarcados ? s.delete(x.a.numero) : s.add(x.a.numero))); return s; });

  // Faixa: estado das induções em andamento e do universo de candidatas.
  const linhasAnd = useMemo(() => (ativos ?? []).flatMap((a) => linhasEmAndamento(a, protocolos.find((p) => p.id === a.protocolo_id))), [ativos, protocolos]);
  const emAnd = (ativos ?? []).reduce((s, a) => s + a.animais.length, 0);
  const proxima = proximaOrdenha(linhasAnd.map((l) => l.ordenha), hoje);

  const faltam = [!protocolo && "o protocolo", !dataD0 && `a data do ${rotulo}`, n === 0 && "ao menos um animal"].filter(Boolean) as string[];
  const eventos = protocolo ? eventosNaAgenda(protocolo, n) : null;
  const resumo = n === 0 ? "Nenhum animal marcado"
    : `${n} ${plural(n, "animal", "animais")} · ${protocolo ? `protocolo ${protocolo.duracao_dias} dias · gera ${eventos} ${plural(eventos ?? 0, "evento", "eventos")} na Agenda` : "escolha o protocolo"}`;
  const detalhe = faltam.length ? `Falta escolher ${faltam.join(", ")}.`
    : `${rotulo} em ${dataBR(dataD0)}${responsavel ? ` · responsável: ${responsavel}` : ""}${comAviso ? ` · ${comAviso} com aviso de elegibilidade — pode lançar mesmo assim` : ""}`;

  async function salvar() {
    setRetorno(null);
    const p = montarPayloadInducao({ protocoloId, protocolo, animais: marcados.map((x) => x.a.numero), dataD0, responsavel, observacao });
    if ("erro" in p) { setRetorno({ tipo: "erro", texto: p.erro }); return; }
    setSalvando(true);
    try {
      const r = await salvarInducao(p.dados);
      // `criado: false` = o backend achou um lançamento ativo idêntico (mesmo protocolo, mesmo D0, mesmos animais) e reaproveitou em vez de
      // duplicar — duplo clique ou retry da fila offline. Sem este ramo a tela diria "0 eventos na Agenda", que parece defeito.
      if (r.enviado === false) setRetorno({ tipo: "ok", texto: "Sem internet — guardado, será enviado quando conectar." });
      else if (r.criado === false) setRetorno({ tipo: "repetido", texto: r.aviso || "Este protocolo já estava lançado para estes animais nesta data — nada foi duplicado." });
      else setRetorno({ tipo: "ok", texto: `Protocolo “${protocolo ? nomeCurto(protocolo.nome) : ""}” lançado para ${r.animais ?? p.dados.animais.length} ${plural(r.animais ?? p.dados.animais.length, "animal", "animais")} — ${r.eventos_criados ?? 0} ${plural(r.eventos_criados ?? 0, "evento", "eventos")} na Agenda.` });
      setSel(new Set()); setLotes(new Set());
      if (r.enviado !== false) carregarAtivos();
    } catch (e) {
      setRetorno({ tipo: "erro", texto: mensagemDe(e, "Erro ao lançar indução de lactação") });
    } finally {
      setSalvando(false);
    }
  }

  const retornoNode = aba === "lancar" && retorno ? (
    retorno.tipo === "ok"
      ? <><span role="status" className="gp-ok">✓ {retorno.texto}</span><button type="button" className="btn-ghost gi-botao-mini" onClick={() => setAba("andamento")}>Ver em andamento</button></>
      : retorno.tipo === "repetido" ? <Aviso>{retorno.texto}</Aviso>
      : <span role="alert" className="gp-erro">{retorno.texto}</span>
  ) : undefined;

  return (
    <div className="gp-raiz">
      <style>{CSS_RAIZ + CSS}</style>
      <Faixa itens={[
        { rotulo: "Induções em andamento", valor: ativos ? ativos.length : "—" },
        { rotulo: "Animais em indução", valor: ativos ? emAnd : "—" },
        { rotulo: "Próxima ordenha a iniciar", valor: proxima ? dataBR(proxima, true) : "—" },
        { rotulo: "Candidatas sem aviso", valor: `${semAvisoTotal} de ${candidatas.length}` },
      ]} />
      <div className="gi-topo">
        <Pilulas<Aba> rotulo="Tela" valor={aba} onChange={setAba}
          opcoes={[{ id: "lancar", nome: "Lançar indução" }, { id: "andamento", nome: "Em andamento", n: ativos?.length }]} />
      </div>

      {aba === "andamento" ? (
        <Passo n={1} id="il-and" titulo="Induções em andamento">
          <EmAndamento ativos={ativos} erro={erroAtivos} protocolos={protocolos} hoje={hoje} onTentar={carregarAtivos} />
        </Passo>
      ) : (
        <>
          <Passo n={1} id="il-p1" titulo="Protocolo">
            {protocolosCarregados && protocolos.length === 0 ? (
              <Aviso>Nenhum protocolo de indução de lactação ativo. Cadastre em Configurações › Cadastro › Sanitário › Indução de lactação.</Aviso>
            ) : (
              <div className="gi-cartoes" role="group" aria-label="Protocolo de indução">
                {protocolos.map((p) => (
                  <button key={p.id} type="button" className="gv-cartao-opcao" aria-pressed={protocoloId === String(p.id)} onClick={() => setProtocoloId(String(p.id))}>
                    <b>{nomeCurto(p.nome)} · {p.duracao_dias} dias</b>
                    <span>{resumoDoProtocolo(p) || p.nome}</span>
                  </button>
                ))}
              </div>
            )}
            {protocolo && (
              <>
                <Cronograma p={protocolo} d0={dataD0} />
                {protocolo.observacao && <Ajuda>{protocolo.observacao}</Ajuda>}
              </>
            )}
          </Passo>

          <Passo n={2} id="il-p2" titulo="Quando começa e quem aplica">
            <div className="gi-campos">
              <Campo rotulo={`Data do ${rotulo} · 1º dia (obrigatória)`} id="il-d0">
                <input type="date" value={dataD0} onChange={(e) => setDataD0(e.target.value)} />
              </Campo>
              <Campo rotulo="Responsável (opcional)" id="il-resp">
                <select value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
                  <option value="">Não informar</option>
                  {pessoasAtivas.map((p) => <option key={p.id ?? p.nome} value={p.nome}>{p.nome}</option>)}
                </select>
              </Campo>
              <Campo rotulo="Observação (opcional)" id="il-obs">
                <input type="text" value={observacao} onChange={(e) => setObservacao(e.target.value)} placeholder="Ex.: lote em piquete de adaptação" />
              </Campo>
            </div>
          </Passo>

          <Passo n={3} id="il-p3" titulo="Animais" direita={<span className="gp-contagem" aria-live="polite">{n} marcados · {visiveis.length} na lista</span>}>
            <div className="gv-linha" style={{ justifyContent: "space-between" }}>
              <Pilulas<Origem> rotulo="Escolher por" valor={origem} onChange={setOrigem}
                opcoes={[{ id: "animal", nome: "Animal por animal", titulo: "Selecionar matrizes individualmente" }, { id: "lote", nome: "Lotes", titulo: "Selecionar um ou mais lotes — já vêm todos marcados" }]} />
              <div className="gp-busca">
                <Search size={14} aria-hidden="true" />
                <input type="search" aria-label="Buscar matriz ou lote" placeholder="Buscar matriz ou lote" value={busca} onChange={(e) => setBusca(e.target.value)} />
              </div>
            </div>
            {origem === "lote" && (
              <div className="gv-linha" role="group" aria-label="Lotes">
                {todosLotes.map(([l, c]) => (
                  <button key={l} type="button" className="ft-pilula" aria-pressed={lotes.has(l)} onClick={() => alternarLote(l)}>{l}<b>{c}</b></button>
                ))}
              </div>
            )}
            {visiveis.length === 0 ? (
              <Ajuda>{animais.length === 0 ? "Nenhum animal disponível para indução." : origem === "lote" && lotes.size === 0 ? "Marque um ou mais lotes acima — os animais do lote já vêm marcados." : "Nenhum animal bate com a busca."}</Ajuda>
            ) : (
              <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "19rem" }}>
                <table className="gv-tabela">
                  <thead>
                    <tr>
                      <th scope="col" style={{ width: "2.4rem" }}>
                        <input type="checkbox" checked={todosSemAvisoMarcados} onChange={alternarTodosSemAviso} disabled={visSemAviso.length === 0} aria-label="Selecionar todos os que estão sem aviso" />
                      </th>
                      <th scope="col">Nº</th><th scope="col">Categoria</th><th scope="col">Lote</th>
                      <th scope="col">Situação reprodutiva</th><th scope="col">Idade</th><th scope="col">Aviso de elegibilidade</th>
                    </tr>
                  </thead>
                  <tbody>
                    {grupos.map(([lote, itens]) => (
                      <React.Fragment key={lote}>
                        <tr className="gv-grupo"><th scope="rowgroup" colSpan={7}>{lote} · {itens.length}</th></tr>
                        {itens.map((x) => (
                          <tr key={x.a.numero} className={sel.has(x.a.numero) ? "gv-linha-marcada" : undefined}>
                            <td><input type="checkbox" checked={sel.has(x.a.numero)} onChange={() => alternar(x.a.numero)} aria-label={`Selecionar ${x.a.numero}`} /></td>
                            <td className="gv-forte gv-num">{x.a.numero}</td>
                            <td>{x.categoria}</td>
                            <td>{x.lote}</td>
                            <td>{rotuloDe(x.a.numero)}</td>
                            <td className="gv-num">{formatarIdade(x.a.idade_meses)}</td>
                            <td>{x.avisos.length ? <><Selo tom="atencao">Atenção</Selo><span className="gi-avisotxt">{x.avisos.join(" · ")}</span></> : <Selo tom="neutro">Sem aviso</Selo>}</td>
                          </tr>
                        ))}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <Ajuda>
              Os avisos <strong>só informam</strong>: o animal marcado é lançado mesmo assim. Critérios sugeridos, a confirmar com o dono: já em indução, prenha ou em lactação.
              “Selecionar todos” marca só os que estão sem aviso.
            </Ajuda>
          </Passo>
        </>
      )}

      <BarraAcao
        resumo={aba === "andamento" ? (ativos ? `${ativos.length} ${plural(ativos.length, "indução em andamento", "induções em andamento")} · ${nb(emAnd)} ${plural(emAnd, "animal", "animais")}` : "Carregando…") : resumo}
        detalhe={aba === "andamento" ? "A Agenda mostra o que aplicar em cada dia." : detalhe}
        retorno={retornoNode}
        acao={aba === "andamento"
          ? <BotaoOuro onClick={() => setAba("lancar")}>Lançar nova indução</BotaoOuro>
          : <BotaoOuro desabilitado={faltam.length > 0 || salvando} onClick={salvar}>{salvando ? "Lançando…" : "Lançar indução"}</BotaoOuro>}
      />
    </div>
  );
}
