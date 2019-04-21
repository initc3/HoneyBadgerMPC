import asyncio
import random
from pytest import fixture


@fixture
def galois_field():
    from honeybadgermpc.field import GF
    from honeybadgermpc.elliptic_curve import Subgroup
    return GF(Subgroup.BLS12_381)


@fixture
def galois_field_roots(galois_field):
    """First 33 2^r roots of BLS12_381"""
    return [
        1,
        52435875175126190479447740508185965837690552500527637822603658699938581184512,
        52435875175126190475982595682112313518914282969839895044333406231173219221505,
        28761180743467419819834788392525162889723178799021384024940474588120723734663,
        38476778329304481878022718993882556548812578500290864179952442003245540347252,
        39328881859443649819318207548060215749094715634259317161033277606721139812495,
        7181556051604179363188280445331338471236451149758288711283449754901695186389,
        12058798319732516928593266977629156816578295917773852992327494850156627156852,
        8031134342720706638121837972897357960137225421159210873251699151356237587899,
        27875698343364121290699656948778287454201257612145723397675462767067764955538,
        27833371751571244390832763638558622030804012906942143728341572300682471754788,
        7856015019036898134030885911762020324088142706362191923044581015685623376708,
        1212178207794488802871615932883746973261797952617933748586130149731138850786,
        19613040742470455411907191493822020406495985991136501189627365095126170896081,
        10046109084464152992630654236639403505568771663216388590329280186692245124077,
        5079812778248971429856231719902992892510398570645113444290363477124725425505,
        46841719872634776782065878140549563889417416683298457024380933092377292299436,
        31286683632267680233218648465826402606244084393966558249711273683173231074876,
        1428108191554775640016215541708397688082356600559258886512783148844543714665,
        327233850889118497902974278052939361323213871423270405025475002588376681392,
        15438658051263867286206976968284816972069262219369280291916849633341557975308,
        6671633711488033849356667869801972058459413222446374064179072933526918202732,
        8633459580284099687444669646081337270358347753599706450190470428820665553938,
        14160430570568764764311436585714249089653834673824030315312847891770681518598,
        4355239696899301876039811032650569307957271487840780320514380464874420256750,
        34771460652174823855816724474731618094670816624592246225516300689278210055765,
        44531129011014618925811908669959094672111274131632065926036032322241240693696,
        36121702870952496615949723464477206567869509297540296602215679154386031180758,
        20257086787665235422702333268420930383534697687595131509303186373454682366240,
        19198300450045974760322445328762595043377263979035567067359042471865346602023,
        8440883371485595147185456037843487899036125874298769093456291114070486308750,
        21123405922655689551948186441194090886901565533353647562100078719332932021059,
        25668834994940048658761004830063370081900324240717227839632269577717222857885
    ]


@fixture
def polynomial(galois_field):
    from honeybadgermpc.polynomial import polynomials_over
    return polynomials_over(galois_field)


@fixture
def rust_field():
    from honeybadgermpc.betterpairing import ZR
    return ZR


@fixture
def rust_polynomial(rust_field):
    from honeybadgermpc.polynomial import polynomials_over
    return polynomials_over(rust_field)


@fixture(params=(1,))
def triples_polys(request, triples_fields, polynomial):
    t = request.param
    return [
        polynomial.random(t, field) for triple in triples_fields for field in triple
    ]


class TestPreProcessing():
    def __init__(self):
        from honeybadgermpc.preprocessing import PreProcessedElements
        self.cache = {}
        self.elements = PreProcessedElements()

    def generate(self, kind, n, t, arg1=None, arg2=None, k=1000):
        if kind in [
            "zeros",
            "triples",
            "cubes",
            "rands",
            "bits",
            "oneminusone",
            "double_shares",
            "powers"
        ]:
            if (kind, n, t) in self.cache:
                return
            self.cache[(kind, n, t)] = True
            if kind == "zeros":
                self.elements.generate_zeros(k, n, t)
            elif kind == "triples":
                self.elements.generate_triples(k, n, t)
            elif kind == "cubes":
                self.elements.generate_cubes(k, n, t)
            elif kind == "rands":
                self.elements.generate_rands(k, n, t)
            elif kind == "bits":
                self.elements.generate_bits(k, n, t)
            elif kind == "oneminusone":
                self.elements.generate_one_minus_one_rands(k, n, t)
            elif kind == "double_shares":
                self.elements.generate_double_shares(k, n, t)
            elif kind == "powers":
                self.elements.generate_powers(arg1, n, t, arg2)
        elif kind == "share":
            return self.elements.generate_share(arg1, n, t)


@fixture(scope="session")
def test_preprocessing():
    return TestPreProcessing()


@fixture
def test_router():
    def _test_router(n, maxdelay=0.005, seed=None):
        """Builds a set of connected channels, with random delay
        @return (receives, sends)
        """
        rnd = random.Random(seed)

        queues = [asyncio.Queue() for _ in range(n)]

        def make_send(i):
            def _send(j, o):
                delay = rnd.random() * maxdelay
                # print('SEND  %8s [%2d -> %2d]' % (o, i, j))
                asyncio.get_event_loop().call_later(delay, queues[j].put_nowait, (i, o))
                # queues[j].put_nowait((i, o))

            def _bc(o):
                # print('BCAST  %8s [%2d ->  *]' % (o[0], i), o[1])
                for j in range(n):
                    _send(j, o)
            return _send, _bc

        def make_recv(j):
            async def _recv():
                (i, o) = await queues[j].get()
                # print('RECV %8s [%2d -> %2d]' % (o, i, j))
                return (i, o)
            return _recv

        sends, bcasts = zip(*[make_send(i) for i in range(n)])
        return (sends, [make_recv(j) for j in range(n)], bcasts)
    return _test_router


@fixture()
def test_runner(test_preprocessing):
    from honeybadgermpc.mpc import TaskProgramRunner

    async def _test_runner(prog, n=3, t=1, to_generate=[], k=1000, mixins=[]):
        for to_gen in to_generate:
            test_preprocessing.generate(to_gen, n, t, k=k)

        config = {}
        for mixin in mixins:
            if mixin.name in config:
                raise ValueError(f"Multiple mixins with name {mixin.name} loaded!")

            config[mixin.name] = mixin

        program_runner = TaskProgramRunner(n, t, config)
        program_runner.add(prog)

        return await program_runner.join()

    return _test_runner
