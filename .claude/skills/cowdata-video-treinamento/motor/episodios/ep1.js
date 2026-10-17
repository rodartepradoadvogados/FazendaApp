(()=>{const a=A;
const EP={};
// toques (coordenadas da tela do app, em px CSS 390×844)
const tReb=a('aqui')+0.4,tAnim=a('animais')+0.03,tBusca=a('buscaW'),tRes=a('ficha')-0.5,tResumo=a('resumo')+0.1;
const B1=46.05,tRepro=a('repro'),tServ=a('servico'),B2=54.45,tProd=a('prod')+0.25,tCL=a('controle')+0.35,B3=59.15,tDados=a('dados')+0.18,B4=64.15,tSan=a('sanidade')+0.2,B5=67.85,tMov=a('movimW')+0.2;
EP.toques=[[tReb,241,790],[tAnim,101,266],[tBusca,195,231],[tRes,195,299],[tResumo,103,390],[B1,39,169],[tRepro,103,510],[tServ,195,359],[B2,39,169],[tProd,286,510],[tCL,195,493],[B3,39,169],[tDados,286,390],[B4,39,169],[tSan,103,630],[B5,39,169],[tMov,286,630]];
EP.telas=[[0,'agenda',1],[tReb+0.25,'rebanho',1],[tAnim+0.25,'animais',1],[tRes+0.25,'ficha',1],[tResumo+0.25,'resumo',1],[B1+0.2,'ficha',-1],[tRepro+0.25,'repro',1],[B2+0.2,'ficha',-1],[tProd+0.25,'prod',1],[B3+0.2,'ficha',-1],[tDados+0.25,'dados',1],[B4+0.2,'ficha',-1],[tSan+0.25,'sanid',1],[B5+0.2,'ficha',-1],[tMov+0.25,'movim',1]];
EP.rolagem={rebanho:t=>90*io(lin(t,12.6,13.1))-90*io(lin(t,13.9,14.4)),resumo:t=>150*io(lin(t,40.4,41.3))};
// câmera: [chegada, duração do movimento, cx, cy, zoom]
EP.cam=[[0,0,195,300,1.0],[6.2,1.1,200,600,1.15],[9.25,1.1,195,330,1.0],[10.7,1.0,101,410,1.7],[11.56,0.8,289,410,1.7],[12.46,0.8,289,554,1.7],[13.22,0.7,289,608,1.7],
 [14.75,1.2,101,266,1.5],[16.6,1.1,180,300,1.15],[18.9,0.9,180,290,1.2],[22.9,1.1,195,420,1.0],[26.4,0.9,110,420,1.35],[28.6,1.1,100,262,1.9],
 [36.9,0.9,300,262,1.9],[37.6,0.6,100,312,1.9],[38.9,0.9,300,312,1.9],[41.4,1.1,195,420,1.3],[43.3,1.1,90,370,1.9],
 [45.9,0.9,195,330,1.0],[47.5,0.8,120,480,1.3],[48.6,0.8,195,360,1.4],[50.1,1.0,188,470,1.25],
 [54.3,0.8,195,330,1.0],[55.3,0.6,260,480,1.3],[56.3,0.9,190,500,1.2],[57.3,0.9,190,640,1.2],
 [59.0,0.8,195,330,1.0],[60.2,0.5,250,400,1.3],[61.8,1.0,190,345,1.2],[62.9,1.0,190,552,1.2],
 [64.0,0.8,195,330,1.0],[65.2,0.6,130,580,1.3],[66.4,1.0,190,551,1.2],
 [67.7,0.8,195,330,1.0],[68.9,0.7,260,580,1.3],[70.0,1.0,190,280,1.2],[71.3,1.0,190,470,1.2],[73.6,1.0,195,420,1.0]];
// anotações à mão: [t0, t1, tipo, x, y, w, h, texto, nx, ny]
EP.anot=[[a('rebanho'),tReb+0.15,'circulo',200,764,82,64,'aqui!',90,700],
 [10.75,11.5,'circulo',16,344,170,132],[11.6,12.4,'circulo',204,344,170,132],[12.5,13.2,'circulo',204,488,170,132],[13.25,14.2,'circulo',204,542,170,132],
 [18.75,20.8,'circulo',16,268,358,62],
 [a('ges'),35.6,'circulo',28,234,46,24],[a('dele'),38.6,'circulo',276,234,70,24],[a('cria'),39.2,'circulo',28,286,58,24],[a('previsao'),41.0,'circulo',276,286,90,24],
 [a('tentativas'),45.6,'circulo',28,376,30,24,'2 tentativas',66,326],
 [a('primeiro'),52.4,'circulo',16,392,358,150],[a('data'),54.0,'sub',30,420,90,18],[a('touro')+0.1,54.0,'sub',30,466,60,18],
 [a('ultimas'),59.0,'circulo',16,562,358,168],
 [a('ident'),62.8,'circulo',16,238,358,214],[a('geneal'),63.9,'circulo',16,494,358,116],
 [a('vacinas'),67.6,'circulo',16,462,358,178],
 [a('compras'),71.2,'circulo',16,206,358,70],[a('trocas'),73.3,'circulo',16,352,358,238]];
EP.fitas=[[a('ges'),35.6,'Ges. · <b>prenhe</b>',70,1560,-3],[a('ins'),35.6,'Ins. · <b>inseminada</b>',250,1690,2],[a('vazc'),35.6,'Vaz. · <b>vazia</b>',110,1815,-2]];
EP.titulos=[[0,'Série Treinamento · Ep. 1','O rebanho no <m>celular</m>'],[5.2,'Passo 1','Toque em <m>Rebanho</m>'],[9.3,'Painel do rebanho','Cada card é um <m>atalho</m>'],
 [16.7,'Passo 2','Busque o <m>animal</m>'],[23.9,'Ficha do animal','Seis <m>partes</m>'],[28.5,'Resumo','<m>Ges.</m> = prenhe'],[36.0,'Resumo','DEL, cria e <m>parto</m>'],
 [41.2,'Resumo por parto','<m>Tentativas</m>'],[47.1,'Reprodução','Última <m>IA</m>'],[55.0,'Produção','Últimas <m>produções</m>'],
 [60.1,'Dados gerais','Quem é <m>a vaca</m>'],[65.0,'Sanidade','Vacinas e <m>tratamentos</m>'],[68.6,'Movimentações','Entrou, saiu, <m>trocou</m>']];
EP.fimLeg=73.3;
EP.entrada=t=>{const p=mola(t-0.25,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
EP.estado=(t,{K})=>{
  // busca digitando
  const txt=t<a('brinco')?'':['4','45','452','4521'][Math.min(3,Math.floor((t-a('brinco'))/0.18))];
  X(K.buscaTxt,txt?`<span style="color:#101828">${txt}</span><span style="color:#8A6D2F">${(t*2|0)%2?'|':''}</span>`:'Buscar brinco ou nome…');
  K.busca.style.borderColor=t>=tBusca&&t<tRes+0.3?'#8A6D2F':'#D0D5DD';
  const res=t>=a('brinco')+0.75;K.lista.style.display=res?'none':'block';K.resultado.style.display=res?'block':'none';
  if(res){const p=oc(lin(t,a('brinco')+0.75,a('brinco')+1.1));K.res1.style.transform=`translateY(${(1-p)*30}px)`;K.res1.style.clipPath=`inset(0 0 ${(1-p)*100}% 0)`;}
  // seis partes pulsam
  for(let i=0;i<6;i++){const s=a('seis')+i*0.13;const q=Math.sin(Math.PI*lin(t,s,s+0.45));K['sec'+i].style.transform=`scale(${1+0.07*q})`;K['sec'+i].style.zIndex=q>0?5:1;K['sec'+i].style.boxShadow=q>0?`0 ${8*q}px ${18*q}px rgba(14,42,71,${.25*q})`:'';}
  // acordeões
  const pr=oc(lin(t,tServ+0.1,tServ+0.6));K.accR.style.height=312*pr+'px';K.accRdepois.style.transform=`translateY(${312*pr}px)`;
  const pp=oc(lin(t,tCL+0.1,tCL+0.6));K.accP.style.height=212*pp+'px';
};
EP.capa=(t,el)=>{const p=io(lin(t,73.3,74.0));if(p<=0){el.style.display='none';return;}el.style.display='block';el.style.clipPath=`inset(${(1-p)*100}% 0 0 0)`;
  const q=mola(t-73.9,10,.5),r=mola(t-74.5,12,.5),s=oc(lin(t,75.4,76.0));
  X(el,`<div class="meio-tom" style="left:-80px;top:1180px;width:520px;height:520px"></div>
   <div class="rot" style="top:560px">Próximo episódio</div>
   <div class="abs" style="left:66px;top:610px;font:800 190px/1 Archivo;color:#0E2A47;letter-spacing:-.02em" data-z="1">LOTES</div>
   <div class="abs" data-z="2" style="left:560px;top:860px;width:380px;height:380px;background:#fff;box-shadow:0 26px 50px rgba(30,25,15,.28);display:flex;align-items:center;justify-content:center;color:#B28A3A">${ic('fence',220,'#B28A3A',1.6)}</div>
   <div class="fita" data-z="3" style="left:60px;top:1300px">Composição · <b>Indicadores</b></div>
   <div class="fita" data-z="4" style="left:120px;top:1420px">Exportar · <b>Compartilhar</b></div>
   <div class="abs" data-z="5" style="left:72px;top:1640px;font:700 30px Archivo;letter-spacing:.16em;color:#0E2A47">SÉRIE TREINAMENTO · COWDATA</div>`);
  const z=n=>el.querySelector(`[data-z="${n}"]`);
  z(1).style.transform=`translateY(${(1-cl(q,0,1.2))*120}px)`;z(1).style.clipPath=`inset(0 0 ${(1-cl(q*1.4))*100}% 0)`;
  z(2).style.transform=`rotate(${L(14,4,cl(r,0,1.1))}deg) scale(${L(.4,1,cl(r,0,1.1))})`;
  z(3).style.transform=`translateX(${(1-cl(mola(t-75.0,12,.5),0,1.1))*-900}px) rotate(-3deg)`;z(4).style.transform=`translateX(${(1-cl(mola(t-75.3,12,.5),0,1.1))*-900}px) rotate(2deg)`;
  z(5).style.clipPath=`inset(0 ${(1-s)*100}% 0 0)`;};
return EP;})()
