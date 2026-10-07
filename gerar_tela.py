"""Gera a tela do Price Tracker, no padrao visual do Dashboard TMT.

POR QUE FOI REFEITA. A primeira versao desenhava SVG na mao e o usuario
reprovou: "formatacao mal feita, fugindo do padrao Itau BBA", "grafico
sobrepostos e sem sentido", "um monte de tabelas enfadonhas com muita
informacao irrelevante". Medido no navegador, ele tinha razao em cada
ponto - e os defeitos eram estruturais, nao de acabamento:

  - os SVG tinham viewBox fixo e largura 100%, entao um renderizava a
    0,82x e o vizinho a 1,71x. Textos de tamanhos diferentes lado a lado,
    que e a origem da sensacao de remendo
  - fundo branco e preto azulado, quando a paleta pede bege quente com
    cartoes off-white, raio 12px e sombra suave
  - a tabela despejava 79 linhas e 7 colunas de uma vez
  - um painel aparecia vazio na maioria dos filtros

Agora segue o Dashboard TMT, que e a referencia aprovada: Chart.js 4.4.3
com maintainAspectRatio false (a escala passa a ser do container, nao do
viewBox), tokens de cor identicos, cartoes .bloco, eixo com rotulo
horizontal, linha suave com bolinha no ponto.

Uso:
  python gerar_tela.py --dados dados.json --saida tela.html
  python gerar_tela.py --dados dados.json --saida site/index.html --remoto URL
"""

import argparse
import io
import json
import sys
from datetime import datetime, timedelta, timezone

# Cores de serie, todas da paleta oficial Itau BBA.
CORES = {
    "Vivo": "#8258A0",       # roxo
    "TIM": "#5282D8",        # azul
    "Claro": "#FF5000",      # laranja principal
    "Brisanet": "#73C6A1",   # verde
    "Unifique": "#398478",   # verde-petroleo
    "NuCel": "#809BC4",      # azul acinzentado
    "Starlink": "#1D4080",   # azul escuro
}

