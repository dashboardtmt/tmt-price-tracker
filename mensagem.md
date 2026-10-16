# A mensagem diária do Telegram

Documento de trabalho. **Edite o texto dentro dos blocos `DEPOIS`** e eu
levo para o código. O que estiver em `HOJE` é exatamente o que sai agora.

Cada bloco diz **quando aparece** — vários são condicionais e você pode
nunca ter visto alguns deles.

---

## A mensagem inteira, como saiu em 16/10

```
Price Tracker · 16/10

1 mudança hoje

Vivo · Família 2 + TV
  390,00 → 290,00  -26%   em todas as 20 praças
  (a franquia também mudou)

Sem mudança: Brisanet, Claro, NuCel, Starlink, TIM, Unifique

Entrada em SP
  Controle        TIM 58,99 · Vivo 59,00 · Claro 59,90
  Fibra           Claro 79,90 · TIM 79,99 · Vivo 100,00
  Pós-pago        Claro 124,90 · Vivo 150,00 · TIM 169,99
  Below-the-line  Vivo 30,00

Ponto cego: 20 oferta(s) não foram comparadas por compartilharem chave de
série, praça e nome com outra oferta (Vivo Família 2 + TV). Não é possível
afirmar se houve variação de preço nelas.

1660 ofertas · 9 coletores · 20 praças · tudo ok
```

E vai um PDF anexado, com o catálogo de controle, below-the-line,
pré-pago e combo.

---

## Bloco 1 — cabeçalho

**Quando aparece:** sempre.

HOJE
```
Price Tracker · 16/10
```

DEPOIS
```
Price Tracker · 16/10
```

---

## Bloco 2 — manchete de falha

**Quando aparece:** só quando a coleta não rodou ou veio incompleta.
Nesse caso ela vem ANTES de tudo, porque número de dia incompleto engana.

HOJE
```
O ROBÔ NÃO RODOU HOJE.
Nenhum registro de coleta. Nada do que vem abaixo é de hoje.
```
ou
```
ATENÇÃO: a coleta de hoje está incompleta.
  Claro: 12 de 20 praças
  sem registro: Unifique
  Operadora incompleta deixa buraco, nunca zero.
```

DEPOIS
```

```

---

## Bloco 3 — o contador de mudanças

**Quando aparece:** sempre que a comparação com ontem funcionou.

HOJE
```
1 mudança hoje
```
ou, quando não houve nenhuma:
```
Nenhuma mudança de preço, composição ou nome.
```

DEPOIS
```

```

---

## Bloco 4 — cada mudança de preço

**Quando aparece:** uma vez por oferta que mudou de preço. Até 3, depois
vira "e mais N".

HOJE
```
Vivo · Família 2 + TV
  390,00 → 290,00  -26%   em todas as 20 praças
  (a franquia também mudou)
```

**O que cada parte é:** o nome da oferta sem repetir a operadora; preço de
ontem, preço de hoje, variação; onde valeu (lista as praças quando são
poucas, "em todas as N praças" quando são quase todas). A linha entre
parênteses só sai quando a franquia mudou junto.

DEPOIS
```

```

---

## Bloco 5 — mudança de conteúdo com preço parado

**Quando aparece:** quando a oferta manteve o preço e trocou os serviços
inclusos. Não apareceu em 16/10.

HOJE
```
Claro · Claro Pós — mesmo preço, outra composição
  em 20 praças
```

DEPOIS
```

```

---

## Bloco 6 — quem não mexeu

**Quando aparece:** quando houve alguma mudança no dia. Lista as
operadoras que ficaram paradas.

HOJE
```
Sem mudança: Brisanet, Claro, NuCel, Starlink, TIM, Unifique
```

DEPOIS
```

```

---

## Bloco 7 — preço de entrada

**Quando aparece:** sempre. Mostra o plano mais barato de cada operadora,
em São Paulo, em quatro produtos.

**Ponto em aberto:** este bloco traz Fibra e Pós-pago, que você tirou do
PDF. O PDF traz controle, below-the-line, pré-pago e combo. Os dois estão
em listas diferentes hoje.

HOJE
```
Entrada em SP
  Controle        TIM 58,99 · Vivo 59,00 · Claro 59,90
  Fibra           Claro 79,90 · TIM 79,99 · Vivo 100,00
  Pós-pago        Claro 124,90 · Vivo 150,00 · TIM 169,99
  Below-the-line  Vivo 30,00
```

DEPOIS
```

```

---

## Bloco 8 — a nota do que não deu para comparar

**Quando aparece:** só quando duas ofertas têm chave, praça e nome iguais.
Deve parar de aparecer a partir de 17/10.

**No PDF esta mesma nota se chama "Nota metodológica".**

HOJE
```
Ponto cego: 20 oferta(s) não foram comparadas por compartilharem chave de
série, praça e nome com outra oferta (Vivo Família 2 + TV). Não é possível
afirmar se houve variação de preço nelas.
```

DEPOIS
```

```

---

## Bloco 9 — telemetria

**Quando aparece:** sempre que a coleta terminou sem falha.

HOJE
```
1660 ofertas · 9 coletores · 20 praças · tudo ok
```

DEPOIS
```

```

---

## Bloco 10 — link do painel

**Quando aparece:** não existe hoje. O PDF tem o link, a mensagem não.

DEPOIS
```

```

---

## Coisas que não são texto, mas mudam a mensagem

Marque o que quiser que eu mude:

- [ ] **Ordem dos blocos.** Hoje: falha, mudanças, quem não mexeu,
      entrada, nota, telemetria.
- [ ] **Quantas mudanças antes de resumir.** Hoje mostra 3 e escreve "e
      mais N".
- [ ] **A praça de referência.** Hoje é São Paulo em todo o bloco de
      entrada.
- [ ] **O PDF vai como anexo separado.** Dá para mandar como legenda do
      próprio PDF, mas o Telegram corta legenda em 1.024 caracteres.
- [ ] **Negrito e itálico.** Hoje a mensagem vai em texto puro. O Telegram
      aceita formatação; se usar, o texto fica mais pesado de ler em
      mensagem longa.
