# -*- coding: utf-8 -*-
"""Os defeitos que a auditoria achou, cada um com o cenario que o dispara.

Estes testes nasceram vermelhos. Uma auditoria independente leu o codigo
em 20/10/2026 e achou 23 defeitos que a suite de 76 testes nao pegava -
varios deles na classe que o projeto existe para evitar: afirmar o que a
fonte nao sustenta.

Ficam em arquivo separado de proposito. Teste escrito DEPOIS do defeito
ser apontado tem valor diferente de teste escrito junto com o codigo: o
primeiro prova que o buraco foi fechado, o segundo prova que alguem
pensou no caso. Separar deixa a diferenca a vista.
"""
import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                   # noqa: E402
import vigia                                                  # noqa: E402
from coletores import apps                                    # noqa: E402
from _apoio import (HOJE, ONTEM, dados, em_todas, montar,      # noqa: E402
                    oferta)


def indexar(linhas):
    return {robo._identidade(l): l for l in linhas}


# ======================================================== gravidade alta

class AusenciaNaoEMudanca(unittest.TestCase):
    """AUDITORIA 1. A guarda olhava so o lado de ontem:

        if antes["preco_promocional"] is not None and atual[...] != antes[...]

    Com o preco de HOJE em None, "None != 119.9" e verdadeiro e o evento
    entrava. A mensagem escrevia "119,90 → -" e contava como mudanca. Num
    dia em que a leitura de preco quebrasse numa operadora inteira, a
    mensagem anunciaria uma centena de reajustes que nao existiram.

    Ausencia de leitura nao e noticia - e o que a metodologia chama de
    "ausencia e ausencia, nunca zero".
    """

    def test_preco_que_sumiu_nao_e_anunciado(self):
        t = montar(em_todas(preco=119.90, data=ONTEM),
                   em_todas(preco=None, data=HOJE))
        self.assertNotIn("→ -", t)
        self.assertIn("Nenhuma mudança", t)

    def test_preco_que_apareceu_tambem_nao_e(self):
        # o lado inverso: a oferta que estava sem preco ontem e tem hoje
        t = montar(em_todas(preco=None, data=ONTEM),
                   em_todas(preco=119.90, data=HOJE))
        self.assertIn("Nenhuma mudança", t)

    def test_o_vigia_e_quem_fala_da_ausencia(self):
        # nao e para o fato desaparecer: ele muda de canal, porque a
        # pergunta e outra - "o que eu coletei faz sentido?"
        d = vigia.achados([oferta(preco=None)], {})
        self.assertTrue(any("sem preco" in t for _g, t in d))


class PrecoEDegrauJuntos(unittest.TestCase):
    """AUDITORIA 2. A mesma oferta passa de R$ 30/25 GB para R$ 35/20 GB.

    _identidade carrega a chave, e a chave embute o degrau: sem par. A
    escada exige que o OUTRO campo tenha ficado parado nos dois dias, e
    os dois andaram. _renomeadas pareia por chave e praca, que e
    exatamente o que a troca de degrau quebra.

    Resultado medido pela auditoria: "Nenhuma mudanca de preco,
    composicao ou nome" sobre uma oferta que mudou as duas coisas. E
    afirmacao positiva de ausencia e o pior efeito possivel aqui.
    """

    def test_os_dois_mudando_juntos_aparecem(self):
        achou = robo._oferta_remodelada(
            indexar([oferta(produto="prepago", nome="Vivo Pré",
                            preco=35.0, gb=20)]),
            indexar([oferta(produto="prepago", nome="Vivo Pré",
                            preco=30.0, gb=25, data=ONTEM)]))
        self.assertEqual(len(achou), 1)
        e = achou[0]
        self.assertEqual((e["antes_preco"], e["agora_preco"]), (30.0, 35.0))
        self.assertEqual((e["antes_entrega"], e["agora_entrega"]), (25, 20))

    def test_a_mensagem_mostra_os_dois_numeros(self):
        t = montar(em_todas(produto="prepago", nome="Vivo Pré",
                            preco=30.0, gb=25, data=ONTEM),
                   em_todas(produto="prepago", nome="Vivo Pré",
                            preco=35.0, gb=20, data=HOJE))
        self.assertNotIn("Nenhuma mudança", t)
        self.assertIn("30,00 → 35,00", t)
        self.assertIn("25 → 20 GB", t)
        self.assertIn("+17%", t)
        self.assertIn("-20%", t)

    def test_so_o_preco_mudando_nao_entra_aqui(self):
        # senao a mesma mudanca sairia duas vezes na mensagem
        achou = robo._oferta_remodelada(
            indexar([oferta(preco=135.0)]),
            indexar([oferta(preco=119.90, data=ONTEM)]))
        self.assertEqual(achou, [])

    def test_duas_candidatas_nao_viram_palpite(self):
        """Com duas ofertas de mesmo nome na praca, qualquer pareamento
        seria chute - e chute aqui inventa reajuste."""
        hoje = indexar([oferta(nome="Vivo Pós", preco=35.0, gb=20),
                        oferta(nome="Vivo Pós", preco=45.0, gb=30)])
        ontem = indexar([oferta(nome="Vivo Pós", preco=30.0, gb=25,
                                data=ONTEM)])
        self.assertEqual(robo._oferta_remodelada(hoje, ontem), [])


