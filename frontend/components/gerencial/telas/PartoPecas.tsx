"use client";
// Peças do lançamento de Parto/nascimento LIGADO A DADOS (usadas por components/lancamentos/FormParto.tsx).
// Vêm da proposta gerencial aprovada (docs/mockups/telas-gerenciais/parto-claro.png), mas aqui são CONTROLADAS: quem guarda o estado e fala com a API é o
// FormParto; estas peças só desenham e devolvem eventos. Regras de negócio puras ficam em lib/partoLancamento.ts.
// As classes .rp-* vêm de <EstiloRepro /> (ReprodutivoComum.tsx) e as .gv-* do kit/globals.css.
import React, { useId, useState } from "react";
import { AlertTriangle, BookOpen, ChevronDown, ChevronRight, ExternalLink } from "lucide-react";
import { Aviso, BotaoOuro, Selo } from "@/components/gerencial/kit";
import {
  avisoFreemartin, baixada2Efetiva, baixadaEfetiva, classeColostro, classeEficiencia, classeSoro, colostroPreenchidos,
  enriquecimento, ehAborto, ehNatimorto, erroSexo, erroSexo2, intervaloColostroHoras, linhaEfetiva, linhaVazia,
  TIPOS_PARTO, type Colostro, type LinhaParto, type Sexo, type SexosGemelar,
} from "@/lib/partoLancamento";

export const LINK_COLOSTRO = "https://altagenetics.inf.br/shared/Circulares/Informativo_formas%20de%20utiliza%C3%A7%C3%A3o%20colostro_site.pdf";
export const MANUAL_COLOSTRO = [
  { t: "1. Nascimento e ordenha rápida", d: "Curar umbigo (iodo 10%). Ordenhar a vaca na 1ª HORA pós-parto, com higiene total dos tetos. Coletar todo o colostro em balde limpo. Meta: ordenhar dentro da 1ª hora." },
  { t: "2. Teste de qualidade (Brix)", d: "Misturar o colostro. Pingar 2 gotas no refratômetro limpo e ler a escala Brix contra a luz." },
  { t: "3. A decisão", d: ">25% (OURO): congelar/dar (excelente). 18–25% (PRATA): enriquecer com pó até 25% (médio). <18% (BRONZE): descartar 1ª mamada (ruim) — apenas se o estoque estiver cheio." },
  { t: "4. Banco de colostro (congelamento)", d: "2 L de colostro OURO (>25%) no saco. Tirar o ar, selar, etiquetar (data, vaca, Brix), deitar na forma e congelar." },
  { t: "5. A hora de mamar", d: "Descongelar em banho-maria (máx. 50°C — use termômetro!). Fornecer a 37°C. Volume: 10% do peso vivo (aprox. 4 L)." },
  { t: "6. O tira-teima (monitoramento)", d: "Coletar sangue da bezerra entre 24h e 48h de vida. Separar o soro e medir no refratômetro. Meta: Brix do soro > 8,4%." },
];
export const MANUAL_SANGUE = [
  { t: "1. O momento certo", d: "Coletar entre 24h e 48h após o nascimento. Antes de 24h a absorção continua; após 48h perde precisão." },
  { t: "2. A coleta", d: "Conter a bezerra. Agulha e tubo limpos (tampa vermelha). Coletar 5 ml da veia jugular. Higiene total." },
  { t: "3. Separação do soro", d: "Deixar o tubo em pé em temperatura ambiente por 2–4 horas. O sangue coagula e libera o soro (líquido amarelo)." },
  { t: "4. Leitura no refratômetro", d: "Limpar o refratômetro. Pingar uma gota do SORO amarelo (não o sangue). Ler a escala Brix contra a luz." },
  { t: "5. Resultado e ação", d: "≥ 8,4% (sucesso): manter rotina, bezerra protegida. 8,1–8,3% (alerta): monitorar e revisar rotina de colostro. ≤ 8,0% (falha): ação urgente, bezerra desprotegida." },
  { t: "6. Ação urgente (falha ≤ 8,0%)", d: "1) Isolar a bezerra. 2) Monitorar temperatura 2x/dia. 3) Avisar Vet/Gerente. 4) Auditar urgente a rotina de colostro." },
];

