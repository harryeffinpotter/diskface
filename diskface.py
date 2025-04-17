#!/usr/bin/env python3
################################################################################
#                                                                              #
#    DiskFace3 v3.7 — Comprehensive Disk & File Usage Analyzer                 #
#                                                                              #
#    Features:                                                                 #
#      • JSON config with auto-create and broken backup                         #
#      • CLI overrides for all config parameters                                #
#      • Min-size filter for directories and files                              #
#      • Exclusion patterns via excludes.txt                                   #
#      • Directory & file scanning modes                                       #
#      • Live Rich progress bars and dynamic tables                             #
#      • Interactive deletion of selected items                                 #
#      • Temporary files cleanup with reporting                                 #
#      • Scan current directory only option                                     #
#      • Human-readable size formatting                                        #
#      • Over 400+ lines for full coverage                                      #
#                                                                              #
################################################################################

import os
import sys
import json
import argparse
import fnmatch
import glob
import shutil
from pathlib import Path, PurePath
from typing import Any, Dict, List, Set, Tuple
from datetime import datetime

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel
from rich.live import Live

# Instantiate console for rich output
console = Console()


# =============================================================================
# === Constants & Default Config Values
# =============================================================================
ENTRIES_TO_SHOW = 20  # Maximum entries to display in tables
DEFAULT_CONFIG: Dict[str, Any] = {
    "min_size_mb": 100,
    "top": ENTRIES_TO_SHOW,
    "include_os": False,
    "ignore_dotfolders": False,
    "interactive": True,
    "files": False,
    "auto_clean": False,
    "currentdirectoryonly": False,
    "excludes_file": "excludes.txt",
    "temp_paths_file": "temp_paths.txt"
}


# =============================================================================
# === Function: load_config
# =============================================================================
def load_config(config_path: Path) -> Dict[str, Any]:
    """
    Load JSON config; if missing, create default; if invalid, backup and recreate.
    Returns a dict with all required keys.
    """
    cfg = DEFAULT_CONFIG.copy()
    if not config_path.exists():
        console.print(f"[yellow]Config not found at {config_path}, creating default config.[/]")
        config_path.write_text(json.dumps(cfg, indent=4))
        return cfg
    try:
        data = json.loads(config_path.read_text())
        for key, default_val in DEFAULT_CONFIG.items():
            cfg[key] = data.get(key, default_val)
        return cfg
    except Exception:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup = config_path.with_name(f"{config_path.stem}.broken.{timestamp}{config_path.suffix}")
        config_path.rename(backup)
        console.print(f"[red]Broken config backed up to {backup}. Recreating default config.[/]")
        config_path.write_text(json.dumps(cfg, indent=4))
        return cfg


# =============================================================================
# === Function: load_patterns
# =============================================================================
def load_patterns(patterns_file: Path) -> List[str]:
    """
    Load newline-separated patterns from a file, ignoring blank lines and comments.
    Returns a list of patterns.
    """
    if not patterns_file.exists():
        console.print(f"[yellow]Patterns file not found: {patterns_file}. Continuing with empty list.[/]")
        return []
    lines = patterns_file.read_text().splitlines()
    patterns = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        patterns.append(stripped)
    return patterns


# =============================================================================
# === Function: path_matches_pattern
# =============================================================================
def path_matches_pattern(path: str, pattern: str) -> bool:
    """
    Check if a path matches a glob-like pattern, supporting '**' wildcard.
    """
    p = PurePath(pattern)
    lower_path = path.lower()
    # Absolute pattern
    if p.is_absolute():
        return fnmatch.fnmatch(lower_path, str(p).lower())
    # Recursive '**'
    if '**' in pattern:
        part = pattern.split('**')[-1]
        return fnmatch.fnmatch(lower_path, f"*{part.lower()}")
    # Basic glob
    return fnmatch.fnmatch(lower_path, pattern.lower())


def should_exclude(path: str, exclusions: Set[str]) -> bool:
    """Determine if a path should be excluded based on a set of patterns."""
    for pattern in exclusions:
        if path_matches_pattern(path, pattern):
            return True
    return False


