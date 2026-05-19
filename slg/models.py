from django import forms
from django.conf import settings
from django.db import models
from datetime import datetime
from django.db.models.fields import related
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from django.contrib import admin
from model_clone import CloneMixin
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.text import slugify




# Create your models here.
class FeedbackKategorie(models.Model):
	name = models.CharField(max_length=200, verbose_name='Name')

class Feedback(models.Model):
	name = models.CharField(max_length=200, verbose_name='Name')
	email = models.EmailField(max_length=254)
	kategorie = models.ForeignKey("FeedbackKategorie", verbose_name="Kategorie", on_delete=models.CASCADE)
	beschreibung = models.TextField(verbose_name='Beschreibung', blank=True)
	link = models.CharField(max_length=200, verbose_name='Link')
	erledigt = models.BooleanField(verbose_name='erledigt')

class Slgsart(models.Model):
	name = models.CharField(max_length=200, verbose_name='Sammlungsart')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Sammlungsarten"

class SlgKategorie(models.Model):
	name = models.CharField(max_length=100)
	beschreibung = models.TextField(blank=True, null=True)
	
	def __str__(self):
		return self.name
	
	class Meta:
		verbose_name = "Sammlungskategorie"
		verbose_name_plural = "Sammlungskategorien"

class Slg(models.Model):
	name = models.CharField(max_length=200, verbose_name='Sammlung')
	#art = models.ForeignKey("Slgsart", verbose_name="Art", on_delete=models.CASCADE)
	beschreibung = models.TextField(verbose_name='Beschreibung', blank=True)
	bildrechte_lizenz = models.TextField(verbose_name='Copyrightlizenz der Bilder', blank=True)
	nomisma_export_erlaubt = models.BooleanField(default=False, verbose_name='Nomisma-Export erlauben')
	nomisma_collection_uri = models.URLField(max_length=250, blank=True, verbose_name='Nomisma Collection URI')
	created_at = models.DateTimeField(default=datetime.now, blank=True, null=True)
	bildurl = models.CharField(max_length=250, blank=True, null=True, verbose_name='Url zum Bilderverzeichnis')
	cover = models.CharField(max_length=250, verbose_name='Coverbild-Url', blank=True)
	bild_endung_av = models.CharField(max_length=10, default='a00', verbose_name='Endung Vorderseite')
	bild_endung_rv = models.CharField(max_length=10, default='r00', verbose_name='Endung Rückseite')
	entferne_zeichen = models.CharField(max_length=10, blank=True, null=True, verbose_name='Zu entfernende Zeichen hinsichtlich der Abb.')
	bilder_lokal = models.BooleanField(default=False, verbose_name='Bilder lokal auf Server speichern')
	lokaler_ordnername = models.CharField(max_length=200, blank=True, null=True, verbose_name='Lokaler Ordnername (optional)')
	kategorie = models.ForeignKey(
		SlgKategorie, 
		on_delete=models.SET_NULL, 
		null=True, 
		blank=True,
		related_name='sammlungen'
	)

	def get_absolute_url(self):
		return reverse("Sammlung", kwargs={"id": self.id})

	def __str__(self):
		return self.name
	
	class Meta:
		verbose_name_plural = "Sammlungen"

