# -*- coding: utf-8 -*-
u"""Ensaio da coleta: a MESMA pagina, lida por dois leitores.

POR QUE EXISTE. Em 04/11/2026 uma regra de leitura subiu as 07:09 e a
coleta das 09:00 foi a primeira a exerce-la. A TIM nomeia o app no nome
do arquivo do icone - "/sites/default/files/2026-07/Paramount+ Icon
(1).png" - e a barra do caminho foi lida como o "/" de "Google One /
iCloud+": o Paramount da Ultracombo 6 e o Aya Books da 7 sairam da
lista nas 20 pracas. 40 registros, calados, e a mensagem do dia
atribuiu as quatro ofertas a uma mudanca de leitura declarada, com a
causa certa e o efeito errado.

NADA DISSO ERA INVISIVEL ANTES DO PUSH. A suite prova que a mudanca faz
o que eu quis; a bancada reproduz a MENSAGEM sobre linhas ja gravadas e
nunca rele uma pagina. Entao o primeiro exercicio real do leitor novo
era a mensagem publicada - e e' esse o portao que falta, nao mais um
teste.

COMO FUNCIONA. Em tres passos, e o terceiro e' o que decide:

  1. busca as paginas vivas UMA vez e guarda o corpo de cada resposta;
  2. le o MESMO corpo com os coletores de duas arvores - a do trabalho
     e a de referencia (origin/main por padrao);
  3. compara oferta por oferta. Campo que tinha valor e ficou vazio e'
     PERDA, e perda barra o push. Campo que mudou de valor e' TROCA, e
     tambem barra: a mesma pagina nao muda de preco sozinha.

A MESMA PAGINA PARA OS DOIS LADOS, e nao duas coletas. Coletar duas
vezes mede a vitrine mexendo no meio do caminho junto com a nossa
leitura, e as duas causas saem somadas e indistinguiveis - o defeito
que este projeto passa o dia separando.

Uso:
    python ferramentas/ensaio_da_coleta.py                  # o ensaio
    python ferramentas/ensaio_da_coleta.py --referencia HEAD~1
    python ferramentas/ensaio_da_coleta.py --pracas "Sao Paulo/SP"
    python ferramentas/ensaio_da_coleta.py --gravar .ensaio
    python ferramentas/ensaio_da_coleta.py --reler .ensaio --leitor DIR
    python ferramentas/ensaio_da_coleta.py --comparar a.json b.json
"""
import argparse
import base64
import collections
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# COMO CADA COLETOR BUSCA. Cinco formas diferentes, e nenhuma e
# opcional: coletor que o ensaio nao sabe interceptar fica FORA do
# ensaio, e isso sai DITO. "Nenhuma diferenca" sobre coletor que nao foi
# lido e o jeito de falhar que este projeto mais guarda.
TORNEIRAS = (("vivo", "buscar"), ("tim", "buscar"), ("claro", "buscar"),
             ("brisanet", "_http"), ("starlink", "_http"),
             ("tim_fit", "_buscar"), ("unifique", "buscar"),
             # O REGULAMENTO DA ANATEL NAO PASSA POR buscar: ele abre o
             # ZIP com o opener direto (vivo.py, "with op.open"). Sem
             # esta linha a releitura baixava os ~25 documentos de novo,
             # e a assinatura SVA dos dois lados podia sair de downloads
             # diferentes - duas coletas, que e justamente o que este
             # ensaio nao faz. A torneira dele e a FUNCAO: ela devolve
             # um dicionario pequeno, e e ele que vale guardar.
             ("vivo", "regulamento"))

# Os dois de navegador: a torneira nao e HTTP, e o texto que o
# Playwright renderiza. A pagina e passada de fora - por isso coletar()
# aceita "pagina=None" - e aqui ela vai embrulhada para gravar o texto.
NAVEGADOR = ("nucel", "claro_flex")

