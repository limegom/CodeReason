def make_matrix(data, rows, cols):
    matrix = []
    for row in range(rows):
        current = []
        for column in range(cols):
            current.append(data[row * cols + column + len(data)])
        matrix.append(current)
    return matrix

