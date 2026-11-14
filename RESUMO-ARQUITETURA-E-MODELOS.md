# Resumo: arquitetura e modelos de dados

Data: 2026-11-14. Resume o que foi decidido na conversa sobre a plataforma de turismo e cultura de Natal: escopo, arquitetura (com os Generic Enablers), segurança, modelos de dados e backlog.

## 1. Escopo atual

Plataforma que liga três públicos: governo (incentiva turismo e cultura; precisa de painel de gestão próprio), prestadores (hotéis, bares e restaurantes, produtores culturais de eventos pequenos e grandes) e turistas (geram roteiros e acessam informações via chat com LLM;).

```
Fonte           Dado                                                      Entrada
--------------  --------------------------------------------------------  ----------------------------
Hotéis          disponibilidade agregada por tipo de quarto e noite       API da plataforma
Restaurantes    ocupação atual, capacidade, endereço                      API da plataforma
Eventos         show em bar, congresso, evento comunitário, etc           API da plataforma
Balneabilidade  laudo oficial e estimativa por sondas                     laudo pela API; sondas por MQTT
```

Decisões de escopo:

- Dados simulados, mas no formato real de cada fonte.
- A plataforma só responde consultas de disponibilidade; não há reserva. Guardar disponibilidade agregada.
- A balneabilidade aceita dois formatos de fonte (laudo e estimativa) e consolida em um estado por praia. Laudo válido prevalece; a estimativa não é laudo oficial.
- O turista precisa logar: cadastro próprio ou conta Google.
- Portal de cadastro para prestadores e mapa do turista são itens opcionais ("nice to have").

## 2. Segurança: Keycloak e APISIX

O que foi comparado: Keyrock (FIWARE) com Wilma (PEP proxy) e, para regras mais finas, AuthZForce, contra Keycloak com um gateway.

```
Aspecto                   Keyrock + Wilma                              Keycloak + APISIX
------------------------  -------------------------------------------  --------------------------------------------
Integração com FIWARE     nativa                                       por JWT/OIDC, sem GE específico
Login social (Google)     não nativo                                   suportado
Autorização granular      nível 2 (verbo e caminho); nível 3 exige     papéis, grupos/atributos e authorization
                          AuthZForce e customização do PEP             services
Uso fora do FIWARE        pequeno                                      amplo
```

Decisão: **Keycloak como provedor de identidade e APISIX como gateway (PEP)**.

Pontos de projeto:

- As requisições do usuário chegam ao gateway no perímetro; ele valida o JWT (localmente, por JWKS) e autoriza por papel, rota e verbo. A validação local limita a revogação ao tempo de vida do token.
- O gateway faz só controle grosso. As regras de controle de acesso são aplicadas pela API, validando uma claim do token com o campo `dataOwner` do registro.
- Clientes: público com PKCE (web e mobile) e confidencial com `client_credentials` (simuladores e fontes de laudo).
- Login Google exige e-mail verificado e não faz vínculo automático de contas.
- Controle de abuso: verificação de e-mail, captcha, limite por usuário, cota de custo da LLM.

Papéis: turista, gestor de governo, analista de governo, hotelaria, bares e restaurantes, produtor cultural e fonte de dados (acesso de máquina).

## 3. Arquitetura de comunicações

Apenas o perímetro é exposto. A API da plataforma é a única com permissão de escrita no Orion-LD.

```
EXTERNO      Governo · Clientes de API · Turista · Google
                |
PERÍMETRO    Keycloak · APISIX · Grafana
                |
INTERNO      API da plataforma ──► Orion-LD (+ MongoDB)
             Roteiros (LLM) ──► Provedor de LLM (externo, HTTPS)
             Simuladores ─MQTT─► Mosquitto ─► IoT Agent JSON ─NGSI-LD─► Orion-LD
             Orion-LD ─notifica─► QuantumLeap ─► CrateDB
```

```
De                  Para               Protocolo / conteúdo
------------------  -----------------  --------------------------------------
Governo             Grafana            HTTPS
Clientes de API     APISIX             JWT Bearer
Turista             APISIX             JWT Bearer
Google              Keycloak           OIDC
APISIX              Keycloak           JWKS · UMA
APISIX              API da plataforma  REST · JWT
APISIX              Roteiros (LLM)     HTTPS · JWT
Roteiros            API da plataforma  consulta
Roteiros            Provedor de LLM    HTTPS
Grafana             API da plataforma  consulta
API da plataforma   Orion-LD           NGSI-LD
API da plataforma   QuantumLeap        consulta de histórico
Simuladores         Mosquitto          MQTT
Mosquitto           IoT Agent JSON     MQTT
IoT Agent JSON      Orion-LD           NGSI-LD
Orion-LD            QuantumLeap        notificação
QuantumLeap         CrateDB            gravação
```