class AlcanceNaoSeInfla(unittest.TestCase):
    """AUDITORIA 3. A identidade do agrupamento nao tinha o nome.

    Duas ofertas que dividem chave de serie e preco - "TIM Controle
    Redes Sociais" e "TIM Controle Pro", 46 GB, R$ 49,99 - caiam no
    mesmo grupo, cada uma empurrava a praca na lista, e _onde usava
    len() e nao len(set()). Alta em 10 pracas com duas ofertas virava
    "em todas as 20 praças", e a segunda oferta sumia da mensagem.
    """

    def _duas_ofertas(self, preco, data):
        linhas = []
        for nome in ("TIM Redes Sociais", "TIM Pro"):
            linhas += em_todas(operadora="TIM", produto="controle", nome=nome,
                               preco=preco, gb=46, data=data,
                               chave="TIM|controle|46gb|simples")
        return linhas

    def test_duas_ofertas_sao_dois_eventos(self):
        r = dados(self._duas_ofertas(44.99, ONTEM),
                  self._duas_ofertas(49.99, HOJE))
        self.assertEqual(len(r["mudancas_preco"]), 2)
        for m in r["mudancas_preco"]:
            self.assertEqual(len(m["pracas"]), 20)
            self.assertEqual(len(set(m["pracas"])), 20)
            self.assertIn("todas as 20", m["onde"])

    def test_praca_repetida_nao_conta_duas_vezes(self):
        self.assertIn("3 de 20", robo._onde(["A/X"] * 4 + ["B/X"] * 4
                                            + ["C/X"]))

    def test_oferta_nacional_nao_sai_como_uma_de_vinte(self):
        """AUDITORIA 22. A NuCel e a Starlink gravam "Brasil/BR": contra
        as 20 pracas do painel, qualquer mudanca delas saia como "em 1 de
        20" - numero certo e leitura errada, porque sugere movimento
        localizado onde ele foi total."""
        t = montar([oferta(operadora="NuCel", praca="Brasil/BR",
                           nome="NuCel 40", preco=40.0, data=ONTEM)],
                   [oferta(operadora="NuCel", praca="Brasil/BR",
                           nome="NuCel 40", preco=45.0, data=HOJE)])
        self.assertNotIn("1 de 20", t)
        self.assertIn("única praça", t)


