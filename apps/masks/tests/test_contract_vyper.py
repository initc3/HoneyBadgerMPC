import pytest

n = 4
t = 1


@pytest.fixture
def contract_code():
    with open("apps/masks/contract.rl") as f:
        contract_code = f.read()
    return contract_code


@pytest.fixture
def contract(w3, get_ratl_contract, contract_code):
    contract = get_ratl_contract(contract_code, w3.eth.accounts[:4], t)
    # contract = get_contract(contract_code, n, t)
    return contract


def test_initial_state(w3, contract):
    # Check if the constructor of the contract is set up properly
    assert contract.n() == 4
    assert contract.t() == t
    for i in range(n):
        assert contract.servers(i) == w3.eth.accounts[i]

    assert contract.inputmasks_available() == 0
    assert contract.inputs_ready() == 0
    assert contract.preprocess() == 0


def test_constant_K(w3, contract):
    assert contract.K() == 1
