# -*- coding: utf-8 -*-
u"""A OFERTA QUE SAI DA VITRINE NAO DEIXAVA LINHA NENHUMA.

Em 01/11/2026 a Vivo Lite Anual II e a Mensal II desapareceram das 20
pracas, e a mensagem do dia disse "Nenhuma mudanca de preco, composicao
ou nome". Ausencia de oferta era a unica mudanca de portfolio sem
detector: os sete existentes comparam a oferta de hoje com a de ontem, e
quando ela nao esta em hoje nao ha o que comparar. O degrau que VOLTA
tinha detector desde setembro; o que SAI, nenhum.

Pedido de quem le, em 03/11/2026: "se alguma oferta for removida, preciso
saber no dia: qual oferta foi removida e em qual praca".

MEDIR PRIMEIRO FOI O QUE DESENHOU A REGRA. A definicao ingenua - chave
que estava ontem e nao esta hoje - rende 2.560 linhas em 34 dias de dado
publicado, e quase nenhuma e saida:

    2.560 cruas -> 377 com os filtros obvios -> 35 apertando nome e
    duracao -> 22 comparando por operadora e nao por balde

Cada classe aqui fixa um dos cortes, com o caso real que o obriga.
"""
import datetime
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))

import robo                                                   # noqa: E402
from _apoio import HOJE, ONTEM, dados, montar, oferta         # noqa: E402

try:
    import relatorio
except Exception:                                             # pragma: no cover
    relatorio = None

ANTES = ["2026-10-18", "2026-10-19"]          # dentro da janela do vigia


def pracas(n=3):
    from coletores.pracas import PRACAS, rotulo
    return [rotulo(p) for p in PRACAS][:n]


def vivo(nome="Vivo Lite Anual II", preco=30.0, data=HOJE, onde=None,
         produto="btl", gb=30):
    return [oferta(operadora="Vivo", produto=produto, nome=nome,
                   preco=preco, gb=gb, praca=p, data=data,
                   chave="Vivo|%s|%dgb|simples" % (produto, gb))
            for p in (onde or pracas(3))]


def SOBROU(onde):
    """Uma oferta qualquer para o dia nao ficar VAZIO.

    Dia sem captura nenhuma e outro estado, e a mensagem dele e outra
    ("nenhuma oferta foi capturada hoje"). O que se mede aqui e a oferta
    que SAIU de um dia que teve coleta.
    """
    return vivo(nome="Vivo Lite Outro", data=HOJE, onde=onde, gb=77)


def historia(nome="Vivo Lite Anual II", onde=None, **kw):
    """A mesma oferta nos dias anteriores, para ela ter vivido o bastante."""
    linhas = []
    for dia in ANTES:
        linhas += vivo(nome=nome, data=dia, onde=onde, **kw)
    return linhas


class ASaidaSaiNaMensagem(unittest.TestCase):

    def test_diz_qual_oferta_e_em_que_praca(self):
        onde = pracas(3)
        t = montar(vivo(data=ONTEM, onde=onde), SOBROU(onde),
                   extras=historia(onde=onde))
        self.assertIn("saiu da vitrine", t)
        self.assertIn("Vivo Lite Anual II", t)
        self.assertIn("em todas as 3 pra", t)

    def test_diz_o_preco_que_a_oferta_tinha(self):
        onde = pracas(3)
        t = montar(vivo(data=ONTEM, onde=onde, preco=41.9), SOBROU(onde),
                   extras=historia(onde=onde, preco=41.9))
        self.assertIn("estava a 41,90", t)

    def test_conta_como_mudanca_do_dia(self):
        """O dia em que a unica novidade e uma saida nao pode abrir com
        "nenhuma mudanca" - foi o que 01/11/2026 fez."""
        onde = pracas(3)
        t = montar(vivo(data=ONTEM, onde=onde), SOBROU(onde),
                   extras=historia(onde=onde))
        self.assertIn("1 mudan", t)
        self.assertNotIn("Nenhuma mudan", t)

    def test_o_dia_limpo_declara_que_olhou_a_saida(self):
        """A frase do dia parado enumera o que foi conferido, e a saida
        passou a estar na conta."""
        t = montar(vivo(data=ONTEM), vivo(data=HOJE))
        self.assertIn("nome ou saída de oferta", t)


