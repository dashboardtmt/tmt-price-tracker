# -*- coding: utf-8 -*-
u"""O card de comparacao da TIM, o formato que o GitHub recebe desde 26/11/2026.

27/11/2026, a coleta das 06:00: nenhum card das paginas do TIM Black, do
Familia e da Ultrafibra nas 20 pracas, e o Familia Plus na mensagem a
R$ 284,99 - "entrega deixou de ser lida (era 180)" -, sem a TIM ter mudado
preco nenhum. Daqui, minutos depois, as tres paginas davam 4, 6 e 8 cards.

A sonda de pagina, rodada no servidor do GitHub, mostrou o que so ele via:
a pagina montada a 1h de 27/11 troca o <tim-card-pricing-offer>, com tudo
em atributo, por <article class="oferta-teaser" about="/rj/node/N"> com o
nome e a franquia e SEM preco nem logo. Preco, riscado, UFs e apps moram no
JSON da pagina, no mesmo no - e sao os mesmos campos que o card antigo
imprimia em atributo, medido card a card.

E o preco falso veio do carrossel velho da pagina de pos-pago, que
preenchia o buraco quando a pagina do plano falhava.

As fixtures sao recortes reais do que o GitHub recebeu em 27/11/2026: as
tres paginas de SP, a fibra de PE e o carrossel do pos.
"""
import io
import os
import re
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import tim  # noqa: E402

FIX = os.path.join(AQUI, "fixtures")


def _ler(nome):
    return io.open(os.path.join(FIX, nome), encoding="utf-8").read()


NOVA = {
    "familia": _ler("tim_teaser_familia_sp_2026-11-27.html"),
    "black": _ler("tim_teaser_black_sp_2026-11-27.html"),
    "fibra_sp": _ler("tim_teaser_fibra_sp_2026-11-27.html"),
    "fibra_pe": _ler("tim_teaser_fibra_pe_2026-11-27.html"),
}
ANTIGA = {
    "familia": _ler("tim_black_familia_2026-11-24.html"),
    "black": _ler("tim_black_2026-11-26.html"),
    "fibra": _ler("tim_fibra_cards_2026-11-26.html"),
}
CARROSSEL = _ler("tim_pos_carrossel_2026-11-27.html")

# o que o card mostra e o que a serie guarda - se um formato le diferente
# do outro em qualquer destes, a serie muda sem a TIM ter mudado
CAMPOS = ("nome_oferta", "preco_promocional", "preco_cheio", "degrau_mbps",
          "franquia_anunciada_gb", "franquia_contratual_gb", "apps", "apps_rotulo",
          "apps_planos", "nivel_bundle", "composicao", "destaque", "id_catalogo")


class _ComPaginas(unittest.TestCase):

    def setUp(self):
        guarda = (tim.buscar, tim.navegador, tim.PAUSA)
        self.paginas = {"familia": NOVA["familia"], "black": NOVA["black"],
                        "fibra": NOVA["fibra_sp"], "pos": CARROSSEL}

        def buscar(op, url, *a, **k):
            for fim, qual in (("/tim-black-familia", "familia"), ("/pos-pago/tim-black", "black"),
                              ("/tim-ultrafibra", "fibra"), ("/planos/pos-pago", "pos")):
                if url.endswith(fim):
                    return (200, self.paginas[qual])
            return (200, "")
        tim.buscar = buscar
        tim.navegador = lambda: None
        tim.PAUSA = 0

        def volta():
            tim.buscar, tim.navegador, tim.PAUSA = guarda
        self.addCleanup(volta)

    def ler(self, f, molde, uf, html):
        self.paginas[{tim.ler_familia: "familia", tim.ler_black: "black",
                      tim.ler_fibra_por_card: "fibra"}[f]] = html
        return f(None, molde % uf.lower(), uf)


