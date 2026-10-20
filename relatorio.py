# -*- coding: utf-8 -*-
"""O relatorio diario em PDF, anexado na mensagem do Telegram.

POR QUE EXISTE. A mensagem do Telegram e um resumo que cabe na tela do
telefone: quantas mudancas, quais as maiores, o preco de entrada. O que
nao cabe la - a lista inteira de mudancas, o preco de entrada em cada um
dos cinco produtos, as pracas onde cada mudanca valeu, o estado de cada
coletor - vem aqui.

Os dois saem do MESMO levantamento, feito em montar_mensagem. Se saissem
de consultas separadas, um dia iam discordar, e ai a pessoa teria de
decidir em qual acreditar.

A CARA E A DO DASHBOARD. Mesma paleta do Itau BBA: laranja #FF5000 como
cor principal, preto quase puro no texto, fundo claro. Titulo preto,
negrito, a esquerda, com fio laranja embaixo - o mesmo padrao dos decks.
Sem emoji, sem cor que nao esteja na paleta.

QUANDO O DADO NAO EXISTE, A TABELA DIZ ISSO. Tabela vazia com um "nao
houve" escrito e informacao; tabela que some deixa o leitor sem saber se
nao houve mudanca ou se o relatorio quebrou.
"""
import io
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether,
                                PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

# A paleta do Itau BBA, a mesma da tela.
LARANJA = colors.HexColor("#FF5000")
PRETO = colors.HexColor("#000512")
TEXTO = colors.HexColor("#2B2621")
SUAVE = colors.HexColor("#7C7468")
BORDA = colors.HexColor("#E7E1D4")
FUNDO = colors.HexColor("#F0EDE4")
BRANCO = colors.HexColor("#FCFBF7")

PAINEL = "https://tmt-price-tracker.vercel.app"

MARGEM = 16 * mm
LARGURA = A4[0] - 2 * MARGEM

ESTILOS = {
    "titulo": ParagraphStyle(
        "titulo", fontName="Helvetica-Bold", fontSize=17, leading=20,
        textColor=LARANJA, alignment=TA_LEFT, spaceAfter=1),
    "subtitulo": ParagraphStyle(
        "subtitulo", fontName="Helvetica", fontSize=9, leading=12,
        textColor=SUAVE, spaceAfter=10),
    "secao": ParagraphStyle(
        "secao", fontName="Helvetica-Bold", fontSize=11, leading=14,
        textColor=PRETO, spaceBefore=12, spaceAfter=5),
    "corpo": ParagraphStyle(
        "corpo", fontName="Helvetica", fontSize=8.5, leading=11.5,
        textColor=TEXTO, spaceAfter=4),
    "nota": ParagraphStyle(
        "nota", fontName="Helvetica", fontSize=7.5, leading=10,
        textColor=SUAVE, spaceBefore=2),
    "celula": ParagraphStyle(
        "celula", fontName="Helvetica", fontSize=7.5, leading=9.5,
        textColor=TEXTO),
    # O cabecalho da tabela e branco sobre preto, e a cor TEM de estar
    # no paragrafo: a TEXTCOLOR da TableStyle nao vence a do Paragraph,
    # e o texto saia escuro sobre fundo escuro, ilegivel.
    "cabecalho": ParagraphStyle(
        "cabecalho", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5,
        textColor=colors.white),
}

# Os quatro produtos do relatorio, na ordem pedida. Fibra e pos-pago
# ficam de fora: o relatorio nao e um espelho do painel, e a serie
# completa dos seis esta em tmt-price-tracker.vercel.app.
PRODUTOS = (("controle", "Controle"), ("btl", "Below-the-line"),
            ("prepago", "Pré-pago"), ("combo", "Combo"))


def _reais(v):
    return ("R$ %.2f" % v).replace(".", ",") if v is not None else "—"


def _pc(de, para):
    if not de or para is None:
        return "—"
    return "%+.0f%%" % ((para - de) / de * 100)


def _curto(txt, limite):
    """Corta na palavra, nao no caractere.

    "TIM Ultrafibra com Modem Wi-fi gra" era o corte por numero de
    caracteres, e o leitor tropeca na palavra pela metade.
    """
    t = str(txt or "")
    if len(t) <= limite:
        return t
    corte = t[:limite].rsplit(" ", 1)[0]
    return (corte or t[:limite]).rstrip(" ,;-") + "…"


