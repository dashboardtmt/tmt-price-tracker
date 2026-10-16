# Ligar o e-mail diário — passo a passo

O código já está pronto e instalado. Falta só você fazer **duas coisas**,
que só você pode fazer. Leva uns 10 minutos.

Quando terminar, o robô passa a mandar, todo dia, a mesma mensagem do
Telegram por e-mail, com o relatório em PDF anexado.

---

## Antes de começar: por que precisa de "senha de app"

O Google **não deixa** nenhum programa entrar numa conta com a senha
normal. Em vez disso, você gera uma **senha de app**: uma senha separada,
de 16 letras, que serve só para enviar e-mail.

Duas coisas importantes sobre ela:

- Ela **não substitui** sua senha. Seu login no celular e no computador
  continua igual.
- Você pode **apagar** essa senha a qualquer momento, e só o envio de
  e-mail para de funcionar. Nada mais é afetado.

**Eu nunca vejo essa senha.** Você cola ela direto no GitHub, num cofre
que nem eu nem ninguém consegue abrir depois — nem o próprio GitHub
mostra o valor de volta.

---

## Parte 1 — gerar a senha de app (no Google)

### Passo 1. Ligar a verificação em duas etapas

A senha de app só existe se a conta tiver verificação em duas etapas. Se
a sua já tem, pule para o passo 2.

1. Abra **https://myaccount.google.com/security**
2. Procure **"Verificação em duas etapas"**
3. Se estiver como **Desativada**, clique e siga — ele vai pedir seu
   celular e mandar um código

### Passo 2. Gerar a senha

1. Abra **https://myaccount.google.com/apppasswords**
2. Se ele pedir sua senha do Google, digite
3. No campo **"Nome do app"**, escreva: `Price Tracker`
4. Clique em **Criar**
5. Aparece uma caixa amarela com **16 letras**, tipo `abcd efgh ijkl mnop`

**Copie essas 16 letras agora.** Essa tela não volta. Se perder, é só
gerar outra — não tem problema nenhum.

> Se a página de senhas de app disser que não está disponível, é porque a
> verificação em duas etapas ainda não está ligada. Volte ao passo 1.

---

## Parte 2 — guardar no GitHub

Agora você vai colar isso num cofre do repositório. São três entradas.

1. Abra **https://github.com/dashboardtmt/tmt-price-tracker/settings/secrets/actions**

   > Se aparecer "404", você está logado na conta errada do GitHub.
   > Saia e entre com a conta **dashboardtmt**.

2. Clique no botão verde **"New repository secret"**

3. Crie as três, uma de cada vez — sempre **Name**, depois **Secret**,
   depois **Add secret**:

   | Name | Secret (o que colar) |
   |---|---|
   | `EMAIL_REMETENTE` | seu endereço do Gmail, inteiro |
   | `EMAIL_SENHA_APP` | as 16 letras do passo 2 |
   | `EMAIL_DESTINO` | para onde o relatório vai |

**Sobre o `EMAIL_DESTINO`:** pode ser o mesmo endereço do remetente, ou
outro qualquer. Para mandar para mais de um, separe por vírgula:

```
leonardo@exemplo.com, outra.pessoa@exemplo.com
```

**Sobre o `EMAIL_SENHA_APP`:** pode colar com os espaços, do jeito que o
Google mostrou. O código tira os espaços sozinho.

---

## Parte 3 — me avisar

Me diga "pronto" e eu disparo um envio de teste. Em um minuto a gente
sabe se funcionou, e eu te mostro o resultado.

Se der errado, o log diz exatamente o quê. O erro mais comum é colar a
senha da conta em vez da senha de app — e nesse caso a mensagem já vem
dizendo isso.

---

## O que acontece depois

Todo dia, junto com o Telegram:

- **Assunto:** TMT Price Tracker - relatório de 17/10/2026
- **Corpo:** a mesma mensagem curta do Telegram
- **Anexo:** o PDF com as tabelas

Se o e-mail falhar num dia, **o Telegram chega mesmo assim**. O e-mail é
o canal secundário, e problema nele não derruba o aviso.

Para desligar, apague os três segredos. O robô volta a mandar só o
Telegram, sem reclamar.
