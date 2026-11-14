"""Fonte única da verdade dos modelos NGSI-LD da plataforma. build.py e validate.py leem este arquivo."""
NS = "https://example.org/natal/ns#"          # trocar pelo domínio real antes de publicar
CTX_URL = "https://example.org/natal/natal-context.jsonld"
SDM_CTX = "https://smartdatamodels.org/context.jsonld"

# Atributo: (nome, kind, vtype, req, origem, descrição, extras)
# kind: P Property | G GeoProperty | R Relationship
# vtype: string integer number boolean datetime date point object array enum arrayenum uri
# req: 'R' obrigatório | 'O' opcional | 'C:<regra>' condicional
# origem: SDM (termo oficial) | EXT (termo próprio) | CORE
def A(name, kind, vtype, req, origem, desc, **x): return dict(name=name, kind=kind, vtype=vtype, req=req, origem=origem, desc=desc, **x)

OWNER = A("dataOwner","P","string","R","EXT","Identificador opaco do dono do registro (claim do token no Keycloak). Preenchido pela API a partir do token; o valor enviado pelo cliente é ignorado.", pattern=r"^[A-Za-z0-9._:-]{3,64}$")
NAME  = lambda d="Nome do registro.": A("name","P","string","R","SDM",d, minLength=1, maxLength=200)
DESC  = A("description","P","string","O","SDM","Texto descritivo. Tratado como entrada não confiável pela LLM.", maxLength=2000)
SRC   = A("source","P","string","O","SDM","Origem do dado (URL ou texto).")
LOC   = lambda r="R": A("location","G","point",r,"CORE","Ponto GeoJSON [longitude, latitude], WGS84.")
ADDR  = lambda r="R": A("address","P","object",r,"SDM","Endereço postal (addressLocality, streetAddress, postalCode, addressCountry).", keys=["addressLocality","streetAddress","postalCode","addressCountry","addressRegion"], required_keys=["addressLocality"])
CONTACT = A("contactPoint","P","object","O","SDM","Contato comercial do estabelecimento (telephone, email, url). Nunca dados de pessoa física.", keys=["telephone","email","url"])
def REF(name, target, req="R", desc=None): return A(name,"R","uri",req,"EXT" if name not in ("refPointOfInterest",) else "SDM", desc or f"Referência a {target}.", target=target)
OPEN = A("openingHoursSpecification","P","object","O","SDM","Lista de {dayOfWeek[], opens, closes}.", array=True, keys=["dayOfWeek","opens","closes"])

ENTITIES = {}
def E(name, origem, desc, idpat, attrs, rules=()): ENTITIES[name]=dict(name=name, origem=origem, desc=desc, idpat=idpat, attrs=attrs, rules=list(rules))

E("Hotel","Próprio (não há modelo oficial)","Estabelecimento de hospedagem. Dados estáticos; a disponibilidade fica em RoomAvailability.","urn:ngsi-ld:Hotel:<slug>",[
  NAME("Nome do hotel."), LOC(), ADDR(), OWNER,
  A("category","P","enum","O","EXT","Tipo de hospedagem.",enum=["hotel","inn","resort","hostel","apartHotel"]),
  A("starRating","P","integer","O","EXT","Classificação em estrelas.",minimum=1,maximum=5),
  A("checkInTime","P","string","O","EXT","Horário de check-in, HH:MM.",pattern=r"^([01]\d|2[0-3]):[0-5]\d$"),
  A("checkOutTime","P","string","O","EXT","Horário de check-out, HH:MM.",pattern=r"^([01]\d|2[0-3]):[0-5]\d$"),
  A("amenities","P","arrayenum","O","EXT","Comodidades.",enum=["wifi","pool","parking","breakfast","airConditioning","beachfront","accessible"]),
  CONTACT, DESC, SRC])