class PontoCegoChegaNaMensagem(unittest.TestCase):
    """AUDITORIA 4. O aviso de colisao era gerado e so guardado em
    "dados" - saia como nota de rodape no fim do PDF. O comentario no
    codigo dizia que isso "garante que o proximo nao passe calado", e
    ele passava calado.

    E se o PDF falhasse, o aviso desaparecia inteiro, deixando a
    mensagem afirmar "nenhuma mudanca" sem ressalva nenhuma.
    """

    def _par_colidido(self, data):
        a = oferta(produto="combo", nome="Vivo Família 2 + TV", preco=290.0,
                   gb=None, mbps=700, data=data)
        return [a, dict(a, preco_promocional=390.0)]

    def test_a_colisao_aparece_no_texto(self):
        t = montar(self._par_colidido(ONTEM), self._par_colidido(HOJE))
        self.assertIn("indistinguíveis entre si", t)

    def test_e_vem_junto_da_linha_que_ela_qualifica(self):
        t = montar(self._par_colidido(ONTEM), self._par_colidido(HOJE))
        self.assertLess(t.index("indistinguíveis entre si"),
                        t.index("Relatório completo"))

    def test_dia_limpo_nao_tem_ressalva(self):
        t = montar(em_todas(data=ONTEM), em_todas(data=HOJE))
        self.assertNotIn("indistinguíveis", t)

    def test_o_grupo_inteiro_sai_da_comparacao(self):
        """ACHADO PELA MEDICAO no dado real de 15 e 16/10/2026, depois da
        auditoria. _indexar guardava a PRIMEIRA do grupo e descartava o
        resto - e isso nao e "aproveitar o que da": e sortear qual oferta
        representa as duas, e o sorteio muda de um dia para o outro.

        As duas "Vivo Familia 2 + TV" de 700 Mega, R$ 290 e R$ 390,
        dividiam chave, praca e nome. A ordem elegeu a de R$ 390 em
        15/10; em 16/10 a correcao de variante levou essa para outra
        chave e sobrou a de R$ 290 na chave antiga. A mensagem anunciou:

            Combo - Vivo Familia 2 + TV
              390,00 -> 290,00  -26%   em todas as 20 pracas

        Nenhum preco mudou: as duas existiam nos dois dias pelos mesmos
        valores. E duas linhas acima a mesma mensagem dizia que nao era
        possivel afirmar variacao naquelas ofertas - afirmava e
        desafirmava de uma vez, e o numero era falso.
        """
        def par(data, chave_da_caro):
            base = dict(produto="combo", nome="Vivo Família 2 + TV",
                        gb=None, mbps=700, data=data)
            return (em_todas(preco=290.0, chave="Vivo|combo|700mbps|familia",
                             **base)
                    + em_todas(preco=390.0, chave=chave_da_caro, **base))

        t = montar(par(ONTEM, "Vivo|combo|700mbps|familia"),
                   par(HOJE, "Vivo|combo|700mbps|familia_tv"))
        self.assertNotIn("-26%", t)
        self.assertNotIn("390,00 → 290,00", t)
        # a colisao aqui e de ONTEM: hoje as duas ofertas tem chaves
        # distintas e sao comparaveis. O efeito dela sobre hoje e a perda
        # do par, e e a cobertura que diz isso - a frase "fora da
        # comparação de hoje" seria falsa (auditoria 2, A5)
        self.assertIn("alcançou só", t)
        self.assertNotIn("ficaram fora da comparação de hoje", t)

    def test_e_a_cobertura_conta_as_que_sairam(self):
        """Tirar as colididas do indice faria a cobertura parecer melhor
        do que e: 100% do que deu para comparar nao e 100% do que foi
        coletado."""
        r = dados(self._par_colidido(ONTEM) + em_todas(data=ONTEM),
                  self._par_colidido(HOJE) + em_todas(data=HOJE))
        cob = r["cobertura"]
        self.assertEqual(cob["fora"], 2)
        self.assertEqual(cob["hoje"], 22, "20 comparaveis + as 2 fora")
        self.assertLess(cob["fracao"], 1.0)


