### Hotel

Estabelecimento de hospedagem. Dados estáticos; a disponibilidade fica em RoomAvailability.

- Origem: Próprio (não há modelo oficial)
- Id: `urn:ngsi-ld:Hotel:<slug>`

```
Atributo      Tipo NGSI-LD  Tipo de dado                                  Obrig.  Origem
------------  ------------  --------------------------------------------  ------  ------
name          Property      texto                                         Sim     SDM
location      GeoProperty   GeoJSON Point                                 Sim     CORE
address       Property      objeto                                        Sim     SDM
dataOwner     Property      texto                                         Sim     EXT
category      Property      enum(hotel, inn, resort, hostel, apartHotel)  Não     EXT
starRating    Property      inteiro [1..5]                                Não     EXT
checkInTime   Property      texto                                         Não     EXT
checkOutTime  Property      texto                                         Não     EXT
amenities     Property      lista de enum                                 Não     EXT
contactPoint  Property      objeto                                        Não     SDM
description   Property      texto                                         Não     SDM
source        Property      texto                                         Não     SDM
```

Descrições dos atributos:

- `name`: Nome do hotel.
- `location`: Ponto GeoJSON [longitude, latitude], WGS84.
- `address`: Endereço postal (addressLocality, streetAddress, postalCode, addressCountry).
- `dataOwner`: Identificador opaco do dono do registro (claim do token no Keycloak). Preenchido pela API a partir do token; o valor enviado pelo cliente é ignorado.
- `category`: Tipo de hospedagem.
- `starRating`: Classificação em estrelas.
- `checkInTime`: Horário de check-in, HH:MM.
- `checkOutTime`: Horário de check-out, HH:MM.
- `amenities`: Comodidades.
- `contactPoint`: Contato comercial do estabelecimento (telephone, email, url). Nunca dados de pessoa física.
- `description`: Texto descritivo. Tratado como entrada não confiável pela LLM.
- `source`: Origem do dado (URL ou texto).

### RoomType

Tipo de quarto de um hotel, com capacidade e quantidade total de unidades.

- Origem: Próprio
- Id: `urn:ngsi-ld:RoomType:<hotel>:<tipo>`

```
Atributo          Tipo NGSI-LD  Tipo de dado   Obrig.  Origem
----------------  ------------  -------------  ------  ------
name              Property      texto          Sim     SDM
refHotel          Relationship  URI → Hotel    Sim     EXT
dataOwner         Property      texto          Sim     EXT
maxAdults         Property      inteiro [1..]  Sim     EXT
maxChildren       Property      inteiro [0..]  Sim     EXT
totalUnits        Property      inteiro [1..]  Sim     EXT
bedConfiguration  Property      texto          Não     EXT
description       Property      texto          Não     SDM
```

Descrições dos atributos:

- `name`: Nome do tipo de quarto.
- `refHotel`: Referência a Hotel.
- `dataOwner`: Identificador opaco do dono do registro (claim do token no Keycloak). Preenchido pela API a partir do token; o valor enviado pelo cliente é ignorado.
- `maxAdults`: Máximo de adultos por unidade.
- `maxChildren`: Máximo de crianças por unidade.
- `totalUnits`: Unidades deste tipo no hotel.
- `bedConfiguration`: Descrição das camas.
- `description`: Texto descritivo. Tratado como entrada não confiável pela LLM.

### RoomAvailability

Disponibilidade agregada de um tipo de quarto em uma noite. Não contém hóspede nem reserva.

- Origem: Próprio
- Id: `urn:ngsi-ld:RoomAvailability:<hotel>:<tipo>:<AAAAMMDD>`

```
Atributo        Tipo NGSI-LD  Tipo de dado    Obrig.  Origem
--------------  ------------  --------------  ------  ------
refHotel        Relationship  URI → Hotel     Sim     EXT
refRoomType     Relationship  URI → RoomType  Sim     EXT
dataOwner       Property      texto           Sim     EXT
stayDate        Property      Date            Sim     EXT
availableUnits  Property      inteiro [0..]   Sim     EXT
pricePerNight   Property      número [0..]    Sim     EXT
minimumStay     Property      inteiro [1..]   Não     EXT
```

- `pricePerNight` exige sub-atributo `currency` (ISO 4217, ex.: BRL).
- Regra: availableUnits <= totalUnits do RoomType referenciado.
- Regra: refHotel de RoomAvailability = refHotel do RoomType referenciado.
- Regra: o id contém hotel, tipo e data de stayDate.

