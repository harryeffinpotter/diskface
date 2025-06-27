#!/usr/bin/env python3

import os
import sys
import argparse
import fnmatch
import glob
import shutil
import json
from pathlib import Path, PurePath
from typing import List, Set, Tuple, Dict, Any
from datetime import datetime

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.prompt import Prompt, Confirm

console = Console()

# === Configuration Management ===
class DiskfaceConfig:
    def __init__(self):
        self.config_dir = Path.home() / '.config' / 'diskface'
        self.config_file = self.config_dir / 'config.json'
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        defaults = {
            'exclusions': [
                '/proc', '/sys', '/dev', '/run', '/tmp/systemd-*',
                '/var/run', '/var/lock', '/boot/efi', '/sys/*'
            ],
            'temp_paths': [
                '~/.cache/*',
                '/tmp/*',
                '~/.local/share/Trash/*',
                '/var/tmp/*'
            ],
            'settings': {
                'min_size_mb': 100,
                'entries_to_show': 20,
                'ignore_dotfolders': False,
                'scan_files': True,
                'scan_directories': True,
                'interactive_by_default': False
            }
        }
        
        if not self.config_file.exists():
            self._save_config(defaults)
            return defaults
        
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                # Merge with defaults for new settings
                for key, value in defaults.items():
                    if key not in config:
                        config[key] = value
                    elif key == 'settings' and isinstance(value, dict):
                        for setting_key, setting_value in value.items():
                            if setting_key not in config[key]:
                                config[key][setting_key] = setting_value
                return config
        except (json.JSONDecodeError, KeyError):
            console.print("[red]Config file corrupted, resetting to defaults[/]")
            return defaults
    
    def _save_config(self, config: Dict[str, Any] = None):
        """Save configuration to file."""
        if config is None:
            config = self.config
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def add_exclusion(self, pattern: str):
        """Add an exclusion pattern."""
        if pattern not in self.config['exclusions']:
            self.config['exclusions'].append(pattern)
            self._save_config()
            return True
        return False
    
    def remove_exclusions(self, indices: List[int]) -> List[str]:
        """Remove exclusions by indices (1-based)."""
        removed = []
        # Sort indices in reverse order to avoid index shifting
        for i in sorted(indices, reverse=True):
            if 1 <= i <= len(self.config['exclusions']):
                removed.append(self.config['exclusions'].pop(i-1))
        self._save_config()
        return removed
    
    def get_exclusions(self) -> List[str]:
        """Get all exclusion patterns."""
        return self.config['exclusions'].copy()
    
    def toggle_setting(self, setting: str) -> bool:
        """Toggle a boolean setting and return new value."""
        if setting in self.config['settings'] and isinstance(self.config['settings'][setting], bool):
            self.config['settings'][setting] = not self.config['settings'][setting]
            self._save_config()
            return self.config['settings'][setting]
        return False
    
    def get_setting(self, setting: str, default=None):
        """Get a setting value."""
        return self.config['settings'].get(setting, default)
    
    def get_all_settings(self) -> Dict[str, Any]:
        """Get all settings."""
        return self.config['settings'].copy()

config = DiskfaceConfig()

# === Core Functions ===
def path_matches_pattern(path: str, pattern: str) -> bool:
    """Check if path matches the given pattern using glob rules."""
    pattern_pt = PurePath(pattern)
    path_pt = PurePath(path)

    if pattern_pt.is_absolute():
        return fnmatch.fnmatch(str(path_pt).lower(), str(pattern_pt).lower())

    parts = str(pattern).split('/')
    if '**' in parts:
        return fnmatch.fnmatch(str(path_pt).lower(), f"*{parts[-1]}".lower())
    else:
        path_parts = str(path_pt).split('/')
        plen = len(parts)
        return any(
            fnmatch.fnmatch("/".join(path_parts[i:i+plen]).lower(), pattern.lower())
            for i in range(len(path_parts) - plen + 1)
        )

def should_exclude(path: str, exclusions: Set[str]) -> bool:
    """Check if path should be excluded based on exclusion patterns."""
    return any(path_matches_pattern(path, excl) for excl in exclusions)

