import math
import pytest

n = 4
t = 1


@pytest.fixture
def contract_code():
    with open("apps/robohash/contract.rl") as f:
        contract_code = f.read()
    return contract_code


@pytest.fixture
def contract(w3, get_ratl_contract, contract_code):
    contract = get_ratl_contract(contract_code, w3.eth.accounts[:4], t)
    # contract = get_contract(contract_code, n, t)
    return contract


def test_initial_state(w3, contract):
    # Check if the constructor of the contract is set up properly
    assert contract.god()  # Check that god exists
    assert contract.n() == 4
    assert contract.t() == t
    for i in range(n):
        assert contract.servers(i) == w3.eth.accounts[i]

    # assert contract.CREATED_TOKEN_COUNT == 2
    assert contract.eve_token_id() == 0
    assert contract.adam_token_id() == 1
    assert contract.inputmasks_available() == 0
    assert contract.preprocess() == 0
    assert contract.pp_elems_available() == 0
    assert contract.K() == 32
    expected_mix_constant = contract.K() / 2 * math.log2(contract.K()) ** 2
    assert expected_mix_constant == 400
    assert contract.PER_MIX_TRIPLES() == expected_mix_constant
    assert contract.PER_MIX_BITS() == expected_mix_constant


def test_constant_K(contract):
    assert contract.K() == 32


def test_preprocess_report(contract):
    pass
