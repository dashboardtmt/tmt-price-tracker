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

from coletores import (armazenamento, brisanet, claro, claro_flex, nucel, starlink, tim_fit,  # noqa: E402
                       tim, unifique, vivo)
from coletores.pracas import PRACAS, pracas_de, rotulo   # noqa: E402

BRT = timezone(timedelta(hours=-3))

# Quais operadoras ja tem coletor. As outras entram conforme ficarem prontas;
# a serie comeca desigual de proposito (decisao 18) porque esperar custa
# historico que nao volta.
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


def entrada_do_produto(hoje, produto, praca="Sao Paulo/SP"):
    """O plano de entrada de cada operadora, na praca de referencia."""
    filtro = ("capturas?data_captura=eq.%s&produto=eq.%s&praca=eq.%s"
              "&select=operadora,nome_oferta,destaque,preco_promocional"
              "&order=preco_promocional.asc"
              % (hoje, produto, urllib.parse.quote(praca)))
    linhas, erro = armazenamento.consultar(filtro)
    if erro or not linhas:
        return [], erro
    vistos, saida = set(), []
    for l in linhas:
        if l["operadora"] in vistos or l["preco_promocional"] is None:
            continue
        vistos.add(l["operadora"])
        saida.append(l)
    return saida, None


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
    # DUAS OFERTAS COM A MESMA IDENTIDADE: uma sobrescreve a outra e some
    # do aviso. Era o caso das duas "Vivo Familia 2 + TV" de 700 Mega, a
    # R$ 290 e a R$ 390 - 20 capturas por dia que nunca foram comparadas,
    # e uma diferenca de R$ 100 em ponto cego. A chave de continuidade ja
    # separa aquele par; isto aqui garante que o proximo nao passe calado.
    indice, colididas = {}, []
    for l in (linhas or []):
        k = _identidade(l)
        if k in indice:
            colididas.append(l)
            continue
        indice[k] = l
    # A colisao NAO vai no canal de erro. Erro cancela a comparacao
    # inteira, e isso e certo para consulta que caiu - mas colisao em 20
    # ofertas nao pode apagar o que mudou nas outras 1.640. Foi o que
    # aconteceu em 16/10/2026, com o aviso do dia saindo vazio.
    aviso = None
    if colididas:
        # _rotulo evita o "Vivo Vivo Familia 2 + TV": o nome da oferta
        # ja comeca com a marca na maioria das operadoras
        quais = sorted({_rotulo(c) for c in colididas})
        aviso = ("%d oferta(s) não foram comparadas por compartilharem "
                 "chave de série, praça e nome com outra oferta (%s). "
                 "Não é possível afirmar se houve variação de preço nelas."
                 % (len(colididas), "; ".join(quais[:2])))
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
             "btl": "Below-the-line"}


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
    """Uma mudanca nacional e um alerta com 20 pracas, nao 20 alertas."""
    d = achados.setdefault(ident, {"pracas": [], "atual": atual, "antes": antes})
    d["pracas"].append(atual["praca"])


def mudancas(hoje, ontem):
    """O que mudou de ontem para hoje, na mesma chave e praca.

    Devolve duas listas: as mudancas de preco e as de composicao com
    preco parado. A segunda registra oferta cujo preco nao se moveu e
    cujo conjunto de servicos inclusos mudou. Sem a assinatura dos
    codigos SVA isso passava batido, porque o nome e o preco da oferta
    continuam identicos.
    """
    h, erro_h, cego_h = _indexar(hoje)
    o, erro_o, cego_o = _indexar(ontem)
    # o ponto cego de hoje e o que importa para o leitor; o de ontem so
    # vale dizer se hoje estiver limpo
    cego = cego_h or cego_o
    # Comparacao que falhou nao e comparacao sem novidade. Sem devolver o
    # erro, uma consulta que caiu faria o aviso afirmar "nada mudou" - pior
    # que nao avisar, porque soa como noticia verificada.
    if erro_h or erro_o:
        return [], [], [], [], erro_h or erro_o, cego
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
        if antes["preco_promocional"] is not None and \
                atual["preco_promocional"] != antes["preco_promocional"]:
            _agrupar(precos, (atual["operadora"], atual["produto"], atual["chave"],
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
                                  atual["chave"], a, d), atual, antes)

    renomeadas = [r for r in _renomeadas(h, o)
                  if (r["atual"]["operadora"], r["atual"]["produto"]) not in suprimir]
    return (list(precos.values()), list(composicao.values()),
            renomeadas, grades, None, cego)


def _entrega(l):
    """O degrau da oferta: Mbps na fixa, GB no movel."""
    return l.get("degrau_mbps") or l.get("franquia_anunciada_gb")