def human_readable_size(size_bytes: int) -> str:
    for unit in ['B','KB','MB','GB','TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def parse_selection(selection: str, max_items: int) -> List[int]:
    """Parse user selection string into list of indices."""
    if selection.lower() == 'all':
        return list(range(1, max_items + 1))
    
    indices = []
    parts = selection.replace(',', ' ').split()
    
    for part in parts:
        try:
            if '-' in part:
                start, end = map(int, part.split('-', 1))
                if 1 <= start <= max_items and 1 <= end <= max_items and start <= end:
                    indices.extend(range(start, end + 1))
                else:
                    return []
            else:
                num = int(part)
                if 1 <= num <= max_items:
                    indices.append(num)
                else:
                    return []
        except ValueError:
            return []
    
    return sorted(list(set(indices)))

def interactive_selection(results: List[Tuple[str, int]], max_display: int = 60) -> List[Tuple[str, int]]:
    """Allow user to interactively select directories/files for removal."""
    if not results:
        console.print("[yellow]No results to select from.[/]")
        return []
    
    # Limit display to prevent overwhelming output
    display_results = results[:max_display]
    
    console.print(f"\n[bold green]Interactive Selection Mode[/]")
    if len(results) > len(display_results):
        console.print(f"[yellow]Showing top {len(display_results)} of {len(results)} results for selection[/]")
    
    console.print("[dim]Select directories/files to remove. Enter numbers separated by spaces, ranges (e.g., 1-5), or 'all' for everything shown.[/]")
    console.print("[dim]Examples: '1 3 5', '1-3 7 9-12', 'all'[/]")
    
    # Display numbered list
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="yellow", justify="right")
    table.add_column("Size", style="cyan", justify="right")
    table.add_column("Path", style="green")
    
    for i, (path, size) in enumerate(display_results, 1):
        table.add_row(str(i), human_readable_size(size), path)
    
    console.print(table)
    
    while True:
        try:
            selection = Prompt.ask("\n[bold]Select items to remove (or 'q' to quit)")
            
            if selection.lower() == 'q':
                return []
            
            selected_indices = parse_selection(selection, len(display_results))
            if not selected_indices:
                console.print("[red]Invalid selection. Please try again.[/]")
                continue
                
            selected_items = [display_results[i-1] for i in selected_indices]
            
            # Show what will be removed
            console.print(f"\n[bold yellow]Selected {len(selected_items)} items for removal:[/]")
            removal_table = Table(show_header=True, header_style="bold red")
            removal_table.add_column("Size", style="cyan", justify="right") 
            removal_table.add_column("Path", style="red")
            
            total_size = 0
            for path, size in selected_items:
                removal_table.add_row(human_readable_size(size), path)
                total_size += size
                
            console.print(removal_table)
            console.print(f"[bold]Total size to be freed: {human_readable_size(total_size)}[/]")
            
            if Confirm.ask("\n[bold red]Are you sure you want to remove these items?"):
                return selected_items
            else:
                console.print("[yellow]Selection cancelled. Choose again or 'q' to quit.[/]")
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Selection cancelled.[/]")
            return []
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")

def safe_remove_items(selected_items: List[Tuple[str, int]]) -> Dict[str, int]:
    """Safely remove selected directories/files and return removal stats."""
    removed = {}
    
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), console=console
    ) as progress:
        task = progress.add_task("Removing items...", total=len(selected_items))
        
        for path, expected_size in selected_items:
            progress.update(task, description=f"Removing: {path[:50]}...")
            
            try:
                if not os.path.exists(path):
                    console.print(f"[yellow]Skipping {path} - no longer exists[/]")
                    continue
                
                # Get actual size before removal (in case it changed)
                actual_size = 0
                if os.path.isfile(path):
                    actual_size = os.path.getsize(path)
                    os.remove(path)
                elif os.path.isdir(path):
                    # Calculate actual directory size
                    for dirpath, dirnames, filenames in os.walk(path):
                        for filename in filenames:
                            filepath = os.path.join(dirpath, filename)
                            try:
                                if not os.path.islink(filepath):
                                    actual_size += os.path.getsize(filepath)
                            except (OSError, FileNotFoundError):
                                continue
                    shutil.rmtree(path)
                
                removed[path] = actual_size
                console.print(f"[green]✓ Removed: {path} ({human_readable_size(actual_size)})[/]")
                
            except PermissionError:
                console.print(f"[red]✗ Permission denied: {path}[/]")
            except Exception as e:
                console.print(f"[red]✗ Error removing {path}: {e}[/]")
            
            progress.advance(task)
    
    return removed

