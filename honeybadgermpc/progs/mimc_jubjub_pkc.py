import asyncio
from honeybadgermpc.elliptic_curve import Point, Jubjub
from honeybadgermpc.progs.jubjub import share_mul
from honeybadgermpc.progs.mimc import mimc_mpc, mimc_plain

# TODO: Move into jubjub class
# GP: The generator of Jubjub curve, hardcode here
GP = Point(
    5, 6846412461894745224441235558443359243034138132682534265960483512729196124138
)


async def key_generation(context, key_length=32):
    """
    The MPC system creates random bitwise shared value [x]_B
    as the private key (priv_key),
    then calcultes X = ([x]G).open as the public key (pub_key)
    """
    # Generate the private key
    priv_key = [context.preproc.get_bit(context) for _ in range(key_length)]

    # Compute [X] = [x]G, then open it as public key
    pub_key_share = await share_mul(context, priv_key, GP)
    pub_key = await pub_key_share.open()
    return priv_key, pub_key


def mimc_encrypt(pub_key, ms, seed=None):
    """
    Encrypts blocks of plaintext data using counter-mode encryption.

    args:
    pub_key (Point): public key for encryption
    ms (list): list of message/plaintext data to encode
    seed(int): seed to use for random generation in encryption

    output:
    ciphertext (list): encoded blocks
    a_ (Point) auxilliary point sent to caller for decryption
    """

    # Randomly generated variable hold only by the dealer
    a = Jubjub.Field.random() if seed is None else seed
    # Auxiliary variable needed for decryption
    a_ = a * GP

    # secret key kept by dealer
    k = (a * pub_key).x

    # ciphertext sent to user
    ciphertext = [mimc_plain(idx, k) + m for (idx, m) in enumerate(ms)]

    return (ciphertext, a_)


async def mimc_decrypt(context, priv_key, ciphertext):
    """
    The MPC system decrypts the ciphertext to get the shared value of plaintext.

    args:
    priv_key (list of bit share): private key for decryption
    ciphertext (a tuple (cs, a_)): cs - encoded blocks
                                   a_ - auxilliary point for computing k_share

    output:
    decryted (list)L decoded blocks, list of plaintext share
    """
    (cs, a_) = ciphertext
    # secret share of the secret key k, [k] <- [x]A).x
    k_share = (await share_mul(context, priv_key, a_)).xs

    mpcs = await asyncio.gather(
        *[mimc_mpc(context, context.field(i), k_share) for i in range(len(cs))]
    )

    decrypted = [c - m for (c, m) in zip(cs, mpcs)]

    return decrypted
