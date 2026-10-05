# Kulturpool / OAI-PMH für Eligius

## Zweck und Betrieb

`/oai/` ist ein öffentlicher, ausschließlich lesender OAI-PMH-2.0-Endpoint für
ausdrücklich freigegebene Sammlungen. Das primäre Austauschformat ist EDM als
RDF/XML. Die Implementierung enthält keine sammlungsspezifischen Exportregeln.
Bestehende öffentliche Seiten, REST-, MCP-, WebMCP- und Nomisma-Schnittstellen
behalten ihre bisherigen Routen und Freigabekonzepte.

Alle Sammlungen starten mit `kulturpool_export_erlaubt=False`. Die neue
append-only Migration heißt `slg/migrations/0103_kulturpool_oai.py`; sie ergänzt
drei Sammlungsfelder und den MTOA-Index `(last_modified, obj_id)`. Sie löscht
keine Daten und ändert keine bestehenden Migrationen.

Vor der ersten Übernahme:

```powershell
python manage.py migrate
python manage.py sync_mtoa --slg <Sammlungs-ID>
python manage.py validate_kulturpool_export
python manage.py validate_kulturpool_export --slg <Sammlungs-ID> --strict
```

Die Migration ist im produktiven Datenbank-Deployment anzuwenden. Entwicklung
und Tests verwenden eine isolierte Datenbank; die Implementierungsprüfung hat
keine bestehenden Sammlungen automatisch freigegeben.

## Architekturprüfung und bestehende Felder

Analysiert wurden `slg/models.py`, `slg/signals.py`, `slg/mtoa_sync.py`,
`slg/management/commands/sync_mtoa.py`, Admin, öffentliche Services und
Serializer, URL-Konfiguration, `slg/nomisma_rdf.py` und die bestehenden Tests.

Der verbindliche Kontrollstatus ist:

| Modell | Bestehende Semantik |
| --- | --- |
| `Obj` | `workflow__name__iexact='kontrolliert'` |
| `Muenztyp` | `workflow__name__iexact='kontrolliert'` |
| `Slg` | Neue, unabhängige Freigabe `kulturpool_export_erlaubt=True` |

`Obj.freigabe` existiert, wird nach dem bestehenden öffentlichen Service
`slg/services/search.py` historisch aber nicht als Freigabestatus verwendet.
Der vorhandene Nomisma-Export verwendet ebenfalls den Workflow-Namen. Keine
Workflow-ID wird als Kontrollstatus festgeschrieben. Ein fehlender Workflow
gilt als nicht kontrolliert.

Die OAI-Regel lautet:

```text
Sammlung für Kulturpool freigegeben
AND Objekt kontrolliert
AND (Objekt ohne Typ OR zugeordneter Typ kontrolliert)
```

Der bestehende Nomisma-Export verlangt dagegen einen kontrollierten Typ und
hat eine eigene Variantenregel. Diese zusätzliche Einschränkung wird nicht
auf Kulturpool übertragen.

### Was MTOA tatsächlich liefert

`MuenztypObjektAnzeige.obj_id` ist ein indiziertes Integerfeld, kein Objekt-FK
und kein garantiert eindeutiges Feld. MTOA liefert bereits:

- `obj_id`, `invnr`, `objekttitel`, `objekttyp`, `herstellung`;
- `Slg`, `SlgTeil`, `typ`, `typlink`, `konkordanz`;
- `nominal`, `metall`, `mzstaette`, `region`, `muenzstand`, `reichskreis`;
- `datierung_von`, `datierung_bis`, `datierung_verbale`;
- `gewicht`, `durchmesser`, `stempelstellung`, `abnutzung`;
- `av_legende`, `rv_legende`, `av_bildtyp`, `rv_bildtyp`, Beizeichen,
  Bildränder, Schlagworte, Rand und `anmerkungen`;
