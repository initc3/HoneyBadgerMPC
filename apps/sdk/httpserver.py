import asyncio
import logging
import pickle

from aiohttp import web

from honeybadgermpc.utils.misc import _create_task


class HTTPServer:
    """HTTP server to handle requests from clients."""

    def __init__(
        self, sid, myid, *, host="0.0.0.0", port=8080, db,
    ):
        """
        Parameters
        ----------
        sid: int
            Session id.
        myid: int
            Client id.
        """
        self.sid = sid
        self.myid = myid
        self._host = host
        self._port = port
        self.db = db
        self._http_server = _create_task(self._request_handler_loop())

    async def start(self):
        await self._http_server
        # await self._request_handler_loop()

    async def _request_handler_loop(self):
        """ Task 2. Handling client input

        .. todo:: if a client requests a share, check if it is
            authorized and if so send it along

        """
        routes = web.RouteTableDef()

        @routes.get("/inputmasks/{idx}")
        async def _handler(request):
            idx = int(request.match_info.get("idx"))
            try:
                _inputmasks = self.db[b"inputmasks"]
            except KeyError:
                inputmasks = []
            else:
                inputmasks = pickle.loads(_inputmasks)
            try:
                inputmask = inputmasks[idx]
            except IndexError:
                logging.error(f"No input mask at index {idx}")
                raise

            data = {
                "inputmask": inputmask,
                "server_id": self.myid,
                "server_port": self._port,
            }
            return web.json_response(data)

        app = web.Application()
        app.add_routes(routes)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host=self._host, port=self._port)
        await site.start()
        print(f"======= Serving on http://{self._host}:{self._port}/ ======")
        # pause here for very long time by serving HTTP requests and
        # waiting for keyboard interruption
        await asyncio.sleep(100 * 3600)
