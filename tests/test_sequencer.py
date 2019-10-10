from pytest import mark, raises
from random import shuffle, randint
from honeybadgermpc.utils.sequencer import Sequencer


@mark.parametrize(
    "input_values",
    (
        (
            [(2, "v"), (3, "v"), (1, "v"), (0, "v"), (4, "v")],
            [(0, "v"), (1, "v"), (2, "v"), (3, "v"), (4, "v")],
            [(4, "v"), (3, "v"), (2, "v"), (1, "v"), (0, "v")],
            [(5, "v"), (6, "v"), (1, "v"), (2, "v"), (3, "v"), (4, "v"), (0, "v")],
        )
    ),
)
def test_fixed(input_values):
    output_values = sorted(input_values, key=lambda x: x[0])
    sequencer = Sequencer()
    for value in input_values:
        sequencer.add(value)
    for value in output_values:
        assert sequencer.is_next_available()
        assert value == sequencer.get()
    assert not sequencer.is_next_available()  # All retrieved, should return false


def test_random():
    n = randint(10, 50)
    output_values = [(i, "v") for i in range(n)]
    input_values = output_values[::]
    shuffle(input_values)
    sequencer = Sequencer()
    for value in input_values:
        sequencer.add(value)
    for value in output_values:
        assert sequencer.is_next_available()
        assert value == sequencer.get()  # All retrieved, should return false


def test_already_existing_fail():
    with raises(AssertionError):
        sequencer = Sequencer()
        sequencer.add((0, "v"))
        sequencer.add((0, "v"))


def test_already_existing_pass():
    sequencer = Sequencer()
    sequencer.add((0, "v"))
    assert sequencer.get() == (0, "v")
    sequencer.add((0, "v"))  # should pass


def test_add_get_add():
    sequencer = Sequencer()
    sequencer.add((0, "v"))
    assert sequencer.get() == (0, "v")
    sequencer.add((1, "v"))  # should pass
    assert sequencer.is_next_available()
    assert sequencer.get() == (1, "v")


def test_missing():
    sequencer = Sequencer()
    sequencer.add((1, "v"))
    assert not sequencer.is_next_available()


def test_empty():
    sequencer = Sequencer()
    assert not sequencer.is_next_available()