- `personen_av`, `personen_rv`, `personen_sonstige`;
- `av_url`, `rv_url`, `thumbnail_av_url`, `thumbnail_rv_url`;
- `last_modified` und die vorhandenen FKs `slg_fk`, `slgteil_fk`, `typ_fk`,
  `nominal_fk`, `metall_fk`, `mzstaette_fk`, `region_fk`, `muenzstand_fk`,
  `objekttyp_fk`, `herstellung_fk`, `av_bildtyp_fk`, `rv_bildtyp_fk`.

`MtoaPerson` verbindet MTOA außerdem strukturiert mit `Person`,
`PersonFunktion` und der Angabe `appears_on_rev`. Personenstrings werden für
URI-Zuordnungen nicht geparst. Die bestehenden Rollen 1, 6 und 7 sind
Prägeherren, Rolle 2 bezeichnet eine dargestellte Person; dies entspricht den
vorhandenen MTOA-Hilfsmethoden und der Detaildarstellung.

Die alten `Obj.generate_mtoa_data()`-Daten enthalten bereits viele dieser
Anzeigewerte. Die aktive Synchronisierung benutzt den optimierten
`generate_mtoa_from_obj()` aus `sync_mtoa`, der zusätzlich Inventarnummer,
FKs und die Personen-Bridge pflegt. Der neue Export benutzt diese bestehende
Projektion, ohne sie neu zu konzipieren.

### Datenquellen im Export

Direkt aus MTOA kommen Inventarnummer, Titel bzw. Titelbestandteile, Datierung,
Material-/Nominal-/Münzstätten-/Objekttyp-/Herstellungslabels, Münztypbezeichnung,
Legenden, die bereits zusammengeführten Beschreibungen aus `av_bildtyp` /
`rv_bildtyp`, Beizeichen aus `av_beizeichen` / `rv_beizeichen`, Maße und
OAI-Datestamp. Die MTOA-Synchronisierung verwendet jeweils den Objektwert
mit Münztyp-Fallback und ersetzt bei Beizeichen bereits die Offizin-Platzhalter.
Die separaten Freitextfelder `Obj.avbeschr` / `rvbeschr` beziehungsweise
`Muenztyp.avbeschr` / `rvbeschr` werden für den OAI-Export nicht geladen.

Zusätzlich werden geladen:

- `Obj`, `Obj.Typ`, `Obj.Slg`: verbindliche Freigaben und Beziehungen;
- MTOA-Normdaten-FKs: `name_nom_id`, außerdem `Mzstaette.geonames` und
  vorhandene absolute `Mzstaette.ndpikmk`-URIs;
- `MtoaPerson` mit `Person` und Funktion: semantische Personenbeziehungen und
  externe Normdaten;
- `Muenztyp.link`, kontrollierte `Muenztyp.Konkordanz`-Einträge und
  `Obj_Ref.link`: strukturierte Typologieverweise;
- `Slg`: aktueller Sammlungsname und Rechte; `SlgTeil` bleibt ausschließlich
  für die bestehende Bild-URL-Erzeugung verfügbar und erscheint nicht als
  eigene Sammlungszugehörigkeit in den exportierten Metadaten.

Interne Anmerkungen, Bearbeiterdaten, `fmid`, Pakete und generische
`anmerkungen` werden nicht serialisiert. Technische Primärschlüssel werden
nur für stabile Ressourcen- und OAI-Identifikatoren verwendet.

## Module und Export-QuerySet

Die neue Schicht liegt unter `slg/oai/`:

| Datei | Aufgabe |
| --- | --- |
| `views.py` | Öffentlicher GET-/POST-Transport, XML-Content-Type |
| `service.py` | Verben, Argumentprüfung, Datumsfilter und Pagination |
| `querysets.py` | Freigaben auf Ursprungsmodellen und begrenzte Relation-Ladevorgänge |
| `edm.py` | EDM/RDF-Mapping, Titel, Normdaten, Bilder |
| `dc.py` | OAI-Dublin-Core aus derselben EDM-Repräsentation |
| `identifiers.py` | Stabile IDs, Sets, absolute öffentliche URIs |
| `readiness.py` | Getrennte Rechteprüfung pro Sammlung |
| `xml.py` | Offizielle Namespaces und XML-1.0-Textbereinigung |

