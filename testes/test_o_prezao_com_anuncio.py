# -*- coding: utf-8 -*-
u"""O Prezao com anuncio, so nos DDDs da aba (27/11/2026).

A auditoria contra o site de 26/11/2026 achou uma terceira aba na pagina do
Prezao, que so aparece em alguns DDDs: "Prezao com anuncio", R$ 15,00 por 30
dias, "Assista 1 minuto de anuncio / Leve 1 hora de internet". O segmento
vem nos dados da pagina (DDDs 15, 38, 53 e 79) - das 20 pracas, so Aracaju.

A fixture e a aba real, de 26/11/2026, dentro de um __NEXT_DATA__ minimo.
"""
import io
import json
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import claro, pracas  # noqa: E402

ABA = json.load(io.open(os.path.join(AQUI, "fixtures", "claro_prezao_com_anuncio_2026-11-26.json"),
                        encoding="utf-8"))
PAGINA = ('<script id="__NEXT_DATA__" type="application/json">%s</script>'
          % json.dumps({"props": {"abas": [ABA]}}, ensure_ascii=False))


class _ComPagina(unittest.TestCase):

    def setUp(self):
        guarda = {k: getattr(claro, k) for k in (
            "buscar", "PAUSA", "codigo_cidade", "ler_prezao", "ler_prezao_tematico",
            "ler_sem_fidelidade", "PAGINAS")}
        self.addCleanup(lambda: [setattr(claro, k, v) for k, v in guarda.items()])
        self.pagina = PAGINA
        claro.buscar = lambda op, url, *a, **k: ((200, self.pagina) if url == guarda["PAGINAS"]["prepago"]
                                                 else (404, ""))
        claro.PAUSA = 0
        claro.codigo_cidade = lambda op, c, u: ("x", "123", None)
        claro.ler_prezao = lambda op, url: ([], None)
        claro.ler_prezao_tematico = lambda op, url: ([], None)
        claro.ler_sem_fidelidade = lambda op: ([], None)
        claro.PAGINAS = {"prepago": guarda["PAGINAS"]["prepago"]}


class AAbaDoAnuncio(_ComPagina):

    def test_em_aracaju_entra(self):
        ofertas, erro = claro.ler_prezao_com_anuncio(None, claro.PAGINAS["prepago"], "79")
        self.assertIsNone(erro)
        self.assertEqual([(o["nome_oferta"], o["preco_promocional"], o["validade_dias"],
                           o["franquia_anunciada_gb"], o["whatsapp"]) for o in ofertas],
                         [(u"Claro Prezao com anúncio", 15.0, 30, None, True)])

    def test_o_preco_e_o_do_card_e_nao_a_tarifa_diaria(self):
        u"""Os detalhes falam de R$ 2,19 por dia sem saldo, antes do card."""
        self.assertIn("2,19", json.dumps(ABA, ensure_ascii=False))
        ofertas, _ = claro.ler_prezao_com_anuncio(None, claro.PAGINAS["prepago"], "79")
        self.assertEqual(ofertas[0]["preco_promocional"], 15.0)

    def test_fora_dos_ddds_da_aba_nao_entra(self):
        for cidade in ("Sao Paulo", "Belo Horizonte", "Porto Alegre"):
            ofertas, erro = claro.ler_prezao_com_anuncio(None, claro.PAGINAS["prepago"],
                                                         pracas.DDD[cidade])
            self.assertEqual((ofertas, erro), ([], None), cidade)

    def test_das_20_pracas_so_aracaju(self):
        dentro = [c for c, d in pracas.DDD.items() if d in ("15", "38", "53", "79")]
        self.assertEqual(dentro, ["Aracaju"])

    def test_aba_que_sai_da_pagina_nao_e_erro(self):
        self.pagina = '<script id="__NEXT_DATA__" type="application/json">{"props": {}}</script>'
        self.assertEqual(claro.ler_prezao_com_anuncio(None, claro.PAGINAS["prepago"], "79"), ([], None))


class OCaminhoDeProducao(_ComPagina):

    def test_o_coletor_grava_em_aracaju_com_o_skeelo(self):
        d = claro.coletar("Aracaju", "SE", verbose=False)
        pre = [o for o in d["ofertas"] if o["produto"] == "prepago"]
        self.assertEqual([(o["nome_oferta"], o["preco_promocional"]) for o in pre],
                         [(u"Claro Prezao com anúncio", 15.0)])
        self.assertIn("skeelo", pre[0]["apps"])

    def test_e_nao_em_sao_paulo(self):
        d = claro.coletar("Sao Paulo", "SP", verbose=False)
        self.assertFalse([o for o in d["ofertas"] if "anúncio" in o["nome_oferta"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
