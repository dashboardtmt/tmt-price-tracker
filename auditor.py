# -*- coding: utf-8 -*-
u"""Confere cada afirmacao da mensagem contra as linhas cruas.

POR QUE EXISTE. O vigia confere o DADO; ninguem conferia a AFIRMACAO.
Em 04/11/2026 a mensagem publicou "Vivo Lite Anual III saiu da vitrine,
estava a 40,00, em todas as 2 pracas" enquanto um 40 GB a R$ 40,00
estava na prateleira das mesmas duas pracas, e publicou "a vitrine
passou a listar Max e Telecine" sobre uma mudanca que era nossa. Nos
dois casos o dado estava certo e a FRASE estava errada - e o vigia
passou, porque ele nao le frases.

O QUE ELE FAZ. Para cada evento, rededuz das linhas cruas as pracas em
que a afirmacao e literalmente verdadeira, e compara com as pracas que o
evento diz. Afirmacao que o dado nao sustenta NAO SAI - e a recusa e
dita, nunca calada.

POR QUE REDEDUZIR, E NAO RELER O EVENTO. Reler o que o detector gravou
provaria que o detector concorda consigo mesmo. O valor esta em duas
implementacoes independentes chegarem ao mesmo numero: quando elas
discordam, uma das duas esta errada e nenhuma das duas pode publicar.

O QUE ELE NAO AUDITA, e isto fica dito no proprio relatorio. A janela
do vigia e um select estreito - sem o jsonb, que e a parte pesada da
tabela -, entao assinatura de composicao nao esta ali. Grade, degrau que
voltou e renomeacao olham mais de dois dias e tem detector com memoria
propria. "Nao auditado" sai escrito; "auditado e aprovado" nunca e
suposto.
"""
import collections
import re

# O que este auditor sabe rededuzir da janela crua.
AUDITADOS = ("precos", "contratuais", "remodeladas", "saidas",
             "velocidades")

# E o que ele NAO sabe - escrito aqui para nao parecer aprovado.
FORA = {"composicao": "a assinatura SVA nao esta na janela crua",
        "grades": "a escada olha a serie inteira, nao dois dias",
        "voltaram": "o degrau que voltou olha o historico",
        "renomeadas": "o par vem do nome, que e o que esta em questao",
        "leitura": "nao e evento de mercado, e ressalva sobre o dado"}


def _nome(l):
    return " ".join((l.get("nome_oferta") or "").lower().split())


def _entrega(l):
    return l.get("degrau_mbps") or l.get("franquia_anunciada_gb")


def _indice(linhas, com_chave=True):
    """identidade -> praca -> linhas. Lista, e nao linha: duas ofertas na
    mesma identidade e justamente o caso em que nao se pode afirmar."""
    idx = collections.defaultdict(lambda: collections.defaultdict(list))
    for l in linhas or ():
        ident = (l.get("operadora"), l.get("produto"),
                 l.get("chave") if com_chave else None, _nome(l))
        idx[ident][l.get("praca")].append(l)
    return idx


def _uma(idx, ident, praca):
    """A linha unica daquela identidade na praca, ou None.

    None TAMBEM quando ha duas: afirmar sobre um grupo
    indistinguivel e eleger um representante por sorteio, que e o
    defeito que este projeto mais guarda.
    """
    linhas = idx.get(ident, {}).get(praca) or []
    return linhas[0] if len(linhas) == 1 else None


def _ident_do_evento(e, com_chave=True):
    atual = e.get("atual") or {}
    return (atual.get("operadora") or e.get("operadora"),
            atual.get("produto") or e.get("produto"),
            atual.get("chave") if com_chave else None,
            _nome(atual) if atual else
            " ".join((e.get("nome") or e.get("nome_oferta") or "")
                     .lower().split()))