class OCardNovoLeOMesmoQueOAntigo(_ComPaginas):
    u"""O mesmo leitor nos dois formatos: a fixture antiga (o card de 26/11 e
    de 24/11) e a nova (o teaser de 27/11) - a TIM nao mudou preco entre
    elas, entao tudo o que a serie guarda tem de sair igual."""

    def _iguais(self, f, molde, uf, antiga, nova):
        a, ea = self.ler(f, molde, uf, antiga)
        b, eb = self.ler(f, molde, uf, nova)
        self.assertIsNone(ea)
        self.assertIsNone(eb)
        da = dict((o["nome_oferta"], o) for o in a)
        db = dict((o["nome_oferta"], o) for o in b)
        self.assertEqual(sorted(da), sorted(db))
        for nome in da:
            for c in CAMPOS:
                self.assertEqual(da[nome].get(c), db[nome].get(c), "%s: %s" % (nome, c))
        return b

    def test_a_fibra_de_sao_paulo(self):
        b = self._iguais(tim.ler_fibra_por_card, tim.FIBRA, "SP",
                         ANTIGA["fibra"], NOVA["fibra_sp"])
        self.assertEqual(len(b), 8)

    def test_a_fibra_de_recife(self):
        u"""Outra UF, outra escada: o 600MEGA Paramount+ e o 500MEGA, sem o
        400 Mega de SP - as UFs saem de field_regioes, e nao do atributo ddd
        do teaser, que lista os 67 DDDs ate no card que so vale em SP."""
        b = self._iguais(tim.ler_fibra_por_card, tim.FIBRA, "PE",
                         ANTIGA["fibra"], NOVA["fibra_pe"])
        precos = dict((o["nome_oferta"], o["preco_promocional"]) for o in b)
        self.assertEqual(precos["TIM Ultrafibra 600MEGA Paramount+"], 109.99)
        self.assertEqual(precos["TIM Ultrafibra 500MEGA"], 89.99)
        self.assertNotIn("TIM Ultrafibra 400 Mega", precos)

    def test_o_card_de_sao_paulo_nao_vale_em_recife(self):
        u"""A pagina de SP lida para PE: o 400 Mega e os dois 700MEGA so valem
        em SP e no interior (field_regioes), e ficam fora; os cinco nacionais
        ficam."""
        b, erro = self.ler(tim.ler_fibra_por_card, tim.FIBRA, "PE", NOVA["fibra_sp"])
        self.assertIsNone(erro)
        self.assertEqual(sorted((o["nome_oferta"], o["preco_promocional"]) for o in b),
                         [("TIM Ultrafibra 1GIGA", 99.99), ("TIM Ultrafibra 1GIGA Max", 159.99),
                          ("TIM Ultrafibra 1GIGA Paramount+", 149.99),
                          ("TIM Ultrafibra 2GIGA Paramount+ + Max + Globoplay", 369.99),
                          ("TIM Ultrafibra 800MEGA YouTube Premium", 129.99)])

    def test_o_black(self):
        b = self._iguais(tim.ler_black, tim.BLACK, "SP", ANTIGA["black"], NOVA["black"])
        self.assertEqual(
            sorted((o["nome_oferta"], o["preco_promocional"], o["franquia_anunciada_gb"]) for o in b),
            [("TIM Black", 129.99, 80), ("TIM Black A Express", 119.99, 77),
             ("TIM Black B Express", 144.99, 92), ("TIM Black C Express", 164.99, 117),
             ("TIM Black Plus", 149.99, 110), ("TIM Black Premium", 169.99, 125)])

    def test_o_familia_pelo_total(self):
        u"""O preco do Familia e o TOTAL do principal (264,99), e nao o "por
        pessoa" (82) nem o field_preco_card_oferta (88, resto de campanha)."""
        b = self._iguais(tim.ler_familia, tim.FAMILIA, "SP", ANTIGA["familia"], NOVA["familia"])
        self.assertEqual(
            sorted((o["nome_oferta"], o["preco_promocional"], o["franquia_anunciada_gb"]) for o in b),
            [(u"TIM Black Família", 219.99, 150), (u"TIM Black Família Plus", 264.99, 180),
             (u"TIM Black Família Premium", 314.99, 210), (u"TIM Black Família VIP", 399.99, 250)])


