"use client";
// Lançamentos › Produção › Secagem — PROPOSTA de tela gerencial (variante desktop, só apresentação, dados de exemplo).
// Substitui components/FormSecagem.tsx (dois painéis com rolagem própria, 8 grupos de campos, radios sem `name`, modais de
// escolha de vaca que viram pílulas). Aqui: 4 passos numerados em UMA coluna; vacas em TABELA agrupada por lote; produtos
// e vacina pré-parto em divulgação progressiva; decisões (já consta como seca / lote sugerido) e o resultado dentro da barra.
// A versão ligada a dados (e as outras entradas: FormSecagem em RelatoriosManejo com `numeroInicial`; app de campo com
// `salvarSecagem`/`salvarMovimentacao` injetados) precisa PRESERVAR:
//  • Props: animais, estoque, produtos, numeroInicial (pré-seleciona a vaca vinda de Listas › Previsão de secagem),
//    salvarSecagem (resposta { lote_sugerido?, enviado? } — offline não traz sugestão; "guardado, será enviado quando conectar"),
//    salvarMovimentacao ({ movidos, nao_encontrados, enviado? }; origem "sugestao_confirmada" | "sugestao_automatica").
//  • Só vacas em lactação (animalEmLactacao). Animal(is) ou lote(s); LOTE COMEÇA SEM NINGUÉM MARCADO, de propósito (trocar de lote zera).
//  • GET /producao/secagem-info?numero (DEL, dias de gestação, data prevista = 60 d antes do parto, deve_secar, motivo_exclusao):
//    com UMA vaca marcada, preenche a data com a prevista; aviso/motivo_exclusao só informa (não bloqueia).
//  • POST /producao/secagem por vaca, uma de cada vez (falhou = volta marcada; o que já salvou não se perde), com
//    { numero_matriz, data_secagem (pode ser retroativa), motivo (obrigatório: doente | baixa_producao | comportamento | mastite | casco |
//    rotina | outros), escore_condicao_corporal (1–5, passo 0,25, opcional), responsavel, observacao, aplicado, produtos:[{produto, via,
//    quantidade, unidade}], vacinas_pre_parto[], vacina_pre_parto_aplicada_agora, vacina_pre_parto }.
//  • Produtos: vários; unidade compatível com a do estoque (unidadesCompativeis); dosagem "por vaca" (padrão) ou "total" (divide pelo
//    nº de vacas antes de enviar); estoque restante com alerta de insuficiente (informa, não bloqueia); data futura ⇒ `aplicado=false`
//    (programa na Agenda, não baixa estoque); senão "Aplicados agora?" Sim (baixa) / Não (só programa).
//  • Vacina pré-parto: Não/Sim; Sim exige ≥ 1 vacina (botão Salvar desabilitado e aviso); "incluir itens sem estoque" refaz a lista
//    (fetchMedicamentos finalidade vacina_pre_parto); "já aplicada agora" = registra em Sanidade e baixa estoque, senão cria pendência
//    na Agenda no dia seguinte.
//  • Conflito 409 "já consta como seca" (ErroApi.secagemAnterior {id, data_secagem, motivo}): PAUSA a fila; Substituir reenvia com
//    `substituir_secagem_id`; Cancelar pula só essa vaca e a fila continua.
//  • Pós-salvar: lote sugerido por vaca (r.lote_sugerido; só se a vaca ainda não está no lote), um a um (confirmação) OU automático
//    (fetchTransferenciaLoteAutomatica, Configurações › Parâmetros); falhados voltam marcados com o formulário preenchido.
import React, { useMemo, useState } from "react";
import { CalendarClock, Info, Plus, Search, Trash2 } from "lucide-react";
import { Ajuda, Aviso, BarraAcao, BotaoOuro, Campo, Faixa, Passo, Pilulas, QuadroGaveta, Selo } from "@/components/gerencial/kit";
import { LinhaGrupo, RotuloMini, dataBR, diasEntre, nb, semente, somarDias, HOJE_ISO } from "./utilProducao";

type Cenario = "conflito" | "retorno";
type Vaca = { n: string; lote: string; del: number; gest: number | null; prev: string | null; dias: number | null };
type Item = { produto: string; via: string; qtd: string; un: string; modo: "por_vaca" | "total" };
type Andamento = "lancada" | "conflito" | "falhou" | "fila";