def _pracas_que_sustentam(e, idx_h, idx_o, com_chave, confere):
    """(sustentam, nao_da_para_conferir) para as pracas do evento.

    TRES RESPOSTAS, E NAO DUAS. "A afirmacao e falsa" e "eu nao consigo
    conferir" sao estados diferentes, e confundir os dois foi o primeiro
    defeito deste auditor: ele recusou sete eventos verdadeiros porque
    a identidade aparecia duas vezes na janela crua - caso em que o
    comparador desempata pelo codigo de registro, que o auditor nao
    tinha. Recusar o que nao se consegue conferir e o mesmo erro que o
    projeto combate na direcao oposta.
    """
    ident = _ident_do_evento(e, com_chave)
    candidatas = set(idx_h.get(ident, {})) | set(idx_o.get(ident, {}))
    boas, incertas = set(), set()
    for praca in candidatas:
        a, d = _uma(idx_o, ident, praca), _uma(idx_h, ident, praca)
        if a is None or d is None:
            incertas.add(praca)
            continue
        if confere(e, a, d):
            boas.add(praca)
    return boas, incertas


def _preco(e, a, d):
    return (a.get("preco_promocional") == e["antes"].get("preco_promocional")
            and d.get("preco_promocional") == e["atual"].get(
                "preco_promocional")
            and a.get("preco_promocional") != d.get("preco_promocional"))


def _contratual(e, a, d):
    return (a.get("franquia_contratual_gb") == e.get("antes_contratual")
            and d.get("franquia_contratual_gb") == e.get("agora_contratual")
            and a.get("franquia_contratual_gb")
            != d.get("franquia_contratual_gb"))


def _remodelada(e, a, d):
    return (a.get("preco_promocional") == e.get("antes_preco")
            and d.get("preco_promocional") == e.get("agora_preco")
            and _entrega(a) == e.get("antes_entrega")
            and _entrega(d) == e.get("agora_entrega"))


def _pracas_da_saida(e, idx_h, idx_o, coletadas):
    """A oferta estava ontem e NAO esta hoje, numa praca que foi lida.

    O nome cru basta aqui: o detector de saida ja descartou a troca de
    safra antes de emitir o evento, entao nome diferente por safra nao
    produz recusa falsa.
    """
    ident = (e.get("operadora"), e.get("produto"), None,
             " ".join((e.get("nome_oferta") or "").lower().split()))
    boas, incertas = set(), set()
    for praca in set(idx_o.get(ident, {})) | set(e.get("pracas") or ()):
        if (e.get("operadora"), praca) not in coletadas:
            # praca que ninguem leu hoje nao sustenta nem nega a saida
            incertas.add(praca)
            continue
        if not idx_h.get(ident, {}).get(praca):
            boas.add(praca)
    return boas, incertas


# A MESMA NORMALIZACAO DO DETECTOR, ESCRITA DE NOVO DE PROPOSITO.
# robo.py importa auditor.py, entao importar de volta seria circular - e
# o auditor existe justamente para nao depender do codigo que produziu a
# afirmacao. O preco disso e as duas poderem divergir em silencio, e por
# isso AsDuasNormalizacoesConcordam compara as duas com os nomes reais
# das operadoras.
_VELOCIDADE_NO_NOME = re.compile(r"\b\d+\s*(?:MEGA|MBPS|MB|GIGA|GBPS)\b", re.I)


def _sem_a_velocidade(nome):
    return re.sub(r"\s+", " ",
                  _VELOCIDADE_NO_NOME.sub("", nome or "")).strip(" +-")


def _pracas_da_velocidade(e, do_dia, linhas_de_ontem):
    """Naquele preco e naquela praca, ontem havia "de" e hoje ha "para"?

    RE-DEDUZ, NAO RE-RODA. O detector varre tudo e agrupa; aqui a
    pergunta e feita uma praca por vez, a partir das linhas cruas, e so
    sobre o que o evento afirma.
    """
    alvo = _sem_a_velocidade(e.get("nome_oferta"))

    def degraus(linhas, praca):
        vistos = set()
        for l in (linhas or ()):
            if (l.get("operadora") != e.get("operadora")
                    or l.get("produto") != e.get("produto")
                    or l.get("praca") != praca
                    or l.get("preco_promocional") != e.get("preco")):
                continue
            if _sem_a_velocidade(l.get("nome_oferta")) != alvo:
                continue
            if l.get("degrau_mbps") is not None:
                vistos.add(l.get("degrau_mbps"))
        return vistos

    boas, incertas = set(), set()
    for praca in (e.get("pracas") or ()):
        ontem, hoje = degraus(linhas_de_ontem, praca), degraus(do_dia, praca)
        if not ontem or not hoje:
            # praca que a janela crua nao cobre nao sustenta nem nega
            incertas.add(praca)
        elif ontem == set([e.get("de")]) and hoje == set([e.get("para")]):
            boas.add(praca)
    return boas, incertas


