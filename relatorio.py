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

MARGEM = 16 * mm
LARGURA = A4[0] - 2 * MARGEM

ESTILOS = {
    "titulo": ParagraphStyle(
        "titulo", fontName="Helvetica-Bold", fontSize=17, leading=20,
        textColor=PRETO, alignment=TA_LEFT, spaceAfter=1),
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
    "destaque": ParagraphStyle(
        "destaque", fontName="Helvetica-Bold", fontSize=22, leading=24,
        textColor=LARANJA),
}

PRODUTOS = (("controle", "Controle"), ("movel", "Pós-pago"),
            ("fibra", "Fibra"), ("combo", "Combo"), ("prepago", "Pré-pago"),
            ("btl", "Below-the-line"))


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


def _tabela(cabecalho, linhas, larguras, vazio="não houve"):
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
    canvas.rect(0, A4[1] - 22 * mm, A4[0], 22 * mm, stroke=0, fill=1)
    canvas.setFillColor(LARANJA)
    canvas.rect(0, A4[1] - 23 * mm, A4[0], 1 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(MARGEM, A4[1] - 13 * mm, "Price Tracker TMT")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#B9B2A6"))
    canvas.drawString(MARGEM, A4[1] - 18 * mm,
                      "Relatório diário · preços de varejo de telecom")
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

def _bloco_resumo(d):
    mud = d.get("mudancas_preco") or []
    comp = d.get("mudancas_composicao") or []
    renom = d.get("renomeadas") or []
    grades = d.get("grades") or []
    total = len(mud) + len(comp) + len(renom) + len(grades)
    col = d.get("coletas") or []

    cartoes = [[
        _p("<b>%d</b>" % total, "destaque"),
        _p("<b>%d</b>" % len(mud), "destaque"),
        _p("<b>%d</b>" % d.get("total_ofertas", 0), "destaque"),
        _p("<b>%d</b>" % len(col), "destaque"),
    ], [
        _p("mudanças no dia"), _p("delas, de preço"),
        _p("ofertas capturadas"), _p("coletores"),
    ]]
    larg = [LARGURA / 4.0] * 4
    return Table(cartoes, colWidths=larg, hAlign="LEFT", style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("TOPPADDING", (0, 0), (-1, 0), 2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ("LINEBELOW", (0, 1), (-1, 1), 0.5, BORDA),
    ]))


def _bloco_precos(d):
    linhas = []
    for m in sorted(d.get("mudancas_preco") or [],
                    key=lambda x: -abs((x["atual"]["preco_promocional"] or 0)
                                       - (x["antes"]["preco_promocional"] or 0))):
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
        ["Operadora", "Oferta", "Entrega", "Ontem", "Hoje", "Var.", "Onde"],
        linhas,
        [20 * mm, 46 * mm, 17 * mm, 20 * mm, 20 * mm, 14 * mm, 41 * mm],
        vazio="Nenhuma oferta mudou de preço de ontem para hoje.")


def _bloco_composicao(d):
    linhas = []
    for m in d.get("mudancas_composicao") or []:
        at = m["atual"]
        linhas.append([
            at.get("operadora"),
            _curto(at.get("nome_oferta"), 40),
            _reais(at.get("preco_promocional")),
            m.get("onde") or "—",
        ])
    return _tabela(
        ["Operadora", "Oferta", "Preço (igual)", "Onde"], linhas,
        [24 * mm, 64 * mm, 26 * mm, 64 * mm],
        vazio="Nenhuma oferta trocou de conteúdo mantendo o preço.")


def _bloco_entrada(entradas):
    linhas = []
    for chave, titulo in PRODUTOS:
        itens = entradas.get(chave) or []
        if not itens:
            continue
        for i, e in enumerate(itens):
            linhas.append([
                titulo if i == 0 else "",
                e.get("operadora"),
                _curto(e.get("nome_oferta"), 34),
                e.get("destaque") or "—",
                _reais(e.get("preco_promocional")),
            ])
    return _tabela(
        ["Produto", "Operadora", "Oferta", "Entrega", "Preço"], linhas,
        [26 * mm, 22 * mm, 60 * mm, 24 * mm, 46 * mm],
        vazio="Sem dado de entrada para a praça de referência.")


