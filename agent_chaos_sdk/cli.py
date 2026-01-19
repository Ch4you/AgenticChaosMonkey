#!/usr/bin/env python3
"""
Professional CLI for Agent Chaos Platform

This module provides a beautiful, interactive command-line interface using
typer and rich for managing chaos experiments.
"""

import sys
import os
import subprocess
import signal
import time
import json
import importlib.util
import shlex
import re
import threading
import tarfile
import zipfile
from pathlib import Path
from typing import Optional
from datetime import datetime

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.align import Align
from rich.rule import Rule
from rich import box

import httpx

from agent_chaos_sdk.config_loader import (
    load_chaos_plan,
    set_global_plan,
    ChaosPlan,
    TargetConfig,
    StrategyConfig,
)
from agent_chaos_sdk.common.logger import get_logger
from agent_chaos_sdk.proxy.addon import (
    ChaosProxyAddon, PROXY_MODE_LIVE, PROXY_MODE_RECORD, PROXY_MODE_PLAYBACK
)

# ASCII Art Logo
LOGO = """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║     █████╗  ██████╗ ███████╗███╗   ██╗████████╗              ║
║    ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝              ║
║    ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║                 ║
║    ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║                 ║
║    ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║                 ║
║    ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝                 ║
║                                                               ║
║     ██████╗██╗  ██╗ █████╗  ██████╗ ███████╗                 ║
║    ██╔════╝██║  ██║██╔══██╗██╔═══██╗██╔════╝                 ║
║    ██║     ███████║███████║██║   ██║███████╗                 ║
║    ██║     ██╔══██║██╔══██║██║   ██║╚════██║                 ║
║    ╚██████╗██║  ██║██║  ██║╚██████╔╝███████║                 ║
║     ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝                 ║
║                                                               ║
║              🐵 Chaos Engineering Platform 🐵               ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
"""

def _print_logo():
    """Print the ASCII art logo."""
    console.print(LOGO, style="bold cyan")


def _print_welcome():
    """Print welcome message."""
    welcome_text = Text()
    welcome_text.append("Welcome to ", style="dim")
    welcome_text.append("Agent Chaos Platform", style="bold cyan")
    welcome_text.append(" - Testing AI Agent Resilience", style="dim")
    
    console.print()
    console.print(Panel(
        welcome_text,
        box=box.ROUNDED,
        border_style="cyan",
        padding=(1, 2)
    ))
    console.print()


