import random

from honeybadgermpc.wb_interpolate import make_encoder_decoder


def test_decoding():
    int_msg = [2, 3, 2, 8, 7, 5, 9, 5]
    k = len(int_msg)  # length of message
    n = 22  # size of encoded message
    p = 53  # prime
    t = k - 1  # degree of polynomial

    enc, dec, _ = make_encoder_decoder(n, k, p)
    encoded = enc(int_msg)

    # print("plain message is: %r" % (integerMessage,))
    # print("encoded message is: %r" % (encoded,))  # cleaner output

    # Check decoding with no errors
    decoded = dec(encoded, debug=False)
    assert (decoded == int_msg)

    # Corrupt with maximum number of erasures:
    cmax = n - 2 * t - 1
    corrupted = corrupt(encoded, num_errors=0, num_nones=cmax)
    coeffs = dec(corrupted, debug=False)
    assert coeffs == int_msg

    # Corrupt with maximum number of errors:
    emax = (n - 2 * t - 1) // 2
    corrupted = corrupt(encoded, num_errors=emax, num_nones=0)
    coeffs = dec(corrupted, debug=False)
    assert coeffs == int_msg

    # Corrupt with a mixture of errors and erasures
    e = emax // 2
    c = cmax // 4
    corrupted = corrupt(encoded, num_errors=e, num_nones=c)
    coeffs = dec(corrupted, debug=False)
    assert coeffs == int_msg


def corrupt(message, num_errors, num_nones, min_val=0, max_val=131):
    """
    Inserts random corrupted values
    """
    message = list.copy(message)
    assert (len(message) >= num_errors +
            num_nones), "too much errors and none elements!"
    indices = random.sample(list(range(len(message))), num_errors + num_nones)
    for i in range(0, num_errors):
        message[indices[i]] = random.randint(min_val, max_val)
    for i in range(0, num_nones):
        message[indices[i + num_errors]] = None
    return message
