
# compute the reduced-row echelon form of a matrix in place


def rref(matrix):
    if not matrix:
        return

    num_rows = len(matrix)
    num_cols = len(matrix[0])

    i, j = 0, 0
    while True:
        if i >= num_rows or j >= num_cols:
            break

        if matrix[i][j] == 0:
            non_zero_row = i
            while non_zero_row < num_rows and matrix[non_zero_row][j] == 0:
                non_zero_row += 1

            if non_zero_row == num_rows:
                j += 1
                continue

            temp = matrix[i]
            matrix[i] = matrix[non_zero_row]
            matrix[non_zero_row] = temp

        pivot = matrix[i][j]
        matrix[i] = [x / pivot for x in matrix[i]]

        for other_row in range(0, num_rows):
            if other_row == i:
                continue
            if matrix[other_row][j] != 0:
                matrix[other_row] = [y - matrix[other_row][j] * x
                                     for (x, y) in zip(matrix[i], matrix[other_row])]

        i += 1
        j += 1

    return matrix


# check if a row-reduced system has no solution
# if there is no solution, return (True, dont-care)
# if there is a solution, return (False, i) where i is the index of the last nonzero row
def no_solution(a):
    i = -1
    while all(x == 0 for x in a[i]):
        i -= 1

    last_non_zero_row = a[i]
    if all(x == 0 for x in last_non_zero_row[:-1]):
        return True, 0

    return False, i


# determine if the given column is a pivot column (contains all zeros except a single 1)
# and return the row index of the 1 if it exists
def is_pivot_column(a, j):
    i = 0
    while a[i][j] == 0 and i < len(a):
        i += 1

    if i == len(a):
        return (False, i)

    if a[i][j] != 1:
        return (False, i)
    else:
        pivot_row = i

    i += 1
    while i < len(a):
        if a[i][j] != 0:
            return (False, pivot_row)
        i += 1

    return (True, pivot_row)


# return any solution of the system, with free variables set to the given value
def some_solution(system, free_variable_value=1):
    rref(system)

    has_no_solution, _ = no_solution(system)
    if has_no_solution:
        raise Exception("No solution")

    num_vars = len(system[0]) - 1  # last row is constants
    variable_values = [0] * num_vars

    free_vars = set()
    pivot_vars = set()
    row_index_to_pivot_col_idx = dict()
    pivot_row_idx = dict()

    for j in range(num_vars):
        is_pivot, row_of_pivot = is_pivot_column(system, j)
        if is_pivot:
            row_index_to_pivot_col_idx[row_of_pivot] = j
            pivot_row_idx[j] = row_of_pivot
            pivot_vars.add(j)
        else:
            free_vars.add(j)

    for j in free_vars:
        variable_values[j] = free_variable_value

    for j in pivot_vars:
        the_row = pivot_row_idx[j]
        variable_values[j] = (system[the_row][-1] -
                              sum(system[the_row][i] *
                                  variable_values[i] for i in free_vars))

    return variable_values