class TierNaoVemDaFraseSeguinte(unittest.TestCase):
    """AUDITORIA 5. "if parada > 0" ignorava o separador na posicao 0.

    Quando a janela comeca logo depois do nome do app, o ponto que
    encerra a frase nao cortava nada - e o tier da frase SEGUINTE era
    atribuido a oferta. "Vivo Pós com Netflix. Premium por R$ 55 à
    parte" devolvia Premium, que e o plano de outra oferta.
    """

    def test_ponto_logo_apos_o_nome_corta(self):
        self.assertIsNone(apps.tier_do_texto(
            "netflix", "Vivo Pós com Netflix. Premium por R$ 55 à parte"))
        self.assertIsNone(apps.tier_do_texto(
            "netflix", "Netflix. Padrão com anúncios no plano de cima"))

    def test_sem_a_parede_de_outro_app(self):
        # o teste antigo passava pelo motivo errado: quem bloqueava era o
        # nome "Spotify" servindo de parede, e nao o ponto
        self.assertIsNone(apps.tier_do_texto(
            "netflix", "Netflix incluso. Premium à parte"))

    def test_o_tier_declarado_continua_saindo(self):
        # a correcao nao pode zerar o caso que funciona
        self.assertEqual(apps.tier_do_texto(
            "disney", "VIVO POS COM DISNEY+ PADRAO"), "Padrão")


# ======================================================== gravidade media

class ParedeDeOutrasMarcas(unittest.TestCase):
    """AUDITORIA 6. "if len(primeira) >= 4" excluia Max e Sky da lista de
    paredes, e os nomes entravam com o sinal ("disney+") enquanto a
    parede e procurada com fronteira de palavra - e nao existe fronteira
    entre "+" e o espaco seguinte."""

    def test_marca_curta_tambem_e_parede(self):
        self.assertIsNone(apps.tier_do_texto("netflix", "Netflix e Max Premium"))
        self.assertIsNone(apps.tier_do_texto("netflix", "Netflix, HBO Max Premium"))

    def test_o_sinal_no_nome_nao_atrapalha(self):
        self.assertIsNone(apps.tier_do_texto("netflix", "Netflix e Disney+ Padrão"))
        self.assertIsNone(apps.tier_do_texto("netflix",
                                             "Netflix e Paramount+ Premium"))

    def test_parede_nao_casa_dentro_de_outra_palavra(self):
        # "max" com fronteira dos dois lados nao casa em "maximo"
        self.assertEqual(apps.tier_do_texto(
            "netflix", "Netflix Padrão com máximo de telas"), "Padrão")


class CorteDaDegustacaoNaoLevaOVizinho(unittest.TestCase):
    """AUDITORIA 20. O comentario dizia "o ultimo nome de app antes da
    marca" e o codigo varria a lista para a frente, pegando o PRIMEIRO -
    o app mais distante. O corte comecava nele e levava o vizinho
    embora: em "Netflix incluso. Disney+: 3 meses por conta da Claro",
    quem estava em degustacao era o Disney e o Netflix desaparecia."""

    # DOIS APPS NA MESMA FRASE, e so o segundo em degustacao. Com um
    # ponto entre eles a pontuacao ja protege o primeiro, e o defeito
    # nao aparece - foi assim que o primeiro teste que escrevi para
    # isto passou pelo motivo errado, e o provador de mutacoes mostrou.
    COLADOS = ("Claro Controle 35GB com Netflix e Disney+ 3 meses por "
               "conta da Claro")

    TEXTO = ("Netflix incluso. Disney+: 3 meses por conta da Claro. "
             "Após, R$24,60 por mês.")

    def test_o_app_incluso_sobrevive_na_mesma_frase(self):
        limpo = apps.sem_degustacao(self.COLADOS)
        self.assertIn("Netflix", limpo)
        self.assertNotIn("Disney", limpo)

    def test_o_app_incluso_sobrevive_na_frase_anterior(self):
        limpo = apps.sem_degustacao(self.TEXTO)
        self.assertIn("Netflix", limpo)
        self.assertNotIn("Disney", limpo)

    def test_e_o_nivel_de_bundle_acompanha(self):
        for t in (self.COLADOS, self.TEXTO):
            self.assertEqual(apps.nivel_por_apps(t), 2,
                             "um streaming incluso, nao dois nem zero")


