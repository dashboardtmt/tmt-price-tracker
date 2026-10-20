"""O robo diario do Price Tracker.

Roda as 7h, repica as 7h30 o que falhou, e as 8h manda a mensagem.

Principios que o codigo precisa honrar (secao 1 da metodologia):
  - append-only: repetir e seguro, sobrescrever e proibido
  - falha vira buraco, nunca numero inventado
  - grava o que veio, mesmo parcial: dia perdido nao volta
  - ausencia e ausencia, nunca zero

Uso:
  python robo.py --coletar          # coleta e grava
  python robo.py --avisar           # monta e manda a mensagem do dia
  python robo.py --coletar --praca "Sao Paulo/SP"   # uma praca so, para teste
  python robo.py --coletar --simular                # nao grava nada
"""

import argparse
import collections
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vigia                                                   # noqa: E402
from coletores import (armazenamento, brisanet, claro, claro_flex, nucel, starlink, tim_fit,  # noqa: E402
                       tim, unifique, vivo)
from coletores.pracas import PRACAS, pracas_de, rotulo   # noqa: E402

BRT = timezone(timedelta(hours=-3))

# Quais operadoras ja tem coletor. As outras entram conforme ficarem prontas;
# a serie comeca desigual de proposito (decisao 18) porque esperar custa
# historico que nao volta.
PAINEL = "tmt-price-tracker.vercel.app"

COLETORES = {"Vivo": vivo, "TIM": tim, "Claro": claro,
             # A linha below-the-line da Claro tem dominio proprio e nao
             # aparece em nenhuma pagina de claro.com.br, entao e modulo
             # separado. As ofertas saem gravadas como "Claro" - o nome
             # aqui so rotula a rodada. (O Lite da Vivo nao precisa
             # disto: mora no mesmo site e entrou no coletor dela.)
             "Claro Flex": claro_flex,
             # O FIT da TIM tambem nao aparece na vitrine: o dado sai das
             # etiquetas da Anatel linkadas na pagina de Controle.
             "TIM FIT": tim_fit,
             "Brisanet": brisanet, "Unifique": unifique, "NuCel": nucel,
             # satelite, produto proprio: nao e comparavel com fibra e nao
             # disputa degrau com ela (ver coletores/starlink.py)
             "Starlink": starlink}


def agora():
    return datetime.now(BRT)


# ------------------------------------------------------------------ coleta

def coletar_operadora(nome, modulo, pracas, simular=False, verbose=True):
    inicio = agora()
    ofertas, avisos, ok = [], [], 0

    for i, p in enumerate(pracas, 1):
        try:
            d = modulo.coletar(p["cidade"], p["uf"], verbose=False)
            ofertas.extend(d["ofertas"])
            avisos.extend("%s: %s" % (rotulo(p), a) for a in d["avisos"])
            if d["ofertas"]:
                ok += 1
            else:
                avisos.append("%s: voltou vazia" % rotulo(p))
        except Exception as e:
            # uma praca que quebra nao pode derrubar as outras 19
            avisos.append("%s: erro %s" % (rotulo(p), e))
        if verbose:
            print("  [%2d/%2d] %-22s %d ofertas acumuladas"
                  % (i, len(pracas), rotulo(p), len(ofertas)), flush=True)

    registro = {
        "data_captura": inicio.date().isoformat(),
        "iniciada_em": inicio.isoformat(),
        "terminada_em": agora().isoformat(),
        "operadora": nome,
        "pracas_pedidas": len(pracas),
        "pracas_ok": ok,
        "ofertas": len(ofertas),
        "avisos": avisos or None,
        "sucesso": ok == len(pracas) and bool(ofertas),
    }

    if simular:
        print("  [simulacao] %d ofertas nao gravadas" % len(ofertas))
        return ofertas, registro, None

    gravadas, erro = armazenamento.gravar_capturas(ofertas)
    if erro:
        registro["sucesso"] = False
        registro["avisos"] = (registro["avisos"] or []) + ["gravacao: %s" % erro]
    armazenamento.registrar_coleta(registro)
    return ofertas, registro, erro


def rodar_coleta(uma_praca=None, simular=False):
    print("=" * 70)
    print("COLETA  %s" % agora().strftime("%d/%m/%Y %H:%M"))
    print("=" * 70)
    resumo = []
    for nome, modulo in COLETORES.items():
        # operadora nacional roda uma vez: repetir nas 20 pracas gravaria
        # 20 copias do mesmo preco
        if getattr(modulo, "NACIONAL", False):
            pracas = [{"cidade": "Brasil", "uf": "BR", "regiao": "Nacional", "capital": False}]
        else:
            pracas = pracas_de(nome)
        # o filtro de praca (modo teste) nao se aplica a operadora nacional
        if uma_praca and not getattr(modulo, "NACIONAL", False):
            cidade, uf = uma_praca.split("/")
            pracas = [p for p in pracas if p["cidade"] == cidade and p["uf"] == uf]
        print("\n%s - %d pracas" % (nome, len(pracas)))
        ofertas, registro, erro = coletar_operadora(nome, modulo, pracas, simular)
        resumo.append(registro)
        print("  %s: %d ofertas, %d/%d pracas%s" % (
            nome, len(ofertas), registro["pracas_ok"], registro["pracas_pedidas"],
            "" if registro["sucesso"] else "  (COM AVISOS)"))
        for a in (registro["avisos"] or [])[:5]:
            print("     " + a)

    falhas = [r["operadora"] for r in resumo if not r["sucesso"]]
    if falhas:
        print("")
        print("Incompletas: %s" % ", ".join(falhas))
    return resumo, falhas


# ----------------------------------------------------------------- mensagem