MOLDE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Price Tracker TMT</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%2032%2032'%3E%3Crect%20width='32'%20height='32'%20rx='7'%20fill='%2324201B'/%3E%3Cpath%20d='M7%2022%20L13%2015%20L19%2018%20L25%209'%20stroke='%23FF5000'%20stroke-width='3'%20fill='none'%20stroke-linecap='round'%20stroke-linejoin='round'/%3E%3C/svg%3E">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
<style>
  :root{
    /* os mesmos tokens do Dashboard TMT - identidade clean, bege quente */
    --fonte: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    --laranja:#FF5000; --laranja-claro:#FFAE66;
    --preto:#24201B;            /* dark quente, para cabecalhos */
    --cinza-medio:#6E6E6E; --cinza:#A0A0A0; --cinza-claro:#CFCFCF;
    --cor-fundo:#F0EDE4;        /* bege quente */
    --cor-superficie:#FCFBF7;   /* cartoes, off-white quente */
    --cor-texto:#2B2621; --cor-texto-suave:#7C7468; --cor-borda:#E7E1D4;
    --positivo:#2E7D32; --negativo:#C62828;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--cor-fundo);color:var(--cor-texto);
       font-family:var(--fonte);font-size:14px;line-height:1.5}

  /* fixo no topo, como no Dashboard TMT: a tela tem tabela longa e rolar
     nao pode custar a referencia de onde se esta */
  header{background:var(--preto);border-bottom:3px solid var(--laranja);
         padding:9px 0 8px;position:sticky;top:0;z-index:200;
         box-shadow:0 2px 10px rgba(45,38,30,.10)}
  .dentro{max-width:1440px;margin:0 auto;padding:0 28px}
  header .dentro{display:flex;justify-content:space-between;align-items:flex-end;
                 gap:14px;flex-wrap:wrap}
  /* a barra laranja a esquerda do titulo e a assinatura do dashboard */
  header h1{margin:0;font-size:16.5px;font-weight:800;color:#fff;letter-spacing:-.2px;
    border-left:4px solid var(--laranja);padding-left:10px;line-height:1.2}
  header .sub{color:#B9B2A6;font-size:11px;margin-top:2px;padding-left:14px}
  .idioma{display:flex;gap:7px}
  .bandeira{display:flex;align-items:center;gap:5px;font:inherit;font-size:11px;
    font-weight:600;padding:3px 8px;cursor:pointer;border:1px solid #4A443C;
    border-radius:7px;background:transparent;color:#B9B2A6}
  .bandeira.on{background:rgba(255,80,0,.14);border-color:var(--laranja);color:#fff}
  .bandeira .flag{width:19px;height:13px;display:block;overflow:hidden;
    border-radius:2px;line-height:0}
  .bandeira .flag svg{width:19px;height:13px;display:block}

  /* grudam logo abaixo do cabecalho: trocar de praca ou de data no meio
     de uma tabela longa nao deve exigir voltar ao topo */
  /* grade regular: com flex-wrap cada campo achava seu lugar e sobravam
     orfaos em linhas diferentes, o que deixava o cabecalho irregular */
  .controles{background:var(--cor-superficie);border:1px solid var(--cor-borda);
    border-left:3px solid var(--laranja);border-radius:10px;padding:8px 14px 9px;
    margin:11px 0 10px;display:grid;gap:7px 14px;
    grid-template-columns:repeat(4, minmax(0, 1fr));align-items:end;
    position:sticky;top:calc(var(--topo-h, 86px) + var(--abas-h, 44px));z-index:30;
    box-shadow:0 2px 8px rgba(45,38,30,.06)}
  .controles .campo-largo{grid-column:1 / -1;border-top:1px solid var(--cor-borda);
    padding-top:7px;margin-top:0}
  .abas{position:sticky;top:calc(var(--topo-h, 86px) + var(--filtros-h, 92px));
        z-index:28;background:var(--cor-fundo)}
  .campo label{display:block;font-size:9px;text-transform:uppercase;
    letter-spacing:.6px;color:var(--cor-texto-suave);margin-bottom:2px;font-weight:700}
  .campo select{font:inherit;font-size:12.5px;padding:5px 9px;border-radius:7px;
    border:1px solid var(--cor-borda);background:#fff;color:var(--cor-texto);
    width:100%;cursor:pointer}
  .campo select:focus{outline:2px solid rgba(255,80,0,.35);outline-offset:1px}
  .chips{display:flex;gap:5px;flex-wrap:wrap}
  .chip{display:flex;align-items:center;gap:5px;font-size:11.5px;cursor:pointer;
    padding:3px 9px;border:1px solid var(--cor-borda);border-radius:20px;
    background:#fff;user-select:none;font-weight:600;
    transition:border-color .12s, opacity .12s}
  .chip:hover{border-color:var(--cinza)}
  .chip.off{opacity:.4}
  .chip .marcador{width:9px;height:9px;border-radius:50%}

  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
        gap:12px;margin-bottom:15px}
  .kpi{background:var(--cor-superficie);border:1px solid var(--cor-borda);
    border-radius:12px;padding:13px 16px;box-shadow:0 1px 2px rgba(45,38,30,.04)}
  .kpi .rot{font-size:10px;text-transform:uppercase;letter-spacing:.7px;
    color:var(--cor-texto-suave);font-weight:600}
  .kpi .val{font-size:26px;font-weight:700;margin-top:4px;letter-spacing:-.7px}
  .kpi .pe{font-size:11.5px;color:var(--cor-texto-suave);margin-top:1px}

  .bloco{background:var(--cor-superficie);border:1px solid var(--cor-borda);
    border-radius:12px;padding:17px 24px 19px;margin-bottom:16px;
    box-shadow:0 1px 3px rgba(45,38,30,.05)}
  /* titulo de secao: laranja, forte, com fio - como no dashboard */
  .secao{font-size:17px;font-weight:800;color:var(--laranja);margin:2px 0 10px;
    padding-bottom:5px;border-bottom:2px solid rgba(255,80,0,.22);
    letter-spacing:-.3px}
  .bloco h2{margin:0;font-size:15.5px;font-weight:700;letter-spacing:-.15px}
  td.vazia{color:var(--cinza)}
  td.sobe{color:var(--negativo);font-weight:600}
  td.desce{color:var(--positivo);font-weight:600}
  #matriz th.num{text-align:right}
  /* divisao entre operadoras, no padrao das tabelas do Dashboard TMT: as
     duas primeiras colunas ficam fixas ao rolar na horizontal, a troca de
     operadora ganha fio forte e cada bloco alterna de fundo */
  #matriz td.op-col{position:sticky;left:0;z-index:2;font-weight:700;
    min-width:108px;background:var(--cor-superficie)}
  #matriz td.degrau{position:sticky;left:108px;z-index:2;
    color:var(--cor-texto-suave);white-space:nowrap;
    background:var(--cor-superficie);border-right:1px solid var(--cor-borda)}
  #matriz thead th:nth-child(1){position:sticky;left:0;z-index:3}
  #matriz thead th:nth-child(2){position:sticky;left:108px;z-index:3}
  #matriz tr.bloco-alt td{background:rgba(45,38,30,.04)}
  #matriz tr.bloco-alt td.op-col, #matriz tr.bloco-alt td.degrau{background:#F3F0E9}
  #matriz tbody tr:hover td{background:#FFF6F2}
  #matriz tbody tr:hover td.op-col, #matriz tbody tr:hover td.degrau{background:#FFF0E8}
  #matriz td.trocou{color:var(--cor-texto);font-weight:600}
  .legenda-matriz{font-size:11px;color:var(--cor-texto-suave);margin-top:9px;
                  display:flex;gap:16px;flex-wrap:wrap}
  #matriz tr.troca-op td{border-top:2px solid var(--preto)}
  #matriz tbody tr:first-child td{border-top:none}
  .fonte{font-size:10.5px;color:var(--cor-texto-suave);margin-top:9px;
         padding-top:7px;border-top:1px solid var(--cor-borda)}
  .bloco .descricao{font-size:11.5px;color:var(--cor-texto-suave);margin:2px 0 12px}
  /* abas no topo, coladas ao cabecalho, como no Dashboard TMT */
  nav.abas{background:var(--cor-superficie);border-bottom:1px solid var(--cor-borda);
    position:sticky;top:var(--topo-h, 86px);z-index:150;
    box-shadow:0 1px 4px rgba(45,38,30,.05)}
  nav.abas ul{display:flex;list-style:none;gap:4px;margin:0;padding:0;
    overflow-x:auto;-webkit-overflow-scrolling:touch}
  nav.abas a{display:block;padding:8px 13px;text-decoration:none;
    color:var(--cor-texto-suave);font-weight:bold;font-size:13px;
    border-bottom:3px solid transparent;white-space:nowrap}
  nav.abas a:hover{color:var(--cor-texto)}
  nav.abas a.ativa{color:var(--laranja);border-bottom-color:var(--laranja)}
  #pg-ofertas{padding-top:4px} #pg-panorama{padding-top:4px}
  .bonus{display:block;font-size:10px;color:var(--cor-texto-suave);
         font-weight:600;margin-top:1px}
  .faixa{margin-bottom:20px}
  .faixa:last-child{margin-bottom:0}
  .faixa-rot{font-size:12px;font-weight:700;color:var(--laranja);
    text-transform:uppercase;letter-spacing:.6px;margin-bottom:7px}
  .grupo-op{background:var(--cor-fundo);font-weight:600}
  .grupo-op td{padding-top:9px;padding-bottom:7px}
  .destaque-linha td{background:#FFF4EC}
  .cabeca{display:flex;justify-content:space-between;align-items:flex-start;
          gap:14px;flex-wrap:wrap}
  .metricas{display:flex;gap:12px;flex:none;align-items:center}
  .metricas{flex-wrap:wrap}
  .metricas button{font:inherit;font-size:11.5px;padding:5px 11px;cursor:pointer;
    border:1px solid var(--cor-borda);border-radius:7px;background:#fff;
    color:var(--cor-texto-suave)}
  .metricas button.on{background:var(--preto);border-color:var(--preto);color:#fff}
  .grafico-wrap{position:relative;height:320px}
  .grafico-wrap.baixo{height:260px}
  .grafico-wrap.alto{height:450px}
  @media(max-width:860px){.grafico-wrap.alto{height:340px}}
  .legenda-ponto{display:inline-flex;align-items:center;gap:5px;font-size:11px;
                 color:var(--cor-texto-suave)}
  .legenda-ponto i{width:9px;height:9px;border-radius:50%;display:inline-block}
  .legenda-ponto i.vazado{background:transparent;border:2px solid var(--cinza)}
  .dupla{display:grid;grid-template-columns:1fr 1fr;gap:15px}

  table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}
  th{background:var(--preto);color:#fff;text-align:left;padding:9px 12px;
     font-weight:600;white-space:nowrap;font-size:11.5px;
     text-transform:uppercase;letter-spacing:.5px}
  th:first-child{border-radius:7px 0 0 0} th:last-child{border-radius:0 7px 0 0}
  td{border-bottom:1px solid var(--cor-borda);padding:8px 12px}
  tbody tr:hover td{background:rgba(255,80,0,.045)}
  tbody tr:last-child td{border-bottom:none}
  td.num{text-align:right;font-variant-numeric:tabular-nums}
  .tabela-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
  .op-tag{display:inline-flex;align-items:center;gap:6px;font-weight:600}
  .op-tag .marcador{width:8px;height:8px;border-radius:50%}
  .vazio{color:var(--cor-texto-suave);font-style:italic;padding:26px 0;
         text-align:center;font-size:13px}
  .nota{font-size:11.5px;color:var(--cor-texto-suave);margin-top:10px}
  footer{border-top:1px solid var(--cor-borda);margin-top:14px;padding:20px 0 34px;
         font-size:11.5px;color:var(--cor-texto-suave);text-align:center}

  @media(max-width:980px){
    .controles{grid-template-columns:repeat(2, minmax(0, 1fr))}
  }
  @media(max-width:860px){
    .dupla{grid-template-columns:1fr}
    /* dois KPIs por linha: em 375px, quatro cartoes em quatro linhas
       empurravam os graficos para fora da primeira tela */
    .kpis{grid-template-columns:1fr 1fr;gap:9px}
    .kpi{padding:11px 13px}
    .kpi .val{font-size:19px}
    .bloco{padding:13px 15px 15px}
    .dentro{padding:0 14px}
    .grafico-wrap{height:270px}
    /* no celular os quatro seletores viram uma coluna: dois lado a lado em
       375px deixam o texto da opcao cortado no meio */
    .controles{grid-template-columns:1fr;gap:10px;padding:12px 14px}
    .controles .campo-largo{padding-top:9px}
  }
</style>
</head>
<body>

<header>
  <div class="dentro">
    <div>
      <h1 data-t="titulo">Price Tracker TMT</h1>
      <div class="sub" id="sub"></div>
    </div>
    <div class="idioma">
      <button id="bt-pt" class="bandeira on" onclick="idioma('pt')" title="Português">
        <span class="flag"><svg viewBox='0 0 24 16' aria-hidden='true'><rect width='24' height='16' fill='#009C3B'/><polygon points='12,2 22,8 12,14 2,8' fill='#FFDF00'/><circle cx='12' cy='8' r='3.2' fill='#002776'/><path d='M9 7.5Q12 6.5 15 7.5' stroke='#fff' stroke-width='.4' fill='none'/></svg></span><span>PT</span></button>
      <button id="bt-en" class="bandeira" onclick="idioma('en')" title="English">
        <span class="flag"><svg viewBox='0 0 24 16' aria-hidden='true'><defs><clipPath id='ukc'><rect width='24' height='16'/></clipPath></defs><g clip-path='url(#ukc)'><rect width='24' height='16' fill='#012169'/><path d='M0 0 24 16M24 0 0 16' stroke='#fff' stroke-width='3.2'/><path d='M0 0 24 16M24 0 0 16' stroke='#C8102E' stroke-width='1.6'/><path d='M12 0V16M0 8H24' stroke='#fff' stroke-width='5'/><path d='M12 0V16M0 8H24' stroke='#C8102E' stroke-width='3'/></g></svg></span><span>EN</span></button>
    </div>
  </div>
</header>

<nav class="abas">
  <div class="dentro">
    <ul>
      <li><a href="#" class="ativa" id="ab-panorama" onclick="aba('panorama');return false" data-t="ab_pan">Panorama</a></li>
      <li><a href="#" id="ab-ofertas" onclick="aba('ofertas');return false" data-t="ab_of">Ofertas</a></li>
    </ul>
  </div>
</nav>

<div class="dentro">
  <div class="controles">
    <div class="campo">
      <label data-t="f_praca">Praça</label>
      <select id="f-praca" onchange="desenhar()"></select>
    </div>
    <div class="campo">
      <label data-t="f_produto">Produto</label>
      <select id="f-produto" onchange="desenhar()"></select>
    </div>
    <div class="campo">
      <label data-t="f_escopo">Planos</label>
      <select id="f-escopo" onchange="escopo(this.value)">
        <option value="todos" data-t="e_todos">Todos</option>
        <option value="entrada" data-t="e_entrada">Só o de entrada</option>
      </select>
    </div>
    <div class="campo">
      <label data-t="f_data">Data</label>
      <select id="f-data" onchange="desenhar()"></select>
    </div>
    <div class="campo campo-largo">
      <label data-t="f_operadora">Operadoras</label>
      <div class="chips" id="f-ops"></div>
    </div>
  </div>

  <div id="pg-panorama">
  <div class="secao" data-t="sec_pan">Panorama do mercado</div>
  <div class="bloco">
    <div class="cabeca">
      <div>
        <h2 data-t="q_t">Onde cada oferta está</h2>
        <p class="descricao" data-t="q_x"></p>
      </div>
      <div class="metricas">
        <span id="legenda-datas" style="display:flex;gap:12px"></span>
        <span style="display:flex;gap:5px">
          <button id="bt-r-todos" class="on" onclick="rotulos('todos')" data-t="r_todos">Nomes: todos</button>
          <button id="bt-r-entrada" onclick="rotulos('entrada')" data-t="r_entrada">Só entrada</button>
          <button id="bt-r-nenhum" onclick="rotulos('nenhum')" data-t="r_nenhum">Nenhum</button>
        </span>
      </div>
    </div>
    <div class="grafico-wrap alto"><canvas id="c-quadrante"></canvas></div>
    <div class="fonte" data-t="fonte"></div>
  </div>

  <div class="kpis" id="kpis"></div>

  <div class="bloco">
    <h2 data-t="g1_t">Preço de entrada, por operadora</h2>
    <p class="descricao" data-t="g1_x"></p>
    <div class="grafico-wrap"><canvas id="c-tempo"></canvas></div>
    <div class="nota" id="n-tempo"></div>
    <div class="fonte" data-t="fonte"></div>
  </div>

  <div class="bloco">
    <h2 data-t="g5_t">Preço por unidade entregue, dia a dia</h2>
    <p class="descricao" data-t="g5_x"></p>
    <div class="grafico-wrap"><canvas id="c-tempo-unit"></canvas></div>
    <div class="fonte" data-t="fonte"></div>
  </div>

  <div class="dupla">
    <div class="bloco">
      <h2 data-t="g2_t">Quanto custa o que entrega</h2>
      <p class="descricao" data-t="g2_x"></p>
      <div class="grafico-wrap baixo"><canvas id="c-dispersao"></canvas></div>
    </div>
    <div class="bloco">
      <h2 data-t="g3_t">Preço por unidade entregue</h2>
      <p class="descricao" data-t="g3_x"></p>
      <div class="grafico-wrap baixo"><canvas id="c-unitario"></canvas></div>
    </div>
  </div>

  <div class="bloco">
    <div class="cabeca">
      <div>
        <h2 data-t="mat_t">Preço por degrau, dia a dia</h2>
        <p class="descricao" data-t="mat_x"></p>
      </div>
      <div class="metricas">
        <button id="bt-mes" class="on" onclick="metrica('mes')">R$/mês</button>
        <button id="bt-gb" onclick="metrica('unidade')">R$/GB</button>
      </div>
    </div>
    <div class="tabela-wrap" id="matriz"></div>
    <div class="fonte" data-t="fonte"></div>
  </div>

    </div>

  <div id="pg-ofertas" hidden>
    <div class="secao" data-t="sec_of">As ofertas de hoje</div>
    <div class="bloco">
      <div class="cabeca">
        <div>
          <h2 data-t="of_t">Todas as ofertas, por operadora</h2>
          <p class="descricao" data-t="of_x"></p>
        </div>
        <div class="campo" style="flex:none">
          <label data-t="f_player">Operadora</label>
          <select id="f-player" onchange="desenhar()"></select>
        </div>
      </div>
      <div class="tabela-wrap" id="t-player"></div>
      <div class="nota" id="n-player"></div>
      <div class="fonte" data-t="fonte"></div>
    </div>

    <div class="bloco">
      <h2 data-t="cmp_t">Comparação entre operadoras</h2>
      <p class="descricao" data-t="cmp_x"></p>
      <div class="tabela-wrap" id="t-comparacao"></div>
      <div class="fonte" data-t="fonte"></div>
    </div>

    <div class="bloco">
      <h2 data-t="fx_t">Comparação por faixa de entrega</h2>
      <p class="descricao" data-t="fx_x"></p>
      <div id="t-faixas"></div>
      <div class="fonte" data-t="fonte"></div>
    </div>
  </div>
</div>

<footer>
  <div class="dentro" data-t="rodape"></div>
</footer>

<script>
let DADOS = __DADOS__;
// Vazia no modo embutido. No modo remoto a pagina busca o JSON do Supabase
// Storage, e ai a coleta do dia aparece sem republicar nada.
const FONTE = "__FONTE__";
const CORES = __CORES__;
const GERADO = "__GERADO__";

const T = {
  pt:{titulo:"Price Tracker TMT", f_praca:"Praça", f_produto:"Produto",
      f_operadora:"Operadoras",
      leitura_t:"O que mudou",
      l_preco:"mudou o preço de entrada de", l_em:"em",
      l_trocou:"trocou a oferta de entrada:", l_mesmo:"pelo mesmo preço de",
      l_apareceu:"aparece nesta praça com", l_saiu:"não aparece mais nesta praça hoje",
      l_spread:"Da ponta à ponta:", l_a:"a", l_acima:"de diferença",
      l_nada:"Nenhuma mudança de preço de entrada contra o dia anterior, nas operadoras desta praça.",
      fonte:"Na coluna Entrega, o número pequeno abaixo separa o que o contrato garante do que é bônus (ex.: 50+10 significa 50 GB fixos mais 10 de bônus, que pode expirar). Fonte: vitrines públicas, coletadas uma vez por dia; preço cheio, sem desconto condicionado.",
      d_bonus:"{f} GB garantidos no contrato + {b} GB de bônus, que pode expirar",
      ab_pan:"Panorama", ab_of:"Ofertas",
      sec_pan:"Panorama do mercado", sec_of:"As ofertas de hoje",
      of_t:"Todas as ofertas, por operadora",
      of_x:"A lista completa do dia, agrupada por operadora e ordenada do mais barato ao mais caro. Use o seletor para ver uma operadora de cada vez.",
      fx_t:"Comparação por faixa de entrega",
      fx_x:"A escada cortada em três faixas. Dentro de cada uma, a oferta mais barata de cada operadora — porque quem é barato na porta nem sempre é barato no degrau de cima, que é onde está a receita.",
      fx_baixa:"Faixa de entrada", fx_media:"Faixa intermediária", fx_alta:"Faixa alta",
      cmp_t:"Comparação entre operadoras",
      cmp_x:"A oferta de entrada de cada operadora, lado a lado. A linha destacada é a mais barata por unidade entregue — que nem sempre é a mais barata em reais.",
      f_player:"Operadora", todas:"Todas", oferta:"oferta", ofertas:"ofertas",
      n_player:"{n} ofertas capturadas em {d}, em {p}.",
      col_player:["Oferta","Entrega","Preço","R$/un.","Serviços inclusos"],
      col_cmp:["Operadora","Oferta de entrada","Entrega","Preço","R$/un.","Serviços inclusos"],
      dicas_col:{"Entrega":"O que a oferta entrega. O número pequeno separa o que o contrato garante do que é bônus",
                 "Serviços inclusos":"O que acompanha a conectividade, do plano sem nada ao que inclui TV"},
      // Exemplos reais em vez de jargão: "apps de catálogo" não diz nada a
      // quem não montou a escala. Os nomes citados são os que de fato
      // aparecem nas vitrines.
      bundles:["Só internet e ligações",
               "Apps menores (Skeelo, McAfee, GoRead)",
               "Um streaming (Netflix, Amazon ou Disney+)",
               "Vários streamings juntos",
               "TV por assinatura inclusa"],
      f_data:"Data", f_contra:"Comparar com", f_escopo:"Quais planos",
      e_todos:"Todos os planos", e_entrada:"Só o mais barato de cada operadora",
      produtos:{controle:"Controle", movel:"Pós-pago", fibra:"Fibra",
                combo:"Combo (fibra + móvel)", prepago:"Pré-pago",
                satelite:"Satélite"},
      q_t:"Onde cada oferta está",
      r_entrada:"Só entrada", r_todos:"Nomes: todos", r_nenhum:"Nenhum",
      q_x:"A disposição do dia: cada bolinha é uma oferta, à direita entrega mais e acima custa mais. Para ver o movimento entre datas, use a matriz e o gráfico de evolução mais abaixo.",
      g1_t:"Preço de entrada, por operadora (R$/mês)",
      g1_x:"O plano mais barato de cada operadora, dia a dia. É a linha que responde se houve repasse. Linha tracejada significa que ela coincide com outra — o preço é praticamente o mesmo.",
      sobre:"praticamente sobre a",
      g5_t:"Preço por unidade entregue, dia a dia",
      g5_x:"A mesma série de cima, dividida pelo que cada plano entrega. É aqui que aparece o que o preço nominal esconde: quem manteve o preço e aumentou a franquia fica reto lá em cima e desce aqui.",
      g2_t:"Quanto custa o que entrega (R$/mês × entrega)",
      g2_x:"Cada ponto é uma oferta de hoje. À direita entrega mais; acima custa mais.",
      g3_t:"Quem entrega mais barato hoje",
      g3_x:"O preço de entrada de hoje dividido pelo que ele entrega, do mais barato ao mais caro. Normaliza ofertas de franquia diferente — R$ 59 com 45 GB não é o mesmo que R$ 59 com 40 GB.",
      mat_t:"Preço por degrau, dia a dia", mes:"mês",
      mat_x:"Uma linha por degrau de cada operadora, uma coluna por dia. ▲▼ é o preço da mesma oferta mudando; ◆ é outra oferta assumindo o degrau, que não é mudança de preço. Dentro do degrau vale o menor nível de bundle, e só então o menor preço.",
      m_trocou:"Outra oferta assumiu o degrau",
      m_grade:"A operadora manteve os preços e mudou as franquias — a grade inteira andou, não é mudança de preço",
      tab_t:"As ofertas de entrada de cada operadora",
      tab_x:"Uma linha por operadora: a oferta mais barata de hoje, com o que ela entrega e o que o contrato garante.",
      rodape:"Documento de trabalho interno. Preços coletados das vitrines públicas das operadoras, uma vez por dia.",
      kpi_ops:"Operadoras na praça", kpi_barato:"Mais barato hoje",
      kpi_mediana:"Mediana de entrada", kpi_serie:"Série",
      kpi_dias:"{n} dias", kpi_desde:"desde {d}",
      serie_jovem:"A série tem {n} dia(s). A linha se forma conforme os dias passam.",
      parcial:"Atenção: {d} tem {a} operadora(s) contra {b} no dia anterior — a coleta desse dia está incompleta ou ainda rodando. Os números de hoje podem subir.",
      sem_dado:"Nenhuma oferta capturada com este filtro.",
      sem_praca:"Esta operadora não vende este produto nesta praça — célula vazia, nunca zero.",
      de:"de", preco:"Preço", entrega:"Entrega", contrato:"Contrato",
      col:["Operadora","Oferta","Entrega","Contrato","Preço"],
      mostrando:"Mostrando {a} de {b} ofertas capturadas nesta praça: a mais barata de cada operadora.",
      mbps:"Mbps", gb:"GB"},
  en:{titulo:"TMT Price Tracker", f_praca:"City", f_produto:"Product",
      f_operadora:"Carriers",
      leitura_t:"What changed",
      l_preco:"changed its entry price from", l_em:"on",
      l_trocou:"switched its entry offer:", l_mesmo:"at the same price of",
      l_apareceu:"shows up in this city at", l_saiu:"is not in this city today",
      l_spread:"End to end:", l_a:"at", l_acima:"apart",
      l_nada:"No change in entry price against the previous day, among this city's carriers.",
      fonte:"In the Delivers column, the small figure below splits what the contract guarantees from bonus data (e.g. 50+10 means 50 GB fixed plus 10 GB of bonus, which can expire). Source: public websites, collected once a day; list price, before conditional discounts.",
      d_bonus:"{f} GB guaranteed in the contract + {b} GB of bonus, which can expire",
      ab_pan:"Overview", ab_of:"Offers",
      sec_pan:"Market overview", sec_of:"Today's offers",
      of_t:"All offers, by carrier",
      of_x:"The full list for the day, grouped by carrier and sorted cheapest first. Use the selector to see one carrier at a time.",
      fx_t:"Comparison by delivery tier",
      fx_x:"The ladder cut into three tiers. Within each one, the cheapest offer of each carrier — because whoever is cheap at the door is not always cheap on the next step, which is where the revenue sits.",
      fx_baixa:"Entry tier", fx_media:"Mid tier", fx_alta:"Top tier",
      cmp_t:"Carrier comparison",
      cmp_x:"Each carrier's entry offer, side by side. The highlighted row is the cheapest per unit delivered — which is not always the cheapest in reais.",
      f_player:"Carrier", todas:"All", oferta:"offer", ofertas:"offers",
      n_player:"{n} offers captured on {d}, in {p}.",
      col_player:["Offer","Delivers","Price","R$/unit","Included services"],
      col_cmp:["Carrier","Entry offer","Delivers","Price","R$/unit","Included services"],
      dicas_col:{"Delivers":"What the offer delivers. The small figure splits contract-guaranteed from bonus",
                 "Included services":"Bundle level, from bare connectivity to TV included"},
      bundles:["Data and calls only",
               "Minor apps (Skeelo, McAfee, GoRead)",
               "One streaming (Netflix, Amazon or Disney+)",
               "Several streamings together",
               "Pay TV included"],
      f_data:"Date", f_contra:"Compare with", f_escopo:"Which plans",
      e_todos:"All plans", e_entrada:"Cheapest of each carrier only",
      produtos:{controle:"Hybrid (Controle)", movel:"Postpaid", fibra:"Fibre",
                combo:"Bundle (fibre + mobile)", prepago:"Prepaid",
                satelite:"Satellite"},
      q_t:"Where each offer sits",
      r_entrada:"Entry only", r_todos:"Labels: all", r_nenhum:"None",
      q_x:"Today's layout: each dot is an offer, further right delivers more and higher up costs more. To see movement between dates, use the matrix and the evolution chart below.",
      g1_t:"Entry price, by carrier (R$/month)",
      g1_x:"The cheapest plan of each carrier, day by day. This is the line that answers whether prices were raised. A dashed line means it coincides with another — the price is practically the same.",
      sobre:"practically on top of",
      g5_t:"Price per unit delivered, day by day",
      g5_x:"The same series above, divided by what each plan delivers. This is where what the nominal price hides shows up: whoever kept the price and raised the allowance stays flat up there and drops here.",
      g2_t:"What you pay for what you get (R$/month × delivery)",
      g2_x:"Each dot is an offer from today. Further right delivers more; higher up costs more.",
      g3_t:"Cheapest per unit today",
      g3_x:"Today's entry price divided by what it delivers, cheapest first. Normalises offers with different allowances — R$ 59 with 45 GB is not the same as R$ 59 with 40 GB.",
      mat_t:"Price by tier, day by day", mes:"month",
      mat_x:"One row per tier of each carrier, one column per day. ▲▼ is the same offer changing price; ◆ is a different offer taking over the tier, which is not a price change. Within a tier the lowest bundle level wins, then the lowest price.",
      m_trocou:"A different offer took over this tier",
      m_grade:"The carrier kept its prices and changed the allowances — the whole grid shifted, this is not a price change",
      tab_t:"Each carrier's entry offer",
      tab_x:"One row per carrier: today's cheapest offer, what it delivers and what the contract guarantees.",
      rodape:"Internal working document. Prices collected once a day from carriers' public websites.",
      kpi_ops:"Carriers in this city", kpi_barato:"Cheapest today",
      kpi_mediana:"Median entry price", kpi_serie:"Series",
      kpi_dias:"{n} days", kpi_desde:"since {d}",
      serie_jovem:"The series has {n} day(s). The line builds as days go by.",
      parcial:"Heads up: {d} has {a} carrier(s) against {b} the day before — that day's collection is incomplete or still running. Today's figures may rise.",
      sem_dado:"No offer captured with this filter.",
      sem_praca:"This carrier does not sell this product here — blank cell, never zero.",
      de:"of", preco:"Price", entrega:"Delivers", contrato:"Contract",
      col:["Carrier","Offer","Delivers","Contract","Price"],
      mostrando:"Showing {a} of {b} offers captured in this city: the cheapest per carrier.",
      mbps:"Mbps", gb:"GB"}
};
let lang = "pt";
let desligadas = new Set();
let graficos = {};
// "mes" = o preco que a operadora cobra. "unidade" = o mesmo preco dividido
// pelo que ele entrega, que e a metrica que a XP usa em todo o tracker
// para comparar operadoras com franquias diferentes.
let metricaAtual = "mes";
// "todos" mostra o portfolio inteiro; "entrada" so o plano mais barato de
// cada operadora, que e a espinha dorsal da serie (decisao 7)
let escopoAtual = "todos";
// Rotular as 21 ofertas de uma praca cobre os pontos vizinhos - o
// display:auto do plugin so evita colisao entre textos, nao entre texto e
// ponto. O padrao passa a ser rotular so a oferta de entrada de cada
// operadora: da referencia sem virar mancha, e o resto sai no hover.
let rotulosAtual = "todos";

function rotulos(v){
  rotulosAtual = v;
  for (const k of ["entrada", "todos", "nenhum"]) {
    document.getElementById("bt-r-" + k).className = (k === v ? "on" : "");
  }
  grafQuadrante();
}

function aba(qual){
  const pan = qual === "panorama";
  document.getElementById("pg-panorama").hidden = !pan;
  document.getElementById("pg-ofertas").hidden = pan;
  document.getElementById("ab-panorama").className = pan ? "ativa" : "";
  document.getElementById("ab-ofertas").className = pan ? "" : "ativa";
  desenhar();
}

// O nivel de bundle vira texto: e o que a tabela chama de "vantagens".
// Sai da decisao 10 da metodologia, que e a mesma regra usada para
// comparar nivel com nivel.
function vantagem(o){
  const n = o.nivel_bundle;
  const t_ = T[lang];
  if (n == null) return "—";
  return (t_.bundles[n] || "—");
}

function escopo(v){
  escopoAtual = v;
  desenhar();
}

function metrica(m){
  metricaAtual = m;
  document.getElementById("bt-mes").className = m === "mes" ? "on" : "";
  document.getElementById("bt-gb").className = m === "unidade" ? "on" : "";
  matriz();
}

let OPERADORAS = [], PRACAS = [], PRODUTOS = [], DIAS = [];
const diaDe = o => o.data_captura || (o.capturado_em||"").slice(0,10);

// A NuCel foi gravada como "movel" ate 06/10/2026 e passou a "controle"
// no coletor. O produto sempre foi o mesmo - plano hibrido, com franquia
// e sem fatura aberta - e so a etiqueta estava errada, entao a correcao
// vale para tras tambem. Sem isto a serie dela partiria em duas no dia da
// mudanca, e ela sumiria da comparacao de controle no historico.
function corrigirHistorico(){
  for (const o of DADOS) {
    if (o.operadora === "NuCel" && o.produto === "movel") o.produto = "controle";
  }
}

function derivar(){
  corrigirHistorico();
  OPERADORAS = [...new Set(DADOS.map(o=>o.operadora))].sort();
  PRACAS = [...new Set(DADOS.map(o=>o.praca))].sort();
  PRODUTOS = [...new Set(DADOS.map(o=>o.produto))].sort();
  DIAS = [...new Set(DADOS.map(diaDe))].filter(Boolean).sort();
}

function t(k){ return T[lang][k]; }

// O banco guarda "movel", que no nosso esquema e o pos-pago PURO - mas o
// rotulo fazia pensar em tudo que e celular, sendo que controle e pre-pago
// tambem sao moveis. A tela mostra o nome de mercado; o banco nao muda.
// A coluna de preco unitario diz a unidade de verdade - R$/GB no movel,
// R$/Mbps na fixa - em vez de "R$/un.", que nao diz nada.
// Uma celula para a entrega, com o bonus explicado na dica. Duas colunas
// - anunciado e garantido - obrigavam o leitor a montar a conta sozinho e
// confundiam mais do que informavam.
function celulaEntrega(o){
  const e = entregaDe(o), contr = o.franquia_contratual_gb;
  if (e.v == null) return `<td class="num">—</td>`;
  const txt = e.v + " " + e.u;
  // so faz sentido comparar quando a unidade e a mesma (GB com GB)
  if (contr == null || e.u !== t("gb") || contr >= e.v) {
    return `<td class="num">${txt}</td>`;
  }
  const bonus = e.v - contr;
  return `<td class="num" title="${t("d_bonus")
    .replace("{f}", contr).replace("{b}", bonus)}">${txt}`
    + `<span class="bonus">${contr}+${bonus}</span></td>`;
}

function colunas(chave, ofertas){
  const c = t(chave).slice();
  // a dica no cabecalho explica a diferenca sem ocupar linha na tabela
  const dicas = t("dicas_col") || {};
  for (let i = 0; i < c.length; i++) {
    if (dicas[c[i]]) c[i] = `<span title="${dicas[c[i]]}">${c[i]}</span>`;
  }
  const u = ofertas && ofertas.length ? entregaDe(ofertas[0]).u : "";
  const i = c.findIndex(x => x.indexOf("R$/") === 0);
  if (i >= 0 && u) c[i] = "R$/" + u;
  return c;
}

function nomeProduto(p){
  return (T[lang].produtos || {})[p] || p;
}
function num(v){ return v==null?null:Number(v); }
function reais(v){
  return v==null ? "—" : "R$ " + Number(v).toLocaleString("pt-BR",
    {minimumFractionDigits:2, maximumFractionDigits:2});
}
function dataCurta(d){ return d ? d.slice(8,10)+"/"+d.slice(5,7) : "—"; }

// Entrega: fibra e combo medem em Mbps, movel em GB. Misturar as duas
// unidades num eixo so compararia coisas diferentes.
function entregaDe(o){
  const m = num(o.degrau_mbps), g = num(o.franquia_anunciada_gb);
  if (m) return {v:m, u:t("mbps")};
  if (g) return {v:g, u:t("gb")};
  return {v:null, u:""};
}
function precoDe(o){ return num(o.preco_promocional); }

function idioma(l){
  lang = l;
  document.getElementById("bt-pt").className = "bandeira" + (l==="pt"?" on":"");
  document.getElementById("bt-en").className = "bandeira" + (l==="en"?" on":"");
  document.documentElement.lang = l==="pt"?"pt-BR":"en";
  document.querySelectorAll("[data-t]").forEach(e=>{
    const k = e.dataset.t; if (T[l][k]) e.textContent = T[l][k];
  });
  // os nomes de produto também mudam de idioma
  const fd = document.getElementById("f-produto");
  if (fd && fd.options.length) {
    const atual = fd.value;
    fd.innerHTML = PRODUTOS.map(p=>`<option value="${p}">${nomeProduto(p)}</option>`).join("");
    fd.value = atual;
  }
  desenhar();
}

function montarFiltros(){
  const fp = document.getElementById("f-praca");
  fp.innerHTML = PRACAS.map(p=>`<option value="${p}">${p}</option>`).join("");
  if (PRACAS.includes("Sao Paulo/SP")) fp.value = "Sao Paulo/SP";   // decisao 22
  const fd = document.getElementById("f-produto");
  fd.innerHTML = PRODUTOS.map(p=>`<option value="${p}">${nomeProduto(p)}</option>`).join("");
  if (PRODUTOS.includes("controle")) fd.value = "controle";          // decisao 2
  const fdata = document.getElementById("f-data");
  fdata.innerHTML = DIAS.slice().reverse()
    .map(d=>`<option value="${d}">${dataCurta(d)}</option>`).join("");
  const fplayer = document.getElementById("f-player");
  fplayer.innerHTML = `<option value="">${t("todas")}</option>`
    + OPERADORAS.map(o=>`<option value="${o}">${o}</option>`).join("");

  document.getElementById("f-ops").innerHTML = OPERADORAS.map(o=>
    `<span class="chip" id="chip-${o}" onclick="alternar('${o}')">
       <span class="marcador" style="background:${CORES[o]||"#999"}"></span>${o}</span>`).join("");
}
function alternar(o){
  desligadas.has(o) ? desligadas.delete(o) : desligadas.add(o);
  document.getElementById("chip-"+o).className = "chip" + (desligadas.has(o)?" off":"");
  desenhar();
}

function filtro(){
  return {
    praca: document.getElementById("f-praca").value,
    produto: document.getElementById("f-produto").value,
  };
}
// NuCel e Starlink vendem no pais inteiro e sao gravadas em "Brasil/BR".
// Filtrar so pela praca escolhida as fazia sumir de Sao Paulo, como se
// nao vendessem la - o oposto da verdade.
const PRACA_NACIONAL = "Brasil/BR";

function doFiltro(dia){
  const f = filtro();
  const base = DADOS.filter(o =>
    (o.praca === f.praca || o.praca === PRACA_NACIONAL)
    && o.produto === f.produto
    && !desligadas.has(o.operadora)
    && (!dia || diaDe(o) === dia));
  if (escopoAtual !== "entrada") return base;
  // so a oferta de entrada de cada operadora
  const por = {};
  for (const o of base) {
    const p = precoDe(o);
    if (p == null) continue;
    const k = o.operadora + "|" + diaDe(o);
    if (!por[k] || p < precoDe(por[k])) por[k] = o;
  }
  return Object.values(por);
}

// A oferta de entrada: a mais barata da operadora naquele dia. E a
// espinha dorsal da serie (decisao 7), e o que torna operadoras com
// portfolios diferentes comparaveis entre si.
function entradaPorOperadora(dia){
  const por = {};
  for (const o of doFiltro(dia)) {
    const p = precoDe(o);
    if (p == null) continue;
    const atual = por[o.operadora];
    if (!atual || p < precoDe(atual)) por[o.operadora] = o;
  }
  return por;
}

// O mesmo criterio da entrada, aplicado degrau a degrau: dentro de cada
// par (operadora, degrau), o menor preco do dia. Varias ofertas dividem o
// mesmo degrau - "Vivo Controle" e "Vivo Controle Amazon" sao ambas 45 GB
// - e comparar a mais barata de cada uma mantem a serie estavel quando a
// operadora acrescenta ou tira uma variante.
function nivel(o){
  const n = o.nivel_bundle;
  return n == null ? 9 : Number(n);
}
function menor(a, b){
  const na = nivel(a), nb = nivel(b);
  if (na !== nb) return na < nb;
  return precoDe(a) < precoDe(b);
}

function porDegrau(dia){
  const por = {};
  for (const o of doFiltro(dia)) {
    const p = precoDe(o), e = entregaDe(o);
    if (p == null || e.v == null) continue;
    const k = o.operadora + "|" + e.v;
    const atual = por[k];
    // Decisao 10: dentro do degrau vale o MENOR NIVEL DE BUNDLE, e so
    // entao o menor preco. Pelo preco puro, "Fibra + TV por assinatura"
    // e "Vivo Fibra" disputavam o mesmo degrau de 600 Mbps - comparar
    // fibra pura com fibra mais TV e o que a metodologia proibe.
    if (!atual || menor(o, atual.oferta)) {
      por[k] = {operadora:o.operadora, degrau:e.v, unidade:e.u, oferta:o};
    }
  }
  return por;
}

const EIXO = {
  grade: "rgba(0,0,0,0.07)",
  borda: "#24201B",
};

// Legenda com bolinha da cor da serie. Sem ela o leitor ve tres linhas
// coloridas e nenhuma pista de quem e quem - foi o que o usuario apontou.
// "#8258A0" -> "rgba(130,88,160,.18)". Serve para esmaecer as series que
// nao estao sendo apontadas na legenda.
function comAlfa(cor, alfa){
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(cor || "");
  if (!m) return cor;
  return "rgba(" + parseInt(m[1], 16) + "," + parseInt(m[2], 16) + ","
         + parseInt(m[3], 16) + "," + alfa + ")";
}

// Apontar um nome na legenda realca a linha dele e apaga as outras. Com
// quatro series quase coladas - Vivo e TIM diferem um centavo - achar a
// sua no meio do emaranhado era trabalho de quem le.
function realcar(chart, alvo){
  chart.data.datasets.forEach((d, i) => {
    if (d._corBase === undefined) {
      d._corBase = d.borderColor;
      d._fundoBase = d.backgroundColor;
      d._larguraBase = d.borderWidth;
      d._raioBase = d.pointRadius;
    }
    const neutro = alvo == null;
    const este = i === alvo;
    const apagar = !neutro && !este;
    d.borderColor = apagar ? comAlfa(d._corBase, 0.16) : d._corBase;
    d.backgroundColor = apagar
      ? comAlfa(typeof d._fundoBase === "string" ? d._fundoBase : d._corBase, 0.16)
      : d._fundoBase;
    d.borderWidth = este ? (d._larguraBase || 2) + 1.6 : d._larguraBase;
    if (d._raioBase !== undefined && d._raioBase !== null) {
      d.pointRadius = este ? d._raioBase + 1.5 : d._raioBase;
    }
    d.order = este ? -1 : 0;     // a realcada vai para a frente
  });
  chart.update("none");
}

function legenda(extra){
  return Object.assign({
    display:true, position:"bottom", align:"center",
    labels:{usePointStyle:true, pointStyle:"circle", boxWidth:7, boxHeight:7,
            padding:14, color:"#2B2621", font:{size:11.5, weight:"600"}},
    onHover:(e, item, leg) => {
      e.native.target.style.cursor = "pointer";
      realcar(leg.chart, item.datasetIndex);
    },
    onLeave:(e, item, leg) => {
      e.native.target.style.cursor = "default";
      realcar(leg.chart, null);
    },
  }, extra || {});
}

// A faixa de um eixo de valor, com piso. Comecar em zero deixa metade do
// quadro vazio e espreme os pontos no topo - a ponto de tres planos a
// 58,99, 59,00 e 59,90 cairem no mesmo pixel e os nomes sumirem por
// colisao. Colar na faixa real tem o defeito oposto: a mesma diferenca de
// centavos vira a tela inteira. A saida e uma faixa minima proporcional,
// 15% do maior valor.
// Duas operadoras com o mesmo preco desenham uma linha por cima da outra
// e some uma do grafico - a Vivo a R$ 59,00 ficou escondida atras do TIM
// a R$ 58,99, um centavo de diferenca. Deslocar a linha seria mentir sobre
// o valor; o que se faz e marcar a de cima com tracejado, para a
// coincidencia aparecer como coincidencia.
function marcarSobrepostas(series, tolerancia){
  for (let i = 1; i < series.length; i++) {
    for (let j = 0; j < i; j++) {
      const a = series[i].data, b = series[j].data;
      let juntas = 0, comparaveis = 0;
      for (let k = 0; k < a.length; k++) {
        if (a[k] == null || b[k] == null) continue;
        comparaveis++;
        if (Math.abs(a[k] - b[k]) <= tolerancia) juntas++;
      }
      // precisa coincidir em tudo que da para comparar, e nao so num dia
      if (comparaveis && juntas === comparaveis) {
        series[i].borderDash = [6, 4];
        series[i].borderWidth = 2.5;
        series[i].sobrepoe = series[j].label;
        break;
      }
    }
  }
  return series;
}

function faixaEixo(valores){
  const vs = valores.filter(v => v != null && isFinite(v));
  if (!vs.length) return {};
  const lo = Math.min(...vs), hi = Math.max(...vs);
  const vao = Math.max(hi - lo, hi * 0.15) || 1;
  const centro = (lo + hi) / 2;
  return {min: Math.max(0, centro - vao * 0.8), max: centro + vao * 0.8};
}

function eixos(rotuloY){
  return {
    x: { grid:{display:false}, border:{display:true, color:EIXO.borda, width:1},
         ticks:{maxRotation:0, autoSkip:true, maxTicksLimit:10,
                color:"#7C7468", font:{size:11}} },
    // Comeca no zero. Tres planos entre R$ 58,99 e R$ 59,90 abriam um eixo
    // de um real, e a diferenca de centavos ocupava a tela inteira como se
    // fossem precos distantes. Sao quase iguais, e o grafico tem de dizer isso.
    y: { beginAtZero:true,
         grid:{display:true, color:EIXO.grade, drawTicks:false},
         border:{display:true, color:EIXO.borda, width:1},
         ticks:{padding:8, color:"#7C7468", font:{size:11},
                callback:v=>rotuloY?rotuloY(v):v} },
  };
}

function trocar(id, config){
  if (graficos[id]) graficos[id].destroy();
  graficos[id] = new Chart(document.getElementById(id), config);
}

function grafTempo(){
  const nota = document.getElementById("n-tempo");
  const parcial = diaParcial();
  nota.textContent = parcial
    ? t("parcial").replace("{d}", dataCurta(parcial.dia))
        .replace("{a}", parcial.tem).replace("{b}", parcial.tinha)
    : (DIAS.length < 2 ? t("serie_jovem").replace("{n}", DIAS.length) : "");

  const series = OPERADORAS.filter(o=>!desligadas.has(o)).map(op=>{
    const pontos = DIAS.map(d=>{
      const e = entradaPorOperadora(d)[op];
      return e ? precoDe(e) : null;
    });
    return {label:op, data:pontos, borderColor:CORES[op]||"#999",
            backgroundColor:CORES[op]||"#999",
            // linha suave com bolinha no ponto, como o resto do dashboard
            tension:0.3, pointRadius:2, pointHoverRadius:4, borderWidth:2,
            spanGaps:true};
  }).filter(s=>s.data.some(v=>v!=null));

  if (!series.length) {
    if (graficos["c-tempo"]) graficos["c-tempo"].destroy(), delete graficos["c-tempo"];
    nota.textContent = t("sem_dado");
    return;
  }
  // tolerancia de meio por cento da faixa: abaixo disso as linhas caem no
  // mesmo pixel e uma esconde a outra
  const faixaT = faixaEixo(series.flatMap(s2=>s2.data));
  marcarSobrepostas(series, ((faixaT.max||0) - (faixaT.min||0)) * 0.005);

  trocar("c-tempo", {
    type:"line",
    data:{labels:DIAS.map(dataCurta), datasets:series},
    options:{responsive:true, maintainAspectRatio:false,
      interaction:{mode:"index", intersect:false},
      plugins:{legend:legenda(),
        tooltip:{callbacks:{label:c=>c.parsed.y==null?null:
          c.dataset.label+": "+reais(c.parsed.y)
          + (c.dataset.sobrepoe ? " (" + t("sobre") + " " + c.dataset.sobrepoe + ")" : "")}}},
      scales:{x:eixos().x,
              y:Object.assign(eixos(v=>reais(v).replace("R$ ","")).y,
                              {beginAtZero:false},
                              faixaEixo(series.flatMap(s2=>s2.data)))}},
  });
}

// O mesmo historico, em preco por unidade entregue. Separa o que o preco
// nominal esconde: a NuCel manteve os tres precos em 06/10 e subiu a
// franquia, entao a linha dela fica reta la em cima e despenca aqui.
function grafTempoUnitario(){
  const series = OPERADORAS.filter(o=>!desligadas.has(o)).map(op=>{
    const pontos = DIAS.map(d=>{
      const e = entradaPorOperadora(d)[op];
      if (!e) return null;
      const ent = entregaDe(e), p = precoDe(e);
      return (ent.v && p != null) ? +(p / ent.v).toFixed(4) : null;
    });
    return {label:op, data:pontos, borderColor:CORES[op]||"#999",
            backgroundColor:CORES[op]||"#999",
            tension:0.3, pointRadius:2, pointHoverRadius:4, borderWidth:2,
            spanGaps:true};
  }).filter(s2=>s2.data.some(v=>v!=null));

  if (!series.length) {
    if (graficos["c-tempo-unit"]) {
      graficos["c-tempo-unit"].destroy();
      delete graficos["c-tempo-unit"];
    }
    return;
  }
  // a unidade segue o produto: GB no movel, Mbps na fixa
  const amostra = doFiltro(DIAS[DIAS.length-1])[0];
  const u = amostra ? entregaDe(amostra).u : "";
  const titulo = document.querySelector('[data-t="g5_t"]');
  if (titulo) titulo.textContent = t("g5_t") + (u ? " (R$/" + u + ")" : "");

  const fmt = v => Number(v).toLocaleString("pt-BR",
    {minimumFractionDigits:2, maximumFractionDigits:2});
  const faixaU = faixaEixo(series.flatMap(s2=>s2.data));
  marcarSobrepostas(series, ((faixaU.max||0) - (faixaU.min||0)) * 0.005);

  trocar("c-tempo-unit", {
    type:"line",
    data:{labels:DIAS.map(dataCurta), datasets:series},
    options:{responsive:true, maintainAspectRatio:false,
      interaction:{mode:"index", intersect:false},
      plugins:{legend:legenda(),
        tooltip:{callbacks:{label:c=>c.parsed.y==null?null:
          c.dataset.label+": R$ "+fmt(c.parsed.y)+"/"+u
          + (c.dataset.sobrepoe ? " (" + t("sobre") + " " + c.dataset.sobrepoe + ")" : "")}}},
      scales:{x:eixos().x,
              y:Object.assign(eixos(fmt).y, {beginAtZero:false},
                              faixaEixo(series.flatMap(s2=>s2.data)))}},
  });
}

// O quadrante da Figure 27: uma bolinha por OFERTA, preco contra entrega,
// com o nome ao lado. Duas datas convivem - a escolhida cheia e a de
// comparacao vazada - e e ai que se ve a grade inteira se deslocar.
function grafQuadrante(){
  const dia = document.getElementById("f-data").value;

  const pontos = (d, atual) => {
    const por = {};
    const entrada = entradaPorOperadora(d);
    for (const o of doFiltro(d)) {
      const e = entregaDe(o), p = precoDe(o);
      if (e.v == null || p == null) continue;
      const ent = entrada[o.operadora];
      // Ofertas que coincidem em preco E entrega caem no mesmo pixel: a
      // Vivo tem quatro variantes a 50 GB por R$ 85, que diferem so no app
      // incluso. Desenhadas separadas, tres ficam escondidas atras da
      // primeira e os rotulos somem por colisao. Viram um ponto so, que
      // diz quantas sao e lista todas no tooltip.
      const chave = o.operadora + "|" + e.v + "|" + p;
      if (por[chave]) {
        por[chave].nomes.push(o.nome_oferta || "");
        continue;
      }
      por[chave] = {
        operadora: o.operadora, x:e.v, y:p, u:e.u, atual:atual,
        nome: o.nome_oferta || "", nomes: [o.nome_oferta || ""],
        ehEntrada: !!ent && precoDe(ent) === p && entregaDe(ent).v === e.v,
      };
    }
    const agrupado = {};
    for (const pt of Object.values(por)) {
      (agrupado[pt.operadora] = agrupado[pt.operadora] || []).push(pt);
    }
    return agrupado;
  };

  // Um dia so. Este quadro mostra a disposicao de HOJE; a comparacao entre
  // datas vive na matriz e no grafico de evolucao, e aqui ela dobrava os
  // pontos e espremia o espaco que os nomes precisam.
  const series = [];
  for (const [op, pts] of Object.entries(pontos(dia, true))) {
    series.push({label:op, data:pts, backgroundColor:CORES[op] || "#999",
      borderColor:"#FCFBF7", borderWidth:1.5,
      pointRadius:7, pointHoverRadius:9, ordem:1});
  }

  const alvo = document.getElementById("c-quadrante");
  if (!series.length) {
    if (graficos["c-quadrante"]) graficos["c-quadrante"].destroy(),
      delete graficos["c-quadrante"];
    return;
  }
  const u = series[series.length-1].data[0].u;

  // a faixa real dos pontos, para dar margem e nao encostar na borda
  const xs = series.flatMap(s2=>s2.data.map(p=>p.x));
  const faixa = {min: Math.min(...xs), max: Math.max(...xs)};
  faixa.vao = (faixa.max - faixa.min) || faixa.max || 1;

  const escalaY = faixaEixo(series.flatMap(s2=>s2.data.map(p=>p.y)));


  trocar("c-quadrante", {
    type:"scatter",
    data:{datasets:series},
    options:{responsive:true, maintainAspectRatio:false,
      // folga generosa a direita: o rotulo fica ao lado do ponto e sem
      // ela o texto do ponto mais a direita sai da area e e cortado
      layout:{padding:{right:10, top:12, bottom:4}},
      plugins:{
        // uma entrada por operadora: os datasets da data de comparacao
        // repetiriam os mesmos nomes
        legend:legenda({labels:{usePointStyle:true, pointStyle:"circle",
          boxWidth:7, boxHeight:7, padding:14, color:"#2B2621",
          font:{size:11.5, weight:"600"}}}),
        tooltip:{callbacks:{label:c=>{
          const base = reais(c.parsed.y) + " · " + c.parsed.x + " " + c.raw.u;
          const nomes = c.raw.nomes || [c.raw.nome];
          if (nomes.length === 1) {
            return c.dataset.label + " · " + nomes[0] + ": " + base;
          }
          // uma linha por oferta do grupo, para nenhuma ficar invisivel
          return [c.dataset.label + " · " + base + ":"]
            .concat(nomes.map(n => "   " + n));
        }}},
        datalabels:{
          // so a data escolhida recebe rotulo: rotular as duas viraria
          // uma mancha de texto sobre o grafico
          display: ctx => {
            if (ctx.dataset.ordem !== 1) return false;      // data de comparacao
            if (rotulosAtual === "nenhum") return false;
            if (rotulosAtual === "entrada")
              return ctx.dataset.data[ctx.dataIndex].ehEntrada ? "auto" : false;
            return "auto";
          },
          // Para cada ponto, o rotulo vai para o lado mais VAZIO da
          // vizinhanca. Com vinte ofertas amontoadas, alinhar todos para o
          // mesmo lado faz o texto de um cobrir o ponto do outro - foi o
          // que o usuario viu com "TIM Controle Smart" por cima da bolinha
          // da Claro.
          align: ctx => {
            const ch = ctx.chart, ex = ch.scales.x, ey = ch.scales.y;
            const d = ctx.dataset.data[ctx.dataIndex];
            const px = ex.getPixelForValue(d.x), py = ey.getPixelForValue(d.y);
            const lados = {right:0, left:0, top:0, bottom:0};
            for (const ds of ch.data.datasets) {
              for (const o of ds.data) {
                if (o === d) continue;
                const ox = ex.getPixelForValue(o.x), oy = ey.getPixelForValue(o.y);
                const dx = ox - px, dy = oy - py;
                if (Math.abs(dx) > 150 || Math.abs(dy) > 70) continue;
                if (Math.abs(dx) > Math.abs(dy)) lados[dx > 0 ? "right" : "left"]++;
                else lados[dy > 0 ? "bottom" : "top"]++;
              }
            }
            // perto da borda, nao adianta mandar o texto para fora
            if (px > ex.left + (ex.right - ex.left) * 0.72) lados.right += 9;
            if (px < ex.left + (ex.right - ex.left) * 0.14) lados.left += 9;
            return Object.keys(lados).sort((a, b) => lados[a] - lados[b])[0];
          },
          anchor:"center", offset:9, clamp:true, clip:false,
          color:"#4A443C", font:{size:9.5, weight:"600"},
          textStrokeColor:"#FCFBF7", textStrokeWidth:3,   // halo: separa o texto do que passa atras
          formatter:(v, ctx) => {
            // Operadora + o que diferencia a oferta. O nome do PRODUTO sai,
            // porque o filtro ja o diz e ele e quem mais ocupa espaco:
            // "TIM Controle Smart" vira "TIM Smart". A operadora fica,
            // porque sem ela "35 GB" aparece duas vezes no mesmo quadro -
            // uma da Claro, outra da NuCel - e so a cor distinguiria.
            const op = ctx.dataset.label.split(" · ")[0];
            const prod = nomeProduto(filtro().produto);
            let nome = (v.nome || "").split(op).join(" ");
            for (const palavra of prod.split(/[\s(]+/)) {
              if (palavra.length > 3) nome = nome.split(palavra).join(" ");
            }
            nome = nome.replace(/\s+/g, " ").trim();
            // sobrou nada (a oferta se chama so "Vivo Controle")? usa a
            // entrega, que e o que a distingue das irmas
            if (!nome) return op + " " + v.x + " " + v.u;
            // duas ofertas com o mesmo nome curto - as duas "Claro Day" -
            // ficam indistinguiveis; a entrega desempata
            const iguais = ctx.dataset.data.filter(o => {
              let n2 = (o.nome || "").split(op).join(" ");
              for (const w of prod.split(/[\s(]+/)) {
                if (w.length > 3) n2 = n2.split(w).join(" ");
              }
              return n2.replace(/\s+/g, " ").trim() === nome;
            }).length;
            if (iguais > 1) nome += " " + v.x + " " + v.u;
            // ponto que junta varias ofertas: o nome de uma so enganaria
            if (v.nomes && v.nomes.length > 1) {
              return op + " · " + v.nomes.length + " " + t("ofertas");
            }
            return op + " " + nome.slice(0, 18);
          },
        },
      },
      scales:{
        x:{...eixos().x, title:{display:true, text:u, color:"#7C7468",
           font:{size:11}}, ticks:{...eixos().x.ticks, maxTicksLimit:10},
           // 12% de folga de cada lado para o rotulo caber ao lado do ponto
           min: Math.max(0, faixa.min - faixa.vao * 0.12),
           max: faixa.max + faixa.vao * 0.12},
        y:{...eixos(v=>reais(v).replace("R$ ","")).y,
           beginAtZero:false, min:escalaY.min, max:escalaY.max,
           title:{display:true, text:"R$", color:"#7C7468", font:{size:11}}}},
    },
    plugins:[ChartDataLabels],
  });
}

function grafDispersao(){
  const hoje = DIAS[DIAS.length-1];
  const porOp = {};
  for (const o of doFiltro(hoje)) {
    const e = entregaDe(o), p = precoDe(o);
    if (e.v==null || p==null) continue;
    (porOp[o.operadora] = porOp[o.operadora] || []).push(
      {x:e.v, y:p, nome:o.nome_oferta||"", u:e.u});
  }
  const series = Object.entries(porOp).map(([op, pts])=>(
    {label:op, data:pts, backgroundColor:CORES[op]||"#999",
     pointRadius:5, pointHoverRadius:7}));
  if (!series.length) {
    if (graficos["c-dispersao"]) graficos["c-dispersao"].destroy(), delete graficos["c-dispersao"];
    return;
  }
  const unidade = series[0].data[0].u;
  trocar("c-dispersao", {
    type:"scatter",
    data:{datasets:series},
    options:{responsive:true, maintainAspectRatio:false,
      plugins:{legend:legenda(),
        tooltip:{callbacks:{label:c=>
          c.dataset.label+" · "+c.raw.nome+": "+reais(c.parsed.y)
          +" · "+c.parsed.x+" "+c.raw.u}}},
      scales:{
        x:{...eixos().x, title:{display:true, text:unidade,
           color:"#7C7468", font:{size:11}}},
        y:eixos(v=>reais(v).replace("R$ ","")).y}},
  });
}

// Preco por unidade entregue: R$/GB no movel, R$/Mbps na fibra. E o
// grafico do meio de toda pagina do tracker da XP, e e o que impede de
// comparar precos nominais de ofertas que entregam coisas diferentes.
function grafUnitario(){
  const hoje = DIAS[DIAS.length-1];
  const entrada = entradaPorOperadora(hoje);
  const itens = [];
  for (const [op, o] of Object.entries(entrada)) {
    const e = entregaDe(o), p = precoDe(o);
    if (!e.v || p == null) continue;
    itens.push({op, v:p/e.v, u:e.u, nome:o.nome_oferta||"", preco:p, entrega:e.v});
  }
  itens.sort((a,b)=>a.v-b.v);
  const alvo = document.getElementById("c-unitario");
  if (!itens.length) {
    if (graficos["c-unitario"]) graficos["c-unitario"].destroy(), delete graficos["c-unitario"];
    return;
  }
  const u = itens[0].u;
  // casas decimais conforme a grandeza: R$/GB fica na ordem de centavos
  const casas = itens[itens.length-1].v < 1 ? 2 : 1;
  trocar("c-unitario", {
    type:"bar",
    data:{labels:itens.map(i=>i.op),
          datasets:[{data:itens.map(i=>+i.v.toFixed(3)),
            backgroundColor:itens.map(i=>CORES[i.op]||"#999"),
            borderRadius:4, barThickness:22}]},
    options:{indexAxis:"y", responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false},
        tooltip:{callbacks:{label:c=>{
          const i = itens[c.dataIndex];
          return i.nome+": "+reais(i.v)+"/"+i.u
                 +"  ("+reais(i.preco)+" ÷ "+i.entrega+" "+i.u+")";
        }}}},
      scales:{
        x:{grid:{display:true, color:EIXO.grade, drawTicks:false},
           border:{display:true, color:EIXO.borda, width:1},
           title:{display:true, text:"R$/"+u, color:"#7C7468", font:{size:11}},
           ticks:{color:"#7C7468", font:{size:11},
                  callback:v=>Number(v).toLocaleString("pt-BR",
                    {minimumFractionDigits:casas, maximumFractionDigits:casas})}},
        y:{grid:{display:false}, border:{display:true, color:EIXO.borda, width:1},
           ticks:{color:"#2B2621", font:{size:12, weight:"600"}}}}},
  });
}

// A matriz do Exhibit 1 do J.P. Morgan: linhas sao a oferta, colunas sao
// as datas, e a celula traz o preco. A mudanca aparece sem grafico e sem
// frase - a celula que muda recebe seta e cor.
//
// A deles e por mes e so da oferta de entrada, porque a coleta e manual.
// A nossa e por dia e por DEGRAU: acompanhar so a entrada escondia o que
// a Claro fez em 05/10, quando mexeu no 600 e no 750 Mega e deixou a
// entrada parada.
// Dias em que a operadora manteve TODOS os precos e trocou os degraus.
// E o caso da NuCel em 06/10: 25/30/40 GB viraram 35/40/45 pelos mesmos
// 45/60/70 reais. Pareado por degrau, o "40 GB" de ontem (topo, R$ 70) vira
// o "40 GB" de hoje (meio, R$ 60) e a celula ganharia seta de queda - a
// mesma leitura errada que o aviso do Telegram deu e foi corrigida la.
function gradeDeslizou(operadora, dia, anterior){
  const conj = d => {
    const por = {};
    for (const o of doFiltro(d)) {
      if (o.operadora !== operadora) continue;
      const p = precoDe(o), e = entregaDe(o);
      if (p == null || e.v == null) continue;
      if (por[p] == null || e.v < por[p]) por[p] = e.v;
    }
    return por;
  };
  const a = conj(anterior), b = conj(dia);
  const pa = Object.keys(a).sort(), pb = Object.keys(b).sort();
  if (!pa.length || pa.join() !== pb.join()) return false;
  return pa.some(p => a[p] !== b[p]);
}

function matriz(){
  const alvo = document.getElementById("matriz");
  const dias = DIAS.slice(-12);

  // junta os degraus vistos em qualquer dia do recorte: degrau que sumiu
  // no meio do caminho tem de continuar na tabela, com a celula vazia
  const linhas = {};
  for (const d of dias) {
    for (const [k, v] of Object.entries(porDegrau(d))) {
      if (desligadas.has(v.operadora)) continue;
      linhas[k] = linhas[k] || {operadora:v.operadora, degrau:v.degrau,
                                unidade:v.unidade, por:{}};
      linhas[k].por[d] = {p:precoDe(v.oferta), nome:v.oferta.nome_oferta||""};
    }
  }
  const ordenadas = Object.values(linhas).sort((a, b)=>
    a.operadora.localeCompare(b.operadora) || a.degrau - b.degrau);

  if (!ordenadas.length) {
    alvo.innerHTML = `<div class="vazio">${t("sem_dado")}</div>`;
    return;
  }

  const cab = `<tr><th>${t("col")[0]}</th><th>${t("col")[2]}</th>` +
    dias.map(d=>`<th class="num">${dataCurta(d)}</th>`).join("") + `</tr>`;

  let opAnterior = null, bloco = 0;
  const corpo = ordenadas.map(l=>{
    let anterior = null;
    const celulas = dias.map(d=>{
      const c = l.por[d];
      if (!c || c.p == null) { anterior = null; return `<td class="num vazia">—</td>`; }
      // no modo unidade, a celula vira preco dividido pela entrega
      const mostra = v => metricaAtual === "unidade"
        ? (l.degrau ? (v / l.degrau) : null)
        : v;
      let marca = "", cls = "", dica = c.nome;
      if (anterior) {
        if (anterior.nome !== c.nome) {
          // Outra oferta assumiu o degrau. NAO e mudanca de preco: foi o
          // que aconteceu com a Vivo em 03/10, quando a "Vivo Fibra" de
          // 600 Mbps entrou a R$ 100 num degrau que so tinha "Fibra + TV"
          // a R$ 270 - a seta de queda sugeriria corte de 63% onde houve
          // lancamento de produto.
          marca = " ◆";
          cls = " trocou";
          dica = t("m_trocou") + ": " + anterior.nome + " → " + c.nome;
        } else if (anterior.p !== c.p) {
          if (gradeDeslizou(l.operadora, d, dias[dias.indexOf(d) - 1])) {
            // a grade inteira andou: nao e preco mudando, e outro degrau
            // ocupando a mesma linha
            marca = " ◆";
            cls = " trocou";
            dica = t("m_grade");
          } else {
            const sobe = c.p > anterior.p;
            marca = sobe ? " ▲" : " ▼";
            cls = sobe ? " sobe" : " desce";
            dica = c.nome + ": " + reais(anterior.p) + " → " + reais(c.p);
          }
        }
      }
      anterior = c;
      const v = mostra(c.p);
      if (v == null) return `<td class="num vazia">—</td>`;
      // R$/GB fica na ordem de centavos: duas casas, ou o eixo repete
      const txt = metricaAtual === "unidade"
        ? v.toLocaleString("pt-BR", {minimumFractionDigits:2, maximumFractionDigits:2})
        : reais(v).replace("R$ ", "");
      return `<td class="num${cls}" title="${dica}">` + txt + marca + `</td>`;
    }).join("");
    // o nome da operadora so na primeira linha dela: repetir seis vezes
    // "Claro" rouba a atencao do que importa, que e o degrau e o preco
    const novaOp = l.operadora !== opAnterior;
    if (novaOp) bloco++;
    opAnterior = l.operadora;
    const rotuloOp = novaOp
      ? `<span class="op-tag"><span class="marcador" style="background:${CORES[l.operadora]||"#999"}"></span>${l.operadora}</span>`
      : "";
    // o bloco inteiro da operadora alterna de fundo, em vez da zebra por
    // linha: assim o olho segue o conjunto e nao perde onde um acaba
    const classes = [novaOp ? "troca-op" : "", bloco % 2 === 0 ? "bloco-alt" : ""]
      .filter(Boolean).join(" ");
    return `<tr class="${classes}"><td class="op-col">${rotuloOp}</td>`
         + `<td class="degrau">${l.degrau} ${l.unidade}</td>${celulas}</tr>`;
  }).join("");

  alvo.innerHTML = `<table><thead>${cab}</thead><tbody>${corpo}</tbody></table>`;

  // o titulo diz a unidade, como nos quadros do tracker do BBA
  const unidade = ordenadas[0] ? ordenadas[0].unidade : "";
  document.querySelector('[data-t="mat_t"]').textContent =
    t("mat_t") + (metricaAtual === "unidade"
      ? " (R$/" + unidade + ")" : " (R$/" + t("mes") + ")");
}

function grafRanking(){
  const hoje = DIAS[DIAS.length-1];
  const entrada = entradaPorOperadora(hoje);
  const itens = Object.entries(entrada)
    .map(([op, o])=>({op, p:precoDe(o), nome:o.nome_oferta||""}))
    .sort((a,b)=>a.p-b.p);
  if (!itens.length) {
    if (graficos["c-ranking"]) graficos["c-ranking"].destroy(), delete graficos["c-ranking"];
    return;
  }
  trocar("c-ranking", {
    type:"bar",
    data:{labels:itens.map(i=>i.op),
          datasets:[{data:itens.map(i=>i.p),
            backgroundColor:itens.map(i=>CORES[i.op]||"#999"),
            borderRadius:4, barThickness:22}]},
    options:{indexAxis:"y", responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false},
        tooltip:{callbacks:{label:c=>itens[c.dataIndex].nome+": "+reais(c.parsed.x)}}},
      scales:{
        x:{grid:{display:true, color:EIXO.grade, drawTicks:false},
           border:{display:true, color:EIXO.borda, width:1},
           ticks:{color:"#7C7468", font:{size:11},
                  callback:v=>reais(v).replace("R$ ","")}},
        y:{grid:{display:false}, border:{display:true, color:EIXO.borda, width:1},
           ticks:{color:"#2B2621", font:{size:12, weight:"600"}}}}},
  });
}

