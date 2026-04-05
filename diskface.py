#!/usr/bin/env python3
# diskface v3.8 - disk usage analyzer with live sorted results
# scans from cwd by default, use --root to scan everything

import os
import sys
import json
import argparse
import bisect
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

console = Console()

DEFAULT_CONFIG: Dict[str, Any] = {
    "min_size_mb": 100,
    "top": 20,
    "max_depth": 8,
    "scan_files": False,
    "scan_root": False,
    "hide_dotfiles": False,
    "no_excludes": False,
    "interactive": True,
    "auto_clean": False,
    "excludes_file": "excludes.txt",
    "temp_paths_file": "temp_paths.txt"
}


def load_config(config_path: Path) -> Dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    if not config_path.exists():
        console.print(f"[yellow]config not found at {config_path}, creating defaults[/]")
        config_path.write_text(json.dumps(cfg, indent=4))
        return cfg
    try:
        data = json.loads(config_path.read_text())
        for key, default in DEFAULT_CONFIG.items():
            cfg[key] = data.get(key, default)
        return cfg
    except Exception:
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        backup = config_path.with_name(f"{config_path.stem}.broken.{ts}{config_path.suffix}")
        config_path.rename(backup)
        console.print(f"[red]broken config backed up to {backup}, recreating defaults[/]")
        config_path.write_text(json.dumps(cfg, indent=4))
        return cfg


def load_patterns(path: Path) -> List[str]:
    if not path.exists():
        console.print(f"[yellow]patterns file not found: {path}, skipping[/]")
        return []
    return [l.strip() for l in path.read_text().splitlines()
            if l.strip() and not l.strip().startswith('#')]


def path_matches(path: str, pattern: str) -> bool:
    lp = path.lower()
    if PurePath(pattern).is_absolute():
        return fnmatch.fnmatch(lp, str(PurePath(pattern)).lower())
    if '**' in pattern:
        tail = pattern.split('**')[-1]
        return fnmatch.fnmatch(lp, f"*{tail.lower()}")
    return fnmatch.fnmatch(lp, pattern.lower())


def should_exclude(path: str, exclusions: Set[str]) -> bool:
    return any(path_matches(path, p) for p in exclusions)


def human_size(b: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if b < 1024:
            return f"{b:.2f} {unit}"
        b /= 1024
    return f"{b:.2f} PB"


# sorted insert, keeps top_n largest (stored ascending, displayed reversed)
def _insert(top: List[Tuple[int, str]], size: int, path: str, n: int):
    bisect.insort(top, (size, path))
    if len(top) > n:
        top.pop(0)


def _descending(top: List[Tuple[int, str]]) -> List[Tuple[str, int]]:
    return [(p, s) for s, p in reversed(top)]


def _make_table(results: List[Tuple[str, int]], top_n: int, title: str) -> Table:
    table = Table(show_header=True, header_style="bold magenta", title=title)
    table.add_column("#", style="dim", justify="right")
    table.add_column("Size", style="cyan", justify="right")
    table.add_column("Path", style="green")
    if not results:
        table.add_row("-", "--", "nothing found...")
        return table
    shown = results[:top_n]
    total = sum(s for _, s in shown)
    for i, (path, sz) in enumerate(shown, 1):
        pct = (sz / total) * 100 if total else 0
        table.add_row(str(i), human_size(sz), f"{path} [dim]({pct:.1f}%)[/]")
    return table


def _make_progress():
    return Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), console=console
    )