def _tel(metodo, dados=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    url = "https://api.telegram.org/bot%s/%s" % (token, metodo)
    corpo = urllib.parse.urlencode(dados).encode() if dados else None
    req = urllib.request.Request(url, data=corpo, method="POST" if dados else "GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "erro": str(e)}

def _tel_documento(chat, caminho, legenda=""):
    """Envia um arquivo pelo Telegram.

    sendDocument exige multipart, que urlencode nao faz. Monta na mao
    para nao trazer dependencia so por causa disto.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    url = "https://api.telegram.org/bot%s/sendDocument" % token
    limite = "----PriceTracker%d" % int(time.time())
    nome = os.path.basename(caminho)
    corpo = io.BytesIO()

    def campo(chave, valor):
        corpo.write(("--%s\r\n" % limite).encode())
        corpo.write(('Content-Disposition: form-data; name="%s"\r\n\r\n'
                     % chave).encode())
        corpo.write(("%s\r\n" % valor).encode("utf-8"))

    campo("chat_id", chat)
    if legenda:
        campo("caption", legenda[:1000])
    corpo.write(("--%s\r\n" % limite).encode())
    corpo.write(('Content-Disposition: form-data; name="document"; '
                 'filename="%s"\r\n' % nome).encode())
    corpo.write(b"Content-Type: application/pdf\r\n\r\n")
    corpo.write(open(caminho, "rb").read())
    corpo.write(("\r\n--%s--\r\n" % limite).encode())

    req = urllib.request.Request(url, data=corpo.getvalue(), method="POST")
    req.add_header("Content-Type",
                   "multipart/form-data; boundary=%s" % limite)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "erro": str(e)}


def _montar_pdf(dados):
    """Gera o relatorio do dia. Devolve (caminho, erro)."""
    try:
        import relatorio
        entradas = {}
        for chave, _rot in relatorio.PRODUTOS:
            itens, _erro = ofertas_do_produto(dados["dia"], chave)
            entradas[chave] = itens
        caminho = "relatorio-%s.pdf" % dados["dia"]
        return relatorio.gerar(dados, entradas, caminho), None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)

def ofertas_do_produto(hoje, produto, praca="Sao Paulo/SP"):
    """Todas as ofertas do produto na praca de referencia.

    O relatorio mostra o catalogo inteiro de cada produto, e nao so o
    plano de entrada: para comparar player com player e preciso ver o
    que cada um poe na prateleira, nao so onde ele comeca.

    As ofertas nacionais entram junto. NuCel e Starlink gravam como
    Brasil/BR por nao terem praca, e sem isto sumiriam da tabela.
    """
    campos = ("operadora,nome_oferta,destaque,preco_promocional,"
              "degrau_mbps,franquia_anunciada_gb")
    saida = []
    for p in (praca, "Brasil/BR"):
        filtro = ("capturas?data_captura=eq.%s&produto=eq.%s&praca=eq.%s"
                  "&select=%s&order=operadora.asc,preco_promocional.asc"
                  % (hoje, produto, urllib.parse.quote(p), campos))
        linhas, erro = armazenamento.consultar(filtro)
        if erro:
            return [], erro
        saida.extend(l for l in (linhas or [])
                     if l.get("preco_promocional") is not None)
    # a mesma oferta pode vir duas vezes se a praca for Brasil/BR
    vistos, unicas = set(), []
    for l in saida:
        k = (l.get("operadora"), l.get("nome_oferta"), l.get("destaque"),
             l.get("preco_promocional"))
        if k in vistos:
            continue
        vistos.add(k)
        unicas.append(l)
    return unicas, None


# Quantos dias o vigia usa para saber o que e normal. Menos que isso e
# pouca amostra; mais, e historico velho demais para comparar com hoje.
DIAS_DE_REFERENCIA = 7


def _capturas_para_o_vigia(hoje):
    """O dia e os sete anteriores, so com as colunas que o vigia usa.

    Select estreito de proposito: o vigia olha milhares de linhas e nao
    precisa do bruto, que e a parte pesada da tabela.
    """
    desde = (datetime.fromisoformat(hoje).date()
             - timedelta(days=DIAS_DE_REFERENCIA)).isoformat()
    campos = ("data_captura,operadora,produto,praca,chave,nome_oferta,"
              "preco_promocional,franquia_anunciada_gb,degrau_mbps")
    linhas, erro = armazenamento.consultar_tudo(
        "capturas?data_captura=gte.%s&data_captura=lte.%s&select=%s"
        "&order=data_captura.asc" % (desde, hoje, campos))
    if erro:
        return None, {}, erro
    do_dia, antes = [], collections.defaultdict(list)
    for l in (linhas or []):
        d = l.get("data_captura")
        if d == hoje:
            do_dia.append(l)
        elif d:
            antes[d].append(l)
    return do_dia, dict(antes), None


def _indexar(dia):
    # a assinatura sai de dentro do jsonb: nao existe coluna para ela, e
    # criar uma exigiria um ALTER TABLE na mao a cada campo novo
    campos = ("chave,praca,operadora,produto,nome_oferta,destaque,"
              "preco_promocional,franquia_anunciada_gb,degrau_mbps,"
              "nivel_bundle,assinatura_sva:bruto->>assinatura_sva")
    # paginado: sao mais de mil capturas por dia, e pedir "limit=20000"
    # trazia so as primeiras mil sem reclamar
    linhas, erro = armazenamento.consultar_tudo(
        "capturas?data_captura=eq.%s&select=%s"
        "&order=chave.asc,nome_oferta.asc,codigo_anatel.asc" % (dia, campos))

    # O nome entra na identidade. A chave de continuidade identifica a
    # SERIE - operadora|produto|degrau|variante - e nao a oferta: "TIM
    # Controle Redes Sociais" e "TIM Controle Pro Express" tem a mesma
    # chave, o mesmo degrau e o mesmo preco. Foi por isso que o indice
    # unico do banco precisou ganhar nome_oferta.
    #
    # Indexando so por chave e praca, uma oferta sobrescrevia a outra e
    # qual sobrevivia dependia da ordem em que o banco devolvesse as
    # linhas. Isso comparava o preco de uma oferta hoje com o de outra
    # ontem: capaz de acusar mudanca onde nao houve e de esconder a que
    # houve, variando de uma execucao para a seguinte. A ordem explicita
    # acima e para nao depender de sorte nem quando ainda houver empate.
    # DUAS OFERTAS COM A MESMA IDENTIDADE SAEM AS DUAS. Era o caso das
    # duas "Vivo Familia 2 + TV" de 700 Mega, a R$ 290 e a R$ 390.
    #
    # Guardar a primeira e descartar o resto parecia aproveitar o que
    # dava. Nao e: e sortear qual oferta representa as duas, e o sorteio
    # muda de um dia para o outro. Medido em 15 e 16/10/2026 - a ordem
    # elegeu a de R$ 390 num dia, a correcao de variante levou essa para
    # outra chave, sobrou a de R$ 290 no dia seguinte, e a comparacao
    # anunciou "390,00 -> 290,00  -26% em todas as 20 pracas" num dia em
    # que nenhum preco mudou. As duas ofertas existiam nos dois dias
    # pelos mesmos valores.
    #
    # Pior: a mensagem imprimia, duas linhas acima, que nao era possivel
    # afirmar variacao naquelas ofertas. Afirmava e desafirmava na mesma
    # mensagem, e o numero era falso.
    #
    # Com o grupo inteiro fora, o aviso passa a ser verdade. O que sobra
    # cai nas sobras, onde _renomeadas e _oferta_remodelada exigem uma
    # candidata de cada lado e se recusam a chutar.
    grupos = collections.Counter(_identidade(l) for l in (linhas or []))
    indice, colididas = {}, []
    for l in (linhas or []):
        k = _identidade(l)
        if grupos[k] > 1:
            colididas.append(l)
            continue
        indice[k] = l
    # A colisao NAO vai no canal de erro. Erro cancela a comparacao
    # inteira, e isso e certo para consulta que caiu - mas colisao em 20
    # ofertas nao pode apagar o que mudou nas outras 1.640. Foi o que
    # aconteceu em 16/10/2026, com o aviso do dia saindo vazio.
    #
    # DUAS FRASES, NAO UMA. A curta vai na MENSAGEM, colada na linha que
    # ela qualifica: "nenhuma mudanca" com 20 ofertas fora da comparacao
    # nao e a mesma frase que "nenhuma mudanca". Antes so existia a
    # longa, e ela so chegava ao rodape do PDF - se o relatorio falhasse,
    # o ponto cego desaparecia inteiro e a mensagem afirmava sem ressalva.
    aviso = None
    if colididas:
        # _rotulo evita o "Vivo Vivo Familia 2 + TV": o nome da oferta
        # ja comeca com a marca na maioria das operadoras
        quais = sorted({_rotulo(c) for c in colididas})
        aviso = {
            "quantas": len(colididas),
            "curto": ("%d oferta(s) ficaram fora da comparação de hoje por "
                      "serem indistinguíveis entre si — mesma série, praça "
                      "e nome (%s)." % (len(colididas), quais[0])),
            "longo": ("%d oferta(s) não foram comparadas por compartilharem "
                      "chave de série, praça e nome com outra oferta (%s). "
                      "Todas as ofertas de cada grupo ficam fora da "
                      "comparação: representar o grupo por uma delas "
                      "equivaleria a escolher por sorteio qual das duas "
                      "define o preço do dia, e o sorteio muda de um dia "
                      "para o outro. Não é possível afirmar se houve "
                      "variação de preço nelas."
                      % (len(colididas), "; ".join(quais[:2]))),
        }
    return indice, erro, aviso


def _identidade(l):
    """Como reconhecer a mesma oferta amanha.

    O nome desambigua, mas cru ele tambem muda sozinho: a NuCel carimba a
    safra no proprio nome - "[SET] OFT NC PF PROMO 12M 700M" virou "[OUT]
    ..." no dia primeiro. Com o nome cru, toda virada de mes essas ofertas
    perdem o par e nenhuma mudanca de preco e detectada nelas - justamente
    quando o mes vira, que e quando preco muda.

    Entao a marca de safra sai da identidade e o resto do nome fica. O
    alerta continua mostrando o nome de verdade; isto aqui so serve para
    reencontrar a oferta.
    """
    nome = re.sub(r"\[[^\]]*\]", " ", l.get("nome_oferta") or "")
    return l["chave"], l["praca"], " ".join(nome.lower().split())


# Como cada produto se chama na mensagem. A chave e o que o coletor
# grava; o valor e o que o leitor reconhece.
CATEGORIA = {"controle": "Controle", "movel": "Pós-pago", "fibra": "Fibra",
             "combo": "Combo", "prepago": "Pré-pago",
             "btl": "Below-the-line",
             # a Starlink: faltava aqui, e a mensagem imprimia a chave
             # crua do banco - "satelite" em minuscula, sem acento
             "satelite": "Satélite"}


def _categoria(l):
    """A categoria do produto, para abrir a linha da mudanca.

    Sem ela, "Vivo - Familia 2 + TV" nao diz se aquilo e combo, fibra ou
    pos-pago - e o nome da oferta nem sempre entrega.
    """
    return CATEGORIA.get(l.get("produto"), l.get("produto") or "—")


def _rotulo(l, sem_operadora=False):
    """Operadora e nome, sem repetir: "Vivo Vivo Controle" ficava feio.

    Com sem_operadora devolve so o nome da oferta: a linha do recado ja
    abre com a operadora, e repetir ali ficaria pior ainda.
    """
    nome = l.get("nome_oferta") or l.get("produto") or ""
    op = l.get("operadora") or ""
    if sem_operadora:
        corte = nome[len(op):].strip() if nome.lower().startswith(op.lower()) else nome
        return corte or nome or op
    return nome if nome.lower().startswith(op.lower()) else ("%s %s" % (op, nome)).strip()


def _reais(v):
    return ("%.2f" % v).replace(".", ",") if v is not None else "-"


def _agrupar(achados, ident, atual, antes):
    """Uma mudanca nacional e um alerta com 20 pracas, nao 20 alertas.

    A PRACA NAO ENTRA DUAS VEZES. Quando duas ofertas caiam no mesmo
    grupo, cada uma empurrava a praca na lista e o alcance dobrava:
    alta em 10 pracas saia como "em todas as 20". Dedupe na entrada, e
    nao na saida, porque quem le a lista depois - a mensagem e o PDF -
    nao tem como saber que ela foi contada torto.
    """
    d = achados.setdefault(ident, {"pracas": [], "atual": atual, "antes": antes})
    if atual["praca"] not in d["pracas"]:
        d["pracas"].append(atual["praca"])


# Quanto da vitrine de hoje precisa ter encontrado par em ontem para
# "nenhuma mudanca" significar alguma coisa. Abaixo disto a frase nao
# descreve o mercado, descreve a comparacao nao tendo acontecido - e e
# justamente a frase que soa como noticia verificada.
#
# O NUMERO SAI DA SERIE, nao de palpite. Medido nos 21 dias coletados, a
# cobertura dos dias SEM mudanca nenhuma foi: 100% em seis deles, e 76% e
# 73% nos outros dois - que sao justamente 01/10, quando 346 ofertas
# colidiram, e 16/10, o dia em que o aviso saiu vazio e o usuario
# reclamou. Com o piso em 0,85 a ressalva aparece nesses dois e fica
# calada nos seis. Com 0,60, como escrevi primeiro, ela nunca apareceria
# em dia nenhum da serie - limite que nao dispara e codigo morto com cara
# de salvaguarda.
COBERTURA_MINIMA = 0.85


def mudancas(hoje, ontem):
    """O levantamento do dia, num dicionario com chave para cada coisa.

    POR QUE DICIONARIO E NAO TUPLA. Isto devolvia oito valores em fila, e
    cada detector novo empurrava a fila: quem chamava tinha de acertar a
    ordem e a quantidade. A ferramenta de diagnostico do projeto quebrou
    assim - desempacotando cinco de uma funcao que passou a devolver
    oito - e quebrou calada, ate alguem rodar. Com chaves, codigo que
    nao conhece o detector novo continua funcionando e nao mente.

    As chaves:
      precos        mudanca de preco com a oferta identificavel
      composicao    mesmo preco, outro conjunto de servicos inclusos
      renomeadas    mesma chave de serie, outro nome
      grades        a escada de preco por entrega reorganizada
      voltaram      degrau que saiu dias atras e voltou com outro preco
      remodeladas   preco E entrega mudando no mesmo dia
      erro          a consulta caiu: nao houve comparacao
      cego          ofertas que nao deu para comparar, e por que
      cobertura     quanto da vitrine de hoje tinha par em ontem
    """
    h, erro_h, cego_h = _indexar(hoje)
    o, erro_o, cego_o = _indexar(ontem)
    # o ponto cego de hoje e o que importa para o leitor; o de ontem so
    # vale dizer se hoje estiver limpo
    cego = cego_h or cego_o
    # Comparacao que falhou nao e comparacao sem novidade. Sem devolver o
    # erro, uma consulta que caiu faria o aviso afirmar "nada mudou" - pior
    # que nao avisar, porque soa como noticia verificada.
    vazio = {"precos": [], "composicao": [], "renomeadas": [], "grades": [],
             "voltaram": [], "remodeladas": [], "erro": None, "cego": cego,
             "cobertura": None}
    if erro_h or erro_o:
        return dict(vazio, erro=erro_h or erro_o)
    grades, suprimir = _grades_reorganizadas(h, o)

    precos, composicao = {}, {}
    for k, atual in h.items():
        antes = o.get(k)
        if not antes:
            continue
        # operadora que reorganizou a grade nao emite mudanca de preco:
        # o par por nome casou degraus diferentes da escada
        if (atual["operadora"], atual["produto"]) in suprimir:
            continue
        # OS DOIS LADOS TEM DE TER PRECO. Faltava a guarda do lado de
        # HOJE, e com ela faltando "None != 119.9" era verdadeiro: a
        # oferta cujo preco a coletora nao conseguiu ler entrava como
        # mudanca e a mensagem escrevia "119,90 -> -". Num dia em que a
        # leitura de preco quebrasse numa operadora inteira, a mensagem
        # anunciaria uma centena de reajustes que nao existiram.
        #
        # Preco que sumiu nao e preco que mudou - e ausencia, e ausencia
        # e assunto do vigia, que conta "N oferta(s) sem preco". Mesmo
        # principio da secao 1 da metodologia: ausencia e ausencia,
        # nunca zero, e aqui nunca reajuste.
        if (antes["preco_promocional"] is not None
                and atual["preco_promocional"] is not None
                and atual["preco_promocional"] != antes["preco_promocional"]):
            # O NOME ENTRA NA IDENTIDADE DO GRUPO. Sem ele, duas ofertas
            # que dividem chave de serie e preco - "TIM Controle Redes
            # Sociais" e "TIM Controle Pro", 46 GB, R$ 49,99 - caiam no
            # mesmo evento: a segunda desaparecia da mensagem e as
            # pracas das duas somavam no alcance da primeira.
            _agrupar(precos, (atual["operadora"], atual["produto"], atual["chave"],
                              (atual.get("nome_oferta") or "").lower(),
                              antes["preco_promocional"], atual["preco_promocional"]),
                     atual, antes)
            continue

        # Composicao so e comparavel quando os DOIS dias tem assinatura.
        # Assinatura que aparece ou desaparece e quase sempre o regulamento
        # da Vivo tendo falhado - foi o que houve em 30/09, quando 1042 de
        # 1044 ofertas ficaram sem os campos de contrato. Tratar isso como
        # mudanca de oferta encheria o aviso de alarme falso no pior dia.
        a, d = antes.get("assinatura_sva"), atual.get("assinatura_sva")
        if a and d and a != d:
            _agrupar(composicao, (atual["operadora"], atual["produto"],
                                  atual["chave"],
                                  (atual.get("nome_oferta") or "").lower(),
                                  a, d), atual, antes)

    # A ESCADA NAO REPETE O QUE O DETECTOR POR NOME JA DISSE. Oferta que
    # muda de preco mantendo a identidade ja foi reportada la, com o
    # nome - e o nome e o que interessa. A escada existe para ver o que
    # o outro NAO ve: movimento em que a identidade mudou junto.
    cobertos = {(m["atual"]["operadora"], m["atual"]["produto"],
                 _entrega(m["atual"])) for m in precos.values()}
    for g in grades:
        g["precos"] = [x for x in g["precos"]
                       if (g["operadora"], g["produto"], x[0]) not in cobertos]
    grades = [g for g in grades if g["saltos"] or g["precos"]]

    renomeadas = [r for r in _renomeadas(h, o)
                  if (r["atual"]["operadora"], r["atual"]["produto"]) not in suprimir]

    # A MESMA OFERTA MUDADA POR DENTRO. Era o ponto cego de todos os
    # detectores acima, e o pior deles, porque produzia afirmacao
    # POSITIVA de ausencia. Ver _oferta_remodelada.
    remodeladas = [r for r in _oferta_remodelada(h, o)
                   if (r["operadora"], r["produto"]) not in suprimir]

    # degrau que sumiu dias atras e voltou com outro preco: nenhum dos
    # detectores acima ve isso, porque todos comparam hoje com ontem
    voltaram = _degraus_que_voltaram(h, o, hoje)
    # a remodelada ja contou o movimento com o nome da oferta e com os
    # dois numeros; repetir aqui seria a mesma noticia duas vezes
    remod = {(r["operadora"], r["produto"], r["agora_entrega"])
             for r in remodeladas}
    voltaram = [v for v in voltaram
                if (v["operadora"], v["produto"], v["entrega"]) not in remod]

    precos, composicao = list(precos.values()), list(composicao.values())
    # O ALCANCE PRIMEIRO: a separacao abaixo usa em quantas pracas cada
    # evento valeu, e esse numero e escrito aqui.
    _assinar_alcance(h, precos, composicao, renomeadas, grades, voltaram,
                     remodeladas)
    remodeladas, leitura = _separar_o_que_e_nosso(remodeladas, hoje)
    return {"precos": precos, "composicao": composicao,
            "renomeadas": renomeadas, "grades": grades,
            "voltaram": voltaram, "remodeladas": remodeladas,
            "leitura": leitura,
            "erro": None, "cego": cego,
            "cobertura": _cobertura(h, o, (cego or {}).get("quantas", 0))}


# DIAS EM QUE A NOSSA LEITURA MUDOU, declarados a mao.
#
# Os dois sinais de _separar_o_que_e_nosso sao heuristicas: acertam
# quando a mudanca atinge varias operadoras ou uma minoria das pracas, e
# erram justamente no caso mais comum de mexida nossa - um coletor que
# passa a ler melhor e muda uma operadora INTEIRA de um dia para o
# outro. Aqui a causa e declarada, nao adivinhada.
#
# Quem mexer num coletor de um jeito que mude nivel de bundle, versao da
# chave ou lista de apps poe a data aqui, com uma linha dizendo o que
# mudou. Custa pouco, e e a diferenca entre a serie ter um degrau
# documentado e ter um degrau que alguem vai ler como reposicionamento
# de operadora dois meses depois.
LEITURA_MUDOU_EM = {
    "2026-10-21": "o nível de bundle passou a sair da lista de apps da "
                  "oferta, e não só do texto do card",
}


def _separar_o_que_e_nosso(remodeladas, hoje=None):
    """Separa o que o mercado fez do que a nossa leitura passou a ver.

    Devolve (do mercado, da leitura).

    OPERADORA NAO COMBINA REPOSICIONAMENTO COM A CONCORRENTE. Quando a
    mesma troca de versao aparece em duas ou mais operadoras no mesmo
    dia, a causa quase certa e nossa: um coletor que passou a ler o
    texto de outro jeito. Medido em 16/10/2026 - doze ofertas de Claro
    Flex, Vivo e Brisanet mudando de nivel de bundle juntas, no dia
    seguinte ao coletor de apps passar a exigir o tier declarado pela
    fonte.

    NAO E PARA ESCONDER, E PARA ATRIBUIR CERTO. O fato continua no
    relatorio, oferta por oferta, e a mensagem ganha uma linha dizendo
    que aquilo atingiu varias operadoras de uma vez - o que avisa o
    leitor de que ha um degrau na serie naquele dia, que e a informacao
    que ele precisa para nao ler o degrau como movimento de mercado.

    E A CAUSA PODE SER DECLARADA. Ver LEITURA_MUDOU_EM: quando a data
    de hoje esta la, toda mudanca so-de-versao e nossa, sem heuristica
    nenhuma. E o unico caso em que o codigo sabe a resposta de verdade.

    O SEGUNDO SINAL E O ALCANCE. Em 13/10/2026 a "TIM Controle Redes
    Sociais" apareceu passando a incluir apps em 2 das 18 pracas onde
    ela existe, e em 14/10 apareceu voltando atras nas mesmas duas.
    Operadora nao reposiciona oferta em duas cidades e desfaz no dia
    seguinte - a pagina da TIM mostra a lista de apps as vezes, e a
    leitura oscila com ela. Mudanca de versao que alcanca uma minoria
    das pracas da oferta fica no relatorio.

    PRECO NUNCA CAI NESTA REGRA, por nenhum dos dois sinais. Reajuste
    simultaneo entre operadoras acontece, e reajuste chega praca por
    praca de verdade: a escada da Claro em 13/10 alcancou 19 de 20.
    Quando acontece, e a noticia.
    """
    declarado = LEITURA_MUDOU_EM.get(hoje)
    so_versao = [r for r in remodeladas if r.get("versao_apenas")]
    varias_operadoras = len({r["operadora"] for r in so_versao}) >= 2
    nossas = [r for r in so_versao
              if declarado or varias_operadoras or _minoria_das_pracas(r)]
    ids = {id(r) for r in nossas}
    return [r for r in remodeladas if id(r) not in ids], nossas


def _minoria_das_pracas(e):
    """O evento valeu em menos da metade das pracas em que a oferta existe."""
    universo = e.get("universo") or 0
    quantas = len(set(e.get("pracas") or ()))
    return universo > 1 and quantas * 2 <= universo


def _cobertura(h, o, fora=0):
    """Quantas ofertas de hoje encontraram a mesma identidade ontem.

    POR QUE ISTO E PARTE DA NOTICIA. "Nenhuma mudanca" sobre uma
    comparacao que cobriu 12% da vitrine nao e a mesma frase que
    "nenhuma mudanca" sobre 94% - e as duas saiam escritas igual. Sem
    este numero, o silencio do robo nao se distingue de cegueira do
    robo, que e o modo de falhar que a metodologia proibe: falha que se
    parece com resultado.

    O calculo ja existia, escrito a mao dentro de uma ferramenta de
    diagnostico, e so era visto por quem rodasse a ferramenta.
    """
    if not h:
        return None
    # AS INDISTINGUIVEIS CONTAM NO DENOMINADOR. Elas saem do indice, e
    # sem isto a cobertura pareceria melhor do que e: 100% do que deu
    # para comparar nao e 100% do que foi coletado.
    comuns = set(h) & set(o)
    por_operadora = {}
    for op in sorted({l["operadora"] for l in h.values()}):
        do_op = {k for k, l in h.items() if l["operadora"] == op}
        por_operadora[op] = (len(do_op & comuns), len(do_op))
    total = len(h) + (fora or 0)
    return {"pares": len(comuns), "hoje": total, "ontem": len(o),
            "fora": fora or 0,
            "fracao": len(comuns) / float(total),
            "por_operadora": por_operadora}


def _assinar_alcance(h, *grupos):
    """Escreve "onde" e "universo" em cada evento, uma vez so.

    A MENSAGEM E O PDF NAO PODEM DISCORDAR. A frase do alcance era
    calculada na mensagem e o relatorio lia uma chave "onde" que
    ninguem escrevia - a coluna "Pracas" do PDF saiu "—" em todas as
    linhas, em toda edicao. Calcular aqui, antes de os dois lerem,
    tira a possibilidade de divergirem.

    E O DENOMINADOR E ONDE A OFERTA EXISTE, nao o painel inteiro. A
    NuCel e a Starlink gravam uma praca nacional ("Brasil/BR"), e
    qualquer mudanca delas saia como "em 1 de 20" - que sugere
    movimento localizado onde ele foi total.
    """
    onde_existe = collections.defaultdict(set)
    for l in h.values():
        onde_existe[(l["operadora"], l["produto"])].add(l["praca"])
    for grupo in grupos:
        for e in grupo:
            base = e.get("atual") or e
            op = e.get("operadora") or base.get("operadora")
            pr = e.get("produto") or base.get("produto")
            e["universo"] = len(onde_existe.get((op, pr)) or ())
            e["onde"] = _onde(e.get("pracas") or (), e["universo"])


# Como cada degrau da escada de bundle (decisao 10) se chama em
# portugues. E a mesma escala da tela, com as mesmas palavras: oferta que
# muda de nivel tem de ser descrita igual nos dois lugares.
#
# O rotulo NAO NOMEIA O APP de proposito. Dizer "passou a incluir
# Netflix" exigiria que a fonte dissesse qual, e a maioria nao diz - era
# assim que a tela antiga mostrava Netflix na linha de uma oferta que
# nao inclui Netflix.
BUNDLE = ("sem assinatura inclusa", "com apps de catálogo",
          "com uma assinatura", "com vários streamings",
          "com TV por assinatura")


def _bundle(n):
    return BUNDLE[n] if isinstance(n, int) and 0 <= n < len(BUNDLE) else None


def _variante(l):
    """A ultima parte da chave de continuidade: a VERSAO da oferta.

    "Vivo|prepago|20gb|simples" e "Vivo|prepago|20gb|com_apps" sao a
    mesma oferta em duas versoes. O nome interno nunca sai na mensagem -
    serve so para perceber que mudou.
    """
    return (l.get("chave") or "").split("|")[-1]


def _oferta_remodelada(h, o):
    """A MESMA oferta de volta na vitrine mudada por dentro.

    O PIOR PONTO CEGO QUE O COMPARADOR TINHA, porque nao produzia
    silencio: produzia afirmacao. A mensagem escrevia "Nenhuma mudanca
    de preco, composicao ou nome" sobre ofertas que mudaram.

    POR QUE NENHUM DOS OUTROS VE. A identidade carrega a chave de
    continuidade, e a chave e operadora|produto|degrau|variante: mudou
    o degrau ou a variante, nao ha par e a oferta sai da comparacao. A
    escada compara pelos dois lados, mas cada lado exige que o OUTRO
    campo tenha ficado parado - por_preco casa preco igual, por_entrega
    casa entrega igual. E _renomeadas pareia por chave e praca, que e
    exatamente o que a troca de chave quebra.

    DOIS CASOS MEDIDOS NO DADO REAL:

      preco E entrega juntos - "R$ 30 por 25 GB" virando "R$ 35 por
      20 GB". Cada detector perde este por um motivo diferente, e os
      quatro perdem.

      so a versao - em 16/10/2026 a Vivo Pre de R$ 30 / 20 GB passou de
      "simples" para "com_apps" nas 20 pracas: a oferta passou a incluir
      assinatura pelo mesmo preco e pela mesma franquia. O detector de
      composicao nao pega porque olha os codigos SVA do regulamento, que
      no pre-pago nao existem.

    O QUE SOBRA PARA PAREAR E O NOME, na mesma praca - e o nome e o que
    o leitor reconhece de um dia para o outro. Vale so quando sobrou
    UMA candidata de cada lado, a mesma regra de _renomeadas: com duas
    ou mais, qualquer emparelhamento seria chute, e chute aqui inventa
    reajuste.

    E COMPLEMENTAR A _renomeadas, nao concorrente: la o nome muda e a
    chave fica, aqui a chave muda e o nome fica. Nenhuma oferta cai nas
    duas. Oferta que trocou nome E chave no mesmo dia continua sem par,
    e isso esta certo: nao ha o que a identifique, e inventar o par
    seria pior do que o silencio.
    """
    def pareia(l):
        nome = re.sub(r"\[[^\]]*\]", " ", l.get("nome_oferta") or "")
        return (l["operadora"], l["produto"], l["praca"],
                " ".join(nome.lower().split()))

    sobra_h = collections.defaultdict(list)
    sobra_o = collections.defaultdict(list)
    for k, l in h.items():
        if k not in o:
            sobra_h[pareia(l)].append(l)
    for k, l in o.items():
        if k not in h:
            sobra_o[pareia(l)].append(l)

    achados = {}
    for k, atuais in sobra_h.items():
        anteriores = sobra_o.get(k)
        if not anteriores or len(atuais) != 1 or len(anteriores) != 1:
            continue
        atual, antes = atuais[0], anteriores[0]
        pa, pd = antes["preco_promocional"], atual["preco_promocional"]
        ea, ed = _entrega(antes), _entrega(atual)
        ba, bd = antes.get("nivel_bundle"), atual.get("nivel_bundle")

        preco_mudou = None not in (pa, pd) and pa != pd
        entrega_mudou = None not in (ea, ed) and ea != ed
        versao_mudou = _variante(antes) != _variante(atual)

        # A ESCADA JA CONTA "mesmo preco, outra entrega", e com o nome
        # da oferta. Repetir aqui seria a mesma noticia duas vezes.
        if entrega_mudou and not preco_mudou and not versao_mudou:
            continue
        # Fora disso, entra quando preco e entrega andaram juntos - que
        # e o que ninguem mais ve - ou quando a versao da oferta mudou.
        if not (versao_mudou or (preco_mudou and entrega_mudou)):
            continue

        ident = (atual["operadora"], atual["produto"], k[3],
                 pa, pd, ea, ed, ba, bd)
        d = achados.setdefault(ident, {
            "operadora": atual["operadora"], "produto": atual["produto"],
            "nome": atual.get("nome_oferta"),
            "antes_preco": pa, "agora_preco": pd,
            "antes_entrega": ea, "agora_entrega": ed,
            "antes_bundle": ba, "agora_bundle": bd,
            # o rotulo em portugues viaja com o evento: a mensagem e o
            # PDF leem o mesmo texto e nao podem divergir
            "bundle_antes": _bundle(ba), "bundle_agora": _bundle(bd),
            "preco_mudou": preco_mudou, "entrega_mudou": entrega_mudou,
            "versao_mudou": versao_mudou,
            # so a versao mudou: nem preco nem entrega se moveram
            "versao_apenas": not (preco_mudou or entrega_mudou),
            "unidade": _unidade(atual),
            "atual": atual, "antes": antes, "pracas": []})
        if atual["praca"] not in d["pracas"]:
            d["pracas"].append(atual["praca"])
    return list(achados.values())


def _entrega(l):
    """O degrau da oferta: Mbps na fixa, GB no movel."""
    return l.get("degrau_mbps") or l.get("franquia_anunciada_gb")


def _unidade(l):
    """Mbps ou GB, pelo campo que a oferta preencheu.

    A UNIDADE PERTENCE AO NUMERO, nao ao produto. A regra anterior era
    "Mbps se for fibra ou combo, GB caso contrario" - e a Starlink
    grava produto "satelite", entao os 100 Mbps dela apareciam como
    "100 GB" na mensagem. Mesma coisa para qualquer produto novo: ele
    nasceria com a unidade errada ate alguem lembrar desta linha.
    """
    if l.get("degrau_mbps"):
        return "Mbps"
    if l.get("franquia_anunciada_gb"):
        return "GB"
    return ""


def _grades_reorganizadas(h, o):
    """A escada de cada operadora, comparada pelos dois lados.

    Devolve (lista de eventos, conjunto de operadoras a suprimir).

    POR QUE DOIS LADOS. "R$ 30 dava 25 GB e passou a dar 20" e "25 GB
    custava R$ 30 e passa a custar R$ 35" sao o mesmo fato visto de
    angulos diferentes, e qual deles aparece depende de como a operadora
    mexeu. Em 15/10/2026 a Vivo fez o primeiro; em 20/10, o segundo. Ver
    so um lado deixa metade dos movimentos passar.

    POR QUE PONTO A PONTO. A versao anterior exigia que a lista inteira
    de precos fosse identica nos dois dias, e desistia se um degrau novo
    aparecesse - que e exatamente o que a Vivo fez em 20/10. Agora cada
    preco que existe nos dois dias e comparado com ele mesmo, e o degrau
    que so existe de um lado nao atrapalha os outros.

    A SUPRESSAO CONTINUA: quando a escada desliza inteira, parear por
    nome casa o topo de ontem com o meio de hoje e inventa uma queda que
    nao houve. So que agora ela vale apenas para a operadora e produto
    em que a escada de fato deslizou.
    """
    def agrupar(indice):
        por = collections.defaultdict(list)
        for l in indice.values():
            if l.get("preco_promocional") is None or _entrega(l) is None:
                continue
            por[(l["operadora"], l["produto"], l["praca"])].append(l)
        return por

    # O NOME VIAJA JUNTO porque oferta que some nao e preco que sobe.
    # Entre 17 e 18/10 o "Vivo Total Essencial" de R$ 100 faltou numa
    # praca, o mais barato de 500 Mega virou o "Total Pro" de R$ 160, e
    # sem esta trava o aviso diria que o preco subiu 60%.
    def por_preco(linhas):
        # entre duas ofertas do mesmo preco vale a que entrega mais: e a
        # que o cliente escolheria, e a que representa o degrau
        m = {}
        for l in linhas:
            p, e = l["preco_promocional"], _entrega(l)
            if p not in m or e > m[p][0]:
                m[p] = (e, (l.get("nome_oferta") or "").lower())
        return m

    def por_entrega(linhas):
        # entre duas ofertas da mesma entrega vale a mais barata
        m = {}
        for l in linhas:
            p, e = l["preco_promocional"], _entrega(l)
            if e not in m or p < m[e][0]:
                m[e] = (p, (l.get("nome_oferta") or "").lower())
        return m

    ah, ao = agrupar(h), agrupar(o)
    eventos, suprimir = {}, set()
    for chave, atuais in ah.items():
        anteriores = ao.get(chave)
        if not anteriores:
            continue
        operadora, produto, praca = chave

        ph, po = por_preco(atuais), por_preco(anteriores)
        eh, eo = por_entrega(atuais), por_entrega(anteriores)

        # mesmo preco, outra entrega - e a mesma oferta ocupando o preco
        mesma_etiqueta = sorted(
            (p, po[p][0], ph[p][0]) for p in ph
            if p in po and po[p][0] != ph[p][0] and po[p][1] == ph[p][1])
        # mesma entrega, outro preco - e a mesma oferta no degrau
        mesmo_pacote = sorted(
            (e, eo[e][0], eh[e][0]) for e in eh
            if e in eo and eo[e][0] != eh[e][0] and eo[e][1] == eh[e][1])

        if not mesma_etiqueta and not mesmo_pacote:
            continue
        if mesma_etiqueta:
            # so suprime o pareamento por nome quando a etiqueta de preco
            # mudou de conteudo: e ai que o emparelhamento inventa queda
            suprimir.add((operadora, produto))

        ident = (operadora, produto, tuple(mesma_etiqueta), tuple(mesmo_pacote))
        d = eventos.setdefault(ident, {
            "operadora": operadora, "produto": produto,
            # a unidade sai da linha, e nao do produto: ver _unidade
            "unidade": _unidade(atuais[0]),
            "saltos": mesma_etiqueta, "precos": mesmo_pacote, "pracas": []})
        if praca not in d["pracas"]:
            d["pracas"].append(praca)
    return list(eventos.values()), suprimir


# Ate quando faz sentido chamar de "voltou". Alem disso e produto antigo
# ressuscitado, e comparar preco de dois meses atras sem dizer isso
# engana mais do que informa.
DIAS_DE_MEMORIA = 45


def _degraus_que_voltaram(h, o, hoje):
    """Entrega que reapareceu hoje com preco diferente da ultima vez.

    Os outros detectores comparam hoje com ontem, e por isso nao veem
    movimento feito em dois tempos: em 15/10/2026 a Vivo tirou o degrau
    de 25 GB do pre-pago, e em 20/10 devolveu por R$ 35 em vez de R$ 30.
    No dia 15 foi saida de oferta; no dia 20, entrada. O reajuste de
    16,7% ficou entre os dois dias, invisivel.

    Aqui a pergunta e outra: quando esta operadora vendeu esta entrega
    pela ultima vez, e por quanto.
    """
    def chave(l):
        return (l["operadora"], l["produto"], l["praca"], _entrega(l),
                (l.get("nome_oferta") or "").lower())

    ontem = {chave(l) for l in o.values() if _entrega(l) is not None}
    novos = {}
    for l in h.values():
        if _entrega(l) is None or l.get("preco_promocional") is None:
            continue
        k = chave(l)
        if k in ontem:
            continue
        # entre varias do mesmo degrau vale a mais barata
        if k not in novos or l["preco_promocional"] < novos[k]["preco_promocional"]:
            novos[k] = l
    if not novos:
        return []

    limite = (datetime.fromisoformat(hoje).date()
              - timedelta(days=DIAS_DE_MEMORIA)).isoformat()
    campos = ("data_captura,praca,nome_oferta,preco_promocional,"
              "franquia_anunciada_gb,degrau_mbps")
    cache, eventos = {}, {}
    for k, l in sorted(novos.items()):
        operadora, produto = k[0], k[1]
        if (operadora, produto) not in cache:
            # PAGINADO. Pedir "limit=4000" ao PostgREST devolve 1000
            # linhas sem reclamar, e 1000 linhas de uma operadora sao
            # cerca de quatro dias - a memoria de 45 dias que esta
            # funcao promete nao existia: ela via a semana e dizia que
            # tinha visto o mes e meio.
            linhas, erro = armazenamento.consultar_tudo(
                "capturas?operadora=eq.%s&produto=eq.%s&data_captura=gte.%s"
                "&data_captura=lt.%s&select=%s"
                "&order=data_captura.desc"
                % (urllib.parse.quote(operadora), produto, limite, hoje, campos))
            cache[(operadora, produto)] = [] if erro else (linhas or [])
        antes = None
        for x in cache[(operadora, produto)]:
            if (x.get("praca") == k[2] and _entrega(x) == k[3]
                    and (x.get("nome_oferta") or "").lower() == k[4]
                    and x.get("preco_promocional") is not None):
                antes = x
                break           # a consulta ja vem da mais recente para tras
        if not antes or antes["preco_promocional"] == l["preco_promocional"]:
            continue
        ident = (operadora, produto, k[3], antes["preco_promocional"],
                 l["preco_promocional"], antes["data_captura"])
        d = eventos.setdefault(ident, {
            "operadora": operadora, "produto": produto, "entrega": k[3],
            "unidade": _unidade(l),
            "antes": antes["preco_promocional"],
            "agora": l["preco_promocional"],
            "quando": antes["data_captura"],
            "nome": l.get("nome_oferta"), "pracas": []})
        if k[2] not in d["pracas"]:
            d["pracas"].append(k[2])
    return list(eventos.values())


def _renomeadas(h, o):
    """Oferta que trocou de nome, e o preco que ela levou na troca.

    O nome na identidade protege de comparar ofertas diferentes, mas cria
    um ponto cego: oferta renomeada nao casa com a de ontem e sai da
    comparacao sem gerar alerta. Em 02/10 foi o caso de "TIM Controle",
    que virou "TIM Controle Smart" em 20 pracas - se o preco tivesse
    mudado junto, ninguem saberia, e trocar o nome junto com o preco e
    justamente como um repasse passa desapercebido.

    O reencontro usa a chave de continuidade, que existe para sobreviver a
    renomeacao, e so vale quando sobrou exatamente UMA candidata de cada
    lado: com duas ou mais, qualquer emparelhamento seria chute.
    """
    sobra_h = collections.defaultdict(list)
    sobra_o = collections.defaultdict(list)
    for k, l in h.items():
        if k not in o:
            sobra_h[(l["chave"], l["praca"])].append(l)
    for k, l in o.items():
        if k not in h:
            sobra_o[(l["chave"], l["praca"])].append(l)

    achados = {}
    for cp, atuais in sobra_h.items():
        anteriores = sobra_o.get(cp)
        if not anteriores or len(atuais) != 1 or len(anteriores) != 1:
            continue
        atual, antes = atuais[0], anteriores[0]
        _agrupar(achados, (atual["operadora"], atual["chave"],
                           antes["nome_oferta"], atual["nome_oferta"],
                           antes["preco_promocional"], atual["preco_promocional"]),
                 atual, antes)
    return list(achados.values())


def _operadora_da_rodada(nome):
    """"Claro Flex" -> "Claro". O coletor e separado; a operadora e a mesma."""
    for op in ("Claro", "TIM", "Vivo", "NuCel", "Brisanet", "Unifique", "Starlink"):
        if nome == op or nome.startswith(op + " "):
            return op
    return nome


def _onde(pracas, universo=None):
    """"em todas as 20 praças" ou "em 3 de 20: SP, RJ, BH".

    O DENOMINADOR E ONDE A OFERTA EXISTE. A NuCel e a Starlink nao tem
    praca e gravam "Brasil/BR": contra as 20 do painel, qualquer
    mudanca delas saia como "em 1 de 20" - numero correto e leitura
    errada, porque sugere movimento localizado onde ele foi total.

    E A CONTAGEM E DE PRACAS DISTINTAS. A lista podia trazer repetida
    quando dois eventos caiam no mesmo grupo, e o alcance dobrava.
    """
    quantas = len(set(pracas))
    total = max(universo or len(PRACAS), quantas)
    if quantas >= total:
        if total == 1:
            return "na única praça em que a oferta é vendida"
        return "em todas as %d praças" % total
    nomes = sorted({p.split("/")[0] for p in pracas})[:3]
    return "em %d de %d: %s" % (quantas, total, ", ".join(nomes))


def _mudou_a_entrega(antes, agora):
    """"-20% de internet pelo mesmo preco", ou o contrario.

    "25 -> 20 GB" obriga o leitor a fazer a conta para ver que perdeu um
    quinto do pacote. A direcao e o tamanho tem de estar escritos, e sem
    adjetivo: a conta fica a vista de quem quiser conferir.
    """
    if not antes or agora is None:
        return ""
    pc = (agora - antes) / float(antes) * 100
    if abs(pc) < 0.5:
        return ""
    return "   %+.0f%% de internet pelo mesmo pre\u00e7o" % pc


def _trocou(saiu, entrou):
    """Em portugues, o que aconteceu com os servicos inclusos.

    Os codigos SVA nao tem dicionario publico, entao dizer "saiu 040059"
    e ruido com cara de informacao. O que se sabe e quantos sairam e
    quantos entraram, e isso basta para decidir se vale abrir o
    relatorio.
    """
    def plural(n):
        return "servi\u00e7o" if n == 1 else "servi\u00e7os"

    if saiu and entrou:
        if len(saiu) == len(entrou):
            return "trocou %d %s incluso%s" % (
                len(saiu), plural(len(saiu)), "" if len(saiu) == 1 else "s")
        # "sairam 2 e entraram 1" nao existe: o verbo concorda com o
        # numero que vem depois dele
        # o substantivo fica com o PRIMEIRO numero e o segundo elide:
        # "sairam 2 servicos inclusos e entrou 1". Deixar o
        # substantivo no fim obriga concordancia com os dois de uma
        # vez, o que nao da.
        return "%s %d %s inclu%s e %s %d" % (
            "saiu" if len(saiu) == 1 else "sa\u00edram", len(saiu),
            plural(len(saiu)), "so" if len(saiu) == 1 else "sos",
            "entrou" if len(entrou) == 1 else "entraram", len(entrou))
    if saiu:
        return "perdeu %d %s incluso%s" % (
            len(saiu), plural(len(saiu)), "" if len(saiu) == 1 else "s")
    if entrou:
        return "ganhou %d %s incluso%s" % (
            len(entrou), plural(len(entrou)), "" if len(entrou) == 1 else "s")
    return "mudou o que vem incluso"


def _o_que_mudou(r):
    """As linhas que descrevem uma oferta remodelada, em portugues.

    O NOME INTERNO DA VERSAO NAO SAI. "simples -> com_apps" e como o
    codigo guarda a variante; o que o leitor precisa saber e que a
    oferta passou a incluir assinatura. Mesma regra dos codigos SVA:
    codigo sem dicionario e ruido com cara de informacao.
    """
    u = r.get("unidade") or ""
    linhas = []
    if r["preco_mudou"] and r["entrega_mudou"]:
        linhas.append("%s \u2192 %s%s   com %s \u2192 %s %s%s" % (
            _reais(r["antes_preco"]), _reais(r["agora_preco"]),
            _pct(r["antes_preco"], r["agora_preco"]),
            r["antes_entrega"], r["agora_entrega"], u,
            _pct(r["antes_entrega"], r["agora_entrega"])))
    elif r["preco_mudou"]:
        linhas.append("%s \u2192 %s%s   pela mesma entrega (%s %s)" % (
            _reais(r["antes_preco"]), _reais(r["agora_preco"]),
            _pct(r["antes_preco"], r["agora_preco"]),
            r["agora_entrega"], u))
    elif r["entrega_mudou"]:
        linhas.append("%s \u2192 %s %s%s   pelo mesmo pre\u00e7o (%s)" % (
            r["antes_entrega"], r["agora_entrega"], u,
            _pct(r["antes_entrega"], r["agora_entrega"]),
            _reais(r["agora_preco"])))
    else:
        linhas.append("mesmo pre\u00e7o (%s) e mesma entrega (%s %s)"
                      % (_reais(r["agora_preco"]), r["agora_entrega"], u))

    de, para = _bundle(r.get("antes_bundle")), _bundle(r.get("agora_bundle"))
    if de and para and de != para:
        linhas.append("e passou de \"%s\" para \"%s\"" % (de, para))
    elif r["versao_mudou"]:
        # a versao mudou e a escada de bundle nao: e outra coisa que o
        # nome da oferta nao diz, e o relatorio tem o detalhe
        linhas.append("e voltou \u00e0 vitrine como outra vers\u00e3o da oferta")
    return linhas


def _variacao(de, para):
    if not de or para is None:
        return ""
    return "  %+.0f%%" % ((para - de) / de * 100)


def _pct(de, para):
    """A mesma variacao, entre parenteses, para caber no meio da frase."""
    if not de or para is None:
        return ""
    return " (%+.0f%%)" % ((para - de) / float(de) * 100)


def montar_mensagem(hoje, ontem):
    """O recado do dia: o mercado primeiro, o robo so quando falha."""
    dia = datetime.fromisoformat(hoje).strftime("%d/%m")
    r = mudancas(hoje, ontem)
    mud, comp, renom = r["precos"], r["composicao"], r["renomeadas"]
    grades, voltaram, remodeladas = r["grades"], r["voltaram"], r["remodeladas"]
    erro_cmp, ponto_cego, cobertura = r["erro"], r["cego"], r["cobertura"]
    leitura = r.get("leitura") or []

    # o estado da coleta, que pode virar manchete
    col, _ = armazenamento.consultar(
        "coletas?data_captura=eq.%s&select=operadora,pracas_ok,pracas_pedidas,"
        "ofertas,sucesso,iniciada_em&order=iniciada_em.desc" % hoje)
    if col:
        # em dia de repique a mesma operadora tem varios registros; vale o
        # ultimo, senao a mesma coleta conta duas vezes
        ultima, vistos = [], set()
        for c in col:
            if c["operadora"] in vistos:
                continue
            vistos.add(c["operadora"])
            ultima.append(c)
        col = ultima

    falhas = [c for c in col if not c["sucesso"]] if col else []
    sem_registro = (sorted(set(COLETORES) - {c["operadora"] for c in col})
                    if col else sorted(COLETORES))
    total_ofertas = sum(c["ofertas"] for c in col) if col else 0

    linhas = ["TMT Price Tracker \u00b7 %s" % dia]

    # 1. falha e manchete, nao rodape
    if not col:
        linhas += ["", "O ROB\u00d4 N\u00c3O RODOU HOJE.",
                   "Nenhum registro de coleta. Nada do que vem abaixo \u00e9 de hoje."]
    elif falhas or sem_registro:
        # a falha e manchete e cabe em duas linhas: o detalhe por coletor
        # esta na tabela "Estado da coleta" do relatorio anexo
        quem = ["%s em %d de %d pra\u00e7as"
                % (c["operadora"], c["pracas_ok"], c["pracas_pedidas"])
                for c in falhas]
        quem += ["%s sem registro" % op for op in sem_registro]
        linhas += ["", "COLETA INCOMPLETA \u2014 %s." % ", ".join(quem),
                   "O que vem abaixo vale s\u00f3 para o que foi coletado."]

    if erro_cmp:
        linhas += ["", "N\u00e3o deu para comparar com ontem: %s" % erro_cmp[:100],
                   "Ent\u00e3o n\u00e3o d\u00e1 para dizer o que mudou."]

    # 2. o que mudou
    total_mud = (len(mud) + len(comp) + len(renom) + len(grades)
                 + len(voltaram) + len(remodeladas))
    # Sem registro de coleta nao ha o que comparar, e dizer "nenhuma
    # mudanca" logo abaixo de "o robo nao rodou" contradiz a manchete -
    # soa como noticia verificada num dia em que nao se verificou nada.
    if not erro_cmp and col:
        linhas.append("")
        if not total_mud:
            linhas.append("Nenhuma mudan\u00e7a de pre\u00e7o, composi\u00e7\u00e3o ou nome.")
        else:
            linhas.append("%d mudan\u00e7a%s hoje"
                          % (total_mud, "" if total_mud == 1 else "s"))

        # A COBERTURA QUALIFICA A CONTAGEM, qualquer que ela seja. Com
        # poucas ofertas pareadas, "nenhuma mudanca" descreve a
        # comparacao que nao aconteceu e nao o mercado que ficou
        # parado - e e essa a frase que soa como noticia verificada.
        #
        # E COM MUDANCA TAMBEM. Escrevi esta ressalva so para o dia
        # parado, e isso deixava o buraco inverso: cobertura de 40% com
        # tres mudancas encontradas fazia a mensagem contar as tres sem
        # dizer que nao olhou o resto, e quem le entende que tres e a
        # historia inteira do dia.
        if cobertura and cobertura["fracao"] < COBERTURA_MINIMA:
            linhas += ["", "A compara\u00e7\u00e3o alcan\u00e7ou s\u00f3 %d%% das ofertas "
                       "de hoje: %s."
                       % (round(cobertura["fracao"] * 100),
                          "o sil\u00eancio n\u00e3o confirma que o mercado ficou "
                          "parado" if not total_mud else
                          "pode haver mudan\u00e7a fora do que foi comparado")]

    # O PONTO CEGO QUALIFICA A LINHA DE CIMA, e por isso vem colado
    # nela. "Nenhuma mudanca" com 20 ofertas fora da comparacao nao e a
    # mesma frase que "nenhuma mudanca", e a diferenca entre as duas e
    # exatamente o que o leitor precisa para saber se pode confiar no
    # silencio. Antes isto so chegava ao rodape do PDF.
    if ponto_cego and col:
        linhas += ["", ponto_cego["curto"]]

    for m in mud[:3]:
        a, d = m["antes"], m["atual"]
        de, para = a["preco_promocional"], d["preco_promocional"]
        linhas += ["", "%s \u00b7 %s" % (_categoria(d), _rotulo(d))]
        linhas.append("  %s \u2192 %s%s   %s" % (
            _reais(de), _reais(para), _variacao(de, para), m["onde"]))
    if len(mud) > 3:
        n = len(mud) - 3
        linhas += ["", "e mais %d mudan\u00e7a%s de pre\u00e7o no relat\u00f3rio"
                   % (n, "" if n == 1 else "s")]

    for m in comp[:3]:
        d = m["atual"]
        antes_sva = set((m["antes"]["assinatura_sva"] or "").split("+"))
        agora_sva = set((d["assinatura_sva"] or "").split("+"))
        saiu = sorted(x for x in antes_sva - agora_sva if x)
        entrou = sorted(x for x in agora_sva - antes_sva if x)
        linhas += ["", "%s \u00b7 %s" % (_categoria(d), _rotulo(d))]
        linhas.append("  mesmo pre\u00e7o, %s   %s"
                      % (_trocou(saiu, entrou), m["onde"]))
    if len(comp) > 3:
        linhas += ["", "e mais %d de composi\u00e7\u00e3o no relat\u00f3rio"
                   % (len(comp) - 3)]

    # PRECO E ENTREGA JUNTOS. Vem logo depois das mudancas de preco por
    # ser o movimento de maior efeito sobre o cliente - paga mais e
    # recebe menos - e porque era o unico que a mensagem NEGAVA em vez
    # de omitir. Os dois numeros aparecem com a variacao de cada um,
    # para a conta ficar a vista.
    for r in remodeladas[:3]:
        linhas += ["", "%s \u00b7 %s" % (_categoria(r["atual"]),
                                      _rotulo(r["atual"]))]
        linhas += ["  %s" % x for x in _o_que_mudou(r)]
        linhas.append("  %s" % r["onde"])
    if len(remodeladas) > 3:
        n = len(remodeladas) - 3
        linhas += ["", "e mais %d oferta%s remodelada%s no relat\u00f3rio"
                   % (n, "" if n == 1 else "s", "" if n == 1 else "s")]


    # MESMO PRECO, OUTRA ENTREGA. E o movimento mais facil de nao
    # perceber: o preco na vitrine nao se mexe, e o que encolhe e o que
    # vem dentro. Em 15/10/2026 a Vivo tirou 5 GB do pre-pago de R$ 30 e
    # a linha de entao - "franquia nova" - nao disse que aquilo era 20%
    # menos internet.
    for g in grades[:3]:
        # a unidade sai do campo que a oferta preencheu, e nao do
        # produto: ver _unidade
        unidade = g.get("unidade") or ""
        linhas += ["", "%s \u00b7 %s" % (_categoria(g), g["operadora"])]
        for preco, antes_v, agora_v in g["saltos"][:3]:
            linhas.append("  %s: %s \u2192 %s %s%s" % (
                _reais(preco), antes_v, agora_v, unidade,
                _mudou_a_entrega(antes_v, agora_v)))
        # o outro lado da escada: a mesma entrega passou a custar outro
        # preco. Sem isto, evento que so tem este lado saia em branco.
        for entrega, antes_p, agora_p in g["precos"][:3]:
            linhas.append("  %s %s: %s \u2192 %s%s" % (
                entrega, unidade, _reais(antes_p), _reais(agora_p),
                _variacao(antes_p, agora_p)))
        linhas.append("  %s" % g["onde"])
    if len(grades) > 3:
        n = len(grades) - 3
        linhas += ["", "e mais %d de grade no relat\u00f3rio" % n]

    # DEGRAU QUE VOLTOU COM OUTRO PRECO. E o movimento mais dificil de
    # ver, porque e feito em dois tempos: a operadora retira o degrau num
    # dia e devolve dias depois, mais caro. Comparando so com ontem, o
    # primeiro movimento e "saiu uma oferta" e o segundo e "entrou uma
    # oferta" - e o reajuste fica escondido entre os dois.
    for v in voltaram[:3]:
        unidade = v.get("unidade") or ""
        quando = datetime.fromisoformat(v["quando"]).strftime("%d/%m")
        pc = ((v["agora"] - v["antes"]) / float(v["antes"]) * 100
              if v["antes"] else 0)
        linhas += ["", "%s \u00b7 %s" % (_categoria(v), v["operadora"])]
        linhas.append("  %s %s voltou por %s   %+.0f%% sobre os %s de %s"
                      % (v["entrega"], unidade, _reais(v["agora"]), pc,
                         _reais(v["antes"]), quando))
        linhas.append("  %s" % v["onde"])
    if len(voltaram) > 3:
        linhas += ["", "e mais %d degrau(s) que voltaram, no relat\u00f3rio"
                   % (len(voltaram) - 3)]

    for m in renom[:3]:
        a, d = m["antes"], m["atual"]
        de, para = a["preco_promocional"], d["preco_promocional"]
        linhas += ["", "%s \u00b7 mudou de nome" % d["operadora"]]
        linhas.append("  %s \u2192 %s" % (a["nome_oferta"] or "?", d["nome_oferta"] or "?"))
        if de is not None and para is not None and de != para:
            linhas.append("  e o pre\u00e7o foi de %s para %s%s"
                          % (_reais(de), _reais(para), _variacao(de, para)))
        else:
            linhas.append("  pelo mesmo pre\u00e7o (%s)" % _reais(para))
    if len(renom) > 3:
        linhas.append("  e mais %d renomeada(s)" % (len(renom) - 3))

    # O QUE MUDOU FOI A NOSSA LEITURA. Fica no FIM, depois dos eventos,
    # porque nao e um evento: e uma ressalva sobre o dado, e lugar de
    # ressalva e depois do que ela qualifica. Ver _separar_o_que_e_nosso.
    if leitura:
        ops = sorted({x["operadora"] for x in leitura})
        n = len(leitura)
        # quando a mexida foi declarada, a mensagem diz QUAL foi - e
        # melhor do que "costuma ser", que e o que sobra sem declaracao
        declarado = LEITURA_MUDOU_EM.get(hoje)
        porque = ("a leitura mudou hoje: %s" % declarado if declarado
                  else "isso costuma ser mudan\u00e7a na nossa leitura, e "
                       "n\u00e3o no mercado")
        linhas += ["", "%d oferta%s %s de vers\u00e3o sem mexer em "
                   "pre\u00e7o nem entrega (%s) \u2014 %s. Detalhe no "
                   "relat\u00f3rio."
                   % (n, "" if n == 1 else "s",
                      "mudou" if n == 1 else "mudaram", ", ".join(ops),
                      porque)]

    # O FIM DA MENSAGEM E O LINK, e nao mais a entrada por produto e a
    # telemetria. Os dois viraram tabela no relatorio anexo, com mais
    # detalhe do que cabia aqui: o catalogo inteiro de quatro produtos,
    # e o estado de cada coletor com pracas e ofertas.
    #
    # A mensagem e lida no telefone para saber SE mexeram e em QUE.
    # Consulta se faz no PDF.
    linhas += ["", "Relat\u00f3rio completo em anexo \u00b7 %s" % PAINEL]


    # O VIGIA OLHA O DADO, e nao o que mudou. Sao perguntas diferentes:
    # o comparador pergunta "o mercado se mexeu?", o vigia pergunta "o
    # que eu coletei faz sentido?". Um dia pode estar calmo no primeiro
    # e podre no segundo - foi o caso dos 18 dias em que a Brisanet veio
    # inteira sem velocidade.
    denuncias = []
    do_dia, antes, erro_vigia = _capturas_para_o_vigia(hoje)
    if erro_vigia:
        denuncias = [("atencao", "nao deu para conferir o dado: %s"
                      % str(erro_vigia)[:60])]
    elif do_dia is not None:
        denuncias = vigia.achados(do_dia, antes)
    grave = vigia.resumo(denuncias)
    if grave:
        linhas += ["", grave]

    # O MESMO LEVANTAMENTO ALIMENTA O PDF. A mensagem e o resumo que
    # cabe na tela do telefone; o relatorio anexo traz as tabelas
    # inteiras. Os dois saem daqui para nao poderem discordar.
    dados = {
        "dia": hoje, "ontem": ontem,
        "mudancas_preco": mud, "mudancas_composicao": comp,
        "renomeadas": renom, "grades": grades, "voltaram": voltaram,
        "remodeladas": remodeladas, "leitura": leitura,
        "erro_comparacao": erro_cmp, "cobertura": cobertura,
        # a frase longa e a do relatorio, onde ha espaco para explicar
        # o que "chave de serie" quer dizer; a curta ja foi na mensagem
        "ponto_cego": ponto_cego["longo"] if ponto_cego else None,
        "coletas": col, "falhas": falhas, "sem_registro": sem_registro,
        "denuncias": denuncias,
        "total_ofertas": total_ofertas,
    }
    return "\n".join(linhas), dados

# O Telegram recusa mensagem acima disto, e recusa INTEIRA: nao corta,
# devolve erro e o dia fica sem aviso.
TETO_TELEGRAM = 4096


def _cabe_no_telegram(texto):
    """Corta a mensagem antes de o Telegram a recusar.

    A mensagem e curta por desenho - seis linhas num dia normal -, mas
    e justamente o dia ruim que a engorda: nove operadoras sem
    registro, erro de comparacao, ponto cego, denuncia do vigia e tres
    eventos de cada tipo. E o dia ruim e o que nao pode ficar sem
    aviso: ficar sem a metade de baixo da mensagem e um problema, ficar
    sem a mensagem toda e outro, muito maior.

    O corte e no fim e sai declarado, para ninguem ler uma lista
    truncada pensando que ela acabou ali.
    """
    if len(texto) <= TETO_TELEGRAM:
        return texto
    nota = "\n\n[mensagem cortada aqui; o relat\u00f3rio em anexo est\u00e1 completo]"
    return texto[:TETO_TELEGRAM - len(nota)].rstrip() + nota


def rodar_aviso(simular=False):
    hoje = agora().date()
    ontem = hoje - timedelta(days=1)
    texto, dados = montar_mensagem(hoje.isoformat(), ontem.isoformat())
    print(texto)
    if simular:
        print("\n[simulacao] mensagem nao enviada")
        return 0
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    # O ANEXO NAO PODE DERRUBAR O AVISO. Se o PDF falhar, a mensagem vai
    # do mesmo jeito e o erro entra nela: ficar sem o anexo e um
    # problema, ficar sem o aviso do dia e outro, muito maior.
    pdf, erro_pdf = _montar_pdf(dados)
    if erro_pdf:
        texto += "\n\n(o relatorio em PDF nao foi gerado hoje: %s)" % erro_pdf[:80]

    r = _tel("sendMessage", {"chat_id": chat,
                             "text": _cabe_no_telegram(texto)})
    if not r.get("ok"):
        print("\nFALHOU ao enviar: %s" % r)
        return 1
    print("\nenviado")

    if pdf:
        d = _tel_documento(chat, pdf, "Relatorio completo de %s"
                           % datetime.fromisoformat(dados["dia"]).strftime("%d/%m"))
        if d.get("ok"):
            print("relatorio anexado: %s" % pdf)
        else:
            # o aviso ja foi: o anexo que falhou vira recado proprio
            print("FALHOU ao anexar o relatorio: %s" % d)
            _tel("sendMessage", {"chat_id": chat,
                                 "text": "O relatorio em PDF de hoje nao subiu. "
                                         "A mensagem acima vale; so o anexo faltou."})

    # O E-MAIL E CANAL SECUNDARIO. Vai o mesmo texto e o mesmo anexo, e
    # problema nele nao derruba a rodada: o Telegram ja chegou. Enquanto
    # os segredos nao existirem, isto nao faz nada e nao reclama.
    import email_diario
    if email_diario.configurado():
        dia_br = datetime.fromisoformat(dados["dia"]).strftime("%d/%m/%Y")
        ok, recado = email_diario.enviar(
            "TMT Price Tracker - relatorio de %s" % dia_br, texto, pdf)
        print("e-mail: %s" % recado)
        if not ok:
            # falha de e-mail nao vai para o Telegram do usuario: ele ja
            # recebeu o aviso. Fica no log da rodada, que e onde se
            # conserta.
            print("  (o aviso do Telegram foi enviado normalmente)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coletar", action="store_true")
    ap.add_argument("--avisar", action="store_true")
    ap.add_argument("--praca")
    ap.add_argument("--simular", action="store_true")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not (a.coletar or a.avisar):
        ap.error("escolha --coletar ou --avisar")
    if a.coletar:
        _, falhas = rodar_coleta(a.praca, a.simular)
        # Sair diferente de zero quando algo ficou incompleto. Isto existe
        # para o repique poder ser condicional: antes ele rodava a coleta
        # inteira de novo TODO dia, o que dobrava o consumo de minutos do
        # Actions - medido em 87 min/dia, contra a cota de 2000 por mes.
        # Agora o dia em que tudo deu certo custa metade, e o repique volta
        # a ser o que o nome diz: a segunda tentativa de quem falhou.
        if falhas:
            return 1
    if a.avisar:
        return rodar_aviso(a.simular)
    return 0


if __name__ == "__main__":
    sys.exit(main())
