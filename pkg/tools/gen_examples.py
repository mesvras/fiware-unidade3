"""Gera os exemplos NGSI-LD a partir de funções pequenas, para manter o conjunto coerente."""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTX = ["https://example.org/natal/natal-context.jsonld"]
OWN = "org-exemplo-001"
def P(v): return {"type":"Property","value":v}
def DT(v): return {"type":"Property","value":{"@type":"DateTime","@value":v}}
def DA(v): return {"type":"Property","value":{"@type":"Date","@value":v}}
def REL(o): return {"type":"Relationship","object":o}
def GEO(lon,lat): return {"type":"GeoProperty","value":{"type":"Point","coordinates":[lon,lat]}}
def money(v,cur="BRL"): return {"type":"Property","value":v,"currency":{"type":"Property","value":cur}}
def addr(street,loc="Natal",cc="BR",pc=None):
    a={"streetAddress":street,"addressLocality":loc,"addressCountry":cc}
    if pc: a["postalCode"]=pc
    return P(a)
def ent(id_,type_,**attrs):
    d={"id":id_,"type":type_}; d.update(attrs); d["@context"]=CTX; return d
OUT = {}
def put(e): OUT[e["type"]+"."+e["id"].split(":",3)[3].replace(":","_")] = e

HOT="urn:ngsi-ld:Hotel:hotel-modelo-farol"
put(ent(HOT,"Hotel", name=P("Hotel Modelo Farol"), location=GEO(-35.2050,-5.8700), address=addr("Rua Exemplo, 100",pc="59000-000"),
  dataOwner=P(OWN), category=P("hotel"), starRating=P(4), checkInTime=P("14:00"), checkOutTime=P("12:00"),
  amenities=P(["wifi","pool","breakfast","beachfront"]), contactPoint=P({"telephone":"+55 84 0000-0000","url":"https://hotel-modelo.example"}),
  description=P("Hotel fictício usado apenas para testes.")))
RT1="urn:ngsi-ld:RoomType:hotel-modelo-farol:standard"; RT2="urn:ngsi-ld:RoomType:hotel-modelo-farol:familia"
put(ent(RT1,"RoomType", name=P("Standard casal"), refHotel=REL(HOT), dataOwner=P(OWN), maxAdults=P(2), maxChildren=P(1), totalUnits=P(20), bedConfiguration=P("1 cama de casal")))
put(ent(RT2,"RoomType", name=P("Família"), refHotel=REL(HOT), dataOwner=P(OWN), maxAdults=P(3), maxChildren=P(2), totalUnits=P(8), bedConfiguration=P("1 cama de casal e 2 de solteiro")))
def avail(rt,slug,date,units,price,minstay=None):
    kw=dict(refHotel=REL(HOT), refRoomType=REL(rt), dataOwner=P(OWN), stayDate=DA(date), availableUnits=P(units), pricePerNight=money(price))
    if minstay: kw["minimumStay"]=P(minstay)
    put(ent("urn:ngsi-ld:RoomAvailability:hotel-modelo-farol:%s:%s"%(slug,date.replace("-","")),"RoomAvailability",**kw))
avail(RT1,"standard","2026-12-20",6,420.0)
avail(RT1,"standard","2026-12-21",0,420.0)
avail(RT2,"familia","2026-12-20",3,690.0,minstay=2)
REST="urn:ngsi-ld:PointOfInterest:restaurante-modelo-mare"
put(ent(REST,"PointOfInterest", name=P("Restaurante Modelo Maré"), location=GEO(-35.2062,-5.8688), address=addr("Avenida Exemplo, 250"),
  dataOwner=P("org-exemplo-002"), category=P(["restaurant"]), capacity=P(80), occupancy={"type":"Property","value":52,"observedAt":"2026-12-20T19:30:00Z"},
  availabilityLevel=P("limited"), cuisine=P(["regional","frutos do mar"]), priceRange=P("$$"),
  openingHoursSpecification=P([{"dayOfWeek":["Friday","Saturday"],"opens":"11:00","closes":"23:30"}]),
  contactPoint=P({"telephone":"+55 84 0000-0001"}), description=P("Restaurante fictício para testes.")))
EV1="urn:ngsi-ld:Event:show-bar-modelo-20261220"
put(ent(EV1,"Event", name=P("Show acústico no Bar Modelo"), startDate=DT("2026-12-20T22:00:00Z"), endDate=DT("2026-12-21T00:30:00Z"),
  location=GEO(-35.2071,-5.8695), address=addr("Rua Exemplo, 15"), dataOwner=P("org-exemplo-003"),
  category=P(["spectacle"]), eventScale=P("small"), eventStatus=P(["scheduled"]), venueName=P("Bar Modelo"),
  maximumAttendeeCapacity=P(60), isAccessibleForFree=P(False), eventPriceFrom=money(30.0), eventPriceTo=money(30.0),
  audience=P(["adult"]), description=P("Apresentação fictícia em bar.")))
