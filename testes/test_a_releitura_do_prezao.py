# -*- coding: utf-8 -*-
u"""reler_prezao.py: o historico do Prezao relido pela escada gravada.

Ate 24/11/2026 so a recarga de R$ 30 entrava; as outras ficavam na
composicao. A releitura tem de dar EXATAMENTE o que a coleta de 25/11
grava a partir da mesma pagina - senao o historico ajustado e outra regra,
e a serie ganha um degrau falso no lugar do que tirou.
"""
import copy
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import reler_prezao as R                                      # noqa: E402
from coletores import armazenamento, claro                   # noqa: E402
from test_o_prezao_soma import TABELA                         # noqa: E402

# a composicao como a coleta a gravava ate 24/11 (o mesmo formato desde 07/10)
VELHA = (u"Prezao R$1 por dia, renovacao a cada 30 dias. Escada completa: "
         u"R$ 30,00 = 17GB+ 3GB Youtube/30 dias; R$ 25,00 = 10GB+ 2GB "
         u"Youtube/25 dias; R$ 20,00 = 8GB+ 2GB Youtube/20 dias; R$ 15,00 = "
         u"5GB/15 dias")


def captura_velha(i=1, dia="2026-11-20", praca="Sao Paulo/SP", comp=VELHA):
    bruto = {"nome_oferta": "Claro Prezao 17GB", "destaque": "17 GB",
             "franquia_anunciada_gb": 17, "franquia_contratual_gb": 14,
             "preco_promocional": 30.0, "composicao": comp,
             "operadora": "Claro", "produto": "prepago", "praca": praca,
             "degrau_mbps": None, "nivel_bundle": 0, "apps": [],
             "versao_leitura": "abc123", "whatsapp": True}
    return {"id": i, "capturado_em": dia + "T06:05:00-03:00",
            "data_captura": dia, "operadora": "Claro", "produto": "prepago",
            "praca": praca, "uf": praca.split("/")[-1],
            "nome_oferta": "Claro Prezao 17GB", "destaque": "17 GB",
            "chave": armazenamento.chave_continuidade(bruto),
            "codigo_anatel": "", "codigos_anatel": None, "id_catalogo": None,
            "degrau_mbps": None, "franquia_anunciada_gb": 17,
            "franquia_contratual_gb": 14, "preco_cheio": None,
            "preco_promocional": 30.0, "fidelidade_meses": None,
            "multa_fidelidade": None, "taxa_instalacao": None,
            "meses_desconto": None, "preco_pos_promocao": None,
            "nivel_bundle": 0, "campanha": None, "bruto": bruto}


class AEscadaEAMesmaRegra(unittest.TestCase):

    def test_relida_da_o_que_a_coleta_de_hoje_grava(self):
        u"""A escada que o coletor de HOJE escreve na composicao, relida,
        da as mesmas quatro ofertas que ele grava."""
        guarda = claro.buscar
        claro.buscar = lambda op, url, *a, **k: (200, TABELA)
        self.addCleanup(setattr, claro, "buscar", guarda)
        ofertas, erro = claro.ler_prezao(None, "http://x")
        self.assertIsNone(erro)
        hoje = [(o["preco_promocional"], o["franquia_anunciada_gb"],
                 o["franquia_contratual_gb"], o["validade_dias"]) for o in ofertas]
        for o in ofertas:
            self.assertEqual(R.escada(o["composicao"]), hoje)

    def test_a_escada_velha(self):
        self.assertEqual(R.escada(VELHA), [(30.0, 20, 17, 30), (25.0, 12, 10, 25),
                                           (20.0, 10, 8, 20), (15.0, 5, None, 15)])

    def test_escada_cortada_no_fim_nao_some_calada(self):
        self.assertIsNone(R.escada(VELHA[:-8]))

    def test_sem_escada(self):
        self.assertEqual(R.escada(u"Prezao R$1 por dia"), [])
        self.assertEqual(R.escada(None), [])


