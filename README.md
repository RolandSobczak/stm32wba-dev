# wb55-dev

Dev board na **STM32WB55CGU6** (Bluetooth 5.x + 802.15.4) z pełnym torem
zasilania przeniesionym z `gps_tracker-6l`, pamięcią masową na płytce, anteną
w laminacie i wszystkimi wolnymi nóżkami na goldpinach 2,54 mm.

```
USB-C ──▶ BQ25896 ──┬──▶ SYS ──▶ TPS63020 ──▶ 3V3 ──┬──▶ STM32WB55CGU6 ──▶ MLPF ──▶ antena PCB
  │  (Rd 5.1k + ADC) │                              │        │
  └── D+/D- ─────────│──────────────────────────────│────────┘
                     └──▶ Li-Po 1S                  ├──▶ SD NAND 2 Gbit (SPI1)
                          │                         │
                          └──▶ BQ27441 (gauge)      └──▶ dwie listwy 1×12 (2,54 mm)
                                  │
                                  └── I2C1 ─────────────────┘
```

Obrys 32,5 × 59,6 mm, cztery warstwy, narożniki R2,0, **dwa zestawy otworów**:
cztery M3 (⌀3,2) odsunięte 4,5 mm od krawędzi i cztery ⌀2,0 odziedziczone
po obrysie 25,8 × 42,2.

## Co jest wzięte z `gps_tracker-6l`

Tor zasilania w całości, razem z komentarzami uzasadniającymi — one są
w tych plikach wartością, a nie dekoracją:

| blok | część | skąd |
|---|---|---|
| gniazdo USB-C + ESD | GCT USB4085-GF-A, USBLC6-2SC6 | `power.ato` |
| ładowarka NVDC | TI BQ25896 (I2C 0x6B) | `power.ato` |
| gauge | TI BQ27441-G1A (I2C 0x55), bocznik 10 mΩ po stronie dodatniej | `power.ato` |
| 3V3 | TI TPS63020, buck-boost | `power.ato` |
| gniazdo ogniwa | Molex PicoBlade 53261-0371 — **ten sam pakiet wchodzi w obie płytki** | `power.ato` |
| stos 4-warstwowy | JLC04161H-7628, prepreg 0,2104 mm pod F.Cu | `tools/board_setup.py` |
| obrys, otwory, wylewki, klasy sieci | — | `tools/board_setup.py` |

Zmieniły się trzy rzeczy i każda ma powód w pliku:

