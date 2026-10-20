# -*- coding: utf-8 -*-
"""Os achados da SEGUNDA auditoria, cada um com o cenario que o dispara.

A primeira passada achou 23 defeitos. Corrigidos, medidos no dado real -
o que achou mais cinco -, 166 testes e 39 mutacoes depois, a segunda
passada achou NOVE de gravidade alta. Nenhum deles era resquicio da
primeira: todos nasceram ou sobreviveram ao trabalho de hoje.

A licao, e ela vale mais que os defeitos: suite verde e medicao no dado
real nao substituem alguem lendo o codigo com a pergunta certa. A
pergunta que achou estes nove foi sempre a mesma - "qual caminho faz a
mensagem AFIRMAR o que o dado nao sustenta?" - e os nove sao caminhos de
erro, nao de sucesso. Erro de consulta descartado, lista vazia caindo no
ramo do "nada mudou", None formatado como numero, campo desconhecido
afirmado como igual.

Codigo de sucesso a gente testa. Codigo de erro a gente escreve e nunca
mais olha, e e onde a afirmacao falsa mora.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                   # noqa: E402
import vigia                                                  # noqa: E402
from coletores import armazenamento                           # noqa: E402
from _apoio import (COLETA_OK, HOJE, ONTEM, banco, dados,     # noqa: E402
                    em_todas, montar, oferta)


def so_erro(caminho_que_falha, linhas, coletas=None):
    """Instala um banco em que UMA consulta falha e as outras funcionam.

    E o caso que nenhum teste cobria: o erro parcial. A suite tinha o
    banco inteiro de pe e o banco inteiro no chao, e os dois sao faceis -
    e o caminho de erro de verdade e o de uma consulta que cai.
    """
    responder = banco(linhas, coletas)

    def um(caminho):
        if caminho.startswith(caminho_que_falha):
            return None, "HTTP 503: Service Unavailable"
        return responder(caminho)

    armazenamento.consultar = um
    armazenamento.consultar_tudo = lambda c, pagina=None: um(c)
    return um


# ======================================================== gravidade alta

class ConsultaQueCaiNaoEDiaSemColeta(unittest.TestCase):
    """A1. O erro da consulta de "coletas" era descartado num `_`.

    Com um 503 so naquele GET - as capturas respondendo normalmente - a
    mensagem saia:

        O ROBO NAO RODOU HOJE.
        Nenhum registro de coleta. Nada do que vem abaixo e de hoje.

    num dia em que o robo rodou, coletou as nove operadoras e gravou tudo.
    Afirmacao positiva falsa sobre o pior fato possivel, e o bloco "o que
    mudou" suprimido inteiro junto.

    "Nao sei se rodou" e "nao rodou" sao estados diferentes, e o unico
    jeito de distinguir era justo o valor que o codigo jogava fora.
    """

    def test_erro_nao_vira_dia_perdido(self):
        so_erro("coletas", em_todas(data=ONTEM) + em_todas(data=HOJE))
        t, _d = robo.montar_mensagem(HOJE, ONTEM)
        self.assertNotIn("NÃO RODOU", t)
        self.assertIn("estado da coleta", t.lower())

    def test_e_a_comparacao_continua_valendo(self):
        """As capturas respondem: o que mudou e sabido, e nao pode ser
        suprimido porque OUTRA consulta caiu."""
        so_erro("coletas",
                em_todas(preco=100.0, data=ONTEM)
                + em_todas(preco=120.0, data=HOJE))
        t, _d = robo.montar_mensagem(HOJE, ONTEM)
        self.assertIn("100,00 → 120,00", t)

    def test_dia_realmente_sem_registro_continua_dizendo(self):
        t = montar(em_todas(data=ONTEM), em_todas(data=HOJE), coletas=[])
        self.assertIn("NÃO RODOU", t)


class ZeroOfertasNaoENadaMudou(unittest.TestCase):
    """A2. _cobertura devolve None com "h" vazio, e a guarda caia no else.

    Cenario real: gravar_capturas falha em todos os coletores. A tabela
    "coletas" tem linha para cada um (sucesso=False), e "capturas" esta
    vazia. A mensagem saia com "Nenhuma mudanca de preco, composicao ou
    nome" sobre ZERO ofertas comparadas.

    A guarda de cobertura foi escrita exactamente para isto e nao cobria
    o caso extremo, porque o extremo e None e nao 0.
    """

    def _dia_sem_captura(self):
        falhou = [dict(c, sucesso=False) for c in COLETA_OK]
        return montar([], [], coletas=falhou)

    def test_sem_captura_nao_se_afirma_ausencia(self):
        t = self._dia_sem_captura()
        self.assertNotIn("Nenhuma mudança", t)

    def test_e_a_mensagem_diz_que_nao_houve_comparacao(self):
        self.assertIn("nenhuma oferta", self._dia_sem_captura().lower())


class FalhaDeGravacaoNaoEPracaFaltando(unittest.TestCase):
    """A2b. A manchete da falha usava pracas_ok, que nao e o motivo.

    Coletor que leu as 20 pracas e nao conseguiu GRAVAR sai com
    pracas_ok=20 e sucesso=False. A manchete escrevia "Vivo em 20 de 20
    pracas" - que descreve um sucesso - como explicacao de uma falha, nove
    vezes seguidas.
    """

    def test_vinte_de_vinte_nao_explica_falha(self):
        falhou = [dict(c, sucesso=False) for c in COLETA_OK]
        t = montar(em_todas(data=ONTEM), em_todas(data=HOJE), coletas=falhou)
        self.assertIn("COLETA INCOMPLETA", t)
        self.assertNotIn("em 20 de 20 praças", t)

    def test_praca_faltando_continua_sendo_dita(self):
        falhou = [dict(c) for c in COLETA_OK]
        falhou[0].update({"pracas_ok": 12, "sucesso": False})
        t = montar(em_todas(data=ONTEM), em_todas(data=HOJE), coletas=falhou)
        self.assertIn("12 de 20", t)


class EntregaDesconhecidaNaoEEntregaIgual(unittest.TestCase):
    """A3. "mesma entrega (None )" saia na mensagem e "None" no PDF.

    A Brisanet veio 119 linhas por dia sem velocidade em 18 dos 21 dias
    medidos. Uma dessas ofertas mudando de versao produzia:

        100,00 -> 120,00 (+20%)   pela mesma entrega (None )

    Duas coisas erradas numa linha: o token cru, e a AFIRMACAO de que a
    entrega e a mesma sobre um campo que nao foi lido em nenhum dos dias.
    """

    def _evento(self, **kw):
        base = {"unidade": "", "antes_preco": 100.0, "agora_preco": 120.0,
                "antes_entrega": None, "agora_entrega": None,
                "antes_bundle": 0, "agora_bundle": 0,
                "bundle_antes": None, "bundle_agora": None,
                "preco_mudou": True, "entrega_mudou": False,
                "versao_mudou": True}
        base.update(kw)
        return base

    def test_nao_sai_None_na_linha(self):
        for linha in robo._o_que_mudou(self._evento()):
            self.assertNotIn("None", linha)

    def test_nem_se_afirma_que_a_entrega_e_a_mesma(self):
        linhas = " ".join(robo._o_que_mudou(self._evento()))
        self.assertNotIn("mesma entrega", linhas)
        self.assertIn("entrega não lida", linhas)

    def test_entrega_conhecida_continua_saindo(self):
        linhas = " ".join(robo._o_que_mudou(
            self._evento(antes_entrega=50, agora_entrega=50, unidade="GB")))
        self.assertIn("pela mesma entrega (50 GB)", linhas)


class PrecoDesconhecidoNaoEPrecoIgual(unittest.TestCase):
    """A4. "mesmo preco (35,00)" sobre um dia em que o preco de ontem era
    desconhecido.

    preco_mudou e False quando QUALQUER dos dois lados e None - a guarda
    certa para nao inventar reajuste -, e o else de _o_que_mudou lia isso
    como "o preco nao mudou". Nao mudou e nao se sabe sao estados
    diferentes.
    """

    def _evento(self, pa, pd):
        return {"unidade": "GB", "antes_preco": pa, "agora_preco": pd,
                "antes_entrega": 20, "agora_entrega": 20,
                "antes_bundle": 0, "agora_bundle": 0,
                "bundle_antes": None, "bundle_agora": None,
                "preco_mudou": False, "entrega_mudou": False,
                "versao_mudou": True}

    def test_preco_ausente_ontem_nao_vira_preco_igual(self):
        linhas = " ".join(robo._o_que_mudou(self._evento(None, 35.0)))
        self.assertNotIn("mesmo preço", linhas)
        self.assertIn("preço não lido", linhas)

    def test_preco_ausente_hoje_tambem(self):
        linhas = " ".join(robo._o_que_mudou(self._evento(35.0, None)))
        self.assertNotIn("mesmo preço", linhas)

    def test_preco_igual_de_verdade_continua_saindo(self):
        linhas = " ".join(robo._o_que_mudou(self._evento(35.0, 35.0)))
        self.assertIn("mesmo preço (35,00)", linhas)


class ColisaoDeOntemNaoEDeHoje(unittest.TestCase):
    """A5. "cego = cego_h or cego_o", e o numero de ontem ia para o
    denominador da cobertura de HOJE.

    Com hoje limpo e ontem com um par indistinguivel que nao existe mais,
    a mensagem dizia "a comparacao alcancou so 83% das ofertas de hoje" e
    "2 ofertas ficaram fora da comparacao DE HOJE" - as duas falsas. No
    PDF a linha Total nao fechava com as linhas por operadora.
    """

    def _par(self, data):
        a = oferta(produto="combo", nome="Vivo Família 2 + TV", preco=290.0,
                   gb=None, mbps=700, data=data)
        return [a, dict(a, preco_promocional=390.0)]

    def test_hoje_limpo_tem_cobertura_cheia(self):
        r = dados(em_todas(data=ONTEM) + self._par(ONTEM),
                  em_todas(data=HOJE))
        self.assertEqual(r["cobertura"]["fora"], 0)
        self.assertEqual(r["cobertura"]["fracao"], 1.0)

    def test_e_a_mensagem_nao_fala_de_ofertas_fora(self):
        t = montar(em_todas(data=ONTEM) + self._par(ONTEM),
                   em_todas(data=HOJE))
        self.assertNotIn("ficaram fora da comparação de hoje", t)

    def test_colisao_de_hoje_continua_contando(self):
        r = dados(em_todas(data=ONTEM) + self._par(ONTEM),
                  em_todas(data=HOJE) + self._par(HOJE))
        self.assertEqual(r["cobertura"]["fora"], 2)


class OMaiorMovimentoVaiParaAMensagem(unittest.TestCase):
    """A7. A mensagem mostrava 3 de N na ordem do indice - chave.asc -,
    enquanto o PDF ordenava por tamanho da variacao.

    Com cinco reajustes de +1% a +200%, a mensagem saia com "+1%", "+2%"
    e "+3%" e a linha "e mais 2 mudancas de preco no relatorio". A maior
    variacao do dia era justamente a que nao chegava ao canal que a
    pessoa le no telefone.
    """

    def test_os_tres_maiores_sao_os_que_aparecem(self):
        nomes = ("A Alfa", "B Beta", "C Gama", "D Delta", "E Eps")
        subidas = (1.0, 2.0, 3.0, 100.0, 200.0)
        ontem, hoje = [], []
        for nome, _s in zip(nomes, subidas):
            ontem += em_todas(nome=nome, preco=100.0, data=ONTEM,
                              chave="Vivo|movel|%sgb|simples" % nome[0])
        for nome, s in zip(nomes, subidas):
            hoje += em_todas(nome=nome, preco=100.0 + s, data=HOJE,
                             chave="Vivo|movel|%sgb|simples" % nome[0])
        t = montar(ontem, hoje)
        self.assertIn("D Delta", t)
        self.assertIn("E Eps", t)
        self.assertNotIn("A Alfa", t)
        self.assertIn("e mais 2 mudanças de preço no relatório", t)


class VigiaOlhaOPiorSaltoENaoOMaior(unittest.TestCase):
    """A6. A gravidade do grupo saia de saltos[0], o de maior modulo.

    Medido: Claro 99,90 -> 24,60 (-75%, o preco fantasma) junto com Vivo
    100,00 -> 195,00 (+95%, modulo maior e nao severo). O achado inteiro
    virava "atencao", resumo devolvia vazio, e o preco fantasma - o
    defeito que gerou este modulo - nao chegava a mensagem. O texto que
    sobrava, no relatorio, nomeava outra operadora.
    """

    def _dia(self, n=30):
        return [{"operadora": "Vivo", "produto": "movel", "praca": "P/X",
                 "nome_oferta": "O%d" % i, "preco_promocional": 100.0,
                 "franquia_anunciada_gb": 50, "degrau_mbps": None,
                 "chave": "c%d" % i} for i in range(n)]

    def test_o_severo_manda_na_gravidade(self):
        ontem = self._dia()
        hoje = self._dia()
        hoje[0]["preco_promocional"] = 24.60        # -75%, severo
        hoje[1]["preco_promocional"] = 195.00       # +95%, modulo maior
        r = vigia.achados(hoje, {"2026-10-%02d" % (10 + i): ontem
                                 for i in range(5)})
        graves = [t for g, t in r if g == "grave"]
        self.assertTrue(any("salto" in t for t in graves), r)
        self.assertIn("salto", vigia.resumo(r))

    def test_e_o_exemplo_citado_e_o_severo(self):
        ontem = self._dia()
        hoje = self._dia()
        hoje[0]["preco_promocional"] = 24.60
        hoje[1]["preco_promocional"] = 195.00
        r = vigia.achados(hoje, {"2026-10-%02d" % (10 + i): ontem
                                 for i in range(5)})
        salto = [t for g, t in r if "salto" in t][0]
        self.assertIn("24,60", salto.replace(".", ","))

    def test_dois_nao_severos_continuam_em_atencao(self):
        ontem = self._dia()
        hoje = self._dia()
        hoje[0]["preco_promocional"] = 160.0
        hoje[1]["preco_promocional"] = 165.0
        r = vigia.achados(hoje, {"2026-10-%02d" % (10 + i): ontem
                                 for i in range(5)})
        self.assertEqual([t for g, t in r if g == "grave" and "salto" in t], [])


# ======================================================= gravidade media

class UmDesaparecimentoEUmEvento(unittest.TestCase):
    """M1. A oferta de ONTEM podia ser o "antes" de dois eventos.

    A docstring de _oferta_remodelada garante que nenhuma oferta cai nos
    dois detectores, e isso valia por oferta de HOJE. Com ontem tendo uma
    oferta e hoje tendo duas - uma de mesma chave e outro nome, outra de
    mesmo nome e outra chave -, _renomeadas pareava a primeira e
    _oferta_remodelada a segunda, as duas contra a MESMA base de R$ 100.
    Saiam dois reajustes, "+30%" e "+60%", e total_mud contava dois onde
    havia um desaparecimento.
    """

    def _dia(self):
        ontem = em_todas(operadora="Vivo", produto="fibra",
                         nome="Vivo Fibra 600 Mega", preco=100.0,
                         gb=None, mbps=600, data=ONTEM,
                         chave="Vivo|fibra|600mbps|simples")
        hoje = em_todas(operadora="Vivo", produto="fibra",
                        nome="Vivo Fibra Pro", preco=130.0,
                        gb=None, mbps=600, data=HOJE,
                        chave="Vivo|fibra|600mbps|simples")
        hoje += em_todas(operadora="Vivo", produto="fibra",
                         nome="Vivo Fibra 600 Mega", preco=160.0,
                         gb=None, mbps=600, data=HOJE,
                         chave="Vivo|fibra|600mbps|com_apps")
        return ontem, hoje

    def test_a_mesma_base_nao_vira_dois_reajustes(self):
        ontem, hoje = self._dia()
        r = dados(ontem, hoje)
        total = (len(r["mudancas_preco"]) + len(r["renomeadas"])
                 + len(r["remodeladas"]) + len(r["leitura"]))
        self.assertEqual(total, 1, "um desaparecimento, um evento")

    def test_e_a_mensagem_conta_uma(self):
        ontem, hoje = self._dia()
        t = montar(ontem, hoje)
        self.assertIn("1 mudan\u00e7a hoje", t)


class DiaAnteriorAusenteNaoEDegrauQueVoltou(unittest.TestCase):
    """M5. Sem ontem no banco, TODA entrega de hoje parece ter voltado.

    _degraus_que_voltaram pergunta "esta entrega estava na vitrine
    ontem?" e, com o dia anterior faltando, a resposta e nao para todas.
    Ele entao procura a ultima venda no historico e anuncia "100 Mbps
    voltou por 100,00, +11% sobre os 90,00 de 18/10" sobre um degrau que
    nunca saiu da vitrine - so falta o dia 19 no banco.
    """

    def test_sem_ontem_nao_se_diz_que_voltou(self):
        historico = em_todas(operadora="Vivo", produto="fibra",
                             nome="Vivo Fibra", preco=90.0, gb=None,
                             mbps=100, data="2026-10-18")
        hoje = em_todas(operadora="Vivo", produto="fibra",
                        nome="Vivo Fibra", preco=100.0, gb=None,
                        mbps=100, data=HOJE)
        r = dados([], hoje, extras=historico)
        self.assertEqual(r["voltaram"], [])

    def test_com_ontem_o_detector_continua_funcionando(self):
        """Ontem com OUTRO nome: sem isso a oferta de hoje pareia com a de
        ontem como remodelada, e a remodelada silencia o "voltou" de
        proposito - seria a mesma noticia duas vezes."""
        historico = em_todas(operadora="Vivo", produto="fibra",
                             nome="Vivo Fibra", preco=90.0, gb=None,
                             mbps=100, data="2026-10-18")
        ontem = em_todas(operadora="Vivo", produto="fibra",
                         nome="Vivo Fibra Light", preco=90.0, gb=None,
                         mbps=200, data=ONTEM)
        hoje = em_todas(operadora="Vivo", produto="fibra",
                        nome="Vivo Fibra", preco=100.0, gb=None,
                        mbps=100, data=HOJE)
        r = dados(ontem, hoje, extras=historico)
        self.assertEqual(len(r["voltaram"]), 1, r["voltaram"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
