import asyncio
from contextlib import ExitStack
from pickle import dumps
from random import randint

from pytest import mark

from honeybadgermpc.betterpairing import G1, ZR
from honeybadgermpc.elliptic_curve import Subgroup
from honeybadgermpc.field import GF
from honeybadgermpc.hbavss import HbAvssBatch, HbAvssLight
from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.poly_commit_const import gen_pc_const_crs
from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.symmetric_crypto import SymmetricCrypto
from honeybadgermpc.utils.misc import print_exception_callback


def get_avss_params(n, t):
    g, h = G1.rand(), G1.rand()
    public_keys, private_keys = [None] * n, [None] * n
    for i in range(n):
        private_keys[i] = ZR.random()
        public_keys[i] = pow(g, private_keys[i])
    return g, h, public_keys, private_keys


@mark.asyncio
async def test_hbavss_light(test_router):
    t = 2
    n = 3 * t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = [g, h]

    value = ZR.random()
    avss_tasks = [None] * n
    hbavss_list = [None] * n
    dealer_id = randint(0, n - 1)

    with ExitStack() as stack:
        for i in range(n):
            hbavss = HbAvssLight(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, value=value))
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
            avss_tasks[i].add_done_callback(print_exception_callback)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
        for task in avss_tasks:
            task.cancel()
    shares = []
    for item in outputs:
        shares.append(item[2])
    assert polynomials_over(ZR).interpolate_at(zip(range(1, n + 1), shares)) == value


@mark.asyncio
async def test_hbavss_light_gf(test_router):
    t = 2
    n = 3 * t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = [g, h]
    field = GF(Subgroup.BLS12_381)
    value = field.random()
    avss_tasks = [None] * n
    hbavss_list = [None] * n
    dealer_id = randint(0, n - 1)

    with ExitStack() as stack:
        for i in range(n):
            hbavss = HbAvssLight(
                pks, sks[i], crs, n, t, i, sends[i], recvs[i], field=field
            )
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, value=value))
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
            avss_tasks[i].add_done_callback(print_exception_callback)
        # shares = await asyncio.gather(*avss_tasks)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
        for task in avss_tasks:
            task.cancel()
    shares = []
    for item in outputs:
        shares.append(item[2])
    assert polynomials_over(field).interpolate_at(zip(range(1, n + 1), shares)) == value


@mark.asyncio
async def test_hbavss_light_share_fault(test_router):
    # Injects one invalid share
    class BadDealer(HbAvssLight):
        def _get_dealer_msg(self, value):
            fault_i = randint(0, self.n - 1)
            phi = self.poly.random(self.t, value)
            commitment, aux_poly = self.poly_commit.commit(phi)
            ephemeral_secret_key = self.field.random()
            ephemeral_public_key = pow(self.g, ephemeral_secret_key)
            z = [None] * self.n
            for i in range(self.n):
                witness = self.poly_commit.create_witness(aux_poly, i + 1)
                shared_key = pow(self.public_keys[i], ephemeral_secret_key)
                if i == fault_i:
                    z[i] = SymmetricCrypto.encrypt(
                        str(shared_key).encode(), ([ZR.random()], [witness])
                    )
                else:
                    z[i] = SymmetricCrypto.encrypt(
                        str(shared_key).encode(), ([phi(i + 1)], [witness])
                    )

            return dumps(([commitment], ephemeral_public_key, z))

    t = 2
    n = 3 * t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = [g, h]

    value = ZR.random()
    avss_tasks = [None] * n
    hbavss_list = [None] * n
    dealer_id = randint(0, n - 1)

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
                avss_tasks[i].add_done_callback(print_exception_callback)
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
                avss_tasks[i].add_done_callback(print_exception_callback)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
        for task in avss_tasks:
            task.cancel()
    shares = []
    for item in outputs:
        shares.append(item[2])
    assert polynomials_over(ZR).interpolate_at(zip(range(1, n + 1), shares)) == value


