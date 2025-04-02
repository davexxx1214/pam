import subprocess
import sys
import re
import os
import configparser

# Initialize a flag to prevent repeated 'git not found' warnings
git_blame_not_found = False

# Global cache to store blame information for files
# Key: file path, Value: blame map
global_blame_cache = {}

# Read configuration file
def read_config():
    config = configparser.ConfigParser()
    try:
        # Use absolute path to read config file
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'common.config')
        config.read(config_path)
        debug_enabled = config.getboolean('DEFAULT', 'enableDebug', fallback=False)
        return {'enableDebug': debug_enabled}
    except Exception as e:
        print(f"Warning: Error reading common.config: {e}", file=sys.stderr)
        return {'enableDebug': False}

# Get debug mode status
def is_debug_enabled():
    return read_config()['enableDebug']

def get_actual_case_path(repo_root, rel_path):
    """
    Given the repo_root and a relative path, this function returns the actual stored path 
    using the correct case. On Windows, although the file system is case-insensitive, 
    Git requires the path's case to match exactly what is stored in the repository.
    This function recursively traverses each component of the path to correct its case.
    """
    components = rel_path.split(os.sep)
    current_dir = repo_root
    corrected_components = []
    for comp in components:
        try:
            entries = os.listdir(current_dir)
        except Exception:
            corrected_components.append(comp)
            current_dir = os.path.join(current_dir, comp)
            continue
        found = None

        for entry in entries:
            if entry.lower() == comp.lower():
                found = entry
                break
        if found:
            corrected_components.append(found)
            current_dir = os.path.join(current_dir, found)
        else:
            corrected_components.append(comp)
            current_dir = os.path.join(current_dir, comp)
    return os.path.join(*corrected_components)

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

def get_blame_map_for_file(filepath, repo_root=None):
    """
    Preload git blame info for all lines in a file and return a map:
    line number -> (author, email, commit_hash)
    """
    global git_blame_not_found, global_blame_cache
    
    # Check if the file's blame map is already in the global cache
    if filepath in global_blame_cache:
        if is_debug_enabled():
            print(f"Cache hit: Getting blame info for file '{filepath}' from global cache")
        return global_blame_cache[filepath]
    
    blame_map = {}
    # Cache for storing author and email info for each commit
    commit_info_cache = {}

    if filepath == "N/A" or git_blame_not_found:
        return blame_map

    exec_cwd = repo_root
    path_for_git = filepath
    using_relative_path = False

    if repo_root and os.path.isabs(filepath):
        try:
            norm_repo_root = os.path.normcase(os.path.realpath(repo_root))
            norm_filepath = os.path.normcase(os.path.realpath(filepath))
        except OSError:
            norm_repo_root = os.path.normcase(os.path.normpath(repo_root))
            norm_filepath = os.path.normcase(os.path.normpath(filepath))

        if norm_filepath.startswith(norm_repo_root + os.sep) or norm_filepath == norm_repo_root:
            try:
                relative_path = os.path.relpath(filepath, repo_root)
                if os.name == "nt":
                    relative_path = get_actual_case_path(repo_root, relative_path)
                path_for_git = relative_path.replace(os.sep, '/')
                using_relative_path = True
            except ValueError:
                path_for_git = filepath
    elif not os.path.isabs(filepath):
        path_for_git = filepath.replace(os.sep, '/')

    blame_command = [
        "git", "blame",
        "--porcelain",
        "--", path_for_git
    ]

    try:
        blame_result = subprocess.run(
            blame_command,
            cwd=exec_cwd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=False,
            stdin=subprocess.DEVNULL,
        )

        if blame_result.returncode != 0:
            return blame_map

        lines = blame_result.stdout.splitlines()
        current_line = 0
        pending_commit = None
        pending_author = None
        pending_email = None
        line_index = 0
            
        while line_index < len(lines):
            line = lines[line_index]
            if re.match(r'^[0-9a-f]{40} ', line):
                parts = line.split()
                if len(parts) >= 3:
                    pending_commit = parts[0]
                    try:
                        current_line = int(parts[2])
                    except ValueError:
                        current_line = 0
                
                # Check if we already have info for this commit in our cache
                if pending_commit in commit_info_cache:
                    pending_author, pending_email = commit_info_cache[pending_commit]
                    line_index += 1  # Increment line index to process next line
                else:
                    pending_author = "N/A"
                    pending_email = "N/A"
                    line_index += 1  # Increment line index to process next line
                    
                    # Save current line index for backtracking
                    start_index = line_index
                    
                    # Look for committer and email information
                    committer_found = False
                    email_found = False
                    committer_value = "N/A"
                    email_value = "N/A"
                    
                    # First scan through to find committer and email info
                    scan_index = start_index
                    while scan_index < len(lines) and not lines[scan_index].startswith('\t'):
                        current_line_content = lines[scan_index]
                        
                        if current_line_content.startswith("committer "):
                            committer_value = current_line_content[10:].strip()
                            committer_found = True
                        elif current_line_content.startswith("committer-mail "):
                            email_value = current_line_content[15:].strip().strip('<>')
                            email_found = True
                        
                        scan_index += 1
                    
                    # Update committer and email information
                    if committer_found:
                        pending_author = committer_value
                    if email_found:
                        pending_email = email_value
                    
                    # Store author and email info in commit cache
                    commit_info_cache[pending_commit] = (pending_author, pending_email)
                    
                    # Continue processing other header information
                    while line_index < len(lines) and not lines[line_index].startswith('\t'):
                        line_index += 1
                
                if line_index < len(lines) and lines[line_index].startswith('\t'):
                    if current_line > 0 and pending_commit:
                        blame_map[current_line] = (pending_author, pending_email, pending_commit)
                    current_line += 1
                    line_index += 1
                elif current_line > 0 and pending_commit:
                    # If no content line is found but we have line number and commit, add to blame_map anyway
                    blame_map[current_line] = (pending_author, pending_email, pending_commit)
            else:
                line_index += 1
    except FileNotFoundError:
        git_blame_not_found = True
    except Exception:
        pass
    
    # Store the blame map in the global cache
    global_blame_cache[filepath] = blame_map
    if is_debug_enabled():
        print(f"Cache created: Added blame info for file '{filepath}' to global cache, containing {len(blame_map)} lines")
    return blame_map

def get_git_blame_info(filepath, line_no, repo_root=None):
    """
    Use git blame to get the author, email, and commit hash information
    for a specific file and line number.
    """
    global git_blame_not_found
    
    # Check if filepath and line number are valid
    if filepath == "N/A" or line_no == "N/A":
        return "N/A", "N/A", "N/A"
    
    # If Git command was globally determined as not found, exit early
    if git_blame_not_found:
        return "N/A", "N/A", "N/A"
    
    try:
        # Try to get blame info from the blame map
        blame_map = get_blame_map_for_file(filepath, repo_root)
        line_num = int(line_no)
        
        if line_num in blame_map:
            return blame_map[line_num]
        
        # If not found in blame map, return default values
        return "N/A", "N/A", "N/A"
    except Exception as e:
        print(f"Warning: An error occurred during git blame for {filepath} at line {line_no}: {e}", file=sys.stderr)
        return "N/A", "N/A", "N/A"
