"""
Model object dedicated to Planet interface.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Union

import nest_asyncio
import planet.data_filter as filters
import traitlets as t
from planet import DataClient
from planet.auth import Auth
from planet.exceptions import NoPermission
from planet.http import Session
from sepal_ui.message import ms
from sepal_ui.model import Model

# known problem https://github.com/jupyter/notebook/issues/3397
nest_asyncio.apply()


class PlanetModel(Model):

    SUBS_URL: str = (
        "https://api.planet.com/auth/v1/experimental/public/my/subscriptions"
    )
    "The url of the planet API subscription"

    credentials: List[str] = []
    "list containing [api_key] or pair of [username, password] to log in"

    session: Optional[Session] = None
    "planet.http.session: planet session."

    subscriptions: t.Dict = t.Dict({}).tag(sync=True)
    "All the dictionary info from the available subscriptions"

    active = t.Bool(False).tag(sync=True)
    "Value to determine if at least one subscription has the active true state"

    def __init__(self, credentials: Union[str, List[str]] = "") -> None:
        """
        Planet model helper to connect planet API client and perform requests.

        It can be
        instantiated whether itself or linked with a PlanetView input helper. All the methods
        are aimed to be used without the need of a view.

        Args:
            credentials: planet API key or tuple of username and password of planet explorer.
        """
        self.subscriptions = {}
        self.session = None
        self.active = False

        if credentials:
            self.init_session(credentials)

    def init_session(self, credentials: Union[str, List[str]]) -> None:
        """
        Initialize planet client with api key or credentials. It will handle errors.

        Args:
            credentials: planet API key or username and password pair of planet explorer.
        """
        if not isinstance(credentials, list):
            credentials = [credentials]

        if not all(credentials):
            raise ValueError(ms.planet.exception.empty)

        if len(credentials) == 2:
            self.auth = Auth.from_login(*credentials)
        else:
            self.auth = Auth.from_key(credentials[0])

        self.session = Session(auth=self.auth)
        self._is_active()

        return

    def _is_active(self) -> None:
        """
        check if the key has an associated active subscription and change the state button accordingly.
        """
        # As there is not any key that identify the nicfi contract,
        # let's find though all the subscriptions a representative name
        wildcards = ["Level_0", "Level_1", "Level2"]

        # get the subs from the api key and save them in the model. It will be useful
        # to avoid doing more calls.
        tmp_subscriptions: dict[str, list] = {"nicfi": [], "others": []}
        for sub in self.get_subscriptions():
            for w in wildcards:
                if w in str(sub):
                    tmp_subscriptions["nicfi"].append(sub)
                    break
            if sub not in tmp_subscriptions["nicfi"]:
                tmp_subscriptions["others"].append(sub)

        self.subscriptions = tmp_subscriptions

        states = self.search_status(self.subscriptions)
        self.active = any([next(iter(d.values())) for d in states])

        return

    def get_subscriptions(self) -> dict:
        """
        load the user subscriptions.

        Returns:
            the dictionnary of user subscription or empty list if nothing found
        """
        req = self.session.request("GET", self.SUBS_URL)

        try:
            response = asyncio.run(req)

        except NoPermission:
            raise Exception(
                "You don't have permission to access to this resource. Check your input data."
            )

        except Exception as e:
            raise e

        return response.json() if response.status_code == 200 else {}

    def get_items(
        self,
        aoi: dict,
        start: Union[str, datetime],
        end: Union[str, datetime],
        cloud_cover: float,
        limit_to_x_pages: Optional[int] = None,
    ) -> list:
        """
        Request imagery items from the planet API for the requested dates.

        Args:
            aoi: geojson clipping geometry
            start: the start of the request (YYYY-mm-dd))
            end: the end of the request (YYYY-mm-dd))
            cloud_cover: maximum cloud coverage.
            limit_to_x_pages: number of pages to constrain the search. Defaults to -1 to use all of them.

        Returns:
            items found using the search query

        """
        # cast start and end to str
        start = (
            datetime.strptime(start, "%Y-%m-%d") if isinstance(start, str) else start
        )
        end = datetime.strptime(end, "%Y-%m-%d") if isinstance(end, str) else end

        and_filter = filters.and_filter(
            [
                filters.geometry_filter(aoi),
                filters.range_filter("cloud_cover", lte=cloud_cover),
                filters.date_range_filter("acquired", gt=start),
                filters.date_range_filter("acquired", lt=end),
            ]
        )

        # PSScene3Band and PSScene4Band item type and assets will be deprecated by January 2023
        # But we'll keep them here because there are images tagged with these labels
        # item types from https://developers.planet.com/docs/apis/data/items-assets/

        item_types = ["PSScene"]

        async def _main():
            """
            Create an asyncrhonous function here to avoid making the main get_items as async.

            So we can keep calling get_items without any change.
            """
            client = DataClient(self.session)
            items = await client.search(item_types, and_filter, name="quick_search")
            items.limit = limit_to_x_pages
            items_list = [item async for item in items]
            return items_list

        return asyncio.run(_main())

    @staticmethod
    def search_status(d: dict) -> List[Dict[str, bool]]:
        """
        Get the status of a specific subscription.

        Args:
            d: dictionnary of subscription object

        Returns:
            the (sub.name: status) pairs
        """
        states = []

        for v in d.values():
            for subs in v:
                if "plan" in subs:
                    plan = subs.get("plan")
                    state = True if plan.get("state") == "active" else False
                    states.append({plan.get("name"): state})

        return states