def _grades_reorganizadas(h, o):
    """Operadoras que mantiveram os precos e mexeram nos degraus.

    Devolve (lista de eventos, conjunto de operadoras a suprimir). A
    supressao existe porque, quando a escada inteira desliza, parear por
    nome casa o topo de ontem com o meio de hoje e inventa uma queda que
    nao houve.
    """
    def agrupar(indice):
        por = collections.defaultdict(list)
        for l in indice.values():
            por[(l["operadora"], l["produto"], l["praca"])].append(l)
        return por

    ah, ao = agrupar(h), agrupar(o)
    eventos, suprimir = {}, set()
    for chave, atuais in ah.items():
        anteriores = ao.get(chave)
        if not anteriores or len(atuais) < 2:
            continue
        precos_h = sorted(x["preco_promocional"] for x in atuais
                          if x["preco_promocional"] is not None)
        precos_o = sorted(x["preco_promocional"] for x in anteriores
                          if x["preco_promocional"] is not None)
        if not precos_h or precos_h != precos_o:
            continue        # algum preco mudou: nao e so reorganizacao

        # mesmo preco a mesmo preco, o degrau mudou?
        por_preco_h = {x["preco_promocional"]: _entrega(x) for x in atuais}
        por_preco_o = {x["preco_promocional"]: _entrega(x) for x in anteriores}
        saltos = [(p, por_preco_o[p], por_preco_h[p]) for p in por_preco_h
                  if p in por_preco_o
                  and por_preco_o[p] is not None and por_preco_h[p] is not None
                  and por_preco_o[p] != por_preco_h[p]]
        if not saltos:
            continue

        operadora, produto, praca = chave
        suprimir.add((operadora, produto))
        ident = (operadora, produto, tuple(sorted(saltos)))
        d = eventos.setdefault(ident, {"operadora": operadora, "produto": produto,
                                       "saltos": sorted(saltos), "pracas": []})
        d["pracas"].append(praca)
    return list(eventos.values()), suprimir


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


def _onde(pracas):
    """"em todas as 20 praças" ou "em 3 de 20: SP, RJ, BH"."""
    n = len(pracas)
    if n >= len(PRACAS):
        return "em todas as %d praças" % len(PRACAS)
    nomes = sorted({p.split("/")[0] for p in pracas})[:3]
    return "em %d de %d: %s" % (n, len(PRACAS), ", ".join(nomes))


def _variacao(de, para):
    if not de or para is None:
        return ""
    return "  %+.0f%%" % ((para - de) / de * 100)


