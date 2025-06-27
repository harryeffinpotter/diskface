#!/usr/bin/env python3

import os
import argparse
import sys
import fnmatch
import glob
import shutil
import tempfile
from pathlib import Path, PurePath
from typing import List, Set, Tuple, Dict
from datetime import datetime

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich import print as rprint
from rich.live import Live

console = Console()

# Default paths to exclude from scanning
DEFAULT_EXCLUDES = {
    '/proc', '/sys', '/dev', '/run',  # System
    '/boot', '/lost+found', '/drive',           # Boot and system recovery
    '/var/lib/docker', '/.pycache',
    '**/*vscode*',
    '**/*windsurf*', # Docker (often large)
    '/var/cache/apt',                 # Package manager cache
    '/root/.cache',
    '.cache',
    '.local', # Root user cache
    '**/.git',                        # Git directories
    '**/cache',
    '/media',
    '/home/becky/drive', # Cache directories
    '**/node_modules',                # Node.js modules
    '**/*.pyc',                       # Python compiled files
    '**/tmp',                         # Temporary directories
    '**/temp',
    '**/*pycache*',
    '**/.pyenv'
}

# Temporary directories and patterns to clean
TEMP_PATHS = [
    '/tmp',
    '/var/tmp',
    '~/.cache',
    '/var/cache',
    '/var/log/*.gz',
    '/var/log/old',
    '**/*.tmp',
    '**/*~',
    '**/__pycache__',
    '**/node_modules',
    '**/.pytest_cache',
    '**/.mypy_cache',
]

def path_matches_pattern(path: str, pattern: str) -> bool:
    """Check if path matches the given pattern using glob rules."""
    pattern = PurePath(pattern)
    path = PurePath(path)

    if pattern.is_absolute():
        return fnmatch.fnmatch(str(path).lower(), str(pattern).lower())

    pattern_parts = str(pattern).split('/')
    path_parts = str(path).split('/')

    if '**' in pattern_parts:
        return fnmatch.fnmatch(str(path).lower(), f"*{pattern_parts[-1]}".lower())
    else:
        return any(
            fnmatch.fnmatch('/'.join(path_parts[i:i+len(pattern_parts)]).lower(), str(pattern).lower())
            for i in range(len(path_parts) - len(pattern_parts) + 1)
        )

def should_exclude(path: str, exclusions: Set[str]) -> bool:
    """Check if path should be excluded based on exclusion patterns."""
    return any(path_matches_pattern(path, excl) for excl in exclusions)

def get_dir_size(path: str, exclusions: Set[str], progress) -> int:
    """Calculate total size of a directory, respecting exclusions."""
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path, topdown=True):
            dirnames[:] = [d for d in dirnames if not should_exclude(os.path.join(dirpath, d), exclusions)]
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp) and not should_exclude(fp, exclusions):
                    try:
                        total_size += os.path.getsize(fp)
                    except (OSError, FileNotFoundError):
                        continue
    except (PermissionError, OSError):
        return 0
    return total_size

def clean_temp_files(progress) -> Dict[str, int]:
    """Clean temporary files and return sizes cleaned by category."""
    cleaned_sizes = {}

    def clean_path(path: str) -> int:
        total_cleaned = 0
        try:
            if os.path.exists(path):
                size = get_dir_size(path, set(), progress)
                if os.path.isfile(path):
                    os.remove(path)
                else:
                    shutil.rmtree(path, ignore_errors=True)
                total_cleaned += size
        except (PermissionError, OSError):
            pass
        return total_cleaned

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Cleaning temporary files...", total=None)
        for temp_path in TEMP_PATHS:
            if temp_path.startswith('~'):
                temp_path = os.path.expanduser(temp_path)
            if '*' in temp_path:
                paths = glob.glob(temp_path, recursive=True)
                category = os.path.basename(temp_path)
                cleaned_size = 0
                for p in paths:
                    progress.update(task, description=f"Cleaning: {p}")
                    cleaned_size += clean_path(p)
                if cleaned_size > 0:
                    cleaned_sizes[category] = cleaned_size
            else:
                progress.update(task, description=f"Cleaning: {temp_path}")
                cleaned_size = clean_path(temp_path)
                if cleaned_size > 0:
                    cleaned_sizes[os.path.basename(temp_path)] = cleaned_size

    return cleaned_sizes

def human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def create_top_dirs_table(results: List[Tuple[str, int]]) -> Table:
    """Create a table of top directories."""
    table = Table(show_header=True, header_style="bold magenta", title="Top 10 Largest Directories")
    table.add_column("Size", style="cyan", justify="right")
    table.add_column("Directory", style="green")
    sorted_results = sorted(results, key=lambda x: x[1], reverse=True)[:10]
    if not sorted_results:
        table.add_row("--", "No directories found yet...")
        return table
    total_size = sum(size for _, size in sorted_results)
    for path, size in sorted_results:
        percentage = (size / total_size) * 100 if total_size > 0 else 0
        table.add_row(
            human_readable_size(size),
            f"{path} [dim]({percentage:.1f}%)[/]"
        )
    return table

