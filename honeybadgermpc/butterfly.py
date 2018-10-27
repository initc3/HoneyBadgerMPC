import asyncio
from field import GF
from polynomial import polynomialsOver
from router import simple_router
import math
import sys
import os
from passive import PassiveMpc, generate_test_zeros, generate_test_triples


#######################
# Generating test files
#######################

# Fix the field for now
Field = GF(115792089237316195423570985008687907853269984665640564039457584007913129640423)
Poly = polynomialsOver(Field)


async def beaver_mult(context, x, y, a, b, ab):
    D = await (x - a).open()
    E = await (y - b).open()

# This is a random share of x*y
    xy = context.Share(D*E) + D*b + E*a + ab

    return context.Share(await xy.open())



async def butterfly_network(context):
    k = 128
    delta = 6
    random_shares = [0 for i in range(k * int(math.log(k, 2)))]
    inputs = [0 for i in range(k)]
    p = 115792089237316195423570985008687907853269984665640564039457584007913129640423
    Zp = GF(p)
    filename = 'sharedata/test_triples-%d.share' % (context.myid,)
    triples = iter(context.read_shares(open(filename)))
    trigger = [1]

# ----------------------------------------------------------------------------
    def get_triple():
        a = next(triples)
        b = next(triples)
        ab = next(triples)
        return a, b, ab
# ----------------------------------------------------------------------------
    def mul(x, y):
        a, b, ab = get_triple()
        return beaver_mult(context, x, y, a, b, ab)
# ----------------------------------------------------------------------------
    print("begin allocating input shares")
    filename = 'sharedata/test_zeros-%d.share' % (context.myid,)
    zeros = context.read_shares(open(filename))
    for i in range(k):
        inputs[i] = zeros[i] + context.Share(i)

# ----------------------------------------------------------------------------
    def load_from_file(k, p):
        filename = "party" + str(context.myid + 1) + "_butterfly_random_share"
        FD = open(filename, "r")
        line = FD.readline()
        if int(line) != k:
            print("k dismatch!! k in file is %d" % (int(line)))
        line = FD.readline()
        if int(line) != p:
            print("prime dismatch!! prime in file is %d" % (int(line)))

        line = FD.readline()
        i = 0
        while line and i < k * int(math.log(k, 2)):
            random_shares[i] = context.Share(int(line))

            line = FD.readline()
            i = i + 1
# ----------------------------------------------------------------------------
    load_from_file(k, p)
# ----------------------------------------------------------------------------

    async def switch(input1, input2):
        select_bit = random_shares.pop()
        m = (await mul(select_bit, (input1 - input2)))
        n = 1 / Zp(2)

        output1 = context.Share(n.value * (input1 + input2 + m).v)
        output2 = context.Share(n.value * (input1 + input2 - m).v)

        return output1, output2

    def write_share_to_file(shares):

        filename = "party" + str(context.myid + 1) + "_butterfly_online_batch" + str(len(trigger))
        FD = open(filename, "w")
        content = str(len(shares)) + "\n" + str(p) + "\n"
        for share in shares:
            content = content + str(share.v)[1:-1] + "\n"
        FD.write(content)
        FD.close()
        trigger.append(1)
        if len(trigger) == 2 ** (int(math.log(k, 2)) - delta) + 1:
            print("time to shutdown")
            #os._exit(0)
        

    async def permutation_network(input, num, level=0):
        
        if level == int(math.log(k, 2)) - delta:
            write_share_to_file(input)

            return None
        if level > int(math.log(k, 2)) - delta:
            return None
        if num == 2:
            temp1, temp2 = await switch(input[0], input[1])
            result = [temp1, temp2]
            return result
        else:
            first_layer_output1 = []
            first_layer_output2 = []
            result = []
            for i in range(int(num/2)):
                temp1, temp2 = await switch(input[i * 2], input[i * 2 + 1])
                first_layer_output1.append(temp1)
                first_layer_output2.append(temp2)

            second_layer_output1 = await permutation_network(first_layer_output1, num/2, level + 1)
            second_layer_output2 = await permutation_network(first_layer_output2, num/2, level + 1)
            if second_layer_output1 is None or second_layer_output2 is None:
                return None

            for i in range(int(num/2)):
                temp1, temp2 = await switch(second_layer_output1[i], second_layer_output2[i])
                result.append(temp1)
                result.append(temp2)

            return result
# ----------------------------------------------------------------------------

    output = await permutation_network(inputs, k)
    print("shuffle done")

    if delta == 0:
        open_tx = [0 for i in range(k)]
        for i in range(k):
            open_tx[i] = await (output[i]).open()
        list = [open_tx[i] for i in range(k)]
        print(list)


async def runProgramInNetwork(program, N, t):
    loop = asyncio.get_event_loop()
    sends, recvs = simple_router(N)

    tasks = []

    for i in range(N):
        context = PassiveMpc('sid', N, t, i, sends[i], recvs[i], program)
        tasks.append(loop.create_task(context._run()))

    results = await asyncio.gather(*tasks)
    return results


# Run some test cases
if __name__ == '__main__':
    print('Generating random shares of zero in sharedata/')
    generate_test_zeros('sharedata/test_zeros', 1000, 3, 2)
    print('Generating random shares of triples in sharedata/')
    generate_test_triples('sharedata/test_triples', 1000, 3, 2)

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        loop.run_until_complete(runProgramInNetwork(butterfly_network, 3, 2))

    finally:
        loop.close()

