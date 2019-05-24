// Copyright (C) 2005-2017 The Sage Development Team
// Creating a Viable Open Source Alternative to Magma, Maple, Mathematica, and MATLAB
// https://github.com/sagemath/sage/blob/854f9764d14236110b8d7f7b35a7d52017e044f8/src/sage/ext/ccobject.h

#ifndef __CCOBJECT_H__
#define __CCOBJECT_H__

#ifdef __cplusplus

#include <iostream>
#include <sstream>


template <class T>
static CYTHON_INLINE int ccreadstr(T& x, PyObject* b)
{
    PyObject* converted = NULL;

#if PY_MAJOR_VERSION >= 3
    // Accept "str" input on Python 3
    if (PyUnicode_Check(b))
    {
        converted = PyUnicode_EncodeFSDefault(b);
        if (!converted) {return -1;}
        b = converted;
    }
#endif

    char* buffer;
    Py_ssize_t length;

    if (PyBytes_AsStringAndSize(b, &buffer, &length) == -1)
        {Py_XDECREF(converted); return -1;}
    std::istringstream input(std::string(buffer, length));
    Py_XDECREF(converted);

    input >> x;

    return 0;
}


template <class T>
static CYTHON_INLINE PyObject* ccrepr(const T& x)
{
    std::ostringstream instore;
    instore << x;
    std::string instr = instore.str();
#if PY_MAJOR_VERSION <= 2
    return PyString_FromStringAndSize(instr.c_str(), instr.size());
#else
    return PyUnicode_DecodeFSDefaultAndSize(instr.c_str(), instr.size());
#endif
}

#endif

#endif /* ifndef __CCOBJECT_H__ */