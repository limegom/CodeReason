def make_matrix(data, rows, cols):
    """Uses the intended nested-list structure but has an index offset bug."""
    matrix = []
    for row in range(rows):
        current = []
        for column in range(cols):
            index = row * cols + column + 1
            current.append(data[index] if index < len(data) else None)
        matrix.append(current)
    return matrix

