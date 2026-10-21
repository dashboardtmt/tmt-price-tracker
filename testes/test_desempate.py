# -*- coding: utf-8 -*-
u"""O desempate do grupo indistinguivel pelo codigo de registro.

AS DUAS "VIVO FAMILIA 2 + TV". Ofertas de 700 Mega a R$ 290 e a R$ 390
dividem chave de serie, praca e nome. _indexar tira as duas da
comparacao, e com razao: eleger uma por sorteio ja produziu o falso
"390,00 -> 290,00  -26% em todas as 20 pracas" num dia em que nenhum
preco mudou. Eram 40 ofertas por dia, todo dia, e a mensagem carregava a
ressalva.

O campo que as separa sempre esteve gravado - VIV202604041398 e
VIV202604041326 -, porque e ele que permite as duas linhas conviverem no
indice unico da tabela. So o pareamento nao olhava para ele.

O QUE ESTES TESTES PROTEGEM, nesta ordem de importancia:

  1. o codigo NAO entra na identidade de todo mundo. Medido em 22 dias,
     752 ofertas unicas (2,6%) mantem chave, praca e nome e trocam de
     codigo - e trocam JUNTO COM O PRECO, que e a noticia. Com o codigo
     na identidade, a Vivo Fibra 700 caindo de R$ 150 para R$ 100 em
     08/10/2026 viraria "oferta saiu" mais "oferta nova" e o corte de
     33% desapareceria da mensagem;
  2. o grupo que o codigo NAO separa continua fora. Codigo repetido ou
     ausente dentro do grupo devolve o sorteio, e o sorteio e o defeito;
  3. oferta que o codigo separa e que nao tem par e oferta NOVA, nao
     oferta indistinguivel: entra no indice, chega aos detectores e
     conta na cobertura como sem par;
  4. ninguem ganha dois pares - cobertura acima de 100% seria o sinal.
"""
import unittest

from _apoio import (HOJE, ONTEM, dados, em_todas, montar, oferta,
                    sem_declaracao)

# Os codigos reais das duas ofertas que motivaram tudo isto.
CARA, BARATA = "VIV202604041326", "VIV202604041398"
BASE = dict(operadora="Vivo", produto="combo", nome="Vivo Família 2 + TV",
            gb=None, mbps=700, chave="Vivo|combo|700mbps|familia")


def par(data, preco_cara=390.0, preco_barata=290.0,
        cod_cara=CARA, cod_barata=BARATA):
    """As duas ofertas que dividem chave, praca e nome, nas 20 pracas."""
    return (em_todas(preco=preco_barata, anatel=cod_barata, data=data, **BASE)
            + em_todas(preco=preco_cara, anatel=cod_cara, data=data, **BASE))


class CodigoSeparaOGrupo(unittest.TestCase):
    def test_o_grupo_sai_da_ressalva(self):
        t = montar(par(ONTEM), par(HOJE))
        self.assertNotIn("indistinguíveis", t)
        self.assertNotIn("fora da comparação", t)

    def test_e_a_cobertura_fica_inteira(self):
        r = dados(par(ONTEM), par(HOJE))
        cob = r["cobertura"]
        self.assertEqual(cob["fora"], 0)
        self.assertEqual(cob["pares"], 40, "as 2 ofertas em 20 pracas")
        self.assertEqual(cob["fracao"], 1.0)

    def test_o_reajuste_de_uma_delas_aparece(self):
        """O ponto de tudo. Antes, o grupo inteiro saia e um reajuste
        dentro dele era invisivel - nao havia como anuncia-lo sem
        escolher por sorteio qual das duas tinha mudado."""
        t = montar(par(ONTEM), par(HOJE, preco_cara=420.0))
        self.assertIn("390,00 → 420,00", t)
        self.assertIn("em todas as 20 praças", t)

    def test_e_a_outra_nao_e_arrastada(self):
        """Uma mudou, a irma nao: a mensagem nao pode somar as duas."""
        t = montar(par(ONTEM), par(HOJE, preco_cara=420.0))
        self.assertIn("1 mudança hoje", t)
        self.assertNotIn("290,00 →", t)

    def test_o_reajuste_da_barata_tambem(self):
        """A mesma prova pelo outro lado: nao e a primeira do grupo que
        vale, e a oferta certa - o sorteio ficava com a de R$ 390."""
        t = montar(par(ONTEM), par(HOJE, preco_barata=310.0))
        self.assertIn("290,00 → 310,00", t)
        self.assertNotIn("390,00 →", t)


