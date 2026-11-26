# -*- coding: utf-8 -*-
u"""A fibra e o Multi da Claro lidos do catalogo, como o card mostra.

Ate 26/11/2026 os dois eram lidos pelas frases de acessibilidade do HTML
cru. Medido em Sao Paulo: os planos de 1, 5 e 10 Giga nunca entraram (a
frase deles nao tem preco), o 350 Mega saia a 79,90 com o card a 89,90, e
o Multi trazia tres ofertas que nao estao na vitrine no lugar das que
estao. Desde 27/11 a leitura faz a mesma chamada que a pagina faz
(/api/catalog), e aplica as tres regras que a pagina aplica e o catalogo
nao: a janela do card, a cidade excluida e o card nao achado.

A fixture e a pagina e o catalogo de 26/11/2026, para Sao Paulo e
Blumenau, podados ao que a leitura usa.
"""
import io
import json
import os
import sys
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import claro  # noqa: E402

FIX = json.load(io.open(os.path.join(AQUI, "fixtures", "claro_catalogo_2026-11-26.json"),
                        encoding="utf-8"))
BRT = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 11, 26, 12, 0, tzinfo=BRT)


def _respostas():
    por_cidade = {}
    for k, itens in FIX["catalogo"].items():
        _, uf, cid = k.split("|")
        por_cidade.setdefault((uf, cid), {}).update({x["_uid"]: x for x in itens})
    return por_cidade


class _ComCatalogo(unittest.TestCase):

    def setUp(self):
        self.respostas = _respostas()
        self.lotes = []
        self.paginas = {claro.PAGINAS[p]: FIX["paginas"][p] for p in ("fibra", "combo")}
        guarda = (claro.buscar, claro.PAUSA)

        def buscar(op, url, *a, **k):
            if url.startswith(claro.CATALOGO + "?"):
                q = dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))
                uuids = q["uuids"].split(",")
                self.lotes.append(len(uuids))
                resp = self.respostas.get((q["state"], q["city"]), {})
                # o catalogo de verdade: com 22 ou mais, tudo notFound, HTTP 200
                if len(uuids) > 21:
                    resp = {}
                return 200, json.dumps({"data": [
                    resp.get(u, {"_uid": u, "catalog": {"notFound": True}})
                    for u in uuids]})
            if url in self.paginas:
                return 200, ('<html><script id="__NEXT_DATA__" type="application/json">'
                             '%s</script></html>' % json.dumps(self.paginas[url]))
            return 200, ""
        claro.buscar = buscar
        claro.PAUSA = 0

        def volta():
            claro.buscar, claro.PAUSA = guarda
        self.addCleanup(volta)

    def ler(self, produto, cidade="Sao Paulo", uf="SP", agora=AGORA):
        return claro.ler_catalogo(None, claro.PAGINAS[produto], produto, cidade, uf, agora)


class AFibra(_ComCatalogo):

    def test_os_seis_cards_de_sao_paulo_como_a_pagina_mostra(self):
        u"""Conferido no navegador em 26/11: 350 (de 99,90 por 89,90), 750,
        500, 1, 5 e 10 Giga. Os tres de gigabit nunca tinham entrado."""
        ofertas, erro = self.ler("fibra")
        self.assertIsNone(erro)
        self.assertEqual(
            [(o["nome_oferta"], o["preco_promocional"], o["preco_cheio"]) for o in ofertas],
            [("Claro Fibra 350 Mega", 89.9, 99.9),
             ("Claro Fibra 750 Mega", 99.9, None),
             ("Claro Fibra 500 Mega", 119.9, None),
             ("Claro Fibra 1 Giga", 179.9, None),
             ("Claro Fibra 5 Giga", 499.9, None),
             ("Claro Fibra 10 Giga", 1999.9, None)])

    def test_o_codigo_anatel_vem_do_catalogo(self):
        ofertas, _ = self.ler("fibra")
        self.assertTrue(all(o["codigo_anatel"].startswith("CLR") for o in ofertas))

    def test_o_card_fora_da_janela_nao_entra(self):
        u"""O 600 Mega a 99,90 tinha janela de 15/11 e o catalogo ainda o
        resolvia em 26/11; a pagina nao o mostrava. No dia 15 ele entra."""
        hoje, _ = self.ler("fibra")
        self.assertNotIn("Claro Fibra 600 Mega", [o["nome_oferta"] for o in hoje])
        no_dia, _ = self.ler("fibra", agora=datetime(2026, 11, 15, 12, 0, tzinfo=BRT))
        self.assertIn("Claro Fibra 600 Mega", [o["nome_oferta"] for o in no_dia])

    def test_blumenau_tem_o_preco_dela(self):
        ofertas, _ = self.ler("fibra", "Blumenau", "SC")
        precos = {o["nome_oferta"]: o["preco_promocional"] for o in ofertas}
        self.assertEqual(precos["Claro Fibra 600 Mega"], 59.9)
        self.assertNotIn("Claro Fibra 5 Giga", precos)

    def test_cidade_que_o_catalogo_nao_conhece_e_erro_e_nao_ausencia(self):
        u"""Cidade inventada volta tudo notFound (medido em 26/11). Lista
        vazia seria lida como "a Claro tirou a fibra da vitrine"."""
        ofertas, erro = self.ler("fibra", "Cidade Inventada", "SP")
        self.assertIsNone(ofertas)
        self.assertIn("nao foi reconhecida", erro)

    def test_pagina_sem_cards_e_erro(self):
        self.paginas[claro.PAGINAS["fibra"]] = {"props": {}}
        ofertas, erro = self.ler("fibra")
        self.assertIsNone(ofertas)
        self.assertIn("a pagina mudou", erro)


