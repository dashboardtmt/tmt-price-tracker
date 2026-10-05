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


def entrada_do_controle(hoje, praca="Sao Paulo/SP"):
    """O plano de entrada do controle, o produto principal."""
    return entrada_do_produto(hoje, "controle", praca)


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
        return [], [], [], erro_h or erro_o
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

    renomeadas = _renomeadas(h, o)
    return list(precos.values()), list(composicao.values()), renomeadas, None


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


def montar_mensagem(hoje, ontem):
    linhas = ["Price Tracker - %s" % datetime.fromisoformat(hoje).strftime("%d/%m")]

    # 1. mudanca sobe para o topo, com detalhe
    mud, comp, renom, erro_cmp = mudancas(hoje, ontem)
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

    # 1c. renomeacao: evento por si, e o unico lugar onde um preco novo
    # chegaria sem passar pelos blocos acima
    if renom:
        linhas.append("")
        for m in renom[:4]:
            a, d = m["antes"], m["atual"]
            de, para = a["preco_promocional"], d["preco_promocional"]
            if de is not None and para is not None and de != para:
                var = (para - de) / de * 100 if de else 0
                cauda = "e o preco foi de R$ %s para R$ %s (%+.0f%%)" % (
                    _reais(de), _reais(para), var)
            else:
                cauda = "com o mesmo preco (R$ %s)" % _reais(para)
            linhas.append("RENOMEOU: %s -> %s" % (
                a["nome_oferta"] or "?", d["nome_oferta"] or "?"))
            linhas.append("  %s" % cauda)
            linhas.append("  Onde: %s (%d de %d pracas)" % (
                ", ".join(sorted({p.split("/")[0] for p in m["pracas"]})[:4]),
                len(m["pracas"]), len(PRACAS)))
        if len(renom) > 4:
            linhas.append("  (+%d outras)" % (len(renom) - 4))

    # Nada mudou tem de ser dito, e com o tamanho da base por tras:
    # "sem novidade" sozinho nao diz se o robo olhou 10 ofertas ou 1400.
    if not (mud or comp or renom or erro_cmp):
        linhas.append("")
        linhas.append("Nenhuma mudanca de preco, composicao ou nome.")

    # 2. estado da coleta, operadora por operadora
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
    linhas.append("--- A COLETA ---")
    if col:
        ok = sum(1 for c in col if c["sucesso"])
        tot = sum(c["ofertas"] for c in col)
        linhas.append("%d de %d operadoras | %d ofertas" % (ok, len(col), tot))
        for c in sorted(col, key=lambda x: -x["ofertas"]):
            marca = "" if c["sucesso"] else "   <-- INCOMPLETA"
            linhas.append("  %-9s %5d ofertas  %d/%d pracas%s" % (
                c["operadora"], c["ofertas"], c["pracas_ok"],
                c["pracas_pedidas"], marca))
        if ok < len(col):
            linhas.append("  Operadora incompleta deixa buraco, nunca zero.")
        if len(col) < len(COLETORES):
            faltam = sorted(set(COLETORES) - {c["operadora"] for c in col})
            linhas.append("  SEM REGISTRO AINDA: %s" % ", ".join(faltam))

    else:
        linhas.append("NENHUM REGISTRO HOJE - o robo nao rodou")

    # 3. a saude da comparacao. Sem isto, "nada mudou" nao se sustenta:
    # pode ser mercado parado ou pode ser comparacao sem par para comparar.
    h, e1 = _indexar(hoje)
    o, e2 = _indexar(ontem)
    if not (e1 or e2):
        comuns = len(set(h) & set(o))
        linhas.append("")
        linhas.append("--- A COMPARACAO ---")
        linhas.append("%d ofertas hoje, %d ontem, %d com par nos dois"
                      % (len(h), len(o), comuns))
        if h:
            linhas.append("Cobertura: %.0f%%" % (100.0 * comuns / len(h)))
        com_sva = sum(1 for l in h.values() if l.get("assinatura_sva"))
        if com_sva:
            linhas.append("Assinatura de composicao: %d ofertas"
                          " (so a Vivo publica os codigos)" % com_sva)

    # 4. o plano de entrada, por produto, na praca de referencia
    for produto, titulo in (("controle", "CONTROLE"), ("fibra", "FIBRA"),
                            ("movel", "POS-PAGO")):
        entrada, _ = entrada_do_produto(hoje, produto)
        if not entrada:
            continue
        linhas.append("")
        linhas.append("--- %s, ENTRADA EM SP ---" % titulo)
        for e in entrada:
            linhas.append("  %-9s %-10s R$ %s" % (
                e["operadora"], (e["destaque"] or "-")[:10],
                _reais(e["preco_promocional"])))

    # 5. o tamanho da serie: o ativo do projeto e o historico acumulado
    primeiro, _ = armazenamento.consultar(
        "capturas?select=data_captura&order=data_captura.asc&limit=1")
    if primeiro:
        inicio = primeiro[0]["data_captura"]
        n = (datetime.fromisoformat(hoje).date()
             - datetime.fromisoformat(inicio).date()).days + 1
        linhas.append("")
        linhas.append("--- A SERIE ---")
        linhas.append("%d dia(s) desde %s" % (
            n, datetime.fromisoformat(inicio).strftime("%d/%m")))

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
