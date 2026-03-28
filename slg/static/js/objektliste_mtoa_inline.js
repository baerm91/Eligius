
document.addEventListener("DOMContentLoaded", function () {
    // Initialize date range slider
    const dateSlider = document.getElementById('date-range-slider');

    // Get min and max years from the chart data or use defaults
    let minYear = 0;
    let maxYear = 2000;

    // Check URL parameters for existing values
    const urlParams = new URLSearchParams(window.location.search);
    const currentMinYear = urlParams.get('dat_von') ? parseInt(urlParams.get('dat_von')) : minYear;
    const currentMaxYear = urlParams.get('dat_bis') ? parseInt(urlParams.get('dat_bis')) : maxYear;

    // Initialize the slider if it exists
    if (dateSlider) {
      noUiSlider.create(dateSlider, {
        start: [currentMinYear, currentMaxYear],
        connect: true,
        step: 1,
        range: {
          'min': minYear,
          'max': maxYear
        },
        format: {
          to: function (value) {
            return Math.round(value);
          },
          from: function (value) {
            return Math.round(value);
          }
        },
        tooltips: [true, true]
      });

      // Elements to display values
      const minValueElement = document.getElementById('date-min-value');
      const maxValueElement = document.getElementById('date-max-value');
      const rangeDisplayElement = document.getElementById('date-range-display');

      // Update display values when slider changes
      dateSlider.noUiSlider.on('update', function (values, handle) {
        const minValue = Math.round(values[0]);
        const maxValue = Math.round(values[1]);

        minValueElement.textContent = minValue;
        maxValueElement.textContent = maxValue;
        rangeDisplayElement.textContent = `Jahr ${minValue} - ${maxValue}`;
      });

      // Apply button click handler
      document.getElementById('apply-date-filter').addEventListener('click', function () {
        const values = dateSlider.noUiSlider.get();
        const minValue = Math.round(values[0]);
        const maxValue = Math.round(values[1]);

        // Get current slider range
        const sliderRange = dateSlider.noUiSlider.options.range;
        const sliderMin = sliderRange.min;
        const sliderMax = sliderRange.max;

        // Create new URL with updated parameters
        const url = new URL(window.location.href);

        // Always set both parameters to make the selected range explicit
        url.searchParams.set('dat_von', minValue);
        url.searchParams.set('dat_bis', maxValue);

        // Navigate to the new URL
        window.location.href = url.toString();
      });

    }
  });


// BFCache-Unterstützung implementieren
  document.addEventListener('DOMContentLoaded', function () {
    let infiniteScrollInstance = null;
    let mapInstance = null;
    let chartInstance = null;
    let eventListeners = [];

    // Hilfsfunktion zum Registrieren von Event Listeners
    function addTrackedEventListener(element, event, handler, options) {
      element.addEventListener(event, handler, options);
      eventListeners.push({ element, event, handler, options });
    }

    // Alle Event Listener entfernen
    function removeAllEventListeners() {
      eventListeners.forEach(({ element, event, handler }) => {
        element.removeEventListener(event, handler);
      });
      eventListeners = [];
    }

    // Page Lifecycle Events für bfcache
    function initializePageResources() {
      console.log('Initializing page resources for bfcache compatibility');

      // Infinite Scroll initialisieren falls vorhanden
      const infiniteContainer = document.querySelector('.infinite-container');
      if (infiniteContainer && typeof Waypoint !== 'undefined') {
        infiniteScrollInstance = new Waypoint.Infinite({
          element: infiniteContainer,
          onBeforePageLoad: function () {
            console.log('Loading next page...');
          },
          onAfterPageLoad: function ($items) {
            console.log('Page loaded.');
          }
        });
      }

      // Karte initialisieren falls noch nicht geschehen
      if (!window.map && typeof initializeMapWithClustering === 'function') {
        try {
          mapInstance = initializeMapWithClustering();
          window.map = mapInstance;
        } catch (error) {
          console.error("Fehler beim Initialisieren der Karte:", error);
        }
      }

      if (!window.browseChart && typeof loadChartData === 'function') {
        loadChartData();
      }
    }

    function cleanupPageResources() {
      console.log('Cleaning up page resources for bfcache');

      // Infinite Scroll cleanup
      if (infiniteScrollInstance && infiniteScrollInstance.destroy) {
        infiniteScrollInstance.destroy();
        infiniteScrollInstance = null;
      }

      // Map cleanup
      if (mapInstance && mapInstance.remove) {
        mapInstance.remove();
        mapInstance = null;
        window.map = null;
      }

      if (window.browseChart && window.browseChart.dispose) {
        window.browseChart.dispose();
        window.browseChart = null;
      }

      // Event Listeners cleanup
      removeAllEventListeners();
    }

    // BFCache Events
    window.addEventListener('pageshow', function (event) {
      if (event.persisted) {
        // Seite wurde aus bfcache wiederhergestellt
        console.log('Page restored from bfcache');
        initializePageResources();
      }
    });

    window.addEventListener('pagehide', function (event) {
      if (event.persisted) {
        // Seite wird in bfcache gespeichert
        console.log('Page going into bfcache');
        cleanupPageResources();
      }
    });

    // Sofortiger Start
    initializePageResources();
  });

  // History API bfcache-kompatibel machen
  (function () {
    const originalReplaceState = history.replaceState;
    history.replaceState = function (state, title, url) {
      // Prüfen ob Navigation stattfindet
      if (url !== window.location.href) {
        // Navigation detection für bfcache
        const event = new CustomEvent('urlchange', {
          detail: { url: url, state: state }
        });
        window.dispatchEvent(event);
      }
      return originalReplaceState.call(this, state, title, url);
    };
  })();

// Timeout Management für bfcache
  let activeTimeouts = new Set();
  let activeIntervals = new Set();

  // Wrapper für setTimeout
  const bfcacheCompatibleSetTimeout = function (callback, delay) {
    const timeoutId = setTimeout(function () {
      activeTimeouts.delete(timeoutId);
      callback();
    }, delay);
    activeTimeouts.add(timeoutId);
    return timeoutId;
  };

  // Wrapper für setInterval  
  const bfcacheCompatibleSetInterval = function (callback, delay) {
    const intervalId = setInterval(callback, delay);
    activeIntervals.add(intervalId);
    return intervalId;
  };

  // Cleanup Funktion
  function clearAllTimers() {
    activeTimeouts.forEach(id => clearTimeout(id));
    activeIntervals.forEach(id => clearInterval(id));
    activeTimeouts.clear();
    activeIntervals.clear();
  }

  // Page hide event - cleanup timers
  window.addEventListener('pagehide', clearAllTimers);

  // Ersetzen Sie in Ihrem Code setTimeout/setInterval mit den bfcache-kompatiblen Versionen
  // Zum Beispiel diese Zeile ändern:
  // setTimeout(function(){ map.scrollWheelZoom.disable(); }, 1000);
  // zu:
  // bfcacheCompatibleSetTimeout(function(){ map.scrollWheelZoom.disable(); }, 1000);