class OPlano(unittest.TestCase):

    def test_corrige_a_de_30_e_insere_as_outras_tres(self):
        remendos, novas, problemas = R.planejar([captura_velha()])
        self.assertEqual(problemas, [])
        self.assertEqual(len(remendos), 1)
        i, campos = remendos[0]
        self.assertEqual(i, 1)
        self.assertEqual((campos["nome_oferta"], campos["franquia_anunciada_gb"],
                          campos["franquia_contratual_gb"], campos["destaque"]),
                         ("Claro Prezao 20GB", 20, 17, "20 GB"))
        self.assertEqual(campos["chave"], "Claro|prepago|20gb|simples")
        self.assertEqual(campos["bruto"]["validade_dias"], 30)
        # a prova do que a coleta leu fica no bruto
        self.assertEqual(campos["bruto"]["releitura"]["lido"]["nome_oferta"],
                         "Claro Prezao 17GB")
        self.assertEqual(campos["bruto"]["releitura"]["lido"]["franquia_anunciada_gb"], 17)
        lidas = sorted((n["preco_promocional"], n["nome_oferta"],
                        n["franquia_anunciada_gb"], n["franquia_contratual_gb"],
                        n["bruto"]["validade_dias"], n["chave"]) for n in novas)
        self.assertEqual(lidas, [
            (15.0, "Claro Prezao 5GB", 5, None, 15, "Claro|prepago|5gb|simples"),
            (20.0, "Claro Prezao 10GB", 10, 8, 20, "Claro|prepago|10gb|simples"),
            (25.0, "Claro Prezao 12GB", 12, 10, 25, "Claro|prepago|12gb|simples"),
        ])
        for n in novas:
            self.assertNotIn("id", n)
            self.assertEqual(n["data_captura"], "2026-11-20")
            self.assertEqual(n["praca"], "Sao Paulo/SP")
            self.assertEqual(n["bruto"]["releitura"]["de_id"], 1)
            # os apps nao mudam: a escada velha nao diz nada do Skeelo
            self.assertEqual(n["bruto"]["apps"], [])
        self.assertIn("renovacao a cada 15 dias",
                      [n for n in novas if n["preco_promocional"] == 15.0][0]
                      ["bruto"]["composicao"])

    def test_cada_dia_usa_a_propria_escada(self):
        u"""Nada vem de hoje: a escada de um dia com outro degrau de R$ 15
        da o R$ 15 daquele dia."""
        outra = VELHA.replace("5GB/15 dias", "4GB/15 dias")
        _, novas, _ = R.planejar([captura_velha(1, "2026-10-10", comp=outra),
                                  captura_velha(2, "2026-11-20")])
        quinze = sorted((n["data_captura"], n["franquia_anunciada_gb"])
                        for n in novas if n["preco_promocional"] == 15.0)
        self.assertEqual(quinze, [("2026-10-10", 4), ("2026-11-20", 5)])

    def test_captura_fora_da_escada_para_tudo(self):
        estranha = captura_velha(2)
        estranha["preco_promocional"] = 35.0
        _, _, problemas = R.planejar([captura_velha(1), estranha])
        self.assertEqual(len(problemas), 1)

    def test_escada_ilegivel_para_tudo(self):
        _, _, problemas = R.planejar([captura_velha(comp=VELHA[:-8])])
        self.assertEqual(len(problemas), 1)


class BancoFalso(object):

    def __init__(self, linhas):
        self.linhas = copy.deepcopy(linhas)
        self.proximo = 1 + max(l["id"] for l in linhas)

    def ler(self):
        return copy.deepcopy(self.linhas)

    def pedido(self, metodo, caminho, corpo=None, prefer=None):
        if metodo == "PATCH":
            self.assertivo(caminho.startswith("capturas?id=eq."))
            i = int(caminho.split("eq.")[1])
            alvo = [l for l in self.linhas if l["id"] == i]
            self.assertivo(len(alvo) == 1)
            alvo[0].update(copy.deepcopy(corpo))
            return 204, ""
        if metodo == "POST":
            for l in corpo:
                n = copy.deepcopy(l)
                n["id"] = self.proximo
                self.proximo += 1
                self.linhas.append(n)
            return 201, ""
        raise AssertionError(metodo)

    @staticmethod
    def assertivo(cond):
        if not cond:
            raise AssertionError("pedido fora do esperado")


class OAplicar(unittest.TestCase):
    u"""O caminho de producao: main(--aplicar) grava, rele e confere."""

    def _com(self, banco):
        guarda = (R.ler, R._pedido, R.olhar_tim)
        R.ler, R._pedido, R.olhar_tim = banco.ler, banco.pedido, lambda: None

        def volta():
            R.ler, R._pedido, R.olhar_tim = guarda
        self.addCleanup(volta)

    def test_aplica_e_um_novo_plano_sai_vazio(self):
        banco = BancoFalso([captura_velha(1, "2026-11-20"),
                            captura_velha(2, "2026-11-20", "Rio de Janeiro/RJ"),
                            captura_velha(3, "2026-11-21")])
        self._com(banco)
        self.assertEqual(R.main(["--aplicar"]), 0)
        self.assertEqual(len(banco.linhas), 12)
        self.assertEqual(R.planejar(banco.ler()), ([], [], []))
        entrada = min(l["preco_promocional"] for l in banco.linhas
                      if l["data_captura"] == "2026-11-21")
        self.assertEqual(entrada, 15.0)

    def test_rodar_de_novo_nao_duplica(self):
        banco = BancoFalso([captura_velha(1)])
        self._com(banco)
        self.assertEqual(R.main(["--aplicar"]), 0)
        self.assertEqual(R.main(["--aplicar"]), 0)
        self.assertEqual(len(banco.linhas), 4)

    def test_sem_aplicar_nao_grava(self):
        banco = BancoFalso([captura_velha(1)])
        self._com(banco)
        self.assertEqual(R.main([]), 0)
        self.assertEqual(len(banco.linhas), 1)
        self.assertEqual(banco.linhas[0]["nome_oferta"], "Claro Prezao 17GB")

    def test_problema_nao_grava_nada(self):
        estranha = captura_velha(2)
        estranha["preco_promocional"] = 35.0
        banco = BancoFalso([captura_velha(1), estranha])
        self._com(banco)
        self.assertEqual(R.main(["--aplicar"]), 1)
        self.assertEqual(len(banco.linhas), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
