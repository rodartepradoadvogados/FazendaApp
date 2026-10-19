(()=>{const a=A;const EP={};const SB=30;
// ---- Ep. 10 · Sanidade › protocolo sanitário (Curativa › Protocolo sanitário = CurativaForm tipo="protocolo", a mesma tela de Lançar › Protocolos › Sanitário). Telas = capturas do app real (captura/capturar_t2e10.mjs). ----
// Formulário de UM animal, sem barra fixa (barTop = topo da navegação): a rolagem é contínua dentro de cada captura alta. Cada estado tem o próprio máximo de rolagem; a troca de estado é dissolvida.
const bt=(n,k)=>{const m=MAPA[n];return(m.tall&&m.tall.alvos[k])||m.alvos[k];};
const mx=n=>{const m=MAPA[n];return m.tall?Math.max(0,m.tall.h-69-m.barTop):0;};
const seg=pts=>t=>{if(t<=pts[0][0])return pts[0][1];for(let i=0;i<pts.length-1;i++){const[a0,v0]=pts[i],[a1,v1]=pts[i+1];if(t<a1)return L(v0,v1,io(lin(t,a0,a1)));}return pts[pts.length-1][1];};
const F=TL.frases;
// frases: 0 título · 1 Em Lançar, toque em Sanidade · 2 depois em Curativa · 3 e em Protocolo sanitário · 4 A mesma tela abre em Protocolos · 5 Escolha o animal · 6 ou o lote inteiro · 7 e confira a data de início
// · 8 Em Protocolo sanitário · 9 escolha o tratamento cadastrado pelo veterinário · 10 ele já traz os remédios, as doses e os dias · 11 Protocolo de mastite é lançado um animal por vez · 12 e pede a classificação da mastite
// · 13 Se precisar · 14 escreva uma observação · 15 e toque em Salvar · 16 Pronto, lançado · 17 O app cria o tratamento com todas as etapas · 18 para acompanhar dia a dia · 19 próximo episódio
const s=i=>F[i][1],e=i=>F[i][2];
// ---- tempos (tudo ancorado nas palavras da locução) ----
const tSan=a('sanidade')+0.1,tCur=a('curativa')+0.1,tProt=a('protSanit')+0.1,tRel=a('mesmaTela')-0.35,tBack=e(4)+0.3,
 tBusca=a('animal')+0.1,tDig=tBusca+0.5,tSelAn=s(6)-0.3,
 tTap=a('protocolo')+0.05,tLista=tTap+0.15,tPick=a('veterinario')+0.45,
 tCls=e(12)-0.3,tClsV=tCls+0.3,tObs=a('observacao')+0.05,tObsV=tObs+0.55,tSalv=a('salvar')+0.05;
const cT={grade:tSan+0.12,cur:tCur+0.12,form:tProt+0.12,prot:tRel,form2:tBack,dig:tDig,an:tSelAn+0.12,lista:tLista,proto:tPick+0.12,cls:tClsV,obs:tObsV,salvo:tSalv+0.5};
const tCapa=a('proximo')-0.15;
EP.imgs={lancar:'s01_lancar',grade:'s02_grade',cur:'s03_curativa',form:'s04_form',prot:'p01_protocolos',form2:'s04_form',dig:'s05_digitado',an:'s06_animal',lista:'s07_lista',proto:'s08_proto',cls:'s09_classif',obs:'s10_obs',salvo:'s11_salvo'};
// [t, tela, direção (1 = desliza da direita, -1 = da esquerda: voltar), 1 = só troca de estado (as anotações continuam), dissolvência em s]
const DF=0.18;
EP.telas=[[0,'lancar',0],[cT.grade,'grade',1],[cT.cur,'cur',1],[cT.form,'form',1],[cT.prot,'prot',1],[cT.form2,'form2',-1],[cT.dig,'dig',0,1,0.12],[cT.an,'an',0,1,DF],[cT.lista,'lista',0,1,0.1],[cT.proto,'proto',0,1,DF],
 [cT.cls,'cls',0,1,0.1],[cT.obs,'obs',0,1,0.1],[cT.salvo,'salvo',0,1,DF]];
// ---- rolagem (px CSS do app; cada estado limita ao próprio máximo) ----
// 0 até a classificação · 110 (a observação à vista) · 193 (o Salvar inteiro, máximo do estado) · 162 no salvo (o aviso à vista)
const SG=seg([[0,0],[s(13)-0.1,0],[s(13)+0.6,110],[tObsV+0.15,110],[tObsV+0.8,193],[tSalv+0.45,193]]);
const SGs=seg([[0,162]]);
EP.rolagem={an:()=>0,lista:()=>0,proto:SG,cls:SG,obs:SG,salvo:SGs};
const S=(id,t)=>cl(EP.rolagem[id]?EP.rolagem[id](t):0,0,mx(EP.imgs[id]));
const cx=b=>b.x+b.w/2,cy=b=>b.y+b.h/2;
// ---- toques: [t, x, y] em coordenadas da tela do celular (CSS) já com a barra de status (+30) ----
const B=(n,k)=>bt(n,k);
const bSan=B('s01_lancar','san'),bCur=B('s02_grade','cur'),bProt=B('s03_curativa','proto'),bBusca=B('s04_form','busca'),bRes=B('s05_digitado','res'),
 bPs=B('s06_animal','protoSel'),bLs=B('s07_lista','protoSel'),bCl=B('s08_proto','classifSel'),bOb=B('s09_classif','obsIn'),bSv=B('s10_obs','salvar');
EP.toques=[
 [tSan,cx(bSan),cy(bSan)+SB],[tCur,cx(bCur),cy(bCur)+SB],[tProt,cx(bProt),cy(bProt)+SB],[tBusca,cx(bBusca),cy(bBusca)+SB],[tSelAn,cx(bRes),cy(bRes)+SB],
 [tTap,cx(bPs),cy(bPs)-S('an',tTap)+SB],[tPick,cx(bLs),bLs.y+44+SB],[tCls,cx(bCl),cy(bCl)-S('proto',tCls)+SB],[tObs,cx(bOb),cy(bOb)-S('cls',tObs)+SB],[tSalv,cx(bSv),cy(bSv)-S('obs',tSalv)+SB]];
// ---- câmera: [t de chegada, duração, cx, cy, zoom] (coords da tela do celular com +30). Visível: de cy-189/z a cy+349/z. Zoom ≤ 1,18 e centrado ----
EP.cam=[[0,0,195,300,1.0],[a('emLancar')+0.4,1.0,195,440,1.1],[tSan+0.55,0.9,195,335,1.1],[tCur+0.55,0.8,195,345,1.1],[tProt+0.6,0.8,195,470,1.0],
 [tRel+0.4,0.7,195,345,1.1],[tBack+0.5,0.8,195,470,1.0],[tSelAn+0.7,0.9,195,480,1.0]];
// ---- anotações: [t0,t1,tipo,x,y,w,h,{c,scr}] — somem exatamente no quadro da troca de tela seguinte (regra do motor) ----
const V='#2E7D52',Z='#1E6FA8',D='#E0A63C',IN='#1A2638',RD='#B3392F',AM='#C27B14';
const bx=(n,k,o={})=>{const b=bt(n,k);return[b.x,b.y,b.w,b.h,o];};
EP.anot=[
 [a('sanidade')-0.7,tSan+0.1,'caixa',...bx('s01_lancar','san',{c:V})],
 [a('curativa')-0.25,tCur+0.1,'caixa',...bx('s02_grade','cur',{c:RD})],
 [a('protSanit')-0.3,tProt+0.1,'caixa',...bx('s03_curativa','proto',{c:Z})],
 [a('protocolos')-0.35,tBack-0.05,'caixa',...bx('p01_protocolos','sanitario',{c:V})],
 [a('animal')-0.25,tBusca+0.3,'caixa',...bx('s04_form','pillA',{c:V})],
 [tDig+0.15,tSelAn+0.1,'caixa',...bx('s05_digitado','res',{c:D})],
 [tSelAn+0.2,a('lote')-0.3,'caixa',...bx('s06_animal','animalSel',{c:V,scr:'an'})],
 [a('lote')-0.25,a('data')-0.45,'caixa',...bx('s06_animal','pillL',{c:Z,scr:'an'})],
 [a('data')-0.2,tTap-0.1,'caixa',...bx('s06_animal','dataIn',{c:D,scr:'an'})],
 [tTap-0.2,tTap+0.12,'caixa',...bx('s06_animal','protoSel',{c:D,scr:'an'})],
 [tPick+0.3,a('mastite')-0.1,'caixa',...bx('s08_proto','protoSel',{c:Z,scr:'proto'})],
 [a('classificacao')-0.25,tCls+0.1,'caixa',...bx('s08_proto','classifSel',{c:D,scr:'proto'})],
 [a('observacao')-0.25,tObs+0.1,'caixa',...bx('s09_classif','obsIn',{c:Z,scr:'cls'})],
 [a('salvar')-0.25,tSalv+0.1,'caixa',...bx('s10_obs','salvar',{c:D,scr:'obs'})],
 [tSalv+0.85,a('lancado')-0.1,'caixa',...bx('s11_salvo','aviso',{c:V,scr:'salvo'})]
];
EP.fitas=[[a('fita1')-0.1,a('emLancar')+0.1,'Protocolo <b>sanitário</b>',110,298,-2],
 [a('mastite')-0.3,e(11)+0.1,'Mastite: <b>1 animal por vez</b>',100,298,-1.5]];
EP.titulos=[[0,'Temporada 2 · <m>Ep. 10</m>'],[a('emLancar')-0.1,'Em Lançar: <m>Sanidade</m>'],[a('curativa')-0.3,'Toque em <m>Curativa</m>'],[a('protSanit')-0.3,'Protocolo <m>sanitário</m>'],
 [a('mesmaTela')-0.2,'Mesma tela em <m>Protocolos</m>'],[a('animal')-0.2,'Escolha o <m>animal</m>'],[a('lote')-0.15,'…ou o <m>lote</m>'],[a('data')-0.15,'Data de <m>início</m>'],[a('protocolo')-0.15,'Escolha o <m>protocolo</m>'],
 [e(11)+0.1,'<m>Classificação</m> da mastite'],[a('observacao')-0.25,'<m>Observação</m> (se precisar)'],[a('salvar')-0.25,'Toque em <m>Salvar</m>'],[a('lancado')+0.2,'Feito: <m>lançado</m>']];
// diagramas Vox no papel: (1) o protocolo traz remédios + doses + dias (etapas D0 · D1 · D2, só no papel: o formulário do app não lista as etapas); (2) depois de salvar: as etapas por dia
const D2=[s(10)-0.1,e(10)+0.35],D4=[a('etapas')-0.15,tCapa+0.0];
EP.diag=[0,0];
const tCar=a('lancado'),tCarFim=a('etapas')-0.3;
const L2=i=>[F[i][1],F[i][2],F[i][0]];
EP.leg=[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19].map(L2);
EP.fimLeg=tCapa;EP.shake=a('lancado');
EP.entrada=t=>{const p=mola(t-0.3,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
EP.oculta=[[tCar,D4[1]+0.5],[D2[0],e(11)+0.1+0.36],[a('fita1')-0.1,a('emLancar')+0.4]];
EP.estado=(t,{K,io,oc,lin,mola,L,cl,ob,ic,cow,X,iq})=>{
  K.dymo.style.transform=`translateX(${(1-cl(mola(t-0.55,9,.55),0,1.15))*-1000}px) rotate(-1.6deg)`;
  const g=cl(mola(t-0.15,10,.5),0,1.2);K.grampo.style.transform=`translateY(${(1-g)*-230}px) rotate(${(1-cl(g,0,1))*6}deg)`;
  let desenhado=false;
  const svg=h=>`<svg width="920" height="140" viewBox="0 0 920 140" style="overflow:visible">${h}</svg>`;
  const w=(Math.floor(t*12)%3)-1,off=(Math.floor(t*12)%6)*4;
  const chip=(x,sc,rot,borda,lab,l1,l2,tam=26)=>`<g transform="translate(${x+130} 66) rotate(${rot}) scale(${sc}) translate(-130 -66)"><rect x="3" y="3" width="254" height="126" fill="#FBF6E8" stroke="${borda}" stroke-width="7"/><rect x="3" y="3" width="254" height="126" fill="${borda}" opacity=".14"/>`
    +`<text x="22" y="52" font-family="Archivo" font-weight="800" font-size="40" fill="${borda}">${lab}</text><text x="22" y="88" font-family="Archivo" font-weight="800" font-size="${tam}" fill="${IN}">${l1}</text><text x="22" y="116" font-family="Archivo" font-weight="700" font-size="${tam-4}" fill="${borda}">${l2}</text></g>`;
  const seta=(x,p)=>`<g style="clip-path:inset(0 ${(1-p)*100}% 0 0)"><path d="M${x+6+w} ${66+w} L${x+52-w} ${66-w}" stroke="${IN}" stroke-width="8" stroke-linecap="round" stroke-dasharray="12 10" stroke-dashoffset="${-off}" fill="none"/><path d="M${x+34+w} 46 L${x+58} ${66-w} L${x+34-w} 86" stroke="${IN}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" fill="none"/></g>`;
  const pop=(t0)=>cl(mola(t-t0,12,.55),0,1.15);
  // diagrama 1: o protocolo traz remédios, doses e dias (D0 · D1 · D2)
  if(t>=D2[0]-0.05&&t<D2[1]+0.3){desenhado=true;const pe=oc(lin(t,D2[0],D2[0]+0.4)),ps=iq(lin(t,D2[1],D2[1]+0.3));
    X(K.diag,svg(chip(0,pop(a('remedios')-0.3),-1.5,RD,'D0','Antibiótico','1 bisnaga')+seta(262,io(lin(t,a('doses')-0.45,a('doses')-0.15)))+chip(330,pop(a('doses')-0.25),1,Z,'D1','Antibiótico','1 bisnaga')+seta(592,io(lin(t,a('dias')-0.45,a('dias')-0.15)))+chip(660,pop(a('dias')-0.25),-1,V,'D2','Antibiótico +','Anti-inflamatório',25)));
    K.diag.style.display='block';K.diag.style.opacity=1-ps;K.diag.style.transform=`translateY(${(1-pe)*-170+ps*-120}px)`;}
  // diagrama 2: depois de salvar, uma etapa por dia (17/10 · 18/10 · 19/10)
  else if(t>=D4[0]-0.05&&t<D4[1]+0.3){desenhado=true;const pe=oc(lin(t,D4[0],D4[0]+0.4)),ps=iq(lin(t,D4[1]-0.2,D4[1]+0.3));
    X(K.diag,svg(chip(0,pop(D4[0]+0.1),-1.5,RD,'D0','17/10','aplicar')+seta(262,io(lin(t,D4[0]+0.4,D4[0]+0.7)))+chip(330,pop(D4[0]+0.55),1,Z,'D1','18/10','aplicar')+seta(592,io(lin(t,D4[0]+0.85,D4[0]+1.15)))+chip(660,pop(D4[0]+1.0),-1,V,'D2','19/10','aplicar')));
    K.diag.style.display='block';K.diag.style.opacity=1-ps;K.diag.style.transform=`translateY(${(1-pe)*-170+ps*-120}px)`;}
  if(!desenhado)K.diag.style.display='none';
  K.cartao.style.display='none';
  // carimbo de borracha: bate no "lançado" (3 quadros de tremida na cena inteira, ver shake no motor)
  if(t>=tCar&&t<tCarFim){const q=oc(lin(t,tCar,tCar+0.1)),s=lin(t,tCarFim-0.2,tCarFim);
    X(K.carimbo,`<div style="display:flex;align-items:center;justify-content:center;gap:22px;border:10px solid #14452B;outline:3px solid #14452B;outline-offset:7px;border-radius:18px;padding:22px 34px;color:#14452B;font:800 54px/1 Archivo;letter-spacing:.03em;white-space:nowrap;background:rgba(251,246,232,.55);filter:url(#tinta)"><svg width="70" height="70" viewBox="0 0 24 24" fill="none" stroke="#14452B" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5l5 5L20 6.5"/></svg>LANÇADO NO REBANHO</div>`);
    K.carimbo.style.display='block';K.carimbo.style.opacity=(0.93*(1-s)*cl(q*4)).toFixed(3);K.carimbo.style.transform=`translateX(-50%) rotate(-4deg) scale(${L(1.7,1,q)})`;}else K.carimbo.style.display='none';
};
EP.capa=(t,el)=>{const p=io(lin(t,tCapa,tCapa+0.7));if(p<=0){el.style.display='none';return;}el.style.display='block';el.style.clipPath=`inset(${(1-p)*100}% 0 0 0)`;
  const q=mola(t-tCapa-0.45,10,.5),r=mola(t-tCapa-0.95,12,.5),s=oc(lin(t,tCapa+1.7,tCapa+2.3)),u=mola(t-tCapa-2.5,12,.5);
  X(el,`<div class="dymo" style="top:250px;left:80px;transform:rotate(-1.6deg)">PRÓXIMO EPISÓDIO · TEMP. 02</div>
   <div class="abs" data-z="1" style="left:80px;top:420px;font:800 112px/1.04 Archivo;color:#1A2638;letter-spacing:-.02em;text-transform:uppercase"><span style="position:relative;display:inline-block;z-index:0">Alimentação<i style="position:absolute;left:-10px;right:-14px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span><div style="margin-top:22px;font:700 44px/1.1 Archivo;letter-spacing:.02em">Lançamento e sobra de cocho</div></div>
   <div class="abs" data-z="2" style="left:80px;top:850px;width:380px;height:380px;background:#fff;box-shadow:0 26px 50px rgba(50,32,8,.3);display:flex;align-items:center;justify-content:center">${cow(250,'#1A2638',0.9)}</div>
   <div class="abs" data-z="3" style="left:510px;top:870px;width:490px"><div style="font:800 84px/1 Archivo;color:#1A2638;letter-spacing:-.02em">COW<span style="color:#8A5A12">DATA</span></div><div style="margin-top:28px;font:800 46px/1.1 Archivo;color:#1A2638;text-transform:uppercase">O rebanho na mão de <span style="position:relative;display:inline-block;z-index:0">quem cuida<i style="position:absolute;left:-8px;right:-10px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div></div>
   <div class="fita" data-z="4" style="left:90px;top:1330px;font-size:33px;letter-spacing:.04em">Ep. 10 · <b>Protocolo sanitário</b></div>`);
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
EP.sfx.push([D2[0],'rasgo'],[D4[0],'rasgo'],[tCapa,'whoosh'],[tCapa+2.5,'rasgo'],[EP.shake,'carimbo']);
EP.sfx.sort((p,q)=>p[0]-q[0]);
EP.camadas=[[0,['piano','pad']],[a('emLancar'),['piano','pad','shaker']],[a('curativa')-0.2,['piano','pad','baixo','shaker','bumbo_leve']],[a('animal')-0.2,['piano','pad','baixo','shaker','bumbo','palma','piano_cheio']],
 [a('pronto')-0.2,['piano','pad','baixo','shaker','shaker16','bumbo','palma','piano_cheio','sino']],[a('proximo')-0.6,['piano','pad','baixo','shaker','bumbo_leve']],[tCapa,['piano','pad','baixo','shaker','bumbo_leve','sino']]];
return EP;})()
