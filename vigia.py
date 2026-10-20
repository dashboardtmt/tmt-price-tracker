# -*- coding: utf-8 -*-
"""Olha o dado do dia e denuncia o que esta estranho.

POR QUE EXISTE. As varreduras que acharam os defeitos deste mes foram
todas feitas na mao, quando alguem desconfiou. Elas acharam preco
fantasma de R$ 24,60, 119 linhas por dia sem velocidade, 20 ofertas
indistinguiveis por dia e nomes com banner de campanha colado. Nenhum
deles apareceu porque o sistema avisou - apareceram porque alguem foi
olhar.

Isso nao escala e nao e confiavel: depende de lembrar de olhar.

O QUE ELE FAZ. Roda depois da coleta, compara o dia com os anteriores e
devolve uma lista de achados com gravidade. Os graves entram na mensagem
do dia; todos entram no relatorio.

O QUE ELE NAO FAZ. Nao corrige nada, nao apaga nada, nao impede a
publicacao. Dado estranho pode ser a operadora fazendo algo estranho - e
nesse caso a denuncia e a noticia, nao o erro.

O NORMAL E MEDIDO, NAO CHUTADO. "Poucas ofertas" so faz sentido
comparado com os dias anteriores da mesma operadora. Limite fixo
envelhece: a Claro tinha 280 ofertas por dia no inicio do mes e tem 364
agora, e qualquer numero cravado hoje estaria errado em duas semanas.
"""
import collections

# Piso de sanidade, nao de plausibilidade. A Vivo Pre custa R$ 20 e a
# TIM vende recarga de R$ 20 - preco baixo nao e, por si so, suspeito.
# Abaixo de R$ 5 nao existe plano no varejo, e o que aparece ali e
# numero de outra coisa que vazou para o campo.
#
# O PRECO FANTASMA NAO SE PEGA POR LIMITE FIXO. Os R$ 24,60 que a Claro
# gravou em 07/10 - o preco avulso do Disney+ citado no proprio card -
# estao muito acima de qualquer piso razoavel. O que os denunciava era
# serem -75% do que aquela mesma oferta custou no dia anterior, e quem
# pega isso e o detector de salto.
PISO_PRECO = 5.0

# E acima disto e equipamento, instalacao ou erro de virgula.
TETO_PRECO = 3000.0

# Quanto a contagem de ofertas de uma operadora pode cair em relacao a
# mediana dos dias anteriores antes de virar denuncia. Vitrine muda, e
# queda pequena e vida normal.
QUEDA_QUE_PREOCUPA = 0.25

# Salto de preco que merece conferencia. Reajuste existe; o que nao
# existe e reajuste de 60% da noite para o dia sem nada mais mudar.
SALTO_QUE_PREOCUPA = 0.50


def _entrega(o):
    return o.get("degrau_mbps") or o.get("franquia_anunciada_gb")


def _mediana(valores):
    v = sorted(valores)
    if not v:
        return None
    meio = len(v) // 2
    return v[meio] if len(v) % 2 else (v[meio - 1] + v[meio]) / 2.0


