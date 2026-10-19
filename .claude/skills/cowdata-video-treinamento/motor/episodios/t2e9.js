(()=>{const a=A;const EP={};const SB=30;
// ---- Ep. 9 · Sanidade › aplicação de medicamentos (Curativa › Aplicação de remédio; Preventiva › Aplicação). Telas = capturas do app real (captura/capturar_t2e9.mjs). ----
// Formulários de UM animal / um lote, sem barra fixa (barTop = topo da navegação): a rolagem é contínua dentro de cada captura alta. O seletor de produto é um modal estático (position:fixed).
// bt = caixa no conteúdo (coord. da página rolada a 0 nas capturas altas; viewport nas estáticas). Cada estado tem o próprio máximo de rolagem; a troca de estado é dissolvida (0,18 s).
const bt=(n,k)=>{const m=MAPA[n];return(m.tall&&m.tall.alvos[k])||m.alvos[k];};
const mx=n=>{const m=MAPA[n];return m.tall?Math.max(0,m.tall.h-69-m.barTop):0;};
const seg=pts=>t=>{if(t<=pts[0][0])return pts[0][1];for(let i=0;i<pts.length-1;i++){const[a0,v0]=pts[i],[a1,v1]=pts[i+1];if(t<a1)return L(v0,v1,io(lin(t,a0,a1)));}return pts[pts.length-1][1];};
const F=TL.frases;
// frases: 0 título · 1 Em Lançar, toque em Sanidade · 2 Escolha Curativa… · 3 Na Curativa, toque em Aplicação de remédio · 4 e busque o animal · 5 Em Filtrar…escolha Doença · 6 e depois Mastite…indicados
// · 7 Se o remédio estiver em falta, o app avisa · 8 e sugere um substituto… · 9 Informe a dose, a unidade e a via · 10 e toque em Salvar · 11 Na Preventiva · 12 toque em Aplicação, e escolha o evento…vacina
// · 13 Aplique em um animal · 14 ou no lote inteiro · 15 Pronto, lançado · 16 próximo episódio
const s=i=>F[i][1],e=i=>F[i][2];
// ---- tempos (tudo ancorado nas palavras da locução) ----
const tSan=a('sanidade')+0.1,tCur=a('naCurativa')+0.1,tApl=a('aplicRemedio')+0.15,
 tDigTap=a('busque')+0.05,tDig=tDigTap+0.45,tSelAn=e(4)+0.4,
 tDoe=a('doenca')+0.05,tMas=a('mastite')+0.1,tPick=a('mastite')+0.85,tCef=a('falta')-0.45,tUsar=a('estoque')+0.15,
 tDose=a('dose')+0.1,tUn=a('unidade')+0.1,tVia=a('via')+0.1,tResp=e(9)+0.25,tSalv=a('salvar')+0.05,
 tB1=tSalv+2.1,tB2=tSalv+2.8,tPrev=a('naPreventiva')+0.1,tAplP=a('aplicacao')+0.1,tEv=a('evento')+0.1,
 tLoteP=a('loteInteiro')+0.05,tLoteSel=e(14)-0.35,tSalvP=e(14)+0.55;
const cT={grade:tSan+0.12,cur:tCur+0.12,form:tApl+0.12,dig:tDig,an:tSelAn+0.12,doe:tDoe+0.12,mas:tMas+0.12,pick:tPick+0.12,baixo:tCef+0.12,usar:tUsar+0.12,dose:tDose+0.1,un:tUn+0.1,via:tVia+0.1,resp:tResp+0.1,
 salvo:tSalv+0.5,v1:tB1+0.12,v2:tB2+0.12,pgrade:tPrev+0.12,pform:tAplP+0.12,pev:tEv+0.12,plote:tLoteP+0.12,plote2:tLoteSel+0.12,psalvo:tSalvP+0.5};
const tCapa=a('proximo')-0.15;
EP.imgs={lancar:'s01_lancar',grade:'s02_grade',cur:'s03_curativa',form:'s04_form',dig:'s05_digitado',an:'s06_animal',doe:'s07_doenca',mas:'s08_mastite',pick:'s09_picker',baixo:'s10_baixo',usar:'s11_usar',
 dose:'s12_dose',un:'s13_unidade',via:'s14_via',resp:'s15_resp',salvo:'s16_salvo',v1:'s17_volta1',v2:'s18_volta2',pgrade:'p01_grade',pform:'p02_form',pev:'p03_evento',plote:'p04_lote',plote2:'p05_lote02',psalvo:'p06_salvo'};
// [t, tela, direção (1 = desliza da direita, -1 = da esquerda: voltar), 1 = só troca de estado (as anotações continuam), dissolvência em s]
const DF=0.18;
EP.telas=[[0,'lancar',0],[cT.grade,'grade',1],[cT.cur,'cur',1],[cT.form,'form',1],[cT.dig,'dig',0,1,0.12],[cT.an,'an',0,1,DF],[cT.doe,'doe',0,1,DF],[cT.mas,'mas',0,1,DF],[cT.pick,'pick',0,1,DF],[cT.baixo,'baixo',0,1,DF],
 [cT.usar,'usar',0,1,DF],[cT.dose,'dose',0,1,0.1],[cT.un,'un',0,1,0.1],[cT.via,'via',0,1,0.1],[cT.resp,'resp',0,1,0.1],[cT.salvo,'salvo',0,1,DF],[cT.v1,'v1',-1],[cT.v2,'v2',-1],
 [cT.pgrade,'pgrade',1],[cT.pform,'pform',1],[cT.pev,'pev',0,1,DF],[cT.plote,'plote',0,1,DF],[cT.plote2,'plote2',0,1,0.1],[cT.psalvo,'psalvo',0,1,DF]];
// ---- rolagem (px CSS do app; cada estado limita ao próprio máximo) ----
// Curativa: 0 → 160 ao escolher Doença (o seletor de produto fica à vista; a captura estática do seletor foi feita com a página em 160) → 400 quando aparece o aviso → 446 (dose…Salvar) → 503 (aviso do salvar) → 0 (os dois Voltar)
const SGc=seg([[0,0],[a('doenca')-0.3,0],[a('doenca')+0.2,160],[tCef+0.3,160],[tCef+1.1,400],[tUsar+0.4,400],[tUsar+1.1,446]]);
const SGs=seg([[0,446],[tSalv+0.45,446],[tSalv+0.8,503],[tSalv+1.35,503],[tSalv+1.9,0]]);
const SPf=seg([[0,0],[s(13)-0.2,0],[s(13)+0.5,178]]);
const SPs=seg([[0,178],[tSalvP+0.5,178],[tSalvP+0.9,235]]);
EP.rolagem={an:SGc,doe:SGc,mas:SGc,baixo:SGc,usar:SGc,dose:SGc,un:SGc,via:SGc,resp:SGc,salvo:SGs,pform:SPf,pev:SPf,plote:()=>178,plote2:()=>178,psalvo:SPs};
const S=(id,t)=>cl(EP.rolagem[id]?EP.rolagem[id](t):0,0,mx(EP.imgs[id]));
const cx=b=>b.x+b.w/2,cy=b=>b.y+b.h/2;
// ---- toques: [t, x, y] em coordenadas da tela do celular (CSS) já com a barra de status (+30) ----
const B=(n,k)=>bt(n,k);
const bSan=B('s01_lancar','san'),bCur=B('s02_grade','cur'),bApl=B('s03_curativa','apl'),bBusca=B('s04_form','busca'),bRes=B('s05_digitado','res'),
 bFil=B('s06_animal','filtroSel'),bCrit=B('s07_doenca','critSel'),bProd=B('s08_mastite','prodBtn'),bRcef=B('s09_picker','rCef'),bUsar=B('s10_baixo','usar'),
 bQtd=B('s11_usar','qtdIn'),bUn=B('s12_dose','unSel'),bVia=B('s13_unidade','viaSel'),bResp=B('s14_via','respSel'),bSalv=B('s15_resp','salvar'),
 bV1=B('s16_salvo','voltar2'),bV2=B('s17_volta1','v2'),bPrev=B('s18_volta2','prev'),bAplP=B('p01_grade','aplP'),bEv=B('p02_form','eventoSel'),bPL=B('p03_evento','pillL'),
 bLS=B('p04_lote','loteSel'),bSP=B('p05_lote02','salvar');
EP.toques=[
 [tSan,cx(bSan),cy(bSan)+SB],[tCur,cx(bCur),cy(bCur)+SB],[tApl,cx(bApl),cy(bApl)+SB],[tDigTap,cx(bBusca),cy(bBusca)+SB],[tSelAn,cx(bRes),cy(bRes)+SB],
 [tDoe,cx(bFil),cy(bFil)-S('an',tDoe)+SB],[tMas,cx(bCrit),cy(bCrit)-S('doe',tMas)+SB],[tPick,cx(bProd),cy(bProd)-S('mas',tPick)+SB],
 [tCef,cx(bRcef),cy(bRcef)+SB],[tUsar,cx(bUsar),cy(bUsar)-S('baixo',tUsar)+SB],
 [tDose,cx(bQtd),cy(bQtd)-S('usar',tDose)+SB],[tUn,cx(bUn),cy(bUn)-S('dose',tUn)+SB],[tVia,cx(bVia),cy(bVia)-S('un',tVia)+SB],[tResp,cx(bResp),cy(bResp)-S('via',tResp)+SB],
 [tSalv,cx(bSalv),cy(bSalv)-S('resp',tSalv)+SB],[tB1,cx(bV1),cy(bV1)-S('salvo',tB1)+SB],[tB2,cx(bV2),cy(bV2)+SB],[tPrev,cx(bPrev),cy(bPrev)+SB],[tAplP,cx(bAplP),cy(bAplP)+SB],
 [tEv,cx(bEv),cy(bEv)-S('pform',tEv)+SB],[tLoteP,cx(bPL),cy(bPL)-S('pev',tLoteP)+SB],[tLoteSel,cx(bLS),cy(bLS)-S('plote',tLoteSel)+SB],[tSalvP,cx(bSP),cy(bSP)-S('plote2',tSalvP)+SB]];
// ---- câmera: [t de chegada, duração, cx, cy, zoom] (coords da tela do celular com +30). Visível: de cy-189/z a cy+349/z. Zoom ≤ 1,18 e centrado ----
EP.cam=[[0,0,195,300,1.0],[a('emLancar')+0.4,1.0,195,440,1.1],[tSan+0.55,0.9,195,335,1.1],[tCur+0.55,0.8,195,345,1.1],[tApl+0.6,0.8,195,470,1.0],
 [tSelAn+0.7,0.9,195,490,1.0],[tPick+0.5,0.7,195,400,1.0],[tCef+0.55,0.9,195,500,1.0],[tUsar+0.6,0.9,195,520,1.0],
 [tSalv+1.9,0.55,195,345,1.0],[tPrev+0.5,0.8,195,345,1.1],[tAplP+0.6,0.8,195,470,1.0],[s(13)-0.15,0.9,195,520,1.0],[tSalvP+0.35,0.8,195,520,1.0]];
// ---- anotações: [t0,t1,tipo,x,y,w,h,{c,scr}] — somem exatamente no quadro da troca de tela seguinte (regra do motor) ----
const V='#2E7D52',Z='#1E6FA8',D='#E0A63C',IN='#1A2638',RD='#B3392F',AM='#C27B14';
const bx=(n,k,o={})=>{const b=bt(n,k);return[b.x,b.y,b.w,b.h,o];};
const bm=bt('p03_evento','medP'),bd=bt('p03_evento','dose');
EP.anot=[
 [a('sanidade')-0.7,tSan+0.1,'caixa',...bx('s01_lancar','san',{c:V})],
 [a('curativa')-0.2,a('doente')+1.2,'caixa',...bx('s02_grade','cur',{c:RD})],
 [a('preventiva')-0.2,e(2)+0.2,'caixa',...bx('s02_grade','prev',{c:V})],
 [a('naCurativa')-0.15,tCur+0.1,'caixa',...bx('s02_grade','cur',{c:RD})],
 [a('aplicRemedio')-0.25,tApl+0.1,'caixa',...bx('s03_curativa','apl',{c:Z})],
 [a('busque')-0.1,tDigTap+0.3,'caixa',...bx('s04_form','busca',{c:Z})],
 [tDig+0.15,tSelAn+0.1,'caixa',...bx('s05_digitado','res',{c:D})],
 [tSelAn+0.25,a('filtrar')-0.3,'caixa',...bx('s06_animal','animalSel',{c:V,scr:'an'})],
 [a('filtrar')-0.1,tDoe+0.1,'caixa',...bx('s06_animal','filtroSel',{c:D,scr:'an'})],
 [tDoe+0.3,tMas+0.1,'caixa',...bx('s07_doenca','critSel',{c:Z,scr:'doe'})],
 [tMas+0.3,tPick+0.1,'caixa',...bx('s08_mastite','prodBtn',{c:D,scr:'mas'})],
 [a('indicados')-0.15,tCef-0.05,'caixa',...bx('s09_picker','modTab',{c:V})],
 [a('avisa')-0.25,a('substituto')-0.2,'caixa',...bx('s10_baixo','banner',{c:AM,scr:'baixo'})],
 [a('substituto')-0.2,tUsar-0.6,'caixa',...bx('s10_baixo','dispLinha',{c:V,scr:'baixo'})],
 [tUsar-0.55,tUsar+0.1,'caixa',...bx('s10_baixo','usar',{c:D,scr:'baixo'})],
 [a('dose')-0.1,tUn+0.05,'caixa',...bx('s11_usar','qtdIn',{c:D,scr:'usar'})],
 [a('unidade')-0.1,tVia+0.05,'caixa',...bx('s12_dose','unSel',{c:Z,scr:'dose'})],
 [a('via')-0.1,tResp+0.05,'caixa',...bx('s13_unidade','viaSel',{c:V,scr:'un'})],
 [a('salvar')-0.25,tSalv+0.1,'caixa',...bx('s15_resp','salvar',{c:D,scr:'resp'})],
 [tSalv+0.85,tSalv+1.35,'caixa',...bx('s16_salvo','aviso',{c:V,scr:'salvo'})],
 [tSalv+1.85,tB1+0.1,'caixa',...bx('s16_salvo','voltar2',{c:Z,scr:'salvo'})],
 [tB2-0.4,tB2+0.1,'caixa',...bx('s17_volta1','v2',{c:Z})],
 [a('naPreventiva')-0.1,tPrev+0.1,'caixa',...bx('s18_volta2','prev',{c:V})],
 [a('aplicacao')-0.25,tAplP+0.1,'caixa',...bx('p01_grade','aplP',{c:Z})],
 [a('evento')-0.2,tEv+0.1,'caixa',...bx('p02_form','eventoSel',{c:D,scr:'pform'})],
 [a('vacina')-0.3,s(13)+0.5,'caixa',bm.x,bm.y,bm.w,bd.y+bd.h-bm.y,{c:Z,scr:'pev'}],
 [a('umAnimal')-0.2,tLoteP-0.5,'caixa',...bx('p03_evento','pillA',{c:V,scr:'pev'})],
 [tLoteP-0.5,tLoteP+0.1,'caixa',...bx('p03_evento','pillL',{c:D,scr:'pev'})],
 [tLoteP+0.4,tLoteSel+0.1,'caixa',...bx('p04_lote','loteSel',{c:Z,scr:'plote'})],
 [tLoteSel+0.3,tSalvP+0.1,'caixa',...bx('p05_lote02','salvar',{c:D,scr:'plote2'})],
 [tSalvP+0.95,a('lancado')-0.1,'caixa',...bx('p06_salvo','aviso',{c:V,scr:'psalvo'})]
];
EP.fitas=[[a('fita1')-0.1,a('emLancar')+0.1,'Sanidade · <b>aplicação</b>',110,298,-2],
 [a('naPreventiva')-0.25,a('aplicacao')-0.2,'Agora: <b>Preventiva</b>',110,298,-1.5]];
EP.titulos=[[0,'Temporada 2 · <m>Ep. 9</m>'],[a('emLancar')-0.1,'Em Lançar: <m>Sanidade</m>'],[e(2)+0.12,'Curativa ou <m>Preventiva</m>'],[a('naCurativa')-0.1,'Toque em <m>Curativa</m>'],
 [a('aplicRemedio')-0.15,'Aplicação de <m>remédio</m>'],[a('busque')-0.1,'Busque o <m>animal</m>'],[a('filtrar')-0.1,'Filtrar por <m>Doença</m>'],[a('mastite')-0.2,'Doença: <m>Mastite</m>'],
 [a('indicados')-0.4,'Só os <m>indicados</m>'],[a('falta')-0.4,'Remédio em <m>falta</m>'],[tUsar+0.8,'O produto <m>trocou</m>'],[a('dose')-0.15,'<m>Dose</m>, unidade e via'],[a('salvar')-0.25,'Toque em <m>Salvar</m>'],
 [a('aplicacao')-0.15,'Preventiva: <m>Aplicação</m>'],[a('evento')-0.1,'Escolha o <m>evento</m>'],[a('umAnimal')-0.1,'Um <m>animal</m>…'],[a('loteInteiro')-0.1,'…ou o <m>lote</m> inteiro'],[a('pronto')-0.1,'Feito: <m>lançado</m>']];
// diagramas Vox no papel: (1) Curativa = tratar doente · Preventiva = vacina / vermífugo; (2) item em falta ⇢ substituto disponível (seta tracejada a 12 qps)
const D1=[a('curativa')-0.35,e(2)+0.1],D3=[s(8)-0.15,tUsar+0.4];
EP.diag=D1;
const tCar=a('lancado'),tCarFim=a('proximo')-0.45;
const L2=i=>[F[i][1],F[i][2],F[i][0]];
EP.leg=[L2(0),L2(1),[F[2][1],a('preventiva')-0.25,'Escolha Curativa, para tratar um animal doente,'],[a('preventiva')-0.25,F[2][2],'ou Preventiva, para vacinas e vermífugos.'],L2(3),L2(4),L2(5),L2(6),L2(7),L2(8),L2(9),L2(10),L2(11),L2(12),L2(13),L2(14),L2(15),L2(16)];
EP.fimLeg=tCapa;EP.shake=a('lancado');
EP.entrada=t=>{const p=mola(t-0.3,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
EP.oculta=[[tCar,tCarFim],[D1[1],D1[1]+0.36],[D3[0],D3[1]+0.36],[a('fita1')-0.1,a('emLancar')+0.4],[a('naPreventiva')-0.25,a('aplicacao')-0.15]];
EP.estado=(t,{K,io,oc,lin,mola,L,cl,ob,ic,cow,X,iq})=>{
  K.dymo.style.transform=`translateX(${(1-cl(mola(t-0.55,9,.55),0,1.15))*-1000}px) rotate(-1.6deg)`;
  const g=cl(mola(t-0.15,10,.5),0,1.2);K.grampo.style.transform=`translateY(${(1-g)*-230}px) rotate(${(1-cl(g,0,1))*6}deg)`;
  let desenhado=false;
  const svg=h=>`<svg width="920" height="140" viewBox="0 0 920 140" style="overflow:visible">${h}</svg>`;
  const w=(Math.floor(t*12)%3)-1,off=(Math.floor(t*12)%6)*4;
  // diagrama 1: duas linhas, cada uma acende na palavra
  if(t>=D1[0]-0.05&&t<D1[1]+0.3){desenhado=true;const pe=oc(lin(t,D1[0],D1[0]+0.45)),ps=iq(lin(t,D1[1],D1[1]+0.3));
    const l1=oc(lin(t,a('curativa')-0.2,a('curativa')+0.25)),l2=oc(lin(t,a('preventiva')-0.2,a('preventiva')+0.25));
    const ln=(y,o,cor,pal,resto,ul)=>o<=0?'':`<g opacity="${o}" transform="translate(${(1-o)*-30} 0)"><text x="10" y="${y}" font-family="Archivo" font-weight="800" font-size="50"><tspan fill="${cor}">${pal}</tspan><tspan fill="${IN}">${resto}</tspan></text>`
      +`<path d="M10 ${y+14+w} L${L(10,ul[0],o)} ${y+12-w}" stroke="${cor}" stroke-width="8" stroke-linecap="round" fill="none" opacity=".85"/></g>`;
    X(K.diag,svg(ln(54,l1,RD,'Curativa',' = tratar animal doente',[330])+ln(118,l2,V,'Preventiva',' = vacina / vermífugo',[355])));
    K.diag.style.display='block';K.diag.style.opacity=1-ps;K.diag.style.transform=`translateY(${(1-pe)*-170+ps*-120}px)`;}
  // diagrama 2: item em falta ⇢ substituto disponível
  else if(t>=D3[0]-0.05&&t<D3[1]+0.3){desenhado=true;const pe=oc(lin(t,D3[0],D3[0]+0.4)),ps=iq(lin(t,D3[1],D3[1]+0.3));
    const c1=cl(mola(t-D3[0]-0.05,12,.55),0,1.15),pa=io(lin(t,D3[0]+0.35,D3[0]+0.9)),c2=cl(mola(t-D3[0]-0.75,12,.55),0,1.15);
    const chip=(x,sc,rot,fundo,borda,nome,sub)=>`<g transform="translate(${x+150} 66) rotate(${rot}) scale(${sc}) translate(-150 -66)"><rect x="3" y="3" width="300" height="126" fill="#FBF6E8" stroke="${borda}" stroke-width="7"/><rect x="3" y="3" width="300" height="126" fill="${fundo}" opacity=".18"/>`
      +`<text x="150" y="56" text-anchor="middle" font-family="Archivo" font-weight="800" font-size="36" fill="${IN}">${nome}</text><text x="150" y="102" text-anchor="middle" font-family="Archivo" font-weight="800" font-size="30" fill="${borda}">${sub}</text></g>`;
    X(K.diag,svg(chip(0,c1,-1.5,AM,AM,'CEFALEXINA','2 un · baixo')
      +`<g style="clip-path:inset(0 ${(1-pa)*100}% 0 0)"><path d="M${324+w} ${66+w} L${588-w} ${66-w}" stroke="${IN}" stroke-width="9" stroke-linecap="round" stroke-dasharray="14 12" stroke-dashoffset="${-off}" fill="none"/><path d="M${556+w} 40 L${604} ${66-w} L${556-w} 92" stroke="${IN}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round" fill="none"/></g>`
      +chip(616,c2,1.2,V,V,'CLOXACILINA','36 un · ok')));
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
   <div class="abs" data-z="1" style="left:80px;top:350px;font:800 138px/1.04 Archivo;color:#1A2638;letter-spacing:-.02em;text-transform:uppercase">Protocolo<br><span style="position:relative;display:inline-block;z-index:0">sanitário<i style="position:absolute;left:-10px;right:-14px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div>
   <div class="abs" data-z="2" style="left:80px;top:850px;width:380px;height:380px;background:#fff;box-shadow:0 26px 50px rgba(50,32,8,.3);display:flex;align-items:center;justify-content:center">${cow(250,'#1A2638',0.9)}</div>
   <div class="abs" data-z="3" style="left:510px;top:870px;width:490px"><div style="font:800 84px/1 Archivo;color:#1A2638;letter-spacing:-.02em">COW<span style="color:#8A5A12">DATA</span></div><div style="margin-top:28px;font:800 46px/1.1 Archivo;color:#1A2638;text-transform:uppercase">O rebanho na mão de <span style="position:relative;display:inline-block;z-index:0">quem cuida<i style="position:absolute;left:-8px;right:-10px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div></div>
   <div class="fita" data-z="4" style="left:90px;top:1330px;font-size:33px;letter-spacing:.04em">Ep. 9 · <b>Sanidade — aplicação</b></div>`);
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
EP.sfx.push([D1[0],'rasgo'],[D3[0],'rasgo'],[tCapa,'whoosh'],[tCapa+2.5,'rasgo'],[EP.shake,'carimbo']);
EP.sfx.sort((p,q)=>p[0]-q[0]);
EP.camadas=[[0,['piano','pad']],[a('emLancar'),['piano','pad','shaker']],[a('naCurativa')-0.2,['piano','pad','baixo','shaker','bumbo_leve']],[a('filtrar')-0.2,['piano','pad','baixo','shaker','bumbo','palma','piano_cheio']],
 [a('pronto')-0.2,['piano','pad','baixo','shaker','shaker16','bumbo','palma','piano_cheio','sino']],[a('proximo')-0.6,['piano','pad','baixo','shaker','bumbo_leve']],[tCapa,['piano','pad','baixo','shaker','bumbo_leve','sino']]];
return EP;})()
