(()=>{const a=A;const EP={};const SB=30;
// ---- Ep. 7 · Produção › Pesagem corporal (por lote) e Secagem. Telas = capturas do app real (captura/capturar_t2e7.mjs). ----
// bt = caixa no conteúdo (coord. da página rolada a 0 nas capturas altas; viewport nas estáticas). As duas telas são tabelas LARGAS numa moldura com rolagem de lado:
// as caixas de colunas estão na posição "sem rolar" e as anotações recebem hx (estado cuja tabela rola) para acompanhar o arrasto (EP.hscroll).
const bt=(n,k)=>{const m=MAPA[n];return(m.tall&&m.tall.alvos[k])||m.alvos[k];};
const mx=n=>{const m=MAPA[n];return m.tall?Math.max(0,m.tall.h-69-m.barTop):0;};
const seg=pts=>t=>{if(t<=pts[0][0])return pts[0][1];for(let i=0;i<pts.length-1;i++){const[a0,v0]=pts[i],[a1,v1]=pts[i+1];if(t<a1)return L(v0,v1,io(lin(t,a0,a1)));}return pts[pts.length-1][1];};
const F=TL.frases;
// frases (índices): 0 F1 · 1 F2 · 2 F3 · 3 F4a "Digite…" · 4 F4b "O app mostra…" · 5 F5a "Quem perdeu…" · 6 F5b "Confira…" · 7 F6 · 8 F7a · 9 F7b "Marque…" · 10 F8 · 11 F9a · 12 F9b · 13 F10a "Toque em Salvar." · 14 F10b · 15 F11 · 16 F12
// ---- tempos (tudo ancorado nas palavras da locução) ----
const tProd=a('producao')+0.1,tPes=a('pesagem')+0.1,tPL=a('porLote2')+0.15,tL6=a('novilhas')+0.1;
const tTap=[0,1,2,3].map(i=>a('digite')+0.35+0.65*i);                    // 4 pesos digitados (um por animal), espaçados >= 0,65 s para o dedo caber
const tSave=a('salvar')+0.05,tVolta=a('volte')+0.45,tSecB=a('secagemBtn')+0.05;
const tK1=a('marque2')+0.1,tK2=tK1+0.7,tDate=a('data')+0.2,tMot=a('motivo')+0.1,tEcc=a('obrigatorio')+0.8;
const tAdd1=a('acrescente')+0.15,tFill1=tAdd1+0.85,tAdd2=tFill1+0.9,tFill2=tAdd2+0.9,tSave2=a('salvar2')+0.05;
const tM1=a('loteSecas')+0.05,tM2=tM1+0.95,tCapa=a('proximo')-0.15;
const cT={prod:tProd+0.1,pes:tPes+0.1,lote:tL6+0.12,w:tTap.map(t=>t+0.12),salvo:tSave+0.3,g2:tVolta+0.12,q2:tSecB+0.12,m1:tK1+0.12,m2:tK2+0.12,dt:tDate+0.2,mo:tMot+0.2,ec:tEcc+0.2,
 a1:tAdd1+0.15,f1:tFill1+0.2,a2:tAdd2+0.15,f2:tFill2+0.2,s1:tSave2+0.75,s2:tM1+0.15,s3:tM2+0.15};
EP.imgs={lancar:'s01_lancar',grade:'s02_prod_grade',p3:'p03_pesagem',p4:'p04_lote',p5:'p05_peso1',p6:'p06_peso2',p7:'p07_peso3',p8:'p08_peso4',p9:'p09_salvo',
 g2:'q01_grade',q2:'q02_secagem',q3:'q03_marca1',q4:'q04_marca2',q5:'q05_data',q6:'q06_motivo',q7:'q07_ecc',q8:'q08_prod_novo',q9:'q09_prod1',q10:'q10_prod2_novo',q11:'q11_prod2',
 q12:'q12_salvo',q13:'q13_mov1',q14:'q14_mov2'};
// [t, id, dir, 1 = troca só de estado (as anotações continuam), dissolvência em s]
EP.telas=[[0,'lancar',0],[cT.prod,'grade',1],[cT.pes,'p3',1],[cT.lote,'p4',0,1],[cT.w[0],'p5',0,1],[cT.w[1],'p6',0,1],[cT.w[2],'p7',0,1],[cT.w[3],'p8',0,1],[cT.salvo,'p9',0,1],
 [cT.g2,'g2',-1],[cT.q2,'q2',1],[cT.m1,'q3',0,1],[cT.m2,'q4',0,1],[cT.dt,'q5',0,1],[cT.mo,'q6',0,1],[cT.ec,'q7',0,1],[cT.a1,'q8',0,1],[cT.f1,'q9',0,1],[cT.a2,'q10',0,1],[cT.f2,'q11',0,1],
 [cT.s1,'q12',0,1,0.25],[cT.s2,'q13',0,1],[cT.s3,'q14',0,1]];
// ---- rolagem vertical (px CSS do app; cada estado limita ao próprio máximo) ----
const rA=seg([[0,0],[tPes+0.9,0],[a('modalidade')-0.25,300],[a('porLote2')+0.4,300],[a('marque')-0.3,700],[a('digite')-0.75,700],[a('digite')-0.1,880],[a('confira')-0.05,880],[a('salvar')-0.1,1480]]);
const rP9=seg([[cT.salvo+0.05,1480],[cT.salvo+0.7,1536],[a('agora')+0.4,1536],[a('volte')+0.1,0]]);   // o retorno aumenta a barra: mais 56 px de rolagem; depois sobe até o Voltar
const rB=seg([[0,0],[a('passoUm')+0.15,0],[a('passoUm')+1.0,380],[a('prevista')-0.6,380],[a('prevista')-0.1,440],[a('passoDois')-0.35,440],[a('passoDois')+0.65,1100],
 [a('antibiotico')-0.95,1100],[a('antibiotico')-0.1,1440],[tFill2+0.3,1440],[tSave2-0.9,1440],[tSave2-0.1,1728]]);
EP.rolagem={p3:rA,p4:rA,p5:rA,p6:rA,p7:rA,p8:rA,p9:rP9,q2:rB,q3:rB,q4:rB,q5:rB,q6:rB,q7:rB,q8:rB,q9:rB,q10:rB,q11:rB,q12:()=>1e6,q13:()=>1e6,q14:()=>1e6};
// ---- rolagem de lado da moldura da tabela (px CSS da tabela; cada estado limita ao próprio S) ----
const hsA=seg([[0,0],[a('digite')-0.4,0],[a('digite')+0.1,270],[a('mostra')-0.3,270],[a('mostra')+0.4,562]]);   // 270 = "Peso novo" à vista · 562 = Ganho / GMD / Situação
const hsB=seg([[0,0],[a('prevista')-0.45,0],[a('prevista')+0.15,134],[a('marque2')-0.9,134],[a('marque2')-0.25,0]]);   // 134 = Dias de gestação, Secagem prevista e Situação à vista (as 3 colunas inteiras)
const hsP=seg([[0,0],[tFill2+0.5,0],[tFill2+1.2,752]]);                                                                // 752 = Total da aplicação e Estoque depois
EP.hscroll={p4:hsA,p5:hsA,p6:hsA,p7:hsA,p8:hsA,q2:hsB,q11:hsP};
const S=(id,t)=>cl(EP.rolagem[id](t),0,mx(EP.imgs[id]));
const H=(id,t)=>{const f=EP.hscroll[id];return f?cl(f(t),0,MAPA[EP.imgs[id]].hz.S):0;};
const cx=b=>b.x+b.w/2,cy=b=>b.y+b.h/2;
// ---- toques: [t, x, y] em coordenadas da tela do celular (CSS) já com a barra de status (+30) ----
const ST=['p4','p5','p6','p7'];                                         // estado visível em cada digitação
const bIn=i=>bt('p04_lote','r'+i+'in');
const bSecBlk=bt('q01_grade','secagem'),bProd=bt('s01_lancar','prod'),bPes=bt('s02_prod_grade','pesagem'),bLoteMod=bt('p03_pesagem','mLote'),bL6=bt('p03_pesagem','lote06'),
 bSalA=bt('p08_peso4','salvar'),bVolt=bt('p09_salvo','voltar'),bC1=bt('q02_secagem','r2305c'),bC2=bt('q02_secagem','r3338c'),bDate=bt('q04_marca2','data'),bMot=bt('q05_data','motivo'),
 bEcc=bt('q06_motivo','ecc'),bAcr=bt('q07_ecc','acrescentar'),bP1=bt('q08_prod_novo','p1prod'),bAcr2=bt('q09_prod1','acrescentar'),bP2=bt('q10_prod2_novo','p2prod'),
 bSal2=bt('q11_prod2','salvar'),bSim1=bt('q12_salvo','sim'),bSim2=bt('q13_mov1','sim');
EP.toques=[
 [tProd,cx(bProd),cy(bProd)+SB],[tPes,cx(bPes),cy(bPes)+SB],
 [tPL,cx(bLoteMod),cy(bLoteMod)-S('p3',tPL)+SB],[tL6,cx(bL6),cy(bL6)-S('p3',tL6)+SB],
 ...tTap.map((t,i)=>[t,cx(bIn(i))-H(ST[i],t),cy(bIn(i))-S(ST[i],t)+SB]),
 [tSave,cx(bSalA),cy(bSalA)-S('p8',tSave)+SB],[tVolta,cx(bVolt),cy(bVolt)-S('p9',tVolta)+SB],[tSecB,cx(bSecBlk),cy(bSecBlk)+SB],
 [tK1,cx(bC1)-H('q2',tK1),cy(bC1)-S('q2',tK1)+SB],[tK2,cx(bC2)-H('q2',tK2),cy(bC2)-S('q2',tK2)+SB],
 [tDate,cx(bDate)-60,cy(bDate)-S('q4',tDate)+SB],[tMot,cx(bMot)-40,cy(bMot)-S('q5',tMot)+SB],[tEcc,cx(bEcc)-60,cy(bEcc)-S('q6',tEcc)+SB],
 [tAdd1,cx(bAcr),cy(bAcr)-S('q7',tAdd1)+SB],[tFill1,cx(bP1),cy(bP1)-S('q8',tFill1)+SB],[tAdd2,cx(bAcr2),cy(bAcr2)-S('q9',tAdd2)+SB],[tFill2,cx(bP2),cy(bP2)-S('q10',tFill2)+SB],
 [tSave2,cx(bSal2),cy(bSal2)-S('q11',tSave2)+SB],[tM1,cx(bSim1),cy(bSim1)-S('q12',tM1)+SB],[tM2,cx(bSim2),cy(bSim2)-S('q13',tM2)+SB]];
// ---- câmera: [t de chegada, duração, cx, cy, zoom] (coords da tela do celular com +30). Visível: de cy-189/z a cy+349/z. Zoom ≤ 1,18 e centrado ----
EP.cam=[[0,0,195,300,1.0],[a('emLancar')+0.3,1.0,195,380,1.12],[tProd+0.45,0.9,195,360,1.1],
 [tPes+0.45,0.9,195,470,1.0],[a('modalidade')-0.55,0.8,195,400,1.08],[a('porLote2')+0.25,0.7,195,400,1.0],
 [a('digite')-0.8,0.8,195,500,1.0],[a('confira')-0.05,0.8,195,600,1.0],[a('agora')+0.35,0.9,195,600,1.0],
 [a('volte')-0.2,0.9,195,380,1.1],[tSecB+0.4,0.8,195,400,1.1],[cT.q2+0.5,0.9,195,450,1.0],
 [a('passoUm')+0.85,0.8,195,370,1.0],[a('prevista')-0.55,0.7,195,520,1.0],[a('passoDois')+0.3,0.8,195,430,1.0],
 [a('antibiotico')-0.9,0.8,195,520,1.0],[tSave2-0.9,0.8,195,600,1.0],[cT.s1-0.1,0.6,195,570,1.0]];
// ---- anotações: [t0,t1,tipo,x,y,w,h,{c,scr,hx}] ----
const V='#2E7D52',Z='#1E6FA8',D='#E0A63C',IN='#1A2638',RD='#B3392F';
const bx=(n,k,o={})=>{const b=bt(n,k);return[b.x,b.y,b.w,b.h,o];};
// coluna inteira (cabeçalho + as 4 linhas digitadas) da tabela de pesagem / (cabeçalho + 3 linhas) da lista de secagem / (cabeçalho + 2 produtos)
const colP=(k,o)=>{const h=bt('p08_peso4','th'+k),b=bt('p08_peso4','r3sit');return[h.x,h.y,h.w,b.y+b.h-h.y,o];};
const colS=(k,o)=>{const h=bt('q02_secagem','th'+k),b=bt('q02_secagem','r3013prev');return[h.x,h.y,h.w,b.y+b.h-h.y,o];};
const colE=o=>{const h=bt('q11_prod2','thEst'),b=bt('q11_prod2','p2est');return[h.x,h.y,h.w,b.y+b.h-h.y,o];};
EP.anot=[
 [a('toqueProd')+0.1,tProd+0.1,'caixa',...bx('s01_lancar','prod',{c:V})],
 [a('leite')-0.15,tPes+0.1,'caixa',...bx('s02_prod_grade','pesagem',{c:V})],
 [a('porAnimal')-0.1,a('porLote')-0.15,'caixa',...bx('p03_pesagem','mAnimal',{c:V,scr:'p3'})],
 [a('porLote')-0.1,a('planilha')-0.15,'caixa',...bx('p03_pesagem','mLote',{c:Z,scr:'p3'})],
 [a('planilha')-0.1,a('aqui')-0.05,'caixa',...bx('p03_pesagem','mPlan',{c:D,scr:'p3'})],
 [a('porLote2')-0.1,tPL+0.1,'caixa',...bx('p03_pesagem','mLote',{c:V,scr:'p3'})],
 [a('marque')-0.1,tL6+0.05,'caixa',...bx('p03_pesagem','lote06',{c:V,scr:'p3'})],
 [a('digite')+0.05,tTap[3]+0.2,'caixa',...bx('p04_lote','thPesoNovo',{c:D,scr:'p4',hx:'p4'})],
 [a('ganho')-0.1,a('gmd')-0.1,'caixa',...colP('Ganho',{c:V,scr:'p8',hx:'p8'})],
 [a('gmd')-0.1,a('perdeu')-0.3,'caixa',...colP('Gmd',{c:D,scr:'p8',hx:'p8'})],
 [a('ganhoMedio')-0.2,a('perdeu')-0.35,'marca',...bx('p08_peso4','thGmd',{c:D,scr:'p8',hx:'p8'})],
 [a('perdeu')-0.15,a('confira')+0.25,'caixa',...bx('p08_peso4','r2selo',{c:RD,scr:'p8',hx:'p8'})],
 [a('salvar')-0.25,tSave+0.05,'caixa',...bx('p08_peso4','salvar',{c:D,scr:'p8'})],
 [cT.salvo+0.05,a('agora')+0.4,'caixa',...bx('p09_salvo','retorno',{c:V,scr:'p9'})],
 [a('toqueSec')-0.1,tSecB+0.05,'caixa',...bx('q01_grade','secagem',{c:V})],
 [a('volte')-0.05,tVolta+0.05,'caixa',...bx('p09_salvo','voltar',{c:Z,scr:'p9'})],
 [a('ate30')-0.1,a('prevista')-0.65,'caixa',...bx('q02_secagem','ate30',{c:V,scr:'q2'})],
 [a('prevista')-0.15,a('marque2')-0.95,'caixa',...colS('Prev',{c:D,scr:'q2',hx:'q2'})],
 [tK1-0.5,tK1+0.05,'caixa',...bx('q02_secagem','r2305c',{c:V,scr:'q2'})],
 [tK2-0.45,tK2+0.05,'caixa',...bx('q02_secagem','r3338c',{c:V,scr:'q2'})],
 [a('passoDois')+0.35,tDate+0.3,'caixa',...bx('q04_marca2','campoData',{c:V,scr:'q4'})],
 [a('motivo')-0.1,a('obrigatorio')-0.2,'caixa',...bx('q05_data','campoMotivo',{c:Z,scr:'q5'})],
 [a('obrigatorio')-0.15,a('obrigatorio')+1.1,'marca',...bx('q06_motivo','rotMotivo',{c:D,scr:'q6'})],
 [a('acrescente')-0.25,tAdd1+0.05,'caixa',...bx('q07_ecc','acrescentar',{c:D,scr:'q7'})],
 [tAdd2-0.4,tAdd2+0.05,'caixa',...bx('q09_prod1','acrescentar',{c:D,scr:'q9'})],
 [cT.f2+0.9,tSave2-1.0,'caixa',...colE({c:D,scr:'q11',hx:'q11'})],
 [a('toqueSalvar2')+0.15,tSave2+0.05,'caixa',...bx('q11_prod2','salvar',{c:D,scr:'q11'})],
 [cT.s1+0.05,a('loteSecas')-0.2,'caixa',...bx('q12_salvo','sugerido',{c:V,scr:'q12'})],
 [a('loteSecas')-0.15,tM1+0.05,'caixa',...bx('q12_salvo','sim',{c:D,scr:'q12'})],
 [cT.s2+0.05,tM2+0.05,'caixa',...bx('q13_mov1','sim',{c:D,scr:'q13'})],
 [cT.s3+0.05,cT.s3+0.55,'caixa',...bx('q14_mov2','retorno',{c:V,scr:'q14'})]
];
EP.fitas=[[a('fita1')-0.1,a('emLancar')+0.1,'Pesagem <b>e secagem</b>',110,298,-2],
 [a('agora')-0.1,a('volte')-0.4,'Parte 2 · <b>Secagem</b>',110,298,-1.5]];
EP.titulos=[[0,'Temporada 2 · <m>Ep. 7</m>'],[a('emLancar')-0.1,'Em Lançar: <m>Produção</m>'],[a('leite')-0.2,'Depois, <m>Pesagem corporal</m>'],
 [a('modalidade')-0.1,'Modalidade: <m>Por lote</m>'],[a('marque')-0.1,'Marque o <m>lote</m> das novilhas'],[a('digite')-0.1,'Digite o <m>peso novo</m>'],
 [a('perdeu')-0.1,'Perdeu peso? <m>Aviso</m>'],[a('confira')-0.1,'Confira e toque em <m>Salvar</m>'],
 [a('volte')-0.1,'Volte e toque em <m>Secagem</m>'],
 [a('passoUm')-0.1,'Passo 1: <m>quais vacas</m>'],[a('ate30')-0.1,'Até <m>30 dias</m>'],[a('marque2')-0.1,'Marque as <m>vacas</m>'],
 [a('passoDois')-0.1,'Passo 2: <m>dados</m> da secagem'],[a('motivo')-0.1,'Motivo <m>obrigatório</m>'],[a('antibiotico')-0.1,'Passo 3: <m>produtos</m>'],
 [a('estoque')-0.1,'O <m>estoque</m> depois'],[a('toqueSalvar2')-0.1,'Toque em <m>Salvar</m>'],[a('sugere')-0.1,'Sugere o lote das <m>secas</m>'],
 [a('pronto')-0.1,'Feito: <m>lançado</m>']];
// diagramas Vox no papel: (A) GMD = ganho ÷ dias, com o exemplo real de uma linha, e seta tracejada até a coluna GMD; (B) mini-quadro "04 - Secas 22 → 24"
EP.diag=[a('ganho')-0.25,a('perdeu')-0.3];
const tCar=a('lancado'),tCarFim=a('proximo')-0.45,DQ=[cT.s3+0.3,tCar-0.35];
const L2=i=>[F[i][1],F[i][2],F[i][0]];
EP.leg=[L2(0),[F[1][1],a('leite')+0.5,'Em Lançar, toque em Produção, Leite,'],[a('leite')+0.5,F[1][2],'e depois em Pesagem corporal.'],
 [F[2][1],a('aqui')-0.25,'Em Modalidade, escolha Por animal, Por lote, ou Planilha.'],[a('aqui')-0.25,F[2][2],'Aqui, Por lote: marque o lote das novilhas.'],
 L2(3),L2(4),L2(5),L2(6),L2(7),L2(8),L2(9),
 [F[10][1],a('obrigatorio')-0.2,'No passo dois, confira a data, e escolha o motivo,'],[a('obrigatorio')-0.2,F[10][2],'que é obrigatório.'],
 L2(11),[F[12][1],F[12][2],'O app mostra como fica o estoque.'],L2(13),L2(14),L2(15)];
EP.fimLeg=tCapa;EP.shake=a('lancado');
EP.entrada=t=>{const p=mola(t-0.3,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
EP.oculta=[[tCar,tCarFim],[EP.diag[1],EP.diag[1]+0.36],[a('fita1')-0.1,a('emLancar')+0.4],[a('agora')-0.1,a('volte')-0.1],[DQ[0],tCarFim]];
EP.estado=(t,{K,io,oc,lin,mola,L,cl,ob,ic,cow,X,iq})=>{
  K.dymo.style.transform=`translateX(${(1-cl(mola(t-0.55,9,.55),0,1.15))*-1000}px) rotate(-1.6deg)`;
  const g=cl(mola(t-0.15,10,.5),0,1.2);K.grampo.style.transform=`translateY(${(1-g)*-230}px) rotate(${(1-cl(g,0,1))*6}deg)`;
  // diagrama A: GMD = ganho ÷ dias  ·  18 kg ÷ 30 d = 0,60 kg/dia (a linha da 1ª novilha); seta tracejada a 12 qps até o GMD da tabela
  const D0=EP.diag[0],D1=EP.diag[1];let desenhado=false;
  if(t>=D0-0.05&&t<D1+0.3){desenhado=true;const pe=oc(lin(t,D0,D0+0.45)),ps=iq(lin(t,D1,D1+0.3));const w=(Math.floor(t*12)%3)-1;
    const t1=D0+0.02,t2=a('gmd')+0.25,tk=a('ganhoMedio')+0.2;
    const a1=oc(lin(t,t1,t1+0.4)),a2=oc(lin(t,t2,t2+0.4)),ck=mola(t-tk,13,.5),ul=io(lin(t,t1+0.35,t1+0.85));
    let sv='';
    const[cxm,cym,zz]=camera(t);const b=bt('p08_peso4','r0gmd');const scr=S('p8',t),hs=H('p8',t);
    const fx=540+((b.x+b.w/2-hs)-cxm)*U*zz-80,fy=FY+((b.y+b.h/2-scr+SB)-cym)*U*zz-286;
    const pa=io(lin(t,a('gmd')-0.1,a('ganhoMedio')-0.1)),ta=1-iq(lin(t,a('ganhoMedio')+0.5,a('ganhoMedio')+0.9));
    if(pa>0&&ta>0){const x0=900,y0=150,x1=L(x0,fx,pa),y1=L(y0,fy-20,pa);sv+=`<path d="M${x0} ${y0+w} L${x1} ${y1-w}" stroke="#1E6FA8" stroke-width="8" stroke-linecap="round" stroke-dasharray="4 16" fill="none" opacity="${ta}"/>`;}
    sv+=`<g opacity="${a1}" transform="translate(${(1-a1)*-40} 0)"><text x="10" y="54" font-family="Archivo" font-weight="800" font-size="58" fill="${IN}">GMD = ganho ÷ dias</text>`;
    if(ul>0)sv+=`<path d="M10 ${66+w} L${L(10,520,ul)} ${64-w}" stroke="#E0A63C" stroke-width="9" stroke-linecap="round" fill="none" opacity=".9"/>`;
    sv+=`</g><g opacity="${a2}" transform="translate(${(1-a2)*-40} 0)"><text x="10" y="120" font-family="Archivo" font-weight="800" font-size="52" fill="${IN}">18 kg ÷ 30 d = 0,60 kg/dia</text>`;
    const c2=cl(mola(t-tk-0.1,13,.5),0,1.2);
    if(c2>0)sv+=`<g transform="translate(850 98) scale(${c2})"><path d="M-26 2 L-8 22 L28 -24" stroke="#2E7D52" stroke-width="12" stroke-linecap="round" stroke-linejoin="round" fill="none"/></g>`;
    sv+=`</g>`;
    X(K.diag,`<svg width="920" height="140" viewBox="0 0 920 140" style="overflow:visible">${sv}</svg>`);
    K.diag.style.display='block';K.diag.style.opacity=1-ps;K.diag.style.transform=`translateY(${(1-pe)*-170+ps*-120}px)`;}
  // diagrama B: mini-quadro do lote — 04 - Secas 22 → 24 (as duas vacas movidas)
  else if(t>=DQ[0]-0.05&&t<DQ[1]+0.3){desenhado=true;const pe=oc(lin(t,DQ[0],DQ[0]+0.4)),ps=iq(lin(t,DQ[1],DQ[1]+0.3));const w=(Math.floor(t*12)%3)-1;
    const a1=oc(lin(t,DQ[0]+0.05,DQ[0]+0.45)),a2=oc(lin(t,DQ[0]+0.35,DQ[0]+0.75)),ck=mola(t-DQ[0]-0.7,13,.5);
    let sv=`<g opacity="${a1}" transform="translate(${(1-a1)*-40} 0)"><text x="10" y="56" font-family="Archivo" font-weight="800" font-size="58" fill="${IN}">04 - Secas</text></g>`;
    sv+=`<g opacity="${a2}" transform="translate(${(1-a2)*-40} 0)"><text x="470" y="56" font-family="Archivo" font-weight="800" font-size="58" fill="#4b4034">22</text>`
      +`<path d="M548 ${34+w} L640 ${34-w}" stroke="#1E6FA8" stroke-width="8" stroke-linecap="round" fill="none"/><path d="M618 ${14+w} L644 ${34} L618 ${54-w}" stroke="#1E6FA8" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`
      +`<text x="670" y="56" font-family="Archivo" font-weight="800" font-size="72" fill="#2E7D52">24</text></g>`;
    sv+=`<g opacity="${a2}" transform="translate(${(1-a2)*-40} 0)"><text x="10" y="118" font-family="Archivo" font-weight="700" font-size="34" fill="#4b4034">as duas vacas secas entram no lote</text></g>`;
    const c2=cl(ck,0,1.2);if(c2>0)sv+=`<g transform="translate(860 84) scale(${c2})"><path d="M-26 2 L-8 22 L28 -24" stroke="#2E7D52" stroke-width="12" stroke-linecap="round" stroke-linejoin="round" fill="none"/></g>`;
    X(K.diag,`<svg width="920" height="140" viewBox="0 0 920 140" style="overflow:visible">${sv}</svg>`);
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
   <div class="abs" data-z="1" style="left:80px;top:350px;font:800 250px/1 Archivo;color:#1A2638;letter-spacing:-.02em;text-transform:uppercase"><span style="position:relative;display:inline-block;z-index:0">BST<i style="position:absolute;left:-10px;right:-14px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div>
   <div class="abs" data-z="2" style="left:80px;top:870px;width:380px;height:380px;background:#fff;box-shadow:0 26px 50px rgba(50,32,8,.3);display:flex;align-items:center;justify-content:center">${cow(250,'#1A2638',0.9)}</div>
   <div class="abs" data-z="3" style="left:510px;top:890px;width:490px"><div style="font:800 84px/1 Archivo;color:#1A2638;letter-spacing:-.02em">COW<span style="color:#8A5A12">DATA</span></div><div style="margin-top:28px;font:800 46px/1.1 Archivo;color:#1A2638;text-transform:uppercase">O rebanho na mão de <span style="position:relative;display:inline-block;z-index:0">quem cuida<i style="position:absolute;left:-8px;right:-10px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div></div>
   <div class="fita" data-z="4" style="left:90px;top:1350px">Ep. 7 · <b>Pesagem e secagem</b></div>`);
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
EP.sfx.push([EP.diag[0],'rasgo'],[DQ[0],'rasgo'],[tCapa,'whoosh'],[tCapa+2.5,'rasgo'],[EP.shake,'carimbo']);
EP.sfx.sort((p,q)=>p[0]-q[0]);
EP.camadas=[[0,['piano','pad']],[a('emLancar'),['piano','pad','shaker']],[a('modalidade'),['piano','pad','baixo','shaker','bumbo_leve']],[a('agora'),['piano','pad','baixo','shaker','bumbo','palma','piano_cheio']],
 [a('pronto')-0.2,['piano','pad','baixo','shaker','shaker16','bumbo','palma','piano_cheio','sino']],[a('proximo')-0.6,['piano','pad','baixo','shaker','bumbo_leve']],[tCapa,['piano','pad','baixo','shaker','bumbo_leve','sino']]];
return EP;})()
