"""Coletor do TIM Controle FIT - a linha below-the-line da TIM.

POR QUE EXISTE SEPARADO. O FIT nao aparece em nenhuma das tres paginas
que o coletor da TIM le. Procurei por "flex", "lite", "leve", "digital"
e "esim" nas tres e no home: nada. A palavra "FIT" tambem nao aparece no
TEXTO da pagina de Controle - ela so existe nos LINKS do rodape, que
apontam para as etiquetas da Anatel. E a linha de defesa: vendida, mas
nao exibida.

DE ONDE VEM O DADO. Da Etiqueta-Padrao, o documento que a Anatel obriga
cada oferta a publicar. Ela traz nome, preco, franquia, fidelizacao,
multa, vigencia e codigo - mais do que qualquer card de vitrine daria, e
com valor legal. Em 07/10/2026 o Google resumia o Anual 2.0 como "cerca
de 30 GB a 35 GB"; a etiqueta diz 20 GB. Entre o resumo e o documento,
vale o documento.

OS LINKS SAO DESCOBERTOS A CADA RODADA, e nao fixados aqui: quando a TIM
publicar a versao 3.0, ela entra sozinha. O que se fixa e o padrao do
nome do arquivo.

NACIONAL. A etiqueta declara "Abrangencia da Oferta: Nacional" - uma
captura por dia basta.

Uso:  python coletores/tim_fit.py
"""

import argparse
import io
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

from . import rede

# A pagina que linka as etiquetas. E a de Controle porque o FIT e uma
# variante de Controle - a propria etiqueta diz "Modalidade de
# Contratacao: Controle Express".
PAGINA = "https://www.tim.com.br/%s/para-voce/planos/controle"
UF_PADRAO = "sp"

# Os arquivos de etiqueta do FIT, entre as dezenas de PDFs da pagina
ETIQUETA = re.compile(r'href="(https://[^"]*etiqueta[^"]*fit[^"]*\.pdf)"', re.I)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

NACIONAL = True


def _buscar(url, timeout=45):
    def uma():
        req = urllib.request.Request(url)
        req.add_header("User-Agent", UA)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""
        except Exception:
            return 0, b""
    return rede.insistir(uma, url)


def _campo(texto, rotulo, limite=90):
    m = re.search(re.escape(rotulo) + r"\s*(.{1,%d})" % limite, texto)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def _data(txt):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", str(txt or ""))
    if not m:
        return None
    d, mes, a = (int(x) for x in m.groups())
    try:
        return date(a, mes, d)
    except ValueError:
        return None


def ler_etiqueta(blob):
    """Extrai de um PDF de Etiqueta-Padrao o que o tracker guarda."""
    try:
        import pypdf
    except ImportError:
        return None, "pypdf nao instalado"
    try:
        leitor = pypdf.PdfReader(io.BytesIO(blob))
        t = "\n".join((p.extract_text() or "") for p in leitor.pages)
    except Exception as e:
        return None, "PDF ilegivel: %s" % str(e)[:60]
    t = re.sub(r"[ \t]+", " ", t)

    nome = re.search(r"(TIM CONTROLE FIT[^\n]*)", t, re.I)
    preco_txt = _campo(t, "Preço ", 70)
    if not nome or not preco_txt:
        return None, "etiqueta sem nome ou sem preco"
    # "R$30 por mes, durante 12 meses (R$360 no ano)" -> 30,00
    mp = re.search(r"R\$\s?(\d{1,3}(?:[.,]\d{2})?)\s*por\s*m[êe]s", preco_txt, re.I)
    if not mp:
        return None, "preco em formato novo: %s" % preco_txt[:50]
    preco = float(mp.group(1).replace(".", "").replace(",", "."))

    gb = _campo(t, "Franquia ", 24) or ""
    mg = re.search(r"(\d{1,4})\s*GB", gb, re.I)
    fid = _campo(t, "Fidelização ", 40) or ""
    multa = _campo(t, "Multa por Rescisão Antecipada ", 40) or ""
    mf = re.search(r"(\d{1,2})\s*meses", fid, re.I)
    mm = re.search(r"R\$\s?(\d{1,4}(?:[.,]\d{2})?)", multa)

    return {
        # title() transformaria "TIM" em "Tim": a sigla fica como esta
        "nome_oferta": re.sub(r"\s+", " ",
                              nome.group(1)).strip().title().replace("Tim ", "TIM "),
        "destaque": ("%s GB" % mg.group(1)) if mg else None,
        "franquia_anunciada_gb": int(mg.group(1)) if mg else None,
        "franquia_contratual_gb": int(mg.group(1)) if mg else None,
        "preco_promocional": preco,
        "preco_cheio": preco,
        "fidelidade_meses": int(mf.group(1)) if mf else None,
        "multa_fidelidade": (float(mm.group(1).replace(".", "").replace(",", "."))
                             if mm else None),
        "codigo_anatel": _campo(t, "Código de Identificação ", 24),
        "aplicativos": _campo(t, "Aplicativos Incluídos ", 90),
        "fim_vigencia": _data(_campo(t, "Vigência da Oferta ", 30)),
        "composicao": ("%s · %s · pagamento: %s"
                       % (preco_txt, _campo(t, "Modalidade de Contratação ", 30) or "",
                          _campo(t, "Condições de Pagamento ", 30) or ""))[:400],
    }, None


