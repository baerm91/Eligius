// Shared UI helpers. Collection values and filter identifiers are never translated.
window.eligiusSelect2Language = {
    errorLoading: () => gettext('Fehler beim Laden'),
    inputTooShort: () => gettext('Bitte geben Sie weitere Zeichen ein.'),
    inputTooLong: () => gettext('Bitte kürzen Sie Ihre Eingabe.'),
    loadingMore: () => gettext('Weitere Ergebnisse werden geladen …'),
    maximumSelected: () => gettext('Die maximale Anzahl ist ausgewählt.'),
    noResults: () => gettext('Keine Ergebnisse gefunden.'),
    searching: () => gettext('Suche läuft …'),
    removeAllItems: () => gettext('Auswahl löschen')
};

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.language-switcher').forEach(form => {
        form.addEventListener('submit', () => {
            form.elements.next.value = window.location.pathname + window.location.search + window.location.hash;
        });
    });
});
