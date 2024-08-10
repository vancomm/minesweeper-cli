from __future__ import annotations

import argparse
import collections
import datetime
import http
import math
from dataclasses import dataclass
from itertools import batched
from typing import Callable, NamedTuple, Self

import requests
from colorama import Back, Fore, Style


@dataclass
class GameParams:
    width: int
    height: int
    mine_count: int
    unique: bool

    def validate_move(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height


class Command(NamedTuple):
    callback: Callable[[Minesweeper, list[str]], None]
    nargs: int


class Minesweeper:
    def __init__(
        self,
        url: str,
        width: int,
        height: int,
        mine_count: int,
        unique: int,
    ) -> None:
        self.url = url
        self.width = width
        self.height = height
        self.mine_count = mine_count
        self.unique = unique
        self.session_id: str | None = None
        self.grid: list[int] = []
        self.dead = False
        self.won = False
        self.started_at: datetime.datetime | None = None
        self.ended_at: datetime.datetime | None = None

    def update(self, data: dict) -> None:
        self.session_id = data["session_id"]
        self.grid = data["grid"]
        self.dead = data["dead"]
        self.won = data["won"]
        self.started_at = datetime.datetime.fromtimestamp(
            data["started_at"], datetime.timezone.utc
        )
        if "ended_at" in data:
            self.ended_at = datetime.datetime.fromtimestamp(
                data["ended_at"], datetime.timezone.utc
            )

    @classmethod
    def from_seed(cls, url: str, seed: str) -> Self:
        if len((parts := seed.split(":"))) not in {3, 4}:
            raise ValueError("seed may contain 3 or 4 parts")
        if not all(s for s in parts if s.isdigit()):
            raise ValueError("seed parts must be digits")
        width, height, mine_count, *u = map(int, parts)
        unique = bool(u[0]) if u else True
        return cls(url, width, height, mine_count, unique)

    @classmethod
    def from_session_id(cls, url: str, session_id: str) -> Self:
        res = requests.get(f"{url}/game/{session_id}")
        if not res.ok:
            if res.status_code == http.HTTPStatus.NOT_FOUND:
                raise ValueError("no such session")
            elif res.text:
                raise ValueError(res.text)
            else:
                raise ValueError("could not find game")
        data = res.json()
        game = cls(
            url,
            data["width"],
            data["height"],
            data["mine_count"],
            data["unique"],
        )
        game.session_id = data["session_id"]
        game.update(data)
        return game

    def new_game(self, x: int, y: int) -> None:
        params = {
            "width": self.width,
            "height": self.height,
            "mine_count": self.mine_count,
            "unique": self.unique,
            "x": x,
            "y": y,
        }
        data = requests.post(f"{self.url}/game", params=params).json()
        self.update(data)
        print(f"session id: {self.session_id}")

    def validate_move(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def open(self: Minesweeper, args: list[str]) -> None:
        try:
            x, y = map(int, args)
        except ValueError:
            raise ValueError("args must be integer")
        if not self.validate_move(x, y):
            raise ValueError("out of bounds")
        if not self.grid:
            self.new_game(x, y)
            return
        i = y * self.width + x
        if self.grid[i] != -2:
            return self.chord(args)
        data = requests.post(
            f"{self.url}/game/{self.session_id}/open?{x=}&{y=}",
        ).json()
        self.update(data)
        return

    def chord(self: Minesweeper, args: list[str]) -> None:
        try:
            x, y = map(int, args)
        except ValueError:
            raise ValueError("args must be integer")
        if not self.validate_move(x, y):
            raise ValueError("out of bounds")
        if not self.grid:
            self.new_game(x, y)
            return
        i = y * self.width + x
        if not 0 <= self.grid[i] <= 8:
            raise ValueError("cannot chord closed square")
        data = requests.post(
            f"{self.url}/game/{self.session_id}/chord?{x=}&{y=}",
        ).json()
        self.update(data)
        return

    def flag(self: Minesweeper, args: list[str]) -> None:
        try:
            x, y = map(int, args)
        except ValueError:
            raise ValueError("args must be integer")
        if not self.validate_move(x, y):
            raise ValueError("out of bounds")
        if not self.grid:
            raise ValueError("open any square to start the game")
        data = requests.post(
            f"{self.url}/game/{self.session_id}/flag?{x=}&{y=}",
        ).json()
        self.update(data)
        return

    HELP = """\
 Available commands:
    o [X] [Y]   : open (or chord) a square at X:Y
    f [X] [Y]   : flag (or unflag) a square at X:Y
    h           : print this message
"""

    COMMANDS = {
        "o": Command(open, 2),
        "f": Command(flag, 2),
        "h": Command(lambda *_: (_ for _ in ()).throw(ValueError(Minesweeper.HELP)), 0),
    }

    CELL_TO_CH = collections.defaultdict(
        lambda: "%",  # unknown cell code
        {
            -3: "?",  # question mark
            -2: "#",  # unknown
            -1: "F",  # mine
            0: ".",
            1: f"{Fore.CYAN}1{Style.RESET_ALL}",
            2: f"{Fore.GREEN}2{Style.RESET_ALL}",
            3: f"{Fore.RED}3{Style.RESET_ALL}",
            4: f"{Style.DIM}{Fore.BLUE}4{Style.RESET_ALL}",
            5: f"{Style.DIM}{Fore.RED}5{Style.RESET_ALL}",
            6: f"{Style.DIM}{Fore.GREEN}6{Style.RESET_ALL}",
            7: f"{Style.DIM}{Fore.LIGHTBLACK_EX}7{Style.RESET_ALL}",
            8: f"{Style.DIM}{Fore.BLUE}8{Style.RESET_ALL}",
            32: f"!",  # flag
            64: "*",  # post game-over mine
            65: f"{Fore.WHITE}{Back.RED}*{Style.RESET_ALL}",  # post game-over exploded mine
            66: "X",  # post game-over false flag
        },
    )

    def render(self) -> str:
        grid = self.grid or [-2] * (self.width * self.height)
        colwidth = math.ceil(math.log10(self.width))
        field = (
            " ".join(" " * (colwidth - 1) + f"{self.CELL_TO_CH[ch]}" for ch in line)
            for line in batched(grid, self.width)
        )
        field = (
            f"{Style.DIM}{i: >{colwidth}}{Style.RESET_ALL} {line}"
            for i, line in enumerate(field)
        )
        top_ruler = (
            " " * (colwidth + 1)
            + Style.DIM
            + " ".join(f"{i: >{colwidth}}" for i in range(self.width))
            + Style.RESET_ALL
        )
        return "\n".join((top_ruler, *field))

    def mines_remaining(self) -> int | None:
        if not self.grid:
            return self.mine_count
        return self.mine_count - sum(1 for x in self.grid if x == -1)

    def playtime(self) -> str:
        if not self.started_at:
            return "N/A"
        if not self.ended_at:
            delta = datetime.datetime.now(datetime.timezone.utc) - self.started_at
        else:
            delta = self.ended_at - self.started_at
        return str(delta.seconds)


def validate_url(url: str) -> str:
    if not url.startswith("http"):
        url = f"http://{url}"
    try:
        if requests.get(f"{url}/status").ok:
            return url
        else:
            raise RuntimeError("server is down")
    except requests.exceptions.RequestException:
        raise ValueError("server is unavailable")


def restore_game(
    url: str, game_params: str | None, session_id: str | None
) -> Minesweeper:
    if game_params:
        return Minesweeper.from_seed(url, game_params)
    elif session_id:
        return Minesweeper.from_session_id(url, session_id)
    else:
        raise ValueError("you must supply game params or session id")


def game_loop(game: Minesweeper) -> None:
    print("<Ctrl+C> to exit, <H+Enter> for help")
    if game.session_id is not None:
        print(f"session id: {game.session_id}")
    else:
        print("open any square to start the game")
    print(game.render())

    while not (game.won or game.dead):
        prompt = f"({game.mines_remaining()}) > "
        cmd, *args = input(prompt).split()
        cmd = cmd.lower()
        if cmd not in game.COMMANDS:
            print(f"`{cmd}`: unknown command (<H+Enter> for help)")
            continue
        command = game.COMMANDS[cmd]
        if len(args) != command.nargs:
            print(f"`{cmd}`: expected {command.nargs} args but got {len(args)}")
            continue
        try:
            command.callback(game, args)
        except ValueError as e:
            print(f"`{cmd}`: {e}")
        else:
            print(game.render())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("game_params", nargs="?")
    parser.add_argument("-s", "--session-id", nargs="?")
    parser.add_argument("-u", "--url", nargs="?", default="http://localhost:8000/v1")
    args = parser.parse_args(argv)

    try:
        url = validate_url(args.url)
        game = restore_game(url, args.game_params, args.session_id)
    except Exception as e:
        print(e)
        return 1

    try:
        game_loop(game)
    except KeyboardInterrupt:
        if game.session_id and not (game.dead or game.won):
            print(f"\ruse session id to continue: {game.session_id}")
        raise

    if game.dead:
        print("You lost!")
    elif game.won:
        print(f"You won! Your time: {game.playtime()}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\rgoodbye")
        raise SystemExit(0)
