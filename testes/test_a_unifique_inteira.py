# -*- coding: utf-8 -*-
u"""A Unifique inteira: o combo com TV, a fibra sem apps, o riscado e a
fidelidade da fibra.

Auditoria contra o site de 26/11/2026: o combo celular + fibra + TV (3 por
cidade) e a fibra sem SVA (3 em Florianopolis, Blumenau e Joinville) estao
no menu e a coleta nao lia; a fibra saia sem a fidelidade de 12 meses, que
mora nos "Mais Detalhes", e o FIBRA COMPLETA sem o riscado de R$ 138. As
fixtures sao o texto das tres paginas de Florianopolis em 26/11/2026.
"""
import io
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import unifique  # noqa: E402


def fixture(nome):
    return io.open(os.path.join(AQUI, "fixtures", nome), encoding="utf-8").read()


FIBRA = fixture("unifique_fibra_florianopolis_2026-11-26.txt")
TV = fixture("unifique_combo_tv_florianopolis_2026-11-26.txt")
SEM = fixture("unifique_sem_sva_florianopolis_2026-11-26.txt")


class OsLeitores(unittest.TestCase):

    def test_o_combo_com_tv(self):
        lidos = [(o["nome_oferta"], o["preco_promocional"], o["meses_desconto"],
                  o["preco_pos_promocao"]) for o in unifique.extrair_combo_tv(TV)]
        self.assertEqual(lidos, [
            ("Combo Fibra 650 Mega + Celular 50 GB + TV Completa", 229.91, 12, 259.91),
            ("Combo Fibra 800 Mega + Celular 50 GB + TV Completa", 239.91, 12, 269.91),
            ("Combo Fibra 1000 Mega + Celular 50 GB + TV Completa", 249.91, 12, 279.91)])

    def test_o_riscado_da_fibra_completa(self):
        por = {(o["nome_oferta"], o["degrau_mbps"]): o for o in unifique.extrair(FIBRA)}
        self.assertEqual(por[("FIBRA COMPLETA", 600)]["preco_cheio"], 138.0)
        self.assertIsNone(por[("FIBRA IDEAL", 500)]["preco_cheio"])

    def test_a_taxa_de_instalacao_nao_vira_riscado(self):
        u"""No sem apps o card diz "Instalacao R$ 349,90 a vista R$ 104,90":
        o 349,90 e taxa, nao preco cheio."""
        por = {o["degrau_mbps"]: o for o in unifique.extrair(unifique._vitrine(SEM))}
        self.assertEqual(por[100]["taxa_instalacao"], 349.9)
        self.assertIsNone(por[100]["preco_cheio"])

    def test_a_fidelidade_dos_detalhes(self):
        fid = unifique.fidelidades(FIBRA)
        self.assertEqual(fid[("FIBRA IDEAL", 500)], 12)
        self.assertEqual(fid[("FIBRA TURBO", 1000)], 12)

    def test_o_cookie_da_praca(self):
        import base64
        import urllib.parse
        esperado = urllib.parse.quote(base64.b64encode(b"rs/porto-alegre").decode())
        self.assertEqual(unifique.cookie_da_cidade("Porto Alegre", "RS"),
                         "ckUnifique[location]=%s%s" % (esperado, unifique.SUFIXO_DO_COOKIE))


class OCaminhoDeProducao(unittest.TestCase):

    def paginas(self, sem=SEM):
        guarda = unifique.buscar
        self.cookies = []

        def buscar(url, cookie=None):
            if unifique.PAGINA_SEM_SVA in url:
                self.cookies.append(cookie)
                return (200, sem) if sem is not None else (404, "")
            if unifique.PAGINA_COMBO_TV in url:
                return 200, TV
            if unifique.PAGINA_COMBO in url or unifique.PAGINA_MOVEL in url:
                return 404, ""
            return 200, FIBRA
        unifique.buscar = buscar
        self.addCleanup(setattr, unifique, "buscar", guarda)

    def test_entra_tudo_com_a_fidelidade_e_o_sem_apps(self):
        self.paginas()
        d = unifique.coletar("Florianopolis", "SC", verbose=False)
        por = {o["nome_oferta"]: o for o in d["ofertas"]}
        self.assertEqual(por["FIBRA IDEAL"]["fidelidade_meses"], 12)
        self.assertEqual(por["FIBRA COMPLETA"]["preco_cheio"], 138.0)
        self.assertEqual(por["FIBRA IDEAL sem apps"]["preco_promocional"], 139.9)
        self.assertEqual(por["FIBRA IDEAL sem apps"]["produto"], "fibra")
        self.assertEqual(por["Combo Fibra 650 Mega + Celular 50 GB + TV Completa"]["produto"], "combo")
        self.assertTrue(self.cookies[0].startswith("ckUnifique[location]="))

    def test_sem_apps_de_outra_cidade_nao_entra(self):
        u"""O cookie que muda de formato faz a pagina mostrar outra cidade:
        a leitura falha alto em vez de gravar a fibra de outro lugar."""
        self.paginas(sem=SEM.replace(u"Florianópolis", "Curitiba").replace("Florianopolis", "Curitiba"))
        d = unifique.coletar("Florianopolis", "SC", verbose=False)
        self.assertFalse([o for o in d["ofertas"] if "sem apps" in o["nome_oferta"]])
        self.assertTrue(any("nao confirmou a cidade" in a for a in d["avisos"]))

    def test_falha_do_sem_apps_nao_derruba_o_resto(self):
        guarda = unifique._fibra_sem_apps

        def quebra(*a, **k):
            raise RuntimeError("boom")
        unifique._fibra_sem_apps = quebra
        self.addCleanup(setattr, unifique, "_fibra_sem_apps", guarda)
        self.paginas()
        d = unifique.coletar("Florianopolis", "SC", verbose=False)
        self.assertTrue([o for o in d["ofertas"] if o["produto"] == "combo"])
        self.assertTrue(any(a.startswith("fibra sem apps:") for a in d["avisos"]))


if __name__ == "__main__":
    unittest.main()
