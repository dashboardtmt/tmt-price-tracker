# -*- coding: utf-8 -*-
u"""A oferta nova que repete o nome de outra tambem entra na vitrine.

O CASO REAL, de 27/11/2026. Ate 26/11 a "Vivo Total Essencial" existia so
em 6 pracas do Nordeste (Fortaleza, Natal, Joao Pessoa, Maceio, Aracaju,
Teresina), a R$ 100, com 500 Mega e 20 GB. Em 27/11 a Vivo pos uma oferta
da Purple Friday com o MESMO nome em outras 17 pracas: R$ 130, 600 Mega e
60 GB - em 14 onde o nome nao estava e, ao lado da velha, em Aracaju,
Maceio e Teresina. A mensagem do dia nao disse nada: o detector de entrada
agrupa a serie pelo nome, e o nome ja estava na janela.

MEDIDO NOS 59 DIAS PUBLICADOS, a entrega nova numa serie que ja existia
rende sete casos, e so a Essencial e lancamento. Cada impostor prende uma
guarda, com o caso que a motivou:

  1. a escada andando: o Claro Controle trocou 45 GB por 40 e 55 em 13/10
     e 13/11 - a entrega nova tomou o lugar da velha;
  2. o degrau deslizando sob um nome so: a "Vivo Fibra" de 03/10 passou o
     ponto de R$ 100 do 700 para o 600 Mega, e o 700 para R$ 150;
  3. o renome que o detector de renome nao casa: em 13/10 o "TIM Pre XIP
     Plus - 16GB" de R$ 30 perdeu o sufixo em tres pracas;
  4. a volta: entrega que a serie ja teve na janela nao e nova.

Tudo pela montagem de producao (montar_mensagem, com o auditor no fim), e
nao pela funcao do detector: o defeito de 27/11 era a mensagem calada.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auditor                                                # noqa: E402
from _apoio import HOJE, ONTEM, dados, montar, oferta, sem_declaracao  # noqa: E402
from coletores.pracas import PRACAS, rotulo                    # noqa: E402

try:
    import pypdf
    import relatorio
except ImportError:                                           # pragma: no cover
    relatorio = None

TODAS = [rotulo(p) for p in PRACAS]
NORDESTE = ["Fortaleza/CE", "Natal/RN", "Joao Pessoa/PB", "Maceio/AL",
            "Aracaju/SE", "Teresina/PI"]
# onde a nova entrou ao lado da velha
JUNTO_DA_VELHA = ["Aracaju/SE", "Maceio/AL", "Teresina/PI"]
NOVAS = [p for p in TODAS if p not in NORDESTE] + JUNTO_DA_VELHA
ANTEONTEM = "2026-10-18"


def combo(nome, preco, mbps, gb, pracas, data, chave):
    return [oferta(operadora="Vivo", produto="combo", nome=nome, preco=preco,
                   gb=gb, mbps=mbps, praca=p, data=data, chave=chave)
            for p in pracas]


def essencial_velha(data):
    return combo(u"Vivo Total Essencial", 100.0, 500, 20, NORDESTE, data,
                 "Vivo|combo|500mbps_20gb|com_apps")


def essencial_nova(data, pracas=NOVAS):
    return combo(u"Vivo Total Essencial", 130.0, 600, 60, pracas, data,
                 "Vivo|combo|600mbps_60gb|simples")


def pro(data):
    u"""O combo que a Vivo vende nas 20 pracas: o universo do produto."""
    return combo(u"Vivo Total Pro", 160.0, 600, 100, TODAS, data,
                 "Vivo|combo|600mbps_100gb|simples")


class AEssencialDaPurpleFriday(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)
        self.ontem = essencial_velha(ONTEM) + pro(ONTEM)
        self.hoje = essencial_velha(HOJE) + essencial_nova(HOJE) + pro(HOJE)

    def test_sai_como_entrada_com_preco_e_entrega(self):
        t = montar(self.ontem, self.hoje)
        self.assertIn(u"Combo · Vivo Total Essencial", t)
        self.assertIn(u"entrou na vitrine a 130,00, com 600 Mbps + 60 GB", t)
        self.assertIn(u"em 17 de 20", t)
        self.assertIn(u"1 mudança hoje", t)

    def test_diz_de_quem_era_o_nome(self):
        u"""Sem esta linha, "Essencial a 130,00" le como reajuste da de
        100,00, que segue na vitrine."""
        t = montar(self.ontem, self.hoje)
        self.assertIn(u"o nome já era de outra oferta, que segue na "
                      u"vitrine: 100,00 com 500 Mbps + 20 GB, em 6 praças", t)

    def test_entra_tambem_onde_a_velha_continua(self):
        d = dados(self.ontem, self.hoje)
        self.assertEqual([e["nome_oferta"] for e in d["entradas"]],
                         [u"Vivo Total Essencial"])
        self.assertEqual(sorted(d["entradas"][0]["pracas"]), sorted(NOVAS))
        # o auditor confere pelo degrau, e nao recusa o Nordeste
        self.assertEqual(d.get("recusadas") or [], [])

    def test_o_nome_que_saiu_e_dito_no_passado(self):
        u"""A velha saiu no mesmo dia: a frase nao pode dizer que ela segue."""
        hoje = essencial_nova(HOJE, pracas=[p for p in TODAS
                                            if p not in NORDESTE]) + pro(HOJE)
        t = montar(self.ontem, hoje)
        self.assertIn(u"entrou na vitrine a 130,00, com 600 Mbps + 60 GB", t)
        self.assertIn(u"o nome era de outra oferta, que saiu: 100,00 com "
                      u"500 Mbps + 20 GB", t)
        self.assertNotIn(u"que segue na vitrine", t)

    def test_entra_no_pdf_com_a_frase(self):
        if relatorio is None:
            self.skipTest("reportlab ou pypdf ausente")
        d = dados(self.ontem, self.hoje)
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        texto = " ".join(" ".join((p.extract_text() or "").split())
                         for p in pypdf.PdfReader(caminho).pages)
        self.assertIn(u"Ofertas que entraram na vitrine", texto)
        self.assertIn(u"600 Mbps + 60 GB", texto)
        self.assertIn(u"o nome já era de outra oferta", texto)


class OQueNaoELancamento(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)

    def test_a_escada_que_anda_nao_entra(self):
        u"""O Claro Controle de 13/11: 45 GB vira 55 GB, e numa praca que
        ontem nao tinha a serie ela aparece ja com 55."""
        tres = TODAS[:3]

        def controle(gb, preco, pracas, data):
            return [oferta(operadora="Claro", produto="controle",
                           nome="Claro Controle", preco=preco, gb=gb,
                           praca=p, data=data) for p in pracas]
        fundo = [oferta(operadora="Claro", produto="controle",
                        nome="Claro Controle Geforce", preco=99.9, gb=35,
                        praca=p, data=d) for p in TODAS[:4] for d in (ONTEM, HOJE)]
        t = montar(controle(45, 59.9, tres, ONTEM),
                   controle(55, 59.9, TODAS[:4], HOJE), extras=fundo)
        self.assertNotIn("entrou na vitrine", t)

    def test_o_degrau_que_desliza_sob_um_nome_nao_entra(self):
        u"""A "Vivo Fibra" de 03/10: o ponto de R$ 100 passa do 700 para o
        600 Mega, e o 700 sobe para R$ 150."""
        def fibra(mbps, preco, data):
            return [oferta(operadora="Vivo", produto="fibra", nome="Vivo Fibra",
                           preco=preco, gb=None, mbps=mbps, praca=p, data=data)
                    for p in TODAS[:3]]
        t = montar(fibra(1000, 200.0, ONTEM) + fibra(700, 100.0, ONTEM),
                   fibra(1000, 200.0, HOJE) + fibra(600, 100.0, HOJE)
                   + fibra(700, 150.0, HOJE))
        self.assertNotIn("entrou na vitrine", t)

    def test_o_renome_que_o_detector_nao_casa_nao_entra(self):
        u"""O TIM Pre XIP Plus de 13/10: a de R$ 30 perde o sufixo em tres
        pracas e a chave muda junto (simples -> com o app), entao o
        detector de renome, que casa pela chave, nao a pega."""
        tres, resto = TODAS[:3], TODAS[3:6]

        def xip(nome, gb, preco, pracas, data, chave):
            return [oferta(operadora="TIM", produto="prepago", nome=nome,
                           preco=preco, gb=gb, praca=p, data=data, chave=chave)
                    for p in pracas]
        base = u"TIM Pré XIP Plus"
        velhas = lambda data: (  # noqa: E731
            xip(base, 6, 20.0, tres + resto, data, "TIM|prepago|6gb|com_xip")
            + xip(base, 8, 25.0, tres + resto, data, "TIM|prepago|8gb|com_xip"))
        ontem = velhas(ONTEM) + xip(base + " - 16GB", 16, 30.0, tres + resto,
                                    ONTEM, "TIM|prepago|16gb|simples")
        hoje = (velhas(HOJE)
                + xip(base, 16, 30.0, tres, HOJE, "TIM|prepago|16gb|com_xip")
                + xip(base + " - 16GB", 16, 30.0, resto, HOJE,
                      "TIM|prepago|16gb|simples"))
        t = montar(ontem, hoje)
        self.assertNotIn("entrou na vitrine", t)

    def test_entrega_que_a_serie_ja_teve_na_janela_nao_entra(self):
        u"""Volta nao e lancamento, como no nome novo."""
        hoje = essencial_velha(HOJE) + essencial_nova(HOJE) + pro(HOJE)
        t = montar(essencial_velha(ONTEM) + pro(ONTEM), hoje,
                   extras=essencial_nova(ANTEONTEM))
        self.assertNotIn("entrou na vitrine", t)

    def test_praca_sem_coleta_ontem_fica_fora(self):
        u"""Ontem ninguem olhou Sao Paulo: la a Essencial nova nao e nova."""
        ontem = [l for l in essencial_velha(ONTEM) + pro(ONTEM)
                 if l["praca"] != "Sao Paulo/SP"]
        hoje = essencial_velha(HOJE) + essencial_nova(HOJE) + pro(HOJE)
        d = dados(ontem, hoje)
        self.assertEqual(len(d["entradas"]), 1)
        self.assertNotIn("Sao Paulo/SP", d["entradas"][0]["pracas"])
        self.assertEqual(len(d["entradas"][0]["pracas"]), 16)


class OAuditorConfereODegrau(unittest.TestCase):

    EVENTO = {"operadora": "Vivo", "produto": "combo",
              "nome_oferta": u"Vivo Total Essencial", "degrau": [600, 60],
              "pracas": JUNTO_DA_VELHA}

    def test_a_praca_onde_a_velha_continua_sustenta(self):
        hoje = essencial_velha(HOJE) + essencial_nova(HOJE)
        boas, incertas = auditor._pracas_da_entrada(
            self.EVENTO, auditor._indice(hoje, False),
            auditor._indice(essencial_velha(ONTEM), False),
            {("Vivo", p) for p in TODAS})
        self.assertEqual(boas, set(JUNTO_DA_VELHA))
        self.assertEqual(incertas, set())

    def test_o_mesmo_degrau_ontem_nao_sustenta(self):
        hoje = essencial_velha(HOJE) + essencial_nova(HOJE)
        ontem = essencial_velha(ONTEM) + essencial_nova(ONTEM)
        boas, _ = auditor._pracas_da_entrada(
            self.EVENTO, auditor._indice(hoje, False),
            auditor._indice(ontem, False), {("Vivo", p) for p in TODAS})
        self.assertEqual(boas, set())


if __name__ == "__main__":
    unittest.main()