const LOTES = [
  { id: "01 - Novilhas Alta", n: 11, del: [40, 180] },
  { id: "02 - Vacas Alta", n: 52, del: [60, 200] },
  { id: "03 - Vacas Média", n: 62, del: [200, 330] },
  { id: "04 - Pós-parto/Tratamento", n: 17, del: [2, 24] },
];
const FIXAS: Record<string, { lote: string; del: number; gest: number }> = {
  "11153": { lote: "02 - Vacas Alta", del: 248, gest: 214 },
  "3335": { lote: "02 - Vacas Alta", del: 271, gest: 231 },
  "4410": { lote: "02 - Vacas Alta", del: 259, gest: 218 },
  "075": { lote: "03 - Vacas Média", del: 262, gest: 221 },
  "9378": { lote: "03 - Vacas Média", del: 240, gest: 205 },
  "7120": { lote: "03 - Vacas Média", del: 268, gest: 226 },
};
const GESTACAO_DIAS = 280, ANTES_DO_PARTO = 60;
const SELECAO_INICIAL = ["11153", "3335", "4410", "075", "9378", "7120"]; // na ordem em que a fila é processada

const VACAS: Vaca[] = (() => {
  const r = semente(404);
  const vistos = new Set(Object.keys(FIXAS));
  const mk = (n: string, lote: string, del: number, gest: number | null): Vaca => {
    const dias = gest === null ? null : GESTACAO_DIAS - ANTES_DO_PARTO - gest;
    return { n, lote, del, gest, dias, prev: dias === null ? null : somarDias(HOJE_ISO, dias) };
  };
  const out: Vaca[] = [];
  for (const L of LOTES) {
    const fixas = Object.entries(FIXAS).filter(([, f]) => f.lote === L.id);
    fixas.forEach(([n, f]) => out.push(mk(n, L.id, f.del, f.gest)));
    for (let i = fixas.length; i < L.n; i++) {
      let n = String(1000 + Math.floor(r() * 8999));
      while (vistos.has(n)) n = String(1000 + Math.floor(r() * 8999));
      vistos.add(n);
      const p = r();
      const posParto = L.id.startsWith("04");
      const gest = posParto ? null : p < 0.1 ? Math.round(185 + r() * 70) : p < 0.62 ? Math.round(35 + r() * 145) : null;
      const del = gest !== null ? Math.round(gest + 40 + r() * 45) : Math.round(L.del[0] + r() * (L.del[1] - L.del[0]));
      out.push(mk(n, L.id, del, gest));
    }
  }
  return out;
})();
const ATRASADAS = VACAS.filter((v) => v.dias !== null && v.dias < 0);
const PROXIMAS = VACAS.filter((v) => v.dias !== null && v.dias <= 30);

const MOTIVOS = [
  { v: "doente", l: "Animal doente" }, { v: "baixa_producao", l: "Baixa produção" }, { v: "comportamento", l: "Comportamento" },
  { v: "mastite", l: "Mastite" }, { v: "casco", l: "Problema de casco" }, { v: "rotina", l: "Rotina parto" }, { v: "outros", l: "Outros" },
];
const ESTOQUE: Record<string, { q: number; un: string }> = {
  "Cepravin Vaca Seca (cefalônio)": { q: 64, un: "unidade" },
  "Orbeseal (selante de teta)": { q: 5, un: "unidade" },
  "Vitamina E + Selênio": { q: 400, un: "ml" },
  "Ivermectina 1%": { q: 900, un: "ml" },
};
const VIAS = ["Intramuscular", "Subcutânea", "Intramamária", "Oral", "Tópica"];
const UNIDADES = ["ml", "unidade", "dose"];
const VACINAS = [
  { nome: "Rotavec Corona (pré-parto)", q: 40, un: "dose" },
  { nome: "Bovigen Scour", q: 22, un: "dose" },
  { nome: "Mastivac I", q: 0, un: "dose" },
];
const RESPONSAVEIS = ["Jairo Nasser", "Equipe do curral", "Veterinário da fazenda"];

