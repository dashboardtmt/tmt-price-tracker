# -*- coding: utf-8 -*-
u"""Varre a serie publicada e denuncia inconsistencia, sem credencial.

POR QUE EXISTE. As varreduras deste projeto foram todas feitas a mao,
uma sessao por vez, e cada uma redescobriu as mesmas tres armadilhas de
medicao antes de achar qualquer coisa. Com elas num arquivo, a proxima
varredura e um comando - e o que ela aprendeu nao depende de alguem
lembrar.

  python ferramentas/varredura_da_serie.py
  python ferramentas/varredura_da_serie.py --arquivo dados.json

Le o JSON publicado no Storage, que e publico: nao precisa da chave do
Supabase e nao escreve em lugar nenhum. O banco de mentira dos testes
entra para poder chamar robo.mudancas - ele aplica os filtros do
PostgREST de verdade, entao o que sai aqui e o que a rotina das 06:30
veria com o mesmo dado.

AS TRES ARMADILHAS QUE ESTA FERRAMENTA JA CONHECE, e que uma varredura
a mao erra de novo toda vez:

  1. AGRUPAR PELA CHAVE NAO MEDE COLISAO. A identidade da comparacao e
     chave + praca + NOME (robo._identidade): em 03/11/2026 havia 120
     grupos de chave repetida e ZERO identidade colidindo. Quem conta
     pela chave anuncia 120 defeitos que nao existem.
  2. DEFEITO JA CONSERTADO CONTINUA NA JANELA. A serie guarda 35 dias,
     entao defeito corrigido no dia 10 aparece nos dias 1 a 9 para
     sempre. Toda denuncia aqui sai com o ULTIMO dia em que ocorreu.
  3. LIMITE CHUTADO E RUIDO. "preco acima de R$ 1.000" acusa a Starlink
     de 2 TB e o Vivo Total V de 10 Giga, que custam isso mesmo. Os
     limites vem do vigia, que ja os mediu.
"""
import argparse
import collections
import datetime
import gzip
import io
import json
import os
import sys
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "testes"))

import robo                                                   # noqa: E402
import vigia                                                  # noqa: E402
from coletores import apps as regua                           # noqa: E402
from coletores import (brisanet, claro, claro_flex, nucel,    # noqa: E402
                       starlink, tim, tim_fit, unifique, vivo)

URL = ("https://iuopzrxfmobllhkyuvkk.supabase.co/storage/v1/object/"
       "public/tela/dados.json.gz")
MODULOS = {"brisanet": brisanet, "claro": claro, "claro_flex": claro_flex,
           "nucel": nucel, "starlink": starlink, "tim": tim,
           "tim_fit": tim_fit, "unifique": unifique, "vivo": vivo}

ACHADOS = []


def denuncia(nome, quantos, ultimo=None, exemplos=()):
    """Uma linha por classe. Com o ultimo dia, que e o que diz se vive."""
    if not quantos:
        print("  ok      %s" % nome)
        return
    vivo_hoje = ultimo == DIAS[-1]
    print("  %s %s: %d%s"
          % ("ACHADO " if vivo_hoje else "passado", nome, quantos,
             (" | ultimo dia: %s" % ultimo) if ultimo else ""))
    for e in list(exemplos)[:4]:
        print("          %s" % e)
    if vivo_hoje:
        ACHADOS.append((nome, quantos))


def ultimo_dia(linhas):
    return max([l["data_captura"] for l in linhas]) if linhas else None


ap = argparse.ArgumentParser()
ap.add_argument("--arquivo", help="JSON local, em vez de baixar")
args = ap.parse_args()

if args.arquivo:
    TUDO = json.load(io.open(args.arquivo, encoding="utf-8"))
else:
    with urllib.request.urlopen(URL, timeout=120) as r:
        # publicado em gzip desde 11/11/2026: sem compressao o arquivo
        # passou dos 50 MB do Storage
        TUDO = json.loads(gzip.decompress(r.read()).decode("utf-8"))

POR_DIA = collections.defaultdict(list)
for _l in TUDO:
    POR_DIA[_l["data_captura"]].append(_l)
DIAS = sorted(POR_DIA)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=" * 72)
print("%d linhas | %d dias | %s a %s"
      % (len(TUDO), len(DIAS), DIAS[0], DIAS[-1]))
print("=" * 72)

# ------------------------------------------------------------------
print("")
print("A JANELA")
d0 = datetime.date.fromisoformat(DIAS[0])
d1 = datetime.date.fromisoformat(DIAS[-1])
faltam = []
while d0 <= d1:
    if d0.isoformat() not in POR_DIA:
        faltam.append(d0.isoformat())
    d0 += datetime.timedelta(days=1)
