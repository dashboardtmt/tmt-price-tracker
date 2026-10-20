# -*- coding: utf-8 -*-
"""Os detectores que a suite nao cobria, cada um no caso que o criou.

AUDITORIA 14. O provador de mutacoes mediu que sete das onze mutacoes
que a auditoria escreveu passavam verdes: _renomeadas, a escada,
_degraus_que_voltaram e o alcance nao tinham teste nenhum. Cada um deles
existe por causa de um movimento real de operadora - e sem teste, o
proximo refactor os desliga em silencio, que e exatamente como o
"limit=4000" sobreviveu.

Cada classe aqui tem o par: o caso que o detector TEM de pegar, e o caso
parecido em que ele TEM de ficar calado. Detector sem o segundo teste
nao esta coberto, esta so exercitado - e o que quebra em producao e o
falso positivo, nao o negativo.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                   # noqa: E402
from _apoio import HOJE, ONTEM, em_todas, montar, oferta       # noqa: E402


def indexar(linhas):
    return {robo._identidade(l): l for l in linhas}


class OfertaRenomeada(unittest.TestCase):
    """02/10/2026: "TIM Controle" virou "TIM Controle Smart" em 20
    pracas. O nome entra na identidade para nao comparar ofertas
    diferentes, e isso cria o ponto cego: oferta renomeada nao casa com a
    de ontem e sai da comparacao sem gerar alerta. Trocar o nome junto
    com o preco e justamente como um repasse passa desapercebido.
    """

    def test_nome_novo_e_preco_novo_aparecem_juntos(self):
        achou, _usadas = robo._renomeadas(
            indexar([oferta(operadora="TIM", produto="controle",
                            nome="TIM Controle Smart", preco=62.99, gb=40,
                            chave="TIM|controle|40gb|simples")]),
            indexar([oferta(operadora="TIM", produto="controle",
                            nome="TIM Controle", preco=58.99, gb=40,
                            data=ONTEM, chave="TIM|controle|40gb|simples")]))
        self.assertEqual(len(achou), 1)
        self.assertEqual(achou[0]["antes"]["nome_oferta"], "TIM Controle")
        self.assertEqual(achou[0]["atual"]["preco_promocional"], 62.99)

    def test_a_mensagem_diz_que_o_preco_foi_junto(self):
        t = montar(em_todas(operadora="TIM", produto="controle",
                            nome="TIM Controle", preco=58.99, gb=40,
                            data=ONTEM, chave="TIM|controle|40gb|simples"),
                   em_todas(operadora="TIM", produto="controle",
                            nome="TIM Controle Smart", preco=62.99, gb=40,
                            data=HOJE, chave="TIM|controle|40gb|simples"))
        self.assertIn("mudou de nome", t)
        self.assertIn("58,99 para 62,99", t)

    def test_duas_candidatas_nao_viram_palpite(self):
        """Com duas sobrando de cada lado, qualquer emparelhamento seria
        chute - e chute aqui inventa reajuste em cima de nome trocado."""
        hoje = indexar([oferta(nome="A nova", preco=10.0, chave="k"),
                        oferta(nome="B nova", preco=20.0, chave="k")])
        ontem = indexar([oferta(nome="A velha", preco=10.0, chave="k",
                                data=ONTEM),
                         oferta(nome="B velha", preco=20.0, chave="k",
                                data=ONTEM)])
        self.assertEqual(robo._renomeadas(hoje, ontem)[0], [])

    def test_safra_no_nome_nao_e_renomeacao(self):
        """A NuCel carimba o mes no nome: "[SET] OFT NC PF PROMO 12M" vira
        "[OUT] ...". Toda virada de mes isso geraria uma renomeacao falsa
        em cada oferta dela - e virada de mes e quando preco muda."""
        hoje = indexar([oferta(operadora="NuCel", praca="Brasil/BR",
                               nome="[OUT] OFT NC PF PROMO 12M", preco=45.0)])
        ontem = indexar([oferta(operadora="NuCel", praca="Brasil/BR",
                                nome="[SET] OFT NC PF PROMO 12M", preco=45.0,
                                data=ONTEM)])
        self.assertEqual(robo._renomeadas(hoje, ontem)[0], [])


class OIdentificadoDeOntemSoServeUmaVez(unittest.TestCase):
    """AUDITORIA 2, M1. _renomeadas devolve tambem as identidades de
    ontem que consumiu, porque a oferta de ontem so pode ser o "antes"
    de UM evento.

    Nao da para reconstruir essa lista de fora: _agrupar guarda um
    "antes" por grupo, e foi assim que a primeira tentativa de consertar
    o M1 protegeu uma praca e deixou as outras 19 - a mensagem saiu "em
    19 de 20", que foi o sinal de que o conserto estava errado.
    """

    def test_devolve_uma_identidade_por_praca(self):
        ontem = em_todas(operadora="TIM", produto="controle",
                         nome="TIM Controle", preco=58.99, gb=40,
                         data=ONTEM, chave="TIM|controle|40gb|simples")
        hoje = em_todas(operadora="TIM", produto="controle",
                        nome="TIM Controle Smart", preco=62.99, gb=40,
                        data=HOJE, chave="TIM|controle|40gb|simples")
        eventos, usadas = robo._renomeadas(indexar(hoje), indexar(ontem))
        self.assertEqual(len(eventos), 1, "uma mudanca nacional, um evento")
        self.assertEqual(len(usadas), 20, "mas as 20 identidades consumidas")


class EscadaReorganizada(unittest.TestCase):
    """15/10/2026 a Vivo tirou 5 GB do pre-pago de R$ 30; em 20/10 fez o
    contrario, manteve a entrega e subiu o preco. Sao o mesmo fato visto
    de dois angulos, e ver so um lado deixa metade dos movimentos passar.
    """

    def _escada(self, pares, data):
        """A escada da operadora, com o nome FIXO em cada degrau.

        O nome nao pode carregar o numero do degrau: a escada so pareia
        quando o nome e o mesmo nos dois dias - trava que existe para
        "oferta que sumiu" nao virar "preco que subiu" - e nome com o
        GB dentro muda junto com ele.
        """
        linhas = []
        for i, (preco, gb) in enumerate(pares):
            linhas += em_todas(operadora="Vivo", produto="prepago",
                               nome="Vivo Pré %s" % "ABCDE"[i], preco=preco,
                               gb=gb, data=data)
        return linhas

    def test_mesmo_preco_entregando_menos(self):
        eventos, suprimir = robo._grades_reorganizadas(
            indexar(self._escada([(30.0, 20)], HOJE)),
            indexar(self._escada([(30.0, 25)], ONTEM)))
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["saltos"], [(30.0, 25, 20)])
        self.assertIn(("Vivo", "prepago"), suprimir)

    def test_mesma_entrega_custando_mais(self):
        eventos, _s = robo._grades_reorganizadas(
            indexar(self._escada([(35.0, 25)], HOJE)),
            indexar(self._escada([(30.0, 25)], ONTEM)))
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["precos"], [(25, 30.0, 35.0)])

    def test_a_mensagem_diz_quanto_de_internet_se_perdeu(self):
        t = montar(self._escada([(30.0, 25)], ONTEM),
                   self._escada([(30.0, 20)], HOJE))
        self.assertIn("25 → 20 GB", t)
        self.assertIn("-20% de internet pelo mesmo preço", t)

    def test_escada_parada_nao_gera_evento(self):
        eventos, suprimir = robo._grades_reorganizadas(
            indexar(self._escada([(30.0, 25), (40.0, 40)], HOJE)),
            indexar(self._escada([(30.0, 25), (40.0, 40)], ONTEM)))
        self.assertEqual(eventos, [])
        self.assertEqual(suprimir, set())

    def test_degrau_novo_nao_atrapalha_os_outros(self):
        """A versao anterior exigia a lista inteira de precos identica
        nos dois dias e desistia se um degrau novo aparecesse - que e
        exatamente o que a Vivo fez em 20/10."""
        eventos, _s = robo._grades_reorganizadas(
            indexar(self._escada([(35.0, 25), (50.0, 60)], HOJE)),
            indexar(self._escada([(30.0, 25)], ONTEM)))
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["precos"], [(25, 30.0, 35.0)])

    def test_oferta_que_sumiu_nao_e_preco_que_subiu(self):
        """Entre 17 e 18/10 o "Vivo Total Essencial" de R$ 100 faltou
        numa praca e o mais barato de 500 Mega virou o "Total Pro" de
        R$ 160. Sem a trava do nome, o aviso diria +60%."""
        hoje = indexar(em_todas(operadora="Vivo", produto="combo",
                                nome="Vivo Total Pro", preco=160.0,
                                gb=None, mbps=500, data=HOJE))
        ontem = indexar(em_todas(operadora="Vivo", produto="combo",
                                 nome="Vivo Total Essencial", preco=100.0,
                                 gb=None, mbps=500, data=ONTEM))
        eventos, _s = robo._grades_reorganizadas(hoje, ontem)
        self.assertEqual(eventos, [])


class DegrauQueVoltou(unittest.TestCase):
    """O movimento feito em dois tempos: em 15/10 a Vivo tirou o degrau de
    25 GB do pre-pago, em 20/10 devolveu por R$ 35 em vez de R$ 30. No dia
    15 foi saida de oferta; no dia 20, entrada. O reajuste de 16,7% ficou
    entre os dois dias, invisivel a quem compara hoje com ontem.
    """

    def _com_historico(self, historico):
        def responder(caminho, pagina=None):
            if caminho.startswith("capturas?operadora="):
                return list(historico), None
            return [], None
        guarda = robo.armazenamento.consultar_tudo
        robo.armazenamento.consultar_tudo = responder
        self.addCleanup(lambda: setattr(robo.armazenamento,
                                        "consultar_tudo", guarda))

    def test_a_ultima_venda_e_o_ponto_de_comparacao(self):
        self._com_historico([
            {"data_captura": "2026-10-14", "praca": "Sao Paulo/SP",
             "nome_oferta": "Vivo Pré", "preco_promocional": 30.0,
             "franquia_anunciada_gb": 25, "degrau_mbps": None}])
        achou = robo._degraus_que_voltaram(
            indexar([oferta(produto="prepago", nome="Vivo Pré",
                            preco=35.0, gb=25)]),
            {}, HOJE)
        self.assertEqual(len(achou), 1)
        self.assertEqual((achou[0]["antes"], achou[0]["agora"]), (30.0, 35.0))
        self.assertEqual(achou[0]["quando"], "2026-10-14")
        self.assertEqual(achou[0]["unidade"], "GB")

    def test_degrau_que_voltou_pelo_mesmo_preco_nao_e_noticia(self):
        self._com_historico([
            {"data_captura": "2026-10-14", "praca": "Sao Paulo/SP",
             "nome_oferta": "Vivo Pré", "preco_promocional": 30.0,
             "franquia_anunciada_gb": 25, "degrau_mbps": None}])
        achou = robo._degraus_que_voltaram(
            indexar([oferta(produto="prepago", nome="Vivo Pré",
                            preco=30.0, gb=25)]),
            {}, HOJE)
        self.assertEqual(achou, [])

    def test_degrau_que_estava_ontem_nao_voltou(self):
        self._com_historico([])
        linhas = [oferta(produto="prepago", nome="Vivo Pré", preco=35.0,
                         gb=25)]
        achou = robo._degraus_que_voltaram(
            indexar(linhas),
            indexar([dict(l, data_captura=ONTEM) for l in linhas]), HOJE)
        self.assertEqual(achou, [])

    def test_degrau_estreando_nao_tem_com_que_comparar(self):
        """Sem venda anterior nos 45 dias nao ha preco de referencia, e
        inventar um seria o oposto do que o projeto faz."""
        self._com_historico([])
        achou = robo._degraus_que_voltaram(
            indexar([oferta(produto="prepago", nome="Vivo Pré",
                            preco=35.0, gb=25)]),
            {}, HOJE)
        self.assertEqual(achou, [])


class CoberturaDaComparacao(unittest.TestCase):
    """Zero mudancas pode ser mercado parado ou comparacao cega, e as
    duas saiam escritas igual. O numero que separa as duas e quantas
    ofertas de hoje encontraram par em ontem."""

    def test_dia_pareado_tem_cobertura_alta(self):
        c = robo._cobertura(indexar(em_todas(data=HOJE)),
                            indexar(em_todas(data=ONTEM)))
        self.assertEqual(c["fracao"], 1.0)
        self.assertEqual(c["pares"], 20)

    def test_vitrine_trocada_derruba_a_cobertura(self):
        c = robo._cobertura(
            indexar(em_todas(nome="Oferta nova", data=HOJE)),
            indexar(em_todas(nome="Oferta velha", data=ONTEM)))
        self.assertEqual(c["fracao"], 0.0)

    def test_a_mensagem_avisa_quando_a_comparacao_foi_cega(self):
        """Nome e degrau trocados com o preco parado: nenhum detector
        consegue parear, e com razao - nao ha o que identifique a oferta
        de ontem na de hoje. O que nao pode e a mensagem dizer "nenhuma
        mudanca" sobre uma vitrine que ela nao conseguiu ler."""
        t = montar(em_todas(nome="Oferta velha", gb=50, data=ONTEM),
                   em_todas(nome="Oferta nova", gb=40, data=HOJE))
        self.assertIn("alcançou só 0%", t)
        self.assertIn("não confirma", t)

    def test_a_ressalva_vale_tambem_no_dia_com_mudanca(self):
        """O buraco inverso: cobertura baixa COM mudanca encontrada fazia
        a mensagem contar as mudancas sem dizer que nao olhou o resto, e
        quem le entende que aquilo e a historia inteira do dia."""
        ontem = (em_todas(nome="Fica", preco=100.0, data=ONTEM)
                 + em_todas(nome="Sai", preco=50.0, gb=30, data=ONTEM)
                 + em_todas(nome="Sai 2", preco=60.0, gb=20, data=ONTEM))
        hoje = (em_todas(nome="Fica", preco=120.0, data=HOJE)
                + em_todas(nome="Entra", preco=50.0, gb=25, data=HOJE)
                + em_todas(nome="Entra 2", preco=60.0, gb=15, data=HOJE))
        t = montar(ontem, hoje)
        self.assertIn("100,00 → 120,00", t)
        self.assertIn("pode haver mudança fora do que foi comparado", t)

    def test_e_nao_avisa_quando_a_comparacao_foi_inteira(self):
        t = montar(em_todas(data=ONTEM), em_todas(data=HOJE))
        self.assertIn("Nenhuma mudança de preço", t)
        self.assertNotIn("não confirma", t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
