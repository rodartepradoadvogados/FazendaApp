// ===== corpo do episódio (T3 · Ep. 7) — tudo é função pura do tempo: window.seek(t) =====
// Convenções: coordenadas "css" = px CSS da tela do app (390 x 844). Páginas altas: coordenadas do documento (y - rolagem = y na tela).
// Folhas (gavetas): caixas relativas ao topo do diálogo. O motor compõe a tela no canvas SC (DPR 3) e o navegador no canvas 2D por cima.
const S3 = M.dsf || 3, VH = 844, SHEET_MAX = 675.2;

// ---------- câmera: pose frontal (dolly reto) e pose orbital (abertura/encerramento) ----------
const D0 = 38.5, AZ = 2.5, EL = 87, SHIFT = 40;
const PXCSS = (z) => z * 1920 / (2 * D0 * Math.tan(THREE.MathUtils.degToRad(13))) * U; // px de vídeo por px CSS
function poseFrontal(z, cxs, cys) {
  const d = D0 / z, alvo = phone.localToWorld(cssP(cxs, cys));
  const A = THREE.MathUtils.degToRad(AZ), E = THREE.MathUtils.degToRad(EL);
  return { pos: new THREE.Vector3(alvo.x + d * Math.sin(A) * Math.cos(E), alvo.y + d * Math.sin(E), alvo.z + d * Math.cos(A) * Math.cos(E)), tgt: alvo, up: new THREE.Vector3(0, 0, -1), shift: SHIFT, d };
}
function poseOrbital(az, el, d, tx, ty, tz) {
  const A = THREE.MathUtils.degToRad(az), E = THREE.MathUtils.degToRad(el);
  return { pos: new THREE.Vector3(tx + d * Math.sin(A) * Math.cos(E), ty + d * Math.sin(E), tz + d * Math.cos(A) * Math.cos(E)), tgt: new THREE.Vector3(tx, ty, tz), up: new THREE.Vector3(0, 1, 0), shift: 100, d };
}
const mistura = (a, b, k) => ({ pos: a.pos.clone().lerp(b.pos, k), tgt: a.tgt.clone().lerp(b.tgt, k), up: a.up.clone().lerp(b.up, k).normalize(), shift: lerp(a.shift, b.shift, k), d: lerp(a.d, b.d, k) });
function aplicaCam(P) { cam.up.copy(P.up); cam.position.copy(P.pos); cam.lookAt(P.tgt); cam.setViewOffset(W, H, 0, -P.shift, W, H); cam.updateMatrixWorld(true); foco.dist = P.d; }
// KF: [t, zoom, cx, cy] com (cx,cy) = ponto da tela (css) no centro do quadro. F() calcula o centro para que o foco (fx,fy) caia em y = ay do vídeo.
const F = (z, fx, fy, ay = 680) => [z, fx, fy + (960 + SHIFT - ay) / PXCSS(z)];
const KFS = CAM_KF(F);
function kfCam(t) {
  let i = 0; while (i < KFS.length - 2 && t >= KFS[i + 1][0]) i++;
  const a = KFS[i], b = KFS[i + 1]; let u = clamp01((t - a[0]) / (b[0] - a[0])); u = u * u * (3 - 2 * u);
  return [lerp(a[1], b[1], u), lerp(a[2], b[2], u), lerp(a[3], b[3], u)];
}
const POSE_ORB_FIM = poseOrbital(-12, 54, 50, 0, 0.8, 0.4);
function poseEm(t) {
  const [z, cxs, cys] = kfCam(Math.min(t, T_FIM_FRONTAL));
  let P = poseFrontal(z, cxs, cys);
  const k = sm(T_FIM_FRONTAL, T_FIM_FRONTAL + 1.7, t); if (k > 0) P = mistura(P, poseOrbital(-12 + 5 * clamp01((t - 91) / 8), 54, 50, 0, 0.8, 0.4), k);
  return P;
}
let POSE_ATUAL = null;
let NAV_Z = 0; // elevação (unid.) do plano onde o navegador desenha: 0 = vidro do celular; a folha de papel pousada fica ~0,13 acima
function proj(x, y) { const v = phone.localToWorld(cssP(x, y)); v.y += NAV_Z; v.project(cam); return [(v.x * 0.5 + 0.5) * W, (-v.y * 0.5 + 0.5) * H]; }

