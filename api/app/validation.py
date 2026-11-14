from checks import check, relationship_targets

from .orion import Orion


class ValidationFailed(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


async def validate(orion: Orion, entity: dict) -> None:
    related = await orion.get_many(relationship_targets(entity))
    errors = check(entity, related)
    if errors:
        raise ValidationFailed(errors)