// O ultimo dia pode estar PARCIAL: a coleta leva dezenas de minutos e a
// tela pode ser gerada no meio dela. Aconteceu em 05/10 - o dia tinha so
// a Vivo quando as outras cinco ainda estavam coletando, e a tela mostrou
// uma praca com uma operadora so, sem dizer por que.
//
// Em vez de esconder, declara: compara a contagem de operadoras do ultimo
// dia com a do anterior. Se caiu, o dia esta incompleto e a tela avisa.
function diaParcial(){
  if (DIAS.length < 2) return null;
  const ultimo = DIAS[DIAS.length-1], antes = DIAS[DIAS.length-2];
  const ops = d => new Set(doFiltro(d).map(o=>o.operadora)).size;
  const a = ops(ultimo), b = ops(antes);
  return a < b ? {dia:ultimo, tem:a, tinha:b, antes:antes} : null;
}

function kpis(){
  const hoje = DIAS[DIAS.length-1];
  const entrada = entradaPorOperadora(hoje);
  const precos = Object.values(entrada).map(precoDe).filter(v=>v!=null).sort((a,b)=>a-b);
  // no MESMO dia da tabela e do ranking: contar operadoras de todos os
  // dias dava "3 de 6" ao lado de uma tabela com uma linha
  const naPraca = new Set(doFiltro(hoje).map(o=>o.operadora));
  const mediana = precos.length
    ? (precos.length%2 ? precos[(precos.length-1)/2]
       : (precos[precos.length/2-1]+precos[precos.length/2])/2) : null;
  const maisBarato = Object.entries(entrada).sort((a,b)=>precoDe(a[1])-precoDe(b[1]))[0];

  const cartoes = [
    {rot:t("kpi_ops"), val:naPraca.size+" "+t("de")+" "+OPERADORAS.length,
     pe:[...naPraca].sort().join(", ") || t("sem_dado")},
    {rot:t("kpi_barato"), val:maisBarato?reais(precoDe(maisBarato[1])):"—",
     pe:maisBarato?maisBarato[0]+" · "+(maisBarato[1].destaque||""):t("sem_dado")},
    {rot:t("kpi_mediana"), val:reais(mediana),
     pe:precos.length+" "+t("f_operadora").toLowerCase()},
    {rot:t("kpi_serie"), val:t("kpi_dias").replace("{n}", DIAS.length),
     pe:t("kpi_desde").replace("{d}", dataCurta(DIAS[0]))},
  ];
  document.getElementById("kpis").innerHTML = cartoes.map(c=>
    `<div class="kpi"><div class="rot">${c.rot}</div>
     <div class="val">${c.val}</div><div class="pe">${c.pe}</div></div>`).join("");
}

