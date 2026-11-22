function escHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
function safeUrl(value) {
  const url = String(value ?? '').trim();
  if (/^https?:\/\//i.test(url) || (url.startsWith('/') && !url.startsWith('//'))) {
    return url;
  }
  return '#';
}
document.addEventListener('DOMContentLoaded', function() {
  const coinsContainer = document.getElementById('coinsContainer');
  const coinsIndicators = document.getElementById('coinsProgressIndicators');
  const coinsProgressText = document.getElementById('coinsProgressText');
  if (coinsContainer && coinsIndicators && coinsProgressText) {
    const coinItems = Array.from(coinsContainer.children).filter((item) => item.classList.contains('infinite-item'));
    if (coinItems.length > 0) {
      if (coinItems.length > 1) {
        coinsIndicators.innerHTML = coinItems.map((_, index) => `<span class="coins-progress-indicator${index === 0 ? ' is-active' : ''}"></span>`).join('');
      }
      const indicatorDots = Array.from(coinsIndicators.children);
      let indicatorFrame = null;

      const updateCoinIndicator = () => {
        const containerLeft = coinsContainer.getBoundingClientRect().left;
        let activeIndex = 0;
        let closestDistance = Number.POSITIVE_INFINITY;

        coinItems.forEach((item, index) => {
          const distance = Math.abs(item.getBoundingClientRect().left - containerLeft);
          if (distance < closestDistance) {
            closestDistance = distance;
            activeIndex = index;
          }
        });

        indicatorDots.forEach((dot, index) => {
          dot.classList.toggle('is-active', index === activeIndex);
        });

        coinsProgressText.textContent = interpolate(gettext('%(current)s von %(total)s'), {current: activeIndex + 1, total: coinItems.length}, true);
      };

      if (coinItems.length > 1) {
        coinsContainer.addEventListener('scroll', () => {
          if (indicatorFrame) {
            cancelAnimationFrame(indicatorFrame);
          }
          indicatorFrame = requestAnimationFrame(updateCoinIndicator);
        }, { passive: true });
      }

      window.addEventListener('resize', updateCoinIndicator);
      updateCoinIndicator();
    }
  }

  const grid = document.getElementById('collectionsGrid');
  if (grid) {
    fetch('/api/collections/').then(r => r.json()).then(colls => {
      grid.innerHTML = colls.map(col => `
        <div class="prem-collection-card">
          <div class="prem-col-img-wrapper">
            ${col.cover ? `<img src="${escHtml(safeUrl(col.cover))}" alt="${escHtml(col.name)}">` : `<i class="bi bi-collection collection-placeholder"></i>`}
          </div>
          <div class="prem-col-content">
            <h4 class="prem-col-title">${escHtml(col.name)}</h4>
            <p class="prem-col-desc">${col.beschreibung ? escHtml(col.beschreibung.substring(0, 100)) + '...' : ''}</p>
            <div class="prem-col-footer">
              <a href="${escHtml(safeUrl(col.absolute_url))}" class="prem-col-link"><i class="bi bi-clock-history"></i> ${gettext("Zeitleiste")}</a>
              <a href="/browse/?q=&Slg=${encodeURIComponent(col.id)}" class="prem-col-link"><i class="bi bi-search"></i> ${gettext("Objekte")}</a>
            </div>
          </div>
        </div>
      `).join('');
    });
  }

  function animateValue(el, start, end, duration) {
    if (!el) return;
    let t0 = null;
    const step = (ts) => {
      if (!t0) t0 = ts;
      const p = Math.min((ts - t0) / duration, 1);
      el.textContent = Math.floor(p * (end - start) + start);
      if (p < 1) requestAnimationFrame(step);
      else el.textContent = end;
    };
    requestAnimationFrame(step);
  }

  const statsCard = document.getElementById('statsCard');
  if (statsCard) {
    fetch('/api/stats/').then(r => r.json()).then(data => {
      const map = {
        statObjekte: data.anzahl_qs,
        statMuenztypen: data.anzahl_mt,
        statPersonen: data.anzahl_person,
        statMstaetten: data.anzahl_mstaetten
      };
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting && !entry.target.classList.contains('animated')) {
            entry.target.classList.add('animated');
            Object.entries(map).forEach(([id, val]) => {
              animateValue(document.getElementById(id), 0, val, 1500);
            });
          }
        });
      }, { threshold: 0.3 });
      observer.observe(statsCard);
    });
  }

  const avWordcloudDataElement = document.getElementById('av-wordcloud-data');
  const rvWordcloudDataElement = document.getElementById('rv-wordcloud-data');
  const avWordcloudData = avWordcloudDataElement ? JSON.parse(avWordcloudDataElement.textContent) : [];
  const rvWordcloudData = rvWordcloudDataElement ? JSON.parse(rvWordcloudDataElement.textContent) : [];

  function renderWordcloud(containerId, metaId, words, accentColor) {
    const container = document.getElementById(containerId);
    const meta = document.getElementById(metaId);
    if (!container) {
      return;
    }

    container.innerHTML = '';

    if (meta) {
      const totalOccurrences = words.reduce((sum, word) => sum + Number(word.value || 0), 0);
      meta.textContent = words.length ? `${words.length} ${gettext('Schlagworte')} · ${totalOccurrences} ${gettext('Zuordnungen')}` : gettext("Keine Schlagworte verfügbar");
    }

    if (!words.length) {
      container.innerHTML = '<div class="wordcloud-fallback"><span class="wordcloud-card-subtitle">' + gettext("Keine Schlagworte verfügbar.") + '</span></div>';
      return;
    }

    if (!window.d3) {
      container.innerHTML = `<div class="wordcloud-fallback">${words.slice(0, 24).map(word => `<a class="wordcloud-fallback-tag" href="${escHtml(safeUrl(word.url))}">${escHtml(word.text)}<span>${escHtml(word.value)}</span></a>`).join('')}</div>`;
      return;
    }

    const width = Math.max(container.clientWidth, 280);
    const height = Math.max(container.clientHeight, 300);
    const values = words.map(word => Number(word.value || 0));
    const minValue = d3.min(values) || 1;
    const maxValue = d3.max(values) || 1;
    const fontScale = d3.scaleSqrt().domain([minValue, maxValue]).range(minValue === maxValue ? [34, 34] : [16, 60]);
    const colorScale = d3.scaleLinear().domain([minValue, maxValue]).range(['#9f9f9f', accentColor]);
    const layoutWords = words.map(word => ({
      ...word,
      size: fontScale(Number(word.value || 0)),
      weight: Number(word.value || 0) > ((minValue + maxValue) / 2) ? 700 : 500,
    })).sort((a, b) => b.size - a.size);

    const measureCanvas = document.createElement('canvas');
    const measureContext = measureCanvas.getContext('2d');
    const placedBounds = [];
    const padding = 8;

    const positionedWords = layoutWords.map(word => {
      measureContext.font = `${word.weight} ${word.size}px Plus Jakarta Sans, Segoe UI, sans-serif`;
      const wordWidth = measureContext.measureText(word.text).width;
      const wordHeight = word.size * 0.9;
      const maxRadius = Math.max(width, height);
      let radius = 0;
      let angle = 0;

      while (radius <= maxRadius) {
        const x = (width / 2) + (Math.cos(angle) * radius);
        const y = (height / 2) + (Math.sin(angle) * radius);
        const bounds = {
          left: x - (wordWidth / 2) - padding,
          right: x + (wordWidth / 2) + padding,
          top: y - (wordHeight / 2) - padding,
          bottom: y + (wordHeight / 2) + padding,
        };
        const fitsWithinCanvas = bounds.left >= 0 && bounds.right <= width && bounds.top >= 0 && bounds.bottom <= height;
        const collides = placedBounds.some(box => !(bounds.right < box.left || bounds.left > box.right || bounds.bottom < box.top || bounds.top > box.bottom));

        if (fitsWithinCanvas && !collides) {
          placedBounds.push(bounds);
          return {
            ...word,
            x,
            y,
          };
        }

        angle += 0.35;
        radius += 0.9;
      }

      return null;
    }).filter(Boolean);

    if (!positionedWords.length) {
      container.innerHTML = `<div class="wordcloud-fallback">${words.slice(0, 24).map(word => `<a class="wordcloud-fallback-tag" href="${escHtml(safeUrl(word.url))}">${escHtml(word.text)}<span>${escHtml(word.value)}</span></a>`).join('')}</div>`;
      return;
    }

    const svg = d3.select(container)
      .append('svg')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('preserveAspectRatio', 'xMidYMid meet');

    const links = svg.selectAll('a')
      .data(positionedWords)
      .enter()
      .append('a')
      .attr('href', word => safeUrl(word.url));

    links.append('text')
      .attr('class', 'wordcloud-word')
      .style('font-family', 'Plus Jakarta Sans, Segoe UI, sans-serif')
      .style('font-size', word => `${word.size}px`)
      .style('font-weight', word => word.weight)
      .style('fill', word => colorScale(Number(word.value || 0)))
      .attr('text-anchor', 'middle')
      .attr('x', word => word.x)
      .attr('y', word => word.y)
      .attr('dominant-baseline', 'middle')
      .text(word => word.text);

    links.append('title')
      .text(word => `${word.text}: ${word.value}`);
  }

  let wordcloudResizeFrame = null;
  const renderAllWordclouds = () => {
    renderWordcloud('avWordcloud', 'avWordcloudMeta', avWordcloudData, '#f6b15d');
    renderWordcloud('rvWordcloud', 'rvWordcloudMeta', rvWordcloudData, '#d9b27a');
  };

  renderAllWordclouds();
  window.addEventListener('resize', () => {
    if (wordcloudResizeFrame) {
      cancelAnimationFrame(wordcloudResizeFrame);
    }
    wordcloudResizeFrame = requestAnimationFrame(renderAllWordclouds);
  });
});
