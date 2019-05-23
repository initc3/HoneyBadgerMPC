#include <vector>
#include <algorithm>
#include <cstring>

#include <flint/flint.h>
#include <flint/fmpz.h>
#include <flint/fmpz_mod_polyxx.h>

using namespace std;
using namespace flint;

#define RET_INVALID           1
#define RET_INTERNAL_ERROR  100
#define RET_INPUT_ERROR     101

int solve_impl(vector<fmpzxx>& messages, const fmpzxx& p,  const vector<fmpzxx>& sums) {
    vector<fmpzxx>::size_type n = sums.size();
    if (n < 2) {
#ifdef DEBUG
        cout << "Input vector too short." << endl;
#endif
        return RET_INPUT_ERROR;
    }

    // Basic sanity check to avoid weird inputs
    if (n > 4097) {
#ifdef DEBUG
        cout << "You probably do not want an input vector of more than 1000 elements. " << endl;
#endif
        return RET_INPUT_ERROR;
    }

    if (messages.size() != sums.size()) {
#ifdef DEBUG
        cout << "Output vector has wrong size." << endl;
#endif
        return RET_INPUT_ERROR;
    }

    if (p <= n) {
#ifdef DEBUG
        cout << "Prime must be (way) larger than the size of the input vector." << endl;
#endif
        return RET_INPUT_ERROR;
    }

    fmpz_mod_polyxx poly(p);
    fmpz_mod_poly_factorxx factors;
    factors.fit_length(n);
    vector<fmpzxx> coeff(n);

    // Set lead coefficient
    poly.set_coeff(n, 1);

    fmpzxx inv;
    // Compute other coeffients
    for (vector<fmpzxx>::size_type i = 0; i < n; i++) {
        coeff[i] = sums[i];

        vector<fmpzxx>::size_type k = 0;
        // for j = i-1, ..., 0
        for (vector<fmpzxx>::size_type j = i; j-- > 0 ;) {
            coeff[i] += coeff[k] * sums[j];
            k++;
        }
        inv = i;
        inv = -(inv + 1u);
        inv = inv.invmod(p);
        coeff[i] *= inv;
        poly.set_coeff(n - i - 1, coeff[i]);
    }

#ifdef DEBUG
    cout << "Polynomial: " << endl; print(poly); cout << endl << endl;
#endif

    // Check if our message is a root

    // Factor
    factors.set_factor_kaltofen_shoup(poly);

#ifdef DEBUG
    cout << "Factors: " << endl; print(factors); cout << endl << endl;
#endif

    vector<fmpzxx>::size_type n_roots = 0;
    for (int i = 0; i < factors.size(); i++) {
        if (factors.p(i).degree() != 1 || factors.p(i).lead() != 1) {
#ifdef DEBUG
            cout << "Non-monic factor." << endl;
#endif
            return RET_INVALID;
        }
        n_roots += factors.exp(i);
    }
    if (n_roots != n) {
#ifdef DEBUG
        cout << "Not enough roots." << endl;
#endif
        return RET_INVALID;
    }

    // Extract roots
    int k = 0;

    for (int i = 0; i < factors.size(); i++) {
        for (int j = 0; j < factors.exp(i); j++) {
            messages[k] = factors.p(i).get_coeff(0).negmod(p);

            k++;
        }
    }

    // Sanity check


    sort(messages.begin(), messages.end());

    return 0;
}

int main(int argc, char* argv[])
{
    fmpzxx p;
    p.read();

    vector<fmpzxx>::size_type n;
    cin >> n;

    vector<fmpzxx> s(n);
    vector<fmpzxx> messages(n);


    for (vector<fmpzxx>::iterator it = s.begin(); it != s.end(); it++) {
        it->read();
    }

    int ret = solve_impl(messages, p, s);

    if (ret == 0) {
        cout << "Messages:" << endl << "[";
        for (vector<fmpzxx>::iterator it = messages.begin(); it != messages.end(); it++) {
            cout << *it << ", ";
        }
        cout << "]" << endl;
    }

    return ret;
}

/**
 * Solve function from protocol specification.
 *
 * Solves the equation system
 *   forall 0 <= i < n. sum_{j=0}^{n-1} messages[j]^{i+1} = sums[i]
 * in the finite prime field F_prime for messages[], and checks if my_message is in the solution.
 *
 * \param[out] out_messages    Array of n char buffers (allocated by caller) of length at least strlen(prime) + 1
 * \param[in]  prime           Prime of the finite field (not checked for primality)
 * \param[in]  my_message      Our own message
 * \param[in]  sums            Array of n power sums
 * \param[in]  n               Number of peers, must be at least 2 and not larger than prime
 *
 * \retval 0                   Success, the solution vector is stored as hexadecimal strings in messages[],
 *                             sorted in ascending numerical order.
 * \retval RET_INVALID         sums is not a proper array of power sums or my_message is not in the solution.
 * \retval RET_INPUT_ERROR     Illegal input values.
 * \retval RET_INTERNAL_ERROR  An internal error occured.
 */
extern "C" int solve(char* out_messages[], const char* prime,  const char* sums[], size_t n) {
    // Exceptions should never propagate to C (undefined behavior).
    try {
        fmpzxx p;


        vector<fmpzxx> s(n);
        vector<fmpzxx> messages(n);

        // operator= is hard-coded to base 10 and does not check for errors
        if (fmpz_set_str(p._fmpz(), prime, 16)) {
            return RET_INPUT_ERROR;
        }



        for (size_t i = 0; i < n; i++) {
            if (fmpz_set_str(s[i]._fmpz(), sums[i], 16)) {
                return RET_INPUT_ERROR;
            }
        }

        for (size_t i = 0; i < n; i++) {
            if (out_messages[i] == NULL) {
                return RET_INPUT_ERROR;
            }
        }

        int ret = solve_impl(messages, p, s);

        if (ret == 0) {
            for (size_t i = 0; i < n; i++) {
                // Impossible
                if (messages[i].sizeinbase(16) > strlen(prime)) {
                    return RET_INTERNAL_ERROR;
                }
                fmpz_get_str(out_messages[i], 16, messages[i]._fmpz());
            }
        }

        return ret;
    } catch (...) {
        return RET_INTERNAL_ERROR;
    }
}
