"use client";
import React, { useEffect, useMemo, useState } from "react";
import { Baby, BookOpen, ExternalLink, X } from "lucide-react";
import { criarMovimentacao, criarParto, fetchLotes, previewCriteriosLote, registrarColostragem, sugestaoLoteEvento } from "@/lib/api";
import { AnimalRow } from "@/components/AnimalModal";
import { TabBar } from "@/components/ui";
import { Campo, inputStyle, nota } from "@/components/lancamentos/comumForms";
import { SelectAnimal, CATEGORIAS_ANIMAIS } from "@/components/lancamentos/_shared";

const LINK_COLOSTRO = "https://altagenetics.inf.br/shared/Circulares/Informativo_formas%20de%20utiliza%C3%A7%C3%A3o%20colostro_site.pdf";
/* ───────────────────────── Manual do colostro (modal em tela) ───────────────────────── */
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
function ManualColostroModal({ onClose }: { onClose: () => void }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: "1rem" }} onClick={onClose}>
      <div className="card" style={{ width: "500px", maxWidth: "96vw", maxHeight: "88vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>Manual — Rotina do Colostro</div>
          <button onClick={onClose} title="Fechar" aria-label="Fechar" style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><X size={20} /></button>
        </div>
        <div className="space-y-2">
          {MANUAL_COLOSTRO.map((s) => (
            <div key={s.t} style={{ borderLeft: "3px solid var(--green-light)", paddingLeft: "0.6rem" }}>
              <p style={{ fontSize: "0.8rem", fontWeight: 700 }}>{s.t}</p>
              <p style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{s.d}</p>
            </div>
          ))}
        </div>
        <a href={LINK_COLOSTRO} target="_blank" rel="noreferrer" className="flex items-center gap-2 mt-4" style={{ color: "var(--dourado-light)", fontSize: "0.8rem" }}>
          <ExternalLink size={14} /> Abrir a tabela oficial da Alta (PDF)
        </a>
      </div>
    </div>
  );
}

