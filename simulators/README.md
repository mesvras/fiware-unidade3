# Simuladores

Geram dados realistas de hotéis, restaurantes e bares, eventos e praias de Natal e os enviam à API da plataforma, no mesmo formato JSON que um prestador usaria. Nomes, endereços e coordenadas são fictícios: as coordenadas ficam dentro da área de Natal, mas não correspondem a lugares reais.

Os simuladores só falam com a API (`http://api:8000`). Eles não acessam o Orion-LD diretamente.

## Como usar

Os comandos rodam a partir da pasta `docker/`, com a stack no ar:

```bash
docker compose --profile sim run --rm --build simulator seed all     # cria ou atualiza todos os dados
docker compose --profile sim run --rm simulator check all            # verifica os dados pela API
docker compose --profile sim run --rm simulator run                  # altera os dados de forma contínua
```

```
Comando         Efeito
--------------  ---------------------------------------------------------------------------
seed <alvo>     cria os registros (POST); se o registro já existe (409), atualiza (PATCH)
check <alvo>    consulta a API e compara o resultado com o que o gerador prevê
run             a cada ciclo, altera a disponibilidade dos hotéis e a ocupação de
                restaurantes e bares; termina com SIGTERM ou Ctrl+C
```

Alvos: `hotels`, `restaurants`, `events`, `beaches` ou `all`. O `seed all` segue esta ordem, porque os eventos usam bares e restaurantes como local. Para rodar um alvo sozinho, respeite a mesma ordem: `hotels`, `restaurants`, `events`, `beaches`.

O `seed` termina com código 1 se alguma requisição falhar. O `check` imprime uma linha `OK` ou `FALHA` por verificação e termina com código 1 se alguma falhar.

## O que cada alvo gera

```
Alvo          Volume padrão                    Conteúdo
------------  -------------------------------  ---------------------------------------------------
hotels        12 hotéis, 2 a 4 tipos de        categoria, estrelas e comodidades; disponibilidade
              quarto cada, 60 noites           por noite com preço e ocupação
restaurants   25 restaurantes e 15 bares       cozinha, faixa de preço, horário de funcionamento,
                                               capacidade e ocupação atual
events        40 eventos em 60 dias            shows em bares, oficinas comunitárias, festivais
                                               e congressos
beaches       2 estações meteorológicas,       praias na orla, cada uma ligada à estação mais
              6 praias, 2 pontos de coleta     próxima; pontos de coleta a até 300 m da praia
              por praia
```

### Zonas

Os registros ficam em cinco zonas fictícias: Orla Sul, Orla Central, Centro Histórico, Bairro Universitário e Orla Norte. Cada zona tem centro, raio, ruas e faixa de CEP próprios. Hotéis, restaurantes e bares usam as mesmas zonas, ruas e faixas de CEP. Praias e estações meteorológicas ficam só nas zonas de orla.

### Hotéis

- A categoria define o prefixo do nome e as estrelas: Hostel (1 a 2), Pousada (2 a 3), Hotel (3 a 5), Resort (4 a 5) e Flat (3 a 4). Hotéis na orla têm a comodidade `beachfront`.
- O preço por noite parte de uma base por categoria e estrelas, multiplicada pelo tipo de quarto, pela temporada (alta de dezembro a fevereiro e em julho) e pelo fim de semana (sexta e sábado).
- A ocupação cresce na alta temporada, no fim de semana e quando a data se aproxima.
- `minimumStay` é de 3 noites de 27/12 a 01/01 e de 2 noites em sexta e sábado da alta temporada.
- No `run`, cada ciclo aplica reservas e cancelamentos em noites sorteadas, com mais peso nas próximas, e cria as noites que entram no horizonte quando o dia muda.

### Restaurantes e bares

- A cozinha vem de uma lista fixa em minúsculas (`regional`, `frutos do mar`, `japonesa`, `italiana`, `churrasco`, `vegetariana`, `pizza`; `petiscos` nos bares) e define o prefixo do nome e a faixa de preço.
- O horário dos bares pode passar da meia-noite (por exemplo, 17:00 às 02:00).
- A ocupação segue uma curva pela hora de Natal (UTC−3). Restaurantes têm picos no almoço e no jantar. Bares têm pico à noite, mais forte de quinta a sábado. Fora do horário de funcionamento, a ocupação é 0.
- A API calcula `availabilityLevel` a partir da ocupação e da capacidade.

### Eventos

```
Tipo        Parte do total  Local                                    Horário (hora de Natal)
----------  --------------  ---------------------------------------  ------------------------------
show        45%             bar (refPointOfInterest)                 quinta a domingo, até 23:30
oficina     25%             centro comunitário da zona; a de         sábado, 3 horas
                            culinária fica em um restaurante
festival    15%             calçadão de uma zona de orla             2 a 3 dias, a partir de sexta
congresso   restante        centro de convenções na Orla Central     2 a 3 dias úteis, 08:00 às 18:00
```

Dois eventos ficam com `eventStatus` `cancelled` e um com `postponed`. Os congressos usam a categoria `conference`.

## Variáveis

As variáveis podem ficar no `docker/.env` ou no ambiente do shell.

```
Variável              Padrão         Efeito
--------------------  -------------  ------------------------------------------------------
SIM_SEED              natal          semente dos geradores
SIM_START_DATE        hoje (UTC)     primeiro dia da disponibilidade e dos eventos, AAAA-MM-DD
SIM_CONCURRENCY       8              requisições simultâneas à API
SIM_INTERVAL          30             segundos entre ciclos do run
SIM_HOTELS            12             quantidade de hotéis
SIM_NIGHTS            60             noites de disponibilidade por tipo de quarto
SIM_RESTAURANTS       25             quantidade de restaurantes
SIM_BARS              15             quantidade de bares
SIM_EVENTS            40             quantidade de eventos
SIM_EVENT_DAYS        60             dias do período dos eventos (mínimo 7)
SIM_STATIONS          2              quantidade de estações meteorológicas
SIM_BEACHES           6              quantidade de praias
SIM_POINTS_PER_BEACH  2              pontos de coleta por praia
```

## Comportamento

- **Reprodutível.** A mesma semente e a mesma data inicial geram os mesmos dados. Cada registro tem a sua própria semente: mudar um volume não altera os registros que já existem.
- **Idempotente.** Rodar o `seed` de novo não duplica registros. Ele atualiza os registros para os valores gerados e desfaz as alterações feitas pelo `run`.
- **Ids com prefixo `sim-`.** Os registros ficam no tenant padrão e são permanentes. O prefixo separa esses registros dos registros dos testes (`teste-`, `smoke-`).
- **Novas tentativas.** O cliente repete a requisição em caso de resposta 503 ou falha de rede, até 5 vezes.
- **Sem token.** Os simuladores ainda não enviam token. A API do Compose roda com a autenticação desligada (`AUTH_ENABLED=false`).

## Ressalvas

- Com `SIM_START_DATE` no padrão, a data inicial muda a cada dia. Se o `check hotels` rodar em um dia diferente do `seed`, sem o `run` ligado, as últimas noites do horizonte podem não existir. Rode o `seed` de novo ou use a mesma `SIM_START_DATE` nos dois comandos.
- O `check restaurants` compara `availabilityLevel` com o limiar de 70%, que é o padrão da API (`AVAILABILITY_LIMITED_RATIO`). Se o limiar da API mudar, a verificação falha.
- O `check` usa os mesmos valores das variáveis que o `seed` usou. Com outros valores, ele procura outros registros.

## Testes

Testes unitários dos geradores e do cliente, sem a stack:

```bash
docker compose --profile test run --rm --build sim-tests
```
