# Como auditar este projeto

Este arquivo é o briefing de quem for auditar o Price Tracker — pessoa ou
agente. Ele existe porque o que cada auditoria aprende morre com ela: em
seis rodadas, 74 defeitos foram encontrados, e cada nova leitura começava
do zero redescobrindo o mesmo mapa.

Não é a lista dos defeitos. É a lista das **famílias** de defeito, de
onde elas aparecem, e de onde ninguém olhou ainda.

---

## A régua

**O projeto existe para não afirmar o que a fonte não sustenta.** Essa é
a única regra, e todas as outras saem dela.

Em ordem de gravidade:

1. **Afirmação positiva de ausência.** "Nenhuma mudança de preço" num dia
   em que houve. É o pior de todos porque não se parece com erro: soa
   como notícia verificada.
2. **Número inventado.** Um `-26%` que vem de qual linha o banco
   devolveu primeiro. Um `+0%` calculado sobre um preço de R$ 0,00.
3. **Campo não lido apresentado como valor.** "mesma entrega (None)",
   "pelo mesmo preço (-)", ausência virando zero.
4. **Atribuição errada.** Dizer que a operadora reposicionou quando quem
   mudou foi o nosso parser.

**A régua é a garantia, não a frequência.** Metade do que foi corrigido
nunca tinha acontecido no dado real — zero de 31.727 capturas estão sem
preço. Corrigiu-se assim mesmo, porque se o critério for "já aconteceu",
ele vira elástico e a metade seguinte também passa.

---

## As famílias de defeito

Cada uma apareceu em vários arquivos. Procure a família, não o caso.

### 1. A fronteira entre dois componentes

**Todos** os defeitos graves estavam entre dois componentes que cada um
achava que o outro tinha conferido. Nenhum estava dentro de uma função.

- mensagem contra PDF: a frase foi corrigida num e não no outro, duas vezes
- índice contra tabela crua: `_indexar` descarta o par indistinguível e
  `_degraus_que_voltaram` lê o banco direto, sem saber
- um detector contra outro: a mesma oferta de ontem servindo de "antes"
  para dois eventos; o mesmo reajuste contado como grade e como "voltou"
- o portão contra o job de alerta: um pergunta "preciso coletar?" e o
  outro usa a resposta como "foi coletado?"

**Como procurar:** liste quem lê o mesmo dado. Para cada par, pergunte o
que aconteceria se um mudasse e o outro não.

### 2. O rótulo que fala por um conjunto

Dez ocorrências na tela, todas o mesmo gesto: um texto compartilhado —
cabeçalho de coluna, título de eixo, rótulo de faixa — escolhido pegando
`lista[0]`. Cada número individual estava certo; o texto que falava por
todos, não.

O caso que dói é a Starlink, único produto de unidade mista: 100 e 400
Mbps ao lado de 50, 500, 1024 e 2048 GB, em 300 de 300 combinações de
praça e dia.

**Como procurar:** `grep` por `[0]` perto de qualquer coisa que vire
texto na tela. E por unidade escrita à mão no HTML.

### 3. O código de erro

A segunda auditoria achou nove graves e os nove estavam no caminho de
erro: consulta que cai, lista vazia, `None` formatado como número.
Código de sucesso a gente testa; código de erro a gente escreve e nunca
mais olha — e é onde a afirmação falsa mora.

**Como procurar:** para cada consulta, pergunte o que a mensagem diz se
ela falhar. Para cada lista, o que ela diz se vier vazia.

### 4. O sorteio publicado como fato

Duas ofertas que dividem chave, praça e nome. Guardar uma delas parecia
"aproveitar o que dá"; era sortear qual define o preço do dia, e o
sorteio muda quando a vitrine muda. Produziu um `-26%` falso duas vezes,
por dois caminhos diferentes.

**Como procurar:** todo lugar que faz `if k in indice` ou pega o primeiro
de um grupo. Se o grupo tem mais de um com significados diferentes, ou
sai inteiro, ou vira palpite.