E("RoomType","Próprio","Tipo de quarto de um hotel, com capacidade e quantidade total de unidades.","urn:ngsi-ld:RoomType:<hotel>:<tipo>",[
  NAME("Nome do tipo de quarto."), REF("refHotel","Hotel"), OWNER,
  A("maxAdults","P","integer","R","EXT","Máximo de adultos por unidade.",minimum=1),
  A("maxChildren","P","integer","R","EXT","Máximo de crianças por unidade.",minimum=0),
  A("totalUnits","P","integer","R","EXT","Unidades deste tipo no hotel.",minimum=1),
  A("bedConfiguration","P","string","O","EXT","Descrição das camas."), DESC])
E("RoomAvailability","Próprio","Disponibilidade agregada de um tipo de quarto em uma noite. Não contém hóspede nem reserva.","urn:ngsi-ld:RoomAvailability:<hotel>:<tipo>:<AAAAMMDD>",[
  REF("refHotel","Hotel"), REF("refRoomType","RoomType"), OWNER,
  A("stayDate","P","date","R","EXT","Noite a que a disponibilidade se refere (Date)."),
  A("availableUnits","P","integer","R","EXT","Unidades livres na noite.",minimum=0),
  A("pricePerNight","P","number","R","EXT","Preço por unidade e noite. Sub-atributo currency obrigatório (ISO 4217).",minimum=0,subattrs={"currency":dict(pattern=r"^[A-Z]{3}$",required=True)}),
  A("minimumStay","P","integer","O","EXT","Mínimo de noites.",minimum=1)],
  rules=["availableUnits <= totalUnits do RoomType referenciado","refHotel de RoomAvailability = refHotel do RoomType referenciado","o id contém hotel, tipo e data de stayDate"])
E("Event","SDM dataModel.TourismDestinations/Event (perfil + extensões)","Evento de qualquer porte, de apresentação em bar a congresso. Também representa restrição de banho (category bathingRestriction).","urn:ngsi-ld:Event:<slug>",[
  NAME("Nome do evento."), 
  A("startDate","P","datetime","R","SDM","Início (DateTime, UTC)."),
  A("endDate","P","datetime","R","SDM","Fim (DateTime, UTC), posterior a startDate."),
  LOC(), ADDR(), OWNER,
  A("category","P","arrayenum","R","SDM","Categorias do evento; ao menos uma. bathingRestriction é extensão do projeto.",enum=["excursion","gastronomy","history","museum","outdoorActivities","parksAndGardens","religiousWorship","shopping","spectacle","wellness","bathingRestriction"],minItems=1),
  A("eventScale","P","enum","C:R, exceto se category contém bathingRestriction","EXT","Porte do evento.",enum=["small","medium","large"]),
  A("eventStatus","P","arrayenum","R","SDM","Situação; lista com um valor.",enum=["scheduled","opened","closed","suspended","cancelled","finished","postponed","rescheduled"],minItems=1,maxItems=1),
  A("venueName","P","string","O","EXT","Nome do local (bar, teatro, praça)."),
  A("maximumAttendeeCapacity","P","integer","O","SDM","Público máximo.",minimum=1),
  A("isAccessibleForFree","P","boolean","O","SDM","Entrada gratuita."),
  A("eventPriceFrom","P","number","O","SDM","Menor preço. Com currency.",minimum=0,subattrs={"currency":dict(pattern=r"^[A-Z]{3}$",required=True)}),
  A("eventPriceTo","P","number","O","SDM","Maior preço. Com currency.",minimum=0,subattrs={"currency":dict(pattern=r"^[A-Z]{3}$",required=True)}),
  A("audience","P","arrayenum","O","SDM","Público-alvo.",enum=["adult","allPublic","children","family","senior","teenager"]),
  A("wheelChairAccessible","P","boolean","O","SDM","Acessível a cadeirantes."),
  A("webSite","P","string","O","SDM","Site oficial."),
  REF("refPointOfInterest","Beach ou PointOfInterest","C:R se category contém bathingRestriction (aponta a Beach); O nos demais","Praia afetada (restrição) ou local do evento. Perfil: um único alvo."), DESC],
  rules=["endDate > startDate","category contém bathingRestriction => refPointOfInterest aponta uma Beach e eventScale é dispensado","eventScale obrigatório nos demais eventos"])