Die Lesebasis ist MTOA. Korrelierte `Exists`-Abfragen überprüfen die
maßgeblichen Freigaben in `Obj`, `Muenztyp` und `Slg`. Die projizierte
Sammlung und der projizierte Typ müssen zur kanonischen Zuordnung passen;
veraltete Zuordnungen werden nicht ausgegeben. Verwaiste Zeilen, fehlende
Zeitstempel oder fehlende Sammlungs-FKs sind ebenfalls nicht exportierbar.
Bei mehreren MTOA-Zeilen für dasselbe Objekt wird nur die Zeile mit der
höchsten MTOA-ID verwendet; bestehende Duplikate werden nicht gelöscht.

`select_related` lädt Normdaten und Bildkonfiguration. `prefetch_related`
lädt Personen, Objektverweise und Typkonkordanzen. Da `obj_id` kein FK ist,
werden die kanonischen Objekte mit einer zusätzlichen, auf die jeweilige
Antwortseite begrenzten Abfrage geladen. Die Mapping-Schicht stellt keine
eigenen Einzelabfragen pro Datensatz an.

## OAI-PMH-Protokoll

Alle sechs Verben werden unterstützt:

| Verb | Argumente neben `verb` |
| --- | --- |
| `Identify` | keine |
| `ListMetadataFormats` | optional `identifier` |
| `ListSets` | optional, exklusiv `resumptionToken` |
| `ListIdentifiers` | `metadataPrefix`; optional `set`, `from`, `until`; alternativ exklusiv `resumptionToken` |
| `ListRecords` | wie `ListIdentifiers` |
| `GetRecord` | `metadataPrefix` und `identifier` |

`metadataPrefix=edm` liefert `rdf:RDF`. Daher ist der in
`ListMetadataFormats` angegebene `metadataNamespace` der RDF-Namespace; die
angegebene EDM-XSD hat ebenfalls diesen Zielnamespace.

Zusätzlich steht `oai_dc` zur Verfügung, weil OAI-PMH 2.0 unqualifiziertes
Dublin Core als Mindestformat verlangt. Es verwendet dieselben
Exportfreigaben und dieselbe Mapping-Grundlage; URIs erscheinen dort wegen
der einfacheren DC-Syntax als Textwerte.

GET und `application/x-www-form-urlencoded` POST sind ohne Login und ohne
CSRF-Token möglich. Beide sind rein lesend. Doppelte, unbekannte, fehlende,
leere oder zum Verb unzulässige Argumente werden geprüft; Tokens werden
separat validiert. Die View liefert `text/xml; charset=utf-8`.

OAI-Fehler kommen protokollgemäß im XML bei HTTP 200, darunter `badVerb`,
`badArgument`, `cannotDisseminateFormat`, `idDoesNotExist`, `noRecordsMatch`,
`noSetHierarchy` und `badResumptionToken`. Unbekannte und nicht freigegebene
Objekte haben dieselbe `idDoesNotExist`-Antwort. Unbekannte und private Sets
liefern keine Datensätze und keine Sammlungsnamen.

## Stabile Identifikatoren und Sets

OAI-Identifier:

```text
oai:eligius.donau-uni.ac.at:object:<Obj.pk>
```

Der Namespace ist separat konfigurierbar und darf nach dem ersten Harvest
nicht mehr geändert werden. Inventarnummern oder Sammlungsnamen beeinflussen
den technischen Identifier nicht.

Die öffentliche Objektseite wird mit der bestehenden Route `Objekt`
aufgelöst. Daraus entstehen:

```text
<öffentliche Basis>/objekt/<Obj.pk>/#providedCHO
<öffentliche Basis>/objekt/<Obj.pk>/#aggregation
```

