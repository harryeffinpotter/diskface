# Disk Face 📊

**Disk Face** is your friendly neighborhood disk usage and cleanup tool, powered by Python and [Rich](https://github.com/Textualize/rich). Quickly scan directories, find space-hogs, and clean up temp files — all with a beautiful live display.

---

## 🚀 Features

- **Live scanning progress**: See directories being scanned in real time.
- **Top-N directories**: List the biggest directories (default 20, configurable).
- **Custom exclusion patterns**: Ignore files/folders using simple glob-style rules in `excludes.txt`.
- **Dot-folder skipping**: Easy flag to skip hidden `.` files and folders.
- **Temp cleanup**: Remove temp files based on patterns in `temp_paths.txt`.
- **Auto-sudo**: Re-runs itself under `sudo` if root access is needed.
- **Human-readable sizes**: Shows sizes in B, KB, MB, GB, etc.

---

## 🛠️ Installation

1. **Clone the repo**:
   ```bash
   git clone https://github.com/yourusername/disk-face.git
   cd disk-face
   ```

2. **Install dependencies**:
   ```bash
   pip install rich
   ```

3. **Make it executable**:
   ```bash
   chmod +x disk_face.py
   ```

---

## ⚙️ Configuration

### Exclusion Patterns (`excludes.txt`)

- Place `excludes.txt` next to the script (or override via `--excludes-file`).
- One glob pattern per line (supports `*`, `**`, absolute paths).
- Lines beginning with `#` are comments.

```text
# Ignore common caches
**/.cache
**/node_modules
/var/cache
```

### Temp-clean Patterns (`temp_paths.txt`)

- Same format as excludes.
- Each pattern will be globbed and cleaned when using `--clean`.

```text
/tmp
**/*.tmp
~/.cache
```

---

## 🎮 Usage

```bash
./disk_face.py [options]
```

### Common Flags

| Flag                      | Description                                        |
|---------------------------|----------------------------------------------------|
| `-e, --exclude PATTERN`   | Add an extra exclusion (can be repeated)           |
| `-m, --min-size MB`       | Minimum directory size to report (default: 100 MB) |
| `-t, --top N`             | Max number of directories to show (default: 20)    |
| `-d, --ignore-dotfolders` | Skip hidden files and folders starting with `.`    |
| `-c, --clean`             | Remove temp files based on `temp_paths.txt`        |
| `--include-os`            | Skip reading `excludes.txt` (include system files) |
| `--excludes-file FILE`    | Path to custom excludes file                       |
| `--temp-paths-file FILE`  | Path to custom temp-clean file                     |
| `-h, --help`              | Show help and exit                                 |


### Examples

- **Scan `/var` and show top 10**:
  ```bash
  ./disk_face.py -m 50 -t 10 /var
  ```

- **Skip hidden folders & add custom exclusion**:
  ```bash
  ./disk_face.py -d -e '/mnt/backups'
  ```

- **Clean temp paths before scanning**:
  ```bash
  ./disk_face.py -c
  ```

---

## 📝 License

MIT © Your Name

Enjoy cleaning up your disk with a smile! 🙂

