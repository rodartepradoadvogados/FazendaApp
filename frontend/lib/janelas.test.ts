import { test } from "node:test";
import assert from "node:assert/strict";
import {
  LARGURA_GAVETA_BAIXA, TETO_DOBRO_PX, desempilhar, dobroEmPx, ehTopo, empilhar, idParaFecharComEsc, larguraDobrada,
} from "./janelas.ts";

test("gaveta de baixa: o dobro dos 560 px do painel antigo", () => {
  assert.equal(LARGURA_GAVETA_BAIXA, "min(1120px, 100vw)");
  assert.equal(dobroEmPx(560), 1120);
});

test("dobro de uma janela, com teto e sempre limitada a 95vw", () => {
  assert.equal(larguraDobrada(520), "min(1040px, 95vw)");
  assert.equal(larguraDobrada(380), "min(760px, 95vw)");
  assert.equal(larguraDobrada(560), "min(1120px, 95vw)");
  // acima do teto não cresce mais (680 dobraria para 1360)
  assert.equal(dobroEmPx(680), TETO_DOBRO_PX);
  assert.equal(larguraDobrada(680), "min(1120px, 95vw)");
  // entrada inválida cai no teto em vez de gerar CSS quebrado ("NaNpx")
  assert.equal(dobroEmPx(NaN), TETO_DOBRO_PX);
  assert.equal(dobroEmPx(0), TETO_DOBRO_PX);
});

test("pilha: empilhar, desempilhar e topo", () => {
  let p = empilhar([], { id: 1, fecharComEsc: true });
  p = empilhar(p, { id: 2, fecharComEsc: true });
  assert.equal(ehTopo(p, 2), true);
  assert.equal(ehTopo(p, 1), false);
  p = desempilhar(p, 2);
  assert.equal(ehTopo(p, 1), true);
  assert.deepEqual(desempilhar(p, 99), p);
  assert.equal(ehTopo([], 1), false);
});

test("Esc fecha só o topo", () => {
  let p = empilhar([], { id: 1, fecharComEsc: true }); // gaveta
  p = empilhar(p, { id: 2, fecharComEsc: true });       // modal em cima
  assert.equal(idParaFecharComEsc(p), 2);
  p = desempilhar(p, 2);
  assert.equal(idParaFecharComEsc(p), 1);
  assert.equal(idParaFecharComEsc([]), null);
});

test("janela travada no topo: Esc não faz nada nem vaza para a de baixo", () => {
  let p = empilhar([], { id: 1, fecharComEsc: true });   // gaveta comum
  p = empilhar(p, { id: 2, fecharComEsc: false });        // baixa travada em cima
  assert.equal(idParaFecharComEsc(p), null);
  // gaveta travada com modal comum em cima: Esc fecha o modal, nunca a gaveta
  let q = empilhar([], { id: 1, fecharComEsc: false });
  q = empilhar(q, { id: 2, fecharComEsc: true });
  assert.equal(idParaFecharComEsc(q), 2);
  q = desempilhar(q, 2);
  assert.equal(idParaFecharComEsc(q), null);
});

test("reempilhar o mesmo id só atualiza a flag e mantém a posição", () => {
  let p = empilhar([], { id: 1, fecharComEsc: true });
  p = empilhar(p, { id: 2, fecharComEsc: true });
  p = empilhar(p, { id: 1, fecharComEsc: false });
  assert.equal(p.length, 2);
  assert.equal(ehTopo(p, 2), true);
  assert.equal(p[0].fecharComEsc, false);
});
