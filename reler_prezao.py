# -*- coding: utf-8 -*-
u"""Rele o Prezao gravado ate 24/11/2026 com a regra de 25/11, pela escada
que a propria coleta guardou.

POR QUE EXISTE. Ate 24/11 so a recarga de R$ 30 do Prezao entrava como
oferta; as de R$ 25, 20 e 15 ficavam so na composicao, como "Escada
completa: R$ 30,00 = 17GB+ 3GB Youtube/30 dias; ...; R$ 15,00 = 5GB/15
dias". Em 25/11 as quatro passaram a entrar (decisao 126), e a entrada da
Claro no pre-pago "caiu" de R$ 30 para R$ 15 no grafico - queda da
leitura, nao de preco. Pergunta de quem le, em 25/11/2026: "tem como
ajustar o historico?".

TEM, PORQUE A PROVA ESTA GRAVADA. Toda captura do Prezao desde 08/10 traz
a escada que a pagina mostrava NAQUELE dia e NAQUELA praca. Nada aqui
vem de hoje: cada recarga reconstruida sai da escada da propria linha.
Dia ou praca sem captura do Prezao continua sem captura.

O QUE MUDA, por dia e praca:
  - a recarga de R$ 30 ja gravada passa a 20 GB (17 de uso livre e 3 de
    YouTube), como a regra de 25/11 le o mesmo "17GB+ 3GB Youtube" - nome,
    destaque, as duas franquias e a chave; ganha a validade;
  - as recargas da escada que nao estavam gravadas entram, com o preco, a
    franquia e a validade da escada.

A PROVA FICA. O bruto de cada linha corrigida guarda o que a coleta leu
em "releitura.lido"; a linha nova diz de qual captura saiu
("releitura.de_id"). Os apps nao mudam: o Skeelo que a pagina oferece
aos clientes do pre so passou a ser lido em 25/11, e a escada antiga nao
diz nada sobre ele - inventar seria pior que deixar.

Sem --aplicar, so conta e mostra. Com --aplicar, grava e confere: depois
de gravar, um novo planejamento tem de sair VAZIO e a contagem de linhas
tem de bater. Qualquer diferenca para tudo, alto.

Uso: python reler_prezao.py [--aplicar]   (precisa dos segredos do Supabase)
"""
import copy
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

from coletores import armazenamento

ATE = "2026-11-24"          # o ultimo dia gravado com a regra velha
EM = "2026-11-25"           # o dia da regra nova
POR = "reler_prezao.py"

COLUNAS = ("id,capturado_em,data_captura,operadora,produto,praca,uf,"
           "nome_oferta,destaque,chave,codigo_anatel,codigos_anatel,"
           "id_catalogo,degrau_mbps,franquia_anunciada_gb,"
           "franquia_contratual_gb,preco_cheio,preco_promocional,"
           "fidelidade_meses,multa_fidelidade,taxa_instalacao,meses_desconto,"
           "preco_pos_promocao,nivel_bundle,campanha,bruto")

# um degrau da escada gravada: "R$ 25,00 = 10GB+ 2GB Youtube/25 dias"
DEGRAU = re.compile(r"R\$\s?(\d{1,3},\d{2})\s*=\s*(\d{1,3})\s*GB([^/;]*)"
                    r"/\s*(\d{1,3})\s*dias", re.I)


def escada(composicao):
    u"""[(preco, total, livre ou None, dias)] da "Escada completa" gravada.

    A mesma regra do coletor desde 25/11: "17GB+ 3GB Youtube" sao 20 GB,
    17 de uso livre. Devolve None quando a escada existe mas nao se le
    inteira - o texto tem teto de 400 caracteres, e um degrau cortado no
    fim nao pode sumir calado."""
    if not composicao or "Escada completa:" not in composicao:
        return []
    trecho = composicao.split("Escada completa:", 1)[1]
    degraus = DEGRAU.findall(trecho)
    if not degraus or len(degraus) != len(re.findall(r"R\$", trecho)):
        return None
    saida = []
    for preco, gigas, extra, dias in degraus:
        app = re.search(r"\+\s*(\d{1,3})\s*GB", extra)
        livre = int(gigas)
        total = livre + (int(app.group(1)) if app else 0)
        saida.append((float(preco.replace(",", ".")), total,
                      livre if app else None, int(dias)))
    return saida


def _composicao(linha):
    return (linha.get("bruto") or {}).get("composicao")


