#!/usr/bin/env python3
################################################################################
#                                                                              #
#    DiskFace3 v3.7 — Simple Disk & File Usage Analyzer                        #
#                                                                              #
#    Features:                                                                 #
#      • JSON config (excludes + temp paths)                                   #
#      • CLI overrides                                                          #
#      • Show top N directories & files                                        #
#      • Min-size filter (default 0MB)                                         #
#      • Skip dot-folders (.git) by default                                    #
#      • Configurable scan path & max-depth                                    #
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
from rich.table import Table

console = Console()

# Default config values
DEFAULT_CONFIG: Dict[str, Any] = {
    "min_size_mb": 0,           # default no size filter
    "top": 20,                  # entries to show
    "excludes": [],             # glob patterns
    "temp_paths": [],           # cleanup patterns
    "skip_dotfolders": True     # skip dot-folders like .git
}

# Load or init config
def load_config(cfg_file: Path) -> Dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    if not cfg_file.exists():
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        cfg_file.write_text(json.dumps(cfg, indent=4))
        return cfg
    try:
        data = json.loads(cfg_file.read_text())
        cfg.update({k: data.get(k, v) for k, v in DEFAULT_CONFIG.items()})
        return cfg
    except:
        backup = cfg_file.with_suffix('.broken')
        cfg_file.rename(backup)
        console.print(f"[yellow]Broken config backed up to {backup}[/]")
        cfg_file.write_text(json.dumps(cfg, indent=4))
        return cfg

# Pattern match helper
def matches_any(path: str, patterns: List[str]) -> bool:
    low = path.lower()
    for pat in patterns:
        p = PurePath(pat)
        if p.is_absolute():
            if fnmatch.fnmatch(low, str(p).lower()): return True
        elif '**' in pat:
            part = pat.split('**')[-1]
            if fnmatch.fnmatch(low, f"*{part.lower()}"): return True
        else:
            if fnmatch.fnmatch(low, pat.lower()): return True
    return False

# Human-readable size
def human_size(n: int) -> str:
    for u in ['B','KB','MB','GB','TB']:
        if n < 1024.0:
            return f"{n:.2f} {u}"
        n /= 1024.0
    return f"{n:.2f} PB"

# Build and print table
def show_table(results: List[Tuple[str,int]], label: str):
    tbl = Table(show_header=True, header_style="bold magenta")
    tbl.add_column("#", style="dim", justify="right")
    tbl.add_column("Size", style="cyan", justify="right")
    tbl.add_column(label, style="green")
    if not results:
        tbl.add_row("-", "--", f"No {label.lower()} found")
    else:
        total = sum(sz for _, sz in results)
        top = results[:TOP]
        for i, (p, sz) in enumerate(top, 1):
            pct = (sz / total * 100) if total else 0.0
            tbl.add_row(str(i), human_size(sz), f"{p} ({pct:.1f}%)")
    console.rule(f"Top {TOP} Largest {label}")
    console.print(tbl)

# Analyze disk usage
def analyze(root: Path, cfg: Dict[str, Any], mode: str) -> List[Tuple[str,int]]:
    min_b = int(cfg['min_size_mb'] * 1024 * 1024)
    skip_dot = cfg['skip_dotfolders']
    excl = cfg['excludes']
    results: List[Tuple[str,int]] = []
    base_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        if skip_dot:
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            filenames = [f for f in filenames if not f.startswith('.')]
        dirnames[:] = [d for d in dirnames if not matches_any(os.path.join(dirpath,d), excl)]
        if mode == 'dirs':
            size = 0
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.islink(fp) or matches_any(fp, excl): continue
                try: size += os.path.getsize(fp)
                except: pass
            if size >= min_b:
                results.append((dirpath, size))
        else:
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.islink(fp) or matches_any(fp, excl): continue
                try:
                    sz = os.path.getsize(fp)
                except:
                    continue
                if sz >= min_b:
                    results.append((fp, sz))
    # sort
    return sorted(results, key=lambda x: x[1], reverse=True)

# Cleanup temp
def clean_temp(paths: List[str]):
    tot_freed = 0
    for pat in paths:
        for t in glob.glob(pat, recursive='*' in pat):
            if os.path.isfile(t):
                try:
                    sz = os.path.getsize(t)
                    os.remove(t)
                    tot_freed += sz
                except: pass
            elif os.path.isdir(t):
                for dp, _, fls in os.walk(t):
                    for f in fls:
                        fp = os.path.join(dp, f)
                        try:
                            tot_freed += os.path.getsize(fp)
                        except: pass
                shutil.rmtree(t, ignore_errors=True)
    console.print(f"Freed up {human_size(tot_freed)} by cleaning temp files.")

# Main
if __name__ == '__main__':
    # config file
    cfg_dir = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config')) / 'diskface'
    cfg_file = cfg_dir / 'config.json'
    config = load_config(cfg_file)
    TOP = config['top']

    p = argparse.ArgumentParser()
    p.add_argument('-p','--path', type=Path, default=Path.cwd(), help='Root to scan')
    p.add_argument('-D','--depth', type=int, help='Max depth')
    p.add_argument('-d','--dirs-only', action='store_true', help='Dirs only')
    p.add_argument('-f','--files-only', action='store_true', help='Files only')
    p.add_argument('-m','--min-size', type=float, default=config['min_size_mb'], help='Min size MB')
    p.add_argument('-e','--exclude', action='append', default=[], help='Extra excludes')
    p.add_argument('-c','--clean', action='store_true', help='Clean temp then exit')
    args = p.parse_args()
    # override excludes & min-size
    config['excludes'] += args.exclude
    config['min_size_mb'] = args.min_size
    # clean
    if args.clean:
        clean_temp(config['temp_paths'])
        sys.exit(0)
    # run
    ROOT = args.path.resolve()
    modes = []
    if args.dirs_only: modes = ['dirs']
    elif args.files_only: modes = ['files']
    else: modes = ['dirs','files']
    for m in modes:
        res = analyze(ROOT, config, m)
        show_table(res, 'Directories' if m=='dirs' else 'Files')