@mark.asyncio
async def test_hbavss_light_encryption_fault(test_router):
    # Injects one undecryptable ciphertext
    class BadDealer(HbAvssLight):
        def _get_dealer_msg(self, value):
            fault_i = randint(0, self.n - 1)
            phi = self.poly.random(self.t, value)
            commitment, aux_poly = self.poly_commit.commit(phi)
            ephemeral_secret_key = self.field.random()
            ephemeral_public_key = pow(self.g, ephemeral_secret_key)
            z = [None] * self.n
            for i in range(self.n):
                witness = self.poly_commit.create_witness(aux_poly, i + 1)
                shared_key = pow(self.public_keys[i], ephemeral_secret_key)
                if i == fault_i:
                    z[i] = SymmetricCrypto.encrypt(
                        str(ZR.random()).encode(), ([phi(i + 1)], [witness])
                    )
                else:
                    z[i] = SymmetricCrypto.encrypt(
                        str(shared_key).encode(), ([phi(i + 1)], [witness])
                    )

            return dumps(([commitment], ephemeral_public_key, z))

    t = 2
    n = 3 * t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = [g, h]

    value = ZR.random()
    avss_tasks = [None] * n
    hbavss_list = [None] * n
    dealer_id = randint(0, n - 1)

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
                avss_tasks[i].add_done_callback(print_exception_callback)
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
                avss_tasks[i].add_done_callback(print_exception_callback)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
        for task in avss_tasks:
            task.cancel()
    shares = []
    for item in outputs:
        shares.append(item[2])
    assert polynomials_over(ZR).interpolate_at(zip(range(1, n + 1), shares)) == value


@mark.asyncio
async def test_hbavss_light_batch(test_router):
    t = 2
    n = 3 * t + 1
    batchsize = 50

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = [g, h]

    values = [int(ZR.random()) for _ in range(batchsize)]
    avss_tasks = [None] * n
    hbavss_list = [None] * n
    dealer_id = randint(0, n - 1)

    with ExitStack() as stack:
        for i in range(n):
            hbavss = HbAvssLight(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, value=values))
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
            avss_tasks[i].add_done_callback(print_exception_callback)
        # shares = await asyncio.gather(*avss_tasks)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
        for task in avss_tasks:
            task.cancel()
    shares = [[] for _ in range(batchsize)]
    for i in range(n):
        for j in range(batchsize):
            shares[j].append(outputs[i][2][j])
    for j in range(batchsize):
        assert (
            polynomials_over(ZR).interpolate_at(zip(range(1, n + 1), shares[j]))
            == values[j]
        )


@mark.asyncio
async def test_hbavss_light_batch_share_fault(test_router):
    class BadDealer(HbAvssLight):
        def _get_dealer_msg(self, value):
            if type(value) in (list, tuple):
                valuelist = value
            else:
                valuelist = [value]
            philist, commitlist, auxlist = [], [], []
            fault_i = randint(0, self.n - 1)
            for val in valuelist:
                phi = self.poly.random(self.t, val)
                philist.append(phi)
                commitment, aux_poly = self.poly_commit.commit(phi)
                commitlist.append(commitment)
                auxlist.append(aux_poly)
            ephemeral_secret_key = self.field.random()
            ephemeral_public_key = pow(self.g, ephemeral_secret_key)
            z = [None] * self.n
            for i in range(self.n):
                shared_key = pow(self.public_keys[i], ephemeral_secret_key)
                shares, witnesses = [], []
                for phi in philist:
                    shares.append(phi(i + 1))
                for aux in auxlist:
                    witnesses.append(self.poly_commit.create_witness(aux, i + 1))
                if i == fault_i:
                    shares[20] = ZR.random()
                z[i] = SymmetricCrypto.encrypt(
                    str(shared_key).encode(), (shares, witnesses)
                )

            return dumps((commitlist, ephemeral_public_key, z))

    t = 2
    n = 3 * t + 1
    batchsize = 50

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = [g, h]

    values = [int(ZR.random()) for _ in range(batchsize)]
    avss_tasks = [None] * n
    hbavss_list = [None] * n
    dealer_id = randint(0, n - 1)

    with ExitStack() as stack:
        for i in range(n):
            if i == dealer_id:
                hbavss = BadDealer(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            else:
                hbavss = HbAvssLight(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, value=values))
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
            avss_tasks[i].add_done_callback(print_exception_callback)
        # shares = await asyncio.gather(*avss_tasks)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
        for task in avss_tasks:
            task.cancel()
    shares = [[] for _ in range(batchsize)]
    for i in range(n):
        for j in range(batchsize):
            shares[j].append(outputs[i][2][j])
    for j in range(batchsize):
        assert (
            polynomials_over(ZR).interpolate_at(zip(range(1, n + 1), shares[j]))
            == values[j]
        )


