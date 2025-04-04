# Warning Comparator

This tool compares log files from two directories to detect newly added warnings in updated logs compared to original logs. It integrates with Git to identify the author responsible for the code line associated with each warning and outputs the results in CSV format for easier debugging and tracking.

## Features

- **Log File Comparison:**
  The script accepts two folder paths as command-line arguments—one for the original logs and one for the updated logs. The log filenames in both directories must be identical.

- **Configuration File Support:**
  A configuration file named `compare.config` specifies the list of log files to compare. File names can be provided either comma-separated or one per line. Lines starting with '#' are treated as comments and empty lines are ignored.

- **Warning Extraction:**
  The script extracts warning messages using multiple regex patterns:
  - **Original Warning Format:**
    Supports log lines with an optional numeric prefix (e.g., `80>`) which is removed to capture only the actual file path (starting from the drive letter, e.g., `D:\pam\pam32\console\NAICSubGrpUtl.cpp`). It extracts the file path, line number, column number, and warning code (only the code, e.g., `C4267`, is retained).
  - **CSC/CL Warning Formats:**
    The script also supports `CSC : warning ...` and `cl : command line warning ...` formats, with matching occurring anywhere in the line.

- **Git Blame Integration:**
  For warnings associated with a specific file path and line number, the script attempts to execute `git blame` to retrieve the author's name and email address associated with that line of code.

- **Commit URL Support:**
  The tool can generate clickable commit URLs in the output CSV by configuring the `COMMIT_URL_PREFIX` in the `common.config` file.

- **Warning Message Truncation:**
  When a warning message contains a project path (enclosed in square brackets) or compiling source information (e.g., the text "compiling source file"), the accumulation of the warning message is terminated. Content after these markers is not appended.

- **New Warning Comparison:**
  The script compares the occurrence counts of each unique warning between the original and updated logs. If a warning appears more times in the updated log than in the original, the difference is recorded as "new warnings."

- **Debug Mode:**
  A debug mode can be enabled in `common.config` to provide additional information during execution, particularly useful for troubleshooting Git blame operations.

- **CSV Output:**
  For each compared log file, the results are saved in CSV format with the following header column order:

  - **Committer:** The name of the author who last modified the line (from `git blame`), or "N/A".
  - **E-Mail:** The email of the author (from `git blame`), or "N/A".
  - **Commit URL:** A clickable URL to the commit (if `COMMIT_URL_PREFIX` is configured), or just the commit hash.
  - **Warning keyword:** Only the warning code (e.g., `C4267`).
  - **Message:** The complete warning message (truncated at the project path or compiling source info).
  - **Project:** The project path extracted from the warning message (if available).
  - **Compiling Source:** The source file information extracted from the warning (if available).
  - **File path:** The warning's file path (with the numeric prefix removed).
  - **Line:** The line number of the warning.
  - **Column:** The column number of the warning.
  - **Repeat Count:** The number of extra occurrences of this warning in the updated log compared to the original.

  The CSV filename is formatted as:
  ```
  originalFilename_new_warning_{total}.csv
  ```
  where `{total}` is the total number of additional warnings for that log file.

- **Progress Indication:**
  For large log files with many warnings, a progress bar is displayed during processing to indicate completion status.

## File Structure

Below is the directory structure of the project:

```
|-- compare_warnings.py         # Main script for comparison coordination
|-- warning_parser.py           # Module for parsing warning messages
|-- git_utils.py                # Module for Git operations
|-- comparison.py               # Module for comparing warning counts
|-- common.config               # Configuration for debug mode and commit URL prefix
|-- compare.config              # Configuration file listing log filenames
|-- old_logs/                   # Directory containing original log files
|   |-- core.log
|   |-- release.log
|-- new_logs/                   # Directory containing updated log files
|   |-- core.log
|   |-- release.log
|-- output_YYYYMMDD_HHMMSS/     # Output directory generated by the script (e.g., output_20250402_182557)
    |-- core_new_warning_X.csv
    |-- release_new_warning_Y.csv
    |-- test_new_warning_Z.csv
```

## Configuration Files

### compare.config

This file specifies which log files to compare. Format:
```
# List of log files to compare.
# You can separate file names using commas or newlines.
core.log
release.log, test.log
```

### common.config

This file contains global settings:
```
[DEFAULT]
enableDebug = false
COMMIT_URL_PREFIX = "https://github.com/username/repo/commit/"
```

- `enableDebug`: Set to `true` to enable detailed debug output
- `COMMIT_URL_PREFIX`: URL prefix to create clickable links to commits in the output CSV

## Requirements & Usage

- **Requirements:**
  - Python 3.x
  - **Git:** Git must be installed and accessible via the system's PATH environment variable for the author lookup feature to work.

- **Usage Instructions:**
  1. Ensure your project code (corresponding to the file paths in the logs) is within a Git repository.
  2. Create two directories: one containing the original log files and another containing the updated log files. Ensure the log filenames match between the directories.
  3. Edit the `compare.config` file to list the log filenames to be compared.
  4. Configure `common.config` with your repository's commit URL prefix if desired.
  5. Run the script via the command line, supplying the two folder paths:
     ```bash
     python compare_warnings.py path/to/old_logs path/to/new_logs
     ```
  6. The script compares the specified log files, performs `git blame` for relevant warnings, and outputs CSV files in an output directory (e.g., `output_20250402_182557`).

- **Notes:**
  - The `git blame` operation can be time-consuming, especially for large repositories or numerous warnings. Processing time may increase for large log files.
  - If `git` is not found or if `git blame` fails for a specific file/line (e.g., file not in repo, history rewritten), the "Author" and "E-Mail" fields will contain "N/A".
  - The script uses a caching mechanism to improve performance when retrieving blame information for the same file multiple times.

---

## Overview

This tool assists developers in quickly identifying new warning messages introduced in updated log files. By integrating Git blame information, it further helps pinpoint the origin of the code change associated with the warning. The output is a structured CSV file that details each warning, enabling more efficient debugging and issue tracking.

The modular design separates warning parsing, Git operations, and comparison logic into distinct components, making the codebase more maintainable and extensible.
