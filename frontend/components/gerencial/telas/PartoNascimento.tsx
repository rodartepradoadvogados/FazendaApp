"use client";
// PROPOSTA — Lançamentos › Reprodutivo › Parto/nascimento (variante desktop, só apresentação, dados de exemplo; sem fetch).
// Substitui FormParto.tsx (~850 linhas, 25 campos, 3 modos em abas, duas colunas com rolagem própria, colostro/IgG sempre aberto).
//
// O QUE A VERSÃO LIGADA A DADOS PRECISA PRESERVAR (inventário de FormParto.tsx + PopupAborto.tsx):
//  · Props: animais (AnimalRow[]), lotes (string[]), onSalvo. Modos: "Uma matriz" / "Lote" / "Categoria" (CATEGORIAS_ANIMAIS + POST /lotes/preview).
//  · Por matriz: matriz (obrigatória), data do parto (padrão HOJE), tipo (Normal, Distócico moderado/severo, Cesariana, Natimorto, Aborto — opcional exceto Aborto),
//    retenção de placenta (gera item na Agenda), gemelar + gemelar_sexo (FF/FM/MM; vazio ⇒ deriva dos sexos), cria 1 e cria 2: nº (vazio = SEM cria),
//    sexo, baixada ("nasceu_viva": false). Natimorto força baixada = Sim nas duas crias (sexo continua sendo pedido: relatório % machos/fêmeas).
//  · SEXO: sem default. Hoje o formulário envia "F" quando o sexo da cria está em branco (sexo === "Macho" ? "M" : "F") — nesta proposta cria com nº
//    exige sexo e a linha mostra o erro; a versão real deve BLOQUEAR o salvar (e o servidor devolver 422 se vier sem sexo), nunca assumir "F".
//  · Aborto: não gera cria, some com cria/colostro/IgG. POST /reproducao/encerramento-gestacao {numero_matriz, data, tipo:"aborto", abrir_lactacao,
//    motivo:"aborto"} (Parto com ordem_parto NULL + perda de prenhez no serviço certo + Lactacao com a data real). Aqui a pergunta "abrir lactação?"
//    do PopupAborto vira escolha na própria linha; sem escolha, o PopupAborto continua perguntando ao salvar (onResponder → concluirAborto).
//    Depois: se r.sugerir_lote, mesmo bloco de sugestão de lote do parto normal (categoria "Vaca", del_dias).
//  · Salvar parto: POST /reproducao/parto {numero_matriz, data_parto, tipo_parto, crias[{numero, sexo, nasceu_viva}], retencao_placenta, gemelar, gemelar_sexo}
//    → {ordem_parto, crias_criadas}. Colostragem (POST /sanidade/colostragem) só da 1ª cria CRIADA e só se algum dado foi informado: tomou_colostro, litros,
//    brix_colostro (+data_colostro), hora_parto, hora_colostro, peso_nascer_kg, brix_soro (+data_teste_sangue), proteina_serica, apenas_colostro_po.
//    Falha da colostragem/lote NÃO desfaz o parto: vira "Atenção: …" no retorno. Nesta proposta o painel de colostro é do "foco" (select da cria);
//    a versão real guarda um registro por linha.
//  · Lote/categoria: data e tipo para todas; por linha nº da cria, sexo, baixada, retenção; SEM aborto, gêmeos nem colostro; um POST de parto por linha;
//    cria alocada sem confirmar (sugestao_automatica); a mãe NÃO é movida automaticamente nesse modo (aviso na ajuda). Matriz sem cria = linha só da mãe.
//  · Lote da mãe/cria: POST /producao/sugestao-lote-evento por animal (motor de critérios; sem sugestão ou igual ao lote atual ⇒ não pergunta). Com o parâmetro
//    "transferir para o lote sugerido automaticamente" (fetchTransferenciaLoteAutomatica) mãe e crias são movidas sozinhas (origem sugestao_automatica) e a
//    revisão não aparece; sem ele, "Revisar lotes (N)" abre a janela 'Movimentação de lote' (um select por animal, "Não movimentar"; POST /movimentacao com
//    origem sugestao_confirmada; só afirma "movido" se movidos ≥ 1 e o animal não estiver em nao_encontrados).
//  · Manuais (colostro, sangue) e link do PDF da Alta: textos abaixo copiados de FormParto.tsx (MANUAL_COLOSTRO, MANUAL_SANGUE, LINK_COLOSTRO).
import React, { useMemo, useState } from "react";
import { Baby, BookOpen, ExternalLink, AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import { Aviso, Ajuda, BarraAcao, BotaoOuro, Faixa, Passo, Pilulas, QuadroGaveta, Selo } from "@/components/gerencial/kit";
import { BuscaMatrizes, EstiloRepro, HOJE_ISO, PilulasX, alterna, fmtData, somaDias } from "@/components/gerencial/telas/ReprodutivoComum";

const LINK_COLOSTRO = "https://altagenetics.inf.br/shared/Circulares/Informativo_formas%20de%20utiliza%C3%A7%C3%A3o%20colostro_site.pdf";
const MANUAL_COLOSTRO = [
  { t: "1. Nascimento e ordenha rápida", d: "Curar umbigo (iodo 10%). Ordenhar a vaca na 1ª HORA pós-parto, com higiene total dos tetos. Coletar todo o colostro em balde limpo. Meta: ordenhar dentro da 1ª hora." },
  { t: "2. Teste de qualidade (Brix)", d: "Misturar o colostro. Pingar 2 gotas no refratômetro limpo e ler a escala Brix contra a luz." },
  { t: "3. A decisão", d: ">25% (OURO): congelar/dar (excelente). 18–25% (PRATA): enriquecer com pó até 25% (médio). <18% (BRONZE): descartar 1ª mamada (ruim) — apenas se o estoque estiver cheio." },
  { t: "4. Banco de colostro (congelamento)", d: "2 L de colostro OURO (>25%) no saco. Tirar o ar, selar, etiquetar (data, vaca, Brix), deitar na forma e congelar." },
  { t: "5. A hora de mamar", d: "Descongelar em banho-maria (máx. 50°C — use termômetro!). Fornecer a 37°C. Volume: 10% do peso vivo (aprox. 4 L)." },
  { t: "6. O tira-teima (monitoramento)", d: "Coletar sangue da bezerra entre 24h e 48h de vida. Separar o soro e medir no refratômetro. Meta: Brix do soro > 8,4%." },
];
const MANUAL_SANGUE = [
  { t: "1. O momento certo", d: "Coletar entre 24h e 48h após o nascimento. Antes de 24h a absorção continua; após 48h perde precisão." },
  { t: "2. A coleta", d: "Conter a bezerra. Agulha e tubo limpos (tampa vermelha). Coletar 5 ml da veia jugular. Higiene total." },
  { t: "3. Separação do soro", d: "Deixar o tubo em pé em temperatura ambiente por 2–4 horas. O sangue coagula e libera o soro (líquido amarelo)." },
  { t: "4. Leitura no refratômetro", d: "Limpar o refratômetro. Pingar uma gota do SORO amarelo (não o sangue). Ler a escala Brix contra a luz." },
  { t: "5. Resultado e ação", d: "≥ 8,4% (sucesso): manter rotina, bezerra protegida. 8,1–8,3% (alerta): monitorar e revisar rotina de colostro. ≤ 8,0% (falha): ação urgente, bezerra desprotegida." },
  { t: "6. Ação urgente (falha ≤ 8,0%)", d: "1) Isolar a bezerra. 2) Monitorar temperatura 2x/dia. 3) Avisar Vet/Gerente. 4) Auditar urgente a rotina de colostro." },
];

/* ───────────────────────────── dados de exemplo ───────────────────────────── */
type Gestante = { n: string; lote: string; cat: "Vaca" | "Novilha"; prev: string };
const POOL: Gestante[] = [
  { n: "10987", lote: "05 - Secas", cat: "Vaca", prev: "2026-10-16" },
  { n: "4412", lote: "05 - Secas", cat: "Vaca", prev: "2026-10-17" },
  { n: "063", lote: "05 - Secas", cat: "Vaca", prev: "2026-10-18" },
  { n: "8841", lote: "05 - Secas", cat: "Vaca", prev: "2026-10-19" },
  { n: "2776", lote: "05 - Secas", cat: "Vaca", prev: "2026-10-21" },
  { n: "3908", lote: "05 - Secas", cat: "Vaca", prev: "2026-10-26" },
  { n: "12034", lote: "01 - Novilhas Alta", cat: "Novilha", prev: "2026-10-20" },
  { n: "12051", lote: "01 - Novilhas Alta", cat: "Novilha", prev: "2026-10-24" },
];
const CATEGORIAS = [
  { id: "novilhas_inseminadas", nome: "Novilhas inseminadas", filtra: () => false },
  { id: "novilhas_gestantes", nome: "Novilhas gestantes", filtra: (g: Gestante) => g.cat === "Novilha" },
  { id: "lactacao", nome: "Vacas em lactação", filtra: () => false },
  { id: "secas", nome: "Vacas secas", filtra: (g: Gestante) => g.lote === "05 - Secas" },
  { id: "pre_parto_15", nome: "Pré-parto (próximos 15 dias)", filtra: (g: Gestante) => g.prev <= somaDias(HOJE_ISO, 15) },
  { id: "em_tratamento", nome: "Em tratamento", filtra: () => false },
];
const LOTES_DESTINO = ["01 - Novilhas Alta", "02 - Vacas Alta", "04 - Pós-parto/Tratamento", "05 - Secas", "08 - Bezerreiro 0-60 dias", "13 - Novilhas Novas"];
const TIPOS = ["Normal", "Distócico moderado", "Distócico severo", "Cesariana", "Natimorto", "Aborto"];

type Sexo = "" | "F" | "M";
type Linha = {
  data: string; tipo: string; placenta: boolean;
  cria: string; sexo: Sexo; baixada: boolean;
  gemelar: boolean; gemSexo: "" | "FF" | "FM" | "MM"; cria2: string; sexo2: Sexo; baixada2: boolean;
  lact: "" | "sim" | "nao";
};
const vazia = (data = HOJE_ISO): Linha => ({ data, tipo: "", placenta: false, cria: "", sexo: "", baixada: false, gemelar: false, gemSexo: "", cria2: "", sexo2: "", baixada2: false, lact: "" });
const LINHAS_INICIAIS: Record<string, Linha> = {
  "4412": { ...vazia(), tipo: "Distócico moderado", cria: "4830", sexo: "M", gemelar: true, gemSexo: "FM", cria2: "4831", sexo2: "F" },
  "063": { ...vazia(), tipo: "Aborto" },
  "10987": { ...vazia("2026-10-16"), tipo: "Normal", placenta: true, cria: "4832" },
  "8841": { ...vazia(), tipo: "Cesariana", cria: "4833", sexo: "F" },
  "2776": vazia(),
  "3908": vazia(),
  "12034": vazia(),
  "12051": vazia(),
};
const LINHAS_LOTE: Record<string, Linha> = {
  "10987": { ...vazia(), tipo: "Normal", cria: "4830", sexo: "F" },
  "4412": { ...vazia(), tipo: "Normal", cria: "4831", sexo: "M" },
  "063": { ...vazia(), tipo: "Normal", placenta: true, cria: "4832", sexo: "F" },
  "8841": { ...vazia(), tipo: "Normal" },
  "2776": vazia(), "3908": vazia(), "12034": vazia(), "12051": vazia(),
};

function relativo(prev: string): string {
  const [a, m, d] = prev.split("-").map(Number); const [a2, m2, d2] = HOJE_ISO.split("-").map(Number);
  const dif = Math.round((Date.UTC(a, m - 1, d) - Date.UTC(a2, m2 - 1, d2)) / 86400000);
  return dif === 0 ? "hoje" : dif === -1 ? "ontem" : dif === 1 ? "amanhã" : dif < 0 ? `${-dif} d atrás` : `em ${dif} d`;
}
const erroSexo = (l: Linha) => l.tipo !== "Aborto" && !!l.cria.trim() && !l.sexo;
const erroSexo2 = (l: Linha) => l.tipo !== "Aborto" && l.gemelar && !!l.cria2.trim() && !l.sexo2;

/* ───────────────────────────── classificações do colostro (regras do manual da fazenda) ───────────────────────────── */
type Tom = "ok" | "atencao" | "bloqueio" | "info" | "neutro";
function classeColostro(b: number): { txt: string; tom: Tom } {
  if (b > 25) return { txt: "Ouro — excelente", tom: "ok" };
  if (b >= 18) return { txt: "Prata — médio, enriquecer", tom: "atencao" };
  return { txt: "Bronze — ruim, descartar 1ª mamada", tom: "bloqueio" };
}
function classeSoro(b: number): { txt: string; tom: Tom } {
  if (b >= 8.4) return { txt: "Sucesso — bezerra protegida", tom: "ok" };
  if (b >= 8.1) return { txt: "Alerta — monitorar, revisar colostro", tom: "atencao" };
  return { txt: "Falha — bezerra desprotegida (ação urgente)", tom: "bloqueio" };
}
function classeEficiencia(brix: number | null, prot: number | null): { txt: string; tom: Tom } | null {
  if (brix != null) return brix > 9.4 ? { txt: "Excelente", tom: "ok" } : brix >= 8.9 ? { txt: "Boa", tom: "info" } : brix >= 8.1 ? { txt: "Aceitável", tom: "atencao" } : { txt: "Ruim — bezerra desprotegida", tom: "bloqueio" };
  if (prot != null) return prot > 6.2 ? { txt: "Excelente", tom: "ok" } : prot >= 5.8 ? { txt: "Boa", tom: "info" } : prot >= 5.1 ? { txt: "Aceitável", tom: "atencao" } : { txt: "Ruim — bezerra desprotegida", tom: "bloqueio" };
  return null;
}

/* ───────────────────────────── subcomponentes (fora do pai) ───────────────────────────── */
function PainelColostro({ crias }: { crias: { cria: string; mae: string }[] }) {
  const [aberto, setAberto] = useState(true);
  const [alvo, setAlvo] = useState(crias[0]?.cria ?? "");
  const [horaParto, setHoraParto] = useState("05:40");
  const [horaColostro, setHoraColostro] = useState("06:25");
  const [peso, setPeso] = useState("38,5");
  const [tomou, setTomou] = useState("Sim");
  const [litros, setLitros] = useState("4");
  const [brix, setBrix] = useState("22");
  const [enriq, setEnriq] = useState("25");
  const [soro, setSoro] = useState("8.5");
  const [prot, setProt] = useState("");
  const [po, setPo] = useState(false);

  const brixN = brix ? Number(brix) : null;
  const litrosN = litros ? Number(litros) : 0;
  const cls = brixN != null ? classeColostro(brixN) : null;
  const medidasPorL = brixN != null && brixN < 25 ? Math.max(0, Number(enriq) - brixN) : 0;
  const total = medidasPorL * (litrosN || 1);
  const intervalo = (() => {
    if (!horaParto || !horaColostro) return null;
    const [hp, mp] = horaParto.split(":").map(Number); const [hc, mc] = horaColostro.split(":").map(Number);
    let d = hc * 60 + mc - (hp * 60 + mp); if (d < 0) d += 1440; return d / 60;
  })();
  const soroN = soro ? Number(soro) : null;
  const clsSoro = soroN != null ? classeSoro(soroN) : null;
  const efic = classeEficiencia(soroN, prot ? Number(prot) : null);
  const preenchidos = [horaParto, horaColostro, peso, litros, brix, soro, prot].filter(Boolean).length;

  return (
    <div className="rp-recolher">
      <button type="button" className="rp-recolher-topo" aria-expanded={aberto} aria-controls="colostro-corpo" onClick={() => setAberto((a) => !a)} disabled={!crias.length}>
        {aberto ? <ChevronDown size={15} aria-hidden="true" /> : <ChevronRight size={15} aria-hidden="true" />}
        Registrar colostro e IgG (opcional)
        <span className="rp-recolher-sub">
          {crias.length ? `da 1ª cria · ${preenchidos} de 7 dados preenchidos` : "disponível quando houver uma cria com número"}
        </span>
      </button>
      {aberto && crias.length > 0 && (
        <div className="rp-recolher-corpo" id="colostro-corpo">
          <div className="gv-campo" style={{ maxWidth: "26rem" }}>
            <label htmlFor="col-alvo">Cria que recebe este registro</label>
            <select id="col-alvo" className="rp-select" value={alvo} onChange={(e) => setAlvo(e.target.value)}>
              {crias.map((c) => <option key={c.cria} value={c.cria}>Cria {c.cria} (mãe {c.mae})</option>)}
            </select>
          </div>
          <div className="rp-grade-2e">
            <div className="rp-bloco">
              <div className="rp-bloco-t">Colostro da cria</div>
              <div className="rp-grade-3">
                <div className="gv-campo"><label htmlFor="col-hp">Hora do parto</label><input id="col-hp" type="time" className="rp-input" value={horaParto} onChange={(e) => setHoraParto(e.target.value)} /></div>
                <div className="gv-campo"><label htmlFor="col-hc">Hora do colostro</label><input id="col-hc" type="time" className="rp-input" value={horaColostro} onChange={(e) => setHoraColostro(e.target.value)} /></div>
                <div className="gv-campo"><label htmlFor="col-peso">Peso ao nascer (kg)</label><input id="col-peso" className="rp-input" inputMode="decimal" value={peso} onChange={(e) => setPeso(e.target.value)} placeholder="ex.: 38" /></div>
              </div>
              {intervalo != null && (
                <div className="rp-tarja">
                  Intervalo parto → colostro: <strong style={{ color: "var(--text)" }}>{intervalo.toFixed(1).replace(".", ",")} h</strong>
                  <Selo tom={intervalo <= 6 ? "ok" : "atencao"}>{intervalo <= 6 ? "dentro do ideal" : "acima de 6 h"}</Selo>
                  <span>ideal ≤ 6 h; quanto antes, melhor a absorção de IgG</span>
                </div>
              )}
              <div className="rp-grade-3">
                <div className="gv-campo"><label htmlFor="col-tomou">Tomou colostro?</label>
                  <select id="col-tomou" className="rp-select" value={tomou} onChange={(e) => setTomou(e.target.value)}><option value="">Selecione…</option><option>Sim</option><option>Não</option></select></div>
                <div className="gv-campo"><label htmlFor="col-lit">Quantidade (litros)</label>
                  <select id="col-lit" className="rp-select" value={litros} onChange={(e) => setLitros(e.target.value)}><option value="">Selecione…</option>{["1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5"].map((l) => <option key={l} value={l}>{l.replace(".", ",")} L</option>)}</select></div>
                <div className="gv-campo"><label htmlFor="col-brix">Brix do colostro (%)</label>
                  <select id="col-brix" className="rp-select" value={brix} onChange={(e) => setBrix(e.target.value)}><option value="">Selecione…</option>{Array.from({ length: 21 }, (_, i) => 15 + i).map((b) => <option key={b} value={b}>{b}%</option>)}</select></div>
              </div>
              {cls && (
                <div className="rp-tarja">Qualidade: <Selo tom={cls.tom}>{cls.txt}</Selo></div>
              )}
              {brixN != null && brixN < 25 && (
                <div className="rp-tarja" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.5rem" }}>
                  Enriquecer até
                  <select className="rp-cel" style={{ width: "auto" }} aria-label="Enriquecer até (Brix %)" value={enriq} onChange={(e) => setEnriq(e.target.value)}>
                    {["22", "23", "24", "25", "26", "27", "28", "29", "30"].map((a) => <option key={a} value={a}>{a}%</option>)}
                  </select>
                  <span style={{ color: "var(--text)" }}>
                    adicionar <strong style={{ color: "var(--ft-ouro-txt)" }}>{medidasPorL} medida(s) de colostro em pó por litro</strong> (15 g cada)
                    {litrosN > 0 && <> · para {litrosN} L: <strong>{total} medidas ≈ {total * 15} g</strong></>}
                  </span>
                </div>
              )}
            </div>

            <div className="rp-bloco">
              <div className="rp-bloco-t">Exame de sangue (IgG) da cria</div>
              <p className="gv-ajuda">Colher entre <strong>24 h e 48 h</strong> após o nascimento. Informe o <strong>Brix sérico</strong> OU a <strong>proteína sérica</strong>. Excelente: Brix &gt;9,4% · prot. &gt;6,2 g/dL · boa: 8,9–9,3% · 5,8–6,1 · aceitável: 8,1–8,8% · 5,1–5,7 · ruim: abaixo disso.</p>
              <div className="rp-grade-2e">
                <div className="gv-campo"><label htmlFor="col-soro">Brix do soro (%)</label>
                  <select id="col-soro" className="rp-select" value={soro} onChange={(e) => setSoro(e.target.value)}><option value="">Selecione…</option>{Array.from({ length: 13 }, (_, i) => (6 + i * 0.5).toFixed(1)).map((v) => <option key={v} value={v}>{v.replace(".", ",")}%</option>)}</select></div>
                <div className="gv-campo"><label htmlFor="col-prot">Proteína sérica (g/dL)</label>
                  <input id="col-prot" className="rp-input" inputMode="decimal" value={prot} onChange={(e) => setProt(e.target.value)} placeholder="ex.: 6,0" /></div>
              </div>
              {(clsSoro || efic) && (
                <div className="rp-tarja">
                  {clsSoro && <>Brix do soro: <Selo tom={clsSoro.tom}>{clsSoro.txt}</Selo></>}
                  {efic && <>Eficiência de colostragem: <Selo tom={efic.tom}>{efic.txt}</Selo></>}
                </div>
              )}
              <label style={{ display: "flex", gap: "0.45rem", alignItems: "center", fontSize: "0.82rem", cursor: "pointer" }}>
                <input type="checkbox" checked={po} onChange={(e) => setPo(e.target.checked)} /> Bezerra recebeu somente colostro em pó (sem colostro materno)
              </label>
            </div>
          </div>
          <div className="rp-tarja">
            <BookOpen size={14} aria-hidden="true" />
            <details><summary style={{ cursor: "pointer", fontWeight: 700, color: "var(--text)" }}>Manual do colostro</summary>
              <div className="rp-grade-3" style={{ marginTop: "0.5rem" }}>{MANUAL_COLOSTRO.map((s) => <div key={s.t}><b style={{ color: "var(--text)" }}>{s.t}</b><br />{s.d}</div>)}</div>
            </details>
            <details><summary style={{ cursor: "pointer", fontWeight: 700, color: "var(--text)" }}>Manual do sangue (IgG)</summary>
              <div className="rp-grade-3" style={{ marginTop: "0.5rem" }}>{MANUAL_SANGUE.map((s) => <div key={s.t}><b style={{ color: "var(--text)" }}>{s.t}</b><br />{s.d}</div>)}</div>
            </details>
            <a href={LINK_COLOSTRO} target="_blank" rel="noreferrer" style={{ display: "inline-flex", gap: "0.3rem", alignItems: "center", color: "var(--ft-ouro-txt)", fontWeight: 700 }}>
              <ExternalLink size={13} aria-hidden="true" /> Tabela oficial da Alta (PDF)
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

type ItemLote = { numero: string; rotulo: string; sugerido: string };
function PainelLotes({ itens, onFechar }: { itens: ItemLote[]; onFechar: () => void }) {
  const [escolhas, setEscolhas] = useState<Record<string, string>>(() => Object.fromEntries(itens.map((i) => [i.numero, i.sugerido])));
  return (
    <div className="rp-bloco" style={{ width: "100%", background: "var(--surface)" }}>
      <div className="rp-bloco-t">Movimentação de lote — escolha o destino de cada animal ou deixe “Não movimentar”</div>
      <div className="rp-grade-3">
        {itens.map((i) => (
          <div className="gv-campo" key={i.numero}>
            <label htmlFor={`lote-${i.numero}`}>{i.rotulo} Nº {i.numero}</label>
            <select id={`lote-${i.numero}`} className="rp-select" value={escolhas[i.numero]} onChange={(e) => setEscolhas((p) => ({ ...p, [i.numero]: e.target.value }))}>
              <option value="">Não movimentar</option>
              {LOTES_DESTINO.map((l) => <option key={l}>{l}</option>)}
            </select>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
        <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
        <BotaoOuro onClick={onFechar}>Confirmar movimentação</BotaoOuro>
      </div>
    </div>
  );
}

function TabelaPartos({ linhasVis, modoLote, marc, dados, abertas, onToggle, onMuda, onAbre }: {
  linhasVis: Gestante[]; modoLote: boolean; marc: ReadonlySet<string>; dados: Record<string, Linha>; abertas: ReadonlySet<string>;
  onToggle: (n: string) => void; onMuda: (n: string, p: Partial<Linha>) => void; onAbre: (n: string) => void;
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
          {linhasVis.length === 0 && <tr className="rp-tab-vazia"><td colSpan={colunas}>{modoLote ? "Escolha um lote ou uma categoria acima para ver as matrizes." : "Adicione a matriz que pariu, nas sugestões acima ou pela busca."}</td></tr>}
          {linhasVis.map((g) => {
            const l = dados[g.n] ?? vazia();
            const marcada = marc.has(g.n);
            const aborto = !modoLote && l.tipo === "Aborto";
            const nati = !modoLote && l.tipo === "Natimorto";
            const e1 = marcada && erroSexo(l); const e2 = marcada && erroSexo2(l);
            const aberta = abertas.has(g.n) && !modoLote && !aborto;
            const situacao = !marcada ? null
              : e1 || e2 ? <Selo tom="bloqueio">Falta o sexo</Selo>
              : aborto ? <Selo tom="atencao">Aborto</Selo>
              : nati ? <Selo tom="neutro">Natimorto</Selo>
              : l.gemelar ? <Selo tom="info">Gemelar{l.gemSexo ? ` ${l.gemSexo}` : ""}</Selo>
              : !l.cria.trim() ? <Selo tom="neutro">Sem cria</Selo>
              : <Selo tom="ok">Pronto</Selo>;
            return (
              <React.Fragment key={g.n}>
                <tr className={marcada ? "gv-linha-marcada" : "gv-linha-fora"}>
                  <td><input type="checkbox" checked={marcada} onChange={() => onToggle(g.n)} aria-label={modoLote ? `Marcar ${g.n}` : `Tirar ${g.n} da lista`} /></td>
                  <td><span className="gv-forte">{g.n}</span><span className="rp-sub">{g.lote.split(" - ")[0]} · prevista {fmtData(g.prev, true)} ({relativo(g.prev)})</span></td>
                  {!modoLote && (
                    <>
                      <td style={{ minWidth: "8.8rem" }}><input type="date" className="rp-cel" aria-label={`Data do parto de ${g.n}`} disabled={!marcada} value={l.data} onChange={(e) => onMuda(g.n, { data: e.target.value })} /></td>
                      <td style={{ minWidth: "10.5rem" }}>
                        <select className="rp-cel" aria-label={`Tipo de parto de ${g.n}`} disabled={!marcada} value={l.tipo} onChange={(e) => onMuda(g.n, { tipo: e.target.value, baixada: e.target.value === "Natimorto" ? true : l.baixada, baixada2: e.target.value === "Natimorto" ? true : l.baixada2 })}>
                          <option value="">Selecione…</option>{TIPOS.map((t) => <option key={t}>{t}</option>)}
                        </select>
                      </td>
                      <td style={{ textAlign: "center" }}><input type="checkbox" disabled={!marcada || aborto} checked={l.placenta && !aborto} onChange={(e) => onMuda(g.n, { placenta: e.target.checked })} aria-label={`Retenção de placenta de ${g.n}`} /></td>
                    </>
                  )}
                  <td style={{ minWidth: "6.5rem" }}><input className="rp-cel" aria-label={`Número da cria de ${g.n}`} disabled={!marcada || aborto} value={aborto ? "" : l.cria} placeholder={aborto ? "sem cria" : "ex.: 483"} onChange={(e) => onMuda(g.n, { cria: e.target.value })} /></td>
                  <td style={{ minWidth: "7.5rem" }}>
                    <select className="rp-cel" data-erro={e1 || undefined} aria-invalid={e1 || undefined} aria-label={`Sexo da cria de ${g.n}`} disabled={!marcada || aborto} value={aborto ? "" : l.sexo} onChange={(e) => onMuda(g.n, { sexo: e.target.value as Sexo })}>
                      <option value="">Selecione…</option><option value="F">Fêmea</option><option value="M">Macho</option>
                    </select>
                    {e1 && <span className="rp-erro-txt" role="alert">Informe o sexo da cria</span>}
                  </td>
                  <td style={{ minWidth: "6rem" }}>
                    <select className="rp-cel" aria-label={`Cria baixada de ${g.n}`} disabled={!marcada || aborto || nati} value={(l.baixada || nati) && !aborto ? "Sim" : "Não"} onChange={(e) => onMuda(g.n, { baixada: e.target.value === "Sim" })}>
                      <option>Não</option><option>Sim</option>
                    </select>
                    {nati && <span className="rp-sub">automático</span>}
                  </td>
                  {modoLote && <td style={{ textAlign: "center" }}><input type="checkbox" disabled={!marcada} checked={l.placenta} onChange={(e) => onMuda(g.n, { placenta: e.target.checked })} aria-label={`Retenção de placenta de ${g.n}`} /></td>}
                  {!modoLote && (
                    <td>
                      {aborto ? "—" : (
                        <button type="button" className="btn-ghost" disabled={!marcada} aria-expanded={aberta} onClick={() => onAbre(g.n)} style={{ display: "inline-flex", gap: "0.25rem", alignItems: "center", padding: "0.2rem 0.5rem", fontSize: "0.78rem" }}>
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
                      <div className="rp-grade-4" style={{ alignItems: "end", gridTemplateColumns: "auto repeat(4, minmax(0, 1fr))" }}>
                        <label style={{ display: "inline-flex", gap: "0.4rem", alignItems: "center", fontSize: "0.82rem", paddingBottom: "0.35rem", cursor: "pointer" }}>
                          <input type="checkbox" checked={l.gemelar} onChange={(e) => onMuda(g.n, { gemelar: e.target.checked })} /> Parto gemelar (2 crias)
                        </label>
                        <div className="gv-campo"><label htmlFor={`gs-${g.n}`}>Sexos do parto</label>
                          <select id={`gs-${g.n}`} className="rp-select" disabled={!l.gemelar} value={l.gemSexo} onChange={(e) => onMuda(g.n, { gemSexo: e.target.value as Linha["gemSexo"] })}>
                            <option value="">Selecione… (ou deriva dos sexos)</option><option value="FF">FF — duas fêmeas</option><option value="FM">FM — fêmea e macho</option><option value="MM">MM — dois machos</option>
                          </select></div>
                        <div className="gv-campo"><label htmlFor={`c2-${g.n}`}>Nº da 2ª cria</label>
                          <input id={`c2-${g.n}`} className="rp-input" disabled={!l.gemelar} value={l.cria2} onChange={(e) => onMuda(g.n, { cria2: e.target.value })} placeholder="ex.: 484" /></div>
                        <div className="gv-campo"><label htmlFor={`s2-${g.n}`}>Sexo da 2ª cria</label>
                          <select id={`s2-${g.n}`} className="rp-select" data-erro={e2 || undefined} disabled={!l.gemelar} style={e2 ? { borderColor: "var(--ft-verm)" } : undefined} value={l.sexo2} onChange={(e) => onMuda(g.n, { sexo2: e.target.value as Sexo })}>
                            <option value="">Selecione…</option><option value="F">Fêmea</option><option value="M">Macho</option>
                          </select>
                          {e2 && <span className="rp-erro-txt" role="alert">Informe o sexo da 2ª cria</span>}</div>
                        <div className="gv-campo"><label htmlFor={`b2-${g.n}`}>2ª cria baixada?</label>
                          <select id={`b2-${g.n}`} className="rp-select" disabled={!l.gemelar || nati} value={l.baixada2 || nati ? "Sim" : "Não"} onChange={(e) => onMuda(g.n, { baixada2: e.target.value === "Sim" })}>
                            <option>Não</option><option>Sim</option>
                          </select></div>
                      </div>
                      {l.gemelar && (l.gemSexo === "FM" || (l.sexo && l.sexo2 && l.sexo !== l.sexo2)) && (
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

/* ───────────────────────────── a tela ───────────────────────────── */
type Modo = "animal" | "lote" | "categoria";

export function PartoNascimento({ estado = "animal" }: { estado?: Modo }) {
  const [modo, setModo] = useState<Modo>(estado);
  const [dados, setDados] = useState<Record<string, Linha>>(estado === "animal" ? LINHAS_INICIAIS : LINHAS_LOTE);
  const [adds, setAdds] = useState<string[]>(["4412", "063", "10987", "8841"]);
  const [busca, setBusca] = useState("");
  const [lote, setLote] = useState(estado === "lote" ? "05 - Secas" : "");
  const [cats, setCats] = useState<string[]>([]);
  const [marc, setMarc] = useState<Set<string>>(() => new Set(estado === "animal" ? ["4412", "063", "10987", "8841"] : ["10987", "4412", "063", "8841"]));
  const [dataTodas, setDataTodas] = useState(HOJE_ISO);
  const [tipoTodas, setTipoTodas] = useState("Normal");
  const [abertas, setAbertas] = useState<Set<string>>(new Set(["4412"]));
  const [lotesAberto, setLotesAberto] = useState(false);
  const [retornoVisivel, setRetornoVisivel] = useState(true);

  const modoLote = modo !== "animal";
  const doLote = lote ? POOL.filter((g) => g.lote === lote) : [];
  const dasCats = POOL.filter((g) => CATEGORIAS.some((c) => cats.includes(c.id) && c.filtra(g)));
  const linhasVis: Gestante[] = modo === "animal" ? adds.map((n) => POOL.find((g) => g.n === n)!).filter(Boolean) : modo === "lote" ? doLote : dasCats;

  const muda = (n: string, p: Partial<Linha>) => setDados((d) => ({ ...d, [n]: { ...(d[n] ?? vazia()), ...p } }));
  function alternaMarca(n: string) {
    if (modo === "animal") { setAdds((a) => a.filter((x) => x !== n)); setMarc((m) => { const s = new Set(m); s.delete(n); return s; }); return; }
    setMarc((m) => alterna(m, n));
  }
  function adiciona(n: string) {
    if (adds.includes(n)) return;
    setAdds((a) => [...a, n]); setMarc((m) => new Set(m).add(n)); setDados((d) => ({ ...d, [n]: d[n] ?? vazia() })); setBusca("");
  }
  const marcaPrazo = (itens: Gestante[]) => new Set(itens.filter((g) => g.prev <= somaDias(HOJE_ISO, 3)).map((g) => g.n));
  function trocaModo(m: Modo) { setModo(m); setMarc(m === "animal" ? new Set(adds) : new Set()); }
  function escolheLote(l: string) { setLote(l); setMarc(marcaPrazo(POOL.filter((g) => g.lote === l))); }
  function alternaCat(id: string) {
    const novas = cats.includes(id) ? cats.filter((c) => c !== id) : [...cats, id];
    setCats(novas); setMarc(marcaPrazo(POOL.filter((g) => CATEGORIAS.some((c) => novas.includes(c.id) && c.filtra(g)))));
  }

  const sugestoes = busca.trim()
    ? POOL.filter((g) => !adds.includes(g.n) && `${g.n} ${g.lote}`.toLowerCase().includes(busca.trim().toLowerCase())).slice(0, 8)
    : POOL.filter((g) => !adds.includes(g.n) && g.prev <= somaDias(HOJE_ISO, 3));

  // efeito das linhas marcadas (no modo lote, data e tipo valem para todas)
  const efetivas = linhasVis.filter((g) => marc.has(g.n)).map((g) => {
    const base = dados[g.n] ?? vazia();
    return { g, l: modoLote ? { ...base, data: dataTodas, tipo: tipoTodas, gemelar: false } : base };
  });
  const abortos = efetivas.filter((e) => e.l.tipo === "Aborto").length;
  const partos = efetivas.length - abortos;
  const criasN = efetivas.reduce((s, e) => s + (e.l.tipo === "Aborto" ? 0 : (e.l.cria.trim() ? 1 : 0) + (e.l.gemelar && e.l.cria2.trim() ? 1 : 0)), 0);
  const semSexo = efetivas.filter((e) => erroSexo(e.l) || erroSexo2(e.l)).map((e) => e.g.n);
  const criasColostro = efetivas.filter((e) => e.l.tipo !== "Aborto" && e.l.cria.trim()).map((e) => ({ cria: e.l.cria.trim(), mae: e.g.n }));

  const faixa = [
    { rotulo: "A parir em 7 dias", valor: POOL.filter((g) => g.prev <= somaDias(HOJE_ISO, 7)).length },
    { rotulo: "Passaram da data prevista", valor: POOL.filter((g) => g.prev < HOJE_ISO).length, tom: "atencao" as const },
    { rotulo: "Partos lançados hoje", valor: 2, tom: "ok" as const },
    { rotulo: "Novilhas a parir em 15 dias", valor: POOL.filter((g) => g.cat === "Novilha" && g.prev <= somaDias(HOJE_ISO, 15)).length },
  ];
  const lotesPool = [...new Set(POOL.map((g) => g.lote))].sort();

  return (
    <QuadroGaveta titulo="Lançar › Reprodutivo › Parto / nascimento" icone={Baby} largura={1320}>
      <EstiloRepro />
      <Faixa itens={faixa} />

      <Passo n={1} id="pt-p1" titulo="Como lançar">
        <Pilulas<Modo> rotulo="Modo de lançamento" valor={modo} onChange={trocaModo} opcoes={[
          { id: "animal", nome: "Uma matriz", titulo: "Parto de uma matriz, com cria, colostragem e IgG" },
          { id: "lote", nome: "Lote", titulo: "Partos simples das matrizes de um lote" },
          { id: "categoria", nome: "Categoria", titulo: "Partos simples das matrizes de uma ou mais categorias" },
        ]} />
        {modo === "lote" && (
          <PilulasX<string> rotulo="Lote" valor={lote} onChange={escolheLote} opcoes={lotesPool.map((l) => ({ id: l, nome: l, n: POOL.filter((g) => g.lote === l).length }))} />
        )}
        {modo === "categoria" && (
          <Pilulas<string> rotulo="Categorias" valor={cats} onChange={alternaCat} opcoes={CATEGORIAS.map((c) => ({ id: c.id, nome: c.nome, n: POOL.filter((g) => c.filtra(g)).length }))} />
        )}
        {modoLote && (
          <>
            <div className="rp-grade-4" style={{ maxWidth: "36rem", gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
              <div className="gv-campo"><label htmlFor="pt-data-todas">Data do parto (todas)</label>
                <input id="pt-data-todas" type="date" className="rp-input" value={dataTodas} onChange={(e) => setDataTodas(e.target.value)} /></div>
              <div className="gv-campo"><label htmlFor="pt-tipo-todas">Tipo de parto (todas)</label>
                <select id="pt-tipo-todas" className="rp-select" value={tipoTodas} onChange={(e) => setTipoTodas(e.target.value)}>
                  <option value="">Selecione…</option>{TIPOS.filter((t) => t !== "Aborto").map((t) => <option key={t}>{t}</option>)}
                </select></div>
            </div>
            <Ajuda>
              Modo simplificado: data e tipo valem para todas; por linha você informa nº da cria, sexo, baixada e retenção de placenta. <strong>Aborto, parto gemelar e colostro/IgG ficam só no modo “Uma matriz”.</strong>{" "}
              A cria é alocada no lote sugerido sem perguntar; a mudança de lote das mães não é automática aqui (Rebanho › Movimentar animais).
            </Ajuda>
          </>
        )}
      </Passo>

      <Passo n={2} id="pt-p2" titulo="Partos a lançar" direita={
        <span className="rp-contagem" aria-live="polite">{efetivas.length} de {linhasVis.length} {modoLote ? "marcadas" : efetivas.length === 1 ? "matriz na lista" : "matrizes na lista"}</span>
      }>
        {!modoLote && (
          <div className="rp-ferr">
            <BuscaMatrizes valor={busca} onChange={setBusca} rotulo="Buscar matriz que pariu (nº ou lote)" />
            <div className="rp-tarja">
              <span>{busca.trim() ? "Resultado:" : "Previstas para os próximos 3 dias:"}</span>
              {sugestoes.length === 0 && <span>nenhuma</span>}
              {sugestoes.map((g) => (
                <button key={g.n} type="button" className="rp-chip" onClick={() => adiciona(g.n)} aria-label={`Adicionar ${g.n}`}>+ {g.n} <small>{relativo(g.prev)}</small></button>
              ))}
            </div>
          </div>
        )}
        <TabelaPartos linhasVis={linhasVis} modoLote={modoLote} marc={marc} dados={dados} abertas={abertas}
          onToggle={alternaMarca} onMuda={muda} onAbre={(n) => setAbertas((a) => alterna(a, n))} />
        <Ajuda>
          {modoLote
            ? "Cria em branco = a matriz pariu sem cria cadastrada. Cria “baixada” não entra no rebanho; natimorto força baixada. Ficam marcadas as previstas até 3 dias; marque as demais se precisar."
            : <>Número da cria em branco = <strong>sem cria</strong> (natimorto/baixa). <strong>Sexo é obrigatório quando há cria</strong>: o sistema não assume mais “fêmea”. Retenção de placenta gera item na Agenda. Para mais de uma matriz, adicione quantas precisar: cada linha é um parto.</>}
        </Ajuda>
      </Passo>

      {!modoLote && (
        <Passo n={3} id="pt-p3" titulo="Colostro e IgG da 1ª cria">
          <PainelColostro key={criasColostro.map((c) => c.cria).join("|")} crias={criasColostro} />
          <Ajuda>Gravado em Sanidade › Relatório sanitário de bezerras. Se a gravação do colostro falhar, o parto continua salvo e o retorno avisa.</Ajuda>
        </Passo>
      )}

      <BarraAcao
        resumo={`${efetivas.length} ${efetivas.length === 1 ? "registro" : "registros"} · ${partos} ${partos === 1 ? "parto" : "partos"} · ${criasN} ${criasN === 1 ? "cria" : "crias"}${abortos ? ` · ${abortos} aborto` : ""}`}
        detalhe={semSexo.length
          ? <span className="rp-err" role="alert">Falta o sexo da cria de {semSexo.join(", ")} — preencha para lançar.</span>
          : efetivas.length === 0 ? "Marque ao menos uma matriz na tabela do passo 2"
          : "Ao salvar, sugere o lote da mãe e de cada cria; você confirma antes de mover."}
        retorno={retornoVisivel && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", width: "100%" }}>
            <div className="rp-retorno-linha">
              <span className="rp-ok">✓ Parto registrado (ordem 3) para 2215 · crias 4828 e 4829 cadastradas · 2 sugestões de lote para a cria e 1 para a mãe.</span>
              <span style={{ flex: 1 }} />
              <button type="button" className="btn-secondary" aria-expanded={lotesAberto} onClick={() => setLotesAberto((a) => !a)}>Revisar lotes (3)</button>
              <button type="button" className="btn-ghost" onClick={() => setRetornoVisivel(false)}>Dispensar</button>
            </div>
            {lotesAberto && (
              <PainelLotes onFechar={() => setLotesAberto(false)} itens={[
                { numero: "2215", rotulo: "a vaca", sugerido: "04 - Pós-parto/Tratamento" },
                { numero: "4828", rotulo: "o bezerro", sugerido: "08 - Bezerreiro 0-60 dias" },
                { numero: "4829", rotulo: "a bezerra", sugerido: "08 - Bezerreiro 0-60 dias" },
              ]} />
            )}
            <span className="rp-mudo" style={{ fontSize: "0.74rem" }}>Com “transferir para o lote sugerido automaticamente” ligado em Configurações › Parâmetros, mãe e crias são movidas sozinhas e esta revisão não aparece.</span>
          </div>
        )}
        acao={<BotaoOuro desabilitado={efetivas.length === 0 || semSexo.length > 0} onClick={() => setRetornoVisivel(true)}>{modoLote ? `Salvar ${efetivas.length || ""} partos`.replace("  ", " ") : `Lançar ${efetivas.length || ""} ${efetivas.length === 1 ? "registro" : "registros"}`.replace("  ", " ")}</BotaoOuro>}
      />
    </QuadroGaveta>
  );
}