@mark.asyncio
async def test_hbavss_batch(test_router):
    t = 2
    n = 3 * t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = gen_pc_const_crs(t, g=g, h=h)

    values = [ZR.random()] * (t + 1)
    avss_tasks = [None] * n
    dealer_id = randint(0, n - 1)

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
            avss_tasks[i].add_done_callback(print_exception_callback)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
        shares = [output[2] for output in outputs]
        for task in avss_tasks:
            task.cancel()

    fliped_shares = list(map(list, zip(*shares)))
    recovered_values = []
    for item in fliped_shares:
        recovered_values.append(
            polynomials_over(ZR).interpolate_at(zip(range(1, n + 1), item))
        )

    assert recovered_values == values


@mark.asyncio
async def test_hbavss_batch_share_fault(test_router):
    # Injects one invalid share
    class BadDealer(HbAvssBatch):
        def _get_dealer_msg(self, values, n):
            fault_n = randint(1, n - 1)
            fault_k = randint(1, len(values) - 1)
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
                    witness = self.poly_commit.create_witness(
                        phi[k], aux_poly[k], i + 1
                    )
                    if i == fault_n and k == fault_k:
                        z[k] = (ZR.random(), ZR.random(), witness)
                    else:
                        z[k] = (phi[k](i + 1), aux_poly[k](i + 1), witness)
                zz = SymmetricCrypto.encrypt(str(shared_key).encode(), z)
                dispersal_msg_list[i] = zz
            return dumps((commitments, ephemeral_public_key)), dispersal_msg_list

    t = 2
    n = 3 * t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = gen_pc_const_crs(t, g=g, h=h)

    values = [ZR.random()] * (t + 1)
    avss_tasks = [None] * n
    dealer_id = randint(0, n - 1)

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
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
            avss_tasks[i].add_done_callback(print_exception_callback)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
        shares = [output[2] for output in outputs]
        for task in avss_tasks:
            task.cancel()
    fliped_shares = list(map(list, zip(*shares)))
    recovered_values = []
    for item in fliped_shares:
        recovered_values.append(
            polynomials_over(ZR).interpolate_at(zip(range(1, n + 1), item))
        )

    assert recovered_values == values


@mark.asyncio
# Send t parties entirely faulty messages
async def test_hbavss_batch_t_share_faults(test_router):
    class BadDealer(HbAvssBatch):
        def _get_dealer_msg(self, values, n):
            # return super(BadDealer, self)._get_dealer_msg(values)
            fault_n_list = []
            while len(fault_n_list) < self.t:
                i = randint(1, n - 1)
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
                    witness = self.poly_commit.create_witness(
                        phi[k], aux_poly[k], i + 1
                    )
                    if i in fault_n_list:
                        z[k] = (ZR.random(), ZR.random(), witness)
                    else:
                        z[k] = (phi[k](i + 1), aux_poly[k](i + 1), witness)
                zz = SymmetricCrypto.encrypt(str(shared_key).encode(), z)
                dispersal_msg_list[i] = zz
            return dumps((commitments, ephemeral_public_key)), dispersal_msg_list

    t = 2
    n = 3 * t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = gen_pc_const_crs(t, g=g, h=h)

    values = [ZR.random()] * (t + 1)
    avss_tasks = [None] * n
    dealer_id = randint(0, n - 1)

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
                avss_tasks[i].add_done_callback(print_exception_callback)
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
        shares = [output[2] for output in outputs]
        for task in avss_tasks:
            task.cancel()

    fliped_shares = list(map(list, zip(*shares)))
    recovered_values = []
    for item in fliped_shares:
        recovered_values.append(
            polynomials_over(ZR).interpolate_at(zip(range(1, n + 1), item))
        )

    assert recovered_values == values