// Uma linha por operadora, nao uma por oferta. A versao anterior
// despejava 79 linhas e 7 colunas, o que o usuario chamou de "tabelas
// enfadonhas com muita informacao irrelevante" - e estava certo: ali
// nao se le nada.
function tabela(){
  const hoje = DIAS[DIAS.length-1];
  const entrada = entradaPorOperadora(hoje);
  const itens = Object.entries(entrada).sort((a,b)=>precoDe(a[1])-precoDe(b[1]));
  const alvo = document.getElementById("tabela");
  const nota = document.getElementById("n-tabela");
  if (!itens.length) {
    alvo.innerHTML = `<div class="vazio">${t("sem_dado")}</div>`;
    nota.textContent = "";
    return;
  }
  const c = t("col");
  const linhas = itens.map(([op, o])=>{
    const e = entregaDe(o);
    const contr = num(o.franquia_contratual_gb);
    return `<tr>
      <td><span class="op-tag"><span class="marcador" style="background:${CORES[op]||"#999"}"></span>${op}</span></td>
      <td>${o.nome_oferta||"—"}</td>
      <td>${e.v!=null?e.v+" "+e.u:"—"}</td>
      <td>${contr!=null?contr+" "+t("gb"):"—"}</td>
      <td class="num">${reais(precoDe(o))}</td></tr>`;
  }).join("");
  alvo.innerHTML = `<table><thead><tr>${c.map(x=>`<th>${x}</th>`).join("")}</tr></thead>
    <tbody>${linhas}</tbody></table>`;
  const totalPraca = DADOS.filter(o=>o.praca===filtro().praca
    && o.produto===filtro().produto && diaDe(o)===hoje).length;
  nota.textContent = t("mostrando").replace("{a}", itens.length).replace("{b}", totalPraca);
}

