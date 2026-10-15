#!/usr/bin/env python3
"""Model 3D pamieci SD NAND w obudowie LGA-8 - prosto z tabeli wymiarow.

Footprint `LGA-8_MKDV_handsolder.kicad_mod` nie mial zadnego modelu, wiec
w widoku 3D w tym miejscu plytki byla dziura. W katalogu lezal wprawdzie
plik `LGA-8_L8.0-W6.0-P1.27-TL_MKDV4GCL-ABF.STEP` z EasyEDA, ale nie
nadaje sie do uzycia:

  * siega do Z = -0,21 mm, czyli **zanurza sie w laminat** zamiast stac
    na nim (seating plane w nocie katalogowej to spod obudowy),
  * ma 0,81 mm wysokosci, a nota daje A = 0,65 / 0,70 / 0,75 mm,
  * zawiera punkt (0, -3,81, -0,21) poza bryla, ktory rozciaga obwiednie
    modelu na 6,81 mm przy obudowie 6,00 mm.

Geometria padow w tamtym pliku jest za to dokladnie taka, jaka wychodzi
z noty - i to jest sprawdzian tego skryptu: niezaleznie policzone
krawedzie (X 3,000 / 3,850, Y 0,360 / 0,910 / 1,630 / 2,180) zgadzaja sie
co do setnej.

Wymiary - "MK SD NAND Product Datasheet", rozdz. 9 (JEDEC MO-222), kolumna
NOM. Jedna tabela obowiazuje cala rodzine MKDV1GCL / MKDV2GCL / MKDV4GCL,
wiec ten sam model opisuje takze pozostale dwie pojemnosci.

    A  0,70   grubosc calkowita (z padami)
    D  6,00   krotszy bok obudowy            -> os Y
    E  8,00   dluzszy bok obudowy            -> os X
    b  0,55   szerokosc pada
    L  0,85   dlugosc pada
    e  1,27   raster padow w kolumnie
    SD 0,635  odsuniecie skrajnego rzedu od osi (D1 = 3,81 = 2 x 1,905)
       0,15   odstep zewnetrznej krawedzi pada od krawedzi obudowy

Uklad wspolrzednych jest ukladem KiCada dla modeli: X w prawo, **Y do
gory** (czyli przeciwnie niz w pliku footprintu), Z w gore od laminatu.
Pin 1 ma w footprincie Y = -1,9, wiec w modelu wypada u gory po lewej.

Model powstaje w jadrze OpenCASCADE (DRAWEXE z pakietu `opencascade`),
a nie przez recznie sklecony plik STEP - bryly i kolory zapisuje wtedy
ten sam kod, ktorego uzywa KiCad do czytania.

Uruchomienie:

    python3 tools/sdnand_step.py
"""

import os
import re
import subprocess
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
CZESC = KORZEN / "parts" / "MK_MKDV2GCL_ABF"
WYNIK = CZESC / "LGA-8_L8.0-W6.0-P1.27_MKDV2GCL-ABF.step"

# --- nota katalogowa, rozdz. 9, kolumna NOM ---
E_MM = 8.00          # dluzszy bok  -> X
D_MM = 6.00          # krotszy bok  -> Y
A_MM = 0.70          # wysokosc calkowita
PAD_L_MM = 0.85      # L - dlugosc pada wzdluz X
PAD_B_MM = 0.55      # b - szerokosc pada wzdluz Y
PAD_H_MM = 0.05      # metalizacja; nota jej nie wymiaruje, bo A ja obejmuje
RASTER_MM = 1.27     # e
SD_MM = 0.635        # odsuniecie wewnetrznego rzedu od osi
BRZEG_MM = 0.15      # odstep krawedzi pada od krawedzi obudowy

# Srodek pada: od krawedzi obudowy w glab o 0,15 + polowa dlugosci pada.
PAD_X_MM = E_MM / 2 - BRZEG_MM - PAD_L_MM / 2        # 3,425
PAD_Y_MM = (SD_MM, SD_MM + RASTER_MM)                # 0,635 i 1,905

# Kropka pin 1 - nad padem 1, wpuszczona w gorna sciane obudowy.
KROPKA_R_MM = 0.30
KROPKA_GL_MM = 0.04

KOLOR_OBUDOWY = (0.13, 0.13, 0.14)   # czarny epoksyd
KOLOR_PADU = (0.85, 0.72, 0.35)      # zloto
KOLOR_KROPKI = (0.80, 0.80, 0.78)    # nadruk


def tcl_box(nazwa, x, y, z, dx, dy, dz):
    return f"box {nazwa} {x:.4f} {y:.4f} {z:.4f} {dx:.4f} {dy:.4f} {dz:.4f}"


