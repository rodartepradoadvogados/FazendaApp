(()=>{const a=A;
const EP={};
// listas (dados fictícios coerentes com os episódios 1 e 2)
const LS={
 gest:['Gestantes',96,[['Vaca',[['Nº','4521'],['Dias de gestação','58'],['Dias para o parto','222'],['Parto previsto','26/05/2027']]],['Vaca',[['Nº','3990'],['Dias de gestação','201'],['Dias para o parto','79'],['Parto previsto','03/01/2027']]],['Novilha ges.',[['Nº','3105'],['Dias de gestação','260'],['Dias para o parto','20'],['Parto previsto','05/11/2026']]]]],
 insem:['Inseminadas',31,[['Vaca',[['Nº','4102'],['Lote atual','01 - Alta'],['Data da inseminação','25/09/2026'],['Tipo','IA — IATF']]],['Vaca',[['Nº','3755'],['Lote atual','02 - Média'],['Data da inseminação','02/10/2026'],['Tipo','IA — cio natural']]],['Nov. insem.',[['Nº','1702'],['Lote atual','06 - Novilhas'],['Data da inseminação','10/10/2026'],['Tipo','Monta natural']]]]],
 pev:['PEV',14,[['Vaca',[['Nº','4210'],['DEL (dias pós-parto)','28']]],['Vaca',[['Nº','3366'],['DEL (dias pós-parto)','12']]],['Vaca',[['Nº','4480'],['DEL (dias pós-parto)','40']]],['Vaca',[['Nº','3159'],['DEL (dias pós-parto)','7']]]]],
 vazias:['Vazias',42,[['Vaca',[['Nº','4210'],['Situação','PEV'],['Lote atual','01 - Alta']]],['Vaca',[['Nº','3877'],['Situação','Apta'],['Lote atual','01 - Alta']]],['Vaca',[['Nº','2950'],['Situação','Atrasada'],['Lote atual','02 - Média']]]]],
 aptas:['Aptas',18,[['Vaca',[['Nº','3877'],['DEL (dias pós-parto)','75'],['Lote atual','01 - Alta']]],['Vaca',[['Nº','3602'],['DEL (dias pós-parto)','66'],['Lote atual','02 - Média']]],['Novilha',[['Nº','1688'],['DEL (dias pós-parto)','—'],['Lote atual','06 - Novilhas']]]]],
 atras:['Atrasadas',6,[['Vaca',[['Nº','2950'],['Lote atual','02 - Média']]],['Vaca',[['Nº','3311'],['Lote atual','03 - Baixa']]],['Vaca',[['Nº','2788'],['Lote atual','03 - Baixa']]],['Novilha',[['Nº','1590'],['Lote atual','06 - Novilhas']]]]],
 ia:['IA atual (D0–D11)',9,[['Vaca',[['Nº','3420'],['Dia do protocolo','D7'],['D0','09/10/2026']]],['Vaca',[['Nº','3518'],['Dia do protocolo','D7'],['D0','09/10/2026']]],['Vaca',[['Nº','4011'],['Dia do protocolo','D2'],['D0','14/10/2026']]]]],
 parto:['Parto previsto',12,[['Vaca',[['Nº','3640'],['Parto previsto','22/10/2026'],['Dias de gestação','274'],['Dias para o parto','6']]],['Vaca',[['Nº','2877'],['Parto previsto','30/10/2026'],['Dias de gestação','266'],['Dias para o parto','14']]],['Novilha ges.',[['Nº','3105'],['Parto previsto','05/11/2026'],['Dias de gestação','260'],['Dias para o parto','20']]]]],
 sec:['Secagens previstas',5,[['Vaca',[['Nº','3388'],['Lote atual','01 - Alta'],['Secar em','4 dias'],['Previsão de secagem','20/10/2026']]],['Vaca',[['Nº','3012'],['Lote atual','02 - Média'],['Secar em','9 dias'],['Previsão de secagem','25/10/2026']]],['Vaca',[['Nº','3990'],['Lote atual','01 - Alta'],['Secar em','19 dias'],['Previsão de secagem','04/11/2026']]]]],
 prod:['DEL médio e produção média',84,[['Vaca',[['Nº','4521'],['DEL','142 dias'],['Última produção','32,5 L']]],['Vaca',[['Nº','3877'],['DEL','75 dias'],['Última produção','38,1 L']]],['Vaca',[['Nº','4102'],['DEL','96 dias'],['Última produção','35,4 L']]]]]};
const Y0=254,altura=nf=>110+24*nf,rowY=(id,i)=>{const nf=LS[id][2][0][1].length;return Y0+i*(altura(nf)+10);},linhaY=(id,r,i)=>rowY(id,r)+44+i*24;
function htmlLista(id){const[tit,total,rows]=LS[id];const nf=rows[0][1].length;
 return `${VOLTA(tit)}<div class="abs" style="left:16px;top:212px;font:500 13px Inter;color:#5B6470">Total: ${total} animal(is)</div>${BTN(140,204,'file-down','Exportar PDF')}${BTN(264,204,'share-2','Compartilhar')}
 ${rows.map((r,i)=>`<div class="card" data-r="${i}" style="top:${rowY(id,i)}px;height:${altura(nf)}px;box-shadow:0 1px 3px rgba(16,24,40,.08)"><span class="abs" style="left:14px;top:14px;font:700 11px/20px Inter;color:#8A6D2F;background:rgba(201,164,76,.16);border-radius:10px;padding:0 9px">${r[0]}</span>
  ${r[1].map((f,j)=>`<div class="abs" style="left:14px;width:330px;top:${44+j*24}px;display:flex;justify-content:space-between;font:600 13.5px Inter"><span style="color:#5B6470">${f[0]}</span><span style="font-weight:700;color:#101828">${f[1]}</span></div>`).join('')}
  <div class="abs" data-ver="${i}" style="left:14px;top:${44+nf*24+8}px;width:330px;height:44px;border:1px solid #D0D5DD;background:#fff;font:700 15px/42px Inter;text-align:center;color:#101828">Ver Animal</div></div>`).join('')}`;}
// ciclos: [lista, palavra do card, índice do card, fim da frase anterior, rolagem do painel]
const CI=[['gest','gest',2,null,0],['insem','insem',3,13.048,0],['pev','pev',4,18.368,0],['vazias','vazias',5,27.572,0],['aptas','aptas',6,35.913,120],['atras','atras',7,39.741,120],
 ['ia','ia',8,46.295,260],['parto','parto',9,52.319,260],['sec','sec',11,61.577,400],['prod','delMed',null,67.149,560]];
const posC=i=>i===null?[16,1064,150]:[posCard(i)[0],posCard(i)[1],132];
EP.toques=[];EP.telas=[[0,'rebanho',1]];EP.cam=[[0,0,195,330,1.0],[3.3,1.1,195,450,1.0]];EP.anot=[];const LISTA_EM=[];const ROL=[[0,0]];
for(const[id,w,ci,fimAnt,rol]of CI){const W=a(w);const[cx0,cy0,ch]=posC(ci);
  if(fimAnt!==null){const B=fimAnt+0.2;EP.toques.push([B,39,169]);EP.telas.push([B+0.2,'rebanho',-1]);ROL.push([B+0.45,null],[B+1.0,rol]);}
  const ccx=cx0+87,ccy=cy0+ch/2-rol;
  EP.cam.push([W-0.15,0.9,ccx,ccy,1.55]);EP.anot.push([W-0.6,W+0.15,'circulo',cx0,cy0-rol,170,ch]);
  EP.toques.push([W+0.05,ccx,ccy]);EP.telas.push([W+0.3,'lista',1]);LISTA_EM.push([W+0.05,id]);
  const nf=LS[id][2][0][1].length;EP.cam.push([W+1.35,0.95,195,rowY(id,0)+altura(nf)/2,1.12]);}
EP.rolagem={rebanho:t=>{let v=0,prev=0,pt=0;for(const[k,val]of ROL){if(val===null){pt=k;continue;}if(t<pt)break;prev=v;v=val;if(t<k)return L(prev,val,io(lin(t,pt,k)));}return v;}};
// ajustes de câmera dentro das listas
EP.cam.push([a('situacao')+0.5,0.9,195,500,1.05]);EP.cam.sort((x,y)=>x[0]-y[0]);
// Ver Animal na lista de produção -> ficha
const tVer=a('ver')+0.1;EP.toques.push([tVer,179,rowY('prod',0)+44+3*24+8+22]);EP.telas.push([tVer+0.25,'ficha',1]);EP.cam.push([tVer+1.2,0.9,195,420,1.0]);
EP.toques.sort((x,y)=>x[0]-y[0]);EP.telas.sort((x,y)=>x[0]-y[0]);EP.cam.sort((x,y)=>x[0]-y[0]);
// anotações nas listas
const LC=(id,r,i,t0,t1)=>[t0,t1,'circulo',20,linhaY(id,r,i)-2,340,22];
EP.anot.push(LC('gest',0,1,a('diasGest'),14.0),LC('gest',0,3,a('partoPrev'),14.0),
 LC('insem',0,2,a('insem')+1.6,19.3),LC('insem',0,3,a('aguardam'),19.3),
 LC('pev',0,1,a('dele'),28.4),
 LC('vazias',0,1,a('pevW'),36.4),LC('vazias',1,1,a('aptaW'),36.4),LC('vazias',2,1,a('atrasadaW'),36.4),
 [a('liberadas'),40.3,'circulo',16,rowY('aptas',0),358,altura(3)],
 [a('alerta'),46.9,'circulo',16,rowY('atras',0),358,altura(2)],
 LC('ia',0,1,a('dia')-0.2,53.0),LC('parto',0,3,a('trinta'),62.5),LC('parto',0,1,a('parto')+1.6,62.5),
 LC('sec',0,2,a('quantos'),68.1),LC('prod',0,2,a('ultima'),74.6),
 [a('ver')-0.7,tVer+0.1,'circulo',14,rowY('prod',0)+44+3*24+8,330,44]);
EP.fitas=[[a('descanso'),27.9,'PEV · <b>descanso pós-parto</b>',60,1600,-3],[a('apta'),27.9,'Passou do PEV → <b>apta</b>',140,1730,2],
 [a('situacao'),36.4,'Vazias = PEV + <b>aptas</b> + atrasadas',40,1650,-2],
 [a('alerta'),46.9,'⚠ Alerta · <b>observe</b>',90,1650,-3],
 [a('preparto'),62.5,'Pré-parto · <b>dieta aniônica</b>',70,1650,-2],
 [a('intervalo'),78.3,'IEP médio · <b>412 d</b>',150,1650,-3]];
// nada da lista sobrevive ao toque em "voltar"
{const VOLTAS=EP.toques.filter(q=>q[1]===39).map(q=>q[0]);const corta=(t0,t1)=>{const B=VOLTAS.find(b=>b>t0);return B!==undefined?Math.min(t1,B-0.1):t1;};
 for(const x of EP.anot)x[1]=corta(x[0],x[1]);for(const f of EP.fitas)f[1]=corta(f[0],f[1]);}
EP.titulos=[[0,'Série Treinamento · Ep. 3','As <m>listas</m>'],[a('gest')-0.4,'Lista','<m>Gestantes</m>'],[a('insem')-0.4,'Lista','<m>Inseminadas</m>'],
 [a('pev')-0.4,'Período de espera voluntária','<m>PEV</m>'],[a('vazias')-0.4,'Lista','<m>Vazias</m>'],[a('aptas')-0.4,'Liberadas','<m>Aptas</m>'],
 [a('atras')-0.4,'Alerta','<m>Atrasadas</m>'],[a('ia')-0.4,'IATF · D0–D11','IA <m>atual</m>'],[a('parto')-0.4,'Próximos 30 dias','Parto <m>previsto</m>'],
 [a('sec')-0.4,'Tirar da ordenha','<m>Secagens</m>'],[a('delMed')-0.4,'Ordenha','DEL e <m>produção</m>'],[a('intervalo')-0.5,'Também no painel','<m>IEP</m> médio'],
 [a('qualquer')-0.3,'Em qualquer lista','Ver <m>animal</m>']];
EP.fimLeg=83.4;
EP.entrada=t=>{const p=mola(t-0.25,8,.55);return{dx:0,dy:(1-cl(p,0,1.2))*1500,rot:(1-cl(p,0,1))*-4};};
EP.estado=(t,{K})=>{let id=null;for(const[t0,i]of LISTA_EM)if(t>=t0)id=i;if(id)X(K.listaCont,htmlLista(id));
  const vb=K.listaCont.querySelector('[data-ver="0"]');if(vb)vb.style.background=(id==='prod'&&t>=tVer-0.08&&t<tVer+0.25)?'#F2F4F7':'#fff';};
EP.capa=(t,el)=>{const p=io(lin(t,83.4,84.1));if(p<=0){el.style.display='none';return;}el.style.display='block';el.style.clipPath=`inset(${(1-p)*100}% 0 0 0)`;
  const q=mola(t-83.9,10,.5);const it=[['Ep. 1','Ficha do animal'],['Ep. 2','Lotes'],['Ep. 3','Listas do painel']];
  X(el,`<div class="meio-tom" style="left:620px;top:140px;width:480px;height:480px"></div><div class="rot" style="top:500px">Série Treinamento · APP - Rebanho</div>
   <div class="abs" data-z="1" style="left:66px;top:552px;font:800 118px/1 Archivo;color:#0E2A47;letter-spacing:-.02em">REBANHO</div>
   <div class="abs" data-z="1b" style="left:66px;top:676px;font:800 118px/1 Archivo;color:#0E2A47;letter-spacing:-.02em">COMPLETO</div>
   ${it.map((x,i)=>`<div class="abs" data-z="i${i}" style="left:72px;top:${900+i*150}px;display:flex;align-items:center;gap:28px"><div style="width:84px;height:84px;background:#fff;box-shadow:0 10px 22px rgba(30,25,15,.22);display:flex;align-items:center;justify-content:center">${ic('circle-check-big',58,'#047857',2.4)}</div><div style="font:800 54px Archivo;color:#0E2A47">${x[0]} · <span style="font-weight:600">${x[1]}</span></div></div>`).join('')}
   <div class="abs" data-z="2" style="left:72px;top:1420px;font:700 40px Archivo;color:#0E2A47">Cow<span style="color:#8A6D2F">Data</span> · o rebanho na mão de quem cuida</div>`);
  const z=n=>el.querySelector(`[data-z="${n}"]`);
  for(const k of['1','1b']){z(k).style.transform=`translateY(${(1-cl(q,0,1.2))*100}px)`;z(k).style.clipPath=`inset(0 0 ${(1-cl(q*1.4))*100}% 0)`;}
  for(let i=0;i<3;i++){const r=mola(t-84.6-i*0.45,12,.5);z('i'+i).style.transform=`translateX(${(1-cl(r,0,1.1))*-1100}px)`;}
  const s=oc(lin(t,86.3,86.9));z(2).style.clipPath=`inset(0 ${(1-s)*100}% 0 0)`;};
return EP;})()
