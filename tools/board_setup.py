"""Ustawia to, czego atopile nie ustawia: stos warstw, obrys i reguly.

atopile generuje plytke z samymi footprintami i sieciami - bez obrysu,
na dwoch warstwach i z zerowym odstepem izolacyjnym. Ten skrypt doklada
reszte, idempotentnie, zeby dalo sie go puscic po kazdym `ato build`.

Przeniesiony z `gps_tracker-6l/tools/board_setup.py`. Wyciete zostaly
wszystkie funkcje obslugujace kanapke z dwoch plytek (wciecie pod kabel
ogniwa, wciecie pod nozki listwy ekranu, odbijanie ksztaltow z plytki
dolnej, wciecie pod zlacze SWD) - tutaj plytka jest jedna i prostokatna.
Zostalo to, co opisuje KAZDA plytke: stos, obrys, otwory, wylewki, klasy
sieci i reguly.

Doszla jedna rzecz, ktorej tam nie bylo: **strefa zakazu pod antena**.

Uruchamiac interpreterem KiCada (ma modul `pcbnew`), w kontenerze:

    distrobox enter -n atopile -- python3 tools/board_setup.py [szer] [wys]
"""

from __future__ import annotations

import collections
import json
import math
import re
import sys
from pathlib import Path

import pcbnew

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))
import boards

BOARD = boards.select()
PCB = BOARD.pcb
FP_LIB_TABLE = BOARD.fp_lib_table
PROJECT_FILE = BOARD.pro

# ─── Obrys ───────────────────────────────────────────────────────────────
#
# Prostokat 32,50 x 59,60 mm z narozikami R2,0, lewym gornym rogiem
# w (8,41 / 3,30).
#
# Historia, bo bez niej nie widac, skad te liczby:
#   38,0 x 50,0   pierwszy szacunek, suma powierzchni, przed rozmieszczeniem,
#   25,8 x 42,2   obrys poprawiony recznie po pierwszym rozmieszczeniu,
#   51,6 x 84,4   kazdy bok razy dwa - przesada,
#   38,7 x 63,3   razy poltora,
#   32,5 x 59,6   obrys dociety recznie pod rozmieszczenie i tu wyrownany.
#
# POCZATEK zostaje blisko (8,78 / 3,30) i gorna krawedz wrocila dokladnie
# na 3,30 - nie z sentymentu, tylko dlatego, ze odziedziczony otwor lezy
# na y = 4,70 i przy krawedzi 3,504 zostawalo mu 0,20 mm laminatu zamiast
# 0,40. Krawedz plytki i polozenie tamtych otworow sa ze soba zwiazane.
BOARD_X_MM = 8.41          # lewa krawedz laminatu
BOARD_Y_MM = 2.30          # gorna krawedz laminatu
# Bylo 3.30. Plytka urosla o 1 mm W GORE - dolna krawedz i wszystko, co
# rozmieszczone, zostaje na swoim miejscu, a miejsce przybywa tam, gdzie
# bylo potrzebne: przy antenie. Powod jest podwojny - odsuniecie filtra
# MLPF od obszaru anteny (jego pady masy nie mialy jak dojsc do wylewki)
# i zrobienie miejsca na przelotke zwierajaca przy stopie zwieracza.
# Wplyw na sama antene jest pomijalny: przeciwwaga rosnie z 59,6 na
# 60,6 mm, czyli o 1,7 %, a i tak jest wieksza od cwierci fali (30,6 mm).
DEFAULT_W_MM = 32.50
DEFAULT_H_MM = 60.60

# Promien naroznika. R2,0, a nie R2,5, i to jest poprawka WYMUSZONA:
# odziedziczony otwor w lewym gornym rogu lezy wewnatrz luku, wiec to luk,
# a nie prosta krawedz, decyduje o jego obwodce. Przy R2,5 zostawalo mu
# 0,18 mm laminatu, przy R2,0 jest 0,36. Promien pochodzil z przeciagniecia
# myszka (2,516), nie z zadnego wymogu, wiec nie bylo czego bronic.
CORNER_R_MM = 2.0

# ─── Otwory montazowe: DWA zestawy ───────────────────────────────────────
#
# 1. **M3 odsuniete od rogow o 4,5 mm**, a NIE wspolsrodkowe z lukami.
#    Wczesniej byly wspolsrodkowe i to sie zemscilo: plytka rosla w prawo
#    i w dol, wiec lewy gorny rog NOWEJ plytki to ten sam rog, co STAREJ -
#    a tam juz siedzial otwor odziedziczony. Oba wypadaly 1,49 mm od siebie
#    przy wymaganych 2,60 i zlewaly sie w jedna dziure.
#    Przy 4,5 mm od obu krawedzi: do kraweedzi zostaje 2,9 mm laminatu,
#    a do najblizszego otworu odziedziczonego 1,53 mm.
#
# 2. **Zestaw odziedziczony po obrysie 25,8 x 42,2** - cztery otwory 2,0 mm
#    w tych samych miejscach BEZWZGLEDNYCH, co zawsze: (10,18 / 4,70),
#    (33,18 / 4,70), (10,18 / 44,10), (33,18 / 44,10). Wspolrzedne ponizej
#    sa wzgledem rogu obrysu, wiec przy kazdej zmianie polozenia plytki
#    trzeba je przeliczyc - i dlatego `sprawdz_otwory` pilnuje obwodki.
MOUNT_HOLE_D_MM = 3.2          # nowy zestaw, M3 z luzem
MOUNT_EDGE_MM = 3.5            # srodek otworu M3 od KAZDEJ z dwoch krawedzi
# Bylo 4.5. Zmienione na 3.5 po przesunieciu otworow w KiCadzie przy
# rozmieszczaniu - przy 4.5 lebki wchodzily w pole potrzebne elementom.
# Obwodka laminatu schodzi z 2,90 na 1,90 mm, czyli nadal szescikrotnie
# powyzej progu `MOUNT_MIN_WEB_MM`.
#
# Zestaw odziedziczony (cztery otwory 2,0 mm po obrysie 25,8 x 42,2)
# ZOSTAL USUNIETY. Istnial po to, zeby plytka wchodzila w stare uchwyty
# z poprzedniej konstrukcji; przy tym rozmieszczeniu zabieral miejsce
# potrzebne elementom, a zaden uchwyt nie jest na tyle wazny, zeby
# rozpychac plytke. Stale `MOUNT_LEGACY_*` znikly razem z nim - gdyby
# kiedys mialy wrocic, wracaja z historii gita, a nie z martwego kodu.
MOUNT_MIN_WEB_MM = 0.30        # minimum laminatu miedzy otworem a krawedzia
MOUNT_KEEPOUT_D_MM = 7.0   # lebek i podkladka M3

# ─── Strefa zakazu pod antena ────────────────────────────────────────────
#
# Jedyna rzecz, ktorej w trackerze nie bylo. Antena (`Antenna_IFA_2G4`) to
# ksztalt miedzi na F.Cu, a zeby dzialala, musi miec pod soba i wokol
# siebie PUSTO - na wszystkich czterech warstwach, czyli takze na In1
# (masa) i In2 (zasilanie). Footprint sam tego nie zalatwi: nie zna nazw
# warstw wewnetrznych plytki, na ktorej stanie.
#
# Prostokat jest liczony wzgledem SRODKA footprintu anteny, czyli wzgledem
# jej punktu zasilania (pad 1) - tak ustawiony jest w nim uklad
# wspolrzednych. Liczby ponizej to ten sam rachunek, co w pliku czesci:
#   w prawo/lewo    D1 = 0,5 z lewej, D3 = 0,3 z prawej, miedz 14,40
#   w gore          D2 = 0,3 nad paskiem L3
#   w dol           do krawedzi plaszczyzny, czyli L6 - D4 pod paskiem
# Dwie wiezyczki schodza 0,5 mm (D4) PONIZEJ tej strefy i tam juz masa byc
# ma - tam laduje przelotka zwierajaca i tam dochodzi tor 50 om.
# Sitodruk: minimum JLCPCB, bez zapasu w gore.
#
# Producent podaje jako absolutne minimum **0,8 mm wysokosci znaku i 0,15 mm
# szerokosci kreski**; zaleca 1,0 / 0,2. Bierzemy minimum swiadomie, bo
# plytka jest ciasna i kazdy napis o 20% mniejszy to mniej nachodzenia na
# sasiadow - a oznaczenia czyta sie z lupa przy lutowaniu, nie z metra.
#
# Ponizej 0,15 mm kreski JLCPCB i tak **pogrubia ja sam** do 0,15. Przy
# znaku wysokim na 0,5 mm (tyle mialo 25 oznaczen na tej plytce) daje to
# nieczytelna plame zamiast liter: proporcja szerokosci do wysokosci
# robi sie 1:3 zamiast zalecanego 1:6.
SILK_TEXT_H_MM = 0.80
SILK_TEXT_W_MM = 0.15

ANTENA_FP = "Antenna_IFA_2G4"
ANTENA_KEEPOUT_MM = (-3.05, -5.45, 12.15, -0.25)   # x1, y1, x2, y2 od srodka

# Stos JLCPCB 1,6 mm z rodziny preszpanu 7628 - `head` czterowarstwowa,
# `base` szesciowarstwowa. Obie geometrie maja miedzy warstwa zewnetrzna
# a najblizsza wewnetrzna ten sam preszpan: 0,2104 mm, Er 4,4. To jedyna
# liczba, od ktorej zaleza szerokosci klas `RF` i `USB` nizej, wiec
# dolozenie dwoch warstw nie zmienia zadnej z nich. Szczegoly przy STOSY.
TRACK_MM = 0.15          # domyslne minimum, nie szerokosc do rysowania
CLEARANCE_MM = 0.15

# ─── Przelotki ───────────────────────────────────────────────────────────
#
# Wszystkie wiertla na tej plytce maja **0,3 mm i ani dziesiatej mniej**.
# Nie jest to ostroznosc, tylko cennik: w formularzu JLCPCB opcja
# "Min via hole size/diameter" ma pierwszy prog **0.3mm/(0.4/0.45mm)**
# i jest on bezplatny; kazdy nastepny (0.25, 0.2, 0.15) podnosi cene
# zamowienia. Sprawdzone na wycenie 100 x 100 mm, 5 szt., 4 warstwy.
#
# Skoro prog dopuszcza srednice od 0,4 mm, przelotka sygnalowa schodzi
# z 0,6 na **0,5 mm**: pierscien 0,1 mm nadal jest nad preferowanym przez
# JLCPCB 0,075, a kazda przelotka oddaje 0,1 mm miejsca na trasowanie.
VIA_DIA_MM = 0.5
VIA_DRILL_MM = 0.3

# Przelotka w PADZIE - inne ograniczenie i innego rodzaju. Podpowiedz przy
# opcji "Epoxy Filled & Capped" mowi wprost:
#
#   "Vias should be at most 0.5 mm in diameter to avoid incomplete
#    filling. Vias violating this size will be left unfilled."
#
# Czyli 0,5 mm to SUFIT, nie propozycja - przelotka szersza zostanie
# niezalana, a niezalana przelotka w padzie wysysa cyne ze spoiny.
# Z wiertlem 0,3 mm daje to pierscien 0,1 mm, tyle samo co sygnalowa.
PAD_VIA_DIA_MM = 0.50
PAD_VIA_DRILL_MM = 0.30

# ─── Szycie przelotkami pod padami termicznymi ───────────────────────────
#
# Pad pod obudowa ukladu bez nozek nie jest "dobrze byloby go przylutowac" -
# dla STM32WB55 w UFQFPN-48 jest to **jedyne polaczenie ukladu z masa**,
# bo ta obudowa nie ma ani jednej nozki VSS. Bez siatki przelotek masa
# procesora wisi na wylewce F.Cu, a plaszczyzna In1 lezy 0,2104 mm nizej
# i nie ma jak do niej dojsc.
#
# Rodziny wybierane po NAZWIE FOOTPRINTU, a nie po oznaczeniu: oznaczenia
# przenumerowuja sie przy kazdej przebudowie, nazwa obudowy nie.
#
# Prog powierzchni odsiewa pady sygnalowe od termicznych i przy okazji
# chroni przed footprintem, ktory ma pad termiczny tylko z nazwy: w tym
# projekcie `TPS63020DSJR` i `BQ27441DRZT-G1A` maja na jego miejscu
# zaslepke 0,01 x 0,01 mm (wada odziedziczona po `gps_tracker-6l`).
# Takiego padu nie da sie uszyc i skrypt mowi o tym glosno, zamiast
# wiercic przelotki w punkcie.
#
# Raster 1,0 mm to kompromis, ktory podaja noty aplikacyjne obu rodzin:
# gesciej nie poprawia juz rezystancji cieplnej, a zabiera miedz z padu.
# Przelotki rozklada sie POTEM rownomiernie na dostepnej szerokosci, zeby
# siegaly mozliwie szeroko - przy odprowadzaniu ciepla liczy sie rozstaw,
# nie liczba.
#
# UWAGA PRODUKCYJNA: te przelotki leza W PADZIE, wiec musza byc zalane.
# Wiertlo 0,25 mm miesci sie w zakresie, ktory JLCPCB zalewa zywica
# (POFV), ale na czterech warstwach jest to **usluga platna** - inaczej
# niz na szesciu, gdzie jest darmowa. Bez zalania cyna ucieka przez
# przelotki w czasie rozplywu i spoina pod padem wychodzi glodna.
STITCH_RODZINY = ("QFN", "SON", "DFN")   # obudowy bez nozek
STITCH_MIN_PAD_MM2 = 2.0                 # mniej = pad sygnalowy, nie termiczny
STITCH_PITCH_MM = 1.0                    # docelowy raster
STITCH_MARGIN_MM = 0.25                  # od krawedzi przelotki do krawedzi padu

