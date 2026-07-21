def make_matrix(data, rows, cols):
    if rows < 0 or cols < 0 or rows * cols != len(data):
        raise ValueError("rows * cols must equal len(data)")
    return [data[index : index + cols] for index in range(0, len(data), cols)]

