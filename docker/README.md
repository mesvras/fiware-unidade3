# Stack Docker

Orion-LD e MongoDB em uma rede interna (`internal: true`). Nenhum serviço publica porta no host e nenhum container acessa a internet.

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
Serviço    Imagem                            Variável
---------  --------------------------------  -----------------
Orion-LD   quay.io/fiware/orion-ld:1.12.0    ORION_LD_VERSION
MongoDB    mongo:7.0.48                      MONGO_VERSION
```

## Decisões e ressalvas

- **Orion-LD com `-mongocOnly`.** O driver padrão do Orion-LD usa o comando `OP_QUERY`, que o MongoDB removeu na versão 6.0. Com o driver padrão, o Orion-LD termina ao iniciar (`Unsupported OP_QUERY command: listDatabases`). A opção `-mongocOnly` desliga esse driver, usa só o driver C oficial (`mongoc`) e ativa a implementação nova das operações NGSI-LD, que o Orion-LD chama de experimental. A alternativa era o MongoDB 4.4 ou 5.0, que não têm suporte desde 2024.
- **`-dbhost` no lugar de `-dbURI`.** Na versão 1.12.0, o valor de `-dbURI` chega com um espaço no início e o Orion-LD o rejeita (`Invalid URI scheme " mongodb://"`).
- **MongoDB sem autenticação.** O banco só é acessível pela rede interna. Ative a autenticação antes de expor o ambiente.
- **Core context.** Ao iniciar, o Orion-LD tenta baixar o core context NGSI-LD da internet. Sem acesso, ele usa a cópia embutida e registra erros no log. O comportamento é esperado.
