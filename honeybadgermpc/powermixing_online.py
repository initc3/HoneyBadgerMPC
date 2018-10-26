import asyncio
from asyncio import Future
from field import GF, GFElement
from polynomial import polynomialsOver
from router import simple_router
import random
import math
import sys
import os
from passive import PassiveMpc, shareInContext, generate_test_zeros, generate_test_triples, write_shares

class NotEnoughShares(Exception):
    pass




#######################
# Generating test files
#######################

# Fix the field for now
Field = GF(115792089237316195423570985008687907853269984665640564039457584007913129640423)
Poly = polynomialsOver(Field)


def write_polys(prefix, modulus, N, t, polys):
    for i in range(N):
        shares = [f(i+1) for f in polys]
        with open('%s-%d.share' % (prefix, i), 'w') as f:
            write_shares(f, modulus, t, i, shares)


def generate_test_triples(prefix, k, N, t):
    # Generate k triples, store in files of form "prefix-%d.share"
    polys = []
    for j in range(k):
        a = Field(random.randint(0, Field.modulus-1))
        b = Field(random.randint(0, Field.modulus-1))
        c = a*b
        polys.append(Poly.random(t, a))
        polys.append(Poly.random(t, b))
        polys.append(Poly.random(t, c))
    write_polys(prefix, Field.modulus, N, t, polys)


def generate_test_zeros(prefix, k, N, t):
    polys = []
    for j in range(k):
        polys.append(Poly.random(t, 0))
    write_polys(prefix, Field.modulus, N, t, polys)


def generate_test_randoms(prefix, k, N, t):
    polys = []
    for j in range(k):
        polys.append(Poly.random(t, random.randint(0, Field.modulus-1)))
    write_polys(prefix, Field.modulus, N, t, polys)


async def beaver_mult(context, x, y, a, b, ab):
    D = await (x - a).open()
    E = await (y - b).open()

    # This is a random share of x*y
    xy = context.Share(D*E) + D*b + E*a + ab

    return context.Share(await xy.open())

async def butterfly_network(context):
    #----------------------------------------------------------------------------
    def mul(x, y):
        a, b, ab = context.get_triple()
        return beaver_mult(context, x, y, a, b, ab)
    #----------------------------------------------------------------------------
    k = 128
    delta = 0
    ramdom_shares = [0 for i in range(k * int(math.log(k,2)))]
    inputs = [0 for i in range(k)]
    p = 115792089237316195423570985008687907853269984665640564039457584007913129640423
    Zp = GF(p)
    write_index = 1
    print("begin allocating input shares")
    for i in range(k):
        inputs[i] = context.get_zero() + context.Share(i)

    #----------------------------------------------------------------------------
    def load_from_file(k,p):
        filename = "party" + str(context.myid+1) + "_butterfly_random_share"
    
        FD = open(filename, "r")
        line = FD.readline()
        if int(line) != k:
            print("k dismatch!! k in file is %d"%(int(line)))
        line = FD.readline()
        if int(line) != p:
            print("prime dismatch!! prime in file is %d"%(int(line)) )


        line = FD.readline()
        i = 0
        while line:
            #print i
            ramdom_shares[i] = context.Share(int(line))

            line = FD.readline()  
            i = i + 1
    #----------------------------------------------------------------------------
    load_from_file(k,p)
    #----------------------------------------------------------------------------
    async def switch(input1,input2):

        select_bit = ramdom_shares.pop()

        #print((input1 - input2).v)
        #print(select_bit.v)

        m =(await mul(select_bit , (input1 - input2)))
        n = 1/Zp(2) 

        output1 = context.Share(n.value * (input1 + input2 + m).v)
        output2 = context.Share(n.value * (input1 + input2 - m).v)
        #output1 = n *(input1 + input2 + m)
        #output2 = n *(input1 + input2 - m)

        return output1,output2  

    async def permutation_network(input,num,level = 0):

        #print("new layer%d"%(level))
        if level == int(math.log(k,2)) - delta:
            return None
            # result = gather_shares(input)
            # result.addCallback(self.write_share_to_file,input)
        if level > int(math.log(k,2)) - delta:
            #print "pls shutdown"
            return None
        if num ==2:     
            temp1,temp2 =await switch(input[0],input[1])        
            result =  [temp1,temp2]
            return result   
        else:   
            first_layer_output1 = []
            first_layer_output2 = []
            result = []
            for i in range(int(num/2)):
                temp1,temp2 =await switch(input[i * 2],input[i * 2 + 1])
                first_layer_output1.append(temp1)
                first_layer_output2.append(temp2)

            second_layer_output1 = await permutation_network(first_layer_output1,num/2,level + 1)
            second_layer_output2 = await permutation_network(first_layer_output2,num/2,level + 1)
            if second_layer_output1 == None or second_layer_output2 == None:
                return None
                        
            for i in range(int(num/2)):
                temp1,temp2 =await switch(second_layer_output1[i],second_layer_output2[i])
                result.append(temp1)
                result.append(temp2)            

            return result
    #----------------------------------------------------------------------------
    output = await permutation_network(inputs,k)
    print("shuffle done")

    if delta == 0:
        open_tx = [0 for i in range(k)]
        for i in range(k):
            open_tx[i] = await (output[i]).open()
        list = [open_tx[i] for i in range(k)] 
        print(list)