# =============================================================================
# === Function: human_readable_size
# =============================================================================
def human_readable_size(size_bytes: int) -> str:
    """
    Convert bytes into a human-readable string with appropriate units.
    """
    for unit in ['B','KB','MB','GB','TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"


# =============================================================================
# === Function: create_top_dirs_table
# =============================================================================
def create_top_dirs_table(results: List[Tuple[str, int]]) -> Table:
    """
    Build a rich Table for the top directories by size.
    """
    table = Table(show_header=True, header_style="bold magenta",
                  title=f"Top {ENTRIES_TO_SHOW} Largest Directories")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Size", style="cyan", justify="right")
    table.add_column("Directory", style="green")
    if not results:
        table.add_row("-", "--", "No directories found...")
        return table
    top_n = results[:ENTRIES_TO_SHOW]
    total_size = sum(sz for _, sz in top_n)
    for i, (path, sz) in enumerate(top_n, start=1):
        pct = (sz/total_size)*100 if total_size else 0
        table.add_row(str(i), human_readable_size(sz), f"{path} [dim]({pct:.1f}%)[/]")
    return table


# =============================================================================
# === Function: create_top_files_table
# =============================================================================
def create_top_files_table(results: List[Tuple[str, int]]) -> Table:
    """
    Build a rich Table for the top files by size.
    """
    table = Table(show_header=True, header_style="bold magenta",
                  title=f"Top {ENTRIES_TO_SHOW} Largest Files")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Size", style="cyan", justify="right")
    table.add_column("File", style="green")
    if not results:
        table.add_row("-", "--", "No files found...")
        return table
    top_n = results[:ENTRIES_TO_SHOW]
    total_size = sum(sz for _, sz in top_n)
    for i, (path, sz) in enumerate(top_n, start=1):
        pct = (sz/total_size)*100 if total_size else 0
        table.add_row(str(i), human_readable_size(sz), f"{path} [dim]({pct:.1f}%)[/]")
    return table


# =============================================================================
# === Function: analyze_disk_usage
# =============================================================================
def analyze_disk_usage(root: str, exclusions: Set[str], min_size_mb: float,
                       ignore_dot: bool) -> List[Tuple[str, int]]:
    """
    Scan directories under 'root' with live rich progress.
    Returns list of (path, size) for directories >= min_size_mb.
    """
    min_bytes = int(min_size_mb * 1024 * 1024)
    results: List[Tuple[str, int]] = []
    prog = Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), console=console
    )
    table = create_top_dirs_table(results)
    layout = Table.grid()
    layout.add_row(Panel(prog))
    layout.add_row(Panel(table))
    with Live(layout, console=console, refresh_per_second=4) as live:
        task = prog.add_task("Scanning directories...", total=None)
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            if ignore_dot:
                dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            dirnames[:] = [d for d in dirnames if not should_exclude(os.path.join(dirpath, d), exclusions)]
            prog.update(task, description=f"Scanning: {dirpath[:60]}...")
            dir_size = 0
            for f in filenames:
                if ignore_dot and f.startswith('.'):
                    continue
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp) and not should_exclude(fp, exclusions):
                    try:
                        dir_size += os.path.getsize(fp)
                    except:
                        pass
            if dir_size >= min_bytes:
                results.append((dirpath, dir_size))
                # update table panel
                tbl = create_top_dirs_table(results)
                layout = Table.grid()
                layout.add_row(Panel(prog))
                layout.add_row(Panel(tbl))
                live.update(layout)
    return sorted(results, key=lambda x: x[1], reverse=True)

