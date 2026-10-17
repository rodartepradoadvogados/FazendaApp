import json
LEAD=0.6
def tl(frases,gaps,anc,tail):
    out={"frases":[],"anc":{}};acc=LEAD;starts=[]
    for i,(txt,a,b) in enumerate(frases):
        acc+=gaps[i]; starts.append(acc)
        out["frases"].append([txt,round(a+acc,3),round(b+acc,3)])
    def V(raw):
        k=max(i for i,f in enumerate(frases) if f[1]<=raw+1e-6) if raw>=frases[0][1] else 0
        return round(raw+starts[k],3)
    out["anc"]={k:V(v) for k,v in anc.items()}
    out["voz"]=[[starts[i],a,b] for i,(txt,a,b) in enumerate(frases)]
    out["total"]=round(out["frases"][-1][2]+tail,2)
    return out
F1=[("Série Treinamento, episódio um: o Rebanho no celular.",0.299,3.26),("Abra o app e toque no ícone Rebanho, aqui embaixo.",3.797,6.686),
("Cada card é um atalho: gestantes, inseminadas, vazias, atrasadas.",7.342,11.869),("Toque em Animais.",12.291,12.982),
("Na busca, digite o brinco ou o nome da vaca.",13.443,16.061),("Toque no animal para abrir a ficha.",16.968,18.491),
("A ficha tem seis partes. A mais usada é o Resumo.",19.091,22.21),("Situação reprodutiva: Ges. quer dizer prenhe; Ins., inseminada; Vaz., vazia.",22.632,29.39),
("Ao lado, o DEL, a cria em que a vaca está e a previsão de parto.",29.735,33.246),("Em Resumo por parto, veja quantas tentativas foram precisas para emprenhar.",34.12,38.236),
("Em Reprodução, abra Serviço e IA: o primeiro card é a última inseminação, com a data e o touro.",38.803,44.947),
("Em Produção, o controle leiteiro mostra as últimas produções.",45.547,48.681),("Dados gerais traz identificação e genealogia.",49.621,53.127),
("Sanidade, as vacinas e os tratamentos.",53.96,56.563),("E Movimentações, compras, vendas e trocas de lote.",56.947,60.173),("No próximo episódio: os Lotes.",60.787,62.911)]
G1=[0,0.8,0.6,0.3,1.0,0.6,1.0,1.0,0.4,0.8,1.2,1.2,1.0,0.6,0.6,1.0]
A1=dict(serie=0.299,abra=3.797,toqueReb=4.651,rebanho=5.376,aqui=5.931,cada=7.342,gest=8.707,insem=9.56,vaz=10.456,atras=11.224,toqueAnim=12.291,animais=12.718,
busca=13.443,buscaW=13.827,brinco=14.68,nome=15.406,toqueAnimal=16.968,ficha=18.205,fichaTem=19.091,seis=19.816,resumo=21.821,situacao=22.632,ges=24.168,ins=25.96,vazc=28.029,
aoLado=29.735,dele=30.589,cria=31.186,previsao=32.509,emResumo=34.12,porParto=34.248,tentativas=36.211,emRepro=38.803,repro=39.358,abraServ=40.083,servico=40.467,primeiro=41.79,ultima=42.771,data=44.179,touro=44.691,
emProd=45.547,prod=45.718,controle=46.443,ultimas=47.766,dados=49.621,ident=51.285,geneal=52.352,sanidade=53.96,vacinas=55.24,movim=56.947,movimW=57.118,compras=58.27,trocas=59.55,proximo=60.787,lotes=62.28,fimVoz=62.911)
F2=[("Episódio dois: os Lotes.",0.256,1.89),("No Rebanho, toque no card Lotes.",2.389,4.352),("São dois blocos: Composição e Indicadores.",4.736,7.266),
("Em Composição, cada barra é um lote.",7.765,9.817),("Toque para abrir e ver os animais: situação, DEL e o último controle leiteiro.",10.616,15.547),
("A cor da borda mostra a situação: azul, gestante; verde, apta; dourado, inseminada.",16.151,23.011),
("Em Indicadores, cada lote mostra o DEL médio, a produção média e quantos animais há em cada situação.",23.695,30.486),
("Para enviar, toque em Exportar PDF, ou em Compartilhar, para mandar pelo WhatsApp.",31.32,36.278),("Dentro do lote, sai só aquele lote.",36.739,38.734),
("No topo, saem todos os lotes de uma vez.",39.409,42.102),("CowData. O rebanho na mão de quem cuida.",42.524,45.206)]
G2=[0,0.8,0.6,0.8,0.5,0.6,1.2,1.0,0.6,0.6,1.0]
A2=dict(ep=0.256,noReb=2.389,toqueLotes=3.157,lotes=3.883,sao=4.736,blocos=5.205,comp=5.803,indic=6.827,emComp=7.765,barra=8.96,toqueAbrir=10.616,abrir=11.128,situacao=12.493,dele=13.347,ultimo=14.243,
cor=16.151,borda=16.919,azul=18.54,verde=20.204,dourado=21.57,emInd=23.695,indic2=24.207,delMed=26.383,prodMed=27.193,quantos=28.345,enviar=31.32,exportar=32.558,compart=34.264,whats=35.886,dentro=36.739,so=37.934,topo=39.409,topoW=39.921,todos=40.817,cowdata=42.524,rebanho=43.719,fimVoz=45.206)
json.dump(tl(F1,G1,A1,3.2),open('audio/tl_ep1.json','w'),ensure_ascii=False)
json.dump(tl(F2,G2,A2,2.4),open('audio/tl_ep2.json','w'),ensure_ascii=False)
for e in ('ep1','ep2'):
    d=json.load(open(f'audio/tl_{e}.json'));print(e,d['total'])
