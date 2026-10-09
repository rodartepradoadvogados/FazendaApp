import { test } from "node:test";
import assert from "node:assert/strict";
import {
  algumaFaixaVisivel, criteriosDoSelo, escalaRegua, formatarValorRegua, fraseReguas, limiteFaixa, linhasExportacaoReguas,
  linhasReguas, mostraFaixa, paragrafos, porqueSemFaixa, posicaoEmPalavras, textoAutorizacao, textoFaixa,
  type Regua, type RespostaIndicadoresReguas, type RespostaReguas,
} from "./reguasReferencia.ts";

// Exemplo SÓ de teste (o JSON versionado não tem régua publicada): uma publicada, uma em validação e uma sem faixa.
const regua = (o: Partial<Regua>): Regua => ({
  codigo: "comida_receita", nome: "Comida ÷ receita do leite", unidade: "%", definicao_cowdata: "Alimentação ÷ receita do leite.",
  situacao: "em_validacao", publicavel: false, exibir_faixa: false, faixa: null, fidedignidade: null, ressalva: null,
  compilado_em: null, vence_em: null, fontes: [], ...o,
});
const PUBLICADA = regua({
  situacao: "publicada", publicavel: true, exibir_faixa: true, faixa: { min: 40, max: 55, eficiente_ate: 45, atencao_acima: 60 },
  fidedignidade: "alta", ressalva: "Ressalva.", compilado_em: "2026-10-08", vence_em: "2027-10-08",
  fontes: [{ id: "f1", nome: "Fonte BR", ano: 2025, url: "https://exemplo.org", origem: "nacional" }],
});
const resp = (reguas: Regua[], o: Partial<RespostaReguas> = {}): RespostaReguas => ({
  versao: "2026-10", versao_reguas: "2026-10", revisado_em: "2026-10-08", conferida_em: "2026-10-08", valido_ate: "2027-10-08",
  proxima_conferencia: "2026-11-02", vencida: false, publicacao: { liberada: true }, empresa_pendente: false,
  aceite: { tipo: "reguas", versao: "1", sha256: "x".repeat(64), pendente: false, aceito_em_utc: "2026-10-09T10:00:00Z" },
  aceite_pendente: false, faixas_ocultas_ate_aceite: false,
  textos: {} as RespostaReguas["textos"], reguas, ...o,
});
const ind = (m: Record<string, number | null>): RespostaIndicadoresReguas => ({
  periodo: { inicio: "2026-09-01", fim: "2026-09-30" }, regime: "competencia", centro_custo: null, regras_v2: true,
  indicadores: Object.fromEntries(Object.entries(m).map(([k, v]) => [k, { valor: v, conta: v == null ? null : "A ÷ B", relatorio: "rel_dre", motivo: v == null ? "falta dado" : null }])),
});

test("faixa só aparece publicada, sem aceite pendente e dentro da validade", () => {
  assert.equal(mostraFaixa(PUBLICADA, resp([PUBLICADA])), true);
  assert.equal(mostraFaixa(PUBLICADA, { aceite_pendente: true, vencida: false }), false);
  assert.equal(mostraFaixa(PUBLICADA, { aceite_pendente: false, vencida: true }), false);
  for (const s of ["em_validacao", "retirada", "vencida", "sem_faixa"] as const) {
    // Mesmo que a API mandasse uma faixa fora de "publicada", a tela não mostra (defesa em camadas).
    assert.equal(mostraFaixa({ ...PUBLICADA, situacao: s }, resp([])), false, s);
    assert.ok(porqueSemFaixa({ ...PUBLICADA, situacao: s }, resp([])), s);
  }
  assert.equal(algumaFaixaVisivel(resp([regua({})])), false);
  assert.equal(algumaFaixaVisivel(resp([PUBLICADA])), true);
  assert.match(porqueSemFaixa(regua({ situacao: "sem_faixa", unidade: "R$/L" }), resp([]))!, /Valores em reais não viram faixa/);
  assert.match(porqueSemFaixa(PUBLICADA, { aceite_pendente: true, vencida: false })!, /depois que você ler/);
});

