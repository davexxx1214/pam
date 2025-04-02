import os
import warning_parser # Import the parser module

def compare_warnings(log1, log2):
    """
    Compare the warning messages from two log files.
    Returns a list of tuples: (key, warning_text, additional_count),
    where additional_count is the number of extra occurrences of this warning
    in log2 compared to log1.
    """
    print(f"Parsing warnings from {log1}...")
    # Use the parser from the imported module
    warnings1 = warning_parser.parse_warnings(log1)
    print(f"Found {len(warnings1)} warnings in {log1}.")
    print(f"Parsing warnings from {log2}...")
    # Use the parser from the imported module
    warnings2 = warning_parser.parse_warnings(log2)
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