def montar_mensagem(hoje, ontem):
    """O recado do dia: o mercado primeiro, o robo so quando falha."""
    dia = datetime.fromisoformat(hoje).strftime("%d/%m")
    mud, comp, renom, grades, erro_cmp, ponto_cego = mudancas(hoje, ontem)

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

    linhas = ["Price Tracker \u00b7 %s" % dia]

    # 1. falha e manchete, nao rodape
    if not col:
        linhas += ["", "O ROB\u00d4 N\u00c3O RODOU HOJE.",
                   "Nenhum registro de coleta. Nada do que vem abaixo \u00e9 de hoje."]
    elif falhas or sem_registro:
        linhas += ["", "ATEN\u00c7\u00c3O: a coleta de hoje est\u00e1 incompleta."]
        for c in falhas:
            linhas.append("  %s: %d de %d pra\u00e7as" % (
                c["operadora"], c["pracas_ok"], c["pracas_pedidas"]))
        if sem_registro:
            linhas.append("  sem registro: %s" % ", ".join(sem_registro))
        linhas.append("  Operadora incompleta deixa buraco, nunca zero.")

    if erro_cmp:
        linhas += ["", "N\u00e3o deu para comparar com ontem: %s" % erro_cmp[:100],
                   "Ent\u00e3o n\u00e3o d\u00e1 para dizer o que mudou."]

    # 2. o que mudou
    total_mud = len(mud) + len(comp) + len(renom) + len(grades)
    if not erro_cmp:
        linhas.append("")
        if not total_mud:
            linhas.append("Nenhuma mudan\u00e7a de pre\u00e7o, composi\u00e7\u00e3o ou nome.")
        else:
            linhas.append("%d mudan\u00e7a%s hoje"
                          % (total_mud, "" if total_mud == 1 else "s"))

    for m in mud[:6]:
        a, d = m["antes"], m["atual"]
        de, para = a["preco_promocional"], d["preco_promocional"]
        linhas += ["", "%s \u00b7 %s" % (_categoria(d), _rotulo(d))]
        linhas.append("  %s \u2192 %s%s   %s" % (
            _reais(de), _reais(para), _variacao(de, para), _onde(m["pracas"])))
        avisos = []
        if a.get("franquia_anunciada_gb") != d.get("franquia_anunciada_gb"):
            avisos.append("a franquia tamb\u00e9m mudou")
        if a.get("nivel_bundle") != d.get("nivel_bundle"):
            avisos.append("o que vem junto tamb\u00e9m mudou")
        if avisos:
            linhas.append("  (%s)" % " e ".join(avisos))
    if len(mud) > 6:
        linhas.append("  e mais %d mudan\u00e7a(s) de pre\u00e7o" % (len(mud) - 6))

    for m in comp[:3]:
        d = m["atual"]
        antes_sva = set((m["antes"]["assinatura_sva"] or "").split("+"))
        agora_sva = set((d["assinatura_sva"] or "").split("+"))
        saiu = sorted(x for x in antes_sva - agora_sva if x)
        entrou = sorted(x for x in agora_sva - antes_sva if x)
        linhas += ["", "%s \u00b7 %s \u2014 mesmo pre\u00e7o, outra "
                   "composi\u00e7\u00e3o" % (_categoria(d), _rotulo(d))]
        if saiu:
            linhas.append("  saiu: %s" % ", ".join(saiu))
        if entrou:
            linhas.append("  entrou: %s" % ", ".join(entrou))
        linhas.append("  %s" % _onde(m["pracas"]))
    if len(comp) > 3:
        linhas.append("  e mais %d de composi\u00e7\u00e3o" % (len(comp) - 3))

    for g in grades[:3]:
        linhas += ["", "%s \u00b7 %s \u2014 mesmos pre\u00e7os, franquia nova"
                   % (g["operadora"], g["produto"])]
        for preco, antes_v, agora_v in g["saltos"][:3]:
            linhas.append("  %s: %s \u2192 %s GB" % (_reais(preco), antes_v, agora_v))
        linhas.append("  %s" % _onde(g["pracas"]))
    if len(grades) > 3:
        linhas.append("  e mais %d de grade" % (len(grades) - 3))

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

    # quem nao mexeu em nada tambem e informacao
    if not erro_cmp and total_mud and col:
        mexeram = ({m["atual"]["operadora"] for m in mud}
                   | {m["atual"]["operadora"] for m in comp}
                   | {m["atual"]["operadora"] for m in renom}
                   | {g["operadora"] for g in grades})
        # o nome da rodada nao e o nome da operadora: "Claro Flex" e
        # "TIM FIT" sao coletores a parte, mas gravam como Claro e TIM
        paradas = sorted({_operadora_da_rodada(c["operadora"]) for c in col}
                         - mexeram)
        if paradas:
            linhas += ["", "Sem mudan\u00e7a: %s" % ", ".join(paradas)]

    # 3. o preco de entrada, uma linha por produto
    blocos = []
    for produto, titulo in (("controle", "Controle"), ("fibra", "Fibra"),
                            ("movel", "P\u00f3s-pago"), ("btl", "Below-the-line")):
        entrada, _ = entrada_do_produto(hoje, produto)
        if not entrada:
            continue
        itens = ["%s %s" % (e["operadora"], _reais(e["preco_promocional"]))
                 for e in entrada]
        blocos.append("  %-15s %s" % (titulo, " \u00b7 ".join(itens)))
    if blocos:
        linhas += ["", "Entrada em SP"] + blocos

    # 3b. o ponto cego, quando existe. Nao cancela nada: diz que aquelas
    # ofertas nao puderam ser comparadas, e o resto da mensagem vale.
    if ponto_cego:
        linhas += ["", "Ponto cego: %s" % ponto_cego]

    # 4. a telemetria, em uma linha quando esta tudo bem
    if col and not falhas and not sem_registro:
        linhas += ["", "%d ofertas \u00b7 %d coletores \u00b7 %d pra\u00e7as \u00b7 tudo ok"
                   % (total_ofertas, len(col), len(PRACAS))]

    # O MESMO LEVANTAMENTO ALIMENTA O PDF. A mensagem e o resumo que
    # cabe na tela do telefone; o relatorio anexo traz as tabelas
    # inteiras. Os dois saem daqui para nao poderem discordar.
    dados = {
        "dia": hoje, "ontem": ontem,
        "mudancas_preco": mud, "mudancas_composicao": comp,
        "renomeadas": renom, "grades": grades,
        "erro_comparacao": erro_cmp, "ponto_cego": ponto_cego,
        "coletas": col, "falhas": falhas, "sem_registro": sem_registro,
        "total_ofertas": total_ofertas,
    }
    return "\n".join(linhas), dados

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

    r = _tel("sendMessage", {"chat_id": chat, "text": texto})
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