class UnidadeSaiDoCampo(unittest.TestCase):
    """AUDITORIA 7. A unidade saia do produto: "Mbps se for fibra ou
    combo, GB caso contrario". A Starlink grava produto "satelite",
    entao os 100 Mbps dela apareciam como "100 GB"."""

    def test_satelite_com_mbps_diz_mbps(self):
        self.assertEqual(robo._unidade(
            {"degrau_mbps": 100, "franquia_anunciada_gb": None}), "Mbps")

    def test_movel_com_gb_diz_gb(self):
        self.assertEqual(robo._unidade(
            {"degrau_mbps": None, "franquia_anunciada_gb": 60}), "GB")

    def test_satelite_tem_nome_na_mensagem(self):
        self.assertEqual(robo._categoria({"produto": "satelite"}), "Satélite")

    def test_a_escada_da_starlink_sai_em_mbps(self):
        t = montar([oferta(operadora="Starlink", produto="satelite",
                           nome="Starlink Residencial", praca="Brasil/BR",
                           preco=184.0, gb=None, mbps=100, data=ONTEM)],
                   [oferta(operadora="Starlink", produto="satelite",
                           nome="Starlink Residencial", praca="Brasil/BR",
                           preco=230.0, gb=None, mbps=50, data=HOJE)])
        self.assertIn("Mbps", t)
        self.assertNotIn("100 GB", t)
        self.assertIn("Satélite", t)


class VigiaNaoRepeteNemEsconde(unittest.TestCase):
    """AUDITORIA 10 e 11. Operadora ausente caia em dois blocos e saia
    duas vezes, com textos diferentes. E "resumo" devolvia so o primeiro
    grave, entao um preco fora da faixa escondia "Brisanet: 119 de 119
    sem velocidade"."""

    def _historico(self, n=30, operadora="Claro", dias=5):
        return {"2026-10-%02d" % (10 + i):
                [{"operadora": operadora, "produto": "movel",
                  "praca": "P/X", "nome_oferta": "O%d" % j,
                  "preco_promocional": 100.0, "franquia_anunciada_gb": 50,
                  "degrau_mbps": None, "chave": "c%d" % j} for j in range(n)]
                for i in range(dias)}

    def test_operadora_ausente_denunciada_uma_vez(self):
        r = vigia.achados([{"operadora": "Vivo", "produto": "movel",
                            "praca": "P/X", "nome_oferta": "x",
                            "preco_promocional": 100.0,
                            "franquia_anunciada_gb": 50, "degrau_mbps": None,
                            "chave": "k"}], self._historico())
        sobre_claro = [t for _g, t in r if "Claro" in t]
        self.assertEqual(len(sobre_claro), 1, sobre_claro)

    def test_resumo_diz_quantos_mais(self):
        r = vigia.resumo([("grave", "primeiro"), ("grave", "segundo"),
                          ("atencao", "terceiro")])
        self.assertIn("primeiro", r)
        self.assertIn("mais 1", r)

    def test_um_grave_so_nao_ganha_contagem(self):
        self.assertEqual(vigia.resumo([("grave", "unico")]),
                         "Conferir: unico")


