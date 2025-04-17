# DiskFace

DiskFace is a powerful command-line Disk & File Usage Analyzer with rich, live progress and flexible configuration. It helps you find and manage the largest directories or files on your system (or a specific directory), clean up temporary files, and interactively delete unwanted items.

---

## Features

- **JSON-backed configuration**
  - Auto-creates a default `config.json` if missing
  - Backs up broken configs (`config.broken.<timestamp>.json`)
  - All config values can be overridden via CLI flags

- **Min-size filter**
  - Exclude directories/files below a specified size (in MB)

- **Exclusion patterns**
  - Read glob-style patterns from `excludes.txt`
  - Skip directories/files matching patterns

- **Directory & File scanning modes**
  - Scan entire filesystem or current working directory
  - Toggle between directory mode and file mode

- **Live Rich progress & dynamic tables**
  - Spinner, progress bar, and dynamic Rich tables
  - Shows top N (default 20) largest items

- **Interactive deletion**
  - After scanning, select items by index to delete
  - Confirm each deletion

- **Temporary files cleanup**
  - Load patterns from `temp_paths.txt`
  - Delete matching temp files/directories
  - Summarize freed space per pattern

- **Scan current directory only**
  - Optionally limit scan to the working directory

- **Auto-clean on start**
  - Run temp cleanup before scanning if enabled

- **Human-readable size formatting**
  - Sizes shown in B, KB, MB, GB, TB, PB with two decimals

---

## Installation

1. Clone or download the repository.
2. Ensure you have Python 3 and the `rich` library installed:
   ```bash
   pip install rich
   ```
3. Make the script executable:
   ```bash
   chmod +x diskface.py
   ```

---

## Configuration

A `config.json` file is auto-created on first run. Default contents:

```json
{
    "min_size_mb": 100,
    "top": 20,
    "include_os": false,
    "ignore_dotfolders": false,
    "interactive": true,
    "files": false,
    "auto_clean": false,
    "currentdirectoryonly": false,
    "excludes_file": "excludes.txt",
    "temp_paths_file": "temp_paths.txt"
}
```

- **min_size_mb**: Minimum size (MB) to include in results
- **top**: Number of items to display
- **include_os**: Skip loading `excludes.txt` patterns
- **ignore_dotfolders**: Skip dot-prefixed files/folders
- **interactive**: Enable interactive deletion
- **files**: Default to file scanning mode
- **auto_clean**: Run temp cleanup before scanning
- **currentdirectoryonly**: Scan only current directory
- **excludes_file**: Path to exclusion patterns file
- **temp_paths_file**: Path to temporary cleanup patterns file

---

## Usage

```bash
./diskface.py [options]
```

### Common Flags

- `-m`, `--min-size <MB>`       Minimum size in MB (overrides config)
- `-t`, `--top <N>`             Show top N items
- `-e`, `--exclude <pattern>`   Additional exclusion pattern (can repeat)
- `--files`, `--no-files`       Scan files instead of directories
- `--currentdir-only`           Limit scan to current directory
- `-i`, `--interactive`         Enable interactive deletion
- `-c`, `--clean`               Clean temp files before scanning
- `--excludes-file <path>`      Specify excludes file
- `--temp-paths-file <path>`    Specify temp paths file

---

## Examples

- **Scan largest directories on `/`**:
  ```bash
  sudo ./diskface.py
  ```

- **Scan largest files in current directory**:
  ```bash
  ./diskface.py --files --currentdir-only
  ```

- **Exclude `.git` and temp cleanup**:
  ```bash
  ./diskface.py -e ".git" -c
  ```

- **Non-interactive (just scan)**:
  ```bash
  ./diskface.py --no-interactive
  ```

---

## License

This project is licensed under the MIT License.

