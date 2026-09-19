# Wellmanifest URIprocess

Standard wytwarzania, weryfikacji i dostarczania pakietów procesów identyfikowanych
przez URI. HOME `wellmanifest`, SHAPE `domain_pack`.

- [Standard 0.1.0](docs/information/uriprocess-standard.md)
- [Indeks dokumentacji](docs/README.md)
- [Polityka maszynowa](policy.json)
- [Schematy dwóch profili i pochodzenia](schemas/package.schema.json)
- [Referencyjna kontrola zgodności](operations/conformance.py)
- [Standard komplementarny wykonawczy: wellmanifest/taskand](https://github.com/wellmanifest/taskand)

---

## 🔗 Komplementarność ze standardem wellmanifest/taskand

Standard `wellmanifest/uriprocess` definiuje **fazę wytwórczą (Manufacturing & Packaging)** w architekturze procesów URI:
- Odpowiada za deterministyczne pakowanie kodu z zewnętrznych repozytoriów Git, niezmienność proweniencji (`provenance.json`) i sumy kontrolne plików (`bundle.json`).
- Wyprodukowane i zatwierdzone pakiety `uriprocess` stanowią wejście do standardu wykonawczego [wellmanifest/taskand](https://github.com/wellmanifest/taskand), który zarządza kapsułą (`capsule.yaml`), uprawnieniami (`grants.yaml`), kwalifikacją w Cyfrowym Bliźniaku (bramki A/B) oraz orkiestracją wykonania.

---

Profile: POA/Node oraz natywny konektor Pythona. Kontrola jest tylko do odczytu;
nie wykonuje procesów, testów pakietu ani operacji Guard.

```bash
make test
python3 operations/conformance.py --package /path/to/package
```

Python 3.11+ oraz `jsonschema` 4.x są wymagane do kontroli. Instalacja zależności
należy do środowiska weryfikującego; checker niczego nie pobiera. `bundle.json`
wylicza dokładne pliki do przypiętej adopcji. Runtime i adopcja projektu:
[subactor/uriprocess](https://github.com/subactor/uriprocess).
