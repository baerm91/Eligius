// Infinite Scroll Funktionalität

// FIX: isLoading muss im globalen Scope stehen!
let isLoading = false;

$(document).ready(function() {
    initializeInfiniteScroll();
});

function initializeInfiniteScroll() {
    const loadMoreElement = document.getElementById('load-more');

    if (loadMoreElement) {
        loadMoreElement.querySelector('[data-load-more]').addEventListener('click', event => {
            event.preventDefault();
            loadMoreContent(true);
        });
        const observer = new IntersectionObserver(
            entries => {
                if (entries[0].isIntersecting && !isLoading) {
                    loadMoreContent();
                }
            },
            {
                rootMargin: '0px 0px 100px 0px',
                threshold: 0.1
            }
        );

        observer.observe(loadMoreElement);
    }
}

function loadMoreContent(manual = false) {
    if (isLoading) return;

    const button = $('#load-more');
    const nextPageUrl = button.data('next-page');

    if (!nextPageUrl) return;

    isLoading = true;
    const link = button.find('[data-load-more]');
    button.attr('aria-busy', 'true');
    button.find('[role="status"]').text('');

    $.get(nextPageUrl)
        .done(function(data) {
            const newItems = $(data).find('.infinite-item');
            $('.infinite-container').append(newItems);

            const newNextPageUrl = $(data).find('#load-more').data('next-page');
            if (newNextPageUrl) {
                button.data('next-page', newNextPageUrl);
                link.attr('href', newNextPageUrl);
            } else {
                const restoreFocus = manual || document.activeElement === link[0];
                button.remove();
                if (restoreFocus) newItems.find('a[href]').first().trigger('focus');
            }

            initializeNewElements(newItems);
        })
        .fail(function(error) {
            button.find('[role="status"]').text(gettext('Fehler beim Laden der Daten.'));
            console.error('Fehler beim Laden weiterer Inhalte:', error);
        })
        .always(function() {
            isLoading = false;
            button.removeAttr('aria-busy');
        });
}

function initializeNewElements($items) {
    $items.find('.hovereffect').on('click', 'a', function(e) {
        e.stopPropagation();
        window.location.href = $(this).attr('href');
    });
}