### 5. A fixture uniforme

Três rodadas seguidas o provador de mutações reprovou testes meus
passando pelo motivo errado, sempre igual: fixture montada com
`em_todas`, que põe a oferta nas 20 praças. Defeito de alcance —
"protege uma praça e deixa 19" — fica invisível.

**Como procurar:** teste que monta tudo com `em_todas` não testa alcance,
testa o caso fácil. Monte pelo menos um com a situação em UMA praça que
não é a primeira.

---

## Onde já se olhou, e onde não

| superfície | rodadas | achados |
|---|---|---|
| `robo.py` (comparador e mensagem) | 5 | 48 |
| `relatorio.py` (PDF) | 5 | 9 |
| `vigia.py` | 5 | 7 |
| `ja_coletou.py` e os workflows | 4 | 8 |
| `gerar_tela.py` | 1 | 10 |
| **coletores** | em curso | — |
| `exportar.py`, `publicar_dados.py` | **nunca** | — |

`ofertas_do_produto` (em `robo.py`) deduplica por
`(operadora, nome, destaque, preço)` — chave diferente das outras três do
projeto, e a única que nunca passou por auditoria.

---

## Como medir

Não aceite "parece certo". Meça.

**O dado real** — 32.771 capturas de 21 dias, sem credencial:

```bash
curl -s -o dados.json "https://iuopzrxfmobllhkyuvkk.supabase.co/storage/v1/object/public/tela/dados.json"
```

Não há credencial do Supabase nesta máquina: os segredos vivem só no
GitHub. O `dados.json` do repositório é uma cópia velha.

**A mensagem de qualquer dia** — monte um banco de mentira que responda
`consultar`/`consultar_tudo` filtrando por `data_captura`, e chame
`robo.montar_mensagem(dia, ontem)` para cada dia da série. Olhe duas
coisas: se os dias de evento conhecido aparecem, e se os dias normais
ficam calados. Vigia que grita todo dia vira ruído.

**A tela** — `testes/tela_em_node.mjs` roda o JavaScript dela num DOM de
mentira e devolve o HTML que cada tabela produz e os datasets de cada
gráfico. Não é navegador, não mede layout, mas o texto é o de verdade — e
texto é o que afirma.

**Os coletores, sem gravar nada:**

```bash
python robo.py --coletar --simular --praca "Sao Paulo/SP"
```

---

## As ferramentas que já existem

- **245 testes** (`python -m unittest discover -s testes`)
- **73 mutações** (`python testes/provar_a_suite.py`) — reintroduz cada
  defeito real e exige que a suíte fique vermelha. Rode isto **antes** de
  ler o código: ele diz quais testes não servem, e já apontou testes meus
  passando pelo motivo errado em três rodadas seguidas.
- **`metodologia.html`** — 51 decisões, cada uma com o número que a
  motivou. Se uma decisão sua contradiz uma de lá, uma das duas está
  errada e vale descobrir qual antes de escrever código.

---

## Restrições de quem audita

- **Não altere arquivo nenhum.** Leia, rode, meça.
- Nada que escreva no banco, mande Telegram ou publique no Vercel.
- `robo.py --coletar` só com `--simular`.
- Não dispare workflow.
- Não bata mais de 2 ou 3 praças por operadora: cada chamada vai na
  vitrine real.

## O que se espera de volta

Para cada achado: gravidade, arquivo e linha, o **cenário concreto** de
entrada, o efeito errado, e quantas capturas reais estão nesse estado.

"Linha X assume Y, e com a entrada Z sai W" vale. "Poderia ser mais
robusto" não vale.

**Se não houver nada grave, diga isso** em vez de promover um achado
médio — e nesse caso diga qual parte deixou você mais desconfiado mesmo
sem defeito provado. Essa frase já valeu mais que a lista: foi assim que
a tela entrou na fila, e ela tinha cinco graves.