### Componentes e Generic Enablers

```
Componente           Tipo                       Função
-------------------  -------------------------  ---------------------------------------------------
Orion-LD             GE FIWARE (Context Broker) estado atual das entidades, NGSI-LD
IoT Agent JSON       GE FIWARE                  MQTT das sondas e da estação para NGSI-LD
QuantumLeap          GE FIWARE                  histórico das entidades
MongoDB              apoio do Orion-LD          armazenamento do estado atual
CrateDB              apoio do QuantumLeap       série temporal
Mosquitto            broker MQTT                transporte das medições
Keycloak             fora do FIWARE             identidade, papéis, login Google
APISIX               fora do FIWARE             gateway e PEP
Grafana              fora do FIWARE             painel do governo
API da plataforma    própria                    cadastro, consulta, validação, consolidação
Serviço de roteiros  próprio                    chat do turista e chamada à LLM
```


## 4. Modelos de dados escolhidos

Onze tipos NGSI-LD: cinco do Smart Data Models (SDM), com perfil e extensões, e seis customizados. Não existe modelo oficial de hotel, restaurante nem de estado de banho.

```
Modelo                Fonte                                             Extensões do projeto
--------------------  ------------------------------------------------  ------------------------------------------
Beach                 SDM PointOfInterest/Beach                         refWeatherStation, dataOwner
PointOfInterest       SDM PointOfInterest/PointOfInterest               category bathingSamplingPoint e weatherStation,
                                                                        refBeach, dataOwner
WaterQualityObserved  SDM WaterQuality/WaterQualityObserved             dataOwner; turbidity e salinity obrigatórias
WeatherObserved       SDM Weather/WeatherObserved                       precipitationIntervalMinutes, dataOwner
Event                 SDM TourismDestinations/Event                     eventScale, venueName, bathingRestriction,
                                                                        dataOwner
Hotel                 Customizado                                       —
RoomType              Customizado                                       —
RoomAvailability      Customizado                                       —
Restaurant            Customizado (termos de PointOfInterest do SDM)    —
BathingReport         Customizado                                       —
BathingStatus         Customizado                                       —
```

Relacionamentos (o filho aponta para o pai; o pai não guarda lista de filhos):

```
Origem                Atributo            Destino
--------------------  ------------------  -----------------------------------------
RoomType              refHotel            Hotel
RoomAvailability      refHotel            Hotel
RoomAvailability      refRoomType         RoomType
Event                 refPointOfInterest  Beach ou PointOfInterest
Beach                 refWeatherStation   PointOfInterest (weatherStation)
PointOfInterest       refBeach            Beach
WaterQualityObserved  refPointOfInterest  PointOfInterest (bathingSamplingPoint)
WeatherObserved       refPointOfInterest  PointOfInterest (weatherStation)
BathingReport         refBeach            Beach
BathingReport         refPointOfInterest  PointOfInterest (bathingSamplingPoint)
BathingStatus         refBeach            Beach
BathingStatus         refBathingReport    BathingReport
```

Decisões de modelagem:

- `RoomAvailability` guarda unidades livres e preço por tipo de quarto e noite, sem hóspede nem reserva.
- Restrição de banho é um `Event` com categoria `bathingRestriction`, apontando para a praia.
- `BathingStatus` é uma entidade por praia, atualizada no lugar. Seus campos `status` (`proper`, `improper`, `alert`, `indeterminate`) e `basis` (`report`, `estimate`, `none`) impedem tratar estimativa como laudo.
- Todo registro de prestador, governo ou fonte tem `dataOwner`, preenchido pela API a partir do token.
- Datas em UTC com valor tipado (`DateTime`, `Date`); coordenadas `[longitude, latitude]`; preços com sub-atributo `currency`; `occupancy` com `observedAt`.


## 5. Backlog alternativo

Aba "Product Backlog - Alternativa" da planilha de planejamento: 31 tarefas em três sprints (27 h, 29 h e 27 h) e 2 itens opcionais (portal de cadastro 8 h, mapa do turista 6 h). As abas originais não foram alteradas. A TASK-03 (modelos de dados) está concluída.

## 6. Pontos em aberto

- Trocar o endereço provisório `https://example.org/natal/` do `@context` pelo domínio real.
- Confirmar com os dados reais as unidades de turbidez (NTU) e salinidade (PSU).
- Definir na TASK-10 qual `status` uma estimativa produz e os limiares de `availabilityLevel` dos restaurantes.
- Decidir se os valores extras de enum (`bathingRestriction`, `bathingSamplingPoint`, `weatherStation`) ficam como extensão do projeto; um validador estrito do SDM os rejeitaria.
- Confirmar se QuantumLeap e CrateDB continuam no escopo.
- Subir um Orion-LD e testar upsert e consultas sobre os exemplos.
