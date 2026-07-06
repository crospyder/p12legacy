# P12 Legacy Converter

Windows GUI alat za konverziju `.p12` / `.pfx` certifikata u legacy PFX format kompatibilniji sa starijim Windows sustavima, posebno Windows Server 2012.

## Namjena

Problem koji alat rješava:

- moderni `.p12` / `.pfx` certifikati često koriste novije PKCS#12 algoritme
- stariji Windows Server 2012 wizard zna javiti da je lozinka kriva iako je ispravna
- alat napravi legacy `.pfx` koristeći OpenSSL legacy provider

## Funkcionalnosti

- grafičko sučelje
- dodavanje jednog ili više certifikata
- zasebna lozinka po certifikatu
- odabir output foldera
- generiranje `*.legacy.pfx`
- privremeni PEM ide u `%TEMP%` i automatski se briše
- ne dira sistemski PATH
- footer: `Izradio Neven Pausić / Spine ICT Solutions d.o.o. 2026`

## Portable distribucija

Preporučena struktura release foldera:

```text
P12LegacyConverter\
├── P12LegacyConverter.exe
└── openssl\
    ├── openssl.exe
    ├── legacy.dll
    ├── libcrypto-3-x64.dll
    └── libssl-3-x64.dll
```

Aplikacija prvo traži OpenSSL u lokalnom `openssl` folderu, zatim fallback na sistemske OpenSSL putanje.

## Build

Na Windows računalu s instaliranim Pythonom:

```cmd
build.bat
```

Output:

```text
dist\P12LegacyConverter\P12LegacyConverter.exe
```

Nakon builda u `dist\P12LegacyConverter\` ručno dodati portable OpenSSL folder.

## Napomena

Certifikati, `.p12`, `.pfx`, `.pem` i OpenSSL runtime nisu namijenjeni commitu u git repo. Zato su izignorirani kroz `.gitignore`.