def display_removal_results(removed: Dict[str, int]):
    """Display results of the removal operation."""
    if not removed:
        console.print("[yellow]No items were removed.[/]")
        return
    
    table = Table(show_header=True, header_style="bold green")
    table.add_column("Removed Path", style="green")
    table.add_column("Size Freed", style="cyan", justify="right")
    
    total_freed = 0
    for path, size in removed.items():
        table.add_row(path, human_readable_size(size))
        total_freed += size
    
    console.print(Panel.fit(
        f"[bold]Removal Complete[/]\n[dim]Items removed: {len(removed)}, Total freed: {human_readable_size(total_freed)}[/]",
        border_style="green"
    ))
    console.print(table)

# === Subcommand Functions ===
def cmd_exclude_add(args):
    """Add exclusion patterns."""
    if not args.patterns:
        console.print("[red]No patterns provided[/]")
        return
    
    added = []
    for pattern in args.patterns:
        if config.add_exclusion(pattern):
            added.append(pattern)
        else:
            console.print(f"[yellow]Pattern already exists: {pattern}[/]")
    
    if added:
        console.print(f"[green]Added {len(added)} exclusion pattern(s):[/]")
        for pattern in added:
            console.print(f"  + {pattern}")

def cmd_exclude_list(args):
    """List all exclusion patterns."""
    exclusions = config.get_exclusions()
    if not exclusions:
        console.print("[yellow]No exclusions configured[/]")
        return
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="yellow", justify="right")
    table.add_column("Exclusion Pattern", style="cyan")
    
    for i, pattern in enumerate(exclusions, 1):
        table.add_row(str(i), pattern)
    
    console.print(Panel.fit(
        f"[bold]Exclusion Patterns[/]\n[dim]{len(exclusions)} patterns configured[/]",
        border_style="blue"
    ))
    console.print(table)

def cmd_exclude_remove(args):
    """Remove exclusion patterns."""
    exclusions = config.get_exclusions()
    if not exclusions:
        console.print("[yellow]No exclusions to remove[/]")
        return
    
    if not args.selection:
        console.print("[red]No selection provided[/]")
        return
    
    indices = parse_selection(args.selection, len(exclusions))
    if not indices:
        console.print("[red]Invalid selection[/]")
        return
    
    removed = config.remove_exclusions(indices)
    if removed:
        console.print(f"[green]Removed {len(removed)} exclusion pattern(s):[/]")
        for pattern in removed:
            console.print(f"  - {pattern}")

def cmd_settings(args):
    """Display all settings."""
    settings = config.get_all_settings()
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Description", style="dim")
    
    descriptions = {
        'min_size_mb': 'Minimum directory size in MB to display',
        'entries_to_show': 'Maximum number of entries to show',
        'ignore_dotfolders': 'Skip folders/files starting with a dot',
        'scan_files': 'Include individual files in scan',
        'scan_directories': 'Include directories in scan',
        'interactive_by_default': 'Enter interactive mode automatically'
    }
    
    for setting, value in settings.items():
        desc = descriptions.get(setting, "")
        if isinstance(value, bool):
            value_str = "[green]ON[/]" if value else "[red]OFF[/]"
        else:
            value_str = str(value)
        table.add_row(setting, value_str, desc)
    
    console.print(Panel.fit(
        "[bold]Diskface Settings[/]",
        border_style="blue"
    ))
    console.print(table)

def cmd_toggle_setting(setting_name: str):
    """Toggle a boolean setting."""
    old_value = config.get_setting(setting_name)
    if not isinstance(old_value, bool):
        console.print(f"[red]Setting '{setting_name}' is not toggleable[/]")
        return
    
    new_value = config.toggle_setting(setting_name)
    status = "[green]ON[/]" if new_value else "[red]OFF[/]"
    console.print(f"[bold]{setting_name}[/]: {status}")