async def powermix_phase1(context):
    
    k = 32
    batch = 1
    inputs = [[0 for _ in range(k)] for _ in range(batch)]
    inputs_debug = [[0 for _ in range(k)] for _ in range(batch)]
    p = 115792089237316195423570985008687907853269984665640564039457584007913129640423
    Zp = GF(p)
    a_minus_b = [[0 for _ in range(k)] for _ in range(batch)]
    precomputed_powers = [[0 for _ in range(k)] for _ in range(k)]

    def load_input_from_file(k,p,batch):
        for batchiter in range(1, batch + 1):
            filename = "party" + str(context.myid+1) + "_butterfly_online_batch" + str(batchiter)
            
            FD = open(filename, "r")
            line = FD.readline()
            #if int(line) != k:
            #    print "k dismatch!! k in file is %d"%(int(line))
            line = FD.readline()
            #if int(line) != p:
            #    print "prime dismatch!! prime in file is %d"%(int(line))
            Zp = GF(p)

            line = FD.readline()
            i = 0
            while line and i < k:
                #print i
                inputs[batchiter-1][i] = context.Share(int(line))
                line = FD.readline()  
                i = i + 1

    load_input_from_file(k,p,batch)

    def load_share_from_file(k,p,row):
        #TODO: 
        #filename = "precompute-party%d-%d.share" % (self.runtime.num_players, self.runtime.threshold, self.k, self.runtime.id,cnt)
        filename = "precompute-party%d.share" % (context.myid+1)
        FD = open(filename, "r")
        line = FD.readline()
        # if int(line) != p:
        #     print "p dismatch!! p in file is %d"%(int(line))
        line = FD.readline()
        # if int(line) != k:
        #     print "k dismatch!! k in file is %d"%(int(line))


        line = FD.readline()
        i = 0
        while line and i < k:
            #print i
            precomputed_powers[row][i] = context.Share(int(line))

            line = FD.readline()  
            i = i + 1


    for i in range(k):
        load_share_from_file(k,p,i)

    for b in range(batch):
            for i in range(k):
                a_minus_b[b][i] = await (inputs[b][i] - precomputed_powers[i][0]).open() 


    def create_output(batch):
        print( "a-b calculation finished" )

        path = "party" + str(context.myid+1) + "-powermixing-online-phase1-output"
        folder = os.path.exists(path)  
        if not folder:                  
            os.makedirs(path) 
        for b in range(batch):
            for i in range(k):
                filename = "party" + str(context.myid+1) + "-powermixing-online-phase1-output/powermixing-online-phase1-output" + str(i+1) + "-batch" + str(b+1)

                FD = open(filename, "w")

                content =  str(p) + "\n" + str(inputs[b][i])[1:-1] + "\n" + str(a_minus_b[b][i])[1:-1] + "\n" + str(k) + "\n"
            
                for share in precomputed_powers[i]:
                    content = content + str(share)[1:-1] + "\n"
                FD.write(content)
                FD.close()
        print("output to file finished")
    create_output(batch)


async def powermix_phase3(context):
    
    k = 32
    batch = 1
    inputs = [[0 for _ in range(k)] for _ in range(batch)]
    p = 115792089237316195423570985008687907853269984665640564039457584007913129640423
    Zp = GF(p)
    open_value= [[0 for _ in range(k)] for _ in range(batch)]

    def load_input_from_file(k,p,b):
        for batch in range(b):
            filename = "powers.sum" + str(context.myid+1) + "_batch" + str(batch+1)
        
            FD = open(filename, "r")
            line = FD.readline()
            #if int(line) != p:
            #    print "p dismatch!! p in file is %d"%(int(line))
            line = FD.readline()
            # if int(line) != k:
            #     print "k dismatch!! k in file is %d"%(int(line))


            line = FD.readline()
            i = 0
            while line and i < k:
                #print i
                inputs[batch][i] = context.Share(int(line))

                line = FD.readline()  
                i = i + 1
    load_input_from_file(k,p,batch)

    for b in range(batch):
        for i in range(k):
            open_value[b][i] = await (inputs[b][i]).open() 

    def create_output(batch):

        print("value open finished")

        for b in range(batch):
            filename = "party" + str(context.myid+1) + "-powermixing-online-phase3-output-batch" + str(b+1)

            FD = open(filename, "w")

            content =  str(p) + "\n" + str(k) + "\n"

            for share in open_value[b]:
                content = content + str(share)[1:-1] + "\n"
            FD.write(content)
            FD.close()
            print("file outputs finished")
    create_output(batch)






async def runProgramInNetwork(program, N, t):
    loop = asyncio.get_event_loop()
    sends, recvs = simple_router(N)

    tasks = []
    # bgtasks = []
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
    #try:
    #    loop.run_until_complete(runProgramInNetwork(butterfly_network, 3, 2))
    #
    #finally:
    #    loop.close()
    phase = 1
    if len(sys.argv) > 1:
        phase = sys.argv[1]
    if int(phase) == 1 :
        try:
            loop.run_until_complete(runProgramInNetwork(powermix_phase1, 3, 2))

        finally:
            loop.close()
    else:
        try:
            loop.run_until_complete(runProgramInNetwork(powermix_phase3, 3, 2))

        finally:
            loop.close()