class OGrupoQueOCodigoNaoSepara(unittest.TestCase):
    """A guarda. Sem ela o desempate troca a ambiguidade de lugar."""

    def test_codigo_repetido_mantem_o_grupo_fora(self):
        t = montar(par(ONTEM, cod_cara=BARATA), par(HOJE, cod_cara=BARATA))
        self.assertIn("indistinguíveis entre si", t)

    def test_e_nao_anuncia_reajuste_dentro_dele(self):
        """O defeito original, reproduzido com codigo repetido: as duas
        ofertas existem nos dois dias pelos mesmos precos, e a mensagem
        nao pode dizer que uma virou a outra."""
        t = montar(par(ONTEM, cod_cara=BARATA), par(HOJE, cod_cara=BARATA))
        self.assertNotIn("-26%", t)
        self.assertNotIn("390,00 → 290,00", t)

    def test_codigo_ausente_mantem_o_grupo_fora(self):
        """A Claro nao publica codigo em nenhuma oferta - 7.462 linhas
        medidas, zero com codigo. Grupo sem codigo nao tem desempate."""
        t = montar(par(ONTEM, cod_cara=None, cod_barata=None),
                   par(HOJE, cod_cara=None, cod_barata=None))
        self.assertIn("indistinguíveis entre si", t)

    def test_um_codigo_so_no_grupo_nao_basta(self):
        """Meio desempate nao e desempate: com uma linha sem codigo, a
        outra nao fica identificada por eliminacao - ficaria se o grupo
        tivesse so duas, mas o criterio nao pode depender do tamanho."""
        t = montar(par(ONTEM, cod_cara=None), par(HOJE, cod_cara=None))
        self.assertIn("indistinguíveis entre si", t)


class OCodigoNaoEntraNaIdentidadeDeTodOS(unittest.TestCase):
    """O risco da correcao de uma linha, que era a tentadora.

    Medido em 22 dias: 752 ofertas unicas mantem chave, praca e nome e
    trocam de codigo - a Vivo Fibra 700 passou de VIV202603035617 para
    VIV202603035715 em 08/10/2026 baixando de R$ 150 para R$ 100.
    """

    def test_oferta_unica_que_troca_de_codigo_pareia_pelo_nome(self):
        t = montar(em_todas(operadora="Vivo", produto="fibra",
                            nome="Vivo Fibra", gb=None, mbps=700,
                            preco=150.0, anatel="VIV202603035617",
                            data=ONTEM),
                   em_todas(operadora="Vivo", produto="fibra",
                            nome="Vivo Fibra", gb=None, mbps=700,
                            preco=100.0, anatel="VIV202603035715",
                            data=HOJE))
        self.assertIn("150,00 → 100,00", t)
        self.assertIn("-33%", t)

    def test_e_nao_vira_oferta_nova_mais_oferta_que_saiu(self):
        r = dados(em_todas(operadora="Vivo", produto="fibra",
                           nome="Vivo Fibra", gb=None, mbps=700,
                           preco=150.0, anatel="VIV202603035617",
                           data=ONTEM),
                  em_todas(operadora="Vivo", produto="fibra",
                           nome="Vivo Fibra", gb=None, mbps=700,
                           preco=100.0, anatel="VIV202603035715",
                           data=HOJE))
        self.assertEqual(r["cobertura"]["fracao"], 1.0)


class OGrupoQueColideSoDeUmLado(unittest.TestCase):
    """452 grupos medidos colidem num dia e nao no outro.

    Ontem uma oferta, hoje duas com codigos {A, B} e a de ontem com o
    codigo A. Antes o grupo inteiro de hoje saia e nao se dizia nada; a
    de codigo A tem de parear - reajuste visivel - e a B tem de sobrar
    como oferta nova, uma, no lugar de duas.
    """

    def _ontem_sozinha(self, preco=290.0, cod=BARATA):
        return em_todas(preco=preco, anatel=cod, data=ONTEM, **BASE)

    def test_a_irma_conhecida_pareia(self):
        t = montar(self._ontem_sozinha(), par(HOJE, preco_barata=310.0))
        self.assertIn("290,00 → 310,00", t)

    def test_a_que_sobra_nao_e_chamada_de_indistinguivel(self):
        t = montar(self._ontem_sozinha(), par(HOJE))
        self.assertNotIn("indistinguíveis", t)
        self.assertNotIn("fora da comparação", t)

    def test_e_a_cobertura_conta_ela_como_sem_par(self):
        """Ela e oferta de hoje e nao tem par: a cobertura cai, e esse e
        o numero certo. Antes ela saia do denominador como ponto cego -
        duas afirmacoes falsas pelo preco de uma."""
        r = dados(self._ontem_sozinha(), par(HOJE))
        cob = r["cobertura"]
        self.assertEqual(cob["hoje"], 40, "as 2 ofertas em 20 pracas")
        self.assertEqual(cob["pares"], 20, "so a irma conhecida")
        self.assertEqual(cob["fora"], 0, "nenhuma e indistinguivel")

    def test_o_outro_sentido_tambem(self):
        """Ontem duas, hoje uma. A que ficou tem de parear com a sua, nao
        com a que saiu do ar."""
        t = montar(par(ONTEM),
                   em_todas(preco=310.0, anatel=BARATA, data=HOJE, **BASE))
        self.assertIn("290,00 → 310,00", t)
        self.assertNotIn("390,00 →", t)