# Odstep wylewki od obcej miedzi. Domyslne 0,5 mm KiCada jest tu za duze
# i to nie kwestia gustu: wokol pinow zlaczy 2,54 mm (pad 1,70 mm) robi
# wolne pole 2,70 mm, czyli WIECEJ niz raster - kregi nachodza na siebie
# i plaszczyzna zostaje przecieta na wylot przez caly rzad. Przy 0,2 mm
# wolne pole ma 2,10 mm i miedzy pinami zostaje mostek 0,44 mm.
#
# Bylo 0,2 mm, jest 0,15 - tyle, ile wynosi `CLEARANCE_MM` calej plytki.
# Wylewka ustawiona na wiecej niz reguly projektu cofa sie bardziej, niz
# musi, i rozdrabnia sie na wyspy; przy 0,2 bylo ich na F.Cu siedemdziesiat.
#
# **Nizej zejsc nie wolno i nie ma po co.** Minimum JLCPCB to 0,127 mm,
# a KiCad i tak bierze WIEKSZY z dwoch odstepow - klasy sieci i strefy -
# wiec ponizej 0,15 ustawienie jest martwe, bo wygrywa `CLEARANCE_MM`.
ZONE_CLEARANCE_MM = 0.15

# ─── Geometria laminatu ──────────────────────────────────────────────────
#
# Stos JLCPCB 1,6 mm z rodziny preszpanu 7628. Preszpan miedzy warstwa
# zewnetrzna a najblizsza wewnetrzna ma 0,2104 mm przy Er 4,4 i jest to
# JEDYNA liczba, od ktorej zaleza szerokosci klas `RF` i `USB` wyzej -
# dlatego ten sam stos w wersji szescio- i czterowarstwowej daje te same
# szerokosci, a dolozenie dwoch warstw niczego w nich nie zmienia.
PREPREG_H_MM = 0.2104    # F.Cu -> In1 (masa) - warstwa odniesienia dla RF
PREPREG_ER = 4.4
CU_ZEWN_MM = 0.035       # 1 oz
CU_WEWN_MM = 0.0152      # 0,5 oz
RDZEN_6W_MM, RDZEN_6W_ER = 0.400, 4.36

# ─── Stos warstw ─────────────────────────────────────────────────────────
#
# Zapisywany WPROST do pliku plytki, bo bindingi Pythona KiCada 9 nie
# wystawiaja `BOARD_STACKUP` - `GetStackupDescriptor()` zwraca obiekt bez
# metod dostepowych.
#
# Bez tego bloku plik opisuje plytke DWUWARSTWOWA (F.Cu, jeden dielektryk
# 1,51 mm, B.Cu) mimo czterech warstw w tabeli. Roznica nie jest
# kosmetyczna: warstwa odniesienia dla F.Cu lezy wtedy 1,51 mm nizej
# zamiast 0,21 mm, a tor RF liczy sie na ok. 120 omow zamiast 50.
#
# Miedz wewnetrzna to 0,5 oz, nie 1 oz jak zewnetrzna.
#
# Dlaczego `base` ma szesc warstw, a `head` cztery
# ---------------------------------------------------
# Przy czterech warstwach obie wewnetrzne sa lite (masa i zasilanie), wiec
# do trasowania zostaja DWIE warstwy: F.Cu i B.Cu. Na plytce gornej to
# wystarcza. Na dolnej nie - procesor w LQFP64, gniazdo microSD, gniazdo
# USB-C i cala sekcja zasilania na 90 x 65 mm nie mieszcza sie w dwoch
# warstwach niezaleznie od rozmieszczenia; kolejne przebiegi autoroutera
# konczyly sie tak samo, z polaczeniami zostawionymi nietknietymi.
# Szesc warstw doklada In2 i In3 jako czyste warstwy sygnalowe, czyli
# podwaja miejsce na trasowanie.
STOSY = {
    # JLC06161H-7628. Suma: 2 x 0,035 + 4 x 0,0152 + 3 x 0,2104 + 2 x 0,4
    #                     = 1,5620 mm, plus 2 x 0,01 mm maski = 1,5820 mm.
    #
    # SZESC warstw, nie cztery, i decyzja jest cenowa, nie trasowa.
    # Przelotki szyjace pad pod WB55 leza W PADZIE, wiec musza byc zalane -
    # inaczej kanaly wypijaja soldera wiecej, niz w ogole bylo na padzie
    # (9 otwartych przelotek 0,3/1,6 mm to 1,02 mm3 pojemnosci wobec
    # ok. 1,09 mm3 soldera z pasty). Zalewanie na czterech warstwach jest
    # usluga platna: "Via Covering: Epoxy Filled & Capped" 15,85 EUR plus
    # wymuszone "Horizontal Electroless Copper Plating" 3,06 - razem 18,91
    # i cena zamowienia idzie z 7,13 na 26,03 EUR. Na szesciu warstwach
    # ten sam proces jest DOMYSLNY, a zamowienie kosztuje 28,52 EUR.
    # Za 2,49 EUR roznicy dostajemy dwie warstwy sygnalowe wiecej.
    # (Wycena JLCPCB, 100 x 100 mm, 5 szt., pazdziernik 2026.)
    #
    # Cena ma dwa haczyki, oba poza plikiem plytki: produkcja trwa 8-9 dni
    # zamiast 3-4 (skrocenie do 3-4 kosztuje 118,01 EUR), a szesc warstw
    # NIE OBSLUGUJE HASL - zostaje OSP albo ENIG.
    #
    # Preszpan F.Cu -> In1 zostaje 0,2104 mm, taki sam jak w stosie
    # czterowarstwowym, wiec szerokosci klas `RF` i `USB` sie NIE ZMIENIAJA:
    # tor 50 om to nadal 0,3884 mm. To jedyny powod, dla ktorego ta zmiana
    # nie pociaga za soba przeliczania toru antenowego.
    "dev": [
        ("F.Cu", "copper", CU_ZEWN_MM, None, None),
        ("dielectric 1", "prepreg", PREPREG_H_MM, "FR4", PREPREG_ER),
        ("In1.Cu", "copper", CU_WEWN_MM, None, None),
        ("dielectric 2", "core", RDZEN_6W_MM, "FR4", RDZEN_6W_ER),
        ("In2.Cu", "copper", CU_WEWN_MM, None, None),
        ("dielectric 3", "prepreg", PREPREG_H_MM, "FR4", PREPREG_ER),
        ("In3.Cu", "copper", CU_WEWN_MM, None, None),
        ("dielectric 4", "core", RDZEN_6W_MM, "FR4", RDZEN_6W_ER),
        ("In4.Cu", "copper", CU_WEWN_MM, None, None),
        ("dielectric 5", "prepreg", PREPREG_H_MM, "FR4", PREPREG_ER),
        ("B.Cu", "copper", CU_ZEWN_MM, None, None),
    ],
}

# Zasilanie siedzi na In4, a nie na In2, i to nie jest dowolne: obie warstwy
# sygnalowe maja wtedy plaszczyzne po jednej stronie - In2 mase In1, In3
# zasilanie In4 - i zadna nie sasiaduje z warstwa zewnetrzna. Sasiaduja za to
# ze soba, w odleglosci 0,2104 mm, wiec trasuje sie je prostopadle: jedna
# glownie w X, druga glownie w Y. Inaczej dlugie rownolegle odcinki zaczynaja
# sie przesluchiwac.
#
# Masa zostaje na In1 i to jest warunek, nie wybor: tor RF i para USB sa
# policzone jako mikropasek nad plaszczyzna lezaca 0,2104 mm pod F.Cu.
PLASZCZYZNY = {
    "dev": {"GND": "In1.Cu", "+3V3": "In4.Cu"},
}

# Nazwa uzytkownika nadawana warstwie niosacej dana plaszczyzne. Jest
# jedynym miejscem w pliku plytki, w ktorym widac role warstwy wewnetrznej.
NAZWY_PLASZCZYZN = {"GND": "GND", "+3V3": "PWR"}

# Wylewki na warstwach trasowania - zawsze masa, na obu plytkach. Wypelniaja
# wolne miejsce miedzy sciezkami i daja im droge powrotna tam, gdzie akurat
# nie ma pod nimi plaszczyzny.
#
# Trzeba je umiec ODTWORZYC, a nie tylko wylac: autorouter dostaje polecenie
# usuniecia wylewek z warstw, na ktorych ma pracowac, i Quilter usuwa CALE
# strefy, nie samo wypelnienie. Po powrocie plytki nie ma czego wylac - sa
# tylko dwie plaszczyzny wewnetrzne, ktore byly na liscie preserved pours.
WYLEWKI_ZEWNETRZNE = {"F.Cu": "GND", "B.Cu": "GND"}

# Zarys nowo tworzonej wylewki: laminat wciety o tyle z kazdej strony.
WYLEWKA_WCIECIE_MM = 0.5

# Pady, ktore maja byc wlane w wylewke LITO, mimo ze cala strefa stoi na
# odsprzeganiu termicznym.
#
#   oznaczenie -> nazwy padow
#
# Wylewki trzymaja `THT_THERMAL`, bo plytka jest lutowana recznie i lity
# pad masy na nozce listwy odprowadza cieplo szybciej, niz grot je
# dostarcza. Nozki ekranu gniazda USB sa wyjatkiem i to z dwoch powodow:
# maja 0,9 mm szerokosci, wiec przy odstepie 0,15 mm nie ma na nich
# miejsca na dwie szprychy (DRC zglasza `starved_thermal` - jedna
# szprycha zamiast dwoch), a ekran gniazda nie jest sygnalem do pomiaru,
# tylko mase ma trzymac krotko i szeroko. Lutuje sie je grubym grotem
# niezaleznie od wylewki.
PADY_LITE = {"USB1": ("S1",)}

# Zapas wokol miedzi wlasnej sieci przy ZACIESNIANIU wylewki lokalnej.
#
# Wylewka lokalna (SYS, VBUS pod torem zasilania) ma obejmowac swoj blok
# i nic wiecej. Zapas musi byc wiekszy od odstepu wylewki, bo inaczej
# brzeg zarysu przecinalby wlasne pady; 1,5 mm daje przy 0,15 mm odstepu
# dziesieciokrotna rezerwe i nadal trzyma wylewke przy jej ukladzie.
WYLEWKA_LOKALNA_ZAPAS_MM = 1.5

# ─── Klasy sieci ───
#
#   nazwa, sciezka, srednica przelotki, wiertlo, odstep, sieci, dodatki
#
# `dodatki` to slownik wpisywany do klasy na koncu. Jest potrzebny, bo
# klasa powstaje przez `{**default, ...}` i BEZ NIEGO po cichu dziedziczy
# po Default `diff_pair_width 0.2 / diff_pair_gap 0.25` - czyli para USB
# wyszlaby na 118 omow zamiast 90, i nic by o tym nie powiedzialo.
#
# Wzorce sa nazwami sieci, nie oznaczeniami, wiec przezywaja przebudowe.
# Sieci, ktore maja tu wpasc, musza miec nadana nazwe w `.ato` - stad
# `SW_BAT` i `SW_OUT` w `power.ato`; bez tego atopile numeruje je kolejno
# ("6", "8") i przy nastepnej przebudowie numery sa inne.
DEFAULT_TRACK_MM = 0.2   # sygnaly: dwa razy grubiej niz minimum procesu

