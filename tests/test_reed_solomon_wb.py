import random
from honeybadgermpc.reed_solomon_wb import make_wb_encoder_decoder


def test_decoding():
    int_msg = [2, 3, 2, 8, 7, 5, 9, 5]
    k = len(int_msg)  # length of message
    n = 22  # size of encoded message
    p = 53  # prime
    t = k - 1  # degree of polynomial

    enc, dec, _ = make_wb_encoder_decoder(n, k, p)
    encoded = enc(int_msg)

    # Check decoding with no errors
    decoded = dec(encoded, debug=False)
    assert decoded == int_msg

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


def test_decoding_all_zeros():
    int_msg = [0, 0, 0, 0, 0, 0, 0, 0]
    k = len(int_msg)  # length of message
    n = 22  # size of encoded message
    p = 53  # prime
    t = k - 1  # degree of polynomial

    enc, dec, _ = make_wb_encoder_decoder(n, k, p)
    encoded = enc(int_msg)

    # Check decoding with no errors
    # https://github.com/initc3/HoneyBadgerMPC/issues/143
    # If an error is raised then the bug has not been fixed D:
    _ = dec(encoded, debug=False)

    # Corrupt with maximum number of erasures:
    cmax = n - 2 * t - 1

    corrupted = corrupt(encoded, num_errors=0, num_nones=cmax)
    _ = dec(corrupted, debug=False)

    # Corrupt with maximum number of errors:
    emax = (n - 2 * t - 1) // 2
    corrupted = corrupt(encoded, num_errors=emax, num_nones=0)
    coeffs = dec(corrupted, debug=False)

    # This also showcases inconsistency in polynomial functions
    # poly([]) should be equal to poly([0])
    assert coeffs == []

    # Corrupt with a mixture of errors and erasures
    e = emax // 2
    c = cmax // 4
    corrupted = corrupt(encoded, num_errors=e, num_nones=c)
    coeffs = dec(corrupted, debug=False)
    assert coeffs == []


def corrupt(message, num_errors, num_nones, min_val=0, max_val=131):
    """
    Inserts random corrupted values
    """
    message = list.copy(message)
    assert len(message) >= num_errors + num_nones, "too much errors and none elements!"
    indices = random.sample(list(range(len(message))), num_errors + num_nones)
    for i in range(0, num_errors):
        message[indices[i]] = random.randint(min_val, max_val)
    for i in range(0, num_nones):
        message[indices[i + num_errors]] = None
    return message
