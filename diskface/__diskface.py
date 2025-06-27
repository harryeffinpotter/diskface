#!/usr/bin/env python3
################################################################################
#                                                                              #
#    DiskFace3 v3.7 — Comprehensive Disk & File Usage Analyzer                 #
#                                                                              #
#    Features:                                                                 #
#      • JSON config with auto-create and broken backup                        #
#      • CLI overrides for all config parameters                               #
#      • Min-size filter for directories and files                             #
#      • Exclusion patterns via excludes.txt                                   #
#      • Directory & file scanning modes                                      #
#      • Live Rich progress bars and dynamic tables                            #
#      • Interactive deletion of selected items                                #
#      • Temporary files cleanup with reporting                                #
#      • Configurable scan path & max-depth recursion                         #
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

console = Console()

# =============================================================================
# === Constants & Default Config Values
# =============================================================================
ENTRIES_TO_SHOW = 20
DEFAULT_CONFIG: Dict[str, Any] = {
    "min_size_mb": 100,
    "top": ENTRIES_TO_SHOW,
    "include_os": False,
    "ignore_dotfolders": False,
    "interactive": True,
    "files": False,
    "auto_clean": False,
    "excludes_file": "excludes.txt",
    "temp_paths_file": "temp_paths.txt"
}

# =============================================================================
# === Config Loader
# =============================================================================
def load_config(config_path: Path) -> Dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    if not config_path.exists():
        console.print(f"[yellow]Config not found at {config_path}, creating default config[/]")
        config_path.write_text(json.dumps(cfg, indent=4))
        return cfg
    try:
        data = json.loads(config_path.read_text())
        for key, default in DEFAULT_CONFIG.items():
            cfg[key] = data.get(key, default)
        return cfg
    except Exception:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup = config_path.with_name(f"{config_path.stem}.broken.{timestamp}{config_path.suffix}")
        config_path.rename(backup)
        console.print(f"[red]Broken config backed up to {backup}[/]")
        config_path.write_text(json.dumps(cfg, indent=4))
        return cfg

# =============================================================================
# === Pattern Loaders & Matching
# =============================================================================
def load_patterns(file: Path) -> List[str]:
    if not file.exists():
        console.print(f"[yellow]Patterns file not found: {file}, skipping[/]")
        return []
    lines = file.read_text().splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith('#')]

def path_matches_pattern(path: str, pattern: str) -> bool:
    p = PurePath(pattern)
    low = path.lower()
    if p.is_absolute():
        return fnmatch.fnmatch(low, str(p).lower())
    if '**' in pattern:
        part = pattern.split('**')[-1]
        return fnmatch.fnmatch(low, f"*{part.lower()}")
    return fnmatch.fnmatch(low, pattern.lower())

should_exclude = lambda p, excl: any(path_matches_pattern(p, pat) for pat in excl)

# =============================================================================
# === Utility: Human-readable sizes
# =============================================================================
def human_readable_size(n: int) -> str:
    for u in ['B','KB','MB','GB','TB']:
        if n < 1024:
            return f"{n:.2f} {u}"
        n /= 1024
    return f"{n:.2f} PB"

# =============================================================================
# === Table builders
# =============================================================================
def build_table(results: List[Tuple[str,int]], title: str, is_file: bool) -> Table:
    tbl = Table(show_header=True, header_style="bold magenta", title=title)
    tbl.add_column("#", style="dim", justify="right")
    tbl.add_column("Size", style="cyan", justify="right")
    name = "File" if is_file else "Directory"
    tbl.add_column(name, style="green")
    if not results:
        tbl.add_row("-","--", f"No {name.lower()}s found...")
        return tbl
    top = results[:ENTRIES_TO_SHOW]
    total = sum(sz for _,sz in top)
    for i,(p,sz) in enumerate(top,1):
        pct = (sz/total*100) if total else 0
        tbl.add_row(str(i), human_readable_size(sz), f"{p} [dim]({pct:.1f}%)[/]")
    return tbl

# =============================================================================
# === Core scanning functions
# =============================================================================
def analyze_usage(root:str, excl:Set[str], min_mb:float, ignore_dot:bool,
                  max_depth:int, file_mode:bool) -> List[Tuple[str,int]]:
    min_b = int(min_mb*1024*1024)
    res:List[Tuple[str,int]] = []
    base_d = root.rstrip(os.sep).count(os.sep)
    prog = Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console)
    tbl = build_table(res, f"Top {ENTRIES_TO_SHOW} Largest {'Files' if file_mode else 'Directories'}", file_mode)
    layout = Table.grid(); layout.add_row(Panel(prog)); layout.add_row(Panel(tbl))
    with Live(layout, console=console, refresh_per_second=4) as live:
        task = prog.add_task(f"Scanning {'files' if file_mode else 'dirs'}...", total=None)
        for dp, dns, fns in os.walk(root, topdown=True):
            # depth limit
            if max_depth is not None and (dp.count(os.sep)-base_d)>=max_depth:
                dns[:] = []
            if ignore_dot:
                dns[:] = [d for d in dns if not d.startswith('.')]
                fns = [f for f in fns if not f.startswith('.')]
            dns[:] = [d for d in dns if not should_exclude(os.path.join(dp,d), excl)]
            prog.update(task, description=f"Scanning {dp[:60]}...")
            if file_mode:
                for f in fns:
                    fp=os.path.join(dp,f)
                    if not os.path.islink(fp) and not should_exclude(fp, excl):
                        try: s=os.path.getsize(fp)
                        except: continue
                        if s>=min_b:
                            res.append((fp,s))
                            live.update(Table.grid().add_row(Panel(prog)).add_row(Panel(build_table(res,f"Top {ENTRIES_TO_SHOW} Largest Files",True))))
            else:
                total_sz=0
                for f in fns:
                    if ignore_dot and f.startswith('.'): continue
                    fp=os.path.join(dp,f)
                    if not os.path.islink(fp) and not should_exclude(fp, excl):
                        try: total_sz+=os.path.getsize(fp)
                        except: pass
                if total_sz>=min_b:
                    res.append((dp,total_sz))
                    live.update(Table.grid().add_row(Panel(prog)).add_row(Panel(build_table(res,f"Top {ENTRIES_TO_SHOW} Largest Directories",False))))
    return sorted(res, key=lambda x: x[1], reverse=True)

