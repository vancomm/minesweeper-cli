import json
from typing import NotRequired, TypedDict

from requests import get, post
from websockets.sync.connection import Connection


class NewGameParams(TypedDict):
    width: int
    height: int
    mine_count: int
    unique: bool
    x: int
    y: int


class GameSession(TypedDict):
    session_id: str
    grid: list[int]
    width: int
    height: int
    mine_count: int
    unique: bool
    dead: bool
    won: bool
    started_at: int
    ended_at: NotRequired[int]


class GameHTTPAPI:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    @staticmethod
    def new_game(base_url: str, params: NewGameParams) -> GameSession:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return post(f"{base_url}?{query}").json()

    def get(self) -> GameSession:
        return get(f"{self.base_url}").json()

    def open(self, x: int, y: int) -> GameSession:
        return post(f"{self.base_url}/open?{x=}&{y=}").json()

    def flag(self, x: int, y: int) -> GameSession:
        return post(f"{self.base_url}/flag?{x=}&{y=}").json()

    def chord(self, x: int, y: int) -> GameSession:
        return post(f"{self.base_url}/chord?{x=}&{y=}").json()

    def reveal(self) -> GameSession:
        return post(f"{self.base_url}/reveal").json()


class GameWSAPI:
    def __init__(self, ws: Connection) -> None:
        self.ws = ws

    def get(self) -> GameSession:
        self.ws.send("g")
        res = self.ws.recv()
        return json.loads(res)

    def open(self, x: int, y: int) -> GameSession:
        self.ws.send(f"o {x} {y}")
        res = self.ws.recv()
        return json.loads(res)

    def chord(self, x: int, y: int) -> GameSession:
        self.ws.send(f"c {x} {y}")
        res = self.ws.recv()
        return json.loads(res)

    def flag(self, x: int, y: int) -> GameSession:
        self.ws.send(f"f {x} {y}")
        res = self.ws.recv()
        return json.loads(res)

    def reveal(self) -> GameSession:
        self.ws.send("r")
        res = self.ws.recv()
        return json.loads(res)
