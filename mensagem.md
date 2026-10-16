# A mensagem do Telegram

Princípio: **a mensagem mostra o que mudou. O detalhe fica no PDF.**

Edite o bloco PROPOSTA. É isso que eu levo para o código.

---

## HOJE (16 linhas)

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

## PROPOSTA (6 linhas)

```
Price Tracker · 16/10

1 mudança

Combo · Vivo Família 2 + TV
  390,00 → 290,00   -26%   em todas as 20 praças

Relatório completo em anexo · tmt-price-tracker.vercel.app
```

A linha abre pela **categoria**, que é por onde se lê um aviso de preço:
"mexeram no combo" antes de "a Vivo mexeu". Com várias mudanças no mesmo
dia, dá para agrupar de olho.

**O que saiu, e para onde foi:** entrada por produto, telemetria e a nota
do que não deu para comparar — tudo isso já está no PDF.

---

## Os outros dois dias

### Dia sem mudança

```
Price Tracker · 17/10

Nenhuma mudança de preço ou composição.

Relatório completo em anexo · tmt-price-tracker.vercel.app
```

### Dia em que a coleta falhou

A falha vira manchete, porque número de dia incompleto engana.

```
Price Tracker · 18/10

COLETA INCOMPLETA — Claro em 12 de 20 praças, Unifique sem registro.
O que vem abaixo vale só para o que foi coletado.

1 mudança

Pós-pago · Claro Pós
  124,90 → 139,90   +12%   em 12 praças

Relatório completo em anexo · tmt-price-tracker.vercel.app
```

---

## Decisões soltas

Risque o que não quiser:

- Mais de 3 mudanças num dia: mostra as 3 maiores e escreve "e mais N".
- Mudança de conteúdo com preço parado entra como
  `Pós-pago · Claro Pós — mesmo preço, outra composição`.
- A linha "(a franquia também mudou)" sai.
- A lista "Sem mudança: ..." sai.
