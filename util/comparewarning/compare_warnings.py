import re
import csv
import sys
import os
import datetime
import subprocess

# Initialize a flag to prevent repeated 'git not found' warnings
git_blame_not_found = False

def find_git_repo_root():
    """Attempts to find the root directory of the Git repository based on the current working directory."""
    global git_blame_not_found # Allow modification of the global flag
    try:
        # Run git command to find the top-level directory relative to cwd
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=False, # Don't throw error on failure
            # Ensure subprocess doesn't inherit handles that might cause issues
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            repo_root = result.stdout.strip()
            print(f"Info: Determined Git repository root as: {repo_root}")
            return repo_root
        else:
            # This is not necessarily an error, could be running outside a repo.
            print(f"Warning: Could not determine Git repository root from current directory.", file=sys.stderr)
            print(f"         'git blame' will run without explicit 'cwd'. Path case sensitivity issues may occur.", file=sys.stderr)
            if result.stderr:
                 print(f"         Git error: {result.stderr.strip()}", file=sys.stderr)
            return None
    except FileNotFoundError:
        # Git command itself not found.
        if not git_blame_not_found: # Prevent flooding logs if git is missing
            print(f"Warning: 'git' command not found. Git blame functionality disabled.", file=sys.stderr)
            git_blame_not_found = True # Set the global flag
        return None
    except Exception as e:
        print(f"Warning: Error while trying to find Git repository root: {e}", file=sys.stderr)
        return None


def extract_project_path(warning_text):
    """
    Extract project path from the warning text, typically enclosed in square brackets.
    """
    project_match = re.search(r'\[(.*?)\]', warning_text)
    if project_match:
        path = project_match.group(1).strip()
        # Return the path if it contains backslashes, forward slashes, or specific project file extensions.
        if '\\' in path or '/' in path or '.vcxproj' in path or '.csproj' in path:
            return path
    return "N/A"

def has_project_path(text):
    """
    Check if the text contains a project path by verifying if square bracket content exists.
    """
    return extract_project_path(text) != "N/A"


def has_compiling_source(text):
    """
    Check if the text contains compiling source information.
    """
    return re.search(r"compiling source file", text, re.IGNORECASE) is not None

def extract_compiling_source(warning_text):
    """
    Extract the compiling source file path from the warning text,
    expected in the format: compiling source file 'xxx.cpp'
    """
    source_match = re.search(r"compiling source file ['\"](.+?)['\"]", warning_text, re.IGNORECASE)
    return source_match.group(1) if source_match else "N/A"


