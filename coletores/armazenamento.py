"""Gravacao no Supabase.

Append-only: so INSERT. Nada aqui atualiza nem apaga.

Quando o robo repete (o repique das 7h30), as linhas do que ja entrou sao
ignoradas pelo indice unico, em vez de sobrescritas. Repetir e seguro;
perder nao e.
"""

import json
import os
import re
import urllib.error
import urllib.request

API = "/rest/v1/"


def _config():
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    chave = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if not url or not chave:
        raise RuntimeError(
            "SUPABASE_URL ou SUPABASE_SECRET_KEY ausentes. "
            "Sao segredos do repositorio; sem eles o robo coleta mas nao grava.")
    return url, chave


def chave_continuidade(o):
    """A identidade que sobrevive a renomeacao e reedicao da oferta.

    O codigo Anatel NAO serve como chave: ele identifica uma versao da
    oferta e muda a cada reedicao, partindo a serie em duas sem aviso.
    Ele entra como atributo, e a troca dele vira dado - mede com que
    frequencia a operadora reescreve o portfolio.
    """
    degrau = o.get("degrau_mbps") or o.get("franquia_anunciada_gb") or 0
    unidade = "mbps" if o.get("degrau_mbps") else "gb"
    variante = o.get("variante") or _variante(o)
    return "%s|%s|%s%s|%s" % (o.get("operadora"), o.get("produto"),
                              degrau, unidade, variante)


def _variante(o):
    nome = (o.get("nome_oferta") or "").lower()

    # O CICLO DE PAGAMENTO faz parte da identidade onde a operadora vende
    # os dois lados. "TIM Controle FIT Anual 2.0" e "FIT Mensal 2.0"
    # entregam os mesmos 20 GB por R$ 30 e R$ 45; sem isto as duas
    # dividiam uma chave so, e a serie ficaria alternando entre os dois
    # precos como se houvesse reajuste todo dia. Vale igual para o Vivo
    # Lite, que tem o mesmo par.
    ciclo = ("_anual" if "anual" in nome
             else "_mensal" if "mensal" in nome else "")

    if "fam" in nome:
        return "familia" + ciclo
    if " tv" in nome or nome.startswith("tv"):
        return "combo_tv" + ciclo
    nivel = o.get("nivel_bundle") or 0
    if nivel >= 2:
        # o streaming faz parte da identidade: "Pos com Netflix" nao e o
        # mesmo produto que "Pos com Amazon", mesmo com franquia igual
        marca = re.sub(r"^vivo (pos|controle)\s*(com)?\s*", "", nome).strip()
        base = ("com_%s" % re.sub(r"[^a-z0-9]+", "_", marca)[:24].strip("_")
                if marca else "com_streaming")
        return base + ciclo
    return ("com_apps" if nivel == 1 else "simples") + ciclo