# AS PRACAS DO ENSAIO. Tres, e nao uma: a Brisanet nao vende em Sao
# Paulo e a Unifique so no Sul, entao praca unica deixaria dois
# coletores sem exercicio nenhum. Os quatro nacionais (NuCel, Starlink,
# Claro Flex, TIM FIT) rodam uma vez, porque e uma pagina so.
PRACAS = ("Sao Paulo/SP", "Fortaleza/CE", "Florianopolis/SC")
POR_PRACA = {"Sao Paulo/SP": ("vivo", "tim", "claro"),
             "Fortaleza/CE": ("brisanet",),
             "Florianopolis/SC": ("unifique",)}
NACIONAIS = ("nucel", "starlink", "claro_flex", "tim_fit")

# OS CAMPOS QUE O ENSAIO COMPARA. Sao os que viajam para a mensagem e
# para a tela; "composicao" e texto de evidencia e muda de tamanho com a
# fonte, entao nao entra - o que importa dela ja sai em apps e nivel.
CAMPOS = ("preco_promocional", "preco_cheio", "degrau_mbps",
          "franquia_anunciada_gb", "franquia_contratual_gb",
          "nivel_bundle", "apps", "apps_rotulo", "codigo_anatel",
          "fidelidade_meses", "multa_fidelidade", "taxa_instalacao",
          "meses_desconto", "preco_pos_promocao", "assinatura_sva",
          "velocidade_declarada")

# A identidade do PAR, e nao da serie: os dois lados leram a mesma
# pagina, entao o nome e o degrau sao o endereco da oferta. Mudou o
# degrau? Sai como oferta que desapareceu e outra que apareceu, que e a
# leitura certa do que aconteceu.
IDENTIDADE = ("operadora", "produto", "praca", "nome_oferta",
              "degrau_mbps", "franquia_anunciada_gb")

# CAMPO QUE MEDE QUANTO NOS SABEMOS, e por isso tem direcao: subir e
# ganho, cair e perda. O resto - preco, degrau, franquia - e fato, e
# fato diferente lido do mesmo corpo barra em qualquer direcao.
#
# Medido na primeira rodada de verdade, 04/11/2026: o ensaio acusou
# "TROCA: nivel_bundle 1 -> 3" sobre o acerto do dia, em que o nivel
# subiu porque os apps voltaram. Barrar ali seria barrar o conserto.
COM_DIRECAO = ("nivel_bundle",)


# ------------------------------------------------------------------ pacote
def _empacotar(v):
    """O retorno da torneira em JSON, com bytes sobrevivendo."""
    if isinstance(v, bytes):
        return {"__b64": base64.b64encode(v).decode("ascii")}
    if isinstance(v, tuple):
        return {"__tupla": [_empacotar(x) for x in v]}
    if isinstance(v, list):
        return [_empacotar(x) for x in v]
    if isinstance(v, dict):
        return dict((k, _empacotar(x)) for k, x in v.items())
    return v


def _desempacotar(v):
    if isinstance(v, dict):
        if "__b64" in v:
            return base64.b64decode(v["__b64"])
        if "__tupla" in v:
            return tuple(_desempacotar(x) for x in v["__tupla"])
        return dict((k, _desempacotar(x)) for k, x in v.items())
    if isinstance(v, list):
        return [_desempacotar(x) for x in v]
    return v


