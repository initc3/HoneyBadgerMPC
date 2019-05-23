from .typecheck import static_type_check


@static_type_check(str, 'callable(send)')
def wrap_send(tag, send):
    """Given a `send` function which takes a destination and message,
    this returns a modified function which sends the tag with the object.
    """
    def _send(dest, message):
        send(dest, (tag, message))

    return _send


@static_type_check(list, int)
def chunk_data(data, chunk_size, default=0):
    """ Break data into chunks of size `chunk_size`
    Last chunk is padded with the default value to have `chunk_size` length
    If an empty list is provided, this will return a single chunk of default values
    e.g. chunk_data([1,2,3,4,5], 2) => [[1,2], [3,4], [5, 0]]
         chunk_data([], 2) => [[0, 0]]
    """
    if len(data) == 0:
        return [default] * chunk_size

    # Main chunking
    res = [data[start:(start + chunk_size)] for start in range(0, len(data), chunk_size)]

    # Pad final chunk with default value
    res[-1] += [default] * (chunk_size - len(res[-1]))

    return res


@static_type_check(list)
def flatten_lists(lists):
    """ Given a 2d list, return a flattened 1d list
    e.g. [[1,2,3],[4,5,6],[7,8,9]] => [1,2,3,4,5,6,7,8,9]
    """
    res = []
    for inner in lists:
        res += inner

    return res


@static_type_check(list)
def transpose_lists(lists):
    """ Given a 2d list, return the transpose of the list
    e.g. [[1,2,3],[4,5,6],[7,8,9]] => [[1,4,7],[2,5,8],[3,6,9]]
    """
    rows = len(lists)
    cols = len(lists[0])
    return [[lists[j][i] for j in range(rows)] for i in range(cols)]
