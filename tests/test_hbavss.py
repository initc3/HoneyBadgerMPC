from pytest import mark
from random import randint
from contextlib import ExitStack
from pickle import dumps
from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.poly_commit_const import gen_pc_const_crs
from honeybadgermpc.betterpairing import G1, ZR
from honeybadgermpc.hbavss import HbAvssLight, HbAvssBatch
from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.symmetric_crypto import SymmetricCrypto
import asyncio


def get_avss_params(n, t):
    g, h = G1.rand(), G1.rand()
    public_keys, private_keys = [None]*n, [None]*n
    for i in range(n):
        private_keys[i] = ZR.random()
        public_keys[i] = pow(g, private_keys[i])
    return g, h, public_keys, private_keys


@mark.asyncio
async def test_hbavss_light(test_router):
    t = 2
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = [g, h]

    value = ZR.random()
    avss_tasks = [None]*n
    hbavss_list = [None]*n
    dealer_id = randint(0, n-1)

    with ExitStack() as stack:
        for i in range(n):
            hbavss = HbAvssLight(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, value=value))
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
        # shares = await asyncio.gather(*avss_tasks)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)])
        for task in avss_tasks:
            task.cancel()
    shares = []
    for item in outputs:
        shares.append(item[2])
    assert polynomials_over(ZR).interpolate_at(zip(range(1, n+1), shares)) == value


@mark.asyncio
async def test_hbavss_light_share_fault(test_router):
    def callback(future):
        if future.done():
            ex = future.exception()
            if ex is not None:
                print('\nException:', ex)
                raise ex

    # Injects one invalid share
    class BadDealer(HbAvssLight):
        def _get_dealer_msg(self, value):
            fault_i = randint(0, self.n-1)
            phi = self.poly.random(self.t, value)
            commitment, aux_poly = self.poly_commit.commit(phi)
            ephemeral_secret_key = self.field.random()
            ephemeral_public_key = pow(self.g, ephemeral_secret_key)
            z = [None]*self.n
            for i in range(self.n):
                witness = self.poly_commit.create_witness(aux_poly, i+1)
                shared_key = pow(self.public_keys[i], ephemeral_secret_key)
                if i == fault_i:
                    z[i] = SymmetricCrypto.encrypt(
                        str(shared_key).encode(), (ZR.random(), witness))
                else:
                    z[i] = SymmetricCrypto.encrypt(
                        str(shared_key).encode(), (phi(i+1), witness))

            return dumps((commitment, ephemeral_public_key, z))

    t = 2
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = [g, h]

    value = ZR.random()
    avss_tasks = [None]*n
    hbavss_list = [None]*n
    dealer_id = randint(0, n-1)

    with ExitStack() as stack:
        for i in range(n):
            if i == dealer_id:
                hbavss = BadDealer(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            else:
                hbavss = HbAvssLight(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, value=value))
                avss_tasks[i].add_done_callback(callback)
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
                avss_tasks[i].add_done_callback(callback)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)])
        for task in avss_tasks:
            task.cancel()
    shares = []
    for item in outputs:
        shares.append(item[2])
    assert polynomials_over(ZR).interpolate_at(zip(range(1, n+1), shares)) == value


@mark.asyncio
async def test_hbavss_light_encryption_fault(test_router):
    def callback(future):
        if future.done():
            ex = future.exception()
            if ex is not None:
                print('\nException:', ex)
                raise ex

    # Injects one undecryptable ciphertext
    class BadDealer(HbAvssLight):
        def _get_dealer_msg(self, value):
            fault_i = randint(0, self.n-1)
            phi = self.poly.random(self.t, value)
            commitment, aux_poly = self.poly_commit.commit(phi)
            ephemeral_secret_key = self.field.random()
            ephemeral_public_key = pow(self.g, ephemeral_secret_key)
            z = [None]*self.n
            for i in range(self.n):
                witness = self.poly_commit.create_witness(aux_poly, i+1)
                shared_key = pow(self.public_keys[i], ephemeral_secret_key)
                if i == fault_i:
                    z[i] = SymmetricCrypto.encrypt(
                        str(ZR.random()).encode(), (phi(i+1), witness))
                else:
                    z[i] = SymmetricCrypto.encrypt(
                        str(shared_key).encode(), (phi(i+1), witness))

            return dumps((commitment, ephemeral_public_key, z))

    t = 2
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = [g, h]

    value = ZR.random()
    avss_tasks = [None]*n
    hbavss_list = [None]*n
    dealer_id = randint(0, n-1)

    with ExitStack() as stack:
        for i in range(n):
            if i == dealer_id:
                hbavss = BadDealer(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            else:
                hbavss = HbAvssLight(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, value=value))
                avss_tasks[i].add_done_callback(callback)
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
                avss_tasks[i].add_done_callback(callback)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)])
        for task in avss_tasks:
            task.cancel()
    shares = []
    for item in outputs:
        shares.append(item[2])
    assert polynomials_over(ZR).interpolate_at(zip(range(1, n+1), shares)) == value


