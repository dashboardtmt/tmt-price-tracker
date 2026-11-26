# -*- coding: utf-8 -*-
u"""A falha do regulamento da Vivo nao vale para a rodada inteira.

O coletor guardava no cache da rodada o None da primeira falha. Uma
recusa passageira em Sao Paulo (403 em 23/11/2026, 422 em 17/11) valia
para as 20 pracas: nenhuma perguntava de novo, e as ofertas daquele
codigo saiam sem fidelidade, multa e preco de tabela o dia inteiro. Os
codigos que falharam no servidor do robo abriam normalmente daqui.

E o aviso contava a rodada, e nao a praca: a lista de falhas nunca era
zerada, e "regulamento falhou em 5 oferta(s)" saia repetido em toda
praca depois da primeira falha.

Agora o codigo que falha e tentado de novo nas pracas seguintes, ate
TENTATIVAS_REGULAMENTO vezes, e o aviso conta so a praca. Pelo caminho
de producao: vivo.coletar, duas pracas seguidas.
"""
import io
import json
import os
import sys
import unittest
import urllib.error
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletores import vivo                                    # noqa: E402

CODIGO = "VIV202600099999"
REG = {"ofertas": [{"nomeOferta": "Vivo Controle", "precoSemDescontos": 70.0,
                    "fidelizacao": {"tempoFidelizacao": 12}}]}


def _zip():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("r.json", json.dumps(REG))
    return b.getvalue()


class _Resposta(object):
    def __init__(self, corpo):
        self.corpo = corpo

    def read(self):
        return self.corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Navegador(object):
    u"""Recusa as primeiras `falhas` chamadas e responde as outras."""

    def __init__(self, falhas):
        self.falhas = falhas
        self.chamadas = 0

    def open(self, req, timeout=None):
        self.chamadas += 1
        if self.chamadas <= self.falhas:
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
        return _Resposta(_zip())


CARD = {"plano": "Vivo Controle", "texto": "Vivo Controle 50GB", "destaque": "50GB",
        "preco": 59.0, "codigo_anatel": CODIGO}


class ORegulamentoTentaDeNovo(unittest.TestCase):

    def setUp(self):
        self.guarda = {k: getattr(vivo, k) for k in (
            "navegador", "trocar_praca", "indice_catalogo", "ler_vitrine",
            "ler_lite", "PAUSA", "PAGINAS_EXTRAS")}
        self.addCleanup(self._volta)
        vivo.trocar_praca = lambda op, c, u: True
        vivo.indice_catalogo = lambda op: ({}, [])
        vivo.ler_vitrine = lambda op, p, *a: (([dict(CARD)] if p == "controle" else []), None)
        vivo.ler_lite = lambda op, hoje, avisos=None: ([], None)
        vivo.PAUSA = 0
        # as paginas extras da vitrine (26/11/2026) ficam fora deste teste
        vivo.PAGINAS_EXTRAS = ()
        vivo._cache_regulamento.pop(CODIGO, None)
        vivo._tentativas_regulamento.pop(CODIGO, None)
        del vivo._falhas_regulamento[:]

    def _volta(self):
        for k, v in self.guarda.items():
            setattr(vivo, k, v)
        vivo._cache_regulamento.pop(CODIGO, None)
        vivo._tentativas_regulamento.pop(CODIGO, None)
        del vivo._falhas_regulamento[:]

    def _praca(self, nav, cidade, uf):
        vivo.navegador = lambda: (nav, None)
        return vivo.coletar(cidade, uf, verbose=False)

    def test_a_segunda_praca_pergunta_de_novo_e_recebe(self):
        nav = Navegador(falhas=1)
        sp = self._praca(nav, "Sao Paulo", "SP")
        rj = self._praca(nav, "Rio de Janeiro", "RJ")
        self.assertEqual(nav.chamadas, 2, "o Rio tinha de perguntar de novo")
        self.assertTrue([a for a in sp["avisos"] if "regulamento falhou em 1" in a])
        self.assertFalse([a for a in rj["avisos"] if "regulamento falhou" in a],
                         "o aviso nao pode repetir a falha de outra praca")
        self.assertEqual(rj["ofertas"][0].get("fidelidade_meses"), 12)

    def test_depois_das_tentativas_a_falha_vai_para_o_cache(self):
        nav = Navegador(falhas=99)
        for cidade, uf in (("Sao Paulo", "SP"), ("Rio de Janeiro", "RJ"),
                           ("Recife", "PE"), ("Natal", "RN")):
            r = self._praca(nav, cidade, uf)
            # toda praca sem regulamento diz isso - inclusive a que ja
            # nem pergunta mais
            self.assertTrue([a for a in r["avisos"]
                             if "regulamento falhou em 1" in a], cidade)
        self.assertEqual(nav.chamadas, vivo.TENTATIVAS_REGULAMENTO)


if __name__ == "__main__":
    unittest.main(verbosity=2)
