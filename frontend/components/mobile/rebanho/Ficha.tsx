"use client";
// Tela REBANHO › aba "Ficha do Animal".
// Busca grande + lista de recentes; ao tocar num animal abre a ficha completa
// (só leitura) numa sub-tela, com seções recolhíveis. Offline: ficha via cache
// por animal (chave "ficha_<numero>").
import { useEffect, useState } from "react";
import { fetchFichaAnimal, formatDate } from "@/lib/api";
import { fetchComCache, cacheEm } from "@/lib/offline";
import { MobCard, MobVoltar, MobLinha } from "@/components/mobile/ui";
import { BuscaAnimal, lerRecentes, registrarRecente, subtituloAnimal, type Recente } from "./comum";

type Ficha = {
  animal: Record<string, unknown>;
  colostragem: Record<string, unknown> | null;
  compra: Record<string, unknown> | null;
  baixa: Record<string, unknown> | null;
} & Record<string, Record<string, unknown>[] | Record<string, unknown> | null>;

// Grupos de lançamentos (as chaves batem com o retorno de /animais/{n}/ficha).
type Campo = [chave: string, rotulo: string, data?: boolean];
const SECOES: { chave: string; titulo: string; campos: Campo[] }[] = [
  { chave: "movimentos_lote", titulo: "Movimentações de lote", campos: [["data_movimento", "Data", true], ["lote_origem", "De"], ["lote_destino", "Para"], ["motivo", "Motivo"]] },
  { chave: "partos", titulo: "Partos", campos: [["data_parto", "Data", true], ["ordem_parto", "Ordem"], ["tipo_parto", "Tipo"]] },
  { chave: "servicos", titulo: "Reprodução — serviço/IA", campos: [["data_servico", "Data", true], ["tipo_servico", "Tipo"], ["reprodutor", "Reprodutor"], ["diagnostico", "Diagnóstico"]] },
  { chave: "protocolos_iatf", titulo: "Protocolo IATF", campos: [["dia", "Dia"], ["descricao", "Descrição"], ["data_prevista", "Prevista", true], ["realizada", "Feito"]] },
  { chave: "controles_leiteiros", titulo: "Controle leiteiro", campos: [["data_controle", "Data", true], ["producao_kg", "Produção (kg)"], ["del_no_controle", "DEL"]] },
  { chave: "pesagens_corporais", titulo: "Pesagens", campos: [["data_pesagem", "Data", true], ["peso_kg", "Peso (kg)"], ["del_dias", "DEL"]] },
  { chave: "qualidade_leite", titulo: "Qualidade do leite", campos: [["data_coleta", "Data", true], ["ccs", "CCS"], ["cbt", "CBT"]] },
  { chave: "aplicacoes_sanitarias", titulo: "Sanidade — aplicações", campos: [["data_aplicacao", "Data", true], ["produto", "Produto"], ["dose", "Dose"], ["unidade", "Un."]] },
  { chave: "protocolos_sanitarios", titulo: "Protocolos sanitários", campos: [["data_inicio", "Data", true], ["protocolo_nome", "Protocolo"], ["classificacao_mastite", "Mastite"]] },
  { chave: "secagens", titulo: "Secagens", campos: [["data_secagem", "Data", true], ["motivo", "Motivo"]] },
  { chave: "eventos_agenda", titulo: "Agenda — eventos", campos: [["data_evento", "Data", true], ["descricao", "Descrição"], ["categoria", "Categoria"]] },
];

function mostrarValor(v: unknown, data?: boolean): string {
  if (v == null || v === "") return "—";
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  if (data) return formatDate(String(v));
  return String(v);
}

const rotulo: React.CSSProperties = { fontSize: "0.7rem", color: "var(--mob-muted)", fontWeight: 600 };

function ParDado({ label, valor }: { label: string; valor: React.ReactNode }) {
  return (
    <div>
      <span style={rotulo}>{label}</span>
      <div style={{ fontSize: "0.95rem", fontWeight: 600 }}>{valor}</div>
    </div>
  );
}