Sammlungen haben bereits einen unveränderlichen Primärschlüssel, aber keinen
passenden stabilen Slug. Deshalb wird kein zusätzlich zu pflegender Slug
eingeführt. Das Set lautet `eligius:collection-<Slg.pk>`; `setName` ist der
aktuelle reale Sammlungsname. Umbenennungen ändern das Set nicht. Das
übergeordnete `set=eligius` umfasst alle freigegebenen Sammlungen.
`ListSets` listet ausschließlich freigegebene Sammlungen, auch wenn sie
noch keine exportfähigen Objekte enthalten.

## EDM-Mapping

Ein Objekt bleibt genau ein `edm:ProvidedCHO`.

| Quelle | EDM/DC-Ziel |
| --- | --- |
| `invnr` | `dc:identifier` |
| `objekttitel`; Fallback Nominal/Objekttyp + Prägeherren + Datierung | `dc:title` |
| Objekttyp und Nominal | `dc:type`, Label und vorhandene URI |
| Sammlung | `dcterms:isPartOf`; zusätzlich URI der Sammlungsseite und gültige `nomisma_collection_uri` |
| Verbale/numerische Datierung | `dcterms:temporal` |
| Material | `dcterms:medium` |
| Münzstätte und Region | `dcterms:spatial` |
| Herstellung, Typbezeichnung und Typologielinks | `dc:subject` |
| Personenrollen 1/6/7 | `dc:creator` |
| Dargestellte Personen (Rolle 2) | `dc:subject` |
| Übrige Personenrollen | `dc:contributor` |
| MTOA-Vorder-/Rückseitenbeschreibung, Beizeichen und Legenden | getrennt benannte `dc:description` |
| Gewicht, Durchmesser, Stempelstellung | `dcterms:extent` mit g, mm bzw. h |
| Digitale Bildrepräsentation | `edm:type=IMAGE` |

Fehlt ein beschreibender Titel vollständig, ist der stabile, sachliche
Fallback `Objekt <Inventarnummer>` bzw. `Objekt <Objekt-ID>` möglich. Die
Readiness-Prüfung meldet solche fehlenden beschreibenden Titel. Sie erfindet
keinen Münzherrn, kein Nominal und keine Datierung.

Die Aggregation verweist mit `edm:aggregatedCHO` auf das Kulturgut,
`edm:dataProvider` auf den Sammlungsnamen, `edm:provider` auf Eligius und
`edm:isShownAt` auf die öffentliche Objektseite. RDF/XML-Feldreihenfolgen
entsprechen der offiziellen EDM-XSD.

### Nomisma und andere Normdaten

Gültige HTTP(S)-URIs aus `name_nom_id` werden als `rdf:resource` ausgegeben.
Ein bloßer Identifier wie `ar` wird ausschließlich in einem ausdrücklich
als Nomisma-ID bezeichneten Feld zu `http://nomisma.org/id/ar` erweitert.
Andere externe IDs werden nicht pauschal in Nomisma-URIs verwandelt.

Zusätzlich zum lesbaren Label gibt es passende `skos:Concept`, `edm:Place`
oder `edm:Agent`-Kontextressourcen mit `skos:prefLabel`. Für Personen werden
vorhandene gültige URIs aus `DNB`, `VIAF`, `DB`, `OeBL` und `mmlo` erhalten.
Bekannte numerische `geonames`-IDs werden als Geonames-Ressourcen abgebildet;
`ndpikmk` wird nur bei einer bereits vorhandenen absoluten URI übernommen.
Fehlende oder syntaktisch ungültige URIs werden nicht erfunden.

### OCRE, CRRO, RPC und weitere Typologien

Alle gültigen URLs aus `Muenztyp.link`, kontrollierten
`Muenztyp.Konkordanz`-Einträgen und `Obj_Ref.link` erscheinen als
`dc:subject rdf:resource="…"`. Das gilt gleichermaßen für OCRE, CRRO, RPC,
PELLA, SCO oder andere hinterlegte HTTP(S)-Typologien. Es gibt keinen
Domain-Mappingblock, keine neue Typologietabelle und keine behaupteten
`skos:exactMatch`-Beziehungen. Nicht kontrollierte Konkordanztypen werden
nicht veröffentlicht.

