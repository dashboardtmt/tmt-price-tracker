# -*- coding: utf-8 -*-
u"""Mesmo preco, outra velocidade - o detector que faltava.

O QUE ELE PEGA, E POR QUE NINGUEM PEGAVA. Em outubro a Vivo moveu o
plano de R$ 100 de 700 para 600 Mega (03/10), voltou para 700 (08/10) e
desceu de novo (15/10), nas 20 pracas, com o PRECO PARADO nos tres dias.
Preco parado e o sinal que todos os outros detectores usam para concluir
que nada aconteceu: a chave de continuidade carrega o degrau, entao
degrau novo vira "uma oferta saiu e outra entrou"; a remodelada exige
preco E entrega mexendo juntos; a grade olha a escada inteira. As tres
trocas passaram caladas.

AS DUAS ARMADILHAS QUE A MEDICAO MOSTROU, e que estao presas aqui:

  1. Na TIM a velocidade mora DENTRO do nome - "Ultracombo 7 500MEGA +
     65GB" virou "600MEGA" em 27/10 -, entao parear por nome cru perde
     justamente a TIM.
  2. Parear so pelo PONTO DE PRECO, sem o nome, inventa troca: medido
     nos 41 dias, isso produziu uma mudanca de 600 para 1000 Mega na TIM
     que nunca houve - eram duas ofertas diferentes dividindo R$ 149,99
     em dias seguidos.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _apoio import HOJE, ONTEM, dados, montar, oferta, sem_declaracao  # noqa: E402

import auditor                                                # noqa: E402
import robo                                                   # noqa: E402

PRACAS = ("Sao Paulo/SP", "Rio de Janeiro/RJ", "Recife/PE")


def fibra(nome, preco, mbps, data, pracas=PRACAS, operadora="Vivo",
          produto="fibra"):
    return [oferta(operadora=operadora, produto=produto, nome=nome,
                   preco=preco, gb=None, mbps=mbps, praca=p, data=data)
            for p in pracas]


class ATrocaDeVelocidadePeloMesmoPreco(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)

    def test_a_troca_da_claro_sai_na_mensagem(self):
        u"""O caso real de 14/10/2026: o "Especial" de R$ 99,90 girando
        entre 750 e 600 Mega. Oito vezes em outubro, e nenhuma saiu por
        canal nenhum."""
        t = montar(fibra("Claro Multi 750 Mega Especial", 99.90, 750, ONTEM,
                         operadora="Claro", produto="combo"),
                   fibra("Claro Multi 600 Mega Especial", 99.90, 600, HOJE,
                         operadora="Claro", produto="combo"))
        self.assertIn("600 Mega", t)
        self.assertIn("mesmo preço, menos velocidade", t)

    def test_a_subida_tambem_sai(self):
        u"""Mesmo preco e MAIS entrega tambem e movimento de mercado -
        foi o Ultracombo 7 em 27/10, reportado como noticia pelo
        relatorio do concorrente."""
        t = montar(fibra("Claro Multi 600 Mega Especial", 99.90, 600, ONTEM,
                         operadora="Claro", produto="combo"),
                   fibra("Claro Multi 750 Mega Especial", 99.90, 750, HOJE,
                         operadora="Claro", produto="combo"))
        self.assertIn("mesmo preço, mais velocidade", t)

    def test_nome_igual_fica_com_a_escada(self):
        u"""A CLAUSULA QUE EVITA A MENSAGEM REPETIDA. Com o nome igual a
        escada acompanha a oferta pelo indice e ja conta o movimento -
        "-14% de internet pelo mesmo preco". Sem este corte, a primeira
        mensagem de bancada saiu com os dois blocos colados, dizendo a
        mesma coisa com palavras diferentes.

        Medido nos 41 dias: as 4 trocas da Vivo mantem o nome e ja
        saiam; as 10 da Claro e da TIM mudam o nome e nao saiam.
        """
        d = dados(fibra("Vivo Fibra", 100.0, 700, ONTEM),
                  fibra("Vivo Fibra", 100.0, 600, HOJE))
        self.assertEqual(d.get("velocidades") or [], [])
        # e a escada continua contando, que e o ponto
        self.assertTrue(d.get("grades"),
                        "a escada parou de ver a troca de nome igual")

    def test_a_velocidade_dentro_do_nome_nao_esconde_a_troca(self):
        u"""A ARMADILHA DA TIM. Parear por nome cru faz o par nao
        existir, e a troca vira "uma oferta saiu e outra entrou"."""
        t = montar(fibra("TIM Ultracombo 7 500MEGA + 65GB", 89.99, 500,
                         ONTEM, operadora="TIM", produto="combo"),
                   fibra("TIM Ultracombo 7 600MEGA + 65GB", 89.99, 600,
                         HOJE, operadora="TIM", produto="combo"))
        self.assertIn("mesmo preço, mais velocidade", t)

    def test_a_franquia_no_nome_nao_e_confundida_com_velocidade(self):
        u"""So a unidade de VELOCIDADE sai do nome. Tirando o "65GB"
        junto, duas ofertas de franquias diferentes virariam a mesma e o
        pareamento passaria a misturar oferta com oferta."""
        self.assertEqual(robo._sem_a_velocidade("TIM Ultracombo 7 500MEGA + 65GB"),
                         "TIM Ultracombo 7 + 65GB")

    # ------------------------------------------------- os silencios

    def test_preco_que_tambem_mudou_nao_entra_aqui(self):
        u"""Preco e entrega mexendo juntos e a remodelada, que ja
        existe. Este detector e sobre o preco que NAO se mexeu - e o
        preco parado e o contraste da frase."""
        d = dados(fibra("Claro Multi 700 Mega", 100.0, 700, ONTEM,
                        operadora="Claro", produto="combo"),
                  fibra("Claro Multi 600 Mega", 120.0, 600, HOJE,
                        operadora="Claro", produto="combo"))
        self.assertEqual(d.get("velocidades") or [], [])

    def test_dois_degraus_no_mesmo_preco_nao_pareia(self):
        u"""Dois degraus no mesmo nome e no mesmo preco sao duas
        ofertas, e dizer qual virou qual seria chute."""
        ontem = (fibra("Claro Multi 700 Mega", 99.90, 700, ONTEM,
                       operadora="Claro", produto="combo")
                 + fibra("Claro Multi 500 Mega", 99.90, 500, ONTEM,
                         operadora="Claro", produto="combo"))
        hoje = fibra("Claro Multi 600 Mega", 99.90, 600, HOJE,
                     operadora="Claro", produto="combo")
        d = dados(ontem, hoje)
        self.assertEqual(d.get("velocidades") or [], [])

    def test_o_detector_sozinho_recusa_o_par_ambiguo(self):
        u"""MEDIDO NO DETECTOR, E NAO PELA MENSAGEM. Pela mensagem este
        caso passa mesmo com a guarda removida: o auditor ve os dois
        degraus na janela crua, recusa a afirmacao e a lista chega
        vazia do mesmo jeito. O teste ficava verde pelo motivo errado -
        o provador mediu isso e a mutacao Ve3 nao foi pega.

        Defesa em profundidade e boa; teste que nao distingue as duas
        camadas nao e.
        """
        ontem = [oferta(operadora="Claro", produto="combo",
                        nome="Claro Multi 700 Mega", preco=99.90, gb=None,
                        mbps=700, praca="Sao Paulo/SP", data=ONTEM),
                 oferta(operadora="Claro", produto="combo",
                        nome="Claro Multi 500 Mega", preco=99.90, gb=None,
                        mbps=500, praca="Sao Paulo/SP", data=ONTEM)]
        hoje = [oferta(operadora="Claro", produto="combo",
                       nome="Claro Multi 600 Mega", preco=99.90, gb=None,
                       mbps=600, praca="Sao Paulo/SP", data=HOJE)]
        self.assertEqual(robo._mesmo_preco_outra_velocidade(hoje, ontem), [])

    def test_oferta_que_nasce_nao_e_troca(self):
        u"""Medido em 27/10/2026: o Ultracombo 7 so existia em Sao Paulo
        em 26/10 e apareceu nas outras 19 em 27/10. Nas 19 nao houve
        troca nenhuma - a oferta nasceu."""
        d = dados([], fibra("Claro Multi 600 Mega", 99.90, 600, HOJE,
                            operadora="Claro", produto="combo"))
        self.assertEqual(d.get("velocidades") or [], [])

    def test_sem_mudanca_nao_fala(self):
        d = dados(fibra("Claro Multi 700 Mega", 99.90, 700, ONTEM,
                        operadora="Claro", produto="combo"),
                  fibra("Claro Multi 700 Mega", 99.90, 700, HOJE,
                        operadora="Claro", produto="combo"))
        self.assertEqual(d.get("velocidades") or [], [])


class AsDuasNormalizacoesConcordam(unittest.TestCase):
    u"""O DETECTOR E O AUDITOR TIRAM A VELOCIDADE DO NOME CADA UM NA SUA.

    robo.py importa auditor.py, entao o auditor nao pode importar de
    volta - e nao deveria mesmo: ele existe para nao depender do codigo
    que produziu a afirmacao. O preco dessa independencia e as duas
    normalizacoes poderem divergir EM SILENCIO: divergindo, o auditor
    procura um nome que o detector nunca usou, nao acha a oferta em
    praca nenhuma, e recusa o evento inteiro como "o dado nao sustenta"
    - uma recusa que parece conferencia e e desencontro.
    """

    NOMES = ("Vivo Fibra", "TIM Ultracombo 7 500MEGA + 65GB",
             "TIM Ultracombo 6 1GIGA + 70GB", "Claro Multi 750 Mega",
             "Claro Multi 600 Mega Especial", "Vivo Total Pro",
             "Oi Fibra 400 Mbps", "Brisanet 700MB Essencial", "", None)

    def test_as_duas_dao_o_mesmo_nome(self):
        for nome in self.NOMES:
            self.assertEqual(robo._sem_a_velocidade(nome),
                             auditor._sem_a_velocidade(nome),
                             "divergiram em %r" % (nome,))


class OAuditorConfereAVelocidade(unittest.TestCase):
    u"""O AUDITOR RE-DEDUZ, UMA PRACA POR VEZ, DAS LINHAS CRUAS.

    Sem ele a categoria nova sairia como aprovada sem ninguem ter
    conferido: "aplicar" so tira o que "auditar" recusa, e categoria que
    nao esta em AUDITADOS nem em FORA passa reta.
    """

    def _evento(self, pracas, de=700, para=600):
        return {"operadora": "Vivo", "produto": "fibra",
                "nome_oferta": "Vivo Fibra", "preco": 100.0,
                "de": de, "para": para, "pracas": list(pracas)}

    def test_a_velocidade_esta_na_lista_de_auditados(self):
        self.assertIn("velocidades", auditor.AUDITADOS)

    def test_o_que_o_dado_sustenta_passa(self):
        recusas, _fora = auditor.auditar(
            {"velocidades": [self._evento(PRACAS)]},
            fibra("Vivo Fibra", 100.0, 600, HOJE),
            fibra("Vivo Fibra", 100.0, 700, ONTEM))
        self.assertEqual(recusas, [])

    def test_praca_inventada_e_recusada(self):
        u"""O evento afirma quatro pracas e a janela crua so tem tres
        delas com a troca: a quarta nao e omissao, e afirmacao falsa."""
        recusas, _fora = auditor.auditar(
            {"velocidades": [self._evento(list(PRACAS) + ["Manaus/AM"])]},
            fibra("Vivo Fibra", 100.0, 600, HOJE)
            + fibra("Vivo Fibra", 100.0, 600, HOJE, pracas=("Manaus/AM",)),
            fibra("Vivo Fibra", 100.0, 700, ONTEM)
            + fibra("Vivo Fibra", 100.0, 600, ONTEM, pracas=("Manaus/AM",)))
        self.assertEqual(len(recusas), 1, recusas)
        self.assertIn("Manaus", recusas[0][2])

    def test_degrau_errado_e_recusado(self):
        u"""O evento diz 700 para 600 e o dado diz 700 para 500."""
        recusas, _fora = auditor.auditar(
            {"velocidades": [self._evento(PRACAS)]},
            fibra("Vivo Fibra", 100.0, 500, HOJE),
            fibra("Vivo Fibra", 100.0, 700, ONTEM))
        self.assertEqual(len(recusas), 1, recusas)


if __name__ == "__main__":
    unittest.main(verbosity=2)