// Todas as ofertas do dia, agrupadas por operadora. Responde "o que este
// player vende", que e pergunta de lista e nao de grafico.
function tabelaPorPlayer(){
  const alvo = document.getElementById("t-player");
  const nota = document.getElementById("n-player");
  const dia = document.getElementById("f-data").value;
  const player = document.getElementById("f-player").value;

  let ofertas = DADOS.filter(o =>
    (o.praca === filtro().praca || o.praca === PRACA_NACIONAL)
    && o.produto === filtro().produto && diaDe(o) === dia
    && precoDe(o) != null);
  if (player) ofertas = ofertas.filter(o => o.operadora === player);

  if (!ofertas.length) {
    alvo.innerHTML = `<div class="vazio">${t("sem_dado")}</div>`;
    nota.textContent = "";
    return;
  }
  ofertas.sort((a, b) => a.operadora.localeCompare(b.operadora)
    || precoDe(a) - precoDe(b));

  const c = colunas("col_player", ofertas);
  let opAnterior = null, linhas = "";
  for (const o of ofertas) {
    if (o.operadora !== opAnterior) {
      opAnterior = o.operadora;
      linhas += `<tr class="grupo-op"><td colspan="${c.length}">
        <span class="op-tag"><span class="marcador" style="background:${CORES[o.operadora]||"#999"}"></span>
        ${o.operadora}</span></td></tr>`;
    }
    const e = entregaDe(o), p = precoDe(o);
    const contr = o.franquia_contratual_gb;
    linhas += `<tr>
      <td>${o.nome_oferta || "—"}</td>
      ${celulaEntrega(o)}
      <td class="num">${reais(p)}</td>
      <td class="num">${e.v ? (p / e.v).toLocaleString("pt-BR",
        {minimumFractionDigits:2, maximumFractionDigits:2}) : "—"}</td>
      <td>${vantagem(o)}</td></tr>`;
  }
  alvo.innerHTML = `<table><thead><tr>${c.map(x=>`<th>${x}</th>`).join("")}</tr></thead>
    <tbody>${linhas}</tbody></table>`;
  nota.textContent = t("n_player")
    .replace("{n}", ofertas.length)
    .replace("{d}", dataCurta(dia))
    .replace("{p}", filtro().praca);
}

