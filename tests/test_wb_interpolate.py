import random

from honeybadgermpc.wb_interpolate import makeEncoderDecoder, decoding_message_with_none_elements
from honeybadgermpc.field import GF
from honeybadgermpc.polynomial import polynomialsOver


def test_decoding():
    integerMessage = [2, 3, 2, 8, 7, 5, 9, 5]
    k = len(integerMessage)  # length of message
    n = 22  # size of encoded message
    p = 23  # prime

    enc, dec, solveSystem = makeEncoderDecoder(n, k, p)
    encoded = enc(integerMessage)

    print("plain message is: %r" % (integerMessage,))
    print("encoded message is: %r" % (encoded,))  # cleaner output

    corrupted = corrupt(encoded, k-1, 0)
    print("corrupted message is: %r" % (corrupted,))

    Q, E = solveSystem(corrupted, False)
    P, remainder = (Q.__divmod__(E))

    print("P(x) = %r" % P)
    print("r(x) = %r" % remainder)
    Fp = GF(p)
    Poly = polynomialsOver(Fp)
    original_poly = Poly(integerMessage)
    assert(
        (original_poly - P).isZero()), "Decoded message does not match original message!"


def test_decoding_message_with_none_elements():
    integerMessage = [2, 3, 2, 8, 7, 5, 9, 5]
    k = len(integerMessage)  # length of message
    n = 22  # size of encoded message
    p = 23  # prime

    enc, _, _ = makeEncoderDecoder(n, k, p)
    encoded = enc(integerMessage)

    print("plain message is: %r" % (integerMessage,))
    print("encoded message is: %r" % (encoded,))  # cleaner output

    corrupted = corrupt(encoded, k-5, 3)
    print("corrupted message is: %r" % (corrupted,))
    solved, P = decoding_message_with_none_elements(k-1, corrupted, p)
    assert(solved), "Decoding failed"
    Fp = GF(p)
    Poly = polynomialsOver(Fp)
    original_poly = Poly(integerMessage)
    assert(
        (original_poly - P).isZero()), "Decoded message does not match original message!"
    return


def corrupt(message, numErrors, numNones, minVal=0, maxVal=131):
    assert(len(message) >= numErrors + numNones), "too much errors and none elements!"
    indices = random.sample(list(range(len(message))), numErrors + numNones)
    for i in range(0, numErrors):
        message[indices[i]][1] = random.randint(minVal, maxVal)
    for i in range(0, numNones):
        message[indices[i+numErrors]][1] = None
    return message


test_decoding()
print("test_decoding_pass!!!!")
test_decoding_message_with_none_elements()