def _chave(modulo, funcao, args, kwargs):
    """A chamada identificada pelo que muda a resposta: url e corpo.

    O corpo entra porque a Claro busca por POST na mesma url com
    payloads diferentes - sem ele, a segunda chamada receberia a
    resposta da primeira e o ensaio compararia leitura de pagina errada.
    """
    valores = list(args) + [kwargs.get(k) for k in sorted(kwargs)]
    textos = [a for a in valores if isinstance(a, str)]
    url = next((a for a in textos if "://" in a), None)
    # OS OUTROS ARGUMENTOS DE TEXTO TAMBEM ENTRAM. regulamento(op,
    # codigo) nao recebe url: sem isto as 25 chamadas cairiam na mesma
    # chave, e a releitura receberia o regulamento de outra oferta -
    # defeito que este projeto ja teve uma vez (C1).
    resto = "|".join(a for a in textos if a is not url)[:120]
    corpo = next((a for a in valores if isinstance(a, bytes)), None)
    if corpo is None:
        corpo = kwargs.get("dados")
    # O CORPO INTEIRO, EM HASH - e nao os 40 primeiros caracteres.
    # Medido em 04/11/2026: a Brisanet faz varios POST de GraphQL na
    # mesma url, e os corpos comecam identicos ("query($cityId: ID)...").
    # Com o prefixo de 40, um sobrescrevia o outro na gravacao e a
    # releitura devolvia a mesma resposta para todos: 4 ofertas
    # desapareciam, EM SILENCIO, e saiam do outro lado como "oferta
    # nova". Falha que parece resultado e o modo de falhar que este
    # projeto mais guarda.
    marca = ""
    if isinstance(corpo, str):
        corpo = corpo.encode("utf-8")
    if isinstance(corpo, bytes):
        marca = hashlib.sha1(corpo).hexdigest()
    return "%s.%s|%s|%s|%s" % (modulo, funcao, url, resto, marca)


class PaginaGravada(object):
    """A pagina do Playwright embrulhada, para guardar o que renderizou."""

    def __init__(self, real, caixa, nome):
        self._real, self._caixa, self._nome = real, caixa, nome

    def goto(self, *a, **k):
        return self._real.goto(*a, **k)

    def wait_for_timeout(self, *a, **k):
        return self._real.wait_for_timeout(*a, **k)

    def inner_text(self, seletor):
        t = self._real.inner_text(seletor)
        self._caixa.setdefault("%s|inner_text|%s" % (self._nome, seletor),
                               []).append(t)
        return t


class PaginaDeMentira(object):
    """A mesma pagina, de novo, sem abrir navegador nenhum."""

    def __init__(self, caixa, nome):
        self._caixa, self._nome = caixa, nome

    def goto(self, *a, **k):
        return None

    def wait_for_timeout(self, *a, **k):
        return None

    def inner_text(self, seletor):
        chave = "%s|inner_text|%s" % (self._nome, seletor)
        fila = self._caixa.get(chave) or []
        if not fila:
            raise RuntimeError("o ensaio nao gravou %s" % chave)
        # a ultima chamada repete a ultima gravada: a pagina e a mesma
        return fila[0] if len(fila) == 1 else fila.pop(0)


# ------------------------------------------------------------------ leitura
def _coletores(arvore):
    """Os modulos de coletor de UMA arvore, importados dali.

    A arvore de referencia entra na frente do sys.path para que
    "from coletores import x" resolva nela. Cada leitura roda no seu
    PROPRIO processo: Python guarda o modulo importado, e duas arvores
    no mesmo processo dariam a primeira para as duas.
    """
    sys.path.insert(0, arvore)
    import coletores                                          # noqa: F401
    vindos = {}
    for nome in [t[0] for t in TORNEIRAS] + list(NAVEGADOR):
        vindos[nome] = __import__("coletores.%s" % nome,
                                  fromlist=["coletores"])
    de_onde = os.path.dirname(os.path.abspath(
        vindos["vivo"].__file__))
    esperado = os.path.join(os.path.abspath(arvore), "coletores")
    if os.path.normcase(de_onde) != os.path.normcase(esperado):
        raise SystemExit("ABORTADO: os coletores vieram de %s, e nao de %s"
                         % (de_onde, esperado))
    return vindos


def instalar_torneiras(mods, paginas, gravando, faltou=None):
    """Embrulha TODA torneira e devolve quais embrulhou.

    DEVOLVE A LISTA PORQUE O LACO NAO SE MEDE SOZINHO. O provador
    reduziu este laco a TORNEIRAS[:1] - um coletor interceptado, os
    outros buscando de verdade nas duas leituras - e nenhum teste
    percebeu: o ensaio comparava duas coletas em vez de duas leituras
    da mesma pagina, que e exatamente o que ele nao serve para fazer.
    """
    faltou = [] if faltou is None else faltou
    instaladas = []

    def torneira(modulo, funcao):
        original = getattr(mods[modulo], funcao)

        def gravar(*a, **k):
            v = original(*a, **k)
            paginas[_chave(modulo, funcao, a, k)] = _empacotar(v)
            return v

        def reler(*a, **k):
            c = _chave(modulo, funcao, a, k)
            if c not in paginas:
                faltou.append(c)
                raise RuntimeError("o ensaio nao gravou %s" % c)
            return _desempacotar(paginas[c])

        setattr(mods[modulo], funcao, gravar if gravando else reler)
        instaladas.append((modulo, funcao))

    for modulo, funcao in TORNEIRAS:
        torneira(modulo, funcao)
    return instaladas


