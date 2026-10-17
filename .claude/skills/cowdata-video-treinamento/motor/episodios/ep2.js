(()=>{const a=A;
const EP={};
const tLotes=a('lotes')+0.12,tComp=a('emComp')+0.2,tAbrir=a('toqueAbrir')+0.3,B1=28.05,tInd=a('indic2'),B2=36.4,tComp2=37.3,tPDF=a('exportar')+0.3,tShare=a('compart')+0.25;
EP.toques=[[tLotes,289,266],[tComp,195,295],[tAbrir,195,280],[B1,39,169],[tInd,195,481],[B2,39,169],[tComp2,195,295],[tPDF,70,337],[tShare,200,337]];
EP.telas=[[0,'rebanho',1],[tLotes+0.25,'lotes',1],[tComp+0.25,'comp',1],[B1+0.2,'lotes',-1],[tInd+0.25,'indic',1],[B2+0.2,'lotes',-1],[tComp2+0.25,'comp',1]];
EP.rolagem={};
EP.cam=[[0,0,195,330,1.0],[4.9,1.0,289,266,1.5],[6.9,1.0,195,390,1.0],[10.4,0.8,195,330,1.0],[12.0,1.0,195,450,1.1],[15.6,0.9,186,450,1.25],
 [20.8,0.9,130,500,1.5],[27.9,0.8,195,330,1.0],[30.6,1.0,190,292,1.25],[34.8,1.0,190,420,1.05],
 [36.2,0.8,195,330,1.0],[38.5,0.9,175,330,1.3],[41.6,0.8,195,600,1.15],[44.0,0.8,175,330,1.3],[47.4,0.9,240,250,1.5],[50.6,0.9,195,330,1.0]];
EP.anot=[[a('noReb')+0.6,tLotes+0.1,'circulo',204,200,170,132],[a('comp'),9.6,'circulo',16,210,358,170],[a('indic'),10.3,'circulo',16,396,358,170],
 [a('barra'),13.7,'circulo',16,252,358,440],
 [a('situacao'),19.5,'sub',150,398,64,14],[a('dele'),19.5,'sub',30,420,52,14],[a('ultimo'),19.5,'sub',104,420,92,14],
 [a('azul'),27.4,'circulo',13,368,10,76],[a('verde'),27.4,'circulo',13,458,10,76],[a('dourado'),27.4,'circulo',13,548,10,76],
 [a('delMed'),34.3,'circulo',26,250,104,44],[a('prodMed'),34.3,'circulo',192,250,112,44],[a('quantos'),35.9,'circulo',26,304,320,58],
 [a('whats')-0.1,43.1,'circulo',20,600,74,82],
 [a('dentro'),46.3,'circulo',16,320,250,34],
 [a('topoW'),50.4,'circulo',118,204,256,34]];
EP.fitas=[[a('so'),46.3,'Só <b>este lote</b>',90,1640,-3],[a('todos'),50.4,'<b>Todos</b> os lotes',90,1640,-3],[a('azul'),27.4,'<span style="color:#2563EB">Azul</span> · <b>gestante</b>',70,1560,-3],[a('verde'),27.4,'<span style="color:#047857">Verde</span> · <b>apta</b>',250,1690,2],[a('dourado'),27.4,'<span style="color:#8A6D2F">Dourado</span> · <b>inseminada</b>',110,1815,-2]];
EP.titulos=[[0,'Série Treinamento · Ep. 2','Os <m>lotes</m>'],[3.7,'Passo 1','Toque em <m>Lotes</m>'],[6.7,'Lotes','Dois <m>blocos</m>'],[10.5,'Composição','Cada barra, <m>um lote</m>'],
 [13.9,'Composição','Os <m>animais</m>'],[20.0,'Composição','A cor diz a <m>situação</m>'],[28.7,'Indicadores','Médias do <m>lote</m>'],[37.3,'Enviar','PDF ou <m>WhatsApp</m>'],
 [43.4,'Enviar','Só <m>este lote</m>'],[46.6,'Enviar','<m>Todos</m> os lotes']];
EP.fimLeg=50.6;
EP.entrada=t=>{const p=mola(t-0.25,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
EP.estado=(t,{K})=>{
  const p=oc(lin(t,tAbrir+0.1,tAbrir+0.7));K.exp0.style.height=498*p+'px';K.barsResto.style.transform=`translateY(${498*p}px)`;K.cv0.style.transform=`rotate(${180*p}deg)`;
  // toast "Arquivo salvo"
  const tv=t>=tPDF+0.2&&t<tPDF+1.9;K.toast.style.display=tv?'block':'none';K.toast.style.top='402px';K.toast.style.left='16px';K.toast.style.width='300px';
  if(tv){const q=oc(lin(t,tPDF+0.2,tPDF+0.5)),s=iq(lin(t,tPDF+1.6,tPDF+1.9));K.toast.style.transform=`translateY(${(1-q)*24+s*24}px)`;K.toast.style.clipPath=`inset(0 0 ${s*100}% 0)`;}
  // folha de compartilhar do Android
  const sv=t>=tShare+0.15&&t<43.5;K.sheet.style.display=sv?'block':'none';
  if(sv){const q=io(lin(t,tShare+0.15,tShare+0.55)),s=io(lin(t,43.1,43.5));K.sheet.style.transform=`translateY(${(1-q)*320+s*320}px)`;}
  for(const k of['lotePDF','loteShare','topoPDF','topoShare']){K[k].style.background='#fff';}
  if(t>=tPDF-0.08&&t<tPDF+0.25)K.lotePDF.style.background='#F8EFD9';if(t>=tShare-0.08&&t<tShare+0.25)K.loteShare.style.background='#F8EFD9';
};
EP.capa=(t,el)=>{const p=io(lin(t,50.6,51.3));if(p<=0){el.style.display='none';return;}el.style.display='block';el.style.clipPath=`inset(${(1-p)*100}% 0 0 0)`;
  const q=mola(t-51.1,10,.5),r=mola(t-51.6,12,.5),s=oc(lin(t,52.4,53.0)),u=mola(t-53.2,12,.5);
  X(el,`<div class="meio-tom" style="left:640px;top:120px;width:460px;height:460px"></div>
   <div class="rot" style="top:520px">Série Treinamento · APP - Rebanho</div>
   <div class="abs" data-z="1" style="left:66px;top:572px;font:800 150px/1 Archivo;color:#0E2A47;letter-spacing:-.02em">COW<span style="color:#8A6D2F">DATA</span></div>
   <div class="abs" data-z="2" style="left:560px;top:900px;width:400px;height:400px;background:#fff;box-shadow:0 26px 50px rgba(30,25,15,.28);display:flex;align-items:center;justify-content:center">${cow(260,'#0E2A47',0.9)}</div>
   <div class="abs" data-z="3" style="left:72px;top:900px;width:470px;font:800 64px/1.05 Archivo;color:#0E2A47;text-transform:uppercase">O rebanho na mão de <span style="position:relative;display:inline-block;z-index:0">quem cuida<i style="position:absolute;left:-8px;right:-10px;top:42%;height:62%;background:#C9A44C;opacity:.8;z-index:-1"></i></span></div>
   <div class="fita" data-z="4" style="left:90px;top:1420px">Ep. 1 · <b>Ficha</b>  ·  Ep. 2 · <b>Lotes</b></div>`);
  const z=n=>el.querySelector(`[data-z="${n}"]`);
  z(1).style.transform=`translateY(${(1-cl(q,0,1.2))*120}px)`;z(1).style.clipPath=`inset(0 0 ${(1-cl(q*1.4))*100}% 0)`;
  z(2).style.transform=`rotate(${L(-14,-4,cl(r,0,1.1))}deg) scale(${L(.4,1,cl(r,0,1.1))})`;
  z(3).style.clipPath=`inset(0 0 ${(1-s)*100}% 0)`;z(3).style.transform=`translateY(${(1-s)*40}px)`;
  z(4).style.transform=`translateX(${(1-cl(u,0,1.1))*-1100}px) rotate(-2deg)`;};
return EP;})()
