"use client";
// Etapa 2 — dados do animal/lote. Ao escolher o lote, pré-preenche via
// GET /formulacao/contexto/{lote} (campos_estimados vêm do rebanho real e
// levam o selo "estimado do rebanho"; o resto fica 100% manual).
import { useEffect, useState } from "react";
import { BadgeCheck } from "lucide-react";
import { fetchLotes } from "@/lib/api";
import {
  AnimalPayload, ESTADOS_FISIOLOGICOS_SELECIONAVEIS, EquacaoCms, ModoMonensina,
  OPCOES_EQ_CMS, OPCOES_MONENSINA, RACAS, contextoFormulacao,
} from "@/lib/dietas";

type LoteOpcao = { codigo: string; nome?: string | null };

const campo: React.CSSProperties = { display: "flex", flexDirection: "column", gap: "0.25rem" };
const rotulo: React.CSSProperties = { fontSize: "0.74rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.3rem" };
// Texto explicativo curto, abaixo do campo — usado para a origem de cada
// desconto de monensina e para a nota das equações de CMS.
const nota: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)", lineHeight: 1.45 };
const entrada: React.CSSProperties = {
  padding: "0.42rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)",
  background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem",
};
const grade: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(11rem, 1fr))", gap: "0.8rem" };

function Selo() {
  return (
    <span title="Estimado a partir dos animais ativos deste lote" style={{ display: "inline-flex", alignItems: "center", gap: "0.15rem", color: "var(--green)", fontSize: "0.66rem", fontWeight: 700 }}>
      <BadgeCheck size={11} /> estimado do rebanho
    </span>
  );
}

