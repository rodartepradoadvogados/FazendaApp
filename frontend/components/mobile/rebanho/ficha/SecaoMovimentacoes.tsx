"use client";
// Seção MOVIMENTAÇÕES — a seção "guarda-chuva" para tudo que é registro/
// documento (GTA, compra, venda, baixa, movimentação de lote, agenda), não
// dado clínico ou produtivo. GTA/Compra/Venda/Baixa já existiam no mobile
// como cards soltos — só mudaram de arquivo, sem reescrever a lógica.
import { formatDate } from "@/lib/api";
import { MobCard } from "@/components/mobile/ui";
import { Grade, ParDado, Secao, secaoPorChave, mostrarValor, tituloCartao, type Ficha } from "./comumFicha";

export function SecaoMovimentacoes({ ficha }: { ficha: Ficha }) {
  const baixa = ficha.baixa as Record<string, unknown> | null;
  const compra = ficha.compra as Record<string, unknown> | null;
  const compras = (ficha.compras as Record<string, unknown>[] | undefined) || (compra ? [compra] : []);
  const vendas = (ficha.vendas as Record<string, unknown>[] | undefined) || [];

  let altContador = 0;
  const proximoAlt = (): 0 | 1 => (altContador++ % 2) as 0 | 1;

  function acordeao(chave: string) {
    const s = secaoPorChave(chave);
    const linhas = (ficha[chave] as Record<string, unknown>[]) || [];
    const altInicio = altContador;
    altContador += linhas.length;
    return <Secao key={chave} chave={chave} titulo={s.titulo} campos={s.campos} linhas={linhas} altInicio={altInicio} />;
  }

  const semDocumento = !ficha.gtas?.length && !compras.length && !vendas.length && !baixa;

  return (
    <div>
      {!!ficha.gtas?.length && (
        <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem" }}>
          <p style={tituloCartao}>GTA(s) do animal</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
            {ficha.gtas.map((g) => (
              <span key={g} style={{ fontSize: "0.78rem", fontWeight: 700, padding: "0.25rem 0.6rem", background: "var(--mob-surface-2)", border: "1px solid var(--mob-border)", color: "var(--mob-dourado-2)" }}>
                GTA {g}
              </span>
            ))}
          </div>
        </MobCard>
      )}

      {compras.map((c, i) => (
        <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem" }} key={`compra-${i}`}>
          <p style={tituloCartao}>Compra{compras.length > 1 ? ` (${i + 1}/${compras.length})` : ""}</p>
          <Grade>
            <ParDado label="Data" valor={mostrarValor(c.data_compra, true)} />
            <ParDado label="Vendedor" valor={mostrarValor(c.vendedor)} />
            <ParDado label="Valor" valor={c.valor != null ? `R$ ${c.valor}` : "—"} />
            <ParDado label="GTA" valor={mostrarValor(c.gta)} />
            <ParDado label="Responsável" valor={mostrarValor(c.responsavel)} />
          </Grade>
        </MobCard>
      ))}

      {vendas.map((v, i) => (
        <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem" }} key={`venda-${i}`}>
          <p style={tituloCartao}>Venda{vendas.length > 1 ? ` (${i + 1}/${vendas.length})` : ""}</p>
          <Grade>
            <ParDado label="Data" valor={mostrarValor(v.data_venda, true)} />
            <ParDado label="Comprador" valor={mostrarValor(v.comprador)} />
            <ParDado label="Valor" valor={v.valor != null ? `R$ ${v.valor}` : "—"} />
            <ParDado label="GTA" valor={mostrarValor(v.gta)} />
            <ParDado label="Responsável" valor={mostrarValor(v.responsavel)} />
          </Grade>
        </MobCard>
      ))}

      {baixa && (
        <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem", borderColor: "var(--mob-vermelho)" }}>
          <p style={{ ...tituloCartao, color: "var(--mob-vermelho)" }}>Baixa (saída do rebanho)</p>
          <Grade>
            <ParDado label="Data" valor={mostrarValor(baixa.data_baixa, true)} />
            <ParDado label="Tipo" valor={mostrarValor(baixa.tipo_baixa)} />
            <ParDado label="Motivo" valor={mostrarValor(baixa.motivo)} />
            <ParDado label="Valor" valor={baixa.valor != null ? `R$ ${baixa.valor}` : "—"} />
          </Grade>
        </MobCard>
      )}

      {semDocumento && (
        <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem" }}>
          <p style={{ fontSize: "0.82rem", color: "var(--mob-muted)" }}>Nasceu na fazenda — sem registro de compra, venda ou baixa.</p>
        </MobCard>
      )}

      {acordeao("movimentos_lote")}
      {acordeao("eventos_agenda")}
    </div>
  );
}