## Bilder und getrennte Rechte

Die vorhandene Eigenschaft `MTOA.get_bild_urls` verwendet
`build_bild_urls_for_invnr()` mit Sammlung und Sammlungsteil und hat einen
Fallback auf vorhandene MTOA-Bild-URLs. Dieses Verfahren wird wiederverwendet.
Es werden keine alternativen Bildpfade oder Dateinamen geraten.

Vorder- und Rückseite ergeben je ein `edm:WebResource`. Die erste verfügbare
Ansicht steht in `edm:isShownBy`, weitere Ansichten in `edm:hasView`. Eine
vorhandene Vorschau steht in `edm:object`. Identische Bild-URLs werden
dedupliziert. Relative lokale Bildpfade werden mit der öffentlichen Basis
absolut gemacht. Ob die konstruierten URLs tatsächlich erreichbar sind,
wird beim Harvest nicht durch zusätzliche HTTP-Anfragen geprüft; das muss
vor der produktiven Übernahme separat überprüft werden.

`Slg.bildrechte_lizenz` ist bisher Freitext für die öffentliche Anzeige.
Dieser Text wird nicht als maschinenlesbare Lizenz interpretiert. Dafür
gibt es nun zwei bewusst getrennte, standardmäßig leere Felder:

| Feld | Verwendung |
| --- | --- |
| `kulturpool_rights_uri` | Bestätigte Rechte-URI der Bilddigitalisate; `edm:rights` an WebResources und Aggregation |
| `kulturpool_metadata_rights_uri` | Separat vereinbarte Metadatenrechte; `dc:rights` an der Aggregation |

Enthält `bildrechte_lizenz` bereits ausschließlich eine gültige HTTP(S)-URI,
kann sie als Bildrechte-Fallback dienen. Ein vorrangig konfiguriertes
`kulturpool_rights_uri` wird bevorzugt. Freitext oder ungültige Werte erzeugen
keine `edm:rights`-Angabe. Bildrechte werden nicht als Metadatenrechte
übernommen und Metadatenrechte nicht an Bilder geschrieben.

Es gibt keine vorausgesetzte CC-, CC0-, Public-Domain- oder andere Lizenz.
Unbekannte Rechte verhindern die Entwicklung nicht; OAI liefert dann XML
ohne diese Rechteaussage. **Das erfüllt noch nicht die vollständigen
Europeana/Kulturpool-Annahmeregeln:** Die Europeana-Schematron-Regeln verlangen
eine Bildrechte-URI an der Aggregation. XSD-Gültigkeit allein ist kein
Nachweis organisatorischer oder vollständiger ingestbezogener Bereitschaft.

Im bestehenden Adminbereich **Datenweitergabe / Nomisma und Kulturpool**
erscheinen Freigabe, Rechtefelder und ein sichtbarer Bereitschaftsstatus.
`validate_kulturpool_export --strict` soll vor produktiver Übernahme
erfolgreich sein. Organisatorisch benötigt werden die bestätigten Bildrechte,
die separat vereinbarten Metadatenrechte und die Bestätigung des konkreten
Kulturpool-Annahmeprofils je Sammlung. Die Rechteprüfung validiert URI-Syntax,
aber keine rechtsverbindliche Lizenzentscheidung oder entfernte URI-Inhalte.

## Inkrementelles Harvesting und Synchronisierung

Der OAI-Datestamp ist `MTOA.last_modified`. Antwortwerte sind UTC mit
Sekundengranularität (`YYYY-MM-DDThh:mm:ssZ`). `from` und `until` unterstützen
Tages- oder Sekundengranularität, bei gemeinsamer Angabe dieselbe Granularität.
Beide Grenzen sind inklusive, einschließlich DB-Mikrosekunden in der letzten
angeforderten Sekunde. Ungültige Daten, Zeitzonenvarianten und umgekehrte
Bereiche werden zurückgewiesen.

