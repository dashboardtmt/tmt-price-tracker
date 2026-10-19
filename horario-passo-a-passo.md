# Fazer a mensagem chegar de manhã — o que falta

O código está pronto e no ar. Falta **uma coisa**, que só você pode
fazer: criar um token do GitHub. Leva uns 3 minutos.

---

## O que já está funcionando, desde agora

**Os oito agendamentos do GitHub.** Em vez de um às 07:07, oito ao longo
da madrugada. O primeiro que o GitHub disparar faz o trabalho; os outros
perguntam ao banco, veem que o dia já foi, e encerram em segundos.

Isso sozinho já deve adiantar bastante a entrega, porque o atraso varia
a cada evento — com oito chances, a mais pontual ganha. Mas não é
garantia.

## O que falta, para ser garantia

**O Vercel chamando o GitHub na hora certa.** O atraso só existe no
agendamento do GitHub; um disparo direto sai no instante da chamada. A
função já está escrita e o horário já está configurado para **06:00 da
manhã**.

Ela só precisa de um token para poder falar com o GitHub.

---

## Passo 1 — criar o token (no GitHub)

1. Abra **https://github.com/settings/personal-access-tokens/new**

   > Precisa estar logado na conta **dashboardtmt**. Se aparecer outra
   > conta no canto, troque antes.

2. Preencha:

   | Campo | O que pôr |
   |---|---|
   | **Token name** | `Disparar robo` |
   | **Expiration** | escolha **No expiration**, ou a data mais longa |
   | **Resource owner** | dashboardtmt |

3. Em **Repository access**, marque **Only select repositories** e
   escolha **tmt-price-tracker**

4. Em **Permissions** → **Repository permissions**, procure **Actions** e
   mude para **Read and write**

   > Só essa. Nenhuma outra permissão é necessária — esse token só pode
   > mandar o robô rodar, nada além disso.

5. Clique em **Generate token** e **copie** o que aparecer (começa com
   `github_pat_`)

---

## Passo 2 — me avisar

Me diga "pronto" e eu guardo o token no Vercel e disparo um teste. Em um
minuto a gente sabe se funcionou.

**Não cole o token aqui no chat.** Me avise que está pronto e eu te passo
o comando para você rodar — ele guarda o token sem que ninguém veja.

---

## Como vai funcionar depois

```
06:00  o Vercel chama o GitHub
06:00  o GitHub começa a coleta na hora
06:40  a mensagem e o PDF chegam no Telegram
```

E os oito agendamentos do GitHub continuam lá como rede de segurança: se
o Vercel falhar, se o token expirar ou se o projeto sair do ar, o robô
ainda entrega — mais tarde, mas entrega. A guarda no banco impede que os
dois caminhos coletem duas vezes.

> Uma ressalva: no plano gratuito, o Vercel dispara **dentro da hora**
> agendada, não no minuto exato. Então a mensagem sai entre 06:00 e
> 07:00, e não às 06:00 cravadas. Contra as 3,5 a 9,6 horas de atraso de
> hoje, é outro mundo.

## Se quiser desligar

Apague a variável do Vercel. O robô volta a depender só dos
agendamentos do GitHub, sem quebrar nada.