def auditar(dados, do_dia, linhas_de_ontem):
    """Devolve (recusas, nao_auditados).

    recusas: [(tipo, rotulo, motivo, evento)] - o que nao pode sair.
    """
    if not do_dia or not linhas_de_ontem:
        return [], dict(FORA, **{t: "sem janela crua para conferir"
                                 for t in AUDITADOS})
    com_chave = {"precos": True, "contratuais": True, "remodeladas": False}
    confere = {"precos": _preco, "contratuais": _contratual,
               "remodeladas": _remodelada}
    idx_h = {True: _indice(do_dia), False: _indice(do_dia, False)}
    idx_o = {True: _indice(linhas_de_ontem),
             False: _indice(linhas_de_ontem, False)}
    coletadas = set((l.get("operadora"), l.get("praca")) for l in do_dia)

    recusas, nao_conferidas = [], []
    for tipo in AUDITADOS:
        for e in (dados.get(tipo) or ()):
            ditas = set(e.get("pracas") or ())
            if tipo == "saidas":
                boas, incertas = _pracas_da_saida(
                    e, idx_h[False], idx_o[False], coletadas)
            elif tipo == "velocidades":
                # o indice nao serve aqui: ele e chaveado pelo degrau, e
                # o degrau e o que mudou
                boas, incertas = _pracas_da_velocidade(
                    e, do_dia, linhas_de_ontem)
            else:
                k = com_chave[tipo]
                boas, incertas = _pracas_que_sustentam(
                    e, idx_h[k], idx_o[k], k, confere[tipo])
            # SO O QUE O EVENTO AFIRMA, e nao o que ele deixa de
            # afirmar. Evento que cobre PARTE das pracas onde o mesmo
            # movimento aconteceu nao esta mentindo: o detector separa
            # de proposito - "a praca que desfez e a que mexeu pela
            # primeira vez sao dois fatos", e a escada e o "voltou"
            # dividem o mesmo movimento em relatos diferentes. Exigir
            # evento maximo era exigir outra coisa, e recusava 11 casos
            # verdadeiros na primeira rodada.
            # A PRACA QUE NAO DEU PARA CONFERIR NAO CONTA COMO FALSA.
            faltam = sorted(ditas - boas - incertas)
            if not faltam:
                if ditas & incertas:
                    nao_conferidas.append(
                        (tipo, e.get("nome") or e.get("nome_oferta")
                         or (e.get("atual") or {}).get("nome_oferta") or "?",
                         "%d de %d praca(s) nao deram para conferir na "
                         "janela crua" % (len(ditas & incertas), len(ditas))))
                continue
            motivo = ("o dado nao sustenta a afirmacao em %d de %d praca(s) "
                      "(%s)" % (len(faltam), len(ditas),
                                ", ".join(x.split("/")[0]
                                          for x in faltam[:3])))
            recusas.append((tipo, e.get("nome") or e.get("nome_oferta")
                            or (e.get("atual") or {}).get("nome_oferta")
                            or "?", motivo, e))
    fora = dict(FORA)
    for tipo, rotulo, motivo in nao_conferidas:
        fora.setdefault("%s: %s" % (tipo, rotulo), motivo)
    return recusas, fora


def aplicar(dados, do_dia, linhas_de_ontem):
    """Tira do levantamento o que o auditor recusou, e diz o que tirou.

    NAO APAGA: move. O evento recusado continua no dicionario, em
    "recusadas", porque a recusa e informacao - e porque auditor com
    defeito teria de poder ser auditado de volta.
    """
    recusas, fora = auditar(dados, do_dia, linhas_de_ontem)
    if recusas:
        por_tipo = collections.defaultdict(list)
        for tipo, _rotulo, _motivo, e in recusas:
            por_tipo[tipo].append(id(e))
        for tipo, ids in por_tipo.items():
            dados[tipo] = [x for x in (dados.get(tipo) or ())
                           if id(x) not in ids]
    dados["recusadas"] = [(t, r, m) for t, r, m, _e in recusas]
    dados["nao_auditado"] = fora
    return dados