def zbuduj_skrypt(plik_wyjsciowy):
    """Zwraca skrypt Tcl dla DRAWEXE budujacy komplet bryl."""
    w = ["pload MODELING XDE XSDRAW OCAF", "XNewDoc D"]
    kolory = []

    # Obudowa stoi NA padach, zeby nic sie nie przenikalo:
    # pady 0,00-0,05, obudowa 0,05-0,70. Razem A = 0,70.
    w.append(tcl_box("korpus_pelny", -E_MM / 2, -D_MM / 2, PAD_H_MM,
                     E_MM, D_MM, A_MM - PAD_H_MM))

    # Kropka pin 1: wyciecie w gornej scianie plus wypelniajacy je walec.
    # Pin 1 jest w footprincie przy Y = -1,9, czyli w modelu przy Y = +1,905.
    kx, ky = -PAD_X_MM, PAD_Y_MM[1]
    w += [
        f"pcylinder wyciecie {KROPKA_R_MM:.4f} {KROPKA_GL_MM + 0.01:.4f}",
        f"ttranslate wyciecie {kx:.4f} {ky:.4f} {A_MM - KROPKA_GL_MM:.4f}",
        "bcut korpus korpus_pelny wyciecie",
        f"pcylinder kropka {KROPKA_R_MM - 0.02:.4f} {KROPKA_GL_MM - 0.005:.4f}",
        f"ttranslate kropka {kx:.4f} {ky:.4f} {A_MM - KROPKA_GL_MM:.4f}",
    ]
    kolory += [("korpus", KOLOR_OBUDOWY), ("kropka", KOLOR_KROPKI)]

    # Osiem padow. Numeracja jak w footprincie: 1-4 lewa kolumna od gory
    # (w modelu: od najwiekszego Y), 5-8 prawa kolumna od dolu.
    for nr, (sx, sy) in enumerate(
        [(-1, +1), (-1, +0.5), (-1, -0.5), (-1, -1),
         (+1, -1), (+1, -0.5), (+1, +0.5), (+1, +1)], start=1
    ):
        x = sx * PAD_X_MM
        y = (PAD_Y_MM[1] if abs(sy) == 1 else PAD_Y_MM[0]) * (1 if sy > 0 else -1)
        nazwa = f"pad{nr}"
        w.append(tcl_box(nazwa, x - PAD_L_MM / 2, y - PAD_B_MM / 2, 0.0,
                         PAD_L_MM, PAD_B_MM, PAD_H_MM))
        kolory.append((nazwa, KOLOR_PADU))

    for nazwa, (r, g, b) in kolory:
        w.append(f"XAddShape D {nazwa} 0")
        w.append(f"XSetColor D {nazwa} {r} {g} {b}")

    w.append(f'WriteStep D "{plik_wyjsciowy}"')
    w.append("exit")
    return "\n".join(w) + "\n"


def obwiednia(plik):
    """Czyta z gotowego STEP-a obwiednie i poziomy Z - do sprawdzenia."""
    tekst = Path(plik).read_text(encoding="latin-1")
    punkty = [
        tuple(float(v) for v in p)
        for p in re.findall(
            r"CARTESIAN_POINT\s*\(\s*'[^']*',\s*\(\s*"
            r"([-\d.E+]+)\s*,\s*([-\d.E+]+)\s*,\s*([-\d.E+]+)\s*\)", tekst)
    ]
    if not punkty:
        raise SystemExit("blad: w zapisanym pliku nie ma zadnych punktow")
    os_ = lambda i: (min(p[i] for p in punkty), max(p[i] for p in punkty))
    return os_(0), os_(1), os_(2), len(punkty)


def main():
    if not CZESC.is_dir():
        raise SystemExit(f"blad: brak katalogu {CZESC}")

    skrypt = Path(os.environ.get("TMPDIR", "/tmp")) / "sdnand_step.tcl"
    skrypt.write_text(zbuduj_skrypt(WYNIK))

    wynik = subprocess.run(["DRAWEXE", "-b", "-f", str(skrypt)],
                           capture_output=True, text=True)
    if wynik.returncode != 0 or not WYNIK.exists():
        sys.stderr.write(wynik.stdout + wynik.stderr)
        raise SystemExit("blad: DRAWEXE nie zapisal pliku")

    (xmin, xmax), (ymin, ymax), (zmin, zmax), n = obwiednia(WYNIK)
    print(f"zapisano {WYNIK.relative_to(KORZEN)}  ({WYNIK.stat().st_size // 1024} kB)")
    print(f"obwiednia X {xmin:+.3f} .. {xmax:+.3f}  ({xmax - xmin:.3f} mm, nota {E_MM:.2f})")
    print(f"obwiednia Y {ymin:+.3f} .. {ymax:+.3f}  ({ymax - ymin:.3f} mm, nota {D_MM:.2f})")
    print(f"obwiednia Z {zmin:+.3f} .. {zmax:+.3f}  ({zmax - zmin:.3f} mm, nota {A_MM:.2f})")

    bledy = []
    if abs((xmax - xmin) - E_MM) > 0.001:
        bledy.append("szerokosc X nie zgadza sie z E")
    if abs((ymax - ymin) - D_MM) > 0.001:
        bledy.append("szerokosc Y nie zgadza sie z D")
    if abs(zmin) > 0.001:
        bledy.append("model nie stoi na Z = 0 (zatopilby sie w laminacie)")
    if abs(zmax - A_MM) > 0.001:
        bledy.append("wysokosc nie zgadza sie z A")
    if bledy:
        raise SystemExit("blad: " + "; ".join(bledy))
    print("zgodne z nota katalogowa: obwiednia, wysokosc i seating plane")


if __name__ == "__main__":
    main()