def _ler(arvore, paginas, pracas, gravando, verbose=False):
    """Roda os coletores de uma arvore. Devolve (ofertas, avisos).

    gravando=True busca de verdade e enche "paginas"; False le dali.
    """
    mods = _coletores(arvore)
    ofertas, avisos, faltou = [], {}, []

    instaladas = instalar_torneiras(mods, paginas, gravando, faltou)
    if sorted(instaladas) != sorted(TORNEIRAS):
        raise SystemExit("ABORTADO: torneira faltando (%s)"
                         % sorted(set(TORNEIRAS) - set(instaladas)))

    def rodar(nome, cidade, uf, **extra):
        mod = mods[nome]
        try:
            r = mod.coletar(cidade, uf, verbose=verbose, **extra)
        except Exception as e:
            avisos.setdefault(nome, []).append("caiu: %s" % e)
            return
        ofertas.extend(r.get("ofertas") or [])
        if r.get("avisos"):
            avisos.setdefault(nome, []).extend(r["avisos"])

    for praca in pracas:
        cidade, uf = praca.split("/")
        for nome in POR_PRACA.get(praca, ()):
            rodar(nome, cidade, uf)

    # OS DOIS DE NAVEGADOR, com a pagina embrulhada. Sem Playwright eles
    # ficam fora - e fora DITO, nunca como zero diferencas.
    p = nav = contexto = None
    try:
        if gravando:
            from playwright.sync_api import sync_playwright
            p = sync_playwright().start()
            nav = p.chromium.launch(headless=True)
            contexto = nav.new_context(locale="pt-BR")
    except Exception as e:
        avisos.setdefault("navegador", []).append(
            "Playwright indisponivel, NuCel e Claro Flex ficaram fora "
            "do ensaio: %s" % e)
    for nome in NAVEGADOR:
        if gravando and contexto is None:
            continue
        if gravando:
            pagina = PaginaGravada(contexto.new_page(), paginas, nome)
        else:
            if not any(k.startswith("%s|" % nome) for k in paginas):
                continue
            pagina = PaginaDeMentira(paginas, nome)
        rodar(nome, "Brasil", "BR", pagina=pagina)
    for nome in ("starlink", "tim_fit"):
        rodar(nome, "Brasil", "BR")
    if contexto is not None:
        try:
            contexto.close(), nav.close(), p.stop()
        except Exception:
            pass
    if faltou:
        # FALHA ALTO, e nao como aviso. A premissa do ensaio e os dois
        # lados lerem o MESMO corpo; chamada sem pagina gravada quebra
        # a premissa, e comparacao sobre premissa quebrada nao vale.
        # Como aviso isso ficava invisivel: o lado que leu menos saia
        # como "oferta nova" do outro lado.
        avisos.setdefault("ensaio", []).append(
            "%d chamada(s) sem pagina gravada: %s"
            % (len(faltou), faltou[0][:120]))
    return ofertas, avisos


# ---------------------------------------------------------------- comparar
def _id(o):
    return tuple(o.get(c) for c in IDENTIDADE)


def _vazio(v):
    return v is None or v == "" or v == [] or v == {}