NETCLASSES = [
    # Tor zasilania. 0,5 mm przy miedzi 35 um to ok. 1,4 A przy przyroscie
    # 10 stopni (IPC-2221, warstwa zewnetrzna) - z zapasem ponad wszystko,
    # co ta plytka pobiera. Przelotki 0,8/0,4, zeby przejscie na plaszczyzne
    # nie bylo wezszym gardlem niz sciezka.
    # Odstep 0,15 mm, czyli minimum procesu, a nie 0,2 jak w Switch.
    # Powod jest konkretny: gniazdo USB-C ma wlasny raster padow 0,84 mm
    # przy padach 0,65 mm, czyli 0,19 mm miedzy VBUS a sasiednim pinem.
    # Zadna decyzja trasowania tego nie zmieni, a 0,2 mm w klasie kazaloby
    # DRC zglaszac wnetrze gniazda jako blad. Sieci zasilania sa
    # niskoimpedancyjne i nie potrzebuja zapasu odstepu.
    ("Power", 0.5, 0.8, 0.4, 0.15,
     ["VBUS", "VBAT", "VBAT_CHG", "SYS", "PMID"],
     {"pcb_color": "rgba(220, 70, 70, 1.000)"}),
    # GND i +3V3 wyszly z klasy Power i to nie jest kosmetyka.
    #
    # One nie plyna sciezkami, tylko PLASZCZYZNAMI (In1 i In4) - sciezka
    # na tych sieciach to prawie zawsze krotki ogonek z padu do przelotki.
    # Tymczasem domyslna sciezka 0,5 mm i przelotka 0,8 mm sprawialy, ze
    # NIE DA SIE ICH FIZYCZNIE PODLACZYC do przelotek pod procesorem:
    # przy padzie przelotki 0,30 mm i rastrze 0,5 mm krawedz sasiedniej
    # przelotki lezy 0,35 mm od srodka, a sciezka 0,5 mm potrzebuje
    # 0,25 + 0,15 = 0,40 mm. Nie miesci sie o 0,05 mm.
    #
    # 0,30 mm potrzebuje 0,15 + 0,15 = 0,30 mm i wchodzi z zapasem,
    # a przy miedzi 35 um wiezie ok. 0,9 A przy przyroscie 10 stopni -
    # wielokrotnie wiecej, niz pobiera cokolwiek na tej szynie. Tam,
    # gdzie plynie realny prad, sciezke poszerza sie recznie; klasa daje
    # wartosc DOMYSLNA, nie sufit.
    #
    # Odstep zostaje 0,15 mm, bo przy rastrze 0,5 mm i padzie 0,30 mm
    # miedzy sasiednimi przelotkami zostaje 0,20 mm - 0,15 sie miesci
    # i nie ma po co schodzic nizej.
    ("Plane", 0.30, 0.5, 0.3, 0.15, ["GND", "+3V3"],
     {"pcb_color": "rgba(130, 130, 130, 1.000)"}),
    # Wezly przelaczajace przetwornicy. Szerzej nie dlatego, ze plynie tedy
    # wiekszy prad sredni, tylko dlatego, ze plynie SZYBKO: petla cewki
    # przelacza caly prad w nanosekundy, a jej indukcyjnosc zamienia to na
    # przepiecia i promieniowanie. Krotko i grubo, blisko ukladu.
    ("Switch", 0.8, 0.8, 0.4, 0.2, ["SW_BAT", "SW_OUT", "SW_CHG"],
     {"pcb_color": "rgba(255, 140, 0, 1.000)"}),
    # Przetwornica WEWNATRZ procesora: wezel przelaczajacy VLXSMPS, odcinek
    # miedzy cewkami (SMPS_MID) i wyjscie VFBSMPS.
    #
    # 0,30 mm, nie 0,8 jak w Switch: ta przetwornica wiezie dziesiatki
    # miliamperow, nie ampery. Tym, co sie tu liczy, jest DLUGOSC petli
    # VDDSMPS -> klucz -> VLXSMPS -> 10 nH -> 10 uH -> VFBSMPS, a nie
    # przekroj. Cala trojka ma zostac na F.Cu, tuz przy ukladzie - jest to
    # ten sam warunek, ktory AN5165 par. 5.3.2 stawia dla SMPS.
    ("McuSmps", 0.30, 0.5, 0.3, 0.15, ["VLXSMPS", "SMPS_MID", "VFBSMPS"],
     {"pcb_color": "rgba(230, 200, 60, 1.000)"}),
    # Tor nadawczo-odbiorczy 2,4 GHz: `RF1` (procesor -> MLPF) i `ANT`
    # (MLPF -> antena). Mikropasek 50 omow nad plaszczyzna In1 przy stosie
    # zapisanym wyzej wypada na 0,3884 mm; 0,39 mm daje dokladnie 50,0 oma.
    # Liczba przeniesiona z trackera, gdzie policzono ja dwoma niezaleznymi
    # modelami (wlasny Hammerstad i IPC-2141 z KiCadRoutingTools) - stos
    # jest ten sam, wiec i wynik ten sam.
    #
    # Odstep 0,3 mm jest wiekszy od grubosci dielektryka (0,21 mm) celowo -
    # wylana masa blizej zaczelaby robic z tego linie koplanarna i zbijac
    # impedancje ponizej zalozonej.
    #
    # Inaczej niz przy GNSS w trackerze, tutaj tor NADAJE: przy 2,4 GHz
    # dlugosc fali w laminacie to ok. 69 mm, wiec kazdy milimetr toru to
    # 1/69 fali. Dlatego MLPF ma stac przy procesorze, a antena przy MLPF -
    # i dlatego AN5165 par. 7 konczy sie uwaga, zeby ten odcinek skracac.
    # Odstep 0,15, a nie 0,30 jak pierwotnie. Przy procesorze tor RF
    # przechodzi miedzy wyprowadzeniami 19-24 w rastrze 0,5 mm i tam nie
    # ma go jak odsunac - 0,30 bylo zyczeniem, nie wymiarem. 0,15 to
    # jednoczesnie `CLEARANCE_MM` calej plytki i wartosc powyzej minimum
    # JLCPCB (0,127), wiec nie podnosi ceny ani nie lamie regul.
    ("RF", 0.39, 0.5, 0.3, 0.15, ["RF1", "ANT"], {"pcb_color": "rgba(80, 190, 120, 1.000)"}),
    # Para roznicowa USB 2.0. 0,28 mm przy odstepie 0,15 mm daje 90 omow
    # roznicowo nad plaszczyzna In1 przy stosie wyzej (wymog USB: 90 omow
    # +/-15%, czyli 76,5..103,5).
    #
    # Odstep 0,15, a nie szerszy, wymusza geometria konca trasy: pady
    # U2.44 i U2.45 leza na rastrze 0,5 mm, a para o rozstawie osi 0,43 mm
    # ucieka stamtad bez przewezenia. Przy odstepie 0,25 trzeba by zwezac
    # sciezke dokladnie w miejscu, w ktorym najmniej wolno.
    #
    # Nazwy MUSZA konczyc sie na `_P` / `_N` - KiCad rozpoznaje pare
    # roznicowa wylacznie po tym przyrostku (albo po `+` / `-`) i po
    # wspolnej bazie. Przy poprzednich `USB_DP` / `USB_DM` narzedzie do
    # trasowania par nie widzialo tu pary w ogole.
    #
    # Odcinek przy gniezdzie (`USB_CONN_*`) jest tu RAZEM z odcinkiem przy
    # procesorze, ale z zastrzezeniem: to sa sieci 3-padowe (dwa piny
    # gniazda USB-C plus dioda ESD), a rzedy A i B w Type-C sa wzgledem
    # siebie odwrocone. Zwarcie A6-B6 i A7-B7 trasuje sie wiec osobno,
    # a para biegnie dopiero stamtad do diody. Klasa daje temu odcinkowi
    # wlasciwa szerokosc i odstep; nie zalatwia za nikogo geometrii gniazda.
    ("USB", 0.28, 0.5, 0.3, 0.15,
     ["USB_D_P", "USB_D_N", "USB_CONN_P", "USB_CONN_N"],
     {"diff_pair_width": 0.28, "diff_pair_gap": 0.15,
      "pcb_color": "rgba(70, 130, 220, 1.000)"}),
]


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def clear_outline(board: pcbnew.BOARD) -> None:
    """Kasuje stary obrys. `Delete`, nie `Remove` - i to nie jest detal.

    `BOARD.Remove()` wypina ksztalt z plytki, ale go NIE KASUJE: obiekt
    zostaje bez wlasciciela (SWIG melduje wtedy "detected a memory leak of
    type 'PCB_SHAPE *', no destructor found"), a plytka potrafi trzymac do
    niego odwolanie w swoim indeksie przestrzennym. Skutkiem jest
    segmentation fault przy NASTEPNYM siegnieciu do plytki - u mnie przy
    `board.Zones()` w `set_zones`, czyli trzy funkcje dalej i bez zwiazku
    z obrysem. Objaw byl niedeterministyczny: ten sam skrypt na tym samym
    pliku raz przechodzil, raz wywalal proces.

    `BOARD.Delete()` wypina i kasuje, wiec nie zostaje nic, co moglo by
    zwisac. Przy pierwszym uruchomieniu na swiezej plytce z `ato build`
    roznicy nie widac - nie ma czego kasowac.
    """
    for drawing in list(board.GetDrawings()):
        if drawing.GetLayer() == pcbnew.Edge_Cuts:
            board.Delete(drawing)


