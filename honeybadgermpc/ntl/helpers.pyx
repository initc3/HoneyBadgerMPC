# Overall, the objective of this NTL-Python interface is to minimize the
# amount of code in C++
# The data validation and checking must be done in python in all cases!
# PEP8 standards are observed wherever possible but ignored in cases whether NTL
# classes are used (like ZZ, mat_ZZ_p, etc) and also for NTL function names
from .ctypes cimport ZZ_c, ZZ_p_c, mat_ZZ_p, vec_ZZ_p, ZZ_pX_c
from .ctypes cimport ZZ_p_conv_from_int, mat_ZZ_p_mul, ZZ_conv_from_int
from .objectwrapper cimport ccrepr, ccreadstr
from .ctypes cimport SetNumThreads, AvailableThreads, ZZ_p_init, ZZ_pX_get_coeff, \
    ZZ_pX_set_coeff, ZZ_pX_eval, SqrRootMod
from cpython.int cimport PyInt_AS_LONG

cdef ZZ_c py_obj_to_ZZ(object v):
    cdef ZZ_c result
    if isinstance(v, int):
        if v <= 2147483647:
            ZZ_conv_from_int(result, PyInt_AS_LONG(v))
        else:
            ccreadstr(result, str(v))
    elif v is not None:
        ccreadstr(result, v)
    else:
        raise ValueError(f"Unsupported data type. {type(v)}")

    return result

cdef ZZ_p_c py_obj_to_ZZ_p(object v):
    cdef ZZ_p_c result
    if isinstance(v, int):
        if v <= 2147483647:
            ZZ_p_conv_from_int(result, PyInt_AS_LONG(v))
        else:
            ccreadstr(result, str(v))
    elif v is not None:
        ccreadstr(result, v)
    else:
        raise ValueError(f"Unsupported data type. {type(v)}")

    return result

cdef vec_ZZ_p py_list_to_vec_ZZ_p(object v):
    cdef vec_ZZ_p result
    if not isinstance(v, list) and not isinstance(v, tuple):
        raise ValueError("Invalid arguments")

    result.SetLength(len(v))
    cdef int i
    for i in range(len(v)):
        result[i] = py_obj_to_ZZ_p(v[i])
    return result

cdef str ZZ_to_str(ZZ_c x):
    return ccrepr(x)

cpdef interpolate(x, y, modulus):
    """Interpolate polynomial P s.t. P(x[i]) = y[i]
    :param x: Evaluation points for polynomial
    :type x: list of integers
    :param y: Evaluation of polynomial
    :type y: list of integers
    :param modulus: Field modulus
    :type modulus: integer
    :return: 
    """
    assert len(x) == len(y)

    cdef vector[ZZ_c] x_vec;
    cdef vector[ZZ_c] y_vec;
    cdef vector[ZZ_c] r_vec;

    for xi in x:
        x_vec.push_back(py_obj_to_ZZ(xi))
    for yi in y:
        y_vec.push_back(py_obj_to_ZZ(yi))

    cdef ZZ_c zz_modulus = py_obj_to_ZZ(modulus)
    interpolate_c(r_vec, x_vec, y_vec, zz_modulus)

    result = []
    for i in range(r_vec.size()):
        result.append(int(ZZ_to_str(r_vec[i])))
    return result

cpdef evaluate(polynomial, x, modulus):
    """Evaluate polynomial at x"""
    cdef ZZ_pX_c poly
    cdef ZZ_p_c y
    cdef int i

    ZZ_p_init(py_obj_to_ZZ(modulus))
    poly.SetMaxLength(len(polynomial))
    for i in range(len(polynomial)):
        ZZ_pX_set_coeff(poly, i, py_obj_to_ZZ_p(polynomial[i]))

    ZZ_pX_eval(y, poly, py_obj_to_ZZ_p(x))
    return int(ccrepr(y))

cpdef vandermonde_inverse(x, modulus):
    """Generate inverse of vandermonde matrix
    :param x: Evaluation points for polynomial
    :type x: list of integers
    :param modulus: Field modulus
    :type modulus: integers
    :return: 
    """
    cdef vector[ZZ_c] x_vec;

    for xi in x:
        x_vec.push_back(py_obj_to_ZZ(xi))

    cdef ZZ_c zz_modulus = py_obj_to_ZZ(modulus)
    cdef mat_ZZ_p r
    vandermonde_inverse_c(r, x_vec, zz_modulus)

    return ccrepr(r)


class InterpolationError(Exception):
    pass