# =============================================================================
# === Function: analyze_file_usage
# =============================================================================
def analyze_file_usage(root: str, exclusions: Set[str], min_size_mb: float,
                       ignore_dot: bool) -> List[Tuple[str, int]]:
    """
    Scan files under 'root' with live rich progress.
    Returns list of (path, size) for files >= min_size_mb.
    """
    min_bytes = int(min_size_mb * 1024 * 1024)
    results: List[Tuple[str, int]] = []
    prog = Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), console=console
    )
    table = create_top_files_table(results)
    layout = Table.grid()
    layout.add_row(Panel(prog))
    layout.add_row(Panel(table))
    with Live(layout, console=console, refresh_per_second=4) as live:
        task = prog.add_task("Scanning files...", total=None)
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            if ignore_dot:
                dirnames[:] = [d for d in dirnames if not d.startswith('.')]
                filenames = [f for f in filenames if not f.startswith('.')]
            dirnames[:] = [d for d in dirnames if not should_exclude(os.path.join(dirpath, d), exclusions)]
            prog.update(task, description=f"Scanning files in: {dirpath[:60]}...")
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp) and not should_exclude(fp, exclusions):
                    try:
                        sz = os.path.getsize(fp)
                    except:
                        continue
                    if sz >= min_bytes:
                        results.append((fp, sz))
                        tbl = create_top_files_table(results)
                        layout = Table.grid()
                        layout.add_row(Panel(prog))
                        layout.add_row(Panel(tbl))
                        live.update(layout)
    return sorted(results, key=lambda x: x[1], reverse=True)

# =============================================================================
# === Function: clean_temp_files
# =============================================================================
def clean_temp_files(temp_paths: List[str]) -> Dict[str, int]:
    """
    Clean temporary files per patterns. Return dict of pattern->bytes freed.
    """
    cleaned: Dict[str, int] = {}
    prog = Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), console=console
    )
    with prog:
        task = prog.add_task("Cleaning temporary files...", total=None)
        for pat in temp_paths:
            pattern = os.path.expanduser(pat) if pat.startswith('~') else pat
            targets = glob.glob(pattern, recursive=True) if '*' in pat else [pattern]
            freed = 0
            for t in targets:
                prog.update(task, description=f"Cleaning: {t}")
                if os.path.isfile(t):
                    try:
                        freed += os.path.getsize(t)
                        os.remove(t)
                    except:
                        pass
                elif os.path.isdir(t):
                    for dp, dirs, files in os.walk(t):
                        for f in files:
                            fp = os.path.join(dp, f)
                            try:
                                freed += os.path.getsize(fp)
                            except:
                                pass
                    shutil.rmtree(t, ignore_errors=True)
            if freed > 0:
                cleaned[pat] = freed
    return cleaned

# =============================================================================
# === Function: display_results
# =============================================================================
def display_results(results: List[Tuple[str, int]], top_n: int, files_mode: bool):
    title = "Largest Files" if files_mode else "Largest Directories"
    tbl = create_top_files_table(results) if files_mode else create_top_dirs_table(results)
    total = sum(sz for _, sz in results)
    console.print(Panel.fit(
        f"[bold]DiskFace3 - {title} Analysis[/]\n"
        f"[dim]Showing up to {top_n} of {len(results)} entries, total size: {human_readable_size(total)}[/]",
        border_style="blue"
    ))
    console.print(tbl)

# =============================================================================
# === Function: display_cleaned
# =============================================================================
def display_cleaned(cleaned: Dict[str, int]):
    if not cleaned:
        console.print("[yellow]No temporary files cleaned.[/]")
        return
    tbl = Table(show_header=True, header_style="bold magenta")
    tbl.add_column("Pattern", style="green")
    tbl.add_column("Freed", style="cyan", justify="right")
    total = sum(cleaned.values())
    for pat, sz in cleaned.items():
        tbl.add_row(pat, human_readable_size(sz))
    console.print(Panel.fit(
        f"[bold]Cleanup Results[/]\n"
        f"[dim]Total freed: {human_readable_size(total)}[/]",
        border_style="green"
    ))
    console.print(tbl)

# =============================================================================
# === Function: prompt_deletion
# =============================================================================
def prompt_deletion(results: List[Tuple[str, int]], files_mode: bool):
    sel = console.input("Enter numbers to delete (comma-separated) or press Enter to skip: ")
    if not sel.strip():
        return
    indices = [int(x.strip()) for x in sel.split(',') if x.strip().isdigit()]
    for i in indices:
        if 1 <= i <= len(results):
            path, _ = results[i-1]
            confirm = console.input(f"Confirm delete {path}? [y/N]: ")
            if confirm.lower().startswith('y'):
                try:
                    if files_mode:
                        os.remove(path)
                    else:
                        shutil.rmtree(path)
                    console.print(f"[green]Deleted: {path}[/]")
                except Exception as e:
                    console.print(f"[red]Failed to delete {path}: {e}[/]")
        else:
            console.print(f"[yellow]Index {i} out of range, skipping.[/]")