// ---------- rolagem global da página e planos de estado ----------
function interpKF(K, t, ease = true) {
  if (t <= K[0][0]) return K[0][1]; if (t >= K[K.length - 1][0]) return K[K.length - 1][1];
  let i = 0; while (t >= K[i + 1][0]) i++;
  const a = K[i], b = K[i + 1]; let u = clamp01((t - a[0]) / (b[0] - a[0])); if (ease) u = u * u * (3 - 2 * u); return lerp(a[1], b[1], u);
}
const sy = (t) => interpKF(SYK, t);
function paginaEm(t) { let k = 0; for (let i = 0; i < PLANO_PG.length; i++) if (t >= PLANO_PG[i][0]) k = i; return k; }
// folha ativa: { id, e(0..1 abertura), scroll }
function folhaEm(t) {
  for (const [a, b, ids] of FOLHAS) {
    if (t < a - 0.001 || t > b + 0.5) continue;
    let id = ids[0][1]; for (const [ti, idi] of ids) if (t >= ti) id = idi;
    const e = Math.min(eo(a, a + 0.42, t), 1 - ei(b, b + 0.4, t));
    if (e <= 0) continue;
    const h = M[id].h, vis = Math.min(h, SHEET_MAX), sc = Math.min(Math.max(0, h - SHEET_MAX), interpKF(SCK, t));
    return { id, e, vis, top: VH - vis + (1 - e) * (vis + 30), scroll: sc };
  }
  return null;
}
function visaoEm(t) { for (const [a, b, id, fade] of VISOES) if (t >= a && t < b) return { id, a: Math.min(clamp01((t - a) / fade), 1 - clamp01((t - (b - fade)) / fade)) }; return null; }

// ---------- desenho da tela ----------
const CH = M.pl_vp; const HDR = CH.hdrBottom || 95.78, NAVT = CH.navTop || 775;
function desenhaPagina(id, y, a) {
  sg.globalAlpha = a;
  if (VP[id]) { sg.drawImage(IM[id], 0, 0, 1170, 2532, 0, 0, 1170, 2532); sg.globalAlpha = 1; return; } // Menu: a captura da tela já traz cabeçalho e barra
  const P = M[id], ymax = Math.max(0, P.docH - VH), yy = Math.min(Math.max(y, 0), ymax);
  sg.drawImage(IM[id], 0, Math.round(yy * S3), 1170, 2532, 0, 0, 1170, 2532);
  sg.drawImage(IM.pl_vp, 0, 0, 1170, Math.round(HDR * S3), 0, 0, 1170, Math.round(HDR * S3));
  sg.drawImage(IM.pl_vp, 0, Math.round(NAVT * S3), 1170, 2532 - Math.round(NAVT * S3), 0, Math.round(NAVT * S3), 1170, 2532 - Math.round(NAVT * S3));
  sg.globalAlpha = 1;
}
function desenhaFolha(f, t) {
  const img = IM[f.id], top = f.top * S3, vis = f.vis * S3;
  sg.fillStyle = `rgba(0,0,0,${0.5 * f.e})`; sg.fillRect(0, 0, 1170, 2532);
  sg.save(); sg.shadowColor = "rgba(0,0,0,.28)"; sg.shadowBlur = 24; sg.fillStyle = "#fff"; sg.beginPath(); sg.roundRect(0, top, 1170, vis + 200, [53, 53, 0, 0]); sg.fill(); sg.restore();
  sg.save(); sg.beginPath(); sg.roundRect(0, top, 1170, vis + 200, [53, 53, 0, 0]); sg.clip();
  sg.drawImage(img, 0, Math.round(f.scroll * S3), 1170, Math.round(vis), 0, top, 1170, Math.round(vis)); sg.restore();
}
function desenhaTela(t) {
  sg.clearRect(0, 0, 1170, 2532); sg.fillStyle = "#eff1f6"; sg.fillRect(0, 0, 1170, 2532);
  const k = paginaEm(t), [t0, id] = PLANO_PG[k], fade = 0.14, y = sy(t);
  if (k > 0 && t < t0 + fade) { desenhaPagina(PLANO_PG[k - 1][1], sy(t0 - 0.001), 1); desenhaPagina(id, y, clamp01((t - t0) / fade)); } else desenhaPagina(id, y, 1);
  scTex.needsUpdate = true;
}

