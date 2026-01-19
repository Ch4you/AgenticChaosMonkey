#!/usr/bin/env python3
"""
Generate Resilience Scorecard

Analyzes proxy logs and test run data to generate resilience reports.

Usage:
    python src/reporter/generate.py [--log-file path/to/log] [--output-dir output/]
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.reporter.scorecard import ScorecardGenerator


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Resilience Scorecard from Chaos Testing Logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (auto-find logs)
  python src/reporter/generate.py
  
  # Specify log file
  python src/reporter/generate.py --log-file logs/proxy.log
  
  # Custom output directory
  python src/reporter/generate.py --output-dir reports/
        """
    )
    
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to proxy log file (default: auto-detect)"
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default="logs",
        help="Directory to search for log files"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Output directory for reports"
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Only generate JSON report"
    )
    parser.add_argument(
        "--md-only",
        action="store_true",
        help="Only generate Markdown report"
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("Resilience Scorecard Generator")
    print("="*70 + "\n")
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create generator
    generator = ScorecardGenerator(
        log_file=args.log_file,
        log_dir=args.log_dir
    )
    
    # Analyze once and reuse results
    scorecard = generator.analyze()
    
    # Generate reports (reuse analyzed scorecard to avoid re-analysis)
    if not args.md_only:
        json_path = output_dir / "resilience_report.json"
        generator.generate_json_report(str(json_path), scorecard=scorecard)
        print(f"✓ JSON report: {json_path}")
    
    if not args.json_only:
        md_path = output_dir / "resilience_report.md"
        generator.generate_markdown_report(str(md_path), scorecard=scorecard)
        print(f"✓ Markdown report: {md_path}")
    
    # Display summary (use already analyzed scorecard)
    grade = scorecard.get("grade", "N/A")
    score = scorecard.get("metrics", {}).get("resilience_score", 0)
    summary = scorecard.get("summary", {})
    
    print("\n" + "="*70)
    print("Scorecard Summary")
    print("="*70 + "\n")
    print(f"Grade: {grade}")
    print(f"Resilience Score: {score:.1f}/100\n")
    
    for key, value in summary.items():
        if key != "grade":
            print(f"  {key.replace('_', ' ').title()}: {value}")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    main()

