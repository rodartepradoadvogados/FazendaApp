(()=>{const a=A;const EP={};const SB=30;
// ---- Ep. 6 · Produção › Controle leiteiro (por vaca e por lote). Telas = capturas do app real (captura/capturar_t2e6.mjs). ----
// bt = caixa no conteúdo (coord. da página rolada a 0 nas capturas altas; viewport nas estáticas), bn = elementos fixos
const bt=(n,k)=>{const m=MAPA[n];return(m.tall&&m.tall.alvos[k])||m.alvos[k];};const bn=(n,k)=>MAPA[n].alvosN[k];
const mx=n=>{const m=MAPA[n];return m.tall?Math.max(0,m.tall.h-69-m.barTop):0;};
const seg=pts=>t=>{if(t<=pts[0][0])return pts[0][1];for(let i=0;i<pts.length-1;i++){const[a0,v0]=pts[i],[a1,v1]=pts[i+1];if(t<a1)return L(v0,v1,io(lin(t,a0,a1)));}return pts[pts.length-1][1];};
const F=TL.frases;
// ---- tempos (tudo ancorado nas palavras da locução) ----
const tProd=a('producao')+0.1,tCtl=a('controle')+0.1,tBusca=a('busque')+0.25,tDig=tBusca+0.5,tSelV=a('lactacao')+0.9,tO1=a('primeira')-0.3,tO2=a('segunda')-0.1,
 tSave=a('salvar')+0.05,tLote=a('loteBtn')+0.05,tSelL=a('escolha')+0.3,tScr0=a('delA')+0.55,tF1=tScr0+0.85,tF2=a('preencha')+0.4,tF3=a('totalLote')+0.5,
 tFl0=a('media')+0.95,tFl1=a('salvar2')-0.45,tSave2=a('salvar2')+0.05,tCapa=a('proximo')-0.15;
const cT={prod:tProd+0.1,vaca:tCtl+0.1,dig:tDig,sel:tSelV+0.12,o1:tO1+0.15,o2:tO2+0.15,salvo:tSave+0.25,lvz:tLote+0.12,lc:tSelL+0.15,v1:tF1+0.13,v2:tF2+0.13,v3:tF3+0.13,fim:tSave2+0.3};
EP.imgs={lancar:'s01_lancar',grade:'s02_prod_grade',vaca:'s03_vaca_busca',dig:'s04_digitado',sel:'s05_selecionada',o1:'s06_o1',o2:'s07_o2_total',salvo:'s08_salvo',
 lvz:'s09_lote_vazio',lc:'s10_lote_cartoes',v1:'s11_vaca1',v2:'s12_vaca2',v3:'s13_vaca3_vazio',fim:'s15_salvo_lote'};
// [t, id, dir, 1 = troca só de estado (as anotações continuam)]
EP.telas=[[0,'lancar',0],[cT.prod,'grade',1],[cT.vaca,'vaca',1],[cT.dig,'dig',0,1],[cT.sel,'sel',0,1],[cT.o1,'o1',0,1],[cT.o2,'o2',0,1],[cT.salvo,'salvo',0,1],
 [cT.lvz,'lvz',0,1],[cT.lc,'lc',0,1],[cT.v1,'v1',0,1],[cT.v2,'v2',0,1],[cT.v3,'v3',0,1],[cT.fim,'fim',0,1]];
// ---- rolagem (px CSS do app) ----
const SAL=79;                                    // Salvar da vaca: sobe 79 px para o botão e o aviso ficarem acima da navegação
const rV=seg([[a('soma')+0.9,0],[a('toqueSalvar')-0.2,SAL],[a('loteInteiro')-0.3,SAL],[tLote-0.4,0]]);
const rL=seg([[tScr0,0],[tScr0+0.7,200],[tFl0,200],[tFl1,4468]]);
const rS=seg([[cT.salvo+0.2,SAL],[cT.salvo+0.8,136],[a('loteInteiro')-0.3,136],[tLote-0.4,0]]);   // depois de salvar o aviso aparece e a página cresce: mais 57 px de rolagem
EP.rolagem={dig:rV,sel:rV,o1:rV,o2:rV,salvo:rS,lvz:rL,lc:rL,v1:rL,v2:rL,v3:rL,fim:()=>1e6};
const S=(id,t)=>cl(EP.rolagem[id](t),0,mx(EP.imgs[id]));
const cx=b=>b.x+b.w/2,cy=b=>b.y+b.h/2;
// ---- toques: [t, x, y] em coordenadas da tela do celular (CSS) já com a barra de status (+30) ----
const bProd=bt('s01_lancar','prod'),bCtl=bt('s02_prod_grade','controle'),bBus=bt('s03_vaca_busca','busca'),bRes=bt('s04_digitado','res4746'),
 bO1=bt('s05_selecionada','o1In'),bO2=bt('s06_o1','o2In'),bSal=bt('s07_o2_total','salvar'),bLote=bt('s08_salvo','btnLote'),bSel=bt('s09_lote_vazio','loteSel'),
 bC0=bt('s10_lote_cartoes','c0a'),bC1=bt('s11_vaca1','c1a'),bC2=bt('s12_vaca2','c2a'),bSal2=bt('s13_vaca3_vazio','salvar');
EP.toques=[
 [tProd,cx(bProd),cy(bProd)+SB],[tCtl,cx(bCtl),cy(bCtl)+SB],[tBusca,cx(bBus)-40,cy(bBus)+SB],[tSelV,cx(bRes),cy(bRes)+SB],
 [tO1,cx(bO1),cy(bO1)+SB],[tO2,cx(bO2),cy(bO2)+SB],[tSave,cx(bSal),cy(bSal)-S('o2',tSave)+SB],
 [tLote,cx(bLote),cy(bLote)-S('salvo',tLote)+SB],[tSelL,cx(bSel),cy(bSel)+SB],
 [tF1,cx(bC0),cy(bC0)-S('lc',tF1)+SB],[tF2,cx(bC1),cy(bC1)-S('v1',tF2)+SB],[tF3,cx(bC2),cy(bC2)-S('v2',tF3)+SB],
 [tSave2,cx(bSal2),cy(bSal2)-S('v3',tSave2)+SB]];
// ---- câmera: [t de chegada, duração, cx, cy, zoom] (coords da tela do celular com +30). Visível: de cy-189/z a cy+349/z. Zoom ≤ 1,18 e centrado ----
EP.cam=[[0,0,195,300,1.0],[a('emLancar')+0.3,1.0,195,380,1.12],[tProd+0.45,0.9,195,360,1.1],
 [tCtl+0.5,0.9,195,470,1.0],[a('porVaca')-0.3,0.8,195,470,1.05],
 [tSelV+0.35,0.8,195,530,1.0],[a('soma')+0.7,0.7,195,570,1.0],
 [a('loteInteiro')-0.2,0.8,195,500,1.0],[a('aparece')-0.4,0.8,195,520,1.0],[tScr0-0.1,0.6,195,540,1.0],
 [a('branco')-0.3,0.8,195,600,1.1],[tFl0-0.1,0.6,195,540,1.0],[tSave2+0.5,0.7,195,520,1.0]];
// ---- anotações: [t0,t1,tipo,x,y,w,h,{c,scr}] ----
const V='#2E7D52',Z='#1E6FA8',D='#E0A63C',IN='#1A2638';
const bx=(n,k,o={})=>{const b=bt(n,k);return[b.x,b.y,b.w,b.h,o];};
const del=(()=>{const b=bt('s10_lote_cartoes','c0h');return[b.x+76,b.y,86,b.h,{c:D,scr:'lc'}];})();
EP.anot=[
 [a('toqueProd')+0.1,tProd+0.1,'caixa',...bx('s01_lancar','prod',{c:V})],
 [a('leite')-0.15,tCtl+0.1,'caixa',...bx('s02_prod_grade','controle',{c:V})],
 [a('vaca')-0.15,a('lote')-0.15,'caixa',...bx('s03_vaca_busca','btnVaca',{c:V})],
 [a('lote')-0.1,a('busque')-0.1,'caixa',...bx('s03_vaca_busca','btnLote',{c:Z})],
 [a('busque')-0.1,tDig-0.05,'caixa',...bx('s03_vaca_busca','busca',{c:D})],
 [tDig+0.3,tSelV+0.05,'caixa',...bx('s04_digitado','res4746',{c:V})],
 [a('primeira')-0.2,tO2-0.1,'caixa',...bx('s05_selecionada','o1',{c:V})],
 [a('segunda')-0.2,a('soma')-0.3,'caixa',...bx('s06_o1','o2',{c:Z,scr:'o1'})],
 [a('opcional')-0.5,a('soma')-0.35,'caixa',...bx('s07_o2_total','o3',{c:D,scr:'o2'})],
 [a('soma')-0.2,a('soma')+0.75,'marca',...bx('s07_o2_total','total',{c:D,scr:'o2'})],
 [a('toqueSalvar')+0.1,tSave+0.05,'caixa',...bx('s07_o2_total','salvar',{c:D,scr:'o2'})],
 [cT.salvo+0.05,a('loteInteiro')-0.35,'caixa',...bx('s08_salvo','aviso',{c:V,scr:'salvo'})],
 [a('toqueLote')+0.05,tLote+0.05,'caixa',...bx('s08_salvo','btnLote',{c:D,scr:'salvo'})],
 [a('escolha')-0.15,tSelL+0.05,'caixa',...bx('s09_lote_vazio','loteSel',{c:V})],
 [a('aparece')-0.1,a('delA')-0.15,'caixa',...bx('s10_lote_cartoes','qtd',{c:V,scr:'lc'})],
 [a('delA')-0.1,tScr0+0.1,'marca',...del],
 [tF3-0.55,a('somando')+0.9,'caixa',...bx('s12_vaca2','totalLote',{c:D,scr:'v2'})],
 [a('branco')-0.1,a('media')+0.8,'caixa',...bx('s13_vaca3_vazio','c2b',{c:Z,scr:'v3'})],
 [tFl1-0.05,tSave2+0.05,'caixa',...bx('s13_vaca3_vazio','salvar',{c:D,scr:'v3'})],
 [cT.fim+0.1,a('proximo')-0.5,'caixa',...bx('s15_salvo_lote','aviso',{c:V,scr:'fim'})]
];
EP.fitas=[[a('controle1')-0.1,a('emLancar')+0.1,'Controle <b>leiteiro</b>',110,298,-2],
 [a('lactacao')-0.15,tSelV-0.05,'Só <b>em lactação</b>',110,298,-1.5]];
EP.titulos=[[0,'Temporada 2 · <m>Ep. 6</m>'],[a('emLancar')-0.1,'Em Lançar: <m>Produção</m>'],[a('leite')-0.2,'Depois, <m>Controle leiteiro</m>'],[a('lancarPor')-0.1,'Lançar por: <m>Vaca</m> ou <m>Lote</m>'],
 [a('porVaca')-0.1,'Por vaca: <m>busque</m> a vaca'],[a('digite')-0.1,'Digite as <m>ordenhas</m> (kg)'],[a('soma')-0.3,'O app soma o <m>total do dia</m>'],[a('toqueSalvar')-0.1,'Toque em <m>Salvar</m>'],
 [a('loteInteiro')-0.1,'Lote inteiro: toque em <m>Lote</m>'],[a('aparece')-0.1,'Cada vaca com o <m>DEL</m>'],[a('preencha')-0.1,'Preencha as <m>ordenhas</m>'],
 [a('branco')-0.1,'Em branco: <m>não é zero</m>'],[a('media')+1.45,'Toque em <m>Salvar</m>'],[a('pronto')-0.1,'Feito: <m>lançado</m>']];
// diagrama Vox no papel: vazio ≠ 0 — a média com zero (riscada) contra a ordenha única (certa)
EP.diag=[a('branco')-0.1,a('media')+1.5];
EP.leg=[[F[0][1],F[0][2],F[0][0]],[F[1][1],a('leite')+0.5,'Em Lançar, toque em Produção, Leite,'],[a('leite')+0.5,F[1][2],'e depois em Controle leiteiro.'],
 [F[2][1],F[2][2],F[2][0]],
 [F[3][1],a('lactacao')-0.35,'Por vaca: busque a vaca.'],[a('lactacao')-0.35,F[3][2],'Só aparecem as vacas em lactação.'],
 [F[4][1],F[4][2],F[4][0]],[F[5][1],F[5][2],F[5][0]],[F[6][1],F[6][2],F[6][0]],[F[7][1],F[7][2],F[7][0]],[F[8][1],F[8][2],F[8][0]],[F[9][1],F[9][2],F[9][0]],
 [F[10][1],a('semLanc')-0.3,'Ordenha em branco não vira zero:'],[a('semLanc')-0.3,F[10][2],'fica sem lançamento, e não puxa a média para baixo.'],
 [F[11][1],a('pronto')-0.15,'Toque em Salvar.'],[a('pronto')-0.15,F[11][2],'Pronto, lançado.']];
EP.fimLeg=tCapa;EP.shake=a('lancado');
EP.entrada=t=>{const p=mola(t-0.3,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
const tCar=a('lancado'),tCarFim=a('proximo')-0.45;
EP.oculta=[[tCar,tCarFim],[EP.diag[1],EP.diag[1]+0.36],[a('controle1')-0.1,a('emLancar')+0.4],[a('lactacao')-0.15,tSelV+0.6]];
EP.estado=(t,{K,io,oc,lin,mola,L,cl,ob,ic,cow,X,iq})=>{
  K.dymo.style.transform=`translateX(${(1-cl(mola(t-0.55,9,.55),0,1.15))*-1000}px) rotate(-1.6deg)`;
  const g=cl(mola(t-0.15,10,.5),0,1.2);K.grampo.style.transform=`translateY(${(1-g)*-230}px) rotate(${(1-cl(g,0,1))*6}deg)`;
  // diagrama: (20,5 + 0) ÷ 2 = 10,3 ✕ (riscado)  ·  20,5 ✔ ; seta tracejada a 12 qps até a 2ª ordenha vazia da 3ª vaca
  const D0=EP.diag[0],D1=EP.diag[1];
  if(t>=D0-0.05&&t<D1+0.3){const pe=oc(lin(t,D0,D0+0.45)),ps=iq(lin(t,D1,D1+0.3));const w=(Math.floor(t*12)%3)-1;
    const tz=a('naoVira')-0.1,t2=a('semLanc')+0.1,tx=a('media')-0.1,tk=a('media')+0.35;
    const a1=oc(lin(t,tz,tz+0.4)),a2=oc(lin(t,t2,t2+0.4)),rx=io(lin(t,tx,tx+0.4)),ck=mola(t-tk,13,.5);
    let sv='';
    // seta: do diagrama até o campo vazio (posição na tela calculada da câmera e da rolagem naquele instante)
    const[cxm,cym,zz]=camera(t);const b=bt('s13_vaca3_vazio','c2b');const scr=cl(EP.rolagem.v3(t),0,mx('s13_vaca3_vazio'));
    const fx=540+((b.x+b.w/2)-cxm)*U*zz-80,fy=FY+((b.y-scr+SB)-cym)*U*zz-286;
    const pa=io(lin(t,D0+0.2,a('naoVira')-0.1)),ta=1-iq(lin(t,tz+0.35,tz+0.7));
    if(pa>0&&ta>0){const x0=700,y0=150,x1=L(x0,fx,pa),y1=L(y0,fy-20,pa);sv+=`<path d="M${x0} ${y0+w} L${x1} ${y1-w}" stroke="#1E6FA8" stroke-width="8" stroke-linecap="round" stroke-dasharray="4 16" fill="none" opacity="${ta}"/>`;}
    sv+=`<g opacity="${a1}" transform="translate(${(1-a1)*-40} 0)"><text x="10" y="54" font-family="Archivo" font-weight="800" font-size="58" fill="${IN}">(20,5 + 0) ÷ 2 = 10,3</text>`;
    if(rx>0)sv+=`<path d="M0 ${38+w} L${L(0,730,rx)} ${34-w}" stroke="#1E6FA8" stroke-width="8" stroke-linecap="round" fill="none"/>`;
    if(ck>0)sv+=`<g transform="translate(820 32) scale(${cl(ck,0,1.2)})"><path d="M-22 -22 L22 22 M22 -22 L-22 22" stroke="#B3392F" stroke-width="11" stroke-linecap="round"/></g>`;
    sv+=`</g><g opacity="${a2}" transform="translate(${(1-a2)*-40} 0)"><text x="10" y="118" font-family="Archivo" font-weight="800" font-size="58" fill="${IN}">20,5</text><text x="180" y="116" font-family="Archivo" font-weight="700" font-size="32" fill="#4b4034">(só a ordenha lançada)</text>`;
    const c2=cl(mola(t-tk-0.1,13,.5),0,1.2);
    if(c2>0)sv+=`<g transform="translate(820 94) scale(${c2})"><path d="M-26 2 L-8 22 L28 -24" stroke="#2E7D52" stroke-width="12" stroke-linecap="round" stroke-linejoin="round" fill="none"/></g>`;
    sv+=`</g>`;
    X(K.diag,`<svg width="920" height="140" viewBox="0 0 920 140" style="overflow:visible">${sv}</svg>`);
    K.diag.style.display='block';K.diag.style.opacity=1-ps;K.diag.style.transform=`translateY(${(1-pe)*-170+ps*-120}px)`;}
  else K.diag.style.display='none';
  K.cartao.style.display='none';
  // carimbo de borracha: bate no "lançado" (3 quadros de tremida na cena inteira, ver shake no motor)
  if(t>=tCar&&t<tCarFim){const q=oc(lin(t,tCar,tCar+0.1)),s=lin(t,tCarFim-0.2,tCarFim);
    X(K.carimbo,`<div style="display:flex;align-items:center;justify-content:center;gap:22px;border:10px solid #14452B;outline:3px solid #14452B;outline-offset:7px;border-radius:18px;padding:22px 34px;color:#14452B;font:800 54px/1 Archivo;letter-spacing:.03em;white-space:nowrap;background:rgba(251,246,232,.55);filter:url(#tinta)"><svg width="70" height="70" viewBox="0 0 24 24" fill="none" stroke="#14452B" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5l5 5L20 6.5"/></svg>LANÇADO NO REBANHO</div>`);
    K.carimbo.style.display='block';K.carimbo.style.opacity=(0.93*(1-s)*cl(q*4)).toFixed(3);K.carimbo.style.transform=`translateX(-50%) rotate(-4deg) scale(${L(1.7,1,q)})`;}else K.carimbo.style.display='none';
};
EP.capa=(t,el)=>{const p=io(lin(t,tCapa,tCapa+0.7));if(p<=0){el.style.display='none';return;}el.style.display='block';el.style.clipPath=`inset(${(1-p)*100}% 0 0 0)`;
  const q=mola(t-tCapa-0.45,10,.5),r=mola(t-tCapa-0.95,12,.5),s=oc(lin(t,tCapa+1.7,tCapa+2.3)),u=mola(t-tCapa-2.5,12,.5);
  X(el,`<div class="dymo" style="top:250px;left:80px;transform:rotate(-1.6deg)">PRÓXIMO EPISÓDIO · TEMP. 02</div>
   <div class="abs" data-z="1" style="left:80px;top:350px;font:800 104px/1.02 Archivo;color:#1A2638;letter-spacing:-.02em;text-transform:uppercase">Pesagem<br><span style="position:relative;display:inline-block;z-index:0">corporal<i style="position:absolute;left:-10px;right:-14px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span><br>e secagem</div>
   <div class="abs" data-z="2" style="left:80px;top:870px;width:380px;height:380px;background:#fff;box-shadow:0 26px 50px rgba(50,32,8,.3);display:flex;align-items:center;justify-content:center">${cow(250,'#1A2638',0.9)}</div>
   <div class="abs" data-z="3" style="left:510px;top:890px;width:490px"><div style="font:800 84px/1 Archivo;color:#1A2638;letter-spacing:-.02em">COW<span style="color:#8A5A12">DATA</span></div><div style="margin-top:28px;font:800 46px/1.1 Archivo;color:#1A2638;text-transform:uppercase">O rebanho na mão de <span style="position:relative;display:inline-block;z-index:0">quem cuida<i style="position:absolute;left:-8px;right:-10px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div></div>
   <div class="fita" data-z="4" style="left:90px;top:1350px">Ep. 6 · <b>Controle leiteiro</b></div>`);
  const z=n=>el.querySelector(`[data-z="${n}"]`);
  z(1).style.transform=`translateY(${(1-cl(q,0,1.2))*140}px)`;z(1).style.clipPath=`inset(0 0 ${(1-cl(q*1.4))*100}% 0)`;
  z(2).style.transform=`rotate(${L(-14,-4,cl(r,0,1.1))}deg) scale(${L(.4,1,cl(r,0,1.1))})`;
  z(3).style.clipPath=`inset(0 0 ${(1-s)*100}% 0)`;z(3).style.transform=`translateY(${(1-s)*40}px)`;
  z(4).style.transform=`translateX(${(1-cl(u,0,1.1))*-1200}px) rotate(-2deg)`;};
// ---- SFX e camadas da trilha (lidos por dump_t2.mjs → beats.json) ----
EP.sfx=[[0.3,'whoosh']];
EP.toques.forEach(x=>EP.sfx.push([x[0],'toque']));
EP.anot.forEach(x=>{if(!(x[7]&&x[7].fixo))EP.sfx.push([x[0],'caneta']);});
EP.telas.forEach(x=>{if(x[2])EP.sfx.push([x[0],'whoosh']);});
EP.fitas.forEach(x=>{EP.sfx.push([x[0],'rasgo']);EP.sfx.push([x[1],'rasgo']);});
EP.sfx.push([EP.diag[0],'rasgo'],[tCapa,'whoosh'],[tCapa+2.5,'rasgo'],[EP.shake,'carimbo']);
EP.sfx.sort((p,q)=>p[0]-q[0]);
EP.camadas=[[0,['piano','pad']],[a('emLancar'),['piano','pad','shaker']],[a('lancarPor'),['piano','pad','baixo','shaker','bumbo_leve']],[a('aparece'),['piano','pad','baixo','shaker','bumbo','palma','piano_cheio']],
 [a('pronto')-0.2,['piano','pad','baixo','shaker','shaker16','bumbo','palma','piano_cheio','sino']],[a('proximo')-0.6,['piano','pad','baixo','shaker','bumbo_leve']],[tCapa,['piano','pad','baixo','shaker','bumbo_leve','sino']]];
return EP;})()
