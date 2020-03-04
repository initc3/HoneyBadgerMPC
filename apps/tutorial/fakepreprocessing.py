from honeybadgermpc.preprocessing import (
    PreProcessedElements as FakePreProcessedElements,
)


if __name__ == "__main__":
    pp_elements = FakePreProcessedElements()
    k = 100  # How many of each kind of preproc
    n, t = 4, 1
    pp_elements.gentle_clear_preprocessing()  # deletes sharedata/ if present
    pp_elements.generate_bits(k, n, t)
    pp_elements.generate_triples(k, n, t)
    pp_elements.preprocessing_done()