// A comparacao entre players: a oferta de entrada de cada um, lado a lado.
// E a segunda tabela que o usuario pediu no chat - GB, preco, R$ por GB e
// o que vem junto.
function tabelaComparacao(){
  const alvo = document.getElementById("t-comparacao");
  const dia = document.getElementById("f-data").value;
  const entrada = entradaPorOperadora(dia);
  const itens = Object.entries(entrada)
    .filter(([, o]) => precoDe(o) != null)
    .map(([op, o]) => {
      const e = entregaDe(o), p = precoDe(o);
      return {op, o, e, p, unit: e.v ? p / e.v : null};
    })
    .sort((a, b) => (a.unit == null) - (b.unit == null)
      || (a.unit - b.unit) || (a.p - b.p));

  if (!itens.length) {
    alvo.innerHTML = `<div class="vazio">${t("sem_dado")}</div>`;
    return;
  }
  // o melhor preco por unidade ganha destaque: e a leitura que a tabela
  // existe para dar, e procurar o menor numero na coluna custa atencao
  const melhor = itens[0].unit;
  const c = colunas("col_cmp", itens.map(i => i.o));
  const linhas = itens.map(i => {
    const contr = i.o.franquia_contratual_gb;
    const marca = (i.unit != null && i.unit === melhor) ? ' class="destaque-linha"' : "";
    return `<tr${marca}>
      <td><span class="op-tag"><span class="marcador" style="background:${CORES[i.op]||"#999"}"></span>${i.op}</span></td>
      <td>${i.o.nome_oferta || "—"}</td>
      ${celulaEntrega(i.o)}
      <td class="num">${reais(i.p)}</td>
      <td class="num">${i.unit != null ? i.unit.toLocaleString("pt-BR",
        {minimumFractionDigits:2, maximumFractionDigits:2}) : "—"}</td>
      <td>${vantagem(i.o)}</td></tr>`;
  }).join("");
  alvo.innerHTML = `<table><thead><tr>${c.map(x=>`<th>${x}</th>`).join("")}</tr></thead>
    <tbody>${linhas}</tbody></table>`;
}