app = typer.Typer(
    name="agent-chaos",
    help="🐵 Agent Chaos Platform - Professional CLI for Chaos Engineering",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()
logger = get_logger(__name__)

# Global state for run/record/replay commands
_proxy_process: Optional[subprocess.Popen] = None
_mock_server_process: Optional[subprocess.Popen] = None


def _generate_template_plan() -> str:
    """Generate a template chaos plan YAML."""
    return """version: "1.0"
metadata:
  name: "My Chaos Experiment"
  description: "Describe what this experiment tests"
  experiment_id: "experiment_001"
  author: "Your Name"
  created_at: "{date}"

targets:
  # Define what to attack
  - name: "api_endpoint"
    type: "http_endpoint"
    pattern: ".*/api/.*"
    description: "All API endpoints"
  
  - name: "my_agent"
    type: "agent_role"
    pattern: "MyAgent"
    description: "Agents with role 'MyAgent'"

scenarios:
  # Define how to attack
  - name: "slow_network"
    type: "latency"
    target_ref: "api_endpoint"
    enabled: false
    probability: 1.0
    params:
      delay: 5.0
  
  - name: "inject_errors"
    type: "error"
    target_ref: "api_endpoint"
    enabled: false
    probability: 0.5
    params:
      error_code: 500
  
  - name: "hallucinate_data"
    type: "hallucination"
    target_ref: "api_endpoint"
    enabled: false
    probability: 0.8
    params:
      mode: "swap_entities"
""".format(date=datetime.now().strftime("%Y-%m-%d"))


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _check_llm_health() -> None:
    """
    Fail fast if local LLM is not reachable.
    """
    if os.getenv("CHAOS_LLM_HEALTH_SKIP", "false").lower() == "true":
        return
    health_url = os.getenv("CHAOS_LLM_HEALTH_URL", "http://127.0.0.1:11434/api/tags")
    try:
        # Bypass proxy env to avoid routing health checks through the chaos proxy.
        with httpx.Client(timeout=3.0, trust_env=False, proxy=None) as client:
            response = client.get(health_url)
        if response.status_code >= 400:
            hint = " (rate limited)" if response.status_code == 429 else ""
            raise RuntimeError(
                f"Local LLM health check failed ({response.status_code}){hint}. "
                f"Please ensure the LLM is running at {health_url}."
            )
    except httpx.RequestError as e:
        raise RuntimeError(
            f"Local LLM is not reachable at {health_url}. "
            "Please start the local LLM before running the experiment."
        ) from e


def _preflight_checks(plan: ChaosPlan, mode: str) -> None:
    # Strict classifier rule packs
    if os.getenv("CHAOS_CLASSIFIER_STRICT", "true").lower() == "true":
        if not plan.classifier_rule_packs:
            raise RuntimeError("Classifier strict mode enabled but classifier_rule_packs not configured.")

    # Replay strict mode requires jsonpath-ng when ignore paths are set
    if os.getenv("CHAOS_REPLAY_STRICT", "true").lower() == "true":
        if plan.replay_config.ignore_paths and not _module_available("jsonpath_ng"):
            raise RuntimeError("Replay strict mode requires jsonpath-ng to be installed.")

    # JWT strict mode requires pyjwt if secret configured
    if os.getenv("CHAOS_JWT_STRICT", "true").lower() == "true":
        if os.getenv("CHAOS_JWT_SECRET") and not _module_available("jwt"):
            raise RuntimeError("JWT strict mode requires pyjwt to be installed.")

    # Tape encryption key required for record/replay
    if mode in (PROXY_MODE_RECORD, PROXY_MODE_PLAYBACK):
        if not os.getenv("CHAOS_TAPE_KEY"):
            raise RuntimeError("CHAOS_TAPE_KEY is required for tape encryption in record/replay.")

    # Global LLM health check (fail fast if local LLM is unavailable)
    _check_llm_health()


@app.command()
def init(
    output: Optional[str] = typer.Option(
        "chaos_plan.yaml",
        "--output", "-o",
        help="Output file path"
    )
):
    """
    Generate a scaffold chaos_plan.yaml template.
    
    Creates a template YAML file that you can edit to define your chaos experiment.
    """
    _print_logo()
    
    output_path = Path(output)
    
    if output_path.exists():
        console.print(f"[yellow]⚠[/yellow]  File [cyan]{output_path}[/cyan] already exists.")
        if not typer.confirm("  Overwrite?", default=False):
            console.print("[dim]Cancelled[/dim]")
            raise typer.Abort()
    
    template = _generate_template_plan()
    
    try:
        output_path.write_text(template, encoding='utf-8')
        
        success_panel = Panel(
            Align.center(
                Text(f"✓ Template created successfully!\n\n{output_path}", style="green bold")
            ),
            title="[bold green]Success[/bold green]",
            box=box.ROUNDED,
            border_style="green",
            padding=(1, 2)
        )
        console.print(success_panel)
        
        console.print("\n[dim]💡 Tip:[/dim] Edit this file to define your chaos experiment.")
        console.print(f"[dim]   Then run:[/dim] [cyan]agent-chaos validate {output_path}[/cyan]\n")
    except Exception as e:
        error_panel = Panel(
            f"[red]✗ Failed to create template:[/red]\n\n{str(e)}",
            title="[bold red]Error[/bold red]",
            box=box.ROUNDED,
            border_style="red"
        )
        console.print(error_panel)
        raise typer.Exit(1)


@app.command()
def validate(
    file: str = typer.Argument(..., help="Path to chaos plan YAML file")
):
    """
    Validate a chaos plan YAML file.
    
    Checks if the YAML is valid and matches the schema.
    """
    _print_logo()
    
    file_path = Path(file)
    
    if not file_path.exists():
        error_panel = Panel(
            f"[red]✗ File not found:[/red]\n\n{file_path}",
            title="[bold red]Error[/bold red]",
            box=box.ROUNDED,
            border_style="red"
        )
        console.print(error_panel)
        raise typer.Exit(1)
    
    console.print()
    console.print(Rule(f"[bold cyan]Validating: {file_path.name}[/bold cyan]"))
    console.print()
    
    try:
        plan = load_chaos_plan(str(file_path))
        
        # Create validation report
        table = Table(title="Validation Results", box=box.ROUNDED)
        table.add_column("Check", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details")
        
        table.add_row("YAML Syntax", "✓ Valid", "File parsed successfully")
        table.add_row("Schema", "✓ Valid", "Matches ChaosPlan schema")
        table.add_row("Targets", f"✓ {len(plan.targets)}", f"{len(plan.targets)} target(s) defined")
        table.add_row("Scenarios", f"✓ {len(plan.scenarios)}", f"{len(plan.scenarios)} scenario(s) defined")
        
        # Check enabled scenarios
        enabled = sum(1 for s in plan.scenarios if s.enabled)
        table.add_row("Enabled", f"✓ {enabled}", f"{enabled} scenario(s) enabled")
        
        # Check target references
        target_names = {t.name for t in plan.targets}
        invalid_refs = []
        for scenario in plan.scenarios:
            if scenario.target_ref not in target_names:
                invalid_refs.append(f"{scenario.name} -> {scenario.target_ref}")
        
        if invalid_refs:
            table.add_row("Target Refs", "✗ Invalid", f"{len(invalid_refs)} invalid reference(s)")
            for ref in invalid_refs:
                table.add_row("", "", f"  - {ref}", style="red")
        else:
            table.add_row("Target Refs", "✓ Valid", "All references valid")
        
        console.print(table)
        
        # Print plan summary
        console.print(f"\n[bold]Plan:[/bold] {plan.metadata.get('name', 'Unnamed')}")
        console.print(f"[bold]Experiment ID:[/bold] {plan.metadata.get('experiment_id', 'N/A')}")
        
        if plan.targets:
            console.print(f"\n[bold]Targets:[/bold]")
            for target in plan.targets:
                console.print(f"  • {target.name} ({target.type}): {target.pattern}")
        
        if plan.scenarios:
            console.print(f"\n[bold]Scenarios:[/bold]")
            for scenario in plan.scenarios:
                status = "✓" if scenario.enabled else "○"
                style = "green" if scenario.enabled else "dim"
                console.print(
                    f"  {status} [{style}]{scenario.name}[/{style}] "
                    f"({scenario.type}) -> {scenario.target_ref}"
                )
        
        console.print()
        success_panel = Panel(
            Align.center(Text("✓ Validation passed!", style="green bold")),
            box=box.ROUNDED,
            border_style="green",
            padding=(1, 2)
        )
        console.print(success_panel)
        console.print()

        if exit_code != 0:
            raise typer.Exit(exit_code)
        
    except FileNotFoundError:
        error_panel = Panel(
            f"[red]✗ File not found:[/red]\n\n{file_path}",
            title="[bold red]Error[/bold red]",
            box=box.ROUNDED,
            border_style="red"
        )
        console.print(error_panel)
        raise typer.Exit(1)
    except Exception as e:
        error_panel = Panel(
            f"[red]✗ Validation failed:[/red]\n\n{str(e)}",
            title="[bold red]Error[/bold red]",
            box=box.ROUNDED,
            border_style="red"
        )
        console.print(error_panel)
        import traceback
        console.print(f"\n[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(1)


def _create_dashboard(metrics: dict, plan: Optional[ChaosPlan] = None) -> Layout:
    """Create a real-time dashboard layout."""
    layout = Layout()
    
    # Header with logo (compact version)
    header_text = Text()
    header_text.append("╔═══ ", style="cyan")
    header_text.append("Agent Chaos Platform", style="bold cyan")
    header_text.append(" ═══╗", style="cyan")
    header_text.append("\n", style="cyan")
    
    if plan:
        exp_name = plan.metadata.get('name', 'Unnamed')
        if len(exp_name) > 50:
            exp_name = exp_name[:47] + "..."
        header_text.append(f" Experiment: {exp_name}", style="dim")
        header_text.append("\n", style="dim")
    
    header_text.append(" ════════════════════════════════════════════════", style="cyan dim")
    
    header = Panel(
        Align.center(header_text),
        box=box.ROUNDED,
        border_style="cyan",
        padding=(0, 1)
    )
    
    # Metrics table with enhanced styling
    metrics_table = Table(
        title="[bold cyan]📊 Metrics[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="cyan"
    )
    metrics_table.add_column("Metric", style="cyan", width=22, no_wrap=True)
    metrics_table.add_column("Value", style="bold", width=18, justify="right")
    
    requests = metrics.get("requests", 0)
    attacks = metrics.get("active_attacks", 0)
    errors = metrics.get("errors", 0)
    
    # Format numbers with colors
    requests_text = Text(str(requests), style="bold green")
    metrics_table.add_row("Total Requests", requests_text)
    
    attacks_text = Text(str(attacks), style="bold yellow" if attacks > 0 else "dim")
    metrics_table.add_row("Chaos Injections", attacks_text)
    
    errors_text = Text(str(errors), style="bold red" if errors > 0 else "bold green")
    metrics_table.add_row("Errors", errors_text)
    
    last_error = metrics.get("last_error", "None")
    if len(last_error) > 35:
        last_error = last_error[:32] + "..."
    error_style = "red" if errors > 0 else "dim"
    metrics_table.add_row("Last Error", Text(last_error, style=error_style))
    
    # Status panel with enhanced styling
    status_table = Table(
        title="[bold cyan]⚙️  Status[/bold cyan]",
        box=box.ROUNDED,
        show_header=False,
        border_style="cyan"
    )
    status_table.add_column("Component", style="cyan", width=18, no_wrap=True)
    status_table.add_column("Status", width=20, justify="center")
    
    proxy_running = metrics.get("proxy_running", False)
    proxy_status = Text("🟢 RUNNING", style="bold green") if proxy_running else Text("🔴 STOPPED", style="bold red")
    status_table.add_row("Proxy", proxy_status)
    
    mock_running = metrics.get("mock_server_running", False)
    if mock_running:
        status_table.add_row("Mock Server", Text("🟢 RUNNING", style="bold green"))
    else:
        status_table.add_row("Mock Server", Text("⚪ STOPPED", style="dim"))
    
    # Active scenarios
    if plan:
        active_scenarios = [s for s in plan.scenarios if s.enabled]
        scenario_text = Text(str(len(active_scenarios)), style="bold yellow")
        status_table.add_row("Active Scenarios", scenario_text)
    
    # Add timestamp
    timestamp = datetime.now().strftime("%H:%M:%S")
    status_table.add_row("", "")  # Spacer
    status_table.add_row("Time", Text(timestamp, style="dim"))
    
    # Layout structure
    layout.split_column(
        Layout(header, size=5),
        Layout(name="body"),
    )
    
    layout["body"].split_row(
        Layout(Panel(metrics_table, border_style="cyan"), name="metrics"),
        Layout(Panel(status_table, border_style="cyan"), name="status", size=40),
    )
    
    return layout


def _parse_proxy_log(log_file: Path) -> dict:
    """Parse proxy log to extract metrics."""
    metrics = {
        "requests": 0,
        "active_attacks": 0,
        "errors": 0,
        "last_error": "None",
        "proxy_running": True,
        "mock_server_running": False,
    }
    
    if not log_file.exists():
        return metrics
    
    try:
        # Read last N lines
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            metrics["requests"] = len(lines)
            
            # Count attacks and errors
            for line in lines[-100:]:  # Last 100 lines
                try:
                    entry = json.loads(line.strip())
                    if entry.get("chaos_applied"):
                        metrics["active_attacks"] += 1
                    if entry.get("status_code", 200) >= 400:
                        metrics["errors"] += 1
                        error_msg = f"{entry.get('method', '?')} {entry.get('url', '?')} -> {entry.get('status_code', '?')}"
                        if error_msg != "? ? -> ?":
                            metrics["last_error"] = error_msg
                except (json.JSONDecodeError, KeyError):
                    pass
    except Exception:
        pass
    
    # Check if mock server is running (by checking if port is accessible)
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.1)
        result = sock.connect_ex(('localhost', 8001))
        sock.close()
        metrics["mock_server_running"] = (result == 0)
    except Exception:
        pass
    
    return metrics


@app.command()
def run(
    file: str = typer.Argument(..., help="Path to chaos plan YAML file"),
    proxy_port: int = typer.Option(8080, "--port", "-p", help="Proxy port"),
    mock_server: bool = typer.Option(False, "--mock-server", help="Start mock server"),
    mock_port: int = typer.Option(8001, "--mock-port", help="Mock server port"),
    repeat: int = typer.Option(1, "--repeat", "-r", help="Repeat running the agent command N times"),
    repeat_delay: float = typer.Option(0.0, "--repeat-delay", help="Delay between repeats in seconds"),
    repeat_concurrency: int = typer.Option(1, "--repeat-concurrency", help="Concurrent agent runs"),
    agent_cmd: Optional[str] = typer.Option(None, "--agent-cmd", help="Shell command to run your agent once"),
    agent_query: str = typer.Option(
        "Book a flight from New York to Los Angeles",
        "--agent-query",
        help="Query for the demo agent when --agent-cmd is not provided",
    ),
    report_json: Optional[str] = typer.Option(None, "--report-json", help="Write JSON summary report to this path"),
    report_csv: Optional[str] = typer.Option(None, "--report-csv", help="Write CSV summary report to this path"),
    report_md: Optional[str] = typer.Option(None, "--report-md", help="Write Markdown summary report to this path"),
    report_pdf: Optional[str] = typer.Option(None, "--report-pdf", help="Write PDF summary report to this path"),
    failure_artifacts_dir: Optional[str] = typer.Option(
        None,
        "--failure-artifacts-dir",
        help="Directory to store per-run failure outputs",
    ),
    failure_artifacts_zip: Optional[str] = typer.Option(
        None,
        "--failure-artifacts-zip",
        help="Path to write a zip of failure artifacts",
    ),
    failure_artifacts_tar: Optional[str] = typer.Option(
        None,
        "--failure-artifacts-tar",
        help="Path to write a tar.gz of failure artifacts",
    ),
    acceptance_report: Optional[str] = typer.Option(
        None,
        "--acceptance-report",
        help="Write a production acceptance report template (Markdown)",
    ),
    sla_success_rate: Optional[float] = typer.Option(
        None,
        "--sla-success-rate",
        help="SLA minimum success rate (0-1). Example: 0.99",
    ),
    sla_p95_ms: Optional[float] = typer.Option(
        None,
        "--sla-p95-ms",
        help="SLA maximum P95 latency in ms",
    ),
    sla_p99_ms: Optional[float] = typer.Option(
        None,
        "--sla-p99-ms",
        help="SLA maximum P99 latency in ms",
    ),
):
    """
    Run a chaos experiment from a plan file.
    
    Loads the plan, starts the chaos proxy, and displays a real-time dashboard.
    """
    global _proxy_process, _mock_server_process
    
    _print_logo()
    _print_welcome()
    
    file_path = Path(file)
    
    if not file_path.exists():
        error_panel = Panel(
            f"[red]✗ File not found:[/red]\n\n{file_path}",
            title="[bold red]Error[/bold red]",
            box=box.ROUNDED,
            border_style="red"
        )
        console.print(error_panel)
        raise typer.Exit(1)
    
    # Validate plan first
    console.print(Rule("[bold cyan]Loading Experiment Plan[/bold cyan]"))
    console.print()
    
    try:
        plan = load_chaos_plan(str(file_path))
        set_global_plan(plan)
        _preflight_checks(plan, PROXY_MODE_LIVE)
        
        plan_info = Table.grid(padding=(0, 2))
        plan_info.add_column(style="cyan", width=15)
        plan_info.add_column(style="white")
        
        plan_info.add_row("Plan Name:", plan.metadata.get('name', 'Unnamed'))
        plan_info.add_row("Experiment ID:", plan.metadata.get('experiment_id', 'N/A'))
        plan_info.add_row("Targets:", str(len(plan.targets)))
        plan_info.add_row("Scenarios:", str(len(plan.scenarios)))
        plan_info.add_row("Enabled:", str(sum(1 for s in plan.scenarios if s.enabled)))
        
        console.print(Panel(plan_info, title="[bold green]✓ Plan Loaded[/bold green]", border_style="green"))
        console.print()
    except Exception as e:
        error_panel = Panel(
            f"[red]✗ Failed to load plan:[/red]\n\n{str(e)}",
            title="[bold red]Error[/bold red]",
            box=box.ROUNDED,
            border_style="red"
        )
        console.print(error_panel)
        raise typer.Exit(1)

    # Create per-run artifact directory (logs/reports) to avoid overwriting history
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    plan_name = plan.metadata.get("name", "run")
    safe_plan_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(plan_name)).strip("-").lower() or "run"
    run_dir = Path("runs") / f"{run_id}-{safe_plan_name}"
    run_logs_dir = run_dir / "logs"
    run_reports_dir = run_dir / "reports"
    run_logs_dir.mkdir(parents=True, exist_ok=True)
    run_reports_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"  [green]✓[/green] Run artifacts: [cyan]{run_dir}[/cyan]")
    
    # Convert plan to legacy format for proxy
    console.print(Rule("[bold cyan]Initializing Services[/bold cyan]"))
    console.print()
    
    legacy_config = plan.to_legacy_config()
    config_path = Path("config/chaos_config.yaml")
    config_path.parent.mkdir(exist_ok=True)
    
    import yaml
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(legacy_config, f, default_flow_style=False)
    
    console.print(f"  [green]✓[/green] Generated proxy config: [cyan]{config_path}[/cyan]")
    
    # Start mock server if requested
    if mock_server:
        with console.status("[bold cyan]Starting mock server...", spinner="dots"):
            try:
                _mock_server_process = subprocess.Popen(
                    [sys.executable, "src/tools/mock_server.py"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                time.sleep(2)  # Wait for server to start
                console.print(f"  [green]✓[/green] Mock server started on port [cyan]{mock_port}[/cyan] (PID: {_mock_server_process.pid})")
            except Exception as e:
                error_panel = Panel(
                    f"[red]✗ Failed to start mock server:[/red]\n\n{str(e)}",
                    title="[bold red]Error[/bold red]",
                    box=box.ROUNDED,
                    border_style="red"
                )
                console.print(error_panel)
                raise typer.Exit(1)
    
    # Start proxy (dashboard is started inside the proxy process)
    with console.status("[bold cyan]Starting chaos proxy...", spinner="dots"):
        try:
            proxy_script = Path("agent_chaos_sdk/proxy/addon.py")
            proxy_env = os.environ.copy()
            proxy_env["CHAOS_DASHBOARD_AUTOSTART"] = "true"
            log_file = run_logs_dir / "proxy.log"
            proxy_env["CHAOS_LOG_FILE"] = str(log_file)
            _proxy_process = subprocess.Popen(
                ["mitmdump", "-s", str(proxy_script), "--listen-port", str(proxy_port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=proxy_env,
            )
            time.sleep(2)  # Wait for proxy to start
            console.print(f"  [green]✓[/green] Chaos proxy started on port [cyan]{proxy_port}[/cyan] (PID: {_proxy_process.pid})")
        except Exception as e:
            error_panel = Panel(
                f"[red]✗ Failed to start proxy:[/red]\n\n{str(e)}",
                title="[bold red]Error[/bold red]",
                box=box.ROUNDED,
                border_style="red"
            )
            console.print(error_panel)
            raise typer.Exit(1)
    
    # Verify dashboard is running (started inside proxy process)
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 8081))
        sock.close()
        
        if result == 0:
            console.print(f"  [green]✓[/green] Dashboard available at [cyan]http://127.0.0.1:8081[/cyan]")
            console.print("  [dim]Dashboard is started inside the proxy process (WebSocket events are emitted there).[/dim]")
        else:
            console.print(f"  [yellow]⚠[/yellow]  Dashboard server started but not responding on port 8081")
    except Exception as e:
        console.print(f"  [yellow]⚠[/yellow]  Dashboard not available: {e}")
        logger.error(f"Failed to check dashboard: {e}", exc_info=True)

    # Optional: run agent command repeatedly in the background
    agent_stop_event = threading.Event()
    sla_failed_event = threading.Event()
    agent_thread = None
    exit_code = 0
    if repeat < 1:
        console.print("[yellow]⚠[/yellow]  --repeat must be >= 1; defaulting to 1")
        repeat = 1
    if repeat_concurrency < 1:
        console.print("[yellow]⚠[/yellow]  --repeat-concurrency must be >= 1; defaulting to 1")
        repeat_concurrency = 1

    resolved_agent_cmd: Optional[list[str]] = None
    if agent_cmd:
        try:
            resolved_agent_cmd = shlex.split(agent_cmd)
        except ValueError as e:
            console.print(f"[yellow]⚠[/yellow]  Invalid --agent-cmd: {e}")
    elif repeat > 1:
        if not mock_server:
            console.print("[yellow]⚠[/yellow]  --repeat requires --agent-cmd or --mock-server to run the demo agent.")
        else:
            resolved_agent_cmd = [
                sys.executable,
                "examples/production_simulation/travel_agent.py",
                "--query",
                agent_query,
            ]

    if resolved_agent_cmd:
        agent_log = run_logs_dir / "agent_run.log"
        agent_log.parent.mkdir(parents=True, exist_ok=True)
        agent_metrics_path = run_logs_dir / "agent_metrics.json"

        results_lock = threading.Lock()
        total_runs = repeat
        successes = 0
        failures = 0
        durations_ms: list[float] = []
        error_breakdown: dict[str, int] = {}
        error_categories: dict[str, int] = {}
        sla_failed = False

        # Split runs across workers
        base = total_runs // repeat_concurrency
        remainder = total_runs % repeat_concurrency
        worker_runs = [base + (1 if i < remainder else 0) for i in range(repeat_concurrency)]

        def _extract_error_type(output: str) -> str:
            # Prefer explicit exception lines
            for line in output.splitlines():
                if "ResponseError:" in line:
                    return line.strip()
                if "Traceback" in line:
                    return "Traceback"
                if "Error:" in line:
                    return line.strip()
                if "Exception" in line:
                    return line.strip()
            return "nonzero_exit"

        def _percentile(values: list[float], pct: float) -> Optional[float]:
            if not values:
                return None
            sorted_vals = sorted(values)
            idx = int(round((pct / 100.0) * (len(sorted_vals) - 1)))
            return sorted_vals[min(max(idx, 0), len(sorted_vals) - 1)]

        def _categorize_error(error_text: str) -> str:
            text = error_text.lower()
            if "chaos injection" in text:
                return "chaos_injection"
            if "responseerror" in text or "ollama" in text:
                return "llm_response_error"
            if "connection" in text or "timeout" in text:
                return "connection_error"
            if "traceback" in text or "exception" in text:
                return "exception"
            return "other"

        def run_agent_repeats(worker_id: int, runs: int) -> None:
            nonlocal successes, failures
            for i in range(runs):
                if agent_stop_event.is_set():
                    break
                cmd_env = os.environ.copy()
                cmd_env["HTTP_PROXY"] = f"http://127.0.0.1:{proxy_port}"
                cmd_env["HTTPS_PROXY"] = f"http://127.0.0.1:{proxy_port}"
                # Skip per-worker LLM health checks; CLI preflight already validated.
                cmd_env["CHAOS_LLM_HEALTH_SKIP"] = "true"
                cmd_env.setdefault("AGENT_METRICS_PATH", str(agent_metrics_path))
                default_rules_path = Path("examples/production_simulation/validation_rules.yaml")
                if "AGENT_VALIDATION_RULES" not in cmd_env and default_rules_path.exists():
                    cmd_env["AGENT_VALIDATION_RULES"] = str(default_rules_path)
                with open(agent_log, "a", encoding="utf-8") as log_fp:
                    log_fp.write(
                        f"\n--- Worker {worker_id} run {i + 1}/{runs} at {datetime.now().isoformat()} ---\n"
                    )
                    try:
                        start_time = time.monotonic()
                        result = subprocess.run(
                            resolved_agent_cmd,
                            env=cmd_env,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            check=False
                        )
                        elapsed_ms = (time.monotonic() - start_time) * 1000.0
                        log_fp.write(result.stdout or "")
                        with results_lock:
                            durations_ms.append(elapsed_ms)
                            if result.returncode == 0:
                                successes += 1
                            else:
                                failures += 1
                                error_type = _extract_error_type(result.stdout or "")
                                error_breakdown[error_type] = error_breakdown.get(error_type, 0) + 1
                                category = _categorize_error(error_type)
                                error_categories[category] = error_categories.get(category, 0) + 1
                                if failure_artifacts_dir:
                                    try:
                                        artifacts_dir = Path(failure_artifacts_dir)
                                        artifacts_dir.mkdir(parents=True, exist_ok=True)
                                        artifact_path = artifacts_dir / f"failure_worker{worker_id}_run{i + 1}.log"
                                        artifact_path.write_text(result.stdout or "", encoding="utf-8")
                                    except Exception:
                                        pass
                    except Exception as e:
                        log_fp.write(f"Agent run failed: {e}\n")
                        with results_lock:
                            failures += 1
                            error_breakdown[str(e)] = error_breakdown.get(str(e), 0) + 1
                            category = _categorize_error(str(e))
                            error_categories[category] = error_categories.get(category, 0) + 1
                if repeat_delay > 0 and i < runs - 1:
                    time.sleep(repeat_delay)

        console.print(
            f"  [green]✓[/green] Repeating agent run {repeat} times "
            f"with concurrency {repeat_concurrency} (logs: {agent_log})"
        )
        agent_thread = threading.Thread(target=run_agent_repeats, daemon=True)
        # Fan out workers under a supervisor thread
        def supervisor() -> None:
            threads = []
            for idx, runs in enumerate(worker_runs, start=1):
                if runs <= 0:
                    continue
                t = threading.Thread(target=run_agent_repeats, args=(idx, runs), daemon=True)
                threads.append(t)
                t.start()
            for t in threads:
                t.join()

            # Summary output
            console.print()
            console.print(Rule("[bold cyan]Agent Run Summary[/bold cyan]"))
            avg_ms = (sum(durations_ms) / len(durations_ms)) if durations_ms else None
            p95_ms = _percentile(durations_ms, 95.0)
            p99_ms = _percentile(durations_ms, 99.0)
            p999_ms = _percentile(durations_ms, 99.9)
            console.print(
                f"[green]Success:[/green] {successes}  "
                f"[red]Failures:[/red] {failures}  "
                f"[cyan]Total:[/cyan] {successes + failures}"
            )
            console.print(
                f"[cyan]Avg ms:[/cyan] {avg_ms:.2f}  "
                f"[cyan]P95 ms:[/cyan] {p95_ms:.2f}  "
                f"[cyan]P99 ms:[/cyan] {p99_ms:.2f}  "
                f"[cyan]P99.9 ms:[/cyan] {p999_ms:.2f}" if avg_ms is not None and p95_ms is not None else
                "[yellow]Latency metrics unavailable (no completed runs).[/yellow]"
            )
            if error_breakdown:
                console.print("[bold]Failure breakdown:[/bold]")
                for err, count in sorted(error_breakdown.items(), key=lambda x: x[1], reverse=True):
                    console.print(f"  - {count}x {err}")
            if error_categories:
                console.print("[bold]Failure categories:[/bold]")
                for err, count in sorted(error_categories.items(), key=lambda x: x[1], reverse=True):
                    console.print(f"  - {count}x {err}")

            summary = {
                "schema_version": "1.0",
                "generated_at": datetime.now().isoformat(),
                "plan_file": str(file_path),
                "proxy_port": proxy_port,
                "mock_server": mock_server,
                "repeat": repeat,
                "repeat_concurrency": repeat_concurrency,
                "repeat_delay": repeat_delay,
                "results": {
                    "successes": successes,
                    "failures": failures,
                    "total": successes + failures,
                    "avg_ms": avg_ms,
                    "p95_ms": p95_ms,
                    "p99_ms": p99_ms,
                    "p99_9_ms": p999_ms,
                },
                "errors": {
                    "breakdown": error_breakdown,
                    "categories": error_categories,
                },
                "sla": {
                    "success_rate_min": sla_success_rate,
                    "p95_ms_max": sla_p95_ms,
                    "p99_ms_max": sla_p99_ms,
                    "pass": None,
                },
            }
            if report_json:
                try:
                    report_path = Path(report_json)
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
                    console.print(f"[green]✓[/green] JSON report: {report_path}")
                except Exception as e:
                    console.print(f"[yellow]⚠[/yellow] Failed to write JSON report: {e}")
            if report_csv:
                try:
                    report_path = Path(report_csv)
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    # Flatten error breakdown into a single column
                    error_str = "; ".join([f"{k}:{v}" for k, v in error_breakdown.items()])
                    csv_content = "successes,failures,total,avg_ms,p95_ms,p99_ms,p99_9_ms,error_breakdown,error_categories\n"
                    categories_str = "; ".join([f"{k}:{v}" for k, v in error_categories.items()])
                    csv_content += (
                        f"{successes},{failures},{successes + failures},"
                        f"{avg_ms},{p95_ms},{p99_ms},{p999_ms},"
                        f"\"{error_str}\",\"{categories_str}\"\n"
                    )
                    report_path.write_text(csv_content, encoding="utf-8")
                    console.print(f"[green]✓[/green] CSV report: {report_path}")
                except Exception as e:
                    console.print(f"[yellow]⚠[/yellow] Failed to write CSV report: {e}")
            if report_md:
                try:
                    report_path = Path(report_md)
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    lines = [
                        "# Agent Chaos Run Summary",
                        "",
                        f"- Successes: {successes}",
                        f"- Failures: {failures}",
                        f"- Total: {successes + failures}",
                        "",
                        "## Latency",
                        f"- Avg ms: {avg_ms:.2f}" if avg_ms is not None else "- Avg ms: N/A",
                        f"- P95 ms: {p95_ms:.2f}" if p95_ms is not None else "- P95 ms: N/A",
                        f"- P99 ms: {p99_ms:.2f}" if p99_ms is not None else "- P99 ms: N/A",
                        f"- P99.9 ms: {p999_ms:.2f}" if p999_ms is not None else "- P99.9 ms: N/A",
                        "",
                        "## Failure Breakdown",
                    ]
                    if error_breakdown:
                        for err, count in sorted(error_breakdown.items(), key=lambda x: x[1], reverse=True):
                            lines.append(f"- {count}x {err}")
                    else:
                        lines.append("- None")
                    lines.append("")
                    lines.append("## Failure Categories")
                    if error_categories:
                        for err, count in sorted(error_categories.items(), key=lambda x: x[1], reverse=True):
                            lines.append(f"- {count}x {err}")
                    else:
                        lines.append("- None")
                    report_path.write_text("\n".join(lines), encoding="utf-8")
                    console.print(f"[green]✓[/green] Markdown report: {report_path}")
                except Exception as e:
                    console.print(f"[yellow]⚠[/yellow] Failed to write Markdown report: {e}")

            # SLA evaluation
            if sla_success_rate is not None or sla_p95_ms is not None or sla_p99_ms is not None:
                total = successes + failures
                success_rate = (successes / total) if total > 0 else 0.0
                sla_ok = True
                if sla_success_rate is not None and success_rate < sla_success_rate:
                    sla_ok = False
                if sla_p95_ms is not None and p95_ms is not None and p95_ms > sla_p95_ms:
                    sla_ok = False
                if sla_p99_ms is not None and p99_ms is not None and p99_ms > sla_p99_ms:
                    sla_ok = False
                summary["sla"]["pass"] = sla_ok
                if sla_ok:
                    console.print("[green]✓[/green] SLA check passed")
                else:
                    console.print("[red]✗[/red] SLA check failed")
                    sla_failed = True
                    sla_failed_event.set()

            # PDF report
            if report_pdf:
                try:
                    from reportlab.lib.pagesizes import letter
                    from reportlab.pdfgen import canvas
                    pdf_path = Path(report_pdf)
                    pdf_path.parent.mkdir(parents=True, exist_ok=True)
                    c = canvas.Canvas(str(pdf_path), pagesize=letter)
                    width, height = letter
                    y = height - 72
                    lines = [
                        "Agent Chaos Run Summary",
                        f"Generated at: {datetime.now().isoformat()}",
                        f"Plan file: {file_path}",
                        f"Successes: {successes}",
                        f"Failures: {failures}",
                        f"Total: {successes + failures}",
                        f"Avg ms: {avg_ms:.2f}" if avg_ms is not None else "Avg ms: N/A",
                        f"P95 ms: {p95_ms:.2f}" if p95_ms is not None else "P95 ms: N/A",
                        f"P99 ms: {p99_ms:.2f}" if p99_ms is not None else "P99 ms: N/A",
                        f"P99.9 ms: {p999_ms:.2f}" if p999_ms is not None else "P99.9 ms: N/A",
                        f"SLA pass: {summary['sla']['pass']}",
                        "",
                        "Failure categories:",
                    ]
                    for err, count in sorted(error_categories.items(), key=lambda x: x[1], reverse=True):
                        lines.append(f"- {count}x {err}")
                    if not error_categories:
                        lines.append("- None")
                    for line in lines:
                        c.drawString(72, y, line)
                        y -= 14
                        if y < 72:
                            c.showPage()
                            y = height - 72
                    c.save()
                    console.print(f"[green]✓[/green] PDF report: {pdf_path}")
                except Exception as e:
                    console.print(f"[yellow]⚠[/yellow] Failed to write PDF report: {e}")

            # Update JSON with SLA outcome if needed
            if report_json:
                try:
                    report_path = Path(report_json)
                    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
                except Exception:
                    pass

            # Exit non-zero on SLA failure (for CI)
            if sla_failed:
                console.print("[red]SLA FAILED — stopping run (non-zero exit).[/red]")

            # Package failure artifacts
            if failure_artifacts_dir:
                artifacts_dir = Path(failure_artifacts_dir)
                if artifacts_dir.exists():
                    if failure_artifacts_zip:
                        try:
                            zip_path = Path(failure_artifacts_zip)
                            zip_path.parent.mkdir(parents=True, exist_ok=True)
                            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                                for item in artifacts_dir.rglob("*"):
                                    if item.is_file():
                                        zf.write(item, item.relative_to(artifacts_dir))
                            console.print(f"[green]✓[/green] Failure artifacts zip: {zip_path}")
                        except Exception as e:
                            console.print(f"[yellow]⚠[/yellow] Failed to write zip: {e}")
                    if failure_artifacts_tar:
                        try:
                            tar_path = Path(failure_artifacts_tar)
                            tar_path.parent.mkdir(parents=True, exist_ok=True)
                            with tarfile.open(tar_path, "w:gz") as tf:
                                tf.add(artifacts_dir, arcname=artifacts_dir.name)
                            console.print(f"[green]✓[/green] Failure artifacts tar: {tar_path}")
                        except Exception as e:
                            console.print(f"[yellow]⚠[/yellow] Failed to write tar: {e}")

            # Acceptance report template
            if acceptance_report:
                try:
                    report_path = Path(acceptance_report)
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    lines = [
                        "# Production Acceptance Report",
                        "",
                        f"- Generated at: {datetime.now().isoformat()}",
                        f"- Plan file: {file_path}",
                        f"- Repeat: {repeat}",
                        f"- Concurrency: {repeat_concurrency}",
                        "",
                        "## Summary Metrics",
                        f"- Successes: {successes}",
                        f"- Failures: {failures}",
                        f"- Total: {successes + failures}",
                        f"- Avg ms: {avg_ms:.2f}" if avg_ms is not None else "- Avg ms: N/A",
                        f"- P95 ms: {p95_ms:.2f}" if p95_ms is not None else "- P95 ms: N/A",
                        f"- P99 ms: {p99_ms:.2f}" if p99_ms is not None else "- P99 ms: N/A",
                        f"- P99.9 ms: {p999_ms:.2f}" if p999_ms is not None else "- P99.9 ms: N/A",
                        "",
                        "## Failure Categories",
                    ]
                    if error_categories:
                        for err, count in sorted(error_categories.items(), key=lambda x: x[1], reverse=True):
                            lines.append(f"- {count}x {err}")
                    else:
                        lines.append("- None")
                    lines += [
                        "",
                        "## Acceptance Checklist",
                        "- [ ] Success rate meets target",
                        "- [ ] P95/P99 latency within SLA",
                        "- [ ] No critical failure categories",
                        "- [ ] Replay available for failures",
                        "- [ ] Observability verified (dashboard + logs)",
                        "",
                        "## Notes",
                        "- ",
                    ]
                    report_path.write_text("\n".join(lines), encoding="utf-8")
                    console.print(f"[green]✓[/green] Acceptance report: {report_path}")
                except Exception as e:
                    console.print(f"[yellow]⚠[/yellow] Failed to write acceptance report: {e}")

        agent_thread = threading.Thread(target=supervisor, daemon=True)
        agent_thread.start()
    
    # Setup log file path (per-run)
    log_file = run_logs_dir / "proxy.log"
    
    # Real-time dashboard
    console.print()
    console.print(Rule("[bold cyan]Live Dashboard[/bold cyan]"))
    console.print()
    
    info_panel = Panel(
        Align.center(
            Text("Press [bold red]Ctrl+C[/bold red] to stop the experiment", style="dim")
        ),
        box=box.ROUNDED,
        border_style="dim",
        padding=(0, 1)
    )
    console.print(info_panel)
    console.print()
    
    try:
        initial_metrics = {
            "proxy_running": True,
            "mock_server_running": mock_server,
        }
        use_live_screen = console.is_terminal
        with Live(
            _create_dashboard(initial_metrics, plan),
            refresh_per_second=2,
            screen=use_live_screen,
            transient=False,
        ) as live:
            while True:
                metrics = _parse_proxy_log(log_file)
                metrics["proxy_running"] = _proxy_process.poll() is None
                if mock_server and _mock_server_process:
                    metrics["mock_server_running"] = _mock_server_process.poll() is None
                else:
                    metrics["mock_server_running"] = False
                live.update(_create_dashboard(metrics, plan))
                if sla_failed_event.is_set():
                    exit_code = 2
                    break
                time.sleep(0.5)
    except KeyboardInterrupt:
        console.print()
        console.print(Rule("[bold yellow]Shutting Down[/bold yellow]"))
        console.print()
    finally:
        # Cleanup
        with console.status("[bold yellow]Stopping services...", spinner="dots"):
            # Stop agent repeat loop if running
            if agent_thread and agent_thread.is_alive():
                agent_stop_event.set()
            # Dashboard runs inside the proxy process; stopping the proxy is enough.
            if _proxy_process:
                _proxy_process.terminate()
                _proxy_process.wait()
                console.print("  [green]✓[/green] Proxy stopped")
            
            if _mock_server_process:
                _mock_server_process.terminate()
                _mock_server_process.wait()
                console.print("  [green]✓[/green] Mock server stopped")
        
        console.print()
        success_panel = Panel(
            Align.center(Text("✓ Experiment complete!", style="green bold")),
            box=box.ROUNDED,
            border_style="green",
            padding=(1, 2)
        )
        console.print(success_panel)
        console.print()


def _signal_handler(signum, frame):
    """Handle shutdown signals."""
    global _proxy_process, _mock_server_process
    
    console.print("\n[yellow]Shutting down...[/yellow]")
    
    if _proxy_process:
        _proxy_process.terminate()
    if _mock_server_process:
        _mock_server_process.terminate()
    
    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


@app.command()
def record(
    plan: str = typer.Argument(..., help="Path to chaos plan YAML file"),
    tape: str = typer.Option(
        None,
        "--tape", "-t",
        help="Path to output tape file (default: auto-generated)"
    ),
    port: int = typer.Option(8080, "--port", "-p", help="Proxy port")
):
    """
    Record HTTP interactions to a tape file.
    
    Runs the proxy in RECORD mode, capturing all requests/responses
    along with chaos context for deterministic replay.
    """
    _print_logo()
    _print_welcome()
    
    plan_path = Path(plan)
    if not plan_path.exists():
        error_panel = Panel(
            f"[red]✗ Plan file not found:[/red]\n\n{plan_path}",
            title="[bold red]Error[/bold red]",
            box=box.ROUNDED,
            border_style="red"
        )
        console.print(error_panel)
        raise typer.Exit(1)
    
    # Load chaos plan
    try:
        chaos_plan = load_chaos_plan(str(plan_path))
        set_global_plan(chaos_plan)
        _preflight_checks(chaos_plan, PROXY_MODE_RECORD)
        console.print(f"[green]✓[/green] Loaded chaos plan: {plan_path.name}")
    except Exception as e:
        error_panel = Panel(
            f"[red]✗ Failed to load plan:[/red]\n\n{str(e)}",
            title="[bold red]Error[/bold red]",
            box=box.ROUNDED,
            border_style="red"
        )
        console.print(error_panel)
        raise typer.Exit(1)
    
    # Determine tape path
    if tape:
        tape_path = Path(tape)
    else:
        tape_dir = Path("tapes")
        tape_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        tape_path = tape_dir / f"recording_{timestamp}.tape"
    
    console.print(f"[cyan]📼 Recording to:[/cyan] {tape_path}")
    console.print(f"[cyan]🔌 Proxy port:[/cyan] {port}")
    console.print()
    
    # Create addon with RECORD mode
    addon = ChaosProxyAddon(
        config_path=str(plan_path),
        mode=PROXY_MODE_RECORD,
        tape_path=tape_path
    )
    
    # Start mitmdump
    console.print(Rule("[bold cyan]Starting Proxy (RECORD mode)[/bold cyan]"))
    console.print()
    
    try:
        import mitmproxy.tools.dump
        from mitmproxy import options
        
        opts = options.Options(listen_port=port)
        master = mitmproxy.tools.dump.DumpMaster(opts)
        master.addons.add(addon)
        
        console.print(f"[green]✓[/green] Proxy started on port {port}")
        console.print(f"[yellow]⚠[/yellow]  Press Ctrl+C to stop recording and save tape")
        console.print()
        
        master.run()
    except KeyboardInterrupt:
        console.print()
        console.print("[yellow]Stopping proxy...[/yellow]")
        addon.done()  # This saves the tape
        console.print(f"[green]✓[/green] Tape saved: {tape_path}")
        console.print(f"[green]✓[/green] Recording complete!")
    except Exception as e:
        error_panel = Panel(
            f"[red]✗ Error:[/red]\n\n{str(e)}",
            title="[bold red]Error[/bold red]",
            box=box.ROUNDED,
            border_style="red"
        )
        console.print(error_panel)
        raise typer.Exit(1)


@app.command()
def replay(
    tape: str = typer.Argument(..., help="Path to tape file"),
    plan: Optional[str] = typer.Option(
        None,
        "--plan", "-p",
        help="Path to chaos plan YAML file (optional, for metadata)"
    ),
    port: int = typer.Option(8080, "--port", help="Proxy port")
):
    """
    Replay recorded HTTP interactions from a tape file.
    
    Runs the proxy in PLAYBACK mode, returning recorded responses
    without network access. Perfect for debugging flaky failures.
    """
    _print_logo()
    _print_welcome()
    
    tape_path = Path(tape)
    if not tape_path.exists():
        error_panel = Panel(
            f"[red]✗ Tape file not found:[/red]\n\n{tape_path}",
            title="[bold red]Error[/bold red]",
            box=box.ROUNDED,
            border_style="red"
        )
        console.print(error_panel)
        raise typer.Exit(1)

    # Load tape metadata
    try:
        from agent_chaos_sdk.storage.tape import Tape
        tape_obj = Tape.load(tape_path)
        console.print(f"[green]✓[/green] Loaded tape: {tape_path.name}")
        console.print(f"[cyan]📼 Entries:[/cyan] {len(tape_obj.entries)}")
        if tape_obj.metadata.get("created_at"):
            console.print(f"[cyan]📅 Created:[/cyan] {tape_obj.metadata['created_at']}")
        # Preflight checks for replay mode
        if plan:
            try:
                replay_plan = load_chaos_plan(str(plan))
                set_global_plan(replay_plan)
                _preflight_checks(replay_plan, PROXY_MODE_PLAYBACK)
            except Exception as e:
                error_panel = Panel(
                    f"[red]✗ Failed to load plan:[/red]\n\n{str(e)}",
                    title="[bold red]Error[/bold red]",
                    box=box.ROUNDED,
                    border_style="red"
                )
                console.print(error_panel)
                raise typer.Exit(1)
    except Exception as e:
        error_panel = Panel(
            f"[red]✗ Failed to load tape:[/red]\n\n{str(e)}",
            title="[bold red]Error[/bold red]",
            box=box.ROUNDED,
            border_style="red"
        )
        console.print(error_panel)
        raise typer.Exit(1)
    
    # Load chaos plan if provided (for metadata)
    if plan:
        plan_path = Path(plan)
        if plan_path.exists():
            try:
                chaos_plan = load_chaos_plan(str(plan_path))
                set_global_plan(chaos_plan)
                console.print(f"[green]✓[/green] Loaded chaos plan: {plan_path.name}")
            except Exception as e:
                console.print(f"[yellow]⚠[/yellow]  Failed to load plan: {e}")
    
    console.print(f"[cyan]🔌 Proxy port:[/cyan] {port}")
    console.print()
    
    # Create addon with PLAYBACK mode
    addon = ChaosProxyAddon(
        config_path=plan or "config/chaos_config.yaml",
        mode=PROXY_MODE_PLAYBACK,
        tape_path=tape_path
    )
    
    # Start mitmdump
    console.print(Rule("[bold cyan]Starting Proxy (PLAYBACK mode)[/bold cyan]"))
    console.print()
    console.print("[yellow]⚠[/yellow]  No network access - all responses from tape")
    console.print()
    
    try:
        import mitmproxy.tools.dump
        from mitmproxy import options
        
        opts = options.Options(listen_port=port)
        master = mitmproxy.tools.dump.DumpMaster(opts)
        master.addons.add(addon)
        
        console.print(f"[green]✓[/green] Proxy started on port {port}")
        console.print(f"[yellow]⚠[/yellow]  Press Ctrl+C to stop")
        console.print()
        
        master.run()
    except KeyboardInterrupt:
        console.print()
        console.print("[yellow]Stopping proxy...[/yellow]")
        addon.done()
        console.print(f"[green]✓[/green] Replay complete!")
    except Exception as e:
        error_panel = Panel(
            f"[red]✗ Error:[/red]\n\n{str(e)}",
            title="[bold red]Error[/bold red]",
            box=box.ROUNDED,
            border_style="red"
        )
        console.print(error_panel)
        raise typer.Exit(1)


@app.command()
def health_check(
    plan: Optional[str] = typer.Option(
        None,
        "--plan", "-p",
        help="Path to chaos plan YAML file (optional)"
    ),
    mode: str = typer.Option(
        "live",
        "--mode",
        help="Mode to validate (live|record|replay)"
    ),
):
    """
    Run preflight checks without starting the proxy.
    """
    _print_logo()
    _print_welcome()

    mode_lower = mode.lower()
    mode_map = {
        "live": PROXY_MODE_LIVE,
        "record": PROXY_MODE_RECORD,
        "replay": PROXY_MODE_PLAYBACK,
    }
    if mode_lower not in mode_map:
        console.print(Panel(
            f"[red]✗ Invalid mode:[/red] {mode}\n\nUse live|record|replay.",
            title="[bold red]Error[/bold red]",
            box=box.ROUNDED,
            border_style="red"
        ))
        raise typer.Exit(1)

    if plan:
        plan_path = Path(plan)
        if not plan_path.exists():
            console.print(Panel(
                f"[red]✗ Plan file not found:[/red]\n\n{plan_path}",
                title="[bold red]Error[/bold red]",
                box=box.ROUNDED,
                border_style="red"
            ))
            raise typer.Exit(1)

        try:
            chaos_plan = load_chaos_plan(str(plan_path))
            set_global_plan(chaos_plan)
        except Exception as e:
            console.print(Panel(
                f"[red]✗ Failed to load plan:[/red]\n\n{str(e)}",
                title="[bold red]Error[/bold red]",
                box=box.ROUNDED,
                border_style="red"
            ))
            raise typer.Exit(1)
    else:
        chaos_plan = ChaosPlan()

    try:
        # Health-check should not require a running local LLM by default.
        os.environ["CHAOS_LLM_HEALTH_SKIP"] = "true"
        _preflight_checks(chaos_plan, mode_map[mode_lower])
        console.print(Panel(
            "[green]✓ All preflight checks passed[/green]",
            title="[bold green]Ready[/bold green]",
            box=box.ROUNDED,
            border_style="green"
        ))
    except Exception as e:
        console.print(Panel(
            f"[red]✗ Preflight checks failed:[/red]\n\n{str(e)}",
            title="[bold red]Error[/bold red]",
            box=box.ROUNDED,
            border_style="red"
        ))
        raise typer.Exit(1)
    


if __name__ == "__main__":
    app()

