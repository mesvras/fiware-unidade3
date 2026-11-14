# Plataforma para os setores de turismo cultura de Natal

Plataforma baseada em FIWARE que reúne, dados de hospedagem, restaurantes, eventos e balneabilidade de praias de Natal/RN. Integra três atores principa o governo; os prestadores de serviço e produtores culturais da cidade; e os turistas, visitantes e moradores que desejam estar por dentro da programação da cidade e exercerem seu direito à cidade.

## O que faz

- **Governo** acompanha, em um painel próprio, a disponibilidade e a ocupação de hotéis e restaurantes, a agenda de eventos e o estado de banho de cada praia. Pode utilizar da inteligência fornecida pela plataforma para tomar decisões de incentivo aos setores da cultura e do turismo. 
- **Prestadores** (hotelaria, bares e restaurantes, produtores culturais) mantêm os próprios dados pela API. Podem dar visibilidade aos seus trabalhos e negócios que movimentam e dão vida à cena cultural e de turismo de Natal.
- **Turistas** entram por cadastro ou login social e podem montar seus roteiros de turismo e se informar dos eventos e pontos de interesse disponíveis e mais procurados da cidade, através de uma interface possibilitada via LLM.

A plataforma gera roteiros e responde consultas informações como disponibilidade e informaoes de contato, não realiza reservas nem pagamentos.
 
## Fontes de dados

```
Fonte          Conteúdo                                                  Como entra
-------------  --------------------------------------------------------  ----------------------------------
Hotéis         disponibilidade agregada por tipo de quarto e noite,      API da plataforma
               capacidade (adultos e crianças), preço e endereço
Restaurantes   ocupação atual, capacidade, horário e endereço            API da plataforma
Eventos        de show em bar a congresso, com local, data e porte       API da plataforma
Balneabilidade laudo oficial (com validade) e estimativa por sondas      laudo pela API; sondas por MQTT
```

Os dados são simulados, mas seguem o formato real de cada fonte.


## Arquitetura

O perímetro (Keycloak, APISIX e Grafana) fica exposto, enquanto os demais componentes executam em rede interna.

```
EXTERNO      Governo · Clientes de API · Turista · Google (login social)
                |
PERÍMETRO    Keycloak (identidade, papéis) · APISIX (gateway, valida JWT e papel) · Grafana (painel do governo)
                |
INTERNO      API da plataforma ──► Orion-LD (+ MongoDB)
             (única que escreve)         │ notifica
             Roteiros (LLM) ──► Provedor de LLM (externo)
                                         ▼
             Simuladores ─MQTT─► Mosquitto ─► IoT Agent JSON ─NGSI-LD─► Orion-LD
                                         QuantumLeap ─► CrateDB (histórico)
```

```
Componente           Papel
-------------------  ------------------------------------------------------------------
Orion-LD             Context Broker FIWARE (NGSI-LD): estado atual de todas as entidades
MongoDB              armazenamento do Orion-LD
IoT Agent JSON       converte as mensagens MQTT das sondas e estações em NGSI-LD
Mosquitto            broker MQTT
QuantumLeap          grava o histórico das entidades no CrateDB
CrateDB              série temporal (precipitação acumulada, tendências)
API da plataforma    cadastro e consulta, validação de esquema e do dono do registro
Serviço de roteiros  chat do turista; consulta a API e chama a LLM externa
Keycloak             provedor de identidade (OIDC/OAuth2), papéis, login Google
APISIX               gateway: valida o JWT, autoriza por papel e rota, limita requisições
Grafana              painel de gestão do governo
```

Keycloak e APISIX não são Generic Enablers do FIWARE, mas foram escolhidos no lugar de Keyrock, e APISIX no lugar de Wilma, pelo login social, pela maior granularidade nos recursos de autorização e por serem mais usados fora do ecossistema FIWARE.

## Perfis de acesso

Turista · gestor de governo · analista de governo · hotelaria · bares e restaurantes · produtor cultural · fonte de dados (acesso de máquina).

O APISIX autoriza por papel, rota e verbo. O dono do registro é validado pela API, comparando o token com o campo `dataOwner` da entidade.

## Modelos de dados

Dez tipos de entidade NGSI-LD: cinco do Smart Data Models (com perfil e extensões) e cinco próprios. Restaurantes e bares são `PointOfInterest` com `category` `restaurant` ou `bar`.

```
Origem          Modelos
--------------  ---------------------------------------------------------------------
SDM             Beach, PointOfInterest, WaterQualityObserved, WeatherObserved, Event
Customizados    Hotel, RoomType, RoomAvailability, BathingReport, BathingStatus
```

Detalhes, atributos e relacionamentos em [`docs/modelos.md`](docs/modelos.md). O contexto, o vocabulário com o alinhamento ao schema.org (`Hotel`, `checkInTime`, `checkOutTime`), os schemas e os exemplos ficam em [`pkg/`](pkg/).

## Balneabilidade

Laudo oficial e estimativa por sondas são consolidados em um único `BathingStatus` por praia, com os estados `proper`, `improper`, `alert` e `indeterminate`. Um laudo válido prevalece. A estimativa **não é laudo oficial** e é sempre marcada como tal. Períodos de restrição são registrados como eventos.

## Estrutura do repositório

```
pkg/           @context, vocabulário schema.org, JSON Schemas, exemplos NGSI-LD e validador
docker/        Docker Compose da stack (Orion-LD, MongoDB, Mosquitto, IoT Agent, QuantumLeap, CrateDB, servidor de contextos) e smoke test
api/           API da plataforma
simulators/    simuladores de hotéis, restaurantes, eventos, laudos, sondas e estação
llm/           serviço de roteiros
docs/          arquitetura, modelos e decisões
```

## Como executar

Requisitos: Docker com Compose v2 e `vm.max_map_count` de pelo menos 262144 no host (exigência do CrateDB).

```bash
cd docker
cp .env.example .env
docker compose up -d --wait
./smoke-test.sh
```

A stack sobe Orion-LD, MongoDB, Mosquitto, IoT Agent JSON, CrateDB, QuantumLeap e um servidor de contextos em uma rede interna, sem portas publicadas. As versões ficam fixas no `.env`. O `smoke-test.sh` verifica a comunicação entre os serviços e carrega os exemplos de `pkg/` no Orion-LD. Versões, decisões e limitações conhecidas estão em [`docker/README.md`](docker/README.md).

Keycloak, APISIX e Grafana entram nas TASK-16, TASK-17 e TASK-21.

Para validar os modelos de dados:

```bash
pip install pyld jsonschema
python3 -I pkg/tools/validate.py
```

## Segurança e privacidade

- Apenas o perímetro é exposto; o acesso direto aos serviços internos é bloqueado.
- A API é a única que escreve no Orion-LD.
- Cadastro de turista com verificação de e-mail, proteção contra força bruta e limite de uso por usuário.
- Nenhum identificador do usuário é enviado ao provedor de LLM.
- Textos cadastrados por terceiros (nome e descrição de hotéis, restaurantes e eventos) devem ser tratados como entrada não confiável pela LLM, por causa de injeção de prompt.
- O modelo de hospedagem não guarda hóspedes nem reservas, o que reduz a exposição de dados pessoais (LGPD).
- Segredos ficam fora do repositório.


## Limitações

- Dados simulados; coordenadas e nomes são ilustrativos.
- A estimativa de balneabilidade não substitui o laudo oficial.
- MongoDB, Mosquitto e CrateDB rodam sem autenticação, acessíveis só pela rede interna. A autenticação do Mosquitto entra na TASK-11.

## Licença

A definir.