def comparar(antigas, novas):
    """As diferencas entre duas leituras da mesma pagina.

    PERDA e TROCA barram; ganho e oferta nova sao informativos. A
    assimetria e o ponto: melhorar a leitura ACRESCENTA, e o que este
    portao existe para pegar e a melhoria que, de passagem, apaga.
    """
    a = collections.OrderedDict((_id(o), o) for o in antigas)
    b = collections.OrderedDict((_id(o), o) for o in novas)
    # IDENTIDADE REPETIDA NAO COLAPSA CALADA. A rodada de 04/11/2026
    # gravou 112 ofertas e comparou 110: duas identidades repetidas, e o
    # dicionario ficou com a ultima de cada par. Comparar uma oferta
    # achando que e outra foi o defeito que publicou "-26% em 20 pracas"
    # num dia sem reajuste nenhum.
    def repetidas(lista):
        vistos, rep = set(), set()
        for o in lista:
            k = _id(o)
            if k in vistos:
                rep.add(k)
            vistos.add(k)
        return rep

    # E A COLISAO QUE JA EXISTIA NAO BARRA. A vitrine da Vivo chama duas
    # ofertas de "Vivo Familia 2 + TV" no mesmo degrau desde sempre:
    # barrar por isso seria barrar todo push para sempre, e portao que
    # sempre barra vira portao que ninguem respeita - a mesma razao pela
    # qual _indexar manda colisao para o ponto cego e nao para o canal
    # de erro. Barra a colisao NOVA, que a mudanca criou.
    antes_rep, agora_rep = repetidas(antigas), repetidas(novas)
    colididas = [(k, "identidade repetida que a mudanca criou", None, None)
                 for k in sorted(agora_rep - antes_rep,
                                 key=lambda x: [str(i) for i in x])]
    herdadas = [(k, "identidade repetida nos dois lados", None, None)
                for k in sorted(agora_rep & antes_rep,
                                key=lambda x: [str(i) for i in x])]
    perdas, trocas, ganhos = [], [], []
    for k in a:
        if k not in b:
            perdas.append((k, "a oferta inteira", a[k].get("preco_promocional"),
                           None))
            continue
        for campo in CAMPOS:
            va, vb = a[k].get(campo), b[k].get(campo)
            if isinstance(va, list) or isinstance(vb, list):
                sa, sb = set(va or ()), set(vb or ())
                if sa - sb:
                    perdas.append((k, campo, sorted(sa), sorted(sb)))
                if sb - sa:
                    ganhos.append((k, campo, sorted(sa), sorted(sb)))
                continue
            if va == vb:
                continue
            if _vazio(vb) and not _vazio(va):
                perdas.append((k, campo, va, vb))
            elif _vazio(va) and not _vazio(vb):
                ganhos.append((k, campo, va, vb))
            elif campo in COM_DIRECAO:
                caixa = ganhos if (vb or 0) > (va or 0) else perdas
                caixa.append((k, campo, va, vb))
            else:
                trocas.append((k, campo, va, vb))
    novas_ofertas = [(k, "oferta nova", None,
                      b[k].get("preco_promocional")) for k in b if k not in a]
    return {"perdas": perdas, "trocas": trocas, "ganhos": ganhos,
            "novas": novas_ofertas, "colididas": colididas,
            "herdadas": herdadas,
            "lidas": (len(a), len(b)), "cruas": (len(antigas), len(novas))}


