---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "uriprocess-standard",
  "kind": "information",
  "version": 1,
  "title": "Standard wytwarzania URIprocess 0.1.0",
  "status": "implemented",
  "owner": "wellmanifest/uriprocess",
  "created": "2026-09-09",
  "updated": "2026-09-09",
  "review_after": "2026-10-09",
  "source_revision": "f29f72a3b96a2400cfcdd27205509604da3e8b27",
  "affected_repositories": ["wellmanifest/uriprocess"],
  "evidence": [
    "repo://wellmanifest/uriprocess/policy.json",
    "repo://wellmanifest/uriprocess/schemas/package.schema.json",
    "repo://wellmanifest/uriprocess/operations/conformance.py",
    "repo://wellmanifest/uriprocess/tests/test_conformance.py",
    "https://github.com/subactor/uriprocess/tree/f29f72a3b96a2400cfcdd27205509604da3e8b27",
    "https://github.com/subactor/uripack/tree/23925ec4b3a5283f51e74b36c4bd33a9cd2820b7"
  ]
}
---

# Standard wytwarzania URIprocess 0.1.0

<!-- docs:section purpose -->
## Cel

URIprocess jest pakietem istniejącej implementacji procesu, zachowującym pełną
tożsamość URI, natywny kontrakt, źródła i testy. Standard określa sposób jego
wytwarzania oraz dowody wymagane na kolejnych etapach dostarczenia.
HOME `wellmanifest`, SHAPE `domain_pack`. Generatory, wykonanie URIpack, Guard,
publikacja i routing pozostają w repozytoriach runtime.

Słowa MUSI, NIE WOLNO i POWINIEN mają znaczenie normatywne. `policy.json`
zawiera stabilne wymagania, profile i diagnostykę. Schematy opisują istniejące
manifesty. Zgodność ze standardem nie jest zgodą na wykonanie procesu.

<!-- docs:section scope -->
## Zakres

| Profil | Format manifestu | Natywny sposób użycia |
| --- | --- | --- |
| `poa-node-v1` | `uriprocess.package/v1` | Biblioteka decyzji ES module, adapter stdin JSON, npm i jawnie testowany kontener. |
| `python-native-v1` | `uriprocess.native-package/v1` | Oryginalny pakiet Pythona, manifest konektora i `urirun.bindings`. |

Jedna paczka może zawierać wiele oryginalnych tras URI. Nie wymusza się
sztucznego rozbijania natywnego konektora. `uriprocess/<name>` jest miejscem
dostarczenia, a nie nowym URI. Inne języki i DSL wymagają jawnego profilu.
Sama deklaracja procesu nie dowodzi implementacji jego grafu capabilities.

<!-- docs:section evidence -->
## Podstawa i dowody

Wymagania wynikają z `subactor/uriprocess` w rewizji podanej w metadanych:
dwóch bibliotek POA i sześciu konektorów Pythona obejmujących 21 URI. Jest to
rewizja analizowanego źródła, nie rewizja publikacji nowego standardu.
Kontrakt ekstrakcji odnosi się do URIpack
`23925ec4b3a5283f51e74b36c4bd33a9cd2820b7`.

Szesnaście testów standardu sprawdza syntetyczne paczki, odmowy, brak zapisów,
zgodność eksportów npm, pochodzenie i natywne metadane. Nie wykonuje procesów
ani nie dowodzi działania produkcji. Adopcja wymaga osobnych testów na
rzeczywistych paczkach konsumenta.

<!-- docs:section content -->
## Wymagania

### URP-001–004: źródło, URI i budowa

1. Producent MUSI wskazać repozytorium, pełny niezmienny SHA Git oraz jawną
   listę źródeł, zależności przechodnich, kontraktów i oryginalnych testów.
   Gałąź, tag ani bieżący katalog roboczy nie zastępują przypięcia.
2. Publiczne URI MUSZĄ być identyczne z oryginalnym kontraktem. Producent MUSI
   odrzucać kolizje właścicieli. Nie wolno usuwać authority, dopisywać wersji
   do tras bez wersji ani wyprowadzać tożsamości wyłącznie z nazwy katalogu.
3. Kopiowane bajty i bit wykonywalności Git MUSZĄ odpowiadać źródłowym obiektom.
   `provenance.json` wiąże ścieżki źródłowe, docelowe i SHA-256. Natywny profil
   wymaga `mode`; starszy POA dopuszcza jego brak oznaczający `100644`.
   Nowe projekcje POWINNY zapisywać tryb jawnie. Pochodzenie nie jest podpisem.
