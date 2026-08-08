"use client";
// O wizard inteiro mora numa ÚNICA rota (/dietas/[id]), com a etapa atual
// controlada por ?etapa=N (router.replace, sem trocar de segmento de rota).
// Um segmento aninhado [id]/[etapa] remontaria a árvore de componentes a
// cada troca de etapa — perdendo a grade e o `resultado` calculado em
// memória, que não são recarregados do zero a cada clique no stepper.
import { use, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { WizardStepper } from "@/components/dietas/WizardStepper";
import { GradeAlimentos } from "@/components/dietas/GradeAlimentos";
import { FormAnimal } from "@/components/dietas/FormAnimal";
import { PainelExigencias } from "@/components/dietas/PainelExigencias";
import { PainelBalanco } from "@/components/dietas/PainelBalanco";
import { PainelDominio } from "@/components/dietas/PainelDominio";
import { RelatorioFinal } from "@/components/dietas/RelatorioFinal";
import { AplicarNaDietaModal } from "@/components/dietas/AplicarNaDietaModal";
import {
  AnimalPayload, ItemGrade, Resultado, SimulacaoAplicadaError, SimulacaoCabecalho, SimulacaoConflitoError,
  animalPadrao, calcularDieta, duplicarSimulacao, obterSimulacao, salvarSimulacao,
} from "@/lib/dietas";

function extrairAnimal(cabecalho: SimulacaoCabecalho): AnimalPayload {
  const base = animalPadrao();
  const patch: Partial<AnimalPayload> = {};
  for (const chave of Object.keys(base) as (keyof AnimalPayload)[]) {
    if (chave in cabecalho) (patch as any)[chave] = (cabecalho as any)[chave];
  }
  return { ...base, ...patch };
}

export default function SimulacaoWizardPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: idParam } = use(params);
  const id = Number(idParam);
  const router = useRouter();
  const searchParams = useSearchParams();
  const etapa = Math.min(10, Math.max(1, Number(searchParams.get("etapa")) || 1));

  const [carregado, setCarregado] = useState(false);
  const [erroCarga, setErroCarga] = useState<string | null>(null);
  const [cabecalho, setCabecalho] = useState<SimulacaoCabecalho | null>(null);
  const [animal, setAnimal] = useState<AnimalPayload>(animalPadrao());
  const [itens, setItens] = useState<ItemGrade[]>([]);
  const [lote, setLote] = useState<number | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [calculando, setCalculando] = useState(false);
  const [erroCalculo, setErroCalculo] = useState<string | null>(null);

  const [salvando, setSalvando] = useState(false);
  const [salvoEm, setSalvoEm] = useState<Date | null>(null);
  const [erroSalvar, setErroSalvar] = useState<string | null>(null);
  const [conflitoAplicada, setConflitoAplicada] = useState(false);
  const [conflitoConcorrente, setConflitoConcorrente] = useState(false);

  const [aplicarAberto, setAplicarAberto] = useState(false);

  useEffect(() => {
    obterSimulacao(id)
      .then((d) => {
        setCabecalho(d.cabecalho);
        setAnimal(extrairAnimal(d.cabecalho));
        setItens(d.itens);
        setLote(d.cabecalho.lote);
        setResultado(d.resultado);
        setCarregado(true);
      })
      .catch((e) => setErroCarga(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!carregado) return;
    if (itens.length === 0) { setResultado(null); setCalculando(false); setErroCalculo(null); return; }
    setCalculando(true);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      calcularDieta(animal, itens, ctrl.signal)
        .then((r) => { setResultado(r); setErroCalculo(null); })
        .catch((e) => { if (e?.name !== "AbortError") { setResultado(null); setErroCalculo(e.message || "Não foi possível calcular a dieta."); } })
        .finally(() => { if (abortRef.current === ctrl) setCalculando(false); });
    }, 400);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [animal, itens, carregado]);

  const irParaEtapa = useCallback((n: number) => {
    router.replace(`/dietas/${id}?etapa=${n}`, { scroll: false });
  }, [id, router]);

  async function salvar() {
    setSalvando(true);
    setErroSalvar(null);
    setConflitoAplicada(false);
    setConflitoConcorrente(false);
    try {
      const r = await salvarSimulacao(id, { animal, itens, etapa_atual: etapa, atualizado_em: cabecalho?.atualizado_em });
      setCabecalho(r.cabecalho);
      setItens(r.itens);
      setResultado(r.resultado);
      setSalvoEm(new Date());
    } catch (e) {
      if (e instanceof SimulacaoAplicadaError) setConflitoAplicada(true);
      else if (e instanceof SimulacaoConflitoError) setConflitoConcorrente(true);
      else setErroSalvar((e as Error).message);
    } finally {
      setSalvando(false);
    }
  }

  async function duplicarEContinuar() {
    if (!cabecalho) return;
    try {
      const nome = prompt("Nome da cópia:", `${cabecalho.nome} (cópia)`);
      if (!nome) return;
      const { cabecalho: novo } = await duplicarSimulacao(id, nome);
      router.push(`/dietas/${novo.id}`);
    } catch (e: any) {
      alert(e.message);
    }
  }

  if (erroCarga) return <div className="alert-critico">{erroCarga}</div>;
  if (!carregado || !cabecalho) {
    return <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--text-muted)" }}><Loader2 size={16} className="animate-spin" /> Carregando simulação…</div>;
  }

  return (
    <div style={{ maxWidth: "78rem", margin: "0 auto", paddingBottom: "4.5rem" }}>
      <div style={{ marginBottom: "1rem" }}>
        <h1 style={{ margin: 0, fontSize: "1.25rem", fontWeight: 800, color: "var(--text)" }}>{cabecalho.nome}</h1>
        <p style={{ margin: "0.15rem 0 0", fontSize: "0.8rem", color: "var(--text-muted)" }}>
          Lote {cabecalho.lote ?? "—"} · status {cabecalho.status} · etapa {etapa}/10
        </p>
      </div>

      <div style={{ marginBottom: "1.1rem" }}>
        <WizardStepper etapaAtual={etapa} onSelecionar={irParaEtapa} />
      </div>

      {conflitoAplicada && (
        <div className="alert-critico" style={{ marginBottom: "1rem", flexDirection: "column", alignItems: "flex-start", gap: "0.5rem" }}>
          <span>Esta simulação já foi aplicada numa dieta e não pode mais ser editada.</span>
          <button type="button" className="btn-primary-gold" onClick={duplicarEContinuar}>Duplicar para continuar editando</button>
        </div>
      )}
      {conflitoConcorrente && (
        <div className="alert-critico" style={{ marginBottom: "1rem", flexDirection: "column", alignItems: "flex-start", gap: "0.5rem" }}>
          <span>Esta simulação foi alterada em outra guia enquanto você editava.</span>
          <button type="button" className="btn-secondary" onClick={() => location.reload()}>Recarregar</button>
        </div>
      )}
      {erroSalvar && <div className="alert-critico" style={{ marginBottom: "1rem" }}>{erroSalvar}</div>}
      {erroCalculo && !calculando && (
        <div className="alert-critico" style={{ marginBottom: "1rem", background: "color-mix(in srgb, var(--amber) 14%, transparent)", borderColor: "var(--amber)", color: "var(--text)" }}>
          Não foi possível calcular com os dados atuais: {erroCalculo}
        </div>
      )}

      <div>
        {etapa === 1 && <GradeAlimentos itens={itens} onChange={setItens} />}
        {etapa === 2 && <FormAnimal animal={animal} onChange={setAnimal} lote={lote} onLoteChange={setLote} />}
        {etapa === 3 && <PainelExigencias resultado={resultado} />}
        {etapa === 4 && (
          <PainelBalanco itens={itens} onChangeItens={setItens} resultado={resultado} calculando={calculando} onAbrirAplicar={() => setAplicarAberto(true)} />
        )}
        {etapa === 5 && <PainelDominio dominio="energia" resultado={resultado} />}
        {etapa === 6 && <PainelDominio dominio="proteina" resultado={resultado} />}
        {etapa === 7 && <PainelDominio dominio="carboidratos" resultado={resultado} />}
        {(etapa === 8 || etapa === 9) && (
          <div className="empty-state">Esta etapa ({etapa === 8 ? "Modelo ruminal" : "Aminoácidos"}) chega numa fase futura do módulo de Formulação de Dietas.</div>
        )}
        {etapa === 10 && (
          <RelatorioFinal
            cabecalho={cabecalho} itens={itens} resultado={resultado}
            onAbrirAplicar={() => setAplicarAberto(true)} onSalvar={salvar} salvando={salvando}
          />
        )}
      </div>

      <div style={{
        position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 20,
        background: "var(--surface)", borderTop: "1px solid var(--border)", padding: "0.7rem 1.4rem",
        display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "0.8rem",
      }}>
        {salvoEm && <span style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>Salvo às {salvoEm.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</span>}
        <button type="button" className="btn-secondary" disabled={salvando || conflitoAplicada} onClick={salvar}>
          {salvando ? "Salvando…" : "Salvar simulação"}
        </button>
      </div>

      {aplicarAberto && resultado && (
        <AplicarNaDietaModal simulacaoId={id} loteDefault={cabecalho.lote} resultado={resultado} onFechar={() => setAplicarAberto(false)} />
      )}
    </div>
  );
}