@mark.asyncio
async def test_hbavss_batch_encryption_fault(test_router):
    class BadDealer(HbAvssBatch):
        def _get_dealer_msg(self, values, n):
            fault_n = randint(1, n - 1)
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
                    witness = self.poly_commit.create_witness(
                        phi[k], aux_poly[k], i + 1
                    )
                    if i == fault_n:
                        z[k] = (ZR.random(), ZR.random(), witness)
                    else:
                        z[k] = (phi[k](i + 1), aux_poly[k](i + 1), witness)
                zz = SymmetricCrypto.encrypt(str(shared_key).encode(), z)
                dispersal_msg_list[i] = zz
            return dumps((commitments, ephemeral_public_key)), dispersal_msg_list

    t = 2
    n = 3 * t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = gen_pc_const_crs(t, g=g, h=h)

    values = [ZR.random()] * (t + 1)
    avss_tasks = [None] * n
    dealer_id = randint(0, n - 1)

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
                avss_tasks[i].add_done_callback(print_exception_callback)
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
                avss_tasks[i].add_done_callback(print_exception_callback)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
        shares = [output[2] for output in outputs]
        for task in avss_tasks:
            task.cancel()

    fliped_shares = list(map(list, zip(*shares)))
    recovered_values = []
    for item in fliped_shares:
        recovered_values.append(
            polynomials_over(ZR).interpolate_at(zip(range(1, n + 1), item))
        )

    assert recovered_values == values


