# Modelos NGSI-LD da plataforma de turismo e cultura (TASK-03)

Documentação completa: docs/modelos.md e o documento "Modelos de dados NGSI-LD da plataforma de turismo e cultura".

Regerar e validar (Python 3.10+, `pip install pyld jsonschema`):

    python3 -I tools/build.py
    python3 -I tools/gen_examples.py
    python3 -I tools/validate.py

Antes de usar com um Orion-LD, troque o endereço provisório https://example.org/natal/ em tools/spec.py
(NS e CTX_URL), rode build.py e gen_examples.py, e sirva natal-context.jsonld nesse endereço.

ctx/ngsi-ld-core-context.jsonld é uma cópia do core context do repositório FIWARE/context.Orion-LD (ldcontexts.old),
com um espaço ao fim de um IRI removido. ctx/sdm-merged-offline.jsonld mescla os contextos dos domínios
PointOfInterest, TourismDestinations, WaterQuality e Weather do Smart Data Models (licença CC-BY 4.0).
