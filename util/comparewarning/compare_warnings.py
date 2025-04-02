import csv
import sys
import os
import datetime
import configparser
# Removed subprocess, re imports as they are now in other modules

# Import the new utility modules
import git_utils
import warning_parser
import comparison

def read_config():
    config = configparser.ConfigParser()
    try:
        # Use absolute path to read config file
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'common.config')
        config.read(config_path)
        commit_url_prefix = config.get('DEFAULT', 'COMMIT_URL_PREFIX', fallback="")
        # Remove quotes if present
        if commit_url_prefix.startswith('"') and commit_url_prefix.endswith('"'):
            commit_url_prefix = commit_url_prefix[1:-1]
        return {'COMMIT_URL_PREFIX': commit_url_prefix}
    except Exception as e:
        print(f"Warning: Error reading common.config: {e}", file=sys.stderr)
        return {'COMMIT_URL_PREFIX': ""}

def main():
    """
    Main function to compare warnings between two folders.
    Expects two command-line arguments: <old_folder> and <new_folder>.
    Reads log filenames from the configuration file "compare.config".
    Writes the comparison results to output CSV files, including author info and commit hash from git blame.
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
    # Call the function from the git_utils module
    repo_root = git_utils.find_git_repo_root()
    # If git command itself is not found, find_git_repo_root sets git_utils.git_blame_not_found flag.


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

        # Call the function from the comparison module
        added_warnings = comparison.compare_warnings(old_file, new_file)
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
                # Header remains the same conceptually, but the content will be a URL if prefix is set
                writer.writerow(["Committer", "E-Mail", "Commit URL", "Warning keyword", "Message", "Project", "Compiling Source", "File path", "Line", "Column", "Repeat Count"]) # Updated header slightly

                if not added_warnings:
                    # Write only header if no new warnings
                    pass
                else:
                    processed_count = 0
                    # Create a cache dictionary to store blame information for files
                    blame_cache = {}
                    print(f"\nStarting to process warnings, creating local blame cache...")
                    
                    # Iterate through the identified new/increased warnings
                    for key, text, extra in added_warnings:
                        filepath, line_no, column, warning_code = key
                        # Get blame map from cache, if not exists then load and cache it
                        if filepath != "N/A" and filepath not in blame_cache:
                            if git_utils.is_debug_enabled():
                                print(f"Local cache miss: File '{filepath}' not in local cache, calling git_utils to get blame info")
                            blame_cache[filepath] = git_utils.get_blame_map_for_file(filepath, repo_root)
                        elif filepath != "N/A" and git_utils.is_debug_enabled():
                            print(f"Local cache hit: Getting blame info for file '{filepath}' from local cache")
                        
                        # Call functions from warning_parser module
                        project = warning_parser.extract_project_path(text)
                        compiling_source = warning_parser.extract_compiling_source(text)

                        author = "N/A"
                        email = "N/A"
                        commit_hash = "N/A"
                        if filepath != "N/A" and line_no != "N/A":
                            try:
                                line_int = int(line_no)
                                blame_map = blame_cache.get(filepath, {})
                                if line_int in blame_map:
                                    author, email, commit_hash = blame_map[line_int]
                            except Exception:
                                pass
                        # else: Git not found or N/A path/line, author/email/commit remain "N/A"

                        # Get COMMIT_URL_PREFIX from config
                        commit_url_prefix = read_config()['COMMIT_URL_PREFIX']
                        
                        # Prepare the commit information for display (either hash or full URL)
                        commit_display_info = commit_hash # Default to hash or "N/A"
                        if commit_url_prefix and commit_hash != "N/A":
                            commit_display_info = commit_url_prefix + commit_hash

                        # Write the row including author, email, and the commit display info
                        writer.writerow([author, email, commit_display_info, warning_code, text, project, compiling_source, filepath, line_no, column, extra])
                        processed_count += 1
                        
                        # Display progress bar
                        if processed_count % 10 == 0:
                            total = len(added_warnings)
                            percent = int(processed_count / total * 100)
                            bar_length = 30
                            filled_length = int(bar_length * processed_count / total)
                            bar = '█' * filled_length + '░' * (bar_length - filled_length)
                            print(f"\rProgress: [{bar}] {percent}% ({processed_count}/{total})", end='', flush=True)


            print(f"\nComparison result for '{log_filename}' ({total_added_count} total new warnings across {len(added_warnings)} types) written to '{output_filepath}'.")

        except IOError as e:
            print(f"Error writing output file '{output_filepath}': {e}")
        except Exception as e:
             print(f"An unexpected error occurred while processing '{log_filename}': {e}")


if __name__ == "__main__":
    main()