def _p(txt, estilo="celula"):
    """Celula como paragrafo, para o texto quebrar em vez de vazar."""
    return Paragraph(str(txt if txt is not None else "—"), ESTILOS[estilo])


def _tabela(cabecalho, linhas, larguras, vazio="Sem ocorrências."):
    """Uma tabela com a cara da tela: cabecalho preto, zebra discreta."""
    if not linhas:
        return Table([[_p("<i>%s</i>" % vazio)]], colWidths=[sum(larguras)],
                     hAlign="LEFT",
                     style=TableStyle([
                         ("TEXTCOLOR", (0, 0), (-1, -1), SUAVE),
                         ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                         ("TOPPADDING", (0, 0), (-1, -1), 6),
                         ("LEFTPADDING", (0, 0), (-1, -1), 6),
                         ("BOX", (0, 0), (-1, -1), 0.5, BORDA)]))

    dados = [[_p(c, "cabecalho") for c in cabecalho]]
    dados += [[_p(c) for c in linha] for linha in linhas]
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), PRETO),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDA),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDA),
    ]
    for i in range(1, len(dados)):
        if i % 2 == 0:
            estilo.append(("BACKGROUND", (0, i), (-1, i), BRANCO))
    return Table(dados, colWidths=larguras, style=TableStyle(estilo),
                 repeatRows=1, hAlign="LEFT")


def _cabecalho_pagina(canvas, doc):
    """A faixa preta com o fio laranja, igual ao topo da tela."""
    canvas.saveState()
    canvas.setFillColor(FUNDO)
    canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
    canvas.setFillColor(PRETO)
    canvas.rect(0, A4[1] - 15 * mm, A4[0], 15 * mm, stroke=0, fill=1)
    canvas.setFillColor(LARANJA)
    canvas.rect(0, A4[1] - 16 * mm, A4[0], 1 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(MARGEM, A4[1] - 10 * mm, "Price Tracker TMT")
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(SUAVE)
    canvas.drawRightString(A4[0] - MARGEM, 10 * mm,
                           "página %d" % doc.page)
    canvas.drawString(MARGEM, 10 * mm,
                      "Fonte: site das companhias / vitrines virtuais de "
                      "cada região.")
    canvas.restoreState()


def _com_titulo(titulo, *conteudo):
    """Secao e conteudo numa peca so, para o titulo nao ficar orfao.

    "Estado da coleta" ficou no fim de uma pagina e a tabela dele comecou
    na seguinte. Titulo sozinho no rodape nao informa nada.
    """
    return KeepTogether(_secao(titulo) + list(conteudo))


def _secao(titulo):
    """Titulo de secao com o fio laranja embaixo, como nos decks."""
    # hAlign LEFT: sem isto a tabela de uma celula fica centralizada no
    # quadro e o fio aparece no meio da pagina, longe do titulo
    fio = Table([[""]], colWidths=[26 * mm], rowHeights=[1.2],
                hAlign="LEFT",
                style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), LARANJA)]))
    return [Paragraph(titulo, ESTILOS["secao"]), fio, Spacer(1, 5)]


# ------------------------------------------------------------------ blocos

def _bloco_precos(d):
    linhas = []
    # A ORDEM VEM PRONTA DO ROBO (_por_efeito). Ordenar de novo aqui,
    # por outro critério, fazia a mensagem e o PDF discordarem sobre qual
    # era a maior mudanca do dia - e a mensagem mostra tres de N.
    for m in (d.get("mudancas_preco") or []):
        a, at = m["antes"], m["atual"]
        linhas.append([
            at.get("operadora"),
            _curto(at.get("nome_oferta"), 38),
            at.get("destaque") or "—",
            _reais(a.get("preco_promocional")),
            _reais(at.get("preco_promocional")),
            _pc(a.get("preco_promocional"), at.get("preco_promocional")),
            m.get("onde") or "—",
        ])
    return _tabela(
        ["Operadora", "Oferta", "Entrega", "Anterior", "Atual", "Var.",
         "Praças"],
        linhas,
        [20 * mm, 46 * mm, 17 * mm, 20 * mm, 20 * mm, 14 * mm, 41 * mm],
        vazio="Nenhuma variação de preço identificada em relação ao dia anterior.")