class OperadoraPequenaNaoEInvisivel(unittest.TestCase):
    """AUDITORIA 12. "n >= max(5, total/2)": a NuCel tem 3 ofertas por
    dia e podia perder a franquia das tres sem o vigia abrir a boca - e
    operadora pequena e justamente a de coletor mais fragil."""

    def test_nucel_inteira_sem_entrega_e_denunciada(self):
        hoje = [{"operadora": "NuCel", "produto": "movel",
                 "praca": "Brasil/BR", "nome_oferta": "NuCel %d" % i,
                 "preco_promocional": 45.0, "franquia_anunciada_gb": None,
                 "degrau_mbps": None, "chave": "n%d" % i} for i in range(3)]
        r = vigia.achados(hoje, {})
        self.assertTrue(any("sem velocidade nem franquia" in t
                            for g, t in r if g == "grave"), r)

    def test_uma_oferta_avulsa_sem_entrega_continua_calada(self):
        hoje = [{"operadora": "Vivo", "produto": "movel", "praca": "P/X",
                 "nome_oferta": "O%d" % i, "preco_promocional": 100.0,
                 "franquia_anunciada_gb": None if i == 0 else 50,
                 "degrau_mbps": None, "chave": "c%d" % i} for i in range(30)]
        r = vigia.achados(hoje, {})
        self.assertEqual([t for g, t in r
                          if g == "grave" and "sem velocidade" in t], [])


class MemoriaDeQuarentaECincoDias(unittest.TestCase):
    """AUDITORIA 8. _degraus_que_voltaram pedia "limit=4000" e o
    PostgREST devolvia 1000 linhas sem reclamar. Mil linhas de uma
    operadora sao cerca de quatro dias: a memoria de 45 dias que a
    funcao promete nao existia - ela via a semana e dizia que tinha
    visto o mes e meio."""

    def test_a_consulta_e_paginada(self):
        pedidos = []

        def espiao(caminho, pagina=None):
            pedidos.append(caminho)
            return [], None

        def proibido(caminho):
            raise AssertionError("a busca de 45 dias nao pode usar consultar()")

        guarda = (robo.armazenamento.consultar_tudo,
                  robo.armazenamento.consultar)
        try:
            robo.armazenamento.consultar_tudo = espiao
            robo.armazenamento.consultar = proibido
            robo._degraus_que_voltaram(
                indexar([oferta(produto="prepago", gb=25, preco=30.0)]),
                {}, HOJE)
        finally:
            (robo.armazenamento.consultar_tudo,
             robo.armazenamento.consultar) = guarda
        self.assertTrue(pedidos)
        self.assertNotIn("limit=", pedidos[0])


class ODiaFechaQuandoARodadaPassaPorTodos(unittest.TestCase):
    """AUDITORIA 17. MINIMO = 5 de 9 coletores errava dos dois lados: dia
    com 5 fechava faltando 4, e dia com 4 reabria para cada um dos oito
    gatilhos - ate oito mensagens e oito rodadas de 50 minutos contra a
    cota de 2000 minutos por mes.

    O sinal certo e "a rodada chegou ao fim": cada coletor grava sua
    linha ao terminar, com sucesso ou sem.
    """

    def _responder(self, linhas):
        import json as _json
        import ja_coletou

        class Resposta(object):
            def __enter__(self2):
                return self2

            def __exit__(self2, *a):
                return False

            def read(self2):
                return _json.dumps(linhas).encode()

        guarda = ja_coletou.urllib.request.urlopen
        os.environ["SUPABASE_URL"] = "https://exemplo.invalido"
        os.environ["SUPABASE_SECRET_KEY"] = "x"
        ja_coletou.urllib.request.urlopen = lambda *a, **k: Resposta()
        self.addCleanup(setattr, ja_coletou.urllib.request, "urlopen", guarda)
        # a guarda conta o que achou no stderr, que e util na rodada e
        # ruido aqui
        calado = contextlib.redirect_stderr(io.StringIO())
        calado.__enter__()
        self.addCleanup(calado.__exit__, None, None, None)
        return ja_coletou

    def _registros(self, operadoras, sucesso=True):
        return [{"operadora": op, "sucesso": sucesso} for op in operadoras]

    def test_rodada_completa_fecha_o_dia(self):
        import robo as _robo
        jc = self._responder(self._registros(_robo.COLETORES))
        feito, quantas = jc._ja_coletou(HOJE)
        self.assertTrue(feito)
        self.assertEqual(quantas, len(_robo.COLETORES))

    def test_rodada_que_morreu_no_meio_nao_fecha(self):
        import robo as _robo
        jc = self._responder(self._registros(list(_robo.COLETORES)[:5]))
        feito, _q = jc._ja_coletou(HOJE)
        self.assertFalse(feito, "5 de 9 nao e uma rodada que terminou")

    def test_coletor_que_falha_sempre_nao_deixa_o_dia_aberto(self):
        """Contar SUCESSO em vez de registro faria um site que passou a
        bloquear manter o dia aberto para sempre - e ai os oito gatilhos
        recoletariam todos os dias, queimando a cota."""
        import robo as _robo
        jc = self._responder(self._registros(_robo.COLETORES, sucesso=False))
        feito, _q = jc._ja_coletou(HOJE)
        self.assertTrue(feito)


