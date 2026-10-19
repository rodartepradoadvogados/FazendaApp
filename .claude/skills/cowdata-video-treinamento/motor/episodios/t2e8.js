(()=>{const a=A;const EP={};const SB=30;
// ---- Ep. 8 · Produção › BST (PainelLancarBst). Telas = capturas do app real (captura/capturar_t2e8.mjs). ----
// bt = caixa no conteúdo (coord. da página rolada a 0 nas capturas altas). A tabela de Aptas é LARGA (moldura com rolagem de lado, DEL projetado = 4ª coluna): as anotações
// de coluna recebem hx (EP.hscroll). A barra de ação (.gv-barra, sticky) fica no fim da captura alta e começa na mesma posição (1471,5) em todos os estados;
// cada estado tem a PRÓPRIA função de rolagem (a barra muda de altura e o máximo de cada estado é diferente: a troca de estado é dissolvida, como no Ep. 7).
const bt=(n,k)=>{const m=MAPA[n];return(m.tall&&m.tall.alvos[k])||m.alvos[k];};
const mx=n=>{const m=MAPA[n];return m.tall?Math.max(0,m.tall.h-69-m.barTop):0;};
const seg=pts=>t=>{if(t<=pts[0][0])return pts[0][1];for(let i=0;i<pts.length-1;i++){const[a0,v0]=pts[i],[a1,v1]=pts[i+1];if(t<a1)return L(v0,v1,io(lin(t,a0,a1)));}return pts[pts.length-1][1];};
const F=TL.frases;
// frases: 0 título · 1 F2 · 2 "No topo…" · 3 "e separa…três grupos" · 4 "Em Aptas, toque em Marcar todas" · 5 "O DEL projetado…" · 6 "Confira o produto e a dose:" · 7 "o app mostra…estoque"
// · 8 "Toque em Aplicar BST, e confirme" · 9 "Vaca que não deve receber?" · 10 "Marque," · 11 "e toque em Marcar inapta:" · 12 "ela sai da lista," · 13 "sem mexer no estoque." · 14 "Pronto, lançado." · 15 próximo
const s=i=>F[i][1],e=i=>F[i][2];
// ---- tempos (tudo ancorado nas palavras da locução) ----
const tProd=a('producao')+0.1,tBst=a('bst')+0.1;
const tTodas=a('marcarTodas')+0.1;
const hs0=e(4)+0.2,hs1=s(5)-0.15,hs2=e(5)+0.35;                                   // arrasta a tabela até DEL projetado, segura e volta a 0
const tUn=e(5)+1.15;                                                               // desmarca a 1ª vaca (1502)
const tDose=a('dose')+0.05;
const tApl=a('aplicar')+0.05,tConf1=a('confirme')+0.15;
const tTk=a('marque')+0.1;
const tIna=a('marcarInapta')+0.25,tConf2=a('saiLista')+0.1;
const cT={prod:tProd+0.1,bst:tBst+0.12,td:tTodas+0.12,un:tUn+0.12,dose:tDose+0.4,conf:tApl+0.15,ret:tConf1+0.12,tk:tTk+0.12,ci:tIna+0.12,in:tConf2+0.12};
const tCapa=a('proximo')-0.15;
EP.imgs={lancar:'s01_lancar',grade:'s02_prod_grade',b03:'b03_bst',b04:'b04_todas',b05:'b05_desmarca',b06:'b06_dose',b07:'b07_confirma',b08:'b08_aplicado',b09:'b09_marca1',b10:'b10_conf_inapta',b11:'b11_inapta'};
// [t, id, dir, 1 = troca só de estado (as anotações continuam), dissolvência em s]
EP.telas=[[0,'lancar',0],[cT.prod,'grade',1],[cT.bst,'b03',1],[cT.td,'b04',0,1],[cT.un,'b05',0,1],[cT.dose,'b06',0,1],[cT.conf,'b07',0,1,0.18],[cT.ret,'b08',0,1,0.18],[cT.tk,'b09',0,1],
 [cT.ci,'b10',0,1,0.18],[cT.in,'b11',0,1,0.18]];
// ---- rolagem vertical (px CSS do app; cada estado limita ao próprio máximo) ----
EP.rolagem={b03:seg([[0,0],[e(3)+0.25,0],[s(4)+0.4,600]]),b04:()=>600,
 b05:seg([[0,600],[tUn+0.4,600],[tUn+1.4,1510]]),b06:()=>1510,b07:()=>951,
 b08:seg([[cT.ret,1151],[e(8)+0.5,1151],[s(9)+0.7,800]]),b09:seg([[cT.tk,800],[s(11)-1.0,800],[s(11)-0.15,1189]]),b10:()=>884,b11:()=>884};
// ---- rolagem de lado da moldura da tabela (px CSS da tabela; cada estado limita ao próprio S) ----
const hsA=seg([[0,0],[hs0,0],[hs1,437],[hs2,437],[hs2+0.6,0]]);                      // 437 = fim da rolagem: DEL projetado, DEL atual e Situação inteiros à vista
EP.hscroll={b04:hsA,b05:hsA};
const S=(id,t)=>cl(EP.rolagem[id](t),0,mx(EP.imgs[id]));
const H=(id,t)=>{const f=EP.hscroll[id];return f?cl(f(t),0,MAPA[EP.imgs[id]].hz.S):0;};
const cx=b=>b.x+b.w/2,cy=b=>b.y+b.h/2;
// ---- toques: [t, x, y] em coordenadas da tela do celular (CSS) já com a barra de status (+30) ----
const bProd=bt('s01_lancar','prod'),bBst=bt('s02_prod_grade','bst'),bTodas=bt('b03_bst','marcarTodas'),bR1=bt('b04_todas','r1c'),bDose=bt('b05_desmarca','dose'),
 bApl=bt('b06_dose','aplicar'),bOk1=bt('b07_confirma','confOk'),bR1b=bt('b08_aplicado','r1c'),bIna=bt('b09_marca1','inapta'),bOk2=bt('b10_conf_inapta','confOk');
EP.toques=[
 [tProd,cx(bProd),cy(bProd)+SB],[tBst,cx(bBst),cy(bBst)+SB],
 [tTodas,cx(bTodas)-H('b03',tTodas),cy(bTodas)-S('b03',tTodas)+SB],
 [tUn,cx(bR1)-H('b04',tUn),cy(bR1)-S('b04',tUn)+SB],
 [tDose,cx(bDose),cy(bDose)-S('b05',tDose)+SB],
 [tApl,cx(bApl),cy(bApl)-S('b06',tApl)+SB],[tConf1,cx(bOk1),cy(bOk1)-S('b07',tConf1)+SB],
 [tTk,cx(bR1b),cy(bR1b)-S('b08',tTk)+SB],
 [tIna,cx(bIna),cy(bIna)-S('b09',tIna)+SB],[tConf2,cx(bOk2),cy(bOk2)-S('b10',tConf2)+SB]];
// ---- câmera: [t de chegada, duração, cx, cy, zoom] (coords da tela do celular com +30). Visível: de cy-189/z a cy+349/z. Zoom ≤ 1,18 e centrado ----
EP.cam=[[0,0,195,300,1.0],[a('emLancar')+0.3,1.0,195,380,1.12],[tProd+0.45,0.9,195,360,1.1],
 [cT.bst+0.3,0.9,195,520,1.0],                                // topo: Próxima aplicação e os três grupos
 [s(4)+0.4,1.4,195,330,1.0],                                  // tabela de Aptas (S=600): contagem, Marcar todas e as primeiras linhas
 [tUn+0.4,0.9,195,300,1.0],                                   // barra de ação (S=1510): produto, dose e previsão
 [e(7)+0.2,0.7,195,480,1.0],                                  // previsão + Aplicar BST
 [e(8)+0.4,0.9,195,380,1.0],                                  // volta à tabela (S=800)
 [s(11)-0.95,0.8,195,480,1.0]];                               // barra: Marcar inapta e a confirmação
// ---- anotações: [t0,t1,tipo,x,y,w,h,{c,scr,hx}] ----
const V='#2E7D52',Z='#1E6FA8',D='#E0A63C',IN='#1A2638',RD='#B3392F',AM='#C27B14';
const bx=(n,k,o={})=>{const b=bt(n,k);return[b.x,b.y,b.w,b.h,o];};
const colDp=o=>{const h=bt('b04_todas','thDp'),f=bt('b04_todas','frame');return[h.x,h.y,h.w,f.y+f.h-h.y-2,o];};      // coluna DEL projetado (cabeçalho + linhas visíveis da moldura)
EP.anot=[
 [a('toqueProd')+0.1,tProd+0.1,'caixa',...bx('s01_lancar','prod',{c:V})],
 [a('bst')-0.5,tBst+0.1,'caixa',...bx('s02_prod_grade','bst',{c:V})],
 [a('proximaAplic')-0.3,s(3)-0.1,'caixa',...bx('b03_bst','proxData',{c:D,scr:'b03'})],
 [a('aptas')-0.1,a('incluir')-0.05,'caixa',...bx('b03_bst','segA',{c:V,scr:'b03'})],
 [a('incluir')-0.05,a('inaptas')-0.1,'caixa',...bx('b03_bst','segI',{c:AM,scr:'b03'})],
 [a('inaptas')-0.1,e(3),'caixa',...bx('b03_bst','segN',{c:RD,scr:'b03'})],
 [a('toqueMarcar')-0.1,tTodas+0.05,'caixa',...bx('b03_bst','marcarTodas',{c:D,scr:'b03'})],
 [cT.td+0.15,e(4)+0.3,'caixa',...bx('b04_todas','cont',{c:V,scr:'b04'})],
 [a('delProj')-0.1,e(5)+0.05,'caixa',...colDp({c:D,scr:'b04',hx:'b04'})],
 [tUn-0.5,tUn+0.05,'caixa',...bx('b04_todas','r1c',{c:RD,scr:'b04'})],
 [a('produto')-0.1,a('dose')-0.15,'caixa',...bx('b06_dose','produto',{c:V,scr:'b06'})],
 [a('dose')-0.15,cT.dose+0.55,'caixa',...bx('b06_dose','dose',{c:D,scr:'b06'})],
 [a('comoFica')-0.1,tApl-0.3,'caixa',...bx('b06_dose','resumoLinha',{c:D,scr:'b06'})],
 [a('aplicar')-0.2,tApl+0.05,'caixa',...bx('b06_dose','aplicar',{c:D,scr:'b06'})],
 [tApl+0.35,tConf1+0.05,'caixa',...bx('b07_confirma','confOk',{c:D,scr:'b07'})],
 [cT.ret+0.3,e(8)+0.3,'caixa',...bx('b08_aplicado','ret',{c:V,scr:'b08'})],
 [a('marque')-0.25,tTk+0.05,'caixa',...bx('b08_aplicado','r1c',{c:RD,scr:'b09'})],
 [a('marcarInapta')-0.15,tIna+0.05,'caixa',...bx('b09_marca1','inapta',{c:RD,scr:'b09'})],
 [tIna+0.35,tConf2+0.05,'caixa',...bx('b10_conf_inapta','confOk',{c:RD,scr:'b10'})],
 [cT.in+0.3,e(13)+0.3,'caixa',...bx('b11_inapta','retTxt',{c:V,scr:'b11'})]
];
EP.fitas=[[a('fita1')-0.1,a('emLancar')+0.1,'Produção · <b>BST</b>',110,298,-2],
 [s(13)-0.05,e(13)+0.5,'Sem mexer <b>no estoque</b>',110,298,-1.5]];
EP.titulos=[[0,'Temporada 2 · <m>Ep. 8</m>'],[a('emLancar')-0.1,'Em Lançar: <m>Produção</m>'],[a('leite')-0.2,'Depois, <m>BST</m>'],
 [a('topo')-0.1,'No topo: <m>próxima aplicação</m>'],[e(3)+0.05,'Os três <m>grupos</m>'],[s(4)-0.1,'Em <m>Aptas</m>: marcar todas'],[e(5)+0.15,'Desmarque quem <m>não recebe</m>'],[s(6)-0.1,'Confira <m>produto</m> e <m>dose</m>'],
 [a('comoFica')-0.1,'Como fica o <m>estoque</m>'],[a('aplicar')-0.1,'<m>Aplicar BST</m> e confirme'],[a('naoDeve')-0.1,'Vaca que <m>não deve</m> receber?'],
 [a('marque')-0.1,'Marque e toque em <m>Marcar inapta</m>'],[a('pronto')-0.1,'Feito: <m>lançado</m>']];
// diagramas Vox no papel: (A) os três grupos acendendo com as contagens reais; (B) DEL projetado = DEL no dia da aplicação
EP.diag=[a('aptas')-0.45,e(3)+0.05];
const DB=[a('delProj')-0.3,e(5)+0.1];
const tCar=a('lancado'),tCarFim=a('proximo')-0.45;
const L2=i=>[F[i][1],F[i][2],F[i][0]];
EP.leg=[L2(0),[F[1][1],a('leite')+0.5,'Em Lançar, toque em Produção, Leite,'],[a('leite')+0.5,F[1][2],'e depois em BST.'],L2(2),L2(3),L2(4),L2(5),L2(6),L2(7),L2(8),L2(9),
 [F[10][1],F[11][2],'Marque, e toque em Marcar inapta:'],[F[12][1],F[13][2],'ela sai da lista, sem mexer no estoque.'],L2(14),L2(15)];
EP.fimLeg=tCapa;EP.shake=a('lancado');
EP.entrada=t=>{const p=mola(t-0.3,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
EP.oculta=[[tCar,tCarFim],[EP.diag[1],EP.diag[1]+0.36],[DB[0],DB[1]+0.36],[a('fita1')-0.1,a('emLancar')+0.4],[s(13)-0.05,e(13)+0.8]];
EP.estado=(t,{K,io,oc,lin,mola,L,cl,ob,ic,cow,X,iq})=>{
  K.dymo.style.transform=`translateX(${(1-cl(mola(t-0.55,9,.55),0,1.15))*-1000}px) rotate(-1.6deg)`;
  const g=cl(mola(t-0.15,10,.5),0,1.2);K.grampo.style.transform=`translateY(${(1-g)*-230}px) rotate(${(1-cl(g,0,1))*6}deg)`;
  const D0=EP.diag[0],D1=EP.diag[1];let desenhado=false;
  const svg=h=>`<svg width="920" height="140" viewBox="0 0 920 140" style="overflow:visible">${h}</svg>`;
  const check=(x,y,c)=>c>0?`<g transform="translate(${x} ${y}) scale(${c})"><path d="M-26 2 L-8 22 L28 -24" stroke="#2E7D52" stroke-width="12" stroke-linecap="round" stroke-linejoin="round" fill="none"/></g>`:'';
  // diagrama A: três grupos com as contagens reais, cada um acende na palavra
  if(t>=D0-0.05&&t<D1+0.3){desenhado=true;const pe=oc(lin(t,D0,D0+0.45)),ps=iq(lin(t,D1,D1+0.3));const w=(Math.floor(t*12)%3)-1;let sv='';
    const it=[[0,'18','Aptas','#2E7D52',a('aptas')],[300,'4','Incluir','#C27B14',a('incluir')],[620,'6','Inaptas','#B3392F',a('inaptas')]];
    for(const[x,n,lb,c,ta]of it){const o=oc(lin(t,ta-0.15,ta+0.3));if(o<=0)continue;const dw=n.length*56+16;
      sv+=`<g opacity="${o}" transform="translate(${(1-o)*-30} 0)"><text x="${x}" y="84" font-family="Archivo" font-weight="800" font-size="86" fill="${c}">${n}</text><text x="${x+dw+12}" y="82" font-family="Archivo" font-weight="800" font-size="46" fill="${IN}">${lb}</text>`
        +`<path d="M${x} ${106+w} L${L(x,x+dw+12+lb.length*27,io(lin(t,ta,ta+0.4)))} ${104-w}" stroke="${c}" stroke-width="9" stroke-linecap="round" fill="none" opacity=".85"/></g>`;}
    X(K.diag,svg(sv));K.diag.style.display='block';K.diag.style.opacity=1-ps;K.diag.style.transform=`translateY(${(1-pe)*-170+ps*-120}px)`;}
  // diagrama B: DEL projetado = DEL no dia da aplicação
  else if(t>=DB[0]-0.05&&t<DB[1]+0.3){desenhado=true;const pe=oc(lin(t,DB[0],DB[0]+0.4)),ps=iq(lin(t,DB[1],DB[1]+0.3));const w=(Math.floor(t*12)%3)-1;
    const a1=oc(lin(t,DB[0]+0.05,DB[0]+0.45)),a2=oc(lin(t,a('diaAplic')-0.7,a('diaAplic')-0.3)),ul=io(lin(t,a('delProj')+0.3,a('delProj')+0.9)),ck=cl(mola(t-a('diaAplic')-1.0,13,.5),0,1.2);
    let sv=`<g opacity="${a1}" transform="translate(${(1-a1)*-40} 0)"><text x="10" y="58" font-family="Archivo" font-weight="800" font-size="62" fill="${IN}">DEL projetado</text>`
      +(ul>0?`<path d="M10 ${72+w} L${L(10,470,ul)} ${70-w}" stroke="#E0A63C" stroke-width="9" stroke-linecap="round" fill="none" opacity=".9"/>`:'')+`</g>`
      +`<g opacity="${a2}" transform="translate(${(1-a2)*-40} 0)"><text x="10" y="122" font-family="Archivo" font-weight="800" font-size="50" fill="#4b4034">= DEL no dia da aplicação</text></g>`+check(880,86,ck);
    X(K.diag,svg(sv));K.diag.style.display='block';K.diag.style.opacity=1-ps;K.diag.style.transform=`translateY(${(1-pe)*-170+ps*-120}px)`;}
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
   <div class="abs" data-z="1" style="left:80px;top:350px;font:800 150px/1 Archivo;color:#1A2638;letter-spacing:-.02em;text-transform:uppercase"><span style="position:relative;display:inline-block;z-index:0">Sanidade<i style="position:absolute;left:-10px;right:-14px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span><div style="margin-top:22px;font:800 52px/1.1 Archivo;letter-spacing:0">Aplicação de medicamentos</div></div>
   <div class="abs" data-z="2" style="left:80px;top:870px;width:380px;height:380px;background:#fff;box-shadow:0 26px 50px rgba(50,32,8,.3);display:flex;align-items:center;justify-content:center">${cow(250,'#1A2638',0.9)}</div>
   <div class="abs" data-z="3" style="left:510px;top:890px;width:490px"><div style="font:800 84px/1 Archivo;color:#1A2638;letter-spacing:-.02em">COW<span style="color:#8A5A12">DATA</span></div><div style="margin-top:28px;font:800 46px/1.1 Archivo;color:#1A2638;text-transform:uppercase">O rebanho na mão de <span style="position:relative;display:inline-block;z-index:0">quem cuida<i style="position:absolute;left:-8px;right:-10px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div></div>
   <div class="fita" data-z="4" style="left:90px;top:1350px">Ep. 8 · <b>BST</b></div>`);
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
EP.sfx.push([EP.diag[0],'rasgo'],[DB[0],'rasgo'],[tCapa,'whoosh'],[tCapa+2.5,'rasgo'],[EP.shake,'carimbo']);
EP.sfx.sort((p,q)=>p[0]-q[0]);
EP.camadas=[[0,['piano','pad']],[a('emLancar'),['piano','pad','shaker']],[a('topo'),['piano','pad','baixo','shaker','bumbo_leve']],[a('toqueMarcar'),['piano','pad','baixo','shaker','bumbo','palma','piano_cheio']],
 [a('pronto')-0.2,['piano','pad','baixo','shaker','shaker16','bumbo','palma','piano_cheio','sino']],[a('proximo')-0.6,['piano','pad','baixo','shaker','bumbo_leve']],[tCapa,['piano','pad','baixo','shaker','bumbo_leve','sino']]];
return EP;})()
