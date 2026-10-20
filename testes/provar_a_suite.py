# -*- coding: utf-8 -*-
"""Reintroduz cada defeito real e confere se a suite pega.

TESTE QUE NUNCA FALHA NAO PROTEGE NADA. Uma suite verde so vale alguma
coisa se ficar vermelha quando o defeito volta - e isso tem de ser
demonstrado, nao suposto.

Cada mutacao abaixo e um defeito que EXISTIU neste projeto, escrito de
volta no codigo. A suite roda, e o resultado esperado e vermelho. Se
alguma passar verde, o teste correspondente nao serve e o relatorio diz
qual.

A ultima entrada e um controle: uma mudanca que nenhum teste cobre, e
que PRECISA passar verde. Sem ela, uma suite que falhasse sempre - por
um erro de importacao, digamos - pareceria perfeita aqui.

Nao roda junto com a suite: e uma ferramenta de conferir a suite, e leva
uns 20 segundos. Rodar quando mexer nos testes.
"""
import io
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class Mutacao(object):
    def __init__(self, arquivo, de, para, conta, controle=False):
        self.arquivo = arquivo
        self.de = de
        self.para = para
        self.conta = conta
        self.controle = controle


MUTACOES = [
    Mutacao(
        "coletores/apps.py",
        '    tiers = TIERS.get(app)\n    if not tiers:\n        return None\n',
        '    tiers = TIERS.get(app)\n    if not tiers:\n        return None\n'
        '    return tiers[-1][0]\n',
        "o tier do app volta a sair de um padrao nosso, e nao da fonte"),

    Mutacao(
        "coletores/apps.py",
        '        if DEGUSTACAO.search(t[max(0, ini - 24):ini] + trecho):\n'
        '            continue\n',
        '        if False:\n'
        '            continue\n',
        "degustacao volta a contar como app incluso"),

    Mutacao(
        "coletores/apps.py",
        '    m = re.fullmatch(r"(\\d+(?:[.,]\\d+)?)", t)\n'
        if False else 'def sem_degustacao(texto):',
        'def sem_degustacao(texto):\n    return texto\n\n\ndef _sem_degustacao_morta(texto):',
        "o corte da degustacao some do calculo de nivel"),

    Mutacao(
        "coletores/brisanet.py",
        '    m = re.fullmatch(r"(\\d+(?:[.,]\\d+)?)", t)\n    if m:',
        '    m = None\n    if m:',
        "a velocidade da Brisanet volta a se perder inteira"),

    Mutacao(
        "coletores/brisanet.py",
        '    v = int(achados[-1])',
        '    v = int(achados[0])',
        "o Giga da fibra volta a ser lido como franquia de movel"),

    Mutacao(
        "coletores/claro.py",
        '    for m in re.finditer(r"\\bClaro\\s+(?:P[óo]s|Controle|Multi|Fibra|"',
        '    for m in re.finditer(r"\\bNUNCA_CASA\\s+(?:P[óo]s|Controle|Multi|Fibra|"',
        "o banner de campanha volta a entrar no nome da oferta"),

    Mutacao(
        "ja_coletou.py",
        '    if agora.time() < ABERTURA:',
        '    if False:',
        "a coleta volta a poder rodar de madrugada"),

    Mutacao(
        "robo.py",
        '        mesma_etiqueta = sorted(',
        '        mesma_etiqueta = [] or sorted(' if False else '        mesma_etiqueta = []\n        _ignorado = sorted(',
        "o corte de franquia com preco parado volta a passar batido"),

    Mutacao(
        "robo.py",
        '            if e in eo and eo[e][0] != eh[e][0] and eo[e][1] == eh[e][1])',
        '            if e in eo and eo[e][0] != eh[e][0])',
        "oferta que some volta a virar 'preco que sobe'"),

    Mutacao(
        "relatorio.py",
        'PAINEL = "https://tmt-price-tracker.vercel.app"',
        'PAINEL = "https://exemplo.invalido"',
        "(controle: mudanca que nenhum teste cobre)",
        controle=True),
]


def suite_verde():
    r = subprocess.run([sys.executable, "-m", "unittest", "discover",
                        "-s", "testes"], cwd=BASE, capture_output=True)
    return r.returncode == 0


def main():
    if not suite_verde():
        print("A SUITE JA ESTA VERMELHA. Conserte antes de medir.")
        return 1

    print("%-60s %s" % ("DEFEITO REINTRODUZIDO", "A SUITE PEGA?"))
    print("-" * 78)
    inuteis, controle_errado = [], False

    for m in MUTACOES:
        caminho = os.path.join(BASE, m.arquivo)
        original = io.open(caminho, encoding="utf-8").read()
        if m.de not in original:
            print("%-60s  NAO APLIQUEI" % m.conta[:60])
            inuteis.append("%s (o trecho mudou)" % m.conta)
            continue
        io.open(caminho, "w", encoding="utf-8", newline="\n").write(
            original.replace(m.de, m.para, 1))
        try:
            verde = suite_verde()
        finally:
            io.open(caminho, "w", encoding="utf-8", newline="\n").write(original)

        if m.controle:
            ok = verde
            print("%-60s  %s" % (m.conta[:60],
                                 "nao, e esperado" if ok else "PEGOU - suspeito"))
            controle_errado = not ok
        else:
            print("%-60s  %s" % (m.conta[:60],
                                 "sim" if not verde else "NAO - teste inutil"))
            if verde:
                inuteis.append(m.conta)

    print()
    if not suite_verde():
        print("A SUITE FICOU VERMELHA DEPOIS DE RESTAURAR. Confira o repositorio.")
        return 1
    print("codigo restaurado e suite verde.")

    if controle_errado:
        print("\nO CONTROLE FALHOU: a suite fica vermelha com uma mudanca que")
        print("nenhum teste deveria cobrir. Isso indica teste fragil.")
    if inuteis:
        print("\n%d defeito(s) passariam sem a suite notar:" % len(inuteis))
        for x in inuteis:
            print("   - %s" % x)
    return 1 if (inuteis or controle_errado) else 0


if __name__ == "__main__":
    sys.exit(main())