class SlgTeil(models.Model):
	name = models.CharField(max_length=200, verbose_name='Sammlungsteil')
	idfk_Slg_SlgTeil = models.ForeignKey('Slg', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Sammlungsteil')
	bildurl = models.CharField(max_length=250, blank=True, null=True)
	bild_endung_av = models.CharField(max_length=10, blank=True, null=True, default='a00', verbose_name='Endung Vorderseite')
	bild_endung_rv = models.CharField(max_length=10, blank=True, null=True, default='r00', verbose_name='Endung Rückseite')
	entferne_zeichen = models.CharField(max_length=10, blank=True, null=True, verbose_name='Zu entfernende Zeichen hinsichtlich der Abb.')
	bilder_lokal = models.BooleanField(default=False, verbose_name='Bilder lokal auf Server speichern')
	lokaler_unterordner = models.CharField(max_length=200, blank=True, null=True, verbose_name='Lokaler Unterordner (optional)')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Sammlungsteile"
		ordering = ['name']

class Herstellung(models.Model):
	name = models.CharField(max_length=200)
	name_nom_id = models.CharField(max_length=200, blank=True, verbose_name='Nomisma ID')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Herstellungsarten"


class SlgInformation(models.Model):
	dat_von = models.IntegerField(blank=True, null=True, verbose_name='Datierung von')
	dat_bis = models.IntegerField(blank=True, null=True, verbose_name='Datierung bis')
	dat_verb = models.CharField(max_length=100, blank=True, null=True, verbose_name='Datierung verbale')
	Slg = models.ForeignKey('Slg', blank=True, null=True, on_delete=models.CASCADE)
	person = models.ManyToManyField('Person', blank=True, verbose_name = ("Person/Organisation"))
	raw_personen = models.TextField(blank=True, verbose_name='Personen')
	information = models.TextField(blank=True, verbose_name='Information')
	name = models.CharField(max_length=100, blank=True, null=True, verbose_name='Kurzbeschreibung')
	# im Model SlgInformation_Ref werden die Zitate abgespeichert
	objekte = models.ManyToManyField('Obj', blank=True, verbose_name = ("Objekte"))
	
	# NEU: Schlagworte für Ereignisse
	schlagworte = models.ManyToManyField('EreignisSchlagwort', through='SlgInformationSchlagwort', verbose_name = ("Schlagworte"))
	raw_schlagworte = models.TextField(blank=True, verbose_name='Schlagworte')
	
	
	def get_dat_verb(self):
		if self.dat_von < self.dat_bis and self.dat_bis > 0:
			result = str(self.dat_von) + "-" + str(self.dat_bis)
			if self.dat_von < 492:
				result = result + " n. Chr."
			return result
		elif self.dat_von < self.dat_bis and self.dat_bis < 0:
			result = str(abs(self.dat_von)) + "-" + str(abs(self.dat_bis)) + " v. Chr."
			return result
		elif self.dat_von == self.dat_bis and self.dat_von < 0:
			result = str(abs(self.dat_von)) + " v. Chr."
			return result
		elif self.dat_von == self.dat_bis and self.dat_von > 0:
			result = str(self.dat_von)
			if self.dat_von < 492:
				result = result + " n. Chr."
			return result

	def save(self, *args, **kwargs):
		if self.dat_verb is None and self.dat_bis is not None and self.dat_von is not None:
			self.dat_verb = self.get_dat_verb()
		super(SlgInformation, self).save(*args, **kwargs)

	def __str__(self):
		# result = self.information
		# if self.dat_verb is not None:
		#     result = result + " [" + self.dat_verb + "]"

		# if self.beschreibung != "":
		#     result = result + " - " + self.beschreibung

		return ""

	class Meta:
		ordering = ('-dat_von','dat_bis',)
		verbose_name = "Ereignis"
		verbose_name_plural = "Ereignisse"

	def clean(self):
		super().clean()
		if self.dat_von is not None and self.dat_bis is not None:
			if self.dat_von > self.dat_bis:
				raise ValidationError({
					'dat_von': 'Das "Von"-Datum darf nicht größer sein als das "Bis"-Datum.',
					'dat_bis': 'Das "Bis"-Datum darf nicht kleiner sein als das "Von"-Datum.'
				})

class Datierung(models.Model):
	ereignis = models.ForeignKey(SlgInformation, on_delete=models.CASCADE)
	jahr_start = models.IntegerField(null=True, blank=True)
	jahr_ende = models.IntegerField(null=True, blank=True)
	monat_von = models.IntegerField(null=True, blank=True)
	monat_bis = models.IntegerField(null=True, blank=True)
	tag_von = models.IntegerField(null=True, blank=True)
	tag_bis = models.IntegerField(null=True, blank=True)
	zusaetzliche_beschreibung = models.CharField(max_length=200, null=True, blank=True)
	zitat = models.ForeignKey('Ref', on_delete=models.CASCADE, null=True, blank=True)
	verweis = models.CharField(max_length=75, null=True, blank=True,)
	unsicher = models.BooleanField(default=False)
	gesamterzeitraum = models.BooleanField(default=False)


	
	
	
class Person(models.Model):
	name = models.CharField(max_length=200, verbose_name='Person/Organisation')
	name_nom_id = models.CharField(max_length=200, blank=True, verbose_name='Nomisma ID')
	beschreibung = models.CharField(max_length=200, blank=True, verbose_name='Kurzbeschreibung')
	zeichen = models.CharField(max_length=200, blank=True, verbose_name='Zeichen/Signatur')
	dat_geboren = models.IntegerField(blank=True, null=True, verbose_name='Geboren im Jahr')
	dat_gestorben = models.IntegerField(blank=True, null=True, verbose_name='Gestorben im Jahr')
	dat_verb = models.CharField(max_length=100, blank=True, null=True, verbose_name='Lebensdaten verbale')
	Zisterzienserlexikon = models.URLField(max_length=255, blank=True, null=True, verbose_name='URL (Zisterzienserlexikon)')
	Benediktinerlexikon = models.URLField(max_length=255, blank=True, null=True, verbose_name='URL (Benediktinerlexikon)')
	WikiDe = models.URLField(max_length=255, blank=True, null=True, verbose_name='URL (dt. Wiki)')
	WikiEn = models.URLField(max_length=255, blank=True, null=True, verbose_name='URL (eng. Wiki)')
	GeschichteWikiWien = models.URLField(max_length=255, blank=True, null=True, verbose_name='URL (WienGeschichteWiki)')
	BiographiePortal = models.URLField(max_length=255, blank=True, null=True, verbose_name='URL (Biographie-Portal)')
	DeutscheDigitaleBib = models.URLField(max_length=255, blank=True, null=True, verbose_name='URL (DDB Deutsche Digitale Bibliothek)')
	DNB = models.URLField(max_length=255, blank=True, null=True, verbose_name='URL (GND/DNB Deutsche National Bibliothek)')
	VIAF = models.URLField(max_length=255, blank=True, null=True, verbose_name='URL (VIAF)')
	DB = models.URLField(max_length=255, blank=True, null=True, verbose_name='URL (Deutsche Biographie)')
	OeBL = models.URLField(max_length=255, blank=True, null=True, verbose_name='URL (Österreich. Biographisches Lexikon)')
	mmlo = models.URLField(max_length=255, blank=True, null=True, verbose_name='URL (Biographisches Lexikon der Münzmeister und Wardeine, Stempelschneider und Medailleure)')
	
	def get_dat_verb(self):
		if self.dat_geboren < self.dat_gestorben and self.dat_gestorben > 0:
			result = str(self.dat_geboren) + "-" + str(self.dat_gestorben)
			if self.dat_geboren < 492:
				result = result + " n. Chr."
			return result
		elif self.dat_geboren < self.dat_gestorben and self.dat_gestorben < 0:
			result = str(abs(self.dat_geboren)) + "-" + str(abs(self.dat_gestorben)) + " v. Chr."
			return result
		elif self.dat_geboren == self.dat_gestorben and self.dat_geboren < 0:
			result = str(abs(self.dat_geboren)) + " v. Chr."
			return result
		elif self.dat_geboren == self.dat_gestorben and self.dat_geboren > 0:
			result = str(self.dat_geboren)
			if self.dat_geboren < 492:
				result = result + " n. Chr."
			return result

	def save(self, *args, **kwargs):
		if self.dat_verb is None and self.dat_gestorben is not None and self.dat_geboren is not None:
			self.dat_verb = self.get_dat_verb()
		super(Person, self).save(*args, **kwargs)

	def __str__(self):
		result = self.name
		if self.dat_verb is not None:
			result = result + " [" + self.dat_verb + "]"

		if self.beschreibung != "":
			result = result + " - " + self.beschreibung

		return result

	class Meta:
		ordering = ('name',)
		verbose_name_plural = "Personen/Organisationen"

class PersonFunktion(models.Model):
	name = models.CharField(max_length=200, verbose_name='Funktion')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Personenrollen"
		ordering = ['name']

class Ref(models.Model):
	zitat = models.CharField(max_length=200, blank=True, verbose_name='Zitat')
	abk = models.CharField(max_length=30, blank=True, verbose_name='Abkürzung')
	name_nom_id = models.CharField(max_length=200, blank=True, verbose_name='Nomisma ID')
	
	
	def __str__(self):
		return self.abk
	class Meta:
		ordering = ('abk',)
		verbose_name_plural = "Referenzen"


class Bemerkung(models.Model):
	beschr = models.TextField(blank=True, verbose_name='Bemerkung')
	idfk_Obj = models.ForeignKey('Ref', on_delete=models.CASCADE)
	
	def __str__(self):
		return self.beschr

class Muenzstand(models.Model):
	name = models.CharField(max_length=200, verbose_name='Münzstand')
	
	# name_nom_id = models.CharField(max_length=200, blank=True, verbose_name='Nomisma ID')
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Münzstände"
		ordering = ('name',)

class Nominal(models.Model):
	name = models.CharField(max_length=200, verbose_name='Nominal')
	name_nom_id = models.CharField(max_length=200, blank=True, verbose_name='Nomisma ID')
	material = models.ForeignKey('Metall', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Material')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Nominalien"
		ordering = ('name',)

class Region(models.Model):
	name = models.CharField(max_length=200, verbose_name='Region')
	name_nom_id = models.CharField(max_length=200, blank=True, verbose_name='Nomisma ID')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Regionen"
		ordering = ('name',)

class Mzstaette(models.Model):
	name = models.CharField(max_length=200, verbose_name='Münzstätte', blank=True, null=True, unique=True)
	name_nom_id = models.CharField(max_length=200, blank=True, null=True, verbose_name='Nomisma ID')
	ndpikmk = models.CharField(max_length=200, blank=True, null=True, verbose_name='NDP-IKMK')
	geonames = models.CharField(max_length=200, blank=True, null=True, verbose_name='Geonames ID')
	region = models.ForeignKey('Region', blank=True, null=True, on_delete=models.CASCADE, verbose_name='Region')
	zeichen = models.CharField(max_length=100, blank=True, null=True, verbose_name='Zeichen')
	lat = models.FloatField(blank=True, null=True, verbose_name='Breitengrad')
	long = models.FloatField(blank=True, null=True, verbose_name='Längengrad')
	
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Münzstätten"
		ordering = ('name',)


class Obj_Person(models.Model):
	idfk_Obj = models.ForeignKey('Obj', on_delete=models.CASCADE)
	idfk_Person = models.ForeignKey('Person', on_delete=models.CASCADE, verbose_name='Name')
	idfk_PersonFunktion = models.ForeignKey('PersonFunktion', on_delete=models.CASCADE, verbose_name='Personenrolle')
	appears_on_rev = models.BooleanField(verbose_name='am Revers')
	
	def __str__(self):
		return ""
	class Meta:
		verbose_name = "Person"
		verbose_name_plural = "Personen"
		ordering = ('idfk_PersonFunktion',)
		unique_together = ('idfk_Obj', 'idfk_Person', 'idfk_PersonFunktion', 'appears_on_rev')

class Mztyp_Person(models.Model):
	Mztyp = models.ForeignKey('Muenztyp', on_delete=models.CASCADE)
	idfk_Person = models.ForeignKey('Person', on_delete=models.CASCADE, verbose_name='Name')
	idfk_PersonFunktion = models.ForeignKey('PersonFunktion', on_delete=models.CASCADE, verbose_name='Personenrolle')
	appears_on_rev = models.BooleanField(verbose_name='am Revers')
	
	def __str__(self):
		return ""
	class Meta:
		verbose_name = "Person"
		verbose_name_plural = "Personen"
		ordering = ('idfk_PersonFunktion',)
		unique_together = ('Mztyp', 'idfk_Person', 'idfk_PersonFunktion', 'appears_on_rev')
		indexes = [
			models.Index(fields=['Mztyp', 'idfk_Person']),           # KORRIGIERT: Django-Feldnamen
			models.Index(fields=['Mztyp', 'idfk_PersonFunktion']),   # KORRIGIERT: Django-Feldnamen
		]

class KatalogPerson(models.Model):
	katalog = models.ForeignKey('Katalog', on_delete=models.CASCADE, related_name='sammler')
	person = models.ForeignKey('Person', on_delete=models.CASCADE, verbose_name='Name')
	personfunktion = models.ForeignKey('PersonFunktion', on_delete=models.CASCADE, verbose_name='Personenrolle')
	
	def __str__(self):
		return ""
	class Meta:
		verbose_name = "Person"
		verbose_name_plural = "Personen"
		ordering = ('personfunktion',)
		unique_together = ('katalog', 'person', 'personfunktion',)

class Variantenbeschr(models.Model):
	name = models.CharField(max_length=200, verbose_name='Beschreibung')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Varianten-Beschreibungen"
		ordering = ['name']

class Faelschung(models.Model):
	name = models.CharField(max_length=200, verbose_name='Fälschung')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Fälschungen"
		ordering = ['name']
		
class Metall(models.Model):
	name = models.CharField(max_length=200, verbose_name='Metall')
	name_nom_id = models.CharField(max_length=200, blank=True, verbose_name='Nomisma ID')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Metalle"
		ordering = ['name']

class Schlagwort(models.Model):
	name = models.CharField(max_length=200, verbose_name='Schlagwort')
	name_nom_id = models.CharField(max_length=200, blank=True, verbose_name='Nomisma ID')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Schlagworte"
		ordering = ['name']

class KatSchlagwort(models.Model):
	name = models.CharField(max_length=200, verbose_name='Schlagwort')
	name_nom_id = models.CharField(max_length=200, blank=True, verbose_name='Nomisma ID')
	synonyme = models.TextField(blank=True, null=True,verbose_name='Synonyme')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Schlagworte"
		ordering = ['name']

class KatalogSchlagwort(models.Model):
	
	katalog = models.ForeignKey('Katalog', on_delete=models.CASCADE)
	katschlagwort = models.ForeignKey('KatSchlagwort', on_delete=models.CASCADE, verbose_name='Schlagwort')

	def __str__(self):
		return self.katschlagwort.name
	class Meta:
		verbose_name_plural = "Verschlagwortung"
		unique_together = ['katalog','katschlagwort']
		ordering=['katschlagwort']

class Objekttyp(models.Model):
	name = models.CharField(max_length=200, verbose_name='Name')
	name_nom_id = models.CharField(max_length=200, blank=True, verbose_name='Nomisma ID')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Objekttypen"
		ordering = ['name']

class AvBildtyp_Schlagwort(models.Model):
	
	avbildtyp = models.ForeignKey('AvBildtyp', on_delete=models.CASCADE)
	schlagwort = models.ForeignKey('Schlagwort', on_delete=models.CASCADE, verbose_name='Schlagwort')

	def __str__(self):
		return self.schlagwort.name
	class Meta:
		verbose_name_plural = "AvBildtyp-Schlagworte"
		unique_together = ['avbildtyp','schlagwort']

class RvBildtyp_Schlagwort(models.Model):
	
	rvbildtyp = models.ForeignKey('RvBildtyp', on_delete=models.CASCADE)
	schlagwort = models.ForeignKey('Schlagwort', on_delete=models.CASCADE, verbose_name='Schlagwort')

	def __str__(self):
		return ""
	class Meta:
		verbose_name_plural = "RvBildtyp-Schlagworte"
		unique_together = ['rvbildtyp','schlagwort']
		
class Mztyp_Schlagwort(models.Model):
	
	mztyp = models.ForeignKey('Muenztyp', on_delete=models.CASCADE)
	schlagwort = models.ForeignKey('Schlagwort', on_delete=models.CASCADE, verbose_name='Schlagwort')

	def __str__(self):
		return ""
	class Meta:
		verbose_name = "Schlagwort"
		verbose_name_plural = "Verschlagwortung"
		unique_together = ['mztyp','schlagwort']

class Wappen(models.Model):
	name = models.CharField(max_length=250, verbose_name='Wappen')
	beschreibung = models.CharField(max_length=250, blank=True, verbose_name='Kurzbeschreibung')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Wappen"
		ordering = ['name']

class Mztyp_Wappen(models.Model):
	mztyp = models.ForeignKey('Muenztyp', on_delete=models.CASCADE)
	wappen = models.ForeignKey('Wappen', on_delete=models.CASCADE, verbose_name='Wappen')
	appears_on_rev = models.BooleanField(verbose_name='am Revers', default=1)

	def __str__(self):
		return ""
	class Meta:
		verbose_name = "Wappen"
		verbose_name_plural = "Wappen"
		unique_together = ['mztyp','wappen', 'appears_on_rev']
		

class Rand(models.Model):
	name = models.CharField(max_length=250, verbose_name='Rand')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Randtypen"
		ordering = ['name']

class AvBildtyp(models.Model):
	name = models.CharField(max_length=250, unique=True, verbose_name='AvBildtyp')
	abk = models.CharField(max_length=20, blank=True, null=True, verbose_name='Abkürzung')
	schlagworte = models.ManyToManyField('Schlagwort', through="AvBildtyp_Schlagwort", verbose_name = ("Schlagwort"))
	def __str__(self):
		return self.name
	
	def save(self, *args, **kwargs):
		# Speichern Sie den alten Namen für spätere Vergleiche
		old_name = self.name if self.pk else None

		# Speichern des AvBildtyp-Objekts
		super(AvBildtyp, self).save(*args, **kwargs)

		# Prüfen, ob der Name geändert wurde
		if old_name and old_name != self.name:
			# Aktualisieren Sie alle MuenztypObjektAnzeige-Einträge mit dem alten Namen
			MuenztypObjektAnzeige.objects.filter(av_bildtyp=old_name).update(av_bildtyp=self.name)

	class Meta:
		verbose_name_plural = "AvBildtypen"
		ordering = ['name']

class AvBeizeichen(models.Model):
	name = models.CharField(max_length=250, verbose_name='AvBeizeichen')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "AvBeizeichen"
		ordering = ['name']

class AvOffizin(models.Model):
	name = models.CharField(max_length=250, verbose_name='AvOffizin')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "AvOffizin"
		ordering = ['name']

class AvBildrand(models.Model):
	name = models.CharField(max_length=250, verbose_name='AvBildrand')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "AvBildrandgestaltung"
		ordering = ['name']

class RvBildtyp(models.Model):
	name = models.CharField(max_length=250, unique=True, verbose_name='RvBildtyp')
	abk = models.CharField(max_length=20, blank=True, null=True, verbose_name='Abkürzung')
	schlagworte = models.ManyToManyField('Schlagwort', through="RvBildtyp_Schlagwort", verbose_name = ("Schlagwort"))
	def __str__(self):
		return self.name
	
	def save(self, *args, **kwargs):
		# Speichern Sie den alten Namen für spätere Vergleiche
		old_name = self.name if self.pk else None

		# Speichern des AvBildtyp-Objekts
		super(RvBildtyp, self).save(*args, **kwargs)

		# Prüfen, ob der Name geändert wurde
		if old_name and old_name != self.name:
			# Aktualisieren Sie alle MuenztypObjektAnzeige-Einträge mit dem alten Namen
			MuenztypObjektAnzeige.objects.filter(rv_bildtyp=old_name).update(rv_bildtyp=self.name)
			
	class Meta:
		verbose_name_plural = "RvBildtypen"
		ordering = ['name']

class RvBeizeichen(models.Model):
	name = models.CharField(max_length=250, verbose_name='RvBeizeichen')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "RvBeizeichen"
		ordering = ['name']

class RvOffizin(models.Model):
	name = models.CharField(max_length=250, verbose_name='RvOffizin')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "RvOffizin"
		ordering = ['name']

class RvBildrand(models.Model):
	name = models.CharField(max_length=250, verbose_name='RvBildrand')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "RvBildrandgestaltungen"
		ordering = ['name']

class Workflow(models.Model):
	name = models.CharField(max_length=250, verbose_name='Workflow')
	reihenfolge = models.PositiveSmallIntegerField(null=True, verbose_name="Reihenfolge")
	
	def __str__(self):
		# return self.name
		return str(self.reihenfolge) + " - " +self.name
	class Meta:
		verbose_name_plural = "Workflows"
		ordering = ['reihenfolge']

class Typ_Ref(models.Model):
	Typ = models.ForeignKey('Muenztyp', on_delete=models.CASCADE)
	Ref = models.ForeignKey('Ref', on_delete=models.CASCADE, verbose_name='Literatur')
	nummer = models.CharField(max_length=100, verbose_name='Seiten von-bis')
	def __str__(self):
		return ""
	class Meta:
		verbose_name = "Ergänzende Literatur"
		verbose_name_plural = "Ergänzende Literatur"

class Obj_Ref(models.Model):
	idfk_Obj = models.ForeignKey('Obj', on_delete=models.CASCADE)
	idfk_Ref = models.ForeignKey('Ref', on_delete=models.CASCADE, verbose_name='Zitat')
	
	nummer = models.CharField(max_length=100, verbose_name='Nummer')
	nach = models.BooleanField(verbose_name='Variante')
	variante = models.ForeignKey('Variantenbeschr', on_delete=models.CASCADE, verbose_name='Variante', blank=True, null=True)
	link = models.URLField(blank=True, null=True, verbose_name='Link zum Online-Typ')
	
	def __str__(self):
		# var = self.nach
		# return self.nummer + " " + '%s' % (var)
		return ""
	def _hlink(self):
		ocre = "http://numismatics.org/ocre/id/"
		crro = "http://numismatics.org/crro/id/"
		pella = "http://numismatics.org/pella/id/"
		agco = "http://numismatics.org/agco/id/"
		pco = "http://numismatics.org/pco/id/"
		hrc = "http://numismatics.org/hrc/id/"
		sco = "http://numismatics.org/sco/id/"
		if ocre in self.link:
			newlink = self.link.replace(ocre, 'http://numismatics.org/ocre/apis/reconcile/preview?id=')
			return '%s' % (newlink)
		elif crro in self.link:
			newlink = self.link.replace(crro, 'http://numismatics.org/crro/apis/reconcile/preview?id=')
			return '%s' % (newlink)
		elif pella in self.link:
			newlink = self.link.replace(pella, 'http://numismatics.org/pella/apis/reconcile/preview?id=')
			return '%s' % (newlink)
		elif pco in self.link:
			newlink = self.link.replace(pco, 'http://numismatics.org/pco/apis/reconcile/preview?id=')
			return '%s' % (newlink)
		elif agco in self.link:
			newlink = self.link.replace(agco, 'http://numismatics.org/agco/apis/reconcile/preview?id=')
			return '%s' % (newlink)
		elif hrc in self.link:
			newlink = self.link.replace(hrc, 'http://numismatics.org/hrc/apis/reconcile/preview?id=')
			return '%s' % (newlink)
		elif sco in self.link:
			newlink = self.link.replace(sco, 'http://numismatics.org/sco/apis/reconcile/preview?id=')
			return '%s' % (newlink)
		else:
			return '%s' % ('nolink')
		# when ocre = self.link
		#     hl = ocre
		# elif crro in self.link
		#     hl = crro
		# endif
		#print(newlink)
		#return '%s' % (newlink)
	hlink = property(_hlink)
	class Meta:
		verbose_name = "Literatur"
		verbose_name_plural = "Literatur, in der das Objekt erwähnt wird"

class SlgInformation_Ref(models.Model):
	Slginfo = models.ForeignKey('SlgInformation', on_delete=models.CASCADE)
	Ref = models.ForeignKey('Ref', on_delete=models.CASCADE, verbose_name='Name', related_name='Zitate')
	nummer = models.CharField(max_length=100, blank=True, null=True, verbose_name='Seitenzahl')
	link = models.URLField(blank=True, null=True, verbose_name='Webseite')
	
	def __str__(self):
		return ""
	
	class Meta:
		verbose_name = "Quelle"
		verbose_name_plural = "Quelle/n zum Ereignis"

class Person_Ref(models.Model):
	Person = models.ForeignKey('Person', on_delete=models.CASCADE)
	Ref = models.ForeignKey('Ref', on_delete=models.CASCADE, verbose_name='Name')
	nummer = models.CharField(max_length=100, blank=True, null=True, verbose_name='Seitenzahl')
	link = models.URLField(blank=True, null=True, verbose_name='Webseite')
	
	def __str__(self):
		return ""
	
	class Meta:
		verbose_name = "Literatur"
		verbose_name_plural = "Literatur"

STPL = (
	(0, 'unbekannt'),
	(1, '1'),
	(2, '2'),
	(3, '3'),
	(4, '4'),
	(5, '5'),
	(6, '6'),
	(7, '7'),
	(8, '8'),
	(9, '9'),
	(10, '10'),
	(11, '11'),
	(12, '12'),
	(13, 'nicht feststellbar')
)

Abnutzung = (
	(1, '1 - nicht bis kaum abgenutzt'),
	(2, '2 - leicht abgenutzt'),
	(3, '3 - abgenutzt'),
	(4, '4 - stark abgenutzt'),
	(5, '5 - sehr stark bis ganz abgenutzt'),
)

class interneAnmerkung(models.Model):
	name = models.CharField(max_length=250, verbose_name='Anmerkung')

	def __str__(self):
		return self.name

	class Meta:
		ordering = ('name',)
		verbose_name = "Interne Anmerkung"
		verbose_name_plural = "Interne Anmerkungen"

class Obj_interne_Anmerkung(models.Model):
	idfk_Obj = models.ForeignKey('Obj', on_delete=models.CASCADE, related_name='intanmerkungen')
	interne_Anmerkung = models.ForeignKey('interneAnmerkung', on_delete=models.CASCADE, verbose_name='Anmerkung (Auswahl)')
	text_anmerkung = models.TextField(blank=True, null=True, verbose_name='Anmerkung (freies Textfeld)')
	erledigt = models.BooleanField(blank=True, null=True, verbose_name='erledigt')
	class Meta:
		verbose_name = "Interne Anmerkung"
		verbose_name_plural = "Interne Anmerkungen"
		ordering = ('interne_Anmerkung',)

class Mztyp_interne_Anmerkung(models.Model):
	Mztyp = models.ForeignKey('Muenztyp', on_delete=models.CASCADE, related_name='intanmerkungen')
	interne_Anmerkung = models.ForeignKey('interneAnmerkung', on_delete=models.CASCADE, verbose_name='Anmerkung (Auswahl)')
	text_anmerkung = models.TextField(blank=True, null=True, verbose_name='Anmerkung (freies Textfeld)')
	erledigt = models.BooleanField(blank=True, null=True, verbose_name='erledigt')
	class Meta:
		verbose_name = "Interne Anmerkung"
		verbose_name_plural = "Interne Anmerkungen"
		ordering = ('interne_Anmerkung',)

class Sek_Merkmale(models.Model):
	name = models.CharField(max_length=200)
	name_nom_id = models.CharField(max_length=250, blank=True, verbose_name='Nomisma ID')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Sekundäre Merkmale"

class Herstellungsmerkmale(models.Model):
	name = models.CharField(max_length=200)
	name_nom_id = models.CharField(max_length=250, blank=True, verbose_name='Nomisma ID')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Herstellungsmerkmale"

class Reichskreis(models.Model):
	name = models.CharField(max_length=250)
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Reichskreise"

class Auflage(models.Model):
	name = models.CharField(max_length=200, verbose_name='Auflage')
	
	def __str__(self):
		return self.name
	class Meta:
		verbose_name_plural = "Auflagen"
		ordering = ['name']

class Paket(models.Model):
	DARSTELLUNGSART_FRONTCOVER = 'frontcover'
	DARSTELLUNGSART_KARTE = 'karte'
	DARSTELLUNGSART_OBJEKT = 'objekt'
	DARSTELLUNGSART_DIAGRAMM = 'diagramm'
	DARSTELLUNGSART_CHOICES = [
		(DARSTELLUNGSART_FRONTCOVER, 'Frontcover'),
		(DARSTELLUNGSART_KARTE, 'Karte'),
		(DARSTELLUNGSART_OBJEKT, 'Objekt'),
		(DARSTELLUNGSART_DIAGRAMM, 'Diagramm'),
	]

	KONTEXTTYP_HORTFUND = 'hortfund'
	KONTEXTTYP_FUNDKONTEXT = 'fundkontext'
	KONTEXTTYP_GRABUNG = 'grabung'
	KONTEXTTYP_THEMA = 'thema'
	KONTEXTTYP_CHOICES = [
		(KONTEXTTYP_HORTFUND, 'Hortfund'),
		(KONTEXTTYP_FUNDKONTEXT, 'Fundkontext'),
		(KONTEXTTYP_GRABUNG, 'Grabung'),
		(KONTEXTTYP_THEMA, 'Thema'),
	]

	FUNDPLATZ_CANABAE = 'canabae'
	FUNDPLATZ_AMPHITHEATER = 'amphitheater'
	FUNDPLATZ_KONTEXT_CHOICES = [
		(FUNDPLATZ_CANABAE, 'Canabae'),
		(FUNDPLATZ_AMPHITHEATER, 'Amphitheater'),
	]

	name = models.CharField(max_length=200, verbose_name='Paketname', unique=True)
	titel_oeffentlich = models.CharField(max_length=200, blank=True, verbose_name='Titel öffentlich')
	slug = models.SlugField(max_length=220, unique=True, blank=True, null=True, verbose_name='Slug')
	beschreibung = models.TextField(blank=True, null=True, verbose_name='Beschreibung')
	ist_arbeitspaket = models.BooleanField(default=True, verbose_name='Ist Arbeitspaket')
	online_freigegeben = models.BooleanField(default=False, verbose_name='Online freigegeben')
	darstellungsart = models.CharField(
		max_length=20,
		choices=DARSTELLUNGSART_CHOICES,
		default=DARSTELLUNGSART_OBJEKT,
		verbose_name='Startseiten-Darstellung',
		help_text='Legt fest, ob auf der Startseite Frontcover, Karte, Objektthumbnails oder Diagramm gezeigt werden.'
	)
	frontcover = models.FileField(
		upload_to='pakete/frontcover/',
		blank=True,
		null=True,
		verbose_name='Frontcover'
	)
	bekannte_objektanzahl = models.PositiveIntegerField(blank=True, null=True, verbose_name='Bekannte Anzahl der Objekte')
	kontexttyp = models.CharField(max_length=20, choices=KONTEXTTYP_CHOICES, blank=True, verbose_name='Kontexttyp')
	fund_lat = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, verbose_name='Fundkoordinate Breite', help_text='Dezimalgrad in WGS84, z. B. 48.116000')
	fund_lng = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, verbose_name='Fundkoordinate Länge', help_text='Dezimalgrad in WGS84, z. B. 16.867000')
	fundzeitpunkt_verbal = models.CharField(max_length=200, blank=True, verbose_name='Fundzeitpunkt (verbal)')
	fundplatz_kontext = models.CharField(
		max_length=20,
		choices=FUNDPLATZ_KONTEXT_CHOICES,
		blank=True,
		verbose_name='Fundplatz Kontext'
	)
	vergleichspakete = models.ManyToManyField(
		'self',
		blank=True,
		symmetrical=False,
		verbose_name='Vergleichsdiagramme mit Paketen',
		related_name='vergleichende_pakete'
	)
	literatur = models.ManyToManyField('Ref', blank=True, verbose_name='Literatur')
	erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name='Erstellt am')
	bearbeitet_am = models.DateTimeField(auto_now=True, verbose_name='Bearbeitet am')
	
	def __str__(self):
		return self.name

	@property
	def oeffentlicher_titel(self):
		return self.titel_oeffentlich or self.name

	def save(self, *args, **kwargs):
		if not self.slug:
			base_slug = slugify(self.titel_oeffentlich or self.name) or 'paket'
			slug = base_slug[:220]
			counter = 2
			while Paket.objects.filter(slug=slug).exclude(pk=self.pk).exists():
				suffix = f'-{counter}'
				slug = f'{base_slug[:220 - len(suffix)]}{suffix}'
				counter += 1
			self.slug = slug
		super().save(*args, **kwargs)
	
	class Meta:
		verbose_name = "Paket"
		verbose_name_plural = "Pakete"
		ordering = ['name']

