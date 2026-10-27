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
import concurrent.futures
import io
import json
import os
import re
import sys
import threading
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

# AS RAIAS DA COLETA. Cada raia roda numa thread; dentro de uma raia, os
# coletores rodam um depois do outro.
#
# POR QUE EXISTE. Em sequencia a coleta levava 46 minutos, medidos em
# 27/10/2026: Vivo 18m51s, Claro 7m57s, Brisanet 7m53s, TIM 7m12s, e os
# outros cinco somando 2 minutos. Contra a cota de 2.000 minutos/mes do
# Actions isso dava ~59 min/dia com os oito gatilhos - 88% da cota, sem
# margem. Em 27/10 a cota acabou no dia 27: a coleta rodou e os jobs do
# aviso e da tela nao chegaram a iniciar, entao o dia foi coletado e
# ficou sem mensagem e sem tela.
#
# Em paralelo o relogio vira o da raia mais lenta - a Vivo, 19 minutos -
# em vez da soma. O ganho e de ~25 minutos por dia, e o custo do Actions
# e tempo de relogio do job.
#
# POR QUE NAO UMA RAIA POR COLETOR. Duas razoes, e as duas sao medidas:
#
#   MESMO HOST, MESMA FILA. TIM e TIM FIT batem no mesmo dominio: o FIT
#   sai das etiquetas linkadas na pagina de Controle da TIM. Dobrar a
#   batida de um host so para ganhar segundos convida bloqueio - e a
#   Vivo ja bloqueou o acesso quando as requisicoes sairam em rajada,
#   durante a investigacao de 10/2026. (O Claro Flex NAO entra nesta
#   regra: ele tem dominio proprio, fora de claro.com.br. Ele esta na
#   raia de navegador pela razao de baixo.)
#
#   NAVEGADOR NAO VAI PARA THREAD. Unifique, NuCel e Claro Flex sobem
#   Chromium pelo Playwright, cuja API sincrona nao foi feita para
#   varias instancias concorrentes. Os tres somam 35 segundos: paralelizar
#   nao compra nada e paga risco. Ficam todos na mesma raia.
#
# A praca continua SEQUENCIAL dentro de cada operadora, de proposito. E
# ali que esta a rajada que derruba: 20 requisicoes simultaneas no mesmo
# host e o padrao que anti-bot existe para barrar.
RAIAS = (
    ("Vivo",),                      # a mais lenta: e ela que define o relogio
    ("Claro",),
    ("TIM", "TIM FIT"),             # mesmo dominio
    ("Brisanet",),
    ("Starlink",),
    ("Claro Flex", "Unifique", "NuCel"),   # os tres de navegador
)

# COLETOR FORA DAS RAIAS NAO COLETA, e nao coletar calado e o pior jeito
# de falhar que este projeto tem: a serie e append-only, entao o dia que
# nao entra nao volta. Quem adicionar um coletor em COLETORES e esquecer
# de lhe dar raia descobre aqui, na importacao, e nao em marco olhando um
# grafico com um buraco de cinco meses.
_nas_raias = [n for raia in RAIAS for n in raia]
if sorted(_nas_raias) != sorted(COLETORES):
    faltam = sorted(set(COLETORES) - set(_nas_raias))
    sobram = sorted(set(_nas_raias) - set(COLETORES))
    raise RuntimeError(
        "RAIAS e COLETORES nao batem%s%s"
        % (" - sem raia: %s" % ", ".join(faltam) if faltam else "",
           " - raia sem coletor: %s" % ", ".join(sobram) if sobram else ""))
if len(_nas_raias) != len(set(_nas_raias)):
    raise RuntimeError("coletor repetido nas RAIAS: coletaria duas vezes")


def agora():
    return datetime.now(BRT)


# ------------------------------------------------------------------ coleta

def _dizer(linha):
    print(linha, flush=True)


def coletar_operadora(nome, modulo, pracas, simular=False, verbose=True,
                      escrever=_dizer):
    """Coleta uma operadora nas suas pracas e grava o que veio.

    `escrever` recebe cada linha de progresso. Em paralelo as raias
    escrevem ao mesmo tempo, e quem chama passa uma funcao que prefixa a
    linha com o nome da operadora - sem isso o log vira nove conversas
    sobrepostas e deixa de servir para achar onde travou.
    """
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
            escrever("  [%2d/%2d] %-22s %d ofertas acumuladas"
                     % (i, len(pracas), rotulo(p), len(ofertas)))

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
        escrever("  [simulacao] %d ofertas nao gravadas" % len(ofertas))
        return ofertas, registro, None

    gravadas, erro = armazenamento.gravar_capturas(ofertas)
    if erro:
        registro["sucesso"] = False
        registro["avisos"] = (registro["avisos"] or []) + ["gravacao: %s" % erro]
    # O DIARIO DE BORDO TEM DE SER GRAVADO, e o retorno disto era
    # descartado. Linha de "coletas" que nao entra faz ja_coletou nunca
    # fechar o dia - ele conta coletores registrados - e cada gatilho
    # seguinte coleta de novo E manda outra mensagem diaria: ate tres no
    # mesmo dia, com ~50 minutos de Actions cada.
    ok, erro_registro = armazenamento.registrar_coleta(registro)
    if not ok:
        escrever("     ATENCAO: o registro da rodada nao gravou (%s)."
                 % str(erro_registro)[:80])
        escrever("     O dia pode ser recoletado pelo proximo gatilho.")
        erro = erro or ("registro da rodada: %s" % erro_registro)
    return ofertas, registro, erro


def pracas_da_operadora(nome, modulo, uma_praca=None):
    # operadora nacional roda uma vez: repetir nas 20 pracas gravaria
    # 20 copias do mesmo preco
    if getattr(modulo, "NACIONAL", False):
        # o filtro de praca (modo teste) nao se aplica a operadora nacional
        return [{"cidade": "Brasil", "uf": "BR", "regiao": "Nacional",
                 "capital": False}]
    pracas = pracas_de(nome)
    if uma_praca:
        cidade, uf = uma_praca.split("/")
        pracas = [p for p in pracas if p["cidade"] == cidade and p["uf"] == uf]
    return pracas


def rodar_coleta(uma_praca=None, simular=False, raias=RAIAS):
    """Roda as raias em paralelo e devolve o resumo na ordem de COLETORES.

    Ver RAIAS para por que o paralelo existe e por que ele para no nivel
    da operadora. Passar raias=(tuple(COLETORES),) poe tudo numa raia so,
    que e a coleta em serie de antes - e o que --em-serie faz.
    """
    print("=" * 70)
    print("COLETA  %s" % agora().strftime("%d/%m/%Y %H:%M"))
    print("=" * 70)

    # UMA LINHA POR VEZ. Sem a tranca, duas raias escrevendo juntas
    # partem a linha uma da outra e o log deixa de servir para achar
    # onde travou - que e justamente para o que ele existe num job de
    # 20 minutos sem ninguem olhando.
    tranca = threading.Lock()

    def falar(linha):
        with tranca:
            print(linha, flush=True)

    def correr_raia(nomes):
        registros = []
        for nome in nomes:
            modulo = COLETORES[nome]
            pracas = pracas_da_operadora(nome, modulo, uma_praca)
            marcar = lambda l, n=nome: falar("%-11s %s" % (n, l))
            marcar("- %d pracas" % len(pracas))
            ofertas, registro, _ = coletar_operadora(
                nome, modulo, pracas, simular, escrever=marcar)
            marcar("  %d ofertas, %d/%d pracas%s" % (
                len(ofertas), registro["pracas_ok"], registro["pracas_pedidas"],
                "" if registro["sucesso"] else "  (COM AVISOS)"))
            for a in (registro["avisos"] or [])[:5]:
                marcar("     " + a)
            registros.append(registro)
        return registros

    # A EXCECAO CONTINUA DERRUBANDO A RODADA, de proposito: e assim que o
    # job da coleta falha e o repique roda. As outras raias terminam
    # assim mesmo - o executor espera todas - e cada operadora ja gravou
    # o que coletou antes de voltar, entao o que entrou no banco fica.
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, len(raias))) as pool:
        por_raia = list(pool.map(correr_raia, raias))

    # A ORDEM DE COLETORES, e nao a de quem terminou primeiro. O resumo
    # alimenta a mensagem e o relatorio, e ordem que muda a cada dia
    # conforme a rede estava faria a tabela "Estado da coleta" dancar
    # sem nada ter mudado.
    por_nome = {r["operadora"]: r for raia in por_raia for r in raia}
    resumo = [por_nome[n] for n in COLETORES if n in por_nome]

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
        entradas, falhou = {}, {}
        for chave, _rot in relatorio.PRODUTOS:
            itens, erro = ofertas_do_produto(dados["dia"], chave)
            entradas[chave] = itens
            # "Sem dados disponiveis" e indistinguivel de "a consulta
            # caiu", e e justamente essa distincao que o cabecalho deste
            # relatorio promete manter
            if erro:
                falhou[chave] = str(erro)[:120]
        dados = dict(dados, erros_catalogo=falhou)
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
              "nivel_bundle,codigo_anatel,"
              "assinatura_sva:bruto->>assinatura_sva,"
              # A RECUSA DO COLETOR, que ninguem lia. Quatro coletores
              # escrevem avisos_oferta em sete lugares - regulamento de
              # outra oferta, card sem composicao, total anual que nao
              # fecha - e o campo nunca saiu do bruto. O numero errado
              # nao foi gravado, e o buraco nao foi anunciado.
              "avisos_oferta:bruto->avisos_oferta")
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
    # as descartadas tambem interessam a quem pergunta "esta oferta
    # estava na vitrine ontem?": descartada e diferente de ausente

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
    return indice, erro, _aviso_de_colisao(colididas)