test("linguagem neutra: posição em palavras, nunca meta, média, alvo ou zona de atenção", () => {
  const r = resp([PUBLICADA]);
  assert.equal(posicaoEmPalavras(PUBLICADA, 50, r), "dentro da faixa de referência");
  assert.equal(posicaoEmPalavras(PUBLICADA, 62, r), "maior que a faixa de referência");
  assert.equal(posicaoEmPalavras(PUBLICADA, 30, r), "menor que a faixa de referência");
  assert.equal(posicaoEmPalavras(PUBLICADA, null, r), "sem número no período");
  assert.equal(posicaoEmPalavras(regua({}), 30, r), "sem faixa de referência para comparar");
  assert.equal(textoFaixa(PUBLICADA), "referência de 40 a 55%");
  assert.equal(textoFaixa(regua({ faixa: { max: 35 } })), "referência até 35%");
  assert.equal(textoFaixa(regua({ unidade: "meses", faixa: { min: 1.5 } })), "referência a partir de 1,5 mês");
  const tudo = [textoFaixa(PUBLICADA), ...[30, 50, 62].map((v) => posicaoEmPalavras(PUBLICADA, v, r)),
    ...(["em_validacao", "retirada", "vencida", "sem_faixa"] as const).map((s) => porqueSemFaixa({ ...PUBLICADA, situacao: s }, r))].join(" ");
  assert.doesNotMatch(tudo, /\bmeta\b|média|alvo|eficient|atenção|bom|ruim|padrão/i);
});

test("formatos por unidade e limites sem casas inúteis", () => {
  assert.equal(formatarValorRegua("%", 35), "35,0%");
  assert.equal(formatarValorRegua("x", 1.456), "1,46×");
  assert.equal(formatarValorRegua("meses", 1.3), "1,3 mês");
  assert.equal(formatarValorRegua("meses", 2.5), "2,5 meses");
  assert.equal(formatarValorRegua("R$/L", 2.0012), "R$ 2,00/L");
  assert.equal(formatarValorRegua("L", 362.4), "362 L");
  assert.equal(formatarValorRegua("%", null), "—");
  assert.equal(formatarValorRegua("%", -4), "−4,0%");
  assert.equal(limiteFaixa("x", 1.25), "1,25×");
});

test("escala do trilho inclui o número da fazenda e só a faixa visível", () => {
  const e = escalaRegua(PUBLICADA, 50, resp([PUBLICADA]))!;
  assert.ok(e.min <= 40 && e.max >= 55);
  const semFaixa = escalaRegua(regua({}), 50, resp([]))!;
  assert.ok(semFaixa.min <= 50 && semFaixa.max >= 50);
  assert.equal(escalaRegua(regua({}), null, resp([])), null);
});

test("textos jurídicos: parágrafos sem mudar uma letra, critério do selo lido do pop-up, autorização com destinatário", () => {
  const alerta = "TÍTULO.\n\nPrimeiro parágrafo.\nCom quebra.\n\nÚltimo.";
  assert.deepEqual(paragrafos(alerta), ["TÍTULO.", "Primeiro parágrafo.\nCom quebra.", "Último."]);
  assert.equal(paragrafos(alerta).join("\n\n"), alerta);
  const modal = "QUÃO CONFIÁVEL É\n• Alta: várias fontes recentes.\n• Média: poucas fontes.\n• Baixa: pouca base.\nCada indicador…";
  assert.deepEqual(criteriosDoSelo(modal), { alta: "várias fontes recentes.", media: "poucas fontes.", baixa: "pouca base." });
  assert.equal(textoAutorizacao("Autorizo o envio deste relatório a {{destinatario}}.", " Banco X "), "Autorizo o envio deste relatório a Banco X.");
  assert.equal(textoAutorizacao("Autorizo o envio deste relatório a {{destinatario}}.", ""), "Autorizo o envio deste relatório a [destinatário].");
});

test("linhas, frase e exportação: estado de hoje (nada publicado) não mostra número de faixa", () => {
  const hoje = resp([regua({}), regua({ codigo: "coe_litro_reais", unidade: "R$/L", situacao: "sem_faixa", nome: "COE por litro" })]);
  const ls = linhasReguas(hoje, ind({ comida_receita: 49.3, coe_litro_reais: null }));
  assert.equal(ls[0].valorTexto, "49,3%");
  assert.equal(ls[0].faixaVisivel, false);
  assert.equal(ls[0].faixaTexto, null);
  assert.match(fraseReguas(ls, "setembro/2026"), /Nenhuma faixa de referência está liberada/);
  const semReguas = linhasExportacaoReguas(ls, false);
  assert.equal(semReguas[0].length, 3);
  assert.equal(semReguas[1][1], "— (falta dado)");
  const comPublicada = linhasReguas(resp([PUBLICADA]), ind({ comida_receita: 49.3 }));
  assert.match(fraseReguas(comPublicada, "setembro/2026"), /1 de 1 indicadores com faixa ficam dentro/);
  assert.deepEqual(linhasExportacaoReguas(comPublicada, true)[0], ["Comida ÷ receita do leite", "49,3%", "referência de 40 a 55% (dentro da faixa de referência)", "A ÷ B"]);
});