4. Natywne nazwy, wersje, zależności, entry points, testy i licencje MUSZĄ zostać
   zachowane. Brak licencji nie pozwala nadać cudzym źródłom nowej licencji.
   Generowane pliki MUSZĄ należeć do zamkniętej listy profilu i być oddzielone
   od kopii źródłowych przez rekord pochodzenia.
5. Należy odrzucać dowiązania, pliki specjalne, ścieżki absolutne, `..`, niejawne
   źródła i nadpisanie celu. Sekrety i prywatny stan operacyjny nie mogą wejść
   do paczki, repozytorium, URL-a pochodzenia ani dowodu publikacji.
6. POA zachowuje bibliotekę decyzji i `executes_declared_capabilities=false`.
   Eksport npm może być skrótem tekstowym albo równoważną mapą `.`; obraz bazowy
   wymaga digestu. Python zachowuje trasy, dystrybucję, wersję, zależności i
   `urirun.bindings`. `production_binding_verified=false` opisuje zakres pakowania.

Paczka zachowuje natywny układ: `poa/<process>/<authority>/v<N>/` lub
`native/<connector-id>/v<package-version>/`. URIpack może dodać otoczkę
`packs/.../tree/`. Nie spłaszcza się paczki; rekord repozytorium wskazuje jej
rzeczywisty katalog. Katalog techniczny nie ustanawia tożsamości procesu.

### URP-005: weryfikacja paczki

Producent MUSI porównać paczkę z niezależnie wskazanymi obiektami Git, sprawdzić
profil i pełny zbiór plików, uruchomić oryginalne testy oraz sprawdzić faktycznie
zainstalowaną dystrybucję. Wszystkie zadeklarowane przypadki MUSZĄ się wykonać.
Pominięte testy, brak uruchomienia i błędy nie są sukcesem. Tożsamości przypadków,
parametryzacja i krotność MUSZĄ zgadzać się w źródle i instalacji; same liczby
nie dowodzą kompletności.

POA wymaga zgodności biblioteki, CLI, zainstalowanego npm i kontenera. Po
przygotowaniu przypiętych zależności budowa i instalacja odbywają się bez sieci.
Test kontenera używa nieuprzywilejowanego użytkownika, systemu plików tylko do
odczytu, ograniczeń zasobów i braku sekretów. Python wymaga instalacji wheel
bez pobierania zależności, oryginalnych testów i rejestracji natywnych bindings.
Kontener jest wymagany tylko wtedy, gdy deklaruje go profil lub środowisko.

### URP-006: URIpack i odzyskiwanie po błędzie

Producent MUSI utworzyć rzeczywisty plan URIpack związany ze źródłem, celem,
operacjami i digestami. Partia zapewnia pełne pokrycie mapowania repozytoriów
i unikalną własność URI. Przed wykonaniem odtwarza się oczekiwane plany z
przypiętych źródeł i ponownie odczytuje ich wejścia.

Guard MUSI niezależnie rozstrzygnąć admission, wymagane kontrole, lokalną
publikację artefaktu i completion. Zgoda na jedną paczkę nie obejmuje kolejnej.
Fikstura testowa nie zastępuje produkcyjnego Guard. Native Organism Guard export
i URIpack GuardBridge to różne kontrakty; ich zgodność wymaga integracji.

Niepewny wynik, w tym `MATERIALIZED_PENDING_COMPLETION`, zachowuje cel, próbę
i dowody. Następne efekty zatrzymuje się do niezależnego rozstrzygnięcia.
Inspekcja nie uprawnia do retry, usunięcia blokady ani ponownego wykonania.
Lokalny hash lub spójny łańcuch zdarzeń nie uwierzytelnia decyzji Guard.

### URP-007–008: dowody publikacji i wdrożenia

