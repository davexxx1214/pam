import subprocess
import sys
import re
import os # os is needed indirectly by print's file=sys.stderr in some envs

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
