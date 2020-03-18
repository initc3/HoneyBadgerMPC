import asyncio

from pytest import mark

from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.preprocessing import PreProcessedElements, PreProcessingConstants


@mark.asyncio
async def test_get_triple():
    n, t = 4, 1
    num_triples = 2
    pp_elements = PreProcessedElements()
    pp_elements.generate_triples(1000, n, t)

    async def _prog(ctx):
        for _ in range(num_triples):
            a_sh, b_sh, ab_sh = ctx.preproc.get_triples(ctx)
            a, b, ab = await a_sh.open(), await b_sh.open(), await ab_sh.open()
            assert a * b == ab

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_cube():
    n, t = 4, 1
    num_cubes = 2
    pp_elements = PreProcessedElements()
    pp_elements.generate_cubes(1000, n, t)

    async def _prog(ctx):
        for _ in range(num_cubes):
            a1_sh, a2_sh, a3_sh = ctx.preproc.get_cubes(ctx)
            a1, a2, a3 = await a1_sh.open(), await a2_sh.open(), await a3_sh.open()
            assert a1 * a1 == a2
            assert a1 * a2 == a3

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_zero():
    n, t = 4, 1
    num_zeros = 2
    pp_elements = PreProcessedElements()
    pp_elements.generate_zeros(1000, n, t)

    async def _prog(ctx):
        for _ in range(num_zeros):
            x_sh = ctx.preproc.get_zero(ctx)
            assert await x_sh.open() == 0

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_rand():
    n, t = 4, 1
    num_rands = 2
    pp_elements = PreProcessedElements()
    pp_elements.generate_rands(1000, n, t)

    async def _prog(ctx):
        for _ in range(num_rands):
            # Nothing to assert here, just check if the
            # required number of rands are generated
            ctx.preproc.get_rand(ctx)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_bit():
    n, t = 4, 1
    num_bits = 20
    pp_elements = PreProcessedElements()
    pp_elements.generate_bits(1000, n, t)

    async def _prog(ctx):
        shares = [ctx.preproc.get_bit(ctx) for _ in range(num_bits)]
        x = ctx.ShareArray(shares)
        x_ = await x.open()
        for i in x_:
            assert i == 0 or i == 1

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_powers():
    n, t = 4, 1
    pp_elements = PreProcessedElements()
    nums, num_powers = 2, 3

    pp_elements.generate_powers(num_powers, n, t, nums)

    async def _prog(ctx):
        for i in range(nums):
            powers = ctx.preproc.get_powers(ctx, i)
            x = await powers[0].open()
            for i, power in enumerate(powers[1:]):
                assert await power.open() == pow(x, i + 2)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_share():
    n, t = 4, 1
    x = 41
    pp_elements = PreProcessedElements()
    sid = pp_elements.generate_share(n, t, x)

    async def _prog(ctx):
        x_sh = ctx.preproc.get_share(ctx, sid)
        assert await x_sh.open() == x

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_double_share():
    n, t = 9, 2
    pp_elements = PreProcessedElements()
    pp_elements.generate_double_shares(1000, n, t)

    async def _prog(ctx):
        r_t_sh, r_2t_sh = ctx.preproc.get_double_shares(ctx)
        assert r_t_sh.t == ctx.t
        assert r_2t_sh.t == ctx.t * 2
        await r_t_sh.open()
        await r_2t_sh.open()
        assert await r_t_sh.open() == await r_2t_sh.open()

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_share_bits():
    n, t, = 4, 1
    pp_elements = PreProcessedElements()
    pp_elements.generate_share_bits(1, n, t)

    async def _prog(ctx):
        share, bits = ctx.preproc.get_share_bits(ctx)
        opened_share = await share.open()
        opened_bits = await asyncio.gather(*[b.open() for b in bits])
        bit_value = int("".join([str(b.value) for b in reversed(opened_bits)]), 2)
        assert bit_value == opened_share.value

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_intershard_masks():
    k, n, t = 100, 4, 1
    shards = (3, 8)
    pp_elements = PreProcessedElements()
    pp_elements.generate_intershard_masks(
        k, n, t, shard_1_id=shards[0], shard_2_id=shards[1]
    )
    intershard_masks = pp_elements._intershard_masks
    # check that all masks are there
    assert all(
        (f"{i}-{s}", n, t) in intershard_masks.count for i in range(n) for s in shards
    )
    num_masks = 2
    masks_3 = []
    masks_8 = []

    # TODO
    # * simplify the 2 progs, and
    # * if possible only have one def, parametrized with the shard id
    # * also: can the shard be accessed via the ctx object instead? The main
    #   point is that information seems to be redundant ... if the ctx has
    #   access to the shard id then perhaps no need to pass it to the method
    #  `get_intershard_masks()`
    async def _prog3(ctx):
        for _ in range(num_masks):
            mask_share = ctx.preproc.get_intershard_masks(ctx, shards[0])
            mask = await mask_share.open()
            masks_3.append(mask)

    async def _prog8(ctx):
        for _ in range(num_masks):
            mask_share = ctx.preproc.get_intershard_masks(ctx, shards[1])
            mask = await mask_share.open()
            masks_8.append(mask)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog3, shard_id=shards[0])
    await program_runner.join()
    program_runner.add(_prog8, shard_id=shards[1])
    await program_runner.join()
    print(f"\nmasks for shard 3: {masks_3}")
    print(f"len of masks: {len(masks_3)}")
    print(f"\nmasks for shard 8: {masks_8}")
    print(f"len of masks: {len(masks_8)}")
    assert masks_3 == masks_8


def test_generate_intershard_masks():
    k, n, t = 100, 4, 1
    shards = (3, 8)
    pp_elements = PreProcessedElements()
    pp_elements.generate_intershard_masks(
        k, n, t, shard_1_id=shards[0], shard_2_id=shards[1]
    )
    intershard_masks = pp_elements._intershard_masks
    # check the cache and count
    cache = intershard_masks.cache
    count = intershard_masks.count
    assert len(cache) == 2 * n  # there are 2 shards with n servers in each
    # Check that the cache contains all expected keys. A key is a 3-tuple made
    # from (context_id, n, t), The context_id is made from "{i}-{shard_id}".
    assert all((f"{i}-{s}", n, t) in cache for i in range(n) for s in shards)
    assert all(len(tuple(elements)) == k for elements in cache.values())
    assert all(c == k for c in count.values())
    assert all((f"{i}-{s}", n, t) in count for i in range(n) for s in shards)
    # check all the expected files have been created
    data_dir_path = intershard_masks.data_dir_path
    for shard_index, shard_id in enumerate(shards):
        other_shard = shards[1 - shard_index]
        for node_id in range(n):
            node_path = data_dir_path.joinpath(f"{node_id}-{shard_id}")
            assert node_path.exists()
            csm_path = node_path.joinpath(intershard_masks.preprocessing_name)
            assert csm_path.exists()
            file_path = csm_path.joinpath(
                f"{n}_{t}-{shard_id}_{other_shard}"
            ).with_suffix(PreProcessingConstants.SHARE_FILE_EXT.value)
            assert file_path.exists()
            with file_path.open() as f:
                _lines = f.readlines()
            lines = [int(line) for line in _lines]
            assert len(lines) == 3 + k  # modulus, degree t, n, k
            assert lines[0] == intershard_masks.field.modulus
            assert lines[1] == t
            assert lines[2] == node_id
