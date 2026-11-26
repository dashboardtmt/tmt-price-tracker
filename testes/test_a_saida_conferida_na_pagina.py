# -*- coding: utf-8 -*-
u"""A SEGUNDA BARREIRA DA SAIDA: a pagina relida antes de afirmar.

Item 3 da fila de 24/11/2026, escolha de quem le: construir, comecando por
TIM e Unifique; nas outras, "saida nao conferida na pagina" ate ficar
pronto. Os sete filtros de _ofertas_que_sairam olham o dado gravado, que e
a leitura de uma passada pela pagina; produto sumindo de praca coletada foi
leitura 23 de 23 vezes nos 49 dias medidos, e 21 voltaram no dia seguinte.

O robo rele a pagina com o coletor de producao (robo.RELEITORES) so quando a
variavel CONFERIR_SAIDAS existe - o passo do aviso no diario.yml. Aqui o
releitor e de mentira: a suite nao toca a rede.
"""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))

import robo                                                   # noqa: E402
from _apoio import HOJE, ONTEM, dados, montar, oferta         # noqa: E402

ANTES = ["2026-10-18", "2026-10-19"]


def pracas(n=3):
    from coletores.pracas import PRACAS, rotulo
    return [rotulo(p) for p in PRACAS][:n]


def linhas(op, nome, data, onde, gb=30, produto="controle"):
    return [oferta(operadora=op, produto=produto, nome=nome, preco=59.99, gb=gb,
                   praca=p, data=data, chave="%s|%s|%dgb|simples" % (op, produto, gb))
            for p in onde]


def dia(op, nomes=("Controle Que Sai",)):
    u"""A oferta (ou as ofertas) que existiam ate ontem e hoje nao, e uma
    que fica nos dois dias para o dia nao ser vazio."""
    onde = pracas(3)
    ontem, hist = [], []
    for i, nome in enumerate(nomes):
        ontem += linhas(op, nome, ONTEM, onde, gb=30 + i)
        for d in ANTES:
            hist += linhas(op, nome, d, onde, gb=30 + i)
    fica = linhas(op, "Controle Que Fica", ONTEM, onde, gb=77)
    hoje = linhas(op, "Controle Que Fica", HOJE, onde, gb=77)
    return ontem + fica, hoje, hist


class _ComBarreira(unittest.TestCase):

    def setUp(self):
        guarda_env = os.environ.get("CONFERIR_SAIDAS")
        os.environ["CONFERIR_SAIDAS"] = "1"
        guarda = robo.RELEITORES
        self.chamadas = []

        def volta():
            robo.RELEITORES = guarda
            if guarda_env is None:
                os.environ.pop("CONFERIR_SAIDAS", None)
            else:
                os.environ["CONFERIR_SAIDAS"] = guarda_env
        self.addCleanup(volta)

    def releitor(self, op, pagina):
        u"""pagina: as ofertas que a releitura devolve, ou uma excecao."""
        def reler(praca, produto):
            self.chamadas.append((op, praca, produto))
            if isinstance(pagina, Exception):
                raise pagina
            return {"ofertas": pagina}
        robo.RELEITORES = {op: reler}


