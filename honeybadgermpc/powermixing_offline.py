import asyncio
from field import GF
from polynomial import polynomialsOver
from router import simple_router
import math
import sys
import os
from passive import PassiveMpc, generate_test_randoms, generate_test_triples


#######################
# Generating test files
#######################

# Fix the field for now
P = 115792089237316195423570985008687907853269984665640564039457584007913129640423
Field = GF(P)
Poly = polynomialsOver(Field)


async def beaver_mult(context, x, y, a, b, ab):
    D = await (x - a).open()
    E = await (y - b).open()

# This is a random share of x*y
    xy = context.Share(D*E) + D*b + E*a + ab

    return context.Share(await xy.open())

def read_shares(context, f):
	# Read shares from a file object
	lines = iter(f)
	# first line: field modulus
	modulus = int(next(lines))
	assert Field.modulus == modulus
	# second line: share degree
	degree = int(next(lines))   # noqa
	# third line: id
	myid = int(next(lines))     # noqa
	shares = []
	# remaining lines: shared values
	for line in lines:
		shares.append(context.Share(int(line)))
	return shares

async def powermix_offline(context):

	filename = 'sharedata/test_triples-%d.share' % (context.myid)
	triples = iter(read_shares(context, open(filename)))
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
	k = 32
	output_shares = [0 for _ in range(k)]
	filename = 'sharedata/test_randoms-%d.share' % (context.myid)
	randoms = read_shares(context, open(filename))
	output_shares[0] = randoms[0]
	for i in range(1, k):
		output_shares[i] = (await mul(randoms[0], output_shares[i - 1]))
	# ----------------------------------------------------------------------------	
	def write_to_file(shares, modulus, k):

		lines = [modulus, k] + [str(i.v)[1:-1] for i in shares[:]]
		filename = "precompute-party%d.share" % (context.myid + 1)
		with open(filename, "w") as handle:
			for line in lines:
				handle.write("{}\n".format(line))
		print("done")
	# ----------------------------------------------------------------------------
	write_to_file(output_shares, P, k)



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
	print('Generating random shares in sharedata/')
	generate_test_randoms('sharedata/test_randoms', 1, 3, 2)
	print('Generating random shares of triples in sharedata/')
	generate_test_triples('sharedata/test_triples', 1000, 3, 2)

	asyncio.set_event_loop(asyncio.new_event_loop())
	loop = asyncio.get_event_loop()
	loop.set_debug(True)
	try:
		loop.run_until_complete(runProgramInNetwork(powermix_offline, 3, 2))
	finally:
		loop.close()