def get_git_blame_info(filepath, line_no, repo_root=None):
    """
    Use git blame to get the author and email information for a specific file and line number.
    Relies on setting the correct 'cwd' (repo_root) for git blame to handle paths.
    """
    global git_blame_not_found # Access the global flag

    # Check if filepath and line number are valid
    if filepath == "N/A" or line_no == "N/A":
        return "N/A", "N/A"

    # If Git command was globally determined as not found, exit early.
    if git_blame_not_found:
        return "N/A", "N/A"

    # Use repo_root as the execution directory if found
    exec_cwd = repo_root

    try:
        # Ensure line number is an integer
        line_num = int(line_no)
        if line_num <= 0:
            return "N/A", "N/A"

        # Construct the git blame command - pass the original filepath directly
        blame_command = [
            "git", "blame",
            f"-L{line_num},{line_num}",
            "--porcelain",
            "--", filepath # Pass the original path (often absolute)
        ]

        # Execute the git blame command with cwd set
        blame_result = subprocess.run(
            blame_command,
            cwd=exec_cwd, # Set the working directory to repo root
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=False,
            stdin=subprocess.DEVNULL,
        )

        # Check if the command executed successfully
        if blame_result.returncode != 0:
            cwd_info = f"CWD='{exec_cwd}'" if exec_cwd else "CWD=Default (None)"
            print(f"Warning: git blame failed for '{filepath}' at line {line_no}. {cwd_info}. Error: {blame_result.stderr.strip()}", file=sys.stderr)
            # If the error is 'no such path', it might still be a case issue not resolved by cwd,
            # or the file truly isn't tracked at that location in HEAD.
            return "N/A", "N/A"

        # --- Parse the blame output (robust parsing) ---
        author = "N/A"
        email = "N/A"
        lines = blame_result.stdout.splitlines()

        if not lines:
             cwd_info = f"CWD='{exec_cwd}'" if exec_cwd else "CWD=Default (None)"
             print(f"Warning: git blame produced no output for '{filepath}' at line {line_no}. {cwd_info}.", file=sys.stderr)
             return "N/A", "N/A"

        # Check if the first line looks like blame info (commit hash etc.)
        first_line_parts = lines[0].split()
        if len(first_line_parts) < 3 or not re.match(r'^[0-9a-f]{40}', first_line_parts[0]):
             cwd_info = f"CWD='{exec_cwd}'" if exec_cwd else "CWD=Default (None)"
             print(f"Warning: Unexpected git blame output format (first line) for '{filepath}' at line {line_no}. {cwd_info}. Output: {lines[0]}", file=sys.stderr)
             return "N/A", "N/A"

        commit_hash = first_line_parts[0]

        # Find the author and email associated with this commit hash in the header
        found_author = False
        found_email = False
        for i, line in enumerate(lines):
             # The blame header block starts with the commit hash line
             if line.startswith(commit_hash):
                 # Subsequent lines contain author, email, etc., until the next commit hash or content
                 j = i + 1
                 while j < len(lines) and not re.match(r'^[0-9a-f]{40}', lines[j]) and not lines[j].startswith('\t'):
                     if lines[j].startswith("author "):
                         author = lines[j].split(" ", 1)[1]
                         found_author = True
                     elif lines[j].startswith("author-mail "):
                         email = lines[j].split(" ", 1)[1].strip('<>')
                         found_email = True
                     # Found both for this commit block, no need to parse further
                     if found_author and found_email:
                         break
                     j += 1
                 # Exit outer loop once author/email found for the relevant commit
                 if found_author and found_email:
                     break

        # Fallback if parsing didn't find author/email
        if not found_author: author = "N/A"
        if not found_email: email = "N/A"

        return author, email

    except FileNotFoundError:
        # Handle case where 'git' command is not found specifically during blame execution
        # This might occur if git was found initially but removed later, or PATH issues.
        if not git_blame_not_found: # Print only once globally
             print(f"Warning: 'git' command not found during blame execution. Please ensure Git is installed and in your PATH.", file=sys.stderr)
             git_blame_not_found = True # Set global flag
        return "N/A", "N/A"
    except ValueError:
        # Handle case where line_no is not a valid integer
        print(f"Warning: Invalid line number '{line_no}' for git blame.", file=sys.stderr)
        return "N/A", "N/A"
    except Exception as e:
        # Catch any other exceptions during git blame execution
        print(f"Warning: An error occurred during git blame for {filepath} at line {line_no}: {e}", file=sys.stderr)
        return "N/A", "N/A"


