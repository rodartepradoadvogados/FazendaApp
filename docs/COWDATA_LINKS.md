# CowData — todos os links, num lugar só

> **Sobre a pasta.** Não existe (nem existia) uma pasta `CowData-Milk` neste
> repositório — as únicas pastas de documentação são `docs/` (esta) e
> `docs/security-audit/`. Este arquivo foi criado em `docs/`, ao lado de
> `APP_INSTALACAO.md`, que é o passo a passo detalhado de instalação no
> celular. Se a pasta `CowData-Milk` existe em outro lugar (Drive, notebook,
> WhatsApp), é só copiar este arquivo para lá — ele é autocontido.

Atualizado em 06/09/2026.

---

## 1. Site completo (uso no computador e no notebook)

| O que | Link |
| --- | --- |
| Sistema (site completo) | **https://fazenda-app-jfye.vercel.app** |
| Entrar direto na tela de login | https://fazenda-app-jfye.vercel.app/login |
| Trocar de fazenda / Painel CowData | https://fazenda-app-jfye.vercel.app/escolher-conta |
| Painel CowData (administração da empresa) | https://fazenda-app-jfye.vercel.app/painel-cowdata |

É o mesmo endereço para todo mundo: o que cada pessoa vê depende do usuário e
da fazenda com que ela entra.

### Instalar o SITE como aplicativo (PWA de computador/notebook)

1. Abra **https://fazenda-app-jfye.vercel.app** no Chrome ou no Edge e faça o login.
2. Na barra de endereço, à direita, clique no ícone de **instalar** (um monitor
   com uma seta para baixo) — ou vá em menu **⋮ → Salvar e compartilhar →
   Instalar página como aplicativo**.
3. Confirme em **Instalar**. Aparece um ícone na área de trabalho / barra de tarefas.

**O aplicativo instalado no computador abre o SITE COMPLETO**, com o menu
lateral de sempre. Não é mais preciso ir em "acessar site completo" no menu do
navegador — isso era um defeito, corrigido em 06/09/2026.

> Se o seu atalho antigo ainda abrir a versão de celular: feche o aplicativo,
> abra o site no navegador uma vez (o Chrome aproveita para atualizar as
> informações do atalho) e abra o ícone de novo. Se insistir, desinstale o
> atalho e instale outra vez pelo passo a passo acima.

---

## 2. App de campo (uso no celular, no curral)

| O que | Link |
| --- | --- |
| App de campo pelo navegador (PWA) | **https://fazenda-app-jfye.vercel.app/app** |
| App nativo Android (`.apk`) | GitHub → repositório `rodartepradoadvogados/FazendaApp` → aba **Actions** → fluxo **"Gerar .apk de debug"** → última execução → seção **Artifacts** → baixar `app-debug.apk` |
| Passo a passo completo de instalação | [`docs/APP_INSTALACAO.md`](./APP_INSTALACAO.md) |

### Instalar o APP DE CAMPO no celular (PWA)

- **Android (Chrome)**: abra `…/app`, faça login, menu **⋮ → Adicionar à tela
  inicial / Instalar app**.
- **iPhone (Safari — tem que ser o Safari)**: abra `…/app`, faça login, botão
  **Compartilhar** → **Adicionar à Tela de Início**.

No celular o ícone abre direto o app de campo (agenda, lançamentos, rebanho,
menu) — mesmo o atalho tendo o endereço do site, o sistema reconhece a tela
pequena e leva para `/app` sozinho.

### App nativo Android (.apk)

O `.apk` é gerado pelo GitHub Actions a cada versão. Ainda é uma versão de
teste (fora da Play Store), então o Android avisa "app de fonte desconhecida" —
é só tocar em **Instalar mesmo assim**. Detalhes e prints em
[`docs/APP_INSTALACAO.md`](./APP_INSTALACAO.md).

---

## 3. Bastidores (só para a equipe CowData)

| O que | Link |
| --- | --- |
| API / backend (produção, Railway) | https://fazendaapp-production.up.railway.app |
| Documentação automática da API | https://fazendaapp-production.up.railway.app/docs |
| Repositório do código | https://github.com/rodartepradoadvogados/FazendaApp |
| Build do app Android | https://github.com/rodartepradoadvogados/FazendaApp/actions/workflows/build-android.yml |
| Hospedagem do site | Vercel (projeto `fazenda-app`) |
| Hospedagem da API e do banco | Railway (projeto `FazendaApp`, ambiente `production`) |

O endereço da API não precisa ser digitado por ninguém: o site já sabe qual é.
Ele está aqui só para diagnóstico ("a API está no ar?" → abrir `/docs`).

---

## 4. Perguntas rápidas

**Qual link eu mando para um funcionário novo?**
`https://fazenda-app-jfye.vercel.app/app` — é o app de campo. Ele instala em
1 minuto e usa o próprio usuário e senha.

**E para o veterinário / contador / sócio, que usa no computador?**
`https://fazenda-app-jfye.vercel.app` — o site completo.

**É o mesmo login nos dois?**
Sim. Site, app de campo e app nativo são o mesmo sistema, com os mesmos dados.

**Tenho acesso a mais de uma fazenda. Como troco?**
Menu → **Trocar de conta**, ou direto em
`https://fazenda-app-jfye.vercel.app/escolher-conta`. A fazenda em que você já
está aparece marcada como **CONTINUAR AQUI** e é clicável — dá para voltar para
ela sem precisar entrar em outra antes.

**Por que às vezes ele pergunta de novo em qual fazenda quero entrar?**
Só quando você fica mais de 15 minutos fora da tela, ou quando sai do sistema
de propósito. Navegar entre telas não pergunta nada.