@mark.asyncio
async def test_hbavss_light_client_mode(test_router):
    t = 2
    n = 3 * t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n + 1)
    crs = [g, h]

    value = ZR.random()
    avss_tasks = [None] * (n + 1)
    hbavss_list = [None] * n
    dealer_id = n

    with ExitStack() as stack:
        client_hbavss = HbAvssLight(
            pks, None, crs, n, t, dealer_id, sends[dealer_id], recvs[dealer_id]
        )
        stack.enter_context(client_hbavss)
        avss_tasks[n] = asyncio.create_task(
            client_hbavss.avss(0, value=value, client_mode=True)
        )
        for i in range(n):
            hbavss = HbAvssLight(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            avss_tasks[i] = asyncio.create_task(
                hbavss.avss(0, dealer_id=dealer_id, client_mode=True)
            )
            avss_tasks[i].add_done_callback(print_exception_callback)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
        for task in avss_tasks:
            task.cancel()
    shares = []
    for item in outputs:
        shares.append(item[2])
    assert polynomials_over(ZR).interpolate_at(zip(range(1, n + 1), shares)) == value


@mark.asyncio
async def test_hbavss_batch_client_mode(test_router):
    t = 2
    n = 3 * t + 1

    g, h, pks, sks = get_avss_params(n + 1, t)
    sends, recvs, _ = test_router(n + 1)
    crs = gen_pc_const_crs(t, g=g, h=h)

    values = [ZR.random()] * (t + 1)
    avss_tasks = [None] * (n + 1)
    hbavss_list = [None] * n
    dealer_id = n

    with ExitStack() as stack:
        client_hbavss = HbAvssBatch(
            pks, None, crs, n, t, dealer_id, sends[dealer_id], recvs[dealer_id]
        )
        stack.enter_context(client_hbavss)
        avss_tasks[n] = asyncio.create_task(
            client_hbavss.avss(0, values=values, client_mode=True)
        )
        for i in range(n):
            hbavss = HbAvssBatch(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            avss_tasks[i] = asyncio.create_task(
                hbavss.avss(0, dealer_id=dealer_id, client_mode=True)
            )
            avss_tasks[i].add_done_callback(print_exception_callback)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
        shares = [output[2] for output in outputs]
        for task in avss_tasks:
            task.cancel()

    fliped_shares = list(map(list, zip(*shares)))
    recovered_values = []
    for item in fliped_shares:
        recovered_values.append(
            polynomials_over(ZR).interpolate_at(zip(range(1, n + 1), item))
        )

    assert recovered_values == values


@mark.asyncio
async def test_hbavss_light_share_open(test_router):
    t = 2
    n = 3 * t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = [g, h]

    value = ZR.random()
    avss_tasks = [None] * n
    hbavss_list = [None] * n
    dealer_id = randint(0, n - 1)

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
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
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
    t = 2
    n = 3 * t + 1
    k = 4

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = [g, h]

    values = [int(ZR.random()) for _ in range(k)]
    dealer_id = randint(0, n - 1)

    with ExitStack() as stack:
        avss_tasks = [None] * n
        hbavss_list = [None] * n
        for i in range(n):
            hbavss = HbAvssLight(pks, sks[i], crs, n, t, i, sends[i], recvs[i])
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)

            if i == dealer_id:
                v, d = values, None
            else:
                v, d = None, dealer_id

            avss_tasks[i] = asyncio.create_task(hbavss.avss_parallel(0, k, v, d))
            avss_tasks[i].add_done_callback(print_exception_callback)

        outputs = [None] * k
        for j in range(k):
            outputs[j] = await asyncio.gather(
                *[hbavss_list[i].output_queue.get() for i in range(n)]
            )

        for task in avss_tasks:
            task.cancel()
    # Sort the outputs incase they're out of order
    round_outputs = [[[] for __ in range(n)] for _ in range(k)]
    for i in range(k):
        for j in range(n):
            round_outputs[outputs[i][j][1]][j] = outputs[i][j]
    shares = [[] for _ in range(n)]
    for i in range(k):
        round_output = round_outputs[i]
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


@mark.asyncio
async def test_hbavss_batch_batch(test_router):
    t = 2
    n = 3 * t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = gen_pc_const_crs(t, g=g, h=h)

    values = [ZR.random()] * 50
    avss_tasks = [None] * n
    dealer_id = randint(0, n - 1)

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
            avss_tasks[i].add_done_callback(print_exception_callback)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
        shares = [output[2] for output in outputs]
        for task in avss_tasks:
            task.cancel()

    fliped_shares = list(map(list, zip(*shares)))
    recovered_values = []
    for item in fliped_shares:
        recovered_values.append(
            polynomials_over(ZR).interpolate_at(zip(range(1, n + 1), item))
        )

    assert recovered_values == values


@mark.asyncio
async def test_hbavss_batch_batch_gf(test_router):
    t = 2
    n = 3 * t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    crs = gen_pc_const_crs(t, g=g, h=h)
    field = GF(Subgroup.BLS12_381)
    values = [field.random() for _ in range(50)]
    avss_tasks = [None] * n
    dealer_id = randint(0, n - 1)

    shares = [None] * n
    with ExitStack() as stack:
        hbavss_list = [None] * n
        for i in range(n):
            hbavss = HbAvssBatch(
                pks, sks[i], crs, n, t, i, sends[i], recvs[i], field=field
            )
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, values=values))
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
            avss_tasks[i].add_done_callback(print_exception_callback)
        outputs = await asyncio.gather(
            *[hbavss_list[i].output_queue.get() for i in range(n)]
        )
        shares = [output[2] for output in outputs]
        for task in avss_tasks:
            task.cancel()

    fliped_shares = list(map(list, zip(*shares)))
    recovered_values = []
    for item in fliped_shares:
        recovered_values.append(
            polynomials_over(field).interpolate_at(zip(range(1, n + 1), item))
        )

    assert recovered_values == values