class OMulti(_ComCatalogo):

    def test_os_quatro_de_sao_paulo(self):
        u"""As abas de celular e de familia; a de internet + TV, sem linha
        movel, fica fora."""
        ofertas, erro = self.ler("combo")
        self.assertIsNone(erro)
        self.assertEqual(
            [(o["nome_oferta"], o["preco_promocional"]) for o in ofertas],
            [(u"Claro Multi 750 Mega + Pós 100GB", 159.9),
             (u"Claro Multi 1 Giga + Pós 100GB", 179.9),
             (u"Claro Multi 750 Mega + Pós 100GB + TV Box", 259.8),
             (u"Claro Multi 1 Giga + Pós 100GB + TV Box", 279.8)])

    def test_o_preco_e_o_do_card_e_nao_a_soma(self):
        u"""O catalogo da 99,90 pela fibra e 124,90 pelo Pos; o card cobra
        159,90."""
        x = [x for x in FIX["catalogo"]["combo|SP|sao_paulo"]
             if (x["catalog"].get("internet") or {}).get("nome") == "750 Mega"
             and x.get("actions")][0]
        soma = (x["catalog"]["internet"]["preco"] + x["catalog"]["celular"]["preco"]) / 100.0
        self.assertNotEqual(soma, 159.9)
        ofertas, _ = self.ler("combo")
        self.assertEqual(ofertas[0]["preco_promocional"], 159.9)

    def test_pede_em_lotes_que_o_catalogo_responde(self):
        u"""Medido em 26/11: com 22 _uids ou mais o catalogo devolve tudo
        notFound, com HTTP 200. Um lote so viraria "cidade nao reconhecida"
        no dia em que a Claro pusesse mais cards no ar."""
        # os 23 cards do Multi no ar ao mesmo tempo: sem janela nenhuma
        pagina = json.loads(json.dumps(self.paginas[claro.PAGINAS["combo"]]))
        for it in pagina["props"]["pageProps"]["content"][0]["data"]["data"]:
            it["scheduling"] = None
        self.assertGreater(len(pagina["props"]["pageProps"]["content"][0]["data"]["data"]), 21)
        self.paginas[claro.PAGINAS["combo"]] = pagina
        ofertas, erro = self.ler("combo")
        self.assertIsNone(erro)
        self.assertTrue(ofertas)
        self.assertLessEqual(max(self.lotes), 21)

    def test_a_franquia_e_a_do_card_com_o_bonus_separado(self):
        u"""O catalogo chama o produto de "Pos 80GB"; o card diz "Pos 100GB,
        50GB + 50GB bonus". Anunciada 100, contratual 50."""
        ofertas, _ = self.ler("combo")
        self.assertEqual({(o["franquia_anunciada_gb"], o["franquia_contratual_gb"])
                          for o in ofertas}, {(100, 50)})

    def test_sem_celular_nao_e_combo(self):
        ofertas, _ = self.ler("combo")
        self.assertTrue(all(u"Pós" in o["nome_oferta"] or "Controle" in o["nome_oferta"]
                            for o in ofertas))

    def test_a_cidade_excluida_nao_ve_o_card(self):
        u"""O 1 Giga + Pos de Sao Paulo exclui Blumenau, e o catalogo o
        devolve para Blumenau a 169,90. Sem o card proprio de Blumenau, o
        1 Giga com celular some de la."""
        card = [it for it in FIX["paginas"]["combo"]["props"]["pageProps"]["content"][0]
                ["data"]["data"] if it["segments"] and it["segments"]["data"]][0]
        self.assertEqual(claro.na_cidade(card, "Blumenau", "SC"), (False, None))
        self.assertEqual(claro.na_cidade(card, "Joinville", "SC"), (True, None))
        proprio = [u for u, x in self.respostas[("SC", "blumenau")].items()
                   if (x["catalog"].get("internet") or {}).get("nome") == "1 Giga"
                   and (x["catalog"].get("celular") or {}) and not x["catalog"].get("tv")
                   and u != card["_uid"]]
        for u in proprio:
            self.respostas[("SC", "blumenau")][u] = {"_uid": u, "catalog": {"notFound": True}}
        ofertas, _ = self.ler("combo", "Blumenau", "SC")
        self.assertFalse([o for o in ofertas
                          if o["nome_oferta"].startswith(u"Claro Multi 1 Giga + Pós")
                          and "TV" not in o["nome_oferta"]])

    def test_segmento_por_ddd_entra_com_ressalva(self):
        card = {"segments": {"data": [{"ufs": [], "cities": [], "ddds": ["11"],
                                       "cities_exclusion": []}]}}
        deixa, ressalva = claro.na_cidade(card, "Sao Paulo", "SP")
        self.assertTrue(deixa)
        self.assertIn("DDD", ressalva)


