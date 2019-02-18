#include <NTL/ZZ.h>
#include <NTL/ZZ_p.h>
#include <NTL/ZZ_pX.h>
#include <NTL/vec_ZZ_p.h>
#include <vector>
#include <iostream>

using namespace NTL;
using namespace std;

void interpolate(vector<ZZ> &result, vector<ZZ> &x, vector<ZZ> &y, ZZ &modulus)
{
    // Converting types to what we need
    ZZ_p::init(modulus);
    vec_ZZ_p x_p, y_p;
    x_p.SetLength(x.size());
    y_p.SetLength(y.size());

    for (unsigned int i=0; i < x.size(); i++) {
        x_p[i] = conv<ZZ_p>(x[i]);
    }
    for (unsigned int i=0; i < y.size(); i++) {
        y_p[i] = conv<ZZ_p>(y[i]);
    }

    // Actual interpolation
    ZZ_pX P;
    interpolate(P, x_p, y_p);

    // Converting back to python friendly types
    for (int i=0; i <= deg(P); i++) {
        result.push_back(conv<ZZ>(coeff(P, i)));
    }
}

/*
 * Create a vandermonde based on the values given in x and invert it
 * Result is stored in `result`
 * Return value is whether or not inversion succeeded
 */
bool vandermonde_inverse(mat_ZZ_p &result, vector<ZZ> &x, ZZ &modulus)
{
    ZZ_p::init(modulus);

    // First create vandermonde matrix
    mat_ZZ_p m;
    int n = x.size();

    m.SetDims(n, n);

    for (int i=0; i < n; i++) {
        ZZ_p x_here = conv<ZZ_p>(x[i]);
        ZZ_p y(1);

        for (int j=0; j < n; j++) {
            m[i][j] = y;
            y = y * x_here;
        }
    }

    // Now invert the matrix
    ZZ_p det;
    inv(det, result, m);

    return !IsZero(det);
}

void set_vm_matrix(mat_ZZ_p &result, vec_ZZ_p &x_list, int d, ZZ &modulus)
{
    ZZ_p::init(modulus);
    int n = x_list.length();

    result.SetDims(n, d);
    for (int i=0; i < n; i++) {
        ZZ_p x(1);
        ZZ_p x_here = x_list[i];
        for (int j=0; j < d; j++) {
            result[i][j] = x;
            x = x * x_here;
        }
    }
}

void _fft(ZZ_p *a, ZZ_p *tmp, ZZ_p omega, int n) {
    if (n == 1) {
        return;
    }

    for (int i=0; i < n; i++) {
        tmp[i] = a[i];
    }

    ZZ_p *a0 = a, *a1 = a + n / 2;
    for (int k=0; k < n / 2; k++) {
        a0[k] = tmp[2 * k];
        a1[k] = tmp[2 * k + 1];
    }

    ZZ_p omega2 = omega * omega;

    _fft(a0, tmp, omega2, n / 2);
    _fft(a1, tmp + n / 2, omega2, n / 2);

    for (int i=0; i < n; i++) {
        tmp[i] = a[i];
    }

    ZZ_p w(1);
    ZZ_p *t0 = tmp, *t1 = tmp + n / 2;

    for (unsigned int k=0; k < n / 2; k++) {
        a[k] = t0[k] +  w * t1[k];
        a[k + n / 2] = t0[k] - w * t1[k];
        w = w * omega;
    }
}

void fft(vec_ZZ_p &result, vec_ZZ_p &coeffs, ZZ_p &omega, int n) {
    ZZ_p *a = new ZZ_p[n];
    ZZ_p *tmp = new ZZ_p[n];

    for (unsigned int i=0; i < coeffs.length() && i < n; i++) {
        a[i] = coeffs[i];
    }
    for (int i=coeffs.length(); i < n; i++) {
        a[i] = ZZ_p(0);
    }

    _fft(a, tmp, omega, n);

    result.SetLength(n);
    for (int i=0; i < n; i++) {
        result[i] = a[i];
    }

    delete[] tmp;
    delete[] a;
}

