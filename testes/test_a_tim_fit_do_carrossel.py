# -*- coding: utf-8 -*-
u"""O TIM Controle FIT lido do carrossel da pagina de controle, por praca.

Auditoria contra o site de 26/11/2026: a coleta lia o FIT pelas etiquetas
em PDF, e so a Mensal 1.0 ainda linka etiqueta - duas das tres ofertas
faltavam, e a entrada da linha saia a R$ 35 quando e R$ 30. A pagina vende o
FIT num carrossel com dois blocos: SP, SC, RN e CE, e as demais UFs, com
franquias diferentes. A pagina aqui segue a marcacao medida naquele dia.
"""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import tim_fit  # noqa: E402


def card(titulo, gb, preco, parcelas, modal):
    texto = ("Tenha %dGB por %sR$%s/mês, perfeito" % (gb, ("%sx " % parcelas) if parcelas else "", preco))
    return ('<tim-carousel-article-content class="card-conteudo" image-alt="x">'
            '<h2 class="coh-heading title" slot="secondary" > %s </h2> '
            '<h2 class="coh-heading text" slot="title" > %s </h2>'
            '<a href="" data-modal-open="%s" link>Saber mais</a></tim-carousel-article-content>'
            % (titulo, texto, modal))


def modal(nome, plano):
    return ('<div class="cpt_modal" id="%s" data-ic-section="sec-modal-beneficios" hidden>'
            '<p>Seu plano com XXGB/mês : %dGB do plano + 10GB bônus promo</p></div>' % (nome, plano))


PAGINA = (
    '<details regionalization-toggle="sp,sc,rn,ce"> Plano anual'
    + card("TIM Controle Fit Anual 2.0", 46, "30", 12, "modal-fit-anual-2.0-sp-sc-rn-ce")
    + card("TIM Controle Fit Mensal 1.0", 30, "35", None, "modal-fit-mensal-1.0-sp-sc-rn-ce")
    + card("TIM Controle Fit Mensal 2.0", 40, "45", None, "modal-fit-mensal-2.0-sp-sc-rn-ce")
    + '</details><details regionalization-toggle="ac,al,am,ba,pe,rs,rj,mg"> Plano anual'
    + card("TIM Controle Fit Anual 2.0", 40, "30", 12, "modal-fit-anual-2.0-demais-ufs")
    + card("TIM Controle Fit Mensal 1.0", 30, "35", None, "modal-fit-mensal-1.0-demais-ufs")
    + card("TIM Controle Fit Mensal 2.0", 35, "45", None, "modal-fit-mensal-2.0-demais-ufs")
    + '</details>'
    + modal("modal-fit-anual-2.0-sp-sc-rn-ce", 20) + modal("modal-fit-mensal-1.0-sp-sc-rn-ce", 15)
    + modal("modal-fit-mensal-2.0-sp-sc-rn-ce", 20) + modal("modal-fit-anual-2.0-demais-ufs", 20)
    + modal("modal-fit-mensal-1.0-demais-ufs", 15) + modal("modal-fit-mensal-2.0-demais-ufs", 20))


class OCarrossel(unittest.TestCase):

    def test_as_tres_ofertas_do_bloco_de_sp(self):
        lidas = [(o["nome_oferta"], o["franquia_anunciada_gb"], o["preco_promocional"])
                 for o in tim_fit.ler_carrossel(PAGINA, "sp")]
        self.assertEqual(lidas, [("TIM Controle Fit Anual 2.0", 46, 30.0),
                                 ("TIM Controle Fit Mensal 1.0", 30, 35.0),
                                 ("TIM Controle Fit Mensal 2.0", 40, 45.0)])

    def test_o_bloco_das_demais_ufs(self):
        por = {o["nome_oferta"]: o for o in tim_fit.ler_carrossel(PAGINA, "pe")}
        self.assertEqual(por["TIM Controle Fit Anual 2.0"]["franquia_anunciada_gb"], 40)
        self.assertEqual(por["TIM Controle Fit Mensal 2.0"]["franquia_anunciada_gb"], 35)

    def test_o_anual_tem_12_meses_e_a_garantida_vem_do_modal(self):
        por = {o["nome_oferta"]: o for o in tim_fit.ler_carrossel(PAGINA, "sp")}
        self.assertEqual(por["TIM Controle Fit Anual 2.0"]["fidelidade_meses"], 12)
        self.assertIsNone(por["TIM Controle Fit Mensal 1.0"]["fidelidade_meses"])
        self.assertEqual(por["TIM Controle Fit Mensal 1.0"]["franquia_contratual_gb"], 15)


class OCaminhoDeProducao(unittest.TestCase):

    def setUp(self):
        guarda = tim_fit._buscar
        self.pedidas = []

        def buscar(url, timeout=45):
            self.pedidas.append(url)
            return 200, PAGINA.encode("utf-8")
        tim_fit._buscar = buscar
        self.addCleanup(setattr, tim_fit, "_buscar", guarda)

    def test_por_praca_e_com_a_pagina_da_uf(self):
        self.assertFalse(tim_fit.NACIONAL)
        d = tim_fit.coletar("Recife", "PE", verbose=False)
        self.assertIn("/pe/", self.pedidas[0])
        self.assertEqual({o["praca"] for o in d["ofertas"]}, {"Recife/PE"})
        self.assertEqual({o["produto"] for o in d["ofertas"]}, {"btl"})
        self.assertEqual(min(o["preco_promocional"] for o in d["ofertas"]), 30.0)


if __name__ == "__main__":
    unittest.main()
