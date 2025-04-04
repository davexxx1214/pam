import re
import sys

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

def parse_warnings(filename):
    """
    Parse warning messages from the log file and return a list.
    Each element in the list is a tuple (key, warning_text),
    where key is a tuple (file path, line number, column number, warning code),
    and warning_text is the complete warning message.
    """
    warnings = []

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