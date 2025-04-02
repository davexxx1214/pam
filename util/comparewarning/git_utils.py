import subprocess
import sys
import re
import os

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
    Use git blame to get the author, email, and commit hash information
    for a specific file and line number.
    Relies on setting the correct 'cwd' (repo_root) for git blame to handle paths,
    and attempts to use relative paths within the repo for better cross-platform/case handling.

    Returns:
        tuple: (author, email, commit_hash) or ("N/A", "N/A", "N/A") on failure.
    """
    global git_blame_not_found # Access the global flag

    # Check if filepath and line number are valid
    if filepath == "N/A" or line_no == "N/A":
        # Return N/A for all three fields
        return "N/A", "N/A", "N/A"

    # If Git command was globally determined as not found, exit early.
    if git_blame_not_found:
        # Return N/A for all three fields
        return "N/A", "N/A", "N/A"

    # Use repo_root as the execution directory if found
    exec_cwd = repo_root
    commit_hash = "N/A" # Initialize commit_hash

    try:
        # Ensure line number is an integer
        line_num = int(line_no)
        if line_num <= 0:
            # Return N/A for all three fields
            return "N/A", "N/A", "N/A"

        # --- Prepare the path for git blame ---
        # Default: use the original path passed in. Git might handle absolute paths
        # correctly sometimes, or this is the fallback if relative path calculation fails.
        path_for_git = filepath
        using_relative_path = False # Flag for debugging output

        if repo_root and os.path.isabs(filepath):
            # Normalize paths for reliable prefix checking (case-insensitive on Windows)
            # Use realpath to resolve potential symlinks or '..' components first
            try:
                norm_repo_root = os.path.normcase(os.path.realpath(repo_root))
                norm_filepath = os.path.normcase(os.path.realpath(filepath))
            except OSError:
                 # realpath might fail if the path doesn't exist in the expected case
                 # Fallback to basic normalization
                 norm_repo_root = os.path.normcase(os.path.normpath(repo_root))
                 norm_filepath = os.path.normcase(os.path.normpath(filepath))


            # Check if the real filepath seems to be inside the real repo_root (case-insensitive check)
            # Ensure we add a separator to avoid matching "/path/to/repo" with "/path/to/repo_extra"
            if norm_filepath.startswith(norm_repo_root + os.sep) or norm_filepath == norm_repo_root:
                 # Now calculate the relative path using original casing (from the input filepath)
                try:
                    # Use original filepath and repo_root for relpath to preserve case
                    relative_path = os.path.relpath(filepath, repo_root)
                    # Git generally prefers forward slashes, convert for robustness
                    path_for_git = relative_path.replace(os.sep, '/')
                    using_relative_path = True
                    # print(f"Debug: Using relative path for git blame: '{path_for_git}' (CWD='{repo_root}')") # Optional debug
                except ValueError:
                    # This might happen on Windows if filepath and repo_root are on different drives.
                    # Should be rare if startswith passed, but handle defensively.
                    print(f"Warning: Could not determine relative path for '{filepath}' from '{repo_root}' (possibly different drives?). Using original path.", file=sys.stderr)
                    path_for_git = filepath # Fallback to original absolute path
            # else:
                 # Filepath is absolute but not detected within repo_root.
                 # Keep the original absolute path; let git blame try to handle it.
                 # print(f"Debug: Absolute path '{filepath}' not detected within repo '{repo_root}'. Using original path.", file=sys.stderr) # Optional debug
                 # path_for_git remains the original filepath

        elif not os.path.isabs(filepath):
             # Filepath is already relative. Assume it's relative to exec_cwd (which should be repo_root if found).
             # Convert slashes for Git.
             path_for_git = filepath.replace(os.sep, '/')
             # print(f"Debug: Using provided relative path '{path_for_git}' for git blame. CWD='{exec_cwd}'", file=sys.stderr) # Optional debug


        # Construct the git blame command using the determined path
        blame_command = [
            "git", "blame",
            f"-L{line_num},{line_num}",
            "--porcelain",
            "--", path_for_git # Use the potentially relative path with forward slashes
        ]

        # Execute the git blame command with cwd set
        # Ensure exec_cwd is repo_root if we intend to use a relative path.
        # If repo_root wasn't found (exec_cwd is None), using a relative path might fail,
        # but we proceed anyway as it might be relative to the script's CWD.
        effective_cwd = exec_cwd # exec_cwd is already repo_root or None

        # Add extra debug info to be used if blame fails
        cwd_info_on_fail = f"CWD='{effective_cwd}'" if effective_cwd else "CWD=Default (None)"
        path_info_on_fail = f"GitPath='{path_for_git}' (relative={using_relative_path}, original='{filepath}')"


        blame_result = subprocess.run(
            blame_command,
            cwd=effective_cwd, # Set the working directory to repo root if found
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=False,
            stdin=subprocess.DEVNULL,
        )

        # Check if the command executed successfully
        if blame_result.returncode != 0:
            # Include more context in the warning message
            print(f"Warning: git blame failed for line {line_no}. {cwd_info_on_fail}, {path_info_on_fail}. Error: {blame_result.stderr.strip()}", file=sys.stderr)
            # Return N/A for all three fields
            return "N/A", "N/A", "N/A"

        # --- Parse the blame output (robust parsing) ---
        author = "N/A"
        email = "N/A"
        # commit_hash already initialized to "N/A"
        lines = blame_result.stdout.splitlines()

        if not lines:
             cwd_info = f"CWD='{exec_cwd}'" if exec_cwd else "CWD=Default (None)"
             print(f"Warning: git blame produced no output for '{filepath}' at line {line_no}. {cwd_info}.", file=sys.stderr)
             # Return N/A for all three fields
             return "N/A", "N/A", "N/A"

        # Check if the first line looks like blame info (commit hash etc.)
        first_line_parts = lines[0].split()
        if len(first_line_parts) < 3 or not re.match(r'^[0-9a-f]{40}', first_line_parts[0]):
             cwd_info = f"CWD='{exec_cwd}'" if exec_cwd else "CWD=Default (None)"
             print(f"Warning: Unexpected git blame output format (first line) for '{filepath}' at line {line_no}. {cwd_info}. Output: {lines[0]}", file=sys.stderr)
             # Return N/A for all three fields
             return "N/A", "N/A", "N/A"

        # Successfully extracted commit hash from the first line
        commit_hash = first_line_parts[0] # Assign the found hash

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

        # Fallback if parsing didn't find author/email (commit_hash might still be valid)
        if not found_author: author = "N/A"
        if not found_email: email = "N/A"

        # Return all three pieces of information
        return author, email, commit_hash

    except FileNotFoundError:
        # Handle case where 'git' command is not found specifically during blame execution
        # This might occur if git was found initially but removed later, or PATH issues.
        if not git_blame_not_found: # Print only once globally
             print(f"Warning: 'git' command not found during blame execution. Please ensure Git is installed and in your PATH.", file=sys.stderr)
             git_blame_not_found = True # Set global flag
        # Return N/A for all three fields
        return "N/A", "N/A", "N/A"
    except ValueError:
        # Handle case where line_no is not a valid integer
        print(f"Warning: Invalid line number '{line_no}' for git blame.", file=sys.stderr)
        # Return N/A for all three fields
        return "N/A", "N/A", "N/A"
    except Exception as e:
        # Catch any other exceptions during git blame execution
        print(f"Warning: An error occurred during git blame for {filepath} at line {line_no}: {e}", file=sys.stderr)
        # Return N/A for all three fields
        return "N/A", "N/A", "N/A"