void fnt_decode_step1(ZZ_pX &A, vec_ZZ_p &Ad_evals, vector<int>& zs,
                      ZZ_p &omega, int n) {
    // Build roots xs
    int k = zs.size();
    vec_ZZ_p xs;
    xs.SetLength(k);

    for (int i=0; i < k; i++) {
        power(xs[i], omega, zs[i]);
    }

    // Build polynomial A
    BuildFromRoots(A, xs);

    int d = deg(A);
    // Differentiate polynomial A
    vec_ZZ_p Ad_coeffs;
    Ad_coeffs.SetLength(d);
    for (int i=0; i < d; i++) {
        Ad_coeffs[i] = (i + 1) * coeff(A, i + 1);
    }

    // Evaluate derivative at x0, x1, ..., x_(n-1). Then cherry pick ones present in zs
    vec_ZZ_p Ad_evals_all;
    fft(Ad_evals_all, Ad_coeffs, omega, n);

    Ad_evals.SetLength(k);
    for (int i=0; i < k; i++) {
        Ad_evals[i] = Ad_evals_all[zs[i]];
    }
}

void fnt_decode_step2(vec_ZZ_p &P_coeffs, ZZ_pX &A, vec_ZZ_p &Ad_evals,
                      vector<int> &zs, vec_ZZ_p& ys, ZZ_p &omega, int n) {
    int k = zs.size();

    // Prep for building N
    vec_ZZ_p nis;
    nis.SetLength(k);
    for (int i=0; i < k; i++) {
        div(nis[i], ys[i], Ad_evals[i]);
    }

    // Build N
    vec_ZZ_p N_coeffs;
    N_coeffs.SetLength(n);
    for (int i=0; i < n; i++) {
       N_coeffs[i] = 0;
    }

    for (int i=0; i < k; i++) {
        N_coeffs[zs[i]] = nis[i];
    }

    // Build Q = P / A
    vec_ZZ_p N_rev_evals;
    fft(N_rev_evals, N_coeffs, omega, n);

    ZZ_pX Q;
    Q.SetMaxLength(n);
    for (int i=0; i < n; i++) {
        SetCoeff(Q, i, -N_rev_evals[n - i - 1]);
    }

    ZZ_pX P;
    mul(P, Q, A);

    P_coeffs.SetLength(k);
    for (int i=0; i < k; i++) {
        P_coeffs[i] = coeff(P, i);
    }
}

void partial_gcd(ZZ_pX &r, ZZ_pX &u, ZZ_pX &v, ZZ_pX &p0, ZZ_pX &p1, int threshold)
{
    ZZ_pX r0, r1, r2, s0, s1, s2, t0, t1, t2;
    r0 = p0;
    r1 = p1;
    SetCoeff(s0, 0, 1);
    SetCoeff(t1, 0, 1);

    if (deg(r0) < threshold) {
        r = r0;
        u = s0;
        v = t0;
        return;
    }

    if (deg(r1) < threshold) {
        r = r1;
        u = s1;
        v = t1;
        return;
    }

    while (true) {
        ZZ_pX q;
        DivRem(q, r2, r0, r1);
        s2 = s0 - q * s1;
        t2 = t0 - q * t1;

        if (deg(r2) < threshold) {
            r = r2;
            u = s2;
            v = t2;
            return;
        }

        r0 = r1;
        r1 = r2;
        s0 = s1;
        s1 = s2;
        t0 = t1;
        t1 = t2;
    }
}

bool gao_interpolate(vec_ZZ_p &res_vec, vec_ZZ_p &err_vec,
                     vec_ZZ_p &x_vec, vec_ZZ_p &y_vec, int k, int n)
{
    // Step 0: Compute g0(x) = (x - x0) * (x - x1) ... (x - x_{n-1})
    ZZ_pX g0;
    BuildFromRoots(g0, x_vec);

    // Step 1: Interpolate g1(x) s.t g1(xi) = yi
    ZZ_pX g1;
    interpolate(g1, x_vec, y_vec);

    // Step 2: Partial GCD
    ZZ_pX g, u, v;
    partial_gcd(g, u, v, g0, g1, (n + k) / 2);

    // Step 3: Long division of g(x) / s(x)
    ZZ_pX r, f1;

    DivRem(f1, r, g, v);

    // If r(x) = 0 and degree of f1 is less than k, then decoding is successful
    // Else decoding failed
    if (!IsZero(r) || deg(f1) >= k) {
        return false;
    }

    res_vec.SetLength(k);
    for (int i=0; i < k; i++) {
        res_vec[i] = coeff(f1, i);
    }

    int num_errors = deg(v);
    err_vec.SetLength(num_errors + 1);
    for (int i=0; i < num_errors + 1; i++) {
        err_vec[i] = coeff(v, i);
    }

    return true;
}