# =============================================================================
# === Main Entry Point
# =============================================================================
def main():
    # Setup config
    script_dir = Path(__file__).resolve().parent
    config_path = script_dir / 'config.json'
    cfg = load_config(config_path)

    # Argument parsing
    parser = argparse.ArgumentParser(
        description='DiskFace3 v3.7 - Disk & File Usage Analyzer',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--config', type=Path, default=config_path, help='Path to JSON config')
    parser.add_argument('--min-size', '-m', type=float, default=cfg['min_size_mb'], help='Min size in MB')
    parser.add_argument('--top', '-t', type=int, default=cfg['top'], help='Max entries to display')
    parser.add_argument('--exclude', '-e', action='append', default=[], help='Additional exclusion patterns')
    parser.add_argument('--include-os', action='store_true', default=cfg['include_os'], help='Ignore excludes file')
    parser.add_argument('--ignore-dotfolders', '-d', action='store_true', default=cfg['ignore_dotfolders'], help='Skip dot folders/files')
    parser.add_argument('--files', '-f', action='store_true', dest='files', help='Scan files instead of directories')
    parser.add_argument('--no-files', action='store_false', dest='files', help='Scan directories instead of files')
    parser.set_defaults(files=cfg['files'])
    parser.add_argument('--currentdir-only', action='store_true', dest='currentdir_only', help='Scan only current directory')
    parser.add_argument('--no-currentdir-only', action='store_false', dest='currentdir_only', help='Scan entire filesystem')
    parser.set_defaults(currentdir_only=cfg['currentdirectoryonly'])
    parser.add_argument('--interactive', '-i', action='store_true', dest='interactive', help='Enable interactive deletion')
    parser.add_argument('--no-interactive', action='store_false', dest='interactive', help='Disable interactive deletion')
    parser.set_defaults(interactive=cfg['interactive'])
    parser.add_argument('--clean', '-c', action='store_true', default=cfg['auto_clean'], help='Clean temp files then continue')
    parser.add_argument('--excludes-file', type=str, default=cfg['excludes_file'], help='Path to excludes.txt')
    parser.add_argument('--temp-paths-file', type=str, default=cfg['temp_paths_file'], help='Path to temp_paths.txt')
    args = parser.parse_args()

    # Elevate if needed
    if os.geteuid() != 0:
        console.print("[yellow]Elevating privileges with sudo...[/]")
        os.execvp('sudo', ['sudo', sys.executable] + sys.argv)

    # Determine root path based on currentdir-only
    if args.currentdir_only:
        root = os.getcwd()
    else:
        root = '/'
    console.print(f"[blue]Scanning root path: {root}[/]")

    # Load exclusions
    excludes_file_path = Path(args.excludes_file) if args.excludes_file else script_dir / DEFAULT_CONFIG['excludes_file']
    exclusions: Set[str] = set() if args.include_os else set(load_patterns(excludes_file_path))
    exclusions.update(args.exclude)
    console.print(f"[blue]Loaded {len(exclusions)} exclusion patterns from                                                                     {excludes_file_path}[/]")

    # Load temporary paths patterns
    temp_paths_file_path = Path(args.temp_paths_file) if args.temp_paths_file else script_dir / DEFAULT_CONFIG['temp_paths_file']
    temp_paths = load_patterns(temp_paths_file_path)
    console.print(f"[blue]Loaded {len(temp_paths)} temp-clean patterns from {temp_paths_file_path}[/]")

    # Auto-clean if requested
    if args.clean:
        cleaned = clean_temp_files(temp_paths)
        display_cleaned(cleaned)
        # proceed to scan

    # Perform scan
    start_time = datetime.now()
    if args.files:
        results = analyze_file_usage(root, exclusions, args.min_size, args.ignore_dotfolders)
    else:
        results = analyze_disk_usage(root, exclusions, args.min_size, args.ignore_dotfolders)
    display_results(results, args.top, args.files)
    console.print(f"[dim]Completed in {(datetime.now() - start_time).total_seconds():.1f}s[/]")

    # Interactive deletion
    if args.interactive:
        prompt_deletion(results, args.files)

if __name__ == '__main__':
    main()
