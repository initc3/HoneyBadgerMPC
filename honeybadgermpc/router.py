import asyncio
import logging
from abc import ABC, abstractmethod
from functools import partial

from honeybadgermpc.utils.typecheck import TypeCheck


class Router(ABC):
    """
    Base class for Router objects defining the recv and send methods.
    """

    def __init__(self, num_parties: int, debug: bool = False):
        self.n = num_parties
        self.sends = self._make_sends()
        self.recvs = self._make_recvs()
        self.broadcasts = self._make_broadcasts()
        self.debug = debug

    @abstractmethod
    async def recv(self, player_id: int) -> object:
        """ Receives a message from player with id `player_id`

        args:
            player_id (int): Id of the receiving player

        outputs:
            returns the first message that arrives for the given player
        """
        return NotImplementedError

    @abstractmethod
    def send(self, player_id: int, dest_id: int, message: object):
        """ Sends a message to player with id `dest` from `player_id`

        args:
            player_id (int): Id of the sending player
            dest_id (int): Id of the receiving player
            message (object): Message to send to dest_id

        """
        return NotImplementedError

    @TypeCheck()
    def broadcast(self, player_id: int, message: object):
        """ Sends a message from player to all other players

        args:
            player_id (int): Id of the broadcasting player
            message (object): Message to broadcast
        """
        for dest_id in range(self.n):
            self.send(player_id, dest_id, message)

    def _make_recvs(self):
        return [partial(self.recv, player_id) for player_id in range(self.n)]

    def _make_sends(self):
        return [partial(self.send, player_id) for player_id in range(self.n)]

    def _make_broadcasts(self):
        return [partial(self.broadcast, player_id) for player_id in range(self.n)]


class SimpleRouter(Router):
    """ Simple router which uses queues as a mechanism for sending messages between players
    """

    @TypeCheck()
    def __init__(self, num_parties: int):
        super().__init__(num_parties)

        # Mailboxes for each party
        self._queues = [asyncio.Queue() for _ in range(num_parties)]

    @TypeCheck()
    async def recv(self, player_id: int) -> object:
        """ Retrieves a message for player_id.

        args:
            player_id(int): id of player to receive message

        outputs:
            Returns the first message received for the given player
        """
        (source_id, message) = await self._queues[player_id].get()

        if self.debug:
            logging.info(f"Received {message} [{player_id}<-{source_id}]")

        return (source_id, message)

    @TypeCheck()
    def send(self, player_id: int, dest_id: int, message: object):
        """ Sends  message from player_id to dest_id

        args:
            player_id (int): Player sending message
            dest_id (int): Player receiving message
            message (object): Message to send to other player
        """
        self._queues[dest_id].put_nowait((player_id, message))

        if self.debug:
            logging.debug(f"Sent {message} [{player_id}->{dest_id}]")