// ---------- navegador ----------
const nav = document.getElementById("nav").getContext("2d");
const OURO = "#E0A63C"; const R_EL = 9;
function resolve(spec, t) { // → caixa em px CSS da tela (viewport)
  const [tipo, a, b] = spec;
  if (tipo === "pg") { const bx = b(M[a]); return { x: bx.x, y: bx.y - sy(t), w: bx.w, h: bx.h }; }
  if (tipo === "sh") { const f = folhaEm(t); const bx = b(M[a]); const top = f ? f.top : VH - Math.min(M[a].h, SHEET_MAX), sc = f ? f.scroll : 0; return { x: bx.x, y: top + bx.y - sc, w: bx.w, h: bx.h }; }
  const bx = b(M[a] || a); return { x: bx.x, y: bx.y, w: bx.w, h: bx.h };
}
const uniao = (...bs) => { const x0 = Math.min(...bs.map((q) => q.x)), y0 = Math.min(...bs.map((q) => q.y)), x1 = Math.max(...bs.map((q) => q.x + q.w)), y1 = Math.max(...bs.map((q) => q.y + q.h)); return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }; };
const quadro = (b, p) => ({ cx: b.x + b.w / 2, cy: b.y + b.h / 2, w: b.w + 2 * p, h: b.h + 2 * p, r: Math.min(R_EL, (b.h + 2 * p) / 2), f: 1 });
const PUCK = (cx, cy) => ({ cx, cy, w: 24, h: 24, r: 12, f: 0 });
const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const lerpS = (a, b, k) => ({ cx: lerp(a.cx, b.cx, k), cy: lerp(a.cy, b.cy, k), w: lerp(a.w, b.w, k), h: lerp(a.h, b.h, k), r: lerp(a.r, b.r, k), f: lerp(a.f, b.f, k) });
const shapeWP = (w, t) => (w.puck ? PUCK(w.puck[0], w.puck[1]) : quadro(resolve(w.spec, t), w.pad ?? 5));
function forma(t) {
  if (t <= WP[0].ta) return { s: shapeWP(WP[0], t), v: 0, alfa: 0 };
  for (let i = 1; i < WP.length; i++) {
    const A = WP[i - 1], B_ = WP[i];
    if (t < A.td) return { s: shapeWP(A, t), v: 0, alfa: 1 };
    if (t < B_.ta) {
      const x = (t - A.td) / (B_.ta - A.td), e = ease(x);
      let s = lerpS(shapeWP(A, t), shapeWP(B_, t), e); const dist = Math.hypot(shapeWP(A, t).cx - shapeWP(B_, t).cx, shapeWP(A, t).cy - shapeWP(B_, t).cy);
      const mid = dist > 60 ? Math.pow(Math.sin(Math.PI * e), 0.8) : 0;
      if (mid > 0) s = lerpS(s, PUCK(s.cx, s.cy), mid * 0.92);
      return { s, v: Math.sin(Math.PI * x) * Math.min(1, dist / 120), alfa: i === 1 ? clamp01((t - WP[0].ta) / (B_.ta - WP[0].ta) * 3) : 1 };
    }
  }
  return { s: shapeWP(WP[WP.length - 1], t), v: 0, alfa: 1 };
}
function trilhaRR(s, n = 22) {
  const w = s.w / 2, h = s.h / 2, r = Math.min(s.r, w, h), pts = [];
  const arco = (cx, cy, a0) => { for (let k = 0; k <= n; k++) { const a = a0 + (k / n) * Math.PI / 2; pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]); } };
  arco(s.cx + w - r, s.cy + h - r, 0); arco(s.cx - w + r, s.cy + h - r, Math.PI / 2); arco(s.cx - w + r, s.cy - h + r, Math.PI); arco(s.cx + w - r, s.cy - h + r, Math.PI * 1.5);
  return pts.map(([x, y]) => proj(x, y));
}
function caminho(P) { nav.beginPath(); P.forEach(([x, y], i) => (i ? nav.lineTo(x, y) : nav.moveTo(x, y))); nav.closePath(); }
function desenhaForma(s, alfa, press) {
  const k = PXCSS(1) / 1.911; // espessura do traço acompanha o dolly
  const z = poseZ; const P = trilhaRR(press ? { ...s, w: s.w * (1 - 0.04 * press), h: s.h * (1 - 0.06 * press) } : s); const f = s.f;
  const lw = Math.max(3.2, Math.min(6.5, 2.6 * z + 1.4));
  nav.save(); nav.lineJoin = "round"; nav.globalAlpha = alfa;
  nav.save(); nav.translate(0, 5); caminho(P); nav.shadowColor = "rgba(15,22,36,.45)"; nav.shadowBlur = 16; nav.strokeStyle = "rgba(15,22,36,.28)"; nav.lineWidth = lw + 2; nav.stroke(); nav.restore();
  caminho(P); nav.fillStyle = `rgba(224,166,60,${lerp(0.30, 0.07, f)})`; nav.fill();
  caminho(P); nav.strokeStyle = "rgba(26,38,56,.42)"; nav.lineWidth = lw + 2.6; nav.stroke();
  caminho(P); nav.shadowColor = "rgba(233,168,42,.85)"; nav.shadowBlur = 20; nav.strokeStyle = OURO; nav.lineWidth = lw; nav.stroke();
  nav.restore();
}
let poseZ = 1;
function desenhaNav(t) {
  nav.clearRect(0, 0, W, H);
  if (t > NAV_FIM + 0.4) return;
  const { s, v, alfa } = forma(t); const fim = 1 - clamp01((t - NAV_FIM) / 0.35); if (alfa * fim <= 0.01) return;
  if (v > 0.12) for (let k = 7; k >= 1; k--) {
    const f2 = forma(t - k * 0.022); if (f2.alfa <= 0.01) continue;
    const [px, py] = proj(f2.s.cx, f2.s.cy); const a = (1 - k / 8) * 0.34 * v * fim, r = lerp(26, 8, k / 8);
    nav.save(); nav.globalAlpha = a; nav.fillStyle = OURO; nav.shadowColor = "rgba(233,168,42,.7)"; nav.shadowBlur = 12; nav.beginPath(); nav.arc(px, py, r, 0, 7); nav.fill(); nav.restore();
  }
  let press = 0; for (const tp of TAPS) { const dt = t - tp[0]; if (dt > 0 && dt < 0.2) press = Math.max(press, dt < 0.07 ? dt / 0.07 : 1 - (dt - 0.07) / 0.13); }
  desenhaForma(s, alfa * fim, press);
  for (const [tt, spec] of TAPS) { // onda do toque (0,25 s) sobre o alvo
    const dt = t - tt; if (!(dt > 0 && dt < 0.25) || !spec) continue;
    const k = dt / 0.25, e = 1 - Math.pow(1 - k, 2), b = quadro(resolve(spec, tt), 5), sp = { ...b, w: b.w + 46 * e, h: b.h + 46 * e, r: Math.min(R_EL + 23 * e, (b.h + 46 * e) / 2), f: 1 };
    const Pp = trilhaRR(sp); nav.save(); nav.globalAlpha = 0.85 * (1 - k) * fim; caminho(Pp); nav.strokeStyle = OURO; nav.shadowColor = "rgba(233,168,42,.8)"; nav.shadowBlur = 16; nav.lineWidth = lerp(6, 2, k); nav.stroke(); nav.restore();
  }
}

