# -*- coding: utf-8 -*-
"""Os achados da TERCEIRA auditoria, e o que eu piorei consertando.

A segunda passada achou nove caminhos de erro. Consertei os nove, e a
terceira passada achou QUATRO defeitos graves nas minhas correcoes -
mais um ponto em que eu tornei o sistema pior do que estava.

E o padrao dos quatro e um so, e e humilhante de simples: **eu consertei
a afirmacao falsa num canal e deixei o outro afirmando.** A mensagem
passou a dizer "entrega nao lida" e o PDF seguiu imprimindo "None" na
mesma oferta. A mensagem passou a dizer "nao deu para ler o estado da
coleta" e o PDF seguiu listando as nove operadoras como "Sem registro".

Os dois canais saem do mesmo levantamento exatamente para nao poderem
discordar, e a minha correcao criou a discordancia que a arquitetura
existe para impedir. A licao que fica no codigo: texto que afirma algo
sobre uma oferta mora NO EVENTO, uma vez, e os dois canais leem. Nao em
dois lugares que combinam de dizer a mesma coisa.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                   # noqa: E402
import vigia                                                  # noqa: E402
from _apoio import (COLETA_OK, HOJE, ONTEM, dados, em_todas,   # noqa: E402
                    montar, oferta)
from test_auditoria2 import so_erro                            # noqa: E402


def indexar(linhas):
    return {robo._identidade(l): l for l in linhas}


def ontem_sem(oferta_de_hoje=None):
    """Um indice de ontem com uma oferta qualquer, que nao a de hoje.

    _degraus_que_voltaram so olha um degrau que NAO estava em "o". Passar
    ali a propria oferta de hoje fazia o teste medir o contrario: o
    degrau estava na vitrine, nao havia o que voltar.
    """
    return indexar([oferta(nome="Outra coisa", preco=50.0, gb=10,
                           data=ONTEM, chave="Vivo|movel|10gb|simples")])


# ======================================================== gravidade alta

class OFantasmaVoltouPorOutraPorta(unittest.TestCase):
    """N1. O MESMO -26% falso, agora por _degraus_que_voltaram.

    _indexar tira o grupo indistinguivel de h e de o. Mas
    _degraus_que_voltaram le a tabela crua para a parte historica, e
    pergunta "esta entrega estava na vitrine ontem?" olhando so o indice
    - entao toda oferta do grupo descartado parecia ter faltado ontem.

    Na transicao real de 15 para 16/10, com a correcao de variante
    separando o par, saia:

        Combo - Vivo
          700 Mbps voltou por 290,00   -26% sobre os 390,00 de 15/10

    Nenhum preco mudou, as duas ofertas existiam nos dois dias pelos
    mesmos valores, e o degrau nunca saiu da vitrine. Mesmo sorteio que o
    indice recusou, agora com a palavra "voltou" e uma data.
    """

    def _historico(self, linhas):
        def responder(caminho, pagina=None):
            if caminho.startswith("capturas?operadora="):
                return list(linhas), None
            return [], None
        guarda = robo.armazenamento.consultar_tudo
        robo.armazenamento.consultar_tudo = responder
        self.addCleanup(lambda: setattr(robo.armazenamento,
                                        "consultar_tudo", guarda))

    def test_descartada_de_ontem_nao_e_ausente_de_ontem(self):
        hoje = indexar([oferta(produto="combo", nome="Vivo Família 2 + TV",
                               preco=290.0, gb=None, mbps=700,
                               chave="Vivo|combo|700mbps|familia")])
        # ontem o par colidiu, entao as duas linhas foram descartadas
        par = [oferta(produto="combo", nome="Vivo Família 2 + TV",
                      preco=p, gb=None, mbps=700, data=ONTEM,
                      chave="Vivo|combo|700mbps|familia")
               for p in (290.0, 390.0)]
        # O HISTORICO VAI COM UMA LINHA SO. Com as duas, quem barra o
        # evento e a defesa de ambiguidade e nao a de descartadas - e o
        # teste passaria sem medir o que ele nomeia.
        self._historico([par[1]])
        achou = robo._degraus_que_voltaram(hoje, ontem_sem(), HOJE,
                                           descartadas_de_ontem=par)
        self.assertEqual(achou, [], "o degrau nao faltou ontem")

    def test_sem_a_defesa_o_fantasma_sai(self):
        """O mesmo cenario sem a lista de descartadas: a prova de que a
        defesa e ela, e nao outra coisa no caminho."""
        hoje = indexar([oferta(produto="combo", nome="Vivo Família 2 + TV",
                               preco=290.0, gb=None, mbps=700,
                               chave="Vivo|combo|700mbps|familia")])
        par = [oferta(produto="combo", nome="Vivo Família 2 + TV",
                      preco=390.0, gb=None, mbps=700, data=ONTEM,
                      chave="Vivo|combo|700mbps|familia")]
        self._historico(par)
        achou = robo._degraus_que_voltaram(hoje, ontem_sem(), HOJE)
        self.assertEqual(len(achou), 1, "sem a defesa, o fantasma aparece")

    def test_dia_historico_ambiguo_nao_serve_de_referencia(self):
        """A busca de 45 dias le a tabela crua e nao sabe das ofertas
        indistinguiveis: com duas linhas do mesmo dia, mesma praca,
        mesma entrega e mesmo nome a precos diferentes, "a primeira que
        aparecer" e sorteio. Dia ambiguo nao diz por quanto a operadora
        vendia aquele degrau."""
        hoje = indexar([oferta(produto="combo", nome="Vivo Família 2 + TV",
                               preco=250.0, gb=None, mbps=700,
                               chave="Vivo|combo|700mbps|familia")])
        ambiguo = [{"data_captura": "2026-10-15", "praca": "Sao Paulo/SP",
                    "nome_oferta": "Vivo Família 2 + TV",
                    "preco_promocional": p, "franquia_anunciada_gb": None,
                    "degrau_mbps": 700} for p in (290.0, 390.0)]
        self._historico(ambiguo)
        achou = robo._degraus_que_voltaram(hoje, ontem_sem(), HOJE)
        self.assertEqual(achou, [], "o dia de referencia e ambiguo")

    def test_dia_historico_limpo_continua_servindo(self):
        hoje = indexar([oferta(produto="combo", nome="Vivo Total",
                               preco=250.0, gb=None, mbps=700,
                               chave="Vivo|combo|700mbps|simples")])
        limpo = [{"data_captura": "2026-10-15", "praca": "Sao Paulo/SP",
                  "nome_oferta": "Vivo Total", "preco_promocional": 200.0,
                  "franquia_anunciada_gb": None, "degrau_mbps": 700}]
        self._historico(limpo)
        achou = robo._degraus_que_voltaram(hoje, ontem_sem(), HOJE)
        self.assertEqual(len(achou), 1)
        self.assertEqual(achou[0]["antes"], 200.0)


class OPesoDaRemodeladaNaoEraLido(unittest.TestCase):
    """N2. _por_efeito tinha um ramo morto, e era o das remodeladas.

    Elas carregam "antes" e "atual" como dicionarios, igual as mudancas
    de preco, entao caiam no ramo do par antes/atual e o
    max(preco, entrega) nunca rodava.

    Consequencia medida: a oferta que paga 5% mais e recebe METADE da
    internet pesava 0,05 e era a unica das quatro a ficar fora da
    mensagem - justo o movimento que o modulo chama de "maior efeito
    sobre o cliente". E pior num aspecto: como o relatorio parou de
    reordenar, os dois canais passaram a concordar na ordem errada.
    """

    def _remodelada(self, pa, pd, ea, ed):
        return {"antes_preco": pa, "agora_preco": pd,
                "antes_entrega": ea, "agora_entrega": ed,
                "antes": {"preco_promocional": pa},
                "atual": {"preco_promocional": pd}}

    def test_a_entrega_entra_no_peso(self):
        # 5% no preco, 50% na entrega: o peso e o maior dos dois
        self.assertAlmostEqual(
            robo._por_efeito(self._remodelada(100.0, 105.0, 600, 300)), 0.5)

    def test_so_entrega_tambem_pesa(self):
        self.assertAlmostEqual(
            robo._por_efeito(self._remodelada(100.0, 100.0, 600, 300)), 0.5)

    def test_a_pior_oferta_abre_a_mensagem(self):
        ontem, hoje = [], []
        casos = (("Vivo A", 105.0, 300), ("Vivo B", 140.0, 580),
                 ("Vivo C", 130.0, 590), ("Vivo D", 120.0, 595))
        for nome, _p, _e in casos:
            ontem += em_todas(operadora="Vivo", produto="fibra", nome=nome,
                              preco=100.0, gb=None, mbps=600, data=ONTEM,
                              chave="Vivo|fibra|600mbps|%s" % nome[-1])
        for nome, p, e in casos:
            hoje += em_todas(operadora="Vivo", produto="fibra", nome=nome,
                             preco=p, gb=None, mbps=e, data=HOJE,
                             chave="Vivo|fibra|%dmbps|%s" % (e, nome[-1]))
        t = montar(ontem, hoje)
        # "Vivo A" paga 5% mais e recebe metade: tem de estar na mensagem
        self.assertIn("Vivo A", t)

    def test_composicao_pesa_pelo_que_mudou_dentro(self):
        """O preco e igual por definicao, entao todas pesariam zero - e
        os tres mostrados voltariam a ser os primeiros do indice."""
        muita = {"antes": {"preco_promocional": 100.0, "assinatura_sva": "a+b"},
                 "atual": {"preco_promocional": 100.0, "assinatura_sva": "c+d"}}
        pouca = {"antes": {"preco_promocional": 100.0, "assinatura_sva": "a+b"},
                 "atual": {"preco_promocional": 100.0, "assinatura_sva": "a+b+c"}}
        self.assertGreater(robo._por_efeito(muita), robo._por_efeito(pouca))

    def test_o_peso_dos_servicos_nao_vaza_para_o_preco(self):
        """QUARTA AUDITORIA, V1 - e e defeito meu, introduzido ao
        consertar o N12. O ramo dos servicos ficou dentro do "antes e
        atual sao dicionarios", que e compartilhado com preco e com
        nome: qualquer reajuste cujo sva tambem mudou passou a pesar pela
        distancia dos servicos, de 0 a 1, contra a variacao de preco, que
        nao tem teto.

        O teste acima nao pegava isso: ele usa dois eventos de preco
        IGUAL, entao passa sem nunca tocar no vazamento.
        """
        def ev(pa, pd, sa, sd):
            return {"antes": {"preco_promocional": pa, "assinatura_sva": sa},
                    "atual": {"preco_promocional": pd, "assinatura_sva": sd}}

        queda = robo._por_efeito(ev(100.0, 50.0, "a", "a"))        # -50%
        alta = robo._por_efeito(ev(100.0, 101.0, "a", "b"))        # +1%
        self.assertGreater(queda, alta,
                           "uma queda de 50% pesa mais que uma alta de 1%")
        self.assertAlmostEqual(alta, 0.01)

    def test_e_no_dia_em_que_o_regulamento_falha_tambem(self):
        """O pior dia e o 30/09/2026 documentado em mudancas(): o
        regulamento da Vivo falhou em 1042 de 1044 ofertas e todo sva foi
        para vazio. Com o vazamento, TODO evento de preco daquele dia
        pesava 1,000 e a ordem voltava a ser chave.asc - nos dois canais,
        no dia em que o dado esta pior."""
        def ev(pa, pd):
            return {"antes": {"preco_promocional": pa,
                              "assinatura_sva": "a+b+c"},
                    "atual": {"preco_promocional": pd, "assinatura_sva": None}}

        pesos = [robo._por_efeito(ev(100.0, p)) for p in (300.0, 40.0, 102.0)]
        self.assertEqual(len(set(pesos)), 3, "os tres nao podem empatar")
        self.assertGreater(pesos[0], pesos[2])


class OPdfNaoPodeDiscordarDaMensagem(unittest.TestCase):
    """N3 e N4. Eu consertei a afirmacao falsa na MENSAGEM e deixei o PDF
    afirmando - duas vezes, e sao o mesmo erro de forma.

    Os dois canais saem do mesmo levantamento justamente para nao
    poderem discordar. Texto que afirma algo sobre uma oferta mora no
    EVENTO, uma vez.
    """

    def test_o_texto_da_entrega_viaja_no_evento(self):
        r = dados(em_todas(operadora="Brisanet", produto="fibra",
                           nome="Brisanet 500", preco=114.80, gb=None,
                           mbps=None, data=ONTEM,
                           chave="Brisanet|fibra|None|simples"),
                  em_todas(operadora="Brisanet", produto="fibra",
                           nome="Brisanet 500", preco=120.0, gb=None,
                           mbps=None, data=HOJE,
                           chave="Brisanet|fibra|None|com_apps"))
        self.assertTrue(r["remodeladas"], "o cenario tem de produzir evento")
        e = r["remodeladas"][0]
        self.assertEqual(e["texto_entrega"], "entrega não lida")
        self.assertNotIn("None", e["texto_entrega"])

    def test_e_o_do_preco_tambem(self):
        r = dados(em_todas(nome="Vivo Pós", preco=None, gb=20, data=ONTEM,
                           chave="Vivo|movel|20gb|simples"),
                  em_todas(nome="Vivo Pós", preco=35.0, gb=20, data=HOJE,
                           chave="Vivo|movel|20gb|com_apps"))
        self.assertTrue(r["remodeladas"])
        self.assertEqual(r["remodeladas"][0]["texto_preco"],
                         "preço não lido nos dois dias")

    def test_o_erro_da_coleta_chega_ao_pdf(self):
        so_erro("coletas", em_todas(data=ONTEM) + em_todas(data=HOJE))
        _t, d = robo.montar_mensagem(HOJE, ONTEM)
        self.assertTrue(d["erro_coleta"], "o PDF precisa do erro para "
                                          "nao listar nove sem registro")


class IndiceVazioNaoEBancoVazio(unittest.TestCase):
    """N5. "Nenhuma oferta foi capturada hoje" saia de indice vazio, e
    indice vazio inclui o caso em que as capturas existem e TODAS
    colidiram. A frase era falsa e a linha do ponto cego, duas abaixo,
    a desmentia."""

    def _tudo_colidido(self):
        a = oferta(produto="combo", nome="Vivo Família 2 + TV", preco=290.0,
                   gb=None, mbps=700, data=HOJE)
        return [a, dict(a, preco_promocional=390.0)]

    def test_capturas_que_colidiram_nao_sao_capturas_ausentes(self):
        t = montar([], self._tudo_colidido(), coletas=COLETA_OK)
        self.assertNotIn("Nenhuma oferta foi capturada", t)
        self.assertIn("indistinguíveis entre si", t)

    def test_banco_de_fato_vazio_continua_dizendo(self):
        falhou = [dict(c, sucesso=False) for c in COLETA_OK]
        t = montar([], [], coletas=falhou)
        self.assertIn("Nenhuma oferta foi capturada", t)


# ======================================================== gravidade media

class AEscolhaEntreDuasLeituras(unittest.TestCase):
    """N8. A regra estava no codigo e nao no papel: quando a oferta de
    ontem pareia por chave E por nome, _renomeadas rodava primeiro e
    ganhava. A preferencia e defensavel - a chave de continuidade e a
    identidade mais forte - e o que faltava era declara-la e nao esconder
    a leitura descartada."""

    def _dia(self):
        ontem = em_todas(operadora="Vivo", produto="fibra",
                         nome="Vivo Fibra 600 Mega", preco=100.0,
                         gb=None, mbps=600, data=ONTEM,
                         chave="Vivo|fibra|600mbps|simples")
        hoje = em_todas(operadora="Vivo", produto="fibra",
                        nome="Vivo Fibra Pro", preco=130.0, gb=None,
                        mbps=600, data=HOJE,
                        chave="Vivo|fibra|600mbps|simples")
        hoje += em_todas(operadora="Vivo", produto="fibra",
                         nome="Vivo Fibra 600 Mega", preco=160.0, gb=None,
                         mbps=600, data=HOJE,
                         chave="Vivo|fibra|600mbps|com_apps")
        return ontem, hoje

    def test_a_chave_ganha_do_nome(self):
        ontem, hoje = self._dia()
        r = dados(ontem, hoje)
        self.assertEqual(len(r["renomeadas"]), 1)
        self.assertEqual(r["remodeladas"], [])

    def test_e_a_outra_leitura_fica_registrada(self):
        ontem, hoje = self._dia()
        r = dados(ontem, hoje)
        outras = r["renomeadas"][0].get("outras_leituras") or []
        self.assertTrue(outras, "a leitura descartada nao pode desaparecer")
        self.assertEqual(outras[0]["preco"], 160.0)

    def test_mesmo_quando_ela_nao_esta_na_praca_representante(self):
        """QUARTA AUDITORIA, V3. O laco que colava a leitura descartada
        no evento procurava pela identidade do REPRESENTANTE do grupo -
        uma praca so. Com a alternativa existindo em Joinville e o
        representante sendo Sao Paulo, a coluna "Outra leitura possivel"
        saia "—", que se le como "nao havia outra".

        E o teste acima era cego: ele monta as duas leituras com
        em_todas, entao a alternativa esta em todas as 20 pracas e a
        representante sempre e uma delas. Fixture uniforme nao testa
        alcance.
        """
        from coletores.pracas import PRACAS, rotulo
        quais = [rotulo(p) for p in PRACAS]
        ontem = em_todas(operadora="Vivo", produto="fibra",
                         nome="Vivo Fibra 600 Mega", preco=100.0,
                         gb=None, mbps=600, data=ONTEM,
                         chave="Vivo|fibra|600mbps|simples")
        hoje = em_todas(operadora="Vivo", produto="fibra",
                        nome="Vivo Fibra Pro", preco=130.0, gb=None,
                        mbps=600, data=HOJE,
                        chave="Vivo|fibra|600mbps|simples")
        # a leitura alternativa existe em UMA praca, que nao e a primeira
        hoje += [oferta(operadora="Vivo", produto="fibra",
                        nome="Vivo Fibra 600 Mega", preco=160.0, gb=None,
                        mbps=600, data=HOJE, praca=quais[-1],
                        chave="Vivo|fibra|600mbps|com_apps")]
        r = dados(ontem, hoje)
        outras = r["renomeadas"][0].get("outras_leituras") or []
        self.assertTrue(outras, "a alternativa estava em %s" % quais[-1])
        self.assertEqual(outras[0]["praca"], quais[-1])


class UmMovimentoUmEvento(unittest.TestCase):
    """V2. Grade e "degrau que voltou" contavam o mesmo movimento duas
    vezes, e esta no dado real de 13/10: o reajuste de 45 GB da Claro sai
    como grade em 19 pracas e, em Belo Horizonte - onde o degrau faltou
    em 12/10 -, sai de novo como "voltou". "3 mudancas hoje" sobre dois
    fatos, com o mesmo +17% em duas linhas e denominadores diferentes.

    A grade e o relato mais completo: ela mostra a escada inteira. Entao
    ela fica e o "voltou" do mesmo degrau sai.
    """

    def _escada(self, sem_45_em=None):
        """A escada da Claro: 45 GB de 59,90 para 69,90 em todas as pracas.

        O HISTORICO VAI POR "extras", e nao por um patch proprio: o
        banco de mentira de dados() e instalado depois e sobrescreveria
        o patch - era assim que este teste ficava vazio, com "voltaram"
        em zero por falta de historico e nao pelo dedupe (V2).
        """
        from coletores.pracas import PRACAS, rotulo
        quais = [rotulo(p) for p in PRACAS]
        ontem, hoje, historico = [], [], []
        for p in quais:
            for preco, gb in ((59.90, 45), (69.90, 50)):
                ontem.append(oferta(operadora="Claro", produto="controle",
                                    nome="Claro Controle", preco=preco,
                                    gb=gb, praca=p, data=ONTEM,
                                    chave="Claro|controle|%dgb|s" % gb))
                historico.append(
                    oferta(operadora="Claro", produto="controle",
                           nome="Claro Controle", preco=preco, gb=gb,
                           praca=p, data="2026-10-18",
                           chave="Claro|controle|%dgb|s" % gb))
            for preco, gb in ((69.90, 45), (79.90, 50)):
                hoje.append(oferta(operadora="Claro", produto="controle",
                                   nome="Claro Controle", preco=preco,
                                   gb=gb, praca=p, data=HOJE,
                                   chave="Claro|controle|%dgb|s" % gb))
        if sem_45_em:
            ontem = [l for l in ontem
                     if not (l["praca"] == sem_45_em
                             and l["franquia_anunciada_gb"] == 45)]
        return ontem, hoje, historico, quais

    def test_a_grade_e_o_voltou_nao_contam_duas_vezes(self):
        """A FORMA REAL: a grade vale em 19 pracas e o "voltou" esta na
        vigesima, onde o degrau faltou ontem. Foi por isso que o dedupe
        por praca - o primeiro que escrevi - nao pegava nada: a praca e
        exatamente o que difere entre os dois relatos."""
        _o, _h, _x, quais = self._escada()
        ontem, hoje, historico, _q = self._escada(sem_45_em=quais[2])
        r = dados(ontem, hoje, extras=historico)
        self.assertTrue(r["grades"], "a escada tem de aparecer")
        self.assertEqual(r["voltaram"], [],
                         "a grade ja contou este movimento")
        # E A PRACA DO EVENTO DESCARTADO ENTRA NA GRADE (W2). O reajuste
        # alcancou as 20; naquela praca a escada nao era comparavel
        # porque o degrau faltava ontem, mas o movimento chegou la - e
        # dizer "em 19 de 20" subestimaria um movimento nacional.
        self.assertIn(quais[2], r["grades"][0]["pracas"])
        self.assertIn("todas as 20", r["grades"][0]["onde"])

    def test_preco_anterior_diferente_sao_dois_fatos(self):
        """Se em BH a ultima venda foi a outro valor, o movimento nao e o
        mesmo - e os dois saem, cada um com o seu percentual."""
        _o, _h, _x, quais = self._escada()
        ontem, hoje, historico, _q = self._escada(sem_45_em=quais[2])
        # na praca sem o degrau, a ultima venda foi a 49,90 e nao a 59,90
        historico = [l for l in historico
                     if not (l["praca"] == quais[2]
                             and l["franquia_anunciada_gb"] == 45)]
        historico += [oferta(operadora="Claro", produto="controle",
                             nome="Claro Controle", preco=49.90, gb=45,
                             praca=quais[2], data="2026-10-18",
                             chave="Claro|controle|45gb|s")]
        r = dados(ontem, hoje, extras=historico)
        self.assertEqual(len(r["voltaram"]), 1, r["voltaram"])
        self.assertEqual(r["voltaram"][0]["antes"], 49.90)

    def test_mas_um_degrau_fora_da_grade_continua_voltando(self):
        """O dedupe nao pode comer o que a grade NAO conta: degrau que
        voltou e nao aparece em nenhum movimento da escada segue sendo
        noticia."""
        ontem, hoje, historico, quais = self._escada()
        # um degrau de 20 GB que nao esta na escada de hoje nem de ontem
        hoje += [oferta(operadora="Claro", produto="controle",
                        nome="Claro Controle Mini", preco=39.90, gb=20,
                        praca=quais[0], data=HOJE,
                        chave="Claro|controle|20gb|s")]
        historico += [oferta(operadora="Claro", produto="controle",
                             nome="Claro Controle Mini", preco=29.90, gb=20,
                             praca=quais[0], data="2026-10-18",
                             chave="Claro|controle|20gb|s")]
        r = dados(ontem, hoje, extras=historico)
        self.assertEqual(len(r["voltaram"]), 1, r["voltaram"])
        self.assertEqual(r["voltaram"][0]["entrega"], 20)


class AJanelaEUmaSo(unittest.TestCase):
    """N9 e N10. Uma linha sem hora apagava o aviso inteiro, e havia duas
    definicoes de "janela da manha" em dois arquivos."""

    def _com_hora(self, *horas):
        col = []
        for i, h in enumerate(horas):
            c = dict(COLETA_OK[i])
            c["iniciada_em"] = (HOJE + "T" + h) if h else None
            col.append(c)
        return montar(em_todas(data=ONTEM), em_todas(data=HOJE), coletas=col)

    def test_uma_linha_sem_hora_nao_apaga_o_aviso(self):
        t = self._com_hora(None, "22:40", "22:41")
        self.assertIn("começou às 22:40", t)

    def test_a_janela_e_a_da_guarda(self):
        import ja_coletou
        t = self._com_hora("11:50")
        self.assertIn("começou às 11:50", t)
        self.assertIn(ja_coletou.LIMITE.strftime("%H:%M"), t)

    def test_coleta_na_janela_nao_recebe_ressalva(self):
        self.assertNotIn("fora da janela", self._com_hora("06:30", "06:40"))


class OVigiaDizQuantosSaoGraves(unittest.TestCase):
    """N13. "20 salto(s) acima de 50%, o mais grave em X" deixa o leitor
    entender que os 20 sao graves, e em geral e um so."""

    def _dia(self, n=30):
        return [{"operadora": "Vivo", "produto": "movel", "praca": "P/X",
                 "nome_oferta": "O%d" % i, "preco_promocional": 100.0,
                 "franquia_anunciada_gb": 50, "degrau_mbps": None,
                 "chave": "c%d" % i} for i in range(n)]

    def test_a_contagem_dos_severos_aparece(self):
        ontem = self._dia()
        hoje = self._dia()
        hoje[0]["preco_promocional"] = 24.60      # severo
        for i in range(1, 6):
            hoje[i]["preco_promocional"] = 160.0  # nao severos
        r = vigia.achados(hoje, {"2026-10-%02d" % (10 + i): ontem
                                 for i in range(5)})
        salto = [t for _g, t in r if "salto" in t][0]
        self.assertIn("6 salto(s)", salto)
        self.assertIn("1 deles grande demais", salto)


class EntregaQueMexeuNaoEEntregaParada(unittest.TestCase):
    """N14. A linha da leitura afirma "sem mexer em preco nem entrega", e
    entrega_mudou e False tambem quando um dos lados nao foi lido - a
    entrega mexeu, de desconhecida para 500. Caso real da Brisanet."""

    def test_entrega_nao_lida_nos_dois_dias_nao_se_moveu(self):
        """QUARTA AUDITORIA, V6. A primeira correcao exigia que os
        quatro campos fossem conhecidos, e isso tirou a possibilidade de
        atribuir a nossa leitura justamente as operadoras de coletor
        mais fragil: a Brisanet, sem velocidade nos dois dias, ficava
        permanentemente no balde do mercado.

        Desconhecido nos DOIS dias nao se moveu. Desconhecido num dia
        so, sim - e esse e o N14, no teste abaixo."""
        self.assertTrue(robo._parado(None, None))
        self.assertFalse(robo._parado(None, 500))
        self.assertFalse(robo._parado(500, None))
        self.assertTrue(robo._parado(500, 500))
        self.assertFalse(robo._parado(500, 600))

    def test_e_a_oferta_sem_entrega_pode_ser_da_leitura(self):
        """O efeito do _parado onde ele importa: duas operadoras mudando
        de versao no mesmo dia, as duas sem entrega lida, tem de poder
        ser atribuido a nossa leitura."""
        def dia(variante, bundle, data):
            linhas = []
            for op, prod in (("Brisanet", "fibra"), ("Unifique", "fibra")):
                for l in em_todas(operadora=op, produto=prod,
                                  nome="%s 500" % op, preco=114.80,
                                  gb=None, mbps=None, data=data,
                                  chave="%s|%s|None|%s" % (op, prod, variante)):
                    l["nivel_bundle"] = bundle
                    linhas.append(l)
            return linhas

        r = dados(dia("simples", 0, ONTEM), dia("com_apps", 2, HOJE))
        self.assertTrue(r["leitura"], "duas operadoras no mesmo dia")
        self.assertEqual(r["remodeladas"], [])

    def test_entrega_que_apareceu_nao_conta_como_parada(self):
        # a variante muda junto, que e o caso real de 10-19: sem isso nao
        # ha evento nenhum, e esta certo - nada identifica a mudanca
        r = dados(em_todas(operadora="Brisanet", produto="fibra",
                           nome="Brisanet 500", preco=114.80, gb=None,
                           mbps=None, data=ONTEM,
                           chave="Brisanet|fibra|None|simples"),
                  em_todas(operadora="Brisanet", produto="fibra",
                           nome="Brisanet 500", preco=114.80, gb=None,
                           mbps=500, data=HOJE,
                           chave="Brisanet|fibra|500mbps|com_apps"))
        eventos = r["remodeladas"] + r["leitura"]
        self.assertTrue(eventos)
        self.assertFalse(eventos[0]["versao_apenas"],
                         "a entrega passou de desconhecida para 500")


# ===================================== quinta auditoria: a ultima frase

class IgualdadeDePrecoSoComOsDoisLados(unittest.TestCase):
    """W1. Eu criei _texto_preco para a frase morar num lugar so, e liguei
    SO ao caminho das remodeladas. Dos seis tipos de evento, quatro
    montavam a frase na mao - e em dois deles ela afirmava igualdade.

    Composicao: o evento nasce quando o sva difere e o ramo de preco NAO
    disparou, e ele nao dispara quando um dos lados e None - a guarda do
    A1. Entao "mesmo preco, trocou 1 servico incluso" saia sobre uma
    oferta cujo preco de ontem nao foi lido, e o PDF afirmava junto, na
    mesma pagina: "Ofertas cujo preco permaneceu inalterado" com a
    coluna Preco em "—".

    Renomeada: o else de "if de is not None and para is not None and de
    != para" recolhia "igual" e "nao lido" no mesmo ramo, e saia "pelo
    mesmo preco (-)" - a afirmacao de igualdade mais o travessao onde
    devia estar o numero.

    SOBRE A FREQUENCIA: zero de 31.727 capturas reais estao sem preco, e
    o gatilho nunca ocorreu em 21 dias. A3, A4, N4 e V1 tambem nunca
    ocorreram e foram consertados como graves. A regua e a garantia, nao
    a frequencia.
    """

    def test_composicao_com_preco_nao_lido(self):
        ontem = em_todas(nome="Vivo Total", preco=None, gb=50, data=ONTEM,
                         sva="A+B", chave="Vivo|combo|50gb|s")
        hoje = em_todas(nome="Vivo Total", preco=200.0, gb=50, data=HOJE,
                        sva="A+C", chave="Vivo|combo|50gb|s")
        t = montar(ontem, hoje)
        self.assertNotIn("mesmo pre\u00e7o,", t)
        self.assertIn("pre\u00e7o n\u00e3o lido nos dois dias", t)

    def test_composicao_com_preco_lido_continua_dizendo(self):
        ontem = em_todas(nome="Vivo Total", preco=200.0, gb=50, data=ONTEM,
                         sva="A+B", chave="Vivo|combo|50gb|s")
        hoje = em_todas(nome="Vivo Total", preco=200.0, gb=50, data=HOJE,
                        sva="A+C", chave="Vivo|combo|50gb|s")
        t = montar(ontem, hoje)
        self.assertIn("mesmo pre\u00e7o (200,00)", t)

    def test_renomeada_com_preco_nao_lido(self):
        ontem = em_todas(operadora="TIM", produto="controle",
                         nome="TIM Controle", preco=58.99, gb=40,
                         data=ONTEM, chave="TIM|controle|40gb|s")
        hoje = em_todas(operadora="TIM", produto="controle",
                        nome="TIM Controle Smart", preco=None, gb=40,
                        data=HOJE, chave="TIM|controle|40gb|s")
        t = montar(ontem, hoje)
        self.assertIn("mudou de nome", t)
        self.assertNotIn("pelo mesmo pre\u00e7o (-)", t)
        self.assertIn("pre\u00e7o n\u00e3o lido nos dois dias", t)

    def test_renomeada_pelo_mesmo_preco_continua_dizendo(self):
        ontem = em_todas(operadora="TIM", produto="controle",
                         nome="TIM Controle", preco=58.99, gb=40,
                         data=ONTEM, chave="TIM|controle|40gb|s")
        hoje = em_todas(operadora="TIM", produto="controle",
                        nome="TIM Controle Smart", preco=58.99, gb=40,
                        data=HOJE, chave="TIM|controle|40gb|s")
        t = montar(ontem, hoje)
        self.assertIn("mesmo pre\u00e7o (58,99)", t)

    def test_e_o_peso_da_composicao_sem_preco_nao_e_zero(self):
        """W3. Com a guarda do V1, composicao com um preco nao lido caia
        em pc(None, pd) e pesava 0,000, indo para o fim do grupo nos dois
        canais."""
        e = {"antes": {"preco_promocional": None, "assinatura_sva": "A+B"},
             "atual": {"preco_promocional": 200.0, "assinatura_sva": "C+D"}}
        self.assertGreater(robo._por_efeito(e), 0.0)


class PrecoEVoltouNaoContamDuasVezes(unittest.TestCase):
    """W2. A cadeia de dedupes cobria tres dos quatro pares possiveis, e
    faltava preco x voltou. Pior: "cobertos" esvazia os precos da grade
    justamente quando existe um evento de preco para aquela entrega,
    entao nos casos em que o movimento sai como preco o conjunto da
    grade nasce vazio e o conserto anterior nao tem o que comparar.
    """

    def test_o_mesmo_reajuste_por_duas_rotas(self):
        from coletores.pracas import PRACAS, rotulo
        quais = [rotulo(p) for p in PRACAS]
        ontem, hoje, historico = [], [], []
        for p in quais:
            ontem.append(oferta(operadora="Claro", produto="controle",
                                nome="Claro Controle 45GB", preco=59.90,
                                gb=45, praca=p, data=ONTEM,
                                chave="Claro|controle|45gb|s"))
            historico.append(oferta(operadora="Claro", produto="controle",
                                    nome="Claro Controle 45GB", preco=59.90,
                                    gb=45, praca=p, data="2026-10-18",
                                    chave="Claro|controle|45gb|s"))
            hoje.append(oferta(operadora="Claro", produto="controle",
                               nome="Claro Controle 45GB", preco=69.90,
                               gb=45, praca=p, data=HOJE,
                               chave="Claro|controle|45gb|s"))
        # numa praca o degrau faltou ontem: ele "volta" por la
        ontem = [l for l in ontem if l["praca"] != quais[2]]
        r = dados(ontem, hoje, extras=historico)
        self.assertEqual(len(r["mudancas_preco"]), 1)
        self.assertEqual(r["voltaram"], [], "o preco ja contou")

    def test_e_a_praca_do_descartado_entra_no_que_fica(self):
        from coletores.pracas import PRACAS, rotulo
        quais = [rotulo(p) for p in PRACAS]
        ontem, hoje, historico = [], [], []
        for p in quais:
            ontem.append(oferta(operadora="Claro", produto="controle",
                                nome="Claro Controle 45GB", preco=59.90,
                                gb=45, praca=p, data=ONTEM,
                                chave="Claro|controle|45gb|s"))
            historico.append(oferta(operadora="Claro", produto="controle",
                                    nome="Claro Controle 45GB", preco=59.90,
                                    gb=45, praca=p, data="2026-10-18",
                                    chave="Claro|controle|45gb|s"))
            hoje.append(oferta(operadora="Claro", produto="controle",
                               nome="Claro Controle 45GB", preco=69.90,
                               gb=45, praca=p, data=HOJE,
                               chave="Claro|controle|45gb|s"))
        ontem = [l for l in ontem if l["praca"] != quais[2]]
        r = dados(ontem, hoje, extras=historico)
        m = r["mudancas_preco"][0]
        self.assertIn(quais[2], m["pracas"],
                      "o reajuste alcancou esta praca, por outra rota")
        self.assertIn("todas as 20", m["onde"])


class OPrecoNaoLidoNaoEntraNaLeitura(unittest.TestCase):
    """W4. Oferta sem preco nos DOIS dias entrava em versao_apenas, e o
    resumo dizia "sem mexer em preco nem entrega" enquanto a linha da
    mesma oferta dizia "preco nao lido nos dois dias".

    A assimetria com a entrega e deliberada: entrega nao lida nos dois
    dias nao se moveu - e o caso da Brisanet, e a docstring de _parado
    defende. Preco nao lido e diferente: a operadora pode ter reajustado
    e nos simplesmente nao vimos.
    """

    def test_sem_preco_nos_dois_dias_nao_e_so_versao(self):
        def dia(variante, bundle, data):
            linhas = []
            for op in ("Brisanet", "Claro"):
                for l in em_todas(operadora=op, produto="fibra",
                                  nome="%s 500" % op, preco=None,
                                  gb=None, mbps=500, data=data,
                                  chave="%s|fibra|500mbps|%s" % (op, variante)):
                    l["nivel_bundle"] = bundle
                    linhas.append(l)
            return linhas

        r = dados(dia("simples", 0, ONTEM), dia("com_apps", 2, HOJE))
        eventos = r["remodeladas"] + r["leitura"]
        self.assertTrue(eventos)
        self.assertFalse(eventos[0]["versao_apenas"])
        self.assertEqual(r["leitura"], [], "sem preco lido, nao e so versao")


class OVoltouNaoCalculaOProprioPercentual(unittest.TestCase):
    """W5. A linha do voltou tinha "if v["antes"] else 0", e com um preco
    anterior de 0,00 imprimia "+0% sobre os 0,00" enquanto o PDF
    imprimia "—" para o mesmo evento. Ultimo numero que os dois canais
    calculavam em dois lugares."""

    def _voltou(self, antes):
        historico = em_todas(operadora="Vivo", produto="fibra",
                             nome="Vivo Fibra", preco=antes, gb=None,
                             mbps=100, data="2026-10-18")
        ontem = em_todas(operadora="Vivo", produto="fibra",
                         nome="Vivo Fibra Light", preco=90.0, gb=None,
                         mbps=200, data=ONTEM)
        hoje = em_todas(operadora="Vivo", produto="fibra",
                        nome="Vivo Fibra", preco=100.0, gb=None,
                        mbps=100, data=HOJE)
        return montar(ontem, hoje, extras=historico)

    def test_preco_anterior_zero_nao_vira_mais_zero_por_cento(self):
        t = self._voltou(0.0)
        self.assertIn("voltou por", t)
        self.assertNotIn("+0% sobre", t)
        self.assertIn("sem varia\u00e7\u00e3o apurada", t)

    def test_percentual_de_verdade_continua_saindo(self):
        self.assertIn("+11%", self._voltou(90.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
