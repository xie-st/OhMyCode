"""`ohmycode vchange` — git-based version switch (browse & checkout commits on main)."""

from __future__ import annotations

import os
import subprocess

from rich.console import Console


_console = Console()


def run_vchange(step: int | None = None) -> int:
    """Version switch: step=None shows status, step=-1 goes back, step=1 goes forward."""
    cwd = os.getcwd()

    r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                       capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        _console.print("[red]Not in a git repository.[/red]")
        return 1

    if step is None:
        log = subprocess.run(["git", "log", "--oneline", "-5"],
                             capture_output=True, text=True, cwd=cwd)
        head = subprocess.run(["git", "rev-parse", "HEAD"],
                              capture_output=True, text=True, cwd=cwd).stdout.strip()
        _console.print(f"\n  [bold]Recent commits:[/]")
        for line in log.stdout.strip().splitlines():
            sha = line.split()[0]
            if head.startswith(sha):
                _console.print(f"    [green]▸ {line}[/]  [green]← HEAD[/]")
            else:
                _console.print(f"    [dim]  {line}[/]")
        _console.print(f"\n  [dim]Usage: ohmycode vchange -1 (back) / ohmycode vchange 1 (forward)[/]")
        return 0

    if step == 0:
        _console.print("[dim]Nothing to do.[/dim]")
        return 0

    all_log = subprocess.run(["git", "log", "main", "--oneline", "--reverse"],
                             capture_output=True, text=True, cwd=cwd)
    all_commits = all_log.stdout.strip().splitlines()
    if not all_commits:
        _console.print("[yellow]No commits found.[/yellow]")
        return 1

    head_sha = subprocess.run(["git", "rev-parse", "HEAD"],
                              capture_output=True, text=True, cwd=cwd).stdout.strip()
    current_idx = -1
    for i, line in enumerate(all_commits):
        sha = line.split()[0]
        if head_sha.startswith(sha):
            current_idx = i
            break

    if current_idx == -1:
        _console.print("[yellow]HEAD is not on main branch history.[/yellow]")
        return 1

    target_idx = current_idx + step
    if target_idx < 0:
        _console.print("[yellow]Already at the oldest commit. Cannot go back further.[/yellow]")
        return 1
    if target_idx >= len(all_commits):
        _console.print("[yellow]Already at the latest commit. Cannot go forward.[/yellow]")
        return 1

    target_line = all_commits[target_idx]
    target_sha = target_line.split()[0]

    _console.print(f"\n  [bold]Current:[/] {all_commits[current_idx]}")
    _console.print(f"  [bold]Target: [/] {target_line}")

    status = subprocess.run(["git", "status", "--porcelain"],
                            capture_output=True, text=True, cwd=cwd)
    if status.stdout.strip():
        n = len(status.stdout.strip().splitlines())
        _console.print(f"  [yellow]Warning: {n} uncommitted change{'s' if n > 1 else ''} will be lost[/yellow]")

    _console.print("  [bold]Confirm? (y/n):[/bold] ", end="")
    answer = input().strip().lower()
    if answer == "y":
        subprocess.run(["git", "checkout", target_sha, "--force"],
                       capture_output=True, text=True, cwd=cwd)
        _console.print(f"  [green]✓ Switched to: {target_line}[/green]")
        _console.print("  [dim]Restart ohmycode to load the changed code.[/dim]")
        return 0
    else:
        _console.print("  [dim]Cancelled.[/dim]")
        return 0