// ---------- legenda e etiqueta de contexto ----------
const etq = document.getElementById("etq"), etqTxt = document.getElementById("etqt"); const leg = document.getElementById("leg"), legSp = leg.firstElementChild;
let legAtual = -1;
function atualizaLeg(t) {
  let k = -1; for (let i = 0; i < LEG.length; i++) if (t >= LEG[i][0] - 0.05 && t < LEG[i][1] + 0.3) k = i;
  if (k !== legAtual) { legAtual = k; if (k >= 0) legSp.innerHTML = LEG[k][2]; }
  let o = 0; if (k >= 0) { const [a, b] = LEG[k]; o = Math.min(clamp01((t - (a - 0.05)) / 0.25), 1 - clamp01((t - b) / 0.3)); }
  leg.style.opacity = o; leg.style.transform = `translateY(${(1 - o) * 14}px)`;
}
function atualizaEtq(t) {
  let txt = ETQ[0][1]; for (const [ti, tx] of ETQ) if (t >= ti) txt = tx; if (etqTxt.textContent !== txt) etqTxt.textContent = txt;
  const topo = proj(195, -27)[1]; let o = clamp01((topo - 118) / 34); o *= clamp01((t - ETQ[0][0]) / 0.3) * (1 - clamp01((t - T_ETQ_FIM) / 0.3)); etq.style.opacity = o;
}

