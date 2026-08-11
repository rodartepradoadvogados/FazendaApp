// Testes de frontend/lib/busca.ts — o helper único de normalização de busca.
// Roda com o runner nativo do Node (sem depender de jest/vitest, que o
// projeto não tem instalado): `npm test` (ver script em package.json).
import { test } from "node:test";
import assert from "node:assert/strict";
import { casaBusca, normalizarBusca } from "./busca.ts";

test("normalizarBusca ignora maiúscula/minúscula", () => {
  assert.equal(normalizarBusca("PROTEINA"), normalizarBusca("proteina"));
  assert.equal(normalizarBusca("Ração"), normalizarBusca("ração"));
});

test("normalizarBusca ignora acento", () => {
  assert.equal(normalizarBusca("racao"), normalizarBusca("Ração"));
  assert.equal(normalizarBusca("PROTEINA"), normalizarBusca("Proteína"));
});

test("normalizarBusca ignora cedilha", () => {
  assert.equal(normalizarBusca("coracao"), normalizarBusca("coração"));
});

test("normalizarBusca ignora hífen", () => {
  assert.equal(normalizarBusca("sal-mineral"), normalizarBusca("salmineral"));
});

test("normalizarBusca ignora underscore", () => {
  assert.equal(normalizarBusca("sal_mineral"), normalizarBusca("salmineral"));
});

test("normalizarBusca ignora espaço", () => {
  assert.equal(normalizarBusca("sal mineral"), normalizarBusca("salmineral"));
});

test("normalizarBusca: hífen, underscore e espaço são todos equivalentes entre si", () => {
  const variantes = ["salmineral", "sal-mineral", "sal_mineral", "sal mineral", "SAL-MINERAL", "Sal_Mineral"];
  const normalizados = new Set(variantes.map(normalizarBusca));
  assert.equal(normalizados.size, 1);
});

test("normalizarBusca não altera o texto original (só a comparação)", () => {
  const original = "Ração 20% Proteína";
  normalizarBusca(original);
  assert.equal(original, "Ração 20% Proteína");
});

test("normalizarBusca trata null/undefined/vazio como string vazia", () => {
  assert.equal(normalizarBusca(null), "");
  assert.equal(normalizarBusca(undefined), "");
  assert.equal(normalizarBusca(""), "");
});

test("casaBusca: combinação de acento + maiúscula + separador", () => {
  assert.equal(casaBusca("Sal-Mineral 20%", "salmineral20"), true);
  assert.equal(casaBusca("Ração de Proteína", "RACAO DE PROTEINA"), true);
  assert.equal(casaBusca("Ração de Proteína", "racaodeproteina"), true);
});

test("casaBusca: termo vazio sempre casa (busca vazia mostra tudo)", () => {
  assert.equal(casaBusca("qualquer coisa", ""), true);
  assert.equal(casaBusca("qualquer coisa", "   "), true);
  assert.equal(casaBusca("qualquer coisa", null), true);
  assert.equal(casaBusca("qualquer coisa", undefined), true);
});

test("casaBusca: alvo vazio/nulo nunca casa com um termo real", () => {
  assert.equal(casaBusca("", "racao"), false);
  assert.equal(casaBusca(null, "racao"), false);
  assert.equal(casaBusca(undefined, "racao"), false);
});

test("casaBusca: termo que não aparece não casa", () => {
  assert.equal(casaBusca("Ração de Proteína", "silagem"), false);
});

test("casaBusca: exemplos reais do domínio (produto/serviço/fornecedor)", () => {
  // Produto de estoque.
  assert.equal(casaBusca("Ração Concentrado Proteico", "concentrado proteico"), true);
  // Serviço.
  assert.equal(casaBusca("Inseminação Artificial", "inseminacao artificial"), true);
  // Fornecedor.
  assert.equal(casaBusca("João Nutrição Animal Ltda", "joao nutricao"), true);
});