class OQuantoTempoAOfertaViveu(unittest.TestCase):
    """O numero de dias e cego alem da janela, e a frase tem de dizer.

    A consulta olha oito dias. A Vivo Lite que saiu em 01/11/2026 vivia
    25, e a primeira versao desta linha dizia "depois de 7 dias na
    vitrine": o TAMANHO DA JANELA afirmado como IDADE da oferta. Quando
    os dois numeros batem, a frase passa a dizer "pelo menos".
    """

    def test_oferta_mais_velha_que_a_janela_diz_pelo_menos(self):
        onde = pracas(2)
        janela = []
        for n in range(1, 8):
            dia = (datetime.date.fromisoformat(HOJE)
                   - datetime.timedelta(days=n)).isoformat()
            janela += vivo(data=dia, onde=onde)
        ontem = [l for l in janela if l["data_captura"] == ONTEM]
        extras = [l for l in janela if l["data_captura"] != ONTEM]
        t = montar(ontem, SOBROU(onde), extras=extras)
        self.assertIn("pelo menos 7 dias", t)
        self.assertNotIn("depois de 7 dias", t)

    def test_oferta_mais_nova_que_a_janela_diz_o_numero(self):
        """A JANELA E O QUE FOI OLHADO, e nao um numero fixo. Com sete
        dias de dado e a oferta em tres deles, o numero e o numero. Com
        a oferta em todos os dias olhados, a frase volta a ser "pelo
        menos" - inclusive quando o dado tem tres dias, que foi o que a
        primeira versao deste teste leu como defeito e nao era.
        """
        onde = pracas(2)
        fundo = []
        for n in range(1, 8):
            dia = (datetime.date.fromisoformat(HOJE)
                   - datetime.timedelta(days=n)).isoformat()
            fundo += vivo(nome="Vivo Lite Fundo", data=dia, onde=onde, gb=11)
        hoje_fundo = vivo(nome="Vivo Lite Fundo", data=HOJE, onde=onde, gb=11)
        ontem = (vivo(data=ONTEM, onde=onde)
                 + [l for l in fundo if l["data_captura"] == ONTEM])
        extras = ([l for l in fundo if l["data_captura"] != ONTEM]
                  + historia(onde=onde))
        t = montar(ontem, SOBROU(onde) + hoje_fundo, extras=extras)
        self.assertIn("depois de 3 dias na vitrine", t)
        self.assertNotIn("pelo menos", t)


