# -*- coding: utf-8 -*-
"""A mensagem do dia, nos quatro dias que ela precisa cobrir.

O dia normal a gente ve toda manha. Os outros tres so aparecem quando
dao errado - e e neles que o texto nao pode estar torto, porque e quando
alguem vai precisar dele.
"""
import contextlib
import io
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ja_coletou                                             # noqa: E402
import _apoio                                                 # noqa: E402
from _apoio import COLETA_OK, HOJE, ONTEM                      # noqa: E402

BRT = timezone(timedelta(hours=-3))


def oferta(operadora, produto, nome, preco, gb=50, praca="Sao Paulo/SP",
           data=HOJE):
    return _apoio.oferta(operadora=operadora, produto=produto, nome=nome,
                         preco=preco, gb=gb, praca=praca, data=data)


# OS DOIS DIAS COM A DATA CERTA DENTRO DA LINHA. A fixture anterior
# usava data=ONTEM nas duas listas e o banco de mentira nao olhava a
# coluna - o dia de hoje chegava vazio ao vigia, que denunciava "nenhuma
# captura hoje" dentro do teste do dia limpo.
def base(data):
    return [oferta("Claro", "movel", "Claro Pós", 124.90, data=data),
            oferta("Vivo", "fibra", "Vivo Fibra", 100.0, data=data)]


ONTEM_BASE = base(ONTEM)


class Mensagem(unittest.TestCase):

    def montar(self, ontem, hoje, coletas):
        return _apoio.montar(ontem, hoje, coletas)

    # ----------------------------------------------------- dia normal
    def test_dia_sem_mudanca_e_curto_e_direto(self):
        t = self.montar(ONTEM_BASE, base(HOJE), COLETA_OK)
        self.assertIn("TMT Price Tracker", t)
        self.assertIn("Nenhuma mudança", t)
        self.assertIn("tmt-price-tracker.vercel.app", t)
        self.assertLess(len(t.split("\n")), 8, "a mensagem engordou")

    def test_dia_limpo_nao_tem_conferir(self):
        """O vigia tem de ficar CALADO no dia normal.

        O teste acima passava com "Conferir: nenhuma captura hoje" dentro
        da mensagem, porque a fixture nao punha a data de hoje nas linhas
        de hoje. Afirmar o contrario aqui e o que impede o teste de
        passar pelo motivo errado de novo.
        """
        t = self.montar(ONTEM_BASE, base(HOJE), COLETA_OK)
        self.assertNotIn("Conferir", t)

    def test_mudanca_de_preco_traz_categoria_e_variacao(self):
        hoje = [oferta("Claro", "movel", "Claro Pós", 139.90),
                base(HOJE)[1]]
        t = self.montar(ONTEM_BASE, hoje, COLETA_OK)
        self.assertIn("Pós-pago · Claro Pós", t)
        self.assertIn("124,90 → 139,90", t)
        self.assertIn("+12%", t)

    # ----------------------------------------------------- dias ruins
    def test_coleta_incompleta_e_manchete(self):
        falhou = [dict(c) for c in COLETA_OK]
        falhou[2].update({"pracas_ok": 12, "sucesso": False})
        t = self.montar(ONTEM_BASE, base(HOJE), falhou)
        self.assertIn("COLETA INCOMPLETA", t)
        self.assertLess(t.index("COLETA INCOMPLETA"), 60,
                        "a falha tem de vir antes de qualquer numero")

    def test_sem_coleta_nao_se_fala_em_mudanca(self):
        # "o robo nao rodou" e "nenhuma mudanca" na mesma mensagem se
        # contradizem: sem coleta nao ha o que comparar
        t = self.montar(ONTEM_BASE, base(HOJE), [])
        self.assertIn("NÃO RODOU", t)
        self.assertNotIn("Nenhuma mudança", t)

    def test_teto_de_mudancas(self):
        hoje = [oferta("Claro", "movel", "Claro Pós", 139.90),
                oferta("Vivo", "fibra", "Vivo Fibra", 120.0),
                oferta("TIM", "controle", "TIM Smart", 62.99),
                oferta("Claro", "btl", "Claro Flex", 49.90)]
        ontem = [oferta("Claro", "movel", "Claro Pós", 124.90, data=ONTEM),
                 oferta("Vivo", "fibra", "Vivo Fibra", 100.0, data=ONTEM),
                 oferta("TIM", "controle", "TIM Smart", 58.99, data=ONTEM),
                 oferta("Claro", "btl", "Claro Flex", 44.90, data=ONTEM)]
        t = self.montar(ontem, hoje, COLETA_OK)
        self.assertIn("4 mudanças hoje", t)
        self.assertIn("e mais 1 mudança de preço no relatório", t)