class NinguemGanhaDoisPares(unittest.TestCase):
    """Cobertura acima de 100% e o sinal de oferta com dois pares.

    A linha que vem do indice muda de identidade ao ser promovida. Se a
    identidade base continuasse apontando para ela, a mesma oferta
    pareava duas vezes.
    """

    def test_a_cobertura_nunca_passa_de_cem(self):
        casos = (
            (self._so_hoje, "grupo so de hoje"),
            (self._so_ontem, "grupo so de ontem"),
            (self._nos_dois, "grupo nos dois dias"),
        )
        for monta, qual in casos:
            with self.subTest(qual):
                cob = dados(*monta())["cobertura"]
                self.assertLessEqual(cob["fracao"], 1.0, qual)
                self.assertLessEqual(cob["pares"], cob["hoje"], qual)

    def test_a_oferta_promovida_nao_conta_duas_vezes(self):
        """A LINHA QUE VEM DO INDICE MUDA DE IDENTIDADE. Se a base
        continuasse apontando para ela, a mesma oferta entrava duas
        vezes no denominador: 20 ofertas coletadas viravam 40 e a
        cobertura caia para 50% sem que nada tivesse faltado.

        A cobertura nunca passa de 100% - pares e um subconjunto do
        indice -, entao o excesso aparece pelo outro lado, como
        cegueira inventada. E a classe de defeito que a metodologia
        proibe: falha que se parece com resultado.
        """
        cob = dados(par(ONTEM),
                    em_todas(preco=290.0, anatel=BARATA, data=HOJE,
                             **BASE))["cobertura"]
        self.assertEqual(cob["hoje"], 20, "uma oferta por praca, e so")
        self.assertEqual(cob["pares"], 20)
        self.assertEqual(cob["fracao"], 1.0)

    def test_e_o_denominador_nao_muda_com_o_desempate(self):
        """O desempate move oferta de "fora" para o indice; o total de
        ofertas de hoje e o mesmo nos dois casos.

        Com enchimento comparavel dos dois lados, como em dia real: um
        dia feito so do grupo colidido deixa o indice vazio, e ai
        _cobertura devolve None de proposito - nao ha o que cobrir.
        """
        cheio = (em_todas(data=ONTEM), em_todas(data=HOJE))
        com = dados(par(ONTEM) + cheio[0], par(HOJE) + cheio[1])["cobertura"]
        sem = dados(par(ONTEM, cod_cara=None, cod_barata=None) + cheio[0],
                    par(HOJE, cod_cara=None, cod_barata=None)
                    + cheio[1])["cobertura"]
        self.assertEqual(com["hoje"], sem["hoje"])
        self.assertEqual(com["fora"], 0)
        self.assertEqual(sem["fora"], 40, "sem codigo, o grupo fica fora")

    def _so_hoje(self):
        return em_todas(preco=290.0, anatel=BARATA, data=ONTEM, **BASE), par(HOJE)

    def _so_ontem(self):
        return par(ONTEM), em_todas(preco=290.0, anatel=BARATA, data=HOJE, **BASE)

    def _nos_dois(self):
        return par(ONTEM), par(HOJE)


