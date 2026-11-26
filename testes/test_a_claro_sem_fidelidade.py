# -*- coding: utf-8 -*-
u"""Os planos sem fidelidade da loja da Claro (27/11/2026).

Escolha de quem le em 26/11/2026, "incluir, como a Vivo sem apps": a loja
vende o Controle de 15 e 20 GB e o Pos de 50 a 200 GB sem fidelidade, em
duas familias - com os apps exclusivos e sem eles. O preco e o "price" do
__NEXT_DATA__; o do debito automatico (R$ 54,90 no Controle de R$ 59,90) e
condicionado e fica de fora.

A fixture e um recorte real de 26/11/2026, so com os campos lidos.
"""
import io
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import claro  # noqa: E402

LOJA = io.open(os.path.join(AQUI, "fixtures", "claro_loja_sem_fidelidade_2026-11-26.html"),
               encoding="utf-8").read()


class _ComLoja(unittest.TestCase):

    def setUp(self):
        guarda = (claro.buscar, claro.PAUSA, claro.codigo_cidade)
        self.loja = (200, LOJA)

        def buscar(op, url, *a, **k):
            if url == claro.LOJA_SEM_FIDELIDADE:
                return self.loja
            return (404, "")
        claro.buscar = buscar
        claro.PAUSA = 0
        claro.codigo_cidade = lambda op, c, u: ("x", "123", None)
        claro._cache_sem_fidelidade.clear()

        def volta():
            claro.buscar, claro.PAUSA, claro.codigo_cidade = guarda
            claro._cache_sem_fidelidade.clear()
        self.addCleanup(volta)


class ALojaSemFidelidade(_ComLoja):

    def test_as_doze_ofertas(self):
        ofertas, erro = claro.ler_sem_fidelidade(None)
        self.assertIsNone(erro)
        self.assertEqual(
            sorted((o["produto"], o["nome_oferta"], o["franquia_anunciada_gb"], o["preco_promocional"])
                   for o in ofertas),
            [("controle", u"Claro Controle sem fidelidade", 15, 59.9),
             ("controle", u"Claro Controle sem fidelidade", 20, 69.9),
             ("controle", u"Claro Controle sem fidelidade sem apps", 15, 59.9),
             ("controle", u"Claro Controle sem fidelidade sem apps", 20, 69.9),
             ("movel", u"Claro Pós sem fidelidade", 50, 124.9),
             ("movel", u"Claro Pós sem fidelidade", 100, 179.9),
             ("movel", u"Claro Pós sem fidelidade", 150, 239.9),
             ("movel", u"Claro Pós sem fidelidade", 200, 339.9),
             ("movel", u"Claro Pós sem fidelidade sem apps", 50, 119.9),
             ("movel", u"Claro Pós sem fidelidade sem apps", 100, 174.9),
             ("movel", u"Claro Pós sem fidelidade sem apps", 150, 234.9),
             ("movel", u"Claro Pós sem fidelidade sem apps", 200, 334.9)])

    def test_o_preco_do_debito_nao_entra(self):
        ofertas, _ = claro.ler_sem_fidelidade(None)
        self.assertNotIn(54.9, [o["preco_promocional"] for o in ofertas])

    def test_os_apps_e_a_escolha(self):
        u"""O Skeelo do Controle so esta nos icones do grupo; o "Google One
        ou iCloud+" do Pos e escolha, e nenhum dos dois entra."""
        ofertas, _ = claro.ler_sem_fidelidade(None)
        de = dict(((o["nome_oferta"], o["franquia_anunciada_gb"]), o) for o in ofertas)
        self.assertEqual(sorted(de[(u"Claro Controle sem fidelidade", 15)]["apps"]),
                         ["claro_banca", "skeelo"])
        pos = de[(u"Claro Pós sem fidelidade", 50)]["apps"]
        self.assertEqual(sorted(pos), ["claro_banca", "skeelo", "truecaller"])
        self.assertEqual(de[(u"Claro Pós sem fidelidade sem apps", 50)]["apps"], [])
        self.assertFalse(any(o["whatsapp"] for o in ofertas))
        self.assertTrue(all(o["fidelidade_meses"] == 0 for o in ofertas))


class OCaminhoDeProducao(_ComLoja):

    def test_a_loja_entra_na_praca(self):
        d = claro.coletar("Sao Paulo", "SP", verbose=False)
        sem = [o for o in d["ofertas"] if "sem fidelidade" in o["nome_oferta"]]
        self.assertEqual(len(sem), 12)
        self.assertTrue(all(o["praca"] == "Sao Paulo/SP" for o in sem))

    def test_sem_a_loja_o_pos_e_o_controle_saem_da_praca(self):
        u"""O que so a loja traz nao pode virar saida da vitrine: sem ela, o
        pos e o controle ficam fora da praca hoje, e o aviso diz."""
        self.loja = (503, "")
        d = claro.coletar("Sao Paulo", "SP", verbose=False)
        self.assertFalse([o for o in d["ofertas"] if o["produto"] in ("movel", "controle")])
        self.assertTrue(any("loja sem fidelidade falhou" in a for a in d["avisos"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
