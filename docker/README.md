# Stack Docker

Orion-LD, MongoDB, Mosquitto, IoT Agent JSON, CrateDB, QuantumLeap, um servidor de contextos (nginx) e a API da plataforma em uma rede interna (`internal: true`). Nenhum serviço publica porta no host e nenhum container acessa a internet.

## Como subir

```bash
cp .env.example .env
docker compose up -d --wait
docker compose ps
```

Para consultar o Orion-LD, use um container na mesma rede:

```bash
docker compose exec orion curl -s http://localhost:1026/ngsi-ld/ex/v1/version
```

## API da plataforma

O serviço `api` é construído a partir de `api/Dockerfile`, com o repositório como contexto de build, porque a imagem inclui `pkg/` (schemas e `spec.py`). A API roda sem root, na porta 8000, só na rede interna. A variável `API_TENANT` define o tenant NGSI-LD; vazia, usa o tenant padrão.

Os testes rodam em um container na mesma rede, no perfil `test`:

```bash
docker compose --profile test run --rm --build api-tests
```

## Teste de fumaça

```bash
./smoke-test.sh
```

O script usa o tenant `smoketest` e remove tudo o que cria. Ele verifica:

- todos os serviços `healthy` e nenhuma porta publicada;
- uma medição MQTT passa pela IoT Agent e chega ao Orion-LD;
- uma assinatura leva o histórico do Orion-LD ao QuantumLeap e ao CrateDB;
- os 17 exemplos de `pkg/` entram por upsert em lote, voltam equivalentes na leitura e respondem às consultas por categoria, relacionamento, distância e janela de datas.

## Servidor de contextos

O serviço `context` serve os arquivos `.jsonld` de `pkg/` em `http://context/`. Os outros arquivos retornam 404. Ao servir, o nginx troca dois endereços que a rede interna não alcança:

```
Endereço no arquivo                                 Endereço servido
--------------------------------------------------  -------------------------------------------
https://example.org/natal/natal-context.jsonld      http://context/natal-context.jsonld
https://smartdatamodels.org/context.jsonld          http://context/ctx/sdm-merged-offline.jsonld
```

O namespace `https://example.org/natal/ns#` não muda, porque identifica os termos e não é baixado. Para consultar com o contexto do projeto, envie o cabeçalho `Link: <http://context/natal-context.jsonld>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"`.

## Versões

```
Serviço    Imagem                              Variável
---------  ----------------------------------  -----------------
Orion-LD   quay.io/fiware/orion-ld:1.12.0      ORION_LD_VERSION
MongoDB    mongo:7.0.48                        MONGO_VERSION
Mosquitto  eclipse-mosquitto:2.0.22            MOSQUITTO_VERSION
IoT Agent  telefonicaiot/iotagent-json:3.14.0  IOTA_JSON_VERSION
CrateDB    crate:6.5.1                         CRATE_VERSION
QL         orchestracities/quantumleap:1.0.0   QUANTUMLEAP_VERSION
nginx      nginx:1.30.6-alpine                 NGINX_VERSION
```

O CrateDB exige `vm.max_map_count` de pelo menos 262144 no host (`sysctl vm.max_map_count`). O heap do CrateDB é definido por `CRATE_HEAP_SIZE` (padrão `1g`).

## Decisões e ressalvas