Die bestehenden Signals und die gemeinsame MTOA-Synchronisierung wurden
gezielt erweitert:

- Objekt-, Münztyp-, Sammlungs- und Sammlungsteiländerungen;
- Personen, Personenfunktionen, Objekt-/Typ-Personenzuordnungen einschließlich
  Entfernung und Wechsel des bisherigen Besitzers;
- Material, Nominal, Münzstätte, Region, Objekttyp, Herstellung, Workflow,
  Vorder-/Rückseitenbildtypen, Beizeichen und Offizinen;
- öffentliche Objekt-Typologieverweise und Typkonkordanzen;
- Bild-/Rechtekonfiguration über Sammlung und Sammlungsteil.

Die früheren Grenzen von 500 Objekten pro Münztyp bzw. 2000 pro Sammlung
wurden durch vollständige Verarbeitung in Batches von 500 IDs ersetzt.
Jeder gemeinsame MTOA-Sync läuft atomar einschließlich Personen-Bridge.
Es gibt kein zweites OAI-Zeitstempel- oder Historienmodell.

Django `QuerySet.update`, `bulk_update`, `bulk_create`, direkte SQL-Änderungen
und Dateiänderungen unter einer unveränderten Bild-URL senden keine
Modell-Signals. Solche Import-/Bildprozesse müssen anschließend den bestehenden
`sync_objs_to_mtoa()` bzw. `sync_mtoa --slg …` aufrufen. Ersetzte Bilddateien
sind ohne dieses explizite Sync nicht inkrementell erkennbar. Fehler im
bestehenden Auto-Sync werden protokolliert und müssen mit einem erneuten Sync
behoben werden. Nach Änderungen an Mapping/öffentlicher Basis-URL ist ebenfalls
ein Sync beziehungsweise Vollharvest erforderlich.

## Entzug der Freigabe und gelöschte Records

`Identify` meldet **`deletedRecord=no`**. Die vorhandene `ObjektAenderung`-
Tabelle beschreibt eingereichte Änderungsvorschläge, keine vollständige
Historie publizierter OAI-Records; außerdem werden diese Einträge beim
Löschen des Objekts kaskadiert. Damit ist weder `transient` noch `persistent`
verlässlich implementierbar. Eine neue Historientabelle wird in Phase 1
nicht eingeführt.

Beim Entzug der Objekt-/Typkontrolle, Verschieben in eine andere Sammlung,
Deaktivieren der Sammlungsfreigabe oder Löschen verschwindet der betreffende
Record. Ein inkrementeller Harvest erkennt diesen Entzug nicht zuverlässig.
Kulturpool muss in diesen Fällen einen **vollständigen Abgleich mit Entfernung
der inzwischen fehlenden Identifier** durchführen; bloß erneutes Hinzufügen
der noch vorhandenen Records reicht nicht. Bei deaktivierter Sammlung ist
auch deren Set nicht mehr in `ListSets` enthalten.

## Pagination, Performance und Caching

Standardmäßig werden 200 Records pro Antwort geliefert, konfigurierbar bis
maximal 500. Alle Listen einschließlich `ListSets` können einen
`resumptionToken` liefern. Pro Seite werden höchstens Seitengröße + 1 Zeilen
geladen. Es werden keine großen Ergebnislisten in Python materialisiert und
keine tiefen OFFSET-Seiten verwendet.

Der Django-signierte, zeitlich begrenzte Token enthält Version, Verb,
Metadatenformat, Set, Datumsgrenzen, letzten Objekt-/Sammlungs-PK, ursprüngliche
PK-Obergrenze, Seitengröße und Cursor. Signatur, Datentypen, Format und
Verbbindung werden geprüft; keine Pickle- oder Python-Objekt-Deserialisierung.
Tokens sind standardmäßig 24 Stunden gültig. Wiederholungen funktionieren;
die letzte Seite einer Fortsetzung liefert einen leeren Token.

