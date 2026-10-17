"""Sklada komplet plikow produkcyjnych z gotowej plytki.

Zrodlem jest **plik plytki z repozytorium**, a nie przebudowa z atopile.
To celowe: plytka w gicie jest tym, co faktycznie idzie do produkcji, i ma
juz w sobie miedz reczna, wylewki i blokady. Przebudowa w CI musialaby
odtworzyc caly lancuch narzedzi, a przy okazji zdjelaby blokady ze sciezek.

**Uruchamiaj to PO `tools/board_setup.py`, nie przed.** Skrypt eksportuje
to, co jest w pliku - a `board_setup` dopiero nadaje wylewkom siec, wylewa
je i stawia przelotki w padach termicznych. Gerbery wziete przed nim maja
inna miedz niz plytka, ktora sprawdzales w DRC.

Wszystkie dane do BOM-u i pliku pozycji siedza w polach footprintow na
plytce (`LCSC`, `Manufacturer`, `Partnumber`), wiec atopile nie jest tu
w ogole potrzebne.

    python3 tools/fabrication.py --board dev [--out build/fab-dev]

Powstaje:

    gerbers.zip              gerbery + wiercenia, spakowane pod JLCPCB
    bom_zakupy.csv           WSZYSTKO z numerem LCSC - lista zakupow
    bom_montaz_jlc.csv       zawezone: co JLCPCB ma zmontowac
    cpl_montaz_jlc.csv       pozycje tych samych czesci
    cpl_wszystko.csv         pozycje wszystkich czesci z LCSC
    plytka.pdf               warstwy miedzi i opisu do ogladania
    plytka.step              model 3D do mechaniki
    montaz_recznie.csv       czesci BEZ numeru LCSC - do wlutowania samemu
"""

from __future__ import annotations

import argparse
import json
import csv
import re
import shutil
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import pcbnew

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))
import boards

BOARD = boards.select()
PCB = BOARD.pcb

# Prawdziwy numer LCSC to "C" i cyfry. Czesci lutowane recznie maja w tym
# samym polu tekst zastepczy ("PinHeader-2x08-2.54", "OLED-096-I2C"), wiec
# sprawdzanie samej niepustosci wpuscilo by je do BOM-u i JLCPCB
# probowaloby zamowic cos, czego nie ma w katalogu.
LCSC_RE = re.compile(r"C\d+")


def jlc_part(p: dict) -> bool:
    return bool(LCSC_RE.fullmatch(p["lcsc"]))


# ─── Co zamawiamy w montazu, a co lutujemy sami ──────────────────────────
#
# JLCPCB montuje TYLKO to, czego nie da sie sensownie polutowac grotem:
#
#   * obudowy **leadless** - QFN, SON, DFN, LGA. Nie maja nozek, tylko
#     pady pod spodem; bez szablonu i goracego powietrza nie ma do nich
#     dostepu, a pod procesorem jest jeszcze pad termiczny z 22 przelotkami;
#   * `FL1` - filtr MLPF ma szesc padow w rastrze 0,50 mm na obudowie
#     1,6 x 1,0 mm i siedzi w torze RF, gdzie zimny lut widac dopiero
#     jako brak zasiegu;
#   * kwarce - NX2016SA ma 2,0 x 1,6 mm i cztery pady pod spodem, a zle
#     polutowany rezonator nie jest "troche gorszy", tylko nie startuje.
#
# Reszta - rezystory, kondensatory, diody, przyciski, zlacza - idzie
# recznie. Przy 0603 i wiekszych to kwadrans roboty, a kazda pozycja
# w montazu JLCPCB to osobna oplata za podajnik.
LEADLESS = ("QFN", "SON", "DFN", "LGA")
MONTAZ_WPROST = ("FL1",)
MONTAZ_FOOTPRINT = ("CRYSTAL",)


def do_montazu(p: dict) -> bool:
    """Czy ta czesc idzie do montazu w JLCPCB."""
    if not jlc_part(p):
        return False
    if p["ref"] in MONTAZ_WPROST:
        return True
    fp = p["footprint"].split(":")[-1].upper()
    return any(k in fp for k in LEADLESS + MONTAZ_FOOTPRINT)


def comment(p: dict) -> str:
    """Opis pozycji: wartosc elementu, a dla ukladow numer katalogowy."""
    return p["value"] or p["partnumber"] or p["footprint"].split(":")[-1]


