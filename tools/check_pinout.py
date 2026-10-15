#!/usr/bin/env python3
"""Sprawdza mape wyprowadzen procesora wobec danych ST.

Trzy pytania, na kazde osobna odpowiedz:

  1. Czy to, co wyszlo na plytke, zgadza sie z tym, co zamierzylismy?
     (tablica `ZAMIAR` nizej wobec pliku `.kicad_pcb`)
  2. Czy funkcja, ktorej od nozki wymagamy, naprawde na niej istnieje?
     (tablica `ZAMIAR` wobec `STM32WB55CGUx.xml` od ST)
  3. Czy zadna nozka nie zostala pominieta ani uzyta dwa razy?

Po co to w ogole jest
---------------------
Rewizja 1 trackera opierala mape wyprowadzen na tekscie wyciagnietym
z PDF-a i wyszly z tego dwa falszywe wnioski o pinach - wiersze zginely
przy konwersji. Blad tego rodzaju nie daje sie zauwazyc ani na schemacie,
ani na renderze: widac go dopiero przy uruchamianiu, na gotowej plytce,
jako peryferial, ktory milczy. Ten skrypt kosztuje sekunde i zamyka ten
rodzaj pomylki raz na zawsze.

`ZAMIAR` jest tutaj CELOWO przepisany recznie, a nie czytany z `mcu.ato`.
Gdyby byl czytany, sprawdzalby plik sam ze soba. Tak jak jest, trzeba go
dopisac przy kazdej zmianie przypisania - i to jest ta chwila, w ktorej
czlowiek patrzy w karte katalogowa po raz drugi.

Zrodlo danych ST: `STM32_open_pin_data/mcu/STM32WB55CGUx.xml`
(github.com/STMicroelectronics/STM32_open_pin_data), wgrane do `tools/`,
zeby sprawdzenie dzialalo bez sieci. Ten sam plik, z ktorego generowany
jest CubeMX.

    python3 tools/check_pinout.py        # kod wyjscia 1, jesli cos nie gra
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
PCB = PROJECT / "layouts" / "dev" / "dev.kicad_pcb"
XML = Path(__file__).resolve().parent / "STM32WB55CGUx.xml"
FOOTPRINT = "STM32WB55CGU6"

# nozka -> (nazwa sieci na plytce, wymagana funkcja ST albo None)
#
# Uwaga przy USB: po LEWEJ stoi nazwa SIECI (`USB_D_N`), po PRAWEJ nazwa
# SYGNALU u ST (`USB_DM`). Rozjechaly sie celowo - siec musi konczyc sie
# na `_P` / `_N`, zeby KiCad widzial pare roznicowa, a nazwa sygnalu jest
# ta, ktora podaje karta katalogowa i ktorej nie wolno zmieniac.
#
# `None` tam, gdzie nozka pracuje jako zwykly GPIO - wtedy nie ma czego
# sprawdzac w danych ST poza tym, ze nozka w ogole istnieje i jest I/O.
ZAMIAR = {
    1:  ("+3V3",      None),             # VBAT
    2:  ("LSE_IN",    "RCC_OSC32_IN"),
    3:  ("LSE_OUT",   "RCC_OSC32_OUT"),
    4:  ("BOOT0",     None),
    5:  ("PMIC_SCL",  "I2C1_SCL"),
    6:  ("PMIC_SDA",  "I2C1_SDA"),
    7:  ("NRST",      None),
    8:  ("+3V3",      None),             # VDDA
    9:  ("CC1",       "ADC1_IN5"),
    10: ("CC2",       "ADC1_IN6"),
    11: ("PA2",       None),             # wolna
    12: ("PA3",       None),             # wolna
    13: ("SD_CS",     None),             # GPIO, nie SPI1_NSS - patrz interfaces.ato
    14: ("SD_CLK",    "SPI1_SCK"),
    15: ("SD_MISO",   "SPI1_MISO"),
    16: ("SD_MOSI",   "SPI1_MOSI"),
    17: ("PA8",       None),             # wolna
    18: ("PA9",       None),             # wolna
    19: ("CHG_STAT",  None),
    20: ("+3V3",      None),             # VDD
    21: ("RF1",       "RF_RF1"),
    22: ("GND",       None),             # VSSRF
    23: ("+3V3",      None),             # VDDRF
    24: ("OSC_OUT",   "RCC_OSC_OUT"),
    25: ("OSC_IN",    "RCC_OSC_IN"),
    26: (None,        None),             # AT0 - celowo bez sieci
    27: (None,        None),             # AT1 - celowo bez sieci
    28: ("CHG_INT",   None),
    29: ("CHG_CE",    None),
    30: ("CHG_PG",    None),
    31: ("VFBSMPS",   None),
    32: ("GND",       None),             # VSSSMPS
    33: ("VLXSMPS",   None),
    34: ("+3V3",      None),             # VDDSMPS
    35: ("+3V3",      None),             # VDD
    36: ("PA10",      None),             # wolna
    37: ("USB_D_N",   "USB_DM"),
    38: ("USB_D_P",   "USB_DP"),
    39: ("SWDIO",     "SYS_JTMS-SWDIO"),
    40: ("+3V3",      None),             # VDDUSB
    41: ("SWCLK",     "SYS_JTCK-SWCLK"),
    42: ("EXT_CS",    None),             # CS ukladu zewnetrznego na SPI1
    43: ("SWO",       "SYS_JTDO-SWO"),
    44: ("GAUGE_INT", None),
    45: ("EXP_INT",   None),             # przerwanie z ekspandera TCA6408A
    46: ("PB6",       None),             # wolna
    47: ("PB7",       None),             # wolna
    48: ("+3V3",      None),             # VDD
    49: ("GND",       None),             # pad pod obudowa - JEDYNA masa ukladu
}


def poddrzewa(text: str, head: str):
    """Kolejne zrownowazone s-wyrazenia zaczynajace sie od `head`."""
    start = 0
    while True:
        i = text.find(head, start)
        if i < 0:
            return
        d = j = 0
        j = i
        instr = esc = False
        while True:
            ch = text[j]
            if instr:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    instr = False
            elif ch == '"':
                instr = True
            elif ch == "(":
                d += 1
            elif ch == ")":
                d -= 1
                if d == 0:
                    j += 1
                    break
            j += 1
        yield text[i:j]
        start = j


def z_plytki() -> dict[int, str | None]:
    text = PCB.read_text(encoding="utf8")
    fps = [b for b in poddrzewa(text, "(footprint ") if FOOTPRINT in b.split("\n")[0]]
    if len(fps) != 1:
        sys.exit(f"na plytce jest {len(fps)} ukladow {FOOTPRINT}, oczekiwano 1")
    out = {}
    for pb in poddrzewa(fps[0], "(pad "):
        num = re.match(r'\(pad "([^"]+)"', pb).group(1)
        net = re.search(r'\(net \d+ "([^"]*)"\)', pb)
        out[int(num)] = net.group(1) if net else None
    return out


def ze_st() -> dict[int, tuple[str, set[str]]]:
    ns = {"m": "http://dummy.com"}
    root = ET.parse(XML).getroot()
    return {int(p.get("Position")): (p.get("Name"),
                                     {s.get("Name") for s in p.findall("m:Signal", ns)})
            for p in root.findall("m:Pin", ns)}


def main() -> int:
    plytka = z_plytki()
    st = ze_st()
    bledy: list[str] = []

    if len(st) != 48:
        bledy.append(f"plik ST opisuje {len(st)} nozek, a UFQFPN-48 ma 48")

    for nozka, (siec, funkcja) in sorted(ZAMIAR.items()):
        nazwa = st[nozka][0] if nozka in st else "EP"
        realna = plytka.get(nozka)

        if siec is None:
            # Nozka ma zostac bez sieci. atopile nadaje takiej wlasna siec
            # jednopadowa nazwana jak numer nozki - to tez znaczy "wolna".
            if realna not in (None, str(nozka)):
                bledy.append(f"nozka {nozka} ({nazwa}) miala zostac wolna, "
                             f"a jest na sieci {realna!r}")
            continue

        if realna != siec:
            bledy.append(f"nozka {nozka} ({nazwa}): zamiar {siec!r}, "
                         f"na plytce {realna!r}")

        if funkcja and funkcja not in st[nozka][1]:
            bledy.append(f"nozka {nozka} ({nazwa}): wymagamy funkcji "
                         f"{funkcja!r}, a ST jej na tej nozce NIE MA "
                         f"(ma: {', '.join(sorted(st[nozka][1])) or 'nic'})")

    brakuje = sorted(set(range(1, 50)) - set(ZAMIAR))
    if brakuje:
        bledy.append(f"ZAMIAR nie opisuje nozek: {brakuje}")

    nadmiarowe = sorted(set(plytka) - set(ZAMIAR))
    if nadmiarowe:
        bledy.append(f"na plytce sa nozki spoza ZAMIARU: {nadmiarowe}")

    # Dwie rozne nozki na tej samej sieci sa dozwolone tylko dla zasilania
    # i masy. Wszedzie indziej to zwarcie, ktorego nikt nie chcial.
    wspolne = {}
    for nozka, (siec, _) in ZAMIAR.items():
        if siec and siec not in ("+3V3", "GND"):
            wspolne.setdefault(siec, []).append(nozka)
    for siec, nozki in wspolne.items():
        if len(nozki) > 1:
            bledy.append(f"siec {siec!r} siedzi na nozkach {nozki} - "
                         f"zwarcie albo literowka w ZAMIARZE")

    uzyte = len([1 for s, _ in ZAMIAR.values() if s])
    sprawdzone = len([1 for _, f in ZAMIAR.values() if f])
    if bledy:
        print(f"BLEDY ({len(bledy)}):")
        for b in bledy:
            print("  -", b)
        return 1
    print(f"mapa wyprowadzen OK: 48 nozek + pad, {uzyte} obsadzonych, "
          f"2 celowo wolne (AT0, AT1), {sprawdzone} funkcji sprawdzonych "
          f"wobec STM32WB55CGUx.xml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
