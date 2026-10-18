(()=>{const a=A;const EP={};const SB=30;
// ---- Ep. 3 · Reprodutivo › Diagnóstico de gestação. Telas = capturas do app real (captura/capturar_t2e3.mjs). ----
// bt = caixa no conteúdo (coord. da página rolada a 0 nas capturas altas; viewport nas estáticas), bn = elementos fixos (barra, navegação)
const bt=(n,k)=>{const m=MAPA[n];return(m.tall&&m.tall.alvos[k])||m.alvos[k];};const bn=(n,k)=>MAPA[n].alvosN[k];
const mx=n=>{const m=MAPA[n];return m.tall?Math.max(0,m.tall.h-69-m.barTop):0;};
const seg=pts=>t=>{if(t<=pts[0][0])return pts[0][1];for(let i=0;i<pts.length-1;i++){const[a0,v0]=pts[i],[a1,v1]=pts[i+1];if(t<a1)return L(v0,v1,io(lin(t,a0,a1)));}return pts[pts.length-1][1];};
// ---- tempos (tudo ancorado nas palavras da locução) ----
const tRepro=a('reprodutivo')+0.1,tDiag=a('diagnostico')+0.1,
 tm1=a('marque')+0.3,tm2=tm1+0.75,tm3=tm2+0.95,tm4=tm3+0.75,tm5=tm4+0.75,           // as 5 positivas, uma a uma
 tCont=a('continuar')+0.1,tRet=a('positivo2')+0.3,tMet=a('metodo')+0.4,tSalvar=a('salvar')+0.1,tP1s=tSalvar+0.85,
 tn1=a('vazias')+0.55,tn2=tn1+0.75,tCont2=tn2+0.8,tNeg=a('negativo2')-0.05,tSL=a('toqueSL')+0.45;
const cT={grade:tRepro+0.1,p1:tDiag+0.1,m1:tm1+0.1,m2:tm2+0.1,m3:tm3+0.1,m4:tm4+0.1,m5:tm5+0.1,p2:tCont+0.1,p2r:tRet+0.1,p2m:tMet+0.1,salv:tSalvar+0.1,p1s:tP1s,
 n1:tn1+0.1,n2:tn2+0.1,p2n:tCont2+0.1,p2nr:tNeg+0.1,ins:tSL+0.1};
EP.imgs={lancar:'s01_lancar',grade:'s02_repro_grade',p1:'s03_p1',m1:'s04_marca1',m2:'s05_marca2',m3:'s06_marca3',m4:'s07_marca4',m5:'s08_marca5',p2:'s09_p2',p2r:'s10_p2_retoque',
 p2m:'s11_p2_metodo',salv:'s12_salvando',p1s:'s13_p1_salvo',n1:'s14_marca_neg1',n2:'s15_marca_neg2',p2n:'s16_p2_neg',p2nr:'s17_p2_neg_ok',ins:'s18_insem'};
// [t, tela, direção (1 = desliza da direita), 1 = só troca de estado da mesma tela (as anotações continuam)]
EP.telas=[[0,'lancar',0],[cT.grade,'grade',1],[cT.p1,'p1',1],[cT.m1,'m1',0,1],[cT.m2,'m2',0,1],[cT.m3,'m3',0,1],[cT.m4,'m4',0,1],[cT.m5,'m5',0,1],[cT.p2,'p2',1],[cT.p2r,'p2r',0,1],[cT.p2m,'p2m',0,1],
 [cT.salv,'salv',0],[cT.p1s,'p1s',0],[cT.n1,'n1',0,1],[cT.n2,'n2',0,1],[cT.p2n,'p2n',1],[cT.p2nr,'p2nr',0,1],[cT.ins,'ins',1]];
// ---- rolagem (px CSS do app) ----
const SA=520,SC=800;       // SA: o grupo 01 - Alta inteiro na tela (inclui os dois AINDA NÃO); SC: o 02 - Média na tela
const rP1=seg([[a('prazo')+0.3,0],[a('aindaNao')-0.8,SA],[tm2+0.2,SA],[tm3-0.2,SC]]);
const rP2=seg([[a('agenda')+0.7,0],[a('data')-0.25,234]]);
const rP1s=seg([[tP1s+0.55,0],[tn1-0.25,SA]]);
const rP2n=seg([[0,0]]);
const rIns=seg([[a('abre')-0.1,0],[a('abre')+0.9,640]]);
EP.rolagem={p1:rP1,m1:rP1,m2:rP1,m3:rP1,m4:rP1,m5:rP1,p2:rP2,p2r:rP2,p2m:rP2,p1s:rP1s,n1:rP1s,n2:rP1s,p2n:rP2n,p2nr:rP2n,ins:rIns};
const S=(id,t)=>cl(EP.rolagem[id](t),0,mx(EP.imgs[id]));
const cx=b=>b.x+b.w/2,cy=b=>b.y+b.h/2;
// ---- toques: [t, x, y] em coordenadas da tela do celular (CSS) já com a barra de status (+30) ----
const rep=bt('s01_lancar','repro'),dg=bt('s02_repro_grade','diagnostico'),co=bn('s08_marca5','continuar'),rRet=bt('s09_p2','rRet'),met=bt('s10_p2_retoque','metodo'),
 sv=bn('s11_p2_metodo','salvar'),co2=bn('s15_marca_neg2','continuar'),rNeg=bt('s16_p2_neg','rNeg'),sl=bn('s17_p2_neg_ok','salvarLancar');
const cc=(n,k)=>bt(n,k);const XC=62;   // toque perto da caixa de marcar do cartão
EP.toques=[
 [tRepro,cx(rep),cy(rep)+SB],[tDiag,cx(dg),cy(dg)+SB],
 [tm1,XC,cy(cc('s03_p1','c4318'))-S('p1',tm1)+SB],[tm2,XC,cy(cc('s03_p1','c4455'))-S('p1',tm2)+SB],[tm3,XC,cy(cc('s03_p1','c2127'))-S('p1',tm3)+SB],
 [tm4,XC,cy(cc('s03_p1','c2263'))-S('p1',tm4)+SB],[tm5,XC,cy(cc('s03_p1','c2342'))-S('p1',tm5)+SB],
 [tCont,cx(co),cy(co)+SB],[tRet,cx(rRet),cy(rRet)-S('p2',tRet)+SB],[tMet,cx(met),cy(met)-S('p2m',tMet)+SB],[tSalvar,cx(sv),cy(sv)+SB],
 [tn1,XC,cy(cc('s13_p1_salvo','c4731'))-S('p1s',tn1)+SB],[tn2,XC,cy(cc('s13_p1_salvo','c2388'))-S('p1s',tn2)+SB],[tCont2,cx(co2),cy(co2)+SB],
 [tNeg,cx(rNeg),cy(rNeg)-S('p2n',tNeg)+SB],[tSL,cx(sl),cy(sl)+SB]];
// ---- câmera: [t de chegada, duração, cx, cy, zoom] (coords da tela do celular com +30). Zoom ≤ 1,18 e centrado: nada de texto cortado nas bordas ----
EP.cam=[[0,0,195,300,1.0],[a('emLancar')+0.3,1.0,195,380,1.12],[tRepro+0.55,0.9,195,330,1.1],
 [a('passoUm')-0.4,1.0,195,450,1.0],[a('situacao')-0.4,0.9,195,480,1.1],[a('prazo')+0.2,0.8,195,470,1.0],
 [a('aindaNao')-0.4,0.9,195,520,1.12],[a('umaPorUma')+1.0,0.9,195,470,1.0],
 [a('atencao')+0.4,0.9,195,400,1.0],
 [tCont+0.25,0.8,195,470,1.0],[a('positivo2')-0.5,0.8,195,500,1.08],[a('agenda')+0.5,0.8,195,490,1.0],[a('data')-0.3,0.8,195,540,1.06],[a('toqueSalvar')+0.2,0.7,195,555,1.1],
 [tP1s+0.1,0.7,195,400,1.0],
 [tCont2+0.3,0.8,195,470,1.0],[tNeg+0.3,0.8,195,520,1.0],[a('toqueSL')-0.4,0.7,195,540,1.1],
 [tSL+0.45,0.8,195,430,1.0],[a('pronto')-0.1,0.8,195,470,1.0]];
// ---- anotações: [t0,t1,tipo,x,y,w,h,{c,scr}] — somem exatamente no quadro da troca de tela seguinte (regra do motor) ----
const V='#2E7D52',Z='#1E6FA8',D='#E0A63C';
const bx=(n,k,o={})=>{const b=bt(n,k);return[b.x,b.y,b.w,b.h,o];};
const nb=(n,k,o={})=>{const b=bn(n,k);return[b.x,b.y,b.w,b.h,o];};
const tIndo=a('aindaNao')-0.55;
EP.anot=[
 [a('toqueRepro')+0.1,tRepro+0.1,'caixa',...bx('s01_lancar','repro',{c:V})],
 [a('diagnostico')-0.35,tDiag+0.1,'caixa',...bx('s02_repro_grade','diagnostico',{c:V})],
 [a('passoUm')-0.05,a('situacao')-0.35,'marca',16,260,256,19,{c:D,scr:'p1'}],
 [a('situacao')-0.1,a('aTocar')-0.1,'caixa',...bx('s03_p1','situacao',{c:V,scr:'p1'})],
 [a('aTocar')-0.05,tIndo,'caixa',...bx('s03_p1','btnATocar',{c:D,scr:'p1'})],
 [a('aTocar')+0.4,tIndo,'circulo',...bx('s03_p1','btnATocarN',{c:Z,scr:'p1'})],
 [a('aindaNao')-0.1,a('atencao')-0.3,'caixa',...bx('s03_p1','selo4902',{c:D,scr:'p1'})],
 [a('aindaNao')+0.35,a('atencao')-0.3,'caixa',...bx('s03_p1','selo4846',{c:D,scr:'p1'})],
 [a('umaPorUma')+0.0,a('atencao')-0.3,'caixa',...bx('s03_p1','cx4902',{c:V,scr:'p1'})],
 // as 5 positivas: o grifo nasce no toque e fica até o Continuar
 [tm1+0.05,tCont+0.1,'caixa',...bx('s03_p1','c4318',{c:V,scr:'p1'})],[tm2+0.05,tCont+0.1,'caixa',...bx('s03_p1','c4455',{c:Z,scr:'p1'})],
 [tm3+0.05,tCont+0.1,'caixa',...bx('s03_p1','c2127',{c:V,scr:'p1'})],[tm4+0.05,tCont+0.1,'caixa',...bx('s03_p1','c2263',{c:Z,scr:'p1'})],
 [tm5+0.05,tCont+0.1,'caixa',...bx('s03_p1','c2342',{c:V,scr:'p1'})],
 [tm5+0.3,tCont+0.1,'marca',...(()=>{const b=bn('s08_marca5','barraTxt');return[b.x,b.y,b.w,b.h,{c:D}];})()],
 [a('toqueCont')+0.05,tCont+0.1,'caixa',...nb('s08_marca5','continuar',{c:D})],
 [a('passoDois')+0.15,a('resultado')-0.1,'caixa',...bx('s09_p2','resumoN',{c:Z,scr:'p2'})],
 [a('resultado')-0.05,a('positivo2')-0.2,'caixa',...bx('s09_p2','resultado',{c:V,scr:'p2'})],
 [a('positivo2')-0.15,tMet+0.1,'caixa',...bx('s09_p2','rRet',{c:D,scr:'p2'})],
 [a('agenda')-0.4,a('data')-0.15,'marca',...bx('s10_p2_retoque','rRetDica',{c:D,scr:'p2'})],
 [a('data')-0.1,tSalvar+0.1,'caixa',...bx('s10_p2_retoque','data',{c:V,scr:'p2'})],
 [a('metodo')-0.1,tSalvar+0.1,'caixa',...bx('s10_p2_retoque','metodo',{c:Z,scr:'p2'})],
 [a('toqueSalvar')+0.05,tSalvar+0.1,'caixa',...nb('s11_p2_metodo','salvar',{c:D})],
 // as 2 negativas
 [tn1+0.05,tCont2+0.1,'caixa',...bx('s13_p1_salvo','c4731',{c:V,scr:'p1s'})],[tn2+0.05,tCont2+0.1,'caixa',...bx('s13_p1_salvo','c2388',{c:Z,scr:'p1s'})],
 [tCont2-0.55,tCont2+0.1,'caixa',...nb('s15_marca_neg2','continuar',{c:D})],
 [tNeg-0.2,tSL+0.1,'caixa',...bx('s16_p2_neg','rNeg',{c:Z,scr:'p2n'})],
 [tNeg+0.3,a('toqueSL')-0.2,'marca',...bx('s17_p2_neg_ok','rNegDica',{c:D,scr:'p2n'})],
 [a('toqueSL')-0.1,tSL+0.1,'caixa',...nb('s17_p2_neg_ok','salvarLancar',{c:D})],
 [a('abre')-0.3,a('pronto')-0.2,'circulo',...(()=>{const b=bn('s18_insem','barraN');return[b.x,b.y,b.w,b.h,{c:Z}];})()],
 [a('abre')+1.0,a('pronto')-0.2,'caixa',...bx('s18_insem','c4731',{c:V,scr:'ins'})]
];
EP.fitas=[[a('diagnostico1')-0.1,a('emLancar')+0.1,'Diagnóstico de <b>gestação</b>',100,298,-2],
 [a('retoque2')-0.15,a('proximo')-0.3,'Retoque: <b>A reconfirmar</b>',80,1500,-2]];
EP.titulos=[[0,'Temporada 2 · <m>Ep. 3</m>'],[a('emLancar')-0.1,'Toque em <m>Reprodutivo</m>'],[a('diagnostico')-0.5,'Depois, <m>Diagnóstico</m>'],[a('passoUm')-0.1,'Passo 1: <m>quem</m>'],
 [a('situacao')-0.15,'Situação: <m>A tocar</m>'],[a('aindaNao')-0.15,'Selo <m>Ainda não</m>'],[a('positivo')+0.35,'Primeiro, as <m>positivas</m>'],
 [a('toqueCont')+0.0,'Toque em <m>Continuar</m>'],[a('passoDois')-0.1,'Passo 2: o <m>resultado</m>'],[a('positivo2')-0.1,'<m>Positivo</m> · para retoque'],[a('data')-0.15,'<m>Data</m> e método'],
 [a('toqueSalvar')-0.2,'<m>Salvar</m> (5)'],[a('vazias')-0.1,'Agora, as <m>vazias</m>'],[a('escolhaNeg')-0.2,'Escolha <m>Negativo</m>'],[a('toqueSL')-0.2,'Salvar e <m>lançar inseminação</m>'],
 [a('abre')-0.1,'Abre a <m>inseminação</m>'],[a('pronto')-0.1,'Feito: <m>lançado</m>'],[a('retoque2')+0.95,'No retoque, <m>mesmo jeito</m>']];
// diagrama Vox no papel: 1 resultado → todas as marcadas (positivas primeiro, negativas depois)
EP.diag=[a('atencao')-0.1,a('positivo')+0.35];
const F=TL.frases;
EP.leg=[[F[0][1],F[0][2],F[0][0]],[F[1][1],F[1][2],F[1][0]],
 [F[2][1],a('situacao')-0.35,'No passo um, escolha quem vai ser diagnosticada.'],[a('situacao')-0.35,F[2][2],'Em Situação, A tocar mostra as vacas no prazo do toque.'],
 [F[3][1],a('umaPorUma')-0.5,'Quem ainda não chegou no prazo vem com o selo Ainda não,'],[a('umaPorUma')-0.5,F[3][2],'e só entra marcando uma por uma.'],
 [F[4][1],a('marque')-0.4,'Atenção: o resultado vale para todas as marcadas.'],[a('marque')-0.4,F[4][2],'Então, marque primeiro as que deram positivo.'],
 [F[5][1],F[5][2],F[5][0]],
 [F[6][1],a('agenda')-0.6,'No passo dois, escolha o resultado: Positivo, para retoque.'],[a('agenda')-0.6,F[6][2],'A vaca volta na agenda para reconfirmar.'],
 [F[7][1],F[7][2],F[7][0]],
 [F[8][1],a('escolhaNeg')-0.25,'Agora as vazias: marque as que deram negativo,'],[a('escolhaNeg')-0.25,F[8][2],'e escolha Negativo.'],
 [F[9][1],a('abre')-0.6,'Toque em Salvar e lançar inseminação:'],[a('abre')-0.6,F[9][2],'o app já abre a inseminação com essas vacas.'],
 [F[10][1],a('retoque2')-0.3,'Pronto, lançado.'],[a('retoque2')-0.3,F[10][2],'No retoque, use A reconfirmar, do mesmo jeito.']];
const tCapa=a('proximo')-0.15;EP.fimLeg=tCapa;EP.shake=a('lancado');
EP.entrada=t=>{const p=mola(t-0.3,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
const tCar=a('lancado'),tCarFim=a('retoque2')+0.95;
EP.oculta=[[tCar,tCarFim],[a('diagnostico1')-0.1,a('emLancar')+0.4]];
const IN='#1A2638';
const chk=(c)=>`<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5l5 5L20 6.5"/></svg>`;
const quad=(n,c,k)=>Array.from({length:n},(_,i)=>`<span style="display:inline-block;width:27px;height:27px;margin-right:6px;background:${c};border:3px solid ${IN};transform:scale(${cl(mola(k-i*0.09,14,.5),0,1.15)});vertical-align:top;padding:1px 0 0 1px">${chk()}</span>`).join('');
EP.estado=(t,{K,io,oc,lin,mola,L,cl,ob,ic,cow,X,iq})=>{
  K.dymo.style.transform=`translateX(${(1-cl(mola(t-0.55,9,.55),0,1.15))*-1000}px) rotate(-1.6deg)`;
  const g=cl(mola(t-0.15,10,.5),0,1.2);K.grampo.style.transform=`translateY(${(1-g)*-230}px) rotate(${(1-cl(g,0,1))*6}deg)`;
  // diagrama: 1 RESULTADO ⇢ TODAS AS MARCADAS (POSITIVAS ■■■■■ | NEGATIVAS ■■), seta tracejada a 12 qps
  const D0=EP.diag[0],D1=EP.diag[1];
  if(t>=D0-0.05&&t<D1+0.3){const pe=oc(lin(t,D0,D0+0.45)),ps=iq(lin(t,D1,D1+0.3));
    const bA=cl(mola(t-D0-0.05,12,.55),0,1.15),bB=cl(mola(t-a('todas')+0.25,12,.55),0,1.15),pa=io(lin(t,a('resultadoVale')-0.1,a('resultadoVale')+0.5));
    const w=(Math.floor(t*12)%3)-1,off=(Math.floor(t*12)%6)*4;
    const fp=io(lin(t,a('positivo')-0.35,a('positivo')+0.1));   // "positivo": as positivas ganham força, as negativas esmaecem
    X(K.diag,`<div class="abs" style="left:0;top:2px;width:330px;height:132px;background:#FBF6E8;border:6px solid ${IN};box-shadow:6px 8px 0 rgba(26,38,56,.25);transform:scale(${bA}) rotate(-1.5deg)"><div class="abs" style="left:18px;top:12px;font:800 62px/1 Archivo;color:${IN}">1</div><div class="abs" style="left:66px;top:28px;font:800 36px/1 Archivo;color:${IN};white-space:nowrap">RESULTADO</div><div class="abs" style="left:18px;top:90px;font:700 25px/1 Inter,Archivo;color:#4b4034;white-space:nowrap">um só, para o grupo</div></div>
     <svg class="abs" style="left:338px;top:6px;clip-path:inset(0 ${(1-pa)*100}% 0 0)" width="136" height="130" viewBox="0 0 136 130"><path d="M${6+w} ${65+w} L${108-w} ${65-w}" stroke="${IN}" stroke-width="10" stroke-linecap="round" stroke-dasharray="16 14" stroke-dashoffset="${-off}" fill="none"/><path d="M${92+w} ${40} L${120} ${65-w} L${92-w} ${90}" stroke="${IN}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>
     <div class="abs" style="left:480px;top:2px;width:440px;height:132px;background:#FBF6E8;border:6px solid ${IN};box-shadow:6px 8px 0 rgba(26,38,56,.25);transform:scale(${bB}) rotate(1.2deg)"><div class="abs" style="left:14px;top:8px;font:800 25px/1 Archivo;color:${IN};letter-spacing:.04em;white-space:nowrap">TODAS AS MARCADAS</div>
      <div class="abs" style="left:12px;top:42px;width:222px;height:78px;border:4px solid #1E6FA8;background:rgba(30,111,168,${.08+.1*fp});transform:scale(${1+.05*fp})"><div style="margin:7px 0 0 10px;font:800 24px/1 Archivo;color:#1E6FA8">POSITIVAS</div><div style="margin:7px 0 0 10px;white-space:nowrap;height:30px">${quad(5,'#1E6FA8',t-a('todas')-0.2)}</div></div>
      <div class="abs" style="left:246px;top:42px;width:172px;height:78px;border:4px solid #2E7D52;background:rgba(46,125,82,.08);opacity:${1-.55*fp}"><div style="margin:7px 0 0 10px;font:800 24px/1 Archivo;color:#2E7D52">NEGATIVAS</div><div style="margin:7px 0 0 10px;white-space:nowrap;height:30px">${quad(2,'#2E7D52',t-a('todas')-0.7)}</div></div></div>`);
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
   <div class="abs" data-z="1" style="left:80px;top:360px;font:800 230px/1 Archivo;color:#1A2638;letter-spacing:-.02em;text-transform:uppercase"><span style="position:relative;display:inline-block;z-index:0">Parto<i style="position:absolute;left:-10px;right:-14px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div>
   <div class="abs" data-z="2" style="left:80px;top:850px;width:380px;height:380px;background:#fff;box-shadow:0 26px 50px rgba(50,32,8,.3);display:flex;align-items:center;justify-content:center">${cow(250,'#1A2638',0.9)}</div>
   <div class="abs" data-z="3" style="left:510px;top:870px;width:490px"><div style="font:800 84px/1 Archivo;color:#1A2638;letter-spacing:-.02em">COW<span style="color:#8A5A12">DATA</span></div><div style="margin-top:28px;font:800 46px/1.1 Archivo;color:#1A2638;text-transform:uppercase">O rebanho na mão de <span style="position:relative;display:inline-block;z-index:0">quem cuida<i style="position:absolute;left:-8px;right:-10px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div></div>
   <div class="fita" data-z="4" style="left:90px;top:1330px;font-size:37px;letter-spacing:.05em">Ep. 3 · <b>Diagnóstico de gestação</b></div>`);
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
EP.camadas=[[0,['piano','pad']],[a('emLancar'),['piano','pad','shaker']],[a('passoUm'),['piano','pad','baixo','shaker','bumbo_leve']],[a('atencao'),['piano','pad','baixo','shaker','bumbo','palma','piano_cheio']],
 [a('pronto')-0.2,['piano','pad','baixo','shaker','shaker16','bumbo','palma','piano_cheio','sino']],[a('aReconfirmar')+0.9,['piano','pad','baixo','shaker','bumbo_leve']],[tCapa,['piano','pad','baixo','shaker','bumbo_leve','sino']]];
return EP;})()