class SufixoDaVivoNaoVaiParaOsOutros(unittest.TestCase):
    """AUDITORIA 19. "Saude", "Educacao", "Entretenimento", "Travel" e
    "Musica" nao sao nomes de app: sao como a VIVO batiza a oferta. Em
    DO_NOME casavam com o nome de qualquer operadora, e a tela mostraria
    "Vivo TV Inicial" como servico incluso numa oferta da Brisanet."""

    def test_entretenimento_de_outra_operadora_nao_e_a_tv_da_vivo(self):
        self.assertEqual(apps.apps_da_oferta("Brisanet Entretenimento 500MB"),
                         [])
        self.assertEqual(apps.apps_da_oferta("Claro Controle Saúde"), [])
        self.assertEqual(apps.apps_da_oferta("TIM Travel 20GB"), [])

    def test_na_vivo_o_sufixo_continua_valendo(self):
        self.assertEqual(
            apps.apps_da_oferta("Vivo Controle Saúde", "Vivo"),
            ["vale_saude"])
        self.assertEqual(
            apps.apps_da_oferta("Vivo Controle Entretenimento", "Vivo"),
            ["vivo_tv"])

    def test_nome_proprio_de_app_vale_em_qualquer_uma(self):
        for op in (None, "Claro", "TIM", "Vivo", "Brisanet"):
            self.assertEqual(
                apps.apps_da_oferta("Pós com Netflix", op), ["netflix"],
                "Netflix é Netflix em qualquer vitrine")


# ======================================================== gravidade baixa

class TelegramNaoRecusaAMensagem(unittest.TestCase):
    """AUDITORIA 21. O Telegram recusa mensagem acima de 4096 caracteres,
    e recusa INTEIRA: nao corta, devolve erro e o dia fica sem aviso. E o
    dia que engorda a mensagem - nove operadoras sem registro, erro de
    comparacao, ponto cego, denuncia - e o que menos pode ficar sem."""

    def test_mensagem_normal_passa_intacta(self):
        t = "linha\n" * 10
        self.assertEqual(robo._cabe_no_telegram(t), t)

    def test_mensagem_gigante_e_cortada_e_avisa(self):
        r = robo._cabe_no_telegram("x" * 9000)
        self.assertLessEqual(len(r), robo.TETO_TELEGRAM)
        self.assertIn("cortado", r)

    def test_o_corte_preserva_o_fim_da_mensagem(self):
        """AUDITORIA 2, M8. O corte era no fim, e o fim e onde moram
        o link do painel e a linha "Conferir" do vigia - e o dia que
        passa de 4096 caracteres e justamente o dia em que ha
        denuncia grave. Cortar o fim jogava fora a informacao de
        maior consequencia."""
        rodape = ("Relat\u00f3rio completo em anexo \u00b7 %s" % robo.PAINEL
                  + "\n\nConferir: Brisanet sem velocidade")
        texto = "abre\n" + "recheio " * 900 + "\n" + rodape
        r = robo._cabe_no_telegram(texto)
        self.assertLessEqual(len(r), robo.TETO_TELEGRAM)
        self.assertTrue(r.startswith("abre"))
        self.assertIn(robo.PAINEL, r)
        self.assertIn("Conferir: Brisanet sem velocidade", r)




if __name__ == "__main__":
    unittest.main(verbosity=2)
