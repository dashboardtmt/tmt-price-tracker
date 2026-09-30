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
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from coletores import armazenamento, tim, vivo     # noqa: E402
from coletores.pracas import PRACAS, pracas_de, rotulo   # noqa: E402

BRT = timezone(timedelta(hours=-3))

# Quais operadoras ja tem coletor. As outras entram conforme ficarem prontas;
# a serie comeca desigual de proposito (decisao 18) porque esperar custa
# historico que nao volta.
COLETORES = {"Vivo": vivo, "TIM": tim}


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
        pracas = pracas_de(nome)
        if uma_praca:
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
    return resumo


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


def entrada_do_controle(hoje, praca="Sao Paulo/SP"):
    """O plano de entrada do controle em cada operadora, na praca de referencia."""
    filtro = ("capturas?data_captura=eq.%s&produto=eq.controle&praca=eq.%s"
              "&select=operadora,nome_oferta,destaque,preco_promocional"
              "&order=preco_promocional.asc" % (hoje, urllib.parse.quote(praca)))
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


def mudancas(hoje, ontem):
    """O que mudou de preco de ontem para hoje, na mesma chave e praca."""
    def indexar(dia):
        f = ("capturas?data_captura=eq.%s&select=chave,praca,operadora,produto,"
             "nome_oferta,destaque,preco_promocional,franquia_anunciada_gb,"
             "degrau_mbps,nivel_bundle&limit=20000" % dia)
        linhas, _ = armazenamento.consultar(f)
        return {(l["chave"], l["praca"]): l for l in (linhas or [])}

    h, o = indexar(hoje), indexar(ontem)
    achados = {}
    for k, atual in h.items():
        antes = o.get(k)
        if not antes or antes["preco_promocional"] is None:
            continue
        if atual["preco_promocional"] == antes["preco_promocional"]:
            continue
        # agrupa por oferta: uma mudanca nacional nao vira 20 alertas
        ident = (atual["operadora"], atual["produto"], atual["chave"],
                 antes["preco_promocional"], atual["preco_promocional"])
        d = achados.setdefault(ident, {"pracas": [], "atual": atual, "antes": antes})
        d["pracas"].append(atual["praca"])
    return list(achados.values())


def montar_mensagem(hoje, ontem):
    linhas = ["Price Tracker - %s" % datetime.fromisoformat(hoje).strftime("%d/%m")]

    # 1. mudanca sobe para o topo, com detalhe
    mud = mudancas(hoje, ontem)
    if mud:
        linhas.append("")
        for m in mud[:6]:
            a, d = m["antes"], m["atual"]
            de, para = a["preco_promocional"], d["preco_promocional"]
            var = (para - de) / de * 100 if de else 0
            linhas.append("MUDOU: %s %s %g -> %g (%+.0f%%)" % (
                d["operadora"], d["nome_oferta"] or d["produto"], de, para, var))
            linhas.append("  Onde: %s (%d de %d pracas)" % (
                ", ".join(sorted({p.split("/")[0] for p in m["pracas"]})[:4]),
                len(m["pracas"]), len(PRACAS)))
            mesma_franquia = a.get("franquia_anunciada_gb") == d.get("franquia_anunciada_gb")
            mesmo_bundle = a.get("nivel_bundle") == d.get("nivel_bundle")
            linhas.append("  Franquia: %s | Bundle: %s" % (
                "igual" if mesma_franquia else "MUDOU",
                "igual" if mesmo_bundle else "MUDOU"))
        if len(mud) > 6:
            linhas.append("  (+%d outras mudancas)" % (len(mud) - 6))

    # 2. estado da coleta
    col, _ = armazenamento.consultar(
        "coletas?data_captura=eq.%s&select=operadora,pracas_ok,pracas_pedidas,ofertas,sucesso" % hoje)
    linhas.append("")
    if col:
        ok = sum(1 for c in col if c["sucesso"])
        tot_ofertas = sum(c["ofertas"] for c in col)
        linhas.append("Coleta: %d de %d operadoras, %d ofertas" % (ok, len(col), tot_ofertas))
        for c in col:
            if not c["sucesso"]:
                linhas.append("  %s: %d de %d pracas" % (
                    c["operadora"], c["pracas_ok"], c["pracas_pedidas"]))
    else:
        linhas.append("Coleta: NENHUM REGISTRO HOJE - o robo nao rodou")

    # 3. resumo do controle, o produto principal
    entrada, _ = entrada_do_controle(hoje)
    if entrada:
        linhas.append("")
        linhas.append("Controle, plano de entrada (SP):")
        for e in entrada:
            linhas.append("%-7s %-8s R$ %s" % (
                e["operadora"], e["destaque"] or "-",
                ("%.2f" % e["preco_promocional"]).replace(".", ",")))
    return "\n".join(linhas)


def rodar_aviso(simular=False):
    hoje = agora().date()
    ontem = hoje - timedelta(days=1)
    texto = montar_mensagem(hoje.isoformat(), ontem.isoformat())
    print(texto)
    if simular:
        print("\n[simulacao] mensagem nao enviada")
        return 0
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    r = _tel("sendMessage", {"chat_id": chat, "text": texto})
    if not r.get("ok"):
        print("\nFALHOU ao enviar: %s" % r)
        return 1
    print("\nenviado")
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
        rodar_coleta(a.praca, a.simular)
    if a.avisar:
        return rodar_aviso(a.simular)
    return 0


if __name__ == "__main__":
    sys.exit(main())