class AContagemDoBancoNaoDerrubaAMensagem(unittest.TestCase):
    """Numero de rodape nao pode levar a mensagem do dia junto.

    A primeira versao chamava armazenamento.contar() direto na montagem
    do dicionario de dados. Qualquer tropeco ali - segredo ausente,
    rede fora, Supabase respondendo torto - levantava dentro de
    montar_mensagem e o dia inteiro ficava sem aviso, por causa de uma
    linha de rodape do anexo.

    Nove testes ficaram vermelhos no mesmo instante em que ela entrou,
    o que foi sorte: em producao o segredo existe, e o defeito so
    apareceria no dia em que o banco tropecasse - que e o dia em que a
    mensagem mais importa.
    """

    def _com_contagem(self, falsa):
        import robo
        original = robo.armazenamento.contar
        robo.armazenamento.contar = falsa
        self.addCleanup(setattr, robo.armazenamento, "contar", original)
        return robo

    def test_a_contagem_que_levanta_nao_para_a_montagem(self):
        def explode():
            raise RuntimeError("Supabase fora do ar")
        robo = self._com_contagem(explode)
        self.assertIsNone(robo._tamanho_da_serie())

    def test_a_contagem_que_falha_vira_None(self):
        robo = self._com_contagem(lambda: (None, "HTTP 500"))
        self.assertIsNone(robo._tamanho_da_serie())

    def test_a_contagem_boa_passa(self):
        """Controle: sem isto os dois de cima passariam com uma funcao
        que devolve None sempre."""
        robo = self._com_contagem(lambda: (44687, None))
        self.assertEqual(robo._tamanho_da_serie(), 44687)

    def test_sem_segredo_a_contagem_responde_nao_sei(self):
        """No local e no teste nao ha credencial, e isso nao e erro."""
        from coletores import armazenamento
        url = os.environ.pop("SUPABASE_URL", None)
        chave = os.environ.pop("SUPABASE_SECRET_KEY", None)
        try:
            total, motivo = armazenamento.contar()
        finally:
            if url is not None:
                os.environ["SUPABASE_URL"] = url
            if chave is not None:
                os.environ["SUPABASE_SECRET_KEY"] = chave
        self.assertIsNone(total)
        self.assertIn("SUPABASE", motivo)


class JanelaDaColeta(unittest.TestCase):
    """A coleta leva ~50 minutos e a mensagem sai logo depois. Para
    chegar as 7h, a coleta comeca as 6h - e gatilho que chega antes disso
    nao pode coletar, senao a mensagem chega de madrugada."""

    def responder(self, hora_brt, ja_coletou_hoje):
        class Falso(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 10, 21, hora_brt, 0, tzinfo=BRT)
        ja_coletou.datetime = Falso
        ja_coletou._ja_coletou = lambda d: (ja_coletou_hoje, 9 if ja_coletou_hoje else 0)
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida), \
                contextlib.redirect_stderr(io.StringIO()):
            ja_coletou.main()
        return saida.getvalue().strip()

    def test_cedo_demais_nao_coleta(self):
        for h in (0, 3, 5):
            self.assertEqual(self.responder(h, False), "nao",
                             "as %dh ainda e madrugada" % h)

    def test_dentro_da_janela_coleta(self):
        for h in (6, 7, 9):
            self.assertEqual(self.responder(h, False), "sim")

    def test_depois_do_limite_coleta_de_qualquer_jeito(self):
        # um dia sem dado e pior do que um dado que chegou tarde
        for h in (10, 14, 23):
            self.assertEqual(self.responder(h, False), "sim")

    def test_uma_vez_por_dia(self):
        for h in (6, 8, 11, 23):
            self.assertEqual(self.responder(h, True), "nao")


if __name__ == "__main__":
    unittest.main(verbosity=2)
