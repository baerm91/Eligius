(function () {
  'use strict';

  window.EligiusMaps = {
    addDarkBasemap: function (map) {
      // OpenFreeMap serves vector tiles without an account or API key.
      // Keep Leaflet controls, marker clustering and popups above the basemap.
      map.setMinZoom(1);
      map.setMaxZoom(20);
      map.setMaxBounds([[-85.051129, -Infinity], [85.051129, Infinity]]);
      map.options.maxBoundsViscosity = 1;

      return L.maplibreGL({
        style: 'https://tiles.openfreemap.org/styles/dark',
        interactive: false,
        attribution: '<a href="https://openfreemap.org/">OpenFreeMap</a> ' +
          '&copy; <a href="https://www.openmaptiles.org/">OpenMapTiles</a> ' +
          'Data from <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      }).addTo(map);
    }
  };
}());
