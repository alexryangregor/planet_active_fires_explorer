import requests

from planet import api
from planet.api import filters

import component.parameter as param

__all__ = [
    "PlanetKey",
    "build_request",
    "get_items",
    "get_thresholds",
    "get_confidence_color",
]


class PlanetKey:
    def __init__(self, api_key):

        self.api_key = api_key
        self.url = "https://api.planet.com/auth/v1/experimental/public/my/subscriptions"
        self.subs = None
        self.active = None

    def client(self):

        return api.ClientV1(api_key=self.api_key)

    def get_subscription(self):

        resp = requests.get(self.url, auth=(self.api_key, ""))
        subscriptions = resp.json()

        if resp.status_code == 200:
            return subscriptions

    def is_active(self):

        subs = self.get_subscription()
        active = [False]

        if subs:
            active = [True for sub in subs if sub["state"] == "active"]

        return any(active)


def build_request(aoi_geom, start_date, stop_date, cloud_cover=100):
    """build a data api search request for PS imagery.

    Args:
        aoi_geom (geojson):
        start_date (datetime.datetime)
        stop_date (datetime.datetime)

    Returns:
        Request
    """

    query = filters.and_filter(
        filters.geom_filter(aoi_geom),
        filters.range_filter("cloud_cover", lte=cloud_cover),
        filters.date_range("acquired", gt=start_date),
        filters.date_range("acquired", lt=stop_date),
    )

    # Skipping REScene because is not orthorrectified and
    # cannot be clipped.

    return filters.build_search_request(
        query,
        [
            "PSScene3Band",
            "PSScene4Band",
            "PSOrthoTile",
            "REOrthoTile",
        ],
    )


def get_items(id_name, request, client):
    """Get items using the request with the given parameters"""
    result = client.quick_search(request)

    items_pages = []
    limit_to_x_pages = None
    for page in result.iter(limit_to_x_pages):
        items_pages.append(page.get())

    items = [item for page in items_pages for item in page["features"]]

    return (id_name, items)


def get_thresholds(lower):
    """Get the upper limit based on the lower value"""

    thres = sorted(param.CONFIDENCE["disc"].keys(), reverse=True)
    upper = 100 if thres.index(lower) == 0 else thres[thres.index(lower) - 1]

    return (upper, lower)


def get_confidence_color(satsource, value):
    """Return confidence color depending on the satellite type

    Args:
        satsource (str): Satellite soure, depending on the satellite source,
            the confidence will be categorical (high, nominal, low )
            or discrete (raging from 0-100)
        value (int, str): The confidence value
    """

    # Get the type of the confidence representation, categorical or discrete
    type_ = "disc" if satsource == "modis" else "cat"

    # Get category name and color into a dictionary
    confidence_color = {k: v[1] for k, v in param.CONFIDENCE[type_].items()}

    if type_ == "disc":

        thresholds = sorted(param.CONFIDENCE["disc"].keys(), reverse=True)

        for threshold in thresholds:
            if int(value) >= threshold:
                break

        return confidence_color[threshold]

    else:
        return confidence_color[value]