class ABarreira(_ComBarreira):

    def test_a_pagina_ainda_mostra_e_a_saida_nao_e_noticia(self):
        self.releitor("TIM", [{"produto": "controle", "nome_oferta": "Controle Que Sai"},
                              {"produto": "controle", "nome_oferta": "Controle Que Fica"}])
        ontem, hoje, hist = dia("TIM")
        d = dados(ontem, hoje, extras=hist)
        self.assertFalse(d["saidas"])
        self.assertEqual([s["nome_oferta"] for s in d["saidas_desmentidas"]],
                         ["Controle Que Sai"])
        t = montar(ontem, hoje, extras=hist)
        self.assertNotIn("saiu da vitrine", t)

    def test_a_pagina_confirma_e_a_saida_sai_sem_ressalva(self):
        self.releitor("TIM", [{"produto": "controle", "nome_oferta": "Controle Que Fica"}])
        ontem, hoje, hist = dia("TIM")
        t = montar(ontem, hoje, extras=hist)
        self.assertIn("saiu da vitrine", t)
        self.assertNotIn(robo.SAIDA_NAO_CONFERIDA, t)
        self.assertNotIn(robo.SAIDA_SEM_RELEITURA, t)

    def test_a_serie_e_procurada_em_todos_os_produtos(self):
        u"""Filtro 2: a serie e por operadora, nao por balde - a oferta que
        o classificador trocou de produto continua na pagina."""
        self.releitor("TIM", [{"produto": "controle", "nome_oferta": "Controle Que Fica"},
                              {"produto": "movel", "nome_oferta": "Controle Que Sai"}])
        ontem, hoje, hist = dia("TIM")
        self.assertFalse(dados(ontem, hoje, extras=hist)["saidas"])

    def test_releitura_que_falha_deixa_a_saida_com_a_ressalva(self):
        self.releitor("TIM", RuntimeError("HTTP 503"))
        ontem, hoje, hist = dia("TIM")
        t = montar(ontem, hoje, extras=hist)
        self.assertIn("saiu da vitrine", t)
        self.assertIn(robo.SAIDA_SEM_RELEITURA, t)

    def test_releitura_sem_o_produto_nao_prova_nada(self):
        u"""Relida que nao trouxe nenhum controle nao diz que o controle
        saiu - diz que a releitura nao leu."""
        self.releitor("TIM", [{"produto": "fibra", "nome_oferta": "TIM Ultrafibra 1 Giga"}])
        ontem, hoje, hist = dia("TIM")
        t = montar(ontem, hoje, extras=hist)
        self.assertIn(robo.SAIDA_SEM_RELEITURA, t)

    def test_operadora_sem_releitor_sai_dita_nao_conferida(self):
        self.releitor("TIM", [])
        ontem, hoje, hist = dia("Vivo")
        t = montar(ontem, hoje, extras=hist)
        self.assertIn("saiu da vitrine", t)
        self.assertIn(u"(saída não conferida na página)", t)

    def test_rele_uma_vez_por_operadora_e_praca(self):
        self.releitor("TIM", [{"produto": "controle", "nome_oferta": "Controle Que Fica"}])
        ontem, hoje, hist = dia("TIM", nomes=("Controle Um", "Controle Dois"))
        d = dados(ontem, hoje, extras=hist)
        self.assertEqual(len(d["saidas"]), 2)
        self.assertEqual(len(self.chamadas), 1)

    def test_o_pdf_leva_a_ressalva(self):
        self.releitor("TIM", [])
        ontem, hoje, hist = dia("Vivo")
        d = dados(ontem, hoje, extras=hist)
        self.assertEqual(d["saidas"][0]["conferida_texto"], robo.SAIDA_NAO_CONFERIDA)


class SemAVariavel(unittest.TestCase):

    def test_sem_conferir_saidas_nada_muda_e_ninguem_rele(self):
        u"""A suite, a bancada e o relatorio rodam sem rede: sem a variavel,
        a barreira nao rele e nao escreve ressalva."""
        guarda_env = os.environ.pop("CONFERIR_SAIDAS", None)
        if guarda_env is not None:
            self.addCleanup(os.environ.__setitem__, "CONFERIR_SAIDAS", guarda_env)
        guarda = robo.RELEITORES
        robo.RELEITORES = {"TIM": lambda *a: self.fail("releu sem a variavel")}
        self.addCleanup(setattr, robo, "RELEITORES", guarda)
        ontem, hoje, hist = dia("TIM")
        t = montar(ontem, hoje, extras=hist)
        self.assertIn("saiu da vitrine", t)
        self.assertNotIn(robo.SAIDA_NAO_CONFERIDA, t)

    def test_o_aviso_do_robo_liga_a_barreira(self):
        with open(os.path.join(os.path.dirname(AQUI), ".github", "workflows", "diario.yml"),
                  encoding="utf-8") as f:
            self.assertIn('CONFERIR_SAIDAS: "1"', f.read())


if __name__ == "__main__":
    unittest.main()