def _bloco_composicao(d):
    linhas = []
    for m in d.get("mudancas_composicao") or []:
        at, a = m["atual"], m["antes"]
        # o mesmo texto da mensagem, e nao um "—" que se le como "nao ha
        # preco" numa tabela cujo titulo afirma que o preco nao mudou
        preco = (_reais(at.get("preco_promocional"))
                 if a.get("preco_promocional") is not None
                 and at.get("preco_promocional") is not None
                 else "não lido")
        linhas.append([
            at.get("operadora"),
            _curto(at.get("nome_oferta"), 40),
            preco,
            m.get("onde") or "—",
        ])
    return _tabela(
        ["Operadora", "Oferta", "Preço", "Praças"], linhas,
        [24 * mm, 64 * mm, 26 * mm, 64 * mm],
        vazio="Nenhuma alteração de composição identificada.")


# A ordem da tela: a leitura comeca pelas tres grandes, que e como o
# mercado se le.
ORDEM = ("Claro", "TIM", "Vivo", "NuCel", "Brisanet", "Unifique", "Starlink")


def _unitario(o):
    """R$ por GB no movel, R$ por Mbps na fixa. Sem isso, oferta de
    franquia diferente nao se compara."""
    p = o.get("preco_promocional")
    if p is None:
        return "—", ""
    mbps = o.get("degrau_mbps")
    gb = o.get("franquia_anunciada_gb")
    if mbps:
        return ("%.2f" % (p / mbps)).replace(".", ","), "R$/Mbps"
    if gb:
        return ("%.2f" % (p / gb)).replace(".", ","), "R$/GB"
    return "—", ""


def _entrega(o, produto):
    """O que a oferta entrega, com as duas pernas do combo.

    Combo e fibra MAIS movel, e mostrar so os Mbps esconde metade da
    oferta: duas de 600 Mega parecem iguais quando uma traz 60 GB de
    movel e a outra nao traz movel nenhum.
    """
    base = o.get("destaque") or "—"
    gb = o.get("franquia_anunciada_gb")
    if produto == "combo" and gb and "GB" not in base.upper():
        return "%s + %s GB" % (base, gb)
    return base


def _bloco_produto(itens, produto, erro=None):
    """Todas as ofertas de um produto, agrupadas por operadora.

    CONSULTA QUE CAIU NAO E PRODUTO SEM OFERTA. As duas saiam como "Sem
    dados disponiveis para a praca de referencia", e distinguir uma da
    outra e justamente o que o cabecalho deste arquivo promete.
    """
    def chave(o):
        op = o.get("operadora")
        i = ORDEM.index(op) if op in ORDEM else len(ORDEM)
        return (i, o.get("preco_promocional") or 0)

    unidade = ""
    linhas = []
    anterior = None
    for o in sorted(itens, key=chave):
        valor, un = _unitario(o)
        unidade = unidade or un
        op = o.get("operadora")
        linhas.append([
            op if op != anterior else "",
            _curto(o.get("nome_oferta"), 40),
            _entrega(o, produto),
            _reais(o.get("preco_promocional")),
            valor,
        ])
        anterior = op
    return _tabela(
        ["Operadora", "Oferta", "Entrega", "Preço", unidade or "Unitário"],
        linhas,
        [24 * mm, 64 * mm, 28 * mm, 26 * mm, 36 * mm],
        vazio=("Não foi possível consultar as ofertas deste produto: %s"
               % erro) if erro
        else "Sem dados disponíveis para a praça de referência.")


def _unidade(e):
    """A unidade que o evento carrega, ja decidida pelo campo preenchido.

    Vem pronta do robo de proposito: calcular de novo aqui abriria a
    porta para o PDF e a mensagem discordarem sobre a mesma oferta.
    """
    return e.get("unidade") or ""


def _versao(r):
    """Como a versao da oferta mudou, em portugues.

    O texto vem pronto do robo - ver BUNDLE em robo.py. Monta-lo aqui
    faria o PDF e a mensagem poderem divergir sobre a mesma oferta.
    """
    de, para = r.get("bundle_antes"), r.get("bundle_agora")
    if de and para and de != para:
        return "%s → %s" % (de, para)
    if r.get("versao_mudou"):
        return "outra versão da oferta"
    return "—"