function ManualSangueModal({ onClose }: { onClose: () => void }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: "1rem" }} onClick={onClose}>
      <div className="card" style={{ width: "500px", maxWidth: "96vw", maxHeight: "88vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>Manual — Teste de Sangue (IgG)</div>
          <button onClick={onClose} title="Fechar" aria-label="Fechar" style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><X size={20} /></button>
        </div>
        <div className="space-y-2">
          {MANUAL_SANGUE.map((s) => (
            <div key={s.t} style={{ borderLeft: "3px solid var(--blue)", paddingLeft: "0.6rem" }}>
              <p style={{ fontSize: "0.8rem", fontWeight: 700 }}>{s.t}</p>
              <p style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{s.d}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
// Classificação padrão ouro/prata/bronze (manual da fazenda):
//  > 25% OURO (excelente) · 18–25% PRATA (médio, enriquecer) · < 18% BRONZE (ruim).
// Tabela de enriquecimento: medidas de pó por litro = Brix alvo − Brix atual.
function classeColostro(brix: number): { txt: string; cor: string } {
  if (brix > 25) return { txt: "Ouro (excelente)", cor: "var(--dourado-light)" };
  if (brix >= 18) return { txt: "Prata (médio — enriquecer)", cor: "var(--text-muted)" };
  return { txt: "Bronze (ruim — descartar 1ª mamada)", cor: "var(--red)" };
}

// Brix do soro (teste de IgG): >=8,4 sucesso; 8,1-8,3 alerta; <=8,0 falha.
function classeSoro(brix: number): { txt: string; cor: string } {
  if (brix >= 8.4) return { txt: "Sucesso — bezerra protegida", cor: "var(--green-light)" };
  if (brix >= 8.1) return { txt: "Alerta — monitorar, revisar colostro", cor: "var(--amber)" };
  return { txt: "Falha — bezerra desprotegida (ação urgente)", cor: "var(--red)" };
}
const OPCOES_SORO = Array.from({ length: 13 }, (_, i) => (6 + i * 0.5).toFixed(1)); // 6,0 … 12,0

// Eficiência de colostragem em 4 níveis por Brix sérico (%) OU proteína
// sérica (g/dL) — o que estiver disponível (Brix tem prioridade).
function classeColostragemUI(brix: number | null, proteina: number | null): { txt: string; cor: string } {
  const excelente = { txt: "Excelente", cor: "var(--green-light)" };
  const boa = { txt: "Boa", cor: "var(--dourado-light)" };
  const aceitavel = { txt: "Aceitável", cor: "var(--amber)" };
  const ruim = { txt: "Ruim — bezerra desprotegida", cor: "var(--red)" };
  if (brix != null && !Number.isNaN(brix)) {
    if (brix > 9.4) return excelente;
    if (brix >= 8.9) return boa;
    if (brix >= 8.1) return aceitavel;
    return ruim;
  }
  if (proteina != null && !Number.isNaN(proteina)) {
    if (proteina > 6.2) return excelente;
    if (proteina >= 5.8) return boa;
    if (proteina >= 5.1) return aceitavel;
    return ruim;
  }
  return { txt: "—", cor: "var(--text-muted)" };
}

export function FormParto({ animais, lotes }: { animais: AnimalRow[]; lotes: string[] }) {
  const [modo, setModo] = useState<"animal" | "lote" | "categoria">("animal");
  const [matriz, setMatriz] = useState("");
  const [dataParto, setDataParto] = useState(() => new Date().toISOString().slice(0, 10));
  const [tipoParto, setTipoParto] = useState("");
  const [gemelar, setGemelar] = useState(false);
  const [gemelarSexo, setGemelarSexo] = useState("");
  const [criaNumero, setCriaNumero] = useState("");
  const [criaSexo, setCriaSexo] = useState("");
  const [criaBaixada, setCriaBaixada] = useState(false);
  const [cria2Numero, setCria2Numero] = useState("");
  const [cria2Sexo, setCria2Sexo] = useState("");
  const [cria2Baixada, setCria2Baixada] = useState(false);
  const [retencaoPlacenta, setRetencaoPlacenta] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const [tomouColostro, setTomou] = useState("");
  const [litros, setLitros] = useState("");
  const [brix, setBrix] = useState("");
  const [alvo, setAlvo] = useState("25");
  const [horaParto, setHoraParto] = useState("");
  const [horaColostro, setHoraColostro] = useState("");
  const [pesoNascer, setPesoNascer] = useState("");
  const [manualColostroAberto, setManualColostroAberto] = useState(false);
  const [manualSangueAberto, setManualSangueAberto] = useState(false);

  const [soro, setSoro] = useState("");
  const [proteinaSerica, setProteinaSerica] = useState("");
  const [apenasColostroPo, setApenasColostroPo] = useState(false);
  const brixN = brix ? Number(brix) : null;
  const litrosN = litros ? Number(litros) : 0;
  const cls = brixN != null ? classeColostro(brixN) : null;
  const soroN = soro ? Number(soro) : null;
  const clsSoro = soroN != null ? classeSoro(soroN) : null;
  const enriquecer = brixN != null && brixN < 25;
  const medidasPorL = enriquecer ? Math.max(0, Number(alvo) - brixN!) : 0;
  const totalMedidas = medidasPorL * (litrosN || 1);
  // Intervalo parto→colostro em horas (a partir de "HH:MM"), tratando virada de dia.
  const intervaloColostroHoras = (() => {
    if (!horaParto || !horaColostro) return null;
    const [hp, mp] = horaParto.split(":").map(Number);
    const [hc, mc] = horaColostro.split(":").map(Number);
    if ([hp, mp, hc, mc].some((n) => Number.isNaN(n))) return null;
    let diff = (hc * 60 + mc) - (hp * 60 + mp);
    if (diff < 0) diff += 24 * 60; // colostro no dia seguinte ao parto
    return diff / 60;
  })();

  async function alocarSeConfirmado(numero: string, categoriaAbrev: string, extra: { del_dias?: number | null; data_nasc?: string | null }, motivo: string, falhas: string[]) {
    try {
      const { lote_sugerido } = await sugestaoLoteEvento({ numero_matriz: numero, categoria_abrev: categoriaAbrev, ...extra });
      if (lote_sugerido && window.confirm(`Alocar o animal ${numero} no lote ${lote_sugerido.rotulo}? Ele ainda não tem lote definido.`)) {
        await criarMovimentacao({ data_movimento: dataParto, motivo, lote_destino_codigo: lote_sugerido.codigo, animais: [numero] });
        return lote_sugerido.rotulo as string;
      }
    } catch (e: any) {
      // Sugestão/alocação é best-effort — não bloqueia o parto já salvo, mas
      // avisamos para o usuário não achar que o animal já foi movido de lote.
      falhas.push(`alocação do animal ${numero} não pôde ser feita${e?.message ? `: ${e.message}` : ""}`);
    }
    return null;
  }

  // Nascimento: o bezerro cai automaticamente no lote sugerido (bezerreiro),
  // sem perguntar — diferente da mãe, aqui não há confirmação nenhuma.
  async function alocarSemConfirmar(numero: string, categoriaAbrev: string, extra: { del_dias?: number | null; data_nasc?: string | null }, motivo: string, falhas: string[]) {
    try {
      const { lote_sugerido } = await sugestaoLoteEvento({ numero_matriz: numero, categoria_abrev: categoriaAbrev, ...extra });
      if (lote_sugerido) {
        await criarMovimentacao({ data_movimento: dataParto, motivo, lote_destino_codigo: lote_sugerido.codigo, animais: [numero] });
        return lote_sugerido.rotulo as string;
      }
    } catch (e: any) {
      falhas.push(`alocação do animal ${numero} não pôde ser feita${e?.message ? `: ${e.message}` : ""}`);
    }
    return null;
  }

  // Lançamento em lote: partos simples (sem gêmeos/colostro/IgG) de várias
  // matrizes de um mesmo lote de uma vez — mesma data e tipo de parto para
  // todas, cria/retenção de placenta editável linha a linha. Cada linha chama
  // o mesmo endpoint do lançamento único (não existe endpoint de parto em
  // lote no backend); a mudança de lote da mãe (que pede confirmação one-by-one
  // no modo "Uma matriz") não é feita automaticamente aqui para não abrir N
  // caixas de confirmação — só a alocação da cria (sem confirmação) é mantida.
  const [loteBatch, setLoteBatch] = useState("");
  const [selBatch, setSelBatch] = useState<Set<string>>(new Set());
  const [dadosBatch, setDadosBatch] = useState<Record<string, { criaNumero: string; criaSexo: string; criaBaixada: boolean; retencaoPlacenta: boolean }>>({});
  const [salvandoBatch, setSalvandoBatch] = useState(false);
  const [erroBatch, setErroBatch] = useState<string | null>(null);
  const [sucessoBatch, setSucessoBatch] = useState<string | null>(null);

  const animaisDoLoteBatch = useMemo(() => (loteBatch ? animais.filter((a) => a.grupo_primario === loteBatch) : []), [animais, loteBatch]);

  // Categoria: alternativa ao lote — pode escolher uma ou mais categorias
  // prontas (mesmo motor de critérios cumulativos de Configurações > Lotes,
  // POST /lotes/preview, reaproveitando CATEGORIAS_ANIMAIS — mesmo padrão do
  // Preventivo > Aplicação) para lançar partos em lote sem precisar que as
  // matrizes estejam todas no mesmo lote.
  const [categoriasSel, setCategoriasSel] = useState<Set<string>>(new Set());
  const toggleCategoria = (id: string) => setCategoriasSel((p) => { const s = new Set(p); s.has(id) ? s.delete(id) : s.add(id); return s; });
  const [animaisCategoriasUniao, setAnimaisCategoriasUniao] = useState<string[]>([]);
  useEffect(() => {
    if (!categoriasSel.size) { setAnimaisCategoriasUniao([]); return; }
    Promise.all(Array.from(categoriasSel).map((id) => {
      const cat = CATEGORIAS_ANIMAIS.find((c) => c.id === id);
      if (!cat) return Promise.resolve([] as string[]);
      return previewCriteriosLote(cat.criterios).then((r: any) => r.animais || []).catch(() => [] as string[]);
    })).then((listas) => setAnimaisCategoriasUniao(Array.from(new Set(listas.flat()))));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Array.from(categoriasSel).sort().join("|")]);
  const animaisDaCategoriaBatch = useMemo(() => {
    const nums = new Set(animaisCategoriasUniao);
    return animais.filter((a) => nums.has(a.numero));
  }, [animais, animaisCategoriasUniao]);
  const animaisBatchFonte = modo === "categoria" ? animaisDaCategoriaBatch : animaisDoLoteBatch;

  useEffect(() => {
    setSelBatch(new Set(animaisBatchFonte.map((a) => a.numero)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loteBatch, animaisCategoriasUniao.join("|"), modo]);

  function toggleBatch(numero: string) {
    setSelBatch((p) => { const s = new Set(p); s.has(numero) ? s.delete(numero) : s.add(numero); return s; });
  }
  function toggleTodosBatch() {
    setSelBatch((p) => (p.size === animaisBatchFonte.length && animaisBatchFonte.length ? new Set() : new Set(animaisBatchFonte.map((a) => a.numero))));
  }
  function campoBatch(numero: string) {
    return dadosBatch[numero] || { criaNumero: "", criaSexo: "", criaBaixada: false, retencaoPlacenta: false };
  }
  function setCampoBatch(numero: string, patch: Partial<{ criaNumero: string; criaSexo: string; criaBaixada: boolean; retencaoPlacenta: boolean }>) {
    setDadosBatch((p) => ({ ...p, [numero]: { ...campoBatch(numero), ...patch } }));
  }

  async function salvarLote() {
    setErroBatch(null); setSucessoBatch(null);
    const alvo = Array.from(selBatch);
    if (!alvo.length) { setErroBatch("Selecione ao menos uma matriz do lote ou categoria."); return; }
    if (!dataParto) { setErroBatch("Informe a data do parto."); return; }
    setSalvandoBatch(true);
    let partosOk = 0;
    const criasOk: string[] = [];
    const falhas: string[] = [];
    for (const numero of alvo) {
      const d = campoBatch(numero);
      try {
        const crias = d.criaNumero ? [{ numero: d.criaNumero, sexo: d.criaSexo === "Macho" ? "M" : "F", nasceu_viva: !d.criaBaixada }] : [];
        const r = await criarParto({
          numero_matriz: numero, data_parto: dataParto, tipo_parto: tipoParto || undefined,
          crias, retencao_placenta: d.retencaoPlacenta, gemelar: false,
        });
        partosOk += 1;
        for (const c of r.crias_criadas as string[]) {
          criasOk.push(c);
          await alocarSemConfirmar(c, d.criaSexo === "Macho" ? "Bezerro" : "Bezerra", { data_nasc: dataParto }, "Nascimento", falhas);
        }
      } catch (e: any) {
        falhas.push(`${numero}: ${e.message || "erro ao registrar parto"}`);
      }
    }
    setSucessoBatch(
      `${partosOk} de ${alvo.length} parto(s) registrado(s)${criasOk.length ? `; cria(s) cadastrada(s): ${criasOk.join(", ")}` : ""}.` +
      `${falhas.length ? ` Atenção: ${falhas.join("; ")}.` : ""} A mudança de lote das mães não é automática aqui — use Rebanho > Movimentar animais, se precisar.`
    );
    if (partosOk) { setSelBatch(new Set()); setDadosBatch({}); setLoteBatch(""); setCategoriasSel(new Set()); }
    setSalvandoBatch(false);
  }

  // Todo parto pergunta se a mãe muda para o lote 3 — independentemente de
  // critério, ao contrário da sugestão genérica (que só age quando o animal
  // ainda não tem lote). Confirmando, move; não confirmando, ela permanece no
  // lote em que já estava.
  async function confirmarMudancaLote3(numero: string, falhas: string[]) {
    try {
      const lotes = await fetchLotes();
      const lote3 = (lotes as any[]).find((l) => l.codigo === "03");
      if (!lote3) return null;
      if (window.confirm(`Confirmar mudança de lote da vaca ${numero} para o lote 3 — ${lote3.nome}?`)) {
        await criarMovimentacao({ data_movimento: dataParto, motivo: "Parto", lote_destino_codigo: lote3.codigo, animais: [numero] });
        return lote3.rotulo as string;
      }
    } catch (e: any) {
      falhas.push(`mudança de lote da vaca ${numero} não pôde ser feita${e?.message ? `: ${e.message}` : ""}`);
    }
    return null;
  }

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!matriz) { setErro("Selecione a matriz que pariu."); return; }
    const crias = [
      ...(criaNumero ? [{ numero: criaNumero, sexo: criaSexo === "Macho" ? "M" : "F", nasceu_viva: !criaBaixada }] : []),
      ...(gemelar && cria2Numero ? [{ numero: cria2Numero, sexo: cria2Sexo === "Macho" ? "M" : "F", nasceu_viva: !cria2Baixada }] : []),
    ];
    setSalvando(true);
    try {
      const r = await criarParto({
        numero_matriz: matriz, data_parto: dataParto, tipo_parto: tipoParto || undefined,
        crias, retencao_placenta: retencaoPlacenta, gemelar,
        gemelar_sexo: gemelar ? (gemelarSexo || undefined) : undefined,
      });
      // Efeitos colaterais do parto (alocação de lote e colostragem) são
      // complementares: não bloqueiam o parto já salvo, mas as falhas são
      // coletadas para avisar o usuário no fim, em vez de sumirem em silêncio.
      const falhasEfeito: string[] = [];
      const alocacoes: string[] = [];
      const rotuloMae = await confirmarMudancaLote3(matriz, falhasEfeito);
      if (rotuloMae) alocacoes.push(`${matriz} → ${rotuloMae}`);
      for (const c of r.crias_criadas as string[]) {
        const sexoCria = c === cria2Numero ? cria2Sexo : criaSexo;
        const rotulo = await alocarSemConfirmar(c, sexoCria === "Macho" ? "Bezerro" : "Bezerra", { data_nasc: dataParto }, "Nascimento", falhasEfeito);
        if (rotulo) alocacoes.push(`${c} → ${rotulo}`);
      }
      // Colostragem/IgG acima descrevem só a 1ª cria (o formulário tem um único
      // bloco de colostro mesmo em parto gemelar) — grava se a cria foi criada
      // e algum dado foi informado.
      const criaRegistrada = r.crias_criadas.includes(criaNumero);
      if (criaRegistrada && (tomouColostro || litros || brix || soro || proteinaSerica || horaParto || horaColostro || pesoNascer || apenasColostroPo)) {
        try {
          await registrarColostragem({
            numero_animal: criaNumero,
            tomou_colostro: tomouColostro ? tomouColostro === "Sim" : undefined,
            litros_colostro: litrosN || undefined,
            brix_colostro: brixN ?? undefined,
            data_colostro: brix ? dataParto : undefined,
            hora_parto: horaParto || undefined,
            hora_colostro: horaColostro || undefined,
            peso_nascer_kg: pesoNascer ? Number(pesoNascer) : undefined,
            brix_soro: soroN ?? undefined,
            proteina_serica: proteinaSerica ? Number(proteinaSerica) : undefined,
            apenas_colostro_po: apenasColostroPo || undefined,
            data_teste_sangue: soro ? dataParto : undefined,
          });
        } catch (e: any) {
          falhasEfeito.push(`a colostragem não pôde ser gravada${e?.message ? `: ${e.message}` : ""}`);
        }
      }
      setSucesso(`Parto registrado (ordem ${r.ordem_parto}).${r.crias_criadas.length ? ` Cria(s) cadastrada(s): ${r.crias_criadas.join(", ")}.` : ""}${alocacoes.length ? ` Alocação: ${alocacoes.join("; ")}.` : ""}${falhasEfeito.length ? ` Atenção: ${falhasEfeito.join("; ")}.` : ""}`);
      setMatriz(""); setTipoParto(""); setGemelar(false); setGemelarSexo("");
      setCriaNumero(""); setCriaSexo(""); setCriaBaixada(false);
      setCria2Numero(""); setCria2Sexo(""); setCria2Baixada(false);
      setRetencaoPlacenta(false);
      setTomou(""); setLitros(""); setBrix(""); setSoro(""); setProteinaSerica("");
      setHoraParto(""); setHoraColostro(""); setPesoNascer(""); setApenasColostroPo(false);
    } catch (e: any) {
      setErro(e.message || "Erro ao registrar parto");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      {manualColostroAberto && <ManualColostroModal onClose={() => setManualColostroAberto(false)} />}
      {manualSangueAberto && <ManualSangueModal onClose={() => setManualSangueAberto(false)} />}

      <div className="mb-3">
        <TabBar<"animal" | "lote" | "categoria">
          abas={[
            { id: "animal", label: "Uma matriz", title: "Lançar o parto de uma matriz, com cria, colostragem e IgG" },
            { id: "lote", label: "Lotes", title: "Selecionar um lote e lançar partos simples de várias matrizes de uma vez" },
            { id: "categoria", label: "Categoria", title: "Selecionar uma ou mais categorias e lançar partos simples de várias matrizes de uma vez" },
          ]}
          ativa={modo}
          onChange={setModo}
        />
      </div>

      {modo !== "animal" ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {modo === "lote" ? (
              <Campo label="Lote">
                <select style={inputStyle} value={loteBatch} onChange={(e) => setLoteBatch(e.target.value)}>
                  <option value="">Selecione…</option>
                  {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </Campo>
            ) : (
              <Campo label="Categoria(s)" full>
                <div className="flex flex-wrap gap-3">
                  {CATEGORIAS_ANIMAIS.map((c) => (
                    <label key={c.id} className="flex items-center gap-2" style={{ fontSize: "0.8rem", cursor: "pointer" }}>
                      <input type="checkbox" checked={categoriasSel.has(c.id)} onChange={() => toggleCategoria(c.id)} /> {c.label}
                    </label>
                  ))}
                </div>
              </Campo>
            )}
            <Campo label="Data do parto (todas)"><input type="date" style={inputStyle} value={dataParto} onChange={(e) => setDataParto(e.target.value)} /></Campo>
            <Campo label="Tipo de parto (todas)">
              <select style={inputStyle} value={tipoParto} onChange={(e) => setTipoParto(e.target.value)}>
                <option value="">Selecione…</option><option>Normal</option>
                <option>Distócico moderado</option><option>Distócico severo</option>
                <option>Cesariana</option>
              </select>
            </Campo>
          </div>

          {(modo === "lote" ? !!loteBatch : categoriasSel.size > 0) ? (
            <div className="card mt-3" style={{ padding: 0 }}>
              <div className="card-header m-3 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
                <span>{modo === "lote" ? `Matrizes do lote ${loteBatch}` : "Matrizes das categorias selecionadas"} ({animaisBatchFonte.length})</span>
                <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={toggleTodosBatch} disabled={!animaisBatchFonte.length}>
                  {selBatch.size === animaisBatchFonte.length && animaisBatchFonte.length ? "Limpar seleção" : "Selecionar todos"}
                </button>
              </div>
              <div className="overflow-x-auto" style={{ maxHeight: "460px" }}>
                <table className="fazenda-table" style={{ margin: 0 }}>
                  <thead><tr><th></th><th>Nº</th><th>Nº da cria (vazio = baixa)</th><th>Sexo da cria</th><th>Cria baixada?</th><th>Retenção de placenta</th></tr></thead>
                  <tbody>
                    {animaisBatchFonte.map((a) => {
                      const d = campoBatch(a.numero);
                      const marcada = selBatch.has(a.numero);
                      return (
                        <tr key={a.numero} style={{ opacity: marcada ? 1 : 0.45 }}>
                          <td><input type="checkbox" checked={marcada} onChange={() => toggleBatch(a.numero)} /></td>
                          <td style={{ fontWeight: 700 }}>{a.numero}</td>
                          <td><input style={inputStyle} disabled={!marcada} value={d.criaNumero} onChange={(e) => setCampoBatch(a.numero, { criaNumero: e.target.value })} placeholder="ex.: 483" /></td>
                          <td>
                            <select style={inputStyle} disabled={!marcada} value={d.criaSexo} onChange={(e) => setCampoBatch(a.numero, { criaSexo: e.target.value })}>
                              <option value="">—</option><option>Fêmea</option><option>Macho</option>
                            </select>
                          </td>
                          <td>
                            <select style={inputStyle} disabled={!marcada} value={d.criaBaixada ? "Sim" : "Não"} onChange={(e) => setCampoBatch(a.numero, { criaBaixada: e.target.value === "Sim" })}>
                              <option>Não</option><option>Sim</option>
                            </select>
                          </td>
                          <td style={{ textAlign: "center" }}>
                            <input type="checkbox" disabled={!marcada} checked={d.retencaoPlacenta} onChange={(e) => setCampoBatch(a.numero, { retencaoPlacenta: e.target.checked })} />
                          </td>
                        </tr>
                      );
                    })}
                    {!animaisBatchFonte.length && <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhum animal {modo === "lote" ? "neste lote" : "nesta(s) categoria(s)"}.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p style={nota}>Selecione um lote ou uma categoria para ver a lista de matrizes e lançar vários partos de uma vez.</p>
          )}

          <p style={nota}>
            Modo simplificado: grava matriz, data, tipo de parto, cria e retenção de placenta de cada uma. Para
            parto gemelar, colostragem e IgG, use "Uma matriz". A mudança de lote da mãe (lote 3) precisa ser feita
            depois, manualmente, em Rebanho {"›"} Movimentar animais.
          </p>

          {erroBatch && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erroBatch}</p>}
          {sucessoBatch && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucessoBatch}</p>}
          <div className="flex items-center gap-3 mt-4">
            <button className="btn-primary" onClick={salvarLote} disabled={salvandoBatch}>{salvandoBatch ? "Salvando…" : "Salvar todos"}</button>
          </div>
        </>
      ) : (
        <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Matriz (nº)"><SelectAnimal animais={animais} value={matriz} onChange={setMatriz} placeholder="Selecione a matriz que pariu…" /></Campo>
        <Campo label="Data do parto"><input type="date" style={inputStyle} value={dataParto} onChange={(e) => setDataParto(e.target.value)} /></Campo>
        <Campo label="Tipo de parto">
          <select style={inputStyle} value={tipoParto} onChange={(e) => setTipoParto(e.target.value)}>
            <option value="">Selecione…</option><option>Normal</option>
            <option>Distócico moderado</option><option>Distócico severo</option>
            <option>Cesariana</option>
          </select>
        </Campo>
        <Campo label="Retenção de placenta"><label className="flex items-center gap-2" style={{ fontSize: "0.85rem", padding: "0.45rem 0" }}><input type="checkbox" checked={retencaoPlacenta} onChange={(e) => setRetencaoPlacenta(e.target.checked)} /> Sim (gera item na Agenda)</label></Campo>
        <Campo label="Parto gemelar (2 crias)"><label className="flex items-center gap-2" style={{ fontSize: "0.85rem", padding: "0.45rem 0" }}><input type="checkbox" checked={gemelar} onChange={(e) => setGemelar(e.target.checked)} /> Sim</label></Campo>
        {gemelar && (
          <Campo label="Sexos do parto gemelar">
            <select style={inputStyle} value={gemelarSexo} onChange={(e) => setGemelarSexo(e.target.value)}>
              <option value="">Selecione… (ou deriva dos sexos)</option>
              <option value="FF">FF — duas fêmeas</option>
              <option value="FM">FM — fêmea e macho (fêmea pode ser freemartin)</option>
              <option value="MM">MM — dois machos</option>
            </select>
          </Campo>
        )}
      </div>

      <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
        <div className="card-header mb-2 flex items-center gap-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
          <Baby size={14} /> Cadastro da cria (prole)
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Campo label="Número da cria (vazio = baixa automática)"><input style={inputStyle} value={criaNumero} onChange={(e) => setCriaNumero(e.target.value)} placeholder="ex.: 483 — em branco, natimorto/baixa" /></Campo>
          <Campo label="Sexo da cria"><select style={inputStyle} value={criaSexo} onChange={(e) => setCriaSexo(e.target.value)}><option value="" disabled>Selecione…</option><option>Fêmea</option><option>Macho</option></select></Campo>
          <Campo label="Cria baixada? (não entra no rebanho)">
            <select style={inputStyle} value={criaBaixada ? "Sim" : "Não"} onChange={(e) => setCriaBaixada(e.target.value === "Sim")}><option>Não</option><option>Sim</option></select>
          </Campo>
        </div>
        {gemelar && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.75rem" }}>
            <Campo label="Número da 2ª cria"><input style={inputStyle} value={cria2Numero} onChange={(e) => setCria2Numero(e.target.value)} placeholder="ex.: 484" /></Campo>
            <Campo label="Sexo da 2ª cria"><select style={inputStyle} value={cria2Sexo} onChange={(e) => setCria2Sexo(e.target.value)}><option value="" disabled>Selecione…</option><option>Fêmea</option><option>Macho</option></select></Campo>
            <Campo label="2ª cria baixada?">
              <select style={inputStyle} value={cria2Baixada ? "Sim" : "Não"} onChange={(e) => setCria2Baixada(e.target.value === "Sim")}><option>Não</option><option>Sim</option></select>
            </Campo>
          </div>
        )}

        <div className="mt-3" style={{ background: "rgba(22,101,52,0.12)", border: "1px solid var(--green-light)", borderRadius: "8px", padding: "0.6rem 0.8rem" }}>
          <p style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--green-light)" }}>Colostragem da cria</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-2">
            <Campo label="Hora do parto"><input type="time" style={inputStyle} value={horaParto} onChange={(e) => setHoraParto(e.target.value)} /></Campo>
            <Campo label="Hora do colostro"><input type="time" style={inputStyle} value={horaColostro} onChange={(e) => setHoraColostro(e.target.value)} /></Campo>
            <Campo label="Peso ao nascer (kg)"><input type="number" step="0.1" inputMode="decimal" style={inputStyle} value={pesoNascer} onChange={(e) => setPesoNascer(e.target.value)} placeholder="ex.: 38" /></Campo>
          </div>
          {horaParto && horaColostro && (
            <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
              Intervalo parto→colostro: <strong style={{ color: intervaloColostroHoras != null && intervaloColostroHoras <= 6 ? "var(--green-light)" : "var(--amber)" }}>
                {intervaloColostroHoras != null ? `${intervaloColostroHoras.toFixed(1)} h` : "—"}</strong> (ideal ≤ 6 h; quanto antes, melhor a absorção de IgG).
            </p>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
            <Campo label="Tomou colostro?"><select style={inputStyle} value={tomouColostro} onChange={(e) => setTomou(e.target.value)}><option value="" disabled>Selecione…</option><option>Sim</option><option>Não</option></select></Campo>
            <Campo label="Quantidade de colostro (litros)">
              <select style={inputStyle} value={litros} onChange={(e) => setLitros(e.target.value)}>
                <option value="" disabled>Selecione…</option>
                {["1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5"].map((l) => <option key={l} value={l}>{l} L</option>)}
              </select>
            </Campo>
            <Campo label="Brix do colostro (%)">
              <select style={inputStyle} value={brix} onChange={(e) => setBrix(e.target.value)}>
                <option value="" disabled>Selecione…</option>
                {Array.from({ length: 21 }, (_, i) => 15 + i).map((b) => <option key={b} value={b}>{b}%</option>)}
              </select>
            </Campo>
          </div>

          {cls && (
            <div className="mt-2" style={{ fontSize: "0.82rem" }}>
              Qualidade: <strong style={{ color: cls.cor }}>{cls.txt}</strong>
              {enriquecer && (
                <div style={{ marginTop: "0.5rem", background: "rgba(94,26,46,0.2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "0.6rem 0.8rem" }}>
                  <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                    <span>Enriquecer até</span>
                    <select style={{ ...inputStyle, width: "auto", padding: "0.2rem 0.4rem" }} value={alvo} onChange={(e) => setAlvo(e.target.value)}>
                      {["22", "23", "24", "25", "26", "27", "28", "29", "30"].map((a) => <option key={a} value={a}>{a}%</option>)}
                    </select>
                  </div>
                  <p style={{ marginTop: "0.4rem" }}>
                    Adicionar <strong style={{ color: "var(--dourado-light)" }}>{medidasPorL} medida(s) de colostro em pó por litro</strong> (15 g cada).
                    {litrosN > 0 && <> Para {litrosN} L: <strong>{totalMedidas} medidas ≈ {totalMedidas * 15} g</strong>.</>}
                  </p>
                </div>
              )}
            </div>
          )}

          <div className="flex items-center gap-3 mt-2" style={{ flexWrap: "wrap" }}>
            <button onClick={() => setManualColostroAberto(true)} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.75rem" }}><BookOpen size={13} /> Manual do colostro</button>
            <a href={LINK_COLOSTRO} target="_blank" rel="noreferrer" className="flex items-center gap-1" style={{ color: "var(--dourado-light)", fontSize: "0.75rem" }}><ExternalLink size={13} /> Tabela oficial (PDF)</a>
          </div>
        </div>

        <div className="mt-3" style={{ background: "rgba(30,111,168,0.1)", border: "1px solid var(--blue)", borderRadius: "8px", padding: "0.6rem 0.8rem" }}>
          <p style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--blue)" }}>Exame de sangue (IgG) da cria</p>
          <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
            Colher entre <strong>24h e 48h</strong> após o nascimento. Pode informar <strong>Brix sérico</strong> OU
            <strong> proteína sérica</strong>. Classificação: excelente (Brix &gt;9,4% · prot. &gt;6,2 g/dL) ·
            boa (8,9–9,3% · 5,8–6,1) · aceitável (8,1–8,8% · 5,1–5,7) · ruim (abaixo disso).
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
            <Campo label="Brix do soro (%)">
              <select style={inputStyle} value={soro} onChange={(e) => setSoro(e.target.value)}>
                <option value="" disabled>Selecione…</option>
                {OPCOES_SORO.map((v) => <option key={v} value={v}>{v.replace(".", ",")}%</option>)}
              </select>
            </Campo>
            <Campo label="Proteína sérica (g/dL)">
              <input type="number" step="0.1" inputMode="decimal" style={inputStyle} value={proteinaSerica} onChange={(e) => setProteinaSerica(e.target.value)} placeholder="ex.: 6,0" />
            </Campo>
          </div>
          {(clsSoro || proteinaSerica) && (
            <p style={{ fontSize: "0.82rem", marginTop: "0.4rem" }}>
              Eficiência de colostragem: <strong style={{ color: classeColostragemUI(soroN, proteinaSerica ? Number(proteinaSerica) : null).cor }}>
                {classeColostragemUI(soroN, proteinaSerica ? Number(proteinaSerica) : null).txt}</strong>
            </p>
          )}
          <label className="flex items-center gap-2" style={{ fontSize: "0.8rem", marginTop: "0.4rem" }}>
            <input type="checkbox" checked={apenasColostroPo} onChange={(e) => setApenasColostroPo(e.target.checked)} /> Bezerra recebeu somente colostro em pó (sem colostro materno)
          </label>
          <div className="flex items-center gap-3 mt-2" style={{ flexWrap: "wrap" }}>
            <button onClick={() => setManualSangueAberto(true)} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.75rem" }}><BookOpen size={13} /> Manual do sangue</button>
          </div>
        </div>
      </div>
      <p style={nota}>
        Matriz, data, tipo de parto, crias e retenção de placenta já gravam de verdade. Ao salvar, sugere o lote da
        mãe e de cada cria (confirmação antes de mover). Colostragem e IgG da 1ª cria também são gravadas — o
        histórico completo aparece em Sanidade → Relatório sanitário de bezerras.
      </p>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
        </>
      )}
    </>
  );
}