class OsCincoCortesComOCasoRealAtras(unittest.TestCase):

    def _saidas(self, ontem, hoje, extras=()):
        return dados(ontem, hoje, extras=extras).get("saidas") or []

    def test_praca_sem_coleta_hoje_nao_rende_saida(self):
        """13/10/2026, Belo Horizonte: a coleta da vespera falhou e o
        reajuste da Claro alcancou BH como as outras 19 - o que faltou
        foi com que comparar. Praca que nao foi olhada hoje nao pode
        render afirmacao sobre hoje."""
        tres = pracas(3)
        ontem = vivo(data=ONTEM, onde=tres)
        # hoje a operadora so trouxe a primeira praca, e com outra oferta
        hoje = vivo(nome="Vivo Lite Novo", data=HOJE, onde=tres[:1], gb=99)
        saidas = self._saidas(ontem, hoje, extras=historia(onde=tres))
        self.assertEqual(len(saidas), 1)
        self.assertEqual(saidas[0]["pracas"], tres[:1],
                         "a saida so pode falar da praca que foi coletada")
        self.assertEqual(saidas[0]["universo"], 1)

    def test_troca_de_balde_nao_e_saida(self):
        """21/10/2026: "SET26 500MB + TELECINE" estava em fibra em 20/10
        e em combo em 21/10. Mesma oferta, classificador nosso - e vinte
        das 35 saidas do corte anterior eram isso."""
        onde = pracas(3)
        ontem = vivo(nome="SET26 500MB + TELECINE", produto="fibra",
                     data=ONTEM, onde=onde)
        hoje = vivo(nome="SET26 500MB + TELECINE", produto="combo",
                    data=HOJE, onde=onde)
        extras = historia(nome="SET26 500MB + TELECINE", produto="fibra",
                          onde=onde)
        self.assertEqual(self._saidas(ontem, hoje, extras=extras), [])

    def test_recarimbo_de_mes_nao_e_saida(self):
        """A Brisanet recarimba o catalogo todo mes. "AGO26 500MB + 20GB"
        e "[NOV] 500MB + 20GB" sao a mesma oferta, e sem tirar a safra
        80% das saidas medidas eram renomeacao."""
        onde = pracas(3)
        ontem = vivo(nome="AGO26 500MB + 20GB", data=ONTEM, onde=onde)
        hoje = vivo(nome="[NOV] 500MB + 20GB", data=HOJE, onde=onde, gb=31)
        extras = historia(nome="AGO26 500MB + 20GB", onde=onde)
        self.assertEqual(self._saidas(ontem, hoje, extras=extras), [])

    def test_renumeracao_do_nome_nao_e_saida(self):
        """27/10/2026: o Ultracombo 3 e o 2 "sairam" e o 7 e o 5
        entraram - a TIM renumerou a linha. Nome parecido entrando no
        mesmo dia e renomeacao, e tem detector proprio.

        Este e o caso que o corte da safra NAO pega: "Ultracombo 3" e
        "Ultracombo 7" nao tem carimbo de mes, e so a semelhanca entre
        os nomes separa renumeracao de saida.
        """
        onde = pracas(3)
        ontem = vivo(nome="TIM Ultracombo 3 600MEGA + 70GB", data=ONTEM,
                     onde=onde)
        hoje = vivo(nome="TIM Ultracombo 7 600MEGA + 70GB", data=HOJE,
                    onde=onde)
        extras = historia(nome="TIM Ultracombo 3 600MEGA + 70GB", onde=onde)
        self.assertEqual(self._saidas(ontem, hoje, extras=extras), [])

    def test_piscada_de_dois_dias_nao_e_saida(self):
        """A pagina do Vivo Lite respondeu com um conjunto em 2 pracas e
        outro nas 18 restantes na MESMA rodada de 03/11/2026. Oferta que
        viveu dois dias e ruido de pagina."""
        onde = pracas(3)
        ontem = vivo(data=ONTEM, onde=onde)
        um_dia_antes = vivo(data=ANTES[1], onde=onde)
        self.assertEqual(
            self._saidas(ontem, SOBROU(onde), extras=um_dia_antes), [])

    def test_sair_de_algumas_pracas_nao_e_saida(self):
        """Sair de parte das pracas e rotacao, e tem outro evento. A
        saida afirma portfolio, e portfolio nao sai pela metade."""
        cinco = pracas(5)
        ontem = vivo(data=ONTEM, onde=cinco)
        # AS CINCO PRACAS FORAM COLETADAS HOJE: duas ainda tem a oferta,
        # tres trazem outra. Sem as cinco coletadas, o filtro da praca
        # resolveria sozinho e este corte nao seria medido - foi o que a
        # primeira versao deste teste fez, e a mutacao do provador
        # passou verde.
        hoje = vivo(data=HOJE, onde=cinco[:2]) + SOBROU(cinco[2:])
        extras = historia(onde=cinco)
        self.assertEqual(self._saidas(ontem, hoje, extras=extras), [])

    def test_mas_sair_de_todas_as_comparaveis_e_saida(self):
        """O contraste do teste acima: se ela sai de todas as pracas que
        foram olhadas nos dois dias, saiu."""
        cinco = pracas(5)
        ontem = vivo(data=ONTEM, onde=cinco)
        hoje = vivo(nome="Vivo Lite Outro", data=HOJE, onde=cinco, gb=77)
        saidas = self._saidas(ontem, hoje, extras=historia(onde=cinco))
        self.assertEqual(len(saidas), 1)
        self.assertEqual(len(saidas[0]["pracas"]), 5)