// Comparar so a entrada e pouco: a operadora pode ser barata na porta e
// cara no degrau de cima, que e onde esta a receita. Aqui a escada e
// cortada em faixas e, dentro de cada uma, compara-se a oferta mais
// barata de cada operadora - mesmo criterio da entrada, aplicado faixa a
// faixa.
function tabelaFaixas(){
  const alvo = document.getElementById("t-faixas");
  const dia = document.getElementById("f-data").value;

  const ofertas = DADOS.filter(o =>
    (o.praca === filtro().praca || o.praca === PRACA_NACIONAL)
    && o.produto === filtro().produto && diaDe(o) === dia
    && !desligadas.has(o.operadora)
    && precoDe(o) != null && entregaDe(o).v != null);
  if (ofertas.length < 2) { alvo.innerHTML = ""; return; }

  const vals = ofertas.map(o => entregaDe(o).v).sort((a, b) => a - b);
  const u = entregaDe(ofertas[0]).u;
  // tercis: tres faixas com numero parecido de ofertas, em vez de cortes
  // redondos que deixariam uma faixa vazia
  const c1 = vals[Math.floor(vals.length / 3)];
  const c2 = vals[Math.floor(vals.length * 2 / 3)];
  const faixas = [
    {nome: t("fx_baixa") + " — até " + c1 + " " + u, min: -Infinity, max: c1},
    {nome: t("fx_media") + " — " + c1 + " a " + c2 + " " + u, min: c1, max: c2},
    {nome: t("fx_alta") + " — acima de " + c2 + " " + u, min: c2, max: Infinity},
  ];

  const c = colunas("col_cmp", ofertas);
  let html = "";
  for (const f of faixas) {
    const dentro = ofertas.filter(o => {
      const v = entregaDe(o).v;
      return f.min === -Infinity ? v <= f.max
           : f.max === Infinity ? v > f.min
           : (v > f.min && v <= f.max);
    });
    if (!dentro.length) continue;
    // a mais barata de cada operadora dentro da faixa
    const por = {};
    for (const o of dentro) {
      const p = precoDe(o);
      if (!por[o.operadora] || p < precoDe(por[o.operadora])) por[o.operadora] = o;
    }
    const itens = Object.entries(por).map(([op, o]) => {
      const e = entregaDe(o), p = precoDe(o);
      return {op, o, e, p, unit: e.v ? p / e.v : null};
    }).sort((a, b) => a.unit - b.unit);
    if (itens.length < 2) continue;      // faixa com uma operadora so nao compara

    const melhor = itens[0].unit;
    const linhas = itens.map(i => {
      const contr = i.o.franquia_contratual_gb;
      const marca = i.unit === melhor ? ' class="destaque-linha"' : "";
      return `<tr${marca}>
        <td><span class="op-tag"><span class="marcador" style="background:${CORES[i.op]||"#999"}"></span>${i.op}</span></td>
        <td>${i.o.nome_oferta || "—"}</td>
        ${celulaEntrega(i.o)}
        <td class="num">${reais(i.p)}</td>
        <td class="num">${i.unit.toLocaleString("pt-BR",
          {minimumFractionDigits:2, maximumFractionDigits:2})}</td>
        <td>${vantagem(i.o)}</td></tr>`;
    }).join("");
    html += `<div class="faixa"><div class="faixa-rot">${f.nome}</div>
      <div class="tabela-wrap"><table><thead><tr>${c.map(x=>`<th>${x}</th>`).join("")}</tr></thead>
      <tbody>${linhas}</tbody></table></div></div>`;
  }
  alvo.innerHTML = html || `<div class="vazio">${t("sem_dado")}</div>`;
}

