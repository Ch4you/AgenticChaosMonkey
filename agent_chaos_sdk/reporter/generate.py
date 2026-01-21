#!/usr/bin/env python3
"""
Generate Compliance Audit Report

Analyzes proxy logs and test run data to generate compliance audit reports.

Usage:
    python -m agent_chaos_sdk.reporter.generate [--log-file path/to/log] [--output-dir output/]
"""

import argparse
from pathlib import Path

from agent_chaos_sdk.reporter.scorecard import ScorecardGenerator


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Compliance Audit Report from Chaos Testing Logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (auto-find logs)
  python -m agent_chaos_sdk.reporter.generate

  # Specify log file
  python -m agent_chaos_sdk.reporter.generate --log-file logs/proxy.log

  # Custom output directory
  python -m agent_chaos_sdk.reporter.generate --output-dir reports/
        """,
    )

    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to proxy log file (default: auto-detect)",
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default="logs",
        help="Directory to search for log files",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Output directory for reports",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Only generate JSON report",
    )
    parser.add_argument(
        "--md-only",
        action="store_true",
        help="Only generate Markdown report",
    )

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("Compliance Audit Report Generator")
    print("=" * 70 + "\n")

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create generator
    generator = ScorecardGenerator(log_file=args.log_file, log_dir=args.log_dir)

    # Analyze logs
    report_data = generator.analyze()

    # Generate JSON report
    if not args.md_only:
        json_path = output_dir / "compliance_audit_report.json"
        generator.generate_json_report(str(json_path), scorecard=report_data)
        print(f"✅ JSON report saved to: {json_path}")

    # Generate Markdown report
    if not args.json_only:
        md_path = output_dir / "compliance_audit_report.md"
        generator.generate_markdown_report(str(md_path), scorecard=report_data)
        print(f"✅ Markdown report saved to: {md_path}")

    print("\nReport generation complete.")


if __name__ == "__main__":
    main()
