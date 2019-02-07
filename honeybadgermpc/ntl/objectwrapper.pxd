# Code ot help help python objects to C++ objects
cdef extern from "ccobject.h":
    # Print representation of any C++ object
    str ccrepr[T](T x)

    # Read a Python bytes/str into a C++ object
    int ccreadstr[T](T x, object b) except -1
