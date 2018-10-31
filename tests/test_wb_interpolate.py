import random

from honeybadgermpc.wb_interpolate import makeEncoderDecoder


def test_decoding():
    integerMessage = [2, 3, 2, 8, 7, 5, 9, 5]
    k = len(integerMessage)  # length of message
    n = 22  # size of encoded message
    p = 53  # prime
    t = k - 1  # degree of polynomial

    enc, dec, solveSystem = makeEncoderDecoder(n, k, p)
    encoded = enc(integerMessage)

    # print("plain message is: %r" % (integerMessage,))
    # print("encoded message is: %r" % (encoded,))  # cleaner output

    # Check decoding with no errors
    decoded = dec(encoded, debug=False)
    assert(decoded == integerMessage)

    # Corrupt with maximum number of erasures:
    cMax = n - 2 * t - 1
    corrupted = corrupt(encoded, numErrors=0, numNones=cMax)
    coeffs = dec(corrupted, debug=False)
    assert coeffs == integerMessage

    # Corrupt with maximum number of errors:
    eMax = (n - 2 * t - 1) // 2
    corrupted = corrupt(encoded, numErrors=eMax, numNones=0)
    coeffs = dec(corrupted, debug=False)
    assert coeffs == integerMessage

    # Corrupt with a mixture of errors and erasures
    e = eMax // 2
    c = cMax // 4
    corrupted = corrupt(encoded, numErrors=e, numNones=c)
    coeffs = dec(corrupted, debug=False)
    assert coeffs == integerMessage


def corrupt(message, numErrors, numNones, minVal=0, maxVal=131):
    """
    Inserts random corrupted values
    """
    message = list.copy(message)
    assert(len(message) >= numErrors +
           numNones), "too much errors and none elements!"
    indices = random.sample(list(range(len(message))), numErrors + numNones)
    for i in range(0, numErrors):
        message[indices[i]] = random.randint(minVal, maxVal)
    for i in range(0, numNones):
        message[indices[i+numErrors]] = None
    return message