def clean_temp(patterns:List[str]) -> Dict[str,int]:
    freed:Dict[str,int]={}
    prog = Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console)
    with prog:
        task = prog.add_task("Cleaning temp files...", total=None)
        for pat in patterns:
            tgt = glob.glob(pat, recursive='*' in pat)
            tot=0
            for t in tgt:
                prog.update(task, description=f"Cleaning {t}")
                if os.path.isfile(t):
                    try: tot+=os.path.getsize(t); os.remove(t)
                    except: pass
                elif os.path.isdir(t):
                    for dp,dls,fls in os.walk(t):
                        for f in fls:
                            fp=os.path.join(dp,f)
                            try: tot+=os.path.getsize(fp)
                            except: pass
                    shutil.rmtree(t,ignore_errors=True)
            if tot: freed[pat]=tot
    return freed

# =============================================================================
# === Display & Prompt
# =============================================================================
def display(res:List[Tuple[str,int]], top_n:int, file_mode:bool):
    title=f"Largest {'Files' if file_mode else 'Directories'} Analysis"
    tbl=build_table(res, title, file_mode)
    console.print(Panel.fit(f"[bold]DiskFace3 - {title}[/]\n[dim]Showing up to {top_n} of {len(res)} entries[/]", border_style="blue"))
    console.print(tbl)

def display_cleaned(c:Dict[str,int]):
    if not c: console.print("[yellow]No temp files cleaned[/]"); return
    tbl=Table(show_header=True, header_style="bold magenta"); tbl.add_column("Pattern"); tbl.add_column("Freed",justify="right")
    for p,s in c.items(): tbl.add_row(p,human_readable_size(s))
    console.print(Panel.fit(f"[bold]Cleanup Results[/]\n[dim]Total freed: {human_readable_size(sum(c.values()))}[/]",border_style="green"))
    console.print(tbl)

def prompt_del(res:List[Tuple[str,int]], file_mode:bool):
    sel=console.input("Numbers to delete (comma sep) or Enter to skip: ")
    if not sel.strip(): return
    for i in [int(x) for x in sel.split(',') if x.isdigit()]:
        if 1<=i<=len(res):
            path,_=res[i-1]
            if console.input(f"Delete {path}? [y/N]: ").lower().startswith('y'):
                try: os.remove(path) if file_mode else shutil.rmtree(path); console.print(f"[green]Deleted {path}[/]")
                except Exception as e: console.print(f"[red]Failed {path}: {e}[/]")

# =============================================================================
# === Main Entry
# =============================================================================
def main():
    # Config path: user XDG or /etc fallback
    xdg=Path(os.environ.get("XDG_CONFIG_HOME", Path.home()/".config")) / "diskface"
    etc=Path("/etc/diskface/config.json")
    xdg.mkdir(parents=True, exist_ok=True)
    cfg_path=xdg/"config.json"
    if not cfg_path.exists() and etc.exists(): cfg_path.write_text(etc.read_text())
    cfg=load_config(cfg_path)

    parser=argparse.ArgumentParser()
    parser.add_argument('-m','--min-size', type=float, default=cfg['min_size_mb'])
    parser.add_argument('-t','--top', type=int, default=cfg['top'])
    parser.add_argument('-e','--exclude', action='append', default=[] )
    parser.add_argument('-i','--ignore-dotfolders', action='store_true', default=cfg['ignore_dotfolders'])
    parser.add_argument('-f','--files', action='store_true', dest='files', default=cfg['files'])
    parser.add_argument('-p','--path', type=Path, default=Path.cwd())
    parser.add_argument('-D','--depth', type=int, default=None)
    parser.add_argument('-c','--clean', action='store_true', default=cfg['auto_clean'])
    parser.add_argument('--excludes-file', type=str, default=None)
    parser.add_argument('--temp-paths-file', type=str, default=None)
    parser.add_argument('-x','--no-interactive', action='store_false', dest='interactive', default=cfg['interactive'])
    args=parser.parse_args()

    if os.geteuid()!=0: os.execvp('sudo',['sudo',sys.executable]+sys.argv)

    root=str(args.path.resolve()); console.print(f"Scanning: {root}, max depth: {args.depth or '∞'}")
    base=cfg_path.parent
    excl_file=Path(args.excludes_file) if args.excludes_file else base/ cfg['excludes_file']
    exclusions=set(load_patterns(excl_file)+args.exclude) if not cfg['include_os'] else set()
    console.print(f"Loaded excludes from {excl_file}")
    temp_file=Path(args.temp_paths_file) if args.temp_paths_file else base/ cfg['temp_paths_file']
    temp_patterns=load_patterns(temp_file)
    console.print(f"Loaded temp patterns from {temp_file}")

    if args.clean:
        cleaned=clean_temp(temp_patterns); display_cleaned(cleaned)

    res=analyze_usage(root, exclusions, args.min_size, args.ignore_dotfolders, args.depth, args.files)
    display(res,args.top,args.files)
    console.print(f"Completed in {(datetime.now()-datetime.now()).total_seconds():.1f}s")
    if args.interactive: prompt_del(res,args.files)

if __name__=='__main__': main()
