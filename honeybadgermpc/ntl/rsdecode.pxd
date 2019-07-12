from .ntlwrapper cimport ZZ, mat_ZZ_p, vec_ZZ_p, ZZ_p, ZZ_pX_c, ZZ_limb_t
from libcpp.vector cimport vector
from libcpp cimport bool
from libcpp.string cimport string
cdef extern from "rsdecode_impl.h":
    cdef void interpolate_c "interpolate"(vector[ZZ] r, vector[ZZ] x,
                                          vector[ZZ] y, ZZ modulus)
    cdef bool vandermonde_inverse_c "vandermonde_inverse"(mat_ZZ_p r, vector[ZZ] x,
                                                          ZZ modulus)
    cdef void set_vm_matrix_c "set_vm_matrix"(mat_ZZ_p r, vec_ZZ_p x_list,
                                              int d)
    cdef void fft_c "fft"(vec_ZZ_p r, vec_ZZ_p coeffs, ZZ_p omega, int n)
    cdef void fft_partial_c "fft"(vec_ZZ_p r, vec_ZZ_p coeffs, ZZ_p omega,
                                  int n, int k) nogil
    cdef void fnt_decode_step1_c "fnt_decode_step1"(ZZ_pX_c A_coeffs,
                                                    vec_ZZ_p Ad_evals,
                                                    vector[int] z,
                                                    ZZ_p omega, int n)
    cdef void fnt_decode_step2_c "fnt_decode_step2"(vec_ZZ_p P_coeffs, ZZ_pX_c A_coeffs,
                                                    vec_ZZ_p Ad_evals, vector[int] z,
                                                    vec_ZZ_p ys, ZZ_p omega,
                                                    int n) nogil
    cdef bool gao_interpolate_c "gao_interpolate"(vec_ZZ_p res_vec, vec_ZZ_p err_vec,
                                                  vec_ZZ_p x_vec,
                                                  vec_ZZ_p y_vec, int k, int n)
    cdef bool gao_interpolate_fft_c "gao_interpolate_fft"(vec_ZZ_p res_vec,
                                                          vec_ZZ_p err_vec,
                                                          vec_ZZ_p x_vec,
                                                          vector[int] z,
                                                          vec_ZZ_p y_vec,
                                                          ZZ_p omega,
                                                          int k, int n, int order)
    
    ctypedef string ZZ_limbs

    cdef void mat_mul_serialize "mat_mul_serialize"(vector[vector[ZZ_limbs]] x,  mat_ZZ_p a, mat_ZZ_p b) 

    cdef void ZZ_pToLimbs(ZZ_limbs&l, ZZ_p &x)
    cdef void LimbsToZZ_p(ZZ_p& zzp, ZZ_limbs &r)
    cdef void vec_ZZ_pToVecLimbs(vector[ZZ_limbs] &VecLimbs, vec_ZZ_p &row)
    cdef void VecLimbsToVec_ZZ_p(vec_ZZ_p &veczzp, vector[ZZ_limbs] &serializedRow)
    cdef void mat_ZZ_pToVecVecLimbs(vector[vector[ZZ_limbs]] &vecveclimbs, mat_ZZ_p &a)
    # cdef mat_ZZ_p VecVecLimbsToMat_ZZ_p(vector[vector[ZZ_limbs]] &serializedRows)
