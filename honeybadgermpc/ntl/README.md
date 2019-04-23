# Python-NTL interface

The code in this directory exposes an python interface
for several NTL functions, and other C++ code using
NTL.

# Modifying code

Currently, this directory is not mounted when you run
`docker-compose ...`. In order to mount it, please remove
or comment out this line `- /usr/src/HoneyBadgerMPC/honeybadgermpc/ntl`
 and then start the container again.


# Building code

If you go through the instructions above, you will find that you might
need to rebuild all the Cython code. This can be done by running the
following command from `/usr/src/HoneyBadgerMPC`


```python setup.py build_ext --inplace```


The same command can be used to rebuild the code if you
modify any of the Cython node. Note that you *must* rebuild the code
to observe any changes during execution.

# Writing Parallel Code

Take a look at NTL documentation and see which operations are already
parallelized. In general, it might be better to use these directly
whenever possible.

If you wish to write parallel code yourself, please take a look
at OpenMP documentation for Cython.

Here's a gist of what parallel code using OpenMP in Cython would look
like when using NTL

```
with nogil, parallel():
    ZZ_p::init(modulus)
    for i in prange(start, end, step):
        ...:
```

The operation above starts `n` threads (`n` is decided by OpenMP and
can be modified by using `openmp.set_num_threads` or modifying the
environment variable `OMP_NUM_THREADS`), calls
`ZZ_p::init()` for each thread, and then splits the
`for` loop into `n` chunks. Different chunking strategies
can be used but this has not been explored much and might not
particularly turn out to be useful since we have a largely even
distribution of work among threads.