def analyze_disk_usage(root_path: str,
                       exclusions: Set[str],
                       min_size_mb: float = 100,
                       ignore_dotfolders: bool = False
                      ) -> List[Tuple[str, int]]:
    """Analyze disk usage starting from root_path."""
    results = []
    min_size_bytes = min_size_mb * 1024 * 1024

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    )

    table = create_top_dirs_table(results)
    layout = Table.grid()
    layout.add_row(Panel(progress))
    layout.add_row(Panel(table))

    with Live(layout, console=console, refresh_per_second=4) as live:
        scan_task = progress.add_task("Starting scan...", total=None)
        try:
            for dirpath, dirnames, filenames in os.walk(root_path, topdown=True):
                # ignore dot-folders if requested
                if ignore_dotfolders:
                    dirnames[:] = [d for d in dirnames if not d.startswith('.')]
                # apply exclusions
                dirnames[:] = [d for d in dirnames if not should_exclude(os.path.join(dirpath, d), exclusions)]

                progress.update(scan_task, description=f"Scanning: {dirpath[:60]}..." if len(dirpath) > 60 else f"Scanning: {dirpath}")
                try:
                    current_size = 0
                    for f in filenames:
                        if ignore_dotfolders and f.startswith('.'):
                            continue
                        fp = os.path.join(dirpath, f)
                        if not os.path.islink(fp) and not should_exclude(fp, exclusions):
                            try:
                                current_size += os.path.getsize(fp)
                            except (OSError, FileNotFoundError):
                                pass
                    if current_size >= min_size_bytes:
                        results.append((dirpath, current_size))
                        table = create_top_dirs_table(results)
                        layout = Table.grid()
                        layout.add_row(Panel(progress))
                        layout.add_row(Panel(table))
                        live.update(layout)
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError) as e:
            console.print(f"[red]Error accessing {root_path}: {e}[/]", style="bold red")

    return sorted(results, key=lambda x: x[1], reverse=True)

def display_results(results: List[Tuple[str, int]], top_n: int):
    """Display results in a beautiful table format."""
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Size", style="cyan", justify="right")
    table.add_column("Directory", style="green")

    total_size = sum(size for _, size in results)
    for path, size in results[:top_n]:
        percentage = (size / total_size) * 100
        table.add_row(
            human_readable_size(size),
            f"{path} [dim]({percentage:.1f}%)[/]"
        )

    console.print("\n")
    console.print(Panel.fit(
        f"[bold]Disk Usage Analysis[/]\n[dim]Total size of found directories: {human_readable_size(total_size)}[/]",
        border_style="blue"
    ))
    console.print(table)

def display_cleaned_sizes(cleaned_sizes: Dict[str, int]):
    """Display information about cleaned temporary files."""
    if not cleaned_sizes:
        console.print("\n[yellow]No temporary files were cleaned.[/]")
        return
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Category", style="green")
    table.add_column("Space Freed", style="cyan", justify="right")

    total_cleaned = sum(cleaned_sizes.values())
    for category, size in sorted(cleaned_sizes.items(), key=lambda x: x[1], reverse=True):
        table.add_row(category, human_readable_size(size))

    console.print("\n")
    console.print(Panel.fit(
        f"[bold]Cleanup Results[/]\n[dim]Total space freed: {human_readable_size(total_cleaned)}[/]",
        border_style="green"
    ))
    console.print(table)

def main():
    parser = argparse.ArgumentParser(description='Analyze disk usage and find largest directories.')
    parser.add_argument('--exclude', '-e', action='append', default=[],
                       help='Additional patterns to exclude (can be used multiple times)')
    parser.add_argument('--min-size', '-m', type=float, default=100,
                       help='Minimum size in MB to report (default: 100)')
    parser.add_argument('--top', '-t', type=int, default=20,
                       help='Number of top directories to show (default: 20)')
    parser.add_argument('--clean', '-c', action='store_true',
                       help='Clean temporary files before analysis')
    parser.add_argument('--include-os', action='store_true',
                       help='Include OS directories in analysis')
    parser.add_argument('--ignore-dotfolders', '-d', action='store_true',
                       help='Ignore any directory (and its contents) whose name starts with a dot')
    args = parser.parse_args()

    if os.geteuid() != 0:
        console.print("[yellow]Warning: Running without sudo privileges. Some directories may be inaccessible.[/]")
        console.print("[yellow]Consider running with sudo for full access.[/]\n")

    if args.clean:
        if os.geteuid() != 0:
            console.print("[red]Error: Cleaning temporary files requires sudo privileges.[/]")
            sys.exit(1)
        cleaned_sizes = clean_temp_files(None)
        display_cleaned_sizes(cleaned_sizes)

    exclusions = set(args.exclude)
    if not args.include_os:
        exclusions.update(DEFAULT_EXCLUDES)

    console.print(Panel.fit(
        f"[bold green]Disk Space Analyzer[/]\n[dim]Excluding: {', '.join(sorted(exclusions))}[/]",
        border_style="green"
    ))

    start_time = datetime.now()
    results = analyze_disk_usage('/', exclusions, args.min_size, args.ignore_dotfolders)
    end_time = datetime.now()
    scan_duration = (end_time - start_time).total_seconds()

    display_results(results, args.top)
    console.print(f"\n[dim]Scan completed in {scan_duration:.1f} seconds[/]")

if __name__ == '__main__':
    main()