def _bloco_remodeladas(itens, vazio):
    """Oferta que voltou a vitrine mudada por dentro.

    Preco e entrega mudando juntos e o movimento de maior efeito sobre o
    cliente - paga mais e recebe menos - e era o unico que a mensagem
    NEGAVA antes de existir o detector: nenhum dos outros conseguia
    parear a oferta, e o aviso do dia dizia "nenhuma mudanca de preco,
    composicao ou nome".
    """
    linhas = []
    for r in (itens or []):
        # O TEXTO VEM PRONTO DO ROBO. Montado aqui, divergia da
        # mensagem na mesma oferta: ela dizia "entrega nao lida" e esta
        # tabela imprimia "None" (terceira auditoria, N4).
        preco = r.get("texto_preco") or _reais(r.get("agora_preco"))
        entrega = r.get("texto_entrega") or "—"
        linhas.append([
            r.get("operadora"),
            _curto(r.get("nome"), 30),
            preco,
            entrega,
            _versao(r),
            r.get("onde") or "—",
        ])
    return _tabela(
        ["Operadora", "Oferta", "Preço", "Entrega", "Versão", "Praças"],
        linhas,
        [19 * mm, 30 * mm, 30 * mm, 24 * mm, 37 * mm, 38 * mm],
        vazio=vazio)


def _bloco_grades(d):
    """A escada de precos reorganizada, vista pelos dois lados."""
    linhas = []
    for g in d.get("grades") or []:
        u = _unidade(g)
        movimento = []
        for preco, antes_v, agora_v in g.get("saltos") or ():
            movimento.append("%s passou a entregar %s %s (antes %s)"
                             % (_reais(preco), agora_v, u, antes_v))
        for entrega, antes_p, agora_p in g.get("precos") or ():
            movimento.append("%s %s passou a custar %s (antes %s)"
                             % (entrega, u, _reais(agora_p), _reais(antes_p)))
        linhas.append([
            g.get("operadora"),
            g.get("produto"),
            "; ".join(movimento) or "—",
            g.get("onde") or "—",
        ])
    return _tabela(
        ["Operadora", "Produto", "Movimento observado", "Praças"], linhas,
        [22 * mm, 22 * mm, 92 * mm, 42 * mm],
        vazio="Nenhuma reorganização de grade identificada.")


def _bloco_voltaram(d):
    """Entrega que reapareceu com outro preco, dias depois de sair."""
    linhas = []
    for v in d.get("voltaram") or []:
        quando = str(v.get("quando") or "")
        if len(quando) == 10:
            quando = datetime.fromisoformat(quando).strftime("%d/%m")
        linhas.append([
            v.get("operadora"),
            v.get("produto"),
            ("%s %s" % (v.get("entrega"), _unidade(v))).strip(),
            quando or "—",
            _reais(v.get("antes")),
            _reais(v.get("agora")),
            _pc(v.get("antes"), v.get("agora")),
            v.get("onde") or "—",
        ])
    return _tabela(
        ["Operadora", "Produto", "Entrega", "Última venda", "Preço então",
         "Atual", "Var.", "Praças"],
        linhas,
        [19 * mm, 19 * mm, 19 * mm, 19 * mm, 21 * mm, 19 * mm, 12 * mm,
         30 * mm],
        vazio="Nenhum degrau retornou à vitrine com preço diferente.")


def _bloco_renomeadas(d):
    """Oferta que trocou de nome, e o preco que ela levou na troca.

    A COLUNA DA LEITURA ALTERNATIVA. Quando a oferta do dia anterior
    podia ser pareada tambem por nome, havia duas leituras do mesmo
    fato e o robo usou a chave de continuidade, que e a identidade mais
    forte. A outra leitura fica registrada aqui: eleger uma e publicar
    como fato unico seria esconder que havia duas.
    """
    linhas = []
    for m in d.get("renomeadas") or []:
        a, at = m["antes"], m["atual"]
        outras = m.get("outras_leituras") or []
        outra = outras[0] if outras else {}
        linhas.append([
            at.get("operadora"),
            _curto(a.get("nome_oferta"), 34),
            _curto(at.get("nome_oferta"), 34),
            _reais(a.get("preco_promocional")),
            _reais(at.get("preco_promocional")),
            (("%s a %s%s" % (_curto(outra.get("nome"), 20),
                             _reais(outra.get("preco")),
                             (" (+%d)" % (len(outras) - 1))
                             if len(outras) > 1 else ""))
             if outra else "—"),
            m.get("onde") or "—",
        ])
    return _tabela(
        ["Operadora", "Nome anterior", "Nome atual", "Preço antes",
         "Preço atual", "Outra leitura possível", "Praças"],
        linhas,
        [19 * mm, 30 * mm, 30 * mm, 18 * mm, 18 * mm, 33 * mm, 30 * mm],
        vazio="Nenhuma oferta mudou de nome.")


