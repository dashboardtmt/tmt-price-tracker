# -*- coding: utf-8 -*-
u"""Quando o regulamento muda e a vitrine nao.

A PERGUNTA DE QUEM LE, EM 11/11/2026, sobre a mensagem daquela manha:

  "na mensagem de hj houve uma mudanca no pre pago da vivo. O que foi
   isso?? nao estava na msg nem no report"

A mensagem dizia "Pre-pago - Vivo Pre / mesmo preco (35,00), ganhou 1
servico incluso em todas as 20 pracas". Era verdade no que foi medido:
o regulamento que a Vivo deposita na Anatel passou de cinco para seis
codigos SVA - entrou o 060017. E era tudo o que tinha mudado. Na tela
da Vivo, o plano de R$ 35 seguia com os mesmos 25 GB, o mesmo nome e o
mesmo "Vale Saude Sempre + Google One".

"ganhou 1 servico" se le como oferta melhor. O leitor foi procurar no
site qual era, e nao havia nada para achar.

MEDIDO NOS 43 DIAS PUBLICADOS: 10 eventos de composicao, e em NENHUM a
lista de apps da vitrine mexeu junto. Em 6 a vitrine estava parada
inteira; nos outros 4 - as Vivo Total de 17/10 - mexeu so o preco de
tabela. A prateleira nunca confirmou o regulamento nessa categoria, e
por isso nao da para nomear o servico pela vitrine: o que da e dizer
que ela nao mudou.

O QUE ESTE ARQUIVO PRENDE:

  1. a frase sai quando a vitrine esta parada, e so ai;
  2. cada campo da vitrine, mexendo sozinho, cala a frase - tirar um
     deles da lista faria a mensagem afirmar "esta igual" sobre um
     campo que mudou;
  3. a consulta do robo TRAZ cada campo sobre o qual a frase afirma. O
     banco de mentira devolve a linha inteira e ignora o select, entao
     nenhum teste de mensagem pegaria um campo fora da consulta: em
     producao ele chegaria None dos dois lados, "igual", e a frase
     afirmaria sobre o vazio;
  4. dia sem preco lido nao sustenta igualdade.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                   # noqa: E402
from _apoio import (HOJE, ONTEM, montar, oferta,              # noqa: E402
                    sem_declaracao)
from coletores import armazenamento                           # noqa: E402

FRASE = u"a vitrine está igual - mudou o que a Vivo declara na Anatel"
ANTES_SVA = "030012+030021+030032+040022+060016"
AGORA_SVA = ANTES_SVA + "+060017"


def pre(data, sva, **mexer):
    u"""O Vivo Pre de R$ 35 / 25 GB como estava em 10 e 11/11/2026."""
    o = oferta(operadora="Vivo", produto="prepago", nome=u"Vivo Pré",
               preco=35.0, gb=25, data=data, sva=sva,
               apps=["vale_saude", "google_one"])
    o["preco_cheio"] = 35.0
    o.update(mexer)
    return [o]


class AFraseSaiSoComAVitrineParada(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)

    def test_o_caso_de_11_11(self):
        t = montar(pre(ONTEM, ANTES_SVA), pre(HOJE, AGORA_SVA))
        self.assertIn(u"ganhou 1 serviço incluso", t)
        self.assertIn(FRASE, t)

    def test_os_apps_em_outra_ordem_sao_os_mesmos(self):
        u"""O coletor nao promete ordem na lista; a vitrine com os
        mesmos dois apps e a mesma vitrine."""
        t = montar(pre(ONTEM, ANTES_SVA),
                   pre(HOJE, AGORA_SVA, apps=["google_one", "vale_saude"]))
        self.assertIn(FRASE, t)

    def test_app_que_entra_na_vitrine_cala_a_frase(self):
        u"""Aqui a prateleira MEXEU: dizer "esta igual" seria falso."""
        t = montar(pre(ONTEM, ANTES_SVA),
                   pre(HOJE, AGORA_SVA,
                       apps=["vale_saude", "google_one", "spotify"]))
        self.assertIn(u"ganhou 1 serviço incluso", t)
        self.assertNotIn(u"a vitrine está igual", t)

    def test_o_preco_de_tabela_que_mexe_cala_a_frase(self):
        u"""O caso das Vivo Total de 17/10/2026: o regulamento trocou um
        codigo e, no mesmo dia, so o preco riscado ao lado do
        promocional mudou."""
        t = montar(pre(ONTEM, ANTES_SVA),
                   pre(HOJE, AGORA_SVA, preco_cheio=40.0))
        # o evento tem de ter saido, senao a ausencia da frase nao mede
        # nada
        self.assertIn(u"ganhou 1 serviço incluso", t)
        self.assertNotIn(u"a vitrine está igual", t)

    def test_cada_campo_da_vitrine_mexendo_sozinho_cala_a_frase(self):
        u"""Um por um. Tirar qualquer campo de CAMPOS_DA_VITRINE faria a
        frase afirmar igualdade sobre um campo que mudou - e e
        exatamente o tipo de afirmacao que este projeto nao pode fazer.

        Mexe-se direto em _a_vitrine_nao_mexeu: pela mensagem, mudar o
        nome ou o destaque muda a identidade do evento e ele vira outra
        coisa, e o teste passaria pelo motivo errado."""
        base = pre(HOJE, AGORA_SVA)[0]
        trocas = {"preco_promocional": 36.0, "preco_cheio": 40.0,
                  "nome_oferta": u"Vivo Pré Turbo", "destaque": "30 GB",
                  "franquia_anunciada_gb": 30, "degrau_mbps": 100,
                  "nivel_bundle": 2}
        self.assertEqual(set(trocas), set(robo.CAMPOS_DA_VITRINE),
                         "campo novo na vitrine sem teste aqui")
        self.assertTrue(robo._a_vitrine_nao_mexeu(base, dict(base)))
        for campo, valor in trocas.items():
            with self.subTest(campo=campo):
                outro = dict(base)
                outro[campo] = valor
                self.assertFalse(robo._a_vitrine_nao_mexeu(base, outro))

    def test_dia_sem_preco_lido_nao_sustenta_igualdade(self):
        u"""None == None e verdade para o Python e mentira para quem le:
        "a vitrine esta igual" sobre um preco que nao foi lido em dia
        nenhum."""
        base = pre(HOJE, AGORA_SVA)[0]
        sem = dict(base, preco_promocional=None)
        self.assertFalse(robo._a_vitrine_nao_mexeu(sem, dict(sem)))
        self.assertFalse(robo._a_vitrine_nao_mexeu(base, sem))


class AConsultaTrazOQueAFraseAfirma(unittest.TestCase):
    u"""O caminho de producao: o select que _indexar manda ao banco."""

    def test_cada_campo_da_vitrine_esta_no_select(self):
        pedidos = []
        guarda = (armazenamento.consultar_tudo, robo.armazenamento)

        def registrar(caminho, pagina=None):
            pedidos.append(caminho)
            return [], None

        armazenamento.consultar_tudo = registrar
        robo.armazenamento = armazenamento
        try:
            robo._indexar(HOJE)
        finally:
            armazenamento.consultar_tudo, robo.armazenamento = guarda

        sel = re.search(r"select=([^&]+)", pedidos[0]).group(1)
        pedidos_campos = {p.split(":")[0] for p in sel.split(",")}
        for campo in robo.CAMPOS_DA_VITRINE + ("apps",):
            with self.subTest(campo=campo):
                self.assertIn(campo, pedidos_campos,
                              "a frase afirma sobre %s e a consulta nao o "
                              "traz" % campo)


if __name__ == "__main__":
    unittest.main()
