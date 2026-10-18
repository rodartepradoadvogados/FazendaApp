(()=>{const a=A;const EP={};const SB=30;
// ---- Ep. 5 · Reprodutivo › Protocolo de IATF (em lote). Telas = capturas do app real (captura/capturar_t2e5.mjs). ----
// bt = caixa no conteúdo (coord. da página rolada a 0 nas capturas altas; viewport nas estáticas), bn = elementos fixos (barra, navegação)
const bt=(n,k)=>{const m=MAPA[n];return(m.tall&&m.tall.alvos[k])||m.alvos[k];};const bn=(n,k)=>MAPA[n].alvosN[k];
const mx=n=>{const m=MAPA[n];return m.tall?Math.max(0,m.tall.h-69-m.barTop):0;};
const seg=pts=>t=>{if(t<=pts[0][0])return pts[0][1];for(let i=0;i<pts.length-1;i++){const[a0,v0]=pts[i],[a1,v1]=pts[i+1];if(t<a1)return L(v0,v1,io(lin(t,a0,a1)));}return pts[pts.length-1][1];};
const F=TL.frases;
// ---- tempos (tudo ancorado nas palavras da locução) ----
const tRepro=a('reprodutivo')+0.1,tIatf=a('protocoloIatf')+0.15,tAtr=a('atrasadas')+0.12,tSel=a('selecionar')+0.35,
 tTodas=F[4][1]-0.25,tBusca=tTodas+1.15,tCont=a('continuar')+0.1,tLanc=a('lancarD0')+0.1,tCapa=a('proximo')-0.15;
const tProt=a('protocolos')-0.4,tBack=a('passoUm')-0.35;
const cT={lancar:0,grade:tRepro+0.1,p1a:tIatf+0.1,prot:tProt,p1b:tBack,atr:tAtr+0.1,sel:tSel+0.1,todas:tTodas+0.1,busca:tBusca+0.1,p2a:tCont+0.1,res:tLanc+0.35};
EP.imgs={lancar:'s01_lancar',grade:'s02_repro_grade',p1a:'s03_p1_aptas',prot:'s11_protocolos_grade',p1b:'s03_p1_aptas',atr:'s04_atrasadas',sel:'s05_atrasadas_marcadas',todas:'s06_todas',busca:'s07_busca_protocolo',
 p2a:'s08_p2_topo',res:'s10_resultado'};
EP.telas=[[0,'lancar',0],[cT.grade,'grade',1],[cT.p1a,'p1a',1],[cT.prot,'prot',1],[cT.p1b,'p1b',1],[cT.atr,'atr',0],[cT.sel,'sel',0],[cT.todas,'todas',0],[cT.busca,'busca',0],[cT.p2a,'p2a',1],[cT.res,'res',1]];
// ---- rolagem (px CSS do app) ----
const SA=300;                                   // Atrasadas: o botão "Selecionar todas as atrasadas" e os cartões na tela
const rAtr=seg([[a('ponto')+0.1,0],[tSel-0.75,SA]]);
const rSel=seg([[0,SA+21.5],[tTodas-1.1,SA+21.5],[tTodas-0.5,150]]);   // +21,5: a linha "Rascunho salvo" empurra a página
const rTodas=seg([[0,150]]);
const rBusca=seg([[0,150]]);
const rP=seg([[a('protocoloInteiro')-0.5,0],[a('d7')-0.3,200],[a('atencao')-0.5,200],[a('atencao')+0.2,281]]);
EP.rolagem={atr:rAtr,sel:rSel,todas:rTodas,busca:rBusca,p2a:rP};
const S=(id,t)=>cl(EP.rolagem[id](t),0,mx(EP.imgs[id]));
const cx=b=>b.x+b.w/2,cy=b=>b.y+b.h/2;
// ---- toques: [t, x, y] em coordenadas da tela do celular (CSS) já com a barra de status (+30) ----
const rep=bt('s01_lancar','repro'),iat=bt('s02_repro_grade','iatf'),bAtr=bt('s03_p1_aptas','btnAtrasadas'),sl=bt('s04_atrasadas','selTodas'),bTodas=bt('s05_atrasadas_marcadas','btnTodas'),
 bus=bt('s06_todas','busca'),co=bn('s07_busca_protocolo','continuar'),cta=bn('s08_p2_topo','cta');
EP.toques=[
 [tRepro,cx(rep),cy(rep)+SB],[tIatf,cx(iat),cy(iat)+SB],[tAtr,cx(bAtr),cy(bAtr)+SB],
 [tSel,cx(sl),cy(sl)-S('atr',tSel)+SB],[tTodas,cx(bTodas),cy(bTodas)-S('sel',tTodas)+SB],[tBusca,cx(bus)-40,cy(bus)-S('todas',tBusca)+SB],
 [tCont,cx(co),cy(co)+SB],[tLanc,cx(cta),cy(cta)+SB]];
// ---- câmera: [t de chegada, duração, cx, cy, zoom] (coords da tela do celular com +30). Visível: de cy-189/z a cy+349/z. Zoom ≤ 1,18 e centrado ----
EP.cam=[[0,0,195,300,1.0],[a('emLancar')+0.3,1.0,195,380,1.12],[tRepro+0.55,0.9,195,360,1.1],
 [tIatf+0.5,0.9,195,450,1.0],[tProt+0.1,0.6,195,330,1.1],[tBack+0.1,0.25,195,450,1.0],
 [a('situacao')-0.4,0.9,195,470,1.1],[a('vazias')+0.3,0.8,195,470,1.05],[tSel-0.9,0.8,195,520,1.0],
 [a('atrasadas2')-0.2,0.7,195,540,1.0],[tTodas-0.6,0.7,195,480,1.0],[cT.busca,0.6,195,520,1.12],[tCont+0.35,0.7,195,520,1.0],
 [a('passoDois')-0.2,0.8,195,480,1.0],[a('protocoloInteiro')-0.4,0.9,195,520,1.0],[a('atencao')-0.3,0.8,195,560,1.0],
 [tLanc+0.5,0.7,195,470,1.0]];
// ---- anotações: [t0,t1,tipo,x,y,w,h,{c,scr}] — somem exatamente no quadro da troca de tela seguinte (regra do motor) ----
const V='#2E7D52',Z='#1E6FA8',D='#E0A63C',IN='#1A2638';
const bx=(n,k,o={})=>{const b=bt(n,k);return[b.x,b.y,b.w,b.h,o];};
const nb=(n,k,o={})=>{const b=bn(n,k);return[b.x,b.y,b.w,b.h,o];};
const tFim=a('atencao')-0.45;
const cN=i=>bx('s05_atrasadas_marcadas','c'+i,{c:i%2?Z:V,scr:'sel'});
EP.anot=[
 [a('toqueRepro')+0.1,tRepro+0.1,'caixa',...bx('s01_lancar','repro',{c:V})],
 [a('protocoloIatf')-0.1,tIatf+0.1,'caixa',...bx('s02_repro_grade','iatf',{c:V})],
 [a('iatf2')-0.2,tBack,'caixa',...bx('s11_protocolos_grade','iatf',{c:V})],
 [a('quem')-0.1,a('situacao')-0.4,'marca',88,270,168,21,{c:D}],
 [a('atrasadas')-0.2,tAtr+0.1,'caixa',...bx('s03_p1_aptas','btnAtrasadas',{c:V})],
 [a('atrasadas')+0.45,a('vazias')-0.2,'circulo',137,435,26,28,{c:Z,scr:'atr'}],
 [a('vazias')-0.1,a('ponto')+0.15,'caixa',...bx('s04_atrasadas','notaSit',{c:Z,scr:'atr'})],
 [a('selecionar')-0.35,tSel+0.1,'caixa',...bx('s04_atrasadas','selTodas',{c:D,scr:'atr'})],
 [a('atrasadas2')-0.1,tTodas-0.3,'caixa',...cN(0)],[a('atrasadas2')+0.2,tTodas-0.3,'caixa',...cN(1)],
 [a('atrasadas2')+0.5,tTodas-0.3,'caixa',...cN(2)],[a('atrasadas2')+0.8,tTodas-0.3,'caixa',...cN(3)],
 [tSel+0.5,tTodas-0.3,'circulo',...(()=>{const b=bn('s05_atrasadas_marcadas','barraN');return[b.x,b.y,b.w,b.h,{c:Z}];})()],
 [tTodas-0.55,tTodas+0.1,'caixa',...bx('s05_atrasadas_marcadas','btnTodas',{c:V,scr:'sel'})],
 [tBusca-0.5,tBusca+0.1,'caixa',...bx('s06_todas','busca',{c:D,scr:'todas'})],
 [cT.busca+0.15,tCont+0.1,'caixa',...bx('s07_busca_protocolo','cProt',{c:Z,scr:'busca'})],
 [a('dia')-0.45,tCont+0.1,'caixa',...bx('s07_busca_protocolo','chipProt',{c:D,scr:'busca'})],
 [a('duasVezes')-0.35,tCont+0.1,'sub',136,648,238,0,{c:V,scr:'busca',txt:'✕ não entra 2 vezes',nx:140,ny:628}],
 [a('toqueCont')-0.1,tCont+0.1,'caixa',...nb('s07_busca_protocolo','continuar',{c:D})],
 [a('passoDois')+0.15,a('data')-0.15,'caixa',...bx('s08_p2_topo','resumo',{c:V,scr:'p2a'})],
 [a('data')-0.1,a('protocoloInteiro')-0.5,'caixa',16,419,358,77,{c:V,scr:'p2a'}],
 [a('protocoloInteiro')-0.1,a('d7')-0.15,'caixa',...bx('s08_p2_topo','tl',{c:Z,scr:'p2a'})],
 [a('d7')-0.1,tFim,'caixa',...bx('s08_p2_topo','li1',{c:V,scr:'p2a'})],
 [a('d9')-0.1,tFim,'caixa',...bx('s08_p2_topo','li2',{c:Z,scr:'p2a'})],
 [a('d11')-0.1,tFim,'caixa',...bx('s08_p2_topo','li3',{c:V,scr:'p2a'})],
 [a('hormonios')-0.25,tFim,'marca',...bx('s08_p2_topo','hm0',{c:D,scr:'p2a'})],
 [a('hormonios')-0.1,tFim,'marca',...bx('s08_p2_topo','hm1',{c:D,scr:'p2a'})],
 [a('hormonios')+0.05,tFim,'marca',...bx('s08_p2_topo','hm2',{c:D,scr:'p2a'})],
 [a('hormonios')+0.2,tFim,'marca',...bx('s08_p2_topo','hm3',{c:D,scr:'p2a'})],
 [a('soAgenda')-0.35,tLanc+0.1,'caixa',...bx('s08_p2_topo','nota',{c:Z,scr:'p2a'})],
 [a('toqueLancar')-0.15,tLanc+0.1,'caixa',...nb('s08_p2_topo','cta',{c:D})],
 [a('agenda')-0.45,tCapa,'caixa',...bx('s10_resultado','texto',{c:D})]
];
EP.fitas=[[a('protocolo1')-0.1,a('emLancar')+0.1,'Protocolo de <b>IATF</b>',110,298,-2],
 [a('inseminacao')-0.2,a('aParte')+0.45,'<span style="font-size:36px">D11 → Reprodutivo › <b>Inseminação</b></span>',70,298,-1.5]];
EP.titulos=[[0,'Temporada 2 · <m>Ep. 5</m>'],[a('emLancar')-0.1,'Toque em <m>Reprodutivo</m>'],[a('protocoloIatf')-0.25,'Depois, <m>Protocolo IATF</m>'],[a('mesmaTela')-0.1,'Ou: <m>Protocolos › IATF</m>'],
 [a('passoUm')-0.1,'Passo 1: <m>quem</m> entra'],[a('situacao')-0.15,'Situação: <m>Atrasadas</m>'],[a('toqueSel')-0.1,'Selecionar <m>todas</m>'],
 [F[4][1]-0.1,'Já em <m>protocolo</m>: travada'],[a('toqueCont')-0.1,'Toque em <m>Continuar</m>'],[a('passoDois')-0.1,'Passo 2: o <m>protocolo</m>'],[a('data')-0.1,'Confira a <m>data do D0</m>'],
 [a('atencao'),'Só <m>agenda</m> o protocolo'],[a('toqueLancar')-0.2,'<m>Lançar</m> D0'],[a('pronto')-0.1,'Feito: <m>lançado</m>']];
// diagrama Vox no papel: régua D0 → D7 → D9 → D11 com as datas, cada marco acende na palavra
EP.diag=[a('protocoloInteiro')-0.25,a('atencao')-0.35];
EP.leg=[[F[0][1],F[0][2],F[0][0]],[F[1][1],a('mesmaTela')-0.3,'Em Lançar, toque em Reprodutivo, e depois em Protocolo IATF.'],[a('mesmaTela')-0.3,F[1][2],'A mesma tela abre em Protocolos, IATF.'],
 [F[2][1],a('situacao')-0.25,'No passo um, escolha quem entra no protocolo.'],[a('situacao')-0.25,F[2][2],'Em Situação, toque em Atrasadas: são as vacas vazias que já passaram do ponto.'],
 [F[3][1],F[3][2],F[3][0]],
 [F[4][1],a('duasVezes')-0.5,'Vaca que já está em protocolo aparece travada, com o dia da etapa.'],[a('duasVezes')-0.5,F[4][2],'Ela não entra duas vezes.'],
 [F[5][1],F[5][2],F[5][0]],
 [F[6][1],a('protocoloInteiro')-0.3,'No passo dois, confira a data do D zero.'],[a('protocoloInteiro')-0.3,F[6][2],'O app já mostra o protocolo inteiro: D sete, D nove e D onze, com as datas e os hormônios.'],
 [F[7][1],F[7][2],F[7][0]],[F[8][1],F[8][2],F[8][0]],[F[9][1],F[9][2],F[9][0]]];
EP.fimLeg=tCapa;EP.shake=a('lancado');
EP.entrada=t=>{const p=mola(t-0.3,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
const tCar=a('lancado'),tCarFim=a('agenda')-0.4;
EP.oculta=[[tCar,tCarFim],[EP.diag[1],EP.diag[1]+0.36],[a('protocolo1')-0.1,a('emLancar')+0.4],[a('inseminacao')-0.2,a('aParte')+0.65]];
EP.estado=(t,{K,io,oc,lin,mola,L,cl,ob,ic,cow,X,iq})=>{
  K.dymo.style.transform=`translateX(${(1-cl(mola(t-0.55,9,.55),0,1.15))*-1000}px) rotate(-1.6deg)`;
  const g=cl(mola(t-0.15,10,.5),0,1.2);K.grampo.style.transform=`translateY(${(1-g)*-230}px) rotate(${(1-cl(g,0,1))*6}deg)`;
  // diagrama: régua do protocolo (D0 17/10 · D7 24/10 · D9 26/10 · D11 28/10), traço tracejado a 12 qps entre os marcos
  const D0=EP.diag[0],D1=EP.diag[1];
  if(t>=D0-0.05&&t<D1+0.3){const pe=oc(lin(t,D0,D0+0.45)),ps=iq(lin(t,D1,D1+0.3));const w=(Math.floor(t*12)%3)-1;
    const M=[[0,60,'D0','17/10',D0+0.05],[7,524,'D7','24/10',a('d7')-0.05],[9,642,'D9','26/10',a('d9')-0.05],[11,860,'D11','28/10',a('d11')-0.05]];
    let sv='';
    for(let i=0;i<3;i++){const x0=M[i][1],x1=M[i+1][1];const pr=io(lin(t,M[i+1][4]-0.45,M[i+1][4]));if(pr<=0)continue;
      sv+=`<path d="M${x0+30} ${54+w} L${L(x0+30,x1-30,pr)} ${54-w}" stroke="${i==2?'#2E7D52':'#1E6FA8'}" stroke-width="8" stroke-linecap="round" stroke-dasharray="4 16" fill="none"/>`;}
    for(const[,x,lab,dt,t0]of M){const b=cl(mola(t-t0,13,.5),0,1.2),on=t>=t0;const fim=lab==='D11';
      sv+=`<g transform="translate(${x} 54) scale(${b})"><circle r="${fim?34:30}" fill="${on?(fim?'#E0A63C':'#FBF6E8'):'#FBF6E8'}" stroke="${fim?'#2E7D52':IN}" stroke-width="7"/><text y="10" text-anchor="middle" font-family="Archivo" font-weight="800" font-size="${fim?27:28}" fill="${IN}">${lab}</text></g>
       <text x="${x}" y="${128}" text-anchor="middle" font-family="Archivo" font-weight="800" font-size="34" fill="${IN}" opacity="${cl(b)}">${dt}</text>`;}
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
   <div class="abs" data-z="1" style="left:80px;top:360px;font:800 118px/1.02 Archivo;color:#1A2638;letter-spacing:-.02em;text-transform:uppercase">Controle<br><span style="position:relative;display:inline-block;z-index:0">leiteiro<i style="position:absolute;left:-10px;right:-14px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div>
   <div class="abs" data-z="2" style="left:80px;top:850px;width:380px;height:380px;background:#fff;box-shadow:0 26px 50px rgba(50,32,8,.3);display:flex;align-items:center;justify-content:center">${cow(250,'#1A2638',0.9)}</div>
   <div class="abs" data-z="3" style="left:510px;top:870px;width:490px"><div style="font:800 84px/1 Archivo;color:#1A2638;letter-spacing:-.02em">COW<span style="color:#8A5A12">DATA</span></div><div style="margin-top:28px;font:800 46px/1.1 Archivo;color:#1A2638;text-transform:uppercase">O rebanho na mão de <span style="position:relative;display:inline-block;z-index:0">quem cuida<i style="position:absolute;left:-8px;right:-10px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div></div>
   <div class="fita" data-z="4" style="left:90px;top:1330px">Ep. 5 · <b>Protocolo de IATF</b></div>`);
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
EP.camadas=[[0,['piano','pad']],[a('emLancar'),['piano','pad','shaker']],[a('passoUm'),['piano','pad','baixo','shaker','bumbo_leve']],[a('passoDois'),['piano','pad','baixo','shaker','bumbo','palma','piano_cheio']],
 [a('pronto')-0.2,['piano','pad','baixo','shaker','shaker16','bumbo','palma','piano_cheio','sino']],[a('agenda')+0.4,['piano','pad','baixo','shaker','bumbo_leve']],[tCapa,['piano','pad','baixo','shaker','bumbo_leve','sino']]];
return EP;})()