def _pedir(url, chave, caminho, corpo, prefer):
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url + API + caminho, data=dados, method="POST")
    req.add_header("apikey", chave)
    req.add_header("Authorization", "Bearer " + chave)
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", prefer)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def gravar_capturas(ofertas):
    """Grava as ofertas do dia. Devolve (gravadas, erro)."""
    if not ofertas:
        return 0, None
    url, chave = _config()

    linhas = []
    for o in ofertas:
        data = (o.get("capturado_em") or "")[:10]
        praca = o.get("praca") or ""
        linhas.append({
            "capturado_em": o.get("capturado_em"),
            "data_captura": data,
            "operadora": o.get("operadora"),
            "produto": o.get("produto"),
            "praca": praca,
            "uf": praca.split("/")[-1] if "/" in praca else None,
            "nome_oferta": o.get("nome_oferta") or "",
            "destaque": o.get("destaque"),
            "chave": chave_continuidade(o),
            "codigo_anatel": o.get("codigo_anatel") or "",
            "codigos_anatel": o.get("codigos_anatel"),
            "id_catalogo": o.get("id_catalogo"),
            "degrau_mbps": o.get("degrau_mbps"),
            "franquia_anunciada_gb": o.get("franquia_anunciada_gb"),
            "franquia_contratual_gb": o.get("franquia_contratual_gb"),
            "preco_cheio": o.get("preco_cheio"),
            "preco_promocional": o.get("preco_promocional"),
            "fidelidade_meses": o.get("fidelidade_meses"),
            "multa_fidelidade": o.get("multa_fidelidade"),
            "taxa_instalacao": o.get("taxa_instalacao"),
            "meses_desconto": o.get("meses_desconto"),
            "preco_pos_promocao": o.get("preco_pos_promocao"),
            "nivel_bundle": o.get("nivel_bundle"),
            "campanha": o.get("campanha"),
            # A oferta inteira. Campo novo entra aqui no mesmo dia em que o
            # coletor passa a ler - sem coluna nova e sem ALTER TABLE, que e
            # passo manual e portanto dia de coleta em risco. A assinatura
            # dos codigos SVA e lida daqui, por bruto->>assinatura_sva.
            "bruto": o,
        })

    # Deduplica dentro do proprio lote. O Postgres rejeita o lote INTEIRO
    # quando duas linhas dele colidem entre si - nesse caso nem o
    # ignore-duplicates salva, porque ele so trata conflito com o que ja
    # esta gravado, nao conflito interno.
    unicas, vistas = [], set()
    for l in linhas:
        k = (l["data_captura"], l["operadora"], l["produto"], l["praca"],
             l["chave"], l["nome_oferta"], l["codigo_anatel"])
        if k in vistas:
            continue
        vistas.add(k)
        unicas.append(l)

    # on_conflict precisa nomear a restricao, senao o banco rejeita em vez
    # de ignorar - foi o que derrubou a coleta de 30/09.
    alvo = ("capturas?on_conflict=data_captura,operadora,produto,praca,"
            "chave,nome_oferta,codigo_anatel")
    status, corpo = _pedir(url, chave, alvo,
                           unicas, "return=minimal,resolution=ignore-duplicates")
    if status in (200, 201, 204):
        return len(unicas), None
    return 0, "HTTP %s: %s" % (status, corpo[:300])


def registrar_coleta(registro):
    """Grava o diario de bordo de uma operadora."""
    url, chave = _config()
    status, corpo = _pedir(url, chave, "coletas", [registro], "return=minimal")
    if status in (200, 201, 204):
        return True, None
    return False, "HTTP %s: %s" % (status, corpo[:300])


PAGINA = 1000   # o PostgREST corta a resposta nesse tamanho


def consultar_tudo(caminho, pagina=PAGINA):
    """Como consultar, mas segue as paginas ate o fim.

    O PostgREST devolve no maximo 1000 linhas. Quem pede 20000 e confia
    recebe 1000 e nao percebe: truncamento calado. Na comparacao diaria
    isso significa deixar de ver as ofertas que ficaram de fora da
    primeira pagina - a falha silenciosa que a metodologia proibe, e que
    sobreviveu aqui porque o numero pedido parecia grande demais para
    importar.
    """
    tudo, inicio = [], 0
    sep = "&" if "?" in caminho else "?"
    while True:
        linhas, erro = consultar("%s%slimit=%d&offset=%d"
                                 % (caminho, sep, pagina, inicio))
        if erro:
            return None, erro
        if not linhas:
            break
        tudo.extend(linhas)
        if len(linhas) < pagina:
            break
        inicio += pagina
    return tudo, None


def consultar(caminho):
    """GET simples na API, para a mensagem diaria comparar com ontem."""
    url, chave = _config()
    req = urllib.request.Request(url + API + caminho)
    req.add_header("apikey", chave)
    req.add_header("Authorization", "Bearer " + chave)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300])
    except Exception as e:
        return None, str(e)
