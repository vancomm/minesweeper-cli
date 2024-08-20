from __future__ import annotations

import argparse
import collections
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import batched
from typing import Callable, NamedTuple

import requests
from colorama import Back, Fore, Style
from websockets.sync.client import connect

from minesweeper.api import GameHTTPAPI, GameSession, GameWSAPI


@dataclass
class GameParams:
    width: int
    height: int
    mine_count: int
    unique: bool

    def validate_move(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height


class Minesweeper:
    def __init__(self, wsapi: GameWSAPI, session: GameSession) -> None:
        self.wsapi = wsapi
        self.session = session

    def validate_move(self, x: int, y: int) -> bool:
        return 0 <= x < self.session["width"] and 0 <= y < self.session["height"]

    def open(self: Minesweeper, args: list[str]) -> None:
        try:
            x, y = map(int, args)
        except ValueError:
            raise ValueError("args must be integer")
        if not self.validate_move(x, y):
            raise ValueError("out of bounds")
        i = y * self.session["width"] + x
        if self.session["grid"][i] != -2:
            self.chord(args)
        else:
            self.session = self.wsapi.open(x, y)

    def chord(self: Minesweeper, args: list[str]) -> None:
        try:
            x, y = map(int, args)
        except ValueError:
            raise ValueError("args must be integer")
        if not self.validate_move(x, y):
            raise ValueError("out of bounds")
        i = y * self.session["width"] + x
        if not 0 <= self.session["grid"][i] <= 8:
            raise ValueError("cannot chord closed square")
        self.session = self.wsapi.chord(x, y)

    def flag(self: Minesweeper, args: list[str]) -> None:
        try:
            x, y = map(int, args)
        except ValueError:
            raise ValueError("args must be integer")
        if not self.validate_move(x, y):
            raise ValueError("out of bounds")
        self.session = self.wsapi.flag(x, y)

    HELP = """\
 Available commands:
    o [X] [Y]   : open (or chord) a square at X:Y
    f [X] [Y]   : flag (or unflag) a square at X:Y
    h           : print this message
"""

    # COMMANDS = {
    #     "o": Command(open, 2),
    #     "f": Command(flag, 2),
    #     "h": Command(lambda *_: (_ for _ in ()).throw(ValueError(Minesweeper.HELP)), 0),
    # }

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
            67: "x",  # post game-over unflagged mine
        },
    )

    def render(self) -> str:
        grid = self.session["grid"]
        colwidth = math.ceil(math.log10(self.session["width"]))
        field = (
            " ".join(" " * (colwidth - 1) + f"{self.CELL_TO_CH[ch]}" for ch in line)
            for line in batched(grid, self.session["width"])
        )
        field = (
            f"{Style.DIM}{i: >{colwidth}}{Style.RESET_ALL} {line}"
            for i, line in enumerate(field)
        )
        top_ruler = (
            " " * (colwidth + 1)
            + Style.DIM
            + " ".join(f"{i: >{colwidth}}" for i in range(self.session["width"]))
            + Style.RESET_ALL
        )
        return "\n".join((top_ruler, *field))

    def mines_remaining(self) -> int | None:
        return self.session["mine_count"] - sum(
            1 for x in self.session["grid"] if x == -1
        )

    def playtime(self) -> str:
        if "ended_at" not in self.session:
            now = math.trunc(datetime.now(timezone.utc).timestamp())
            delta = now - self.session["started_at"]
        else:
            delta = self.session["ended_at"] - self.session["started_at"]
        return str(delta)


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
        67: "x",  # post game-over unflagged mine
    },
)


def render_grid(grid: list[int], width: int) -> str:
    colwidth = math.ceil(math.log10(width))
    field = (
        " ".join(" " * (colwidth - 1) + f"{CELL_TO_CH[ch]}" for ch in line)
        for line in batched(grid, width)
    )
    field = (
        f"{Style.DIM}{i: >{colwidth}}{Style.RESET_ALL} {line}"
        for i, line in enumerate(field)
    )
    top_ruler = (
        " " * (colwidth + 1)
        + Style.DIM
        + " ".join(f"{i: >{colwidth}}" for i in range(width))
        + Style.RESET_ALL
    )
    return "\n".join((top_ruler, *field))


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


class Command(NamedTuple):
    callback: Callable[[GameSession, GameWSAPI, list[str]], GameSession | None]
    nargs: int


