import typing as T
from dataclasses import asdict, dataclass
from itertools import batched

from colorama import Back, Fore, Style
from requests import get


@dataclass
class GameParams:
    width: int
    height: int
    mine_count: int
    unique: bool
    x: int
    y: int

    def validate_move(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height


class Minesweeper:
    url: str
    params: GameParams
    session_id: str
    grid: list[int]
    dead: bool
    won: bool

    def __init__(
        self,
        url: str,
        params: GameParams,
        session_id: str,
        grid: list[int],
        dead: bool,
        won: bool,
    ) -> None:
        self.url = url
        self.params = params
        self.session_id = session_id
        self.grid = grid
        self.dead = dead
        self.won = won

    @staticmethod
    def cell_to_str(cell: int) -> str:
        match cell:
            case -3:  # question mark
                return "?"
            case -2:  # unknown
                return "#"
            case -1:  # flagged
                return "P"
            case 0:
                return "."
            case 1:
                return f"{Fore.CYAN}1{Style.RESET_ALL}"
            case 2:
                return f"{Fore.GREEN}2{Style.RESET_ALL}"
            case 3:
                return f"{Fore.RED}3{Style.RESET_ALL}"
            case 4:
                return f"{Style.DIM}{Fore.BLUE}4{Style.RESET_ALL}"
            case 5:
                return f"{Style.DIM}{Fore.RED}5{Style.RESET_ALL}"
            case 6:
                return f"{Style.DIM}{Fore.GREEN}6{Style.RESET_ALL}"
            case 7:
                return f"{Style.DIM}{Fore.LIGHTBLACK_EX}7{Style.RESET_ALL}"
            case 8:
                return f"{Style.DIM}{Fore.BLUE}8{Style.RESET_ALL}"
            case 64:  # post game-over mine
                return f"*"
            case 65:  # post game-over exploded mine
                return f"{Fore.WHITE}{Back.RED}*{Style.RESET_ALL}"
            case 66:  # post game-over false flag
                return "X"
            case _:  # bad cell code
                return "%"

    @classmethod
    def new_game(cls, url: str, params: GameParams) -> T.Self:
        res = get(f"{url}/newgame", params=asdict(params)).json()
        return cls(url, params, **res)

    def validate_move(self, x: int, y: int) -> bool:
        return self.params.validate_move(x, y)

    def open(self, x: int, y: int):
        res = get(f"{self.url}/{self.session_id}/open?{x=}&{y=}").json()
        self.grid = res["grid"]
        self.dead = res["dead"]
        self.won = res["won"]

    def render(self) -> str:
        field = (
            " ".join(map(self.cell_to_str, line))
            for line in batched(self.grid, self.params.width)
        )
        field = (
            f"{Style.DIM}{i}{Style.RESET_ALL} {line}" for i, line in enumerate(field)
        )
        top_ruler = (
            f"  {Style.DIM}"
            f"{' '.join(map(str, range(self.params.width)))}"
            f"{Style.RESET_ALL}"
        )
        field = (top_ruler, *field)
        return "\n".join(field)


def main(argv: list[str] | None = None) -> int:
    print("<Ctrl+C> to exit")

    url = "http://localhost:8000"

    if not get(f"{url}/status").ok:
        print(f"server {url} is down")
        return 1

    params = GameParams(10, 10, 10, True, 5, 5)

    game = Minesweeper.new_game(url, params)
    print(f"session id: {game.session_id}")

    print(game.render())

    while not (game.won or game.dead):
        while print("> ", end="") or (
            len(command := input().split()) != 2
            or not all(x for x in command if x.isdigit())
            or not game.validate_move(*(point := list(map(int, command))))
        ):
            print("Input two valid field indices")

        game.open(*point)
        print(game.render())

    if game.dead:
        print("You lost!")
    elif game.won:
        print("You won!")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\rgoodbye")
        raise SystemExit(0)
