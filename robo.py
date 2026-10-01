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
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from coletores import (armazenamento, brisanet, claro, nucel, tim,   # noqa: E402
                       unifique, vivo)
from coletores.pracas import PRACAS, pracas_de, rotulo   # noqa: E402

BRT = timezone(timedelta(hours=-3))

# Quais operadoras ja tem coletor. As outras entram conforme ficarem prontas;
# a serie comeca desigual de proposito (decisao 18) porque esperar custa
# historico que nao volta.
COLETORES = {"Vivo": vivo, "TIM": tim, "Claro": claro,
             "Brisanet": brisanet, "Unifique": unifique, "NuCel": nucel}


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
    return {_identidade(l): l for l in (linhas or [])}, erro


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


def _rotulo(l):
    """Operadora e nome, sem repetir: "Vivo Vivo Controle" ficava feio."""
    nome = l.get("nome_oferta") or l.get("produto") or ""
    op = l.get("operadora") or ""
    return nome if nome.lower().startswith(op.lower()) else ("%s %s" % (op, nome)).strip()


def _reais(v):
    return ("%.2f" % v).replace(".", ",") if v is not None else "-"


def _agrupar(achados, ident, atual, antes):
    """Uma mudanca nacional e um alerta com 20 pracas, nao 20 alertas."""
    d = achados.setdefault(ident, {"pracas": [], "atual": atual, "antes": antes})
    d["pracas"].append(atual["praca"])


def mudancas(hoje, ontem):
    """O que mudou de ontem para hoje, na mesma chave e praca.

    Devolve duas listas: as mudancas de preco e as de composicao com preco
    parado. A segunda e o repasse disfarcado - tiraram algo da oferta e
    cobraram o mesmo. Sem a assinatura dos codigos SVA isso passava batido,
    porque o nome e o preco da oferta continuam identicos.
    """
    h, erro_h = _indexar(hoje)
    o, erro_o = _indexar(ontem)
    # Comparacao que falhou nao e comparacao sem novidade. Sem devolver o
    # erro, uma consulta que caiu faria o aviso afirmar "nada mudou" - pior
    # que nao avisar, porque soa como noticia verificada.
    if erro_h or erro_o:
        return [], [], erro_h or erro_o
    precos, composicao = {}, {}
    for k, atual in h.items():
        antes = o.get(k)
        if not antes:
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
    return list(precos.values()), list(composicao.values()), None


def montar_mensagem(hoje, ontem):
    linhas = ["Price Tracker - %s" % datetime.fromisoformat(hoje).strftime("%d/%m")]

    # 1. mudanca sobe para o topo, com detalhe
    mud, comp, erro_cmp = mudancas(hoje, ontem)
    if erro_cmp:
        linhas.append("")
        linhas.append("COMPARACAO COM ONTEM FALHOU: %s" % erro_cmp[:120])
        linhas.append("  Nao da para dizer se algo mudou hoje.")
    if mud:
        linhas.append("")
        for m in mud[:6]:
            a, d = m["antes"], m["atual"]
            de, para = a["preco_promocional"], d["preco_promocional"]
            var = (para - de) / de * 100 if de else 0
            linhas.append("MUDOU: %s R$ %s -> R$ %s (%+.0f%%)" % (
                _rotulo(d), _reais(de), _reais(para), var))
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

    # 1b. preco parado e composicao mexida: o repasse que nao aparece na
    # etiqueta. Vem depois das mudancas de preco porque e mais raro, e
    # antes do estado da coleta porque e noticia, nao diagnostico.
    if comp:
        linhas.append("")
        for m in comp[:4]:
            d = m["atual"]
            antes_sva = set((m["antes"]["assinatura_sva"] or "").split("+"))
            agora_sva = set((d["assinatura_sva"] or "").split("+"))
            preco = d["preco_promocional"]
            linhas.append("COMPOSICAO MUDOU, PRECO PARADO: %s (R$ %s)" % (
                _rotulo(d), _reais(preco)))
            saiu, entrou = sorted(antes_sva - agora_sva), sorted(agora_sva - antes_sva)
            if saiu:
                linhas.append("  Saiu: %s" % ", ".join(saiu))
            if entrou:
                linhas.append("  Entrou: %s" % ", ".join(entrou))
            linhas.append("  Onde: %s (%d de %d pracas)" % (
                ", ".join(sorted({p.split("/")[0] for p in m["pracas"]})[:4]),
                len(m["pracas"]), len(PRACAS)))
        if len(comp) > 4:
            linhas.append("  (+%d outras)" % (len(comp) - 4))

    # 2. estado da coleta
    col, _ = armazenamento.consultar(
        "coletas?data_captura=eq.%s&select=operadora,pracas_ok,pracas_pedidas,"
        "ofertas,sucesso,iniciada_em&order=iniciada_em.desc" % hoje)
    # Em dia de repique ou de correcao, a mesma operadora tem varios
    # registros. Vale o ultimo: somar todos contaria a mesma coleta duas
    # vezes e transformaria uma rodada que falhou em numero no relatorio.
    if col:
        ultima, vistos = [], set()
        for c in col:
            if c["operadora"] in vistos:
                continue
            vistos.add(c["operadora"])
            ultima.append(c)
        col = ultima
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
