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


# ------------------------------------------------------------------
# OS DOIS VIGIAS DE SILENCIO, de 09/11/2026.
#
# O RESTO DESTE ARQUIVO PERGUNTA "o que eu coletei hoje faz sentido?".
# Estes dois perguntam outra coisa: "o que parou de aparecer, e ja faz
# dias?". Sao o mesmo defeito com duas caras, e as duas custaram caro:
#
#   - a fibra da TIM ficou 35 dias com 1 oferta de 10, e a mensagem
#     seguiu comparando precos daquela unica oferta como se fosse a
#     prateleira inteira;
#   - a franquia garantida das Vivo Familia ficou 31 dias nula, e a
#     anunciada caiu 10GB no dia seguinte - o que, lido de fora,
#     pareceria a Vivo cortando franquia.
#
# POR QUE NENHUM DOS DOIS APARECEU SOZINHO. Coleta que traz 1 oferta e
# uma coleta de sucesso: nao falha, nao erra, nao pinta vermelho. Campo
# nulo e um valor valido. Nos dois casos o dado continua chegando, so
# que menor - e o sistema inteiro foi desenhado para reclamar do que
# chega errado, nao do que deixa de chegar.
#
# TRES DIAS, E FALA UMA VEZ. Medido nos 41 dias publicados: falar no
# primeiro dia renderia 35 avisos, e 7 das 17 mortes de campo duravam um
# dia so - susto, nao defeito. Esperando o terceiro dia seguido sobram
# OITO avisos em 41 dias, um a cada cinco, e os cinco casos longos que
# ninguem tinha visto estao todos neles. O preco e saber dois dias
# depois; o troco e nunca falar por oscilacao.
#
# O NORMAL E MEDIDO, como no resto do arquivo: a prateleira "encolheu"
# em relacao a mediana dos dias anteriores DAQUELE balde, e nao de um
# numero cravado - a NuCel tem 3 ofertas e a Claro tem 364.
DIAS_PARA_FALAR = 3

# Metade da mediana. Medido: com 50% saem 18 avisos brutos em 41 dias e
# com um terco saem 14, mas o terco perde a TIM que foi de 4 ofertas
# para 1 - que e exatamente o caso que deu origem a isto.
CORTE_DA_PRATELEIRA = 0.5

# Balde com menos de 3 ofertas nao tem queda que signifique alguma
# coisa: sair de 2 para 1 e metade, e nao e noticia.
PRATELEIRA_MINIMA = 3

# Campo que ja vinha falhando metade do tempo nao "morreu": sempre foi
# assim, e isso e outro assunto.
PISO_DE_PREENCHIMENTO = 0.5

# So os campos que o select do vigia traz. Nao adiantar vigiar
# fidelidade ou velocidade declarada aqui: elas nao chegam neste
# levantamento, e pedir por elas engordaria a consulta que foi estreitada
# de proposito.
CAMPOS_VIGIADOS = {
    "franquia_contratual_gb": "a franquia garantida",
    "franquia_anunciada_gb": "a franquia anunciada",
    "degrau_mbps": "a velocidade do degrau",
    "preco_promocional": "o preço promocional",
}

NOME_DO_PRODUTO = {
    "movel": "o móvel", "controle": "o controle", "prepago": "o pré-pago",
    "fibra": "a fibra", "combo": "o combo", "btl": "a linha de entrada",
    "satelite": "o satélite",
}


def _plural(n, singular, plural):
    return "%d %s" % (n, singular if n == 1 else plural)


# Quando as capturas de hoje chegam sem data - acontece em teste e
# aconteceria num select que esquecesse a coluna -, hoje ainda e o dia
# mais novo que existe. Esta marca ordena depois de qualquer data ISO,
# e assim o vigia segue comparando com os dias anteriores em vez de
# emudecer sem dizer por que.
HOJE_SEM_DATA = "zzzz-hoje"


def _dias(hoje, anteriores):
    """(dia de hoje, dias em ordem, {dia: capturas}) com hoje incluido."""
    datadas = [o.get("data_captura") for o in hoje if o.get("data_captura")]
    dia = max(datadas) if datadas else HOJE_SEM_DATA
    tudo = dict(anteriores or {})
    tudo[dia] = hoje
    return dia, sorted(d for d in tudo if d), tudo


def _prefixo(nomes):
    """O comeco que todos os nomes tem em comum, cortado na palavra.

    "Vivo Familia 2", "Vivo Familia 3" e "Vivo Familia 4" viram "Vivo
    Familia". Serve para a frase dizer QUAL familia de ofertas parou de
    ser lida em vez de "5 ofertas", que nao diz onde ir olhar.
    """
    p = nomes[0]
    for n in nomes[1:]:
        while p and not n.startswith(p):
            p = p[:-1]
    p = p.rstrip()
    if " " not in p or len(p) < 8:
        return ""
    return p


def _quem(ofertas, produto):
    nomes = sorted(n for n in ofertas if n)
    if not nomes:
        return "%s" % NOME_DO_PRODUTO.get(produto, produto)
    if len(nomes) == 1:
        return nomes[0][:40]
    pref = _prefixo(nomes)
    if pref:
        return "%s (%d ofertas)" % (pref[:34], len(nomes))
    # SEM COMECO EM COMUM, NOMEIA UMA E CONTA O RESTO. "5 ofertas de
    # movel" nao diz onde ir olhar, que e a unica coisa que esta frase
    # precisa entregar. Acontece quando ofertas de familias diferentes
    # perdem o mesmo campo no mesmo dia - foi o caso das Vivo Familia
    # junto com uma Vivo Total Familia, em 09/10.
    return "%s e mais %d" % (nomes[0][:34], len(nomes) - 1)


