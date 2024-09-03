from __future__ import annotations

import argparse
import collections
import math
from itertools import batched
from typing import Callable, NamedTuple

import requests
from colorama import Back, Fore, Style
from websockets.sync.client import connect

from minesweeper.api import GameAPI, GameHTTPAPI, GameSession, GameWSAPI, GridParams

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
        32: "!",  # flag
        64: "*",  # post game-over correct flag
        65: f"{Fore.WHITE}{Back.RED}*{Style.RESET_ALL}",  # post game-over exploded mine
        66: "-",  # post game-over false flag
        67: "*",  # post game-over unflagged mine
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


def open(session: GameSession, api: GameAPI, args: list[str]) -> GameSession:
    try:
        x, y = map(int, args)
    except ValueError:
        raise ValueError("args must be integer")
    if not (0 <= x < session["width"]) or not (0 <= y < session["height"]):
        raise ValueError("out of bounds")
    if session["grid"][y * session["width"] + x] == -2:
        return api.open(x, y)
    else:
        return api.chord(x, y)


def flag(session: GameSession, api: GameAPI, args: list[str]) -> GameSession:
    try:
        x, y = map(int, args)
    except ValueError:
        raise ValueError("args must be integer")
    if not (0 <= x < session["width"]) or not (0 <= y < session["height"]):
        raise ValueError("out of bounds")
    return api.flag(x, y)


def new_game(params: GridParams, url: str, args: list[str]) -> GameSession:
    try:
        x, y = map(int, args)
    except ValueError:
        raise ValueError("args must be integer")
    if not (0 <= x < params["width"]) or not (0 <= y < params["height"]):
        raise ValueError("out of bounds")
    return GameHTTPAPI.new_game(url + "/game", {**params, "x": x, "y": y})


class PreGameCommand(NamedTuple):
    callback: Callable[[GridParams, str, list[str]], GameSession | None]
    nargs: int


class Command(NamedTuple):
    callback: Callable[[GameSession, GameAPI, list[str]], GameSession | None]
    nargs: int


HELP = """\
 Available commands:
    o [X] [Y]   : open (or chord) a square at X:Y
    f [X] [Y]   : flag (or unflag) a square at X:Y
    h           : print this message
"""

PRE_GAME_DISPATCH = {
    "o": PreGameCommand(new_game, 2),
    "f": PreGameCommand(
        lambda *_: (_ for _ in ()).throw(
            ValueError("use `o` to open any square to start the game")
        ),
        2,
    ),
    "h": PreGameCommand(lambda *_: (_ for _ in ()).throw(ValueError(HELP)), 0),
}

DISPATCH: dict[str, Command] = {
    "o": Command(open, 2),
    "f": Command(flag, 2),
    "h": Command(lambda *_: (_ for _ in ()).throw(ValueError(HELP)), 0),
}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "game_params",
        nargs="?",
        help="game grid's width, height, mine count (and optionally uniqueness, 1 or 0) separated with colons",
    )
    parser.add_argument(
        "-s",
        "--session-id",
        nargs="?",
        help="id of a previosly started session to resume it",
    )
    parser.add_argument(
        "-u",
        "--url",
        nargs="?",
        default="http://localhost:8000/v1",
        help="URL of a (remote) game server",
    )
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
            raise ValueError("game params may contain 3 or 4 parts")
        if not all(s for s in parts if s.isdigit()):
            raise ValueError("game params must be digits")
        width, height, mine_count, *u = map(int, parts)
        unique = bool(u[0]) if u else True
        params = GridParams(
            width=width, height=height, mine_count=mine_count, unique=unique
        )
        grid = [-2] * (width * height)
        print(render_grid(grid, width))
        while not session:
            prompt = f"({mine_count}) > "
            cmd, *args = input(prompt).split()
            cmd = cmd.lower()
            if cmd not in PRE_GAME_DISPATCH:
                print(f"`{cmd}`: unknown command")
                continue
            command = PRE_GAME_DISPATCH[cmd]
            if len(args) != command.nargs:
                print(f"`{cmd}`: expected {command.nargs} args, got {len(args)}")
                continue
            try:
                update = command.callback(params, url, args)
                if update:
                    session = update
                    session_id = session["session_id"]
                    print(f"session id: {session_id}")
            except ValueError as e:
                print(f"`{cmd}`: {e}")

    ws_url = (
        "ws://"
        + url.removeprefix("http://").removeprefix("https://")
        + "/game/"
        + session_id
        + "/connect"
    )
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
                print(f"`{cmd}`: {e}")

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