class OffizinSymbol(models.Model):
	name = models.CharField(max_length=250, verbose_name='Offizinsymbol/Monogramm')
	beschreibung = models.TextField(blank=True, null=True, verbose_name='Beschreibung')
	svg_link = models.URLField(blank=True, null=True, verbose_name='Link zum SVG')
	uri_reference = models.URLField(blank=True, null=True, verbose_name='URI Referenz')
	
	def __str__(self):
		return self.name
	
	def get_svg_html(self):
		"""Returns HTML for displaying the SVG symbol"""
		html = ''
		if self.svg_link:
			html = f'<img src="{self.svg_link}" class="offizin-symbol" alt="{self.name}" title="{self.name}">'
		else:
			html = self.name
			
		# Add URI reference link if available
		if self.uri_reference:
			html += f' <a href="{self.uri_reference}" target="_blank" rel="noopener noreferrer" title="Externe Referenz"><i class="bi bi-box-arrow-up-right"></i></a>'
			
		return mark_safe(html)
	
	class Meta:
		verbose_name = "Offizinsymbol/Monogramm"
		verbose_name_plural = "Offizinsymbole/Monogramme"
		ordering = ['name']

class Muenztyp(CloneMixin, models.Model):
	Nominal = models.ForeignKey('Nominal', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Nominal')
	Ppl = models.ManyToManyField('Person', through='Mztyp_Person', verbose_name = ("Person"))
	Mzstaette = models.ForeignKey('Mzstaette', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Münzstätte')
	rv_bildtyp = models.ForeignKey('RvBildtyp', on_delete=models.CASCADE, blank=True, null=True, verbose_name='RvBildtyp', related_name='rvmztypen')
	
	muenztyptitel = models.CharField(max_length=250, blank=True, null=True, unique=True, verbose_name='Titel des Münztyps', help_text="optional (Zitat + Zitatnr. + Variante)")
	titel = models.CharField(max_length=200, blank=True, null=True, verbose_name='Titel der Münze', help_text="optional (Münzstand + Münzstätte + Münzherr/-en)")
	Objekttyp = models.ForeignKey('Objekttyp', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Objekttyp', default=1)
	Herstellung = models.ForeignKey('Herstellung', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Herstellung', default=1)
	Reichskreis = models.ForeignKey('Reichskreis', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Reichskreis')
	Muenzstand = models.ForeignKey('Muenzstand', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Münzstand')
	Metall = models.ForeignKey('Metall', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Material', help_text="optional")
	region = models.ForeignKey('Region', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Region', help_text="optional")

	dat_von = models.IntegerField(blank=True, null=True, verbose_name='Datierung von')
	dat_bis = models.IntegerField(blank=True, null=True, verbose_name='Datierung bis')
	dat_verb = models.CharField(max_length=100, blank=True, null=True, verbose_name='Datierung verbale', help_text="optional")

	avleg = models.TextField(blank=True, null=True, verbose_name='Av.-Legende')
	avbeschr = models.TextField(blank=True, null=True, verbose_name='Av.-Beschreibung')
	av_bildtyp = models.ForeignKey('AvBildtyp', on_delete=models.CASCADE, blank=True, null=True, verbose_name='AvBildtyp', related_name='avmztypen')
	av_beizeichen = models.ForeignKey('AvBeizeichen', on_delete=models.CASCADE, blank=True, null=True, verbose_name='AvBeizeichen')
	#av_offizin = models.ForeignKey('AvOffizin', on_delete=models.CASCADE, blank=True, null=True, verbose_name='AvOffizin')
	av_offizin_symbol = models.ForeignKey('OffizinSymbol', on_delete=models.CASCADE, blank=True, null=True, 
										  verbose_name='AvOffizinsymbol', related_name='av_muenztypen')
	av_bildrand = models.ForeignKey('AvBildrand', on_delete=models.CASCADE, blank=True, null=True, verbose_name='AvBildrand')
	
	rvleg = models.TextField(blank=True, null=True, verbose_name='Rv.-Legende')
	rvbeschr = models.TextField(blank=True, null=True, verbose_name='Rv.-Beschreibung')
	rv_beizeichen = models.ForeignKey('RvBeizeichen', on_delete=models.CASCADE, blank=True, null=True, verbose_name='RvBeizeichen', related_name='rvbeizeichen')
	#rv_offizin = models.ForeignKey('RvOffizin', on_delete=models.CASCADE, blank=True, null=True, verbose_name='RvOffizin')
	rv_offizin_symbol = models.ForeignKey('OffizinSymbol', on_delete=models.CASCADE, blank=True, null=True, 
										  verbose_name='RvOffizinsymbol', related_name='rv_muenztypen')
	rv_bildrand = models.ForeignKey('RvBildrand', on_delete=models.CASCADE, blank=True, null=True, verbose_name='RvBildrand')
	
	rand = models.ForeignKey('Rand', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Rand')


	anmerkung = models.TextField(blank=True, null=True, verbose_name='Anmerkungen')
	workflow = models.ForeignKey('Workflow', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Workflow', default=2)
	Ref = models.ForeignKey('Ref', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Zitat')
	nummer = models.CharField(blank=True, null=True, max_length=100, verbose_name='Nummer')
	nach = models.BooleanField(blank=True, null=True, verbose_name='Variante')
	variante = models.ForeignKey('Variantenbeschr', on_delete=models.CASCADE, verbose_name='Variante', blank=True, null=True)
	link = models.URLField(blank=True, null=True, verbose_name='Link zum Online-Typ')
	Konkordanz = models.ManyToManyField('self', symmetrical=True, blank=True, verbose_name = ("Konkordanz"))
	Literatur = models.ManyToManyField('Ref', through='Typ_Ref', related_name='Erweiterte_Literatur', verbose_name = ("Weitere Literatur"))

	wappen = models.ManyToManyField('Wappen', through="Mztyp_Wappen", verbose_name = ("Wappen"))
	
	schlagworte = models.ManyToManyField('Schlagwort', through="Mztyp_Schlagwort", verbose_name = ("Schlagwort"))
	interne_anmerkungen = models.ManyToManyField('interneAnmerkung', through='Mztyp_interne_Anmerkung', verbose_name = ("interne Anmerkungen"), default=0)

	created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
	modified_at = models.DateTimeField(auto_now=True, null=True, blank=True)

	# für den Button "Duplicate"
	_clone_m2m_fields = ['Literatur', 'Ppl', 'schlagworte']

	auflage = models.ForeignKey('Auflage', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Auflage')
	ausgabedatum = models.DateField(blank=True, null=True, verbose_name='Ausgabedatum')
	beschlussdatum = models.DateField(blank=True, null=True, verbose_name='Beschlussdatum')

	def __str__(self):
		return self.muenztyptitel
	
	def _hlink(self):
		ocre = "http://numismatics.org/ocre/id/"
		crro = "http://numismatics.org/crro/id/"
		pella = "http://numismatics.org/pella/id/"
		agco = "http://numismatics.org/agco/id/"
		pco = "http://numismatics.org/pco/id/"
		hrc = "http://numismatics.org/hrc/id/"
		sco = "http://numismatics.org/sco/id/"
		if ocre in self.link:
			newlink = self.link.replace(ocre, 'http://numismatics.org/ocre/apis/reconcile/preview?id=')
			return '%s' % (newlink)
		elif crro in self.link:
			newlink = self.link.replace(crro, 'http://numismatics.org/crro/apis/reconcile/preview?id=')
			return '%s' % (newlink)
		elif pella in self.link:
			newlink = self.link.replace(pella, 'http://numismatics.org/pella/apis/reconcile/preview?id=')
			return '%s' % (newlink)
		elif pco in self.link:
			newlink = self.link.replace(pco, 'http://numismatics.org/pco/apis/reconcile/preview?id=')
			return '%s' % (newlink)
		elif agco in self.link:
			newlink = self.link.replace(agco, 'http://numismatics.org/agco/apis/reconcile/preview?id=')
			return '%s' % (newlink)
		elif hrc in self.link:
			newlink = self.link.replace(hrc, 'http://numismatics.org/hrc/apis/reconcile/preview?id=')
			return '%s' % (newlink)
		elif sco in self.link:
			newlink = self.link.replace(sco, 'http://numismatics.org/sco/apis/reconcile/preview?id=')
			return '%s' % (newlink)
		else:
						return '%s' % ('nolink')

	hlink = property(_hlink)
	
	def get_dat_verb(self):
		if self.dat_von < self.dat_bis and self.dat_bis > 0:
			result = str(self.dat_von) + "-" + str(self.dat_bis)
			if self.dat_von < 492:
				result = result + " n. Chr."
			return result
		elif self.dat_von < self.dat_bis and self.dat_bis < 0:
			result = str(abs(self.dat_von)) + "-" + str(abs(self.dat_bis)) + " v. Chr."
			return result
		elif self.dat_von == self.dat_bis and self.dat_von < 0:
			result = str(abs(self.dat_von)) + " v. Chr."
			return result
		elif self.dat_von == self.dat_bis and self.dat_von > 0:
			result = str(self.dat_von)
			if self.dat_von < 492:
				result = result + " n. Chr."
			return result

	def save(self, *args, **kwargs):
		if self.dat_verb is None and self.dat_bis is not None and self.dat_von is not None:
			self.dat_verb = self.get_dat_verb()
		if self.muenztyptitel is None:
			self.muenztyptitel = str(self.Ref) + ", " + str(self.nummer)
			if self.variante:
				self.muenztyptitel = self.muenztyptitel + "var." + self.variante
		if self.titel is None:
			# Titel soll sich zusammensetzen aus Münzstand + Stadt + Münzherr
			
			if self.Muenzstand and not "Antike" in str(self.Muenzstand) and self.Mzstaette and not "ANT" in str(self.Muenzstand):
				self.titel = str(self.Muenzstand) + ", " + str(self.Mzstaette)
			elif self.Muenzstand and not "Antike" in str(self.Muenzstand) and not "ANT" in str(self.Muenzstand) and not self.Mzstaette:
				self.titel = str(self.Muenzstand)
			elif self.Mzstaette:
				self.titel = str(self.Mzstaette)
			# else:
			#     self.titel = ""
			
			# if self.Muenzstand:
			#     self.titel = self.Muenzstand
			
			muenzherr = Mztyp_Person.objects.filter(Mztyp=self.pk, idfk_PersonFunktion="1").select_related('idfk_Person')
			if muenzherr and self.titel is not None:
				self.titel += ": " + ' und '.join(str(v.idfk_Person.name) for v in muenzherr)
			elif self.titel is None:
				self.titel = ' und '.join(str(v.idfk_Person.name) for v in muenzherr)

			# # if "Antike" in str(self.Muenzstand):
			# if int(self.Muenzstand.pk) == '424':
			#     self.titel = "ANT"
			
		if self.Metall is None and self.Nominal is not None and self.Nominal.material is not None:
			# material = Nominal.objects.get(pk=self.Mzstaette.id)
			self.Metall = self.Nominal.material
		if self.region is None and self.Mzstaette is not None and self.Mzstaette.region is not None:
			self.region = self.Mzstaette.region
		super(Muenztyp, self).save(*args, **kwargs)
		
		# TEMPORÄR AUSKOMMENTIERT FÜR PERFORMANCE-TEST
		# # Sammle alle zugehörigen Obj-Instanzen
		# # ❷ einmaligen Zeitstempel erzeugen, damit jede Zeile denselben Wert bekommt
		# timestamp = timezone.now()
		# 
		# zu_aktualisieren = []
		# felder = None                           # wir merken uns die Feldliste nur einmal
		# 
		# for obj in self.objekte.select_related().all():
		# 
		#     mtoa_werte = obj.generate_mtoa_data()
		#     
		#     mtoa, created = MuenztypObjektAnzeige.objects.get_or_create(
		#         invnr=obj.invnr,
		#         defaults=mtoa_werte
		#     )
		# 
		#     if not created:
		#         for k, v in mtoa_werte.items():
		#             setattr(mtoa, k, v)
		#         zu_aktualisieren.append(mtoa)
		# 
		#     # Feldliste nur *ein* Mal festlegen …
		#     if felder is None:
		#         felder = list(mtoa_werte.keys())
		# 
		# # ❃ alle bereits existierenden Datensätze in einem Rutsch aktualisieren
		# if zu_aktualisieren:
		#     MuenztypObjektAnzeige.objects.bulk_update(zu_aktualisieren, felder)

	def get_absolute_url(self):
		return reverse("Typ", kwargs={"id": self.id})
	
	class Meta:
		verbose_name = "Münztyp"
		verbose_name_plural = "Münztypen"
		indexes = [
			models.Index(fields=['dat_von','dat_bis']),
			#models.Index(fields=['first_name'], name='first_name_idx'),
		]
		# PERFORMANCE: ordering entfernt - wurde bei JEDER Query angehängt (auch Subqueries).
		# Admin definiert eigenes ordering.

	def clean(self):
		super().clean()
		if self.dat_von is not None and self.dat_bis is not None:
			if self.dat_von > self.dat_bis:
				raise ValidationError({
					'dat_von': 'Das "Von"-Datum darf nicht größer sein als das "Bis"-Datum.',
					'dat_bis': 'Das "Bis"-Datum darf nicht kleiner sein als das "Von"-Datum.'
				})

class Fundort(models.Model):
	name = models.CharField(max_length=20, verbose_name='Fundort')
	def __str__(self):
		return self.name
	
class Fund(models.Model):
	objekt = models.OneToOneField('Obj', on_delete=models.CASCADE, verbose_name='Objekt')
	maßnahmennr = models.CharField(max_length=20, blank=True, null=True, verbose_name='Maßnahmen-Nr.')
	fundnummer = models.IntegerField(blank=True, null=True, verbose_name='Fundnummer')
	fundnummerzusatz = models.CharField(max_length=2, blank=True, null=True, verbose_name='Fundnummerzusatz')
	kistennr = models.CharField(max_length=20, blank=True, null=True, verbose_name='Kisten-Nr.')
	fundort = models.ForeignKey('Fundort', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Fundort')
	parzelle = models.CharField(max_length=200, blank=True, null=True, verbose_name='Parzelle')
	fundstelle = models.CharField(max_length=200, blank=True, null=True, verbose_name='Fundstelle')
	lm_von = models.DecimalField(blank=True, null=True, verbose_name='Laufmeter von', max_digits=5, decimal_places=2)
	lm_bis = models.DecimalField(blank=True, null=True, verbose_name='Laufmeter bis', max_digits=5, decimal_places=2)
	niveautiefe_in_m_von = models.DecimalField(blank=True, null=True, verbose_name='Niveautiefe in m von', max_digits=5, decimal_places=2)
	niveautiefe_in_m_bis = models.DecimalField(blank=True, null=True, verbose_name='Niveautiefe in m bis', max_digits=5, decimal_places=2)
	niveau = models.DecimalField(blank=True, null=True, verbose_name='Niveau', max_digits=6, decimal_places=3)
	vn = models.DecimalField(blank=True, null=True, verbose_name='von Norden (mm)', max_digits=6, decimal_places=2)
	vno = models.DecimalField(blank=True, null=True, verbose_name='von Nordosten (mm)', max_digits=6, decimal_places=2)
	vo = models.DecimalField(blank=True, null=True, verbose_name='von Osten (mm)', max_digits=6, decimal_places=2)
	vso = models.DecimalField(blank=True, null=True, verbose_name='von Südosten (mm)', max_digits=6, decimal_places=2)
	vs = models.DecimalField(blank=True, null=True, verbose_name='von Süden (mm)', max_digits=6, decimal_places=2)
	vsw = models.DecimalField(blank=True, null=True, verbose_name='von Südwesten (mm)', max_digits=6, decimal_places=2)
	vw = models.DecimalField(blank=True, null=True, verbose_name='von Westen (mm)', max_digits=6, decimal_places=2)
	vnw = models.DecimalField(blank=True, null=True, verbose_name='von Nordwesten (mm)', max_digits=6, decimal_places=2)
	schnitt = models.CharField(max_length=5, blank=True, null=True, verbose_name='Schnitt')
	bereichsbezeichnung = models.CharField(max_length=25, blank=True, null=True, verbose_name='Bereichsbezeichnung')
	sondage = models.IntegerField(blank=True, null=True, verbose_name='Sondage')
	quadrant = models.IntegerField(blank=True, null=True, verbose_name='Quadrant')
	quadrantzusatz = models.CharField(max_length=5, blank=True, null=True, verbose_name='Quadrant-Zusatz')
	flaeche = models.CharField(max_length=25, blank=True, null=True, verbose_name='Fläche')
	se = models.IntegerField(blank=True, null=True, verbose_name='Stratigraphische Einheit')
	stratum = models.CharField(max_length=200, blank=True, null=True, verbose_name='Stratum')
	funddatum = models.DateField(null=True, blank=True, verbose_name='Funddatum')
	fundjahr = models.IntegerField(null=True, blank=True, verbose_name='Fundjahr')
	zusammen_gefundene_muenzen = models.ManyToManyField('self', blank=True, symmetrical=True, verbose_name='Zusammen gefundene Münzen')
	andere_materialien = models.CharField(max_length=225, blank=True, null=True, verbose_name='Sonstiges Fundmaterial')
	fundposition = models.CharField(max_length=50, blank=True, null=True, verbose_name='Fundposition')
	fundkontext = models.CharField(max_length=225, blank=True, null=True, verbose_name='fundkontext')
	anmerkung = models.CharField(max_length=225, blank=True, null=True, verbose_name='Anmerkung')
	bearbeiter = models.CharField(max_length=225, blank=True, null=True, verbose_name='Fundzettel erfasst von')

	def __str__(self):
		return str(self.objekt.invnr)
	
	class Meta:
		verbose_name = "Fundinformation"
		verbose_name_plural = "Fundinformationen"
		ordering = ('maßnahmennr','fundnummer')

	def save(self, *args, **kwargs):
		if self.funddatum and not self.fundjahr:
			self.fundjahr = self.funddatum.year
		if self.lm_von and not self.lm_bis:
			self.lm_bis = self.lm_von
		if self.niveautiefe_in_m_von and not self.niveautiefe_in_m_bis:
			self.niveautiefe_in_m_bis = self.niveautiefe_in_m_von
		super().save(*args, **kwargs)

class Obj(models.Model):
	Typ = models.ForeignKey('Muenztyp', related_name='objekte', on_delete=models.CASCADE, 
						   blank=True, null=True, verbose_name='Typ', db_index=True)  # db_index hinzugefügt
	invnr = models.CharField(max_length=20, verbose_name='Inv.-Nr.')
	fmid = models.CharField(max_length=20, blank=True, null=True, verbose_name='Alte Filemaker-ID')
	#slug = models.SlugField(max_length=48, blank=True, null=True,)
	freigabe = models.BooleanField(blank=True, null=True, verbose_name='Freigabe')
	#faelschung = models.BooleanField(verbose_name='Fälschung')
	Objekttyp = models.ForeignKey('Objekttyp', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Objekttyp', default=1)
	idfk_Muenzstand = models.ForeignKey('Muenzstand', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Münzstand', db_index=True)
	idfk_Herstellung = models.ForeignKey('Herstellung', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Herstellung', db_index=True)
	Herstellungsmerkmale = models.ManyToManyField('Herstellungsmerkmale', blank=True, verbose_name = 'Herstellungsmerkmal',)
	sekundaere_Merkmale = models.ManyToManyField('Sek_Merkmale', blank=True, verbose_name = 'Sekundäres Merkmal',)
	#idfk_Mint = models.ForeignKey(Mint, on_delete=models.CASCADE, blank=True, null=True, verbose_name='Münzstätte')
	titel = models.CharField(max_length=200, blank=True, null=True, verbose_name='Titel')
	SlgTeil = models.ForeignKey('SlgTeil', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Sammlungsteil', db_index=True)
	Slg = models.ForeignKey('Slg', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Sammlung', db_index=True)
	idfk_Nominal = models.ForeignKey('Nominal', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Nominal', db_index=True)
	Metall = models.ForeignKey('Metall', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Material', db_index=True)
	faelschung = models.ForeignKey('Faelschung', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Fälschung', db_index=True)
	idfk_Mzstaette = models.ForeignKey('Mzstaette', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Münzstätte', db_index=True)
	region = models.ForeignKey('Region', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Region', db_index=True)
	Ppl = models.ManyToManyField('Person', through='Obj_Person', verbose_name = ("Person"))
	idfk_Ref = models.ManyToManyField('Ref', through='Obj_Ref', verbose_name = ("Referenz"))
	Typ_unsicher = models.BooleanField(blank=True, null=True, default=0, verbose_name='Typ ist unsicher')
	TempTyp = models.TextField(blank=True, null=True, verbose_name='TempTyp')
	Untertyp = models.ForeignKey('Muenztyp', related_name='OUntertyp', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Untertyp')
	Untertyp_unsicher = models.BooleanField(blank=True, null=True, default=0, verbose_name='Typ ist unsicher')

	dat_von = models.IntegerField(blank=True, null=True, verbose_name='Datierung von')
	dat_bis = models.IntegerField(blank=True, null=True, verbose_name='Datierung bis')
	dat_verb = models.CharField(max_length=100, blank=True, null=True, verbose_name='Datierung verbale')

	durchmesser = models.DecimalField(blank=True, null=True, verbose_name='Durchmesser', max_digits=5, decimal_places=1)
	gewicht = models.DecimalField(blank=True, null=True, verbose_name='Gewicht', max_digits=5, decimal_places=2)
	stempelstellung = models.IntegerField(choices=STPL, blank=True, null=True, verbose_name='Stempelstellung')
	abnutzung = models.IntegerField(choices=Abnutzung, blank=True, null=True, verbose_name='Abnutzung')

	avleg = models.TextField(blank=True, null=True, verbose_name='Av.-Legende')
	avbeschr = models.TextField(blank=True, null=True, verbose_name='Av.-Beschreibung')
	av_bildtyp = models.ForeignKey('AvBildtyp', on_delete=models.CASCADE, blank=True, null=True, verbose_name='AvBildtyp', db_index=True)
	av_beizeichen = models.ForeignKey('AvBeizeichen', on_delete=models.CASCADE, blank=True, null=True, verbose_name='AvBeizeichen', db_index=True)
	av_offizin = models.ForeignKey('AvOffizin', on_delete=models.CASCADE, blank=True, null=True, verbose_name='AvOffizin', db_index=True)
	av_offizin_symbol = models.ForeignKey('OffizinSymbol', on_delete=models.CASCADE, blank=True, null=True, 
										  verbose_name='AvOffizinMonogrammSymbol', related_name='av_objekte', db_index=True)
	av_bildrand = models.ForeignKey('AvBildrand', on_delete=models.CASCADE, blank=True, null=True, verbose_name='AvBildrand', db_index=True)

	#av_img = models.ImageField(upload_to='slgmz_based_upload_to', height_field=None, width_field=None, max_length=None, blank=True)
	rvleg = models.TextField(blank=True, null=True, verbose_name='Rv.-Legende')
	rvbeschr = models.TextField(blank=True, null=True, verbose_name='Rv.-Beschreibung')
	rv_bildtyp = models.ForeignKey('RvBildtyp', on_delete=models.CASCADE, blank=True, null=True, verbose_name='RvBildtyp', db_index=True)
	rv_beizeichen = models.ForeignKey('RvBeizeichen', on_delete=models.CASCADE, blank=True, null=True, verbose_name='RvBeizeichen', db_index=True)
	rv_offizin = models.ForeignKey('RvOffizin', on_delete=models.CASCADE, blank=True, null=True, verbose_name='RvOffizin', db_index=True)
	rv_offizin_symbol = models.ForeignKey('OffizinSymbol', on_delete=models.CASCADE, blank=True, null=True, 
										  verbose_name='RvOffizinMonogrammSymbol', related_name='rv_objekte', db_index=True)
	rv_bildrand = models.ForeignKey('RvBildrand', on_delete=models.CASCADE, blank=True, null=True, verbose_name='RvBildrand', db_index=True)
	
	rand = models.ForeignKey('Rand', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Rand', db_index=True)

	anmerkung = models.TextField(blank=True, null=True, verbose_name='Anmerkungen')
	interne_anmerkungen = models.ManyToManyField('interneAnmerkung', through='Obj_interne_Anmerkung', verbose_name = ("interne Anmerkungen"), default=0)
	pakete = models.ManyToManyField('Paket', blank=True, verbose_name='Pakete')
	workflow = models.ForeignKey('Workflow', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Workflow', default=1, db_index=True)

	created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
	modified_at = models.DateTimeField(auto_now=True, null=True, blank=True)
	# added_by = models.ForeignKey(User,editable=False, null=True, blank=True, on_delete=models.DO_NOTHING, related_name='Object_added_by')
	# modified_by = models.ForeignKey(User,editable=False, null=True, blank=True, on_delete=models.DO_NOTHING, related_name='Object_modified_by')
	
	#rv_img = models.ImageField(upload_to='slgmz_based_upload_to', height_field=None, width_field=None, max_length=None, blank=True)

	@property
	def av_schlagworte(self):
		"""
		Gibt alle Schlagworte für den Avers-Bildtyp des Typs zurück.
		Optimiert für den Fall, dass die Schlagworte bereits geprefetcht wurden.
		"""
		if self.Typ and self.Typ.av_bildtyp:
			# Versuche zuerst, bereits geladene Daten zu verwenden
			if (hasattr(self.Typ.av_bildtyp, '_prefetched_objects_cache') and 
				'avbildtyp_schlagwort_set' in self.Typ.av_bildtyp._prefetched_objects_cache):
				return [
					asw.schlagwort
					for asw in self.Typ.av_bildtyp._prefetched_objects_cache['avbildtyp_schlagwort_set']
				]
			else:
				# Fallback zur ursprünglichen Implementierung
				return [
					asw.schlagwort
					for asw in AvBildtyp_Schlagwort.objects.filter(avbildtyp=self.Typ.av_bildtyp).select_related('schlagwort')
				]
		return []

	@property
	def rv_schlagworte(self):
		"""
		Gibt alle Schlagworte für den Revers-Bildtyp des Typs zurück.
		Optimiert für den Fall, dass die Schlagworte bereits geprefetcht wurden.
		"""
		if self.Typ and self.Typ.rv_bildtyp:
			# Versuche zuerst, bereits geladene Daten zu verwenden
			if (hasattr(self.Typ.rv_bildtyp, '_prefetched_objects_cache') and 
				'rvbildtyp_schlagwort_set' in self.Typ.rv_bildtyp._prefetched_objects_cache):
				return [
					rsw.schlagwort
					for rsw in self.Typ.rv_bildtyp._prefetched_objects_cache['rvbildtyp_schlagwort_set']
				]
			else:
				# Fallback zur ursprünglichen Implementierung
				return [
					rsw.schlagwort
					for rsw in RvBildtyp_Schlagwort.objects.filter(rvbildtyp=self.Typ.rv_bildtyp).select_related('schlagwort')
				]
		return []

	@property
	def typ_personen_mit_funktion(self):
		"""
		Gibt alle Personen mit ihrer Funktion und appears_on_rev zurück, die über den Typ (Mztyp_Person) mit diesem Objekt verbunden sind.
		Optimiert für den Fall, dass mztyp_person_set bereits geprefetcht wurde.
		"""
		if self.Typ:
			# Versuche zuerst, bereits geladene Daten zu verwenden
			if hasattr(self.Typ, '_prefetched_objects_cache') and 'mztyp_person_set' in self.Typ._prefetched_objects_cache:
				# Verwende bereits geprefetchte Daten
				return [
					(mp.idfk_Person, mp.idfk_PersonFunktion, getattr(mp, 'appears_on_rev', None))
					for mp in self.Typ._prefetched_objects_cache['mztyp_person_set']
				]
			else:
				# Fallback zur ursprünglichen Implementierung
				return [
					(mp.idfk_Person, mp.idfk_PersonFunktion, getattr(mp, 'appears_on_rev', None))
					for mp in Mztyp_Person.objects.filter(Mztyp=self.Typ).select_related('idfk_Person', 'idfk_PersonFunktion')
				]
		return []

	def __str__(self):
		# return str('{0} ({1})'.format(self.invnr, str(self.id)))
		# return '{0}'.format(self.invnr)
		return "Objekt"

	def get_dat_verb(self):
		if self.dat_von < self.dat_bis and self.dat_bis > 0:
			result = str(self.dat_von) + "-" + str(self.dat_bis) + " n. Chr."
			return result
		elif self.dat_von < self.dat_bis and self.dat_bis < 0:
			result = str(abs(self.dat_von)) + "-" + str(abs(self.dat_bis)) + " v. Chr."
			return result
		elif self.dat_von == self.dat_bis and self.dat_von < 0:
			result = str(abs(self.dat_von)) + " v. Chr."
			return result
		elif self.dat_von == self.dat_bis and self.dat_von > 0:
			result = str(self.dat_von) + " n. Chr."
			return result
		
	# def save_model(self, request, obj, form, change):
	#     if not obj.pk:
	#         # Only set added_by during the first save.
	#         obj.added_by = request.user
	#     else:
	#         obj.modified_by = request.user
	#     super().save_model(request, obj, form, change)

	def save(self, *args, **kwargs):
		if self.dat_verb is None and self.dat_bis is not None and self.dat_von is not None:
			self.dat_verb = self.get_dat_verb()

		if self.Typ_id is None and self.Metall_id is None and self.idfk_Nominal_id and self.idfk_Nominal.material_id is not None:
			self.Metall = self.idfk_Nominal.material
			update_fields = kwargs.get('update_fields')
			if update_fields is not None:
				update_fields = set(update_fields)
				if update_fields:
					kwargs['update_fields'] = update_fields | {'Metall'}

		super(Obj, self).save(*args, **kwargs)

		# MTOA-Sync wird automatisch via post_save Signal ausgeführt (siehe slg/signals.py)

	# Funktion wird auch beim Abspeichern von Münztyp aufgerufen
	def generate_mtoa_data(self):

		urls = self.get_bild_urls() or {}

		personen_av = ''
		personen_rv = ''
		sonstige_personen = ''
		konkordanz_liste = ''
		av_schlagworte = ''
		rv_schlagworte = ''

		if self.av_bildtyp:
			av_schlagworte_liste = AvBildtyp_Schlagwort.objects.filter(avbildtyp=self.av_bildtyp)
			av_schlagworte = ', '.join([str(asw.schlagwort) for asw in av_schlagworte_liste])
		if self.rv_bildtyp:
			rv_schlagworte_liste = RvBildtyp_Schlagwort.objects.filter(rvbildtyp=self.rv_bildtyp)
			rv_schlagworte = ', '.join([str(rsw.schlagwort) for rsw in rv_schlagworte_liste])

		if self.Typ:
			# For personen_av, include function ID in parentheses
			personen_av = ' | '.join(
				[f"{mp.idfk_Person}: {mp.idfk_PersonFunktion} ({mp.idfk_PersonFunktion.id})" 
				 for mp in Mztyp_Person.objects.filter(Mztyp=self.Typ, appears_on_rev=False, idfk_PersonFunktion__id=2)]
			)

			# For personen_rv, include function ID in parentheses
			personen_rv = ' | '.join(
				[f"{mp.idfk_Person}: {mp.idfk_PersonFunktion} ({mp.idfk_PersonFunktion.id})" 
				 for mp in Mztyp_Person.objects.filter(Mztyp=self.Typ, appears_on_rev=True, idfk_PersonFunktion__id=2)]
			)

			# For sonstige_personen, include function ID in parentheses
			sonstige_personen = ' | '.join(
				[f"{mp.idfk_Person}: {mp.idfk_PersonFunktion} ({mp.idfk_PersonFunktion.id})" 
				 for mp in Mztyp_Person.objects.filter(Mztyp=self.Typ).exclude(idfk_PersonFunktion__id=2)]
			)

			konkordanz_liste = ' | '.join([str(konkordanz_objekt) for konkordanz_objekt in self.Typ.Konkordanz.all()])

		rv_beizeichen = self.rv_beizeichen.name if self.rv_beizeichen else ''
		if not rv_beizeichen and self.Typ and hasattr(self.Typ, 'rv_beizeichen') and self.Typ.rv_beizeichen:
			rv_beizeichen = self.Typ.rv_beizeichen.name
		if hasattr(self, 'rv_offizin') and self.rv_offizin:
			rv_beizeichen = rv_beizeichen.replace('?', self.rv_offizin.name)
		av_beizeichen = self.av_beizeichen.name if self.av_beizeichen else ''
		if not av_beizeichen and self.Typ and hasattr(self.Typ, 'av_beizeichen') and self.Typ.av_beizeichen:
			av_beizeichen = self.Typ.av_beizeichen.name
		if hasattr(self, 'av_offizin') and self.av_offizin:
			av_beizeichen = av_beizeichen.replace('?', self.av_offizin.name)

		# Logik zur Generierung der Daten für MuenztypObjektAnzeige
		return {
			'obj_id': self.id,
			'objekttitel': self.titel if self.titel else (self.Typ.titel if self.Typ and self.Typ.titel else None),
			'objekttyp': self.Objekttyp.name if self.Objekttyp else (self.Typ.Objekttyp.name if self.Typ and self.Typ.Objekttyp else None),
			'herstellung': self.idfk_Herstellung.name if self.idfk_Herstellung else (self.Typ.Herstellung.name if self.Typ and self.Typ.Herstellung else None),
			'reichskreis': self.Typ.Reichskreis.name if self.Typ and self.Typ.Reichskreis else None,
			'muenzstand': self.idfk_Muenzstand.name if self.idfk_Muenzstand else (self.Typ.Muenzstand.name if self.Typ and self.Typ.Muenzstand else None),
			'nominal': self.idfk_Nominal.name if self.idfk_Nominal else (self.Typ.Nominal.name if self.Typ and self.Typ.Nominal else None),
			'metall': self.Metall.name if self.Metall else (self.Typ.Metall.name if self.Typ and self.Typ.Metall else None),
			'mzstaette': self.idfk_Mzstaette.name if self.idfk_Mzstaette else (self.Typ.Mzstaette.name if self.Typ and self.Typ.Mzstaette else None),
			'region': self.region.name if self.region else (self.Typ.region.name if self.Typ and self.Typ.region else None),
			'datierung_von': self.dat_von if self.dat_von else (self.Typ.dat_von if self.Typ and self.Typ.dat_von else None),
			'datierung_bis': self.dat_bis if self.dat_bis else (self.Typ.dat_bis if self.Typ and self.Typ.dat_bis else None),
			'datierung_verbale': self.dat_verb if self.dat_verb else (self.Typ.dat_verb if self.Typ and self.Typ.dat_verb else None),
			'durchmesser': self.durchmesser if self.durchmesser else None,
			'gewicht': self.gewicht if self.gewicht else None,
			'stempelstellung': self.stempelstellung if self.stempelstellung else None,
			'abnutzung': self.abnutzung if self.abnutzung else None,
			'av_legende': self.avleg if self.avleg else (self.Typ.avleg if self.Typ and self.Typ.avleg else None),
			'av_bildtyp': self.av_bildtyp.name if self.av_bildtyp else (self.Typ.av_bildtyp.name if self.Typ and self.Typ.av_bildtyp else None),
			'av_beizeichen': av_beizeichen,
			'av_bildrand': self.av_bildrand.name if self.av_bildrand else (self.Typ.av_bildrand.name if self.Typ and self.Typ.av_bildrand else None),
			'rv_legende': self.rvleg if self.rvleg else (self.Typ.rvleg if self.Typ and self.Typ.rvleg else None),
			'rv_bildtyp': self.rv_bildtyp.name if self.rv_bildtyp else (self.Typ.rv_bildtyp.name if self.Typ and self.Typ.rv_bildtyp else None),
			'rv_beizeichen': rv_beizeichen,
			'rv_bildrand': self.rv_bildrand.name if self.rv_bildrand else (self.Typ.rv_bildrand.name if self.Typ and self.Typ.rv_bildrand else None),
			'rand': self.rand.name if self.rand else (self.Typ.rand.name if self.Typ and self.Typ.rand else None),
			'anmerkungen': self.anmerkung if self.anmerkung else (self.Typ.anmerkung if self.Typ and self.Typ.anmerkung else None),
			'typ': self.Typ.muenztyptitel if self.Typ and self.Typ.muenztyptitel else None,
			'typlink': self.Typ.link if self.Typ and self.Typ.link else None,
			'personen_av': personen_av,
			'personen_rv': personen_rv,
			'personen_sonstige': sonstige_personen,
			'konkordanz': konkordanz_liste,
			'av_schlagworte': av_schlagworte,
			'rv_schlagworte': rv_schlagworte,
			'last_modified': timezone.now(),
			'av_url'           : urls.get('av'),
			'rv_url'           : urls.get('rv'),
			'thumbnail_av_url' : urls.get('thumbnail_av'),
			'thumbnail_rv_url' : urls.get('thumbnail_rv'),
			'SlgTeil'          : self.SlgTeil.name if self.SlgTeil else None,
			'Slg'              : self.Slg.name if self.Slg else None,
		}
	# def image_tag(self):
	#     return '<img src="Obj.av_img.url" width="100" height="50" />' #% ({{MEDIA_URL}} + self.av_img)
	# image_tag.short_description = 'Image'
	# image_tag.allow_tags = True
	def _get_img(self):
		#"Returns the person's full name."
		if self.SlgTeil == "Slg. Neukloster":
			print("genau 1")
			return '%s' % (self.invnr.replace('/','-'))
		else:
			return '%s' % (self.invnr.replace('S','').replace('/','-'))
	img = property(_get_img)

	def get_bild_urls(self):
		basis_url = None
		endung_av = None
		endung_rv = None
		entferne_zeichen = None

		def build_local_base(slg, slgteil=None):
			# Verwende STATIC_URL statt MEDIA_URL für lokale Bilder
			static_subdir = getattr(settings, 'SLG_BILDER_STATIC_SUBDIR', 'slg_bilder')
			parts = [settings.STATIC_URL.rstrip('/'), static_subdir, slugify((slg.lokaler_ordnername or slg.name) if slg else 'unbekannt')]
			if slgteil:
				parts.append(slugify(slgteil.lokaler_unterordner or slgteil.name))
			return '/'.join(parts) + '/'

		if self.SlgTeil and self.SlgTeil.bildurl:
			basis_url = self.SlgTeil.bildurl
			endung_av = self.SlgTeil.bild_endung_av or ''
			endung_rv = self.SlgTeil.bild_endung_rv or ''
			entferne_zeichen = self.SlgTeil.entferne_zeichen or ''
		if self.SlgTeil and getattr(self.SlgTeil, 'bilder_lokal', False):
			basis_url = build_local_base(self.SlgTeil.idfk_Slg_SlgTeil, self.SlgTeil)
			endung_av = self.SlgTeil.bild_endung_av or endung_av or ''
			endung_rv = self.SlgTeil.bild_endung_rv or endung_rv or ''
			entferne_zeichen = self.SlgTeil.entferne_zeichen or entferne_zeichen or ''

		if not basis_url and self.Slg and self.Slg.bildurl:
			basis_url = self.Slg.bildurl
			endung_av = endung_av or (self.Slg.bild_endung_av or '')
			endung_rv = endung_rv or (self.Slg.bild_endung_rv or '')
			entferne_zeichen = entferne_zeichen or (self.Slg.entferne_zeichen or '')
		if not basis_url and self.Slg and getattr(self.Slg, 'bilder_lokal', False):
			basis_url = build_local_base(self.Slg)
			endung_av = self.Slg.bild_endung_av or endung_av or ''
			endung_rv = self.Slg.bild_endung_rv or endung_rv or ''
			entferne_zeichen = self.Slg.entferne_zeichen or entferne_zeichen or ''

		invnr = self.invnr or ''
		if entferne_zeichen:
			invnr = invnr.replace(entferne_zeichen, '')

		invnr_alt = invnr.replace('S', '').replace('/', '-')
		if self.SlgTeil and str(self.SlgTeil) == "Slg. Neukloster":
			invnr_alt = invnr.replace('/', '-')

		if basis_url:
			urls = {
				'av': f"{basis_url}{invnr}{endung_av}.jpg",
				'rv': f"{basis_url}{invnr}{endung_rv}.jpg",
				'thumbnail_av': f"{basis_url}thumbnails/{invnr}{endung_av}.webp",
				'thumbnail_rv': f"{basis_url}thumbnails/{invnr}{endung_rv}.webp"
			}
			if invnr_alt and invnr_alt != invnr:
				urls.update({
					'av_alt': f"{basis_url}{invnr_alt}{endung_av}.jpg",
					'rv_alt': f"{basis_url}{invnr_alt}{endung_rv}.jpg",
					'thumbnail_av_alt': f"{basis_url}thumbnails/{invnr_alt}{endung_av}.webp",
					'thumbnail_rv_alt': f"{basis_url}thumbnails/{invnr_alt}{endung_rv}.webp",
				})
			return urls
		else:
			return None
	
	# def get_absolute_url(self):
	#     return reverse("Objekt", kwargs={"pk": self.pk})
	def get_absolute_url(self):
		return reverse("Objekt", kwargs={"id": self.id})
	
	class Meta:
		unique_together = ('invnr', 'Slg', 'SlgTeil')
		verbose_name = "Objekt"
		verbose_name_plural = "Objekte"
		indexes = [
			models.Index(fields=['dat_von', 'dat_bis']),
			models.Index(fields=['Slg', 'SlgTeil']),  # PERFORMANCE: Für Admin-Filter
			# Die anderen Indizes werden durch db_index=True automatisch erstellt
		]
		# PERFORMANCE: ordering entfernt - wurde bei JEDER Query angehängt.
		# Admin definiert eigenes ordering ('-id').

	def clean(self):
		super().clean()
		if self.dat_von is not None and self.dat_bis is not None:
			if self.dat_von > self.dat_bis:
				raise ValidationError({
					'dat_von': 'Das "Von"-Datum darf nicht größer sein als das "Bis"-Datum.',
					'dat_bis': 'Das "Bis"-Datum darf nicht kleiner sein als das "Von"-Datum.'
				})

class MyObjects(Obj):
	class Meta:
		proxy = True
		verbose_name_plural = "Liste: Objekte"
		verbose_name = "Objekt"

class Staat(models.Model):
	name = models.CharField(max_length=200, verbose_name='Name')
	created_at = models.DateTimeField(default=datetime.now, null=True,blank=True)

class Katalogart(models.Model):
	name = models.CharField(max_length=200, verbose_name='Name')
	created_at = models.DateTimeField(default=datetime.now, null=True,blank=True)
	class Meta:
		verbose_name = "Katalogart"
		verbose_name_plural = "Katalogarten"

	def __str__(self):
		return self.name

class Firma(models.Model):
	name = models.CharField(max_length=200, verbose_name='Name')
	beschreibung = models.TextField(verbose_name='Beschreibung', blank=True)
	created_at = models.DateTimeField(default=datetime.now, null=True, blank=True)

	class Meta:
		verbose_name = "Firma"
		verbose_name_plural = "Firmen"
		ordering = ['name']
	
	def __str__(self):
		return self.name

class Monat(models.Model):
	name = models.CharField(max_length=200, verbose_name='Name')
	sortierung = models.PositiveSmallIntegerField(blank=True, null=True,)
	created_at = models.DateTimeField(default=datetime.now, null=True,blank=True)
	class Meta:
		verbose_name = "Monat"
		verbose_name_plural = "Monate"

	def __str__(self):
		return self.name

class Onlineressource(models.Model):
	name = models.URLField(blank=True, null=True, verbose_name='Link zum Online-Typ')
	temp = models.CharField(max_length=250, blank=True, null=True,verbose_name='Temp')
	katalog = models.ForeignKey('Katalog', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Katalog', related_name='hlinks')
	firma = models.ForeignKey('Firma', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Firma')
	def __str__(self):
		return str(self.name)

class Katalog(models.Model):
	#company = models.ManyToManyField('Firma', through='KatalogFirmen', verbose_name = 'Firmen')
	firmen = models.ManyToManyField('Firma', through='KatalogFirmen', verbose_name = 'Firmen')
	titel = models.CharField(max_length=200, blank=True, null=True,verbose_name='Titel')
	staat = models.ForeignKey('Staat', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Staat')
	katalogart = models.ForeignKey('Katalogart', on_delete=models.CASCADE, null=True, blank=True, verbose_name = ("Katalogart"))
	nummer = models.CharField(max_length=50, null=True, blank=True, verbose_name='Nummer')
	katalogteil = models.CharField(max_length=200, null=True, blank=True, verbose_name='Teil')
	anzahl = models.PositiveIntegerField(blank=True, null=True, verbose_name='Anzahl der Objekte')
	
	Ppl = models.ManyToManyField('Person', through='KatalogPerson', verbose_name = ("Person"))

	tag_von  = models.IntegerField(blank=True, null=True, verbose_name='Tag von')
	tag_bis  = models.IntegerField(blank=True, null=True, verbose_name='Tag bis')
	monat = models.ForeignKey('Monat', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Monat/Jahreszeit')
	jahr = models.PositiveIntegerField(blank=True, null=True, verbose_name='Jahr')

	tafelteil = models.BooleanField(verbose_name='Tafeln')
	tafelanzahl = models.PositiveIntegerField(blank=True, null=True, verbose_name='T.-Anzahl')

	workflow = models.ForeignKey('Workflow', on_delete=models.CASCADE, blank=True, null=True, verbose_name='Workflow', default=2)
	schlagworte = models.ManyToManyField('KatSchlagwort', through="KatalogSchlagwort", verbose_name = ("Schlagwort"))
	anmerkung = models.TextField(verbose_name='Anmerkung', blank=True)
	#created_at = models.DateTimeField(default=datetime.now, null=True, blank=True)

	class Meta:
		verbose_name = "Katalog"
		verbose_name_plural = "Kataloge"
		ordering = ['katalogart','jahr', 'monat', 'tag_von']

	def __str__(self):
		#string = self.katalogart #+ " " + self.nummer
		# if self.katalogart == None:
		#     return "ERROR-CUSTOMER NAME IS NULL"
		# try:
		#     # print(self.monat.name)
		#     return str(self.katalogart) + " " + str(self.nummer) + " (" + str(self.tag_von) + "." + str(self.monat) + "." + str(self.jahr) + ")"
		# except AttributeError:
		#     return self.katalogart + " " + str(self.nummer) + " (" + str(self.tag_von) + ".-." + str(self.jahr) + ")"
		# return str(self.katalogart) + " " + str(self.nummer) + " (" + str(self.tag_von) + "." + str(self.monat) + "." + str(self.jahr) + ")"
		return "%s, %s" % (
			", ".join(firma.name for firma in self.firmen.all()),
			str(self.katalogart) + " " + str(self.nummer) + " (" + str(self.tag_von) + "." + str(self.monat) + "." + str(self.jahr) + ")",
		)

class KatalogFirmen(models.Model):
	katalog = models.ForeignKey('Katalog', on_delete=models.CASCADE)
	firma = models.ForeignKey('Firma', on_delete=models.CASCADE)

	class Meta:
		unique_together = (('katalog', 'firma'),)
		verbose_name = "KatalogFirmen"
		verbose_name_plural = "KatalogFirmen"

class MuenztypObjektAnzeige(models.Model):
	obj_id = models.PositiveIntegerField(
		db_index=True,
		null=True,      # für das Daten-Backfill
		blank=True,
		verbose_name='Objekt-ID'
	)
	invnr = models.CharField(max_length=20, verbose_name='Inventarnummer')
	SlgTeil = models.CharField(max_length=100, null=True, blank=True, verbose_name='SlgTeil')
	Slg = models.CharField(max_length=100, null=True, blank=True, verbose_name='Slg')
	objekttitel = models.CharField(max_length=200, null=True, blank=True,verbose_name='Titel des Objekts')
	objekttyp = models.CharField(max_length=100, null=True, blank=True,verbose_name='Objekttyp')
	herstellung = models.CharField(max_length=100, null=True, blank=True,verbose_name='Herstellung')
	reichskreis = models.CharField(max_length=100, null=True, blank=True,verbose_name='Reichskreis')
	muenzstand = models.CharField(max_length=100, null=True, blank=True,verbose_name='Münzstand')
	nominal = models.CharField(max_length=100, null=True, blank=True,verbose_name='Nominal')
	metall = models.CharField(max_length=100, null=True, blank=True,verbose_name='Material')
	mzstaette = models.CharField(max_length=100, null=True, blank=True,verbose_name='Münzstätte')
	region = models.CharField(max_length=100, null=True, blank=True,verbose_name='Region')
	datierung_von = models.IntegerField(null=True, blank=True, verbose_name='Datierung von')
	datierung_bis = models.IntegerField(null=True, blank=True, verbose_name='Datierung bis')
	datierung_verbale = models.CharField(max_length=100, null=True, blank=True, verbose_name='Datierung verbale')
	durchmesser = models.DecimalField(null=True, blank=True, max_digits=5, decimal_places=1, verbose_name='Durchmesser')
	gewicht = models.DecimalField(null=True, blank=True, max_digits=5, decimal_places=2, verbose_name='Gewicht')
	stempelstellung = models.CharField(max_length=100, null=True, blank=True, verbose_name='Stempelstellung')
	abnutzung = models.CharField(max_length=100, null=True, blank=True, verbose_name='Abnutzung')
	av_legende = models.TextField(null=True, blank=True, verbose_name='Av.-Legende')
	av_bildtyp = models.CharField(max_length=255, null=True, blank=True, verbose_name='AvBildtyp')
	av_beizeichen = models.CharField(max_length=100, null=True, blank=True, verbose_name='AvBeizeichen')
	av_bildrand = models.CharField(max_length=100, null=True, blank=True, verbose_name='AvBildrand')
	av_schlagworte = models.TextField(null=True, blank=True, verbose_name='Av.-Schlagworte')
	rv_legende = models.TextField(null=True, blank=True, verbose_name='Rv.-Legende')
	rv_bildtyp = models.CharField(max_length=255, null=True, blank=True, verbose_name='RvBildtyp')
	rv_beizeichen = models.CharField(max_length=100, null=True, blank=True, verbose_name='RvBeizeichen')
	rv_bildrand = models.CharField(max_length=100, null=True, blank=True, verbose_name='RvBildrand')
	rv_schlagworte = models.TextField(null=True, blank=True, verbose_name='Rv.-Schlagworte')
	rand = models.CharField(max_length=100, null=True, blank=True, verbose_name='Rand')
	anmerkungen = models.TextField(null=True, blank=True, verbose_name='Anmerkungen')
	typ = models.CharField(max_length=100, null=True, blank=True, verbose_name='Typ')
	typlink = models.URLField(null=True, blank=True, verbose_name='Link zum Online-Typ')
	konkordanz = models.TextField(blank=True, null=True, verbose_name='Konkordanz')
	personen_av = models.TextField(blank=True, null=True, verbose_name='Personen Av')
	personen_rv = models.TextField(blank=True, null=True, verbose_name='Personen Rv')
	personen_sonstige = models.TextField(blank=True, null=True, verbose_name='Sonstige Personen')
	last_modified = models.DateTimeField(auto_now=True, null=True, blank=True, verbose_name='Zuletzt bearbeitet')
	av_url           = models.URLField(null=True, blank=True, verbose_name='Bild Avers')
	rv_url           = models.URLField(null=True, blank=True, verbose_name='Bild Revers')
	thumbnail_av_url = models.URLField(null=True, blank=True, verbose_name='Thumbnail Avers')
	thumbnail_rv_url = models.URLField(null=True, blank=True, verbose_name='Thumbnail Revers')

	# ── FK-Felder für effizientes Filtern (Hybrid: FK + Text) ──
	# Text-Felder oben bleiben für JOIN-freie Anzeige.
	# Diese FKs ermöglichen WHERE nominal_fk_id=5 statt WHERE nominal='Denar'.
	nominal_fk = models.ForeignKey(
		'Nominal', on_delete=models.SET_NULL, null=True, blank=True,
		db_index=True, related_name='+', verbose_name='Nominal (FK)')
	metall_fk = models.ForeignKey(
		'Metall', on_delete=models.SET_NULL, null=True, blank=True,
		db_index=True, related_name='+', verbose_name='Material (FK)')
	mzstaette_fk = models.ForeignKey(
		'Mzstaette', on_delete=models.SET_NULL, null=True, blank=True,
		db_index=True, related_name='+', verbose_name='Münzstätte (FK)')
	region_fk = models.ForeignKey(
		'Region', on_delete=models.SET_NULL, null=True, blank=True,
		db_index=True, related_name='+', verbose_name='Region (FK)')
	muenzstand_fk = models.ForeignKey(
		'Muenzstand', on_delete=models.SET_NULL, null=True, blank=True,
		db_index=True, related_name='+', verbose_name='Münzstand (FK)')
	objekttyp_fk = models.ForeignKey(
		'Objekttyp', on_delete=models.SET_NULL, null=True, blank=True,
		db_index=True, related_name='+', verbose_name='Objekttyp (FK)')
	herstellung_fk = models.ForeignKey(
		'Herstellung', on_delete=models.SET_NULL, null=True, blank=True,
		db_index=True, related_name='+', verbose_name='Herstellung (FK)')
	av_bildtyp_fk = models.ForeignKey(
		'AvBildtyp', on_delete=models.SET_NULL, null=True, blank=True,
		db_index=True, related_name='+', verbose_name='AvBildtyp (FK)')
	rv_bildtyp_fk = models.ForeignKey(
		'RvBildtyp', on_delete=models.SET_NULL, null=True, blank=True,
		db_index=True, related_name='+', verbose_name='RvBildtyp (FK)')
	slg_fk = models.ForeignKey(
		'Slg', on_delete=models.SET_NULL, null=True, blank=True,
		db_index=True, related_name='+', verbose_name='Sammlung (FK)')
	slgteil_fk = models.ForeignKey(
		'SlgTeil', on_delete=models.SET_NULL, null=True, blank=True,
		db_index=True, related_name='+', verbose_name='Sammlungsteil (FK)')
	typ_fk = models.ForeignKey(
		'Muenztyp', on_delete=models.SET_NULL, null=True, blank=True,
		db_index=True, related_name='+', verbose_name='Münztyp (FK)')

	@property
	def personen_mit_funktion(self):
		"""
		Parses the person fields and returns structured data similar to typ_personen_mit_funktion.
		Returns a list of dictionaries with name, function and appears_on_rev information.
		"""
		result = []
		
		# Process personen_av (appears_on_rev = False)
		if self.personen_av:
			for person_entry in self.personen_av.split(' | '):
				if ': ' in person_entry:
					person_name, function_name = person_entry.split(': ', 1)
					result.append({
						'name': person_name,
						'function': function_name,
						'appears_on_rev': False,
						'function_id': self._extract_function_id(function_name)
					})
		
		# Process personen_rv (appears_on_rev = True)
		if self.personen_rv:
			for person_entry in self.personen_rv.split(' | '):
				if ': ' in person_entry:
					person_name, function_name = person_entry.split(': ', 1)
					result.append({
						'name': person_name,
						'function': function_name,
						'appears_on_rev': True,
						'function_id': self._extract_function_id(function_name)
					})
		
		# Process personen_sonstige
		if self.personen_sonstige:
			for person_entry in self.personen_sonstige.split(' | '):
				if ': ' in person_entry:
					person_name, function_name = person_entry.split(': ', 1)
					result.append({
						'name': person_name,
						'function': function_name,
						'appears_on_rev': None,  # Unknown side
						'function_id': self._extract_function_id(function_name)
					})
		
		return result
		
	def _extract_function_id(self, function_text):
		"""Helper method to extract function ID from function text if available"""
		# Try to extract function ID from format like "Function Name (ID)"
		if function_text and '(' in function_text and function_text.endswith(')'):
			try:
				return int(function_text.split('(')[-1].strip(')'))
			except (ValueError, IndexError):
				pass
		return None
		
	def get_praegeherren(self):
		"""Returns people with minting authority functions (1, 6, 7)"""
		return [p for p in self.personen_mit_funktion 
				if p.get('function_id') in (1, 6, 7)]
		
	def get_dargestellte_av(self):
		"""Returns people depicted on averse (function 2, not on reverse)"""
		return [p for p in self.personen_mit_funktion 
				if p.get('function_id') == 2 and not p.get('appears_on_rev')]
		
	def get_dargestellte_rv(self):
		"""Returns people depicted on reverse (function 2, on reverse)"""
		return [p for p in self.personen_mit_funktion 
				if p.get('function_id') == 2 and p.get('appears_on_rev')]
				
	def get_other_persons(self):
		"""Returns people with other functions"""
		return [p for p in self.personen_mit_funktion 
				if p.get('function_id') not in (1, 2, 6, 7)]
		
	@property
	def Typ(self):
		class DummyTyp:
			def __init__(self, parent):
				self.titel = parent.objekttitel
				self.dat_verb = parent.datierung_verbale
				self.dat_von = parent.datierung_von
				self.dat_bis = parent.datierung_bis
				self.Metall = type('Metall', (), {'name': parent.metall})() if parent.metall else None
				self.Nominal = type('Nominal', (), {'name': parent.nominal})() if parent.nominal else None
		return DummyTyp(self)

	@property
	def get_absolute_url(self):
		"""Link auf das ursprüngliche Objekt (keine Inventarnr. mehr)."""
		if self.obj_id:
			# reverse vermeidet harte URL-Strings und folgt Ihren URL-Patterns
			return reverse('Objekt', kwargs={'id': self.obj_id})
		# Fallback, solange alte Datensätze noch keine obj_id haben
		return f"/objekt/{self.invnr}/"

	@property
	def get_bild_urls(self):
		"""Gibt die bereits zwischengespeicherten Pfade zurück – keine Berechnung mehr nötig."""
		return {
			'av'          : self.av_url,
			'rv'          : self.rv_url,
			'thumbnail_av': self.thumbnail_av_url,
			'thumbnail_rv': self.thumbnail_rv_url,
		}

	@property
	def typ_personen_mit_funktion(self):
		result = []
		for p in self.personen_mit_funktion:
			person = type('Person', (), {'name': p['name']})()
			funktion = type('Funktion', (), {'id': p['function_id'], 'name': p['function']})()
			result.append((person, funktion, p['appears_on_rev']))
		return result


class MtoaPerson(models.Model):
	"""
	Bridge-Tabelle für Personen zur MuenztypObjektAnzeige.
	Schlüsselt die Textfelder (personen_av etc) relational auf für effiziente
	Filter-Facetten über 500k+ Objekte.
	"""
	mtoa = models.ForeignKey(MuenztypObjektAnzeige, on_delete=models.CASCADE)
	person = models.ForeignKey('Person', on_delete=models.CASCADE)
	funktion = models.ForeignKey('PersonFunktion', on_delete=models.CASCADE)
	appears_on_rev = models.BooleanField(default=False)

	class Meta:
		verbose_name = "MTOA Person"
		verbose_name_plural = "MTOA Personen"
		indexes = [
			# Beschleunigt Filter wie "Welche MTOAs zeigen Person X mit Funktion Y"
			models.Index(fields=['person', 'funktion', 'appears_on_rev']),
			models.Index(fields=['mtoa']),
		]

	def __str__(self):
		return f"{self.person} ({self.funktion}) an MTOA {self.mtoa_id}"


# Fügen Sie dieses Model am Ende der models.py-Datei hinzu
class Kontaktanfrage(models.Model):
	name = models.CharField(max_length=100, verbose_name="Name")
	email = models.EmailField(verbose_name="E-Mail")
	betreff = models.CharField(max_length=200, verbose_name="Betreff")
	nachricht = models.TextField(verbose_name="Nachricht")
	erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")
	bearbeitet = models.BooleanField(default=False, verbose_name="Bearbeitet")
	
	class Meta:
		verbose_name = "Kontaktanfrage"
		verbose_name_plural = "Kontaktanfragen"
		ordering = ['-erstellt_am']
	
	def __str__(self):
		return f"{self.betreff} von {self.name} ({self.erstellt_am.strftime('%d.%m.%Y')})"

class ObjektAenderung(models.Model):
	objekt = models.ForeignKey(Obj, on_delete=models.CASCADE, related_name='aenderungen', verbose_name="Objekt")
	name = models.CharField(max_length=100, verbose_name="Name")
	email = models.EmailField(verbose_name="E-Mail")
	feld = models.CharField(max_length=100, verbose_name="Geändertes Feld")
	alter_wert = models.TextField(verbose_name="Alter Wert")
	neuer_wert = models.TextField(verbose_name="Neuer Wert")
	begruendung = models.TextField(verbose_name="Begründung")
	erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")
	status = models.CharField(
		max_length=20,
		choices=[
			('offen', 'Offen'),
			('angenommen', 'Angenommen'),
			('abgelehnt', 'Abgelehnt')
		],
		default='offen',
		verbose_name="Status"
	)
	bearbeitet_von = models.ForeignKey(
		User, 
		on_delete=models.SET_NULL, 
		null=True, 
		blank=True, 
		related_name='bearbeitete_aenderungen',
		verbose_name="Bearbeitet von"
	)
	bearbeitet_am = models.DateTimeField(null=True, blank=True, verbose_name="Bearbeitet am")
	
	class Meta:
		verbose_name = "Objektänderung"
		verbose_name_plural = "Objektänderungen"
		ordering = ['-erstellt_am']
	
	def __str__(self):
		return f"Änderung an {self.objekt} ({self.feld}) von {self.name}"

# Kategorie für Ereignis-Schlagworte
class EreignisSchlagwortKategorie(models.Model):
	name = models.CharField(max_length=100, verbose_name='Kategorie')
	beschreibung = models.TextField(blank=True, null=True, verbose_name='Beschreibung')
	
	def __str__(self):
		return self.name
	
	class Meta:
		verbose_name = "Ereignis-Schlagwort-Kategorie"
		verbose_name_plural = "Ereignis-Schlagwort-Kategorien"
		ordering = ['name']

# Spezielle Schlagworte für Ereignisse
class EreignisSchlagwort(models.Model):
	name = models.CharField(max_length=200, verbose_name='Schlagwort')
	kategorie = models.ForeignKey(
		'EreignisSchlagwortKategorie', 
		on_delete=models.CASCADE, 
		blank=True, 
		null=True, 
		verbose_name='Kategorie'
	)
	name_nom_id = models.CharField(max_length=200, blank=True, verbose_name='Nomisma ID')
	synonyme = models.TextField(blank=True, null=True, verbose_name='Synonyme')
	beschreibung = models.TextField(blank=True, null=True, verbose_name='Beschreibung')
	
	def __str__(self):
		if self.kategorie:
			return f"{self.kategorie.name}: {self.name}"
		return self.name
	
	class Meta:
		verbose_name = "Ereignis-Schlagwort"
		verbose_name_plural = "Ereignis-Schlagworte"
		ordering = ['kategorie__name', 'name']

# Through-Model für die Many-to-Many Beziehung
class SlgInformationSchlagwort(models.Model):
	slginformation = models.ForeignKey('SlgInformation', on_delete=models.CASCADE)
	ereignisschlagwort = models.ForeignKey('EreignisSchlagwort', on_delete=models.CASCADE, verbose_name='Schlagwort')
	
	def __str__(self):
		return self.ereignisschlagwort.name
	
	class Meta:
		verbose_name = "Ereignis-Schlagwort"
		verbose_name_plural = "Ereignis-Verschlagwortung"
		unique_together = ['slginformation', 'ereignisschlagwort']
		ordering = ['ereignisschlagwort__kategorie__name', 'ereignisschlagwort__name']

# Proxy-Model für den Paket-Import
class ObjPaketZuweisung(Obj):
	class Meta:
		proxy = True
		verbose_name = "Paket-Zuweisung (Import)"
		verbose_name_plural = "Paket-Zuweisungen (Import)"

class Titel(models.Model):
	name = models.CharField(max_length=200, verbose_name='Titel', unique=True)
	sortierung = models.PositiveIntegerField(default=0, verbose_name='Sortierung')
	erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name='Erstellt am')
	
	def __str__(self):
		return self.name
	
	class Meta:
		verbose_name = "Titel"
		verbose_name_plural = "Titel"
		ordering = ['sortierung', 'name']
