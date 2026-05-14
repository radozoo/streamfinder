"""CLI for VOD dashboard generation."""

import argparse
import json
from pathlib import Path

from csfd_vod.config import load_config_from_env
from csfd_vod.export.exporter import DataExporter
from csfd_vod.export.dashboard_generator import DashboardGenerator
from csfd_vod.logger import get_logger

logger = get_logger(__name__)


def main():
    """Main CLI entry point for dashboard generation."""
    parser = argparse.ArgumentParser(
        description="Generate VOD dashboard from PostgreSQL data"
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="dashboard",
        help="Output directory for dashboard (default: dashboard)",
    )

    parser.add_argument(
        "--data-export",
        type=str,
        help="Path to JSON data export (if not provided, will export from DB)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (test without writing files)",
    )

    args = parser.parse_args()

    try:
        logger.info("dashboard_generation_started", output_dir=args.output_dir)

        # Load configuration
        config = load_config_from_env()

        # Create output directory
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Export data from database (unless provided)
        if args.data_export:
            logger.info("loading_data_from_file", path=args.data_export)
            with open(args.data_export, "r", encoding="utf-8") as f:
                data = json.load(f)
            export_stats = {"file_size_kb": Path(args.data_export).stat().st_size / 1024}
        else:
            logger.info("exporting_data_from_database")
            exporter = DataExporter(config.database.connection_string)

            # Export to temporary JSON file
            json_path = output_dir / "data.json"
            export_stats = exporter.export_to_json(str(json_path))

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        logger.info("data_exported", **export_stats)

        # Step 2: Generate dashboard
        logger.info("generating_dashboard")
        generator = DashboardGenerator()

        html_path = output_dir / "index.html"

        if not args.dry_run:
            dashboard_stats = generator.generate(data, str(html_path))
            logger.info("dashboard_generated", **dashboard_stats)

            print(f"\n✅ Dashboard generated successfully!")
            print(f"📊 Output: {html_path.absolute()}")
            print(f"📈 Titles: {data['metadata']['total_titles']}")
            print(f"📁 File size: {dashboard_stats['file_size_kb']:.1f} KB")
            print(f"\n🌐 Open in browser: file://{html_path.absolute()}")
        else:
            print(f"\n✅ Dry-run completed successfully!")
            print(f"📊 Would generate: {html_path}")
            print(f"📈 Titles: {data['metadata']['total_titles']}")

        return {
            "success": True,
            "output_dir": str(output_dir.absolute()),
            "data_exported": export_stats,
            "html_path": str(html_path.absolute()) if not args.dry_run else None,
        }

    except Exception as e:
        logger.error("dashboard_generation_failed", error=str(e))
        print(f"\n❌ Error: {str(e)}")
        raise


if __name__ == "__main__":
    main()
