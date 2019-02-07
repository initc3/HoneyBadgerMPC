from .ctypes cimport ZZ_c, mat_ZZ_p, vec_ZZ_p, ZZ_p_c, ZZ_pX_c
from libcpp.vector cimport vector
from libcpp cimport bool

cdef extern from "helpers.h":
    cdef void interpolate_c "interpolate"(vector[ZZ_c] r, vector[ZZ_c] x,
                                          vector[ZZ_c] y, ZZ_c modulus)
    cdef bool vandermonde_inverse_c "vandermonde_inverse"(mat_ZZ_p r, vector[ZZ_c] x,
                                                          ZZ_c modulus)
    cdef void set_vm_matrix_c "set_vm_matrix"(mat_ZZ_p r, vec_ZZ_p x_list,
                                              int d, ZZ_c modulus)
    cdef void fft_c "fft"(vec_ZZ_p r, vec_ZZ_p coeffs, ZZ_p_c omega, int n)
    cdef void fnt_decode_step1_c "fnt_decode_step1"(ZZ_pX_c A_coeffs,
                                                    vec_ZZ_p Ad_evals,
                                                    vector[int] z, ZZ_p_c omega, int n)
    cdef void fnt_decode_step2_c "fnt_decode_step2"(vec_ZZ_p P_coeffs, ZZ_pX_c A_coeffs,
                                                    vec_ZZ_p Ad_evals, vector[int] z,
                                                    vec_ZZ_p ys, ZZ_p_c omega,
                                                    int n) nogil