# === Scan Functions (simplified from original) ===
def create_live_results_table(results: List[Tuple[str,int]], max_entries: int = 20) -> Table:
    """Create a table showing the largest directories found so far."""
    table = Table(show_header=True, header_style="bold magenta", 
                  title=f"Top {max_entries} Largest Items Found")
    table.add_column("Size", style="cyan", justify="right")
    table.add_column("Path", style="green")

    top = sorted(results, key=lambda x: x[1], reverse=True)[:max_entries]
    if not top:
        table.add_row("--", "Scanning...")
        return table

    total = sum(sz for _,sz in top)
    for path, sz in top:
        pct = (sz/total)*100 if total > 0 else 0
        table.add_row(human_readable_size(sz), f"{path} [dim]({pct:.1f}%)[/]")
    return table

def analyze_disk_usage(root: str, exclusions: Set[str], min_size_mb: float) -> List[Tuple[str, int]]:
    """Disk analysis with live updating display."""
    min_bytes = min_size_mb * 1024 * 1024
    results: List[Tuple[str, int]] = []
    
    scan_files = config.get_setting('scan_files', True)
    scan_dirs = config.get_setting('scan_directories', True)
    ignore_dot = config.get_setting('ignore_dotfolders', False)
    entries_to_show = config.get_setting('entries_to_show', 20)

    # Create live display layout
    progress = Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), console=console
    )
    table = create_live_results_table(results, entries_to_show)
    layout = Table.grid()
    layout.add_row(Panel(progress))
    layout.add_row(Panel(table))

    with Live(layout, console=console, refresh_per_second=4) as live:
        task = progress.add_task("Scanning...", total=None)
        
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            # Skip if we're inside a dot directory when ignore_dotfolders is enabled
            if ignore_dot:
                path_parts = Path(dirpath).parts
                if any(part.startswith('.') for part in path_parts):
                    dirnames[:] = []  # Don't descend into any subdirectories
                    continue
                dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            dirnames[:] = [d for d in dirnames if not should_exclude(os.path.join(dirpath, d), exclusions)]
            progress.update(task, description=f"Scanning: {dirpath[:60]}...")

            # Skip processing files if we're in a dot directory
            if ignore_dot:
                path_parts = Path(dirpath).parts
                if any(part.startswith('.') for part in path_parts):
                    continue  # Skip this entire directory
            
            # Directory size calculation
            if scan_dirs:
                dir_size = 0
                for f in filenames:
                    if ignore_dot and f.startswith('.'): continue
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp) and not should_exclude(fp, exclusions):
                        try:
                            dir_size += os.path.getsize(fp)
                        except Exception:
                            pass
                if dir_size >= min_bytes:
                    results.append((dirpath, dir_size))
                    # Update live display
                    table = create_live_results_table(results, entries_to_show)
                    layout = Table.grid()
                    layout.add_row(Panel(progress))
                    layout.add_row(Panel(table))
                    live.update(layout)
            
            # Individual file scanning
            if scan_files:
                for f in filenames:
                    if ignore_dot and f.startswith('.'): continue
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp) and not should_exclude(fp, exclusions):
                        try:
                            file_size = os.path.getsize(fp)
                            if file_size >= min_bytes:
                                results.append((fp, file_size))
                                # Update live display for large files too
                                table = create_live_results_table(results, entries_to_show)
                                layout = Table.grid()
                                layout.add_row(Panel(progress))
                                layout.add_row(Panel(table))
                                live.update(layout)
                        except Exception:
                            pass

        return sorted(results, key=lambda x: x[1], reverse=True)