def parse_warnings(filename):
    """
    Parse warning messages from the log file and return a list.
    Each element in the list is a tuple (key, warning_text),
    where key is a tuple (file path, line number, column number, warning code),
    and warning_text is the complete warning message.
    """
    warnings = []

    # Regex pattern for the original warning format:
    # Optional numeric prefix (e.g., "80>") then a Windows file path followed by (line,column): warning <code>: message
    original_pattern = re.compile(
        r"(?:(?:\d+>\s*)?)"                               # optional numeric prefix like "80>"
        r"(?P<filepath>[A-Za-z]:[\\/][^(]+)"              # capture file path (e.g. D:\pam\pam32\console\NAICSubGrpUtl.cpp)
        r"\((?P<line>\d+),(?P<column>\d+)\):\s*"           # capture (line,column):
        r"warning\s+(?P<warning_num>\S+):\s*"              # capture warning code (e.g. C4267)
        r"(?P<message>.*)"                                # the rest is treated as message
    )

    # Regex pattern for the new "CSC" warning format:
    # Optional prefix then: CSC : warning <errorCode>: message
    csc_pattern = re.compile(
        r"(?:(?:\d+>\s*)?)"                               # optional numeric prefix
        r"CSC\s*:\s*warning\s+(?P<warning_num>\S+):\s*(?P<message>.*)",
        re.IGNORECASE
    )

    # Regex pattern for the new "cl" warning format:
    # Optional prefix then: cl : command line warning <errorCode>: message
    cl_pattern = re.compile(
        r"(?:(?:\d+>\s*)?)"                               # optional numeric prefix
        r"cl\s*:\s*command\s+line\s+warning\s+(?P<warning_num>\S+):\s*(?P<message>.*)",
        re.IGNORECASE
    )

    try:
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Log file '{filename}' not found.", file=sys.stderr)
        return [] # Return empty list if file not found
    except Exception as e:
        print(f"Error reading log file '{filename}': {e}", file=sys.stderr)
        return [] # Return empty list on other read errors


    current_warning_text = None
    current_key = None
    i = 0

    while i < len(lines):
        # Remove trailing spaces from the original line
        line = lines[i].rstrip(' ')
        # Remove numeric prefix such as "80>" if present at the start
        clean_line = re.sub(r'^\d+>\s*', '', line)

        # If current warning text already contains project path or compiling source, finish accumulation.
        if current_warning_text is not None:
            if extract_project_path(current_warning_text) != "N/A" or has_compiling_source(current_warning_text):
                warnings.append((current_key, current_warning_text.strip()))
                current_warning_text = None
                current_key = None
                # Do not increment i here, reprocess the current line as it might start a new warning
                continue # Use continue to re-evaluate line 'i' in the next loop iteration

        # Check for the CSC warning format using search (match anywhere in the line).
        csc_match = csc_pattern.search(clean_line)
        if csc_match:
            # If there's a pending warning, save it first
            if current_warning_text is not None:
                warnings.append((current_key, current_warning_text.strip()))
                current_warning_text = None
                current_key = None
            # Create key for CSC warning (no file/line info)
            warning_code = csc_match.group("warning_num").strip()
            key = ("N/A", "N/A", "N/A", warning_code)
            warnings.append((key, clean_line.strip()))
            i += 1
            continue

        # Check for the cl warning format.
        cl_match = cl_pattern.search(clean_line)
        if cl_match:
            # If there's a pending warning, save it first
            if current_warning_text is not None:
                warnings.append((current_key, current_warning_text.strip()))
                current_warning_text = None
                current_key = None
            # Create key for cl warning (no file/line info)
            warning_code = cl_match.group("warning_num").strip()
            key = ("N/A", "N/A", "N/A", warning_code)
            warnings.append((key, clean_line.strip()))
            i += 1
            continue

        # Check if the line matches the original warning format.
        original_match = original_pattern.search(clean_line)
        if original_match:
            # If there's a pending warning, save it first
            if current_warning_text is not None:
                warnings.append((current_key, current_warning_text.strip()))
            # Extract info and start a new warning context
            filepath = original_match.group("filepath").strip()
            line_no = original_match.group("line").strip()
            column = original_match.group("column").strip()
            warning_code = original_match.group("warning_num").strip()
            current_key = (filepath, line_no, column, warning_code)
            current_warning_text = clean_line # Start accumulating the warning text
            i += 1
        else:
            # This line is not a new warning start
            if current_warning_text is not None:
                # This line is part of the current multi-line warning
                # If line is empty, end the current warning.
                if clean_line.strip() == "":
                    warnings.append((current_key, current_warning_text.strip()))
                    current_warning_text = None
                    current_key = None
                    i += 1
                # If the current line contains a project path, append up to that part and end warning.
                elif has_project_path(clean_line):
                    project_path = extract_project_path(clean_line)
                    project_pattern = r'\[' + re.escape(project_path) + r'\]'
                    match = re.search(project_pattern, clean_line)
                    if match:
                        # Append only the part of the line up to and including the project path
                        end_pos = match.end()
                        truncated_line = clean_line[:end_pos]
                        current_warning_text += " " + truncated_line.strip() # Add stripped line part
                    else:
                        # Fallback: append the whole line if pattern match fails unexpectedly
                        current_warning_text += " " + clean_line.strip()

                    # Check if the *next* line contains compiling source info; if so, append it.
                    if i + 1 < len(lines):
                         next_line_clean = re.sub(r'^\d+>\s*', '', lines[i + 1].rstrip(' '))
                         if has_compiling_source(next_line_clean):
                             i += 1 # Consume the next line as well
                             compiling_source = extract_compiling_source(next_line_clean)
                             # Append the compiling source info in a standard format
                             current_warning_text += " (compiling source file '" + compiling_source + "')"

                    # Finalize the current warning
                    warnings.append((current_key, current_warning_text.strip()))
                    current_warning_text = None
                    current_key = None
                    i += 1 # Move past the current line (and possibly the next line if it had compiling info)
                # If the line looks like a new warning (original format), finish the current one first.
                # This handles cases where multiline messages end right before a new warning starts.
                elif original_pattern.search(clean_line):
                    warnings.append((current_key, current_warning_text.strip()))
                    current_warning_text = None
                    current_key = None
                    # Do not increment i, let the next iteration handle the new warning start.
                    continue # Re-process current line
                else:
                    # Append regular continuation lines (stripped) to the current warning.
                    if clean_line.strip(): # Only append if line is not just whitespace
                        current_warning_text += " " + clean_line.strip()
                    i += 1
            else:
                # This line is not part of a warning, skip it.
                i += 1

    # Append any remaining warning accumulated at the end of the file.
    if current_warning_text is not None:
        warnings.append((current_key, current_warning_text.strip()))

    return warnings

