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

# E a partir daqui nao e mais reajuste: o achado vira GRAVE e chega a
# mensagem, em vez de ficar no relatorio.
#
# DOIS LIMITES, PORQUE SAO DUAS ESCALAS. Queda nunca passa de 100%, e
# com um limite simetrico de 100% o lado de BAIXO - que e justamente o
# lado do preco fantasma: R$ 24,60 no lugar de R$ 99,90, -75% - nunca
# poderia ser grave, e o detector seguiria calado onde importa.
#
# Perder metade do preco com nome e entrega iguais e quase sempre
# numero de outra coisa que vazou para o campo. Dobrar tambem, e o lado
# de cima ganha mais folga de proposito: reposicionamento de operadora
# existe e o comparador ja o reporta com nome e praca.
QUEDA_INACREDITAVEL = 0.50
SALTO_INACREDITAVEL = 1.00


def _entrega(o):
    return o.get("degrau_mbps") or o.get("franquia_anunciada_gb")


def _severo(antes, agora):
    """Este salto e grande demais para ser reajuste?

    DOIS LIMITES, PORQUE SAO DUAS ESCALAS - ver QUEDA_INACREDITAVEL e
    SALTO_INACREDITAVEL. Funcao separada porque a resposta e usada duas
    vezes: para decidir a gravidade do grupo e para escolher qual salto
    o texto cita.
    """
    if not antes or agora is None:
        return False
    return (agora <= antes * (1 - QUEDA_INACREDITAVEL)
            or agora >= antes * (1 + SALTO_INACREDITAVEL))


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
        # defeito de leitura, como foi com a Brisanet.
        #
        # O PISO ERA 5, E A NUCEL TEM 3 OFERTAS. Com "max(5, metade)",
        # uma operadora pequena podia perder a franquia de TODAS as
        # ofertas sem o vigia abrir a boca - e operadora pequena e
        # justamente a de coletor mais fragil. Tres linhas erradas em
        # tres e defeito tanto quanto 119 em 119.
        total = sum(1 for o in hoje if o.get("operadora") == op)
        if n >= max(3, total * 0.5):
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

    # UMA DENUNCIA POR FATO. O bloco de volume tinha um ramo para
    # "agora == 0" e logo abaixo havia outro bloco para a operadora que
    # sumiu - e os dois falavam do MESMO caso, porque uma operadora
    # ausente nao e chave do contador de hoje e "agora" volta zero.
    # Saiam as duas linhas, com textos diferentes, e a lista do
    # relatorio contava duas anomalias onde havia uma.
    for op, antes in sorted(historico.items()):
        if len(antes) < 3:
            continue
        tipico = _mediana(antes)
        agora = por_op_hoje.get(op, 0)
        if not tipico:
            continue
        if agora == 0:
            grave("%s nao aparece hoje (tipico: %d ofertas)"
                  % (op, int(tipico)))
        elif (tipico - agora) / float(tipico) >= QUEDA_QUE_PREOCUPA:
            atencao("%s trouxe %d ofertas hoje, contra %d tipicos"
                    % (op, agora, int(tipico)))

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
            # MODULO MAIOR NAO E PIOR. A gravidade saia de saltos[0], o
            # de maior modulo, e isso escondia o pior: medido com Claro
            # 99,90 -> 24,60 (-75%, o formato do preco fantasma) junto
            # com Vivo 100,00 -> 195,00 (+95%, modulo maior e nao
            # severo), o grupo inteiro virava "atencao" e o fantasma nao
            # chegava a mensagem. E o texto que sobrava nomeava a outra
            # operadora, mandando a pessoa olhar a oferta errada.
            severos = [x for x in saltos if _severo(x[2], x[3])]
            # ordena so pelo tamanho do salto: com empate, o Python
            # tentaria comparar os dicionarios de oferta e estouraria
            (severos or saltos).sort(key=lambda x: x[0], reverse=True)
            pc, o, a, p = (severos or saltos)[0]
            # A CONTAGEM DOS SEVEROS APARECE. "20 salto(s) acima de 50%,
            # o mais grave em X" deixa o leitor entender que os 20 sao
            # graves, e em geral e um so.
            quantos = ("%d salto(s) de preco acima de %d%%"
                       % (len(saltos), int(SALTO_QUE_PREOCUPA * 100)))
            if severos:
                quantos += (", %d deles grande demais para ser reajuste"
                            % len(severos))
            texto = ("%s, o %s em %s (R$ %.2f para R$ %.2f)"
                     % (quantos, "mais grave" if severos else "maior",
                        (o.get("nome_oferta") or "?")[:30], a, p))
            # O SALTO INACREDITAVEL CHEGA A MENSAGEM. Era tudo
            # "atencao", e atencao nao sai do relatorio - o detector que
            # pegaria os R$ 24,60 do preco fantasma existia e ficava
            # calado onde importa.
            (grave if severos else atencao)(texto)

    # ------------------------------------------------ nome suspeito
    vazios = sum(1 for o in hoje if not (o.get("nome_oferta") or "").strip())
    if vazios:
        atencao("%d oferta(s) sem nome" % vazios)

    return saida


# A ordem em que os achados graves disputam a vaga da mensagem. O
# critério e quanto cada um muda o que a pessoa faz ao ler, e ele e
# DECLARADO aqui em vez de herdado da ordem em que "achados" os produz.
#
# POR QUE ISTO IMPORTA. A mensagem tem uma vaga: o primeiro grave sai
# inteiro e os outros saem na contagem. Por 18 dos 21 dias medidos o
# primeiro era "Brisanet: 119 de 119 ofertas sem velocidade" - defeito
# de leitura ja corrigido, que se repetia todo dia -, e um achado novo
# entrava atras dele. E segundo plano e a posicao de onde o preco
# fantasma de R$ 24,60 ja ficou calado uma vez.
PRIORIDADE = (
    "nenhuma captura",          # o dia nao existe; nada mais importa
    "nao aparece hoje",         # um nono do mercado desapareceu
    "fora da faixa",            # numero que nao e preco de plano
    "nao deu para conferir",    # a propria conferencia nao aconteceu
    "salto",                    # numero que talvez nao seja daquela oferta
    "sem velocidade",           # leitura quebrada, mas o preco esta la
)


def _peso(texto):
    for i, marca in enumerate(PRIORIDADE):
        if marca in texto:
            return i
    return len(PRIORIDADE)


def resumo(lista):
    """Uma linha para a mensagem, ou vazio quando nao ha o que dizer.

    O RESTO NAO PODE DESAPARECER. Antes saia so o primeiro grave, e com
    isso um preco fora da faixa escondia "Brisanet: 119 de 119 ofertas
    sem velocidade" - o achado maior ficava atras do que veio primeiro
    na lista. Agora o primeiro aparece inteiro, escolhido por
    PRIORIDADE, e os outros aparecem na contagem, que e o que faz
    alguem abrir o relatorio.
    """
    graves = sorted((t for g, t in lista if g == "grave"), key=_peso)
    if not graves:
        return ""
    if len(graves) == 1:
        return "Conferir: %s" % graves[0]
    return ("Conferir: %s \u2014 e mais %d ponto(s) no relat\u00f3rio"
            % (graves[0], len(graves) - 1))
