(()=>{const a=A;const EP={};const SB=30;
// ---- Ep. 11 · Alimentação: consumo e sobra de cocho (Lançar › Outros lançamentos frequentes › Alimentação = FormAlimentacao). Telas = capturas do app real (captura/capturar_t2e11.mjs). ----
// Formulário sem barra fixa (barTop = topo da navegação): a rolagem é contínua dentro de cada captura alta. Os estados lote/num/kg/kg2/volta compartilham a mesma rolagem (SM); consumo e sobra, a SC; ok, a SO. A troca de estado é dissolvida.
const bt=(n,k)=>{const m=MAPA[n];return(m.tall&&m.tall.alvos[k])||m.alvos[k];};
const mx=n=>{const m=MAPA[n];return m.tall?Math.max(0,m.tall.h-69-m.barTop):0;};
const seg=pts=>t=>{if(t<=pts[0][0])return pts[0][1];for(let i=0;i<pts.length-1;i++){const[a0,v0]=pts[i],[a1,v1]=pts[i+1];if(t<a1)return L(v0,v1,io(lin(t,a0,a1)));}return pts[pts.length-1][1];};
const F=TL.frases;
// frases: 0 título · 1 Em Lançar, toque em Alimentação · 2 em Outros lançamentos frequentes · 3 Escolha o lote · 4 Aparecem só os alimentos da dieta ativa · 5 e o que já foi lançado hoje · 6 Em Como informar a quantidade
// · 7 escolha Número de animais · 8 digite quantos comeram · 9 e o app calcula os quilos · 10 Se preferir · 11 toque em Kg direto · 12 e digite o peso de cada um · 13 Toque em Lançar consumo · 14 No fim do dia
// · 15 pese o que sobrou no cocho · 16 e lance o total em Sobra · 17 Relançar substitui, não soma · 18 O app mostra a porcentagem… · 19 Pronto, lançado · 20 próximo episódio
const s=i=>F[i][1],e=i=>F[i][2];
// ---- tempos (tudo ancorado nas palavras da locução) ----
const tAli=e(2)+0.1,cForm=tAli+0.14,tLoteTap=a('lote')-0.15,cLote=tLoteTap+0.6,tNumTap=a('numAnimais')+0.1,tDigTap=a('digite'),cNum=tDigTap+0.7,
 tKgTap=a('kgDireto')+0.1,cKg=tKgTap+0.14,tPeso=a('peso')-0.15,cKg2=tPeso+0.55,tBack=e(12)+0.3,cVolta=tBack+0.14,tLC=a('lancarConsumo')+0.1,cCons=tLC+0.5,
 tSobraTap=a('sobra')-0.35,cSobra=a('sobra')+0.3,tLS=e(17)+0.15,cOk=tLS+0.5,up1=s(18)-0.7,tCar=a('lancado'),tCapa=a('proximo')-0.15;
EP.imgs={lancar:'a01_lancar',form:'a02_form',lote:'a03_lote',num:'a04_num',kg:'a05_kg',kg2:'a06_kg1380',volta:'a07_volta',consumo:'a08_consumo',sobra:'a09_sobra',ok:'a10_sobra_ok'};
const DF=0.18;
// [t, tela, direção (1 = desliza da direita), 1 = só troca de estado (as anotações continuam), dissolvência em s]
EP.telas=[[0,'lancar',0],[cForm,'form',1],[cLote,'lote',0,1,DF],[cNum,'num',0,1,0.1],[cKg,'kg',0,1,0.1],[cKg2,'kg2',0,1,0.1],[cVolta,'volta',0,1,0.12],[cCons,'consumo',0,1,DF],[cSobra,'sobra',0,1,0.1],[cOk,'ok',0,1,DF]];
// ---- rolagem (px CSS do app) ----
// lote…volta: 0 → 250 (dieta e "Já lançado hoje" à vista) → 340 (o Lançar consumo à vista) · consumo/sobra: 458 (o botão no mesmo lugar do estado anterior) → 300 (o cartão atualizado) → 560 (o aviso) → 753 (a sobra, máximo) · ok: 783 → 840 (o aviso) → 330 (a % de sobra)
const SM=seg([[0,0],[s(4)-0.1,0],[s(4)+0.7,250],[tBack+0.1,250],[tBack+0.9,340]]);
const SC=seg([[0,458],[cCons+0.15,458],[cCons+0.95,300],[cCons+1.5,300],[cCons+2.2,560],[s(15)-0.1,560],[s(15)+0.9,753]]);
const SO=seg([[0,783],[cOk+0.35,840],[up1,840],[up1+0.9,330]]);
EP.rolagem={lote:SM,num:SM,kg:SM,kg2:SM,volta:SM,consumo:SC,sobra:SC,ok:SO};
const S=(id,t)=>cl(EP.rolagem[id]?EP.rolagem[id](t):0,0,mx(EP.imgs[id]));
const cx=b=>b.x+b.w/2,cy=b=>b.y+b.h/2;
// ---- toques: [t, x, y] em coordenadas da tela do celular (CSS) já com a barra de status (+30) ----
const B=bt;
const bAli=B('a01_lancar','alimentacao'),bLote=B('a02_form','loteSel'),bModoAn=B('a03_lote','modoAn'),bNum=B('a03_lote','numIn'),bModoKg=B('a04_num','modoKg'),bSilIn=B('a05_kg','silIn'),bModoAn2=B('a06_kg1380','modoAn'),
 bLC=B('a07_volta','lancarCons'),bSobIn=B('a08_consumo','sobraIn'),bLS=B('a09_sobra','lancarSobra');
EP.toques=[
 [tAli,cx(bAli),cy(bAli)+SB],[tLoteTap,cx(bLote),cy(bLote)+SB],[tNumTap,cx(bModoAn),cy(bModoAn)-S('lote',tNumTap)+SB],[tDigTap,cx(bNum),cy(bNum)-S('lote',tDigTap)+SB],
 [tKgTap,cx(bModoKg),cy(bModoKg)-S('num',tKgTap)+SB],[tPeso,cx(bSilIn),cy(bSilIn)-S('kg',tPeso)+SB],[tBack,cx(bModoAn2),cy(bModoAn2)-S('kg2',tBack)+SB],
 [tLC,cx(bLC),cy(bLC)-S('volta',tLC)+SB],[tSobraTap,cx(bSobIn),cy(bSobIn)-S('consumo',tSobraTap)+SB],[tLS,cx(bLS),cy(bLS)-S('sobra',tLS)+SB]];
// ---- câmera: [t de chegada, duração, cx, cy, zoom] (coords da tela do celular com +30). Visível: de cy-189/z a cy+349/z. Zoom ≤ 1,18 e centrado ----
EP.cam=[[0,0,195,300,1.0],[a('emLancar')+0.4,1.0,195,440,1.1],[cForm+0.6,0.8,195,330,1.0],[s(4)-0.1,0.9,195,470,1.0],[a('jaLancado')-0.2,0.7,195,350,1.0],[a('comoInformar')-0.1,0.8,195,470,1.0],
 [cCons+0.95,0.8,195,310,1.0],[cCons+2.2,0.7,195,470,1.0],[s(18)+0.1,0.9,195,310,1.0]];
// ---- anotações: [t0,t1,tipo,x,y,w,h,{c,scr}] — as de tela com troca de tela somem no quadro da troca; as demais têm fim explícito ----
const V='#2E7D52',Z='#1E6FA8',D='#E0A63C',IN='#1A2638',RD='#B3392F';
const bx=(n,k,o={},dx=0,dy=0,dw=0,dh=0)=>{const b=bt(n,k);return[b.x+dx,b.y+dy,b.w+dw,b.h+dh,o];};
const lin1=bt('a10_sobra_ok','sobraHoje');
EP.anot=[
 [a('alimentacao')-0.2,a('outros')-0.3,'caixa',...bx('a01_lancar','alimentacao',{c:V})],
 [a('outros')-0.25,tAli+0.1,'caixa',...bx('a01_lancar','outros',{c:Z})],
 [a('alimentos')-0.2,a('jaLancado')-0.55,'caixa',36,732.2,321,273.6,{c:V,scr:'lote'}],
 [a('jaLancado')-0.2,a('comoInformar')-0.35,'caixa',...bx('a03_lote','jaSec',{c:Z,scr:'lote'},0,-2,0,68)],
 [a('comoInformar')-0.2,a('numAnimais')-0.3,'caixa',...bx('a03_lote','como',{c:V,scr:'lote'})],
 [a('numAnimais')-0.25,tNumTap+0.2,'caixa',...bx('a03_lote','modoAn',{c:Z,scr:'lote'})],
 [tDigTap-0.35,a('calcula')-0.3,'caixa',...bx('a03_lote','numIn',{c:D,scr:'lote'})],
 [a('calcula')-0.1,a('cadaAlimento')+0.5,'caixa',282,740,84,268,{c:D,scr:'num'}],
 [a('kgDireto')-0.25,tKgTap+0.12,'caixa',...bx('a04_num','modoKg',{c:D,scr:'num'})],
 [a('peso')-0.45,tBack-0.2,'caixa',247,640,118,312,{c:Z,scr:'kg'}],
 [tBack-0.3,tBack+0.15,'caixa',...bx('a06_kg1380','modoAn',{c:V,scr:'kg2'})],
 [a('lancarConsumo')-0.25,tLC+0.1,'caixa',...bx('a07_volta','lancarCons',{c:D,scr:'volta'})],
 [cCons+0.9,cCons+1.5,'caixa',...bx('a08_consumo','jaCard',{c:V,scr:'consumo'})],
 [cCons+2.2,s(15),'caixa',...bx('a08_consumo','avisoCons',{c:V,scr:'consumo'})],
 [a('sobra')-0.55,cSobra+0.1,'caixa',...bx('a08_consumo','sobra',{c:D,scr:'consumo'})],
 [a('relancar')-0.05,tLS+0.05,'caixa',...bx('a09_sobra','nota',{c:Z,scr:'sobra'},-4,-2,8,4)],
 [cOk+0.3,up1-0.05,'caixa',...bx('a10_sobra_ok','avisoSobra',{c:V,scr:'ok'})],
 [a('porcentagem')-0.1,a('dentro')-0.2,'caixa',lin1.x-2,lin1.y-1,138,lin1.h+2,{c:D,scr:'ok'}],
 [a('dentro')-0.15,tCar-0.15,'caixa',lin1.x+150,lin1.y-1,108,lin1.h+2,{c:V,scr:'ok'}]
];
EP.fitas=[[a('fita1')-0.1,a('emLancar')+0.1,'<b>Alimentação</b>',110,298,-2],
 [a('substitui')-0.3,e(17)+0.1,'Substitui, <b>não soma</b>',100,298,-1.5]];
const D1=[a('calcula')-0.3,s(10)-0.05],D2=[a('porcentagem')-0.15,a('dentro')-0.25];
EP.titulos=[[0,'Temporada 2 · <m>Ep. 11</m>'],[a('emLancar')-0.1,'Em Lançar: <m>Alimentação</m>'],[a('outros')-0.2,'Outros <m>lançamentos</m>'],[a('lote')-0.15,'Escolha o <m>lote</m>'],[a('alimentos')-0.15,'Alimentos da <m>dieta</m>'],
 [a('jaLancado')-0.2,'Já lançado <m>hoje</m>'],[a('comoInformar')-0.2,'Como informar a <m>quantidade</m>'],[a('numAnimais')-0.15,'Nº de <m>animais</m>'],[a('digite')-0.15,'Digite <m>quantos</m> comeram'],
 [D1[1]+0.05,'Ou <m>Kg direto</m>'],[a('peso')-0.25,'Digite o <m>peso</m>'],[e(12)+0.1,'Toque em <m>Lançar consumo</m>'],[a('fimDia')-0.15,'No fim do dia: <m>sobra</m>'],[a('sobrou')-0.15,'Pese a <m>sobra</m> do cocho'],
 [a('sobra')-0.4,'Lance o <m>total</m> em kg'],[a('relancar')-0.1,'Relançar <m>substitui</m>'],[e(17)+0.1,'Toque em <m>Lançar sobra</m>'],[cOk+0.2,'Sobra <m>lançada</m>'],[D2[1]+0.05,'Dentro da <m>faixa</m>']];
EP.titulos.sort((p,q)=>p[0]-q[0]);
EP.diag=[0,0];
const L2=i=>[F[i][1],F[i][2],F[i][0]];
EP.leg=[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20].map(L2);
EP.fimLeg=tCapa;EP.shake=a('lancado');
EP.entrada=t=>{const p=mola(t-0.3,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
EP.oculta=[[tCar,tCapa+0.8],[D1[0],D1[1]+0.36],[D2[0],D2[1]+0.36],[a('fita1')-0.1,a('emLancar')+0.4],[a('substitui')-0.3,e(17)+0.1+0.36]];
EP.estado=(t,{K,io,oc,lin,mola,L,cl,ob,ic,cow,X,iq})=>{
  K.dymo.style.transform=`translateX(${(1-cl(mola(t-0.55,9,.55),0,1.15))*-1000}px) rotate(-1.6deg)`;
  const g=cl(mola(t-0.15,10,.5),0,1.2);K.grampo.style.transform=`translateY(${(1-g)*-230}px) rotate(${(1-cl(g,0,1))*6}deg)`;
  const w=(Math.floor(t*12)%3)-1;let desenhado=false;
  const svg=h=>`<svg width="920" height="140" viewBox="0 0 920 140" style="overflow:visible">${h}</svg>`;
  const mostra=(pe,ps)=>{K.diag.style.display='block';K.diag.style.opacity=1-ps;K.diag.style.transform=`translateY(${(1-pe)*-170+ps*-120}px)`;};
  // diagrama 1: 40 animais × 35 kg = 1.400 kg, com seta tracejada (12 qps) até o valor da silagem na tela (posição vinda da câmera e da rolagem no mesmo instante)
  if(t>=D1[0]-0.05&&t<D1[1]+0.3){desenhado=true;const pe=oc(lin(t,D1[0],D1[0]+0.4)),ps=iq(lin(t,D1[1],D1[1]+0.3));
    const a1=oc(lin(t,D1[0]+0.1,D1[0]+0.5)),a2=cl(mola(t-(a('quilos')-0.1),12,.55),0,1.15),ul=io(lin(t,a('quilos')+0.2,a('quilos')+0.7));
    const[cxm,cym,zz]=camera(t);const b=bt('a04_num','silVal');const scr=S('num',t);
    const ex=540+((b.x+b.w/2)-cxm)*U*zz-80,ey=FY+((b.y-scr+SB)-cym)*U*zz-286-34;
    const pa=io(lin(t,a('cadaAlimento')-0.45,a('cadaAlimento')+0.45));
    let sv=`<g opacity="${a1}" transform="translate(${(1-a1)*-40} 0)"><text x="6" y="58" font-family="Archivo" font-weight="800" font-size="47" fill="${IN}">40 animais × 35 kg<tspan fill="#2E7D52" fill-opacity="${cl(a2)}"> = 1.400 kg</tspan></text></g>`;
    sv+=`<path d="M6 ${74+w} L${L(6,770,ul)} ${72-w}" stroke="#1E6FA8" stroke-width="8" stroke-linecap="round" fill="none"/>`;
    sv+=`<g opacity="${a1}"><text x="6" y="118" font-family="Inter,Archivo" font-weight="600" font-size="30" fill="#4b4034">(animais × kg por cabeça, no dia)</text></g>`;
    if(pa>0){const ox=800,oy=96,off=(Math.floor(t*12)%6)*4;sv+=`<g style="clip-path:inset(0 0 ${(1-pa)*100}% 0)"><path d="M${ox} ${oy+w} C${ox+170} ${oy+60}, ${ex+150} ${ey-420}, ${ex+8} ${ey-6}" stroke="${IN}" stroke-width="8" stroke-linecap="round" stroke-dasharray="12 10" stroke-dashoffset="${-off}" fill="none"/><path d="M${ex-22+w} ${ey-30} L${ex+8} ${ey+4} L${ex+30-w} ${ey-24}" stroke="${IN}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" fill="none"/></g>`;}
    X(K.diag,svg(sv));mostra(pe,ps);}
  // diagrama 2: a conta da sobra, 52 kg ÷ 1.850 kg = 2,8 %
  else if(t>=D2[0]-0.05&&t<D2[1]+0.3){desenhado=true;const pe=oc(lin(t,D2[0],D2[0]+0.4)),ps=iq(lin(t,D2[1],D2[1]+0.3));
    const a1=oc(lin(t,D2[0]+0.1,D2[0]+0.5)),a2=cl(mola(t-(D2[0]+0.9),12,.55),0,1.15);
    let sv=`<g opacity="${a1}" transform="translate(${(1-a1)*-40} 0)"><text x="6" y="58" font-family="Archivo" font-weight="800" font-size="52" fill="${IN}">52 kg ÷ 1.850 kg<tspan fill="#2E7D52" fill-opacity="${cl(a2)}"> = 2,8 %</tspan></text></g>`;
    sv+=`<g opacity="${a1}"><text x="6" y="116" font-family="Inter,Archivo" font-weight="600" font-size="30" fill="#4b4034">(sobra ÷ total fornecido)</text></g>`;
    X(K.diag,svg(sv));mostra(pe,ps);}
  if(!desenhado)K.diag.style.display='none';
  K.cartao.style.display='none';
  // carimbo de borracha: bate no "lançado" (3 quadros de tremida na cena inteira, ver shake no motor)
  if(t>=tCar&&t<tCapa+0.8){const q=oc(lin(t,tCar,tCar+0.1)),s=lin(t,tCapa+0.35,tCapa+0.75);
    X(K.carimbo,`<div style="display:flex;align-items:center;justify-content:center;gap:22px;border:10px solid #14452B;outline:3px solid #14452B;outline-offset:7px;border-radius:18px;padding:22px 34px;color:#14452B;font:800 54px/1 Archivo;letter-spacing:.03em;white-space:nowrap;background:rgba(251,246,232,.55);filter:url(#tinta)"><svg width="70" height="70" viewBox="0 0 24 24" fill="none" stroke="#14452B" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5l5 5L20 6.5"/></svg>LANÇADO NO REBANHO</div>`);
    K.carimbo.style.display='block';K.carimbo.style.opacity=(0.93*(1-s)*cl(q*4)).toFixed(3);K.carimbo.style.transform=`translateX(-50%) rotate(-4deg) scale(${L(1.7,1,q)})`;}else K.carimbo.style.display='none';
};
EP.capa=(t,el)=>{const p=io(lin(t,tCapa,tCapa+0.7));if(p<=0){el.style.display='none';return;}el.style.display='block';el.style.clipPath=`inset(${(1-p)*100}% 0 0 0)`;
  const q=mola(t-tCapa-0.45,10,.5),r=mola(t-tCapa-0.95,12,.5),s=oc(lin(t,tCapa+1.7,tCapa+2.3)),u=mola(t-tCapa-2.5,12,.5);
  X(el,`<div class="dymo" style="top:250px;left:80px;transform:rotate(-1.6deg)">PRÓXIMO EPISÓDIO · TEMP. 02</div>
   <div class="abs" data-z="1" style="left:80px;top:420px;font:800 112px/1.04 Archivo;color:#1A2638;letter-spacing:-.02em;text-transform:uppercase"><span style="position:relative;display:inline-block;z-index:0">Protocolos<i style="position:absolute;left:-10px;right:-14px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span><div style="margin-top:22px;font:700 44px/1.1 Archivo;letter-spacing:.02em">Lançamento de protocolos</div></div>
   <div class="abs" data-z="2" style="left:80px;top:850px;width:380px;height:380px;background:#fff;box-shadow:0 26px 50px rgba(50,32,8,.3);display:flex;align-items:center;justify-content:center">${cow(250,'#1A2638',0.9)}</div>
   <div class="abs" data-z="3" style="left:510px;top:870px;width:490px"><div style="font:800 84px/1 Archivo;color:#1A2638;letter-spacing:-.02em">COW<span style="color:#8A5A12">DATA</span></div><div style="margin-top:28px;font:800 46px/1.1 Archivo;color:#1A2638;text-transform:uppercase">O rebanho na mão de <span style="position:relative;display:inline-block;z-index:0">quem cuida<i style="position:absolute;left:-8px;right:-10px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div></div>
   <div class="fita" data-z="4" style="left:90px;top:1330px;font-size:33px;letter-spacing:.04em">Ep. 11 · <b>Alimentação</b></div>`);
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
EP.sfx.push([D1[0],'rasgo'],[D2[0],'rasgo'],[tCapa,'whoosh'],[tCapa+2.5,'rasgo'],[EP.shake,'carimbo']);
EP.sfx.sort((p,q)=>p[0]-q[0]);
EP.camadas=[[0,['piano','pad']],[a('emLancar'),['piano','pad','shaker']],[a('lote')-0.3,['piano','pad','baixo','shaker','bumbo_leve']],[a('comoInformar')-0.2,['piano','pad','baixo','shaker','bumbo','palma','piano_cheio']],
 [a('pronto')-0.2,['piano','pad','baixo','shaker','shaker16','bumbo','palma','piano_cheio','sino']],[a('proximo')-0.6,['piano','pad','baixo','shaker','bumbo_leve']],[tCapa,['piano','pad','baixo','shaker','bumbo_leve','sino']]];
return EP;})()