def compare_warnings(log1, log2):
    """
    Compare the warning messages from two log files.
    Returns a list of tuples: (key, warning_text, additional_count),
    where additional_count is the number of extra occurrences of this warning
    in log2 compared to log1.
    """
    print(f"Parsing warnings from {log1}...")
    warnings1 = parse_warnings(log1)
    print(f"Found {len(warnings1)} warnings in {log1}.")
    print(f"Parsing warnings from {log2}...")
    warnings2 = parse_warnings(log2)
    print(f"Found {len(warnings2)} warnings in {log2}.")

    # Count occurrences in log1 using the warning's unique key.
    counts1 = {}
    for key, text in warnings1:
        counts1[key] = counts1.get(key, 0) + 1

    # Count occurrences in log2 and store a representative message.
    counts2 = {}
    details2 = {} # Store one representative text for each key in log2
    for key, text in warnings2:
        counts2[key] = counts2.get(key, 0) + 1
        # Keep the first encountered text for this key
        if key not in details2:
            details2[key] = text

    added = []
    # Compare counts for each warning found in log2.
    for key, count2 in counts2.items():
        count1 = counts1.get(key, 0) # Get count from log1, default to 0 if not present
        if count2 > count1:
            # If count in log2 is greater, calculate the difference
            extra = count2 - count1
            # Use the representative text stored for this key
            added.append((key, details2[key], extra))

    print(f"Found {len(added)} types of warnings with increased counts in {os.path.basename(log2)}.")
    return added