def draw_outline(board: pcbnew.BOARD, w: float, h: float, r: float,
                 przerwy: list[tuple] | None = None,
                 ox: float = 0.0, oy: float = 0.0) -> None:
    """Prostokat ze zaokraglonymi rogami, lewy gorny rog w (`ox`, `oy`).

    Przesuniecie `ox`/`oy` wchodzi na poziomie prymitywow (`seg` i `arc`),
    wiec cala geometria nizej liczy sie tak, jakby rog byl w (0,0) -
    a to ona niesie logike przerw i lukow. Wspolrzedne w `przerwy` sa
    wiec takze wzgledem rogu, nie wzgledem poczatku ukladu KiCada.

    `przerwy` to lista `(krawedz, a, b)` - kawalkow obrysu, ktorych NIE
    rysujemy, bo wchodzi tam wciecie. `krawedz` to "N", "E", "S" albo "W",
    a `a` i `b` to wspolrzedne wzdluz tej krawedzi (X dla polnocnej
    i poludniowej, Y dla wschodniej i zachodniej), w dowolnej kolejnosci.

    Bez tych przerw obrys bylby zamkniety, a wciecia zawislyby w srodku
    laminatu jako osobne wysepki, ktorych producent nie ma jak
    zinterpretowac.

    Plytka GORNA ma dzis trzy takie przerwy i kazda z innego powodu:
    nozki listwy ekranu (krawedz wschodnia), korpus zlacza SWD (polnocna)
    i kabel ogniwa (poludniowa). Pierwsza wersja tej funkcji umiala
    jedna, i to tylko na krawedzi pionowej.
    """
    clear_outline(board)
    przerwy = list(przerwy or [])

    def seg(x1, y1, x2, y2):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(mm(x1 + ox), mm(y1 + oy)))
        s.SetEnd(pcbnew.VECTOR2I(mm(x2 + ox), mm(y2 + oy)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    def arc(cx, cy, sx, sy, ex, ey):
        a = pcbnew.PCB_SHAPE(board)
        a.SetShape(pcbnew.SHAPE_T_ARC)
        a.SetCenter(pcbnew.VECTOR2I(mm(cx + ox), mm(cy + oy)))
        a.SetStart(pcbnew.VECTOR2I(mm(sx + ox), mm(sy + oy)))
        a.SetEnd(pcbnew.VECTOR2I(mm(ex + ox), mm(ey + oy)))
        a.SetLayer(pcbnew.Edge_Cuts)
        a.SetWidth(mm(0.1))
        board.Add(a)

    def krawedz(nazwa, od, do, na_punkt):
        """Rysuje krawedz od `od` do `do`, omijajac swoje przerwy.

        `od` i `do` sa wspolrzednymi wzdluz krawedzi i moga isc malejaco
        (tak biegnie poludniowa i zachodnia) - kierunek jest zachowany,
        bo luki narozne licza na to, ze odcinki biegna zgodnie z ruchem
        wskazowek zegara.
        """
        moje = sorted((min(a, b), max(a, b))
                      for kr, a, b in przerwy if kr == nazwa)
        for a, b in moje:
            if not (min(od, do) - 1e-6 <= a and b <= max(od, do) + 1e-6):
                raise SystemExit(
                    f"przerwa {nazwa} {a}..{b} nie miesci sie w krawedzi "
                    f"{min(od, do)}..{max(od, do)} - popraw wciecie")
        granice = [od]
        for a, b in (moje if do > od else reversed(moje)):
            granice += [a, b] if do > od else [b, a]
        granice.append(do)
        for i in range(0, len(granice), 2):
            p1, p2 = granice[i], granice[i + 1]
            if abs(p2 - p1) < 1e-6:
                continue
            seg(*na_punkt(p1), *na_punkt(p2))

    krawedz("N", r, w - r, lambda x: (x, 0))
    krawedz("E", r, h - r, lambda y: (w, y))
    krawedz("S", w - r, r, lambda x: (x, h))
    krawedz("W", h - r, r, lambda y: (0, y))
    # Luki rysowane od poczatku do konca zgodnie z ruchem wskazowek zegara,
    # czyli w tym samym kierunku, w ktorym biegna odcinki.
    arc(w - r, r, w - r, 0, w, r)
    arc(w - r, h - r, w, h - r, w - r, h)
    arc(r, h - r, r, h, 0, h - r)
    arc(r, r, 0, r, r, 0)

def obwodka_mm(cx: float, cy: float, d: float,
               w: float, h: float, r: float) -> float:
    """Ile laminatu zostaje miedzy otworem a krawedzia plytki.

    Liczy TAKZE naroznik zaokraglony, i to jest cala wartosc tej funkcji.
    Poprzednia wersja sprawdzala sam prostokat (`margines <= cx <= w -
    margines`) i przez to przepuscila otwor, ktory miescil sie w prostokacie,
    ale wychodzil 0,47 mm poza luk naroznika. Bledu nie widac ani w DRC
    (otwor jest na Edge.Cuts, nie na miedzi), ani na renderze - zobaczylby
    go dopiero producent albo nikt.

    W narozniku krawedzia plytki jest LUK, wiec obwodka liczy sie od srodka
    luku, nie od prostych krawedzi: punkt lezacy w kwadracie naroznika jest
    w laminacie tylko wtedy, gdy jest blizej niz `r` od srodka luku.
    """
    rr = d / 2
    proste = min(cx, cy, w - cx, h - cy) - rr
    for sx, sy in ((r, r), (w - r, r), (w - r, h - r), (r, h - r)):
        # kwadrat naroznika: tylko w nim luk jest krawedzia
        if min(sx, w - sx) >= abs(cx - sx) and min(sy, h - sy) >= abs(cy - sy):
            w_kwadracie = (abs(cx - sx) <= r and abs(cy - sy) <= r
                           and (cx - sx) * (2 * sx - w) >= 0
                           and (cy - sy) * (2 * sy - h) >= 0)
            if w_kwadracie:
                odl = ((cx - sx) ** 2 + (cy - sy) ** 2) ** 0.5
                return min(proste, r - odl - rr)
    return proste


def draw_mounting_holes(board: pcbnew.BOARD, w: float, h: float,
                        r: float, ox: float = 0.0, oy: float = 0.0) -> list:
    """Otwory montazowe M3 jako okregi na Edge.Cuts.

    Okrag na warstwie krawedzi to dla producenta polecenie frezowania,
    czyli otwor NIEPLATEROWANY. Tak ma byc: sruba w otworze platerowanym
    zwieralaby to, co akurat obok niej lezy na plaszczyznach.

    Zestaw jest JEDEN - cztery otwory M3 odsuniete od rogow o
    `MOUNT_EDGE_MM`, a nie wspolsrodkowe z lukami naroznikow. Drugi,
    odziedziczony po obrysie 25,8 x 42,2, zostal usuniety przy
    rozmieszczaniu elementow.

    Kazdy otwor jest sprawdzany na dwie rzeczy: obwodke do krawedzi (razem
    z lukiem naroznika) i odleglosc do kazdego innego otworu. Oba bledy
    wygladaja na renderze niewinnie - pierwszy jak otwor przy krawedzi,
    drugi jak dwa otwory obok siebie - a oba oznaczaja plytke do wyrzucenia.
    """
    def okrag(cx, cy, d):
        c = pcbnew.PCB_SHAPE(board)
        c.SetShape(pcbnew.SHAPE_T_CIRCLE)
        c.SetCenter(pcbnew.VECTOR2I(mm(cx + ox), mm(cy + oy)))
        c.SetEnd(pcbnew.VECTOR2I(mm(cx + ox + d / 2), mm(cy + oy)))
        c.SetLayer(pcbnew.Edge_Cuts)
        c.SetWidth(mm(0.1))
        board.Add(c)

    e = MOUNT_EDGE_MM
    zestawy = [
        ("M3, %.1f mm od krawedzi" % e, MOUNT_HOLE_D_MM,
         [(e, e), (w - e, e), (w - e, h - e), (e, h - e)]),
    ]

    wszystkie = [(cx, cy, d) for _, d, lista in zestawy for cx, cy in lista]
    for cx, cy, d in wszystkie:
        web = obwodka_mm(cx, cy, d, w, h, r)
        if web < MOUNT_MIN_WEB_MM:
            raise SystemExit(
                f"otwor {d} mm w ({cx}, {cy}) zostawia {web:.3f} mm laminatu "
                f"do krawedzi - minimum to {MOUNT_MIN_WEB_MM}")
    for i, (ax, ay, ad) in enumerate(wszystkie):
        for bx, by, bd in wszystkie[i + 1:]:
            odl = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
            luz = odl - ad / 2 - bd / 2
            if luz < MOUNT_MIN_WEB_MM:
                raise SystemExit(
                    f"otwory ({ax}, {ay}) i ({bx}, {by}) dzieli {luz:.3f} mm "
                    f"laminatu - minimum to {MOUNT_MIN_WEB_MM}")

    wynik = []
    for opis, d, lista in zestawy:
        for cx, cy in lista:
            okrag(cx, cy, d)
        najciensza = min(obwodka_mm(cx, cy, d, w, h, r) for cx, cy in lista)
        wynik.append((opis, d, lista, najciensza))
    return wynik


def sprawdz_przelotki(board: pcbnew.BOARD) -> int:
    """Pilnuje, zeby zadna przelotka nie miala wiertla ponizej minimum.

    To nie jest kontrola wytrzymalosciowa, tylko CENOWA. W formularzu
    JLCPCB "Min via hole size/diameter" ma progi 0.3 / 0.25 / 0.2 / 0.15 mm
    i tylko pierwszy jest bezplatny - jedna zapomniana przelotka 0,25 mm
    przesuwa cale zamowienie na drozszy prog, a w KiCadzie wyglada
    dokladnie tak samo jak reszta.

    Nie poprawiamy jej po cichu: przelotki stawia czlowiek przy trasowaniu
    i to on ma zdecydowac, czy zmienic ja, czy zaplacic. Skrypt ma tylko
    nie pozwolic, zeby dowiedzial sie o tym z wyceny.
    """
    zle = []
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_VIA_T:
            continue
        wiertlo = pcbnew.ToMM(t.GetDrill())
        if wiertlo < min(VIA_DRILL_MM, PAD_VIA_DRILL_MM) - 1e-6:
            p = t.GetPosition()
            zle.append((wiertlo, pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
                        t.GetNetname()))
    if zle:
        print(f"UWAGA: {len(zle)} przelotek z wiertlem ponizej "
              f"{min(VIA_DRILL_MM, PAD_VIA_DRILL_MM)} mm - podnosza prog "
              f"cenowy u JLCPCB:")
        for w, x, y, siec in zle:
            print(f"   {w} mm w ({x:.3f}, {y:.3f}) na sieci {siec}")
    return len(zle)


def stitch_thermal_pads(board: pcbnew.BOARD) -> list:
    """Siatka przelotek pod kazdym padem termicznym lezacym na masie.

    Idempotentne: najpierw kasuje przelotki o rozmiarze `PAD_VIA_*` lezace
    wewnatrz tych padow, potem rysuje je od nowa. Dzieki temu siatka idzie
    za rozmieszczeniem - przesuniecie albo obrocenie ukladu przenosi ja
    razem z nim, a `ato build` jej nie gubi, bo nie jest czescia netlisty.

    Zwraca liste `(oznaczenie, nx, ny, raster_x, raster_y)` do wypisania.
    """
    gnd = board.FindNet("GND")
    if gnd is None:
        raise SystemExit("na plytce nie ma sieci GND - nie ma czego szyc")

    kandydaci, odrzucone = [], []
    for fp in board.GetFootprints():
        nazwa = str(fp.GetFPIDAsString()).upper()
        if not any(r in nazwa for r in STITCH_RODZINY):
            continue
        for pad in fp.Pads():
            if pad.GetNetname() != "GND":
                continue
            # Wymiar bierzemy z OBRYSU, nie z `GetSizeX/Y`. Pad typu
            # `custom` trzyma w tych polach rozmiar KOTWICY, a prawdziwy
            # ksztalt siedzi w `primitives` - i tak sa zrobione pady
            # termiczne TPS63020 i BQ27441, ktore przyszly z EasyEDA.
            # Przez caly czas raportowalo je tu jako "zaslepki 0,01 mm"
            # i zostawialo bez szycia, choc maja 6,95 i 8,09 mm2 miedzi
            # z pasta i siecia GND. Obrys widzi jedno i drugie.
            bb = pad.GetBoundingBox()
            w = pcbnew.ToMM(bb.GetWidth())
            h = pcbnew.ToMM(bb.GetHeight())
            if w * h >= STITCH_MIN_PAD_MM2:
                kandydaci.append((fp.GetReference(), pad, w, h))
            elif w * h < 0.1:
                odrzucone.append((fp.GetReference(), pad.GetPadName(), w, h))

    # ─── Kasowanie poprzedniej siatki ───
    # Po SAMYM POLOZENIU: kasujemy kazda przelotke lezaca wewnatrz padu
    # termicznego, niezaleznie od jej rozmiaru. Przelotka w KiCadzie nie ma
    # pola, w ktorym dalo by sie zapisac "moja", a wnetrze padu termicznego
    # nalezy do tej funkcji i nic innego nie ma prawa tam stac.
    #
    # Pierwsza wersja dopasowywala po wiertle rownym `PAD_VIA_DRILL_MM`
    # i to byla pulapka: zmiana tej stalej z 0,25 na 0,3 sprawila, ze stara
    # siatka przestala pasowac do wzorca, nie zostala skasowana i plytka
    # dostala 29 przelotek PODWOJNIE, jedna w drugiej. Kryterium nie moze
    # zalezec od wartosci, ktora sie wlasnie zmienia.
    stare = []
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_VIA_T:
            continue
        for _, pad, _, _ in kandydaci:
            if pad.HitTest(t.GetPosition()):
                stare.append(t)
                break
    for t in stare:
        board.Delete(t)

    # ─── Siatka ───
    # Przelotki rozklada sie po RZECZYWISTEJ miedzi padu, nie po jego
    # prostokatnym obrysie. Pady termiczne z EasyEDA sa wielokatami:
    #
    #   TPS63020 - prostokat z grzebieniem wyciec na nozki,
    #   BQ27441  - ksztalt teowy: srodkowa belka 2,0 x 1,95 mm i dwa
    #              pionowe pasy szerokie na 0,22 mm, w ktore zadna
    #              przelotka 0,5 mm nie wejdzie.
    #
    # Siatka na obrysie stawiala przelotki w wycieciach i w waskich
    # pasach - czyli na golym laminacie miedzy nozkami przetwornicy.
    # Zamiast tego: gesty raster kandydatow, kazdy sprawdzony na
    # przynaleznosc do miedzi, i zachlanny wybor z zachowaniem odstepu.
    KROK_PROBKI_MM = 0.1
    wynik = []
    for ref, pad, w, h in kandydaci:
        srodek = pad.GetPosition()
        r = mm(PAD_VIA_DIA_MM / 2)

        def w_miedzi(x, y):
            """Czy CALA przelotka miesci sie w miedzi padu.

            Sprawdzamy srodek i cztery punkty na obwodzie. Sam srodek nie
            wystarcza: przelotka przy krawedzi wielokata wystawalaby poza
            miedz, a tego nie widac inaczej niz w DRC przy gotowej plytce.
            """
            return all(
                pad.HitTest(pcbnew.VECTOR2I(int(x + dx), int(y + dy)), 0)
                for dx, dy in ((0, 0), (r, 0), (-r, 0), (0, r), (0, -r)))

        bb = pad.GetBoundingBox()
        nx = max(1, int(pcbnew.ToMM(bb.GetWidth()) / KROK_PROBKI_MM))
        ny = max(1, int(pcbnew.ToMM(bb.GetHeight()) / KROK_PROBKI_MM))
        kandydaci_xy = []
        for i in range(nx + 1):
            for j in range(ny + 1):
                x = bb.GetLeft() + int(i * bb.GetWidth() / nx)
                y = bb.GetTop() + int(j * bb.GetHeight() / ny)
                if w_miedzi(x, y):
                    d = (x - srodek.x) ** 2 + (y - srodek.y) ** 2
                    kandydaci_xy.append((d, x, y))
        # Od srodka na zewnatrz: przelotka w srodku padu odprowadza cieplo
        # lepiej niz przy krawedzi, a przy ciasnym ksztalcie to ona ma
        # pierwszenstwo.
        kandydaci_xy.sort()

        # Drugi warunek: przelotka jest PRZELOTOWA, wiec przebija takze
        # In2, In3 i B.Cu - a tam moga lezec cudze sciezki. Pierwsze
        # uruchomienie tego kodu postawilo pod U3 i U5 komplet przelotek
        # w miedzi padu i zrobilo 18 zwarc z SD_CLK, SD_MISO, SD_MOSI,
        # PB6, CHG_CE, CHG_PG i GAUGE_INT na warstwach wewnetrznych.
        # Stawiamy wiec tylko tam, gdzie nic obcego nie przeszkadza.
        promien = mm(PAD_VIA_DIA_MM / 2) + mm(CLEARANCE_MM)
        obce = []
        for t in board.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T:
                continue
            if t.GetNetname() == "GND":
                continue
            obce.append((t.GetStart(), t.GetEnd(),
                         t.GetWidth() // 2 + promien))

        def wolne(x, y):
            """Czy w tym miejscu przelotka nie wejdzie w cudza miedz."""
            for a_, b_, luz in obce:
                dx, dy = b_.x - a_.x, b_.y - a_.y
                dl = dx * dx + dy * dy
                if dl == 0:
                    t = 0.0
                else:
                    t = ((x - a_.x) * dx + (y - a_.y) * dy) / dl
                    t = max(0.0, min(1.0, t))
                px, py = a_.x + t * dx, a_.y + t * dy
                if (x - px) ** 2 + (y - py) ** 2 < luz * luz:
                    return False
            return True

        minimum = mm(STITCH_PITCH_MM) ** 2
        wybrane, kolizje = [], 0
        for _, x, y in kandydaci_xy:
            if any((x - px) ** 2 + (y - py) ** 2 < minimum for px, py in wybrane):
                continue
            if not wolne(x, y):
                kolizje += 1
                continue
            wybrane.append((x, y))

        if not wybrane:
            print(f"  UWAGA: {ref} - pod padem termicznym nie ma miejsca na "
                  f"ani jedna przelotke; cudza miedz na warstwach "
                  f"wewnetrznych blokuje caly pad")

        for x, y in wybrane:
            v = pcbnew.PCB_VIA(board)
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
            # `SetWidth` bez warstwy jest w KiCadzie 9 przestarzale
            # (przelotka moze miec rozna srednice na kazdej warstwie)
            # i sypie ostrzezeniem przy kazdym wywolaniu.
            v.SetWidth(pcbnew.F_Cu, mm(PAD_VIA_DIA_MM))
            v.SetDrill(mm(PAD_VIA_DRILL_MM))
            v.SetNet(gnd)
            board.Add(v)
        wynik.append((ref, len(wybrane), w, h, kolizje))

    for ref, nazwa_padu, w, h in odrzucone:
        print(f"  UWAGA: {ref} pad {nazwa_padu} ma obrys {w:.2f} x {h:.2f} mm - "
              f"za maly na pad termiczny; NIE SZYTY")
    return wynik, len(stare)


def ustaw_sitodruk(board: pcbnew.BOARD) -> tuple[int, int]:
    """Sprowadza wszystkie oznaczenia na sitodruku do jednego rozmiaru.

    Napisy przychodza z footprintow, a te pochodza z roznych zrodel -
    EasyEDA, biblioteka KiCada, pliki pisane tutaj - i kazde ma wlasne
    zwyczaje. Na tej plytce dawalo to cztery rozmiary naraz, od
    0,50 x 0,062 mm (ponizej tego, co JLCPCB umie wydrukowac) po
    1,27 x 0,254.

    Musi to robic skrypt, a nie reka: `ato build` odtwarza footprinty
    z bibliotek i kazda reczna zmiana rozmiaru znika przy przebudowie.

    Pogrubienia nie wlaczamy - minimum to minimum.
    """
    silk = (pcbnew.F_SilkS, pcbnew.B_SilkS)
    h, w = mm(SILK_TEXT_H_MM), mm(SILK_TEXT_W_MM)
    zmienione = 0
    wszystkie = 0
    for fp in board.GetFootprints():
        for t in (fp.Reference(), fp.Value()):
            if t.GetLayer() not in silk:
                continue
            wszystkie += 1
            if (t.GetTextHeight() == h and t.GetTextWidth() == h
                    and t.GetTextThickness() == w and not t.IsBold()):
                continue
            t.SetTextHeight(h)
            t.SetTextWidth(h)
            t.SetTextThickness(w)
            t.SetBold(False)
            zmienione += 1

    # Napisy wlasne, dopisane w KiCadzie - na tej plytce mapa pinow listew
    # (`+3V3`, `GND`, `SCL`, `PA2`, `RST`, `BOOT0`, `LD1`...). Tych NIE
    # zmniejszamy: ktos dobral im wysokosc 1,0 mm swiadomie, a to one sa
    # czytane przy wpinaniu przewodu, nie oznaczenia elementow.
    #
    # Poprawiamy im wylacznie grubosc kreski, bo 0,100 mm jest ponizej
    # tego, co JLCPCB drukuje - producent pogrubilby ja i tak do 0,15,
    # tyle ze bez pytania i bez zachowania proporcji znaku.
    for d in board.GetDrawings():
        if d.GetClass() not in ("PCB_TEXT", "PCB_TEXTBOX"):
            continue
        if d.GetLayer() not in silk:
            continue
        wszystkie += 1
        if d.GetTextThickness() >= w and not d.IsBold():
            continue
        d.SetTextThickness(w)
        d.SetBold(False)
        zmienione += 1

    return zmienione, wszystkie


def przelotka_zwierajaca(board: pcbnew.BOARD) -> tuple | None:
    """Stawia przelotke zwierajaca radiator anteny do plaszczyzny masy.

    W antenie typu odwrocone F radiator jest zwarty do masy przez zwieracz
    i **to jest cala zasada jej dzialania** - bez tego zwarcia zostaje
    kawalek miedzi o nieokreslonej impedancji. Komentarz przy
    `ANTENA_KEEPOUT_MM` zaklada te przelotke od poczatku ("tam laduje
    przelotka zwierajaca"), ale przez dlugi czas jej nie bylo: stopa
    zwieracza z AN043 ma 0,90 x 0,50 mm, a przelotka z odstepem potrzebuje
    0,80 mm w obu osiach. Dopiero pad ladowania 1,10 x 1,10 mm dolozony do
    footprintu dal jej miejsce.

    Pad wybierany jest geometrycznie, nie po wspolrzednych:

      * musi pomiescic CALA przelotke z odstepem,
      * musi lezec w calosci PONIZEJ strefy zakazu - czyli juz w obszarze
        masy. Pionowy zwieracz tez przeszedlby pierwszy warunek (0,90 mm
        szerokosci), ale siedzi w strefie zakazu i przelotka w nim byloby
        masa dokladnie tam, gdzie masy byc nie moze.

    Zwraca `(x, y)` postawionej przelotki albo `None`.
    """
    ant = next((f for f in board.GetFootprints()
                if ANTENA_FP in str(f.GetFPIDAsString())), None)
    gnd = board.FindNet("GND")
    if ant is None or gnd is None:
        return None

    zasilanie = next((p for p in ant.Pads() if p.GetNetname() == "ANT"), None)
    if zasilanie is None:
        return None
    dol_strefy = zasilanie.GetPosition().y + mm(ANTENA_KEEPOUT_MM[3])

    potrzeba = mm(PAD_VIA_DIA_MM) + 2 * mm(CLEARANCE_MM)
    promien = mm(PAD_VIA_DIA_MM / 2)
    kandydat = None
    for pad in ant.Pads():
        if pad.GetNetname() != "GND":
            continue
        bb = pad.GetBoundingBox()
        if bb.GetWidth() < potrzeba or bb.GetHeight() < potrzeba:
            continue
        if bb.GetTop() < dol_strefy:          # siega w strefe zakazu
            continue
        kandydat = pad
        break
    if kandydat is None:
        print("  UWAGA: antena nie ma padu, w ktorym zmiescilaby sie "
              "przelotka zwierajaca PONIZEJ strefy zakazu")
        return None

    srodek = kandydat.GetPosition()
    # Ta sama kontrola, co przy szyciu padow termicznych: przelotka ma
    # miescic sie cala w miedzi i nie wchodzic w nic obcego.
    punkty = ((0, 0), (promien, 0), (-promien, 0), (0, promien), (0, -promien))
    if not all(kandydat.HitTest(
            pcbnew.VECTOR2I(int(srodek.x + dx), int(srodek.y + dy)), 0)
            for dx, dy in punkty):
        print("  UWAGA: srodek padu zwieracza nie miesci calej przelotki")
        return None

    for t in list(board.GetTracks()):
        if t.Type() != pcbnew.PCB_VIA_T:
            continue
        d = (t.GetPosition().x - srodek.x) ** 2 + (t.GetPosition().y - srodek.y) ** 2
        if d < (promien * 2) ** 2:
            return (pcbnew.ToMM(srodek.x), pcbnew.ToMM(srodek.y))   # juz stoi

    v = pcbnew.PCB_VIA(board)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetPosition(srodek)
    v.SetWidth(pcbnew.F_Cu, mm(PAD_VIA_DIA_MM))
    v.SetDrill(mm(PAD_VIA_DRILL_MM))
    v.SetNet(gnd)
    board.Add(v)
    return (pcbnew.ToMM(srodek.x), pcbnew.ToMM(srodek.y))


def napraw_siec_anteny(board: pcbnew.BOARD) -> int:
    """Oddaje masie te pady anteny, ktorym `ato build` jej nie przypisal.

    Footprint anteny jest net-tie: trzynascie prostokatow na GND i jeden
    pad zasilania na ANT, wszystkie o numerze "2" poza zasilaniem. Przy
    dokladaniu pada ladowania pod zwieraczem okazalo sie, ze po
    przebudowie jeden z nich zostaje BEZ SIECI - i wtedy zwiera sie
    z kazda sasiednia miedzia, bo DRC traktuje brak sieci jako osobna
    siec. Na plytce wygladalo to na trzy zwarcia z +3V3.

    Tu nie ma co zgadywac: w tym footprincie wszystko poza padem ANT jest
    masa z definicji - radiator odwroconej F jest zwarty do masy przez
    zwieracz, stad w ogole net tie. Pad bez sieci dostaje wiec GND.
    """
    ant = next((f for f in board.GetFootprints()
                if ANTENA_FP in str(f.GetFPIDAsString())), None)
    if ant is None:
        return 0
    gnd = board.FindNet("GND")
    if gnd is None:
        return 0
    n = 0
    for pad in ant.Pads():
        if not pad.GetNetname():
            pad.SetNet(gnd)
            n += 1
    return n


def draw_antenna_keepout(board: pcbnew.BOARD) -> tuple | None:
    """Strefa zakazu wylewki pod antena - na WSZYSTKICH warstwach miedzi.

    Antena typu F dziala dzieki temu, ze obok niej jest krawedz
    plaszczyzny masy, a pod nia i wokol niej nie ma nic. Wylana masa na
    F.Cu albo plaszczyzna In1 siegajaca pod radiator rozstraja ja tak, ze
    nie da sie tego poprawic strojeniem - jest to zmiana otoczenia, a nie
    dopasowania.

    Strefa jest `rule area` z zakazem WYPELNIENIA, a nie zakazem wszystkiego:
    pady samej anteny leza w jej srodku i maja tam zostac. Zabronione sa za
    to sciezki i przelotki - zeby nikt nie poprowadzil tedy sygnalu przy
    recznym trasowaniu.

    Prostokat idzie za footprintem anteny: jego polozenie i obrot sa brane
    z plytki, wiec przesuniecie albo obrocenie anteny przesuwa strefe razem
    z nia. Gdyby bylo przepisane na sztywno, rozjechaloby sie po cichu przy
    pierwszej zmianie rozmieszczenia - a tego nie widac na renderze.
    """
    ant = [f for f in board.GetFootprints()
           if ANTENA_FP in str(f.GetFPIDAsString())]
    if not ant:
        return None
    if len(ant) > 1:
        raise SystemExit(f"na plytce jest {len(ant)} anten - strefa zakazu "
                         f"nie wie, ktorej dotyczy")
    fp = ant[0]

    # Stare strefy anteny z poprzedniego przebiegu - skrypt ma byc
    # idempotentny, wiec kasujemy przed narysowaniem.
    for z in list(board.Zones()):
        if z.GetZoneName() == "antena":
            board.Remove(z)

    x1, y1, x2, y2 = ANTENA_KEEPOUT_MM
    pos = fp.GetPosition()
    kat = fp.GetOrientation()
    zone = pcbnew.ZONE(board)
    zone.SetZoneName("antena")
    zone.SetIsRuleArea(True)
    zone.SetDoNotAllowCopperPour(True)
    zone.SetDoNotAllowTracks(True)
    zone.SetDoNotAllowVias(True)
    zone.SetDoNotAllowPads(False)
    zone.SetDoNotAllowFootprints(False)
    warstwy = pcbnew.LSET()
    for _, numer in warstwy_miedzi():
        warstwy.addLayer(numer)
    zone.SetLayerSet(warstwy)
    # Obrot liczony tutaj, a nie przez `pcbnew.RotatePoint` - tej funkcji
    # bindingi KiCada 9 nie wystawiaja. KiCad obraca footprinty PRZECIWNIE
    # do wskazowek przy osi Y skierowanej w dol, stad znak przy sinusie.
    kat_rad = fp.GetOrientation().AsRadians()
    cos_a, sin_a = math.cos(kat_rad), math.sin(kat_rad)
    kontur = zone.Outline()
    kontur.NewOutline()
    for px, py in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
        ux, uy = mm(px), mm(py)
        rx = int(round(ux * cos_a + uy * sin_a))
        ry = int(round(-ux * sin_a + uy * cos_a))
        kontur.Append(rx + pos.x, ry + pos.y)
    board.Add(zone)
    return (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), x2 - x1, y2 - y1)


def sprawdz_kontur(pcb: Path) -> int:
    """Czy Edge.Cuts w ZAPISANYM pliku tworzy jeden zamkniety kontur.

    Kazdy wierzcholek ma nalezec do DOKLADNIE dwoch ksztaltow. Wolny
    koniec znaczy dziure w obrysie, a plytki z dziurawym obrysem nie da
    sie wyprodukowac - producent albo odesle plik, albo zgadnie.

    Robi sie to sprawdzenie odkad obrys ma wciecie: dopoki byl prostym
    prostokatem, nie bylo czego zepsuc. Teraz krawedz jest przerwana
    w dwoch punktach i musi sie w nich spotkac ze scianami wciecia -
    pomylki o 0,01 mm nie widac okiem w KiCadzie.

    Czyta PLIK, a nie obiekt `BOARD`, i to nie jest kaprys. Po pierwsze
    sprawdza sie w ten sposob to, co naprawde pojedzie do producenta. Po
    drugie bindingi KiCada 9 nie daja tu innego wyjscia: `GetDrawings()`
    na plytce zmienionej w pamieci przewraca sie na "SwigPyObject is not
    iterable", a `LoadBoard()` wolane po raz drugi w tym samym procesie
    zwraca obiekt bez metod.

    Okregi (`gr_circle`, czyli otwory montazowe) sa wlasnymi konturami
    i nie maja koncow, wiec sie ich nie liczy.
    """
    tekst = pcb.read_text(encoding="utf-8")
    konce: dict[tuple[float, float], int] = {}
    ksztaltow = 0
    blok: list[str] | None = None
    glebokosc = 0
    for linia in tekst.splitlines():
        if blok is None:
            if linia.strip() in ("(gr_line", "(gr_arc"):
                blok, glebokosc = [linia], 1
            continue
        blok.append(linia)
        # Licznik nawiasow, a nie "pierwszy wiersz z samym )". Ksztalt ma
        # w srodku zagniezdzony blok `(stroke ...)`, ktory tez konczy sie
        # nawiasem w osobnym wierszu - naiwny warunek urywal blok przed
        # `(layer "Edge.Cuts")` i nie znajdowal ani jednego ksztaltu.
        glebokosc += linia.count("(") - linia.count(")")
        if glebokosc > 0:
            continue
        tresc = "\n".join(blok)
        blok = None
        if '(layer "Edge.Cuts")' not in tresc:
            continue
        ksztaltow += 1
        for pole in ("start", "end"):
            m = re.search(rf"\({pole} (-?[\d.]+) (-?[\d.]+)\)", tresc)
            if not m:
                raise SystemExit(f"ksztalt Edge.Cuts bez pola {pole}")
            klucz = (round(float(m.group(1)), 3), round(float(m.group(2)), 3))
            konce[klucz] = konce.get(klucz, 0) + 1

    if ksztaltow < 4:
        # Prostokat to co najmniej cztery ksztalty. Mniej znaczy, ze
        # parser nic nie znalazl - a cicho przechodzace sprawdzenie jest
        # gorsze niz jego brak.
        raise SystemExit(
            f"sprawdzenie konturu znalazlo tylko {ksztaltow} ksztaltow "
            f"Edge.Cuts w {pcb.name} - to blad parsera, nie plytki")

    wolne = sorted(k for k, ile in konce.items() if ile != 2)
    if wolne:
        raise SystemExit(
            "obrys nie jest zamkniety - wiszace konce w " +
            ", ".join(f"({x}, {y})" for x, y in wolne))
    return ksztaltow


def prune_fp_lib_table() -> None:
    """Wyrzuca z fp-lib-table wpisy wskazujace na nieistniejace katalogi.

    atopile dopisuje do tej tabeli kazda czesc, ktora kiedykolwiek byla
    w projekcie, i nigdy nic z niej nie usuwa. Po kilku wymianach
    komponentow polowa wpisow wskazuje w prozne miejsce, a KiCad przy
    kazdym otwarciu plytki zglasza je jako brakujace biblioteki.

    Same footprinty siedza w pliku .kicad_pcb, wiec tabela jest potrzebna
    dopiero przy "Update Footprints from Library" i w przegladarce
    footprintow - ale to wlasnie tam pusty wpis boli.
    """
    if not FP_LIB_TABLE.is_file():
        return
    text = FP_LIB_TABLE.read_text(encoding="utf8")
    kept, dropped = [], 0
    for m in re.finditer(r"\t\(lib\n(?:.*?\n)*?\t\)\n", text):
        name = re.search(r'\(name "([^"]+)"', m.group(0))
        if name and (PROJECT / "parts" / name.group(1)).is_dir():
            kept.append(m.group(0))
        else:
            dropped += 1
    if not dropped:
        return
    head = text[: text.index("\t(lib\n")]
    FP_LIB_TABLE.write_text(head + "".join(kept) + ")\n", encoding="utf8")
    print(f"fp-lib-table: usunieto {dropped} martwych wpisow, zostalo {len(kept)}")


def warstwy_miedzi() -> list[tuple[str, int]]:
    """Warstwy miedzi tej plytki, w kolejnosci stosu: (nazwa, numer)."""
    numery = {"F.Cu": pcbnew.F_Cu, "In1.Cu": pcbnew.In1_Cu,
              "In2.Cu": pcbnew.In2_Cu, "In3.Cu": pcbnew.In3_Cu,
              "In4.Cu": pcbnew.In4_Cu, "B.Cu": pcbnew.B_Cu}
    return [(n, numery[n]) for n, kind, *_ in STOSY[BOARD.name]
            if kind == "copper"]


def set_stackup(board: pcbnew.BOARD) -> None:
    miedz = warstwy_miedzi()
    enabled = board.GetEnabledLayers()
    for _, numer in miedz:
        enabled.AddLayer(numer)
    board.SetEnabledLayers(enabled)
    board.SetCopperLayerCount(len(miedz))

    # In1 to lita masa pod warstwa sygnalowa - to ona daje odbiornikowi GNSS
    # i przetwornicy sensowna droge powrotna.
    #
    # Warstwa, ktora przestala niesc plaszczyzne, musi TEZ stracic nazwe.
    # Bez tego In2 na `base` dalej nazywaloby sie "PWR", a lezy na niej
    # teraz trasowanie - i kazdy, kto otworzy plytke, przeczyta warstwe
    # sygnalowa jako zasilanie.
    role = {w: NAZWY_PLASZCZYZN[s] for s, w in PLASZCZYZNY[BOARD.name].items()}
    for nazwa, numer in miedz:
        if nazwa in ("F.Cu", "B.Cu"):
            continue
        board.SetLayerName(numer, role.get(nazwa, nazwa))


def zarys_wylewki(board: pcbnew.BOARD) -> pcbnew.VECTOR_VECTOR2I:
    """Prostokat laminatu wciety o WYLEWKA_WCIECIE_MM z kazdej strony.

    Czyta obrys Z PLYTKI, wiec wymaga, zeby obrys juz istnial. Brak tej
    kontroli kosztowal dwie wylewki: `set_zones()` szlo w `main()` PRZED
    `draw_outline()`, `GetBoardEdgesBoundingBox()` oddawalo pudelko zerowe,
    a strefa powstawala jako kwadracik 1 x 1 mm wokol punktu (0,0) - z
    poprawna siecia i warstwa, wiec na pierwszy rzut oka w porzadku.
    Wylewalo sie z niej zero miedzi i nikt tego nie zauwazyl, bo liczba
    stref sie zgadzala.
    """
    bb = board.GetBoardEdgesBoundingBox()
    d = mm(WYLEWKA_WCIECIE_MM)
    if bb.GetWidth() <= 2 * d or bb.GetHeight() <= 2 * d:
        raise SystemExit(
            "wylewka nie ma sie na czym oprzec: obrys plytki ma "
            f"{pcbnew.ToMM(bb.GetWidth()):.1f} x {pcbnew.ToMM(bb.GetHeight()):.1f} mm. "
            "`set_zones()` musi isc PO `draw_outline()`")
    pts = pcbnew.VECTOR_VECTOR2I()
    for x, y in ((bb.GetLeft() + d, bb.GetTop() + d),
                 (bb.GetRight() - d, bb.GetTop() + d),
                 (bb.GetRight() - d, bb.GetBottom() - d),
                 (bb.GetLeft() + d, bb.GetBottom() - d)):
        pts.append(pcbnew.VECTOR2I(x, y))
    return pts


def prostokat(bb: pcbnew.BOX2I) -> pcbnew.VECTOR_VECTOR2I:
    """Pudelko jako lista czterech wierzcholkow dla `ZONE.AddPolygon`."""
    pts = pcbnew.VECTOR_VECTOR2I()
    for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()),
                 (bb.GetRight(), bb.GetBottom()), (bb.GetLeft(), bb.GetBottom())):
        pts.append(pcbnew.VECTOR2I(x, y))
    return pts


def zarys_lokalny(board: pcbnew.BOARD, siec: str):
    """Pudelko obejmujace CALA miedz danej sieci, z zapasem.

    Zwraca `None`, gdy siec nie ma na plytce ani jednego padu i sladu -
    wtedy nie ma z czego liczyc i decyzje podejmuje wolajacy.

    Liczone jest po padach, sladach I przelotkach, nie po samych padach,
    i to nie jest nadmiar ostroznosci. Wylewka VBUS na tej plytce byla
    NOSNA: pad 1 ukladu U4 dochodzil do sladu na B.Cu wylacznie przez
    przelotke siedzaca w tej wylewce, a pad A9 gniazda USB przez nia
    siegal sladu 4,2 mm dalej. Zarys policzony z samych padow odciąłby
    jedno i drugie - sprawdzone, dawalo dwa niepolaczenia i wiszaca
    przelotke.
    """
    bb = pcbnew.BOX2I()
    pusto = True
    for f in board.GetFootprints():
        for pad in f.Pads():
            if pad.GetNetname() == siec:
                bb.Merge(pad.GetBoundingBox())
                pusto = False
    for t in board.GetTracks():
        if t.GetNetname() == siec:
            bb.Merge(t.GetBoundingBox())
            pusto = False
    if pusto:
        return None
    bb.Inflate(mm(WYLEWKA_LOKALNA_ZAPAS_MM))
    return bb


def nowa_wylewka(board: pcbnew.BOARD, warstwa: int, siec) -> pcbnew.ZONE:
    """Wylewka na calej plytce: laminat wciety o WYLEWKA_WCIECIE_MM.

    Ustawienia sa te same, co mialy strefy postawione przy pierwszym
    wylaniu plaszczyzn: pady lite (`connect_pads yes`), bez odsprzegania
    termicznego. Wylewki nikt tu nie rysuje recznie, wiec zarys da sie
    policzyc i nie trzeba go nigdzie pamietac.
    """
    z = pcbnew.ZONE(board)
    z.SetLayer(warstwa)
    z.SetNetCode(siec.GetNetCode())
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
    z.SetLocalClearance(mm(ZONE_CLEARANCE_MM))
    z.SetMinThickness(mm(0.1))
    z.SetThermalReliefGap(mm(ZONE_CLEARANCE_MM))
    z.SetThermalReliefSpokeWidth(mm(ZONE_CLEARANCE_MM))
    z.SetIsFilled(False)

    z.AddPolygon(zarys_wylewki(board))
    board.Add(z)
    return z


def ustaw_pady_lite(board: pcbnew.BOARD) -> int:
    """Wymusza lite polaczenie z wylewka na padach z PADY_LITE.

    Zwraca liczbe zmienionych padow. `-1` w `GetLocalZoneConnection`
    znaczy "dziedzicz po strefie", wiec tylko to warto nadpisywac.
    """
    zmienione = 0
    for f in board.GetFootprints():
        nazwy = PADY_LITE.get(f.GetReference())
        if not nazwy:
            continue
        for pad in f.Pads():
            if pad.GetPadName() not in nazwy:
                continue
            if int(pad.GetLocalZoneConnection()) == int(pcbnew.ZONE_CONNECTION_FULL):
                continue
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
            zmienione += 1
    return zmienione


def set_zones(board: pcbnew.BOARD, w: float, h: float) -> None:
    """Doprowadza wylewki do stanu, ktory deklaruja PLASZCZYZNY i WYLEWKI_ZEWNETRZNE.

    Trzy rzeczy, kazda z konkretnego powodu:

      * **plaszczyzny wewnetrzne trafiaja na warstwy ze stosu.** KiCad nie
        przesunie strefy dlatego, ze warstwa zmienila role - bez tego kroku
        +3V3 na `base` zostaloby na In2, czyli na warstwie, na ktorej ma sie
        teraz trasowac, a padom zasilania nie mialoby co podac pradu,
      * **brakujace wylewki powstaja od nowa.** Autorouter dostaje polecenie
        usuniecia wylewek z warstw trasowania i Quilter usuwa cale strefy,
        nie samo wypelnienie. Po powrocie plytki `fill_zones.py` nie ma
        czego wylac, bo strefy F.Cu i B.Cu po prostu nie istnieja,
      * **strefy zakazu obejmuja cala miedz**, ile by jej nie bylo.

    Zarysow istniejacych stref nie rusza: autorouter potrafi oddac strefe
    obrysowana wzdluz zaokraglonej krawedzi laminatu i to jest lepszy zarys
    niz prostokat, ktory tu powstaje przy tworzeniu nowej.

    Wypelnien nie liczy - robi to `main()` po szyciu, bo dopiero wtedy
    znana jest ostateczna liczba przelotek.
    """
    miedz = warstwy_miedzi()
    numery = dict(miedz)
    plany = PLASZCZYZNY[BOARD.name]
    komplet = pcbnew.LSET()
    for _, numer in miedz:
        komplet.AddLayer(numer)
    zewnetrzne = {pcbnew.F_Cu, pcbnew.B_Cu}

    ruchy = []
    zastane = {}
    maja_plaszczyzne = set()

    def ustaw_laczenie(z):
        """Wymusza na wylewce laczenie sie z padami wlasnej sieci.

        Wszystkie szesc wylewek na tej plytce mialo `ZONE_CONNECTION_NONE`,
        czyli "nie dotykaj zadnego padu". Wylewka trzymala wtedy odstep
        nawet od padow WLASNEJ sieci, a kazdy pad masy, do ktorego nikt nie
        dociagnal sciezki ani przelotki, zostawal w powietrzu. Tak wisialy:
        zwieracz anteny (czyli cala zasada dzialania odwroconej F), masa
        filtra MLPF i ekrany obu przyciskow. Na F.Cu robilo to 70 wysp.

        `nowa_wylewka()` nadaje nowym strefom `FULL`, ale `set_zones` nigdy
        nie poprawialo zastanych - i to jest ta luka.

        Tryb `THT_THERMAL`, a nie `FULL`: pady SMD dostaja polaczenie lite
        (elektrycznie najlepsze), a przelotowe odsprzeganie termiczne.
        Ta plytka jest lutowana recznie, a lity pad masy na nozce listwy
        THT odprowadza cieplo szybciej, niz grot je dostarcza.
        """
        zmiany = []
        if int(z.GetPadConnection()) != int(pcbnew.ZONE_CONNECTION_THT_THERMAL):
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
            zmiany.append("pady -> THT_THERMAL")

        # Odstep tez trzeba WYMUSIC, nie tylko nadac nowym strefom.
        # Zastane wylewki trzymaly swoje wlasne wartosci: 0,200 mm na
        # masie i zasilaniu, a na SYS i VBUS **0,100 mm**, czyli ponizej
        # minimum JLCPCB (0,127). Recznie zmieniona wartosc w KiCadzie
        # zostawala w strefie i zyla wlasnym zyciem obok stalej w tym
        # pliku - dokladnie ta sama luka, co przy trybie laczenia padow.
        docelowy = mm(ZONE_CLEARANCE_MM)
        if z.GetLocalClearance() != docelowy:
            zmiany.append(f"odstep {pcbnew.ToMM(z.GetLocalClearance()):.3f}"
                          f" -> {ZONE_CLEARANCE_MM}")
            z.SetLocalClearance(docelowy)
        z.SetThermalReliefGap(docelowy)
        z.SetThermalReliefSpokeWidth(docelowy)
        return ", ".join(zmiany) if zmiany else False

    def zgubiona(nazwa: str) -> bool:
        """Czy ta nazwa sieci jest smieciem po przenumerowaniu.

        Pusta - strefa wskazuje numer, ktorego juz nie ma. Zlozona z
        samych cyfr - wskazuje numer, ktory tymczasem przejela inna siec,
        nazwana przez atopile od numeru nozki. To drugie jest grozniejsze,
        bo wyglada na poprawne: raz juz trzy wylewki masy pokazywaly na
        siec "7", czyli na wolne wyprowadzenie ekspandera.

        Zadna prawdziwa siec w tym projekcie nie nazywa sie samymi
        cyframi - wszystkie maja nazwy z `override_net_name`.
        """
        return not nazwa or nazwa.isdigit()

    def przywroc_siec(z, warstwa):
        """Oddaje strefie siec, ktora zgubil `ato build`.

        `ato build` przepisuje plik plytki i przy okazji przenumerowuje
        sieci. Strefy trzymaja siec NUMEREM, nie nazwa, wiec po
        przebudowie potrafia wskazywac na cudza siec albo na zadna - i
        wylewka masy staje sie wyspa albo, gorzej, plaszczyzna czyjegos
        sygnalu.

        Ktora siec przywrocic, wynika jednoznacznie z warstwy: zewnetrzne
        opisuje WYLEWKI_ZEWNETRZNE, wewnetrzne PLASZCZYZNY.
        """
        # Po nazwach warstw tego szukac NIE WOLNO: stos przemianowuje
        # In1.Cu na "GND", a In4.Cu na "PWR", wiec `GetLayerName` zwraca
        # etykiete z pliku plytki, a PLASZCZYZNY mowia o nazwach
        # kanonicznych. Jedyne, co sie zgadza po obu stronach, to numer.
        nazwa = board.GetLayerName(warstwa)
        if warstwa in zewnetrzne:
            chciana = WYLEWKI_ZEWNETRZNE.get(pcbnew.LayerName(warstwa))
        else:
            chciana = next((n for n, w in plany.items()
                            if numery.get(w) == warstwa), None)
        if chciana is None:
            return None
        net = board.FindNet(chciana)
        if net is None:
            raise SystemExit(
                f"na plytce {BOARD} nie ma sieci {chciana!r}, a wylewka na "
                f"{nazwa} jej potrzebuje")
        z.SetNet(net)
        ruchy.append(f"wylewka na {nazwa}: ODZYSKANA siec {chciana}")
        return chciana
    # Pole laminatu liczone z PODANYCH wymiarow, a nie z
    # `board.GetBoardEdgesBoundingBox()`. To wywolanie na plytce
    # zmodyfikowanej w pamieci (a obrys dorysowalismy przed chwila) zwraca
    # w KiCadzie 9 goly `SwigPyObject` bez metod, a jego uzycie przewraca
    # caly proces segmentation faultem przy nastepnym siegnieciu do plytki.
    # To ta sama usterka bindingow, ktora opisuje `sprawdz_kontur` przy
    # `GetDrawings()`. Wymiary i tak znamy - przyszly argumentem.
    pole_plytki = mm(w) * mm(h)
    for z in board.Zones():
        if z.GetIsRuleArea():
            if list(z.GetLayerSet().Seq()) != list(komplet.Seq()):
                z.SetLayerSet(komplet)
                ruchy.append(f"{z.GetZoneName() or 'strefa zakazu'} -> "
                             f"{len(miedz)} warstw miedzi")
            continue
        opis = ustaw_laczenie(z)
        if opis:
            ruchy.append(f"{z.GetNetname() or 'wylewka'}: {opis}")
        warstwy = list(z.GetLayerSet().Seq())
        if len(warstwy) == 1 and warstwy[0] in zewnetrzne:
            # Na F.Cu stoja DWA rodzaje wylewek i rozni je nie wyglad,
            # tylko siec: ta z WYLEWKI_ZEWNETRZNE (masa) nalezy do calej
            # warstwy, a kazda inna (SYS, VBUS) to wylewka LOKALNA pod
            # jednym blokiem. Dopoki tego nie rozrozniano, obie szly
            # przez te sama regule i konczylo sie to tak:
            #
            #   wylewka VBUS na F.Cu  906 mm2 (46 % warstwy), priorytet 2
            #   wylewka GND  na F.Cu  157 mm2 w 55 kawalkach, priorytet 0
            #
            # czyli 5 V zamiast masy wokol wszystkiego, w tym 102 mm2
            # w pasku przy antenie (masy zostawalo tam 7 mm2). Antena
            # inverted-F ma odczep zwarty do masy i to plaszczyzna masy
            # jest jej przeciwwaga, wiec to nie kosmetyka.
            if zgubiona(z.GetNetname()):
                przywroc_siec(z, warstwy[0])
            siec_warstwy = WYLEWKI_ZEWNETRZNE.get(pcbnew.LayerName(warstwy[0]))
            nazwa_w = board.GetLayerName(warstwy[0])
            zb = z.Outline().BBox()
            if z.GetNetname() == siec_warstwy:
                zastane[warstwy[0]] = z
                # Wylewka warstwy ma lezec NAJNIZEJ, inaczej zabiera
                # lokalnym ich wlasny placek.
                if z.GetAssignedPriority() != 0:
                    ruchy.append(f"{z.GetNetname()} na {nazwa_w}: priorytet "
                                 f"{z.GetAssignedPriority()} -> 0")
                    z.SetAssignedPriority(0)
                # Zarysow co do zasady nie ruszamy - autorouter potrafi
                # oddac lepszy niz prostokat. Ale zarys mniejszy niz
                # cwierc plytki nie jest wyborem trasera, tylko
                # pozostaloscia po tworzeniu strefy bez obrysu.
                if zb.GetWidth() * zb.GetHeight() < pole_plytki // 4:
                    z.Outline().RemoveAllContours()
                    z.AddPolygon(zarys_wylewki(board))
                    ruchy.append(
                        f"{z.GetNetname()} na {nazwa_w}: zarys byl "
                        f"{pcbnew.ToMM(zb.GetWidth()):.1f} x "
                        f"{pcbnew.ToMM(zb.GetHeight()):.1f} mm, WYPROSTOWANY")
                continue
            # Wylewka lokalna. Jej zarys ma obejmowac miedz WLASNEJ sieci
            # i nic wiecej - prostowanie do calej plytki jest tu dokladnie
            # bledem, nie naprawa.
            if z.GetAssignedPriority() < 1:
                ruchy.append(f"{z.GetNetname()} na {nazwa_w}: priorytet "
                             f"{z.GetAssignedPriority()} -> 1 (lokalna)")
                z.SetAssignedPriority(1)
            zarys = zarys_lokalny(board, z.GetNetname())
            if zarys is None:
                raise SystemExit(
                    f"wylewka {z.GetNetname()!r} na {nazwa_w} nie ma na "
                    f"plytce ANI JEDNEGO padu i sladu tej sieci - nie ma "
                    f"z czego policzyc jej zarysu")
            lb, cel = zb, zarys
            if lb.GetWidth() > cel.GetWidth() or lb.GetHeight() > cel.GetHeight():
                z.Outline().RemoveAllContours()
                z.AddPolygon(prostokat(cel))
                ruchy.append(
                    f"{z.GetNetname()} na {nazwa_w}: zarys "
                    f"{pcbnew.ToMM(lb.GetWidth()):.1f} x "
                    f"{pcbnew.ToMM(lb.GetHeight()):.1f} -> "
                    f"{pcbnew.ToMM(cel.GetWidth()):.1f} x "
                    f"{pcbnew.ToMM(cel.GetHeight()):.1f} mm, ZACIESNIONY")
            continue
        siec = z.GetNetname()
        # Warstwa wewnetrzna niesie DOKLADNIE jedna plaszczyzne, wiec
        # mapa jest tu jednoznaczna i to ona jest zrodlem prawdy - nie
        # plik. Nazwe z pliku bierzemy tylko wtedy, gdy jest zdrowa.
        if zgubiona(siec) and len(warstwy) == 1:
            siec = przywroc_siec(z, warstwy[0]) or siec
        if siec not in plany:
            raise SystemExit(
                f"strefa sieci {siec!r} lezy na warstwie wewnetrznej, a "
                f"PLASZCZYZNY dla plytki {BOARD} jej nie deklaruje")
        maja_plaszczyzne.add(siec)
        cel = numery[plany[siec]]
        if warstwy != [cel]:
            ls = pcbnew.LSET()
            ls.AddLayer(cel)
            z.SetLayerSet(ls)
            ruchy.append(f"{siec} -> {plany[siec]}")

    for nazwa, siec in WYLEWKI_ZEWNETRZNE.items():
        warstwa = numery[nazwa]
        if warstwa in zastane:
            continue
        net = board.FindNet(siec)
        if net is None:
            raise SystemExit(f"na plytce {BOARD} nie ma sieci {siec!r}")
        nowa_wylewka(board, warstwa, net)
        ruchy.append(f"{siec} na {nazwa}: odtworzona")

    # Plaszczyzny wewnetrzne, ktorych NA PLYTCE NIE MA.
    #
    # Dotad ten krok umial tylko PRZENIESC istniejaca strefe na wlasciwa
    # warstwe. Wystarczalo to dopoki plaszczyzny raz powstaly recznie -
    # ale `ato build` ich nie tworzy, a `base` doszla do stanu, w ktorym
    # miala obie wylewki zewnetrzne i ZADNEJ warstwy odniesienia.
    #
    # To nie jest brak kosmetyczny. Para USB high-speed i odstepy klas
    # sa policzone wzgledem masy lezacej 0,2104 mm pod F.Cu, kazda
    # przelotka sygnalowa potrzebuje drogi powrotnej, a pady zasilania
    # procesora nie maja skad wziac pradu, dopoki In4 jest pusta.
    for siec, nazwa in plany.items():
        if siec in maja_plaszczyzne:
            continue
        net = board.FindNet(siec)
        if net is None:
            raise SystemExit(f"na plytce {BOARD} nie ma sieci {siec!r}")
        nowa_wylewka(board, numery[nazwa], net)
        ruchy.append(f"{siec} na {nazwa}: UTWORZONA")

    role = ", ".join(f"{w} = {s}" for s, w in plany.items())
    print(f"plaszczyzny: {role}"
          + (f"; zmiany: {', '.join(ruchy)}" if ruchy else "; bez zmian"))


def stackup_block(old_block: str, stos: list) -> str:
    """Sklada blok `(stackup ...)` z warstw miedzi i dielektrykow ze stosu.

    Wpisy sitodruku, pasty i soldermaski przepisuje z istniejacego bloku bez
    zmian - to one niosa kolor i grubosc maski, ktore ustawia sie osobno.
    Podmieniany jest tylko srodek: miedz i dielektryki.
    """
    def sub_blocks(text: str):
        for m in re.finditer(r"\(layer \"", text):
            i = m.start(); d = 0
            for j in range(i, len(text)):
                if text[j] == "(":
                    d += 1
                elif text[j] == ")":
                    d -= 1
                    if d == 0:
                        yield text[i : j + 1]
                        break

    keep = {b: re.search(r'\(layer "([^"]+)"', b).group(1) for b in sub_blocks(old_block)}
    head = [b for b, n in keep.items() if n in ("F.SilkS", "F.Paste", "F.Mask")]
    tail = [b for b, n in keep.items() if n in ("B.Mask", "B.Paste", "B.SilkS")]

    core = []
    for name, kind, thick, material, er in stos:
        lines = [f'(layer "{name}"', f'\t(type "{kind}")', f"\t(thickness {thick})"]
        if material:
            lines += [f'\t(material "{material}")', f"\t(epsilon_r {er})",
                      "\t(loss_tangent 0.02)"]
        core.append("\n".join(lines) + "\n)")

    # Wykonczenie miedzi jest parametrem ZAMOWIENIA, nie geometrii, wiec
    # przepisujemy je z pliku. Zapis pcbnew wstawia jednak `"None"` wszedzie
    # tam, gdzie plik przyszedl bez tego wpisu - a tak wraca plytka z
    # Quiltera. Traktujemy to jako brak wartosci i wracamy do ENIG.
    finish = re.search(r'\(copper_finish "(?!None")[^)]*\)', old_block)
    body = head + core + tail
    out = ["(stackup"]
    for b in body:
        out += ["\t\t\t" + ln for ln in b.split("\n")]
    out.append("\t\t\t" + (finish.group(0) if finish else '(copper_finish "ENIG")'))
    out.append("\t\t\t(dielectric_constraints no)")
    out.append("\t\t)")
    return "\n".join(out)


def write_net_tie() -> None:
    """Dopisuje `net_tie_pad_groups` do footprintu anteny, w pliku plytki.

    Dwa pady anteny typu F SA jednym kawalkiem miedzi - bez tej deklaracji
    DRC zglasza zwarcie ANT z GND. Footprint ja ma, ale **atopile jej nie
    przenosi**: przepisuje pady, opis, znaczniki i atrybuty, a te linie
    gubi.

    Robione tekstem, a nie przez `FOOTPRINT.AddNetTiePadGroup()`, bo to
    wywolanie wywraca pcbnew KiCada 9 segmentation faultem. Ten plik ma
    juz jeden taki przypadek - `write_stackup()` - i z tego samego powodu:
    bindingi nie nadazaja za formatem pliku.

    Uruchamiane PO `board.Save()`, inaczej pcbnew nadpisalby zmiane.
    Idempotentne, bo `ato build` i tak kasuje te linie przy kazdej
    przebudowie i trzeba ja dopisywac od nowa.
    """
    text = PCB.read_text(encoding="utf8")
    wzorzec = f'(footprint "{ANTENA_FP}:{ANTENA_FP}"'
    i = text.find(wzorzec)
    if i < 0:
        print("net tie anteny: nie znalazlem footprintu, POMINIETE")
        return
    # Wstawiamy zaraz za linia `(attr ...)` tego footprintu - jest w nim
    # dokladnie jedna i lezy przed padami.
    j = text.index("(attr ", i)
    k = text.index("\n", j)
    wciecie = text[text.rindex("\n", 0, j) + 1:j]
    linia = f'{wciecie}(net_tie_pad_groups "1, 2")'
    if text[k + 1:k + 1 + len(linia)] == linia:
        print("net tie anteny: bez zmian")
        return
    PCB.write_text(text[:k + 1] + linia + "\n" + text[k + 1:], encoding="utf8")
    print('net tie anteny: dopisane `net_tie_pad_groups "1, 2"` '
          "(pady 1 i 2 to jedna miedz - DRC ma o tym wiedziec)")


def write_stackup() -> None:
    """Wpisuje stos warstw wprost do pliku plytki.

    Uruchamiane PO `board.Save()`, bo pcbnew nadpisalby te zmiane. KiCad 9
    nie wystawia `BOARD_STACKUP` do Pythona, wiec nie da sie tego zrobic
    przez API. Idempotentne.
    """
    text = PCB.read_text(encoding="utf8")
    i = text.index("(stackup")
    d = 0
    for j in range(i, len(text)):
        if text[j] == "(":
            d += 1
        elif text[j] == ")":
            d -= 1
            if d == 0:
                end = j + 1
                break
    stos = STOSY[BOARD.name]
    new = stackup_block(text[i:end], stos)
    if text[i:end].split() == new.split():
        print("stos warstw: bez zmian")
        return
    PCB.write_text(text[:i] + new + text[end:], encoding="utf8")
    total = sum(x[2] for x in stos)
    print(f"stos warstw: {len(stos)} pozycji, "
          f"{sum(1 for x in stos if x[1] == 'copper')} warstw miedzi, "
          f"laminat {total:.4f} mm (z maskami {total + 0.02:.4f} mm)")


def set_rules(board: pcbnew.BOARD) -> None:
    """Minima plytki. Musza dopuszczac NAJWEZSZA klase, nie domyslna.

    Inaczej DRC zglasza jako blad kazda sciezke klasy wezszej od domyslnej,
    a klasa, ktorej nie da sie narysowac, jest dekoracja.

    Po zejsciu na wiertlo 0,3 mm minimum przelotki to 0,5/0,3, czyli
    dokladnie to, co zamawiamy u JLCPCB w progu "0.3mm/(0.4/0.45mm)".
    Gdyby ktos narysowal cieniej, DRC powie o tym ZANIM zobaczy to wycena.
    """
    ds = board.GetDesignSettings()
    # Progi sitodruku rowne minimum JLCPCB, zeby DRC sprawdzalo to, co
    # producent naprawde umie wydrukowac. Domyslne 0,08 mm grubosci kreski
    # jest ponizej jego mozliwosci - przepuszczalo napisy, ktore JLCPCB
    # i tak musialby pogrubic, psujac proporcje znaku.
    ds.m_MinSilkTextHeight = mm(SILK_TEXT_H_MM)
    ds.m_MinSilkTextThickness = mm(SILK_TEXT_W_MM)
    ds.m_MinClearance = mm(CLEARANCE_MM)
    ds.m_TrackMinWidth = mm(TRACK_MM)
    ds.m_ViasMinSize = mm(min(VIA_DIA_MM, PAD_VIA_DIA_MM))
    ds.m_MinThroughDrill = mm(min(VIA_DRILL_MM, PAD_VIA_DRILL_MM))
    # Pierscien. KiCad trzyma tu domyslne 0,1 mm i tego NIE bylo widac,
    # dopoki przelotki mialy 0,45/0,25 - przy 0,30/0,20 pierscien spada
    # do 0,05 mm i DRC zglasza kazda z 55 kulek. Minimum musi dopuszczac
    # najciensza przelotke na plytce, inaczej jest dekoracja.
    ds.m_ViasMinAnnularWidth = mm(min(
        (VIA_DIA_MM - VIA_DRILL_MM) / 2,
        (PAD_VIA_DIA_MM - PAD_VIA_DRILL_MM) / 2))
    ds.SetCustomTrackWidth(mm(TRACK_MM))
    ds.SetCustomViaSize(mm(VIA_DIA_MM))
    ds.SetCustomViaDrill(mm(VIA_DRILL_MM))


def set_netclasses() -> None:
    """Wpisuje klasy sieci do pliku projektu KiCada.

    Klasy sieci nie mieszkaja w `.kicad_pcb`, tylko w `.kicad_pro`, i to
    jest dobra wiadomosc: `ato build` tego pliku NIE nadpisuje, wiec wpis
    zostaje na stale. Przypisanie idzie po nazwie sieci (`netclass_patterns`),
    a nie po oznaczeniu elementu - nazwy sieci sa stabilne miedzy
    przebudowami, oznaczenia nie.
    """
    proj = json.loads(PROJECT_FILE.read_text(encoding="utf8"))
    ns = proj.setdefault("net_settings", {})
    classes = ns.setdefault("classes", [])

    default = next((c for c in classes if c.get("name") == "Default"), None)
    if default is None:
        raise SystemExit(f"{PROJECT_FILE.name}: brak klasy Default")
    default.update({"track_width": DEFAULT_TRACK_MM, "clearance": CLEARANCE_MM,
                    "via_diameter": VIA_DIA_MM, "via_drill": VIA_DRILL_MM})

    # NETCLASSES opisuje CALY uklad, a kazda plytka stosu niesie tylko
    # jego czesc: para USB i petla przetwornicy siedza na `base`, tor RF
    # odbiornika GNSS na `head`. Klasa bez ani jednej sieci na tej plytce
    # jest wpisem-widmem: myli przy otwarciu plytki w KiCadzie i nie ma
    # sie do czego przypiac. Wpisujemy tylko to, co na plytce faktycznie
    # jest, i mowimy na koniec, co zostalo pominiete.
    #
    # Wciecie w tym wzorcu musi byc dowolne. Plik, ktory wraca z Quiltera,
    # jest przepisany spacjami zamiast tabulatorow, a wzorzec zaczepiony o
    # `\t` nie znajduje w nim ANI JEDNEJ sieci - i wtedy ten skrypt cicho
    # kasuje wszystkie klasy sieci poza Default.
    on_board = set(re.findall(r'^\s*\(net \d+ "([^"]*)"',
                              PCB.read_text(encoding="utf8"), re.M))
    klasy = list(NETCLASSES)
    used = [(name, track, via, drill, clear,
             [n for n in nets if n in on_board], extra)
            for name, track, via, drill, clear, nets, extra in klasy]
    used = [c for c in used if c[5]]

    ns["classes"] = [default] + [
        {**default, "name": name, "track_width": track, "via_diameter": via,
         "via_drill": drill, "clearance": clear, "priority": i, **extra}
        for i, (name, track, via, drill, clear, _, extra) in enumerate(used)
    ]
    # Wzorce sa rozlaczne, wiec kolejnosc nie ma znaczenia.
    ns["netclass_patterns"] = [
        {"pattern": net, "netclass": name}
        for name, _, _, _, _, nets, _ in used for net in nets
    ]

    zones = (proj.setdefault("board", {}).setdefault("design_settings", {})
                 .setdefault("defaults", {}).setdefault("zones", {}))
    zones["min_clearance"] = ZONE_CLEARANCE_MM
    PROJECT_FILE.write_text(json.dumps(proj, indent=2), encoding="utf8")

    listed = {net for _, _, _, _, _, nets, _ in used for net in nets}
    pominiete = [name for name, *_ in klasy
                 if name not in {c[0] for c in used}]
    print(f"klasy sieci: {len(used)} + Default, "
          f"{len(listed)} przypisanych sieci, sygnaly {DEFAULT_TRACK_MM} mm, "
          f"odstep wylewki {ZONE_CLEARANCE_MM} mm")
    if pominiete:
        print("  bez sieci na tej plytce, pominiete: " + ", ".join(pominiete))


def sprawdz_czy_kicad_nie_trzyma_plytki() -> None:
    """Odmawia pracy, gdy plytka jest otwarta w pcbnew.

    Ten skrypt nadpisuje plik plytki. pcbnew trzyma w pamieci WLASNA kopie
    i zapisuje ja przy najblizszym zapisie albo autozapisie - czyli po
    cichu cofa wszystko, co tu powstalo. Raz juz tak zginela podmiana
    obudowy ekspandera: proces `kicad` (menedzer projektu) zostal
    zamkniety, ale `pcbnew` z otwarta plytka zyl dalej i kilka minut
    pozniej zapisal swoja wersje na dysk.

    KiCad zaklada przy otwartej plytce pliki blokady obok niej. Ich
    obecnosc jest jedynym tanim sygnalem, ze ktos ma ten plik w reku.
    """
    katalog = PCB.parent
    blokady = sorted(
        p.name for p in katalog.glob("*.lck")
        if PCB.stem in p.name or p.name.startswith("~")
    )
    if blokady:
        raise SystemExit(
            "plytka jest otwarta w KiCadzie - zamknij pcbnew i powtorz.\n"
            f"  blokady w {katalog}: {', '.join(blokady)}\n"
            "  (ten skrypt nadpisuje plik; pcbnew zapisalby na to swoja "
            "kopie sprzed zmian)")


def main() -> None:
    w = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_W_MM
    h = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_H_MM
    if max(w, h) >= 100:
        raise SystemExit(f"{w} x {h} mm - powyzej 100 mm cena panelu skacze")

    sprawdz_czy_kicad_nie_trzyma_plytki()
    prune_fp_lib_table()
    set_netclasses()
    board = pcbnew.LoadBoard(str(PCB))
    set_stackup(board)
    set_rules(board)
    # Obrys bez przerw: plytka jest prostokatem, nie polowka kanapki.
    draw_outline(board, w, h, CORNER_R_MM, [], BOARD_X_MM, BOARD_Y_MM)
    otwory = draw_mounting_holes(board, w, h, CORNER_R_MM,
                                 BOARD_X_MM, BOARD_Y_MM)
    # PRZED wylewkami: strefa liczy szprychy przy wylewaniu, wiec pad
    # musi juz wtedy wiedziec, ze ma byc wlany lito.
    lite = ustaw_pady_lite(board)
    # PO obrysie: wylewka bierze swoj zarys z krawedzi laminatu.
    set_zones(board, w, h)
    # PO wylewkach: strefa zakazu ma je przycinac, a nie odwrotnie.
    bez_sieci = napraw_siec_anteny(board)
    antena = draw_antenna_keepout(board)
    # PO strefach: przelotki maja byc ostatnia rzecza dokladana
    # do miedzi, zeby kasowanie poprzedniej siatki nie kolidowalo
    # z przebudowa wylewek.
    szycie, skasowane = stitch_thermal_pads(board)
    # PO szyciu: gdyby kiedys pad zwieracza trafil w rodzine szytych
    # obudow, kasowanie starej siatki zabraloby te przelotke razem z nia.
    zwieracz = przelotka_zwierajaca(board)
    sitodruk = ustaw_sitodruk(board)
    za_cienkie = sprawdz_przelotki(board)

    # Wylanie stref MUSI byc po szyciu i przed zapisem. Ten skrypt dodaje
    # i kasuje przelotki, a wylewka wylana wczesniej nie ma wokol nowych
    # przelotek otworow izolacyjnych - DRC zglasza wtedy naruszenia
    # otworu i mostki maski, ktorych w miedzi nie ma. Zanim to tu weszlo,
    # plytka miala z tego powodu 3 naruszenia otworu i 2 mostki maski,
    # ktore znikly same po pierwszym wylaniu.
    wylane = pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    board.Save(str(PCB))
    # Kontur sprawdza sie na ZAPISANYM pliku, nie na obiekcie w pamieci.
    # Dwa powody, oba praktyczne: sprawdzamy to, co naprawde pojedzie do
    # producenta, a przy okazji omija to `GetDrawings()`, ktore na
    # zmodyfikowanej w pamieci plytce przewraca sie w bindingach KiCada 9
    # ("SwigPyObject is not iterable").
    ksztaltow = sprawdz_kontur(PCB)
    write_stackup()
    write_net_tie()
    print(f"obrys {w} x {h} mm w ({BOARD_X_MM}, {BOARD_Y_MM}), naroznik R{CORNER_R_MM}, "
          f"{board.GetCopperLayerCount()} warstw miedzi, "
          f"sciezka {TRACK_MM} mm, odstep {CLEARANCE_MM} mm")
    for opis, srednica, gdzie, web in otwory:
        print(f"otwory {srednica} mm: {len(gdzie)} szt. - {opis}, "
              f"najciensza obwodka {web:.2f} mm")
    if antena:
        x, y, szer, wys = antena
        print(f"strefa zakazu pod antena: {szer:.2f} x {wys:.2f} mm "
              f"na wszystkich warstwach miedzi, "
              f"wysrodkowana na punkcie zasilania ({x:.2f}, {y:.2f})")
    else:
        print("UWAGA: nie znalazlem footprintu anteny - strefy zakazu NIE MA")
    if bez_sieci:
        print(f"antena: {bez_sieci} padow bylo bez sieci - przypisane do GND")
    for ref, ile, w, h, kolizje in szycie:
        blok = f", {kolizje} miejsc zablokowanych cudza miedzia" if kolizje else ""
        print(f"szycie {ref}: {ile} przelotek {PAD_VIA_DIA_MM}/"
              f"{PAD_VIA_DRILL_MM} mm w miedzi padu {w:.2f} x {h:.2f} mm, "
              f"odstep >= {STITCH_PITCH_MM} mm{blok}"
              + (f" (skasowano {skasowane} starych)" if skasowane else ""))
    print(f"wylewki: {'wylane' if wylane else 'NIE UDALO SIE WYLAC'} "
          f"({len([z for z in board.Zones() if not z.GetIsRuleArea()])} stref)")
    if lite:
        print(f"pady lite: {lite} - "
              + ", ".join(f"{r} {'/'.join(n)}" for r, n in PADY_LITE.items()))
    if zwieracz:
        print(f"przelotka zwierajaca anteny: ({zwieracz[0]:.2f}, {zwieracz[1]:.2f})"
              f" - radiator zwarty do plaszczyzny masy")
    print(f"sitodruk: {sitodruk[0]} z {sitodruk[1]} napisow poprawione - "
          f"oznaczenia na {SILK_TEXT_H_MM} x {SILK_TEXT_W_MM} mm, napisy wlasne "
          f"tylko na kresce {SILK_TEXT_W_MM} mm (minimum JLCPCB)")
    print(f"obrys zamkniety: {ksztaltow} ksztaltow, kazdy wierzcholek laczy dwa")
    if not za_cienkie:
        print(f"wszystkie przelotki maja wiertlo >= "
              f"{min(VIA_DRILL_MM, PAD_VIA_DRILL_MM)} mm (bezplatny prog JLCPCB)")


if __name__ == "__main__":
    main()
