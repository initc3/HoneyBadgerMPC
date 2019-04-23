#ifndef NTL_WRAPPER_CPP
#define NTL_WRAPPER_CPP
#include <NTL/ZZ.h>
#include <NTL/ZZ_p.h>
#include <NTL/ZZ_pX.h>
#include <NTL/mat_ZZ_p.h>
#include <NTL/BasicThreadPool.h>
using namespace NTL;

unsigned char* bytesFromZZ(const ZZ& a) {
   long n = NumBytes(a);
   unsigned char* p = new unsigned char[n];
   BytesFromZZ(p, a, n);
   return p;
}
#endif