/** A barra do pé fica colada na borda da gaveta (padding 0.9rem) e, fora dela, gruda no pé da janela sem sair da moldura. */
const CSS_PARTO = `
.pt-raiz { display: flex; flex-direction: column; font-size: 0.85rem; color: var(--text); min-width: 0; }
.pt-raiz .gv-barra { bottom: 0; margin: 0.9rem 0 0; border: 1px solid var(--border); }
.gaveta-lancamento-corpo .pt-raiz .gv-barra { bottom: -0.9rem; margin: 0.9rem -0.9rem -0.9rem; border: 0; border-top: 1px solid var(--border); }
.pt-raiz .gv-barra-retorno { background: var(--surface); }
.pt-raiz .gv-barra-retorno > * { min-width: 0; }
.pt-raiz .rp-grade-3 { grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr)); }
.pt-raiz .rp-grade-2e { grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr)); }
.pt-raiz .btn-ghost, .pt-raiz .btn-secondary { min-height: 2rem; }
.pt-raiz .btn-ghost:focus-visible, .pt-raiz .btn-secondary:focus-visible, .pt-raiz .btn-primary-gold:focus-visible, .pt-raiz .ft-pilula:focus-visible,
.pt-raiz .rp-chip:focus-visible { outline: 2px solid var(--ft-ouro); outline-offset: 1px; }
.pt-raiz .pt-rolagem-lotes { max-height: 40vh; overflow-y: auto; }
.pt-raiz .pt-detalhe-linha { display: grid; align-items: end; gap: 0.75rem; grid-template-columns: auto repeat(4, minmax(0, 1fr)); }
.pt-raiz .gv-tabela thead th { white-space: normal; padding-left: 0.4rem; padding-right: 0.4rem; line-height: 1.25; vertical-align: bottom; }
.pt-raiz .gv-tabela tbody td { padding-left: 0.4rem; padding-right: 0.4rem; }
.pt-raiz .gv-tabela .rp-sub { white-space: normal; max-width: 8.5rem; }
.pt-raiz .pt-chk { display: inline-flex; gap: 0.45rem; align-items: center; font-size: 0.82rem; cursor: pointer; min-height: 2rem; }
.pt-raiz .pt-manuais summary { cursor: pointer; font-weight: 700; color: var(--text); min-height: 1.5rem; }
.pt-raiz .pt-link-ouro { display: inline-flex; gap: 0.3rem; align-items: center; color: var(--ft-ouro-txt); font-weight: 700; }
`;
export function EstiloParto() {
  return <style>{CSS_PARTO}</style>;
}

/* ───────────────────────────── colostro / IgG — um registro por cria ───────────────────────────── */
export type CriaColostro = { chave: string; cria: string; mae: string; ordem: 1 | 2 };

const LITROS = ["1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5"];
const BRIX_COLOSTRO = Array.from({ length: 21 }, (_, i) => 15 + i);
const BRIX_SORO = Array.from({ length: 13 }, (_, i) => (6 + i * 0.5).toFixed(1));
const ENRIQUECER_ATE = ["22", "23", "24", "25", "26", "27", "28", "29", "30"];

