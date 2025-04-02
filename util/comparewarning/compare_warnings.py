import csv
import sys
import os
import datetime
# Removed subprocess, re imports as they are now in other modules

# Import the new utility modules
import git_utils
import warning_parser
import comparison

# Removed function definitions: find_git_repo_root, extract_project_path, has_project_path,
# has_compiling_source, extract_compiling_source, get_git_blame_info, parse_warnings,
# compare_warnings as they are moved to separate files.

# Removed the global git_blame_not_found initialization here, it's in git_utils.py

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
                        # Call functions from warning_parser module
                        project = warning_parser.extract_project_path(text)
                        compiling_source = warning_parser.extract_compiling_source(text)

                        author = "N/A"
                        email = "N/A"
                        # Only run git blame if filepath/line_no are valid AND git command is available
                        # Access the global flag from the git_utils module
                        if filepath != "N/A" and line_no != "N/A" and not git_utils.git_blame_not_found:
                            # Call the function from the git_utils module
                            # Pass the determined repo_root (which might be None if not found)
                            author, email = git_utils.get_git_blame_info(filepath, line_no, repo_root)
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