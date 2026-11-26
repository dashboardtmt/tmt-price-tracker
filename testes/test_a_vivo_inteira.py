# -*- coding: utf-8 -*-
u"""A Vivo inteira: as paginas que a vitrine linka, a TV Completo do card, o
preco partido em dois, o adicional que nao e app e o Apple Music.

Auditoria contra o site de 26/11/2026. Os cards aqui seguem a marcacao real
medida nas paginas salvas naquele dia (unique-card, fieldset do interruptor,
radio da TV, o titulo co-branded do topo).
"""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import vivo  # noqa: E402


def card(plano, preco, codigos=("VIV202600000001",), meio="", depois="", destaque="25 GB"):
    nome = '<p class="unique-card__plan">%s</p>' % plano if plano else ""
    rgc = "".join('<a data-code-rgc="%s">x</a>' % c for c in codigos)
    return ('<div class="unique-card unique-card__bordered">%s'
            '<p class="unique-card__header-benefit-text-big">%s</p>%s'
            '<span data-price="" data-original-price="%s" class="total-card-price-value">%s</span>'
            '<span class="unique-card__price-new--side">/mês</span>%s%s</div>'
            % (nome, destaque, meio, preco, preco, rgc, depois))


ADICIONAL = ('<fieldset class="unique-card__switch"><label><span>+ 10 GB por R$ 5</span>'
             '<button class="unique-card__switch-hover"><span class="unique-card__switch-tooltip hide">'
             '10 GB de internet com Proteção McAfee por R$5</span></button></label></fieldset>')
RADIO_TV = ('<fieldset><legend>Selecionar assinatura:</legend>'
            '<input aria-label="Vivo TV Avançado" type="radio" name="1" data-value="MA==" data-rgc-number="1">'
            '<input aria-label="Vivo TV Completo" type="radio" name="1" data-value="MTI1" data-rgc-number="2">'
            '</fieldset>')


class _ComPagina(unittest.TestCase):

    def ler(self, html, produto="controle", url=None, sufixo=None):
        guarda = vivo.buscar
        vivo.buscar = lambda op, u, *a, **k: (200, html)
        try:
            return vivo.ler_vitrine(None, produto, url, sufixo)
        finally:
            vivo.buscar = guarda


class OCard(_ComPagina):

    def test_o_adicional_opcional_nao_e_app_incluso(self):
        u"""O Vivo Controle de R$ 59 saia com o McAfee, que so existe no
        adicional de R$ 5."""
        cards, _ = self.ler(card("Vivo Controle", "59", meio=ADICIONAL))
        self.assertNotIn("mcafee", vivo.apps_da_vitrine(cards[0]["plano"], cards[0]["texto"]))

    def test_o_apple_music_do_topo_depois_do_corte(self):
        u"""O "Apple Music Individual" do Controle Musica mora depois dos 12
        mil caracteres; o nome so diz "Musica"."""
        enche = '<div data-x="%s"></div>' % ("x" * 13000)
        topo = '<p class="unique-card__features-cobranded-title"> Apple Music Individual </p>'
        cards, _ = self.ler(card("Vivo Controle Música", "75", depois=enche + topo))
        lista = vivo.apps_da_vitrine(cards[0]["plano"], cards[0]["texto"])
        self.assertEqual(lista, ["apple_music"])

    def test_o_preco_partido_em_dois(self):
        u"""O Vivo Total V sem apps: o atributo diz "1" e o resto vem colado
        no "/mes" - R$ 1.190, e nao R$ 1."""
        html = ('<div class="unique-card "><p class="unique-card__plan">Vivo Total V</p>'
                '<span data-price="" data-original-price="1" class="total-card-price-value">1</span> '
                '<span class="unique-card__price-new--side" aria-hidden="true">190/mês</span></div>')
        cards, _ = self.ler(html, "combo")
        self.assertEqual(cards[0]["preco"], 1190.0)

    def test_a_tv_completo_do_card_com_o_codigo_dela(self):
        u"""Conferido no navegador em 26/11: 270 + 125 = 395, e o codigo e o
        segundo do card."""
        cards, _ = self.ler(card("Fibra + TV por assinatura", "270",
                                 codigos=("VIV202604060286", "VIV202604060066"),
                                 meio=RADIO_TV, destaque="600 Mega"), "fibra")
        por = {c["plano"]: c for c in cards}
        completo = por["Fibra + TV por assinatura (Vivo TV Completo)"]
        self.assertEqual(completo["preco"], 395.0)
        self.assertEqual(completo["codigo_anatel"], "VIV202604060066")
        self.assertEqual(por["Fibra + TV por assinatura"]["preco"], 270.0)

    def test_o_card_so_de_tv_completo_leva_o_pacote_no_nome(self):
        html = (card("Vivo Fibra + TV + Netflix", "315", meio="Vivo TV Avançado", destaque="600 Mega")
                + card("Vivo Fibra + TV + Netflix", "440", meio="Vivo TV Completo", destaque="600 Mega"))
        cards, _ = self.ler(html, "fibra", "x", "com Netflix")
        nomes = [c["plano"] for c in cards]
        self.assertIn("Vivo Fibra + TV + Netflix (Vivo TV Completo)", nomes)
        self.assertIn("Vivo Fibra + TV + Netflix", nomes)

    def test_o_sufixo_separa_as_homonimas(self):
        cards, _ = self.ler(card("Vivo Família 2", "265", destaque="120 GB"), "movel", "x", "sem apps")
        self.assertEqual(cards[0]["plano"], "Vivo Família 2 sem apps")
        cards, _ = self.ler(card("Vivo Fibra + TV + Netflix", "315", destaque="600 Mega"), "fibra", "x", "com Netflix")
        self.assertEqual(cards[0]["plano"], "Vivo Fibra + TV + Netflix")

    def test_o_pre_sem_servico_digital_sem_nome_de_plano(self):
        u"""Os cards abrem pela franquia, sem unique-card__plan."""
        cards, _ = self.ler(card(None, "16", meio="Válido por 15 dias", destaque="5 GB"),
                            "prepago", "x", u"sem serviço digital")
        self.assertEqual(cards[0]["plano"], u"Vivo Pré sem serviço digital")
        self.assertEqual(cards[0]["preco"], 16.0)

    def test_combo_na_pagina_do_pos_nao_entra_como_pos(self):
        cards, _ = self.ler(card("Vivo Total V 1 Giga", "1200", destaque="1 Giga"), "movel", "x", None)
        self.assertEqual(cards, [])