Neue Objekte oberhalb der ursprünglichen PK-Obergrenze gelangen erst in den
nächsten Harvest. Ein Token ist kein Datenbanksnapshot: während einer Folge
geänderte oder entzogene Objekte können die Treffermenge verändern. Der nächste
inkrementelle Harvest soll am Zeitbeginn des vorherigen Laufs mit mindestens
einer Sekunde Überlappung ansetzen; Identifier deduplizieren. Abgelaufene Tokens
oder komplett verschwundene Fortsetzungsseiten erfordern einen Neustart.

Im SQL-Budget-Test benötigen `ListRecords` für 1 und 31 Records jeweils
**6 Abfragen**. `ListIdentifiers` lädt nur Headerfelder. Indizes der vorhandenen
FKs, von `obj_id` und der neue Datestamp-Index unterstützen die Abfragen.
Ein Lasttest mit hunderttausenden Records auf dem produktiven MySQL-System
steht noch aus; die Query-Anzahlprüfung ersetzt diesen nicht.

Die Antworten verwenden `Cache-Control: no-store`. Es gibt bewusst keine
neue Cache-Schicht, damit entzogene Freigaben und neue Datestamps unmittelbar
sichtbar werden. Kein öffentliches Debug-Endpoint wird angelegt.

## Konfiguration

| Einstellung / Umgebungsvariable | Standard / Bedeutung |
| --- | --- |
| `ELIGIUS_PUBLIC_BASE_URL` | Vorhandene öffentliche Basis; leer bedeutet absolute URLs aus dem Request |
| `ELIGIUS_OAI_IDENTIFIER_NAMESPACE` | `eligius.donau-uni.ac.at`; nach Veröffentlichung unverändert lassen |
| `ELIGIUS_OAI_REPOSITORY_NAME` | `Eligius – Kulturpool` |
| `ELIGIUS_OAI_ADMIN_EMAIL` | Vorhandener Kontakt aus dem Impressum, separat konfigurierbar |
| `ELIGIUS_OAI_PAGE_SIZE` | `200`, Laufzeitbegrenzung auf 1–500 |
| `ELIGIUS_OAI_TOKEN_MAX_AGE` | `86400` Sekunden |

In Produktion die kanonische HTTPS-Basis und einen dauerhaften
`DJANGO_SECRET_KEY` für Signaturen konfigurieren. Ein Wechsel des Secrets
invalidiert ausstehende Tokens.

## Bereitschaftsprüfung

`python manage.py validate_kulturpool_export` prüft ausschließlich freigegebene
Sammlungen. Optional begrenzt `--slg <ID>` die Ausgabe. Es meldet pro Sammlung:

- grundsätzlich exportfähige und über OAI tatsächlich verfügbare Objekte;
- Ausschlüsse wegen fehlender Objekt- oder Typkontrolle;
- fehlende/veraltete MTOA-Zeilen;
- fehlende Bilder, beschreibende Titel, externe Normdaten und Rechtekonfiguration.

`--strict` ergibt bei fehlenden/ungültigen Rechten, Bildern, beschreibenden
Titeln oder Projektionen einen Fehlerstatus. Fehlende Normdaten werden als
Qualitätshinweis gezählt, sind allein kein harter Fehler. Das Kommando ändert
keine Daten und ruft keine entfernten Bild- oder Normdaten-URLs ab.

## Beispielabfragen

