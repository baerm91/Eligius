// Infinite Scroll Funktionalität

// FIX: isLoading muss im globalen Scope stehen!
let isLoading = false;

$(document).ready(function() {
    initializeInfiniteScroll();
});

function initializeInfiniteScroll() {
    const loadMoreElement = document.getElementById('load-more');
    
    if (loadMoreElement) {
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

function loadMoreContent() {
    if (isLoading) return;
    
    const button = $('#load-more');
    const nextPageUrl = button.data('next-page');
    
    if (!nextPageUrl) return;
    
    isLoading = true;
    
    $.get(nextPageUrl)
        .done(function(data) {
            const newItems = $(data).find('.infinite-item');
            $('.infinite-container').append(newItems);
            
            const newNextPageUrl = $(data).find('#load-more').data('next-page');
            if (newNextPageUrl) {
                button.data('next-page', newNextPageUrl);
            } else {
                button.remove();
            }
            
            initializeNewElements(newItems);
        })
        .fail(function(error) {
            console.error('Fehler beim Laden weiterer Inhalte:', error);
        })
        .always(function() {
            isLoading = false;
        });
}

function initializeNewElements($items) {
    $items.find('.hovereffect').on('click', 'a', function(e) {
        e.stopPropagation();
        window.location.href = $(this).attr('href');
    });
} 