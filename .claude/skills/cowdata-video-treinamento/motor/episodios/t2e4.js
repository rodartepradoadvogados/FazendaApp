(()=>{const a=A;const EP={};const SB=30;
// ---- Ep. 4 · Reprodutivo › Parto. Telas = capturas do app real (captura/capturar_t2e4.mjs). O formulário do parto é de UM animal e uma tela só: a rolagem é contínua. ----
// bt = caixa no conteúdo (coord. da página rolada a 0 nas capturas altas; viewport nas estáticas), bn = caixa no viewport (modais, avisos)
const bt=(n,k)=>{const m=MAPA[n];return(m.tall&&m.tall.alvos[k])||m.alvos[k];};const bn=(n,k)=>MAPA[n].alvosN[k];
const mx=n=>{const m=MAPA[n];return m.tall?Math.max(0,m.tall.h-69-m.barTop):0;};
const seg=pts=>t=>{if(t<=pts[0][0])return pts[0][1];for(let i=0;i<pts.length-1;i++){const[a0,v0]=pts[i],[a1,v1]=pts[i+1];if(t<a1)return L(v0,v1,io(lin(t,a0,a1)));}return pts[pts.length-1][1];};
// ---- tempos (tudo ancorado nas palavras da locução) ----
const tRepro=a('reprodutivo')+0.1,tParto=a('parto')+0.15,tDig=a('numero')+0.25,tSel=a('nome')+0.6,
 tTipo=a('normal')-0.25,tSexo=a('sexo')+0.25,tNum=a('numeroCria')-0.05,
 tColo=a('abra')+0.1,tTom=tColo+1.15,tLit=tTom+0.6,tBrix=tLit+0.6,
 tSalvar=a('salvar')+0.1,tConf1=a('confirmar')+0.05,tConf2=a('bezerras')+0.25,
 tG1=a('gemeos')+0.25,tGem=a('gemelar')-0.15,tG3=a('segunda')+0.2;
const cT={grade:tRepro+0.1,p0:tParto+0.1,dig:tDig,pm:tSel+0.1,pt:tTipo+0.1,ps:tSexo+0.1,pn:tNum+0.2,pc:tColo+0.1,ph:tTom+0.1,pl:tLit+0.1,pb:tBrix+0.1,
 m1:tSalvar+0.25,m2:tConf1+0.35,fin:tConf2+0.1,g0:tG1,g1:tGem+0.1,g2:tG3};
EP.imgs={lancar:'s01_lancar',grade:'s02_repro_grade',p0:'s03_parto_busca',dig:'s04_digitado',pm:'s05_matriz',pt:'s06_tipo',ps:'s07_sexo',pn:'s08_numero',pc:'s09_colo',ph:'s10_tomou',
 pl:'s11_litros',pb:'s12_brix',m1:'s13_modal_mae',m2:'s14_modal_cria',fin:'s15_final',g0:'s16_novo',g1:'s17_gemelar',g2:'s18_gemelar2'};
// [t, tela, direção (1 = desliza da direita), 1 = só troca de estado da mesma tela (as anotações continuam)]
EP.telas=[[0,'lancar',0],[cT.grade,'grade',1],[cT.p0,'p0',1],[cT.dig,'dig',0,1],[cT.pm,'pm',0],[cT.pt,'pt',0,1],[cT.ps,'ps',0,1],[cT.pn,'pn',0,1],[cT.pc,'pc',0,1],[cT.ph,'ph',0,1],[cT.pl,'pl',0,1],[cT.pb,'pb',0,1],
 [cT.m1,'m1',0],[cT.m2,'m2',0,1],[cT.fin,'fin',0],[cT.g0,'g0',1],[cT.g1,'g1',0,1],[cT.g2,'g2',0,1]];
// ---- rolagem (px CSS do app): uma só função para todos os estados do formulário ----
const SG=seg([[0,0],[a('tipoParto')-0.5,0],[a('tipoParto')+0.3,150],[a('sexo')-0.5,150],[a('sexo')+0.1,300],[tColo+0.15,300],[tColo+1.1,1000],
 [a('bronze')+0.6,1000],[a('bronze')+1.4,1171]]);
const SGg=seg([[0,350],[a('gemelar')+0.6,350],[a('gemelar')+1.2,700]]);
EP.rolagem={pm:SG,pt:SG,ps:SG,pn:SG,pc:SG,ph:SG,pl:SG,pb:SG,g0:SGg,g1:SGg,g2:SGg};
const S=(id,t)=>cl(EP.rolagem[id](t),0,mx(EP.imgs[id]));
const cx=b=>b.x+b.w/2,cy=b=>b.y+b.h/2;
// ---- toques: [t, x, y] em coordenadas da tela do celular (CSS) já com a barra de status (+30) ----
const rep=bt('s01_lancar','repro'),pto=bt('s02_repro_grade','parto'),res=bt('s04_digitado','res3654'),tipoS=bt('s05_matriz','tipoSel'),btF=bt('s06_tipo','btnF'),numI=bt('s07_sexo','numIn'),
 btC=bt('s08_numero','btnColo'),tomS=bt('s09_colo','tomouSim'),litS=bt('s10_tomou','litrosSel'),brxS=bt('s11_litros','brixSel'),sv=bt('s12_brix','salvar'),
 cf1=bn('s13_modal_mae','confirmar'),cf2=bn('s14_modal_cria','confirmar'),gmC=bt('s16_novo','gemCx');
EP.toques=[
 [tRepro,cx(rep),cy(rep)+SB],[tParto,cx(pto),cy(pto)+SB],[tSel,cx(res),cy(res)+SB],
 [tTipo,cx(tipoS),cy(tipoS)-S('pm',tTipo)+SB],[tSexo,cx(btF),cy(btF)-S('pt',tSexo)+SB],[tNum,cx(numI),cy(numI)-S('ps',tNum)+SB],
 [tColo,cx(btC),cy(btC)-S('pn',tColo)+SB],[tTom,cx(tomS),cy(tomS)-S('pc',tTom)+SB],[tLit,cx(litS),cy(litS)-S('ph',tLit)+SB],[tBrix,cx(brxS),cy(brxS)-S('pl',tBrix)+SB],
 [tSalvar,cx(sv),cy(sv)-S('pb',tSalvar)+SB],[tConf1,cx(cf1),cy(cf1)+SB],[tConf2,cx(cf2),cy(cf2)+SB],[tGem,cx(gmC),cy(gmC)-S('g0',tGem)+SB]];
// ---- câmera: [t de chegada, duração, cx, cy, zoom] (coords da tela do celular com +30). Zoom ≤ 1,18 e centrado: nada de texto cortado nas bordas ----
EP.cam=[[0,0,195,300,1.0],[a('emLancar')+0.3,1.0,195,380,1.12],[tRepro+0.55,0.9,195,350,1.1],
 [tParto+0.55,0.8,195,430,1.0],[tSel+0.4,0.8,195,450,1.0],
 [a('tipoParto')-0.3,0.7,195,440,1.08],[a('sexo')-0.4,0.8,195,470,1.0],[a('semNumero')-0.5,0.7,195,500,1.1],
 [a('colostro')-0.2,0.8,195,470,1.0],[tColo+0.9,0.8,195,470,1.0],
 [a('bronze')+0.7,0.8,195,560,1.1],[tSalvar+0.3,0.8,195,450,1.1],[tConf1+0.45,0.8,195,450,1.1],
 [tConf2+0.3,0.8,195,520,1.0],[tG1+0.3,0.8,195,470,1.0]];
// ---- anotações: [t0,t1,tipo,x,y,w,h,{c,scr}] — somem exatamente no quadro da troca de tela seguinte (regra do motor) ----
const V='#2E7D52',Z='#1E6FA8',D='#E0A63C';
const bx=(n,k,o={})=>{const b=bt(n,k);return[b.x,b.y,b.w,b.h,o];};
const nb=(n,k,o={})=>{const b=bn(n,k);return[b.x,b.y,b.w,b.h,o];};
const ret=bt('s05_matriz','ret'),tmBr=a('bronze')+0.5,g2=bt('s17_gemelar','sec2'),g2n=bt('s17_gemelar','baixada2');
EP.anot=[
 [a('toqueRepro')+0.1,tRepro+0.1,'caixa',...bx('s01_lancar','repro',{c:V})],
 [a('parto')-0.35,tParto+0.1,'caixa',...bx('s02_repro_grade','parto',{c:V})],
 [a('busque')+0.05,tSel+0.1,'caixa',...bx('s03_parto_busca','busca',{c:Z})],
 [tDig+0.3,tSel+0.1,'caixa',...bx('s04_digitado','res3654',{c:D})],
 [a('data')-0.1,a('tipoParto')+0.2,'caixa',...bx('s05_matriz','data',{c:V,scr:'pm'})],
 [a('tipoParto')+0.2,a('retencao')-0.1,'caixa',...bx('s05_matriz','tipoSel',{c:D,scr:'pm'})],
 [a('retencao')-0.05,a('agenda')+0.2,'caixa',...bx('s05_matriz','ret',{c:Z,scr:'pm'})],
 [a('placenta')+0.15,a('agenda')+0.2,'marca',ret.x+4,ret.y+31,204,22,{c:D,scr:'pm'}],
 [tSexo+0.05,a('colostro')-0.2,'caixa',...bx('s06_tipo','btnF',{c:V,scr:'pt'})],
 [tNum+0.05,a('colostro')-0.2,'caixa',...bx('s07_sexo','numIn',{c:Z,scr:'ps'})],
 [a('semNumero')-0.1,a('colostro')-0.2,'marca',...bx('s08_numero','numRot',{c:D,scr:'pn'})],
 [tColo-0.5,tColo+0.15,'caixa',...bx('s08_numero','btnColo',{c:D,scr:'pn'})],
 [tTom+0.05,tmBr,'caixa',...bx('s09_colo','tomouSim',{c:V,scr:'pc'})],
 [tLit+0.05,tmBr,'caixa',...bx('s10_tomou','litrosSel',{c:Z,scr:'ph'})],
 [tBrix+0.05,tmBr,'caixa',...bx('s11_litros','brixSel',{c:D,scr:'pl'})],
 [a('classifica')-0.1,tmBr,'marca',...bx('s12_brix','brixCls',{c:V,scr:'pb'})],
 [a('toqueSalvar')+0.05,tSalvar+0.25,'caixa',...bx('s12_brix','salvar',{c:D,scr:'pb'})],
 // os dois modais (estáticos, coordenadas do viewport)
 [a('lote')-0.15,tConf1+0.3,'caixa',...nb('s13_modal_mae','lote',{c:V})],
 [a('confirmar')-0.35,tConf1+0.3,'caixa',...nb('s13_modal_mae','confirmar',{c:D})],
 [a('loteCria')-0.1,tConf2+0.2,'caixa',...nb('s14_modal_cria','lote',{c:V})],
 [a('bezerras')-0.25,tConf2+0.2,'caixa',...nb('s14_modal_cria','confirmar',{c:D})],
 [tConf2+0.4,tCarFimF(),'caixa',...nb('s15_final','aviso1',{c:V})],[tConf2+0.6,tCarFimF(),'caixa',...nb('s15_final','aviso2',{c:V})],
 // gêmeos
 [tG1+0.55,a('gemelar')+0.45,'caixa',...bx('s16_novo','gem',{c:V,scr:'g0'})],
 [a('segunda')+0.1,a('proximo')-0.3,'caixa',g2.x,g2.y-4,g2.w,g2n.y+g2n.h-g2.y+4,{c:Z,scr:'g2'}]
];
function tCarFimF(){return a('gemeos')-0.05;}
EP.fitas=[[a('parto1')-0.1,a('emLancar')+0.1,'<b>Parto</b>',100,298,-2],
 [a('agenda')-0.3,a('agenda')+0.9,'→ <b>Agenda</b>',640,1085,-2]];
EP.titulos=[[0,'Temporada 2 · <m>Ep. 4</m>'],[a('emLancar')-0.1,'Toque em <m>Reprodutivo</m>'],[a('parto')-0.5,'Depois, <m>Parto</m>'],[a('busque')-0.1,'Busque a <m>matriz</m>'],
 [a('data')-0.15,'Confira a <m>data</m>'],[a('tipoParto')-0.1,'Tipo de parto: <m>Normal</m>'],[a('retencao')-0.1,'<m>Retenção</m> de placenta'],[tSexo-0.55,'<m>Sexo</m> da cria'],
 [a('numeroCria')-0.1,'<m>Número</m> da cria'],[a('colostro')-0.1,'<m>Colostragem</m> e IgG'],[a('toqueSalvar')-0.2,'Toque em <m>Salvar</m>'],
 [a('pergunta')-0.2,'Mover a <m>mãe</m> de lote'],[a('confirmar')-0.3,'Toque em <m>Confirmar</m>'],[a('depois')-0.1,'Lote da <m>cria</m>'],
 [tG1,'Parto <m>gemelar</m>'],[a('segunda')-0.2,'Segunda <m>cria</m>']];
// diagramas Vox no papel: (1) Brix 27% → Ouro / Prata / Bronze; (2) mini-quadro dos lotes (ocupa o lugar do título)
EP.diag=[a('classifica')-0.15,a('bronze')+0.95];
const tQ0=tConf2+0.3;
const F=TL.frases;
EP.leg=[[F[0][1],F[0][2],F[0][0]],[F[1][1],F[1][2],F[1][0]],
 [F[2][1],a('data')-0.3,'Busque a matriz pelo número ou pelo nome,'],[a('data')-0.3,F[2][2],'e confira a data do parto.'],
 [F[3][1],a('retencao')-0.3,'Em Tipo de parto, escolha Normal.'],[a('retencao')-0.3,a('agenda')-0.45,'Se houve retenção de placenta, marque:'],[a('agenda')-0.45,F[3][2],'o app cria um item na Agenda.'],
 [F[4][1],a('semNumero')-0.4,'Toque no sexo da cria, e digite o número dela.'],[a('semNumero')-0.4,F[4][2],'Se ficar sem número, a cria é baixada automaticamente.'],
 [F[5][1],a('classifica')-0.3,'Tem os dados do colostro? Abra Colostragem e IgG.'],[a('classifica')-0.3,F[5][2],'O app já classifica: ouro, prata ou bronze.'],
 [F[6][1],F[6][2],F[6][0]],
 [F[7][1],a('confira')-0.2,'O app pergunta se quer mover a mãe de lote.'],[a('confira')-0.2,F[7][2],'Confira, e toque em Confirmar.'],
 [F[8][1],a('bezerra')-0.3,'Depois, sugere o lote da cria:'],[a('bezerra')-0.3,F[8][2],'a bezerra vai para o lote de bezerras.'],
 [F[9][1],a('gemeos')-0.2,'Pronto, lançado.'],[a('gemeos')-0.2,a('gemelar')-0.3,'Nasceram gêmeos?'],[a('gemelar')-0.3,F[9][2],'Marque Parto gemelar, e preencha a segunda cria.'],
 [F[10][1],F[10][2],F[10][0]]];
const tCapa=a('proximo')-0.15;EP.fimLeg=tCapa;EP.shake=a('lancado');
EP.entrada=t=>{const p=mola(t-0.3,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
const tCar=a('lancado'),tCarFim=a('gemeos')-0.05;
EP.oculta=[[tCar,tCarFim],[a('parto1')-0.1,a('emLancar')+0.4],[tQ0,tCar-0.02]];
const IN='#1A2638';
const caixa=(l,w,rot,cont,extra='')=>`<div class="abs" style="left:${l}px;top:2px;width:${w}px;height:132px;background:#FBF6E8;border:6px solid ${IN};box-shadow:6px 8px 0 rgba(26,38,56,.25);${extra}">${cont}</div>`;
EP.estado=(t,{K,io,oc,lin,mola,L,cl,ob,ic,cow,X,iq})=>{
  K.dymo.style.transform=`translateX(${(1-cl(mola(t-0.55,9,.55),0,1.15))*-1000}px) rotate(-1.6deg)`;
  const g=cl(mola(t-0.15,10,.5),0,1.2);K.grampo.style.transform=`translateY(${(1-g)*-230}px) rotate(${(1-cl(g,0,1))*6}deg)`;
  const D0=EP.diag[0],D1=EP.diag[1];let vis=false;
  if(t>=D0-0.05&&t<D1+0.3){vis=true;
    // (1) BRIX 27% ⇢ OURO | PRATA | BRONZE, seta tracejada a 12 qps
    const pe=oc(lin(t,D0,D0+0.45)),ps=iq(lin(t,D1,D1+0.3));
    const b0=cl(mola(t-D0-0.05,12,.55),0,1.15),pa=io(lin(t,D0+0.3,D0+0.85));
    const w=(Math.floor(t*12)%3)-1,off=(Math.floor(t*12)%6)*4;
    const pulso=(t0)=>{const u=lin(t,t0-0.1,t0+0.6);return u>0&&u<1?Math.sin(u*Math.PI):0;};
    const fo=io(lin(t,a('ouro')-0.1,a('ouro')+0.25));
    const faixa=(i,l,nome,reg,sub,cor,t0,hi)=>{const bb=cl(mola(t-D0-0.3-i*0.15,12,.55),0,1.15),pu=pulso(t0),sc=bb*(1+.04*hi+.04*pu);
      return caixa(l,196,0,`<div class="abs" style="left:0;right:0;top:9px;text-align:center;font:800 35px/1 Archivo;color:${IN};letter-spacing:.03em">${nome}</div><div class="abs" style="left:0;right:0;top:50px;text-align:center;font:800 30px/1 Archivo;color:${IN}">${reg}</div><div class="abs" style="left:0;right:0;top:92px;text-align:center;font:700 21px/1 Inter,Archivo,sans-serif;color:#4b4034">${sub}</div>`,
       `background:${hi?cor:'#FBF6E8'};background-image:linear-gradient(${cor}${hi?'':'33'},${cor}${hi?'':'33'});transform:scale(${sc}) rotate(${(i-1)*1.1}deg);${hi||pu?`border-color:${IN};outline:5px solid ${cor};outline-offset:0;`:''}`);};
    const ho=fo,hp=0,hb=0;
    X(K.diag,caixa(0,196,0,`<div class="abs" style="left:0;right:0;top:12px;text-align:center;font:800 26px/1 Archivo;color:${IN};letter-spacing:.08em">BRIX</div><div class="abs" style="left:0;right:0;top:44px;text-align:center;font:800 72px/1 Archivo;color:${IN}">27%</div>`,`transform:scale(${b0}) rotate(-1.5deg)`)
     +`<svg class="abs" style="left:204px;top:6px;clip-path:inset(0 ${(1-pa)*100}% 0 0)" width="90" height="130" viewBox="0 0 90 130"><path d="M${4+w} ${65+w} L${68-w} ${65-w}" stroke="${IN}" stroke-width="10" stroke-linecap="round" stroke-dasharray="14 12" stroke-dashoffset="${-off}" fill="none"/><path d="M${50+w} 42 L${80} ${65-w} L${50-w} 88" stroke="${IN}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>`
     +faixa(0,300,'OURO','&gt;25%','excelente','#E0A63C',a('ouro'),ho)+faixa(1,512,'PRATA','18–25%','médio','#8793A0',a('prata'),hp)+faixa(2,724,'BRONZE','&lt;18%','ruim','#A8622A',a('bronze'),hb));
    K.diag.style.opacity=1-ps;K.diag.style.transform=`translateY(${(1-pe)*-170+ps*-120}px)`;}
  else if(t>=tQ0&&t<tCar-0.02){vis=true;
    // (2) mini-quadro: 05 Pré-parto 12 → 11 · 01 Alta 39 → 40 · 07 Bezerras 58 → 59
    const pe=oc(lin(t,tQ0,tQ0+0.4)),ps=iq(lin(t,tCar-0.3,tCar-0.02));
    const card=(i,l,cod,nome,de,para,cor)=>{const bb=cl(mola(t-tQ0-0.1-i*0.18,12,.55),0,1.15),nv=cl(mola(t-tQ0-0.7-i*0.18,14,.5),0,1.2);
      return caixa(l,290,0,`<div class="abs" style="left:0;right:0;top:10px;text-align:center;font:800 25px/1 Archivo;color:${IN};white-space:nowrap">${cod} · ${nome}</div><div class="abs" style="left:0;right:0;top:48px;text-align:center;font:800 62px/1 Archivo;color:${IN};white-space:nowrap">${de} <span style="color:${cor}">→</span> <span style="color:${cor};display:inline-block;transform:scale(${1+.18*Math.sin(Math.PI*cl(nv))})">${para}</span></div>`,`transform:scale(${bb}) rotate(${(i-1)*1.2}deg)`);};
    X(K.diag,card(0,0,'05','PRÉ-PARTO',12,11,Z)+card(1,315,'01','ALTA',39,40,V)+card(2,630,'07','BEZERRAS',58,59,V));
    K.diag.style.opacity=1-ps;K.diag.style.transform=`translateY(${(1-pe)*-170+ps*-120}px)`;}
  K.diag.style.display=vis?'block':'none';
  K.cartao.style.display='none';
  // carimbo de borracha: bate no "lançado" (3 quadros de tremida na cena inteira, ver shake no motor)
  if(t>=tCar&&t<tCarFim){const q=oc(lin(t,tCar,tCar+0.1)),s=lin(t,tCarFim-0.2,tCarFim);
    X(K.carimbo,`<div style="display:flex;align-items:center;justify-content:center;gap:22px;border:10px solid #14452B;outline:3px solid #14452B;outline-offset:7px;border-radius:18px;padding:22px 34px;color:#14452B;font:800 54px/1 Archivo;letter-spacing:.03em;white-space:nowrap;background:rgba(251,246,232,.55);filter:url(#tinta)"><svg width="70" height="70" viewBox="0 0 24 24" fill="none" stroke="#14452B" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5l5 5L20 6.5"/></svg>LANÇADO NO REBANHO</div>`);
    K.carimbo.style.display='block';K.carimbo.style.opacity=(0.93*(1-s)*cl(q*4)).toFixed(3);K.carimbo.style.transform=`translateX(-50%) rotate(-4deg) scale(${L(1.7,1,q)})`;}else K.carimbo.style.display='none';
};
EP.capa=(t,el)=>{const p=io(lin(t,tCapa,tCapa+0.7));if(p<=0){el.style.display='none';return;}el.style.display='block';el.style.clipPath=`inset(${(1-p)*100}% 0 0 0)`;
  const q=mola(t-tCapa-0.45,10,.5),r=mola(t-tCapa-0.95,12,.5),s=oc(lin(t,tCapa+1.7,tCapa+2.3)),u=mola(t-tCapa-2.5,12,.5);
  X(el,`<div class="dymo" style="top:250px;left:80px;transform:rotate(-1.6deg)">PRÓXIMO EPISÓDIO · TEMP. 02</div>
   <div class="abs" data-z="1" style="left:80px;top:350px;font:800 150px/1.02 Archivo;color:#1A2638;letter-spacing:-.02em;text-transform:uppercase">Protocolo<br><span style="position:relative;display:inline-block;z-index:0">de IATF<i style="position:absolute;left:-10px;right:-14px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div>
   <div class="abs" data-z="2" style="left:80px;top:850px;width:380px;height:380px;background:#fff;box-shadow:0 26px 50px rgba(50,32,8,.3);display:flex;align-items:center;justify-content:center">${cow(250,'#1A2638',0.9)}</div>
   <div class="abs" data-z="3" style="left:510px;top:870px;width:490px"><div style="font:800 84px/1 Archivo;color:#1A2638;letter-spacing:-.02em">COW<span style="color:#8A5A12">DATA</span></div><div style="margin-top:28px;font:800 46px/1.1 Archivo;color:#1A2638;text-transform:uppercase">O rebanho na mão de <span style="position:relative;display:inline-block;z-index:0">quem cuida<i style="position:absolute;left:-8px;right:-10px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div></div>
   <div class="fita" data-z="4" style="left:90px;top:1330px;font-size:37px;letter-spacing:.05em">Ep. 4 · <b>Parto</b></div>`);
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
EP.sfx.push([EP.diag[0],'rasgo'],[tQ0,'rasgo'],[tCapa,'whoosh'],[tCapa+2.5,'rasgo'],[EP.shake,'carimbo']);
EP.sfx.sort((p,q)=>p[0]-q[0]);
EP.camadas=[[0,['piano','pad']],[a('emLancar'),['piano','pad','shaker']],[a('busque'),['piano','pad','baixo','shaker','bumbo_leve']],[a('sexo')-0.2,['piano','pad','baixo','shaker','bumbo','palma','piano_cheio']],
 [a('pronto')-0.2,['piano','pad','baixo','shaker','shaker16','bumbo','palma','piano_cheio','sino']],[a('gemelar')+0.9,['piano','pad','baixo','shaker','bumbo_leve']],[tCapa,['piano','pad','baixo','shaker','bumbo_leve','sino']]];
return EP;})()