class OPrecoDoCard(unittest.TestCase):

    def p(self, **price):
        return claro.preco_do_catalogo({"actions": [{"price": price}]})

    def test_o_de_riscado_e_o_preco_cheio(self):
        self.assertEqual(self.p(prefix="De: ~R$99,90~", price="R$ 89,90"),
                         (89.9, 99.9, None, None))

    def test_o_apos_e_a_promocao(self):
        self.assertEqual(self.p(prefix="De: ~R$ 374,70~", price="R$ 239,80",
                                period=" 2 meses",
                                suffix=u"por 2 meses. Após, R$ 249,80 mensal"),
                         (239.8, 374.7, 2, 249.8))

    def test_o_periodo_sozinho_nao_e_promocao(self):
        u"""O Multi de familia vem com period " 2 meses" e o card diz
        "Valor mensal" - nao ha preco depois."""
        self.assertEqual(self.p(price="R$ 259,80", period=" 2 meses", suffix=""),
                         (259.8, None, None, None))

    def test_milhar_com_ponto(self):
        self.assertEqual(self.p(price="R$ 1.999,90")[0], 1999.9)


class OCaminhoDeProducao(_ComCatalogo):
    u"""O coletar() inteiro, e nao a peca: e ele que grava."""

    def coletar(self, cidade="Sao Paulo", uf="SP"):
        d = claro.coletar(cidade, uf, verbose=False)
        return ([o for o in d["ofertas"] if o["produto"] == "fibra"],
                [o for o in d["ofertas"] if o["produto"] == "combo"], d)

    def test_a_fibra_grava_velocidade_codigo_e_preco_cheio(self):
        fibra, _, _ = self.coletar()
        por_nome = {o["nome_oferta"]: o for o in fibra}
        self.assertEqual(por_nome["Claro Fibra 10 Giga"]["degrau_mbps"], 10000)
        self.assertEqual(por_nome["Claro Fibra 1 Giga"]["degrau_mbps"], 1000)
        self.assertEqual(por_nome["Claro Fibra 350 Mega"]["preco_cheio"], 99.9)
        self.assertTrue(por_nome["Claro Fibra 350 Mega"]["codigo_anatel"].startswith("CLR"))
        self.assertIn("globoplay", por_nome["Claro Fibra 350 Mega"]["apps"])

    def test_o_multi_grava_as_duas_franquias(self):
        _, combo, _ = self.coletar()
        self.assertEqual(combo[0]["franquia_anunciada_gb"], 100)
        self.assertEqual(combo[0]["franquia_contratual_gb"], 50)
        self.assertEqual(combo[0]["degrau_mbps"], 750)

    def test_o_multi_com_tv_lista_os_apps_do_pacote(self):
        u"""O teto de 6 apps protege contra texto de PAGINA; o do catalogo e
        o do card, e o Multi com TV nomeia oito. Com o teto de 6 a lista
        saia vazia e o aviso dizia que a leitura pegou a vitrine - falso."""
        _, combo, _ = self.coletar()
        tv = [o for o in combo if "TV Box" in o["nome_oferta"]][0]
        self.assertIn("netflix", tv["apps"])
        self.assertIn("disney", tv["apps"])
        self.assertEqual(tv["nivel_bundle"], 4)
        self.assertFalse(tv.get("avisos_oferta"))

    def test_o_teto_do_catalogo_nao_vaza_para_os_outros_produtos(self):
        _, _, d = self.coletar()
        self.assertFalse([o for o in d["ofertas"] if "limite_apps" in o])


