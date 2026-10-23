# 📱 CowData Milk — como instalar o app no celular

Existem hoje DUAS formas de instalar, dependendo do celular. Use a que se aplica:

- **Android**: app nativo (arquivo `.apk`), enviado por WhatsApp/link — ver seção
  **"Android (app nativo, .apk)"** abaixo. É a forma recomendada para os funcionários
  enquanto o app ainda não está na Play Store.
- **iPhone**: não existe app nativo ainda (só compilamos para Android por enquanto).
  Use o site instalado como app (PWA) — ver seção **"iPhone (Safari)"** abaixo, funciona
  igual no dia a dia (abre em tela cheia, ícone próprio, funciona sem internet).

O app dos funcionários (site/PWA) também fica neste endereço (é só um link — não tem arquivo para baixar):

**https://milk.cowdata.com.br/app**

O site completo (computador) é **https://milk.cowdata.com.br**. O servidor (API) é
`https://api.milk.cowdata.com.br` — o funcionário não precisa dele. O endereço antigo
(`fazenda-app-jfye.vercel.app`) continua no ar, mas o app novo já usa o domínio próprio.

Cada pessoa instala UMA vez, em 1 minuto. Depois é só tocar no ícone, como qualquer app.

---

## Android (app nativo, .apk)

1. Baixe o `.apk` mais recente gerado pelo GitHub Actions (peça o link de download —
   é o mesmo app, só que atualizado, a cada nova versão nativa).
2. Abra o arquivo baixado no celular e toque em **Instalar**. O Android vai avisar
   "app de fonte desconhecida" — toque em **Instalar mesmo assim** (é normal, o app
   ainda não está na Play Store).
3. Abra o app pelo ícone (**CowData Milk**, ícone azul-marinho com a curva dourada). Faça login normalmente.

Esse `.apk` de teste (debug) é só para os funcionários experimentarem antes de irmos
para a Play Store — quando isso acontecer, a atualização passa a ser automática, como
qualquer outro app.

### Atualizar o app (funcionários que já têm o antigo)

O app novo se chama **CowData Milk** e abre o endereço novo (`milk.cowdata.com.br`).
Ele é assinado com a mesma chave do antigo, então **instala por cima**, sem desinstalar.
Como o endereço mudou, o celular **esquece o login e a fila local**: por isso o passo 1 é importante.

1. **Antes:** abra o app antigo, vá em **Menu › Sincronização** e confirme que a fila está **VAZIA**
   (nada pendente). Se tiver pendência, espere enviar com internet.
2. Instale o `.apk` novo **POR CIMA**, sem desinstalar o antigo (abra o arquivo e toque em **Instalar**/**Atualizar**).
3. Abra o app e entre com o **MESMO usuário e senha**. O login some do celular, mas os usuários
   continuam existindo — nada foi apagado no servidor.
4. Se o Android disser **"app não instalado"** ou apontar conflito de pacote, aí sim: desinstale o antigo
   e instale o novo. **Atenção:** isso perde o que não foi enviado (lançamentos/fotos ainda na fila).
5. **iPhone / Chrome (PWA):** abra o endereço novo `https://milk.cowdata.com.br/app` e instale de novo
   (iPhone: Safari › Compartilhar › Adicionar à Tela de Início; Android/Chrome: menu ⋮ › Instalar app).
   Pode apagar o ícone antigo.

Texto curto para mandar no WhatsApp:

> Pessoal, o app da fazenda mudou de nome: agora é o **CowData Milk** (ícone azul-marinho).
> 1) Antes de atualizar, abra o app e vá em Menu > Sincronização: não pode ter nada pendente.
> 2) Baixe o arquivo novo que estou mandando e instale POR CIMA do antigo (não precisa apagar o antigo).
> 3) Abra e entre com o MESMO usuário e senha de sempre. Vai pedir o login de novo, é normal.
> Se o Android falar "app não instalado", me avisem antes de apagar o antigo.
> Quem usa o iPhone: abra https://milk.cowdata.com.br/app no Safari e adicione de novo à Tela de Início.

### Android (alternativa: Chrome, sem instalar .apk)

1. Mande o link acima por WhatsApp para o funcionário.
2. Ele abre o link no **Chrome** e entra com o usuário e a senha dele.
3. O Chrome mostra o aviso **"Adicionar CowData Milk à tela inicial"** (ou: menu ⋮ no canto
   superior direito → **"Adicionar à tela inicial"** / **"Instalar app"**).
4. Toca em **Instalar**. Pronto: aparece o ícone do touro 🐂 na tela do celular.

## iPhone (Safari)

1. Abra o link no **Safari** (tem que ser o Safari) e faça o login.
2. Toque no botão **Compartilhar** (o quadradinho com a seta para cima, no meio da barra de baixo).
3. Role a lista e toque em **"Adicionar à Tela de Início"**.
4. Toque em **Adicionar**. O ícone aparece na tela inicial.

---

## O que o app faz

- **Agenda** — as tarefas do dia, com botão verde de concluir.
- **Lançar** — lançamento rápido: reprodutivo, leite, sanidade, alimentação, estoque.
- **Rebanho** — ficha do animal, movimentar de lote e baixar animal.
- **Menu** — agenda do veterinário, calendário sanitário, relatórios, indicadores,
  Fotos do campo (tira foto com a câmera e já envia).

### Funciona sem internet ("do mato")

- A **bolinha** ao lado de FAZENDA mostra a conexão: **verde** = com internet, **vermelha** = sem.
- Sem internet, os lançamentos ficam **guardados no celular** e são **enviados sozinhos**
  quando a internet voltar (dá para acompanhar em **Menu → Sincronização**).
- Para o app abrir sem internet, é preciso ter aberto **pelo menos uma vez** conectado.

### Dicas

- O botão de sol/lua no topo troca entre **modo claro** (bom no sol) e **modo escuro** (economiza bateria).
- Cada funcionário usa o **próprio usuário** — assim os lançamentos ficam registrados no nome de quem fez.
- O site completo (relatórios grandes, financeiro, configurações) continua em
  **https://milk.cowdata.com.br/** — o app é a versão de campo, enxuta de propósito.