function desenhar(){
  const emOfertas = !document.getElementById("pg-ofertas").hidden;
  if (emOfertas) {
    tabelaPorPlayer();
    tabelaComparacao();
    tabelaFaixas();
    return;        // nao desenha grafico escondido: Chart.js mede errado
  }
  grafQuadrante();
  kpis();
  grafTempo();
  grafTempoUnitario();
  grafDispersao();
  grafUnitario();
  matriz();
  const ultimo = DIAS.length ? dataCurta(DIAS[DIAS.length-1]) : "—";
  document.getElementById("sub").textContent =
    (lang==="pt" ? "Última coleta: " : "Last collection: ") + ultimo
    + " · " + DADOS.length + (lang==="pt" ? " capturas" : " captures");
}

// A altura do cabecalho muda com a largura da tela, porque o conteudo
// quebra em duas linhas no celular. Medir e melhor que chutar um valor
// fixo: com chute, os filtros grudam sobrepondo o cabecalho ou flutuando
// longe dele.
function medirTopo(){
  const h = document.querySelector("header");
  const f = document.querySelector(".controles");
  const n = document.querySelector("nav.abas");
  if (h) document.documentElement.style.setProperty("--topo-h", h.offsetHeight + "px");
  if (n) document.documentElement.style.setProperty("--abas-h", n.offsetHeight + "px");
  if (f) document.documentElement.style.setProperty("--filtros-h", (f.offsetHeight + 14) + "px");
}
addEventListener("resize", medirTopo);

function iniciar(){
  derivar();
  montarFiltros();
  idioma(lang);
  medirTopo();
}

function recado(txt){
  document.getElementById("sub").textContent = txt;
  document.getElementById("n-tempo").textContent = txt;
}

if (FONTE) {
  recado(lang==="pt" ? "Carregando a série..." : "Loading the series...");
  // no-store: a tela tem de mostrar a coleta de hoje, nao a de ontem que
  // ficou no cache do navegador
  fetch(FONTE, {cache:"no-store"})
    .then(r=>{ if(!r.ok) throw new Error("HTTP "+r.status); return r.json(); })
    .then(d=>{ if(!Array.isArray(d)||!d.length) throw new Error("vazio");
               DADOS = d; iniciar(); })
    .catch(e=>recado(lang==="pt"
      ? "Não consegui carregar a série ("+e.message+"). A página está no ar, mas sem dado — nada aqui foi estimado."
      : "Could not load the series ("+e.message+"). The page is up but has no data — nothing was estimated."));
} else {
  iniciar();
}
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", required=True)
    ap.add_argument("--saida", default="tela.html")
    ap.add_argument("--remoto", default="",
                    help="URL do JSON; a pagina busca o dado em vez de embuti-lo")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    dados = json.load(io.open(a.dados, encoding="utf-8"))
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")

    # no modo remoto o HTML vai sem os dados: fica leve e nao envelhece
    embutidos = [] if a.remoto else dados
    html = (MOLDE
            .replace("__DADOS__", json.dumps(embutidos, ensure_ascii=False))
            .replace("__FONTE__", a.remoto)
            .replace("__CORES__", json.dumps(CORES, ensure_ascii=False))
            .replace("__GERADO__", agora))
    io.open(a.saida, "w", encoding="utf-8").write(html)
    print("tela gerada: %s (%d KB)%s"
          % (a.saida, len(html) // 1024,
             "" if a.remoto else " com %d capturas embutidas" % len(dados)))
    if a.remoto:
        print("  busca o dado em: %s" % a.remoto)
        print("  (%d capturas na origem, nenhuma embutida)" % len(dados))
    return 0


if __name__ == "__main__":
    sys.exit(main())