Descrições dos atributos:

- `refHotel`: Referência a Hotel.
- `refRoomType`: Referência a RoomType.
- `dataOwner`: Identificador opaco do dono do registro (claim do token no Keycloak). Preenchido pela API a partir do token; o valor enviado pelo cliente é ignorado.
- `stayDate`: Noite a que a disponibilidade se refere (Date).
- `availableUnits`: Unidades livres na noite.
- `pricePerNight`: Preço por unidade e noite. Sub-atributo currency obrigatório (ISO 4217).
- `minimumStay`: Mínimo de noites.

### Restaurant

Restaurante, bar ou similar, com ocupação atual.

- Origem: Próprio (não há modelo oficial)
- Id: `urn:ngsi-ld:Restaurant:<slug>`

```
Atributo                   Tipo NGSI-LD  Tipo de dado                    Obrig.  Origem
-------------------------  ------------  ------------------------------  ------  ------
name                       Property      texto                           Sim     SDM
location                   GeoProperty   GeoJSON Point                   Sim     CORE
address                    Property      objeto                          Sim     SDM
dataOwner                  Property      texto                           Sim     EXT
capacity                   Property      inteiro [1..]                   Sim     SDM
occupancy                  Property      inteiro [0..]                   Sim     SDM
availabilityLevel          Property      enum(available, limited, full)  Não     EXT
cuisine                    Property      lista de texto                  Não     EXT
priceRange                 Property      texto                           Não     SDM
openingHoursSpecification  Property      objeto                          Não     SDM
contactPoint               Property      objeto                          Não     SDM
description                Property      texto                           Não     SDM
source                     Property      texto                           Não     SDM
```

- `occupancy` exige `observedAt` no atributo.
- Regra: occupancy <= capacity.
- Regra: availabilityLevel coerente com a razão occupancy/capacity (limiares a definir na API).

Descrições dos atributos:

- `name`: Nome do estabelecimento.
- `location`: Ponto GeoJSON [longitude, latitude], WGS84.
- `address`: Endereço postal (addressLocality, streetAddress, postalCode, addressCountry).
- `dataOwner`: Identificador opaco do dono do registro (claim do token no Keycloak). Preenchido pela API a partir do token; o valor enviado pelo cliente é ignorado.
- `capacity`: Lugares totais.
- `occupancy`: Lugares ocupados agora. Exige observedAt no atributo.
- `availabilityLevel`: Derivado de occupancy/capacity (limiares configuráveis na API).
- `cuisine`: Tipos de cozinha (texto livre).
- `priceRange`: Faixa de preço, de $ a $$$$.
- `openingHoursSpecification`: Lista de {dayOfWeek[], opens, closes}.
- `contactPoint`: Contato comercial do estabelecimento (telephone, email, url). Nunca dados de pessoa física.
- `description`: Texto descritivo. Tratado como entrada não confiável pela LLM.
- `source`: Origem do dado (URL ou texto).

### Event

Evento de qualquer porte, de apresentação em bar a congresso. Também representa restrição de banho (category bathingRestriction).

- Origem: SDM dataModel.TourismDestinations/Event (perfil + extensões)
- Id: `urn:ngsi-ld:Event:<slug>`

```
Atributo                 Tipo NGSI-LD  Tipo de dado                    Obrig.  Origem
-----------------------  ------------  ------------------------------  ------  ------
name                     Property      texto                           Sim     SDM
startDate                Property      DateTime                        Sim     SDM
endDate                  Property      DateTime                        Sim     SDM
location                 GeoProperty   GeoJSON Point                   Sim     CORE
address                  Property      objeto                          Sim     SDM
dataOwner                Property      texto                           Sim     EXT
category                 Property      lista de enum                   Sim     SDM
eventScale               Property      enum(small, medium, large)      Cond.   EXT
eventStatus              Property      lista de enum                   Sim     SDM
venueName                Property      texto                           Não     EXT
maximumAttendeeCapacity  Property      inteiro [1..]                   Não     SDM
isAccessibleForFree      Property      booleano                        Não     SDM
eventPriceFrom           Property      número [0..]                    Não     SDM
eventPriceTo             Property      número [0..]                    Não     SDM
audience                 Property      lista de enum                   Não     SDM
wheelChairAccessible     Property      booleano                        Não     SDM
webSite                  Property      texto                           Não     SDM
refPointOfInterest       Relationship  URI → Beach ou PointOfInterest  Cond.   SDM
description              Property      texto                           Não     SDM
```