// ---------- selos 3D (carimbos que descem na tela) e folha de papel (PDF real) ----------
const sombraTela = new THREE.Mesh(new THREE.PlaneGeometry(SW, SH), new THREE.ShadowMaterial({ opacity: 0.30, transparent: true, depthWrite: false })); sombraTela.position.z = telaZ + 0.008; sombraTela.receiveShadow = true; sombraTela.renderOrder = 4; phone.add(sombraTela);
function criaSelo(l1, l2, cor, f1 = 150, f2 = 190) {
  const g3 = new THREE.Group(), w = 5.4, h = 2.3; const geo = new THREE.ExtrudeGeometry(retRedondo(w, h, 0.5), { depth: 0.22, bevelEnabled: true, bevelThickness: 0.08, bevelSize: 0.08, bevelSegments: 4, curveSegments: 16 });
  const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: cor, roughness: 0.45, metalness: 0.25 })); m.castShadow = true; g3.add(m);
  const c = document.createElement("canvas"); c.width = 1400; c.height = 596; const g = c.getContext("2d");
  g.strokeStyle = "#F4E9C8"; g.lineWidth = 12; g.beginPath(); g.roundRect(26, 26, 1348, 544, 70); g.stroke(); g.lineWidth = 4; g.beginPath(); g.roundRect(52, 52, 1296, 492, 50); g.stroke();
  g.fillStyle = "#F4E9C8"; g.textAlign = "center"; g.textBaseline = "middle"; g.font = `800 ${f1}px Archivo`; g.fillText(l1, 700, 215); g.font = `800 ${f2}px Archivo`; g.fillText(l2, 700, 395);
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = aniso;
  const face = new THREE.Mesh(new THREE.PlaneGeometry(w * 0.97, h * 0.97), new THREE.MeshStandardMaterial({ map: tex, transparent: true, roughness: 0.5, emissive: 0xffffff, emissiveMap: tex, emissiveIntensity: 0.25 })); face.position.z = 0.31; g3.add(face);
  g3.rotation.x = -Math.PI / 2; g3.rotation.z = 0.12; g3.visible = false;
  const wrap = new THREE.Group(); wrap.add(g3); scene.add(wrap); return { g3, wrap };
}
const SELO_OBJ = SELOS.map((o) => ({ ...o, ...criaSelo(o.l1, o.l2, o.cor, o.f1, o.f2) }));
function atualizaSelo(t) {
  let ativo = false;
  for (const o of SELO_OBJ) {
    const vis = t >= o.t0 && t < o.t1; o.g3.visible = vis; if (!vis) continue; ativo = true;
    const q = clamp01((t - o.t0) / 0.42), queda = q * q; let y = 0.10 + (1 - queda) * 11.0; const r = t - (o.t0 + 0.42); if (r > 0) y += 0.16 * Math.exp(-r * 11) * Math.abs(Math.sin(r * 22));
    if (o.saida) y += 12 * ei(o.t1 - 0.32, o.t1, t); // carimbo de consulta: sobe e sai antes do relance do Menu
    o.wrap.position.set(0.2, Y0 + telaZ + y, 2.0); o.g3.rotation.z = 0.12 * (1 - 0.35 * q);
  }
  return ativo;
}
// ---------- fitas do encerramento ----------
function fitaTex(txt, w, h, cor = "#EBDDB4", tinta = "#1A2638") {
  const c = document.createElement("canvas"); c.width = w; c.height = h; const g = c.getContext("2d");
  g.save(); g.beginPath(); g.moveTo(10, 0); for (let i = 0; i <= 10; i++) g.lineTo(i % 2 ? 2 : 14, (i / 10) * h); g.lineTo(w - 10, h); for (let i = 10; i >= 0; i--) g.lineTo(i % 2 ? w - 14 : w - 2, (i / 10) * h); g.closePath(); g.clip();
  g.fillStyle = cor; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 1400; i++) { g.fillStyle = `rgba(${120 + (i * 7) % 60},${95 + (i * 13) % 40},60,${0.03 + ((i * 17) % 9) / 160})`; g.fillRect((i * 97) % w, (i * 57) % h, 1 + (i % 7) * 7, 1); }
  g.fillStyle = "rgba(255,255,255,.18)"; g.fillRect(0, 0, w, 10); g.fillStyle = "rgba(0,0,0,.07)"; g.fillRect(0, h - 10, w, 10);
  g.fillStyle = tinta; g.font = `800 ${h * 0.58}px Archivo`; g.textAlign = "center"; g.textBaseline = "middle"; const sc = Math.min(1, (w - 120) / g.measureText(txt).width);
  g.save(); g.translate(w / 2, h / 2 + h * 0.03); g.scale(sc, 1); g.fillText(txt, 0, 0); g.restore(); g.restore();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = aniso; return t;
}
function fita(txt, larg, alt) {
  const tex = fitaTex(txt, 1600, Math.round(1600 * alt / larg));
  const geo = new THREE.PlaneGeometry(larg, alt, 60, 4); geo.userData.base = geo.attributes.position.array.slice();
  const mat = new THREE.MeshStandardMaterial({ map: tex, transparent: true, alphaTest: 0.4, side: THREE.DoubleSide, roughness: 0.9, emissive: 0xffffff, emissiveMap: tex, emissiveIntensity: 0.45 });
  const m = new THREE.Mesh(geo, mat); const g = new THREE.Group(); g.add(m); cam.add(g); g.visible = false; return { g, m, geo, larg, alt, mat };
}
function dobra(f, t, fase, ond = 1, curl = 1) {
  const a = f.geo.attributes.position, b = f.geo.userData.base;
  for (let i = 0; i < a.count; i++) { const x = b[3 * i], y = b[3 * i + 1], u = x / f.larg;
    const z = 0.16 * ond * Math.sin(u * 7 + fase + t * 1.2) + curl * 0.9 * Math.pow(clamp01((u - 0.28) / 0.22), 2) * 0.45 - 0.12 * ond * Math.abs(Math.sin(u * 3.2 + fase));
    a.setXYZ(i, x, y + 0.05 * Math.sin(u * 5 + fase), z); }
  a.needsUpdate = true; f.geo.computeVertexNormals();
}
const DIST_F = 34, PXU = H / (2 * DIST_F * Math.tan(THREE.MathUtils.degToRad(13)));
const naTela = (px, py) => [(px - W / 2) / PXU, (H / 2 - py) / PXU, -DIST_F];
const fFim = [fita("FIM DO MÓDULO ALIMENTAÇÃO", 7.6, 1.1), fita("OBRIGADO, E BOM TRABALHO!", 7.4, 1.25), fita("T3 · EP. 7 · ALIMENTAÇÃO", 7.6, 0.95)];
const FIM_T = [[B.fimModulo - 0.02, 330, -0.02, 0.4], [B.obrigado - 0.02, 540, 0.02, 0.4], [B.obrigado + 1.2, 1500, -0.015, 0.4]];
function atualizaFitas(t) {
  fFim.forEach((f, i) => {
    const [ta, py, rz] = FIM_T[i]; const e = eb(ta, ta + 0.55, t), vis = t > ta - 0.02 && t < T_FIM_TOTAL - 0.1; f.g.visible = vis; if (!vis) return;
    const [x, y, z] = naTela(W / 2, py); const sai = ei(T_FIM_TOTAL - 0.6, T_FIM_TOTAL - 0.1, t);
    f.g.position.set(x + (1 - e) * (i % 2 ? 9 : -9), y, z); f.g.rotation.z = rz - 0.02 * (1 - e); f.g.rotation.y = 0.12 * Math.sin(t * 0.8 + i) * e; f.g.rotation.x = 0.05 * Math.sin(t * 0.9 + i); f.g.scale.setScalar(1 - 0.0 * sai);
    dobra(f, t, 0.3 + i * 1.1, 1, 0.5 * (1 - e)); f.mat.opacity = 1 - sai;
  });
}