class ODiaDaTroca(unittest.TestCase):
    u"""Na primeira coleta com o leitor novo, a diferenca e a nossa leitura.

    Escolha de quem le (24/11): fora da noticia, uma linha e a lista no
    PDF. A bancada do dia mostrou um segundo paragrafo sobre a mesma
    mudanca - as ofertas que so ganharam os apps sairam como "mudaram de
    versao" - e o grupo "leitura" passou a ser alcancado tambem."""

    def setUp(self):
        sys.path.insert(0, AQUI)
        import robo
        from _apoio import HOJE, ONTEM, dados, montar, oferta
        self.robo, self.HOJE, self.ONTEM = robo, HOJE, ONTEM
        self.dados, self.montar, self.oferta = dados, montar, oferta
        guarda = robo.LEITURA_DE_OFERTA_MUDOU_EM
        robo.LEITURA_DE_OFERTA_MUDOU_EM = {HOJE: [{
            "quem": [("Claro", "fibra", u""), ("Claro", "combo", u"")],
            "texto": u"a fibra e o Multi da Claro passaram a ser lidos dos cards"}]}
        self.addCleanup(setattr, robo, "LEITURA_DE_OFERTA_MUDOU_EM", guarda)

    def _dia(self):
        of, pracas = self.oferta, ["Sao Paulo/SP", "Rio de Janeiro/RJ"]
        ontem, hoje = [], []
        for p in pracas:
            # o 750 Mega: mesmo preco, os apps passaram a ser lidos
            ontem.append(of(operadora="Claro", produto="fibra", nome="Claro Fibra 750 Mega",
                            preco=99.9, gb=None, mbps=750, praca=p, data=self.ONTEM,
                            chave="Claro|fibra|750mbps|simples", apps=[]))
            hoje.append(of(operadora="Claro", produto="fibra", nome="Claro Fibra 750 Mega",
                           preco=99.9, gb=None, mbps=750, praca=p, data=self.HOJE,
                           chave="Claro|fibra|750mbps|com_globoplay_mcafee_skeelo",
                           apps=["globoplay", "mcafee", "skeelo"]))
            # o 350 Mega: o preco do card
            ontem.append(of(operadora="Claro", produto="fibra", nome="Claro Fibra 350 Mega",
                            preco=79.9, gb=None, mbps=350, praca=p, data=self.ONTEM))
            hoje.append(of(operadora="Claro", produto="fibra", nome="Claro Fibra 350 Mega",
                           preco=89.9, gb=None, mbps=350, praca=p, data=self.HOJE))
            # e o controle da Claro mexendo de verdade no mesmo dia
            ontem.append(of(operadora="Claro", produto="controle", nome="Claro Controle 25GB",
                            preco=64.9, gb=25, praca=p, data=self.ONTEM))
            hoje.append(of(operadora="Claro", produto="controle", nome="Claro Controle 25GB",
                           preco=69.9, gb=25, praca=p, data=self.HOJE))
        return ontem, hoje

    def test_uma_linha_so_para_a_troca(self):
        ontem, hoje = self._dia()
        t = self.montar(ontem, hoje)
        self.assertIn("A nossa leitura mudou hoje", t)
        self.assertNotIn(u"mudaram de versão", t)
        self.assertNotIn("79,90", t)

    def test_o_controle_da_claro_continua_noticia(self):
        ontem, hoje = self._dia()
        t = self.montar(ontem, hoje)
        self.assertIn("64,90", t)

    def test_as_duas_vao_para_a_lista(self):
        ontem, hoje = self._dia()
        d = self.dados(ontem, hoje)
        nomes = set(self.robo._quem_e(x["evento"])[2] for x in d["relidos"])
        self.assertEqual(nomes, {"Claro Fibra 750 Mega", "Claro Fibra 350 Mega"})
        self.assertFalse(d["leitura"])


if __name__ == "__main__":
    unittest.main()