- **Orion-LD com `-mongocOnly`.** O driver padrão do Orion-LD usa o comando `OP_QUERY`, que o MongoDB removeu na versão 6.0. Com o driver padrão, o Orion-LD termina ao iniciar (`Unsupported OP_QUERY command: listDatabases`). A opção `-mongocOnly` desliga esse driver, usa só o driver C oficial (`mongoc`) e ativa a implementação nova das operações NGSI-LD, que o Orion-LD chama de experimental. A alternativa era o MongoDB 4.4 ou 5.0, que não têm suporte desde 2024.
- **`-dbhost` no lugar de `-dbURI`.** Na versão 1.12.0, o valor de `-dbURI` chega com um espaço no início e o Orion-LD o rejeita (`Invalid URI scheme " mongodb://"`).
- **MongoDB sem autenticação.** O banco só é acessível pela rede interna. Ative a autenticação antes de expor o ambiente.
- **Core context.** Ao iniciar, o Orion-LD tenta baixar o core context NGSI-LD da internet. Sem acesso, ele usa a cópia embutida e registra erros no log. O comportamento é esperado.
- **Mosquitto sem autenticação.** O broker aceita conexões anônimas e só é acessível pela rede interna. A autenticação entra na TASK-11, junto dos simuladores.
- **Contexto da IoT Agent.** A IoT Agent envia as medições com `Content-Type: application/ld+json` e precisa de `IOTA_JSON_LD_CONTEXT`. Sem ela, o Orion-LD recusa o upsert (`no @context in payload`). O valor padrão é o core context `v1.8`, que o Orion-LD tem embutido e por isso não precisa baixar. Outro endereço de core context faz o Orion-LD tentar baixá-lo e falhar.
- **AMQP desligado.** A IoT Agent tenta conectar a um AMQP local se ele não for desligado (`IOTA_AMQP_DISABLED`).
- **Provisionamento na IoT Agent.** O grupo de serviço precisa de `resource: /iot/json`, e o dispositivo precisa da `apikey` do grupo. Sem isso, a IoT Agent não encontra o dispositivo (`MEASURES-004: Device not found`). O tópico MQTT é `/<apikey>/<device_id>/attrs`. O `fiware-service` do provisionamento vira o tenant NGSI-LD (`NGSILD-Tenant`) no Orion-LD.
- **IoT Agent 3.14.** A conexão com o MongoDB usa `IOTA_MONGO_URI`. As variáveis separadas de host, porta e banco não são mais aceitas.
- **CrateDB sem senha.** O QuantumLeap usa o usuário padrão `crate`, sem senha, e o banco só é acessível pela rede interna.
- **Tipo das colunas no QuantumLeap.** O QuantumLeap cria cada coluna com o tipo do valor da primeira notificação e não o muda depois. Um valor `25.0` chega em JSON como `25`, e a coluna vira `bigint`. Os valores seguintes, como `26.5`, são truncados para `26`. Isso afeta medições como `precipitation` (TASK-13). A correção fica para a TASK-13.
- **Remoção no QuantumLeap.** `DELETE /v2/types/<tipo>` apaga as linhas, mas mantém a tabela e o tipo das colunas. Para recriar uma tabela, remova-a no CrateDB (`DROP TABLE mt<tenant>.et<tipo>`) e apague as linhas dela em `doc.md_ets_metadata`.
- **Consulta por data no Orion-LD.** O Orion-LD 1.12 guarda um valor `{"@type": "DateTime", "@value": "..."}` como objeto e não compara datas como datas. Use `q=startDate[@value]>="2026-12-20T00:00:00Z"`, com a data entre aspas. A comparação é de texto e só respeita a ordem do tempo porque todas as datas estão em UTC, no mesmo formato.
- **`GET /ngsi-ld/v1/types` trava com tenant vazio.** No Orion-LD 1.12 com `-mongocOnly`, a rota não responde quando o tenant existe mas não tem entidades, inclusive no tenant padrão. Com entidades, ela responde normalmente. Evite essa rota ou use limite de tempo.
- **Não apague o banco de um tenant com o Orion-LD rodando.** O Orion-LD guarda em memória que o tenant existe e não recria os índices, entre eles o geográfico. As consultas por distância passam a falhar. Para limpar, remova as entidades pela API ou reinicie o Orion-LD depois.
- **Listas de um elemento.** O Orion-LD grava e devolve uma lista de um elemento como valor simples: `["restaurant"]` volta como `"restaurant"`. A API devolve esses atributos como lista de novo, de acordo com o `spec.py`.
- **`observedAt` com milissegundos.** O Orion-LD devolve `2026-12-20T22:00:00Z` como `2026-12-20T22:00:00.000Z`. É o mesmo instante.