EV2="urn:ngsi-ld:Event:festival-modelo-2027"
put(ent(EV2,"Event", name=P("Festival Modelo de Verão"), startDate=DT("2027-01-15T18:00:00Z"), endDate=DT("2027-01-17T04:00:00Z"),
  location=GEO(-35.2301,-5.8402), address=addr("Parque de Exposições Exemplo"), dataOwner=P("org-exemplo-004"),
  category=P(["spectacle","gastronomy"]), eventScale=P("large"), eventStatus=P(["scheduled"]), venueName=P("Parque de Exposições Exemplo"),
  maximumAttendeeCapacity=P(20000), isAccessibleForFree=P(False), eventPriceFrom=money(120.0), eventPriceTo=money(480.0),
  audience=P(["allPublic"]), wheelChairAccessible=P(True), webSite=P("https://festival-modelo.example")))
BCH="urn:ngsi-ld:Beach:praia-modelo-do-farol"
STN="urn:ngsi-ld:PointOfInterest:estacao-modelo-01"; PTO="urn:ngsi-ld:PointOfInterest:coleta-modelo-farol-01"
put(ent(BCH,"Beach", name=P("Praia Modelo do Farol"), location=GEO(-35.1990,-5.7790), dataOwner=P("org-governo-001"),
  beachType=P(["urban","calmWaters"]), facilities=P(["promenade","showers","lifeGuard"]), accessType=P(["privateVehicle","onFoot","publicTransport"]),
  length=P(1800), width=P(60), occupationRate=P("medium"), refWeatherStation=REL(STN), address=addr("Orla Modelo"),
  description=P("Praia fictícia; coordenadas ilustrativas, não representam local real.")))
put(ent(PTO,"PointOfInterest", name=P("Ponto de coleta Farol 01"), location=GEO(-35.1992,-5.7793), dataOwner=P("org-governo-001"),
  category=P(["bathingSamplingPoint"]), refBeach=REL(BCH)))
put(ent(STN,"PointOfInterest", name=P("Estação meteorológica modelo 01"), location=GEO(-35.2000,-5.7800), dataOwner=P("org-governo-001"),
  category=P(["weatherStation"])))
put(ent("urn:ngsi-ld:WaterQualityObserved:coleta-modelo-farol-01:20261220T120000Z","WaterQualityObserved",
  dateObserved=DT("2026-12-20T12:00:00Z"), location=GEO(-35.1992,-5.7793), refPointOfInterest=REL(PTO), dataOwner=P("fonte-sonda-001"),
  turbidity=P(8.4), salinity=P(34.1), temperature=P(28.6), pH=P(8.1), O2=P(6.3), source=P("simulador-sondas")))
put(ent("urn:ngsi-ld:WeatherObserved:estacao-modelo-01:20261220T120000Z","WeatherObserved",
  dateObserved=DT("2026-12-20T12:00:00Z"), location=GEO(-35.2000,-5.7800), refPointOfInterest=REL(STN), dataOwner=P("fonte-estacao-001"),
  precipitation=P(2.4), precipitationIntervalMinutes=P(10), temperature=P(29.2), relativeHumidity=P(0.78), source=P("simulador-estacao")))
REP="urn:ngsi-ld:BathingReport:praia-modelo-do-farol:laudo-2026-0451"
put(ent(REP,"BathingReport", refBeach=REL(BCH), refPointOfInterest=REL(PTO), dataOwner=P("org-governo-001"),
  result=P("proper"), collectionDate=DT("2026-12-15T09:00:00Z"), validFrom=DT("2026-12-16T00:00:00Z"), validUntil=DT("2026-12-23T00:00:00Z"),
  issuingAuthority=P("Órgão Ambiental Modelo"), reportNumber=P("2026/0451"), escherichiaColi=P(120), enterococci=P(18),
  documentURL=P("https://laudos.example/2026-0451.pdf")))
put(ent("urn:ngsi-ld:BathingStatus:praia-modelo-do-farol","BathingStatus", refBeach=REL(BCH), dataOwner=P("org-governo-001"),
  status=P("proper"), basis=P("report"), computedAt=DT("2026-12-20T12:05:00Z"), validUntil=DT("2026-12-23T00:00:00Z"),
  refBathingReport=REL(REP), rainfall24h=P(2.4), rainfall72h=P(5.0)))
put(ent("urn:ngsi-ld:Event:restricao-banho-praia-modelo-20261224","Event", name=P("Restrição de banho: Praia Modelo do Farol"),
  startDate=DT("2026-12-24T00:00:00Z"), endDate=DT("2026-12-26T00:00:00Z"), location=GEO(-35.1990,-5.7790), address=addr("Orla Modelo"),
  dataOwner=P("org-governo-001"), category=P(["bathingRestriction"]), eventStatus=P(["scheduled"]), refPointOfInterest=REL(BCH),
  description=P("Restrição fictícia de banho para teste de calendário.")))
if __name__=="__main__":
    d=os.path.join(ROOT,"examples"); os.makedirs(d,exist_ok=True)
    for f in os.listdir(d): os.remove(os.path.join(d,f))
    for k,v in OUT.items(): json.dump(v,open(os.path.join(d,k+".jsonld"),"w"),indent=2,ensure_ascii=False)
    json.dump(list(OUT.values()),open(os.path.join(ROOT,"examples-batch.jsonld"),"w"),indent=2,ensure_ascii=False)
    print(len(OUT),"exemplos")
