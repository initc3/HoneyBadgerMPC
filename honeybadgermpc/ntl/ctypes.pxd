from libcpp.vector cimport vector

cdef extern from "ntlwrapper.h":
    cdef cppclass ZZ_c "ZZ":
        pass

    cdef cppclass ZZ_pContext_c "ZZ_pContext":
        void restore()
        pass

    cdef cppclass ZZ_p_c "ZZ_p":
        pass

    cdef cppclass ZZ_pX_c "ZZ_pX":
        void SetMaxLength(size_t)
        pass

    cdef cppclass vec_ZZ_p:
        ZZ_p_c& operator[](size_t)
        void SetLength(int n)
        void kill()
        size_t length()
    cdef cppclass mat_ZZ_p:
        void SetDims(int m, int n)
        vec_ZZ_p& operator[](size_t)
        void kill()

    void ZZ_p_init "ZZ_p::init"(ZZ_c x)
    void SetNumThreads(int n)
    void ZZ_conv_from_int "conv"(ZZ_c x, int i)
    void ZZ_p_conv_from_int "conv"(ZZ_p_c x, int i)
    void ZZ_conv_to_int "conv"(int i, ZZ_c x)
    void ZZ_conv_from_long "conv"(ZZ_c x, long l)
    void ZZ_conv_to_long "conv"(long l, ZZ_c x)
    void mat_ZZ_p_mul "mul"(mat_ZZ_p x, mat_ZZ_p a, mat_ZZ_p b)
    void mat_ZZ_p_mul_vec "mul"(vec_ZZ_p x, mat_ZZ_p a, vec_ZZ_p b) nogil
    void ZZ_pX_get_coeff "GetCoeff"(ZZ_p_c r, ZZ_pX_c x, int i)
    void ZZ_pX_set_coeff "SetCoeff"(ZZ_pX_c x, int i, ZZ_p_c a)
    void ZZ_pX_eval "eval" (ZZ_p_c b, ZZ_pX_c f, ZZ_p_c a)
    void SqrRootMod "SqrRootMod"(ZZ_c x, ZZ_c a, ZZ_c n)
    int AvailableThreads()
