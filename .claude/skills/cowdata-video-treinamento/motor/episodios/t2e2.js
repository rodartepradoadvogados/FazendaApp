(()=>{const a=A;const EP={};const SB=30;
// ---- Ep. 2 · Reprodutivo › Inseminação em lote. Telas = capturas do app real (captura/capturar_t2e2.mjs). ----
// bt = caixa no conteúdo (coord. da página rolada a 0 nas capturas altas; viewport nas estáticas), bn = elementos fixos (barra, navegação)
const bt=(n,k)=>{const m=MAPA[n];return(m.tall&&m.tall.alvos[k])||m.alvos[k];};const bn=(n,k)=>MAPA[n].alvosN[k];
const mx=n=>{const m=MAPA[n];return m.tall?Math.max(0,m.tall.h-69-m.barTop):0;};
const seg=pts=>t=>{if(t<=pts[0][0])return pts[0][1];for(let i=0;i<pts.length-1;i++){const[a0,v0]=pts[i],[a1,v1]=pts[i+1];if(t<a1)return L(v0,v1,io(lin(t,a0,a1)));}return pts[pts.length-1][1];};
// ---- tempos (tudo ancorado nas palavras da locução) ----
const tRepro=a('reprodutivo')+0.1,tIns=a('inseminacao2')+0.12,tLotes=a('lotes')+0.1,tAlta=a('alta')+0.1,tSel=a('selecionar')+0.35,tTodas=a('todas')+0.15,
 tEst=a('confirmar')+0.1,tDeixe=a('deixe')+0.55,tCont=a('continuar')+0.1,tOrion=a('touro')+0.8,tColap=a('touroPorVaca')+0.2,tVaca=tColap+0.8,tClose=tVaca+1.2,
 tSalvar=a('salvar')+0.1,tTentar=a('tentar')+0.95;
const cT={lancar:0,grade:tRepro+0.1,p1a:tIns+0.1,orig:tLotes+0.1,alta:tAlta+0.1,sel:tSel+0.1,todas:tTodas+0.1,sheet:tEst+0.1,todas2:tDeixe+0.1,p2a:tCont+0.1,p2b:tOrion+0.1,p2c:tColap+0.1,
 sheetT:tVaca+0.1,p2d:tClose+0.1,prog1:tSalvar+0.1,prog3:a('umaPorUma2')+0.35,res:a('pronto')+0.05,falha:a('falhar')-0.3,retry:tTentar+0.1};
EP.imgs={lancar:'s01_lancar',grade:'s02_repro_grade',p1a:'s03_p1_animais',orig:'s04_origem_lotes',alta:'s05_alta_aptas',sel:'s06_aptas_marcadas',todas:'s07_todas',sheet:'s08_sheet_estrela',
 todas2:'s07_todas',p2a:'s10_p2_topo',p2b:'s11_p2_orion',p2c:'s12_p2_touro_vaca',sheetT:'s13_sheet_troca',p2d:'s14_p2_pronto',prog1:'s15_progresso1',prog3:'s16_progresso3',
 res:'s17_resultado',falha:'s18_resultado_falha',retry:'s19_resultado_retry'};
EP.telas=[[0,'lancar',0],[cT.grade,'grade',1],[cT.p1a,'p1a',1],[cT.orig,'orig',0],[cT.alta,'alta',0],[cT.sel,'sel',0],[cT.todas,'todas',0],[cT.sheet,'sheet',0],[cT.todas2,'todas2',0],
 [cT.p2a,'p2a',1],[cT.p2b,'p2b',0],[cT.p2c,'p2c',0],[cT.sheetT,'sheetT',0],[cT.p2d,'p2d',0],[cT.prog1,'prog1',0],[cT.prog3,'prog3',0],[cT.res,'res',1],[cT.falha,'falha',0],[cT.retry,'retry',0]];
// ---- rolagem (px CSS do app) ----
const SA=560;                                   // 01 - Alta: "Selecionar todas" + os 4 cartões na tela
const rAlta=seg([[a('liberadas')+0.5,0],[a('liberadas')+1.6,SA]]);
const rSel=seg([[a('toqueSel')+0.1,SA+21],[a('umaPorUma')+2.0,SA+21],[a('prenhe')+0.1,330]]);   // +21: a linha "Rascunho salvo" empurra a página
const YE=1649;                                  // Estrela (gestante) no meio da tela
const rTodas=seg([[a('todas')+0.1,330],[a('todas')+0.3,330],[a('aviso')+0.5,YE]]);
const rTodas2=seg([[0,YE]]);
const rP=seg([[a('touro')-0.3,0],[a('touro')+0.5,340],[a('outroTouro')-0.4,340],[a('outroTouro')+0.6,525]]);
const rC=seg([[tColap+0.1,525],[tColap+0.3,525],[tColap+1.0,736]]);
EP.rolagem={alta:rAlta,sel:rSel,todas:rTodas,todas2:rTodas2,p2a:rP,p2b:rP,p2c:rC};
const S=(id,t)=>cl(EP.rolagem[id](t),0,mx(EP.imgs[id]));
const cx=b=>b.x+b.w/2,cy=b=>b.y+b.h/2;
// ---- toques: [t, x, y] em coordenadas da tela do celular (CSS) já com a barra de status (+30) ----
const rep=bt('s01_lancar','repro'),ins=bt('s02_repro_grade','inseminacao'),lb=bn('s03_p1_animais','lotesBtn'),pa=bn('s04_origem_lotes','pilulaAlta'),sl=bt('s05_alta_aptas','selTodas'),
 bTodas=bt('s06_aptas_marcadas','btnTodas'),cE=bt('s07_todas','cEstrela'),dx=bn('s08_sheet_estrela','deixar'),co=bn('s07_todas','continuar'),oO=bt('s10_p2_topo','opOrion'),
 cb=bt('s11_p2_orion','colapBtn'),v1=bt('s12_p2_touro_vaca','vaca1'),up=bn('s13_sheet_troca','usarPadrao'),cta=bn('s14_p2_pronto','cta'),te=bt('s18_resultado_falha','tentar');
EP.toques=[
 [tRepro,cx(rep),cy(rep)+SB],[tIns,cx(ins),cy(ins)+SB],[tLotes,cx(lb),cy(lb)+SB],[tAlta,cx(pa),cy(pa)+SB],
 [tSel,cx(sl),cy(sl)-S('alta',tSel)+SB],[tTodas,cx(bTodas),cy(bTodas)-S('sel',tTodas)+SB],[tEst,cx(cE),cy(cE)-S('todas',tEst)+SB],
 [tDeixe,cx(dx),cy(dx)+SB],[tCont,cx(co),cy(co)+SB],[tOrion,150,cy(oO)-S('p2a',tOrion)+SB],[tColap,cx(cb),cy(cb)-S('p2b',tColap)+SB],
 [tVaca,cx(v1),cy(v1)-S('p2c',tVaca)+SB],[tClose,cx(up),cy(up)+SB],[tSalvar,cx(cta),cy(cta)+SB],[tTentar,cx(te),cy(te)+SB]];
// ---- câmera: [t de chegada, duração, cx, cy, zoom] (coords da tela do celular com +30). Zoom ≤ 1,18 e centrado: nada de texto cortado nas bordas ----
EP.cam=[[0,0,195,300,1.0],[a('emLancar')+0.3,1.0,195,380,1.12],[tRepro+0.55,0.9,195,330,1.1],
 [a('primeiro')-0.4,1.0,195,450,1.0],[a('toqueLotes')-0.3,0.7,195,440,1.1],[tLotes+0.5,0.8,195,500,1.05],[a('situacao')-0.4,0.9,195,580,1.1],
 [a('liberadas')+0.4,1.0,195,400,1.0],[tSel+0.4,0.9,195,480,1.0],[a('prenhe')-0.5,1.0,195,430,1.05],[a('aviso')-0.4,0.9,195,330,1.15],
 [tEst+0.15,0.7,195,700,1.12],[a('deixe')-0.35,0.6,195,740,1.15],[tDeixe+0.4,0.8,195,690,1.05],
 [a('agora')-0.3,1.0,195,500,1.0],[a('touro')-0.3,0.9,195,520,1.0],[a('estoque')-0.3,0.8,195,480,1.12],[a('outroTouro')-0.5,0.9,195,520,1.0],
 [tVaca+0.1,0.6,195,600,1.1],[tClose+0.3,0.7,195,640,1.03],[a('pronto')-0.1,0.8,195,480,1.0],[a('falhar')-0.4,0.8,195,590,1.0]];
// ---- anotações: [t0,t1,tipo,x,y,w,h,{c,scr}] — somem exatamente no quadro da troca de tela seguinte (regra do motor) ----
const V='#2E7D52',Z='#1E6FA8',D='#E0A63C';
const bx=(n,k,o={})=>{const b=bt(n,k);return[b.x,b.y,b.w,b.h,o];};
const nb=(n,k,o={})=>{const b=bn(n,k);return[b.x,b.y,b.w,b.h,o];};
const tPv=a('touro')-0.35;
EP.anot=[
 [a('toqueRepro')+0.1,tRepro+0.1,'caixa',...bx('s01_lancar','repro',{c:V})],
 [a('depois')+0.3,tIns+0.1,'caixa',...bx('s02_repro_grade','inseminacao',{c:V})],
 [a('quem')-0.1,a('emOrigem')+0.4,'marca',98,264,226,22,{c:D}],
 [a('emOrigem')+0.3,tLotes+0.1,'caixa',...nb('s03_p1_animais','lotesBtn',{c:V})],
 [a('zeroUm')-0.3,tAlta+0.1,'caixa',...nb('s04_origem_lotes','pilulaAlta',{c:V})],
 [a('aptas')-0.15,a('liberadas')+0.55,'caixa',...bx('s05_alta_aptas','btnAptas',{c:V,scr:'alta'})],
 [a('toqueSel')-0.5,tSel+0.1,'marca',16,861,104,19,{c:D,scr:'alta'}],
 [a('toqueSel')+0.12,tSel+0.1,'caixa',...bx('s05_alta_aptas','selTodas',{c:D,scr:'alta'})],
 [a('umaPorUma')+0.0,a('prenhe')-0.55,'caixa',...bx('s06_aptas_marcadas','cJoia',{c:V,scr:'sel'})],
 [a('umaPorUma')+0.35,a('prenhe')-0.55,'caixa',...bx('s06_aptas_marcadas','cMimosa',{c:Z,scr:'sel'})],
 [a('umaPorUma')+0.7,a('prenhe')-0.55,'caixa',...bx('s06_aptas_marcadas','cBoneca',{c:V,scr:'sel'})],
 [a('umaPorUma')+1.05,a('prenhe')-0.55,'caixa',...bx('s06_aptas_marcadas','cAurora',{c:Z,scr:'sel'})],
 [tSel+0.55,a('umaPorUma')+1.0,'circulo',...(()=>{const b=bn('s06_aptas_marcadas','barraN');return[b.x,b.y,b.w,b.h,{c:Z}];})()],
 [a('todas')-0.2,tTodas+0.1,'caixa',...bx('s06_aptas_marcadas','btnTodas',{c:V,scr:'sel'})],
 [a('aviso')+0.5,tEst+0.1,'caixa',...bx('s07_todas','cEstrela',{c:D,scr:'todas'})],
 [tEst+0.45,tDeixe+0.1,'caixa',...bx('s08_sheet_estrela','sheetTexto',{c:D})],
 [a('deixe')-0.25,tDeixe+0.1,'caixa',...bx('s08_sheet_estrela','deixar',{c:V})],
 [a('data')-0.15,tPv,'caixa',16,419,358,77,{c:V,scr:'p2a'}],
 [a('categoria')-0.1,tPv,'caixa',...bx('s10_p2_topo','btnConv',{c:Z,scr:'p2a'})],
 [tOrion+0.12,a('outroTouro')-0.35,'caixa',...bx('s11_p2_orion','opOrion',{c:V,scr:'p2b'})],
 [a('estoque')-0.1,a('doze')-0.1,'caixa',...bx('s11_p2_orion','opOrionNum',{c:Z,scr:'p2b'})],
 [a('doze')-0.12,a('outroTouro')-0.35,'circulo',215,757,25,18,{c:Z,scr:'p2b'}],
 [a('oito')-0.12,a('outroTouro')-0.35,'circulo',269,757,14,18,{c:V,scr:'p2b'}],
 [a('touroPorVaca')-0.05,tColap+0.1,'caixa',...bx('s11_p2_orion','colapBtn',{c:V,scr:'p2b'})],
 [tColap+0.5,tVaca+0.1,'caixa',...bx('s12_p2_touro_vaca','vaca1',{c:Z,scr:'p2c'})],
 [tVaca+0.3,tClose+0.1,'caixa',...bx('s13_sheet_troca','usarPadrao',{c:V})],
 [a('toqueSalvar')+0.05,tSalvar+0.1,'caixa',...nb('s14_p2_pronto','cta',{c:D})],
 [a('umaPorUma2')-0.15,cT.prog3,'caixa',16,590,358,38,{c:Z}],
 [cT.prog3+0.1,cT.res,'caixa',16,590,358,38,{c:Z}],
 [a('lancado')+0.5,a('falhar')-0.4,'caixa',...bx('s17_resultado','lin1',{c:Z})],
 [a('falhar')+0.2,a('tentar')-0.35,'caixa',...bx('s18_resultado_falha','quadro',{c:V})],
 [a('tentar')-0.2,tTentar+0.1,'caixa',...bx('s18_resultado_falha','tentar',{c:D})]
];
EP.fitas=[[a('inseminacao')-0.1,a('emLancar')+0.1,'Inseminação em <b>lote</b>',110,298,-2]];
EP.titulos=[[0,'Temporada 2 · <m>Ep. 2</m>'],[a('emLancar')-0.1,'Toque em <m>Reprodutivo</m>'],[a('depois')-0.1,'Depois, <m>Inseminação</m>'],[a('primeiro')-0.1,'Passo 1: <m>quem</m>'],
 [a('situacao')-0.15,'Situação: <m>Aptas</m>'],[a('toqueSel')-0.1,'Selecionar <m>todas</m>'],[a('umaPorUma')-0.2,'Ou marque <m>uma por uma</m>'],[a('prenhe')-0.1,'E vaca <m>prenhe</m>?'],
 [a('toqueCont')-0.1,'Toque em <m>Continuar</m>'],[a('agora')-0.1,'Passo 2: o <m>sêmen</m>'],[a('estoque')-0.15,'O <m>estoque</m> baixa'],[a('outroTouro')-0.2,'<m>Touro</m> por vaca'],
 [a('toqueSalvar')-0.2,'<m>Salvar</m> inseminação'],[a('pronto')-0.1,'Feito: <m>lançado</m>'],[a('falhar')-0.25,'Se <m>falhar</m>: de novo'],[a('tentar')+1.6,'Pronto: <m>tudo</m> salvo']];
// diagrama Vox no papel: Gestante ✕ fica de fora (sobre o título, na "dúvida")
EP.diag=[a('duvida')-0.2,a('toqueCont')-0.1];
const F=TL.frases;
EP.leg=[[F[0][1],F[0][2],F[0][0]],[F[1][1],F[1][2],F[1][0]],
 [F[2][1],a('emOrigem')-0.3,'Primeiro, quem vai ser inseminada.'],[a('emOrigem')-0.3,F[2][2],'Em Origem, toque em Lotes, e no lote zero um, Alta.'],
 [F[3][1],F[3][2],F[3][0]],[F[4][1],F[4][2],F[4][0]],
 [F[5][1],a('duvida')-0.2,'E vaca prenhe? Em Todas, ela aparece com aviso, e só entra se você confirmar.'],[a('duvida')-0.2,F[5][2],'Na dúvida, deixe de fora.'],
 [F[6][1],F[6][2],F[6][0]],[F[7][1],F[7][2],F[7][0]],[F[8][1],F[8][2],F[8][0]],[F[9][1],F[9][2],F[9][0]],
 [F[10][1],a('umaPorUma2')-0.9,'Toque em Salvar inseminação.'],[a('umaPorUma2')-0.9,F[10][2],'O app manda uma por uma, e mostra o andamento.'],
 [F[11][1],a('falhar')-0.55,'Pronto, lançado.'],[a('falhar')-0.55,F[11][2],'Se alguma falhar, é só tocar em Tentar de novo só essa.']];
const tCapa=a('proximo')-0.15;EP.fimLeg=tCapa;EP.shake=a('lancado');
EP.entrada=t=>{const p=mola(t-0.3,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
const tCar=a('lancado'),tCarFim=a('falhar')-0.35;
EP.oculta=[[tCar,tCarFim],[a('inseminacao')-0.1,a('emLancar')+0.4]];
const IN='#1A2638';
EP.estado=(t,{K,io,oc,lin,mola,L,cl,ob,ic,cow,X,iq})=>{
  K.dymo.style.transform=`translateX(${(1-cl(mola(t-0.55,9,.55),0,1.15))*-1000}px) rotate(-1.6deg)`;
  const g=cl(mola(t-0.15,10,.5),0,1.2);K.grampo.style.transform=`translateY(${(1-g)*-230}px) rotate(${(1-cl(g,0,1))*6}deg)`;
  // diagrama: GESTANTE ✕ FICA DE FORA (traço do ✕ a 12 qps)
  const D0=EP.diag[0],D1=EP.diag[1];
  if(t>=D0-0.05&&t<D1+0.3){const pe=oc(lin(t,D0,D0+0.45)),ps=iq(lin(t,D1,D1+0.3));const b1=cl(mola(t-D0-0.05,12,.55),0,1.15),b2=cl(mola(t-D0-0.55,12,.55),0,1.15),px=io(lin(t,D0+0.3,D0+0.75));
    const w=(Math.floor(t*12)%3)-1;
    X(K.diag,`<div class="abs" style="left:0;top:20px;width:340px;height:112px;background:#FBF6E8;border:6px solid #1A2638;box-shadow:6px 8px 0 rgba(26,38,56,.25);transform:scale(${b1}) rotate(-1.5deg)"><div class="abs" style="left:18px;top:12px;font:800 42px/1 Archivo;color:${IN}">GESTANTE</div><div class="abs" style="left:18px;top:64px;font:700 27px/1 Inter,Archivo;color:#4b4034">58 dias de gestação</div></div>
     <div class="abs" style="left:590px;top:20px;width:330px;height:112px;background:#FBF6E8;border:6px solid #2E7D52;box-shadow:6px 8px 0 rgba(46,125,82,.28);transform:scale(${b2}) rotate(1.5deg)"><div class="abs" style="left:18px;top:12px;font:800 36px/1 Archivo;white-space:nowrap;color:#2E7D52">FICA DE FORA</div><div class="abs" style="left:18px;top:64px;font:700 27px/1 Inter,Archivo;color:#4b4034">na dúvida</div></div>
     <svg class="abs" style="left:350px;top:6px;clip-path:inset(0 ${(1-px)*100}% 0 0)" width="230" height="140" viewBox="0 0 230 140"><path d="M${62+w} ${34+w} L${168-w} ${106+w}" stroke="#1A2638" stroke-width="16" stroke-linecap="round" fill="none"/><path d="M${168+w} ${34-w} L${62-w} ${106-w}" stroke="#1A2638" stroke-width="16" stroke-linecap="round" fill="none"/></svg>`);
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
   <div class="abs" data-z="1" style="left:80px;top:360px;font:800 118px/1.02 Archivo;color:#1A2638;letter-spacing:-.02em;text-transform:uppercase">Diagnóstico<br>de <span style="position:relative;display:inline-block;z-index:0">gestação<i style="position:absolute;left:-10px;right:-14px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div>
   <div class="abs" data-z="2" style="left:80px;top:850px;width:380px;height:380px;background:#fff;box-shadow:0 26px 50px rgba(50,32,8,.3);display:flex;align-items:center;justify-content:center">${cow(250,'#1A2638',0.9)}</div>
   <div class="abs" data-z="3" style="left:510px;top:870px;width:490px"><div style="font:800 84px/1 Archivo;color:#1A2638;letter-spacing:-.02em">COW<span style="color:#8A5A12">DATA</span></div><div style="margin-top:28px;font:800 46px/1.1 Archivo;color:#1A2638;text-transform:uppercase">O rebanho na mão de <span style="position:relative;display:inline-block;z-index:0">quem cuida<i style="position:absolute;left:-8px;right:-10px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div></div>
   <div class="fita" data-z="4" style="left:90px;top:1330px">Ep. 2 · <b>Inseminação em lote</b></div>`);
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
EP.camadas=[[0,['piano','pad']],[a('emLancar'),['piano','pad','shaker']],[a('primeiro'),['piano','pad','baixo','shaker','bumbo_leve']],[a('agora'),['piano','pad','baixo','shaker','bumbo','palma','piano_cheio']],
 [a('pronto')-0.2,['piano','pad','baixo','shaker','shaker16','bumbo','palma','piano_cheio','sino']],[a('tentar')+1.4,['piano','pad','baixo','shaker','bumbo_leve']],[tCapa,['piano','pad','baixo','shaker','bumbo_leve','sino']]];
return EP;})()