# Warstwy, ktorych oczekuje JLCPCB. Miedz liczy sie z plytki, bo plytki
# stosu maja rozna liczbe warstw (`head` cztery, `base` szesc), a lista
# wpisana na sztywno wyslalaby do produkcji plytke bez dwoch warstw.
def warstwy_miedzi(board: pcbnew.BOARD) -> str:
    wlaczone = board.GetEnabledLayers()
    return ",".join(
        pcbnew.BOARD.GetStandardLayerName(l)
        for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu,
                  pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.B_Cu)
        if wlaczone.Contains(l))


def gerber_layers(board: pcbnew.BOARD) -> str:
    return (warstwy_miedzi(board) +
            ",F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts")


def pdf_layers(board: pcbnew.BOARD) -> str:
    return warstwy_miedzi(board) + ",F.SilkS,B.SilkS,Edge.Cuts"


def run(*args: str) -> None:
    subprocess.run(["kicad-cli", *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def popraw_kolejnosc_warstw(katalog: Path, board: pcbnew.BOARD) -> list[str]:
    """Nazywa gerbery miedzi wewnetrznej po POZYCJI W STOSIE, nie po nazwie.

    Dwie rzeczy trzeba tu naprawic i obie moglyby skonczyc sie plytka
    zbudowana z plaszczyznami nie tam, gdzie trzeba.

    **Nazwa pliku.** `kicad-cli` nazywa gerber nazwa UZYTKOWNIKA warstwy, a my
    nazwalismy warstwy po funkcji, zeby bylo widac, gdzie jest masa - wychodzi
    z tego `base-GND.gbr` i `base-PWR.gbr`. Fab rozpoznaje warstwy po nazwach
    plikow i takich nie zna. Po tym kroku pliki nazywaja sie `In1_Cu` .. `In4_Cu`
    wedlug kolejnosci w stosie, czyli tak, jak wyglada zwykly eksport z KiCada.

    **Numer w pliku zadania.** KiCad 9.0.2 wpisuje do `.gbrjob` `Copper,L<n>`,
    gdzie `n` to jego WEWNETRZNY identyfikator warstwy powiekszony o jeden, a
    nie pozycja w stosie: `In1_Cu` ma id 4, wiec wychodzi `L5`, a `In4_Cu` ma
    id 10, wiec `L11` - na plytce szesciowarstwowej. Wierzch i spod sa
    numerowane poprawnie, wiec bledu nie widac, dopoki nie policzy sie warstw
    wewnetrznych. Tu numeracja jest przeliczana na pozycje w stosie.
    """
    stos = list(board.GetEnabledLayers().CuStack())
    ile = len(stos)
    zmiany: dict[str, str] = {}
    funkcje: dict[str, str] = {}
    for i, warstwa in enumerate(stos, start=1):
        nazwa = board.GetLayerName(warstwa).replace(".", "_")
        stara = next((p for p in katalog.glob(f"*-{nazwa}.gbr")), None)
        if stara is None:
            continue
        if warstwa == pcbnew.F_Cu:
            docelowa, funkcja = "F_Cu", "Copper,L1,Top"
        elif warstwa == pcbnew.B_Cu:
            docelowa, funkcja = "B_Cu", f"Copper,L{ile},Bot"
        else:
            docelowa, funkcja = f"In{i - 1}_Cu", f"Copper,L{i},Inr"
        nowa = stara.with_name(stara.name.replace(f"-{nazwa}.gbr",
                                                 f"-{docelowa}.gbr"))
        if nowa != stara:
            stara.rename(nowa)
        zmiany[stara.name] = nowa.name
        funkcje[nowa.name] = funkcja

    for job in katalog.glob("*.gbrjob"):
        d = json.loads(job.read_text(encoding="utf8"))
        for wpis in d.get("FilesAttributes", []):
            wpis["Path"] = zmiany.get(wpis["Path"], wpis["Path"])
            if wpis["Path"] in funkcje:
                wpis["FileFunction"] = funkcje[wpis["Path"]]
        job.write_text(json.dumps(d, indent=4), encoding="utf8")
    return [f"{s} -> {n}" for s, n in zmiany.items() if s != n]


def board_parts(board: pcbnew.BOARD) -> list[dict]:
    """Wyciaga z plytki wszystko, czego potrzebuja BOM i plik pozycji."""
    out = []
    for f in board.GetFootprints():
        pos = f.GetPosition()
        props = {k: f.GetFieldText(k) for k in
                 ("LCSC", "Manufacturer", "Partnumber", "atopile_address")
                 if f.HasFieldByName(k)}
        out.append({
            "ref": f.GetReference(),
            "value": f.GetValue(),
            "footprint": f.GetFPIDAsString(),
            "lcsc": props.get("LCSC", "").strip(),
            "manufacturer": props.get("Manufacturer", "").strip(),
            "partnumber": props.get("Partnumber", "").strip(),
            "ato": props.get("atopile_address", "").strip(),
            "x": pcbnew.ToMM(pos.x),
            "y": pcbnew.ToMM(pos.y),
            "rot": f.GetOrientationDegrees(),
            "bottom": f.IsFlipped(),
            # `exclude_from_bom` zdjete w pliku czesci. Na tej plytce ma to
            # jeden element: antena, ktora jest KSZTALTEM MIEDZI, a nie
            # czescia - nie ma jej czym wlutowac ani czego zamowic.
            "bom_off": f.IsExcludedFromBOM(),
        })
    return sorted(out, key=lambda p: (p["ref"][:2], len(p["ref"]), p["ref"]))


def write_bom(parts: list[dict], out: Path) -> tuple[int, int]:
    """Lista zakupow: WSZYSTKO z numerem LCSC, z iloscia na plytke.

    To nie jest plik do wgrania w zamowienie montazu - od tego jest
    `bom_montaz_jlc.csv`. Ten ma pomoc przy kupowaniu, wiec ma kolumne
    `Ilosc`: bez niej zamawianie z zapasem sprowadza sie do liczenia
    przecinkow w liscie oznaczen.

    Sa tu takze czesci, ktore lutujemy sami - kupuje sie je w tym samym
    zamowieniu, niezaleznie od tego, kto je potem przylutuje.
    """
    groups: dict[tuple, list[str]] = defaultdict(list)
    for p in parts:
        if not jlc_part(p):
            continue
        groups[(comment(p), p["footprint"], p["lcsc"])].append(p["ref"])
    with out.open("w", newline="", encoding="utf8") as fh:
        w = csv.writer(fh)
        w.writerow(["Comment", "Designator", "Ilosc", "Footprint",
                    "LCSC Part #", "Montaz"])
        for (value, fp, lcsc), refs in sorted(groups.items(),
                                              key=lambda kv: kv[0][2]):
            gdzie = "JLC" if any(do_montazu(p) for p in parts
                                 if p["ref"] in refs) else "recznie"
            w.writerow([value, ",".join(refs), len(refs), fp, lcsc, gdzie])
    return len(groups), sum(len(r) for r in groups.values())


def write_cpl(parts: list[dict], out: Path) -> int:
    """Plik pozycji w formacie JLCPCB.

    Obroty sa przepisywane wprost z plytki. JLCPCB dla czesci obudowy
    stosuje wlasna orientacje odniesienia i czasem trzeba je skorygowac -
    to sie sprawdza w ich podgladzie przed zamowieniem, nie tutaj.
    """
    n = 0
    with out.open("w", newline="", encoding="utf8") as fh:
        w = csv.writer(fh)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for p in parts:
            if not jlc_part(p):
                continue
            w.writerow([p["ref"], f"{p['x']:.4f}mm", f"{-p['y']:.4f}mm",
                        "bottom" if p["bottom"] else "top", f"{p['rot']:.2f}"])
            n += 1
    return n


def write_manual(parts: list[dict], out: Path) -> int:
    """Czesci bez numeru LCSC - te trzeba wlutowac samemu.

    Na tej plytce sa to: dwie listwy goldpinowe, zlacze SWD i cztery pady
    pomiarowe. Nie sa brakiem w projekcie - kupuje sie je poza JLCPCB albo
    nie kupuje wcale.

    Elementy z `exclude_from_bom` NIE trafiaja na te liste. Na tej plytce
    jest to antena: ksztalt miedzi, a nie czesc - nie ma czego zamowic ani
    czym wlutowac, wiec wpis tylko mylilby przy kompletowaniu zakupow.

    Uwaga przy tej plytce: komplet jest lutowany recznie, wiec plik ten
    jest w praktyce lista zakupow, a nie lista "tego, czego JLC nie
    zrobi".
    """
    rows = [p for p in parts if not jlc_part(p) and not p["bom_off"]]
    with out.open("w", newline="", encoding="utf8") as fh:
        w = csv.writer(fh)
        w.writerow(["Designator", "Value", "Footprint", "Modul atopile"])
        for p in rows:
            w.writerow([p["ref"], comment(p), p["footprint"], p["ato"]])
    return len(rows)


def write_bom_montaz(parts: list[dict], out: Path) -> tuple[int, int]:
    """BOM dla JLCPCB zawezony do czesci, ktore faktycznie montuja."""
    groups: dict[tuple, list[str]] = defaultdict(list)
    for p in parts:
        if not do_montazu(p):
            continue
        groups[(comment(p), p["footprint"], p["lcsc"])].append(p["ref"])
    with out.open("w", newline="", encoding="utf8") as fh:
        w = csv.writer(fh)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, fp, lcsc), refs in sorted(groups.items(),
                                              key=lambda kv: kv[0][2]):
            w.writerow([value, ",".join(refs), fp, lcsc])
    return len(groups), sum(len(r) for r in groups.values())


def write_cpl_montaz(parts: list[dict], out: Path) -> int:
    """Plik pozycji zawezony tak samo jak BOM montazowy.

    Musi zgadzac sie z nim CO DO SZTUKI - JLCPCB odrzuca zlecenie, w
    ktorym pozycja wystepuje w jednym pliku, a w drugim nie.
    """
    n = 0
    with out.open("w", newline="", encoding="utf8") as fh:
        w = csv.writer(fh)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for p in parts:
            if not do_montazu(p):
                continue
            w.writerow([p["ref"], f"{p['x']:.4f}mm", f"{-p['y']:.4f}mm",
                        "bottom" if p["bottom"] else "top", f"{p['rot']:.2f}"])
            n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = PROJECT / (args.out or f"build/fab-{BOARD}")
    if out.exists():
        shutil.rmtree(out)
    (out / "gerbers").mkdir(parents=True)

    board = pcbnew.LoadBoard(str(PCB))
    run("pcb", "export", "gerbers", "--layers", gerber_layers(board),
        "--no-protel-ext", "-o", str(out / "gerbers") + "/", str(PCB))
    run("pcb", "export", "drill", "--format", "excellon",
        "--excellon-separate-th", "-o", str(out / "gerbers") + "/", str(PCB))
    przemianowane = popraw_kolejnosc_warstw(out / "gerbers", board)

    archive = out / "gerbers.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted((out / "gerbers").iterdir()):
            z.write(f, f.name)
    n_gerber = len(list((out / "gerbers").iterdir()))
    shutil.rmtree(out / "gerbers")

    run("pcb", "export", "pdf", "--layers", pdf_layers(board),
        "-o", str(out / "plytka.pdf"), str(PCB))
    run("pcb", "export", "step", "--subst-models",
        "-o", str(out / "plytka.step"), str(PCB))

    parts = board_parts(board)
    # Pelny BOM: WSZYSTKO z numerem LCSC, takze to, co lutujemy sami.
    # To jest lista zakupow - czesci kupuje sie w jednym zamowieniu,
    # niezaleznie od tego, kto je pozniej przylutuje.
    kinds, placed = write_bom(parts, out / "bom_zakupy.csv")
    cpl = write_cpl(parts, out / "cpl_wszystko.csv")
    # Zawezone do tego, co JLCPCB ma zmontowac. Oba pliki musza byc
    # zgodne co do sztuki - patrz `write_cpl_montaz`.
    m_kinds, m_placed = write_bom_montaz(parts, out / "bom_montaz_jlc.csv")
    m_cpl = write_cpl_montaz(parts, out / "cpl_montaz_jlc.csv")
    manual = write_manual(parts, out / "montaz_recznie.csv")

    print(f"gerbery       {n_gerber} plikow -> gerbers.zip")
    for z in przemianowane:
        print(f"              {z}")
    print(f"BOM zakupow   {kinds} pozycji, {placed} sztuk (wszystko z LCSC)")
    print(f"montaz JLC    {m_kinds} pozycji, {m_placed} sztuk "
          f"(leadless + FL1 + kwarce)")
    print(f"              pozycje: {m_cpl} elementow "
          f"{'ZGODNE z BOM-em' if m_cpl == m_placed else 'NIEZGODNE - SPRAWDZ'}")
    print(f"pozycje (all) {cpl} elementow")
    print(f"recznie       {manual} elementow bez numeru LCSC")
    print(f"razem na plytce: {len(parts)} elementow")
    print(f"\nwszystko w {out.relative_to(PROJECT)}")


if __name__ == "__main__":
    main()
