import heapq


class Sequencer(object):
    """
    It's an abstract data structure implemented just on top of a priority queue. It
    holds items of the form (i, _, ..). Items can be enqueued in any order, but `get`
    will always return them in strict counting order, (1, _),(2, _),... so values
    added out of order are buffered until the next counting number is available.
    """

    def __init__(self):
        self.heap = []
        self.values = set()  # Use this to ensure a duplicate is not added
        self.next = 0

    def get(self):
        """
        Returns the next value as per the counting order.

        If the next value is not available then this method throws an error. Therefore,
        `is_next_available` should be called before calling `get` to see if the next
        value is available or not.
        """
        assert self.is_next_available()
        value = heapq.heappop(self.heap)
        self.values.remove(value[0])
        self.next += 1
        return value

    def is_next_available(self):
        """
        Returns if the next value in the counting order is available or not.
        """
        return len(self.heap) > 0 and self.heap[0][0] == self.next

    def add(self, value):
        """
        Adds a value to the sequencer.

        value: a `tuple` or a `list` with at least two elements where the first element
        denotes the sequence number.
        """
        assert type(value) in [tuple, list]
        assert type(value[0]) is int
        assert value[0] not in self.values
        self.values.add(value[0])
        heapq.heappush(self.heap, value)