// ---------- fitas 3D de texto (FITAS_TXT): uma ou duas linhas, presas à câmera na zona livre do alto; entram/saem com dobra, ficam paradas no meio (quadros iguais = dedupe) ----------
function fitaTex2(l1, l2, w, h, f1, f2) {
  const c = document.createElement("canvas"); c.width = w; c.height = h; const g = c.getContext("2d");
  g.save(); g.beginPath(); g.moveTo(10, 0); for (let i = 0; i <= 10; i++) g.lineTo(i % 2 ? 2 : 14, (i / 10) * h); g.lineTo(w - 10, h); for (let i = 10; i >= 0; i--) g.lineTo(i % 2 ? w - 14 : w - 2, (i / 10) * h); g.closePath(); g.clip();
  g.fillStyle = "#EBDDB4"; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 1600; i++) { g.fillStyle = `rgba(${120 + (i * 7) % 60},${95 + (i * 13) % 40},60,${0.03 + ((i * 17) % 9) / 160})`; g.fillRect((i * 97) % w, (i * 57) % h, 1 + (i % 7) * 7, 1); }
  g.fillStyle = "rgba(255,255,255,.18)"; g.fillRect(0, 0, w, 10); g.fillStyle = "rgba(0,0,0,.07)"; g.fillRect(0, h - 10, w, 10);
  g.textAlign = "center"; g.textBaseline = "middle"; g.fillStyle = "#1A2638";
  g.font = `800 ${f1}px Archivo`; g.fillText(l1, w / 2, h * 0.32);
  let tam = f2; g.font = `700 ${tam}px Archivo`; while (g.measureText(l2).width > w - 150 && tam > 20) { tam -= 2; g.font = `700 ${tam}px Archivo`; }
  g.fillStyle = "rgba(26,38,56,.5)"; g.fillRect(w / 2 - 190, h * 0.52, 380, 4);
  g.fillStyle = "#1A2638"; g.fillText(l2, w / 2, h * 0.72);
  g.restore();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = aniso; return t;
}

