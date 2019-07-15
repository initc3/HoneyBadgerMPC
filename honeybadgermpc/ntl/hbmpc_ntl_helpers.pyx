# Overall, the objective of this NTL-Python interface is to minimize the
# amount of code in C++
# The data validation and checking must be done in python in all cases!
# PEP8 standards are observed wherever possible but ignored in cases whether NTL
# classes are used (like ZZ, mat_ZZ_p, etc) and also for NTL function names
from .ntlwrapper cimport ZZ, ZZ_p, mat_ZZ_p, vec_ZZ_p, ZZ_pX_c
from .ntlwrapper cimport mat_ZZ_p_mul, ZZ_p_init, SqrRootMod
from .ntlwrapper cimport ZZFromBytes, bytesFromZZ, to_ZZ_p, to_ZZ, ZZNumBytes
from .ntlwrapper cimport SetNTLNumThreads_c, AvailableThreads
from .ntlwrapper cimport ZZ_pX_get_coeff, ZZ_pX_set_coeff, ZZ_pX_eval
from .rsdecode cimport OpaqueZZp
from .rsdecode cimport interpolate_c, vandermonde_inverse_c, set_vm_matrix_c, fft_c, fft_partial_c, fnt_decode_step1_c, fnt_decode_step2_c, gao_interpolate_c, gao_interpolate_fft_c
from .rsdecode cimport mat_mul_serialize
from .rsdecode cimport ZZpToOpaqueZZp, OpaqueZZpToZZp, vec_ZZ_pToVecOpaqueZZp, VecOpaqueZZpToVec_ZZ_p, mat_ZZ_pToVecVecOpaqueZZp
from .ccobject cimport ccrepr, ccreadstr
from cpython.int cimport PyInt_AS_LONG
from cython.parallel import parallel, prange
from libc.stdlib cimport free
from libcpp.vector cimport vector
cimport openmp


cdef ZZ intToZZ(x):
    num = (x.bit_length() + 7) // 8
    return ZZFromBytes(x.to_bytes(num, 'little'), num)

cdef ZZToInt(ZZ X):
    cdef int n = ZZNumBytes(X)
    cdef unsigned char*b = bytesFromZZ(X)
    result = int.from_bytes(b[:n], 'little')
    free(b)
    return result

cdef ZZ_p intToZZp(x):
    return to_ZZ_p(intToZZ(x))

cpdef PyIntToOpaqueZZp(x):
    cdef ZZ_p zzp = intToZZp(x)
    cdef OpaqueZZp limbs
    ZZpToOpaqueZZp(limbs, zzp)
    return limbs

cpdef init(modulus):
    ZZ_p_init(py_obj_to_ZZ(modulus))

cpdef OpaqueZZpToPyInt(x):
    cdef ZZ_p zzp
    OpaqueZZpToZZp(zzp, x)
    return ZZpToInt(zzp)

cdef ZZpToInt(ZZ_p X):
    return ZZToInt(to_ZZ(X))

cdef ZZ py_obj_to_ZZ(object v):
    cdef ZZ result
    if isinstance(v, int):
        result = intToZZ(v)
    elif v is not None:
        ccreadstr(result, v)
    else:
        raise ValueError(f"Unsupported data type. {type(v)}")

    return result

cdef ZZ_p py_obj_to_ZZ_p(object v):
    cdef ZZ_p result
    if isinstance(v, int):
        result = intToZZp(v)
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
        result[i] = intToZZp(v[i])
    return result

cdef str ZZ_to_str(ZZ x):
    return ccrepr(x)

cpdef py_matrix_to_ZZ_matrix(x, modulus):
    cdef ZZ zz_modulus = py_obj_to_ZZ(modulus)
    ZZ_p_init(zz_modulus)
    x_matrix = [list(map(PyIntToOpaqueZZp, row)) for row in x]    
    return x_matrix

cpdef ZZ_matrix_to_py_matrix(x):
    return [[OpaqueZZpToPyInt(c) for c in row] for row in x]

cpdef py_list_to_ZZ_list(x, modulus):
    cdef ZZ zz_modulus = py_obj_to_ZZ(modulus)
    ZZ_p_init(zz_modulus)
    return list(map(PyIntToOpaqueZZp, x))

cpdef ZZ_list_to_py_list(row):
    return [OpaqueZZpToPyInt(x) for x in row]

cpdef lagrange_interpolate(x, y, modulus):
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

    cdef vector[ZZ] x_vec;
    cdef vector[ZZ] y_vec;
    cdef vector[ZZ] r_vec;

    for i in range(len(x)):
        x_vec.push_back(py_obj_to_ZZ(x[i]))
        y_vec.push_back(py_obj_to_ZZ(y[i]))

    cdef ZZ zz_modulus = py_obj_to_ZZ(modulus)
    interpolate_c(r_vec, x_vec, y_vec, zz_modulus)

    result = []
    for i in range(r_vec.size()):
        result.append(int(ZZ_to_str(r_vec[i])))
    return result

