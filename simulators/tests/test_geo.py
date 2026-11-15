import random

import pytest

from sim import geo


@pytest.mark.parametrize("zone", geo.ZONES, ids=lambda z: z.key)
def test_points_stay_inside_zone(zone):
    rng = random.Random(1)
    for _ in range(200):
        p = geo.point(rng, zone)
        assert geo.distance_m(p, zone.center) <= zone.radius + 1


def test_points_are_inside_natal_area():
    rng = random.Random(2)
    for zone in geo.ZONES:
        lon, lat = geo.point(rng, zone)
        assert -35.30 < lon < -35.10 and -5.95 < lat < -5.70


def test_address_is_complete_and_names_zone():
    zone = geo.ZONES[0]
    a = geo.address(random.Random(3), zone)
    assert a["addressLocality"] == "Natal" and a["addressCountry"] == "BR"
    assert a["streetAddress"].endswith(zone.name)
    assert a["postalCode"].startswith(zone.postal_prefix + "-")