def imprimir(d, avisos_antes=None, avisos_depois=None):
    def linha(t):
        k, campo, va, vb = t
        return ("  %-8s %-9s %-34s %-22s %s -> %s"
                % (k[0], k[2].split("/")[0][:9], (k[3] or "")[:34], campo,
                   va, vb))

    print("")
    print("=" * 78)
    print("ofertas lidas: %d na referencia, %d no trabalho"
          % d.get("cruas", d["lidas"]))
    if d.get("cruas", d["lidas"]) != d["lidas"]:
        print("comparadas: %d e %d - o resto tem identidade repetida"
              % d["lidas"])
    print("=" * 78)
    for titulo, chave in (("PERDA (barra o push)", "perdas"),
                          ("IDENTIDADE REPETIDA que a mudanca criou "
                           "(barra o push)", "colididas"),
                          ("identidade repetida que ja existia "
                           "(a comparacao nao fala por elas)", "herdadas"),
                          ("TROCA (barra o push)", "trocas"),
                          ("ganho", "ganhos"),
                          ("oferta nova", "novas")):
        print("")
        print("%s: %d" % (titulo, len(d[chave])))
        for t in d[chave][:12]:
            print(linha(t))
        if len(d[chave]) > 12:
            print("  e mais %d" % (len(d[chave]) - 12))
    # OS AVISOS DOS DOIS LADOS. Imprimir so os novos escondia o que
    # importa mais: o aviso que a REFERENCIA deu e o trabalho nao -
    # coletor que falhou na releitura, por exemplo - e exatamente o
    # caso em que o lado que leu menos sai do outro lado como "oferta
    # nova", e a comparacao nao vale.
    for titulo, a, b in (("aviso que a referencia nao dava", avisos_antes,
                          avisos_depois),
                         ("aviso que SO a referencia deu", avisos_depois,
                          avisos_antes)):
        novos = []
        for nome, lista in sorted((b or {}).items()):
            antes = set((a or {}).get(nome) or ())
            for x in lista:
                if x not in antes:
                    novos.append("%s: %s" % (nome, x))
        print("")
        print("%s: %d" % (titulo, len(novos)))
        for x in novos[:8]:
            print("  %s" % x)


# -------------------------------------------------------------------- modos
def _salvar(caminho, obj):
    with io.open(caminho, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False))


def _abrir(caminho):
    with io.open(caminho, encoding="utf-8") as f:
        return json.load(f)


