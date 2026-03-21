window.addEventListener("load", function() {
    (function($) {
        // Funktion zum Erstellen des Modals
        function createModal() {
            var modalHTML = '<div id="konkordanzModal" class="modal">' +
                            '<div class="modal-content">' +
                            '<span class="close">&times;</span>' +
                            '<p id="modalText">Einige Texte</p>' +
                            '</div></div>';

            $("body").append(modalHTML);

            // Stil für das Modal
            var modalStyle = "<style>" +
                             ".modal {display: none; position: fixed; z-index: 1; left: 0; top: 0; width: 100%; height: 100%; overflow: auto; background-color: rgba(0,0,0,0.4);}" +
                             ".modal-content {background-color: #fefefe; margin: 15% auto; padding: 20px; border: 1px solid #888; width: 80%;}" +
                             ".close {color: #aaa; float: right; font-size: 28px; font-weight: bold;}" +
                             ".close:hover, .close:focus {color: black; text-decoration: none; cursor: pointer;}" +
                             "</style>";

            $("head").append(modalStyle);

            // Event Handler für das Schließen des Modals
            $(".close").on("click", function() {
                $("#konkordanzModal").hide();
            });
        }

        // Funktion zum Erstellen und Hinzufügen des Button-Containers
        function createButtonContainer() {
            var containerHTML = '<div id="konkordanzen-buttons" style="margin-top: 20px;"></div>';
            $("body").append(containerHTML); // Fügen Sie den Container dem Body-Element hinzu
        }

        // Funktion zum Öffnen des Modals
        function openModal(text) {
            $('#modalText').text(text);
            $('#konkordanzModal').show();
        }

        var currentInputField; // Globale Variable, um das aktuelle Eingabefeld zu speichern

        function checkKonkordanzen() {
            currentInputField = $(this); // Speichert das auslösende Eingabefeld
            var typValue = $(this).val();
            $.ajax({
                url: '/ajax/get-konkordanzen/',
                data: { 'typ': typValue },
                success: function(data) {
                    if (data.konkordanzen.length > 0) {
                        var modalText = $('#modalText');
                        modalText.empty(); // Vorherigen Inhalt löschen
        
                        data.konkordanzen.forEach(function(konkordanz) {
                            // Stellen Sie sicher, dass konkordanz sowohl ID als auch Titel enthält
                            var button = $('<button/>', {
                                text: konkordanz.titel, // Beschriftung des Buttons
                                class: 'konkordanz-button',
                                'data-id': konkordanz.id // Speichern der ID als data-Attribut
                            });
                            modalText.append(button);
                        });
        
                        openModal();
                    }
                }
            });
        }
        
        // Event-Delegation für Konkordanz-Buttons
        $(document).on('click', '.konkordanz-button', function() {
            var konkordanzId = $(this).data('id');
            selectKonkordanz(konkordanzId);
        });

        function selectKonkordanz(konkordanzId) {
            if(currentInputField) {
                currentInputField.val(konkordanzId); // Setzt die ID im ursprünglichen Eingabefeld
            }
            $('#konkordanzModal').hide(); // Schließen des Modals
        }
        
        $(document).ready(function() {
            createModal();
            createButtonContainer();

            $('td.field-Typ .vForeignKeyRawIdAdminField, #id_Typ').on('change', function() {
                currentInputField = $(this); // Speichert das auslösende Eingabefeld
                checkKonkordanzen.call(this); // Ruft checkKonkordanzen im Kontext des aktuellen Elements auf
            });
            
            var originalDismissRelatedLookupPopup = window.dismissRelatedLookupPopup;
            window.dismissRelatedLookupPopup = function(win, chosenId) {
                originalDismissRelatedLookupPopup(win, chosenId);
                $('#' + windowname_to_id(win.name)).trigger('change');
            };
        });

    })(django.jQuery);
});
