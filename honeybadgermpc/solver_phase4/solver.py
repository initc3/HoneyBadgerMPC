from lib_solver import ffi, lib
import sys
import time
start = 0


def record_start():
    global start
    start = time.time()
    print("*" * 64)
    print("timer Started")


def record_stop():
    global start
    stop = time.time()
    print("Total time used: %.3f sec" % (stop - start))
    start = stop
    print("*" * 64)


def _int2hexbytes(n):
    return bytes(hex(n), 'ascii')[2:]


P = 115792089237316195423570985008687907853269984665640564039457584007913129640423
_HEX_P = _int2hexbytes(P)

_C_RET_INVALID = 1
_C_RET_INTERNAL_ERROR = 100
_C_RET_INPUT_ERROR = 101


def solve(dc_sums):
    """Solve function from protocol specification.

    Solves the equation system
    forall 0 <= i < size(dc_sums).
    sum_{j=0}^{size(dc_sums)-1)} messages[j]^{i+1} = dc_sums[i]
    in the finite prime field F_P for messages, and checks if my_message is in the
    solution.
    Assumes that size(dc_sums) >= 2.
    Returns a list of messages as solution (sorted in ascending numerial order) 
    in case of success.
    Returns None if dc_sums is not a proper list of power sums, or if my_message is
     not a solution.
    """
    ffi_sums = [ffi.new('char[]', _int2hexbytes(s)) for s in dc_sums]
    # Allocate result buffers (size of P in hex + 1 null char)
    ffi_messages = [ffi.new('char[]', len(_HEX_P) + 1) for _ in dc_sums]

    res = lib.solve(ffi_messages, _HEX_P, ffi_sums, len(dc_sums))

    if res == 0:
        return [int(ffi.string(m), 16) for m in ffi_messages]
    elif res == _C_RET_INVALID:
        return None
    elif res == _C_RET_INPUT_ERROR:
        raise ValueError
    else:
        raise RuntimeError


def load_input_from_file(id, batch):
    result = []
    for b in range(batch):
        filename = "party" + str(id)
        filename = filename + + "-powermixing-online-phase3-output-batch" + str(b + 1)
        FD = open(filename, "r")
        line = FD.readline()

        line = FD.readline()
        k = int(line)
        inputs = [0 for _ in range(k)]
        line = FD.readline()
        i = 0
        while line and i < k:

            inputs[i] = int(line)

            line = FD.readline()
            i = i + 1
        result.append(inputs)
    return result


def create_output(result, party_id, batch):
    filename = "party" + str(party_id) + "-finaloutput-batch" + str(batch + 1)
    FD = open(filename, "w")
    content = ""
    for share in result:
        content = content + str(share) + "\n"
    FD.write(content)
    FD.close()


if __name__ == "__main__":
    print("begin phase 4")
    record_start()
    party_id = sys.argv[1]
    batch = int(sys.argv[2])
    inputs = load_input_from_file(party_id, batch)
    print("load input complete")
    record_stop()
    for i in range(batch):
        result = solve(inputs[i])
        if result is not None:
            print("calculation complete")
            create_output(result, party_id, i)
        else:
            print("input error,skip")
    record_stop()
    print("output to file complete")
    record_stop()