const th = { textAlign: "right" as const };
const BTN: React.CSSProperties = { display: "inline-flex", alignItems: "center", gap: "0.4rem" };
const altura = { ["--gv-altura-tabela" as string]: "44rem" } as React.CSSProperties;
const alturaLivre = { ["--gv-altura-tabela" as string]: "none" } as React.CSSProperties;
const fieldsetLimpo: React.CSSProperties = { accentColor: "var(--ft-ouro)", border: 0, padding: 0, margin: 0, display: "flex", gap: "0.9rem", flexWrap: "wrap", alignItems: "center" };
const rotuloRadio: React.CSSProperties = { display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", cursor: "pointer", minHeight: "1.9rem" };

function SeloSituacao({ v }: { v: Vaca }) {
  if (v.dias === null) return <Selo tom="info" titulo="Sem data de parto não dá para calcular a secagem">Sem prenhez confirmada</Selo>;
  if (v.dias < 0) return <Selo tom="atencao">Atrasada {-v.dias} d</Selo>;
  if (v.dias === 0) return <Selo tom="ok">Hoje</Selo>;
  if (v.dias <= 7) return <Selo tom="ok">Em {v.dias} d</Selo>;
  return <Selo tom="neutro">Em {v.dias} d</Selo>;
}

function SeloAndamento({ a }: { a: Andamento }) {
  if (a === "lancada") return <Selo tom="ok">✓ Lançada</Selo>;
  if (a === "conflito") return <Selo tom="bloqueio" titulo="Esta vaca já tem secagem lançada: decida abaixo">Já consta como seca</Selo>;
  if (a === "falhou") return <Selo tom="bloqueio">Falhou · tente de novo</Selo>;
  return <Selo tom="neutro">Na fila</Selo>;
}

/** Retorno com a decisão pendente (fila de secagem pausada numa vaca que já consta como seca). */
function RetornoConflito({ feitas, total }: { feitas: string[]; total: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", width: "100%" }}>
      <span role="status" style={{ color: "var(--ft-verde)" }}>✓ {feitas.length} de {total} lançadas ({feitas.join(", ")}) · fila pausada na 4410</span>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
        <Selo tom="bloqueio">Já consta como seca</Selo>
        <span style={{ flex: 1, minWidth: "20rem" }}>
          A vaca <b>4410</b> já tem secagem lançada em <b>02/10/2026</b> (rotina parto) — não há lactação aberta em {dataBR(HOJE_ISO)}.
          Se aquela foi lançada errada, substitua pela data de agora; se foi a certa, cancele só esta vaca (as demais continuam).
        </span>
        <button type="button" className="btn-ghost">Cancelar este lançamento</button>
        <button type="button" className="btn-primary">Substituir a secagem de 02/10/2026</button>
      </div>
    </div>
  );
}

/** Retorno final: contagem, o que baixou do estoque, o que foi para a Agenda, falhados e sugestão de lote (um a um). */
function RetornoFinal() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem", width: "100%" }}>
      <span role="status" style={{ color: "var(--ft-verde)" }}>
        ✓ Secagem lançada para 4 vacas (11153, 3335, 075, 9378) em {dataBR(HOJE_ISO)} · baixa no estoque: Cepravin −4 un, Orbeseal −4 un
      </span>
      <span style={{ color: "var(--text-muted)", display: "block" }}>
        <CalendarClock size={13} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4, display: "inline" }} />{" "}
        Agenda: pendência da vacina pré-parto em 18/10/2026 para as 4 vacas (aplicação ainda não feita, sem baixa).
        Cancelado sem lançar: 4410 (já constava como seca).
      </span>
      <span role="alert" style={{ color: "var(--ft-verm)" }}>
        Falhou: 7120 — voltou marcada abaixo, com o formulário preenchido, para tentar de novo só ela.
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap", paddingTop: "0.45rem", borderTop: "1px solid var(--border)" }}>
        <Selo tom="atencao">Lote sugerido</Selo>
        <span style={{ flex: 1, minWidth: "18rem" }}>
          Mover a vaca <b>11153</b> para <b>05 - Secas</b>?{" "}
          <span style={{ color: "var(--text-muted)" }}>Mais 3 na fila depois desta. Para mover sem perguntar: Configurações › Parâmetros › transferir automaticamente.</span>
        </span>
        <button type="button" className="btn-ghost">Agora não</button>
        <button type="button" className="btn-primary">Sim, mover</button>
      </div>
    </div>
  );
}