def _bloco_cobertura(d):
    """Quanto da vitrine de hoje foi efetivamente comparada com ontem.

    SEM ESTE NUMERO, O SILENCIO NAO SE DISTINGUE DA CEGUEIRA. "Nenhuma
    variacao identificada" sobre 12% da vitrine e sobre 94% dela sao
    duas afirmacoes diferentes, e as duas saiam escritas igual. A
    operadora cuja serie partiu aparece aqui antes de alguem precisar
    desconfiar.
    """
    cob = d.get("cobertura")
    if not cob:
        return _tabela(["Operadora", "Ofertas com par", "Total", "Cobertura"],
                       [], [44 * mm, 44 * mm, 44 * mm, 46 * mm],
                       vazio="Comparação não realizada na data.")
    linhas = []
    for op, (pares, total) in sorted(cob["por_operadora"].items()):
        linhas.append([op, str(pares), str(total),
                       "%d%%" % round(100.0 * pares / total) if total else "—"])
    linhas.append(["Total", str(cob["pares"]), str(cob["hoje"]),
                   "%d%%" % round(100.0 * cob["fracao"])])
    return _tabela(["Operadora", "Ofertas com par", "Total", "Cobertura"],
                   linhas, [44 * mm, 44 * mm, 44 * mm, 46 * mm])


def _bloco_denuncias(d):
    """O que o vigia achou de estranho no dado do dia.

    A mensagem leva so o achado grave, porque e o que muda o que a
    pessoa faz. Aqui vai a lista inteira, que e onde se procura detalhe.
    """
    linhas = [[("Grave" if g == "grave" else "Atenção"), _curto(t, 92)]
              for g, t in (d.get("denuncias") or [])]
    return _tabela(["Gravidade", "O que foi observado"], linhas,
                   [26 * mm, 152 * mm],
                   vazio="Nenhuma anomalia observada nos dados do dia.")


def _bloco_coleta(d):
    linhas = []
    for c in sorted(d.get("coletas") or [], key=lambda x: x["operadora"]):
        ok = c.get("sucesso")
        linhas.append([
            c.get("operadora"),
            "%d de %d" % (c.get("pracas_ok") or 0, c.get("pracas_pedidas") or 0),
            str(c.get("ofertas") or 0),
            "Concluída" if ok else "Falha",
        ])
    for op in d.get("sem_registro") or []:
        linhas.append([op, "—", "—", "Sem registro"])
    return _tabela(["Coletor", "Praças", "Ofertas", "Situação"], linhas,
                   [44 * mm, 36 * mm, 36 * mm, 62 * mm],
                   vazio="Sem registro de coleta para a data.")


# ------------------------------------------------------------------ montagem