```text
/oai/?verb=Identify
/oai/?verb=ListMetadataFormats
/oai/?verb=ListSets
/oai/?verb=ListRecords&metadataPrefix=edm
/oai/?verb=ListRecords&metadataPrefix=edm&set=eligius:collection-<Slg-ID>
/oai/?verb=ListIdentifiers&metadataPrefix=edm&set=eligius
/oai/?verb=GetRecord&metadataPrefix=edm&identifier=oai:eligius.donau-uni.ac.at:object:<Obj-ID>
/oai/?verb=ListRecords&metadataPrefix=edm&from=2026-10-01&until=2026-10-05
/oai/?verb=ListRecords&metadataPrefix=edm&from=2026-10-05T00:00:00Z
/oai/?verb=ListRecords&resumptionToken=<URL-kodierter-Token>
```

Tokenanfragen dürfen neben `verb` keine weiteren Argumente enthalten.
Identifier, Set und Token im HTTP-Client als Parameter URL-kodieren.

## Verifikation und bekannte Grenzen

```powershell
.\.venv\Scripts\python.exe manage.py test slg.test_oai --settings=djangoproject.test_settings
.\.venv\Scripts\python.exe manage.py test slg --settings=djangoproject.test_settings
.\.venv\Scripts\python.exe manage.py check --settings=djangoproject.test_settings
```

Am 5. Oktober 2026 wurden 46 neue Tests erfolgreich ausgeführt. Sie prüfen
Protokollverben, GET/POST, Argumentfehler, alle fünf Freigabefälle, stabile
Identifier, Sets, Tages-/Sekundengrenzen, Tokenfortsetzungen und Manipulation,
XML/RDF-Semantik, URI-Mapping, zusammengeführte MTOA-Beschreibungen und
Beizeichen mit Offizin-Ersetzung, das Weglassen der Sammlungsteil-Zugehörigkeit,
Bild-/Rechtetrennung, Synchronisierung und
konstante Abfragezahl. Die Migration wurde zusätzlich gegen den historischen
0102-Modellzustand auf einer isolierten SQLite-Datenbank angewandt: bestehende
Sammlung erhalten, Freigabe False, Rechte leer, Index vorhanden.

Zusätzlich wurden Beispielantworten mit und ohne konfigurierte Rechte gegen
die offizielle EDM-XSD und Antworten aller sechs Verben, beider Formate,
Pagination und Fehler gegen die offizielle OAI-XSD geprüft. Dafür wurde lokal
`lxml` verwendet; der produktive Endpoint benötigt nur Django und die bereits
vorhandenen Standard-/Projektbibliotheken. Die vollständigen
Europeana-Schematron- und Kulturpool-Annahmeregeln sind damit nicht behauptet.

Die vorhandene Gesamtsuite enthält sieben bereits im unveränderten Git-Stand
reproduzierbare Fehler: drei Nomisma-Tests scheitern am bestehenden ORM-Lookup
`obj_ref_set__nach` (Django-Filtername wäre `obj_ref__nach`); vier
`ObjSaveTests` besitzen keine Fixtures für die bestehenden Default-FKs.
Diese separaten Probleme wurden im Rahmen des OAI-Features nicht verändert.
Die übrigen bisherigen Tests einschließlich MCP/WebMCP laufen erfolgreich.
Die abschließende Gesamtsuite umfasste 133 Tests: 126 bestanden, dieselben
sieben bereits vorher vorhandenen Fehler blieben bestehen. Der unveränderte
Git-Stand umfasste 87 Tests mit denselben sieben Fehlern.

Die portable Testkonfiguration überspringt die alten Migrationen. Deshalb
ersetzt sie keinen MySQL-Deploymenttest; der neue Migrationsschritt wurde
gesondert geprüft. Auf der bestehenden Produktivdatenbank wurden keine
Migrationen oder Lasttests ausgeführt.

## Offizielle Referenzen

- [OAI-PMH 2.0](https://www.openarchives.org/OAI/openarchivesprotocol.html)
- [OAI-PMH XML Schema](https://www.openarchives.org/OAI/2.0/OAI-PMH.xsd)
- [Europeana EDM-Dokumentation](https://pro.europeana.eu/index.php/page/edm-documentation)
- [EDM XML Schema](https://www.europeana.eu/schemas/edm/EDM.xsd)
