# -*- coding: utf-8 -*-
u"""O degrau desempata o nome que nomeia varias ofertas.

MEDIDO NOS 35 DIAS PUBLICADOS antes de a regra existir. O pareamento por
nome resolve 1.542 dos 2.024 baldes de sobra e recusa 844; o degrau
aparece nos dois lados de 625 dos recusados e deixa 505 pares, dos quais
120 continuam ambiguos e ficam fora.

O QUE ESSES PARES ERAM e o que desenhou as guardas:

  466 eram mudanca so de versao, e todos nos QUATRO dias em que a nossa
  propria leitura mudou - 16/10, 21/10, 22/10 e 04/11. Nesses dias a
  mensagem subcontava a propria ressalva: em 16/10 publicou "10 ofertas
  mudaram de versao" quando eram 22.

  39 tinham preco se movendo, e os 39 eram FALSOS. Em 06/10 a escada do
  Claro Controle deslizou 5 GB por degrau - 59,90 foi de 40 para 45 GB,
  69,90 de 45 para 50 - e desfez em 13/10. O par por nome e degrau leria
  isso como "45 GB de 69,90 para 59,90, -14% em 20 cidades", um corte
  que nunca houve: era o mesmo preco com mais franquia.

NENHUMA NOTICIA DE MERCADO NOVA EM 35 DIAS, e isso e o resultado, nao a
decepcao. O ganho medido esta na ressalva da nossa leitura, que estava
contando menos da metade do que acontecia.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _apoio import (HOJE, ONTEM, dados, oferta,                # noqa: E402
                    sem_declaracao)

SP = "Sao Paulo/SP"


def pre(gb, preco, variante="simples", data=HOJE, nome=u"Vivo Pré",
         anatel=None):
    u"""Uma das quatro ofertas que dividem o nome "Vivo Pre"."""
    return oferta(operadora="Vivo", produto="prepago", nome=nome, preco=preco,
                  gb=gb, praca=SP, data=data, anatel=anatel,
                  chave="Vivo|prepago|%dgb|%s" % (gb, variante))


def a_familia(dia):
    u"""As outras tres ofertas do mesmo nome, paradas nos dois dias.

    SEM ELAS O TESTE MEDE OUTRA COISA: com uma oferta so, o nome
    identifica e o pareamento por nome - o de sempre - resolve o caso.
    O que se mede aqui so existe quando o nome nomeia varias.
    """
    return [pre(15, 20.00, data=dia), pre(20, 25.00, data=dia),
            pre(30, 40.00, data=dia)]


class OGrauDesempata(unittest.TestCase):

    def test_o_nome_compartilhado_pareia_pelo_degrau(self):
        u"""Quatro "Vivo Pre" na praca, e a de 25 GB troca de versao."""
        sem_declaracao(self)
        ontem = a_familia(ONTEM) + [pre(25, 35.00, data=ONTEM)]
        hoje = a_familia(HOJE) + [pre(25, 35.00, "com_apps", data=HOJE)]
        d = dados(ontem, hoje)
        self.assertEqual(d.get("recusadas") or [], [])
        achados = d.get("remodeladas") or []
        self.assertEqual(len(achados), 1, "o degrau nao desempatou o nome")
        self.assertTrue(achados[0]["versao_mudou"])
        self.assertTrue(achados[0]["versao_apenas"])
        self.assertEqual(achados[0]["agora_entrega"], 25)

    def test_o_nome_unico_continua_pareando_pelo_nome(self):
        u"""A regra antiga nao pode ter sido trocada pela nova."""
        sem_declaracao(self)
        ontem = [pre(25, 35.00, nome=u"Vivo Pré Sozinha", data=ONTEM)]
        hoje = [pre(25, 35.00, "com_apps", nome=u"Vivo Pré Sozinha",
                    data=HOJE)]
        self.assertEqual(len(dados(ontem, hoje).get("remodeladas") or []), 1)


class OPrecoNaoSaiDaquiNunca(unittest.TestCase):
    u"""O caso de 06/10/2026: a escada que desliza nao e corte de preco."""

    def _escada(self, dia, degraus):
        return [oferta(operadora="Claro", produto="controle",
                       nome="Claro Controle", preco=preco, gb=gb, praca=SP,
                       data=dia,
                       chave="Claro|controle|%dgb|com_claro_controle" % gb)
                for gb, preco in degraus]

    def test_a_escada_que_desliza_nao_vira_corte(self):
        u"""Cada preco ganhou 5 GB, e nenhum preco se mexeu."""
        sem_declaracao(self)
        ontem = self._escada(ONTEM, [(35, 99.90), (40, 59.90), (45, 69.90)])
        hoje = self._escada(HOJE, [(35, 99.90), (45, 59.90), (50, 69.90)])
        d = dados(ontem, hoje)
        for r in d.get("remodeladas") or []:
            self.assertFalse(
                r["antes_preco"] == 69.90 and r["agora_preco"] == 59.90,
                "o par do degrau afirmou um corte de 14%% que nao houve: %s"
                % r.get("texto_preco"))

    def test_preco_mexendo_derruba_o_par_do_degrau(self):
        u"""Nome compartilhado + preco se movendo = nenhuma afirmacao."""
        sem_declaracao(self)
        ontem = a_familia(ONTEM) + [pre(25, 35.00, data=ONTEM)]
        hoje = a_familia(HOJE) + [pre(25, 29.00, "com_apps", data=HOJE)]
        self.assertEqual(dados(ontem, hoje).get("remodeladas") or [], [])

    def test_preco_nao_lido_num_dos_dias_derruba(self):
        u"""Preco ausente deixa reajuste possivel, e o par cala."""
        sem_declaracao(self)
        ontem = a_familia(ONTEM) + [pre(25, None, data=ONTEM)]
        hoje = a_familia(HOJE) + [pre(25, 35.00, "com_apps", data=HOJE)]
        self.assertEqual(dados(ontem, hoje).get("remodeladas") or [], [])


class OCodigoDeRegistro(unittest.TestCase):

    def test_codigo_diferente_recusa_o_par(self):
        u"""Duas ofertas registradas, uma saindo e outra entrando."""
        sem_declaracao(self)
        ontem = a_familia(ONTEM) + [pre(25, 35.00, data=ONTEM,
                                        anatel="VIV202603039022")]
        hoje = a_familia(HOJE) + [pre(25, 35.00, "com_apps", data=HOJE,
                                      anatel="VIV202603040130")]
        self.assertEqual(dados(ontem, hoje).get("remodeladas") or [], [])

    def test_codigo_igual_pareia_apesar_da_irma(self):
        u"""O caso das duas "Vivo Familia 2 + TV" de 700 Mega.

        Com o registro igual nos dois dias nao ha escolha a fazer: e a
        mesma oferta, mesmo havendo outra do mesmo nome e degrau no
        balcao.
        """
        sem_declaracao(self)
        irma_ontem = pre(25, 20.00, "familia", data=ONTEM)
        irma_hoje = pre(25, 20.00, "familia", data=HOJE)
        ontem = a_familia(ONTEM) + [irma_ontem,
                                    pre(25, 35.00, data=ONTEM,
                                        anatel="VIV202604036493")]
        hoje = a_familia(HOJE) + [irma_hoje,
                                  pre(25, 35.00, "com_apps", data=HOJE,
                                      anatel="VIV202604036493")]
        achados = dados(ontem, hoje).get("remodeladas") or []
        self.assertEqual(len(achados), 1, "o registro igual nao pareou")
        self.assertEqual(achados[0]["agora_preco"], 35.00)

    def test_sem_codigo_a_irma_no_balcao_recusa(self):
        u"""Sem registro, a irma no balcao devolve a escolha ao chute."""
        sem_declaracao(self)
        ontem = a_familia(ONTEM) + [pre(25, 20.00, "familia", data=ONTEM),
                                    pre(25, 35.00, data=ONTEM)]
        hoje = a_familia(HOJE) + [pre(25, 20.00, "familia", data=HOJE),
                                  pre(25, 35.00, "com_apps", data=HOJE)]
        self.assertEqual(dados(ontem, hoje).get("remodeladas") or [], [])


class OQueContinuaForaDaComparacao(unittest.TestCase):

    def test_degrau_nao_lido_nao_desempata(self):
        u"""Duas ausencias de degrau nao sao o mesmo degrau."""
        sem_declaracao(self)
        def sem_degrau(variante, dia):
            return oferta(operadora="Brisanet", produto="fibra",
                          nome="Brisanet Fibra", preco=99.90, gb=None,
                          mbps=None, praca=SP, data=dia,
                          chave="Brisanet|fibra|nd|%s" % variante)
        # duas ofertas do mesmo nome para o pareamento por nome recusar
        companhia = [oferta(operadora="Brisanet", produto="fibra",
                            nome="Brisanet Fibra", preco=129.90, mbps=600,
                            gb=None, praca=SP, data=d,
                            chave="Brisanet|fibra|600mbps|simples")
                     for d in (ONTEM, HOJE)]
        ontem = [companhia[0], sem_degrau("simples", ONTEM)]
        hoje = [companhia[1], sem_degrau("com_apps", HOJE)]
        self.assertEqual(dados(ontem, hoje).get("remodeladas") or [], [])

    def test_duas_candidatas_no_mesmo_degrau_continua_recusando(self):
        u"""Duas sobras no mesmo nome e degrau: o par seria sorteio.

        AS QUATRO PELO MESMO PRECO E COM O MESMO REGISTRO, de
        proposito, e as duas coisas custaram uma rodada do provador
        cada. Com precos diferentes, o par errado sai com preco se
        movendo e a guarda do PRECO o derruba. Com registro ausente,
        quem derruba e a guarda da IRMA no balcao. Nos dois casos a
        suite ficava verde sem esta regra - Db7 "NAO PEGOU" duas vezes -
        e o que o teste media era o portao de tras. Com preco igual e
        registro igual, so a recusa por ambiguidade sobra.
        """
        sem_declaracao(self)
        reg = "VIV202604036493"
        ontem = a_familia(ONTEM) + [pre(25, 35.00, data=ONTEM, anatel=reg),
                                    pre(25, 35.00, "familia", data=ONTEM,
                                        anatel=reg)]
        hoje = a_familia(HOJE) + [pre(25, 35.00, "com_apps", data=HOJE,
                                      anatel=reg),
                                  pre(25, 35.00, "com_tv", data=HOJE,
                                      anatel=reg)]
        self.assertEqual(dados(ontem, hoje).get("remodeladas") or [], [])


class ARessalvaDaLeitura(unittest.TestCase):
    u"""Na data declarada o par novo vai para a ressalva, e nao a mercado."""

    def test_na_data_declarada_entra_na_ressalva(self):
        ontem = a_familia(ONTEM) + [pre(25, 35.00, data=ONTEM)]
        hoje = a_familia(HOJE) + [pre(25, 35.00, "com_apps", data=HOJE)]
        d = dados(ontem, hoje)
        self.assertEqual(d.get("remodeladas") or [], [])
        self.assertEqual(len(d.get("leitura") or []), 1,
                         "o par novo tem de contar na ressalva da leitura")


if __name__ == "__main__":
    unittest.main()