export function PainelColostro({ crias, dados, onMuda, baixadas }: {
  crias: CriaColostro[]; dados: Record<string, Colostro>; onMuda: (chave: string, patch: Partial<Colostro>) => void; baixadas: string[];
}) {
  const uid = useId();
  const [aberto, setAberto] = useState(true);
  const [alvoEscolhido, setAlvo] = useState("");
  const alvo = crias.find((c) => c.chave === alvoEscolhido) ?? crias[0];
  const c = alvo ? dados[alvo.chave] : undefined;
  const v: Colostro = c ?? { horaParto: "", horaColostro: "", peso: "", tomou: "", litros: "", brix: "", enriq: "25", soro: "", prot: "", po: false };
  const set = (patch: Partial<Colostro>) => alvo && onMuda(alvo.chave, patch);

  const brixN = v.brix ? Number(v.brix) : null;
  const litrosN = v.litros ? Number(v.litros) : 0;
  const cls = brixN != null ? classeColostro(brixN) : null;
  const enr = enriquecimento(brixN, Number(v.enriq), litrosN);
  const intervalo = intervaloColostroHoras(v.horaParto, v.horaColostro);
  const soroN = v.soro ? Number(v.soro) : null;
  const protN = v.prot ? Number(v.prot.replace(",", ".")) : null;
  const clsSoro = soroN != null ? classeSoro(soroN) : null;
  const efic = classeEficiencia(soroN, protN != null && Number.isFinite(protN) ? protN : null);
  const comDados = crias.filter((x) => colostroPreenchidos(dados[x.chave]) > 0 || dados[x.chave]?.tomou || dados[x.chave]?.po).length;
  const corpo = `${uid}-corpo`;

  return (
    <div className="rp-recolher">
      <button type="button" className="rp-recolher-topo" aria-expanded={aberto} aria-controls={corpo} onClick={() => setAberto((a) => !a)} disabled={!crias.length}>
        {aberto ? <ChevronDown size={15} aria-hidden="true" /> : <ChevronRight size={15} aria-hidden="true" />}
        Registrar colostro e IgG (opcional)
        <span className="rp-recolher-sub">
          {crias.length
            ? `${crias.length} ${crias.length === 1 ? "cria" : "crias"} · ${comDados} com dados preenchidos`
            : "disponível quando houver uma cria com número"}
        </span>
      </button>
      {aberto && alvo && (
        <div className="rp-recolher-corpo" id={corpo}>
          <div className="gv-campo" style={{ maxWidth: "30rem" }}>
            <label htmlFor={`${uid}-alvo`}>Cria que recebe este registro (cada cria tem o seu)</label>
            <select id={`${uid}-alvo`} className="rp-select" value={alvo.chave} onChange={(e) => setAlvo(e.target.value)}>
              {crias.map((x) => {
                const n = colostroPreenchidos(dados[x.chave]);
                return <option key={x.chave} value={x.chave}>Cria {x.cria} (mãe {x.mae}){n ? ` · ${n} de 7 dados` : ""}</option>;
              })}
            </select>
          </div>
          {baixadas.length > 0 && (
            <p className="gv-ajuda">Sem colostro: {baixadas.join(", ")} — cria baixada ou natimorto não entra no rebanho, então não tem ficha para receber o registro.</p>
          )}
          <div className="rp-grade-2e">
            <div className="rp-bloco">
              <div className="rp-bloco-t">Colostro da cria {alvo.cria}</div>
              <div className="rp-grade-3">
                <div className="gv-campo"><label htmlFor={`${uid}-hp`}>Hora do parto</label><input id={`${uid}-hp`} type="time" className="rp-input" value={v.horaParto} onChange={(e) => set({ horaParto: e.target.value })} /></div>
                <div className="gv-campo"><label htmlFor={`${uid}-hc`}>Hora do colostro</label><input id={`${uid}-hc`} type="time" className="rp-input" value={v.horaColostro} onChange={(e) => set({ horaColostro: e.target.value })} /></div>
                <div className="gv-campo"><label htmlFor={`${uid}-peso`}>Peso ao nascer (kg)</label><input id={`${uid}-peso`} className="rp-input" inputMode="decimal" value={v.peso} onChange={(e) => set({ peso: e.target.value })} placeholder="ex.: 38" /></div>
              </div>
              {intervalo != null && (
                <div className="rp-tarja">
                  Intervalo parto → colostro: <strong style={{ color: "var(--text)" }}>{intervalo.toFixed(1).replace(".", ",")} h</strong>
                  <Selo tom={intervalo <= 6 ? "ok" : "atencao"}>{intervalo <= 6 ? "dentro do ideal" : "acima de 6 h"}</Selo>
                  <span>ideal ≤ 6 h; quanto antes, melhor a absorção de IgG</span>
                </div>
              )}
              <div className="rp-grade-3">
                <div className="gv-campo"><label htmlFor={`${uid}-tomou`}>Tomou colostro?</label>
                  <select id={`${uid}-tomou`} className="rp-select" value={v.tomou} onChange={(e) => set({ tomou: e.target.value as Colostro["tomou"] })}><option value="">Selecione…</option><option>Sim</option><option>Não</option></select></div>
                <div className="gv-campo"><label htmlFor={`${uid}-lit`}>Quantidade (litros)</label>
                  <select id={`${uid}-lit`} className="rp-select" value={v.litros} onChange={(e) => set({ litros: e.target.value })}><option value="">Selecione…</option>{LITROS.map((l) => <option key={l} value={l}>{l.replace(".", ",")} L</option>)}</select></div>
                <div className="gv-campo"><label htmlFor={`${uid}-brix`}>Brix do colostro (%)</label>
                  <select id={`${uid}-brix`} className="rp-select" value={v.brix} onChange={(e) => set({ brix: e.target.value })}><option value="">Selecione…</option>{BRIX_COLOSTRO.map((b) => <option key={b} value={b}>{b}%</option>)}</select></div>
              </div>
              {cls && <div className="rp-tarja">Qualidade: <Selo tom={cls.tom}>{cls.txt}</Selo></div>}
              {enr && (
                <div className="rp-tarja" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.5rem" }}>
                  Enriquecer até
                  <select className="rp-cel" style={{ width: "auto" }} aria-label="Enriquecer até (Brix %)" value={v.enriq} onChange={(e) => set({ enriq: e.target.value })}>
                    {ENRIQUECER_ATE.map((a) => <option key={a} value={a}>{a}%</option>)}
                  </select>
                  <span style={{ color: "var(--text)" }}>
                    adicionar <strong style={{ color: "var(--ft-ouro-txt)" }}>{enr.porLitro} medida(s) de colostro em pó por litro</strong> (15 g cada)
                    {litrosN > 0 && <> · para {litrosN} L: <strong>{enr.total} medidas ≈ {enr.gramas} g</strong></>}
                  </span>
                </div>
              )}
            </div>

            <div className="rp-bloco">
              <div className="rp-bloco-t">Exame de sangue (IgG) da cria {alvo.cria}</div>
              <p className="gv-ajuda">Colher entre <strong>24 h e 48 h</strong> após o nascimento. Informe o <strong>Brix sérico</strong> OU a <strong>proteína sérica</strong>. Excelente: Brix &gt;9,4% · prot. &gt;6,2 g/dL · boa: 8,9–9,3% · 5,8–6,1 · aceitável: 8,1–8,8% · 5,1–5,7 · ruim: abaixo disso.</p>
              <div className="rp-grade-2e">
                <div className="gv-campo"><label htmlFor={`${uid}-soro`}>Brix do soro (%)</label>
                  <select id={`${uid}-soro`} className="rp-select" value={v.soro} onChange={(e) => set({ soro: e.target.value })}><option value="">Selecione…</option>{BRIX_SORO.map((x) => <option key={x} value={x}>{x.replace(".", ",")}%</option>)}</select></div>
                <div className="gv-campo"><label htmlFor={`${uid}-prot`}>Proteína sérica (g/dL)</label>
                  <input id={`${uid}-prot`} className="rp-input" inputMode="decimal" value={v.prot} onChange={(e) => set({ prot: e.target.value })} placeholder="ex.: 6,0" /></div>
              </div>
              {(clsSoro || efic) && (
                <div className="rp-tarja">
                  {clsSoro && <>Brix do soro: <Selo tom={clsSoro.tom}>{clsSoro.txt}</Selo></>}
                  {efic && <>Eficiência de colostragem: <Selo tom={efic.tom}>{efic.txt}</Selo></>}
                </div>
              )}
              <label className="pt-chk">
                <input type="checkbox" checked={v.po} onChange={(e) => set({ po: e.target.checked })} /> Bezerra recebeu somente colostro em pó (sem colostro materno)
              </label>
            </div>
          </div>
          <div className="rp-tarja pt-manuais" style={{ alignItems: "flex-start" }}>
            <BookOpen size={14} aria-hidden="true" style={{ marginTop: "0.2rem" }} />
            <details><summary>Manual do colostro</summary>
              <div className="rp-grade-3" style={{ marginTop: "0.5rem" }}>{MANUAL_COLOSTRO.map((s) => <div key={s.t}><b style={{ color: "var(--text)" }}>{s.t}</b><br />{s.d}</div>)}</div>
            </details>
            <details><summary>Manual do sangue (IgG)</summary>
              <div className="rp-grade-3" style={{ marginTop: "0.5rem" }}>{MANUAL_SANGUE.map((s) => <div key={s.t}><b style={{ color: "var(--text)" }}>{s.t}</b><br />{s.d}</div>)}</div>
            </details>
            <a href={LINK_COLOSTRO} target="_blank" rel="noreferrer" className="pt-link-ouro">
              <ExternalLink size={13} aria-hidden="true" /> Tabela oficial da Alta (PDF)
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

/* ───────────────────────────── revisão de lotes (mãe e crias) ───────────────────────────── */
export type ItemRevisaoLote = { numero: string; rotulo: string; sugerido: string };
export type OpcaoLote = { codigo: string; rotulo: string };

export function PainelLotes({ itens, opcoes, ocupado, onConfirmar, onFechar }: {
  itens: ItemRevisaoLote[]; opcoes: OpcaoLote[]; ocupado: boolean;
  onConfirmar: (escolhas: Record<string, string>) => void; onFechar: () => void;
}) {
  const uid = useId();
  const [escolhas, setEscolhas] = useState<Record<string, string>>(() => Object.fromEntries(itens.map((i) => [i.numero, i.sugerido])));
  return (
    <div className="rp-bloco" style={{ width: "100%", background: "var(--surface)" }}>
      <div className="rp-bloco-t">Movimentação de lote — escolha o destino de cada animal ou deixe “Não movimentar”</div>
      <div className="rp-grade-3 pt-rolagem-lotes">
        {itens.map((i) => (
          <div className="gv-campo" key={i.numero}>
            <label htmlFor={`${uid}-${i.numero}`}>Movimentar {i.rotulo} Nº {i.numero} para</label>
            <select id={`${uid}-${i.numero}`} className="rp-select" value={escolhas[i.numero] ?? ""} onChange={(e) => setEscolhas((p) => ({ ...p, [i.numero]: e.target.value }))} disabled={ocupado}>
              <option value="">Não movimentar</option>
              {opcoes.map((o) => <option key={o.codigo} value={o.codigo}>{o.rotulo}</option>)}
            </select>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
        <button type="button" className="btn-ghost" onClick={onFechar} disabled={ocupado}>Cancelar</button>
        <BotaoOuro onClick={() => onConfirmar(escolhas)} desabilitado={ocupado}>{ocupado ? "Movendo…" : "Confirmar movimentação"}</BotaoOuro>
      </div>
    </div>
  );
}

/* ───────────────────────────── tabela de partos ───────────────────────────── */
export type MaeLinha = { n: string; lote: string; sub: string };

export function TabelaPartos({ linhasVis, modoLote, marc, dados, dataTodas, tipoTodas, abertas, existentes, repetidas, vazio, onToggle, onMuda, onAbre }: {
  linhasVis: MaeLinha[]; modoLote: boolean; marc: ReadonlySet<string>; dados: Record<string, LinhaParto>;
  dataTodas: string; tipoTodas: string; abertas: ReadonlySet<string>;
  /** Números de cria que já existem como animal (o servidor não sobrescreve) e números repetidos entre as linhas. */
  existentes: ReadonlySet<string>; repetidas: ReadonlySet<string>; vazio: string;
  onToggle: (n: string) => void; onMuda: (n: string, p: Partial<LinhaParto>) => void; onAbre: (n: string) => void;
}) {
  const colunas = modoLote ? 7 : 10;
  return (
    <div className="gv-tabela-moldura rp-tab" style={{ ["--gv-altura-tabela" as string]: "40rem" }}>
      <table className="gv-tabela">
        <thead>
          <tr>
            <th scope="col" style={{ width: "2.4rem" }}><span style={{ position: "absolute", left: "-9999px" }}>Marcar</span></th>
            <th scope="col">Mãe</th>
            {!modoLote && <><th scope="col">Data do parto</th><th scope="col">Tipo de parto</th><th scope="col" title="Retenção de placenta — gera item na Agenda">Placenta retida</th></>}
            <th scope="col" title="Em branco = sem cria">Cria 1 (nº)</th>
            <th scope="col" title="Obrigatório quando há cria">Sexo</th>
            <th scope="col" title="Cria baixada não entra no rebanho">Baixada</th>
            {modoLote && <th scope="col" title="Retenção de placenta — gera item na Agenda">Placenta retida</th>}
            {!modoLote && <th scope="col">Gêmeos</th>}
            <th scope="col">Situação</th>
          </tr>
        </thead>
        <tbody>
          {linhasVis.length === 0 && <tr className="rp-tab-vazia"><td colSpan={colunas}>{vazio}</td></tr>}
          {linhasVis.map((g) => {
            const base = dados[g.n] ?? linhaVazia(dataTodas);
            const l = linhaEfetiva(base, modoLote, dataTodas, tipoTodas);
            const marcada = marc.has(g.n);
            const aborto = !modoLote && ehAborto(l);
            const nati = ehNatimorto(l);
            const e1 = marcada && erroSexo(l); const e2 = marcada && erroSexo2(l);
            const jaExiste = marcada && !aborto && (existentes.has(l.cria.trim()) || (l.gemelar && existentes.has(l.cria2.trim())));
            const repete = marcada && !aborto && (repetidas.has(l.cria.trim()) || (l.gemelar && repetidas.has(l.cria2.trim())));
            const aberta = abertas.has(g.n) && !modoLote && !aborto;
            const situacao = !marcada ? null
              : e1 || e2 ? <Selo tom="bloqueio">Falta o sexo</Selo>
              : repete ? <Selo tom="bloqueio" titulo="O mesmo número de cria aparece em mais de uma linha">Nº repetido</Selo>
              : aborto ? <Selo tom="atencao">Aborto</Selo>
              : jaExiste ? <Selo tom="atencao" titulo="Já existe um animal com este número: o servidor não o sobrescreve">Nº já cadastrado</Selo>
              : nati ? <Selo tom="neutro">Natimorto</Selo>
              : l.gemelar ? <Selo tom="info">Gemelar{l.gemSexo ? ` ${l.gemSexo}` : ""}</Selo>
              : !l.cria.trim() ? <Selo tom="neutro">Sem cria</Selo>
              : <Selo tom="ok">Pronto</Selo>;
            return (
              <React.Fragment key={g.n}>
                <tr className={marcada ? "gv-linha-marcada" : "gv-linha-fora"}>
                  <td><input type="checkbox" checked={marcada} onChange={() => onToggle(g.n)} aria-label={modoLote ? `Marcar ${g.n}` : `Tirar ${g.n} da lista`} /></td>
                  <td><span className="gv-forte">{g.n}</span><span className="rp-sub">{g.sub}</span></td>
                  {!modoLote && (
                    <>
                      <td style={{ minWidth: "8.8rem" }}><input type="date" className="rp-cel" aria-label={`Data do parto de ${g.n}`} disabled={!marcada} value={l.data} onChange={(e) => onMuda(g.n, { data: e.target.value })} /></td>
                      <td style={{ minWidth: "9.2rem" }}>
                        <select className="rp-cel" aria-label={`Tipo de parto de ${g.n}`} disabled={!marcada} value={l.tipo} onChange={(e) => onMuda(g.n, { tipo: e.target.value })}>
                          <option value="">Selecione…</option>{TIPOS_PARTO.map((t) => <option key={t}>{t}</option>)}
                        </select>
                      </td>
                      <td style={{ textAlign: "center" }}><input type="checkbox" disabled={!marcada || aborto} checked={l.placenta && !aborto} onChange={(e) => onMuda(g.n, { placenta: e.target.checked })} aria-label={`Retenção de placenta de ${g.n}`} /></td>
                    </>
                  )}
                  <td style={{ minWidth: "5.6rem" }}><input className="rp-cel" aria-label={`Número da cria de ${g.n}`} disabled={!marcada || aborto} value={aborto ? "" : l.cria} placeholder={aborto ? "sem cria" : "ex.: 483"} onChange={(e) => onMuda(g.n, { cria: e.target.value })} /></td>
                  <td style={{ minWidth: "7.5rem" }}>
                    <select className="rp-cel" data-erro={e1 || undefined} aria-invalid={e1 || undefined} aria-label={`Sexo da cria de ${g.n}`} disabled={!marcada || aborto} value={aborto ? "" : l.sexo} onChange={(e) => onMuda(g.n, { sexo: e.target.value as Sexo })}>
                      <option value="">Selecione…</option><option value="F">Fêmea</option><option value="M">Macho</option>
                    </select>
                    {e1 && <span className="rp-erro-txt" role="alert">Informe o sexo da cria</span>}
                  </td>
                  <td style={{ minWidth: "5rem" }}>
                    <select className="rp-cel" aria-label={`Cria baixada de ${g.n}`} disabled={!marcada || aborto || nati} value={baixadaEfetiva(l) && !aborto ? "Sim" : "Não"} onChange={(e) => onMuda(g.n, { baixada: e.target.value === "Sim" })}>
                      <option>Não</option><option>Sim</option>
                    </select>
                    {nati && <span className="rp-sub">automático</span>}
                  </td>
                  {modoLote && <td style={{ textAlign: "center" }}><input type="checkbox" disabled={!marcada} checked={l.placenta} onChange={(e) => onMuda(g.n, { placenta: e.target.checked })} aria-label={`Retenção de placenta de ${g.n}`} /></td>}
                  {!modoLote && (
                    <td>
                      {aborto ? "—" : (
                        <button type="button" className="btn-ghost" disabled={!marcada} aria-expanded={aberta} aria-label={`Gêmeos de ${g.n}`} onClick={() => onAbre(g.n)} style={{ display: "inline-flex", gap: "0.25rem", alignItems: "center", padding: "0.2rem 0.5rem", fontSize: "0.78rem" }}>
                          {aberta ? <ChevronDown size={13} aria-hidden="true" /> : <ChevronRight size={13} aria-hidden="true" />}
                          {l.gemelar ? `Gemelar${l.gemSexo ? ` ${l.gemSexo}` : ""}` : "+ Gêmeos"}
                        </button>
                      )}
                    </td>
                  )}
                  <td>{situacao ?? <span className="rp-mudo">—</span>}</td>
                </tr>
                {aborto && marcada && (
                  <tr className="rp-linha-aborto">
                    <td />
                    <td colSpan={colunas - 1}>
                      <div style={{ display: "flex", gap: "1rem", alignItems: "center", flexWrap: "wrap", fontSize: "0.8rem" }}>
                        <span style={{ display: "inline-flex", gap: "0.4rem", alignItems: "flex-start", maxWidth: "46rem" }}>
                          <AlertTriangle size={14} aria-hidden="true" style={{ marginTop: "0.15rem", flexShrink: 0, color: "var(--ft-ouro-txt)" }} />
                          <span><strong>Aborto não é parto:</strong> nenhuma cria é cadastrada. Ao salvar, registra a perda de prenhez de {g.n} (motivo “aborto”) e ela volta a <strong>vazia, em observação</strong>.</span>
                        </span>
                        <span style={{ display: "inline-flex", gap: "0.4rem", alignItems: "center" }} role="group" aria-label={`Abrir lactação para ${g.n}?`}>
                          <span className="gv-rotulo">Abrir lactação?</span>
                          <button type="button" className="ft-pilula" aria-pressed={l.lact === "sim"} onClick={() => onMuda(g.n, { lact: "sim" })}>Sim, abrir</button>
                          <button type="button" className="ft-pilula" aria-pressed={l.lact === "nao"} onClick={() => onMuda(g.n, { lact: "nao" })}>Não, só registrar</button>
                        </span>
                        {!l.lact && <span className="rp-mudo">Sem escolha, o sistema pergunta ao salvar.</span>}
                      </div>
                    </td>
                  </tr>
                )}
                {aberta && marcada && (
                  <tr className="rp-linha-detalhe">
                    <td />
                    <td colSpan={colunas - 1}>
                      <div className="pt-detalhe-linha">
                        <label className="pt-chk" style={{ paddingBottom: "0.35rem" }}>
                          <input type="checkbox" checked={l.gemelar} onChange={(e) => onMuda(g.n, { gemelar: e.target.checked })} /> Parto gemelar (2 crias)
                        </label>
                        <div className="gv-campo"><label htmlFor={`gs-${g.n}`}>Sexos do parto</label>
                          <select id={`gs-${g.n}`} className="rp-select" disabled={!l.gemelar} value={l.gemSexo} onChange={(e) => onMuda(g.n, { gemSexo: e.target.value as SexosGemelar })}>
                            <option value="">Selecione… (ou deriva dos sexos)</option><option value="FF">FF — duas fêmeas</option><option value="FM">FM — fêmea e macho</option><option value="MM">MM — dois machos</option>
                          </select></div>
                        <div className="gv-campo"><label htmlFor={`c2-${g.n}`}>Nº da 2ª cria</label>
                          <input id={`c2-${g.n}`} className="rp-input" disabled={!l.gemelar} value={l.cria2} onChange={(e) => onMuda(g.n, { cria2: e.target.value })} placeholder="ex.: 484" /></div>
                        <div className="gv-campo"><label htmlFor={`s2-${g.n}`}>Sexo da 2ª cria</label>
                          <select id={`s2-${g.n}`} className="rp-select" data-erro={e2 || undefined} aria-invalid={e2 || undefined} disabled={!l.gemelar} style={e2 ? { borderColor: "var(--ft-verm)" } : undefined} value={l.sexo2} onChange={(e) => onMuda(g.n, { sexo2: e.target.value as Sexo })}>
                            <option value="">Selecione…</option><option value="F">Fêmea</option><option value="M">Macho</option>
                          </select>
                          {e2 && <span className="rp-erro-txt" role="alert">Informe o sexo da 2ª cria</span>}</div>
                        <div className="gv-campo"><label htmlFor={`b2-${g.n}`}>2ª cria baixada?</label>
                          <select id={`b2-${g.n}`} className="rp-select" disabled={!l.gemelar || nati} value={baixada2Efetiva(l) ? "Sim" : "Não"} onChange={(e) => onMuda(g.n, { baixada2: e.target.value === "Sim" })}>
                            <option>Não</option><option>Sim</option>
                          </select></div>
                      </div>
                      {avisoFreemartin(l) && (
                        <div style={{ marginTop: "0.6rem" }}>
                          <Aviso><AlertTriangle size={15} aria-hidden="true" style={{ flexShrink: 0, marginTop: "0.1rem" }} /><span><strong>Fêmea e macho (FM):</strong> a fêmea pode ser freemartin — vale acompanhar a bezerra antes de colocá-la na recria.</span></Aviso>
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