def _alvo(fonte_bruto, preco, total, livre, dias):
    u"""O bruto de um degrau como a coleta de 25/11 o gravaria, a partir do
    bruto da captura que trouxe a escada."""
    b = copy.deepcopy(fonte_bruto)
    b.pop("releitura", None)
    texto = b.get("composicao") or ""
    b.update({
        "nome_oferta": "Claro Prezao %sGB" % total,
        "destaque": "%s GB" % total,
        "franquia_anunciada_gb": total,
        "franquia_contratual_gb": livre,
        "preco_promocional": preco,
        "validade_dias": dias,
        # a composicao de cada degrau diz a renovacao dele, como a coleta
        # de hoje grava; a escada e a mesma
        "composicao": re.sub(r"renovacao a cada \d+ dias",
                             "renovacao a cada %d dias" % dias, texto, count=1),
    })
    return b


CAMPOS_DA_OFERTA = ("nome_oferta", "destaque", "franquia_anunciada_gb",
                    "franquia_contratual_gb")


def planejar(linhas):
    u"""(remendos, novas, problemas).

    remendos: [(id, {coluna: valor})] para as linhas ja gravadas;
    novas: [linha] para inserir; problemas: [texto] - qualquer um para o
    --aplicar."""
    remendos, novas, problemas = [], [], []
    grupos = defaultdict(list)
    for l in linhas:
        grupos[(l["data_captura"], l["praca"])].append(l)
    for (dia, praca), grupo in sorted(grupos.items()):
        lidas = [(l, escada(_composicao(l))) for l in grupo]
        ilegiveis = [l for l, e in lidas if e is None]
        if ilegiveis:
            problemas.append("%s %s: escada ilegivel na captura %s"
                             % (dia, praca, ilegiveis[0]["id"]))
            continue
        escadas = {tuple(e) for _, e in lidas if e}
        if not escadas:
            problemas.append("%s %s: nenhuma captura traz a escada" % (dia, praca))
            continue
        if len(escadas) > 1:
            problemas.append("%s %s: %d escadas diferentes no mesmo dia"
                             % (dia, praca, len(escadas)))
            continue
        degraus = list(escadas)[0]
        fonte = next(l for l, e in lidas if e)
        precos = [d[0] for d in degraus]
        estranhas = [l for l in grupo if l.get("preco_promocional") not in precos]
        if estranhas:
            problemas.append("%s %s: captura %s a R$ %s fora da escada"
                             % (dia, praca, estranhas[0]["id"],
                                estranhas[0].get("preco_promocional")))
            continue
        por_preco = defaultdict(list)
        for l in grupo:
            por_preco[l["preco_promocional"]].append(l)
        if any(len(v) > 1 for v in por_preco.values()):
            problemas.append("%s %s: duas capturas com o mesmo preco" % (dia, praca))
            continue
        for preco, total, livre, dias in degraus:
            b = _alvo(fonte["bruto"], preco, total, livre, dias)
            chave = armazenamento.chave_continuidade(b)
            if preco in por_preco:
                l = por_preco[preco][0]
                campos = dict((k, b[k]) for k in CAMPOS_DA_OFERTA)
                campos["chave"] = chave
                mudou = dict((k, v) for k, v in campos.items() if l.get(k) != v)
                if not mudou and (l["bruto"] or {}).get("validade_dias") == dias:
                    continue
                # o bruto leva o que a coleta leu, para a prova nao sumir
                nb = dict(l["bruto"] or {})
                antes = nb.get("releitura", {}).get("lido") or dict(
                    (k, l.get(k)) for k in CAMPOS_DA_OFERTA + ("chave",))
                nb.update(dict((k, b[k]) for k in CAMPOS_DA_OFERTA))
                nb["validade_dias"] = dias
                nb["releitura"] = {"em": EM, "por": POR, "lido": antes}
                mudou.update(campos)
                mudou["bruto"] = nb
                remendos.append((l["id"], mudou))
            else:
                b["releitura"] = {"em": EM, "por": POR, "de_id": fonte["id"],
                                  "motivo": "recarga da escada gravada na "
                                            "composicao, fora da oferta"}
                nova = dict((k, v) for k, v in fonte.items() if k != "id")
                nova.update(dict((k, b[k]) for k in CAMPOS_DA_OFERTA))
                nova.update({"chave": chave, "preco_promocional": preco,
                             "preco_cheio": None, "bruto": b})
                novas.append(nova)
    return remendos, novas, problemas


def _pedido(metodo, caminho, corpo=None, prefer="return=minimal"):
    url, chave = armazenamento._config()
    dados = (json.dumps(corpo, ensure_ascii=False).encode("utf-8")
             if corpo is not None else None)
    req = urllib.request.Request(url + armazenamento.API + caminho,
                                 data=dados, method=metodo)
    req.add_header("apikey", chave)
    req.add_header("Authorization", "Bearer " + chave)
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", prefer)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, r.read().decode("utf-8")