- `eventScale`: obrigatório exceto se category contém bathingRestriction.
- `eventPriceFrom` exige sub-atributo `currency` (ISO 4217, ex.: BRL).
- `eventPriceTo` exige sub-atributo `currency` (ISO 4217, ex.: BRL).
- `refPointOfInterest`: obrigatório se category contém bathingRestriction (aponta a Beach); O nos demais.
- Regra: endDate > startDate.
- Regra: category contém bathingRestriction => refPointOfInterest aponta uma Beach e eventScale é dispensado.
- Regra: eventScale obrigatório nos demais eventos.

Descrições dos atributos:

- `name`: Nome do evento.
- `startDate`: Início (DateTime, UTC).
- `endDate`: Fim (DateTime, UTC), posterior a startDate.
- `location`: Ponto GeoJSON [longitude, latitude], WGS84.
- `address`: Endereço postal (addressLocality, streetAddress, postalCode, addressCountry).
- `dataOwner`: Identificador opaco do dono do registro (claim do token no Keycloak). Preenchido pela API a partir do token; o valor enviado pelo cliente é ignorado.
- `category`: Categorias do evento; ao menos uma. bathingRestriction é extensão do projeto.
- `eventScale`: Porte do evento.
- `eventStatus`: Situação; lista com um valor.
- `venueName`: Nome do local (bar, teatro, praça).
- `maximumAttendeeCapacity`: Público máximo.
- `isAccessibleForFree`: Entrada gratuita.
- `eventPriceFrom`: Menor preço. Com currency.
- `eventPriceTo`: Maior preço. Com currency.
- `audience`: Público-alvo.
- `wheelChairAccessible`: Acessível a cadeirantes.
- `webSite`: Site oficial.
- `refPointOfInterest`: Praia afetada (restrição) ou local do evento. Perfil: um único alvo.
- `description`: Texto descritivo. Tratado como entrada não confiável pela LLM.

### Beach

Praia. Ponto central; o estado de banho fica em BathingStatus.

- Origem: SDM dataModel.PointOfInterest/Beach (perfil + extensão)
- Id: `urn:ngsi-ld:Beach:<slug>`

```
Atributo           Tipo NGSI-LD  Tipo de dado                                     Obrig.  Origem
-----------------  ------------  -----------------------------------------------  ------  ------
name               Property      texto                                            Sim     SDM
location           GeoProperty   GeoJSON Point                                    Sim     CORE
dataOwner          Property      texto                                            Sim     EXT
beachType          Property      lista de enum                                    Não     SDM
facilities         Property      lista de enum                                    Não     SDM
accessType         Property      lista de enum                                    Não     SDM
length             Property      número [0..]                                     Não     SDM
width              Property      número [0..]                                     Não     SDM
occupationRate     Property      enum(high, medium, low, none)                    Não     SDM
refWeatherStation  Relationship  URI → PointOfInterest (category weatherStation)  Sim     EXT
address            Property      objeto                                           Não     SDM
description        Property      texto                                            Não     SDM
source             Property      texto                                            Não     SDM
```

Descrições dos atributos:

- `name`: Nome da praia.
- `location`: Ponto GeoJSON [longitude, latitude], WGS84.
- `dataOwner`: Identificador opaco do dono do registro (claim do token no Keycloak). Preenchido pela API a partir do token; o valor enviado pelo cliente é ignorado.
- `beachType`: Tipos de praia.
- `facilities`: Facilidades.
- `accessType`: Formas de acesso.
- `length`: Comprimento, metros.
- `width`: Largura, metros.
- `occupationRate`: Lotação típica.
- `refWeatherStation`: Estação cujas chuvas valem para esta praia (extensão do projeto).
- `address`: Endereço postal (addressLocality, streetAddress, postalCode, addressCountry).
- `description`: Texto descritivo. Tratado como entrada não confiável pela LLM.
- `source`: Origem do dado (URL ou texto).

### PointOfInterest

Ponto de coleta de balneabilidade ou estação meteorológica, conforme category.

- Origem: SDM dataModel.PointOfInterest/PointOfInterest (perfil)
- Id: `urn:ngsi-ld:PointOfInterest:<slug>`