cpdef evaluate(polynomial, x, modulus):
    """Evaluate polynomial at x"""
    cdef ZZ_pX_c poly
    cdef ZZ_p y
    cdef int i

    ZZ_p_init(py_obj_to_ZZ(modulus))
    poly.SetMaxLength(len(polynomial))
    for i in range(len(polynomial)):
        ZZ_pX_set_coeff(poly, i, intToZZp(polynomial[i]))

    ZZ_pX_eval(y, poly, intToZZp(x))
    return int(ccrepr(y))

cpdef vandermonde_inverse(x, modulus):
    """Generate inverse of vandermonde matrix
    :param x: Evaluation points for polynomial
    :type x: list of integers
    :param modulus: Field modulus
    :type modulus: integers
    :return:
    """
    cdef vector[ZZ] x_vec;

    for xi in x:
        x_vec.push_back(py_obj_to_ZZ(xi))

    cdef ZZ zz_modulus = py_obj_to_ZZ(modulus)
    cdef mat_ZZ_p r
    vandermonde_inverse_c(r, x_vec, zz_modulus)

    return ccrepr(r)


class InterpolationError(Exception):
    pass


cpdef vandermonde_batch_interpolate(x, data_list, modulus):
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
    cdef vector[ZZ] x_vec;

    for xi in x:
        x_vec.push_back(py_obj_to_ZZ(xi))

    cdef ZZ zz_modulus = py_obj_to_ZZ(modulus)
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
            OpaqueZZpToZZp(m[j][i], data_list[i][j])
        for j in range(l, k):
            m[j][i] = intToZZp(0)
    
    cdef vector[vector[OpaqueZZp]] res_vectors
    mat_mul_serialize(res_vectors, r, m)
    m.kill()
    r.kill()
    return res_vectors

