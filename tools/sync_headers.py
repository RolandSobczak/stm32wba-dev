#!/usr/bin/env python3
"""Przenosi zmiane kolejnosci nozek na listwach z plytki z powrotem do `headers.ato`.

Po co to istnieje
-----------------
Kolejnosc sygnalow na listwie widac dopiero przy trasowaniu: dopiero wtedy
wychodzi, ze dwie linie sie krzyzuja i wystarczy zamienic je miejscami.
Naturalnym miejscem na te poprawke jest pcbnew - i tam wolno ja zrobic.

Problem w tym, ze **atopile traktuje `.ato` jako jedyne zrodlo prawdy**.
Najblizszy `ato build` przepisze przypisanie sieci do padow z powrotem wedlug
kodu, a miedz zostanie tam, gdzie lezy - czyli bedzie laczyc juz co innego.
To nie konczy sie bledem, tylko cicho zamienia polaczenia na zwarcia
i przerwy. Dlatego kazda taka zmiana musi wrocic do `.ato` ZANIM padnie
kolejny `ato build`.

Jak to dziala
-------------
Narzedzie nie zgaduje i nie trzyma zadnej mapy "siec -> pole w kodzie",
ktora mogla by sie zestarzec. Liczy **permutacje**:

    stara plytka (z gita)  : pad -> siec
    nowa plytka (z dysku)  : pad -> siec
    `headers.ato` (z gita) : pad -> wyrazenie w kodzie

Skoro commit zawiera plytke i kod zgodne ze soba, to z dwoch pierwszych
wychodzi, ktory pad przejal siec ktorego - a trzecia mowi, jakie wyrazenie
stalo przy tamtym padzie. Przestawienie wyrazen wedlug tej samej permutacji
daje `.ato` opisujace dokladnie to, co narysowales.

Zalozenie jest jedno i jest sprawdzane: **sygnaly mozna miedzy padami
PRZESTAWIAC, ale nie wolno ich dokladac ani usuwac**. Pojawienie sie na
listwie sieci, ktorej tam wczesniej nie bylo, konczy sie odmowa - bo wtedy
nie ma z czego odtworzyc wyrazenia w kodzie i trzeba to dopisac recznie.

Uzycie
------
    python3 tools/sync_headers.py            # tylko pokaz roznice
    python3 tools/sync_headers.py --apply    # przepisz headers.ato

Po `--apply` trzeba jeszcze uruchomic `ato build` i `tools/board_setup.py`,
zeby plytka i kod zgodzily sie co do numeracji sieci.
"""

import re
import subprocess
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
PLYTKA = KORZEN / "layouts" / "dev" / "dev.kicad_pcb"
KOD = KORZEN / "headers.ato"
LISTWY = ("J1", "J2")


def z_gita(sciezka: Path) -> str:
    """Zwraca tresc pliku z ostatniego commitu."""
    wzgledna = sciezka.relative_to(KORZEN)
    wynik = subprocess.run(["git", "-C", str(KORZEN), "show", f"HEAD:{wzgledna}"],
                           capture_output=True, text=True)
    if wynik.returncode != 0:
        raise SystemExit(f"blad: nie moge odczytac {wzgledna} z HEAD\n{wynik.stderr}")
    return wynik.stdout


def pady_z_plytki(tresc: str) -> dict:
    """Czyta `{listwa: {numer_padu: nazwa_sieci}}` wprost z pliku plytki.

    Parsowanie tekstem, a nie przez `pcbnew`, bo ta sama funkcja musi
    dzialac na tresci wyjetej z gita, ktorej nie ma na dysku.
    """
    wynik = {}
    for dopas in re.finditer(r'\(footprint\s+"[^"]*"(.*?)\n\t\)\n', tresc, re.S):
        blok = dopas.group(1)
        ref = re.search(r'\(property "Reference" "([^"]+)"', blok)
        if not ref or ref.group(1) not in LISTWY:
            continue
        pady = {}
        for pad in re.finditer(
                r'\(pad "(\w+)".*?(?:\(net \d+ "([^"]*)"\))?\s*\(uuid', blok, re.S):
            pady[pad.group(1)] = pad.group(2) or ""
        wynik[ref.group(1)] = pady
    return wynik


def linie_z_kodu(tresc: str) -> dict:
    """Czyta `{nazwa_modulu: {numer_padu: (wyrazenie, komentarz)}}` z `.ato`."""
    wynik = {}
    modul = None
    for linia in tresc.splitlines():
        m = re.match(r"^module\s+(\w+)\s*:", linia)
        if m:
            modul = m.group(1)
            wynik[modul] = {}
            continue
        m = re.match(r"^(\s*)conn\.p(\d+)\s*~\s*([^#\n]+?)\s*(#.*)?$", linia)
        if m and modul:
            wynik[modul][m.group(2)] = (m.group(3), m.group(4) or "")
    return {k: v for k, v in wynik.items() if v}