@mark.asyncio
async def test_hbavss_batch(test_router):
    t = 2
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = gen_pc_const_crs(t, g=g, h=h)

    values = [ZR.random()] * (t+1)
    avss_tasks = [None] * n
    dealer_id = randint(0, n-1)

    shares = [None] * n
    with ExitStack() as stack:
        hbavss_list = [None] * n
        for i in range(n):
            hbavss = HbAvssBatch(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, values=values))
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
        shares = await asyncio.gather(*[hbavss_list[i].shares_future for i in range(n)])
        for task in avss_tasks:
            task.cancel()

    fliped_shares = list(map(list, zip(*shares)))
    recovered_values = []
    for item in fliped_shares:
        recovered_values.append(polynomials_over(
            ZR).interpolate_at(zip(range(1, n+1), item)))

    assert recovered_values == values


@mark.asyncio
async def test_hbavss_batch_share_fault(test_router):
    def callback(future):
        if future.done():
            ex = future.exception()
            if ex is not None:
                print('\nException:', ex)
                raise ex

    # Injects one invalid share
    class BadDealer(HbAvssBatch):
        def _get_dealer_msg(self, values, n):
            fault_n = randint(1, n-1)
            fault_k = randint(1, len(values)-1)
            secret_size = len(values)
            phi = [None] * secret_size
            commitments = [None] * secret_size
            aux_poly = [None] * secret_size
            for k in range(secret_size):
                phi[k] = self.poly.random(self.t, values[k])
                commitments[k], aux_poly[k] = self.poly_commit.commit(phi[k])

            ephemeral_secret_key = self.field.random()
            ephemeral_public_key = pow(self.g, ephemeral_secret_key)
            dispersal_msg_list = [None] * n
            for i in range(n):
                shared_key = pow(self.public_keys[i], ephemeral_secret_key)
                z = [None] * secret_size
                for k in range(secret_size):
                    witness = self.poly_commit.create_witness(phi[k], aux_poly[k], i+1)
                    if (i == fault_n and k == fault_k):
                        z[k] = SymmetricCrypto.encrypt(
                            str(shared_key).encode("utf-8"),
                            (ZR.random(), ZR.random(), witness))
                    else:
                        z[k] = SymmetricCrypto.encrypt(
                            str(shared_key).encode("utf-8"),
                            (phi[k](i+1), aux_poly[k](i+1), witness))
                dispersal_msg_list[i] = dumps(z)
            return dumps((commitments, ephemeral_public_key)), dispersal_msg_list

    t = 2
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = gen_pc_const_crs(t, g=g, h=h)

    values = [ZR.random()] * (t+1)
    avss_tasks = [None] * n
    dealer_id = randint(0, n-1)

    shares = [None] * n
    with ExitStack() as stack:
        hbavss_list = []
        for i in range(n):
            if i == dealer_id:
                hbavss = BadDealer(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            else:
                hbavss = HbAvssBatch(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list.append(hbavss)
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, values=values))
                avss_tasks[i].add_done_callback(callback)
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
        for i in range(n):
            shares[i] = await hbavss_list[i].shares_future
        for task in avss_tasks:
            task.cancel()

    fliped_shares = list(map(list, zip(*shares)))
    recovered_values = []
    for item in fliped_shares:
        recovered_values.append(polynomials_over(
            ZR).interpolate_at(zip(range(1, n+1), item)))

    assert recovered_values == values