def _bloco_coleta(d):
    linhas = []
    for c in sorted(d.get("coletas") or [], key=lambda x: x["operadora"]):
        ok = c.get("sucesso")
        linhas.append([
            c.get("operadora"),
            "%d de %d" % (c.get("pracas_ok") or 0, c.get("pracas_pedidas") or 0),
            str(c.get("ofertas") or 0),
            "ok" if ok else "FALHOU",
        ])
    for op in d.get("sem_registro") or []:
        linhas.append([op, "—", "—", "SEM REGISTRO"])
    return _tabela(["Coletor", "Praças", "Ofertas", "Estado"], linhas,
                   [44 * mm, 36 * mm, 36 * mm, 62 * mm],
                   vazio="Nenhum registro de coleta hoje.")


# ------------------------------------------------------------------ montagem

def gerar(dados, entradas, caminho):
    """Escreve o PDF e devolve o caminho."""
    dia = datetime.fromisoformat(dados["dia"]).strftime("%d/%m/%Y")
    doc = BaseDocTemplate(
        caminho, pagesize=A4,
        leftMargin=MARGEM, rightMargin=MARGEM,
        topMargin=28 * mm, bottomMargin=16 * mm,
        title="Price Tracker TMT - relatorio de %s" % dia,
        author="Price Tracker TMT")
    quadro = Frame(MARGEM, 16 * mm, LARGURA, A4[1] - 44 * mm, id="corpo",
                   leftPadding=0, rightPadding=0, topPadding=0,
                   bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="pagina", frames=[quadro],
                                       onPage=_cabecalho_pagina)])

    hist = []
    hist.append(Paragraph("Relatório de %s" % dia, ESTILOS["titulo"]))
    hist.append(Paragraph(
        "Comparado com %s. Preços de tabela das vitrines, sem desconto "
        "condicionado." % datetime.fromisoformat(dados["ontem"]).strftime("%d/%m"),
        ESTILOS["subtitulo"]))
    hist.append(_bloco_resumo(dados))
    hist.append(Spacer(1, 4))

    # a coleta vem primeiro quando ela falhou: numero de dia incompleto
    # engana mais do que informa, e o leitor precisa saber antes de ler
    if dados.get("falhas") or dados.get("sem_registro") or not dados.get("coletas"):
        hist += _secao("Atenção: a coleta de hoje está incompleta")
        hist.append(Paragraph(
            "Operadora incompleta deixa buraco no dia, nunca zero. "
            "Os números abaixo valem só para o que foi coletado.",
            ESTILOS["corpo"]))
        hist.append(_bloco_coleta(dados))

    if dados.get("erro_comparacao"):
        hist += _secao("Não deu para comparar com ontem")
        hist.append(Paragraph(str(dados["erro_comparacao"]), ESTILOS["corpo"]))
    else:
        hist.append(_com_titulo("Mudanças de preço", _bloco_precos(dados)))

        hist.append(_com_titulo(
            "Mudanças de conteúdo com preço parado",
            Paragraph("A oferta manteve o preço e trocou o que entrega. É "
                      "repasse disfarçado, e só aparece porque a assinatura "
                      "dos serviços inclusos é comparada dia a dia.",
                      ESTILOS["corpo"]),
            _bloco_composicao(dados)))

    hist += _secao("Preço de entrada por produto (São Paulo)")
    hist.append(Paragraph(
        "O plano mais barato que cada operadora vende em cada produto, na "
        "praça de referência.", ESTILOS["corpo"]))
    hist.append(_bloco_entrada(entradas))

    if not (dados.get("falhas") or dados.get("sem_registro")):
        hist.append(_com_titulo("Estado da coleta", _bloco_coleta(dados)))

    if dados.get("ponto_cego"):
        hist.append(Spacer(1, 6))
        hist.append(Paragraph(
            "<b>Ponto cego.</b> %s" % dados["ponto_cego"], ESTILOS["nota"]))

    hist.append(Spacer(1, 8))
    hist.append(Paragraph(
        "Gerado automaticamente pelo robô do Price Tracker. O painel "
        "completo, com histórico e gráficos, está em "
        "tmt-price-tracker.vercel.app", ESTILOS["nota"]))

    doc.build(hist)
    return caminho