def _scan(root: str, exclusions: Set[str], min_mb: float, hide_dot: bool,
          top_n: int, max_depth, scan_files: bool) -> List[Tuple[str, int]]:
    min_bytes = int(min_mb * 1024 * 1024)
    root_depth = root.rstrip(os.sep).count(os.sep)
    top_list: List[Tuple[int, str]] = []
    label = "files" if scan_files else "dirs"
    title = f"Top {top_n} Largest {'Files' if scan_files else 'Directories'}"

    prog = _make_progress()
    tbl = _make_table([], top_n, title)
    layout = Table.grid()
    layout.add_row(Panel(prog))
    layout.add_row(Panel(tbl))

    with Live(layout, console=console, refresh_per_second=4) as live:
        task = prog.add_task(f"scanning {label}...", total=None)

        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            # depth limit
            depth = dirpath.rstrip(os.sep).count(os.sep) - root_depth
            if depth >= max_depth:
                dirnames.clear()

            if hide_dot:
                dirnames[:] = [d for d in dirnames if not d.startswith('.')]
                if scan_files:
                    filenames = [f for f in filenames if not f.startswith('.')]

            dirnames[:] = [d for d in dirnames
                           if not should_exclude(os.path.join(dirpath, d), exclusions)]

            prog.update(task, description=f"scanning: {dirpath[:60]}...")

            if scan_files:
                # file mode, check each file individually
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.islink(fp) or should_exclude(fp, exclusions):
                        continue
                    try:
                        sz = os.path.getsize(fp)
                    except:
                        continue
                    if sz >= min_bytes:
                        _insert(top_list, sz, fp, top_n)
                        tbl = _make_table(_descending(top_list), top_n, title)
                        layout = Table.grid()
                        layout.add_row(Panel(prog))
                        layout.add_row(Panel(tbl))
                        live.update(layout)
            else:
                # dir mode, sum up all files in this dir
                dir_size = 0
                for f in filenames:
                    if hide_dot and f.startswith('.'):
                        continue
                    fp = os.path.join(dirpath, f)
                    if os.path.islink(fp) or should_exclude(fp, exclusions):
                        continue
                    try:
                        dir_size += os.path.getsize(fp)
                    except:
                        pass
                if dir_size >= min_bytes:
                    _insert(top_list, dir_size, dirpath, top_n)
                    tbl = _make_table(_descending(top_list), top_n, title)
                    layout = Table.grid()
                    layout.add_row(Panel(prog))
                    layout.add_row(Panel(tbl))
                    live.update(layout)

    return _descending(top_list)


def clean_temp_files(temp_paths: List[str]) -> Dict[str, int]:
    cleaned: Dict[str, int] = {}
    prog = _make_progress()
    with prog:
        task = prog.add_task("cleaning temp files...", total=None)
        for pat in temp_paths:
            pattern = os.path.expanduser(pat) if pat.startswith('~') else pat
            targets = glob.glob(pattern, recursive=True) if '*' in pat else [pattern]
            freed = 0
            for t in targets:
                prog.update(task, description=f"cleaning: {t}")
                if os.path.isfile(t):
                    try:
                        freed += os.path.getsize(t)
                        os.remove(t)
                    except:
                        pass
                elif os.path.isdir(t):
                    for dp, _, files in os.walk(t):
                        for f in files:
                            try:
                                freed += os.path.getsize(os.path.join(dp, f))
                            except:
                                pass
                    shutil.rmtree(t, ignore_errors=True)
            if freed > 0:
                cleaned[pat] = freed
    return cleaned


def display_results(results: List[Tuple[str, int]], top_n: int, files_mode: bool):
    title = f"Top {top_n} Largest {'Files' if files_mode else 'Directories'}"
    tbl = _make_table(results, top_n, title)
    total = sum(s for _, s in results)
    console.print(Panel.fit(
        f"[bold]diskface - {title}[/]\n"
        f"[dim]showing top {min(top_n, len(results))} entries, "
        f"total size: {human_size(total)}[/]",
        border_style="blue"
    ))
    console.print(tbl)


def display_cleaned(cleaned: Dict[str, int]):
    if not cleaned:
        console.print("[yellow]nothing to clean[/]")
        return
    tbl = Table(show_header=True, header_style="bold magenta")
    tbl.add_column("Pattern", style="green")
    tbl.add_column("Freed", style="cyan", justify="right")
    total = sum(cleaned.values())
    for pat, sz in cleaned.items():
        tbl.add_row(pat, human_size(sz))
    console.print(Panel.fit(
        f"[bold]cleanup results[/]\n[dim]total freed: {human_size(total)}[/]",
        border_style="green"
    ))
    console.print(tbl)


def prompt_deletion(results: List[Tuple[str, int]], files_mode: bool):
    sel = console.input("enter numbers to delete (comma-separated) or enter to skip: ")
    if not sel.strip():
        return
    indices = [int(x.strip()) for x in sel.split(',') if x.strip().isdigit()]
    for i in indices:
        if 1 <= i <= len(results):
            path, _ = results[i - 1]
            confirm = console.input(f"confirm delete {path}? [y/N]: ")
            if confirm.lower().startswith('y'):
                try:
                    if files_mode:
                        os.remove(path)
                    else:
                        shutil.rmtree(path)
                    console.print(f"[green]deleted: {path}[/]")
                except Exception as e:
                    console.print(f"[red]failed to delete {path}: {e}[/]")
        else:
            console.print(f"[yellow]{i} out of range, skipping[/]")


