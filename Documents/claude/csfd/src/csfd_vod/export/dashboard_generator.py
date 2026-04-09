"""Dashboard generator: Creates HTML dashboard from JSON data."""

import json
import shutil
from pathlib import Path
from typing import Dict, Any

from csfd_vod.logger import get_logger

logger = get_logger(__name__)

# HTML template with embedded Plotly.js visualizations
DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CSFD VOD Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        header {{
            background: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
        }}

        h1 {{
            font-size: 2.5em;
            color: #333;
            margin-bottom: 10px;
        }}

        .metadata {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}

        .stat {{
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}

        .stat-value {{
            font-size: 1.8em;
            font-weight: bold;
            color: #667eea;
        }}

        .stat-label {{
            font-size: 0.9em;
            color: #666;
            margin-top: 5px;
        }}

        .dashboard {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .chart-container {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}

        .chart-container h3 {{
            font-size: 1.2em;
            color: #333;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #f0f0f0;
        }}

        .chart {{
            width: 100%;
            height: 400px;
        }}

        .full-width {{
            grid-column: 1 / -1;
        }}

        footer {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            color: #666;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            margin-top: 30px;
        }}

        @media (max-width: 768px) {{
            .dashboard {{
                grid-template-columns: 1fr;
            }}

            h1 {{
                font-size: 1.8em;
            }}

            .chart {{
                height: 300px;
            }}
        }}

        .loading {{
            text-align: center;
            padding: 40px;
            color: white;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎬 CSFD VOD Dashboard</h1>
            <p>Interactive analysis of VOD titles on Czech Film Database</p>

            <div class="metadata">
                <div class="stat">
                    <div class="stat-value" id="total-titles">-</div>
                    <div class="stat-label">Total Titles</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="total-genres">-</div>
                    <div class="stat-label">Genres</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="total-directors">-</div>
                    <div class="stat-label">Directors</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="total-countries">-</div>
                    <div class="stat-label">Countries</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="total-platforms">-</div>
                    <div class="stat-label">Platforms</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="export-time">-</div>
                    <div class="stat-label">Export Time</div>
                </div>
            </div>
        </header>

        <div class="dashboard">
            <div class="chart-container">
                <h3>📊 Top 20 Genres</h3>
                <div class="chart" id="genres-chart"></div>
            </div>

            <div class="chart-container">
                <h3>🌍 Top Countries</h3>
                <div class="chart" id="countries-chart"></div>
            </div>

            <div class="chart-container">
                <h3>🎬 Titles by Decade</h3>
                <div class="chart" id="decade-chart"></div>
            </div>

            <div class="chart-container">
                <h3>📺 VOD Platform Coverage</h3>
                <div class="chart" id="platforms-chart"></div>
            </div>

            <div class="chart-container full-width">
                <h3>📈 Titles by Year (Last 50 Years)</h3>
                <div class="chart" id="years-chart" style="height: 300px;"></div>
            </div>

            <div class="chart-container full-width">
                <h3>🎯 Distribution Summary</h3>
                <div class="chart" id="summary-stats" style="height: 300px;"></div>
            </div>
        </div>

        <footer>
            <p>Generated on <span id="timestamp">-</span> | Data source: csfd.cz</p>
        </footer>
    </div>

    <script>
        const DATA = {DATA_PLACEHOLDER};

        function formatDate(isoString) {{
            const date = new Date(isoString);
            return date.toLocaleString('en-US', {{
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                timeZone: 'UTC'
            }});
        }}

        function updateMetadata() {{
            const meta = DATA.metadata;
            document.getElementById('total-titles').textContent = meta.total_titles.toLocaleString();
            document.getElementById('total-genres').textContent = meta.total_genres.toLocaleString();
            document.getElementById('total-directors').textContent = meta.total_directors.toLocaleString();
            document.getElementById('total-countries').textContent = meta.total_countries.toLocaleString();
            document.getElementById('total-platforms').textContent = meta.total_platforms.toLocaleString();
            document.getElementById('export-time').textContent = formatDate(meta.export_timestamp);
            document.getElementById('timestamp').textContent = formatDate(meta.export_timestamp);
        }}

        function plotGenres() {{
            const stats = DATA.statistics.genres_by_count;
            const trace = {{
                x: stats.map(s => s.count),
                y: stats.map(s => s.name),
                type: 'bar',
                orientation: 'h',
                marker: {{ color: '#667eea' }}
            }};

            const layout = {{
                margin: {{ l: 200, r: 20, t: 20, b: 40 }},
                xaxis: {{ title: 'Number of Titles' }},
                yaxis: {{ automargin: true }},
                hovermode: 'closest'
            }};

            Plotly.newPlot('genres-chart', [trace], layout, {{ responsive: true }});
        }}

        function plotCountries() {{
            const stats = DATA.statistics.countries_by_count;
            const trace = {{
                labels: stats.map(s => s.name),
                values: stats.map(s => s.count),
                type: 'pie',
                marker: {{ colorscale: 'Viridis' }}
            }};

            const layout = {{
                height: 400,
                margin: {{ l: 50, r: 50, t: 50, b: 50 }},
                hovermode: 'closest'
            }};

            Plotly.newPlot('countries-chart', [trace], layout, {{ responsive: true }});
        }}

        function plotDecades() {{
            const stats = DATA.statistics.decade_distribution;
            const trace = {{
                x: stats.map(s => s.decade),
                y: stats.map(s => s.count),
                type: 'bar',
                marker: {{ color: '#764ba2' }}
            }};

            const layout = {{
                margin: {{ l: 50, r: 20, t: 20, b: 40 }},
                xaxis: {{ title: 'Decade' }},
                yaxis: {{ title: 'Number of Titles' }},
                hovermode: 'closest'
            }};

            Plotly.newPlot('decade-chart', [trace], layout, {{ responsive: true }});
        }}

        function plotPlatforms() {{
            const stats = DATA.statistics.platforms_by_count;
            const trace = {{
                x: stats.map(s => s.count),
                y: stats.map(s => s.name),
                type: 'bar',
                orientation: 'h',
                marker: {{ color: '#f0ad4e' }}
            }};

            const layout = {{
                margin: {{ l: 150, r: 20, t: 20, b: 40 }},
                xaxis: {{ title: 'Number of Titles' }},
                yaxis: {{ automargin: true }},
                hovermode: 'closest'
            }};

            Plotly.newPlot('platforms-chart', [trace], layout, {{ responsive: true }});
        }}

        function plotYears() {{
            const stats = DATA.statistics.years_by_count.reverse();
            const trace = {{
                x: stats.map(s => s.year),
                y: stats.map(s => s.count),
                type: 'scatter',
                mode: 'lines+markers',
                fill: 'tozeroy',
                line: {{ color: '#667eea', width: 3 }},
                marker: {{ size: 4 }}
            }};

            const layout = {{
                margin: {{ l: 50, r: 20, t: 20, b: 40 }},
                xaxis: {{ title: 'Year' }},
                yaxis: {{ title: 'Number of Titles' }},
                hovermode: 'closest',
                plot_bgcolor: '#f8f9fa',
                paper_bgcolor: 'white'
            }};

            Plotly.newPlot('years-chart', [trace], layout, {{ responsive: true }});
        }}

        function plotSummary() {{
            const stats = DATA.statistics;
            const labels = ['Top Genres', 'Countries', 'Platforms'];
            const values = [
                stats.genres_by_count.slice(0, 3).reduce((sum, s) => sum + s.count, 0),
                stats.countries_by_count.slice(0, 3).reduce((sum, s) => sum + s.count, 0),
                stats.platforms_by_count.slice(0, 3).reduce((sum, s) => sum + s.count, 0)
            ];

            const trace = {{
                labels: labels,
                values: values,
                type: 'pie',
                marker: {{ colors: ['#667eea', '#764ba2', '#f0ad4e'] }}
            }};

            const layout = {{
                height: 300,
                margin: {{ l: 50, r: 50, t: 50, b: 50 }},
                hovermode: 'closest'
            }};

            Plotly.newPlot('summary-stats', [trace], layout, {{ responsive: true }});
        }}

        // Initialize on load
        document.addEventListener('DOMContentLoaded', function() {{
            try {{
                updateMetadata();
                plotGenres();
                plotCountries();
                plotDecades();
                plotPlatforms();
                plotYears();
                plotSummary();
            }} catch (error) {{
                console.error('Error rendering dashboard:', error);
                alert('Error rendering dashboard. Check console for details.');
            }}
        }});
    </script>
</body>
</html>
"""


class DashboardGenerator:
    """Generate HTML dashboard from JSON data export."""

    def __init__(self):
        """Initialize dashboard generator."""
        pass

    def generate(self, data_json: Dict[str, Any], output_path: str) -> Dict[str, Any]:
        """
        Generate HTML dashboard from JSON data.

        Args:
            data_json: Exported data dictionary (from DataExporter)
            output_path: Path to write HTML file

        Returns:
            Dict with generation statistics
        """
        try:
            # Create output directory
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)

            # Prepare dashboard content with data embedded
            data_json_str = json.dumps(data_json, ensure_ascii=False, indent=2)
            dashboard_html = DASHBOARD_TEMPLATE.replace("{DATA_PLACEHOLDER}", data_json_str)

            # Write HTML file
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(dashboard_html)

            result = {
                "success": True,
                "output_path": str(output_path_obj.absolute()),
                "file_size_kb": output_path_obj.stat().st_size / 1024,
                "titles_rendered": data_json["metadata"]["total_titles"],
            }

            logger.info("dashboard_generated", **result)
            return result

        except Exception as e:
            logger.error("dashboard_generation_failed", error=str(e))
            raise
