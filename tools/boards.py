"""Wybor plytki dla narzedzi z `tools/`.

Przeniesione z `gps_tracker-6l/tools/boards.py`. Tam projekt mial DWIE
plytki o tym samym obrysie (`base` i `head`) i domyslnej nie bylo celowo:
narzedzia zapisuja pliki plytek w miejscu, a milczaca pomylka co do tego,
ktora plytke sie wlasnie przepisuje, konczyla sie utrata roboty.

**Tutaj plytka jest jedna**, wiec ten argument znika razem z ryzykiem
i `--board` stal sie opcjonalny:

    python3 tools/board_setup.py 38 50
    python3 tools/board_setup.py --board dev 38 50

Zostaje za to drugie zadanie tego pliku, ktore z liczba plytek nie ma nic
wspolnego: **bramka na wersje KiCada**. Opis nizej.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
# ─── Wersja KiCada ────────────────────────────────────────────────────────
#
# Plytki sa w formacie KiCada 9 (`version 20241229`) i maja w nim zostac:
# `atopile` 0.15.8 nie czyta formatu 10, a podniesienie jest JEDNOKIERUNKOWE.
# KiCad 10 nie pyta o zdanie - otwiera plik, a przy pierwszym zapisie
# przepisuje go na swoj format bez ostrzezenia.
#
# Na tym komputerze `pcbnew` jest osiagalny z dwoch miejsc naraz: hostowy
# KiCad 10.0.5 i KiCad 9 w kontenerze `atopile`. O tym, ktory sie zaladuje,
# decyduje sam sposob uruchomienia - `python3 tools/cos.py` bierze hostowy,
# `distrobox enter -n atopile -- python3 tools/cos.py` bierze ten wlasciwy.
# Roznica jest niewidoczna az do zapisu.
#
# Ten import jest wiec bramka dla WSZYSTKICH narzedzi z tego katalogu:
# `boards.py` importuje kazde z nich, wiec sprawdzenie jest tu raz i nie da
# sie o nim zapomniec przy dopisywaniu kolejnego skryptu.
#
# Zdarzylo sie naprawde: `tools/unlock.py` uruchomiony bez `distrobox enter`
# zrobil swoje poprawnie i przy okazji podniosl plytke na format 20260206.
# Wykrylo to dopiero sprawdzenie wersji, a odtworzenie pliku wymagalo
# wylowienia recznie potrasowanej miedzi z uszkodzonej wersji.
KICAD_WERSJA = "9."

try:
    import pcbnew as _pcbnew
except ImportError:  # narzedzia, ktore nie tykaja plytki (floorplan.py)
    _pcbnew = None

if _pcbnew is not None:
    _wersja = _pcbnew.GetBuildVersion()
    if not _wersja.startswith(KICAD_WERSJA):
        raise SystemExit(
            f"zaladowal sie pcbnew {_wersja}, a plytki sa w formacie KiCada 9.\n"
            f"Zapis tym pcbnew podnioslby je na format 10, jednokierunkowo.\n"
            f"Uruchom narzedzie w kontenerze:\n"
            f"    distrobox enter -n atopile -- python3 tools/<nazwa>.py ...")


NAZWY = ("dev",)
DOMYSLNA = "dev"


@dataclass(frozen=True)
class Board:
    name: str

    @property
    def dir(self) -> Path:
        return PROJECT / "layouts" / self.name

    @property
    def pcb(self) -> Path:
        return self.dir / f"{self.name}.kicad_pcb"

    @property
    def pro(self) -> Path:
        return self.dir / f"{self.name}.kicad_pro"

    @property
    def prl(self) -> Path:
        return self.dir / f"{self.name}.kicad_prl"

    @property
    def fp_lib_table(self) -> Path:
        return self.dir / "fp-lib-table"

    def __str__(self) -> str:
        return self.name


def get(name: str) -> Board:
    if name not in NAZWY:
        raise SystemExit(f"nie ma plytki {name!r}; sa: {', '.join(NAZWY)}")
    b = Board(name)
    if not b.pcb.is_file():
        raise SystemExit(f"{b.pcb.relative_to(PROJECT)} nie istnieje - "
                         f"najpierw `ato build -b {name}`")
    return b


_wybrana: Board | None = None


def select() -> Board:
    """Zdejmuje `--board NAZWA` z argv i zwraca plytke. Idempotentne."""
    global _wybrana
    if _wybrana is not None:
        return _wybrana
    for i, a in enumerate(sys.argv[1:], start=1):
        if a in ("--board", "-b") and i + 1 < len(sys.argv):
            name = sys.argv[i + 1]
            del sys.argv[i : i + 2]
            break
        if a.startswith("--board="):
            name = a.split("=", 1)[1]
            del sys.argv[i]
            break
    else:
        name = DOMYSLNA
    _wybrana = get(name)
    return _wybrana