cpdef batch_vandermonde_interpolate(x, data_list, modulus):
    """Interpolate polynomials using vandermonde matrices
    
    This code is based on the observation that we have evaluations for different 
    polynomials P0, P1, etc on the same set of points x[0], x[1], .., x[k]
    
    We first generate the vandermonde matrix `A`
    https://en.wikipedia.org/wiki/Vandermonde_matrix
    
    More on the math behind this here
    http://pages.cs.wisc.edu/~sifakis/courses/cs412-s13/lecture_notes/CS412_12_Feb_2013.pdf
    
    :param x: list of evaluation points
    :type x: list of integers
    :param data_list: evaluations of polynomials
                      data_list[i][j] = evaluation of polynomial i at point x[j]
    :type data_list: list of lists
    :param modulus: field modulus
    :type modulus: integer
    :return: 
    """
    cdef vector[ZZ_c] x_vec;

    for xi in x:
        x_vec.push_back(py_obj_to_ZZ(xi))

    cdef ZZ_c zz_modulus = py_obj_to_ZZ(modulus)
    cdef mat_ZZ_p r
    d = vandermonde_inverse_c(r, x_vec, zz_modulus)
    if d is False:
        raise InterpolationError("Interpolation failed")

    cdef mat_ZZ_p m
    cdef int k = max([len(d) for d in data_list])
    cdef int n_chunks = len(data_list)
    m.SetDims(k, n_chunks)

    for i in range(n_chunks):
        l = len(data_list[i])
        for j in range(l):
            m[j][i] = py_obj_to_ZZ_p(data_list[i][j])
        for j in range(l, k):
            m[j][i] = py_obj_to_ZZ_p(0)
    cdef mat_ZZ_p reconstructions
    mat_ZZ_p_mul(reconstructions, r, m)

    polynomials = [[None] * k for _ in range(n_chunks)]
    for i in range(n_chunks):
        for j in range(k):
            polynomials[i][j] = int(ccrepr(reconstructions[j][i]))
    reconstructions.kill()
    m.kill()
    r.kill()
    return polynomials

cpdef batch_vandermonde_evaluate(x, polynomials, modulus):
    """Evaluate polynomials at given points x using vandermonde matrices
    
    :param x: evaluation points
    :type x: list of integers
    :param polynomials: polynomial coefficients. polynomials[i] = coefficients of the 
        i'th polynomial
    :type x: list of list of integers
    :param modulus: field modulus
    :type modulus: integer
    :return: 
    """
    cdef mat_ZZ_p vm_matrix, poly_matrix, res_matrix
    cdef int n = len(x)
    cdef int i, j
    # Number of chunks
    cdef int k = len(polynomials)
    # Degree of polynomial. Actually number of coefficients.
    cdef int d = max([len(poly) for poly in polynomials])

    cdef ZZ_c zz_modulus = py_obj_to_ZZ(modulus)
    ZZ_p_init(zz_modulus)

    # Set vm_matrix
    cdef vec_ZZ_p x_vec = py_list_to_vec_ZZ_p(x)
    set_vm_matrix_c(vm_matrix, x_vec, d, zz_modulus)

    # Set matrix with polynomial coefficients
    poly_matrix.SetDims(d, k)
    for i in range(k):
        l = len(polynomials[i])
        for j in range(l):
            poly_matrix[j][i] = py_obj_to_ZZ_p(polynomials[i][j])
        for j in range(l, d):
            poly_matrix[j][i] = py_obj_to_ZZ_p(0)

    # Finally multiply matrices. This gives evaluation of polynomials at
    # all points chosen
    mat_ZZ_p_mul(res_matrix, vm_matrix, poly_matrix)

    # Convert back to python friendly formats
    result = [[None] * n for _ in range(k)]
    for i in range(n):
        for j in range(k):
            result[j][i] = int(ccrepr(res_matrix[i][j]))
    return result

cpdef fft(coeffs, omega, modulus, int n):
    cdef int i, d;
    cdef vec_ZZ_p coeffs_vec, result_vec;

    ZZ_p_init(py_obj_to_ZZ(modulus))

    d = len(coeffs)
    coeffs_vec.SetLength(d)
    for i in range(d):
        coeffs_vec[i] = py_obj_to_ZZ_p(coeffs[i])

    cdef ZZ_p_c zz_omega = py_obj_to_ZZ_p(omega)
    fft_c(result_vec, coeffs_vec, zz_omega, n)

    result = [None] * n
    for i in range(n):
        result[i] = int(ccrepr(result_vec[i]))

    return result

cpdef fnt_decode_step1(zs, omega, modulus, int n):
    cdef int i, k
    k = len(zs)
    ZZ_p_init(py_obj_to_ZZ(modulus))

    cdef ZZ_pX_c A
    cdef vec_ZZ_p Ad_evals_vec
    cdef vector[int] z_vec
    cdef ZZ_p_c zz_omega = py_obj_to_ZZ_p(omega)

    z_vec.resize(k)
    for i in range(k):
        z_vec[i] = PyInt_AS_LONG(zs[i])

    fnt_decode_step1_c(A, Ad_evals_vec, z_vec, zz_omega, n)

    A_coeffs, Ad_evals = [None] * (k + 1), [None] * k

    cdef ZZ_p_c A_coeff
    for i in range(k + 1):
        ZZ_pX_get_coeff(A_coeff, A, i)
        A_coeffs[i] = int(ccrepr(A_coeff))

    for i in range(k):
        Ad_evals[i] = int(ccrepr(Ad_evals_vec[i]))

    return A_coeffs, Ad_evals

