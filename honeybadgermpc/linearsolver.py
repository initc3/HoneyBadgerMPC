
# compute the reduced-row echelon form of a matrix in place


def rref(matrix):
    if not matrix:
        return

    numRows = len(matrix)
    numCols = len(matrix[0])

    i, j = 0, 0
    while True:
        if i >= numRows or j >= numCols:
            break

        if matrix[i][j] == 0:
            nonzeroRow = i
            while nonzeroRow < numRows and matrix[nonzeroRow][j] == 0:
                nonzeroRow += 1

            if nonzeroRow == numRows:
                j += 1
                continue

            temp = matrix[i]
            matrix[i] = matrix[nonzeroRow]
            matrix[nonzeroRow] = temp

        pivot = matrix[i][j]
        matrix[i] = [x / pivot for x in matrix[i]]

        for otherRow in range(0, numRows):
            if otherRow == i:
                continue
            if matrix[otherRow][j] != 0:
                matrix[otherRow] = [y - matrix[otherRow][j] * x
                                    for (x, y) in zip(matrix[i], matrix[otherRow])]

        i += 1
        j += 1

    return matrix


# check if a row-reduced system has no solution
# if there is no solution, return (True, dont-care)
# if there is a solution, return (False, i) where i is the index of the last nonzero row
def noSolution(A):
    i = -1
    while all(x == 0 for x in A[i]):
        i -= 1

    lastNonzeroRow = A[i]
    if all(x == 0 for x in lastNonzeroRow[:-1]):
        return True, 0

    return False, i


# determine if the given column is a pivot column (contains all zeros except a single 1)
# and return the row index of the 1 if it exists
def isPivotColumn(A, j):
    i = 0
    while A[i][j] == 0 and i < len(A):
        i += 1

    if i == len(A):
        return (False, i)

    if A[i][j] != 1:
        return (False, i)
    else:
        pivotRow = i

    i += 1
    while i < len(A):
        if A[i][j] != 0:
            return (False, pivotRow)
        i += 1

    return (True, pivotRow)


# return any solution of the system, with free variables set to the given value
def someSolution(system, freeVariableValue=1):
    rref(system)

    hasNoSolution, lastNonzeroRowIndex = noSolution(system)
    if hasNoSolution:
        raise Exception("No solution")

    numVars = len(system[0]) - 1  # last row is constants
    variableValues = [0] * numVars

    freeVars = set()
    pivotVars = set()
    rowIndexToPivotColumnIndex = dict()
    pivotRowIndex = dict()

    for j in range(numVars):
        isPivot, rowOfPivot = isPivotColumn(system, j)
        if isPivot:
            rowIndexToPivotColumnIndex[rowOfPivot] = j
            pivotRowIndex[j] = rowOfPivot
            pivotVars.add(j)
        else:
            freeVars.add(j)

    for j in freeVars:
        variableValues[j] = freeVariableValue

    for j in pivotVars:
        theRow = pivotRowIndex[j]
        variableValues[j] = (system[theRow][-1] -
                             sum(system[theRow][i] *
                                 variableValues[i] for i in freeVars))

    return variableValues