def ler():
    linhas, erro = armazenamento.consultar_tudo(
        "capturas?operadora=eq.Claro&produto=eq.prepago&data_captura=lte.%s"
        "&select=%s" % (ATE, COLUNAS))
    if erro:
        raise RuntimeError(erro)
    return linhas


def olhar_tim():
    u"""A TIM teve o mesmo degrau em 08/10 (R$ 30 -> 20): o que a coleta
    gravou dela antes disso. So mostra."""
    linhas, erro = armazenamento.consultar_tudo(
        "capturas?operadora=eq.TIM&produto=eq.prepago&data_captura=lte.2026-10-08"
        "&select=data_captura,nome_oferta,preco_promocional,"
        "composicao:bruto->>composicao")
    if erro:
        print("TIM: %s" % erro)
        return
    vistos = defaultdict(set)
    for l in linhas:
        vistos[(l["nome_oferta"], l["preco_promocional"],
                (l.get("composicao") or "")[:400])].add(l["data_captura"])
    for (nome, preco, comp), dias in sorted(vistos.items(), key=lambda x: min(x[1])):
        print("TIM %s a %s | %s R$ %s | %s" % (min(dias), max(dias), nome, preco, comp))


def relatorio(linhas, remendos, novas, problemas):
    dias = sorted({l["data_captura"] for l in linhas})
    print("capturas do Prezao lidas: %d, de %s a %s, %d praca(s)"
          % (len(linhas), dias[0] if dias else "-", dias[-1] if dias else "-",
             len({l["praca"] for l in linhas})))
    escadas = defaultdict(set)
    for l in linhas:
        e = escada(_composicao(l))
        escadas[tuple(e) if e else e].add(l["data_captura"])
    for e, ds in sorted(escadas.items(), key=lambda x: min(x[1])):
        print("  escada %s a %s: %s" % (min(ds), max(ds), e))
    print("corrigir: %d linha(s) ja gravadas" % len(remendos))
    print("inserir: %d recarga(s)" % len(novas))
    conta = defaultdict(int)
    for n in novas:
        conta[(n["preco_promocional"], n["nome_oferta"])] += 1
    for (preco, nome), n in sorted(conta.items()):
        print("  R$ %6.2f %-18s %4d" % (preco, nome, n))
    for p in problemas[:20]:
        print("PROBLEMA: " + p)
    if remendos:
        print("exemplo de correcao: %s" % json.dumps(
            dict((k, v) for k, v in remendos[0][1].items() if k != "bruto"),
            ensure_ascii=False))
        print("  releitura: %s" % json.dumps(remendos[0][1]["bruto"]["releitura"],
                                             ensure_ascii=False))
    if novas:
        print("exemplo de recarga nova: %s" % json.dumps(
            dict((k, v) for k, v in novas[0].items() if k != "bruto"),
            ensure_ascii=False))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    gravar = "--aplicar" in argv
    linhas = ler()
    remendos, novas, problemas = planejar(linhas)
    relatorio(linhas, remendos, novas, problemas)
    olhar_tim()
    if problemas:
        print("PAREI: %d problema(s) - nada gravado" % len(problemas))
        return 1
    if not gravar:
        print("so contei - para gravar, --aplicar")
        return 0
    for i, campos in remendos:
        status, _ = _pedido("PATCH", "capturas?id=eq.%d" % int(i), campos)
        if status not in (200, 204):
            print("PAREI: a correcao da captura %s devolveu HTTP %s" % (i, status))
            return 1
    for k in range(0, len(novas), 500):
        status, corpo = _pedido("POST", "capturas", novas[k:k + 500])
        if status not in (200, 201, 204):
            print("PAREI: a insercao devolveu HTTP %s: %s" % (status, corpo[:300]))
            return 1
    depois = ler()
    r2, n2, p2 = planejar(depois)
    if r2 or n2 or p2:
        print("PAREI: depois de gravar ainda faltam %d correcao(oes), %d "
              "recarga(s) e %d problema(s)" % (len(r2), len(n2), len(p2)))
        return 1
    if len(depois) != len(linhas) + len(novas):
        print("PAREI: eram %d capturas, entraram %d, e agora ha %d"
              % (len(linhas), len(novas), len(depois)))
        return 1
    print("gravado e conferido: %d correcao(oes) e %d recarga(s); um novo "
          "planejamento sai vazio" % (len(remendos), len(novas)))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