def main():
    # config lives in ~/.config/diskface/
    script_dir = Path(__file__).resolve().parent
    xdg = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    config_dir = xdg / 'diskface'
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / 'config.json'

    # migrate old config if needed
    old_config = script_dir / 'config.json'
    if not config_path.exists() and old_config.exists():
        shutil.copy2(old_config, config_path)
        console.print(f"[yellow]migrated config to {config_path}[/]")

    cfg = load_config(config_path)

    p = argparse.ArgumentParser(
        description='diskface v3.8 - disk usage analyzer',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument('--config', type=Path, default=config_path, help='config path')
    p.add_argument('--min-size', '-m', type=float, default=cfg['min_size_mb'], help='min size in mb')
    p.add_argument('--top', '-t', type=int, default=cfg['top'], help='how many results')
    p.add_argument('--depth', type=int, default=cfg['max_depth'], help='max depth (0=unlimited)')
    p.add_argument('--exclude', '-e', action='append', default=[], help='extra exclude patterns')
    p.add_argument('--no-excludes', action='store_true', default=cfg['no_excludes'], help='ignore excludes file')
    p.add_argument('--hide-dotfiles', '-d', action='store_true', default=cfg['hide_dotfiles'], help='skip dotfiles')
    p.add_argument('--files', '-f', action='store_true', dest='scan_files', help='scan files not dirs')
    p.add_argument('--dirs', action='store_false', dest='scan_files', help='scan dirs (default)')
    p.set_defaults(scan_files=cfg['scan_files'])
    p.add_argument('--root', '-r', action='store_true', dest='scan_root', help='scan from /')
    p.add_argument('--here', action='store_false', dest='scan_root', help='scan from cwd (default)')
    p.set_defaults(scan_root=cfg['scan_root'])
    p.add_argument('--interactive', '-i', action='store_true', dest='interactive', help='deletion prompt')
    p.add_argument('--no-interactive', action='store_false', dest='interactive', help='no deletion prompt')
    p.set_defaults(interactive=cfg['interactive'])
    p.add_argument('--clean', '-c', action='store_true', default=cfg['auto_clean'], help='clean temp files first')
    p.add_argument('--excludes-file', type=str, default=cfg['excludes_file'], help='excludes file path')
    p.add_argument('--temp-paths-file', type=str, default=cfg['temp_paths_file'], help='temp paths file')
    args = p.parse_args()

    # only sudo when scanning root
    if args.scan_root:
        root = '/'
        if os.geteuid() != 0:
            console.print("[yellow]elevating with sudo for full scan...[/]")
            os.execvp('sudo', ['sudo', sys.executable] + sys.argv)
    else:
        root = os.getcwd()

    console.print(f"[blue]scanning: {root}[/]")

    # find pattern files (check config dir first, then script dir)
    def find_file(name: str) -> Path:
        f = Path(name)
        if f.is_absolute():
            return f
        for d in [config_dir, script_dir]:
            if (d / name).exists():
                return d / name
        return script_dir / name

    # load excludes
    excludes_path = find_file(args.excludes_file)
    exclusions: Set[str] = set() if args.no_excludes else set(load_patterns(excludes_path))
    exclusions.update(args.exclude)
    console.print(f"[blue]{len(exclusions)} exclusion patterns loaded[/]")

    # load temp paths
    temp_path = find_file(args.temp_paths_file)
    temp_paths = load_patterns(temp_path)

    if args.clean:
        display_cleaned(clean_temp_files(temp_paths))

    # scan
    max_depth = args.depth if args.depth > 0 else float('inf')
    start = datetime.now()
    results = _scan(root, exclusions, args.min_size, args.hide_dotfiles,
                    args.top, max_depth, args.scan_files)
    display_results(results, args.top, args.scan_files)
    console.print(f"[dim]done in {(datetime.now() - start).total_seconds():.1f}s[/]")

    if args.interactive:
        prompt_deletion(results, args.scan_files)


if __name__ == '__main__':
    main()