def gerar(dados, entradas, caminho):
    """Escreve o PDF e devolve o caminho."""
    dia = datetime.fromisoformat(dados["dia"]).strftime("%d/%m/%Y")
    doc = BaseDocTemplate(
        caminho, pagesize=A4,
        leftMargin=MARGEM, rightMargin=MARGEM,
        topMargin=22 * mm, bottomMargin=16 * mm,
        title="Price Tracker TMT - relatorio de %s" % dia,
        author="Price Tracker TMT")
    quadro = Frame(MARGEM, 16 * mm, LARGURA, A4[1] - 38 * mm, id="corpo",
                   leftPadding=0, rightPadding=0, topPadding=0,
                   bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="pagina", frames=[quadro],
                                       onPage=_cabecalho_pagina)])

    hist = []
    hist.append(Paragraph("Relatório de %s" % dia, ESTILOS["titulo"]))
    hist.append(Paragraph(
        "Comparação com %s. Preços de tabela publicados nas vitrines, "
        "sem descontos condicionados."
        % datetime.fromisoformat(dados["ontem"]).strftime("%d/%m"),
        ESTILOS["subtitulo"]))
    hist.append(Spacer(1, 2))

    # a coleta vem primeiro quando ela falhou: numero de dia incompleto
    # engana mais do que informa, e o leitor precisa saber antes de ler
    #
    # CONSULTA QUE CAIU NAO E COLETA INCOMPLETA. Sem esta distincao o
    # relatorio listava as nove operadoras como "Sem registro" por causa
    # de um 503 na leitura da tabela - afirmando que nada foi coletado
    # num dia em que tudo foi (N3).
    if dados.get("erro_coleta"):
        hist += _secao("Cobertura da coleta")
        hist.append(Paragraph(
            "Não foi possível consultar o registro de coleta da data "
            "(%s). As ofertas apresentadas a seguir foram lidas "
            "normalmente; não é possível afirmar, a partir desta "
            "edição, se a rotina de coleta cobriu todas as operadoras e "
            "praças previstas." % str(dados["erro_coleta"])[:120],
            ESTILOS["corpo"]))
    elif dados.get("falhas") or dados.get("sem_registro") or not dados.get("coletas"):
        hist += _secao("Cobertura da coleta")
        hist.append(Paragraph(
            "A coleta do dia não cobriu todas as operadoras ou praças "
            "previstas. Os dados a seguir referem-se exclusivamente ao "
            "universo efetivamente coletado.",
            ESTILOS["corpo"]))
        hist.append(_bloco_coleta(dados))

    if dados.get("erro_comparacao"):
        hist += _secao("Comparação indisponível")
        hist.append(Paragraph(str(dados["erro_comparacao"]), ESTILOS["corpo"]))
    else:
        hist.append(_com_titulo("Mudanças de preço", _bloco_precos(dados)))

        hist.append(_com_titulo(
            "Ofertas reapresentadas com outra configuração",
            Paragraph("Ofertas cujo preço e cuja franquia ou velocidade "
                      "foram alterados na mesma data, ou cuja versão foi "
                      "modificada sem variação de preço ou de entrega. O "
                      "pareamento utiliza o nome da oferta na mesma praça, "
                      "e aplica-se exclusivamente aos casos em que resta "
                      "uma única oferta correspondente em cada data.",
                      ESTILOS["corpo"]),
            _bloco_remodeladas(
                dados.get("remodeladas"),
                "Nenhuma oferta foi reapresentada com outra configuração.")))

        # AS QUE A LEITURA EXPLICA, SEPARADAS DAS QUE O MERCADO EXPLICA.
        # Misturar as duas numa tabela so transformaria mudanca de
        # parser em movimento de operadora, que e a atribuicao errada
        # mais facil de fazer aqui.
        hist.append(_com_titulo(
            "Alterações atribuíveis à leitura dos dados",
            Paragraph("Ofertas cuja versão foi alterada sem variação de "
                      "preço ou de entrega, em circunstâncias que indicam "
                      "modificação no procedimento de leitura e não no "
                      "mercado: ocorrência simultânea em mais de uma "
                      "operadora, ou restrita a uma minoria das praças em "
                      "que a oferta é comercializada. Registram-se aqui "
                      "para que a descontinuidade na série seja "
                      "identificável.", ESTILOS["corpo"]),
            _bloco_remodeladas(
                dados.get("leitura"),
                "Nenhuma alteração atribuível à leitura dos dados.")))

        # "PERMANECEU INALTERADO" E UMA AFIRMACAO, e ela nao vale para a
        # oferta cujo preco nao foi lido num dos dois dias - que e um
        # caso que o detector de composicao aceita, porque ele nasce
        # quando o ramo de preco nao disparou (W1). O paragrafo diz as
        # duas possibilidades e a coluna de cada linha diz qual e.
        hist.append(_com_titulo(
            "Alterações de composição sem variação de preço",
            Paragraph("Ofertas cuja composição de serviços inclusos foi "
                      "modificada sem que se tenha apurado variação de "
                      "preço em relação ao dia anterior. A identificação "
                      "decorre da comparação diária do conjunto de "
                      "serviços registrado em cada oferta. A coluna "
                      "Preço indica o valor apurado ou, quando a leitura "
                      "de alguma das datas não o registrou, essa "
                      "circunstância.", ESTILOS["corpo"]),
            _bloco_composicao(dados)))

        hist.append(_com_titulo(
            "Reorganização de grade",
            Paragraph("Alterações na relação entre preço e entrega no "
                      "portfólio de uma operadora: mesmo preço passando a "
                      "corresponder a outra franquia ou velocidade, ou "
                      "mesma franquia ou velocidade passando a "
                      "corresponder a outro preço.", ESTILOS["corpo"]),
            _bloco_grades(dados)))

        hist.append(_com_titulo(
            "Degraus retomados com preço diferente",
            Paragraph("Franquias ou velocidades ausentes da vitrine no dia "
                      "anterior e reapresentadas na data, com preço "
                      "distinto do praticado na última oferta registrada "
                      "nos 45 dias precedentes.", ESTILOS["corpo"]),
            _bloco_voltaram(dados)))

        hist.append(_com_titulo(
            "Alterações de denominação",
            Paragraph("Ofertas identificadas pela mesma chave de série e "
                      "praça, apresentadas sob outra denominação comercial.",
                      ESTILOS["corpo"]),
            _bloco_renomeadas(dados)))

    # O link do painel, entre a parte comparativa e as tabelas de
    # catalogo: quem quiser a serie historica, o grafico ou outra praca
    # sai daqui. Clicavel no PDF.
    hist.append(Spacer(1, 4))
    hist.append(Paragraph(
        'Link do IBBA TMT Price Tracker: '
        '<link href="%s"><font color="#FF5000">%s</font></link>'
        % (PAINEL, PAINEL.replace("https://", "")), ESTILOS["corpo"]))
    hist.append(Spacer(1, 2))

    # A SECAO DO PRODUTO NAO DESAPARECE. Com "if not itens: continue", o
    # produto sem oferta simplesmente nao existia no PDF - e quem le nao
    # tem como distinguir "a Claro nao tem below-the-line hoje" de "o
    # relatorio quebrou no meio". A tabela vazia ja tem a frase para
    # esse caso, e o cabecalho deste arquivo promete usa-la.
    for chave, titulo in PRODUTOS:
        itens = entradas.get(chave) or []
        hist.append(_com_titulo(
            "%s — ofertas em São Paulo" % titulo,
            _bloco_produto(itens, chave,
                           (dados.get("erros_catalogo") or {}).get(chave))))

    if not (dados.get("falhas") or dados.get("sem_registro")):
        hist.append(_com_titulo("Estado da coleta", _bloco_coleta(dados)))

    # A CONFERENCIA DO DADO, e nao do mercado. Sao perguntas diferentes:
    # as tabelas acima dizem o que mudou, esta diz se o que foi coletado
    # faz sentido. Um dia pode estar calmo numa e podre na outra.
    hist.append(_com_titulo(
        "Cobertura da comparação",
        Paragraph("Proporção das ofertas registradas na data que foram "
                  "identificadas também no dia anterior, por operadora. "
                  "A ausência de variações apuradas somente é "
                  "interpretável à luz desta proporção: ofertas sem "
                  "correspondência no dia anterior não integram a "
                  "comparação.", ESTILOS["corpo"]),
        _bloco_cobertura(dados)))

    hist.append(_com_titulo(
        "Conferência dos dados coletados",
        Paragraph("Verificações automáticas sobre a coleta do dia, "
                  "comparada com os sete dias anteriores: preços fora da "
                  "faixa de varejo, ofertas sem velocidade ou franquia, "
                  "ofertas indistinguíveis entre si, variação no volume "
                  "por operadora e saltos de preço.", ESTILOS["corpo"]),
        _bloco_denuncias(dados)))

    if dados.get("ponto_cego"):
        hist.append(Spacer(1, 6))
        hist.append(Paragraph(
            "<b>Nota metodológica.</b> %s" % dados["ponto_cego"],
            ESTILOS["nota"]))

    # O PONTO CEGO DO DIA ANTERIOR e nota, e nao manchete: o efeito dele
    # sobre esta data ja esta na cobertura - as ofertas de hoje que
    # perderam o par. Dizer "N ofertas ficaram fora da comparação de
    # hoje" com o número de ontem seria falso (auditoria 2, A5).
    if dados.get("ponto_cego_ontem"):
        hist.append(Spacer(1, 4))
        hist.append(Paragraph(
            "<b>Nota metodológica (data anterior).</b> %s"
            % dados["ponto_cego_ontem"], ESTILOS["nota"]))

    hist.append(Spacer(1, 8))
    hist.append(Paragraph(
        "Relatório gerado automaticamente a partir da coleta diária. "
        "Série histórica completa em %s" % PAINEL.replace("https://", ""),
        ESTILOS["nota"]))

    doc.build(hist)
    return caminho
