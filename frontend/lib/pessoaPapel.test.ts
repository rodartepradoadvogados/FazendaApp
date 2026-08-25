// Testes de frontend/lib/pessoaPapel.ts — a regra de "quem pode ser
// Responsável" (ver temPapelFuncional), usada por usePessoasAtivas em todos
// os seletores de Responsável do site/app. Roda com o runner nativo do Node
// (sem depender de jest/vitest, que o projeto não tem instalado): `npm test`
// (ver script em package.json).
import { test } from "node:test";
import assert from "node:assert/strict";
import { temPapelFuncional } from "./pessoaPapel.ts";

test("temPapelFuncional: aceita cada papel funcional isolado", () => {
  assert.equal(temPapelFuncional(["Funcionário"]), true);
  assert.equal(temPapelFuncional(["Veterinário"]), true);
  assert.equal(temPapelFuncional(["Zootecnista"]), true);
  assert.equal(temPapelFuncional(["Administrador"]), true);
  assert.equal(temPapelFuncional(["Contador"]), true);
});

test("temPapelFuncional: rejeita quem só tem tipos de apoio", () => {
  assert.equal(temPapelFuncional(["Diarista"]), false);
  assert.equal(temPapelFuncional(["Prestador de serviços"]), false);
  assert.equal(temPapelFuncional(["Empreiteiro"]), false);
  assert.equal(temPapelFuncional(["Geral"]), false);
  assert.equal(temPapelFuncional(["Robô"]), false);
});

test("temPapelFuncional: rejeita combinação de só tipos de apoio", () => {
  assert.equal(temPapelFuncional(["Diarista", "Prestador de serviços"]), false);
  assert.equal(temPapelFuncional(["Empreiteiro", "Geral", "Robô"]), false);
});

test("temPapelFuncional: aceita tipo de apoio combinado com um papel funcional", () => {
  assert.equal(temPapelFuncional(["Diarista", "Funcionário"]), true);
  assert.equal(temPapelFuncional(["Geral", "Veterinário"]), true);
  assert.equal(temPapelFuncional(["Empreiteiro", "Prestador de serviços", "Contador"]), true);
});

test("temPapelFuncional: tolerante a acento/maiúscula/minúscula", () => {
  assert.equal(temPapelFuncional(["VETERINARIO"]), true);
  assert.equal(temPapelFuncional(["veterinario"]), true);
  assert.equal(temPapelFuncional(["Veterinário"]), true);
  assert.equal(temPapelFuncional(["ADMINISTRADOR"]), true);
  assert.equal(temPapelFuncional(["zootecnista "]), true); // espaço solto não deve quebrar
});

test("temPapelFuncional: sem tipos (undefined/vazio) nunca é responsável", () => {
  assert.equal(temPapelFuncional(undefined), false);
  assert.equal(temPapelFuncional([]), false);
});