def open(session: GameSession, wsapi: GameWSAPI, args: list[str]) -> GameSession:
    try:
        x, y = map(int, args)
    except ValueError:
        raise ValueError("args must be integer")
    if not (0 <= x < session["width"]) or not (0 <= y < session["height"]):
        raise ValueError("out of bounds")
    if session["grid"][y * session["width"] + x] == -2:
        return wsapi.open(x, y)
    else:
        return wsapi.chord(x, y)


def flag(session: GameSession, wsapi: GameWSAPI, args: list[str]) -> GameSession:
    try:
        x, y = map(int, args)
    except ValueError:
        raise ValueError("args must be integer")
    if not (0 <= x < session["width"]) or not (0 <= y < session["height"]):
        raise ValueError("out of bounds")
    return wsapi.flag(x, y)


HELP = """\
 Available commands:
    o [X] [Y]   : open (or chord) a square at X:Y
    f [X] [Y]   : flag (or unflag) a square at X:Y
    h           : print this message
"""

DISPATCH: dict[str, Command] = {
    "o": Command(open, 2),
    "f": Command(flag, 2),
    "h": Command(lambda *_: (_ for _ in ()).throw(ValueError(HELP)), 0),
}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("game_params", nargs="?")
    parser.add_argument("-s", "--session-id", nargs="?")
    parser.add_argument("-u", "--url", nargs="?", default="http://localhost:8000/v1")
    args = parser.parse_args(argv)

    if bool(args.game_params) == bool(args.session_id):
        raise ValueError("you must supply exactly one of game_params or session_id")

    url = validate_url(args.url)
    session_id = args.session_id
    session: GameSession | None = None

    print("<Ctrl+C> to exit, <H+Enter> for help")
    if session_id is not None:
        print(f"session id: {session_id}")
    else:
        print("open any square to start the game")

    if args.game_params:
        if len((parts := args.game_params.split(":"))) not in {3, 4}:
            raise ValueError("seed may contain 3 or 4 parts")
        if not all(s for s in parts if s.isdigit()):
            raise ValueError("seed parts must be digits")
        width, height, mine_count, *u = map(int, parts)
        unique = bool(u[0]) if u else True
        grid = [-2] * (width * height)
        print(render_grid(grid, width))
        while not session_id:
            prompt = f"({mine_count}) > "
            cmd, *args = input(prompt).split(" ")
            cmd = cmd.lower()
            if cmd != "o":
                print("use `o` to open any square to start the game")
                continue
            if len(args) != 2:
                print(f"`o`: expected 2 args but got {len(args)}")
                continue
            try:
                x, y = map(int, args)
            except ValueError:
                print("`o`: args must be integer")
                continue
            if not 0 <= x < width and 0 <= y < height:
                print("`o`: out of bounds")
                continue
            session = GameHTTPAPI.new_game(
                url + "/game",
                {
                    "width": width,
                    "height": height,
                    "mine_count": mine_count,
                    "unique": unique,
                    "x": x,
                    "y": y,
                },
            )
            session_id = session["session_id"]
            print(f"session id: {session_id}")

    ws_url = (
        "ws://"
        + url.removeprefix("http://").removeprefix("https://")
        + "/game/"
        + session_id
        + "/connect"
    )
    print(ws_url)
    with connect(ws_url) as ws:
        wsapi = GameWSAPI(ws)

        if not session:
            session = wsapi.get()

        print(render_grid(session["grid"], session["width"]))
        while "ended_at" not in session:
            flag_count = sum(1 for sq in session["grid"] if sq == -1)
            mines_remaining = session["mine_count"] - flag_count
            prompt = f"({mines_remaining}) > "
            cmd, *args = input(prompt).split()
            cmd = cmd.lower()
            if cmd not in DISPATCH:
                print(f"`{cmd}`: unknown command")
                continue
            command = DISPATCH[cmd]
            if len(args) != command.nargs:
                print(f"`{cmd}`: expected {command.nargs} args, got {len(args)}")
                continue
            try:
                update = command.callback(session, wsapi, args)
                if update:
                    session = update
                    print(render_grid(session["grid"], session["width"]))
            except ValueError as e:
                print(e)

    if session["dead"]:
        print("You lost!")
    elif session["won"]:
        playtime = session["ended_at"] - session["started_at"]
        print(f"You won! Your time: {playtime}")

    return 0


def main(argv: list[str] | None = None) -> int:
    """Wrapper around `_main` that handles keyboard events"""
    # logging.basicConfig(level=logging.DEBUG)
    try:
        raise SystemExit(_main(argv))
    except (KeyboardInterrupt, EOFError):
        print("\rgoodbye")
        raise SystemExit(0)
    except Exception as e:
        print(e)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