E("Beach","SDM dataModel.PointOfInterest/Beach (perfil + extensão)","Praia. Ponto central; o estado de banho fica em BathingStatus.","urn:ngsi-ld:Beach:<slug>",[
  NAME("Nome da praia."), LOC(), OWNER,
  A("beachType","P","arrayenum","O","SDM","Tipos de praia.",enum=["whiteSand","urban","isolated","calmWaters","blueFlag","Q-Quality","strongWaves","windy","blackSand"],minItems=1),
  A("facilities","P","arrayenum","O","SDM","Facilidades.",enum=["promenade","showers","cleaningServices","lifeGuard","sunshadeRental","sunLoungerRental","waterCraftRental","toilets","touristOffice","litterBins","telephone","surfPracticeArea","accessforDisabled"],minItems=1),
  A("accessType","P","arrayenum","O","SDM","Formas de acesso.",enum=["privateVehicle","boat","onFoot","publicTransport"],minItems=1),
  A("length","P","number","O","SDM","Comprimento, metros.",minimum=0),
  A("width","P","number","O","SDM","Largura, metros.",minimum=0),
  A("occupationRate","P","enum","O","SDM","Lotação típica.",enum=["high","medium","low","none"]),
  REF("refWeatherStation","PointOfInterest (category weatherStation)","R","Estação cujas chuvas valem para esta praia (extensão do projeto)."),
  ADDR("O"), DESC, SRC])
FOOD = "category contém restaurant ou bar"
E("PointOfInterest","SDM dataModel.PointOfInterest/PointOfInterest (perfil + extensões)","Ponto de coleta de balneabilidade, estação meteorológica, restaurante ou bar, conforme category. Restaurante e bar guardam ocupação atual.","urn:ngsi-ld:PointOfInterest:<slug>",[
  NAME("Nome do ponto."), LOC(), OWNER,
  A("category","P","arrayenum","R","SDM","Função do ponto (extensão de valores do projeto).",enum=["bathingSamplingPoint","weatherStation","restaurant","bar"],minItems=1),
  REF("refBeach","Beach","C:R se category contém bathingSamplingPoint","Praia a que o ponto de coleta pertence."),
  ADDR("C:R se "+FOOD),
  A("capacity","P","integer","C:R se "+FOOD,"SDM","Lugares totais.",minimum=1),
  A("occupancy","P","integer","C:R se "+FOOD,"SDM","Lugares ocupados agora. Exige observedAt no atributo.",minimum=0,observed_at=True),
  A("availabilityLevel","P","enum","O","EXT","Só para restaurante e bar. Derivado de occupancy/capacity (limiares configuráveis na API).",enum=["available","limited","full"]),
  A("cuisine","P","array","O","EXT","Só para restaurante e bar. Tipos de cozinha (texto livre).",items="string"),
  A("priceRange","P","string","O","SDM","Só para restaurante e bar. Faixa de preço, de $ a $$$$.",pattern=r"^\${1,4}$"),
  OPEN, CONTACT, DESC, SRC],
  rules=["bathingSamplingPoint => refBeach presente","restaurant ou bar => address, capacity e occupancy presentes","occupancy <= capacity","capacity, occupancy, availabilityLevel, cuisine, priceRange e openingHoursSpecification só em restaurant ou bar","availabilityLevel coerente com a razão occupancy/capacity (limiares a definir na API)"])
E("WaterQualityObserved","SDM dataModel.WaterQuality/WaterQualityObserved (perfil)","Medição de uma sonda em um ponto de coleta. Estimativa, não laudo.","urn:ngsi-ld:WaterQualityObserved:<ponto>:<AAAAMMDDTHHMMSSZ>",[
  A("dateObserved","P","datetime","R","SDM","Instante da medição (DateTime, UTC)."), LOC(),
  REF("refPointOfInterest","PointOfInterest (bathingSamplingPoint)","R","Ponto de coleta."), OWNER,
  A("turbidity","P","number","R","SDM","Turbidez, NTU.",minimum=0),
  A("salinity","P","number","R","SDM","Salinidade, PSU.",minimum=0),
  A("temperature","P","number","O","SDM","Temperatura da água, °C."),
  A("pH","P","number","O","SDM","pH.",minimum=0,maximum=14),
  A("O2","P","number","O","SDM","Oxigênio dissolvido, mg/L.",minimum=0), SRC])