def permutacja(stare: dict, nowe: dict, listwa: str) -> dict:
    """Dla kazdego padu mowi, z ktorego padu przyszla jego nowa siec.

    Sieci powtarzalne (GND, +3V3) wystepuja na kilku padach naraz, wiec
    dopasowanie jest zachlanne: kazdy pad zrodlowy moze byc uzyty raz.
    """
    wolne = {}
    for pad, siec in stare.items():
        wolne.setdefault(siec, []).append(pad)
    # Pady, ktore sie nie ruszyly, rezerwuja swoje zrodlo jako pierwsze -
    # inaczej zachlanne dopasowanie potrafi przehandlowac dwie identyczne
    # masy i wygenerowac zmiane tam, gdzie nic sie nie stalo.
    mapa, braki = {}, []
    for pad, siec in nowe.items():
        if stare.get(pad) == siec:
            wolne[siec].remove(pad)
            mapa[pad] = pad
    for pad, siec in nowe.items():
        if pad in mapa:
            continue
        if not wolne.get(siec):
            braki.append((pad, siec))
            continue
        mapa[pad] = wolne[siec].pop(0)
    if braki:
        opis = ", ".join(f"p{p} = {s or '(bez sieci)'}" for p, s in braki)
        raise SystemExit(
            f"blad: na listwie {listwa} sa sieci, ktorych wczesniej tam nie bylo:"
            f" {opis}\n"
            "  To narzedzie umie tylko PRZESTAWIAC sygnaly miedzy padami.\n"
            "  Dolozenie nowego sygnalu trzeba dopisac w `headers.ato` recznie,\n"
            "  bo w kodzie nie ma go z czego odtworzyc.")
    return mapa


def main() -> int:
    stosuj = "--apply" in sys.argv

    stara = pady_z_plytki(z_gita(PLYTKA))
    nowa = pady_z_plytki(PLYTKA.read_text())
    kod_tekst = KOD.read_text()
    kod = linie_z_kodu(z_gita(KOD))

    if set(stara) != set(LISTWY) or set(nowa) != set(LISTWY):
        raise SystemExit(f"blad: nie znalazlem obu listew {LISTWY} w pliku plytki")

    # Modul `.ato` rozpoznajemy po tym, ktory z nich opisuje te sama liczbe
    # padow i te same numery, co dana listwa. Przy dwoch listwach 1x12
    # trzeba jeszcze rozstrzygnac, ktora jest ktora - robi to zgodnosc
    # sieci stalych, czyli tych, ktore sie nie zmienily.
    moduly = {}
    for listwa in LISTWY:
        kandydaci = [m for m, p in kod.items() if set(p) == set(stara[listwa])]
        if len(kandydaci) == 1:
            moduly[listwa] = kandydaci[0]
    if set(moduly) != set(LISTWY) or len(set(moduly.values())) != len(LISTWY):
        # Rozstrzygniecie po tresci: listwa zasilania ma `vbus`, GPIO ma `spare`.
        moduly = {}
        for m, pady in kod.items():
            tresci = " ".join(w for w, _ in pady.values())
            if "vbus" in tresci:
                moduly["J2"] = m
            elif "spare" in tresci:
                moduly["J1"] = m
    if set(moduly) != set(LISTWY):
        raise SystemExit("blad: nie umiem dopasowac listew do modulow w headers.ato")

    zmiany = []
    nowe_linie = {}
    for listwa in LISTWY:
        mapa = permutacja(stara[listwa], nowa[listwa], listwa)
        pady_kodu = kod[moduly[listwa]]
        for pad in sorted(nowa[listwa], key=int):
            zrodlo = mapa[pad]
            if zrodlo == pad:
                continue
            zmiany.append((listwa, pad, stara[listwa][pad], nowa[listwa][pad]))
            nowe_linie[(moduly[listwa], pad)] = pady_kodu[zrodlo]

    if not zmiany:
        print("listwy na plytce zgadzaja sie z headers.ato - nie ma czego przenosic")
        return 0

    print(f"roznic: {len(zmiany)}")
    for listwa, pad, bylo, jest in zmiany:
        print(f"  {listwa}-p{pad:<3s} bylo {bylo or '(bez sieci)':<12s} "
              f"-> jest {jest or '(bez sieci)'}")

    if not stosuj:
        print("\nto byl tylko podglad; `--apply` przepisze headers.ato")
        return 0

    modul = None
    wyjscie = []
    for linia in kod_tekst.splitlines():
        m = re.match(r"^module\s+(\w+)\s*:", linia)
        if m:
            modul = m.group(1)
        m = re.match(r"^(\s*)conn\.p(\d+)\s*~\s*([^#\n]+?)\s*(#.*)?$", linia)
        if m and (modul, m.group(2)) in nowe_linie:
            wyraz, komentarz = nowe_linie[(modul, m.group(2))]
            odstep = f"  {komentarz}" if komentarz else ""
            wyjscie.append(f"{m.group(1)}conn.p{m.group(2)} ~ {wyraz}{odstep}")
        else:
            wyjscie.append(linia)
    KOD.write_text("\n".join(wyjscie) + "\n")
    print(f"\nprzepisano {KOD.relative_to(KORZEN)}")
    print("\nUWAGA: tabela listew w naglowku `headers.ato` NIE zostala ruszona.")
    print("  To proza, nie kod - przepisanie jej automatem psuje wiecej, niz")
    print("  naprawia. Ale naglowek jest teraz niezgodny z kodem i trzeba go")
    print("  poprawic recznie, zanim ktos go przeczyta jako prawde.")
    print("\nteraz: ato build -b dev  oraz  python3 tools/board_setup.py --board dev")
    return 0


if __name__ == "__main__":
    sys.exit(main())
