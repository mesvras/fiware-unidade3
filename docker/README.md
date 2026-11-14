# Stack Docker

Orion-LD, MongoDB, Mosquitto, IoT Agent JSON, CrateDB e QuantumLeap em uma rede interna (`internal: true`). Nenhum serviço publica porta no host e nenhum container acessa a internet.

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