def main():
    """
    Main function to compare warnings between two folders.
    Expects two command-line arguments: <old_folder> and <new_folder>.
    Reads log filenames from the configuration file "compare.config".
    Writes the comparison results to output CSV files, including author info from git blame.
    Attempts to run git blame within the detected repository root.
    """
    if len(sys.argv) < 3:
        print("Usage: python compare_warnings.py <old_folder> <new_folder>")
        sys.exit(1)
    old_folder = sys.argv[1]
    new_folder = sys.argv[2]

    # Read log filenames from configuration file "compare.config"
    config_filename = "compare.config"
    try:
        with open(config_filename, "r", encoding="utf-8") as f:
            config_content = f.read()
        files = []
        for line in config_content.splitlines():
            line = line.strip()
            if line == "" or line.startswith("#"): # Skip empty lines and comments
                continue
            # Support comma-separated values in one line.
            if "," in line:
                parts = line.split(",")
                for part in parts:
                    part_stripped = part.strip()
                    if part_stripped: # Avoid adding empty strings if there are trailing commas
                        files.append(part_stripped)
            else:
                if line: # Avoid adding empty strings from blank lines
                    files.append(line)
    except FileNotFoundError:
         print(f"Error: Configuration file '{config_filename}' not found.")
         sys.exit(1)
    except Exception as e:
        print(f"Error reading config file {config_filename}: {e}")
        sys.exit(1)

    if not files:
        print(f"Warning: No log files specified in '{config_filename}'.")
        sys.exit(0)


    # --- Attempt to find the Git repository root once at the start ---
    repo_root = find_git_repo_root()
    # If git command itself is not found, find_git_repo_root sets git_blame_not_found flag.


    # Create an output folder with timestamp.
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    output_folder = f"output_{timestamp}"
    try:
        os.makedirs(output_folder, exist_ok=True)
    except OSError as e:
        print(f"Error creating output directory '{output_folder}': {e}")
        sys.exit(1)

    # Process each log file specified in the configuration file.
    for log_filename in files:
        old_file = os.path.join(old_folder, log_filename)
        new_file = os.path.join(new_folder, log_filename)

        # Check if both old and new log files exist
        old_exists = os.path.exists(old_file)
        new_exists = os.path.exists(new_file)

        if not old_exists:
            print(f"Warning: File {old_file} does not exist, skipping comparison for '{log_filename}'.")
            continue # Skip this file pair
        if not new_exists:
            print(f"Warning: File {new_file} does not exist, skipping comparison for '{log_filename}'.")
            continue # Skip this file pair


        print(f"\nComparing '{log_filename}':")
        print(f"  Old log: {old_file}")
        print(f"  New log: {new_file}")

        added_warnings = compare_warnings(old_file, new_file)
        total_added_count = sum(extra for _, _, extra in added_warnings) # Sum of counts, not types

        if not added_warnings:
            print(f"No new warnings found for '{log_filename}'.")
            # Optionally create an empty CSV or skip file creation
            # continue # Skip CSV creation if no new warnings
            # Let's create the CSV even if empty for consistency
            pass


        # Construct output filename with .csv extension.
        base = os.path.splitext(log_filename)[0]
        # Use total count in filename
        output_filename = f"{base}_new_warning_{total_added_count}.csv"
        output_filepath = os.path.join(output_folder, output_filename)

        print(f"Writing results to {output_filepath}...")

        # Write the CSV content into the output file.
        try:
            with open(output_filepath, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile, quoting=csv.QUOTE_ALL)
                # New header order including Author and E-Mail
                writer.writerow(["Author", "E-Mail", "Warning keyword", "Message", "Project", "Compiling Source", "File path", "Line", "Column", "Repeat Count"])

                if not added_warnings:
                    # Write only header if no new warnings
                    pass
                else:
                    processed_count = 0
                    # Iterate through the identified new/increased warnings
                    for key, text, extra in added_warnings:
                        filepath, line_no, column, warning_code = key
                        project = extract_project_path(text)
                        compiling_source = extract_compiling_source(text)

                        author = "N/A"
                        email = "N/A"
                        # Only run git blame if filepath/line_no are valid AND git command is available
                        if filepath != "N/A" and line_no != "N/A" and not git_blame_not_found:
                            # Pass the determined repo_root (which might be None if not found)
                            author, email = get_git_blame_info(filepath, line_no, repo_root)
                        # else: Git not found or N/A path/line, author/email remain "N/A"


                        # Write the row including author and email information
                        writer.writerow([author, email, warning_code, text, project, compiling_source, filepath, line_no, column, extra])
                        processed_count += 1
                        # Optional: Add progress indicator?
                        if processed_count % 50 == 0:
                           print(f"  Processed {processed_count} new warning types for git blame...")


            print(f"Comparison result for '{log_filename}' ({total_added_count} total new warnings across {len(added_warnings)} types) written to '{output_filepath}'.")

        except IOError as e:
            print(f"Error writing output file '{output_filepath}': {e}")
        except Exception as e:
             print(f"An unexpected error occurred while processing '{log_filename}': {e}")


if __name__ == "__main__":
    main()