def fft_interpolate(zs, ys, omega, modulus, int n):
    cdef int i
    cdef int k = len(zs)
    cdef vector[int] z_vec;
    cdef vec_ZZ_p y_vec, Ad_evals_vec, P_coeffs
    cdef ZZ_pX_c A
    cdef ZZ_p_c zz_omega

    ZZ_p_init(py_obj_to_ZZ(modulus))
    zz_omega = py_obj_to_ZZ_p(omega)
    z_vec.resize(k)
    for i in range(k):
        z_vec[i] = PyInt_AS_LONG(zs[i])

    y_vec.SetLength(k)
    for i in range(k):
        y_vec[i] = py_obj_to_ZZ_p(ys[i])

    fnt_decode_step1_c(A, Ad_evals_vec, z_vec, zz_omega, n)
    fnt_decode_step2_c(P_coeffs, A, Ad_evals_vec, z_vec, y_vec, zz_omega, n)

    result = [None] * k
    for i in range(k):
        result[i] = int(ccrepr(P_coeffs[i]))
    return result

def fft_batch_interpolate(zs, ys_list, omega, modulus, int n):
    cdef int i, j
    cdef int k = len(zs)
    cdef vector[int] z_vec;
    cdef vec_ZZ_p y_vec, Ad_evals_vec, P_coeffs
    cdef ZZ_pX_c A
    cdef ZZ_p_c zz_omega
    cdef int n_chunks = len(ys_list)

    ZZ_p_init(py_obj_to_ZZ(modulus))
    zz_omega = py_obj_to_ZZ_p(omega)
    z_vec.resize(k)
    for i in range(k):
        z_vec[i] = PyInt_AS_LONG(zs[i])

    fnt_decode_step1_c(A, Ad_evals_vec, z_vec, zz_omega, n)

    cdef vector[vec_ZZ_p] y_vec_list, result_vec_list;
    y_vec_list.resize(n_chunks)
    result_vec_list.resize(n_chunks)

    for i in range(n_chunks):
        y_vec_list[i].SetLength(k)
        for j in range(k):
            y_vec_list[i][j] = py_obj_to_ZZ_p(ys_list[i][j])

    for i in range(n_chunks):
        fnt_decode_step2_c(result_vec_list[i], A, Ad_evals_vec, z_vec, y_vec_list[i],
                           zz_omega, n)

    result = [[None] * k for _ in range(n_chunks)]
    for i in range(n_chunks):
        for j in range(k):
            result[i][j] = int(ccrepr(result_vec_list[i][j]))

    return result

cpdef SetNTLNumThreads(x):
    x = int(x)
    SetNumThreads(x)

cpdef int AvailableNTLThreads():
    return AvailableThreads()

cpdef gao_interpolate(x, y, int k, modulus, z=None, omega=None, order=None,
                      use_fft=False):
    cdef vec_ZZ_p x_vec, y_vec, res_vec, err_vec
    cdef ZZ_p_c zz_omega
    cdef vector[int] z_vec;
    cdef int i, n, int_order
    cdef int success
    assert len(x) == len(y)
    ZZ_p_init(py_obj_to_ZZ(modulus))

    is_null = [yi is None for yi in y]
    x = [x[i] for i in range(len(x)) if not is_null[i]]
    y = [y[i] for i in range(len(y)) if not is_null[i]]
    if z is not None:
        z = [z[i] for i in range(len(z)) if not is_null[i]]

    n = len(x)
    x_vec.SetLength(n)
    y_vec.SetLength(n)

    for i in range(n):
        x_vec[i] = py_obj_to_ZZ_p(x[i])
        y_vec[i] = py_obj_to_ZZ_p(y[i])

    if use_fft is True:
        assert z is not None
        assert len(z) is n
        assert omega is not None

        zz_omega = py_obj_to_ZZ_p(omega)
        int_order = int(order)
        z_vec.resize(n)
        for i in range(n):
            z_vec[i] = int(z[i])

        success = gao_interpolate_fft_c(res_vec, err_vec, x_vec, z_vec, y_vec,
                                        zz_omega, k, n, order)
    else:
        success = gao_interpolate_c(res_vec, err_vec, x_vec, y_vec, k, n)

    if success:
        result = [None] * res_vec.length()
        error_poly = [None] * err_vec.length()

        for i in range(res_vec.length()):
            result[i] = int(ccrepr(res_vec[i]))
        for i in range(err_vec.length()):
            error_poly[i] = int(ccrepr(err_vec[i]))
        return result, error_poly

    return None, None

def sqrt_mod(a, n):
    cdef ZZ_c x
    SqrRootMod(x, py_obj_to_ZZ(a), py_obj_to_ZZ(n))
    return int(ccrepr(x))