```
Atributo     Tipo NGSI-LD  Tipo de dado   Obrig.  Origem
-----------  ------------  -------------  ------  ------
name         Property      texto          Sim     SDM
location     GeoProperty   GeoJSON Point  Sim     CORE
dataOwner    Property      texto          Sim     EXT
category     Property      lista de enum  Sim     SDM
refBeach     Relationship  URI → Beach    Cond.   EXT
description  Property      texto          Não     SDM
```

- `refBeach`: obrigatório se category contém bathingSamplingPoint.
- Regra: bathingSamplingPoint => refBeach presente.

Descrições dos atributos:

- `name`: Nome do ponto.
- `location`: Ponto GeoJSON [longitude, latitude], WGS84.
- `dataOwner`: Identificador opaco do dono do registro (claim do token no Keycloak). Preenchido pela API a partir do token; o valor enviado pelo cliente é ignorado.
- `category`: Função do ponto (extensão de valores do projeto).
- `refBeach`: Praia a que o ponto de coleta pertence.
- `description`: Texto descritivo. Tratado como entrada não confiável pela LLM.

### WaterQualityObserved

Medição de uma sonda em um ponto de coleta. Estimativa, não laudo.

- Origem: SDM dataModel.WaterQuality/WaterQualityObserved (perfil)
- Id: `urn:ngsi-ld:WaterQualityObserved:<ponto>:<AAAAMMDDTHHMMSSZ>`

```
Atributo            Tipo NGSI-LD  Tipo de dado                                  Obrig.  Origem
------------------  ------------  --------------------------------------------  ------  ------
dateObserved        Property      DateTime                                      Sim     SDM
location            GeoProperty   GeoJSON Point                                 Sim     CORE
refPointOfInterest  Relationship  URI → PointOfInterest (bathingSamplingPoint)  Sim     SDM
dataOwner           Property      texto                                         Sim     EXT
turbidity           Property      número [0..]                                  Sim     SDM
salinity            Property      número [0..]                                  Sim     SDM
temperature         Property      número                                        Não     SDM
pH                  Property      número [0..14]                                Não     SDM
O2                  Property      número [0..]                                  Não     SDM
source              Property      texto                                         Não     SDM
```

Descrições dos atributos:

- `dateObserved`: Instante da medição (DateTime, UTC).
- `location`: Ponto GeoJSON [longitude, latitude], WGS84.
- `refPointOfInterest`: Ponto de coleta.
- `dataOwner`: Identificador opaco do dono do registro (claim do token no Keycloak). Preenchido pela API a partir do token; o valor enviado pelo cliente é ignorado.
- `turbidity`: Turbidez, NTU.
- `salinity`: Salinidade, PSU.
- `temperature`: Temperatura da água, °C.
- `pH`: pH.
- `O2`: Oxigênio dissolvido, mg/L.
- `source`: Origem do dado (URL ou texto).

### WeatherObserved

Observação de uma estação meteorológica.

- Origem: SDM dataModel.Weather/WeatherObserved (perfil + extensão)
- Id: `urn:ngsi-ld:WeatherObserved:<estacao>:<AAAAMMDDTHHMMSSZ>`

```
Atributo                      Tipo NGSI-LD  Tipo de dado                            Obrig.  Origem
----------------------------  ------------  --------------------------------------  ------  ------
dateObserved                  Property      DateTime                                Sim     SDM
location                      GeoProperty   GeoJSON Point                           Sim     CORE
refPointOfInterest            Relationship  URI → PointOfInterest (weatherStation)  Sim     SDM
dataOwner                     Property      texto                                   Sim     EXT
precipitation                 Property      número [0..]                            Sim     SDM
precipitationIntervalMinutes  Property      número [1..]                            Sim     EXT
temperature                   Property      número                                  Não     SDM
relativeHumidity              Property      número [0..1]                           Não     SDM
source                        Property      texto                                   Não     SDM
```

Descrições dos atributos:

- `dateObserved`: Instante da observação (DateTime, UTC).
- `location`: Ponto GeoJSON [longitude, latitude], WGS84.
- `refPointOfInterest`: Estação.
- `dataOwner`: Identificador opaco do dono do registro (claim do token no Keycloak). Preenchido pela API a partir do token; o valor enviado pelo cliente é ignorado.
- `precipitation`: Chuva acumulada no intervalo da observação, mm (L/m²).
- `precipitationIntervalMinutes`: Duração do intervalo da precipitação, minutos. Necessário para somar 24 h e 72 h.
- `temperature`: Temperatura do ar, °C.
- `relativeHumidity`: Umidade relativa, fração de 0 a 1.
- `source`: Origem do dado (URL ou texto).