// placa do diálogo nativo (window.confirm): texto REAL (mapa.confirm.msg) quebrado em linhas + botões Cancelar / OK como texto
function fitaTexDlg(msg, botoes, w, h) {
  const c = document.createElement("canvas"); c.width = w; c.height = h; const g = c.getContext("2d");
  g.save(); g.beginPath(); g.moveTo(10, 0); for (let i = 0; i <= 10; i++) g.lineTo(i % 2 ? 2 : 14, (i / 10) * h); g.lineTo(w - 10, h); for (let i = 10; i >= 0; i--) g.lineTo(i % 2 ? w - 14 : w - 2, (i / 10) * h); g.closePath(); g.clip();
  g.fillStyle = "#EBDDB4"; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 2200; i++) { g.fillStyle = `rgba(${120 + (i * 7) % 60},${95 + (i * 13) % 40},60,${0.03 + ((i * 17) % 9) / 160})`; g.fillRect((i * 97) % w, (i * 57) % h, 1 + (i % 7) * 7, 1); }
  g.fillStyle = "rgba(255,255,255,.18)"; g.fillRect(0, 0, w, 10); g.fillStyle = "rgba(0,0,0,.07)"; g.fillRect(0, h - 10, w, 10);
  g.textAlign = "left"; g.textBaseline = "middle"; g.fillStyle = "#1A2638";
  let tam = 92, linhas = [];
  for (; tam >= 40; tam -= 2) { g.font = `700 ${tam}px Archivo`; linhas = []; let cur = ""; for (const pal of msg.split(" ")) { const t = cur ? cur + " " + pal : pal; if (g.measureText(t).width > w - 200 && cur) { linhas.push(cur); cur = pal; } else cur = t; } linhas.push(cur); if (linhas.length * tam * 1.22 < h * 0.62) break; }
  const alt = linhas.length * tam * 1.22, y0 = (h * 0.66 - alt) / 2 + tam * 0.61 + h * 0.03;
  linhas.forEach((l, i) => g.fillText(l, 100, y0 + i * tam * 1.22));
  g.fillStyle = "rgba(26,38,56,.5)"; g.fillRect(100, h * 0.74, w - 200, 4);
  // botões como texto: Cancelar (contorno) e OK (cheio)
  g.textAlign = "center"; g.font = `800 ${Math.round(h * 0.085)}px Archivo`; const bw = w * 0.26, bh = h * 0.15, by = h * 0.80;
  const xs = [w - 100 - bw * 2 - 50, w - 100 - bw];
  botoes.forEach((b, i) => { const x = xs[i]; g.beginPath(); g.roundRect(x, by, bw, bh, bh / 2);
    if (i === botoes.length - 1) { g.fillStyle = "#1A2638"; g.fill(); g.fillStyle = "#F4E9C8"; } else { g.strokeStyle = "#1A2638"; g.lineWidth = 6; g.stroke(); g.fillStyle = "#1A2638"; }
    g.fillText(b, x + bw / 2, by + bh / 2 + 4); });
  g.restore();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = aniso; return t;
}
const DIST_FP = 26; // a câmera chega a 32 unidades do celular (zoom 1,2): as fitas ficam mais perto que isso, senão o celular as esconde
const FT = FITAS_TXT.map((o) => {
  const tex = o.corpo ? fitaTexDlg(o.corpo, o.botoes, 1600, Math.round(1600 * o.alt / o.larg)) : fitaTex2(o.l1, o.l2, 1600, Math.round(1600 * o.alt / o.larg), o.f1, o.f2);
  const geo = new THREE.PlaneGeometry(o.larg, o.alt, 60, 4); geo.userData.base = geo.attributes.position.array.slice();
  const mat = new THREE.MeshStandardMaterial({ map: tex, transparent: true, alphaTest: 0.4, side: THREE.DoubleSide, roughness: 0.9, emissive: 0xffffff, emissiveMap: tex, emissiveIntensity: 0.45 });
  const mesh = new THREE.Mesh(geo, mat), grp = new THREE.Group(); grp.add(mesh); cam.add(grp); grp.visible = false;
  return { ...o, grp, geo, mat, larg: o.larg, alt: o.alt };
});
const ftEnt = (o, t) => eb(o.t0, o.t0 + 0.6, t), ftSai = (o, t) => ei(o.t1 - 0.5, o.t1, t);
function atualizaFitasTxt(t) {
  FT.forEach((o, i) => {
    const vis = t > o.t0 - 0.02 && t < o.t1; o.grp.visible = vis; if (!vis) return;
    const e = ftEnt(o, t), sai = ftSai(o, t); const [x, y] = naTela(W / 2, o.py), k = DIST_FP / DIST_F, sg_ = i % 2 ? 1 : -1;
    o.grp.scale.setScalar(k); o.grp.position.set((x - sg_ * (1 - e) * 9 + sg_ * sai * 9) * k, y * k, -DIST_FP); o.grp.rotation.z = -0.018 - 0.02 * (1 - e) + 0.02 * sai; o.grp.rotation.y = 0.06; o.grp.rotation.x = 0.03;
    dobra(o, 0, 0.9 + i, 0.7, 0.5 * (1 - e)); o.mat.opacity = 1;
  });
}

