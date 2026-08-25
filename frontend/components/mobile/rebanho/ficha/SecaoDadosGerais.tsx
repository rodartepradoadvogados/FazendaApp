"use client";
// Seção DADOS GERAIS — identificação, origem/cadastro e genealogia.
// "Idade" é calculada aqui (não existe em nenhuma das duas fichas hoje —
// melhoria nova sobre o desktop, ver plano de redesenho).
import { formatDate } from "@/lib/api";
import { MobCard } from "@/components/mobile/ui";
import { Grade, ParDado, mostrarValor, criarAlternador, tituloCartao, type Ficha } from "./comumFicha";

/** "5 anos e 5 meses" / "3 meses" / "12 dias" — degrada para a unidade maior
 * disponível conforme a idade cresce. `dataNascIso` no formato YYYY-MM-DD
 * (ou qualquer string aceita por `new Date`). */
function calcularIdade(dataNascIso: string): string {
  const nasc = new Date(`${dataNascIso}T00:00:00`);
  const hoje = new Date();
  if (Number.isNaN(nasc.getTime()) || nasc > hoje) return "—";
  let anos = hoje.getFullYear() - nasc.getFullYear();
  let meses = hoje.getMonth() - nasc.getMonth();
  if (hoje.getDate() < nasc.getDate()) meses--;
  if (meses < 0) { anos--; meses += 12; }
  if (anos <= 0 && meses <= 0) {
    const dias = Math.max(0, Math.round((hoje.getTime() - nasc.getTime()) / 86400000));
    return `${dias} ${dias === 1 ? "dia" : "dias"}`;
  }
  const partes: string[] = [];
  if (anos > 0) partes.push(`${anos} ${anos === 1 ? "ano" : "anos"}`);
  if (meses > 0) partes.push(`${meses} ${meses === 1 ? "mês" : "meses"}`);
  return partes.join(" e ");
}

export function SecaoDadosGerais({ ficha }: { ficha: Ficha }) {
  const a = ficha.animal;
  const proximoAlt = criarAlternador();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
      <MobCard alt={proximoAlt()}>
        <p style={tituloCartao}>Identificação</p>
        <Grade>
          <ParDado label="Nome completo" valor={mostrarValor(a.nome)} />
          <ParDado label="Sexo" valor={a.sexo === "M" ? "Macho" : a.sexo === "F" ? "Fêmea" : "—"} />
          <ParDado label="Categoria" valor={mostrarValor(a.categoria_abrev || a.categoria_completa)} />
          <ParDado label="Raça" valor={mostrarValor(a.raca)} />
          <ParDado label="Grau de sangue" valor={mostrarValor(a.grau_sangue)} />
          <ParDado label="Data de nascimento" valor={a.data_nasc ? formatDate(String(a.data_nasc)) : "—"} />
          <ParDado label="Idade" valor={a.data_nasc ? calcularIdade(String(a.data_nasc)) : "—"} />
          <ParDado label="Data de entrada" valor={a.data_entrada ? formatDate(String(a.data_entrada)) : "—"} />
        </Grade>
      </MobCard>

      <MobCard alt={proximoAlt()}>
        <p style={tituloCartao}>Origem &amp; cadastro</p>
        <Grade>
          <ParDado label="Proprietário" valor={mostrarValor(a.proprietario)} />
          <ParDado label="Valor" valor={a.valor != null ? `R$ ${a.valor}` : "—"} />
          <div style={{ gridColumn: "1 / -1" }}>
            <ParDado label="Observações" valor={mostrarValor(a.observacoes)} />
          </div>
        </Grade>
      </MobCard>

      <MobCard alt={proximoAlt()}>
        <p style={tituloCartao}>Genealogia</p>
        <Grade>
          <ParDado label="Mãe" valor={a.mae_numero ? `Nº ${a.mae_numero}${a.mae_nome ? ` — ${a.mae_nome}` : ""}` : "—"} />
          <ParDado label="Pai" valor={ficha.pai?.nome ? `${ficha.pai.nome}${ficha.pai.naab ? ` (NAAB ${ficha.pai.naab})` : ""}` : "—"} />
        </Grade>
        {/* Avô/bisavô paterno: a ficha de mesa (FichaAnimal.tsx) também não
            expõe esses dois níveis hoje — `ficha.pai` só traz nome/NAAB/
            central/TPI/NM$ do pai direto (ver backend fazenda/api/routers/
            animais.py › ficha_animal). Sem esse dado no payload atual, não
            há como mostrar avô/bisavô aqui sem inventar — ficaria para uma
            mudança de backend futura (buscar o pai do pai no cadastro de
            touros/reprodutores), fora do escopo deste redesenho visual. */}
      </MobCard>
    </div>
  );
}