cpdef vandermonde_batch_evaluate(x, polynomials, modulus):
    """Evaluate polynomials at given points x using vandermonde matrices
    :param x: evaluation points
    :type x: list of integers
    :param polynomials: polynomial coefficients. polynomials[i] = coefficients of the
        i'th polynomial
    :type polynomials: list of list of integers
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

    cdef ZZ zz_modulus = py_obj_to_ZZ(modulus)
    ZZ_p_init(zz_modulus)

    # Set vm_matrix
    cdef vec_ZZ_p x_vec = py_list_to_vec_ZZ_p(x)
    set_vm_matrix_c(vm_matrix, x_vec, d)

    # Set matrix with polynomial coefficients
    poly_matrix.SetDims(d, k)
    for i in range(k):
        l = len(polynomials[i])
        for j in range(l):
            OpaqueZZpToZZp(poly_matrix[j][i], polynomials[i][j])
        for j in range(l, d):
            poly_matrix[j][i] = intToZZp(0)
    
    cdef vector[vector[OpaqueZZp]] res_vectors
    # Finally multiply matrices. This gives evaluation of polynomials at
    # all points chosen
    mat_mul_serialize(res_vectors, vm_matrix, poly_matrix)
    
    return res_vectors

cpdef fft(coeffs, omega, modulus, int n):
    cdef int i, d;
    cdef vec_ZZ_p coeffs_vec, result_vec;

    ZZ_p_init(intToZZ(modulus))

    d = len(coeffs)
    VecOpaqueZZpToVec_ZZ_p(coeffs_vec, coeffs)

    cdef ZZ_p zz_omega = intToZZp(omega)
    fft_c(result_vec, coeffs_vec, zz_omega, n)

    cdef vector[OpaqueZZp] result;
    vec_ZZ_pToVecOpaqueZZp(result, result_vec)

    return result

cpdef partial_fft(coeffs, omega, modulus, int n, int k):
    cdef int i, d;
    cdef vec_ZZ_p coeffs_vec, result_vec;

    ZZ_p_init(intToZZ(modulus))

    d = len(coeffs)
    VecOpaqueZZpToVec_ZZ_p(coeffs_vec, coeffs)

    cdef ZZ_p zz_omega = intToZZp(omega)
    fft_partial_c(result_vec, coeffs_vec, zz_omega, n, k)

    cdef vector[OpaqueZZp] result;
    vec_ZZ_pToVecOpaqueZZp(result, result_vec)

    return result

cpdef fft_batch_evaluate(coeffs, omega, modulus, int n, int k):
    cdef int i, d;
    cdef vector[vec_ZZ_p] coeffs_vec_list, result_vec_list
    cdef ZZ zz_modulus

    zz_modulus = intToZZ(modulus)
    ZZ_p_init(zz_modulus)

    batch_size = len(coeffs)
    d = len(coeffs[0])

    coeffs_vec_list.resize(batch_size)
    result_vec_list.resize(batch_size)
    for i in range(batch_size):
        VecOpaqueZZpToVec_ZZ_p(coeffs_vec_list[i], coeffs[i])
        
    
    cdef ZZ_p zz_omega = intToZZp(omega)
    with nogil, parallel():
        ZZ_p_init(zz_modulus)
        for i in prange(batch_size):
            fft_partial_c(result_vec_list[i], coeffs_vec_list[i], zz_omega, n, k)

    cdef vector[vector[OpaqueZZp]] res;
    res.resize(batch_size)
    for i in range(batch_size):
        vec_ZZ_pToVecOpaqueZZp(res[i], result_vec_list[i])
    return res
    
def fft_interpolate(zs, ys, omega, modulus, int n):
    cdef int i
    cdef int k = len(zs)
    cdef vector[int] z_vec;
    cdef vec_ZZ_p y_vec, Ad_evals_vec, P_coeffs
    cdef ZZ_pX_c A
    cdef ZZ_p zz_omega

    ZZ_p_init(intToZZ(modulus))
    zz_omega = intToZZp(omega)
    z_vec.resize(k)
    y_vec.SetLength(k)
    for i in range(k):
        z_vec[i] = PyInt_AS_LONG(zs[i])
    VecOpaqueZZpToVec_ZZ_p(y_vec, ys)

    fnt_decode_step1_c(A, Ad_evals_vec, z_vec, zz_omega, n)
    fnt_decode_step2_c(P_coeffs, A, Ad_evals_vec, z_vec, y_vec, zz_omega, n)

    cdef vector[OpaqueZZp] result;
    vec_ZZ_pToVecOpaqueZZp(result, P_coeffs)

    return result

def fft_batch_interpolate(zs, ys_list, omega, modulus, int n):
    cdef int i, j
    cdef int k = len(zs)
    cdef vector[int] z_vec;
    cdef vec_ZZ_p y_vec, Ad_evals_vec, P_coeffs
    cdef ZZ_pX_c A
    cdef ZZ_p zz_omega
    cdef int n_chunks = len(ys_list)
    cdef ZZ zz_modulus
    zz_modulus = intToZZ(modulus)
    ZZ_p_init(intToZZ(modulus))
    zz_omega = intToZZp(omega)
    z_vec.resize(k)
    for i in range(k):
        z_vec[i] = PyInt_AS_LONG(zs[i])

    fnt_decode_step1_c(A, Ad_evals_vec, z_vec, zz_omega, n)

    cdef vector[vec_ZZ_p] y_vec_list, result_vec_list;
    y_vec_list.resize(n_chunks)
    result_vec_list.resize(n_chunks)

    for i in range(n_chunks):
        VecOpaqueZZpToVec_ZZ_p(y_vec_list[i], ys_list[i])

    with nogil, parallel():

        ZZ_p_init(zz_modulus)
        for i in prange(n_chunks):
            fnt_decode_step2_c(result_vec_list[i], A, Ad_evals_vec, z_vec, y_vec_list[i],
                               zz_omega, n)

    cdef vector[vector[OpaqueZZp]] res;
    res.resize(n_chunks)
    for i in range(n_chunks):
        vec_ZZ_pToVecOpaqueZZp(res[i], result_vec_list[i])
    return res
    

cpdef SetNTLNumThreads(int x):
    SetNTLNumThreads_c(x)

cpdef int AvailableNTLThreads():
    return AvailableThreads()

cpdef gao_interpolate(x, y, int k, modulus, z=None, omega=None, order=None,
                      use_omega_powers=False):
    cdef vec_ZZ_p x_vec, y_vec, res_vec, err_vec
    cdef ZZ_p zz_omega
    cdef vector[int] z_vec;
    cdef int i, n, int_order
    cdef int success    
    cdef vector[OpaqueZZp] res_veclimbs, err_veclimbs;
    assert len(x) == len(y)
    ZZ_p_init(intToZZ(modulus))

    is_null = [yi is None for yi in y]
    x = [x[i] for i in range(len(x)) if not is_null[i]]
    y = [y[i] for i in range(len(y)) if not is_null[i]]
    if z is not None:
        z = [z[i] for i in range(len(z)) if not is_null[i]]

    n = len(x)
    x_vec.SetLength(n)

    for i in range(n):
        x_vec[i] = intToZZp(x[i])        
    VecOpaqueZZpToVec_ZZ_p(y_vec, y)

    if use_omega_powers is True:
        assert z is not None
        assert len(z) is n
        assert omega is not None

        zz_omega = intToZZp(omega)
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

        vec_ZZ_pToVecOpaqueZZp(res_veclimbs, res_vec)
        vec_ZZ_pToVecOpaqueZZp(err_veclimbs, err_vec)
        return res_veclimbs, err_veclimbs

    return None, None

def sqrt_mod(a, n):
    cdef ZZ x
    SqrRootMod(x, intToZZ(a), intToZZ(n))
    return int(ccrepr(x))

cpdef SetNumThreads(int n):
    """
    Set threads for both NTL and OpenMP
    :param n: Number of threads
    """
    SetNTLNumThreads(n)
    openmp.omp_set_num_threads(n)

cpdef GetMaxThreads():
    return openmp.omp_get_max_threads()