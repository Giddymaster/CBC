"""Kenya's administrative hierarchy — county → sub-county → ward.

Backs the cascading pickers on the registration form: choose a county and the
sub-county list narrows to it; choose a sub-county and the ward list narrows to
that. The data is bundled (`locations.json`) rather than fetched live — it only
changes when the IEBC redraws boundaries, and a school on a poor connection must
still be able to register.

`sub-county` here is the IEBC constituency, which is what school records in
Kenya use in practice.
"""

import json
from functools import lru_cache
from pathlib import Path

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

_DATA_FILE = Path(__file__).resolve().parent / "locations.json"

# One typo in the upstream dataset, fixed on the way in.
_COUNTY_FIXES = {"West pokot": "West Pokot"}


@lru_cache(maxsize=1)
def _tree():
    """{county: {subcounty: [wards]}}, built once and cached."""
    raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    tree = {}
    for county in raw:
        name = _COUNTY_FIXES.get(county["county_name"], county["county_name"])
        tree[name] = {
            con["constituency_name"]: list(con["wards"])
            for con in county["constituencies"]
        }
    return tree


def counties():
    return sorted(_tree())


def _find_key(mapping, value):
    """Case-insensitive lookup, so 'nairobi' matches 'Nairobi'."""
    if value is None:
        return None
    lowered = value.strip().lower()
    for key in mapping:
        if key.lower() == lowered:
            return key
    return None


def subcounties(county):
    key = _find_key(_tree(), county)
    return sorted(_tree()[key]) if key else []


def wards(county, subcounty):
    county_key = _find_key(_tree(), county)
    if not county_key:
        return []
    ward_map = _tree()[county_key]
    sub_key = _find_key(ward_map, subcounty)
    return sorted(ward_map[sub_key]) if sub_key else []


class LocationsView(APIView):
    """GET /api/locations/ — cascading county / sub-county / ward lookup.

    - no params            → every county
    - ?county=X            → sub-counties in X
    - ?county=X&subcounty=Y → wards in Y

    Each response is deliberately just the next level down, so the payload is a
    short list, not the whole 1,451-ward tree.

    Public: it is non-sensitive reference data (Kenya's own administrative map)
    and is read before any account exists, so it carries no auth requirement.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        county = request.query_params.get("county")
        subcounty = request.query_params.get("subcounty")

        if county and subcounty:
            return Response(
                {"county": county, "subcounty": subcounty,
                 "wards": wards(county, subcounty)}
            )
        if county:
            return Response({"county": county, "subcounties": subcounties(county)})
        return Response({"counties": counties()})