1. **CC bez PD.** STM32WB55 nie ma UCPD (potwierdzone listą peryferiów
   w `STM32WB55CGUx.xml`). Zamiast negocjacji PD: dwa Rd 5,1 kΩ i pomiar
   napięcia na obu CC przetwornikiem — źródło USB-C ogłasza swój prąd prądem
   Rp niezależnie od PD. Szczegóły, progi i sekwencja dla firmware'u:
   [Zasilanie z USB](#zasilanie-z-usb--co-ustala-prąd-wejściowy).
   Efekt uboczny jest korzystny: Rd działa też przy martwym procesorze,
   więc płytka prosto z montażu dostaje VBUS.
2. **Dzielnik VBUS_SENSE wypadł** — bez maszyny stanów PD nie ma czego nim
   mierzyć w milisekundach, a napięcie VBUS czyta ADC ładowarki po I2C.
3. **Gauge `DRZR` → `DRZT`** — ten sam układ, inna nawijka. `DRZR` ma na LCSC
   stan 0.

## BOM

34 pozycje, wszystkie na stanie LCSC (sprawdzone 2 października 2026),
około **$30,50** za komplet części na jedną sztukę w cenach detalicznych.
Najdroższe: STM32WB55CGU6 $9,04 · SD NAND $8,66 · BQ25896 $3,52 ·
BQ27441 $2,52 · USB-C $1,41.

Pełna lista: `build/builds/dev/dev.bom.csv` (powstaje przy `ato build`).

Trzy pozycje odziedziczone z trackera miały na LCSC stan zero i zostały
podmienione — w komentarzach przy nich stoją nowe numery:

| było | jest | dlaczego |
|---|---|---|
| C25804 10 kΩ | **C98220** YAGEO RC0603FR-0710KL | stan 0 |
| C96446 10 µF 25 V | **C479655** 0603X106M250NT | stan 0 |
| C346479 bocznik 10 mΩ | **C105362** FMF06FTHR010-LH | stan 0; nowy ma ±1 %, 1 W i TCR ±70 ppm/°C, czyli lepiej niż poprzednik |

Poza BOM-em (kupowane osobno albo niekupowane wcale): dwie listwy goldpinów
1×12 2,54 mm, złącze SWD Samtec SHF-105-01-L-D-RA, cztery pady pomiarowe
i antena — ta ostatnia jest kształtem miedzi, nie elementem.

## Mapa wyprowadzeń

Układ ma **30 nóżek I/O i wszystkie są rozdane.** Dziewięć wolnych wychodzi
na prawą listwę.

```
 1 VBAT   +3V3           17 PA8   WOLNY          33 VLXSMPS SMPS
 2 PC14   LSE_IN         18 PA9   WOLNY          34 VDDSMPS +3V3
 3 PC15   LSE_OUT (0R)   19 PB2   CHG_STAT       35 VDD     +3V3
 4 PH3    BOOT0          20 VDD   +3V3           36 PA10    WOLNY
 5 PB8    PMIC_SCL       21 RF1   -> MLPF        37 PA11    USB_D_N
 6 PB9    PMIC_SDA       22 VSSRF GND            38 PA12    USB_D_P
 7 NRST   reset          23 VDDRF +3V3           39 PA13    SWDIO
 8 VDDA   +3V3           24 OSC_OUT 32 MHz       40 VDDUSB  +3V3
 9 PA0    CC1 (ADC_IN5)  25 OSC_IN  32 MHz       41 PA14    SWCLK
10 PA1    CC2 (ADC_IN6)  26 AT0   bez sieci      42 PA15    WOLNY
11 PA2    WOLNY          27 AT1   bez sieci      43 PB3     SWO
12 PA3    WOLNY          28 PB0   CHG_INT        44 PB4     GAUGE_INT
13 PA4    SD_CS          29 PB1   CHG_CE         45 PB5     WOLNY
14 PA5    SD_CLK         30 PE4   CHG_PG         46 PB6     WOLNY
15 PA6    SD_MISO        31 VFBSMPS SMPS         47 PB7     WOLNY
16 PA7    SD_MOSI        32 VSSSMPS GND          48 VDD     +3V3
                                                 49 EP      GND  (jedyna masa!)
```

**Masa układu jest wyłącznie na padzie pod obudową** — UFQFPN-48 nie ma ani
jednej nóżki VSS. Pad dostaje **siatkę 5×5 = 25 przelotek** 0,50/0,25 mm
w rastrze 1,12 mm, stawianą przez `tools/board_setup.py`. Bez niej masa
procesora wisiałaby na wylewce F.Cu, a płaszczyzna In1 leży 0,2104 mm niżej.

**Przelotki leżą w padzie, więc muszą być zalane** — a to kosztuje. Wycena
JLCPCB (100 × 100 mm, 5 szt., FR-4 1,6 mm, 3–4 dni):

| konfiguracja | Via Covering | Via Plating | razem |
|---|---|---|---|
| 4 warstwy, Plugged albo Untented | €0,00 | — | **€7,13** |
| 4 warstwy, **Epoxy Filled & Capped** | €15,85 | €3,06 | **€26,03** |
| 6 warstw, Epoxy Filled & Capped (domyślne) | €0,00 | €0,00 | **€28,52** |

Dopłata na czterech warstwach to **€18,91**; „Horizontal Electroless Copper
Plating" (€3,06) jest przy zalewaniu wymuszone. Sześć warstw wychodzi €2,49
drożej, ale przy czasie produkcji 8–9 dni zamiast 3–4 (przyspieszenie 6L do
3–4 dni to +€118,01) i bez możliwości HASL.

**Wszystkie wiertła mają 0,3 mm i ani dziesiątej mniej.** W formularzu
JLCPCB „Min via hole size/diameter" tylko pierwszy próg — `0.3mm/(0.4/0.45mm)`
— jest bezpłatny; każdy niższy podnosi cenę całego zamówienia. Dlatego
przelotka sygnałowa to **0,5/0,3** (a nie 0,6/0,3 jak wcześniej — próg
dopuszcza średnice od 0,4 mm, więc 0,1 mm wraca na trasowanie), a ta w padzie
**0,5/0,3** z sufitem narzuconym przez samo JLCPCB: *„Vias should be at most
0.5 mm in diameter to avoid incomplete filling. Vias violating this size will
be left unfilled."*

`board_setup.py` sprawdza to przy każdym uruchomieniu i wypisuje każdą
przelotkę z wiertłem poniżej progu — razem z pozycją i siecią.

Listwy (opis i uzasadnienie kolejności w `headers.ato`):

```
LEWA (zasilanie + uruchamianie)     PRAWA (wolne nóżki)
 1 VBUS      7 GND                   1 +3V3    7 PA15
 2 SYS       8 ——                    2 PA2     8 PB5
 3 +3V3      9 ——                    3 PA3     9 PB6
 4 GND      10 GND                   4 PA8    10 PB7
 5 ——       11 BOOT0                 5 PA9    11 GND
 6 ——       12 GND                   6 PA10   12 GND
```

Pozycje 5, 6, 8 i 9 lewej listwy są **celowo bez sieci**. Niosły SWD, zanim
na płytkę weszło osobne złącze ARM Cortex Debug 2×5 — sygnały przeniosły się
tam w całości, a footprint listwy został nietknięty.

Wejście w DFU: zworka z pinu 11 (BOOT0) na pin 3 (+3V3) lewej listwy i reset.

## SWD

**Samtec SHF-105-01-L-D-RA** (`CN1`) — standardowy ARM Cortex Debug Connector
2×5 w rastrze 1,27 mm, kątowy, przewlekany, w kołnierzu z kluczem. Kabel
J-Link EDU Mini wchodzi w niego wprost; ten sam kabel obsługuje ST-LINK V2/V3
i większość sond innych producentów.

```
1 VTref (+3V3)   2 SWDIO
3 GND            4 SWCLK
5 GND            6 SWO
7 KEY            8 NC (TDI)
9 NC (TRST)     10 NRST
```

Dwie masy leżą **między** szybkimi liniami (pin 3 między SWDIO i SWCLK, pin 5
między SWCLK a SWO), więc każda ma drogę powrotną w sąsiedniej żyle taśmy —
przy SWO, którym idzie konsola ITM, od tego zależy, przy jakiej częstotliwości
strumień przestaje się sypać.

**VTref to wejście sondy, nie zasilanie płytki.** J-Link EDU Mini nie zasila
celu i pobiera z tego pinu mniej niż 170 µA, więc płytka musi być zasilona
z USB-C albo z ogniwa — inaczej sonda jej nie zobaczy, a wygląda to dokładnie
jak martwy procesor.

## Jak to zbudować

Wszystko w kontenerze — `tools/boards.py` wywala się na hostowym `pcbnew`,
bo KiCad 10 podniósłby format płytki jednokierunkowo:

```bash
distrobox enter -n atopile -- ato build -b dev           # netlista + projekt KiCada
python3 tools/check_pinout.py                            # mapa nóżek wobec danych ST
distrobox enter -n atopile -- python3 tools/board_setup.py
```

`board_setup.py` jest idempotentny i trzeba go puszczać **po każdym**
`ato build` — `ato` nadpisuje plik płytki i gubi przy tym `net_tie_pad_groups`
anteny. Skrypt ustawia:

* stos 4-warstwowy (In1 = `GND`, In2 = `PWR`), bez niego tor RF liczyłby się
  na ~120 Ω zamiast 50,
* obrys 32,5 × 59,6 mm z narożnikami R2,0, lewym górnym rogiem w (8,41 / 3,30),
  i dwa zestawy otworów nieplaterowanych: **4 × ⌀3,2 (M3)** odsunięte 4,5 mm
  od obu krawędzi oraz **4 × ⌀2,0** odziedziczone po obrysie 25,8 × 42,2,
  w stałych miejscach (10,18 / 4,70), (33,18 / 4,70), (10,18 / 44,10),
  (33,18 / 44,10). Najcieńsza obwódka laminatu w całym komplecie: 0,36 mm,
* wylewki masy na F.Cu i B.Cu, płaszczyzny na In1/In2,
* klasy sieci — m.in. **RF 0,39 mm** (`RF1`, `ANT`) i **USB 0,28 mm**
  (`USB_D_P`/`USB_D_N` przy procesorze, `USB_CONN_P`/`USB_CONN_N` przy
  gnieździe — przyrostki `_P`/`_N` są warunkiem, żeby KiCad w ogóle
  rozpoznał parę różnicową),
* **strefę zakazu 15,2 × 5,2 mm pod anteną na wszystkich czterech warstwach**,
* **szycie przelotkami pod padami termicznymi** obudów bez nóżek (QFN/SON/DFN)
  leżącymi na masie: `U1` 5×5 = 25 przelotek w padzie 5,50 × 5,50 mm,
  `U4` 2×2 = 4 w padzie 2,70 × 2,70. Przelotki 0,50/0,25 mm, margines do
  krawędzi padu 0,25 mm. Siatka idzie za rozmieszczeniem — przesunięcie
  albo obrócenie układu przenosi ją razem z nim,
* `net_tie_pad_groups "1, 2"` na antenie, żeby DRC nie zgłaszał zwarcia
  ANT–GND (w antenie typu F to zwarcie jest zamierzone).

## Antena

TI AN043 (SWRA117D), odwrócone F, 15,2 × 5,7 mm, VSWR < 2 w całym paśmie ISM.
Geometria przepisana co do setnej z Table 1 noty i sprawdzona rachunkiem —
`L3 = W1+D5+W2+D6+W2 = 5,00` oraz gabaryt `15,20 × 5,70` muszą się domknąć
i domykają się (`parts/Antenna_IFA_2G4/Antenna_IFA_2G4.ato`).

Między RF1 a anteną stoi **jedna** część: `MLPF-WB55-01E3`, scalona sieć
dopasowania ST z filtrem harmonicznych. AN5165 §7: zastępuje dyskretny
matching (0,8 pF + 2,7 nH + 0,3 pF) razem z osobnym filtrem, przy
równoważnych parametrach. Nie ma tu czego stroić.

**Do zmierzenia na pierwszej sztuce.** Nota mierzyła tę antenę na laminacie
dwuwarstwowym 1,6 mm; tutaj laminat ma tyle samo, ale masa biegnie 0,21 mm
pod warstwą górną — pod samą anteną wycięta, więc różnica dotyczy głównie
pojemności brzegowej. Kierunek ewentualnej poprawki podaje nota: grubszy
laminat → antena krótsza.

## Co zostało do zrobienia

Projekt dowozi źródło, netlistę, stos, obrys z otworami, klasy sieci
i footprint anteny. **Rozmieszczenie i trasowanie to robota w KiCadzie** —
wszystkie elementy stoją na razie w domyślnych pozycjach z `ato build`.

Czego pilnować przy rozmieszczaniu (uzasadnienia w nagłówku `dev.ato`):

* procesor, oba kwarce, cewki SMPS i cała droga RF **na F.Cu**, nad litą
  masą In1 — AN5165 §4.3,
* antena na krótszej krawędzi, wyśrodkowana między górnymi otworami M3,
  zwrócona na zewnątrz; między nimi zostaje ~24 mm luzu na 15,2 mm anteny,
* MLPF tuż przy procesorze, odcinek 50 Ω do anteny najkrótszy, jaki wyjdzie,
* USB-C i gniazdo ogniwa na przeciwnej krawędzi — najdalej od anteny,
* pętla SMPS (`VDDSMPS → VLXSMPS → 10 nH → 10 µH → VFBSMPS`) krótka i w całości
  na F.Cu,
* obrys przeszedł trzy wersje i każda jest w komentarzu w
  `tools/board_setup.py`: **38 × 50** (szacunek z sumy powierzchni, przed
  rozmieszczeniem), **25,8 × 42,2** (po pierwszym rozmieszczeniu), **51,6 × 84,4**
  (×2 — przesada), **38,7 × 63,3** (×1,5) i **32,5 × 59,6** (docięte ręcznie
  pod rozmieszczenie i tu wyrównane).
* **Otwory M3 nie są współśrodkowe z narożnikami** i to jest poprawka po
  błędzie: płytka rosła w prawo i w dół, więc lewy górny róg nowej płytki
  to ten sam róg, co starej — a tam już siedział otwór ⌀2,0. Oba wypadały
  1,49 mm od siebie przy wymaganych 2,60 i zlewały się w jedną dziurę.
* Narożnik ma **R2,0, nie R2,5**: lewy górny ⌀2,0 leży wewnątrz łuku, więc
  to łuk wyznacza mu obwódkę. Przy R2,5 zostawało 0,18 mm, przy R2,0 — 0,36.
  Wymiary i położenie rogu siedzą w stałych `BOARD_X_MM` / `BOARD_Y_MM` /
  `DEFAULT_W_MM` / `DEFAULT_H_MM`, żeby skrypt je **odtwarzał**, a nie
  nadpisywał — inaczej pierwsze uruchomienie po ręcznej poprawce
  skasowałoby ją bez słowa.
* płytka rośnie **w prawo i w dół**, róg zostaje w (8,78 / 3,30) — dzięki
  temu powiększenie nie rusza niczego, co już rozmieszczone, a zestaw
  otworów ⌀2,0 zostaje tam, gdzie był.

Potem DRC na regułach JLCPCB (0,127/0,127, wiertło 0,2).

## Zasilanie z USB — co ustala prąd wejściowy

To jest miejsce, w którym najłatwiej szukać peryferialu, którego nie ma, więc
warto je przeczytać przed pisaniem firmware'u. Pełne uzasadnienie w nagłówku
`power.ato`.

**Nic na tej płytce nie „włącza" 3 A — źródło oferuje je samo.** Źródło USB-C
wystawia na CC **Rp**, i to jest deklaracja, nie negocjacja. Nasze Rd 5,1 kΩ
zamienia ją na napięcie stałe:

| co źródło daje przy 5 V | Rp (rezystor / źródło prądowe) | na Rd 5,1 kΩ | okno odczytu |
|---|---|---|---|
| Default USB (500/900 mA) | 56 kΩ do 5 V / 80 µA | 0,42 / 0,41 V | 0,25–0,61 V |
| 1,5 A | 22 kΩ do 5 V / 180 µA | 0,94 / 0,92 V | 0,70–1,16 V |
| 3,0 A | 10 kΩ do 5 V / 330 µA | 1,69 / 1,68 V | 1,31–2,04 V |

Przerwy między oknami (0,61–0,70 i 1,16–1,31 V) są martwe — pomiar, który
w nie wpadnie, ma zostawić poprzednią, **niższą** wartość.

VBUS jest żywe z pełną zadeklarowaną zdolnością od chwili, w której źródło
wykryje Rd. Nie trzeba o nie prosić; cała umowa polega na tym, że to
**odbiornik** pilnuje, żeby nie wziąć więcej. Interfejsem procesora są więc
**dwa kanały przetwornika** (PA0 = ADC1_IN5, PA1 = ADC1_IN6) i nic poza tym.
Mierzymy oba, bo przez kabel podłączony jest tylko jeden — ten z napięciem
mówi przy okazji, którą stroną wszedł wtyk.

Sam prąd wejściowy jest **minimum z trzech** rzeczy:

1. **rezystor na ILIM (121 Ω)** — sufit sprzętowy 2,64/2,93/3,22 A, nie do
   przeskoczenia zapisem po I2C,
2. **rejestr IINLIM** — po starcie 500 mA, bo PSEL wisi wysoko (USB SDP),
3. **ICO (Input Current Optimizer)** — sam podnosi prąd aż do progu, przy
   którym źródło zaczyna siadać, czyli **mierzy** zamiast wierzyć deklaracji.

ICO jest domyślnie włączony, ale **rusza sam tylko po wykryciu DCP** — przy
PSEL wysoko jesteśmy SDP, więc firmware musi go odpalić bitem `FORCE_ICO`
(REG09[7]). Bez tego najlepszy mechanizm w tej ładowarce po prostu nie
zadziała.

Pod spodem jest VINDPM: gdy źródło siada, ładowarka sama cofa prąd. Zbyt
optymistyczny IINLIM kończy się więc „ładuje wolniej", a nie zapadnięciem
szyny.

### Dlaczego nie ma tu układu PD

Bo nic by nie dał. Ogniwo przyjmie najwyżej 1,9 A (1C) ≈ 8 W, a przy wybranym
ICHG = 1,3 A z wejścia schodzi ~6,4 W, czyli **1,28 A przy 5 V**. Źródło
ogłaszające 3 A daje 15 W — ponad dwukrotny zapas. PD dołożyłoby wyższe
*napięcie*, a nie większą moc, a BQ25896 jest przetwornicą obniżającą.

Do tego dwa twarde sufity: **V(ACOV) ładowarki to 14 V** (próg z tabeli
parametrów, nie z rejestru), więc z PD użyteczne byłyby tylko 9 V i 12 V;
a **USBLC6-2SC6 ma napięcie przebicia VBUS–GND min. 6 V**, więc PD oznacza
też wymianę układu ESD, a nie dołożenie jednej kości.

Gdyby kiedyś miało to być stanowisko do zabawy z USB-PD, pierwszy wybór to
STUSB4500 (C2678061, QFN-24 4×4, ~$2,7) — negocjuje autonomicznie z NVM,
I2C 0x28 wchodzi na istniejącą magistralę obok ładowarki i gauge'a, bez
zabierania nóżki.

## Firmware — czego sprzęt oczekuje

* **SMPS startuje w trybie BYPASS** (DS11929 §3.7.1) — rdzeń żywi się z LDO
  i płytka wstaje nawet bez cewek. Tryb SMPS włącza firmware; to oszczędność
  prądu przy nadawaniu, nie warunek startu.
* **HSE 32 MHz bez kondensatorów obciążenia** — pojemność daje wewnętrzna
  banka `XOTUNE` (6 bitów, ±40 ppm). Tam też stroi się częstotliwość po
  pomiarze.
* **SD NAND w trybie SPI**: host musi ściągnąć `DAT3` (CS) do zera przy
  pierwszych taktach inicjalizacji, inaczej układ wybierze tryb SD.
  SPI1 na APB2 → maksymalnie 32 MHz SCK, realnie 2–3 MB/s.
* **Ładowarka** — sekwencja po wpięciu kabla:

  ```
  1. ADC na CC1/CC2    →  które okno z tabeli wyżej
  2. IINLIM := 500 mA / 1,5 A / 3,0 A      ← deklaracja źródła, sufit
  3. FORCE_ICO = 1                         ← ładowarka szuka maksimum POD tym sufitem
  4. odczyt IDPM_LIM i ICO_OPTIMIZED       ← ile naprawdę wyszło
  5. ICHG := 1300 mA (0,68 C)
  6. watchdog I2C co < 40 s
  ```

  Kroki 1–2 to zaufanie deklaracji, krok 3 to pomiar — warto zrobić oba.
  Rp może się zmienić w trakcie pracy (hub rozdzielający moc), więc odczyt
  CC powtarza się, a nie robi raz przy starcie.

  Watchdog: po 40 s bez odświeżenia rejestry wracają do domyślnych, czyli do
  500 mA na wejściu. Zawieszony firmware zostawia więc ogniwo ładowane za
  słabo, nie za mocno.