def achados(hoje, anteriores):
    """Devolve [(gravidade, texto)] com o que esta estranho no dia.

    hoje:       lista de capturas do dia
    anteriores: {data: lista de capturas} dos dias usados como referencia
    """
    saida = []

    def grave(t):
        saida.append(("grave", t))

    def atencao(t):
        saida.append(("atencao", t))

    if not hoje:
        grave("nenhuma captura hoje")
        return saida

    # ------------------------------------------------ preco impossivel
    fora = [o for o in hoje
            if o.get("preco_promocional") is not None
            and not (PISO_PRECO <= o["preco_promocional"] <= TETO_PRECO)]
    if fora:
        exemplo = min(fora, key=lambda o: o["preco_promocional"])
        grave("%d oferta(s) com preco fora da faixa de varejo, a menor "
              "delas %s a R$ %.2f"
              % (len(fora), (exemplo.get("nome_oferta") or "?")[:34],
                 exemplo["preco_promocional"]))

    # ------------------------------------------------ sem preco
    sem_preco = [o for o in hoje if o.get("preco_promocional") is None]
    if sem_preco:
        atencao("%d oferta(s) sem preco" % len(sem_preco))

    # ------------------------------------------------ sem entrega
    sem_entrega = collections.Counter(
        o.get("operadora") for o in hoje if _entrega(o) is None)
    for op, n in sem_entrega.most_common():
        # uma ou outra acontece; a operadora inteira sem entrega e
        # defeito de leitura, como foi com a Brisanet
        total = sum(1 for o in hoje if o.get("operadora") == op)
        if n >= max(5, total * 0.5):
            grave("%s: %d de %d ofertas sem velocidade nem franquia"
                  % (op, n, total))

    # ------------------------------------------------ indistinguiveis
    ident = collections.Counter(
        (o.get("operadora"), o.get("produto"), o.get("praca"),
         o.get("chave"), (o.get("nome_oferta") or "").lower())
        for o in hoje)
    colididas = sum(n - 1 for n in ident.values() if n > 1)
    if colididas:
        quais = sorted({k[4] for k, n in ident.items() if n > 1})[:2]
        atencao("%d oferta(s) indistinguiveis entre si (%s): o comparador "
                "so ve uma de cada par" % (colididas, "; ".join(quais)))

    # ------------------------------------------------ volume por operadora
    por_op_hoje = collections.Counter(o.get("operadora") for o in hoje)
    historico = collections.defaultdict(list)
    for _dia, linhas in sorted(anteriores.items()):
        c = collections.Counter(o.get("operadora") for o in linhas)
        for op, n in c.items():
            historico[op].append(n)

    for op, antes in historico.items():
        if len(antes) < 3:
            continue
        tipico = _mediana(antes)
        agora = por_op_hoje.get(op, 0)
        if not tipico:
            continue
        if agora == 0:
            grave("%s nao trouxe nenhuma oferta hoje (tipico: %d)"
                  % (op, tipico))
        elif (tipico - agora) / float(tipico) >= QUEDA_QUE_PREOCUPA:
            atencao("%s trouxe %d ofertas hoje, contra %d tipicos"
                    % (op, agora, int(tipico)))

    # operadora que existia e sumiu do dia inteiro
    sumiram = set(historico) - set(por_op_hoje)
    for op in sorted(sumiram):
        if len(historico[op]) >= 3:
            grave("%s nao aparece hoje" % op)

    # ------------------------------------------------ salto de preco
    if anteriores:
        ultimo = max(anteriores)
        antes = {}
        for o in anteriores[ultimo]:
            if o.get("preco_promocional") is None:
                continue
            antes[(o.get("operadora"), o.get("produto"), o.get("praca"),
                   (o.get("nome_oferta") or "").lower(), _entrega(o))] = \
                o["preco_promocional"]
        saltos = []
        for o in hoje:
            p = o.get("preco_promocional")
            if p is None:
                continue
            k = (o.get("operadora"), o.get("produto"), o.get("praca"),
                 (o.get("nome_oferta") or "").lower(), _entrega(o))
            a = antes.get(k)
            if a and abs(p - a) / a >= SALTO_QUE_PREOCUPA:
                saltos.append((abs(p - a) / a, o, a, p))
        if saltos:
            # ordena so pelo tamanho do salto: com empate, o Python
            # tentaria comparar os dicionarios de oferta e estouraria
            saltos.sort(key=lambda x: x[0], reverse=True)
            pc, o, a, p = saltos[0]
            atencao("%d salto(s) de preco acima de %d%%, o maior em %s "
                    "(R$ %.2f para R$ %.2f)"
                    % (len(saltos), int(SALTO_QUE_PREOCUPA * 100),
                       (o.get("nome_oferta") or "?")[:30], a, p))

    # ------------------------------------------------ nome suspeito
    vazios = sum(1 for o in hoje if not (o.get("nome_oferta") or "").strip())
    if vazios:
        atencao("%d oferta(s) sem nome" % vazios)

    return saida


def resumo(lista):
    """Uma linha para a mensagem, ou vazio quando nao ha o que dizer."""
    graves = [t for g, t in lista if g == "grave"]
    if graves:
        return "Conferir: %s" % graves[0]
    return ""