function Grade({ children }: { children: React.ReactNode }) {
  return <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.7rem 1rem" }}>{children}</div>;
}

function Secao({ titulo, linhas, campos }: { titulo: string; linhas: Record<string, unknown>[]; campos: Campo[] }) {
  if (!linhas.length) return null;
  return (
    <details style={{ marginBottom: "0.7rem" }}>
      <summary style={{ cursor: "pointer", fontWeight: 700, fontSize: "0.95rem", padding: "0.85rem 1rem", background: "var(--mob-surface)", border: "1px solid var(--mob-border)", borderRadius: 14, listStyle: "none", display: "flex", justifyContent: "space-between", alignItems: "center", boxShadow: "var(--mob-sombra)" }}>
        <span>{titulo}</span>
        <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)", fontWeight: 700 }}>{linhas.length}</span>
      </summary>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
        {linhas.map((l, i) => (
          <MobCard key={i}>
            <Grade>
              {campos.map(([chave, rot, data]) => (
                <ParDado key={chave} label={rot} valor={mostrarValor(l[chave], data)} />
              ))}
            </Grade>
          </MobCard>
        ))}
      </div>
    </details>
  );
}

function FichaDetalhe({ numero, onVoltar }: { numero: string; onVoltar: () => void }) {
  const [ficha, setFicha] = useState<Ficha | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [doCache, setDoCache] = useState(false);

  useEffect(() => {
    let vivo = true;
    setCarregando(true); setErro(null);
    fetchComCache<Ficha>(`ficha_${numero}`, () => fetchFichaAnimal(numero))
      .then(({ dados, doCache }) => {
        if (!vivo) return;
        if (dados) {
          setFicha(dados);
          setDoCache(doCache);
          const a = dados.animal || {};
          registrarRecente({ numero, categoria_abrev: (a.categoria_abrev as string) ?? null, grupo_primario: (a.grupo_primario as string) ?? null });
        } else {
          setErro("Sem internet e sem cópia salva desta ficha.");
        }
      })
      .catch((e) => { if (vivo) setErro(e?.message || "Erro ao carregar ficha."); })
      .finally(() => { if (vivo) setCarregando(false); });
    return () => { vivo = false; };
  }, [numero]);

  const a = ficha?.animal;
  const colostragem = ficha?.colostragem as Record<string, unknown> | null;
  const baixa = ficha?.baixa as Record<string, unknown> | null;
  const compra = ficha?.compra as Record<string, unknown> | null;

  return (
    <div>
      <MobVoltar titulo={`Brinco ${numero}`} onVoltar={onVoltar} />
      {carregando && <p style={{ color: "var(--mob-muted)" }}>Carregando ficha…</p>}
      {erro && <p style={{ color: "var(--mob-vermelho)", fontWeight: 600 }}>{erro}</p>}

      {a && (
        <>
          {doCache && (
            <p style={{ fontSize: "0.78rem", color: "var(--mob-ambar)", fontWeight: 600, marginBottom: "0.6rem" }}>
              Mostrando cópia salva{cacheEm(`ficha_${numero}`) ? ` em ${new Date(cacheEm(`ficha_${numero}`)!).toLocaleString("pt-BR")}` : ""}.
            </p>
          )}

          <MobCard style={{ marginBottom: "0.7rem" }}>
            <div style={{ fontWeight: 800, fontSize: "1.05rem", marginBottom: "0.7rem" }}>
              {String(a.nome || `Brinco ${a.numero}`)}
              <span style={{ color: a.ativo === false ? "var(--mob-vermelho)" : "var(--mob-verde)", fontSize: "0.8rem", fontWeight: 700, marginLeft: "0.5rem" }}>
                {a.ativo === false ? "Baixado" : "Ativo"}
              </span>
            </div>
            <Grade>
              <ParDado label="Sexo" valor={a.sexo === "M" ? "Macho" : a.sexo === "F" ? "Fêmea" : "—"} />
              <ParDado label="Categoria" valor={String(a.categoria_abrev || a.categoria_completa || "—")} />
              <ParDado label="Lote atual" valor={String(a.grupo_primario || "—")} />
              <ParDado label="Raça" valor={String(a.raca || "—")} />
              <ParDado label="Nascimento" valor={a.data_nasc ? formatDate(String(a.data_nasc)) : "—"} />
              <ParDado label="Entrada" valor={a.data_entrada ? formatDate(String(a.data_entrada)) : "—"} />
              <ParDado label="Mãe" valor={String(a.mae_numero || "—")} />
              <ParDado label="DEL" valor={a.del_dias != null ? String(a.del_dias) : "—"} />
            </Grade>
          </MobCard>

          {colostragem && (
            <MobCard style={{ marginBottom: "0.7rem" }}>
              <div style={{ fontWeight: 700, marginBottom: "0.6rem" }}>Colostragem / IgG</div>
              <Grade>
                <ParDado label="Tomou colostro?" valor={mostrarValor(colostragem.tomou_colostro)} />
                <ParDado label="Litros" valor={mostrarValor(colostragem.litros_colostro)} />
                <ParDado label="Brix colostro" valor={mostrarValor(colostragem.brix_colostro)} />
                <ParDado label="Brix soro" valor={mostrarValor(colostragem.brix_soro)} />
              </Grade>
            </MobCard>
          )}

          {compra && (
            <MobCard style={{ marginBottom: "0.7rem" }}>
              <div style={{ fontWeight: 700, marginBottom: "0.6rem" }}>Compra</div>
              <Grade>
                <ParDado label="Data" valor={mostrarValor(compra.data_compra, true)} />
                <ParDado label="Vendedor" valor={mostrarValor(compra.vendedor)} />
                <ParDado label="Valor" valor={compra.valor != null ? `R$ ${compra.valor}` : "—"} />
                <ParDado label="Responsável" valor={mostrarValor(compra.responsavel)} />
              </Grade>
            </MobCard>
          )}

          {baixa && (
            <MobCard style={{ marginBottom: "0.7rem", borderColor: "var(--mob-vermelho)" }}>
              <div style={{ fontWeight: 700, marginBottom: "0.6rem", color: "var(--mob-vermelho)" }}>Baixa (saída do rebanho)</div>
              <Grade>
                <ParDado label="Data" valor={mostrarValor(baixa.data_baixa, true)} />
                <ParDado label="Tipo" valor={mostrarValor(baixa.tipo_baixa)} />
                <ParDado label="Motivo" valor={mostrarValor(baixa.motivo)} />
                <ParDado label="Valor" valor={baixa.valor != null ? `R$ ${baixa.valor}` : "—"} />
              </Grade>
            </MobCard>
          )}

          <div className="mob-secao">Lançamentos</div>
          {SECOES.map((s) => (
            <Secao key={s.chave} titulo={s.titulo} campos={s.campos} linhas={(ficha?.[s.chave] as Record<string, unknown>[]) || []} />
          ))}
          {SECOES.every((s) => !((ficha?.[s.chave] as unknown[]) || []).length) && (
            <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum lançamento registrado para este animal.</p>
          )}
        </>
      )}
    </div>
  );
}

export default function Ficha() {
  const [aberto, setAberto] = useState<string | null>(null);
  const [recentes, setRecentes] = useState<Recente[]>([]);

  useEffect(() => { setRecentes(lerRecentes()); }, [aberto]);

  if (aberto) return <FichaDetalhe numero={aberto} onVoltar={() => setAberto(null)} />;

  return (
    <div>
      <BuscaAnimal valor="" onEscolher={(n) => { if (n) setAberto(n); }} />

      <div className="mob-secao">Animais recentes</div>
      {recentes.length === 0 && <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum animal aberto ainda. Use a busca acima.</p>}
      {recentes.map((r) => (
        <MobLinha key={r.numero} titulo={`Brinco ${r.numero}`} subtitulo={subtituloAnimal(r)} onClick={() => setAberto(r.numero)} />
      ))}
    </div>
  );
}
