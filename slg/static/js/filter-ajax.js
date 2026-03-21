// Filter-Ajax Funktionalität
$(document).ready(function() {
    initializeSelect2Filters();
    initializeFilterAccordion();
});

function initializeSelect2Filters() {
    $('.select2-ajax').each(function() {
        $(this).select2({
            ajax: {
                url: $(this).data('ajax-url'),
                dataType: 'json',
                delay: 250,
                data: function(params) {
                    return {
                        term: params.term,
                        ...getAllFilterValues()
                    };
                },
                processResults: function(data) {
                    return { results: data.results };
                },
                cache: true
            },
            minimumInputLength: 2,
            placeholder: $(this).data('placeholder'),
            allowClear: true
        });
    });
}

function getAllFilterValues() {
    const filters = {};
    $('form').serializeArray().forEach(function(item) {
        if (item.value) {
            filters[item.name] = item.value;
        }
    });
    return filters;
}

function initializeFilterAccordion() {
    // Speichern des Accordion-Status
    $('.accordion-button').on('click', function() {
        const targetId = $(this).attr('data-bs-target');
        localStorage.setItem('accordion_' + targetId, 
            $(targetId).hasClass('show') ? 'closed' : 'open');
    });

    // Wiederherstellen des Accordion-Status
    $('.accordion-collapse').each(function() {
        const status = localStorage.getItem('accordion_' + '#' + $(this).attr('id'));
        if (status === 'open') {
            $(this).addClass('show');
        }
    });
} 