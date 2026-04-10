"""Dashboard generator: Reads pre-aggregated JSON files and creates a self-contained HTML dashboard."""

import json
from pathlib import Path
from typing import Any

from csfd_vod.logger import get_logger

logger = get_logger(__name__)

_JSON_FILES = [
    "summary", "genres", "directors", "actors", "countries",
    "platforms", "tags", "rating_distribution", "vod_by_month", "top_titles",
]

DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CSFD VOD Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f0f2f5;
            min-height: 100vh;
            padding: 24px;
            color: #1a1a2e;
        }

        .container { max-width: 1400px; margin: 0 auto; }

        header {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 16px;
            padding: 32px;
            margin-bottom: 24px;
            color: white;
        }

        header h1 { font-size: 2rem; font-weight: 700; margin-bottom: 4px; }
        header p { opacity: 0.7; font-size: 0.9rem; }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
            margin-top: 24px;
        }

        .stat {
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
            padding: 14px 16px;
        }
        .stat-value { font-size: 1.6rem; font-weight: 700; }
        .stat-label { font-size: 0.75rem; opacity: 0.7; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.05em; }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }

        .card {
            background: white;
            border-radius: 14px;
            padding: 24px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        }

        .card.full { grid-column: 1 / -1; }

        .card h3 {
            font-size: 1rem;
            font-weight: 600;
            color: #444;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 2px solid #f0f0f0;
        }

        .chart { width: 100%; height: 380px; }
        .chart-tall { width: 100%; height: 500px; }

        /* Top titles table */
        .titles-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
        .titles-table th {
            text-align: left; padding: 10px 12px;
            background: #f8f9fa; border-bottom: 2px solid #e9ecef;
            font-weight: 600; color: #555;
        }
        .titles-table td { padding: 9px 12px; border-bottom: 1px solid #f0f0f0; }
        .titles-table tr:last-child td { border-bottom: none; }
        .titles-table tr:hover td { background: #fafafa; }
        .rating-badge {
            display: inline-block; padding: 2px 8px;
            border-radius: 12px; font-weight: 700; font-size: 0.8rem;
            background: #e8f5e9; color: #2e7d32;
        }
        .rating-badge.mid { background: #fff8e1; color: #f57f17; }
        .rating-badge.low { background: #fce4ec; color: #c62828; }

        footer {
            background: white; border-radius: 14px; padding: 18px 24px;
            text-align: center; color: #888; font-size: 0.85rem;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06); margin-top: 20px;
        }

        @media (max-width: 768px) {
            .grid { grid-template-columns: 1fr; }
            body { padding: 12px; }
        }
    </style>
</head>
<body>
<div class="container">

    <header>
        <h1>CSFD VOD Dashboard</h1>
        <p>Analýza titulov na VOD platformách — zdroj: csfd.cz</p>
        <div class="stats-grid" id="stats-grid"></div>
    </header>

    <div class="grid">
        <div class="card">
            <h3>Top 30 zanrov</h3>
            <div class="chart" id="chart-genres"></div>
        </div>
        <div class="card">
            <h3>VOD platformy</h3>
            <div class="chart" id="chart-platforms"></div>
        </div>
        <div class="card">
            <h3>Top 30 rezisérov</h3>
            <div class="chart" id="chart-directors"></div>
        </div>
        <div class="card">
            <h3>Top 30 hercov</h3>
            <div class="chart" id="chart-actors"></div>
        </div>
        <div class="card">
            <h3>Krajiny pôvodu</h3>
            <div class="chart" id="chart-countries"></div>
        </div>
        <div class="card">
            <h3>Distribúcia hodnotenia (0–100 %)</h3>
            <div class="chart" id="chart-rating"></div>
        </div>
        <div class="card full">
            <h3>Prírastky na VOD po mesiacoch (posledné 3 roky)</h3>
            <div class="chart" id="chart-vod-months"></div>
        </div>
        <div class="card full">
            <h3>Top 100 titulov podla hodnotenia</h3>
            <div id="top-titles-table"></div>
        </div>
    </div>

    <footer>
        Vygenerované <span id="ts"></span> | Dáta: csfd.cz
    </footer>
</div>

<script>
const D = {DATA_PLACEHOLDER};

const COLORS = {
    primary: '#1a1a2e',
    accent:  '#e94560',
    blue:    '#0f3460',
    green:   '#2ecc71',
    orange:  '#f39c12',
    purple:  '#9b59b6',
    palette: ['#1a1a2e','#0f3460','#e94560','#533483','#2ecc71','#f39c12','#3498db','#e74c3c','#1abc9c','#9b59b6'],
};

const cfg = { responsive: true, displayModeBar: false };

function fmt(n) { return n ? n.toLocaleString('sk') : '0'; }

// --- Header stats ---
function renderStats() {
    const s = D.summary;
    const items = [
        ['Titulov celkom', fmt(s.total_titles)],
        ['Filmov', fmt(s.total_films)],
        ['Seriálov', fmt(s.total_serials)],
        ['Žánrov', fmt(s.total_genres)],
        ['Platforiem', fmt(s.total_platforms)],
        ['Krajín', fmt(s.total_countries)],
        ['Priemerný rating', s.avg_rating ? s.avg_rating + ' %' : '–'],
    ];
    document.getElementById('stats-grid').innerHTML = items
        .map(([label, value]) => `<div class="stat"><div class="stat-value">${value}</div><div class="stat-label">${label}</div></div>`)
        .join('');
    const ts = new Date(s.export_timestamp);
    document.getElementById('ts').textContent = ts.toLocaleString('sk');
}

// --- Horizontal bar chart helper ---
function hbar(divId, data, colorIdx = 0) {
    const trace = {
        x: data.map(d => d.count),
        y: data.map(d => d.name),
        type: 'bar', orientation: 'h',
        marker: { color: COLORS.palette[colorIdx % COLORS.palette.length] },
    };
    Plotly.newPlot(divId, [trace], {
        margin: { l: 200, r: 20, t: 10, b: 40 },
        xaxis: { title: 'Počet titulov' },
        yaxis: { automargin: true },
        paper_bgcolor: 'white', plot_bgcolor: 'white',
    }, cfg);
}

// --- Pie chart helper ---
function pie(divId, data, colorIdx = 0) {
    const trace = {
        labels: data.map(d => d.name),
        values: data.map(d => d.count),
        type: 'pie',
        marker: { colors: COLORS.palette },
        textinfo: 'label+percent',
        hovertemplate: '%{label}: %{value}<extra></extra>',
    };
    Plotly.newPlot(divId, [trace], {
        margin: { l: 20, r: 20, t: 10, b: 10 },
        paper_bgcolor: 'white',
    }, cfg);
}

// --- Charts ---
function renderGenres()    { hbar('chart-genres',    D.genres,    0); }
function renderDirectors() { hbar('chart-directors', D.directors, 1); }
function renderActors()    { hbar('chart-actors',    D.actors,    2); }

function renderPlatforms() { pie('chart-platforms', D.platforms); }
function renderCountries() { pie('chart-countries', D.countries.slice(0, 20)); }

function renderRating() {
    const data = D.rating_distribution;
    Plotly.newPlot('chart-rating', [{
        x: data.map(d => d.bucket),
        y: data.map(d => d.count),
        type: 'bar',
        marker: {
            color: data.map(d => {
                const mid = parseInt(d.bucket);
                return mid >= 70 ? COLORS.green : mid >= 50 ? COLORS.orange : COLORS.accent;
            }),
        },
    }], {
        margin: { l: 50, r: 20, t: 10, b: 50 },
        xaxis: { title: 'Hodnotenie (%)' },
        yaxis: { title: 'Počet titulov' },
        paper_bgcolor: 'white', plot_bgcolor: 'white',
    }, cfg);
}

function renderVodMonths() {
    const data = D.vod_by_month;
    Plotly.newPlot('chart-vod-months', [{
        x: data.map(d => d.month),
        y: data.map(d => d.count),
        type: 'scatter', mode: 'lines+markers',
        fill: 'tozeroy',
        line: { color: COLORS.blue, width: 2 },
        marker: { size: 5, color: COLORS.blue },
    }], {
        margin: { l: 50, r: 20, t: 10, b: 60 },
        xaxis: { title: 'Mesiac' },
        yaxis: { title: 'Nové tituly' },
        paper_bgcolor: 'white', plot_bgcolor: '#fafafa',
    }, cfg);
}

function ratingBadgeClass(r) {
    if (!r) return '';
    if (r >= 70) return 'rating-badge';
    if (r >= 50) return 'rating-badge mid';
    return 'rating-badge low';
}

function renderTopTitles() {
    const titles = D.top_titles;
    const rows = titles.map((t, i) =>
        `<tr>
            <td>${i + 1}</td>
            <td><a href="${t.link}" target="_blank" rel="noopener">${t.title}</a>${t.title_en && t.title_en !== t.title ? ` <small style="color:#888">(${t.title_en})</small>` : ''}</td>
            <td>${t.year || '–'}</td>
            <td>${t.rating !== null ? `<span class="${ratingBadgeClass(t.rating)}">${t.rating} %</span>` : '–'}</td>
            <td>${(t.genres || []).slice(0, 2).join(', ') || '–'}</td>
            <td>${t.distributor || '–'}</td>
            <td>${t.vod_date ? t.vod_date.slice(0, 7) : '–'}</td>
        </tr>`
    ).join('');

    document.getElementById('top-titles-table').innerHTML = `
        <table class="titles-table">
            <thead><tr>
                <th>#</th><th>Titul</th><th>Rok</th><th>Rating</th><th>Žánre</th><th>Platforma</th><th>VOD od</th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
}

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
    try {
        renderStats();
        renderGenres();
        renderPlatforms();
        renderDirectors();
        renderActors();
        renderCountries();
        renderRating();
        renderVodMonths();
        renderTopTitles();
    } catch (err) {
        console.error('Dashboard render error:', err);
    }
});
</script>
</body>
</html>
"""


class DashboardGenerator:
    """Generate HTML dashboard from pre-aggregated JSON files."""

    def generate(self, data_dir: str, output_html: str) -> dict[str, Any]:
        """
        Read JSON files from data_dir and write a self-contained HTML dashboard.

        Args:
            data_dir: Directory containing the JSON files written by DataExporter
            output_html: Path to write the HTML file

        Returns:
            Dict with generation statistics
        """
        data_dir_path = Path(data_dir)
        output_path = Path(output_html)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Load all JSON files into a single dict
        data: dict[str, Any] = {}
        for name in _JSON_FILES:
            json_path = data_dir_path / f"{name}.json"
            if json_path.exists():
                data[name] = json.loads(json_path.read_text(encoding="utf-8"))
            else:
                data[name] = {} if name == "summary" else []
                logger.warning("json_file_missing", file=str(json_path))

        # Embed data in HTML template
        html = DASHBOARD_TEMPLATE.replace(
            "{DATA_PLACEHOLDER}",
            json.dumps(data, ensure_ascii=False),
        )
        output_path.write_text(html, encoding="utf-8")

        total_titles = data.get("summary", {}).get("total_titles", 0)
        result = {
            "success": True,
            "output_path": str(output_path.absolute()),
            "file_size_kb": round(output_path.stat().st_size / 1024, 1),
            "total_titles": total_titles,
        }
        logger.info("dashboard_generated", **result)
        return result