function Secao({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div className="card" style={{ marginBottom: "0.9rem" }}>
      <h3 style={{ margin: "0 0 0.8rem", fontSize: "0.82rem", fontWeight: 700, color: "var(--gold-deep)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{titulo}</h3>
      <div style={grade}>{children}</div>
    </div>
  );
}

export function FormAnimal({
  animal, onChange, lote, onLoteChange,
}: {
  animal: AnimalPayload; onChange: (a: AnimalPayload) => void; lote: number | null; onLoteChange: (l: number | null) => void;
}) {
  const [lotes, setLotes] = useState<LoteOpcao[]>([]);
  const [estimados, setEstimados] = useState<string[]>([]);
  const [carregandoContexto, setCarregandoContexto] = useState(false);

  useEffect(() => { fetchLotes().then((ls: LoteOpcao[]) => setLotes(ls.filter((l) => /^\d\d/.test(l.codigo)))).catch(() => {}); }, []);

  function set<K extends keyof AnimalPayload>(k: K, v: AnimalPayload[K]) {
    onChange({ ...animal, [k]: v });
  }

  function numOuNull(v: string): number | null {
    return v === "" ? null : Number(v);
  }

  async function selecionarLote(valor: string) {
    const n = valor ? Number(valor) : null;
    onLoteChange(n);
    if (n == null) { setEstimados([]); return; }
    setCarregandoContexto(true);
    try {
      const ctx = await contextoFormulacao(n);
      setEstimados(ctx.campos_estimados);
      const patch: Partial<AnimalPayload> = {};
      if (ctx.campos_estimados.includes("peso_vivo_kg") && ctx.peso_vivo_kg != null) patch.peso_vivo_kg = ctx.peso_vivo_kg;
      if (ctx.campos_estimados.includes("ecc") && ctx.ecc != null) patch.ecc = ctx.ecc;
      if (ctx.campos_estimados.includes("del_dias") && ctx.del_dias != null) patch.del_dias = ctx.del_dias;
      if (ctx.campos_estimados.includes("producao_leite_kg_dia") && ctx.producao_leite_kg_dia != null) patch.producao_leite_kg_dia = ctx.producao_leite_kg_dia;
      onChange({ ...animal, ...patch });
    } catch {
      setEstimados([]);
    } finally {
      setCarregandoContexto(false);
    }
  }

  // Unidade da idade — só apresentação. `idade_dias` segue sendo a verdade;
  // 30,4 dias/mês é a média do ano (365/12), não 30, para 24 meses não virar
  // 720 dias (dois meses de erro acumulado em novilha de sobreano).
  const DIAS_POR_MES = 365 / 12;
  const [unidadeIdade, setUnidadeIdade] = useState<"dias" | "meses">("dias");
  const idadeNaUnidade = animal.idade_dias == null
    ? ""
    : unidadeIdade === "meses"
      ? String(Math.round((animal.idade_dias / DIAS_POR_MES) * 10) / 10)
      : String(animal.idade_dias);
  function mudarIdade(bruto: string) {
    const n = numOuNull(bruto);
    if (n == null) return set("idade_dias", null);
    set("idade_dias", unidadeIdade === "meses" ? Math.round(n * DIAS_POR_MES) : Math.round(n));
  }

  const opcoesEqCms = OPCOES_EQ_CMS.filter((o) => o.estados === null || o.estados.includes(animal.estado_fisiologico));
  // `eq_cms` deixou de ser escolha do usuário: agora só diz ao motor QUAL
  // categoria calcular (o par de equações vem dela). O único valor que ainda
  // importa aqui é 0 = "CMS informado manualmente"; ao desmarcar, volta-se
  // para a primeira equação válida da categoria.
  const cmsPadraoDaCategoria = (opcoesEqCms.find((o) => o.valor !== 0)?.valor ?? 8) as EquacaoCms;

  // Trocar de categoria com um eq_cms de outra (ex.: sair de lactante 8 para
  // novilha) faria o motor recusar a entrada — realinha sozinho, preservando
  // a escolha de "informado manualmente".
  useEffect(() => {
    if (animal.eq_cms !== 0 && !opcoesEqCms.some((o) => o.valor === animal.eq_cms)) {
      set("eq_cms", cmsPadraoDaCategoria);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [animal.estado_fisiologico]);

  const leiteExigeComposicao = animal.estado_fisiologico === "vaca_lactante" && (animal.producao_leite_kg_dia || 0) > 0;

  return (
    <div>
      <div className="card" style={{ marginBottom: "0.9rem" }}>
        <div style={grade}>
          <label style={campo}>
            <span style={rotulo}>Lote {carregandoContexto && "· carregando…"}</span>
            <select style={entrada} value={lote ?? ""} onChange={(e) => selecionarLote(e.target.value)}>
              <option value="">Sem lote definido</option>
              {lotes.map((l) => <option key={l.codigo} value={Number(l.codigo.slice(0, 2))}>Lote {l.codigo}{l.nome ? ` — ${l.nome}` : ""}</option>)}
            </select>
          </label>
        </div>
      </div>

      <Secao titulo="Identificação">
        <label style={campo}>
          <span style={rotulo}>Estado fisiológico</span>
          <select style={entrada} value={animal.estado_fisiologico} onChange={(e) => set("estado_fisiologico", e.target.value as AnimalPayload["estado_fisiologico"])}>
            {ESTADOS_FISIOLOGICOS_SELECIONAVEIS.map((o) => <option key={o.valor} value={o.valor}>{o.rotulo}</option>)}
          </select>
        </label>
        <label style={campo}>
          <span style={rotulo}>Raça</span>
          <select style={entrada} value={animal.raca} onChange={(e) => set("raca", e.target.value as AnimalPayload["raca"])}>
            {RACAS.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <label style={campo}>
          <span style={rotulo}>Paridade (0 = novilha)</span>
          <input type="number" step="1" min={0} style={entrada} value={animal.paridade} onChange={(e) => set("paridade", Number(e.target.value))} />
        </label>
        {/* Idade em dias OU meses: o motor trabalha sempre em dias, mas
            ninguém fala "novilha de 540 dias" — fala "de 18 meses". A unidade
            é só da tela; a conversão acontece aqui e `idade_dias` continua
            sendo o que vai para o backend. */}
        <label style={campo}>
          <span style={rotulo}>Idade</span>
          <div style={{ display: "flex", gap: "0.4rem" }}>
            <input type="number" min={0} style={{ ...entrada, flex: 1, minWidth: 0 }}
              value={idadeNaUnidade} onChange={(e) => mudarIdade(e.target.value)} />
            <select style={{ ...entrada, width: "6.2rem" }} value={unidadeIdade}
              onChange={(e) => setUnidadeIdade(e.target.value as "dias" | "meses")}>
              <option value="dias">dias</option>
              <option value="meses">meses</option>
            </select>
          </div>
          {animal.idade_dias != null && unidadeIdade === "meses" && (
            <span style={nota}>{animal.idade_dias} dias</span>
          )}
        </label>
      </Secao>

      <Secao titulo="Peso e condição corporal">
        <label style={campo}>
          <span style={rotulo}>Peso vivo (kg) *{estimados.includes("peso_vivo_kg") && <Selo />}</span>
          <input type="number" style={entrada} value={animal.peso_vivo_kg} onChange={(e) => set("peso_vivo_kg", Number(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>Peso maturo (kg)</span>
          <input type="number" style={entrada} value={animal.peso_maturo_kg} onChange={(e) => set("peso_maturo_kg", Number(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>ECC (1 a 5){estimados.includes("ecc") && <Selo />}</span>
          <input type="number" step="0.25" min={1} max={5} style={entrada} value={animal.ecc} onChange={(e) => set("ecc", Number(e.target.value))} />
        </label>
      </Secao>

      <Secao titulo="Lactação">
        <label style={campo}>
          <span style={rotulo}>DEL — dias em lactação{estimados.includes("del_dias") && <Selo />}</span>
          <input type="number" style={entrada} value={animal.del_dias ?? ""} onChange={(e) => set("del_dias", numOuNull(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>Produção de leite (kg/dia){estimados.includes("producao_leite_kg_dia") && <Selo />}</span>
          <input type="number" style={entrada} value={animal.producao_leite_kg_dia ?? ""} onChange={(e) => set("producao_leite_kg_dia", numOuNull(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>Gordura do leite (%) {leiteExigeComposicao && "*"}</span>
          <input type="number" step="0.1" style={entrada} value={animal.gordura_leite_pct ?? ""} onChange={(e) => set("gordura_leite_pct", numOuNull(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>Proteína do leite (%) {leiteExigeComposicao && "*"}</span>
          <input type="number" step="0.1" style={entrada} value={animal.proteina_leite_pct ?? ""} onChange={(e) => set("proteina_leite_pct", numOuNull(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>Lactose do leite (%)</span>
          <input type="number" step="0.1" style={entrada} value={animal.lactose_leite_pct} onChange={(e) => set("lactose_leite_pct", Number(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>Potencial genético (PL 305, kg)</span>
          <input type="number" style={entrada} value={animal.potencial_genetico_pl_305} onChange={(e) => set("potencial_genetico_pl_305", Number(e.target.value))} />
        </label>
        {leiteExigeComposicao && (!animal.gordura_leite_pct || !animal.proteina_leite_pct) && (
          <div style={{ gridColumn: "1 / -1", fontSize: "0.76rem", color: "var(--amber)" }}>
            Com produção de leite informada, gordura e proteína do leite são obrigatórias para o cálculo.
          </div>
        )}
      </Secao>

      <Secao titulo="Gestação e ganho corporal">
        <label style={campo}>
          <span style={rotulo}>Dias de gestação</span>
          <input type="number" style={entrada} value={animal.dias_gestacao ?? ""} onChange={(e) => set("dias_gestacao", numOuNull(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>Duração da gestação (dias)</span>
          <input type="number" style={entrada} value={animal.duracao_gestacao_dias} onChange={(e) => set("duracao_gestacao_dias", Number(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>Peso do bezerro ao nascer (kg){animal.raca === "Jersey" && animal.peso_bezerro_nascer_kg === 44.1 ? " — sugerido 30 (Jersey)" : ""}</span>
          <input type="number" style={entrada} value={animal.peso_bezerro_nascer_kg} onChange={(e) => set("peso_bezerro_nascer_kg", Number(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>DEL na concepção</span>
          <input type="number" style={entrada} value={animal.del_concepcao ?? ""} onChange={(e) => set("del_concepcao", numOuNull(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>Idade na 1ª concepção (dias)</span>
          <input type="number" style={entrada} value={animal.idade_concepcao_1a_dias ?? ""} onChange={(e) => set("idade_concepcao_1a_dias", numOuNull(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>Ganho de estrutura (kg/dia)</span>
          <input type="number" step="0.01" style={entrada} value={animal.ganho_estrutura_kg_dia} onChange={(e) => set("ganho_estrutura_kg_dia", Number(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>Ganho de reserva (kg/dia)</span>
          <input type="number" step="0.01" style={entrada} value={animal.ganho_reserva_kg_dia} onChange={(e) => set("ganho_reserva_kg_dia", Number(e.target.value))} />
        </label>
      </Secao>

      <Secao titulo="Ambiente e manejo">
        <label style={campo}>
          <span style={rotulo}>Temperatura (°C)</span>
          <input type="number" style={entrada} value={animal.temperatura_c} onChange={(e) => set("temperatura_c", Number(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>Distância até a sala (m)</span>
          <input type="number" style={entrada} value={animal.distancia_sala_m} onChange={(e) => set("distancia_sala_m", Number(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>Viagens à sala/dia</span>
          <input type="number" style={entrada} value={animal.viagens_sala_dia} onChange={(e) => set("viagens_sala_dia", Number(e.target.value))} />
        </label>
        <label style={campo}>
          <span style={rotulo}>Desnível diário (m)</span>
          <input type="number" style={entrada} value={animal.desnivel_diario_m} onChange={(e) => set("desnivel_diario_m", Number(e.target.value))} />
        </label>
      </Secao>

      {/* Consumo de matéria seca — não se escolhe mais a equação (ago/2026).
          As duas estimativas da categoria são sempre calculadas e mostradas
          lado a lado na Etapa 3; a pergunta que importa é "a fibra está
          limitando o consumo?", e isso só a comparação responde. Aqui ficam
          só as duas decisões que ainda são do usuário: medir o CMS na marra e
          o efeito da monensina. */}
      <Secao titulo="Consumo de matéria seca (CMS)">
        <label style={{ ...campo, flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
          <input type="checkbox" checked={animal.eq_cms === 0}
            onChange={(e) => set("eq_cms", (e.target.checked ? 0 : cmsPadraoDaCategoria) as EquacaoCms)} />
          <span style={rotulo}>CMS informado manualmente</span>
        </label>
        {animal.eq_cms === 0 && (
          <label style={campo}>
            <span style={rotulo}>CMS informado (kg/dia) *</span>
            <input type="number" style={entrada} value={animal.cms_informado_kg_dia ?? ""} onChange={(e) => set("cms_informado_kg_dia", numOuNull(e.target.value))} />
            <span style={nota}>Medido no cocho, vence as duas estimativas.</span>
          </label>
        )}

        <label style={{ ...campo, flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
          <input type="checkbox" checked={animal.usa_monensina} onChange={(e) => set("usa_monensina", e.target.checked)} />
          <span style={rotulo}>Usa monensina</span>
        </label>
        {animal.usa_monensina && (
          <>
            <label style={campo}>
              <span style={rotulo}>Redução do consumo</span>
              <select style={entrada} value={animal.monensina_modo ?? "kg"}
                onChange={(e) => set("monensina_modo", e.target.value as ModoMonensina)}>
                {OPCOES_MONENSINA.map((o) => <option key={o.valor} value={o.valor}>{o.rotulo}</option>)}
              </select>
              <span style={nota}>{(OPCOES_MONENSINA.find((o) => o.valor === (animal.monensina_modo ?? "kg")) || OPCOES_MONENSINA[0]).nota}</span>
            </label>
            {(animal.monensina_modo ?? "kg") === "manual" && (
              <label style={campo}>
                <span style={rotulo}>Redução informada (kg de MS/dia) *</span>
                <input type="number" step="0.05" style={entrada} value={animal.monensina_reducao_manual ?? ""}
                  onChange={(e) => set("monensina_reducao_manual", numOuNull(e.target.value))} />
              </label>
            )}
            <span style={nota}>
              A monensina reduz o consumo e, ao mesmo tempo, melhora a eficiência alimentar — por isso o desconto entra
              no consumo sem baixar a produção-alvo.
            </span>
          </>
        )}

        <span style={nota}>
          Não é mais preciso escolher a equação: as duas da categoria são calculadas e aparecem lado a lado na Etapa 3
          (uma só com os dados do animal, outra também com a fibra da dieta). Para {animal.estado_fisiologico.replace("_", " ")}:{" "}
          {opcoesEqCms.filter((o) => o.valor !== 0).map((o) => o.rotulo).join(" · ") || "—"}.
        </span>
      </Secao>
    </div>
  );
}