// ---------- seek ----------
let ultimoT = null;
window.seek = (t) => {
  // celular: sempre de frente; no encerramento vira e pousa de costas
  const fl = ei(T_VIRA, T_VIRA + 1.5, t), efl = sm(T_VIRA, T_VIRA + 1.5, t);
  flip.rotation.z = Math.PI * efl; root.position.set(0, Y0 + 2.4 * Math.sin(Math.PI * clamp01((t - T_VIRA) / 1.5)), 0);
  scene.updateMatrixWorld(true);
  desenhaTela(t);
  const P = poseEm(t); aplicaCam(P); POSE_ATUAL = P; poseZ = kfCam(Math.min(t, T_FIM_FRONTAL))[0];
  const selo = atualizaSelo(t), pap = { ativo: false, anim: false };
  rTex.offset.set(-0.02, 0.01); reflexo.material.opacity = 0.025 + 0.10 * sm(T_VIRA, T_VIRA + 1.5, t);
  const salto = ultimoT === null || Math.abs(t - ultimoT) > 0.4; ultimoT = t;
  key.shadow.needsUpdate = salto || selo || pap.anim || (t >= T_VIRA - 0.05);
  atualizaFitas(t); atualizaFitasTxt(t);
  renderer.render(scene, cam);
  const naFrente = t < T_FIM_FRONTAL; desenhaNav(naFrente ? t : 1e9); NAV_Z = 0;
  atualizaLeg(t); atualizaEtq(t);
};
// assinatura do quadro: quadros com a mesma assinatura saem idênticos (o render copia em vez de redesenhar)
const rd = (v, n = 2) => Math.round(v * 10 ** n) / 10 ** n;
window.sig = (t) => {
  if (t < T_INI + 0.5 || t >= T_VIRA - 0.01 || SELOS.some((o) => t >= o.t0 - 0.01 && t < o.t1 + 0.1) || FITAS_TXT.some((o) => (t > o.t0 - 0.05 && t < o.t0 + 0.7) || (t > o.t1 - 0.55 && t < o.t1 + 0.05))) return "u" + t;
  const k = paginaEm(t); if (t < PLANO_PG[k][0] + 0.16) return "u" + t;
  for (const tp of TAPS) if (t - tp[0] > -0.01 && t - tp[0] < 0.3) return "u" + t;
  const f = folhaEm(t), v = visaoEm(t); if ((f && f.e < 1) || (v && v.a < 1)) return "u" + t;
  const P = poseEm(t); aplicaCam(P); scene.updateMatrixWorld(true);
  const a = forma(t), b = forma(t - 0.2); const ss = (q) => [q.cx, q.cy, q.w, q.h, q.r, q.f].map((x) => rd(x, 1));
  let lk = -1; for (let i = 0; i < LEG.length; i++) if (t >= LEG[i][0] - 0.05 && t < LEG[i][1] + 0.3) lk = i;
  let lo = 0; if (lk >= 0) { const [x0, x1] = LEG[lk]; lo = rd(Math.min(clamp01((t - (x0 - 0.05)) / 0.25), 1 - clamp01((t - x1) / 0.3)), 2); }
  const topo = proj(195, -27)[1];
  return JSON.stringify([kfCam(t).map((x) => rd(x, 3)), rd(sy(t), 2), k, f && [f.id, rd(f.scroll, 2)], v && v.id, ss(a.s), rd(a.alfa, 2), ss(b.s), lk, lo, rd(topo, 0) < 200 ? rd(topo, 0) : 0, NAV_FIM < t + 0.4 ? t : 0, T_ETQ_FIM < t + 0.4 ? t : 0, ETQ.filter((e) => t >= e[0]).length, FITAS_TXT.map((o) => (t > o.t0 && t < o.t1 ? 1 : 0))]);
};
window.__ready = true; window.seek(T_INI);
