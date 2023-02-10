from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from aiohttp import BasicAuth, ClientSession, ClientTimeout
from aiohttp.client_exceptions import ContentTypeError
from attr import dataclass, ib
from jinja2 import Template
from mautrix.util.config import RecursiveDict
from ruamel.yaml.comments import CommentedMap

from ..db.room import RoomState
from .switch import Case, Switch

if TYPE_CHECKING:
    from middlewares.http import HTTPMiddleware


@dataclass
class HTTPRequest(Switch):
    """
    ## HTTPRequest

    HTTPRequest is a subclass of Switch which allows sending a message formatted with jinja
    variables and capturing the response to transit to another node according to the validation

    content:

    ```
    - id: 'r1'
      type: 'http_request'
      method: 'GET'
      url: 'https://inshorts.deta.dev/news?category={{category}}'

      variables:
        news: data

      cases:
        - id: 200
          o_connection: m1
        - id: default
          o_connection: m2
    ```
    """

    method: str = ib(default=None, metadata={"json": "method"})
    url: str = ib(default=None, metadata={"json": "url"})
    middleware: str = ib(default=None, metadata={"json": "middleware"})
    variables: Dict[str, Any] = ib(metadata={"json": "variables"}, factory=dict)
    cookies: Dict[str, Any] = ib(metadata={"json": "cookies"}, factory=dict)
    query_params: Dict[str, Any] = ib(metadata={"json": "query_params"}, factory=dict)
    headers: Dict[str, Any] = ib(metadata={"json": "headers"}, factory=dict)
    basic_auth: Dict[str, Any] = ib(metadata={"json": "basic_auth"}, factory=dict)
    data: Dict[str, Any] = ib(metadata={"json": "data"}, factory=dict)
    cases: List[Case] = ib(metadata={"json": "cases"}, factory=list)

    @property
    def _url(self) -> Template:
        return self.render_data(self.url)

    @property
    def _variables(self) -> Template:
        return self.render_data(self.serialize()["variables"])

    @property
    def _cookies(self) -> Template:
        return self.render_data(self.serialize()["cookies"])

    @property
    def _headers(self) -> Dict[str, Template]:
        return self.render_data(self.serialize()["headers"])

    @property
    def _auth(self) -> Dict[str, Template]:
        return self.render_data(self.serialize()["basic_auth"])

    @property
    def _query_params(self) -> Dict:
        return self.render_data(self.serialize()["query_params"])

    @property
    def _data(self) -> Dict:
        return self.render_data(self.serialize()["data"])

    @property
    def _context_params(self) -> Dict[str, Template]:
        return self.render_data(
            {
                "bot_mxid": "{{bot_mxid}}",
                "customer_room_id": "{{customer_room_id}}",
            }
        )

    async def run(self) -> str:
        pass

    async def request(self, session: ClientSession, middleware: HTTPMiddleware) -> Tuple(int, str):
        request_body = {}

        if self.query_params:
            request_body["params"] = self._query_params

        if self.basic_auth:
            request_body["auth"] = BasicAuth(
                login=self._auth["login"],
                password=self._auth["password"],
            )

        if self.headers:
            request_body["headers"] = self._headers

        if self.data:
            request_body["json"] = self._data

        request_params_ctx = self._context_params
        request_params_ctx.update({"middleware": middleware})

        try:
            timeout = ClientTimeout(total=self.config["menuflow.timeouts.http_request"])
            response = await session.request(
                self.method,
                self._url,
                **request_body,
                trace_request_ctx=request_params_ctx,
                timeout=timeout,
            )
        except Exception as e:
            self.log.exception(f"Error in http_request node: {e}")
            o_connection = await self.get_case_by_id(id=str(500))
            await self.room.update_menu(node_id=o_connection, state=None)
            return 500, e

        self.log.debug(
            f"node: {self.id} method: {self.method} url: {self._url} status: {response.status}"
        )

        if response.status == 401:
            return response.status, await response.text()

        variables = {}
        o_connection = None

        if self._cookies:
            for cookie in self._cookies:
                variables[cookie] = response.cookies.output(cookie)

        try:
            response_data = await response.json()
        except ContentTypeError:
            response_data = {}

        if isinstance(response_data, dict):
            # Tulir and its magic since time immemorial
            serialized_data = RecursiveDict(CommentedMap(**response_data))
            if self._variables:
                for variable in self._variables:
                    try:
                        variables[variable] = self.render_data(
                            serialized_data[self.variables[variable]]
                        )
                    except KeyError:
                        pass
        elif isinstance(response_data, str):
            if self._variables:
                for variable in self._variables:
                    try:
                        variables[variable] = self.render_data(response_data)
                    except KeyError:
                        pass

                    break

        if self.cases:
            o_connection = await self.get_case_by_id(id=str(response.status))

        if o_connection:
            await self.room.update_menu(
                node_id=o_connection, state=RoomState.END.value if not self.cases else None
            )

        if variables:
            await self.room.set_variables(variables=variables)

        return response.status, await response.text()