@mark.asyncio
# Send t parties entirely faulty messages
async def test_hbavss_batch_t_share_faults(test_router):
    def callback(future):
        if future.done():
            ex = future.exception()
            if ex is not None:
                print('\nException:', ex)
                raise ex

    class BadDealer(HbAvssBatch):
        def _get_dealer_msg(self, values, n):
            # return super(BadDealer, self)._get_dealer_msg(values)
            fault_n_list = []
            while len(fault_n_list) < self.t:
                i = randint(1, n-1)
                if i not in fault_n_list:
                    fault_n_list.append(i)
            secret_size = len(values)
            phi = [None] * secret_size
            commitments = [None] * secret_size
            aux_poly = [None] * secret_size
            for k in range(secret_size):
                phi[k] = self.poly.random(self.t, values[k])
                commitments[k], aux_poly[k] = self.poly_commit.commit(phi[k])

            ephemeral_secret_key = self.field.random()
            ephemeral_public_key = pow(self.g, ephemeral_secret_key)
            dispersal_msg_list = [None] * n
            for i in range(n):
                shared_key = pow(self.public_keys[i], ephemeral_secret_key)
                z = [None] * secret_size
                for k in range(secret_size):
                    witness = self.poly_commit.create_witness(phi[k], aux_poly[k], i+1)
                    if (i in fault_n_list):
                        z[k] = SymmetricCrypto.encrypt(
                            str(shared_key).encode("utf-8"),
                            (ZR.random(), ZR.random(), witness))
                    else:
                        z[k] = SymmetricCrypto.encrypt(
                            str(shared_key).encode("utf-8"),
                            (phi[k](i+1), aux_poly[k](i+1), witness))
                dispersal_msg_list[i] = dumps(z)
            return dumps((commitments, ephemeral_public_key)), dispersal_msg_list

    t = 2
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = gen_pc_const_crs(t, g=g, h=h)

    values = [ZR.random()] * (t+1)
    avss_tasks = [None] * n
    dealer_id = randint(0, n-1)

    shares = [None] * n
    with ExitStack() as stack:
        hbavss_list = []
        for i in range(n):
            if i == dealer_id:
                hbavss = BadDealer(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            else:
                hbavss = HbAvssBatch(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list.append(hbavss)
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, values=values))
                avss_tasks[i].add_done_callback(callback)
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
        for i in range(n):
            shares[i] = await hbavss_list[i].shares_future
        for task in avss_tasks:
            task.cancel()

    fliped_shares = list(map(list, zip(*shares)))
    recovered_values = []
    for item in fliped_shares:
        recovered_values.append(polynomials_over(
            ZR).interpolate_at(zip(range(1, n+1), item)))

    assert recovered_values == values


@mark.asyncio
async def test_hbavss_batch_encryption_fault(test_router):
    def callback(future):
        if future.done():
            ex = future.exception()
            if ex is not None:
                print('\nException:', ex)
                raise ex

    class BadDealer(HbAvssBatch):
        def _get_dealer_msg(self, values, n):
            fault_n = randint(1, n-1)
            secret_size = len(values)
            phi = [None] * secret_size
            commitments = [None] * secret_size
            aux_poly = [None] * secret_size
            for k in range(secret_size):
                phi[k] = self.poly.random(self.t, values[k])
                commitments[k], aux_poly[k] = self.poly_commit.commit(phi[k])

            ephemeral_secret_key = self.field.random()
            ephemeral_public_key = pow(self.g, ephemeral_secret_key)
            dispersal_msg_list = [None] * n
            for i in range(n):
                shared_key = pow(self.public_keys[i], ephemeral_secret_key)
                z = [None] * secret_size
                for k in range(secret_size):
                    witness = self.poly_commit.create_witness(phi[k], aux_poly[k], i+1)
                    if (i == fault_n):
                        z[k] = SymmetricCrypto.encrypt(
                            str(ZR.random()).encode("utf-8"),
                            (ZR.random(), ZR.random(), witness))
                    else:
                        z[k] = SymmetricCrypto.encrypt(
                            str(shared_key).encode("utf-8"),
                            (phi[k](i+1), aux_poly[k](i+1), witness))
                dispersal_msg_list[i] = dumps(z)
            return dumps((commitments, ephemeral_public_key)), dispersal_msg_list

    t = 2
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = gen_pc_const_crs(t, g=g, h=h)

    values = [ZR.random()] * (t+1)
    avss_tasks = [None] * n
    dealer_id = randint(0, n-1)

    shares = [None] * n
    with ExitStack() as stack:
        hbavss_list = []
        for i in range(n):
            if i == dealer_id:
                hbavss = BadDealer(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            else:
                hbavss = HbAvssBatch(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list.append(hbavss)
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, values=values))
                avss_tasks[i].add_done_callback(callback)
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
                avss_tasks[i].add_done_callback(callback)
        for i in range(n):
            shares[i] = await hbavss_list[i].shares_future
        for task in avss_tasks:
            task.cancel()

    fliped_shares = list(map(list, zip(*shares)))
    recovered_values = []
    for item in fliped_shares:
        recovered_values.append(polynomials_over(
            ZR).interpolate_at(zip(range(1, n+1), item)))

    assert recovered_values == values


