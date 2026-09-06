"use client";
import { useEffect, useMemo, useState } from "react";
import { formatBRL, type LinhaFolhaUnificada } from "@/lib/api";
import { Modal } from "@/components/Modal";
import { dataBR } from "@/lib/holerite";
import {
  eventosDaPessoa, notaDoGrupo, resumoDaPessoa, type EventoPessoa, type TomEvento,
  type ValeDaLinhaTempo,
} from "@/lib/linhaTempoPessoa";

/*
 * A linha do tempo de uma pessoa na folha.
 *
 * POR QUE ELA EXISTE. A tela de mês responde "quanto sai agora" e, por
 * construção, não alcança a pergunta que o desconto de vale cria: a parcela
 * 3/13 aparece no recibo de setembro e o vale de março, que a gerou, não tem
 * onde ser visto ao lado dela. Aqui a folha de setembro é UM evento entre o
 * vale de março e as parcelas que ele foi gerando — e clicar no vale ACENDE
 * todas as competências em que ele é descontado.
 *
 * O que faz o acender funcionar é o `vale_id` viajando em cada linha do
 * holerite: dois vales com parcela de mesmo valor no mesmo mês eram
 * exatamente o caso em que a identificação pelo valor terminava num palpite.
 *
 * O que esta ficha NÃO tem, de propósito: as abas "Recibos", "Vales" e
 * "Cadastro" do desenho. Recibos e Vales seriam uma segunda cópia do que a
 * tela por trás já mostra (a tabela de folha e o relatório de vales, ambos com
 * filtro por pessoa), e Cadastro é outra tela inteira — abas que só levam de
 * volta para onde o usuário estava não são navegação, são espera.
 */

const TONS: Record<TomEvento, string> = {
  pago: "var(--green-light)",
  aberto: "var(--text-muted)",
  vencido: "var(--red)",
  estourada: "var(--red)",
  vale: "var(--dourado-light)",
  parcela: "var(--vinho-light, var(--vinho))",
};

const GRADE = "5.5rem 1rem minmax(0, 1fr) 6.5rem 7rem";

const rotulo: React.CSSProperties = {
  fontSize: "0.62rem", fontWeight: 700, letterSpacing: "0.05em",
  textTransform: "uppercase", color: "var(--text-muted)",
};

function iniciais(nome: string): string {
  const partes = nome.trim().split(/\s+/);
  return ((partes[0]?.[0] || "") + (partes.length > 1 ? partes[partes.length - 1][0] : "")).toUpperCase();
}

function Evento({ evento, aceso, onTocar }: {
  evento: EventoPessoa; aceso: boolean; onTocar: () => void;
}) {
  const cor = TONS[evento.tom];
  return (
    <div
      className={evento.grupo ? "row-clickable" : undefined}
      onClick={evento.grupo ? onTocar : undefined}
      title={evento.grupo ? "Clique para acender todas as competências deste vale" : undefined}
      style={{
        display: "grid", gridTemplateColumns: GRADE, gap: "0.5rem", alignItems: "center",
        padding: "0.5rem 0.7rem", borderBottom: "1px solid var(--border)",
        background: aceso ? "color-mix(in srgb, var(--dourado-light) 14%, transparent)" : undefined,
        cursor: evento.grupo ? "pointer" : undefined,
      }}
    >
      <div style={{ fontSize: "0.76rem", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
        {dataBR(evento.data)}
      </div>
      <div style={{ display: "flex", justifyContent: "center" }}>
        <span style={{ width: "0.5rem", height: "0.5rem", borderRadius: "50%", background: cor }} />
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: "0.82rem", fontWeight: 600 }}>{evento.titulo}</div>
        <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.05rem" }}>{evento.sub}</div>
      </div>
      <div style={{ textAlign: "right" }}>
        <span style={{
          display: "inline-block", padding: "0.05rem 0.45rem", borderRadius: "999px",
          fontSize: "0.66rem", fontWeight: 700,
          background: `color-mix(in srgb, ${cor} 16%, transparent)`, color: cor,
        }}>{evento.selo}</span>
      </div>
      <div style={{
        textAlign: "right", fontSize: "0.84rem", fontWeight: 600, fontVariantNumeric: "tabular-nums",
        // O sinal do dinheiro na leitura da PESSOA: o desconto sai dela.
        color: evento.sentido === "desconta" ? "var(--red)" : evento.tom === "estourada" ? "var(--red)" : undefined,
      }}>
        {evento.sentido === "desconta" ? "− " : ""}{formatBRL(evento.valor)}
      </div>
    </div>
  );
}