E("WeatherObserved","SDM dataModel.Weather/WeatherObserved (perfil + extensão)","Observação de uma estação meteorológica.","urn:ngsi-ld:WeatherObserved:<estacao>:<AAAAMMDDTHHMMSSZ>",[
  A("dateObserved","P","datetime","R","SDM","Instante da observação (DateTime, UTC)."), LOC(),
  REF("refPointOfInterest","PointOfInterest (weatherStation)","R","Estação."), OWNER,
  A("precipitation","P","number","R","SDM","Chuva acumulada no intervalo da observação, mm (L/m²).",minimum=0),
  A("precipitationIntervalMinutes","P","number","R","EXT","Duração do intervalo da precipitação, minutos. Necessário para somar 24 h e 72 h.",minimum=1),
  A("temperature","P","number","O","SDM","Temperatura do ar, °C."),
  A("relativeHumidity","P","number","O","SDM","Umidade relativa, fração de 0 a 1.",minimum=0,maximum=1), SRC])
E("BathingReport","Próprio","Laudo oficial de balneabilidade de uma praia ou ponto, com validade.","urn:ngsi-ld:BathingReport:<praia>:<numero>",[
  REF("refBeach","Beach"), REF("refPointOfInterest","PointOfInterest (bathingSamplingPoint)","O","Ponto de coleta, quando o laudo é por ponto."), OWNER,
  A("result","P","enum","R","EXT","Resultado do laudo.",enum=["proper","improper"]),
  A("collectionDate","P","datetime","R","EXT","Coleta da amostra."),
  A("validFrom","P","datetime","R","EXT","Início da validade."),
  A("validUntil","P","datetime","R","EXT","Fim da validade."),
  A("issuingAuthority","P","string","R","EXT","Órgão emissor."),
  A("reportNumber","P","string","R","EXT","Número do laudo."),
  A("escherichiaColi","P","number","O","SDM","E. coli, NMP/100 mL.",minimum=0),
  A("enterococci","P","number","O","SDM","Enterococos, NMP/100 mL.",minimum=0),
  A("documentURL","P","string","O","EXT","Link do documento.")],
  rules=["collectionDate <= validFrom < validUntil","o laudo só prevalece entre validFrom e validUntil (política na TASK-10)"])
E("BathingStatus","Próprio","Estado de banho consolidado de uma praia; uma entidade por praia, atualizada no lugar.","urn:ngsi-ld:BathingStatus:<praia>",[
  REF("refBeach","Beach"), OWNER,
  A("status","P","enum","R","EXT","Estado de banho.",enum=["proper","improper","alert","indeterminate"]),
  A("basis","P","enum","R","EXT","Base do estado: laudo, estimativa ou nenhuma.",enum=["report","estimate","none"]),
  A("computedAt","P","datetime","R","EXT","Instante do cálculo."),
  A("validUntil","P","datetime","C:R se basis diferente de none","EXT","Fim da validade deste estado."),
  REF("refBathingReport","BathingReport","C:R se basis = report","Laudo que sustenta o estado."),
  A("estimatedRiskLevel","P","enum","C:R se basis = estimate","EXT","Risco estimado. Não é laudo oficial.",enum=["low","moderate","high"]),
  A("rainfall24h","P","number","O","EXT","Chuva acumulada em 24 h, mm.",minimum=0),
  A("rainfall72h","P","number","O","EXT","Chuva acumulada em 72 h, mm.",minimum=0)],
  rules=["basis = none => status = indeterminate","basis = report => status igual ao result do laudo (proper ou improper)","basis = estimate => status diferente de proper sem laudo vigente é decisão da TASK-10"])

CUSTOM_TYPES = ["Hotel","RoomType","RoomAvailability","BathingReport","BathingStatus"]