| Etap | Wymagany dowód | Zakres dowodu |
| --- | --- | --- |
| Struktura | Przypięty checker, komplet plików i lokalne hashe. | Zgodność paczki; bez autentyczności Git, zachowania i uprawnienia. |
| Źródła i zachowanie | Dokładny upstream, pełne testy, instalacja dystrybucji. | Zbadany artefakt; bez zgody na publikację. |
| Ekstrakcja | Chronione decyzje Guard i odczyt artefaktu z planu. | Ekstrakcja; bez utworzenia repozytorium, merge i wdrożenia. |
| Publikacja kodu | CI dokładnego HEAD, aktualnej bazy i wyniku merge; niezależna uwierzytelniona zgoda. | Opublikowany kod; bez produkcyjnego bindingu. |
| Wdrożenie | Świeży plan rzeczywistego celu i aktualne uprawnienie. | Zastosowanie planu; bez dowodu obsługi procesu. |
| Akceptacja produkcji | Niezależny odczyt rewizji, bindingu i oczekiwanego rezultatu. | Wyłącznie wskazany proces i środowisko. |

Przed utworzeniem lub publikacją repozytorium należy potwierdzić namespace,
dostęp i proces dostarczenia. Agent wytwarzający zmianę nie zatwierdza siebie
i nie wykonuje bezpośredniego merge. Domknięcie pochodzi z zewnętrznego receiptu;
nie tworzy się commitów zamykających tickety. Do akceptacji konsumentów zachowuje
się dotychczasowe źródła i bindingi. Rollback wskazuje znaną rewizję i własne
uprawnienie.

Automatyzacja wymaga zarejestrowanej Strategy i rzeczywistych executable
bindings. Opis standardu, gotowość kolejki, lease ani boolean `approved` nie
tworzą takiego procesu lub uprawnienia.

### URP-009–010: adopcja i rozwój

Konsument MUSI przypiąć repozytorium, pełną rewizję standardu, wersję i hash
`bundle.json`, a także sprawdzić każdy plik bundla. Dopuszczalna jest jawna
projekcja w `.governance/uriprocess/`. Nie wolno odkrywać sąsiedniego repozytorium
ani używać ruchomego fallbacku.

Zmiana wersji, schematów, testów i bundla należy do jednej materialnej zmiany.
Konsument aktualizuje pin w przeglądanej adopcji. Nowy profil wymaga rzeczywistego
przykładu źródłowego, dowodu zachowania oraz pozytywnych i negatywnych przypadków.
Stare wersje pozostają odtwarzalne.

Deklaracja adopcji, przypięte bajty, wywołanie w testach, konfiguracja chronionego
CI, wdrożenie i obserwowane wykonanie są osobnymi stanami. Lock z PR nie jest
niezależnym przypięciem polityki operatora; chronione CI musi otrzymać własny
zaufany pin przed egzekwowaniem standardu jako polityki.

## Referencyjny checker

`python3 -B operations/conformance.py --package /path/to/package` wymaga Python
3.11+, `jsonschema` 4.x i POSIX z `O_NOFOLLOW`. Odczytuje lokalne schematy i pliki;
nie importuje kodu paczki, nie pobiera URL-i ani nie uruchamia jej testów.
Sprawdza pliki, hashe, deklarowane tryby, obecność testów, URI i natywne metadane.
Limit wynosi 8 MiB na plik i 4096 wpisów drzewa. JSON z kodem 0 oznacza zgodność;
kod 2 i stabilna diagnostyka oznaczają odmowę. Producent oddzielnie skanuje
sekrety i weryfikuje licencje.

Udany wynik zachowuje `upstream_git_verified`, `behavior_verified`,
`guard_authenticated`, `execution_authority`, `publication_authority` i
`production_verified` jako `false`.

<!-- docs:section limitations -->
## Ograniczenia

Checker nie potwierdza upstream Git, testów zachowania, uprawnień i produkcji.
Spójnie przeliczona fałszywa kopia może przejść kontrolę lokalną; test pokazuje,
że nadal nie otrzymuje dowodu upstream. URP-005–008 wymagają osobnych obserwacji.
Odczyt całego drzewa nie jest atomowy; źródło i wykonanie wymagają niezmiennego
snapshotu lub kontrolowanej dzierżawy.

Adopcja dokumentacji nie ustanawia pełnej adopcji new-project, DSL, logs, CI
ani URIpack. Pierwsze udostępnienie źródeł standardu nie jest dowodem
niezależnego merge; taki profil wymaga osobnego potwierdzenia.

<!-- docs:section next_actions -->
## Zastosowanie

Przypiąć bundle w `subactor/uriprocess`, sprawdzić rzeczywiste paczki obu profili
i zachować testy upstream, instalacji oraz URIpack. Przed promocją do chronionej
polityki wdrożyć niezależny pin CI i zebrać dowód uruchomienia.