class ASaidaNaoSaiDoIndice(unittest.TestCase):
    """O detector le as capturas cruas, e nao o indice.

    _indexar descarta o par indistinguivel - duas ofertas com a mesma
    chave, praca e nome, que ele nao sabe separar. Oferta descartada
    nunca esta em "hoje", entao sairia como saida TODO DIA, e o ponto
    cego do dia viraria noticia de portfolio.
    """

    def test_oferta_no_ponto_cego_nao_vira_saida(self):
        onde = pracas(2)
        iguais = []
        for dia in ANTES + [ONTEM, HOJE]:
            for p in onde:
                for preco in (30.0, 40.0):
                    iguais.append(oferta(
                        operadora="Vivo", produto="btl",
                        nome="Vivo Lite Anual II", preco=preco, gb=30,
                        praca=p, data=dia, chave="Vivo|btl|30gb|simples"))
        hoje = [l for l in iguais if l["data_captura"] == HOJE]
        ontem = [l for l in iguais if l["data_captura"] == ONTEM]
        extras = [l for l in iguais if l["data_captura"] in ANTES]
        d = dados(ontem, hoje, extras=extras)
        self.assertEqual(d.get("saidas") or [], [],
                         "o ponto cego do indice nao e saida de oferta")


@unittest.skipIf(relatorio is None, "reportlab nao instalado")
class ORelatorioTrazATabela(unittest.TestCase):

    def test_a_secao_lista_a_praca_inteira(self):
        import pypdf
        cinco = pracas(5)
        d = dados(vivo(data=ONTEM, onde=cinco), SOBROU(cinco),
                  extras=historia(onde=cinco))
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        self.assertIn("deixaram a vitrine", texto)
        self.assertIn("Vivo Lite Anual II", texto)

    def test_a_secao_diz_quando_nao_houve_saida(self):
        """Secao vazia e afirmacao, e a frase dela tem de dizer isso -
        nao pode sair em branco, como se nao tivessemos olhado."""
        import pypdf
        d = dados(vivo(data=ONTEM), vivo(data=HOJE))
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        self.assertIn("Nenhuma oferta deixou a vitrine", texto)


class OQueOFunilMediu(unittest.TestCase):
    """Os numeros que decidiram os cortes, escritos onde eles moram.

    Sem isto, os cinco filtros parecem defensivos demais, e o proximo a
    mexer tira um deles por achar que e paranoia. Cada um desses numeros
    saiu do dado publicado, nao de hipotese.
    """

    def test_as_constantes_sao_as_medidas(self):
        self.assertEqual(robo.VIVEU_PARA_SAIR, 3)
        self.assertEqual(robo.PARECIDO_E_RENOME, 0.75)

    def test_a_safra_que_a_serie_ignora(self):
        iguais = ("AGO26 500MB + 20GB", "[SET] 500MB + 20GB",
                  "[NOV] 500MB + 20GB", "500MB + 20GB")
        series = {robo._serie_sem_safra(n) for n in iguais}
        self.assertEqual(len(series), 1, series)

    def test_a_safra_nao_come_nome_de_oferta(self):
        """O corte da safra nao pode apagar palavra que faz parte do
        nome: "Vivo Total" e "Setembro Premiado" sobrevivem."""
        self.assertIn("vivo total", robo._serie_sem_safra("Vivo Total"))
        self.assertNotEqual(robo._serie_sem_safra("Claro Multi 600"),
                            robo._serie_sem_safra("Claro Multi 750"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