F3=[("Episódio três: as listas do Rebanho.",0.299,2.603),("Cada card do painel abre uma lista, animal por animal.",2.987,6.01),
("Gestantes: as vacas prenhes, com os dias de gestação e o parto previsto.",6.72,11.148),("Inseminadas: já foram inseminadas e aguardam o diagnóstico.",11.748,15.368),
("PEV é o período de espera voluntária, o descanso depois do parto.",16.08,19.66),("Acompanhe o DEL: passou do PEV, a vaca fica apta.",20.005,23.272),
("Vazias reúne todas as que não estão prenhes.",23.875,26.606),("A situação mostra quem está no PEV, apta ou atrasada.",26.99,30.313),
("Aptas: liberadas para inseminar.",30.913,33.041),("Atrasadas é um alerta: já deviam ter sido inseminadas.",33.759,36.998),("Observe essas vacas.",37.343,38.495),
("IA atual mostra quem está no protocolo de IATF agora, e em que dia.",39.095,43.419),("Parto previsto: os partos dos próximos trinta dias.",44.321,47.705),
("Essas vacas devem estar no pré-parto, com dieta aniônica.",48.204,51.377),("Secagens previstas: quem sai da ordenha, e em quantos dias.",52.291,55.849),
("DEL médio e produção média: o resumo da ordenha, com a última produção de cada vaca.",56.387,61.355),("E o intervalo entre partos médio também está aqui.",61.912,64.861),
("Em qualquer lista, toque em Ver Animal para abrir a ficha.",65.283,68.461),("Pronto: você já conhece todo o Rebanho no celular.",69.414,72.788)]
G3=[0,0.3,1.0,1.1,1.1,0.2,1.1,0.2,1.1,1.1,0,1.1,1.1,0.2,1.1,1.1,0.4,0.6,0.8]
A3=dict(ep=0.299,cada=2.987,gest=6.72,diasGest=9.194,partoPrev=10.432,insem=11.748,aguardam=14.265,pev=16.08,descanso=18.384,acomp=20.005,dele=20.688,apta=22.949,
vazias=23.875,situacao=27.161,pevW=28.696,aptaW=29.123,atrasadaW=29.848,aptas=30.913,liberadas=31.681,atras=33.759,alerta=34.911,observe=37.343,
ia=39.095,protocolo=40.93,dia=43.106,parto=44.321,trinta=46.881,essas=48.204,preparto=49.569,dieta=50.508,sec=52.291,ordenha=54.424,quantos=55.192,
delMed=56.387,resumo=58.477,ultima=59.928,intervalo=62.467,qualquer=65.283,ver=66.904,ficha=68.056,pronto=69.414,rebanho=71.633,fimVoz=72.788)
json.dump(tl(F3,G3,A3,2.6),open('audio/tl_ep3.json','w'),ensure_ascii=False)
d=json.load(open('audio/tl_ep3.json'));print('ep3',d['total']);print(d['anc'])
for f in d['frases']: print(f[1],f[2],f[0][:30])