export function Secagem({ cenario = "conflito", numeroInicial }: { cenario?: Cenario; numeroInicial?: string }) {
  const final = cenario === "retorno";
  const lancadas = final ? ["11153", "3335", "075", "9378"] : ["11153", "3335"];
  const [modo, setModo] = useState<"animal" | "lote">("animal");
  const [mostrar, setMostrar] = useState<"proximas" | "todas" | "atrasadas">("proximas");
  const [busca, setBusca] = useState("");
  const [lotesSel, setLotesSel] = useState<string[]>([]);
  const [sel, setSel] = useState<Set<string>>(() => new Set(numeroInicial ? [numeroInicial] : final ? ["7120"] : SELECAO_INICIAL));

  const [data, setData] = useState(HOJE_ISO);
  const [motivo, setMotivo] = useState("rotina");
  const [ecc, setEcc] = useState("3.25");
  const [responsavel, setResponsavel] = useState("Equipe do curral");
  const [obs, setObs] = useState("");

  const [itens, setItens] = useState<Item[]>([
    { produto: "Cepravin Vaca Seca (cefalônio)", via: "Intramamária", qtd: "1", un: "unidade", modo: "por_vaca" },
    { produto: "Orbeseal (selante de teta)", via: "Intramamária", qtd: "1", un: "unidade", modo: "por_vaca" },
  ]);
  const [aplicado, setAplicado] = useState(true);
  const [vacinaSim, setVacinaSim] = useState(true);
  const [semEstoque, setSemEstoque] = useState(false);
  const [vacinasSel, setVacinasSel] = useState<string[]>(["Rotavec Corona (pré-parto)"]);
  const [vacinaAgora, setVacinaAgora] = useState(false);
  const [retorno, setRetorno] = useState<React.ReactNode>(
    final ? <RetornoFinal /> : <RetornoConflito feitas={lancadas} total={SELECAO_INICIAL.length} />,
  );

  // Quem já foi processado some da lista (deixou de estar em lactação) — só no retorno final.
  const base = useMemo(() => VACAS.filter((v) => !(final && lancadas.includes(v.n))), [final]); // eslint-disable-line react-hooks/exhaustive-deps
  const linhas = useMemo(() => {
    let r = modo === "lote" ? base.filter((v) => lotesSel.includes(v.lote)) : base;
    if (modo === "animal") {
      if (mostrar === "proximas") r = r.filter((v) => v.dias !== null && v.dias <= 30);
      if (mostrar === "atrasadas") r = r.filter((v) => v.dias !== null && v.dias < 0);
    }
    if (busca.trim()) r = r.filter((v) => v.n.includes(busca.trim()));
    return [...r].sort((a, b) => a.lote.localeCompare(b.lote, "pt-BR", { numeric: true }) || (a.dias ?? 999) - (b.dias ?? 999));
  }, [base, modo, mostrar, lotesSel, busca]);
  const grupos = useMemo(() => {
    const m = new Map<string, Vaca[]>();
    linhas.forEach((v) => m.set(v.lote, [...(m.get(v.lote) ?? []), v]));
    return [...m.entries()];
  }, [linhas]);

  const andamentoDe = (n: string): Andamento | null => {
    if (final) return n === "7120" ? "falhou" : n === "4410" ? "conflito" : null;
    if (!sel.has(n)) return null;
    if (lancadas.includes(n)) return "lancada";
    return n === "4410" ? "conflito" : "fila";
  };

  const marcadas = [...sel];
  const nVacas = sel.size;
  const alternar = (n: string) => setSel((p) => {
    const s = new Set(p);
    if (s.has(n)) s.delete(n); else s.add(n);
    if (s.size === 1) { const v = VACAS.find((x) => x.n === [...s][0]); if (v?.prev) setData(v.prev); }
    return s;
  });
  const marcarAtrasadas = () => setSel((p) => new Set([...p, ...linhas.filter((v) => v.dias !== null && v.dias < 0).map((v) => v.n)]));
  const trocarLotes = (id: string) => { setLotesSel((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id])); setSel(new Set()); };

  const unico = nVacas === 1 ? VACAS.find((v) => v.n === marcadas[0]) : undefined;
  const futura = data > HOJE_ISO;
  const itensValidos = itens.filter((i) => i.produto && Number(i.qtd) > 0);
  const baixa = aplicado && !futura;
  const vacinaInvalida = vacinaSim && vacinasSel.length === 0;
  const motivoRotulo = MOTIVOS.find((m) => m.v === motivo)?.l.toLowerCase();
  const podeSalvar = nVacas > 0 && !!motivo && !vacinaInvalida && !!data;

  const atualizarItem = (i: number, p: Partial<Item>) => setItens((x) => x.map((it, k) => (k === i ? { ...it, ...p } : it)));
  const vacinasVisiveis = VACINAS.filter((v) => semEstoque || v.q > 0);

  const proximasLinhas = linhas.length;
  return (
    <QuadroGaveta titulo="Lançar secagem" icone={CalendarClock} largura={1320}>
      <Faixa itens={[
        { rotulo: "Vacas em lactação", valor: VACAS.length },
        { rotulo: "Secar em até 30 dias", valor: PROXIMAS.length, tom: "atencao" },
        { rotulo: "Já passaram da data prevista", valor: ATRASADAS.length, tom: "alerta" },
        { rotulo: "Última secagem lançada", valor: "12/10/2026" },
      ]} />

      <Passo n={1} id="sc-p1" titulo="Quais vacas secar" direita={
        <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }} aria-live="polite">
          {nVacas} {nVacas === 1 ? "marcada" : "marcadas"} · {proximasLinhas} na lista
        </span>
      }>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "1.5rem" }}>
          <div className="gv-campo">
            <RotuloMini>Escolher por</RotuloMini>
            <Pilulas<"animal" | "lote"> rotulo="Escolher por" valor={modo} onChange={(m) => { setModo(m); if (m === "lote") setSel(new Set()); }} opcoes={[
              { id: "animal", nome: "Animal(is)", titulo: "Marcar vacas uma a uma" },
              { id: "lote", nome: "Lote(s)", titulo: "Escolher um ou mais lotes — começa sem ninguém marcado" },
            ]} />
          </div>
          {modo === "animal" ? (
            <div className="gv-campo">
              <RotuloMini>Mostrar</RotuloMini>
              <Pilulas<"proximas" | "atrasadas" | "todas"> rotulo="Mostrar" valor={mostrar} onChange={setMostrar} opcoes={[
                { id: "proximas", nome: "Até 30 dias", n: PROXIMAS.length }, { id: "atrasadas", nome: "Atrasadas", n: ATRASADAS.length }, { id: "todas", nome: "Todas", n: VACAS.length },
              ]} />
            </div>
          ) : (
            <div className="gv-campo">
              <RotuloMini>Lotes</RotuloMini>
              <Pilulas<string> rotulo="Lotes" valor={lotesSel} onChange={trocarLotes} opcoes={LOTES.map((L) => ({ id: L.id, nome: L.id, n: L.n }))} />
            </div>
          )}
          <div className="gv-campo" style={{ minWidth: "13rem" }}>
            <label htmlFor="sc-busca">Buscar vaca</label>
            <input id="sc-busca" type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nº da vaca" />
          </div>
          <span style={{ flex: 1 }} />
          <button type="button" className="btn-ghost" style={BTN} onClick={marcarAtrasadas} disabled={!linhas.some((v) => v.dias !== null && v.dias < 0)}>
            <Search size={13} aria-hidden="true" /> Marcar as atrasadas
          </button>
          <button type="button" className="btn-ghost" onClick={() => setSel(new Set())} disabled={!nVacas}>Limpar</button>
        </div>

        {modo === "lote" && lotesSel.length === 0 ? (
          <div style={{ border: "1px dashed var(--border-strong, var(--border))", borderRadius: "var(--r-sm)", background: "var(--surface-2)", padding: "1.2rem", color: "var(--text-muted)", fontSize: "0.82rem" }}>
            Escolha um ou mais lotes. A lista abre sem ninguém marcado, de propósito: quem entra é decisão sua (para não secar por engano quem ficou no lote).
          </div>
        ) : (
          <div className="gv-tabela-moldura" style={altura}>
            <table className="gv-tabela">
              <thead>
                <tr>
                  <th scope="col" style={{ width: "2.4rem" }}>
                    <input type="checkbox" aria-label="Marcar todas as atrasadas da lista" onChange={marcarAtrasadas}
                      checked={linhas.filter((v) => v.dias !== null && v.dias < 0).length > 0 && linhas.filter((v) => v.dias !== null && v.dias < 0).every((v) => sel.has(v.n))}
                      disabled={!linhas.some((v) => v.dias !== null && v.dias < 0)} />
                  </th>
                  <th scope="col">Nº</th>
                  <th scope="col" style={th}>DEL</th>
                  <th scope="col" style={th}>Dias de gestação</th>
                  <th scope="col" style={th} title="60 dias antes do parto previsto">Secagem prevista</th>
                  <th scope="col">Situação</th>
                  <th scope="col">Aviso</th>
                  <th scope="col">Neste lançamento</th>
                </tr>
              </thead>
              <tbody>
                {grupos.map(([lote, vs]) => (
                  <React.Fragment key={lote}>
                    <LinhaGrupo colSpan={8} titulo={lote} n={vs.length} />
                    {vs.map((v) => {
                      const a = andamentoDe(v.n);
                      return (
                        <tr key={v.n} className={sel.has(v.n) ? "gv-linha-marcada" : undefined}>
                          <td><input type="checkbox" checked={sel.has(v.n)} onChange={() => alternar(v.n)} aria-label={`Marcar a vaca ${v.n}`} /></td>
                          <td className="gv-forte gv-num">{v.n}</td>
                          <td className="gv-num gv-dir">{v.del}</td>
                          <td className="gv-num gv-dir">{v.gest ?? "—"}</td>
                          <td className="gv-num gv-dir">{v.prev ? dataBR(v.prev) : "—"}</td>
                          <td><SeloSituacao v={v} /></td>
                          <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>
                            {v.gest === null ? "Sem data de parto: confirme a prenhez antes" : ""}
                          </td>
                          <td>{a ? <SeloAndamento a={a} /> : <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                        </tr>
                      );
                    })}
                  </React.Fragment>
                ))}
                {!linhas.length && <tr><td colSpan={8} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhuma vaca neste filtro.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        <p className="gv-ajuda" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <Info size={13} aria-hidden="true" style={{ flexShrink: 0 }} />
          <span>Só aparecem vacas em lactação. A data prevista é 60 dias antes do parto; “sem prenhez” e “atrasada” informam, não impedem. Com uma só vaca marcada, a data da secagem vem preenchida com a prevista.</span>
        </p>
        {unico && (
          <p className="gv-ajuda"><b style={{ color: "var(--text)" }}>Vaca {unico.n}:</b> DEL {unico.del} · {unico.gest ?? "—"} dias de gestação · secagem prevista {unico.prev ? dataBR(unico.prev) : "—"}.</p>
        )}
      </Passo>

      <Passo n={2} id="sc-p2" titulo="Dados da secagem">
        <div style={{ display: "grid", gap: "0.75rem", gridTemplateColumns: "11rem 14rem 8.5rem 14rem minmax(12rem, 1fr)" }}>
          <Campo rotulo="Data da secagem" id="sc-data"><input type="date" value={data} onChange={(e) => setData(e.target.value)} /></Campo>
          <Campo rotulo="Motivo (obrigatório)" id="sc-motivo">
            <select value={motivo} onChange={(e) => setMotivo(e.target.value)}>
              <option value="" disabled>Selecione…</option>
              {MOTIVOS.map((m) => <option key={m.v} value={m.v}>{m.l}</option>)}
            </select>
          </Campo>
          <Campo rotulo="ECC (1 a 5)" id="sc-ecc"><input type="number" step={0.25} min={1} max={5} value={ecc} onChange={(e) => setEcc(e.target.value)} placeholder="ex.: 3,25" /></Campo>
          <Campo rotulo="Responsável" id="sc-resp">
            <select value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
              <option value="">Selecione…</option>
              {RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}
            </select>
          </Campo>
          <Campo rotulo="Observação" id="sc-obs"><input value={obs} onChange={(e) => setObs(e.target.value)} placeholder="opcional" /></Campo>
        </div>
        <Ajuda>A data pode ser retroativa. Escore de condição corporal em passos de 0,25 (opcional). O que você escolher aqui vale para todas as vacas marcadas.</Ajuda>
      </Passo>

      <Passo n={3} id="sc-p3" titulo="Produtos de secagem (opcional)" direita={
        <button type="button" className="btn-ghost" style={BTN} onClick={() => setItens((x) => [...x, { produto: "", via: "", qtd: "", un: "unidade", modo: "por_vaca" }])}>
          <Plus size={14} aria-hidden="true" /> Acrescentar produto
        </button>
      }>
        {itens.length === 0 ? (
          <p className="gv-ajuda">Sem produtos: a secagem é lançada sem baixa de estoque. Use “Acrescentar produto” se aplicou antibiótico, selante ou outro.</p>
        ) : (
          <div className="gv-tabela-moldura" style={alturaLivre}>
            <table className="gv-tabela">
              <thead>
                <tr>
                  <th scope="col">Produto</th><th scope="col">Via</th><th scope="col" style={th}>Dosagem</th><th scope="col">Unidade</th>
                  <th scope="col">A dosagem é</th><th scope="col" style={th}>Por vaca × total</th><th scope="col">Estoque depois</th><th scope="col" aria-label="Remover"></th>
                </tr>
              </thead>
              <tbody>
                {itens.map((it, i) => {
                  const est = ESTOQUE[it.produto];
                  const q = Number(it.qtd) || 0;
                  const total = it.modo === "total" ? q : q * Math.max(1, nVacas);
                  const porVaca = it.modo === "total" && nVacas > 1 ? q / nVacas : q;
                  const restante = est ? est.q - total : null;
                  return (
                    <tr key={i}>
                      <td>
                        <select className="gv-celula-input" style={{ width: "19rem", textAlign: "left" }} aria-label={`Produto ${i + 1}`} value={it.produto}
                          onChange={(e) => atualizarItem(i, { produto: e.target.value, un: ESTOQUE[e.target.value]?.un ?? it.un })}>
                          <option value="" disabled>Selecione…</option>
                          {Object.entries(ESTOQUE).map(([nome, e]) => <option key={nome} value={nome}>{nome} ({e.q} {e.un})</option>)}
                        </select>
                      </td>
                      <td>
                        <select className="gv-celula-input" style={{ width: "8.8rem", textAlign: "left" }} aria-label={`Via do produto ${i + 1}`} value={it.via} onChange={(e) => atualizarItem(i, { via: e.target.value })}>
                          <option value="">Selecione…</option>{VIAS.map((v) => <option key={v}>{v}</option>)}
                        </select>
                      </td>
                      <td className="gv-dir"><input className="gv-celula-input" style={{ width: "4.5rem" }} type="number" inputMode="decimal" min="0" aria-label={`Dosagem do produto ${i + 1}`} value={it.qtd} onChange={(e) => atualizarItem(i, { qtd: e.target.value })} /></td>
                      <td>
                        <select className="gv-celula-input" style={{ width: "6rem", textAlign: "left" }} aria-label={`Unidade do produto ${i + 1}`} value={it.un} onChange={(e) => atualizarItem(i, { un: e.target.value })}>
                          {UNIDADES.map((u) => <option key={u}>{u}</option>)}
                        </select>
                      </td>
                      <td>
                        {nVacas > 1 ? (
                          <fieldset style={{ ...fieldsetLimpo, flexWrap: "nowrap", whiteSpace: "nowrap" }} role="radiogroup" aria-label={`Como a dosagem do produto ${i + 1} vale`}>
                            <label style={rotuloRadio}><input type="radio" name={`dose-${i}`} checked={it.modo === "por_vaca"} onChange={() => atualizarItem(i, { modo: "por_vaca" })} /> por vaca</label>
                            <label style={rotuloRadio}><input type="radio" name={`dose-${i}`} checked={it.modo === "total"} onChange={() => atualizarItem(i, { modo: "total" })} /> total ÷ {nVacas}</label>
                          </fieldset>
                        ) : <span style={{ color: "var(--text-muted)" }}>por vaca</span>}
                      </td>
                      <td className="gv-num gv-dir">
                        {q > 0 ? (it.modo === "total" && nVacas > 1 ? `${nb(porVaca, 2)} × ${nVacas} = ${nb(q, 0)} ${it.un}` : `${nb(q, 0)} × ${Math.max(1, nVacas)} = ${nb(total, 0)} ${it.un}`) : "—"}
                      </td>
                      <td>
                        {est && q > 0 ? (
                          restante !== null && restante < 0
                            ? <span className="gv-num" style={{ display: "inline-flex", alignItems: "center", gap: "0.45rem" }}>{nb(est.q, 0)} → <b style={{ color: "var(--ft-verm)" }}>{nb(restante, 0)}</b><Selo tom="atencao" titulo="Informa, não bloqueia: confira o estoque">Insuficiente</Selo></span>
                            : <span className="gv-num">{nb(est.q, 0)} → <b>{nb(restante ?? 0, 0)}</b> {est.un}</span>
                        ) : <span style={{ color: "var(--text-muted)" }}>—</span>}
                      </td>
                      <td className="gv-dir">
                        <button type="button" className="btn-ghost" style={BTN} aria-label={`Remover o produto ${i + 1}`} title="Remover este produto" onClick={() => setItens((x) => x.filter((_, k) => k !== i))}>
                          <Trash2 size={13} aria-hidden="true" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {itensValidos.length > 0 && (futura ? (
          <Aviso><CalendarClock size={15} aria-hidden="true" style={{ flexShrink: 0, marginTop: "0.1rem" }} /><span>Data futura: os produtos serão <b>programados na Agenda</b>; o estoque só baixa quando você der baixa lá.</span></Aviso>
        ) : (
          <fieldset style={fieldsetLimpo} role="radiogroup" aria-label="Os produtos já foram aplicados?">
            <legend style={{ float: "left", marginRight: "0.9rem", fontSize: "0.7rem", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)", padding: 0 }}>Aplicados agora?</legend>
            <label style={rotuloRadio}><input type="radio" name="sc-aplicado" checked={aplicado} onChange={() => setAplicado(true)} /> Sim — aplicar e baixar o estoque agora</label>
            <label style={rotuloRadio}><input type="radio" name="sc-aplicado" checked={!aplicado} onChange={() => setAplicado(false)} /> Não — só programar na Agenda</label>
          </fieldset>
        ))}
      </Passo>

      <Passo n={4} id="sc-p4" titulo="Vacina pré-parto (opcional)">
        <fieldset style={fieldsetLimpo} role="radiogroup" aria-label="Aplicar vacina pré-parto?">
          <label style={rotuloRadio}><input type="radio" name="sc-vacina" checked={!vacinaSim} onChange={() => { setVacinaSim(false); setVacinasSel([]); }} /> Não</label>
          <label style={rotuloRadio}><input type="radio" name="sc-vacina" checked={vacinaSim} onChange={() => setVacinaSim(true)} /> Sim — aplicar vacina(s) pré-parto</label>
        </fieldset>
        {vacinaSim && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem", paddingLeft: "0.2rem" }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem 1.5rem", alignItems: "center" }}>
              {vacinasVisiveis.map((v) => (
                <label key={v.nome} style={rotuloRadio}>
                  <input type="checkbox" checked={vacinasSel.includes(v.nome)} style={{ accentColor: "var(--ft-ouro)", width: "1.05rem", height: "1.05rem" }}
                    onChange={() => setVacinasSel((p) => (p.includes(v.nome) ? p.filter((x) => x !== v.nome) : [...p, v.nome]))} />
                  {v.nome} <span style={{ color: "var(--text-muted)", fontSize: "0.74rem" }}>{v.q > 0 ? `estoque ${v.q} ${v.un}` : "sem estoque"}</span>
                </label>
              ))}
              <label style={{ ...rotuloRadio, color: "var(--text-muted)", fontSize: "0.76rem" }}>
                <input type="checkbox" checked={semEstoque} onChange={(e) => setSemEstoque(e.target.checked)} style={{ accentColor: "var(--ft-ouro)" }} /> Incluir itens sem estoque
              </label>
            </div>
            {vacinaInvalida && <Aviso tom="erro">Marque ao menos uma vacina pré-parto, ou volte para “Não”.</Aviso>}
            {vacinasSel.length > 0 && (
              <>
                <fieldset style={fieldsetLimpo} role="radiogroup" aria-label="As vacinas já foram aplicadas agora?">
                  <legend style={{ float: "left", marginRight: "0.9rem", fontSize: "0.7rem", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)", padding: 0 }}>Já aplicada agora?</legend>
                  <label style={rotuloRadio}><input type="radio" name="sc-vacina-agora" checked={!vacinaAgora} onChange={() => setVacinaAgora(false)} /> Não, aplico depois</label>
                  <label style={rotuloRadio}><input type="radio" name="sc-vacina-agora" checked={vacinaAgora} onChange={() => setVacinaAgora(true)} /> Sim, já apliquei</label>
                </fieldset>
                <Ajuda>
                  {vacinaAgora
                    ? "Registra a aplicação em Sanidade e dá baixa no estoque agora; não cria pendência na Agenda."
                    : `Cria uma pendência na Agenda para ${dataBR(somarDias(data, 1))} (dia seguinte à secagem), com a vaca e a(s) vacina(s) a aplicar.`}
                </Ajuda>
              </>
            )}
          </div>
        )}
      </Passo>

      <BarraAcao
        retorno={retorno}
        resumo={`${nVacas} ${nVacas === 1 ? "vaca" : "vacas"} · motivo ${motivoRotulo ?? "— escolha"} · ${
          itensValidos.length === 0 ? "sem produtos" : `${baixa ? "baixa" : "programa"} ${itensValidos.length} ${itensValidos.length === 1 ? "produto" : "produtos"}`}`}
        detalhe={`Secagem em ${dataBR(data)}${futura ? " (futura)" : ""}${vacinaSim && vacinasSel.length ? ` · vacina pré-parto: ${vacinasSel.length}${vacinaAgora ? " (aplicada agora)" : " (pendência na Agenda)"}` : ""}${!motivo ? " · falta o motivo" : ""}`}
        secundaria={final && retorno ? <button type="button" className="btn-ghost" onClick={() => setRetorno(null)}>Fechar aviso</button> : undefined}
        acao={<BotaoOuro desabilitado={!podeSalvar || (!final && !!retorno)}>
          {!final && retorno ? `Salvando ${lancadas.length} de ${SELECAO_INICIAL.length}…` : `Salvar (${nVacas})`}
        </BotaoOuro>}
      />
    </QuadroGaveta>
  );
}