class OQueOTeaserNaoTemNaoSeInventa(_ComPaginas):

    def test_teaser_sem_o_no_no_json_fica_fora_e_dito(self):
        u"""O teaser sem preco so vale com o no dele no JSON. Sem o no, nao ha
        preco - e o aviso conta quantos teasers ficaram sem."""
        so_teasers = re.sub(r'<script[^>]*drupal-settings-json[^>]*>.*?</script>', "",
                            NOVA["black"], flags=re.S)
        self.assertIn("oferta-teaser", so_teasers)
        planos, erro = self.ler(tim.ler_black, tim.BLACK, "SP", so_teasers)
        self.assertEqual(planos, [])
        self.assertIn("6 teaser(s) sem o no no JSON", erro)

    def test_o_aviso_diz_o_formato_que_a_pagina_tinha(self):
        planos, erro = self.ler(tim.ler_fibra_por_card, tim.FIBRA, "SP", "<html>nada</html>")
        self.assertIsNone(planos)
        self.assertIn("falhou", erro)
        self.assertIn("0 <tim-card-pricing-offer>, 0 teaser(s)", erro)

    def test_o_no_que_a_pagina_nao_lista_nao_entra(self):
        u"""Entra o que a pagina lista num teaser, nao o JSON inteiro: sem o
        teaser do Black Premium, o Premium nao sai da pagina do Black."""
        corte = NOVA["black"]
        ini = corte.index('about="/rj/node/54261"')
        ini = corte.rindex("<article", 0, ini)
        fim = corte.index("</article>", ini) + len("</article>")
        planos, erro = self.ler(tim.ler_black, tim.BLACK, "SP", corte[:ini] + corte[fim:])
        self.assertIsNone(erro)
        self.assertNotIn("TIM Black Premium", [o["nome_oferta"] for o in planos])
        self.assertEqual(len(planos), 5)


class OCaminhoDeProducao(_ComPaginas):
    u"""coletar() inteiro, com as tres paginas no formato novo e o carrossel
    velho do pos: e ele que grava, e e nele que o R$ 284,99 entrava."""

    def _coletar(self):
        r = tim.coletar("Sao Paulo", "SP", verbose=False)
        return r, dict((o["nome_oferta"], o) for o in r["ofertas"])

    def test_as_tres_paginas_entram_pelo_formato_novo(self):
        r, m = self._coletar()
        self.assertFalse([a for a in r["avisos"] if a.split(":")[0] in ("familia", "black", "fibra")])
        self.assertEqual(m[u"TIM Black Família Plus"]["preco_promocional"], 264.99)
        self.assertEqual(m[u"TIM Black Família Plus"]["franquia_anunciada_gb"], 180)
        self.assertEqual(m[u"TIM Black Família Plus"]["pagina"], "familia")
        self.assertEqual(m["TIM Black"]["franquia_anunciada_gb"], 80)
        self.assertEqual(len([o for o in r["ofertas"] if o["produto"] == "fibra"]), 8)

    def test_o_carrossel_nao_entra_nem_com_tudo_lido(self):
        r, _ = self._coletar()
        self.assertFalse([o for o in r["ofertas"] if o.get("pagina") == "pos-pago"])

    def test_sem_a_pagina_do_familia_o_preco_velho_nao_volta(self):
        u"""O caso de 27/11: a pagina do Familia sem card. O Familia Plus fica
        sem leitura no dia, dito no aviso, e nao a R$ 284,99 do carrossel."""
        self.paginas["familia"] = "<html>nada</html>"
        r, m = self._coletar()
        self.assertFalse([o for o in r["ofertas"] if o["preco_promocional"] == 284.99])
        self.assertNotIn(u"TIM Black Família Plus", m)
        self.assertTrue(any(a.startswith("familia:") for a in r["avisos"]))

    def test_o_carrossel_e_mesmo_o_do_preco_velho(self):
        u"""A fixture do pos e a fonte do numero da mensagem de 27/11."""
        self.paginas["pos"] = CARROSSEL
        pos, _ = tim.ler_cards_dinamicos(None, tim.POS % "sp", "SP")
        precos = dict((o["nome_oferta"], o["preco_promocional"]) for o in pos)
        self.assertEqual(precos[u"TIM Black Família Plus"], 284.99)


if __name__ == "__main__":
    unittest.main()