@mark.asyncio
async def test_hbavss_light_client_mode(test_router):
    t = 2
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n+1)
    crs = [g, h]

    value = ZR.random()
    avss_tasks = [None]*(n+1)
    hbavss_list = [None]*n
    dealer_id = n

    with ExitStack() as stack:
        client_hbavss = HbAvssLight(
            pks, None, crs, n, t, dealer_id, sends[dealer_id], recvs[dealer_id])
        stack.enter_context(client_hbavss)
        avss_tasks[n] = asyncio.create_task(
            client_hbavss.avss(0, value=value, client_mode=True))
        for i in range(n):
            hbavss = HbAvssLight(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            avss_tasks[i] = asyncio.create_task(
                hbavss.avss(0, dealer_id=dealer_id, client_mode=True))
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)])
        for task in avss_tasks:
            task.cancel()
    shares = []
    for item in outputs:
        shares.append(item[2])
    assert polynomials_over(ZR).interpolate_at(zip(range(1, n+1), shares)) == value


@mark.asyncio
async def test_hbavss_batch_client_mode(test_router):
    t = 2
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n+1, t)
    sends, recvs, _ = test_router(n+1)
    crs = gen_pc_const_crs(t, g=g, h=h)

    values = [ZR.random()] * (t+1)
    avss_tasks = [None] * (n+1)
    hbavss_list = [None] * n
    dealer_id = n

    with ExitStack() as stack:
        client_hbavss = HbAvssBatch(
            pks, None, crs, n, t, dealer_id, sends[dealer_id], recvs[dealer_id])
        stack.enter_context(client_hbavss)
        avss_tasks[n] = asyncio.create_task(
            client_hbavss.avss(0, values=values, client_mode=True))
        for i in range(n):
            hbavss = HbAvssBatch(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            avss_tasks[i] = asyncio.create_task(
                hbavss.avss(0, dealer_id=dealer_id, client_mode=True))
        shares = await asyncio.gather(*[hbavss_list[i].shares_future for i in range(n)])
        for task in avss_tasks:
            task.cancel()

    fliped_shares = list(map(list, zip(*shares)))
    recovered_values = []
    for item in fliped_shares:
        recovered_values.append(polynomials_over(
            ZR).interpolate_at(zip(range(1, n+1), item)))

    assert recovered_values == values


@mark.asyncio
async def test_hbavss_light_share_open(test_router):
    t = 2
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = [g, h]

    value = ZR.random()
    avss_tasks = [None]*n
    hbavss_list = [None]*n
    dealer_id = randint(0, n-1)

    with ExitStack() as stack:
        for i in range(n):
            hbavss = HbAvssLight(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, value=value))
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)])
        for task in avss_tasks:
            task.cancel()
    shares = []
    for item in outputs:
        shares.append(item[2])

    async def _prog(context):
        share_value = context.field(shares[context.myid])
        assert await context.Share(share_value).open() == value

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_hbavss_light_parallel_share_array_open(test_router):
    def callback(future):
        if future.done():
            ex = future.exception()
            if ex is not None:
                print('\nException:', ex)
                raise ex
    t = 2
    n = 3*t + 1
    k = 4

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = [g, h]

    values = [int(ZR.random()) for _ in range(k)]
    dealer_id = randint(0, n-1)

    with ExitStack() as stack:
        avss_tasks = [None]*n
        hbavss_list = [None]*n
        for i in range(n):
            hbavss = HbAvssLight(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)

            if i == dealer_id:
                v, d = values, None
            else:
                v, d = None, dealer_id

            avss_tasks[i] = asyncio.create_task(hbavss.avss_parallel(0, k, v, d))
            avss_tasks[i].add_done_callback(callback)

        outputs = [None]*k
        for j in range(k):
            outputs[j] = await asyncio.gather(
                *[hbavss_list[i].output_queue.get() for i in range(n)])

        for task in avss_tasks:
            task.cancel()

    shares = [[] for _ in range(n)]
    for i in range(k):
        round_output = outputs[i]
        for j in range(len(round_output)):
            shares[j].append(round_output[j][2])

    async def _prog(context):
        share_values = list(map(context.field, shares[context.myid]))
        opened_shares = set(await context.ShareArray(share_values).open())

        # The set of opened share should have exactly `k` values
        assert len(opened_shares) == k

        # All the values in the set of opened shares should be from the initial values
        for i in opened_shares:
            assert i.value in values

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()