def cmd_scan(args):
    """Run disk analysis scan."""
    # Get the scan path - default to current directory if not specified
    scan_path = getattr(args, 'path', '.')
    scan_path = os.path.abspath(scan_path)
    
    # Only prompt for sudo if scanning from root or system directories
    needs_sudo = (scan_path == '/' or 
                  scan_path.startswith('/usr') or 
                  scan_path.startswith('/var') or 
                  scan_path.startswith('/etc') or
                  scan_path.startswith('/opt'))
    
    if needs_sudo and os.geteuid() != 0:
        console.print("[yellow]Elevated privileges recommended for system directories. Re-running with sudo...[/]")
        os.execvp('sudo', ['sudo', sys.executable] + sys.argv)

    if not os.path.exists(scan_path):
        console.print(f"[red]Error: Path does not exist: {scan_path}[/]")
        return
    
    if not os.path.isdir(scan_path):
        console.print(f"[red]Error: Path is not a directory: {scan_path}[/]")
        return

    exclusions = set(config.get_exclusions())
    min_size = args.min_size if args.min_size else config.get_setting('min_size_mb', 100)
    
    console.print(f"[blue]Scanning: {scan_path}[/]")
    console.print(f"[blue]Using {len(exclusions)} exclusion patterns[/]")
    
    start = datetime.now()
    results = analyze_disk_usage(scan_path, exclusions, min_size)
    end = datetime.now()
    
    # Display results
    entries_to_show = args.top if args.top else config.get_setting('entries_to_show', 20)
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Size", style="cyan", justify="right")
    table.add_column("Path", style="green")
    
    total = sum(sz for _, sz in results)
    for path, sz in results[:entries_to_show]:
        pct = (sz/total)*100 if total > 0 else 0
        table.add_row(human_readable_size(sz), f"{path} [dim]({pct:.1f}%)[/]")
    
    console.print(Panel.fit(
        f"[bold]Disk Usage Analysis[/]\n"
        f"[dim]Showing {min(len(results), entries_to_show)} of {len(results)} items, "
        f"total size: {human_readable_size(total)}[/]\n"
        f"[dim]Completed in {(end-start).total_seconds():.1f}s[/]",
        border_style="blue"
    ))
    console.print(table)
    
    # Interactive mode
    interactive = args.interactive if hasattr(args, 'interactive') else config.get_setting('interactive_by_default', False)
    if interactive or (results and Confirm.ask("\n[bold]Select items for removal?")):
        selected_items = interactive_selection(results, entries_to_show * 3)
        if selected_items:
            removed = safe_remove_items(selected_items)
            display_removal_results(removed)

def main():
    parser = argparse.ArgumentParser(description='Diskface - Interactive disk space analyzer')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Exclude subcommands
    exclude_parser = subparsers.add_parser('exclude', help='Manage exclusion patterns')
    exclude_subs = exclude_parser.add_subparsers(dest='exclude_action')
    
    add_parser = exclude_subs.add_parser('add', help='Add exclusion patterns')
    add_parser.add_argument('patterns', nargs='+', help='Patterns to add')
    
    exclude_subs.add_parser('list', help='List exclusion patterns')
    
    remove_parser = exclude_subs.add_parser('remove', help='Remove exclusion patterns')
    remove_parser.add_argument('selection', help='Selection (e.g., "1", "1-5", "all")')

    # Settings
    subparsers.add_parser('settings', help='Show all settings')
    subparsers.add_parser('files', help='Toggle file scanning')
    subparsers.add_parser('directories', help='Toggle directory scanning')
    subparsers.add_parser('dotfolders', help='Toggle dotfolder ignoring')
    subparsers.add_parser('interactive', help='Toggle interactive mode default')

    # Scan command (default)
    scan_parser = subparsers.add_parser('scan', help='Run disk analysis')
    scan_parser.add_argument('path', nargs='?', default='.', help='Path to scan (default: current directory)')
    scan_parser.add_argument('--min-size', '-m', type=float, help='Min size in MB')
    scan_parser.add_argument('--top', '-t', type=int, help='Max entries to show')
    scan_parser.add_argument('--interactive', '-i', action='store_true', help='Force interactive mode')

    args = parser.parse_args()

    # Handle subcommands
    if args.command == 'exclude':
        if args.exclude_action == 'add':
            cmd_exclude_add(args)
        elif args.exclude_action == 'list':
            cmd_exclude_list(args)
        elif args.exclude_action == 'remove':
            cmd_exclude_remove(args)
        else:
            exclude_parser.print_help()
    elif args.command == 'settings':
        cmd_settings(args)
    elif args.command == 'files':
        cmd_toggle_setting('scan_files')
    elif args.command == 'directories':
        cmd_toggle_setting('scan_directories')
    elif args.command == 'dotfolders':
        cmd_toggle_setting('ignore_dotfolders')
    elif args.command == 'interactive':
        cmd_toggle_setting('interactive_by_default')
    elif args.command == 'scan' or args.command is None:
        # Default to scan if no command specified
        if args.command is None:
            # Create a dummy args object for scan
            class ScanArgs:
                path = '.'
                min_size = None
                top = None
                interactive = False
            args = ScanArgs()
        cmd_scan(args)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
