def get_entries_by_category(filename, category):
    # Read the file
    with open(filename, 'r') as file:
        content = file.read()

    # Split the content into sections based on the square brackets
    sections = content.split('\n\n')

    # Define the categories
    valid_categories = ['CPU', 'NETWORK', 'MEM', 'GENERIC']

    # Validate the provided category
    if category not in valid_categories:
        return []

    # Find the section corresponding to the specified category
    target_section = None
    for section in sections:
        if section.startswith(f"[{category}]"):
            target_section = section
            break

    # If the category section was not found, return an empty list
    if target_section is None:
        return []

    # Extract the entries from the category section
    entries = [entry.strip() for entry in target_section.split('\n') if entry and not entry.startswith('[')]

    return entries
