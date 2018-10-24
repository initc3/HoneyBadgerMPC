from betterpairing import *

def polynomial_divide(numerator, denominator):
    temp = list(numerator)
    factors = []
    while len(temp) >= len(denominator):
        diff = len(temp) - len(denominator)
        factor = temp[len(temp) - 1] / denominator[len(denominator) - 1]
        factors.insert(0, factor)
        for i in range(len(denominator)):
            temp[i+diff] = temp[i+diff] - (factor * denominator[i])
        temp = temp[:len(temp)-1]
    return factors

def polynomial_multiply_constant(poly1, c):
    #myzero will be appropriate whether we are in ZR or G
    #myzero = poly1[0] - poly1[0]
    product = [None] * len(poly1)
    for i in range(len(product)):
        product[i] = poly1[i] * c
    return product

def polynomial_multiply(poly1, poly2):
    myzero = ZR(0)
    product = [myzero] * (len(poly1) + len(poly2) -1)
    for i in range(len(poly1)):
        temp = polynomial_multiply_constant(poly2, poly1[i])
        while i > 0:
            temp.insert(0,myzero)
            i -= 1
        product = polynomial_add(product, temp)
    return product

def polynomial_add(poly1, poly2):
    if len(poly1) >= len(poly2):
        bigger = poly1
        smaller = poly2
    else:
        bigger = poly2
        smaller = poly1
    polysum = [None] * len(bigger)
    for i in range(len(bigger)):
        polysum[i] = bigger[i]
        if i < len(smaller):
            polysum[i] = polysum[i] + smaller[i]
    return polysum

def polynomial_subtract(poly1, poly2):
    negpoly2 = polynomial_multiply_constant(poly2, -1)
    return polynomial_add(poly1, negpoly2)
    
# Polynomial evaluation
def f(poly, x):
    assert type(poly) is list
    y = ZR(0)
    xx = ZR(1)
    for coeff in poly:
        y += coeff * xx
        xx *= x
    return y
    
def interpolate_at_x(coords, x, order=-1):
    ONE = ZR(1)
    if order == -1:
        order = len(coords)
    xs = []
    sortedcoords = sorted(coords, key=lambda x: x[0])
    for coord in sortedcoords:
        xs.append(coord[0])
    S = set(xs[0:order])
    #The following line makes it so this code works for both members of G and ZR
    out = coords[0][1] - coords[0][1]
    for i in range(order):
        out = out + (lagrange_at_x(S,xs[i],x,group) * sortedcoords[i][1])
    return out

def lagrange_at_x(S,j,x):
    ONE = group.random(ZR)*0 + 1
    S = sorted(S)
    assert j in S
    mul = lambda a,b: a*b
    num = reduce(mul, [x - jj  for jj in S if jj != j], ONE)
    den = reduce(mul, [j - jj  for jj in S if jj != j], ONE)
    return num / den

def interpolate_poly(coords):
    myone = ZR(1)
    myzero = ZR(0)
    if group is not None:
        myone = group.random(ZR)*0 + 1
    #print "IT'SA ME " + str(myzero) + ", THE IDENTITY ELEMENT!"
    #print "Before: " + str(coords[0][1]) + " After: " + str(myzero + coords[0][1])
    poly = [myzero] * len(coords)
    for i in range(len(coords)):
        temp = [myone]
        for j in range(len(coords)):
            if i == j:
                continue
            temp = polynomial_multiply(temp, [ -1 * (coords[j][0] * myone), myone])
            temp = polynomial_divide(temp, [myone * coords[i][0] - myone * coords[j][0]])
        poly = polynomial_add(poly, polynomial_multiply_constant(temp,coords[i][1]))
    return poly