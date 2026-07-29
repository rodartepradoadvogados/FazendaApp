# 📱 App de campo da Fazenda — como instalar no celular

Existem hoje DUAS formas de instalar, dependendo do celular. Use a que se aplica:

- **Android**: app nativo (arquivo `.apk`), enviado por WhatsApp/link — ver seção
  **"Android (app nativo, .apk)"** abaixo. É a forma recomendada para os funcionários
  enquanto o app ainda não está na Play Store.
- **iPhone**: não existe app nativo ainda (só compilamos para Android por enquanto).
  Use o site instalado como app (PWA) — ver seção **"iPhone (Safari)"** abaixo, funciona
  igual no dia a dia (abre em tela cheia, ícone próprio, funciona sem internet).

O app dos funcionários (site/PWA) também fica neste endereço (é só um link — não tem arquivo para baixar):

**https://fazenda-app-jfye.vercel.app/app**

Cada pessoa instala UMA vez, em 1 minuto. Depois é só tocar no ícone, como qualquer app.

---

## Android (app nativo, .apk)

1. Baixe o `.apk` mais recente gerado pelo GitHub Actions (peça o link de download —
   é o mesmo app, só que atualizado, a cada nova versão nativa).
2. Abra o arquivo baixado no celular e toque em **Instalar**. O Android vai avisar
   "app de fonte desconhecida" — toque em **Instalar mesmo assim** (é normal, o app
   ainda não está na Play Store).
3. Abra o app pelo ícone. Faça login normalmente.

Esse `.apk` de teste (debug) é só para os funcionários experimentarem antes de irmos
para a Play Store — quando isso acontecer, a atualização passa a ser automática, como
qualquer outro app.

### Android (alternativa: Chrome, sem instalar .apk)

1. Mande o link acima por WhatsApp para o funcionário.
2. Ele abre o link no **Chrome** e entra com o usuário e a senha dele.
3. O Chrome mostra o aviso **"Adicionar a Fazenda à tela inicial"** (ou: menu ⋮ no canto
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
  **https://fazenda-app-jfye.vercel.app/** — o app é a versão de campo, enxuta de propósito.