function Tile({ titulo, valor, nota, cor }: { titulo: string; valor: string; nota: string; cor?: string }) {
  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)",
      borderLeft: cor ? `3px solid ${cor}` : "1px solid var(--border)",
      borderRadius: "var(--r-sm)", padding: "0.6rem 0.75rem",
    }}>
      <div style={{ ...rotulo, color: cor || rotulo.color }}>{titulo}</div>
      <div style={{ fontSize: "1rem", fontWeight: 700, fontVariantNumeric: "tabular-nums", marginTop: "0.1rem", color: cor }}>
        {valor}
      </div>
      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.05rem" }}>{nota}</div>
    </div>
  );
}

export function LinhaTempoPessoa({ pessoa, linhas, vales, ano, onFechar }: {
  pessoa: { id: number; nome: string; tipos: string[]; data_admissao?: string | null };
  linhas: LinhaFolhaUnificada[];
  vales: ValeDaLinhaTempo[];
  /** Ano dos totais do rodapé — o do mês que está aberto na tela de trás. */
  ano: string;
  onFechar: () => void;
}) {
  const [grupo, setGrupo] = useState<string | null>(null);
  // Monta fechada e abre no quadro seguinte, para o CSS ter um estado inicial
  // real de onde animar (mesma técnica do cartão de origem do holerite).
  // Guarda QUAL grupo já animou, e não um booleano: com um booleano, apagar o
  // grupo exigiria um setState síncrono dentro do efeito (renderização em
  // cascata). Comparando com o grupo atual, a nota nasce fechada de graça a
  // cada troca.
  const [grupoAnimado, setGrupoAnimado] = useState<string | null>(null);
  useEffect(() => {
    if (!grupo) return;
    const id = requestAnimationFrame(() => requestAnimationFrame(() => setGrupoAnimado(grupo)));
    return () => cancelAnimationFrame(id);
  }, [grupo]);
  const notaAberta = !!grupo && grupoAnimado === grupo;

  const eventos = useMemo(
    () => eventosDaPessoa(linhas, vales, pessoa.id, formatBRL),
    [linhas, vales, pessoa.id],
  );
  const resumo = useMemo(() => resumoDaPessoa(linhas, vales, pessoa.id, ano), [linhas, vales, pessoa.id, ano]);
  const nota = useMemo(() => (grupo ? notaDoGrupo(vales, grupo, formatBRL) : null), [vales, grupo]);

  const vinculo = [
    pessoa.tipos.join(", ") || "sem tipo no cadastro",
    pessoa.data_admissao ? `admitido em ${dataBR(pessoa.data_admissao)}` : "",
  ].filter(Boolean).join(" · ");

  return (
    <Modal title={`Linha do tempo — ${pessoa.nome}`} width="960px" onClose={onFechar}>
      {/* Identificação — quem é, e o que ela deve à fazenda agora. O saldo de
          vale em aberto fica aqui porque é o número que explica a maior parte
          do que a linha do tempo abaixo mostra. */}
      <div
        className="flex items-start gap-3 mb-3"
        style={{
          background: "var(--card-header-bg)", color: "var(--card-header-fg)",
          borderRadius: "var(--r-md, 8px)", padding: "0.8rem 1rem", flexWrap: "wrap",
        }}
      >
        <div style={{
          width: "2.6rem", height: "2.6rem", borderRadius: "50%", flexShrink: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          background: "color-mix(in srgb, var(--card-header-fg) 16%, transparent)",
          border: "1px solid color-mix(in srgb, var(--card-header-fg) 40%, transparent)",
          fontSize: "0.9rem", fontWeight: 700,
        }}>{iniciais(pessoa.nome)}</div>
        <div style={{ flexGrow: 1, minWidth: "12rem" }}>
          <div style={{ fontSize: "0.95rem", fontWeight: 700 }}>{pessoa.nome}</div>
          <div style={{ fontSize: "0.72rem", opacity: 0.72, marginTop: "0.1rem" }}>{vinculo}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ ...rotulo, color: "inherit", opacity: 0.6 }}>Saldo de vales em aberto</div>
          <div style={{ fontSize: "1.05rem", fontWeight: 700, fontVariantNumeric: "tabular-nums", color: "var(--dourado-light)" }}>
            {formatBRL(resumo.saldoValesAberto)}
          </div>
          <div style={{ fontSize: "0.7rem", opacity: 0.6 }}>
            {resumo.parcelasAberto} {resumo.parcelasAberto === 1 ? "parcela a descontar" : "parcelas a descontar"}
          </div>
        </div>
      </div>

      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-md, 8px)", overflow: "hidden" }}>
        <div className="flex items-baseline gap-2" style={{
          padding: "0.55rem 0.7rem", background: "var(--surface-2)",
          borderBottom: "1px solid var(--border)", flexWrap: "wrap",
        }}>
          <span style={{ fontSize: "0.78rem", fontWeight: 700 }}>Linha do tempo</span>
          <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
            clique num vale para acender todas as competências em que ele é descontado
          </span>
        </div>
        <div style={{ maxHeight: "26rem", overflowY: "auto" }}>
          {eventos.map((e) => (
            <Evento
              key={e.id} evento={e} aceso={!!grupo && e.grupo === grupo}
              onTocar={() => setGrupo(grupo === e.grupo ? null : e.grupo)}
            />
          ))}
          {!eventos.length && (
            <p style={{ padding: "0.9rem", fontSize: "0.8rem", color: "var(--text-muted)" }}>
              Nenhum pagamento nem vale lançado para esta pessoa.
            </p>
          )}
        </div>
      </div>

      {nota && (
        <div className={`painel-expansivel${notaAberta ? " painel-expansivel-aberto" : ""}`}>
          <div>
            <div className="flash-localizado" style={{
              marginTop: "0.6rem", padding: "0.7rem 0.85rem", background: "var(--surface)",
              border: "1px solid var(--border)", borderLeft: "3px solid var(--dourado-light)",
              borderRadius: "var(--r-sm)",
            }}>
              <div style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--vinho)" }}>{nota.titulo}</div>
              <div style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.15rem", lineHeight: 1.45 }}>
                {nota.texto}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3" style={{ marginTop: "0.8rem" }}>
        <Tile
          titulo={`Recebido em ${ano}`}
          valor={formatBRL(resumo.recebidoNoAno)}
          nota={`${resumo.pagamentosNoAno} ${resumo.pagamentosNoAno === 1 ? "pagamento com baixa" : "pagamentos com baixa"}`}
        />
        <Tile
          titulo={`Vales tirados em ${ano}`}
          valor={formatBRL(resumo.valeTiradoNoAno)}
          nota={
            `${resumo.valesNoAno} ${resumo.valesNoAno === 1 ? "vale" : "vales"}` +
            // Só compara com o que ela EFETIVAMENTE recebeu: sem pagamento com
            // baixa no ano, a proporção não existe — e inventar 0% mentiria.
            (resumo.proporcaoValeSobreRecebido != null
              ? ` · ${Math.round(resumo.proporcaoValeSobreRecebido * 100)}% do que recebeu`
              : " · sem pagamento no ano para comparar")
          }
        />
        {resumo.competenciasEstouradas.length > 0 ? (
          <Tile
            titulo="Competência estourada"
            valor={resumo.competenciasEstouradas.map((c) => c.competencia).join(", ")}
            nota={`descontos passam o salário em ${formatBRL(resumo.competenciasEstouradas.reduce((a, c) => a + c.excedente, 0))}`}
            cor="var(--red)"
          />
        ) : (
          <Tile titulo="Competência estourada" valor="Nenhuma" nota="nenhum mês com desconto maior que o salário" />
        )}
      </div>
    </Modal>
  );
}
