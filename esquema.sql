-- Esquema do Price Tracker
-- Rodar uma vez, no SQL Editor do Supabase do projeto tmt-price-tracker.
--
-- PRINCIPIO: append-only. Nada aqui e atualizado ou apagado. Uma captura
-- nunca sobrescreve outra, porque o que nao foi capturado no dia esta
-- perdido para sempre e o que foi capturado e a unica prova do que houve.

-- ---------------------------------------------------------------- capturas

create table if not exists capturas (
  id                      bigint generated always as identity primary key,

  -- quando e onde
  capturado_em            timestamptz not null,
  data_captura            date        not null,
  operadora               text        not null,
  produto                 text        not null,   -- controle|movel|fibra|combo|prepago
  praca                   text        not null,   -- "Sao Paulo/SP"
  uf                      text,

  -- identidade da oferta
  nome_oferta             text,
  destaque                text,                   -- "45 GB", "700 Mega"
  chave                   text        not null,   -- continuidade: operadora|produto|degrau|variante
  codigo_anatel           text,
  codigos_anatel          text[],
  id_catalogo             text,

  -- o degrau (decisao 8: exato, sem faixa)
  degrau_mbps             integer,
  franquia_anunciada_gb   integer,
  franquia_contratual_gb  integer,

  -- preco: cheio e promocional NUNCA no mesmo campo (decisao 13)
  preco_cheio             numeric(10,2),
  preco_promocional       numeric(10,2),

  -- contrato (so a Vivo publica; nas outras fica nulo - decisao 9)
  fidelidade_meses        integer,
  multa_fidelidade        numeric(10,2),
  taxa_instalacao         numeric(10,2),

  -- comparabilidade
  nivel_bundle            smallint,               -- 0 a 4 (decisao 10)
  campanha                text[],


  -- A captura crua, para nao perder o que ainda nao sabemos usar - e para
  -- que campo novo no coletor entre no mesmo dia, sem ALTER TABLE.
  --
  -- A assinatura da composicao mora aqui, em bruto->>'assinatura_sva': os
  -- codigos SVA da oferta ordenados e unidos por "+". So a Vivo os publica.
  -- Nao sabemos que app e cada codigo, e nao da para saber - o cruzamento
  -- com a vitrine nomeou 1 dos 20 (secao 7 da metodologia). O valor nao
  -- esta no nome e sim no conjunto: quando ele muda com o preco parado, a
  -- oferta trocou de conteudo sem trocar de etiqueta.
  bruto                   jsonb,

  gravado_em              timestamptz not null default now()
);

-- Uma oferta so pode ser gravada uma vez por praca por dia. Protege contra
-- duplicata quando o robo repete (o repique das 7h30) sem apagar nada.
create unique index if not exists capturas_unicas
  on capturas (data_captura, operadora, produto, praca, chave, nome_oferta, codigo_anatel);

create index if not exists capturas_serie
  on capturas (operadora, produto, chave, data_captura);

create index if not exists capturas_por_dia
  on capturas (data_captura);

comment on table capturas is
  'Append-only. Uma linha por oferta, por praca, por dia. Nunca atualizar nem apagar.';

-- ------------------------------------------------------------------ coletas

-- Diario de bordo do robo: o que rodou, o que falhou, o que veio vazio.
-- Sem isto, falha silenciosa vira buraco invisivel na serie.
create table if not exists coletas (
  id             bigint generated always as identity primary key,
  data_captura   date        not null,
  iniciada_em    timestamptz not null,
  terminada_em   timestamptz,
  operadora      text        not null,
  pracas_pedidas integer     not null default 0,
  pracas_ok      integer     not null default 0,
  ofertas        integer     not null default 0,
  avisos         text[],
  sucesso        boolean     not null default false
);

create index if not exists coletas_por_dia on coletas (data_captura);

comment on table coletas is
  'Um registro por operadora por rodada. Alimenta a mensagem diaria das 8h.';

-- --------------------------------------------------------------- seguranca

-- O robo grava com a chave secreta (service role), que ignora RLS.
-- A leitura publica fica liberada porque preco de vitrine e informacao
-- publica - nao ha dado pessoal aqui.
alter table capturas enable row level security;
alter table coletas  enable row level security;

drop policy if exists leitura_publica_capturas on capturas;
create policy leitura_publica_capturas on capturas for select using (true);

drop policy if exists leitura_publica_coletas on coletas;
create policy leitura_publica_coletas on coletas for select using (true);