denuncia("dia sem captura nenhuma", len(faltam),
         faltam[-1] if faltam else None, faltam)

tam = dict((d, len(POR_DIA[d])) for d in DIAS)
mediana = sorted(tam.values())[len(tam) // 2]
magros = [d for d in DIAS if tam[d] < 0.8 * mediana]
denuncia("dia com menos de 80%% da mediana (%d linhas)" % mediana,
         len(magros), magros[-1] if magros else None,
         ["%s: %d linhas" % (d, tam[d]) for d in magros])

# ------------------------------------------------------------------
print("")
print("A COMPARACAO, PELO CAMINHO DE PRODUCAO")
# A QUARTA ARMADILHA, e a mais fina: nem a identidade mede colisao
# sozinha. _indexar separa o grupo repetido, e DEPOIS
# _desempatar_por_anatel refaz a conta com o codigo de registro - em
# 03/11/2026 havia 886 identidades repetidas na janela e o codigo
# resolveu TODAS, entao o ponto cego do dia era zero. Medir antes do
# desempate acusa 886 defeitos que nao existem.
#
# Por isso aqui quem responde e robo.mudancas, que e o que roda as
# 06:30, e nao uma conta escrita de novo.
import _apoio                                                 # noqa: E402

RODADAS = {}
for _ontem, _hoje in zip(DIAS, DIAS[1:]):
    _apoio.banco(POR_DIA[_hoje] + POR_DIA[_ontem])
    RODADAS[_hoje] = robo.mudancas(_hoje, _ontem)

cegos = [(d, m["cego"]["quantas"]) for d, m in sorted(RODADAS.items())
         if m.get("cego")]
denuncia("oferta que ficou fora da comparacao do dia", sum(n for _, n in cegos),
         cegos[-1][0] if cegos else None,
         ["%s: %d ofertas" % t for t in cegos])

erros = [(d, m["erro"]) for d, m in sorted(RODADAS.items()) if m.get("erro")]
denuncia("dia em que a comparacao caiu", len(erros),
         erros[-1][0] if erros else None, ["%s: %s" % t for t in erros])

pior = min((m["cobertura"]["fracao"], d) for d, m in RODADAS.items()
           if m.get("cobertura"))
print("  nota    cobertura: %.1f%% no pior dia (%s), %.1f%% no ultimo"
      % (100 * pior[0], pior[1],
         100 * RODADAS[DIAS[-1]]["cobertura"]["fracao"]))
por_chave = collections.Counter(
    (l["operadora"], l["produto"], l["praca"], l["chave"])
    for l in POR_DIA[DIAS[-1]])
print("  nota    chave repetida (NAO e defeito: o nome e o codigo "
      "desambiguam): %d grupos no ultimo dia"
      % sum(1 for n in por_chave.values() if n > 1))

# ------------------------------------------------------------------
print("")
print("OS CAMPOS QUE A MENSAGEM USA")
for nome, teste in (("sem preco", lambda l: l["preco_promocional"] is None),
                    ("sem nome", lambda l: not (l["nome_oferta"] or "").strip()),
                    ("sem chave", lambda l: not (l["chave"] or "").strip())):
    ruins = [l for l in TUDO if teste(l)]
    denuncia("linha %s" % nome, len(ruins), ultimo_dia(ruins))

fora = [l for l in TUDO if l["preco_promocional"] is not None
        and not (vigia.PISO_PRECO <= l["preco_promocional"]
                 <= vigia.TETO_PRECO)]
denuncia("preco fora da faixa do vigia (R$ %.0f a R$ %.0f)"
         % (vigia.PISO_PRECO, vigia.TETO_PRECO), len(fora), ultimo_dia(fora),
         ["%s %s R$ %s" % (l["data_captura"], l["nome_oferta"][:30],
                           l["preco_promocional"]) for l in fora])

invertido = [l for l in TUDO if l["preco_cheio"] is not None
             and l["preco_promocional"] is not None
             and l["preco_cheio"] < l["preco_promocional"]]
denuncia("preco cheio abaixo do promocional", len(invertido),
         ultimo_dia(invertido),
         ["%s %s: cheio %s < promo %s"
          % (l["data_captura"], l["nome_oferta"][:28], l["preco_cheio"],
             l["preco_promocional"]) for l in invertido])

sem_velocidade = [l for l in TUDO if l["produto"] in ("fibra", "combo")
                  and not l["degrau_mbps"]]
denuncia("oferta de fibra ou combo sem velocidade", len(sem_velocidade),
         ultimo_dia(sem_velocidade))

# ------------------------------------------------------------------
print("")
print("OS CAMPOS DE APP, QUE TEM DE CONCORDAR ENTRE SI")
fantasma = [l for l in TUDO
            if any(a not in regua.APPS for a in (l["apps"] or ()))]
denuncia("lista de apps com nome que a regua nao conhece", len(fantasma),
         ultimo_dia(fantasma),
         sorted({"%s: %s" % (l["operadora"],
                             [a for a in l["apps"] if a not in regua.APPS])
                 for l in fantasma}))
rotulo_so = [l for l in TUDO if l["apps_rotulo"] and not l["apps"]]
denuncia("rotulo de app sem lista", len(rotulo_so), ultimo_dia(rotulo_so))
nivel0 = [l for l in TUDO if l["apps"] and not l["nivel_bundle"]
          and any(a in regua.APPS for a in l["apps"])]
denuncia("app conhecido e nivel de bundle 0", len(nivel0), ultimo_dia(nivel0))

# ------------------------------------------------------------------
print("")
print("A PISCADA DE 24 HORAS (valor de hoje igual ao de anteontem)")
serie = collections.defaultdict(dict)
for l in TUDO:
    k = (l["operadora"], l["produto"], l["praca"],
         " ".join((l["nome_oferta"] or "").lower().split()))
    serie[k].setdefault(l["data_captura"], set()).add(
        (l["preco_promocional"], l["franquia_contratual_gb"],
         tuple(sorted(l["apps"] or ())), l["nivel_bundle"]))
NOMES = ("preco", "franquia contratual", "lista de apps", "nivel de bundle")
contas = [0] * 4
ultimos = [None] * 4
for k, dias_ in serie.items():
    ds = sorted(d for d in dias_ if len(dias_[d]) == 1)
    vals = [next(iter(dias_[d])) for d in ds]
    for i in range(2, len(ds)):
        if DIAS.index(ds[i]) - DIAS.index(ds[i - 2]) != 2:
            continue
        for c in range(4):
            if vals[i][c] == vals[i - 2][c] != vals[i - 1][c]:
                contas[c] += 1
                ultimos[c] = max(ultimos[c] or "", ds[i])
for c, nome in enumerate(NOMES):
    # a contratual tem marca de reversao desde 03/11/2026; as outras tres
    # foram medidas em zero, e por isso nao ganharam guarda
    denuncia("piscada em %s" % nome, contas[c], ultimos[c])

# ------------------------------------------------------------------
print("")
print("A VIRADA DE VERSAO E A DATA DECLARADA")
def mapa(d):
    return dict(((l["operadora"], l["produto"], l["praca"],
                  " ".join((l["nome_oferta"] or "").lower().split()),
                  l["preco_promocional"]), l["chave"])
                for l in POR_DIA[d])


sem_declarar = []
for ontem, hoje in zip(DIAS, DIAS[1:]):
    a, b = mapa(ontem), mapa(hoje)
    virou = sum(1 for k in set(a) & set(b) if a[k] != b[k])
    # o que importa nao e a virada: e' EVENTO publicado como mercado
    # num dia em que a nossa leitura pode ter mudado
    m = RODADAS[hoje]
    if virou and m["remodeladas"] and hoje not in robo.LEITURA_MUDOU_EM:
        sem_declarar.append((hoje, len(m["remodeladas"]), virou))
denuncia("dia com remodelada no mercado e sem data declarada",
         len(sem_declarar),
         sem_declarar[-1][0] if sem_declarar else None,
         ["%s: %d evento(s) de mercado, %d chaves viradas - conferir se "
          "algum commit nosso entrou depois da coleta anterior"
          % t for t in sem_declarar])

# ------------------------------------------------------------------
print("")
print("O ALCANCE DA REGUA (a classe do Google One)")
nao_nomeados = {}
for nome, mod in sorted(MODULOS.items()):
    for atributo in ("STREAMINGS", "APPS_CATALOGO"):
        for termo in sorted(getattr(mod, atributo, None) or ()):
            if not regua.apps_do_texto(termo):
                nao_nomeados.setdefault(termo, []).append(nome)
print("  nota    %d nome(s) que os coletores listam para contar NIVEL e a "
      "regua nao sabe NOMEAR" % len(nao_nomeados))
print("          (nao e defeito de dado: e' o tamanho do balde "
      "\"com apps de catalogo\", que nao diz quais)")
for termo in sorted(nao_nomeados)[:30]:
    print("          %-18s %s" % (termo, ", ".join(nao_nomeados[termo])))

print("")
print("=" * 72)
if ACHADOS:
    print("ACHADO VIVO NO ULTIMO DIA: %d classe(s)" % len(ACHADOS))
    for nome, q in ACHADOS:
        print("  %s: %d" % (nome, q))
    raise SystemExit(1)
print("Nenhum achado vivo no ultimo dia da serie.")
