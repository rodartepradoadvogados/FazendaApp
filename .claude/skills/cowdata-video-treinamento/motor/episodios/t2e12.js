(()=>{const a=A;const EP={};const SB=30;
// ---- Ep. 12 · Protocolos (último da T2): Lançar › Protocolos (grade com 4 tipos) › Personalizado = ProtocoloCustomizadoApp. Telas = capturas do app real (captura/capturar_t2e12.mjs). ----
// Formulário sem barra fixa (barTop = topo da navegação). Os estados form/lista/proto/busca/matriz/tarefa/volta/resp compartilham a mesma rolagem (SM); ok tem a própria (SO: o botão Lançar fica onde estava). A troca de estado é dissolvida.
const bt=(n,k)=>{const m=MAPA[n];return(m.tall&&m.tall.alvos[k])||m.alvos[k];};
const mx=n=>{const m=MAPA[n];return m.tall?Math.max(0,m.tall.h-69-m.barTop):0;};
const seg=pts=>t=>{if(t<=pts[0][0])return pts[0][1];for(let i=0;i<pts.length-1;i++){const[a0,v0]=pts[i],[a1,v1]=pts[i+1];if(t<a1)return L(v0,v1,io(lin(t,a0,a1)));}return pts[pts.length-1][1];};
const F=TL.frases;
// frases: 0 título · 1 Em Lançar, toque em Protocolos · 2 Aqui ficam os quatro tipos · 3 IATF · 4 Indução de lactação · 5 Sanitário e Personalizado · 6 IATF e Sanitário são as mesmas telas · 7 que você já viu nos episódios 5 e 10
// · 8 Toque em Personalizado · 9 Escolha o protocolo · 10 o app mostra quantos dias · 11 Em Aplicar em, escolha Animal · 12 para uma vaca · 13 ou Tarefa da fazenda · 14 como uma limpeza… · 15 Confira a data do primeiro dia
// · 16 e o responsável · 17 e toque em Lançar protocolo · 18 Pronto, lançado · 19 Cada etapa… Agenda · 20 Fim da temporada dois · 21 Obrigado, e bom trabalho
const s=i=>F[i][1],e=i=>F[i][2];
// ---- tempos (tudo ancorado nas palavras da locução) ----
const tProt=e(1)+0.1,cGrade=tProt+0.14,tPers=e(8)+0.05,cForm=tPers+0.14,tSel=a('escolha')+0.05,cLista=tSel+0.14,tOpt=a('quantos')+0.05,cProto=tOpt+0.14,
 tPA=a('animal')+0.1,tBusca=s(12)+0.1,cBusca=tBusca+0.4,tRes=e(12)+0.3,cMatriz=tRes+0.14,tTar=a('tarefa')+0.1,cTarefa=tTar+0.14,tVolta=e(14)+0.35,cVolta=tVolta+0.14,
 tResp=a('responsavel')+0.15,cResp=tResp+0.6,tLanc=a('lancarProt')+0.3,cOk=tLanc+0.5,tCar=a('lancado'),tCapa=a('fim')-0.15;
EP.imgs={lancar:'p01_lancar',grade:'p02_grade',form:'p03_form',lista:'p04_lista',proto:'p05_proto',busca:'p06_busca',matriz:'p07_matriz',tarefa:'p08_tarefa',volta:'p09_volta',resp:'p10_resp',ok:'p11_ok'};
const DF=0.18;
// [t, tela, direção (1 = desliza da direita), 1 = só troca de estado (as anotações continuam), dissolvência em s]
EP.telas=[[0,'lancar',0],[cGrade,'grade',1],[cForm,'form',1],[cLista,'lista',0,1,0.12],[cProto,'proto',0,1,DF],[cBusca,'busca',0,1,0.1],[cMatriz,'matriz',0,1,0.12],[cTarefa,'tarefa',0,1,DF],[cVolta,'volta',0,1,DF],[cResp,'resp',0,1,0.1],[cOk,'ok',0,1,DF]];
// ---- rolagem (px CSS do app) ---- form…resp: 0 até a frase 15; então 94 (o máximo de volta/resp: data, responsável, nota e o botão à vista) · ok: 589 (o botão no mesmo lugar do estado anterior; aviso e nota à vista)
const SM=seg([[0,0],[s(15)-0.25,0],[s(15)+0.55,94]]);
const SO=seg([[0,589]]);
EP.rolagem={form:SM,lista:SM,proto:SM,busca:SM,matriz:SM,tarefa:SM,volta:SM,resp:SM,ok:SO};
const S=(id,t)=>cl(EP.rolagem[id]?EP.rolagem[id](t):0,0,mx(EP.imgs[id]));
const cx=b=>b.x+b.w/2,cy=b=>b.y+b.h/2;
// ---- toques: [t, x, y] em coordenadas da tela do celular (CSS) já com a barra de status (+30) ----
const B=bt;
const bProt=B('p01_lancar','protocolosBloco'),bPers=B('p02_grade','personalizado'),bSel=B('p03_form','protoSel'),bOpt=B('p04_lista','op1'),bPA=B('p05_proto','pillA'),bBu=B('p05_proto','busca'),bRes=B('p06_busca','res3654'),
 bPF=B('p07_matriz','pillF'),bPA2=B('p08_tarefa','pillA'),bRe=B('p09_volta','respSel'),bLa=B('p10_resp','lancar');
EP.toques=[
 [tProt,cx(bProt),cy(bProt)+SB],[tPers,cx(bPers),cy(bPers)+SB],[tSel,cx(bSel),cy(bSel)-S('form',tSel)+SB],[tOpt,cx(bOpt),cy(bOpt)-S('lista',tOpt)+SB],[tPA,cx(bPA),cy(bPA)-S('proto',tPA)+SB],
 [tBusca,cx(bBu),cy(bBu)-S('proto',tBusca)+SB],[tRes,cx(bRes),cy(bRes)-S('busca',tRes)+SB],[tTar,cx(bPF),cy(bPF)-S('matriz',tTar)+SB],[tVolta,cx(bPA2),cy(bPA2)-S('tarefa',tVolta)+SB],
 [tResp,cx(bRe),cy(bRe)-S('volta',tResp)+SB],[tLanc,cx(bLa),cy(bLa)-S('resp',tLanc)+SB]];
// ---- câmera: [t de chegada, duração, cx, cy, zoom] (coords da tela do celular com +30). Visível: de cy-189/z a cy+349/z. Zoom ≤ 1,18 e centrado ----
EP.cam=[[0,0,195,300,1.0],[a('emLancar')+0.4,1.0,195,450,1.1],[cGrade+0.6,0.8,195,330,1.0],[s(15)-0.2,0.9,195,520,1.0]];
// ---- anotações: [t0,t1,tipo,x,y,w,h,{c,scr}] — as de tela com troca de tela somem no quadro da troca; as demais têm fim explícito ----
const V='#2E7D52',Z='#1E6FA8',D='#E0A63C',IN='#1A2638',RD='#B3392F';
const bx=(n,k,o={},dx=0,dy=0,dw=0,dh=0)=>{const b=bt(n,k);return[b.x+dx,b.y+dy,b.w+dw,b.h+dh,o];};
const D1=[s(6)-0.1,e(7)+0.15],D2=[a('cada')-0.2,e(19)+0.25],tCar2=D2[0]-0.4;
EP.anot=[
 [a('protocolos')-0.2,tProt+0.1,'caixa',...bx('p01_lancar','protocolosBloco',{c:V})],
 [a('iatf')-0.1,s(6)-0.15,'caixa',...bx('p02_grade','iatf',{c:V,scr:'grade'})],
 [a('inducao')-0.1,s(6)-0.15,'caixa',...bx('p02_grade','inducao',{c:Z,scr:'grade'})],
 [a('sanitario')-0.1,s(6)-0.15,'caixa',...bx('p02_grade','sanitario',{c:D,scr:'grade'})],
 [a('personalizado')-0.15,s(6)-0.15,'caixa',...bx('p02_grade','personalizado',{c:V,scr:'grade'})],
 [s(6)-0.05,e(7)+0.3,'caixa',...bx('p02_grade','iatf',{c:Z,scr:'grade'})],
 [a('mesmasTelas')-0.6,e(7)+0.3,'caixa',...bx('p02_grade','sanitario',{c:RD,scr:'grade'})],
 [cLista+0.1,s(10)-0.1,'caixa',...bx('p04_lista','protoSel',{c:V,scr:'lista'})],
 ...[1,2,3,4].map((k,i)=>[s(10)+0.1+i*0.22,tOpt-0.05,'sub',...bx('p04_lista','dias'+k,{c:D,scr:'lista'})]),
 [cProto+0.15,s(11)-0.4,'caixa',...bx('p05_proto','trecho',{c:D,scr:'proto'},-3,-1,6,2)],
 [s(11)+0.1,a('animal')-0.15,'caixa',...bx('p05_proto','pills',{c:Z,scr:'proto'})],
 [a('animal')-0.1,e(11)+0.25,'caixa',...bx('p05_proto','pillA',{c:V,scr:'proto'})],
 [cMatriz+0.1,tTar-0.25,'caixa',...bx('p07_matriz','matrizSel',{c:D,scr:'matriz'})],
 [a('tarefa')-0.15,tVolta-0.3,'caixa',...bx('p07_matriz','pillF',{c:Z,scr:'matriz'})],
 [tVolta-0.25,cVolta+0.55,'caixa',...bx('p08_tarefa','pillA',{c:V,scr:'tarefa'})],
 [a('data')-0.1,a('primeiroDia')-0.1,'caixa',...bx('p09_volta','dataIn',{c:Z,scr:'volta'})],
 [a('primeiroDia')-0.1,a('responsavel')-0.3,'caixa',...bx('p09_volta','primeiro',{c:D,scr:'volta'},-2,-1,4,2)],
 [a('responsavel')-0.1,a('lancarProt')-0.35,'caixa',...bx('p10_resp','respSel',{c:V,scr:'resp'})],
 [a('lancarProt')-0.2,tLanc+0.1,'caixa',...bx('p10_resp','lancar',{c:D,scr:'resp'})],
 [cOk+0.2,e(18)+0.3,'caixa',...bx('p11_ok','aviso',{c:V,scr:'ok'})],
 [a('etapa')-0.3,e(19)+0.1,'caixa',...bx('p11_ok','nota',{c:D,scr:'ok'},-4,-2,8,4)]
];
EP.fitas=[[a('fita1')-0.1,a('emLancar')+0.1,'<b>Protocolos</b>',110,298,-2]];
EP.titulos=[[0,'Temporada 2 · <m>Ep. 12</m>'],[a('emLancar')-0.1,'Em Lançar: <m>Protocolos</m>'],[a('aquiFicam')-0.2,'Os quatro <m>tipos</m>'],[D1[1],'Eps. <m>5 e 10</m>'],[a('toquePers')-0.15,'Toque em <m>Personalizado</m>'],
 [a('escolha')-0.15,'Escolha o <m>protocolo</m>'],[s(10)-0.1,'Quantos <m>dias</m> dura'],[s(11)-0.15,'Aplicar em: <m>Animal</m>'],[s(12)-0.1,'Para uma <m>vaca</m>'],[s(13)-0.1,'Ou <m>Tarefa da fazenda</m>'],
 [s(15)-0.15,'Data do <m>primeiro dia</m>'],[s(16)-0.1,'O <m>responsável</m>'],[s(17)-0.1,'Toque em <m>Lançar protocolo</m>'],[cOk+0.2,'Protocolo <m>lançado</m>']];
EP.titulos.sort((p,q)=>p[0]-q[0]);
EP.diag=[0,0];
const L2=i=>[F[i][1],F[i][2],F[i][0]];
EP.leg=[...Array(22).keys()].map(L2);
EP.fimLeg=tCapa;EP.shake=a('lancado');
EP.entrada=t=>{const p=mola(t-0.3,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
EP.oculta=[[tCar,tCapa+0.8],[D1[0],D1[1]+0.36],[a('fita1')-0.1,a('emLancar')+0.4]];
EP.estado=(t,{K,io,oc,lin,mola,L,cl,ob,ic,cow,X,iq})=>{
  K.dymo.style.transform=`translateX(${(1-cl(mola(t-0.55,9,.55),0,1.15))*-1000}px) rotate(-1.6deg)`;
  const g=cl(mola(t-0.15,10,.5),0,1.2);K.grampo.style.transform=`translateY(${(1-g)*-230}px) rotate(${(1-cl(g,0,1))*6}deg)`;
  const w=(Math.floor(t*12)%3)-1;let desenhado=false;
  const svg=h=>`<svg width="920" height="140" viewBox="0 0 920 140" style="overflow:visible">${h}</svg>`;
  const mostra=(pe,ps)=>{K.diag.style.display='block';K.diag.style.opacity=1-ps;K.diag.style.transform=`translateY(${(1-pe)*-170+ps*-120}px)`;};
  // diagrama 1: os dois tipos que já foram vistos (IATF = Ep. 5, Sanitário = Ep. 10), sem entrar neles
  if(t>=D1[0]-0.05&&t<D1[1]+0.3){desenhado=true;const pe=oc(lin(t,D1[0],D1[0]+0.4)),ps=iq(lin(t,D1[1],D1[1]+0.3));
    const a1=oc(lin(t,D1[0]+0.1,D1[0]+0.5)),a2=cl(mola(t-(a('ep5')-0.35),12,.55),0,1.15),ul=io(lin(t,D1[0]+0.5,D1[0]+1.0));
    let sv=`<g opacity="${a1}" transform="translate(${(1-a1)*-40} 0)"><text x="6" y="58" font-family="Archivo" font-weight="800" font-size="46" fill="${IN}">IATF = Ep. 5<tspan fill-opacity="${cl(a2)}" fill="#2E7D52"> · Sanitário = Ep. 10</tspan></text></g>`;
    sv+=`<path d="M6 ${74+w} L${L(6,640,ul)} ${72-w}" stroke="#1E6FA8" stroke-width="8" stroke-linecap="round" fill="none"/>`;
    sv+=`<g opacity="${a1}"><text x="6" y="118" font-family="Inter,Archivo" font-weight="600" font-size="30" fill="#4b4034">(as mesmas telas dos episódios anteriores)</text></g>`;
    X(K.diag,svg(sv));mostra(pe,ps);}
  // diagrama 2: as etapas do cronograma (D0 · D3 · D7 · D10) que viram pendências na Agenda, com seta tracejada (12 qps) até a nota da tela (posição vinda da câmera e da rolagem no mesmo instante)
  else if(t>=D2[0]-0.05&&t<D2[1]+0.3){desenhado=true;const pe=oc(lin(t,D2[0],D2[0]+0.4)),ps=iq(lin(t,D2[1],D2[1]+0.3));
    const a1=oc(lin(t,D2[0]+0.1,D2[0]+0.5)),a2=cl(mola(t-(a('agenda')-0.3),12,.55),0,1.15),ul=io(lin(t,a('etapa')+0.2,a('etapa')+0.7));
    const[cxm,cym,zz]=camera(t);const b=bt('p11_ok','nota');const scr=S('ok',t);
    const ex=540+((b.x+b.w/2)-cxm)*U*zz-80,ey=FY+((b.y-scr+SB)-cym)*U*zz-286-34;
    const pa=io(lin(t,a('vira')-0.5,a('vira')+0.4));
    let sv=`<g opacity="${a1}" transform="translate(${(1-a1)*-40} 0)"><text x="6" y="58" font-family="Archivo" font-weight="800" font-size="47" fill="${IN}">D0 · D3 · D7 · D10<tspan fill="#2E7D52" fill-opacity="${cl(a2)}"> → Agenda</tspan></text></g>`;
    sv+=`<path d="M6 ${74+w} L${L(6,700,ul)} ${72-w}" stroke="#1E6FA8" stroke-width="8" stroke-linecap="round" fill="none"/>`;
    sv+=`<g opacity="${a1}"><text x="6" y="118" font-family="Inter,Archivo" font-weight="600" font-size="30" fill="#4b4034">(cada etapa vira uma pendência)</text></g>`;
    if(pa>0){const ox=800,oy=96,off=(Math.floor(t*12)%6)*4;sv+=`<g style="clip-path:inset(0 0 ${(1-pa)*100}% 0)"><path d="M${ox} ${oy+w} C${ox+170} ${oy+60}, ${ex+150} ${ey-420}, ${ex+8} ${ey-6}" stroke="${IN}" stroke-width="8" stroke-linecap="round" stroke-dasharray="12 10" stroke-dashoffset="${-off}" fill="none"/><path d="M${ex-22+w} ${ey-30} L${ex+8} ${ey+4} L${ex+30-w} ${ey-24}" stroke="${IN}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" fill="none"/></g>`;}
    X(K.diag,svg(sv));mostra(pe,ps);}
  if(!desenhado)K.diag.style.display='none';
  K.cartao.style.display='none';
  // carimbo de borracha: bate no "lançado" (3 quadros de tremida na cena inteira, ver shake no motor) e sai antes do diagrama das etapas
  if(t>=tCar&&t<tCar2+0.3){const q=oc(lin(t,tCar,tCar+0.1)),s=lin(t,tCar2,tCar2+0.3);
    X(K.carimbo,`<div style="display:flex;align-items:center;justify-content:center;gap:22px;border:10px solid #14452B;outline:3px solid #14452B;outline-offset:7px;border-radius:18px;padding:22px 34px;color:#14452B;font:800 54px/1 Archivo;letter-spacing:.03em;white-space:nowrap;background:rgba(251,246,232,.55);filter:url(#tinta)"><svg width="70" height="70" viewBox="0 0 24 24" fill="none" stroke="#14452B" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5l5 5L20 6.5"/></svg>PROTOCOLO LANÇADO</div>`);
    K.carimbo.style.display='block';K.carimbo.style.opacity=(0.93*(1-s)*cl(q*4)).toFixed(3);K.carimbo.style.transform=`translateX(-50%) rotate(-4deg) scale(${L(1.7,1,q)})`;}else K.carimbo.style.display='none';
};
// capa de ENCERRAMENTO da temporada (sem "Próximo episódio")
EP.capa=(t,el)=>{const p=io(lin(t,tCapa,tCapa+0.7));if(p<=0){el.style.display='none';return;}el.style.display='block';el.style.clipPath=`inset(${(1-p)*100}% 0 0 0)`;
  const q=mola(t-tCapa-0.45,10,.5),r=mola(t-tCapa-0.95,12,.5),s=oc(lin(t,tCapa+1.7,tCapa+2.3)),u=mola(t-tCapa-2.5,12,.5);
  X(el,`<div class="dymo" style="top:250px;left:80px;transform:rotate(-1.6deg)">FIM DA TEMPORADA 02</div>
   <div class="abs" data-z="1" style="left:80px;top:400px;width:920px"><div style="font:800 108px/1.04 Archivo;color:#1A2638;letter-spacing:-.02em;text-transform:uppercase">Fim da<br><span style="position:relative;display:inline-block;z-index:0">Temporada 2<i style="position:absolute;left:-10px;right:-14px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div><div style="margin-top:24px;font:700 50px/1.1 Archivo;letter-spacing:.02em;text-transform:uppercase">— Lançamentos</div></div>
   <div class="abs" data-z="2" style="left:80px;top:850px;width:380px;height:380px;background:#fff;box-shadow:0 26px 50px rgba(50,32,8,.3);display:flex;align-items:center;justify-content:center">${cow(250,'#1A2638',0.9)}</div>
   <div class="abs" data-z="3" style="left:510px;top:870px;width:490px"><div style="font:800 84px/1 Archivo;color:#1A2638;letter-spacing:-.02em">COW<span style="color:#8A5A12">DATA</span></div><div style="margin-top:28px;font:800 46px/1.1 Archivo;color:#1A2638;text-transform:uppercase">Obrigado, e <span style="position:relative;display:inline-block;z-index:0">bom trabalho!<i style="position:absolute;left:-8px;right:-10px;top:42%;height:62%;background:#E0A63C;opacity:.85;z-index:-1"></i></span></div></div>
   <div class="fita" data-z="4" style="left:90px;top:1330px;font-size:33px;letter-spacing:.04em">Ep. 12 · <b>Protocolos</b></div>`);
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
EP.camadas=[[0,['piano','pad']],[a('emLancar'),['piano','pad','shaker']],[a('iatf')-0.3,['piano','pad','baixo','shaker','bumbo_leve']],[a('toquePers')-0.2,['piano','pad','baixo','shaker','bumbo','palma','piano_cheio']],
 [a('pronto')-0.2,['piano','pad','baixo','shaker','shaker16','bumbo','palma','piano_cheio','sino']],[a('fim')-0.6,['piano','pad','baixo','shaker','bumbo_leve']],[tCapa,['piano','pad','baixo','shaker','bumbo_leve','sino']]];
return EP;})()