### BathingReport

Laudo oficial de balneabilidade de uma praia ou ponto, com validade.

- Origem: Próprio
- Id: `urn:ngsi-ld:BathingReport:<praia>:<numero>`

```
Atributo            Tipo NGSI-LD  Tipo de dado                                  Obrig.  Origem
------------------  ------------  --------------------------------------------  ------  ------
refBeach            Relationship  URI → Beach                                   Sim     EXT
refPointOfInterest  Relationship  URI → PointOfInterest (bathingSamplingPoint)  Não     SDM
dataOwner           Property      texto                                         Sim     EXT
result              Property      enum(proper, improper)                        Sim     EXT
collectionDate      Property      DateTime                                      Sim     EXT
validFrom           Property      DateTime                                      Sim     EXT
validUntil          Property      DateTime                                      Sim     EXT
issuingAuthority    Property      texto                                         Sim     EXT
reportNumber        Property      texto                                         Sim     EXT
escherichiaColi     Property      número [0..]                                  Não     SDM
enterococci         Property      número [0..]                                  Não     SDM
documentURL         Property      texto                                         Não     EXT
```

- Regra: collectionDate <= validFrom < validUntil.
- Regra: o laudo só prevalece entre validFrom e validUntil (política na TASK-10).

Descrições dos atributos:

- `refBeach`: Referência a Beach.
- `refPointOfInterest`: Ponto de coleta, quando o laudo é por ponto.
- `dataOwner`: Identificador opaco do dono do registro (claim do token no Keycloak). Preenchido pela API a partir do token; o valor enviado pelo cliente é ignorado.
- `result`: Resultado do laudo.
- `collectionDate`: Coleta da amostra.
- `validFrom`: Início da validade.
- `validUntil`: Fim da validade.
- `issuingAuthority`: Órgão emissor.
- `reportNumber`: Número do laudo.
- `escherichiaColi`: E. coli, NMP/100 mL.
- `enterococci`: Enterococos, NMP/100 mL.
- `documentURL`: Link do documento.

### BathingStatus

Estado de banho consolidado de uma praia; uma entidade por praia, atualizada no lugar.

- Origem: Próprio
- Id: `urn:ngsi-ld:BathingStatus:<praia>`

```
Atributo            Tipo NGSI-LD  Tipo de dado                                  Obrig.  Origem
------------------  ------------  --------------------------------------------  ------  ------
refBeach            Relationship  URI → Beach                                   Sim     EXT
dataOwner           Property      texto                                         Sim     EXT
status              Property      enum(proper, improper, alert, indeterminate)  Sim     EXT
basis               Property      enum(report, estimate, none)                  Sim     EXT
computedAt          Property      DateTime                                      Sim     EXT
validUntil          Property      DateTime                                      Cond.   EXT
refBathingReport    Relationship  URI → BathingReport                           Cond.   EXT
estimatedRiskLevel  Property      enum(low, moderate, high)                     Cond.   EXT
rainfall24h         Property      número [0..]                                  Não     EXT
rainfall72h         Property      número [0..]                                  Não     EXT
```

- `validUntil`: obrigatório se basis diferente de none.
- `refBathingReport`: obrigatório se basis = report.
- `estimatedRiskLevel`: obrigatório se basis = estimate.
- Regra: basis = none => status = indeterminate.
- Regra: basis = report => status igual ao result do laudo (proper ou improper).
- Regra: basis = estimate => status diferente de proper sem laudo vigente é decisão da TASK-10.

Descrições dos atributos:

- `refBeach`: Referência a Beach.
- `dataOwner`: Identificador opaco do dono do registro (claim do token no Keycloak). Preenchido pela API a partir do token; o valor enviado pelo cliente é ignorado.
- `status`: Estado de banho.
- `basis`: Base do estado: laudo, estimativa ou nenhuma.
- `computedAt`: Instante do cálculo.
- `validUntil`: Fim da validade deste estado.
- `refBathingReport`: Laudo que sustenta o estado.
- `estimatedRiskLevel`: Risco estimado. Não é laudo oficial.
- `rainfall24h`: Chuva acumulada em 24 h, mm.
- `rainfall72h`: Chuva acumulada em 72 h, mm.