def veredito_do_controle(d):
    """0 se o replay reproduziu a leitura ao vivo; 3 se nao.

    O CONTROLE DE FIDELIDADE E A PREMISSA DO ENSAIO: o mesmo codigo,
    lendo as paginas gravadas, tem de reproduzir a leitura ao vivo
    EXATAMENTE. Sem ele o ensaio comparava uma leitura completa com uma
    truncada e chamava a diferenca de "oferta nova" - medido em
    04/11/2026, quando a chave da chamada usava 40 caracteres do corpo e
    um POST de GraphQL da Brisanet sobrescrevia o outro: 4 ofertas
    desapareciam, em silencio, e a rodada passava.

    QUALQUER diferenca aborta, inclusive ganho: aqui nao ha leitor novo
    para melhorar nada - os dois lados sao o mesmo codigo.
    """
    tudo = (d["perdas"] + d["trocas"] + d["ganhos"] + d["novas"]
            + d["colididas"])
    if tudo or d["cruas"][0] != d["cruas"][1]:
        print("")
        print("ABORTADO: o replay nao reproduziu a leitura ao vivo "
              "(%d diferenca(s), %d ofertas ao vivo e %d na releitura). A "
              "premissa do ensaio e os dois lados lerem o MESMO corpo - "
              "sem ela a comparacao nao vale."
              % (len(tudo), d["cruas"][1], d["cruas"][0]))
        return 3
    print("")
    print("controle: o replay reproduz a leitura ao vivo, oferta por oferta")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gravar", metavar="DIR")
    ap.add_argument("--reler", metavar="DIR")
    ap.add_argument("--leitor", metavar="ARVORE")
    ap.add_argument("--comparar", nargs=2, metavar=("ANTES", "DEPOIS"))
    ap.add_argument("--saida", default="referencia.json")
    ap.add_argument("--estrito", action="store_true",
                    help="qualquer diferenca falha (o controle de "
                         "fidelidade do replay)")
    ap.add_argument("--referencia", default="origin/main")
    ap.add_argument("--pracas")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pracas = ([x.strip() for x in a.pracas.split(";")] if a.pracas
              else list(PRACAS))

    if a.comparar:
        antes, depois = _abrir(a.comparar[0]), _abrir(a.comparar[1])
        d = comparar(antes["ofertas"], depois["ofertas"])
        imprimir(d, antes.get("avisos"), depois.get("avisos"))
        if a.estrito:
            return veredito_do_controle(d)
        return 1 if (d["perdas"] or d["trocas"] or d["colididas"]) else 0



    if a.gravar:
        os.makedirs(a.gravar, exist_ok=True)
        paginas = {}
        ofertas, avisos = _ler(RAIZ, paginas, pracas, True, a.verbose)
        _salvar(os.path.join(a.gravar, "paginas.json"), paginas)
        _salvar(os.path.join(a.gravar, "trabalho.json"),
                {"ofertas": ofertas, "avisos": avisos})
        print("gravado: %d paginas, %d ofertas" % (len(paginas), len(ofertas)))
        return 0

    if a.reler:
        paginas = _abrir(os.path.join(a.reler, "paginas.json"))
        ofertas, avisos = _ler(a.leitor or RAIZ, paginas, pracas, False,
                               a.verbose)
        _salvar(os.path.join(a.reler, a.saida),
                {"ofertas": ofertas, "avisos": avisos})
        print("relido: %d ofertas" % len(ofertas))
        return 0

    # O ENSAIO INTEIRO, em subprocessos: cada leitura no seu Python,
    # porque modulo importado nao se troca dentro do mesmo processo.
    #
    # A ARVORE DE REFERENCIA NASCE FORA DO PROJETO, na pasta temporaria
    # do sistema. Dentro do OneDrive o Windows mantem arquivo preso e o
    # "git worktree remove" falha com Permission denied - a sobra
    # entupia a rodada seguinte.
    dir_ensaio = os.path.join(RAIZ, ".ensaio")
    os.makedirs(dir_ensaio, exist_ok=True)
    # NOME UNICO, E PODA ANTES. O git guarda o metadado da worktree por
    # BASENAME, e no Windows ele as vezes nao sai (OneDrive, antivirus,
    # arquivo aberto): com nome fixo, a rodada seguinte morreria em
    # "already exists" por causa de sujeira da anterior.
    subprocess.call(["git", "worktree", "prune"], cwd=RAIZ)
    arvore = os.path.join(tempfile.mkdtemp(prefix="ensaio-"),
                          "ref-%d" % os.getpid())
    print("referencia: %s" % a.referencia, flush=True)
    if subprocess.call(["git", "worktree", "add", "--detach", arvore,
                        a.referencia], cwd=RAIZ) != 0:
        return 2
    eu = [sys.executable, "-I", os.path.abspath(__file__)]
    args_pracas = ["--pracas", ";".join(pracas)]
    try:
        if subprocess.call(eu + ["--gravar", dir_ensaio] + args_pracas,
                           cwd=RAIZ) != 0:
            return 2
        # O CONTROLE VEM PRIMEIRO: ler as paginas gravadas com ESTE
        # codigo tem de reproduzir a leitura ao vivo. E a premissa do
        # ensaio, e ela ja falhou uma vez - em silencio.
        if subprocess.call(eu + ["--reler", dir_ensaio, "--leitor", RAIZ,
                                 "--saida", "controle.json"] + args_pracas,
                           cwd=RAIZ) != 0:
            return 2
        if subprocess.call(
                eu + ["--comparar", os.path.join(dir_ensaio, "controle.json"),
                      os.path.join(dir_ensaio, "trabalho.json"), "--estrito"],
                cwd=RAIZ) != 0:
            return 3
        if subprocess.call(eu + ["--reler", dir_ensaio, "--leitor", arvore]
                           + args_pracas, cwd=RAIZ) != 0:
            return 2
        return subprocess.call(
            eu + ["--comparar", os.path.join(dir_ensaio, "referencia.json"),
                  os.path.join(dir_ensaio, "trabalho.json")], cwd=RAIZ)
    finally:
        # A LIMPEZA NAO PODE DERRUBAR O VEREDITO. Worktree que nao sai -
        # antivirus, OneDrive, arquivo aberto - e sujeira, e sujeira nao
        # e o mesmo que perda de campo: o "git worktree prune" resolve na
        # proxima rodada e o aviso sai dito.
        if subprocess.call(["git", "worktree", "remove", "--force", arvore],
                           cwd=RAIZ) != 0:
            shutil.rmtree(arvore, ignore_errors=True)
            subprocess.call(["git", "worktree", "prune"], cwd=RAIZ)
            print("nota: a arvore de referencia ficou em %s" % arvore,
                  flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