def _aviso_de_colisao(colididas):
    """A ressalva das ofertas que ficaram fora, do tamanho do que sobrou.

    Mora fora de _indexar porque o desempate por codigo_anatel refaz a
    conta depois, com o grupo ja reduzido: um dia em que o codigo
    resolve tudo nao pode continuar anunciando 40 ofertas fora da
    comparacao.
    """
    if not colididas:
        return None
    # _rotulo evita o "Vivo Vivo Familia 2 + TV": o nome da oferta
    # ja comeca com a marca na maioria das operadoras
    quais = sorted({_rotulo(c) for c in colididas})
    return {
            "quantas": len(colididas),
            # as linhas em si, para _degraus_que_voltaram nao confundir
            # "descartada de ontem" com "ausente de ontem"
            "descartadas": colididas,
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


def _desempatar_por_anatel(h, cego_h, o, cego_o):
    """Dentro do grupo que colide, o codigo de registro separa as ofertas.

    Devolve os dois avisos refeitos. Mexe em h e em o no lugar: a oferta
    que o codigo resolve entra com a identidade estendida pelo codigo nos
    DOIS dias, e e isso que faz o par existir.

    SO DENTRO DO GRUPO. A identidade geral nao leva o codigo porque ele
    troca sozinho em 2,6% das ofertas unicas - e quando troca, troca
    junto com o preco, que e justamente a noticia (Vivo Fibra 700,
    R$ 150 -> 100 em 08/10/2026). Ver o cabecalho do commit.
    """
    def descartadas(cego):
        g = collections.defaultdict(list)
        for l in ((cego or {}).get("descartadas") or ()):
            g[_identidade(l)].append(l)
        return g

    # so as identidades que algum dos dois dias reclamou sao olhadas:
    # quem ja pareia bem nao e tocado
    d_h, d_o = descartadas(cego_h), descartadas(cego_o)
    bases = set(d_h) | set(d_o)

    def separavel(linhas):
        """O codigo da identidade propria a cada linha do grupo?

        Exige codigo em todas e todos distintos. Sem isso, promover o
        grupo trocaria a ambiguidade de lugar em vez de resolve-la: duas
        linhas cairiam na mesma identidade estendida e voltaria o sorteio
        que produziu o falso "-26% em todas as 20 pracas".
        """
        cods = [l.get("codigo_anatel") for l in linhas]
        return bool(cods) and all(cods) and len(set(cods)) == len(cods)

    promovidas_h, promovidas_o = set(), set()
    for k in bases:
        # CADA LADO DECIDE SOZINHO. Grupo separavel entra no indice
        # mesmo sem contraparte: a oferta fica sem par, que e a verdade
        # que a cobertura conta, e nao "indistinguivel das irmas".
        lh, lo = d_h.get(k) or [], d_o.get(k) or []
        pode_h, pode_o = separavel(lh), separavel(lo)
        # A LINHA QUE ESTA NO INDICE NAO ESTAVA AMBIGUA. Ela e unica no
        # seu dia e so e puxada para ca porque o OUTRO dia colidiu - 452
        # grupos medidos. Sobe junto com o outro lado, para que o par
        # exista; sozinha, sair da identidade base nao ganharia nada.
        if not lh and pode_o and h.get(k) is not None:
            lh, pode_h = [h[k]], separavel([h[k]])
        if not lo and pode_h and o.get(k) is not None:
            lo, pode_o = [o[k]], separavel([o[k]])
        # TODAS AS LINHAS DO GRUPO ENTRAM, nao so as que tem par. A que
        # nao tem par e oferta nova - chamar de indistinguivel escondia
        # o degrau novo do pre-pago da Vivo em 20/10/2026 de todos os
        # detectores de uma vez.
        for linhas, pode, indice, promovidas in (
                (lh, pode_h, h, promovidas_h),
                (lo, pode_o, o, promovidas_o)):
            if not pode:
                continue
            # a linha que veio do indice muda de chave: deixar a base
            # tambem apontando para ela daria DOIS pares a uma oferta so
            if indice.get(k) is not None and any(l is indice[k]
                                                 for l in linhas):
                del indice[k]
            for l in linhas:
                indice[_identidade(l) + (l["codigo_anatel"],)] = l
                promovidas.add(id(l))

    def sobrou(cego, promovidas):
        restantes = [l for l in ((cego or {}).get("descartadas") or ())
                     if id(l) not in promovidas]
        return _aviso_de_colisao(restantes)

    return sobrou(cego_h, promovidas_h), sobrou(cego_o, promovidas_o)


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
      duvidosa      ofertas em que o coletor recusou um campo, por motivo
      cobertura     quanto da vitrine de hoje tinha par em ontem
    """
    h, erro_h, cego_h = _indexar(hoje)
    o, erro_o, cego_o = _indexar(ontem)
    # ANTES DOS DETECTORES. O par recuperado pelo codigo de registro tem
    # de existir para todos eles - preco, composicao, grade, renomeada -,
    # senao um detector ve a oferta e o outro nao.
    cego_h, cego_o = _desempatar_por_anatel(h, cego_h, o, cego_o)
    # O PONTO CEGO DE HOJE E O DE ONTEM SAO FATOS DIFERENTES, e misturar
    # os dois num "or" fez a mensagem afirmar duas coisas falsas num dia
    # limpo: "N ofertas ficaram fora da comparacao DE HOJE" com as N de
    # ontem, e uma cobertura rebaixada por ofertas que hoje nem existem.
    #
    # O de hoje vai para a mensagem e para o denominador da cobertura,
    # porque e oferta de hoje que nao foi comparada. O de ontem aparece
    # so como nota no relatorio: o efeito dele ja esta na cobertura, do
    # jeito certo - as ofertas de hoje que perderam o par.
    cego = cego_h
    # Comparacao que falhou nao e comparacao sem novidade. Sem devolver o
    # erro, uma consulta que caiu faria o aviso afirmar "nada mudou" - pior
    # que nao avisar, porque soa como noticia verificada.
    # a ressalva da leitura sai mesmo quando a comparacao falha: ela
    # fala do dado de HOJE, e nao da comparacao com ontem
    duvidosa = _leitura_duvidosa(h)
    vazio = {"precos": [], "composicao": [], "renomeadas": [], "grades": [],
             "voltaram": [], "remodeladas": [], "leitura": [],
             "erro": None, "cego": cego, "cego_ontem": cego_o,
             "duvidosa": duvidosa, "cobertura": None}
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

    renomeadas, usadas = _renomeadas(h, o)
    renomeadas = [r for r in renomeadas
                  if (r["atual"]["operadora"], r["atual"]["produto"]) not in suprimir]
    # a leitura alternativa que _oferta_remodelada descartar e colada
    # direto no evento, por dentro de usadas (N8, V3)

    # A MESMA OFERTA MUDADA POR DENTRO. Era o ponto cego de todos os
    # detectores acima, e o pior deles, porque produzia afirmacao
    # POSITIVA de ausencia. Ver _oferta_remodelada.
    #
    # A OFERTA DE ONTEM SO PODE SER O "ANTES" DE UM EVENTO. A garantia de
    # que nenhuma oferta cai nos dois detectores valia por oferta de
    # HOJE, nao de ontem: com duas ofertas novas - uma de mesma chave e
    # outra de mesmo nome - a mesma base de R$ 100 virava dois reajustes
    # com numeros diferentes, "+60%" e "+30%", e total_mud contava dois.
    remodeladas = [r for r in _oferta_remodelada(h, o, usadas)
                   if (r["operadora"], r["produto"]) not in suprimir]

    precos, composicao = list(precos.values()), list(composicao.values())
    # O ALCANCE PRIMEIRO: a separacao abaixo usa em quantas pracas cada
    # evento valeu, e esse numero e escrito aqui.
    _assinar_alcance(h, precos, composicao, renomeadas, grades,
                     remodeladas)
    remodeladas, leitura = _separar_o_que_e_nosso(remodeladas, hoje)

    # DEGRAU QUE VOLTOU, e so quando ha ontem com que comparar. Sem o dia
    # anterior no banco, TODA entrega de hoje parece ter reaparecido: o
    # detector procura a ultima venda no historico e anuncia "100 Mbps
    # voltou por 100,00, +11% sobre os 90,00 de 18/10" sobre um degrau
    # que nunca saiu da vitrine - so falta o dia 19 no banco.
    voltaram = (_degraus_que_voltaram(
        h, o, hoje, (cego_o or {}).get("descartadas") or ()) if o else [])
    # A remodelada ja contou o movimento com o nome da oferta e os dois
    # numeros; repetir aqui seria a mesma noticia duas vezes. A chave
    # leva a PRACA e o NOME, e o conjunto e montado DEPOIS da separacao:
    # antes, uma remodelada que foi para o balde da leitura silenciava um
    # "voltou" de outra oferta, em outra praca.
    remod = {(r["operadora"], r["produto"], r["agora_entrega"], p)
             for r in remodeladas for p in (r.get("pracas") or ())}
    voltaram = [v for v in voltaram
                if not any((v["operadora"], v["produto"], v["entrega"], p)
                           in remod for p in (v.get("pracas") or ()))]

    # E A GRADE TAMBEM JA CONTOU. Medido no dado real de 13/10: o
    # reajuste de 45 GB da Claro sai como grade em 19 pracas e, em Belo
    # Horizonte - onde o degrau faltou em 12/10 -, sai de novo como
    # "voltou". A mensagem contava "3 mudancas" sobre dois fatos e
    # mostrava o mesmo +17% em duas linhas, com denominadores diferentes
    # e nada ligando uma a outra.
    #
    # A CHAVE E O MOVIMENTO, NAO A PRACA. Escrevi primeiro com praca,
    # por analogia com o dedupe de cima, e nao pegava nada: a praca e
    # exatamente o que difere entre os dois relatos. O que os identifica
    # como o mesmo fato e operadora, produto, entrega e o par de precos.
    #
    # Se o preco anterior for outro - porque em BH a ultima venda foi a
    # outro valor -, sao dois fatos diferentes e os dois saem. E o
    # dedupe de cima segue com praca, porque la ela distingue OFERTAS e
    # nao rotas do mesmo movimento.
    #
    # A grade fica e o "voltou" sai: ela e o relato mais completo dos
    # dois, porque mostra a escada inteira.
    #
    # E O MESMO VALE PARA AS MUDANCAS DE PRECO. A cadeia de dedupes tem
    # quatro pares possiveis e cobria tres; faltava preco x voltou. Pior:
    # "cobertos", acima, ESVAZIA g["precos"] justamente quando existe um
    # evento de preco para aquela entrega - entao nos casos em que o
    # movimento sai como preco o conjunto abaixo nasceria vazio e nao
    # teria o que comparar. E o 13/10, pela outra rota.
    ja_contado = {}
    for g in grades:
        for entrega, antes_p, agora_p in (g.get("precos") or ()):
            ja_contado.setdefault(
                (g["operadora"], g["produto"], entrega, antes_p, agora_p), g)
    for m in precos:
        d, a = m["atual"], m["antes"]
        ja_contado.setdefault(
            (d["operadora"], d["produto"], _entrega(d),
             a["preco_promocional"], d["preco_promocional"]), m)

    sobrou = []
    for v in voltaram:
        dono = ja_contado.get((v["operadora"], v["produto"], v["entrega"],
                               v["antes"], v["agora"]))
        if dono is None:
            sobrou.append(v)
            continue
        # A PRACA DO EVENTO DESCARTADO VAI PARA O QUE FICA. No 13/10 o
        # reajuste alcancou as 20 pracas; em Belo Horizonte a escada nao
        # era comparavel porque o degrau faltava ontem, e sem isto a
        # linha dizia "em 19 de 20" sobre um movimento nacional.
        for p in (v.get("pracas") or ()):
            if p not in dono["pracas"]:
                dono["pracas"].append(p)
    voltaram = sobrou

    # O ALCANCE DE NOVO, porque a juncao acima mexeu nas pracas de quem
    # ficou e o "onde" da primeira passada ficou velho - dizia "em 19 de
    # 20" sobre uma lista que agora tem 20. A funcao e idempotente: ela
    # recalcula universo e onde a partir de "pracas", e a primeira
    # chamada existe porque a separacao precisa do universo antes.
    _assinar_alcance(h, precos, composicao, renomeadas, grades, voltaram,
                     remodeladas, leitura, duvidosa)

    # A ORDEM E PARTE DA NOTICIA, e e decidida aqui para a mensagem e o
    # PDF nao poderem discordar. Ver _por_efeito.
    for grupo in (precos, composicao, renomeadas, grades, voltaram,
                  remodeladas, leitura):
        grupo.sort(key=_por_efeito, reverse=True)
    return {"precos": precos, "composicao": composicao,
            "renomeadas": renomeadas, "grades": grades,
            "voltaram": voltaram, "remodeladas": remodeladas,
            "leitura": leitura,
            "erro": None, "cego": cego, "cego_ontem": cego_o,
            # a recusa do coletor nao passa por _assinar_alcance nem pela
            # ordenacao: nao e evento de mercado, e ressalva sobre o dado
            "duvidosa": duvidosa,
            "cobertura": _cobertura(h, o, (cego_h or {}).get("quantas", 0))}


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
    "2026-10-21": "a identidade das ofertas com app passou a sair da "
                  "lista de apps, e não do nome — que carregava a safra "
                  "do mês e morria na virada; e o nível de bundle passou "
                  "a sair da lista de apps, e não só do texto do card",
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
    return universo > 1 and quantas * 2 < universo


# o mesmo rotulo generico do coletor: a mensagem nao pode imprimir a
# prosa longa nem quando o rotulo curto falta
SEM_ROTULO = "um campo do contrato n\u00e3o deu para ler"


def _duas_formas_do_aviso(aviso):
    """(curto, longo) de uma ressalva do coletor.

    O coletor grava um dicionario {"curto", "longo"} desde 25/10/2026:
    o curto diz O QUE ficou vazio e cabe na mensagem, o longo explica
    POR QUE e cabe no relatorio. Derivar um do outro por recorte de
    texto nao funciona - na Vivo, no Flex e no FIT a explicacao vem
    depois dos dois pontos, e na Claro vem antes.

    Aviso gravado como string vale para os dois: e o que esta nos dias
    anteriores, e historico nao se reescreve.
    """
    if isinstance(aviso, dict):
        longo = aviso.get("longo") or aviso.get("curto") or ""
        return (aviso.get("curto") or SEM_ROTULO), longo
    # ROTULO QUE FALTA DEGRADA PARA O GENERICO, nunca para o longo: a
    # mensagem nao imprime a prosa do coletor em caso nenhum.
    return SEM_ROTULO, str(aviso or "")


def _leitura_duvidosa(h):
    """As ofertas em que o coletor recusou um campo, por motivo.

    NAO E EVENTO DE MERCADO, E RESSALVA SOBRE O DADO: nada mudou na
    vitrine, o que houve foi a nossa leitura dizer "este campo eu nao
    sei". Por isso fica fora da contagem de mudancas e mora ao lado da
    cobertura, que e a outra frase sobre o que NAO foi possivel afirmar.

    AGRUPA POR OPERADORA E PRODUTO, e nao pelo texto do motivo.

    Agrupar pelo texto nao agrupa nada: ele embute os valores da oferta
    ("declara 25 GB para um card de 15 GB", "diz R$ 1200,00 de tabela,
    abaixo dos R$ 1500,00"), entao cada oferta tem motivo unico. Medido
    na coleta real de 25/10/2026, dez ofertas renderam dez grupos - uma
    parede de quase-repeticoes que esconde o que importa: sao DOIS
    problemas, nao dez.

    Cortar o texto no ":" para achar a "especie" do aviso tambem nao
    serve: na Vivo, no Flex e no FIT a explicacao vem depois dos dois
    pontos, e na Claro vem antes. Adivinhar a forma da redacao para
    agrupar e a esperteza que este projeto reprova.

    (operadora, produto) e a granularidade que o leitor usa e que nao
    depende da redacao de ninguem - e e ela que permite medir o alcance,
    porque _onde compara com o universo de (operadora, produto).

    Os motivos distintos viajam numa lista: a mensagem mostra o primeiro
    e diz quantos outros ha, e o relatorio lista todos.
    """
    grupos = {}
    for l in h.values():
        avisos = l.get("avisos_oferta")
        # o bruto pode devolver string em vez de lista quando o coletor
        # grava um aviso so: tratar como lista de um
        if isinstance(avisos, str):
            avisos = [avisos]
        avisos = [a for a in (avisos or ()) if a]
        if not avisos:
            continue
        # AS DUAS FORMAS DE CADA RESSALVA. O rotulo curto diz O QUE
        # ficou vazio e vai na mensagem; o longo explica POR QUE e vai
        # no relatorio. Aviso gravado como string - o que esta nos dias
        # anteriores - vale para os dois.
        duas = [_duas_formas_do_aviso(a) for a in avisos]
        k = (l.get("operadora"), l.get("produto"))
        d = grupos.setdefault(k, {
            "operadora": l.get("operadora"), "produto": l.get("produto"),
            "motivos": [], "curtos": [], "pracas": [], "ofertas": [],
            "quantas": 0,
            # O ROTULO EM PORTUGUES VIAJA COM O EVENTO, como em
            # bundle_antes: a mensagem e o PDF leem o mesmo texto e nao
            # podem divergir.
            "categoria": _categoria(l),
            # _rotulo e _categoria leem "atual" nos outros eventos
            "atual": l})
        # CONTA OFERTA, NAO LINHA NEM AVISO.
        #
        # Uma oferta com dois avisos e uma oferta so - contar aviso
        # inflaria o buraco. E a MESMA oferta em 20 pracas tambem e uma
        # so: todos os outros blocos da mensagem dizem "2 mudancas" para
        # duas ofertas e poem a praca em separado ("em todas as 7
        # pracas"). Este dizia "100 ofertas, em todas as 20 pracas", e
        # 100 era 5 vezes 20 - a praca contada duas vezes na mesma
        # linha. Era por isso que a ressalva parecia enorme: sao 5.
        quem = (l.get("chave"), l.get("nome_oferta"))
        if quem not in d["ofertas"]:
            d["ofertas"].append(quem)
        d["quantas"] = len(d["ofertas"])
        for curto, longo in duas:
            if longo not in d["motivos"]:
                d["motivos"].append(longo)
            if curto and curto not in d["curtos"]:
                d["curtos"].append(curto)
        if l.get("praca") and l["praca"] not in d["pracas"]:
            d["pracas"].append(l["praca"])
    for d in grupos.values():
        d["motivos"].sort()
        d["curtos"].sort()
        # o primeiro motivo serve de exemplo na mensagem; "motivo" fica
        # como apelido para quem le um por um
        d["motivo"] = d["motivos"][0]
    return sorted(grupos.values(),
                  key=lambda d: (-d["quantas"], d["operadora"] or "",
                                 d["produto"] or ""))


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
    # QUANTAS DAS QUE FALTAM SAO A MESMA OFERTA COM IDENTIDADE NOVA.
    #
    # Nao precisa de pareamento: basta existir ontem com o mesmo nome,
    # na mesma praca e pelo MESMO PRECO. E um numero exato, e e o que o
    # leitor precisa quando a cobertura cai - sem ele a mensagem mostra
    # um buraco e nao sabe dizer de que tamanho e a parte conhecida.
    #
    # Medido em 21/10/2026, primeiro dia depois de a chave passar a sair
    # da lista de apps: 732 das 765 sem par eram isto, e a mensagem
    # atribuiu 34 - as unicas que a atribuicao conseguiu parear pelo
    # nome, que em vitrine e compartilhado.
    def sem_chave(l):
        return (l["operadora"], l["produto"], l["praca"],
                " ".join((l.get("nome_oferta") or "").lower().split()),
                l.get("preco_promocional"))

    ontem_igual = {sem_chave(l) for l in o.values()}
    trocaram = sum(1 for k, l in h.items()
                   if k not in comuns and sem_chave(l) in ontem_igual)
    total = len(h) + (fora or 0)
    return {"pares": len(comuns), "hoje": total, "ontem": len(o),
            "fora": fora or 0, "trocaram_de_identidade": trocaram,
            "fracao": len(comuns) / float(total),
            "por_operadora": por_operadora}


def _por_efeito(e):
    """Quanto este evento pesa, para ordenar os eventos entre si.

    POR QUE A ORDEM IMPORTA TANTO. A mensagem mostra tres de cada tipo e
    manda o resto para o relatorio. Sem ordenar, os tres eram os
    primeiros da ordem do indice - chave.asc, que e alfabetica e nao
    quer dizer nada. Medido: com cinco reajustes de +1% a +200%, a
    mensagem saia com +1%, +2% e +3% e "e mais 2 no relatorio". A maior
    variacao do dia era justamente a que nao chegava ao canal que a
    pessoa le no telefone, e o PDF - que ordenava por tamanho - abria
    com ela. Os dois canais discordavam sobre qual era a noticia.

    O peso e a maior variacao percentual que o evento carrega, e nao a
    diferenca em reais: 10% de R$ 30 e 10% de R$ 300 sao a mesma decisao
    para quem compara operadoras, e ordenar por reais poria o combo
    sempre na frente do pre-pago.
    """
    def pc(de, para):
        if not de or para is None:
            return 0.0
        return abs(para - de) / float(de)

    # REMODELADA E LEITURA PRIMEIRO. Elas tambem carregam "antes" e
    # "atual" como dicionarios, entao caiam no ramo de baixo e o
    # max(preco, entrega) nunca rodava: a oferta que paga 5% mais e
    # recebe METADE da internet pesava 0,05 em vez de 0,50, e era a
    # unica das quatro a ficar fora da mensagem.
    if "antes_preco" in e:
        return max(pc(e.get("antes_preco"), e.get("agora_preco")),
                   pc(e.get("antes_entrega"), e.get("agora_entrega")))
    # degrau que voltou
    if "quando" in e:
        return pc(e.get("antes"), e.get("agora"))
    # preco, composicao e renomeada: o par antes/atual
    a, d = e.get("antes"), e.get("atual")
    if isinstance(a, dict) and isinstance(d, dict):
        pa, pd = a.get("preco_promocional"), d.get("preco_promocional")
        # COMPOSICAO PESA PELO QUE MUDOU DENTRO, porque nela o preco e
        # igual por definicao e todas pesariam zero - e ai os tres
        # mostrados voltariam a ser os primeiros da ordem do indice.
        #
        # E SO NELA. Este ramo e compartilhado com preco e com nome, e
        # sem a guarda do preco igual qualquer reajuste cujo sva tambem
        # mudou passava a pesar pela distancia dos servicos, de 0 a 1,
        # contra a variacao de preco, que nao tem teto: medido, +1% com
        # os servicos trocados pesava 1,000 e -50% pesava 0,500.
        #
        # O pior dia e o documentado em mudancas(): 30/09/2026, quando o
        # regulamento da Vivo falhou em 1042 de 1044 ofertas. Todo sva
        # vai para vazio, TODO evento de preco pesa 1,000 e a ordem
        # volta a ser chave.asc - o estado que _por_efeito existe para
        # eliminar, nos dois canais de uma vez, no dia em que o dado
        # esta pior.
        # "preco nao lido" tambem e composicao: o evento nasce quando o
        # ramo de preco nao disparou, e ele nao dispara com None em
        # qualquer dos lados. Sem isto esses eventos pesavam 0,000 e iam
        # para o fim do grupo nos dois canais (W3). E nao reabre o
        # vazamento do V1: evento de PRECO com None nao existe, porque a
        # guarda do A1 o impede de nascer.
        if pa == pd or pa is None or pd is None:
            sa = set((a.get("assinatura_sva") or "").split("+"))
            sd = set((d.get("assinatura_sva") or "").split("+"))
            if sa != sd and (sa or sd):
                return len(sa ^ sd) / float(max(len(sa | sd), 1))
        return pc(pa, pd)
    # grade: a maior variacao entre todos os movimentos dela
    pesos = [pc(x[1], x[2]) for x in (e.get("saltos") or ())]
    pesos += [pc(x[1], x[2]) for x in (e.get("precos") or ())]
    return max(pesos) if pesos else 0.0


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


def _parado(antes, agora):
    """Este campo NAO se moveu de um dia para o outro.

    Tres estados e nao dois, e a diferenca importa duas vezes.

    Desconhecido nos DOIS dias nao se moveu: a Brisanet veio sem
    velocidade ontem e vem sem velocidade hoje, e nada ali mudou. Exigir
    que os dois fossem conhecidos - como eu fiz primeiro - tirou a
    possibilidade de atribuir a nossa leitura justamente as operadoras
    de coletor mais fragil, que ficavam permanentemente no balde do
    mercado (V6).

    Desconhecido num dia SO se moveu: passar de "nao lido" para 500 Mbps
    e uma mudanca, e chamar isso de parado era afirmar "sem mexer na
    entrega" sobre uma entrega que mexeu (N14).
    """
    if antes is None and agora is None:
        return True
    if antes is None or agora is None:
        return False
    return antes == agora


def _oferta_remodelada(h, o, usadas=()):
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

    # O NOME SO IDENTIFICA SE FOR DE UMA OFERTA SO.
    #
    # A regra de "uma candidata de cada lado" contava as SOBRAS, e isso
    # supoe que o nome identifica a oferta - verdade em "TIM Controle"
    # virando "TIM Controle Smart", falso em "Vivo Pre", que nomeia
    # QUATRO ofertas na mesma praca.
    #
    # Em 20/10/2026 sobrou uma de cada lado por acidente: o degrau novo
    # de 25 GB sem par hoje, e o de 15 GB sem par ontem porque a linha
    # de hoje dele caiu por indistinguivel. A mensagem anunciou
    # "25,00 -> 35,00 (+40%) com 15 -> 25 GB" - dois numeros de ofertas
    # diferentes, e nenhum reajuste tinha acontecido.
    #
    # Contar no INDICE INTEIRO fecha isso: nome compartilhado nao
    # identifica, e parear por ele e chute - o mesmo erro do par
    # indistinguivel, por outra porta.
    quantas = collections.Counter()
    for indice in (h, o):
        for l in indice.values():
            quantas[pareia(l)] += 1

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
        # o nome tem de ser de uma oferta so nos dois dias somados: com
        # mais de uma, ele nao identifica e o par seria sorteio
        if quantas[k] > 2:
            continue
        atual, antes = atuais[0], anteriores[0]
        # A CHAVE DE CONTINUIDADE GANHA DO NOME, e esta e a decisao -
        # nao o acidente de _renomeadas rodar primeiro.
        #
        # Quando a oferta de ontem pode parear das duas formas, ha duas
        # leituras do mesmo fato: "mudou de nome e o preco foi de 100
        # para 130" e "voltou com outro degrau por 160". A chave existe
        # para sobreviver a renomeacao e e a identidade mais forte que o
        # projeto tem; o nome muda por decisao de marketing. Entao vale
        # a chave.
        #
        # E A LEITURA DESCARTADA NAO DESAPARECE: vai no evento, para o
        # relatorio mostrar que havia duas e qual foi usada. Escolher em
        # silencio seria o mesmo defeito do par indistinguivel - eleger
        # uma leitura por ordem de codigo e publicar como fato.
        if _identidade(antes) in (usadas or ()):
            # A LEITURA DESCARTADA VAI DIRETO NO EVENTO que a consumiu, e
            # nao numa chave que depois alguem procura pela praca
            # representante. Era o mesmo erro de representante que eu ja
            # cometi do lado da protecao: com a alternativa existindo em
            # Joinville e o representante sendo Sao Paulo, a coluna
            # "Outra leitura possivel" saia "—", que se le como "nao
            # havia outra" (V3).
            evento = (usadas or {}).get(_identidade(antes))
            if isinstance(evento, dict):
                evento.setdefault("outras_leituras", []).append({
                    "praca": atual.get("praca"),
                    "nome": atual.get("nome_oferta"),
                    "preco": atual.get("preco_promocional"),
                    "entrega": _entrega(atual)})
            continue
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
            # E O MESMO VALE PARA PRECO E ENTREGA. Eu consertei o "None"
            # e o "mesma entrega" afirmado na mensagem e deixei o PDF
            # imprimindo "None" na mesma oferta. Texto que viaja no
            # evento nao pode divergir entre os canais, que e a razao de
            # "onde" e do rotulo acima estarem aqui.
            "texto_preco": _texto_preco(pa, pd, preco_mudou),
            "texto_entrega": _texto_entrega(ea, ed, _unidade(atual),
                                            entrega_mudou),
            "preco_mudou": preco_mudou, "entrega_mudou": entrega_mudou,
            "versao_mudou": versao_mudou,
            # SO A VERSAO MUDOU: nem o preco nem a entrega se MOVERAM.
            #
            # O PRECO TEM DE TER SIDO LIDO NOS DOIS DIAS, e a entrega
            # nao. A assimetria e deliberada: entrega nao lida ontem e
            # nao lida hoje nao mudou - nada ali se moveu, e e o caso da
            # Brisanet. Preco nao lido e diferente: a operadora pode ter
            # reajustado e nos simplesmente nao vimos, e ai a frase "sem
            # mexer em preco nem entrega" afirmaria o que a linha da
            # mesma oferta nega duas abaixo, via texto_preco (W4).
            "versao_apenas": (pa is not None and pd is not None
                              and pa == pd and _parado(ea, ed)),
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


def _degraus_que_voltaram(h, o, hoje, descartadas_de_ontem=()):
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

    # DESCARTADA DE ONTEM NAO E AUSENTE DE ONTEM. _indexar tira o grupo
    # indistinguivel do indice, e sem esta linha toda oferta daquele
    # grupo parecia ter faltado ontem e "voltado" hoje. Medido na
    # transicao real de 15 para 16/10: o par "Vivo Familia 2 + TV" saiu
    # como "700 Mbps voltou por 290,00, -26% sobre os 390,00 de 15/10",
    # num dia em que nenhum preco mudou e o degrau nunca saiu da vitrine.
    ontem = {chave(l) for l in o.values() if _entrega(l) is not None}
    ontem |= {chave(l) for l in (descartadas_de_ontem or ())
              if _entrega(l) is not None}
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
        # A ULTIMA VENDA, e so quando ela nao e ambigua. A consulta le a
        # tabela crua, sem passar por _indexar, entao ela nao sabe das
        # ofertas indistinguiveis: com duas linhas do mesmo dia, mesma
        # praca, mesma entrega e mesmo nome a precos diferentes, "a
        # primeira que aparecer" e sorteio - e foi esse sorteio que
        # produziu os -26% falsos do par "Vivo Familia 2 + TV".
        #
        # Dia ambiguo nao serve de referencia: nao da para dizer por
        # quanto a operadora vendia aquele degrau naquele dia.
        candidatas = [x for x in cache[(operadora, produto)]
                      if x.get("praca") == k[2] and _entrega(x) == k[3]
                      and (x.get("nome_oferta") or "").lower() == k[4]
                      and x.get("preco_promocional") is not None]
        # SO O DIA MAIS RECENTE INTERESSA, e a consulta vem ordenada dele
        # para tras. Isto era um laco com break nos dois ramos, o que
        # engana quem for mexer: nunca iterava (V8).
        antes = None
        if candidatas:
            recente = candidatas[0]
            do_dia = {y["preco_promocional"] for y in candidatas
                      if y.get("data_captura") == recente.get("data_captura")}
            # dia ambiguo nao serve de referencia: nao da para dizer por
            # quanto a operadora vendia aquele degrau naquele dia
            if len(do_dia) == 1:
                antes = recente
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

    DEVOLVE TAMBEM AS IDENTIDADES DE ONTEM QUE CONSUMIU, num dicionario
    que _oferta_remodelada preenche com as leituras que teve de
    descartar. A oferta de ontem so pode ser o "antes" de UM evento, e
    sem esta lista _oferta_remodelada reusava a mesma base: hoje com
    duas ofertas novas, uma de mesma chave e outra de mesmo nome,
    produzia dois reajustes sobre os mesmos R$ 100. Nao da para
    reconstruir a lista de fora - _agrupar guarda um "antes" por grupo,
    e as outras 19 pracas ficariam desprotegidas.
    """
    sobra_h = collections.defaultdict(list)
    sobra_o = collections.defaultdict(list)
    for k, l in h.items():
        if k not in o:
            sobra_h[(l["chave"], l["praca"])].append(l)
    for k, l in o.items():
        if k not in h:
            sobra_o[(l["chave"], l["praca"])].append(l)

    achados, usadas = {}, {}
    for cp, atuais in sobra_h.items():
        anteriores = sobra_o.get(cp)
        if not anteriores or len(atuais) != 1 or len(anteriores) != 1:
            continue
        atual, antes = atuais[0], anteriores[0]
        ident = (atual["operadora"], atual["chave"],
                 antes["nome_oferta"], atual["nome_oferta"],
                 antes["preco_promocional"], atual["preco_promocional"])
        _agrupar(achados, ident, atual, antes)
        # a identidade de ontem aponta para o EVENTO, em todas as pracas:
        # assim a leitura descartada chega ao evento certo, venha de
        # qualquer uma delas
        usadas[_identidade(antes)] = achados[ident]
    return list(achados.values()), usadas


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


def _texto_preco(antes, agora, mudou):
    """Como o preco desta oferta aparece nas duas telas.

    Tres estados, e eles nao se confundem: mudou (com a variacao),
    ficou igual (com o valor), ou nao foi lido em um dos dias - e este
    ultimo nunca pode sair como os outros dois.
    """
    if antes is None or agora is None:
        return "pre\u00e7o n\u00e3o lido nos dois dias"
    if mudou:
        return "%s \u2192 %s%s" % (_reais(antes), _reais(agora),
                                _pct(antes, agora))
    return "mesmo pre\u00e7o (%s)" % _reais(agora)


def _texto_entrega(antes, agora, unidade, mudou):
    """Como a entrega desta oferta aparece nas duas telas."""
    if antes is None or agora is None:
        return "entrega n\u00e3o lida"
    u = unidade or ""
    if mudou:
        return "%s \u2192 %s%s" % (antes, ("%s %s" % (agora, u)).strip(),
                                _pct(antes, agora))
    return "mesma entrega (%s)" % ("%s %s" % (agora, u)).strip()


def _mesmo_preco(r):
    """O preco de uma oferta que NAO mudou de preco, ou que nao foi lido.

    AFIRMAR IGUALDADE EXIGE OS DOIS LADOS. preco_mudou e False quando
    qualquer um deles e None - a guarda certa para nao inventar reajuste -
    e quem le o else nao pode concluir "nao mudou" disso. Nao mudou e nao
    se sabe sao estados diferentes, e a diferenca entre os dois e todo o
    valor deste projeto.

    Chama _texto_preco para nao haver duas implementacoes da mesma
    frase: foi com duas que o "None" saiu da mensagem e apareceu no PDF.
    """
    return _texto_preco(r.get("antes_preco"), r.get("agora_preco"), False)


def _mesma_entrega(r, u):
    """A entrega de uma oferta que NAO mudou de entrega, ou nao lida.

    Mesmo principio de _mesmo_preco. A Brisanet veio 119 linhas por dia
    sem velocidade em 18 dos 21 dias coletados, e uma delas mudando de
    versao imprimia "pela mesma entrega (None )" - o token cru do Python
    e, pior, a afirmacao de igualdade sobre um campo que nao foi lido em
    nenhum dos dois dias.
    """
    return _texto_entrega(r.get("antes_entrega"), r.get("agora_entrega"),
                          u, False)


def _agrupar_remodeladas(remodeladas):
    """Ofertas que sofreram o MESMO evento saem juntas.

    As tres Claro Flex de 23/10/2026 tinham a mesma transicao de bundle,
    na mesma praca, sem mexer em preco nem entrega - e cada uma ganhou
    um bloco de quatro linhas repetindo as mesmas palavras.

    SO AGRUPA QUANDO NAO HA NUMERO A PERDER. Com preco ou entrega
    diferentes entre as ofertas, cada uma volta a ter seu bloco: ali o
    numero e a noticia, e juntar esconderia de qual oferta ele e.
    """
    grupos, ordem = {}, []
    for r in remodeladas or ():
        sozinha = r.get("preco_mudou") or r.get("entrega_mudou")
        k = (id(r) if sozinha else
             (r.get("operadora"), r.get("produto"), r.get("antes_bundle"),
              r.get("agora_bundle"), bool(r.get("versao_mudou")),
              r.get("onde")))
        if k not in grupos:
            grupos[k] = []
            ordem.append(k)
        grupos[k].append(r)
    return [grupos[k] for k in ordem]


def _nomes_juntos(grupo):
    """"Claro Flex 40, 45 e 50 GB" a partir dos tres nomes.

    Reduz pelo prefixo e sufixo comuns, que e como a operadora batiza a
    serie: o que varia entre as ofertas e o degrau, e so ele precisa
    aparecer tres vezes. Sem parte comum util, lista os nomes inteiros -
    inventar um nome de serie seria pior que repetir.
    """
    nomes = []
    for r in grupo:
        n = _rotulo(r["atual"])
        if n not in nomes:
            nomes.append(n)
    if len(nomes) == 1:
        return nomes[0]

    def junta(partes):
        return "%s e %s" % (", ".join(partes[:-1]), partes[-1])

    # PREFIXO E SUFIXO SO EM PALAVRA INTEIRA. Sem isto o corte cai no
    # meio: "Claro Controle" e "Claro Flex Passaporte" terminam as duas
    # em "e", o sufixo comum virou "e" e a reducao imprimiu "Claro
    # Control e Flex Passaport" + "e". Texto remendado desse jeito chega
    # ao Telegram sem ninguem perceber.
    ini = os.path.commonprefix(nomes)
    ini = ini[:ini.rfind(" ") + 1]
    fim = os.path.commonprefix([n[::-1] for n in nomes])[::-1]
    corte = fim.find(" ")
    fim = fim[corte:] if corte >= 0 else ""
    meios = [n[len(ini):len(n) - len(fim)] for n in nomes]
    # prefixo curto, ou miolo vazio, ou miolo longo: a reducao nao
    # ajudaria e pode confundir
    if (len(ini) >= 4 and all(0 < len(m) <= 18 for m in meios)
            and len(set(meios)) == len(meios)):
        return "%s%s%s" % (ini, junta(meios), fim)
    return junta(nomes)


def _o_que_mudou(r, sem_numero=False):
    """As linhas que descrevem uma oferta remodelada, em portugues.

    Com sem_numero, a primeira linha nao cita preco nem entrega: e o
    caso do bloco que fala de VARIAS ofertas, em que o numero de uma
    nao vale para as outras. So e usado no grupo, que por construcao
    reune ofertas em que nem preco nem entrega se mexeram.

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
        entrega = _mesma_entrega(r, u)
        linhas.append("%s \u2192 %s%s   %s" % (
            _reais(r["antes_preco"]), _reais(r["agora_preco"]),
            _pct(r["antes_preco"], r["agora_preco"]),
            entrega if entrega.startswith("entrega") else "pela " + entrega))
    elif r["entrega_mudou"]:
        preco = _mesmo_preco(r)
        linhas.append("%s \u2192 %s %s%s   %s" % (
            r["antes_entrega"], r["agora_entrega"], u,
            _pct(r["antes_entrega"], r["agora_entrega"]),
            preco if preco.startswith("pre\u00e7o") else "pelo " + preco))
    elif sem_numero:
        linhas.append("sem mexer em pre\u00e7o nem entrega")
    else:
        linhas.append("%s e %s" % (_mesmo_preco(r), _mesma_entrega(r, u)))

    ba, bd = r.get("antes_bundle"), r.get("agora_bundle")
    de, para = _bundle(ba), _bundle(bd)
    if de and para and de != para:
        # A VITRINE QUE CALA NAO DIZ QUE A OFERTA PERDEU O APP. Nivel 0 e
        # "nada nomeado", entao toda transicao de ou para zero e uma
        # mudanca no que a vitrine DIZ - nunca prova do que a oferta tem.
        #
        # Medido em 23/10/2026: a Claro reescreveu o flex.claro.com.br e
        # a pagina inteira deixou de conter "Skeelo", "Claro Musica",
        # "Claro Banca", "Claro Day" e "McAfee". A mensagem anunciou
        # "passou de com apps de catalogo para sem assinatura inclusa"
        # em tres ofertas - afirmacao sobre o mercado tirada do silencio
        # da vitrine, o oposto do que a metodologia manda: "um card que
        # nao escreve Gemini nao esta dizendo que Gemini ficou fora -
        # esta calado. Silencio nao e ausencia".
        #
        # Transicao entre dois niveis nao-zero fica como estava: ali a
        # vitrine declara os dois lados e a recomposicao e real.
        if bd == 0:
            linhas.append("e a vitrine parou de nomear os apps que "
                          "listava (\"%s\") \u2014 sil\u00eancio n\u00e3o confirma "
                          "que sa\u00edram" % de)
        elif ba == 0:
            linhas.append("e a vitrine passou a nomear \"%s\", que antes "
                          "n\u00e3o aparecia" % para)
        else:
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


def _porque_falhou(c):
    """Por que a rodada deste coletor nao fechou, em uma frase curta.

    PRACA FALTANDO E UM MOTIVO, nao o unico. A manchete usava sempre
    pracas_ok, e coletor que leu as 20 e nao conseguiu GRAVAR saia como
    "Vivo em 20 de 20 pracas" - uma frase de sucesso explicando uma
    falha. O motivo esta em "avisos", que e onde o coletor o escreve.
    """
    op = c.get("operadora")
    ok = c.get("pracas_ok") or 0
    pedidas = c.get("pracas_pedidas") or 0
    if pedidas and ok < pedidas:
        return "%s em %d de %d pra\u00e7as" % (op, ok, pedidas)
    if c.get("avisos"):
        return "%s (%s)" % (op, str(c["avisos"][0])[:52])
    if not c.get("ofertas"):
        return "%s sem oferta nenhuma" % op
    return "%s com aviso na rodada" % op


def _tamanho_da_serie():
    """Quantas linhas a serie tem, ou None - e NUNCA levanta.

    Numero de rodape nao pode derrubar a mensagem do dia. A primeira
    versao disto chamava armazenamento.contar() direto na montagem do
    dicionario, e qualquer tropeco ali - segredo ausente, rede fora -
    levava junto a mensagem inteira, que e a unica coisa que o robo
    precisa entregar.
    """
    try:
        return armazenamento.contar()[0]
    except Exception:
        return None


def montar_mensagem(hoje, ontem):
    """O recado do dia: o mercado primeiro, o robo so quando falha."""
    dia = datetime.fromisoformat(hoje).strftime("%d/%m")
    r = mudancas(hoje, ontem)
    mud, comp, renom = r["precos"], r["composicao"], r["renomeadas"]
    grades, voltaram, remodeladas = r["grades"], r["voltaram"], r["remodeladas"]
    duvidosa = r.get("duvidosa") or []
    erro_cmp, ponto_cego, cobertura = r["erro"], r["cego"], r["cobertura"]
    leitura = r.get("leitura") or []

    # O ESTADO DA COLETA, QUE PODE VIRAR MANCHETE - e o erro dela, que
    # tambem pode. Este retorno era descartado num `_`, e `col` vazio
    # significava "nao rodou": um 503 so nesta consulta fazia a mensagem
    # afirmar "O ROBO NAO RODOU HOJE" num dia em que ele rodou e gravou
    # tudo. "Nao sei se rodou" e "nao rodou" sao estados diferentes.
    #
    # "avisos" entra no select porque e onde mora o MOTIVO da falha. Sem
    # ele a manchete tinha de inventar um: usava pracas_ok, e coletor que
    # leu as 20 pracas e nao conseguiu gravar saia como "em 20 de 20
    # pracas" - frase de sucesso explicando uma falha.
    col, erro_col = armazenamento.consultar(
        "coletas?data_captura=eq.%s&select=operadora,pracas_ok,pracas_pedidas,"
        "ofertas,sucesso,avisos,iniciada_em&order=iniciada_em.desc" % hoje)
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
    if erro_col:
        # NAO SEI NAO E NAO RODOU. A comparacao abaixo vale: ela sai das
        # capturas, que responderam.
        linhas += ["", "N\u00e3o deu para ler o estado da coleta: %s"
                   % str(erro_col)[:80],
                   "O que vem abaixo vale; s\u00f3 n\u00e3o d\u00e1 para dizer se a "
                   "coleta do dia fechou."]
    elif not col:
        linhas += ["", "O ROB\u00d4 N\u00c3O RODOU HOJE.",
                   "Nenhum registro de coleta. Nada do que vem abaixo \u00e9 de hoje."]
    elif falhas or sem_registro:
        # a falha e manchete e cabe em duas linhas: o detalhe por coletor
        # esta na tabela "Estado da coleta" do relatorio anexo
        quem = [_porque_falhou(c) for c in falhas]
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
    if not erro_cmp and (col or erro_col):
        linhas.append("")
        if cobertura is None:
            # ZERO OFERTAS NAO E ZERO MUDANCAS. Acontece quando a
            # gravacao falha em todos os coletores: "coletas" tem linha
            # para cada um e "capturas" fica vazia. A guarda de cobertura
            # abaixo nao pega, porque este caso extremo volta None e nao 0.
            #
            # E INDICE VAZIO NAO E BANCO VAZIO. Se as capturas existem e
            # TODAS colidiram, "nenhuma oferta foi capturada" e falso - e
            # a linha do ponto cego, duas abaixo, desmentia. O numero
            # para separar os dois estados ja esta em ponto_cego (N5).
            fora = (ponto_cego or {}).get("quantas") or 0
            if fora:
                linhas.append("Nenhuma oferta comparável hoje: as %d "
                              "capturas do dia são indistinguíveis entre "
                              "si." % fora)
            else:
                linhas.append("Nenhuma oferta foi capturada hoje: n\u00e3o h\u00e1 o "
                              "que comparar.")
        elif not total_mud:
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
            # QUANDO A CAUSA E CONHECIDA, A FRASE DIZ A CAUSA. Sem isto a
            # mensagem mostrava um buraco de 48% como duvida sobre o
            # dado, no dia em que o buraco era inteiramente nosso e
            # estava declarado tres linhas abaixo.
            trocaram = (cobertura or {}).get("trocaram_de_identidade") or 0
            declarado = LEITURA_MUDOU_EM.get(hoje)
            if trocaram and declarado:
                linhas += ["", "A compara\u00e7\u00e3o alcan\u00e7ou %d%% das ofertas de "
                           "hoje, e %d das que faltam s\u00e3o a mesma oferta com "
                           "identidade nova \u2014 mesmo nome, mesma pra\u00e7a e "
                           "mesmo pre\u00e7o. A leitura mudou hoje: %s."
                           % (round(cobertura["fracao"] * 100), trocaram,
                              declarado)]
            elif trocaram:
                linhas += ["", "A compara\u00e7\u00e3o alcan\u00e7ou s\u00f3 %d%% das ofertas "
                           "de hoje. %d das que faltam s\u00e3o a mesma oferta "
                           "com identidade nova; o resto n\u00e3o d\u00e1 para "
                           "explicar daqui."
                           % (round(cobertura["fracao"] * 100), trocaram)]
            else:
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
    if ponto_cego and (col or erro_col):
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
        # O PRECO SAI DE _texto_preco, como no caminho das remodeladas.
        # "mesmo preco" estava escrito na mao aqui, e o evento de
        # composicao nasce exatamente quando o ramo de preco NAO
        # disparou - o que inclui o caso de um dos lados ser None. A
        # frase afirmava igualdade sobre um preco que nao foi lido.
        linhas.append("  %s, %s   %s"
                      % (_texto_preco(m["antes"].get("preco_promocional"),
                                      d.get("preco_promocional"), False),
                         _trocou(saiu, entrou), m["onde"]))
    if len(comp) > 3:
        linhas += ["", "e mais %d de composi\u00e7\u00e3o no relat\u00f3rio"
                   % (len(comp) - 3)]

    # PRECO E ENTREGA JUNTOS. Vem logo depois das mudancas de preco por
    # ser o movimento de maior efeito sobre o cliente - paga mais e
    # recebe menos - e porque era o unico que a mensagem NEGAVA em vez
    # de omitir. Os dois numeros aparecem com a variacao de cada um,
    # para a conta ficar a vista.
    # O MESMO EVENTO EM VARIAS OFERTAS SAI NUMA LINHA, nao num bloco
    # cada. Em 23/10/2026 as tres Claro Flex mudaram juntas e a mensagem
    # gastou doze linhas repetindo as mesmas palavras - enquanto a
    # mudanca de preco, que agrupa por praca, diz "em todas as 20
    # pracas" numa linha so.
    juntas = _agrupar_remodeladas(remodeladas)
    for g in juntas[:3]:
        linhas += ["", "%s \u00b7 %s" % (_categoria(g[0]["atual"]),
                                      _nomes_juntos(g))]
        # O NUMERO DE UMA OFERTA NAO VALE PARA O GRUPO. As quatro Claro
        # Flex de 23/10/2026 custam R$ 44,90, R$ 59,90, R$ 69,90 e
        # R$ 119,90; imprimir "mesmo preco (44,90)" sob um cabecalho que
        # fala das quatro afirma para todas o que vale para uma - o
        # mesmo defeito de eleger um representante do grupo e publicar
        # como fato.
        #
        # O grupo so se forma quando preco e entrega nao se mexeram em
        # NENHUMA delas, entao a frase sem numero e verdade para todas,
        # e e o que o leitor precisa saber. Oferta sozinha segue com os
        # numeros dela.
        linhas += ["  %s" % x for x in _o_que_mudou(
            g[0], sem_numero=len(g) > 1)]
        linhas.append("  %s" % g[0]["onde"])
    if len(juntas) > 3:
        n = sum(len(g) for g in juntas[3:])
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
        # A GRADE CORTAVA SEM DIZER. "e mais N de grade no relatorio"
        # conta EVENTOS, e nem imprime com tres ou menos: uma escada de
        # nove movimentos saia com seis, sem marca de corte.
        sobra = max(0, len(g["saltos"]) - 3) + max(0, len(g["precos"]) - 3)
        if sobra:
            linhas.append("  e mais %d movimento%s nesta grade, no "
                          "relat\u00f3rio" % (sobra, "" if sobra == 1 else "s"))
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

        linhas += ["", "%s \u00b7 %s" % (_categoria(v), v["operadora"])]
        # O PERCENTUAL SAI DE _pct, como todos os outros. Calculado aqui
        # com "if v["antes"] else 0", um preco anterior de 0,00 fazia a
        # mensagem imprimir "+0% sobre os 0,00" enquanto o PDF imprimia
        # "—" para o mesmo evento - ultimo numero que os dois canais
        # calculavam em dois lugares (W5).
        linhas.append("  %s %s voltou por %s  %s sobre os %s de %s"
                      % (v["entrega"], unidade, _reais(v["agora"]),
                         _pct(v["antes"], v["agora"]) or "(sem variação apurada)",
                         _reais(v["antes"]), quando))
        linhas.append("  %s" % v["onde"])
    if len(voltaram) > 3:
        linhas += ["", "e mais %d degrau(s) que voltaram, no relat\u00f3rio"
                   % (len(voltaram) - 3)]

    for m in renom[:3]:
        a, d = m["antes"], m["atual"]
        de, para = a["preco_promocional"], d["preco_promocional"]
        # O PRODUTO ABRE A LINHA, como nos outros cinco blocos. Este
        # abria com a operadora, e quem lia "-7% na Brisanet" nao sabia
        # se foi na fibra, no combo ou no movel - e ela vende os tres.
        linhas += ["", "%s \u00b7 %s \u00b7 mudou de nome"
                   % (_categoria(d), d["operadora"])]
        linhas.append("  %s \u2192 %s" % (a["nome_oferta"] or "?", d["nome_oferta"] or "?"))
        # TRES ESTADOS, e o else recolhia dois deles: "igual" e "nao
        # lido" saiam os dois como "pelo mesmo preco (-)" - a afirmacao
        # de igualdade mais o travessao onde devia estar o numero.
        if de is not None and para is not None and de != para:
            linhas.append("  e o pre\u00e7o foi de %s para %s%s"
                          % (_reais(de), _reais(para), _variacao(de, para)))
        else:
            linhas.append("  %s" % _texto_preco(de, para, False))
        # A PRACA, COMO EM TODOS OS OUTROS BLOCOS. Este era o unico dos
        # seis sem ela: em 24/10/2026 a mensagem anunciou dois
        # reajustes da Brisanet, de -7% e -6%, sem dizer se foram numa
        # das nove pracas do Nordeste ou nas nove. O evento ja trazia o
        # campo - _assinar_alcance o escreve para renomeadas tambem, e o
        # PDF o imprimia -, so a mensagem nao lia.
        linhas.append("  %s" % m["onde"])
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
        # o motivo ja saiu na linha da cobertura quando ela falou: aqui
        # basta apontar, senao a mesma explicacao aparece duas vezes
        ja_disse = bool(cobertura
                        and cobertura["fracao"] < COBERTURA_MINIMA
                        and (cobertura.get("trocaram_de_identidade") or 0)
                        and declarado)
        porque = ("pela mesma mudan\u00e7a de leitura" if ja_disse
                  else "a leitura mudou hoje: %s" % declarado if declarado
                  else "isso costuma ser mudan\u00e7a na nossa leitura, e "
                       "n\u00e3o no mercado")
        linhas += ["", "%d oferta%s %s de vers\u00e3o sem mexer em "
                   "pre\u00e7o nem entrega (%s) \u2014 %s. Detalhe no "
                   "relat\u00f3rio."
                   % (n, "" if n == 1 else "s",
                      "mudou" if n == 1 else "mudaram", ", ".join(ops),
                      porque)]

    # O QUE O COLETOR RECUSOU LER. Mesma familia da cobertura e da linha
    # de leitura: as tres dizem o que NAO foi possivel afirmar, e por
    # isso ficam juntas no fim e fora da contagem de mudancas - nada
    # mudou na vitrine, foi a nossa leitura que disse "este campo eu nao
    # sei".
    #
    # O CANAL EXISTIA E NAO TINHA LEITOR. Quatro coletores escrevem
    # avisos_oferta em sete lugares - regulamento de outra oferta, card
    # sem composicao reconhecida, total anual que nao fecha - e o campo
    # nunca saiu do bruto. O numero errado nao era gravado, e o buraco
    # nao era anunciado: "falha vira buraco, nao vira numero" cumprido
    # pela metade.
    # UMA LINHA, E O MOTIVO E DO RELATORIO. A primeira versao despejou
    # aqui o texto de avisos_oferta, que e prosa de DEPURACAO - escrita
    # para quem fosse ler o banco - e a mensagem de 25/10/2026 saiu com
    # quinze linhas de justificativa tecnica num aviso de celular.
    #
    # O ponto cego ja tinha a divisao certa, e eu nao a apliquei: "a
    # frase longa e a do relatorio, onde ha espaco para explicar; a
    # curta ja foi na mensagem".
    #
    # E SEM PRACA, de proposito: a regra de "toda mudanca diz em que
    # praca" e sobre MUDANCA, e aqui nada se moveu na vitrine. A
    # cobertura e o ponto cego, da mesma familia, tambem nao a carregam.
    # A FALHA DE LEITURA NAO VAI PARA A MENSAGEM - decisao do usuario
    # em 26/10/2026, e a medicao explica por que ela se justifica: as
    # ressalvas da Vivo e da Claro sao AS MESMAS todo dia. Quatro
    # codigos Anatel que a operadora repete em cards de precos
    # diferentes, mais o HTTP 422 do endpoint da agencia; dez ofertas
    # em Sao Paulo, vezes vinte pracas. Aviso que se repete identico
    # todo dia deixa de ser aviso: ensina o leitor a pular a secao, e
    # o dia em que aparecer uma falha NOVA ele pula tambem.
    #
    # O buraco continua registrado - no RELATORIO, com o texto longo e
    # a conta por operadora e praca. O grupo "duvidosa" segue
    # calculado e segue viajando em dados, porque e o PDF que o
    # consome: nada foi apagado do levantamento, so deixou de ir para
    # o celular.
    #
    # NAO CONFUNDIR COM "COLETA INCOMPLETA", que fica: aquela e alarme
    # de robo quebrado, e sem ela ninguem sabe que o dia nao foi
    # coletado.

    # O AVISO DE RODADA BEM-SUCEDIDA TAMBEM NAO VAI PARA A MENSAGEM,
    # pela mesma decisao de 26/10/2026 e pelo mesmo motivo: ele
    # repete identico todo dia. Continua no relatorio, listado por
    # coletor, logo abaixo da tabela "Estado da coleta".
    #
    # A manchete "COLETA INCOMPLETA" nao e afetada: ela olha quem NAO
    # fechou, e e o alarme de que o dia nao foi coletado.

    # A COLETA FORA DA JANELA SAI DITA. A guarda libera a coleta depois
    # das 10h "de qualquer jeito", porque dia sem dado nao volta - e isso
    # continua certo. So que o gatilho marcado para 22:34 BRT, chegando
    # no horario, cai nessa regra: a coleta roda a noite e a mensagem sai
    # perto da meia-noite. Quem recebe precisa saber que aquele dado e de
    # outra hora do dia, porque vitrine muda ao longo do dia.
    # LINHA SEM HORA NAO APAGA O AVISO. Com sorted() sobre "" uma unica
    # linha de iniciada_em nulo ordenava primeiro, falhava o teste de
    # tamanho e o aviso inteiro desaparecia - ausencia virando silencio,
    # que e o padrao que este projeto persegue (N9).
    #
    # E A JANELA E A DA GUARDA. Havia duas definicoes de "janela da
    # manha" em dois arquivos: 05:00-11:59 aqui e 6h-10h em
    # ja_coletou.py, entao coleta das 11:50 - alcancavel, porque depois
    # das 10h qualquer gatilho libera - nao recebia a ressalva (N10).
    # A HORA VEM EM UTC E TEM DE SER CONVERTIDA. iniciada_em e
    # timestamptz: o Postgres normaliza para UTC e o PostgREST devolve
    # assim. Cortando a string, a mensagem dizia "comecou as 18:56"
    # sobre uma coleta das 15:56 - e pior, num dia normal uma coleta as
    # 07:30 BRT viraria 10:30 na leitura e o aviso de "fora da janela"
    # sairia todo dia.
    inicios = []
    for c in (col or []):
        bruto = c.get("iniciada_em")
        if not bruto:
            continue
        try:
            t = datetime.fromisoformat(str(bruto).replace("Z", "+00:00"))
        except ValueError:
            continue
        inicios.append((t.astimezone(BRT) if t.tzinfo else t).strftime("%H:%M"))
    hora = min(inicios) if inicios else ""
    # IMPORT LOCAL DE PROPOSITO: ja_coletou._esperadas() importa robo
    # para nao guardar uma copia da lista de coletores, entao os dois se
    # importam. Funciona porque nenhum dos dois usa o outro em tempo de
    # import - e no nivel do modulo isso quebraria a coleta e o portao
    # juntos (V7).
    import ja_coletou
    janela = (ja_coletou.ABERTURA.strftime("%H:%M"),
              ja_coletou.LIMITE.strftime("%H:%M"))
    if hora and not (janela[0] <= hora <= janela[1]):
        linhas += ["", "A coleta de hoje come\u00e7ou \u00e0s %s, fora da janela "
                   "de %s a %s \u2014 os pre\u00e7os s\u00e3o os daquela hora."
                   % (hora, janela[0], janela[1])]

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
        # GRAVE, e nao atencao: resumo so leva graves a mensagem, e a
        # mensagem saia sem uma palavra sobre a conferencia do dado nao
        # ter acontecido. Se o PDF tambem falhasse, o fato desaparecia.
        denuncias = [("grave", "n\u00e3o deu para conferir o dado de hoje: %s"
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
        # a recusa do coletor: a frase curta foi na mensagem, a conta
        # inteira por operadora e praca e do relatorio
        "duvidosa": duvidosa,
        "erro_comparacao": erro_cmp, "cobertura": cobertura,
        # O ERRO DA CONSULTA DE COLETAS VAI PARA O PDF TAMBEM. Sem ele,
        # a mensagem dizia "nao deu para ler o estado da coleta" e o
        # relatorio, no mesmo dia, listava as nove operadoras como "Sem
        # registro" - que e uma afirmacao, e falsa (N3).
        "erro_coleta": erro_col,
        # a frase longa e a do relatorio, onde ha espaco para explicar
        # o que "chave de serie" quer dizer; a curta ja foi na mensagem
        "ponto_cego": ponto_cego["longo"] if ponto_cego else None,
        # o de ONTEM e nota do relatorio e nada mais: o efeito dele na
        # comparacao de hoje ja esta na cobertura, do jeito certo
        "ponto_cego_ontem": ((r.get("cego_ontem") or {}).get("longo")
                             if r.get("cego_ontem") else None),
        "coletas": col, "falhas": falhas, "sem_registro": sem_registro,
        "denuncias": denuncias,
        "total_ofertas": total_ofertas,
        # O TAMANHO DA SERIE, para o relatorio. A metodologia listava
        # "arquivamento do historico" como pendencia desde 01/10/2026
        # com a instrucao certa - "decidir antes de encher, nao depois" -
        # e uma estimativa no lugar de um numero. Estimativa nao vence
        # prazo: no dia em que os 500 MB do plano gratuito acabarem, a
        # gravacao falha e o dia se perde, como o de hoje quase se
        # perdeu por uma cota de outro servico.
        #
        # Custa uma requisicao por dia, sem trazer linha nenhuma.
        "linhas_no_banco": _tamanho_da_serie(),
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
    # O CORTE E NO MEIO, e nao no fim. O fim e onde moram o link do
    # painel e a linha "Conferir" do vigia - e o dia que passa de 4096
    # caracteres e justamente o dia em que ha denuncia grave, entao
    # cortar o fim jogava fora a informacao de maior consequencia.
    nota = ("\n\n[trecho do meio cortado; o relat\u00f3rio em anexo "
            "est\u00e1 completo]\n")
    fim = texto[-420:]
    inicio = texto[:TETO_TELEGRAM - len(nota) - len(fim)]
    return inicio.rstrip() + nota + fim.lstrip("\n")


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
    # Para depurar um coletor: poe as nove operadoras numa raia so, o que
    # devolve a coleta em serie e o log sem raia nenhuma escrevendo por
    # cima. Custa os 46 minutos de antes, entao nao e para a rodada
    # diaria - e para quem esta olhando.
    ap.add_argument("--em-serie", action="store_true",
                    help="coleta uma operadora por vez, como antes das raias")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not (a.coletar or a.avisar):
        ap.error("escolha --coletar ou --avisar")
    if a.coletar:
        _, falhas = rodar_coleta(a.praca, a.simular,
                                 (tuple(COLETORES),) if a.em_serie else RAIAS)
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