def coletar(cidade="Brasil", uf="BR", verbose=True):
    agora = datetime.now(timezone(timedelta(hours=-3)))
    praca = "%s/%s" % (cidade, uf)
    saida = {"operadora": "TIM", "praca": praca,
             "capturado_em": agora.isoformat(), "ofertas": [], "avisos": []}

    if verbose:
        print("=" * 70)
        print("COLETOR TIM CONTROLE FIT  |  %s  |  %s"
              % (praca, agora.strftime("%d/%m/%Y %H:%M")))
        print("=" * 70)

    status, html = _buscar(PAGINA % UF_PADRAO)
    if status != 200:
        saida["avisos"].append("pagina de controle: HTTP %s" % status)
        return saida

    links = sorted(set(ETIQUETA.findall(html.decode("utf-8", "replace"))))
    if not links:
        saida["avisos"].append(
            "nenhuma etiqueta do FIT linkada - a pagina mudou ou a linha saiu")
        return saida
    if verbose:
        print("  %d etiqueta(s) encontrada(s)" % len(links))

    hoje = agora.date()
    por_nome, vencidas = {}, 0
    for url in links:
        st, blob = _buscar(url)
        if st != 200 or not blob:
            saida["avisos"].append("etiqueta %s: HTTP %s" % (url.split("/")[-1], st))
            continue
        o, err = ler_etiqueta(blob)
        if err:
            saida["avisos"].append("%s: %s" % (url.split("/")[-1], err))
            continue
        if o["fim_vigencia"] and o["fim_vigencia"] < hoje:
            vencidas += 1
            continue
        # a pagina as vezes linka duas copias da mesma etiqueta; fica a
        # de vigencia mais longa
        antes = por_nome.get(o["nome_oferta"])
        if antes and (antes["fim_vigencia"] or hoje) >= (o["fim_vigencia"] or hoje):
            continue
        por_nome[o["nome_oferta"]] = o

    if vencidas:
        saida["avisos"].append("%d etiqueta(s) com vigencia encerrada, ignoradas"
                               % vencidas)
    if not por_nome:
        saida["avisos"].append("nenhuma oferta FIT vigente")
        return saida

    for o in por_nome.values():
        o.pop("fim_vigencia", None)
        o.update({
            "operadora": "TIM",
            # below-the-line e produto proprio, nao um degrau do controle
            "produto": "btl",
            "linha": "fit",
            "praca": praca,
            "capturado_em": agora.isoformat(),
            "degrau_mbps": None,
            "nivel_bundle": 1 if o.get("aplicativos") else 0,
            "campanha": None, "id_catalogo": None,
        })
        saida["ofertas"].append(o)

    if verbose:
        print("  %d oferta(s) vigente(s)" % len(saida["ofertas"]))
    return saida


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    d = coletar(verbose=not a.json)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1, default=str))
        return 0

    print("\n--- OFERTAS (%d) ---" % len(d["ofertas"]))
    for o in sorted(d["ofertas"], key=lambda x: x["preco_promocional"]):
        print("  %-30s %3s GB | R$ %6.2f | %s"
              % (o["nome_oferta"][:30], o["franquia_anunciada_gb"],
                 o["preco_promocional"], o["codigo_anatel"]))
    if d["avisos"]:
        print("\n--- AVISOS ---")
        for av in d["avisos"]:
            print("  " + av)
    return 0


if __name__ == "__main__":
    sys.exit(main())
