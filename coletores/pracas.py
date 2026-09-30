"""As 20 pracas do tracker.

CONGELADA. Alterar esta lista quebra a comparabilidade da serie inteira.
Praca acrescentada depois comeca do zero e nao tem passado.

Criterio (secao 4 da metodologia): todas as capitais de Sul, Sudeste e
Nordeste, mais quatro pracas que tapam buracos de cobertura:

  Brasilia e Manaus  - Centro-Oeste e Norte para as tres grandes
  Blumenau/Joinville - sem elas a Unifique nao tem onde ser medida.
                       Medido na base da Anatel (julho/2026): a Unifique
                       nao aparece nem entre as quatro maiores em
                       Florianopolis, mas e lider em Blumenau (38%) e
                       vice em Joinville (27%).
"""

PRACAS = [
    # Sudeste
    {"cidade": "Sao Paulo",      "uf": "SP", "regiao": "Sudeste",      "capital": True},
    {"cidade": "Rio de Janeiro", "uf": "RJ", "regiao": "Sudeste",      "capital": True},
    {"cidade": "Belo Horizonte", "uf": "MG", "regiao": "Sudeste",      "capital": True},
    {"cidade": "Vitoria",        "uf": "ES", "regiao": "Sudeste",      "capital": True},
    # Sul
    {"cidade": "Curitiba",       "uf": "PR", "regiao": "Sul",          "capital": True},
    {"cidade": "Florianopolis",  "uf": "SC", "regiao": "Sul",          "capital": True},
    {"cidade": "Porto Alegre",   "uf": "RS", "regiao": "Sul",          "capital": True},
    # Nordeste
    {"cidade": "Salvador",       "uf": "BA", "regiao": "Nordeste",     "capital": True},
    {"cidade": "Fortaleza",      "uf": "CE", "regiao": "Nordeste",     "capital": True},
    {"cidade": "Recife",         "uf": "PE", "regiao": "Nordeste",     "capital": True},
    {"cidade": "Sao Luis",       "uf": "MA", "regiao": "Nordeste",     "capital": True},
    {"cidade": "Natal",          "uf": "RN", "regiao": "Nordeste",     "capital": True},
    {"cidade": "Joao Pessoa",    "uf": "PB", "regiao": "Nordeste",     "capital": True},
    {"cidade": "Maceio",         "uf": "AL", "regiao": "Nordeste",     "capital": True},
    {"cidade": "Aracaju",        "uf": "SE", "regiao": "Nordeste",     "capital": True},
    {"cidade": "Teresina",       "uf": "PI", "regiao": "Nordeste",     "capital": True},
    # Complemento
    {"cidade": "Brasilia",       "uf": "DF", "regiao": "Centro-Oeste", "capital": True},
    {"cidade": "Manaus",         "uf": "AM", "regiao": "Norte",        "capital": True},
    {"cidade": "Blumenau",       "uf": "SC", "regiao": "Sul",          "capital": False},
    {"cidade": "Joinville",      "uf": "SC", "regiao": "Sul",          "capital": False},
]

# Pracas onde cada operadora regional opera. Fora daqui a coleta nem tenta:
# ausencia esperada nao e falha, e pedir o que nao existe so gera ruido.
COBERTURA = {
    "Vivo":     None,   # None = todas as 20
    "Claro":    None,
    "TIM":      None,
    "NuCel":    None,   # nacional, mas sem variacao por praca
    # Medido na API da Brisanet em 30/09/2026: das 9 pracas nordestinas
    # da cesta, ela atende 7. Salvador e Sao Luis nao estao na lista de
    # cidades ativas - ausencia esperada, nao falha de coleta.
    "Brisanet": {"Fortaleza", "Recife", "Natal", "Joao Pessoa", "Maceio",
                 "Aracaju", "Teresina"},
    # Medido no proprio seletor da Unifique em 30/09/2026: ela NAO atende
    # Florianopolis - o site nem lista a cidade. Confirma o que o dado da
    # Anatel ja sugeria, que ela e forte no interior e fraca na capital.
    # Curitiba entra com ressalva: a pagina carrega mas nao traz oferta de
    # fibra legivel, e o coletor avisa em vez de gravar vazio calado.
    "Unifique": {"Blumenau", "Joinville", "Porto Alegre", "Curitiba"},
}


def pracas_de(operadora):
    """As pracas que fazem sentido para esta operadora."""
    cobertura = COBERTURA.get(operadora)
    if cobertura is None:
        return list(PRACAS)
    return [p for p in PRACAS if p["cidade"] in cobertura]


def rotulo(p):
    return "%s/%s" % (p["cidade"], p["uf"])
