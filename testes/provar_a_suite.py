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

    # ---------------------------------------------------------------
    # OS 23 DEFEITOS DA AUDITORIA DE 20/10/2026. Estes sao os que a
    # suite de 76 testes NAO pegava - foi uma leitura independente do
    # codigo que os achou. Cada um ganhou teste, e cada um volta aqui
    # para o teste ter de provar que serve.
    # ---------------------------------------------------------------

    Mutacao(
        "robo.py",
        '        if (antes["preco_promocional"] is not None\n'
        '                and atual["preco_promocional"] is not None\n',
        '        if (antes["preco_promocional"] is not None\n'
        '                and True\n',
        "1. preco ausente hoje volta a ser anunciado como reajuste"),

    Mutacao(
        "robo.py",
        '    remodeladas = [r for r in _oferta_remodelada(h, o, usadas)\n',
        '    remodeladas = [r for r in []\n',
        "2. preco e degrau mudando juntos voltam a ser invisiveis"),

    Mutacao(
        "robo.py",
        '            _agrupar(precos, (atual["operadora"], atual["produto"], atual["chave"],\n'
        '                              (atual.get("nome_oferta") or "").lower(),\n',
        '            _agrupar(precos, (atual["operadora"], atual["produto"], atual["chave"],\n',
        "3. duas ofertas de mesmo preco voltam a virar uma"),

    Mutacao(
        "robo.py",
        '    if ponto_cego and (col or erro_col):',
        '    if False:',
        "4. o ponto cego volta a so existir no rodape do PDF"),

    Mutacao(
        "coletores/apps.py",
        '            corte = min([p for p in paradas if p >= 0], default=None)',
        '            corte = min([p for p in paradas if p > 0], default=None)',
        "5. o tier volta a sair da frase seguinte"),

    Mutacao(
        "coletores/apps.py",
        '        if len(primeira) >= 3:',
        '        if len(primeira) >= 4:',
        "6. Max e Sky voltam a nao servir de parede"),

    Mutacao(
        "coletores/apps.py",
        '        primeira = primeira.strip("+")\n',
        '',
        "6b. o sinal de Disney+ volta a impedir a parede"),

    Mutacao(
        "robo.py",
        '    if l.get("degrau_mbps"):\n        return "Mbps"',
        '    if l.get("produto") in ("fibra", "combo"):\n        return "Mbps"',
        "7. a unidade volta a sair do produto, e nao do campo"),

    Mutacao(
        "robo.py",
        '            linhas, erro = armazenamento.consultar_tudo(\n'
        '                "capturas?operadora=eq.%s&produto=eq.%s&data_captura=gte.%s"',
        '            linhas, erro = armazenamento.consultar(\n'
        '                "capturas?operadora=eq.%s&produto=eq.%s&data_captura=gte.%s"',
        "8. a memoria de 45 dias volta a ser truncada em 1000 linhas"),

    Mutacao(
        "relatorio.py",
        '            m.get("onde") or "—",\n'
        '        ])\n'
        '    return _tabela(\n'
        '        ["Operadora", "Oferta", "Entrega", "Anterior", "Atual", "Var.",',
        '            m.get("pracas_formatadas") or "—",\n'
        '        ])\n'
        '    return _tabela(\n'
        '        ["Operadora", "Oferta", "Entrega", "Anterior", "Atual", "Var.",',
        "9. a coluna Pracas do relatorio volta a sair vazia"),

    Mutacao(
        "vigia.py",
        '            grave("%s nao aparece hoje (tipico: %d ofertas)"\n'
        '                  % (op, int(tipico)))',
        '            grave("%s nao trouxe nenhuma oferta hoje" % op)\n'
        '            grave("%s nao aparece hoje" % op)',
        "10. operadora ausente volta a ser denunciada duas vezes"),

    Mutacao(
        "vigia.py",
        '    if len(graves) == 1:\n        return "Conferir: %s" % graves[0]',
        '    if True:\n        return "Conferir: %s" % graves[0]',
        "11. o resumo volta a esconder os outros achados graves"),

    Mutacao(
        "vigia.py",
        '            (grave if severos else atencao)(texto)',
        '            atencao(texto)',
        "11b. o preco fantasma volta a nao chegar na mensagem"),

    Mutacao(
        "vigia.py",
        '        if n >= max(3, total * 0.5):',
        '        if n >= max(5, total * 0.5):',
        "12. a NuCel volta a poder perder a franquia em silencio"),

    Mutacao(
        "coletores/claro.py",
        '    achado = PRECO.search(apps.sem_degustacao(txt) or "")',
        '    achado = PRECO.search(txt or "")',
        "13. o preco do plano volta a poder sair da frase do beneficio"),

    Mutacao(
        "relatorio.py",
        '    for chave, titulo in PRODUTOS:\n'
        '        itens = entradas.get(chave) or []\n'
        '        hist.append(_com_titulo(',
        '    for chave, titulo in PRODUTOS:\n'
        '        itens = entradas.get(chave) or []\n'
        '        if not itens:\n'
        '            continue\n'
        '        hist.append(_com_titulo(',
        "18. a secao do produto sem oferta volta a desaparecer"),

    Mutacao(
        "coletores/apps.py",
        '        for pos in reversed(nomes):',
        '        for pos in nomes:',
        "20. o corte da degustacao volta a levar o app vizinho"),

    Mutacao(
        "robo.py",
        '    if len(texto) <= TETO_TELEGRAM:\n        return texto',
        '    if True:\n        return texto',
        "21. a mensagem longa volta a ser recusada pelo Telegram"),

    Mutacao(
        "robo.py",
        '    total = max(universo or len(PRACAS), quantas)',
        '    total = len(PRACAS)',
        "22. oferta nacional volta a sair como 'em 1 de 20'"),

    Mutacao(
        "robo.py",
        '        if cobertura and cobertura["fracao"] < COBERTURA_MINIMA:',
        '        if False:',
        "24. comparacao cega volta a ser reportada como mercado parado"),

    Mutacao(
        "ja_coletou.py",
        '    return len(registradas) >= esperadas, len(registradas)',
        '    return len(registradas) >= 5, len(registradas)',
        "17. o dia volta a fechar com cinco dos nove coletores"),

    Mutacao(
        "coletores/apps.py",
        '    if operadora and "vivo" in str(operadora).lower():\n'
        '        regras = DO_NOME + DO_NOME_VIVO',
        '    if True:\n'
        '        regras = DO_NOME + DO_NOME_VIVO',
        "19. o sufixo da Vivo volta a valer para as outras operadoras"),

    # ---------------------------------------------------------------
    # OS DOIS ACHADOS DA MEDICAO nos 21 dias reais, que a auditoria
    # nao tinha visto porque so aparecem no dado de verdade.
    # ---------------------------------------------------------------

    Mutacao(
        "robo.py",
        '        if not (versao_mudou or (preco_mudou and entrega_mudou)):',
        '        if not (preco_mudou and entrega_mudou):',
        "25. a oferta que muda so de versao volta a ser invisivel"),

    Mutacao(
        "robo.py",
        '    nossas = [r for r in so_versao\n'
        '              if declarado or varias_operadoras'
        ' or _minoria_das_pracas(r)]',
        '    nossas = []',
        "26. mudanca da nossa leitura volta a sair como do mercado"),

    Mutacao(
        "robo.py",
        '    return universo > 1 and quantas * 2 < universo',
        '    return False',
        "26b. versao mudando em 2 de 18 pracas volta a ser noticia"),

    Mutacao(
        "coletores/vivo.py",
        '    return max(apps.nivel_por_apps(texto, APPS_CATALOGO),\n'
        '               apps.nivel_dos_apps(lista))',
        '    return apps.nivel_por_apps(texto, APPS_CATALOGO)',
        "27. o nivel volta a contradizer a lista de apps da oferta"),

    Mutacao(
        "robo.py",
        '              if declarado or varias_operadoras'
        ' or _minoria_das_pracas(r)]',
        '              if varias_operadoras or _minoria_das_pracas(r)]',
        "28. a data declarada volta a nao mandar na heuristica"),

    Mutacao(
        "robo.py",
        '        if grupos[k] > 1:',
        '        if k in indice:',
        "29. o par indistinguivel volta a ser representado por um deles"),

    Mutacao(
        "robo.py",
        '    total = len(h) + (fora or 0)',
        '    total = len(h)',
        "30. a cobertura volta a nao contar as ofertas que sairam"),

    # ---------------------------------------------------------------
    # A SEGUNDA AUDITORIA. Nove achados graves que sobreviveram aos
    # 23 da primeira, aos 166 testes e a medicao nos 21 dias - todos
    # em caminho de ERRO: consulta que cai, lista vazia, None
    # formatado como numero, campo desconhecido afirmado como igual.
    # Codigo de sucesso a gente testa; codigo de erro a gente escreve
    # e nunca mais olha, e e onde a afirmacao falsa mora.
    # ---------------------------------------------------------------

    Mutacao(
        "robo.py",
        '    col, erro_col = armazenamento.consultar(',
        '    col, erro_col = (lambda a, b: (a, None))(*armazenamento.consultar(',
        "A1. consulta que cai volta a virar dia sem coleta"),

    Mutacao(
        "robo.py",
        '        if cobertura is None:',
        '        if False:',
        "A2. zero ofertas voltam a sair como zero mudancas"),

    Mutacao(
        "robo.py",
        '    if pedidas and ok < pedidas:',
        '    if pedidas:',
        "A2b. falha de gravacao volta a sair como 20 de 20 pracas"),

    Mutacao(
        "robo.py",
        '    if antes is None or agora is None:\n'
        '        return "entrega n\\u00e3o lida"',
        '    if False:\n'
        '        return "entrega n\\u00e3o lida"',
        "A3. entrega nao lida volta a ser afirmada como igual"),

    Mutacao(
        "robo.py",
        '    if antes is None or agora is None:\n'
        '        return "pre\\u00e7o n\\u00e3o lido nos dois dias"',
        '    if False:\n'
        '        return "pre\\u00e7o n\\u00e3o lido nos dois dias"',
        "A4. preco nao lido volta a ser afirmado como igual"),

    Mutacao(
        "robo.py",
        '    cego = cego_h\n',
        '    cego = cego_h or cego_o\n',
        "A5. a colisao de ontem volta a contar como de hoje"),

    Mutacao(
        "robo.py",
        '        grupo.sort(key=_por_efeito, reverse=True)',
        '        pass',
        "A7. a mensagem volta a mostrar 3 de N sem ordenar"),

    Mutacao(
        "vigia.py",
        '            severos = [x for x in saltos if _severo(x[2], x[3])]',
        '            severos = []',
        "A6. o vigia volta a julgar pelo salto de maior modulo"),

    Mutacao(
        "robo.py",
        '        h, o, hoje, (cego_o or {}).get("descartadas") or ()) if o else [])',
        '        h, o, hoje, (cego_o or {}).get("descartadas") or ()))',
        "M5. dia seguinte a um dia perdido volta a virar enxurrada"),

    Mutacao(
        "robo.py",
        '        if _identidade(antes) in (usadas or ()):',
        '        if False:',
        "M1. a oferta de ontem volta a ser antes de dois eventos"),

    # ---------------------------------------------------------------
    # A TERCEIRA AUDITORIA, sobre as correcoes da segunda. Quatro
    # achados graves, e o padrao dos quatro e um so: eu consertei a
    # afirmacao falsa num canal e deixei o outro afirmando.
    # ---------------------------------------------------------------

    Mutacao(
        "robo.py",
        '    ontem |= {chave(l) for l in (descartadas_de_ontem or ())'
        '\n              if _entrega(l) is not None}\n',
        '',
        "N1. descartada de ontem volta a parecer ausente de ontem"),

    Mutacao(
        "robo.py",
        '            if len(do_dia) == 1:\n'
        '                antes = recente',
        '            if True:\n'
        '                antes = recente',
        "N1b. dia historico ambiguo volta a servir de referencia"),

    Mutacao(
        "robo.py",
        '    if "antes_preco" in e:\n'
        '        return max(pc(e.get("antes_preco"), e.get("agora_preco")),\n'
        '                   pc(e.get("antes_entrega"), e.get("agora_entrega")))',
        '    if False:\n'
        '        return 0.0',
        "N2. o peso da remodelada volta a ignorar a entrega"),

    Mutacao(
        "relatorio.py",
        '        preco = r.get("texto_preco") or _reais(r.get("agora_preco"))',
        '        preco = _reais(r.get("agora_preco"))',
        "N4. o PDF volta a montar a propria frase do preco"),

    Mutacao(
        "robo.py",
        '            fora = (ponto_cego or {}).get("quantas") or 0',
        '            fora = 0',
        "N5. indice vazio volta a sair como banco vazio"),

    Mutacao(
        "robo.py",
        '                              and pa == pd and _parado(ea, ed)),',
        '                              and pa == pd and True),',
        "N14. entrega que apareceu volta a contar como parada"),

    Mutacao(
        "robo.py",
        '    inicios = sorted(c.get("iniciada_em") or "" for c in (col or [])\n'
        '                     if len(str(c.get("iniciada_em") or "")) >= 16)',
        '    inicios = sorted(c.get("iniciada_em") or "" for c in (col or []))',
        "N9. uma linha sem hora volta a apagar o aviso inteiro"),

    Mutacao(
        "vigia.py",
        '                quantos += (", %d deles grande demais para ser reajuste"\n'
        '                            % len(severos))',
        '                pass',
        "N13. o vigia volta a nao dizer quantos saltos sao graves"),

    Mutacao(
        "robo.py",
        '                evento.setdefault("outras_leituras", []).append({',
        '                {}.setdefault("outras_leituras", []).append({',
        "N8. a leitura descartada volta a desaparecer"),

    # ---------------------------------------------------------------
    # A QUARTA AUDITORIA. Um achado alto, e era meu: o peso por
    # servicos que eu acrescentei vazou para os eventos de preco.
    # ---------------------------------------------------------------

    Mutacao(
        "robo.py",
        '        if pa == pd or pa is None or pd is None:',
        '        if True:',
        "V1. o peso dos servicos volta a vazar para o preco"),

    Mutacao(
        "robo.py",
        '    ja_contado = {}',
        '    ja_contado = type("X", (dict,), {"setdefault": lambda s, *a: None})()',
        "V2. grade e voltou voltam a contar o mesmo movimento"),

    Mutacao(
        "robo.py",
        '            evento = (usadas or {}).get(_identidade(antes))',
        '            evento = None',
        "V3. a leitura descartada volta a nao chegar ao evento"),

    Mutacao(
        "robo.py",
        '    if antes is None and agora is None:\n'
        '        return True',
        '    if False:\n'
        '        return True',
        "V6. entrega nao lida nos dois dias volta a contar como movida"),

    # ---------------------------------------------------------------
    # A QUINTA AUDITORIA. Um achado alto: dos seis tipos de evento,
    # quatro ainda montavam a frase do preco na mao, e em dois deles
    # ela afirmava igualdade sobre um preco nao lido.
    # ---------------------------------------------------------------

    Mutacao(
        "robo.py",
        '        linhas.append("  %s, %s   %s"\n'
        '                      % (_texto_preco(m["antes"].get("preco_promocional"),',
        '        linhas.append("  mesmo pre\\u00e7o, %s   %s"\n'
        '                      % (0 * (_texto_preco(m["antes"].get("preco_promocional"),',
        "W1. composicao volta a afirmar mesmo preco sem ler o preco"),

    Mutacao(
        "robo.py",
        '            linhas.append("  %s" % _texto_preco(de, para, False))',
        '            linhas.append("  pelo mesmo pre\\u00e7o (%s)" % _reais(para))',
        "W1b. renomeada volta a afirmar mesmo preco sem ler o preco"),

    Mutacao(
        "robo.py",
        '        dono = ja_contado.get((v["operadora"], v["produto"], v["entrega"],\n'
        '                               v["antes"], v["agora"]))',
        '        dono = None',
        "W2. preco e voltou voltam a contar o mesmo reajuste"),

    Mutacao(
        "robo.py",
        '            if p not in dono["pracas"]:',
        '            if False:',
        "W2b. a praca do evento descartado volta a se perder"),

    Mutacao(
        "robo.py",
        '        if pa == pd or pa is None or pd is None:',
        '        if pa is not None and pa == pd:',
        "W3. composicao sem preco volta a pesar zero"),

    Mutacao(
        "robo.py",
        '            "versao_apenas": (pa is not None and pd is not None',
        '            "versao_apenas": (True or pa is not None and pd is not None',
        "W4. preco nao lido volta a entrar no balde da leitura"),

    Mutacao(
        "robo.py",
        '                         _pct(v["antes"], v["agora"]) or "(sem varia\u00e7\u00e3o apurada)",',
        '                         "%+.0f%%" % ((v["agora"] - v["antes"]) / float(v["antes"] or 1) * 100),',
        "W5. o voltou volta a calcular o proprio percentual"),

    Mutacao(
        "vigia.py",
        '    graves = sorted((t for g, t in lista if g == "grave"), key=_peso)',
        '    graves = [t for g, t in lista if g == "grave"]',
        "R5. a vaga do vigia volta a ser decidida pela ordem do codigo"),

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
