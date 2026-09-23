# TMT Price Tracker

Monitoramento diário de preços de telecomunicações no varejo brasileiro.

**Projeto separado do Dashboard TMT (Anatel).** Nada daqui vai para o
repositório do Dashboard nem para o Vercel sem autorização explícita.

## O que é

Captura diária das ofertas públicas de seis operadoras, em vinte praças, para
construir a série histórica que hoje não existe: preço cheio e preço promocional
guardados **separados**, com fidelidade, multa, taxa de instalação e franquia
contratual, dia a dia.

## Escopo (decidido)

| Dimensão | Definição |
|---|---|
| Produtos | banda larga FTTH, móvel pós-pago, combo, pré-pago |
| Players | Vivo, TIM, Claro, Brisanet, Unifique, NuCel |
| Praças | 20 (16 capitais de Sul/Sudeste/Nordeste + Brasília, Manaus, Blumenau, Joinville) |
| Frequência | diária |
| Granularidade | toda oferta visível na vitrine vira uma linha |

## Princípios

1. **Append-only.** Uma captura nunca sobrescreve outra.
2. **O que não for capturado hoje está perdido.** Não existe coleta retroativa
   de preço.
3. **Falha vira buraco, não vira número.** Nunca interpolar nem repetir o dia
   anterior.
4. **Ausência é ausência, nunca zero.** Operadora que não vende na praça deixa
   célula vazia.

## Estado

Em definição de metodologia. Nenhum coletor escrito ainda.

- `metodologia.html` — documento vivo, com as decisões fechadas e as pendentes.

## Metodologia

Abrir `metodologia.html` no navegador.