class OCaminhoDeProducao(unittest.TestCase):

    def setUp(self):
        self.guarda = {k: getattr(vivo, k) for k in (
            "navegador", "trocar_praca", "indice_catalogo", "ler_vitrine",
            "ler_lite", "PAUSA", "PAGINAS_EXTRAS", "regulamento")}
        self.addCleanup(lambda: [setattr(vivo, k, v) for k, v in self.guarda.items()])
        vivo.navegador = lambda: (None, None)
        vivo.trocar_praca = lambda op, c, u: True
        vivo.indice_catalogo = lambda op: ({}, [])
        vivo.ler_lite = lambda op, hoje, avisos=None: ([], None)
        vivo.regulamento = lambda op, codigo: None
        vivo.PAUSA = 0
        vivo.PAGINAS_EXTRAS = (("movel", "http://extra/sem-apps", "sem apps"),)
        self.falhar = False

        def ler(op, produto, url=None, sufixo=None):
            base = {"destaque": "50 GB", "codigos_anatel": None, "texto": "x"}
            if url is None:
                return ([dict(base, plano="Vivo Pós", preco=150.0, codigo_anatel="VIVA")]
                        if produto == "movel" else []), None
            if self.falhar:
                return None, "HTTP 403"
            return [dict(base, plano="Vivo Pós sem apps", preco=145.0, codigo_anatel="VIVB"),
                    dict(base, plano="Vivo Pós sem apps", preco=150.0, codigo_anatel="VIVA")], None
        vivo.ler_vitrine = ler

    def test_a_pagina_extra_entra_e_o_mesmo_codigo_nao_repete(self):
        d = vivo.coletar("Sao Paulo", "SP", verbose=False)
        movel = sorted((o["nome_oferta"], o["preco_promocional"]) for o in d["ofertas"])
        self.assertEqual(movel, [("Vivo Pós", 150.0), ("Vivo Pós sem apps", 145.0)])

    def test_pagina_extra_que_falha_tira_o_produto_da_praca(self):
        self.falhar = True
        d = vivo.coletar("Sao Paulo", "SP", verbose=False)
        self.assertFalse([o for o in d["ofertas"] if o["produto"] == "movel"])
        self.assertTrue(any("fora da praca hoje" in a for a in d["avisos"]))


class ADeclaracaoPorPadrao(unittest.TestCase):
    u"""As ofertas novas da Vivo tem o nome das antigas mais um sufixo: a
    declaracao do dia da troca casa por padrao, e o reajuste da antiga
    homonima continua noticia."""

    def test_a_nova_sai_da_noticia_e_a_antiga_fica(self):
        import robo
        guarda = robo.LEITURA_DE_OFERTA_MUDOU_EM
        robo.LEITURA_DE_OFERTA_MUDOU_EM = {"2026-11-27": [{
            "quem": [("Vivo", "movel", u"re:sem apps$")], "texto": "leitura nova"}]}
        self.addCleanup(setattr, robo, "LEITURA_DE_OFERTA_MUDOU_EM", guarda)
        d = {"entradas": [{"operadora": "Vivo", "produto": "movel",
                           "nome_oferta": u"Vivo Família 2 sem apps"}],
             "precos": [{"atual": {"operadora": "Vivo", "produto": "movel",
                                   "nome_oferta": u"Vivo Família 2"}}]}
        d = robo._sem_o_relido("2026-11-27", d)
        self.assertEqual(d["entradas"], [])
        self.assertEqual(len(d["precos"]), 1)
        self.assertEqual(len(d["relidos"]), 1)


if __name__ == "__main__":
    unittest.main()
