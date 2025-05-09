import re
import sys

def extract_project_path(warning_text):
    """
    Extract project path from the warning text, typically enclosed in square brackets.
    """
    project_match = re.search(r'\[([^[\]]*?(?:\.vcxproj|\.csproj|/|\\)[^[\]]*?)\]', warning_text)
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

        # Check if the line matches the original warning format.
        original_match = original_pattern.search(clean_line)
        if original_match:
            # If there's a pending warning, save it first
            if current_warning_text is not None:
                print(f"[LOG] ({filename} line {i+1}) new warning starts, save previous: {current_warning_text}")
                warnings.append((current_key, current_warning_text.strip()))
            # Extract info and start a new warning context
            filepath = original_match.group("filepath").strip()
            line_no = original_match.group("line").strip()
            column = original_match.group("column").strip()
            warning_code = original_match.group("warning_num").strip()
            current_key = (filepath, line_no, column, warning_code)
            current_warning_text = clean_line # Only keep the first line
            print(f"[LOG] ({filename} line {i+1}) detected new warning: key={current_key}, text={current_warning_text}")
            warnings.append((current_key, current_warning_text.strip()))
            current_warning_text = None
            current_key = None
            i += 1
        else:
            # Not a warning line, just skip
            i += 1

    # No need to append any remaining warning, as all are saved immediately
    return warnings