class AIdentidadeBaseMudouNosDoisLados(unittest.TestCase):
    """21/10/2026: a chave passou a sair da lista de apps.

    O grupo colide nos dois dias, mas sob identidades base diferentes -
    nao ha o que parear. Isso nao torna a oferta indistinguivel das
    irmas: o codigo continua separando as duas. Cada uma entra no indice
    com identidade propria e fica sem par, e e a cobertura que conta
    isso - nao uma ressalva de ambiguidade que seria falsa.
    """

    def _hoje_com_outra_chave(self):
        novo = dict(BASE, chave="Vivo|combo|700mbps|com_globoplay")
        return (em_todas(preco=290.0, anatel=BARATA, data=HOJE, **novo)
                + em_todas(preco=390.0, anatel=CARA, data=HOJE, **novo))

    def test_nao_ha_ressalva_de_ambiguidade(self):
        sem_declaracao(self)
        t = montar(par(ONTEM), self._hoje_com_outra_chave())
        self.assertNotIn("indistinguíveis", t)

    def test_e_a_cobertura_diz_que_perdeu_o_par(self):
        sem_declaracao(self)
        cob = dados(par(ONTEM), self._hoje_com_outra_chave())["cobertura"]
        self.assertEqual(cob["pares"], 0)
        self.assertEqual(cob["hoje"], 40)
        self.assertEqual(cob["fora"], 0)

    def test_e_atribui_as_duas_a_troca_de_identidade(self):
        """Mesmo nome, mesma praca, mesmo preco com chave nova: e
        exatamente o que trocaram_de_identidade conta, e agora ele
        alcanca as 40 em vez de perde-las no ponto cego."""
        sem_declaracao(self)
        cob = dados(par(ONTEM), self._hoje_com_outra_chave())["cobertura"]
        self.assertEqual(cob["trocaram_de_identidade"], 40)


class ADeteccaoAlcancaAOfertaNova(unittest.TestCase):
    """Oferta nova dentro de grupo colidido nao chegava a detector nenhum.

    Em 20/10/2026 a Vivo devolveu o degrau de 25 GB do pre-pago por
    R$ 35, depois de tira-lo por R$ 30 em 15/10. A oferta entrou num
    grupo que colidia e sumiu de _degraus_que_voltaram junto com o
    grupo: o reajuste de 16,7% ficou invisivel pelos dois caminhos.
    """

    # as duas ofertas do pre-pago dividem chave de serie, praca e nome:
    # e o grupo que colidia, e o codigo de registro e que as separa
    PRE = dict(operadora="Vivo", produto="prepago", nome="Vivo Pré",
               mbps=None, chave="Vivo|prepago|15gb|simples")

    def test_o_degrau_que_voltou_aparece(self):
        sem_declaracao(self)
        antigo = em_todas(preco=30.0, gb=25, anatel="VIV2",
                          data="2026-10-14", **self.PRE)
        ontem = em_todas(preco=25.0, gb=15, anatel="VIV1", data=ONTEM,
                         **self.PRE)
        hoje = (em_todas(preco=25.0, gb=15, anatel="VIV1", data=HOJE,
                         **self.PRE)
                + em_todas(preco=35.0, gb=25, anatel="VIV2", data=HOJE,
                           **self.PRE))
        r = dados(ontem, hoje, extras=antigo)
        self.assertEqual(r["cobertura"]["fora"], 0, "nenhuma fica ambigua")
        achou = [e for e in (r.get("voltaram") or []) if e["agora"] == 35.0]
        self.assertTrue(achou, "o degrau de 25 GB voltou por R$ 35")
        self.assertEqual(achou[0]["antes"], 30.0)

    def test_sem_o_desempate_ele_some(self):
        """A prova de que e o desempate que o traz: com o grupo sem
        codigo, as duas ofertas de hoje saem do indice e o degrau que
        voltou nao chega a ser olhado."""
        sem_declaracao(self)
        antigo = em_todas(preco=30.0, gb=25, anatel=None,
                          data="2026-10-14", **self.PRE)
        ontem = em_todas(preco=25.0, gb=15, anatel=None, data=ONTEM,
                         **self.PRE)
        hoje = (em_todas(preco=25.0, gb=15, anatel=None, data=HOJE,
                         **self.PRE)
                + em_todas(preco=35.0, gb=25, anatel=None, data=HOJE,
                           **self.PRE))
        # enchimento comparavel: um dia feito so do grupo colidido
        # deixa o indice vazio, e ai _cobertura devolve None
        r = dados(ontem + em_todas(data=ONTEM),
                  hoje + em_todas(data=HOJE), extras=antigo)
        self.assertEqual(r["cobertura"]["fora"], 40)
        self.assertEqual([e for e in (r.get("voltaram") or [])
                          if e["agora"] == 35.0], [])


if __name__ == "__main__":
    unittest.main()
