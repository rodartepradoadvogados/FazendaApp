(()=>{const a=A;const EP={};const SB=30;
// ---- caixas medidas no app real (captura): bt = conteúdo (coord. da página rolada a 0), bn = tela fixa (barra, navegação) ----
const bt=(n,k)=>{const m=MAPA[n];return(m.tall&&m.tall.alvos[k])||m.alvos[k];};const bn=(n,k)=>MAPA[n].alvosN[k];
const mx=n=>{const m=MAPA[n];return m.tall?Math.max(0,m.tall.h-69-m.barTop):0;};
const seg=pts=>t=>{if(t<=pts[0][0])return pts[0][1];for(let i=0;i<pts.length-1;i++){const[a0,v0]=pts[i],[a1,v1]=pts[i+1];if(t<a1)return L(v0,v1,io(lin(t,a0,a1)));}return pts[pts.length-1][1];};
// ---- tempos (tudo ancorado nas palavras da locução) ----
const tLanc=a('lancar')+0.1,tMov=a('movimentar')+0.1,tLotes=a('lotes')+0.1,tAlta=a('saem')-0.5,tM=[a('vacas')+0.2,a('pode')+0.2,a('pode')+0.9],tCont=a('continuar')+0.1,
 tDest=a('destino')+0.1,tMot=a('motivo')+0.25,tPill=a('motivo')+1.05,tBtn=a('tres')+0.05,tVer=a('lotesMudam')+0.2,tCmp=a('lotesMudam')+0.9;
const cT={agenda:0,lancar:tLanc+0.1,p1:tMov+0.1,orig:tLotes+0.1,alta:tAlta+0.1,m1:tM[0]+0.1,m2:tM[1]+0.1,m3:tM[2]+0.1,p2a:tCont+0.1,p2b:tDest+0.1,p2c:tMot+0.1,p2d:tPill+0.1,res:tBtn+0.1,lotes:tVer+0.1,comp:tCmp+0.1};
EP.imgs={agenda:'s00_agenda',lancar:'s01_lancar',p1:'s02_mov_p1',orig:'s03_origem_lotes',alta:'s04_alta_aberto',m1:'s05_marc1',m2:'s06_marc2',m3:'s07_marc3',p2a:'s08_p2_topo',p2b:'s09_p2_destino',p2c:'s10_p2_motivo_aberto',p2d:'s11_p2_motivo_ok',res:'s12_resultado',lotes:'s13_composicao',comp:'s14_composicao_lista'};
EP.telas=[[0,'agenda',0],[cT.lancar,'lancar',1],[cT.p1,'p1',1],[cT.orig,'orig',0],[cT.alta,'alta',0],[cT.m1,'m1',0],[cT.m2,'m2',0],[cT.m3,'m3',0],[cT.p2a,'p2a',1],[cT.p2b,'p2b',0],[cT.p2c,'p2c',0],[cT.p2d,'p2d',0],[cT.res,'res',1],[cT.lotes,'lotes',1],[cT.comp,'comp',1]];
// ---- rolagem (px CSS do app) ----
const rA=seg([[a('saem')+0.1,0],[a('saem')+0.5,0],[a('marque')-0.25,440]]);
const rP=seg([[cT.p2a,0],[a('quadro')-0.1,0],[a('quadro')+0.9,560],[a('motivo')-0.5,560],[a('motivo')+0.1,900],[tMot+0.25,900],[tMot+0.8,1236]]);
EP.rolagem={lancar:seg([[a('depois')-1.2,0],[a('depois')-0.3,117]]),alta:rA,m1:rA,m2:rA,m3:rA,p2a:rP,p2b:rP,p2c:rP,p2d:rP};
const S=(id,t)=>cl(EP.rolagem[id](t),0,mx(EP.imgs[id]));
const cx=b=>b.x+b.w/2,cy=b=>b.y+b.h/2;
// ---- toques: [t, x, y] em coordenadas da tela do celular (CSS) já com a barra de status (+30) ----
const nav=bn('s00_agenda','navLancar'),mov=bt('s01_lancar','movimentar'),lb=bn('s02_mov_p1','lotesBtn'),pa=bn('s03_origem_lotes','pilulaAlta');
EP.toques=[
 [tLanc,cx(nav)+2,cy(nav)-24+SB],
 [tMov,cx(mov),cy(mov)-S('lancar',tMov)+SB],
 [tLotes,cx(lb),cy(lb)+SB],
 [tAlta,cx(pa),cy(pa)+SB],
 [tM[0],150,cy(bt('s04_alta_aberto','c3990'))-S('alta',tM[0])+SB],
 [tM[1],150,cy(bt('s05_marc1','c4033'))-S('m1',tM[1])+SB],
 [tM[2],150,cy(bt('s06_marc2','c4078'))-S('m2',tM[2])+SB],
 [tCont,cx(bn('s07_marc3','continuar')),cy(bn('s07_marc3','continuar'))+SB],
 [tDest,150,cy(bt('s08_p2_topo','opMedia'))+SB],
 [tMot,300,cy(bt('s09_p2_destino','colapBtn'))-S('p2b',tMot)+SB],
 [tPill,130,cy(bt('s10_p2_motivo_aberto','pillMotivo'))-S('p2c',tPill)+SB],
 [tBtn,cx(bn('s11_p2_motivo_ok','cta')),cy(bn('s11_p2_motivo_ok','cta'))+SB],
 [tVer,cx(bt('s12_resultado','verLotes')),cy(bt('s12_resultado','verLotes'))+SB],
 [tCmp,cx(bt('s13_composicao','comp')),cy(bt('s13_composicao','comp'))+SB]];
// ---- câmera: [t de chegada, duração, cx, cy, zoom] (coords da tela do celular com +30) ----
EP.cam=[[0,0,195,235,1.0],[a('noApp')+0.5,1.0,150,690,1.25],[a('depois')-0.9,1.0,195,560,1.0],[a('depois')+0.5,0.9,110,640,1.3],
 [a('primeiro')+0.2,1.0,195,330,1.1],[a('toqueLotes')-0.2,0.8,195,320,1.25],[tLotes+0.7,0.8,195,500,1.0],[a('marque')-0.2,0.9,195,450,1.05],
 [a('barra')-0.4,0.9,205,620,1.1],[a('agora')-0.3,1.0,195,520,1.0],[a('conta2')-0.3,0.9,260,500,1.3],
 [a('quadro')+0.2,1.0,195,470,1.1],[a('motivo')-0.1,0.9,195,330,1.25],[a('toqueMov')-0.3,0.9,195,660,1.2],
 [tBtn+0.9,1.0,195,450,1.0],[tVer-0.2,0.7,195,640,1.1],[tVer+0.4,0.5,195,350,1.15],[tCmp+0.6,0.9,195,400,1.1],[a('semInternet')+0.2,1.0,195,480,1.0]];
// ---- anotações: [t0,t1,tipo,x,y,w,h,{c,scr}] — somem exatamente no quadro da troca de tela seguinte (regra do motor) ----
const V='#2E7D52',Z='#1E6FA8',D='#E0A63C';
const bx=(n,k,o={})=>{const b=bt(n,k);return[b.x,b.y,b.w,b.h,o];};
const num=bt('s09_p2_destino','opMediaNum'),dpb=bt('s09_p2_destino','dp');
EP.anot=[
 [a('noApp')+0.3,tLanc+0.1,'circulo',cx(nav)-30,cy(nav)-24-30,60,60,{c:V}],
 [a('depois')+0.3,tMov+0.1,'caixa',...bx('s01_lancar','movimentar',{c:V,scr:'lancar'})],
 [a('quem')-0.1,a('emOrigem')+0.4,'marca',98,190,232,26,{c:D}],
 [a('emOrigem')+0.3,tLotes+0.1,'caixa',lb.x,lb.y,lb.w,lb.h,{c:V}],
 [a('escolha')+0.35,tAlta+0.1,'caixa',pa.x,pa.y,pa.w,pa.h,{c:V}],
 [a('marque')-0.3,cT.m1,'marca',22,604,130,26,{c:D,scr:'alta'}],
 [tM[0]+0.12,cT.m2,'caixa',...bx('s05_marc1','c3990',{c:V,scr:'m1'})],
 [cT.m2,cT.m3,'caixa',...bx('s06_marc2','c3990',{c:V,scr:'m2',fixo:1})],[tM[1]+0.12,cT.m3,'caixa',...bx('s06_marc2','c4033',{c:Z,scr:'m2'})],
 [cT.m3,a('barra')-0.1,'caixa',...bx('s07_marc3','c3990',{c:V,scr:'m3',fixo:1})],[cT.m3,a('barra')-0.1,'caixa',...bx('s07_marc3','c4033',{c:Z,scr:'m3',fixo:1})],
 [tM[2]+0.12,a('barra')-0.1,'caixa',...bx('s07_marc3','c4078',{c:V,scr:'m3'})],
 [a('inteiro')-0.1,a('barra')-0.15,'caixa',...(()=>{const g=bt('s07_marc3','grupoCab');return[g.x+g.w-100,g.y+10,96,g.h-20,{c:D,scr:'m3'}];})()],
 [a('barra')+0.05,cT.p2a,'circulo',...(()=>{const b=bn('s07_marc3','barraN');return[b.x,b.y,b.w,b.h,{c:Z}];})()],
 [a('toqueCont')+0.1,cT.p2a,'caixa',...(()=>{const b=bn('s07_marc3','continuar');return[b.x,b.y,b.w,b.h,{c:D}];})()],
 [a('toqueDest')+0.25,cT.p2b,'caixa',...bx('s08_p2_topo','opMedia',{c:Z})],
 [a('trinta')-0.12,a('quadro')-0.1,'circulo',244.7,num.y+7,24.5,17,{c:Z,scr:'p2b'}],
 [a('quarenta')-0.12,a('quadro')-0.1,'circulo',300.8,num.y+7,24.5,17,{c:V,scr:'p2b'}],
 [a('sai')-0.12,a('motivo')-0.15,'caixa',dpb.x+10,dpb.y+8,160,46,{c:V,scr:'p2b'}],
 [a('chega')-0.12,a('motivo')-0.15,'caixa',dpb.x+dpb.w-120,dpb.y+8,112,46,{c:Z,scr:'p2b'}],
 [tPill+0.12,tPill+1.6,'caixa',...bx('s11_p2_motivo_ok','pillMotivo',{c:V,scr:'p2d'})],
 [a('data')+0.2,tBtn+0.1,'caixa',...bx('s11_p2_motivo_ok','data',{c:D,scr:'p2d'})],
 [a('toqueMov')+0.05,cT.res,'caixa',...(()=>{const b=bn('s11_p2_motivo_ok','cta');return[b.x,b.y,b.w,b.h,{c:D}];})()],
 [tCmp+0.15,a('semInternet')-0.1,'caixa',...bx('s14_composicao_lista','n39',{c:V})],[tCmp+0.45,a('semInternet')-0.1,'caixa',...bx('s14_composicao_lista','n41',{c:Z})]
].map(e=>e);
EP.fitas=[[a('troca')-0.1,a('noApp')+0.1,'Troca de <b>Lotes</b>',120,640,-3]];
EP.titulos=[[0,'Os <m>Lançamentos</m>'],[a('noApp')-0.1,'Toque em <m>Lançar</m>'],[a('depois')-0.1,'Depois, <m>Movimentar</m>'],[a('primeiro')-0.1,'Passo 1: <m>quem</m> sai'],
 [a('marque')-0.1,'<m>Marque</m> as vacas'],[a('barra')-0.25,'A barra <m>conta</m>'],[a('agora')-0.1,'Passo 2: <m>para onde</m>'],[a('motivo')-0.15,'<m>Motivo</m> e data'],
 [a('toqueMov')-0.2,'<m>Movimentar</m> 3 animais'],[a('pronto')-0.1,'Feito: <m>lançado</m>'],[a('lotesMudam')-0.15,'Os lotes <m>mudaram</m>'],[a('semInternet')-0.1,'Sem <m>internet</m>?']];
EP.diag=[a('quadro')-0.15,a('motivo')-0.15];
const F=TL.frases;
EP.leg=[[F[0][1],F[0][2],F[0][0]],[F[1][1],F[1][2],F[1][0]],[F[2][1],F[2][2],F[2][0]],
 [F[3][1],a('emOrigem')-0.3,'Primeiro, quem vai mudar de lote.'],[a('emOrigem')-0.3,F[3][2],'Em Origem, toque em Lotes e escolha o lote de onde as vacas saem.'],
 [F[4][1],F[4][2],F[4][0]],[F[5][1],F[5][2],F[5][0]],
 [F[6][1],a('conta2')-1.1,'Agora, para onde elas vão. Toque no lote de destino.'],[a('conta2')-1.1,F[6][2],'O app já mostra a conta: trinta e oito vira quarenta e um.'],
 [F[7][1],a('motivo')-0.15,'O quadro confere quem sai e quem chega.'],[a('motivo')-0.15,F[7][2],'Escolha o motivo e confira a data.'],
 [F[8][1],F[8][2],F[8][0]],[F[9][1],F[9][2],F[9][0]],[F[10][1],F[10][2],F[10][0]]];
const tCapa=a('proximo')-0.15;EP.fimLeg=tCapa;EP.shake=a('lancado');
EP.entrada=t=>{const p=mola(t-0.3,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
const tCart=a('semInternet')-0.05,tCartFim=tCapa-0.2,tCar=a('lancado'),tCarFim=tVer-0.15;
const IN='#1A2638';
EP.estado=(t,{K,io,oc,lin,mola,L,cl,ob,ic,cow,X,iq})=>{
  K.dymo.style.transform=`translateX(${(1-cl(mola(t-0.55,9,.55),0,1.15))*-1000}px) rotate(-1.6deg)`;
  const g=cl(mola(t-0.15,10,.5),0,1.2);K.grampo.style.transform=`translateY(${(1-g)*-230}px) rotate(${(1-cl(g,0,1))*6}deg)`;
  // diagrama De → Para (fora do celular): seta tracejada animada a 12 qps
  const D0=EP.diag[0],D1=EP.diag[1];
  if(t>=D0-0.05&&t<D1+0.3){const pe=oc(lin(t,D0,D0+0.45)),ps=iq(lin(t,D1,D1+0.3));const b1=cl(mola(t-D0-0.05,12,.55),0,1.15),b2=cl(mola(t-D0-0.45,12,.55),0,1.15),pa=io(lin(t,D0+0.3,D0+0.9));
    const off=-(Math.floor(t*12)%12)*4.5;
    X(K.diag,`<div class="abs" style="left:0;top:20px;width:300px;height:112px;background:#FBF6E8;border:6px solid #2E7D52;box-shadow:6px 8px 0 rgba(46,125,82,.28);transform:scale(${b1}) rotate(-1.5deg)"><div class="abs" style="left:18px;top:12px;font:800 38px/1 Archivo;color:${IN}">01 - ALTA</div><div class="abs" style="left:18px;top:62px;font:700 28px/1 Inter,Archivo;color:#2E7D52">sai · 42 → 39</div></div>
     <div class="abs" style="left:620px;top:20px;width:300px;height:112px;background:#FBF6E8;border:6px solid #1E6FA8;box-shadow:6px 8px 0 rgba(30,111,168,.28);transform:scale(${b2}) rotate(1.5deg)"><div class="abs" style="left:18px;top:12px;font:800 38px/1 Archivo;color:${IN}">02 - MÉDIA</div><div class="abs" style="left:18px;top:62px;font:700 28px/1 Inter,Archivo;color:#1E6FA8">chega · 38 → 41</div></div>
     <div class="abs" style="left:318px;top:0;width:284px;text-align:center;font:800 30px/1 Archivo;color:${IN};letter-spacing:.04em;opacity:${pa}">3 VACAS</div>
     <svg class="abs" style="left:310px;top:36px;clip-path:inset(0 ${(1-pa)*100}% 0 0)" width="300" height="80" viewBox="0 0 300 80"><path d="M6 44 L268 44" stroke="#1E6FA8" stroke-width="10" stroke-linecap="round" stroke-dasharray="26 18" stroke-dashoffset="${off}" fill="none"/><path d="M246 18 L284 44 L246 70" stroke="#1E6FA8" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>
     <div class="abs" style="left:318px;top:112px;width:284px;text-align:center;font:700 26px/1 Inter,Archivo;color:#4b4034;opacity:${pa}">3990 · 4033 · 4078</div>`);
    K.diag.style.display='block';K.diag.style.opacity=1-ps;K.diag.style.transform=`translateY(${(1-pe)*-170+ps*-120}px)`;}
  else K.diag.style.display='none';
  // cartão de nota (sem internet)
  if(t>=tCart&&t<tCartFim+0.4){const q=cl(mola(t-tCart,11,.5),0,1.15),s=iq(lin(t,tCartFim,tCartFim+0.4));
    X(K.cartao,`<div class="fx"></div><div class="abs" style="right:36px;top:28px;color:#8A5A12"><svg width="78" height="78" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m2 2 20 20"/><path d="M5.782 5.782A7 7 0 0 0 9 19h8.5a4.5 4.5 0 0 0 1.307-.193"/><path d="M21.532 16.5A4.5 4.5 0 0 0 17.5 10h-1.79A7.008 7.008 0 0 0 10 5.07"/></svg></div>Sem internet?<small>Fica guardado e vai ao conectar.</small>`);
    K.cartao.style.display='block';K.cartao.style.transform=`translateY(${(1-q)*700+s*900}px) rotate(${L(6,-2.5,cl(q,0,1))}deg)`;}else K.cartao.style.display='none';
  // carimbo de borracha: bate no "lançado", com 3 quadros de tremida (cena inteira, ver shake no motor)
  if(t>=tCar&&t<tCarFim){const q=oc(lin(t,tCar,tCar+0.1)),s=lin(t,tCarFim-0.2,tCarFim);
    X(K.carimbo,`<div style="display:flex;align-items:center;justify-content:center;gap:22px;border:9px solid #1B4D33;outline:3px solid #1B4D33;outline-offset:6px;border-radius:16px;padding:26px 30px;color:#14452B;font:800 44px/1 Archivo;letter-spacing:.04em;white-space:nowrap;background:rgba(251,246,232,.72);filter:url(#tinta)"><svg width="62" height="62" viewBox="0 0 24 24" fill="none" stroke="#1B4D33" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5l5 5L20 6.5"/></svg>LANÇADO NO REBANHO</div>`);
    K.carimbo.style.display='block';K.carimbo.style.opacity=(0.93*(1-s)*cl(q*4)).toFixed(3);K.carimbo.style.transform=`translateX(-50%) rotate(-7deg) scale(${L(1.7,1,q)})`;}else K.carimbo.style.display='none';
};
EP.capa=(t,el)=>{const p=io(lin(t,tCapa,tCapa+0.7));if(p<=0){el.style.display='none';return;}el.style.display='block';el.style.clipPath=`inset(${(1-p)*100}% 0 0 0)`;
  const q=mola(t-tCapa-0.45,10,.5),r=mola(t-tCapa-0.95,12,.5),s=oc(lin(t,tCapa+1.7,tCapa+2.3)),u=mola(t-tCapa-2.5,12,.5);
  X(el,`<div class="dymo" style="top:250px;left:80px;transform:rotate(-1.6deg)">PRÓXIMO EPISÓDIO · TEMP. 02</div>
   <div class="abs" data-z="1" style="left:80px;top:360px;font:800 118px/1.02 Archivo;color:#1A2638;letter-spacing:-.02em;text-transform:uppercase">Inseminação<br>em <span style="position:relative;display:inline-block;z-index:0">lote<i style="position:absolute;left:-10px;right:-14px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div>
   <div class="abs" data-z="2" style="left:80px;top:850px;width:380px;height:380px;background:#fff;box-shadow:0 26px 50px rgba(50,32,8,.3);display:flex;align-items:center;justify-content:center">${cow(250,'#1A2638',0.9)}</div>
   <div class="abs" data-z="3" style="left:510px;top:870px;width:490px"><div style="font:800 84px/1 Archivo;color:#1A2638;letter-spacing:-.02em">COW<span style="color:#8A5A12">DATA</span></div><div style="margin-top:28px;font:800 46px/1.1 Archivo;color:#1A2638;text-transform:uppercase">O rebanho na mão de <span style="position:relative;display:inline-block;z-index:0">quem cuida<i style="position:absolute;left:-8px;right:-10px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div></div>
   <div class="fita" data-z="4" style="left:90px;top:1330px">Ep. 1 · <b>Troca de lotes</b></div>`);
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
EP.sfx.push([EP.diag[0],'rasgo'],[tCart,'rasgo'],[tCartFim,'whoosh'],[tCapa,'whoosh'],[tCapa+2.5,'rasgo'],[EP.shake,'carimbo']);
EP.sfx.sort((p,q)=>p[0]-q[0]);
EP.camadas=[[0,['piano','pad']],[a('noApp'),['piano','pad','shaker']],[a('primeiro'),['piano','pad','baixo','shaker','bumbo_leve']],[a('agora'),['piano','pad','baixo','shaker','bumbo','palma','piano_cheio']],
 [a('pronto')-0.2,['piano','pad','baixo','shaker','shaker16','bumbo','palma','piano_cheio','sino']],[a('semInternet')-0.1,['piano','pad','baixo','shaker','bumbo_leve']],[tCapa,['piano','pad','baixo','shaker','bumbo_leve','sino']]];
return EP;})()
