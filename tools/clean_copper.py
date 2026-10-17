#!/usr/bin/env python3
"""Usuwa z plytki miedz, ktora nie prowadzi donikad.

Co to jest
----------
Przy trasowaniu zostaja odpadki: kawalek sciezki po skasowanym polaczeniu,
przelotka po przeniesionym sygnale, odcinek dlugi na dwanascie mikrometrow,
ktory powstal z nieudanego kliku. Zadne z tego nic nie laczy.

Produkcji to **nie blokuje** - fab wytrawi, co dostanie. Problem jest
gdzie indziej:

  * przelotka wisząca na torze o kontrolowanej impedancji jest odgalezieniem
    i psuje go tym bardziej, im wyzsza czestotliwosc. Na tej plytce dwie
    takie siedzialy na `USB_D_N`, czyli na polowce pary roznicowej;
  * kazdy taki kawalek zostaje w DRC jako ostrzezenie i przykrywa soba
    ostrzezenia, ktore cos znacza.

Dlaczego osobne narzedzie, a nie `board_setup.py`
--------------------------------------------------
`board_setup.py` biegnie po KAZDEJ przebudowie, takze w srodku pracy nad
trasowaniem. Niedokonczone polaczenie wyglada dokladnie tak samo jak
odpadek - obie maja koniec, ktory nic nie dotyka. Narzedzie kasujace
miedz nie moze uruchamiac sie samo, bo pierwsza rzecza, ktora skasuje,
bedzie trasa, ktora ktos wlasnie ciagnie.

Jak rozpoznaje
--------------
Pyta o to KiCada, a nie siebie: `TestTrackEndpointDangling` to ta sama
funkcja, z ktorej korzysta DRC przy `track_dangling` i `via_dangling`.
Dzieki temu narzedzie kasuje dokladnie to, co DRC zglasza - ani mniej,
ani wiecej.

Kasowanie jest **iteracyjne**: usuniecie odcinka moze odsłonic kolejny,
ktory wisial na nim. Petla konczy sie, gdy przebieg nie znajdzie nic.

Uzycie
------
    python3 tools/clean_copper.py            # tylko pokaz
    python3 tools/clean_copper.py --apply    # skasuj

Po `--apply` uruchom `tools/board_setup.py`, zeby wylewki wylaly sie na
nowo, i sprawdz DRC.
"""

import sys
from pathlib import Path

import pcbnew

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))
import boards

BOARD = boards.select()
PCB = BOARD.pcb

MAX_PRZEBIEGOW = 10


def wiszace(board: pcbnew.BOARD) -> list:
    """Slady i przelotki, ktorych koniec nic nie dotyka."""
    conn = board.GetConnectivity()
    out = []
    for t in board.GetTracks():
        pos = pcbnew.VECTOR2I()
        # Drugi argument to `aIgnoreTracksInPads` i MUSI byc True.
        #
        # Przy False funkcja zglasza takze slady, ktorych koniec lezy
        # WEWNATRZ padu - a takie sa polaczone przez ten pad i tylko
        # wygladaja na wiszace. Na tej plytce bylo ich trzy (`LSE_OUT`,
        # `CHG_CE`, `BOOT0`) i skasowanie ich zerwaloby dzialajace
        # polaczenia, w tym linie kwarcu.
        #
        # True daje dokladnie to, co DRC zglasza jako `track_dangling`
        # i `via_dangling` - sprawdzone przez porownanie obu list.
        if conn.TestTrackEndpointDangling(t, True, pos):
            out.append(t)
    return out


def opis(board: pcbnew.BOARD, t: pcbnew.PCB_TRACK) -> str:
    """Opis kawalka miedzi, czytany ZANIM cokolwiek zniknie z plytki.

    Dwie rzeczy robione sa tu ostroznie, bo bindingi KiCada 9 potrafia
    zwrocic goly `SwigPyObject` bez metod - ta sama usterka, ktora
    `board_setup.py` opisuje przy `GetDrawings()`:

      * plytka przychodzi argumentem, a nie z `t.GetBoard()`,
      * polozenie czytane jest z `GetStart()`, nie `GetPosition()`.
    """
    def xy(p):
        try:
            return f"{pcbnew.ToMM(p.x):.2f}, {pcbnew.ToMM(p.y):.2f}"
        except AttributeError:
            return "polozenie nieczytelne"

    siec = t.GetNetname() or "(bez sieci)"
    if t.Type() == pcbnew.PCB_VIA_T:
        return f"przelotka [{siec}] ({xy(t.GetPosition())})"
    return (f"slad [{siec}] {pcbnew.ToMM(t.GetLength()):.3f} mm na "
            f"{board.GetLayerName(t.GetLayer())} ({xy(t.GetStart())})")


def main() -> int:
    stosuj = "--apply" in sys.argv
    board = pcbnew.LoadBoard(str(PCB))

    przed_sladow = len([t for t in board.GetTracks()
                        if t.Type() != pcbnew.PCB_VIA_T])
    przed_przelotek = len([t for t in board.GetTracks()
                           if t.Type() == pcbnew.PCB_VIA_T])

    skasowane = []
    for przebieg in range(1, MAX_PRZEBIEGOW + 1):
        znalezione = wiszace(board)
        if not znalezione:
            break
        # `Delete`, nie `Remove`. Remove wyjmuje obiekt z plytki, ale nie
        # zwalnia go, i plytka zostaje w stanie, w ktorym `GetTracks()`
        # zwraca goly `SwigPyObject`. `board_setup.py` opisuje to samo
        # przy kasowaniu obrysu i starej siatki przelotek.
        opisy = [opis(board, t) for t in znalezione]
        skasowane += [(przebieg, o) for o in opisy]
        if stosuj:
            for t in znalezione:
                board.Delete(t)
        if not stosuj:
            break           # bez kasowania druga petla znalazlaby to samo
        board.BuildConnectivity()
    else:
        print(f"UWAGA: po {MAX_PRZEBIEGOW} przebiegach nadal cos wisi - "
              f"sprawdz recznie")

    if not skasowane:
        print("nie ma wiszacej miedzi")
        return 0

    print(f"wiszacych kawalkow: {len(skasowane)}")
    biezacy = 0
    for przebieg, txt in skasowane:
        if przebieg != biezacy:
            biezacy = przebieg
            if stosuj:
                print(f"  przebieg {przebieg}:")
        print(f"    {txt}")

    if not stosuj:
        print("\nto byl tylko podglad; `--apply` skasuje")
        return 0

    board.Save(str(PCB))
    po_sladow = len([t for t in board.GetTracks()
                     if t.Type() != pcbnew.PCB_VIA_T])
    po_przelotek = len([t for t in board.GetTracks()
                        if t.Type() == pcbnew.PCB_VIA_T])
    print(f"\nslady    {przed_sladow} -> {po_sladow}")
    print(f"przelotki {przed_przelotek} -> {po_przelotek}")
    print("teraz: python3 tools/board_setup.py --board "
          f"{BOARD} (wylewki) i DRC")
    return 0


if __name__ == "__main__":
    sys.exit(main())