def _prateleira_que_encolheu(hoje, anteriores):
    """Baldes que encolheram e seguem encolhidos ha DIAS_PARA_FALAR."""
    dia, dias, tudo = _dias(hoje, anteriores)
    if len(dias) < DIAS_PARA_FALAR + 1:
        return []

    conta = collections.defaultdict(dict)
    for d in dias:
        for o in tudo[d]:
            b = (o.get("operadora"), o.get("produto"), o.get("praca"))
            conta[b][d] = conta[b].get(d, 0) + 1

    def base_de(b, i):
        porDia = conta[b]
        antes = [porDia[x] for x in dias[:i] if x in porDia]
        if len(antes) < 3:
            return None
        m = _mediana(antes)
        return m if m and m >= PRATELEIRA_MINIMA else None

    def magro(b, i):
        d = dias[i]
        if d not in conta[b]:
            return False
        base = base_de(b, i)
        return base is not None and conta[b][d] <= base * CORTE_DA_PRATELEIRA

    i = len(dias) - 1
    juntos = collections.defaultdict(list)
    for b in conta:
        if not all(magro(b, i - k) for k in range(DIAS_PARA_FALAR)):
            continue
        # O DIA ANTERIOR AO EPISODIO TEM DE ESTAR SADIO, senao a frase
        # sairia de novo no quarto dia, no quinto, e todo dia enquanto
        # durasse - que e o oposto de "fala uma vez".
        if magro(b, i - DIAS_PARA_FALAR):
            continue
        juntos[(b[0], b[1])].append(b[2])

    textos = []
    for (op, prod), pracas in sorted(juntos.items(), key=lambda x: str(x[0])):
        agora = _mediana([conta[(op, prod, p)][dia] for p in pracas])
        base = _mediana([base_de((op, prod, p), i) for p in pracas])
        textos.append("%s: %s encolheu para %s em %s, e segue assim há "
                      "%d dias (vinha de %d)"
                      % (op, NOME_DO_PRODUTO.get(prod, prod),
                         _plural(agora, "oferta", "ofertas"),
                         _plural(len(pracas), "praça", "praças"),
                         DIAS_PARA_FALAR, base))
    return textos


def _campo_que_morreu(hoje, anteriores):
    """Campos que zeraram e seguem zerados ha DIAS_PARA_FALAR.

    O GRAO E A OFERTA, e nao a operadora. No grao da operadora a morte
    da garantida das Vivo Familia nao aparece: as outras ofertas do
    mesmo produto seguem preenchidas e a taxa nunca chega a zero. Medido
    - no grao errado este vigia acharia 6 casos e perderia justamente o
    que o fez existir.
    """
    dia, dias, tudo = _dias(hoje, anteriores)
    if len(dias) < DIAS_PARA_FALAR + 1:
        return []

    cheio = collections.defaultdict(dict)
    for d in dias:
        for o in tudo[d]:
            k = (o.get("operadora"), o.get("produto"), o.get("nome_oferta"))
            for campo in CAMPOS_VIGIADOS:
                tem, total = cheio[(k, campo)].get(d, (0, 0))
                cheio[(k, campo)][d] = (tem + (o.get(campo) is not None), total + 1)

    def morto(kc, i):
        d = dias[i]
        par = cheio[kc].get(d)
        return bool(par) and par[1] > 0 and par[0] == 0

    def vinha_cheio(kc, i):
        porDia = cheio[kc]
        antes = [porDia[x][0] / float(porDia[x][1])
                 for x in dias[:i] if x in porDia and porDia[x][1]]
        if len(antes) < 3:
            return False
        m = _mediana(antes)
        return m is not None and m >= PISO_DE_PREENCHIMENTO

    i = len(dias) - 1
    juntos = collections.defaultdict(list)
    for kc in cheio:
        if not all(morto(kc, i - k) for k in range(DIAS_PARA_FALAR)):
            continue
        if morto(kc, i - DIAS_PARA_FALAR):
            continue
        if not vinha_cheio(kc, i - DIAS_PARA_FALAR + 1):
            continue
        (k, campo) = kc
        juntos[(k[0], k[1], campo)].append(k[2])

    textos = []
    for (op, prod, campo), ofertas in sorted(juntos.items(), key=lambda x: str(x[0])):
        textos.append("%s: %s não é lida há %d dias em %s"
                      % (op, CAMPOS_VIGIADOS[campo], DIAS_PARA_FALAR,
                         _quem(ofertas, prod)))
    return textos


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

    # ------------------------------------------------ silencio
    # Os dois unicos achados deste arquivo que NAO olham so o dia: eles
    # precisam de ontem e anteontem para saber que o problema ficou.
    for texto in _prateleira_que_encolheu(hoje, anteriores):
        grave(texto)
    for texto in _campo_que_morreu(hoje, anteriores):
        grave(texto)

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
    # OS DOIS DE 09/11/2026. Vem antes de "salto" e "sem velocidade"
    # porque os dois de baixo sao numero errado numa oferta, e estes
    # dois sao numero que sumiu de uma familia inteira - e ja faz tres
    # dias. As marcas abaixo sao TRECHOS DOS TEXTOS: mudar a frase sem
    # mudar a marca faz o achado perder a vaga da mensagem e nunca mais
    # aparecer, calado. OsDoisVigiasDisputamAVaga prende as duas juntas.
    "não é lida há",            # um campo morreu e ninguem viu
    "encolheu para",            # a prateleira sumiu e ninguem viu
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
