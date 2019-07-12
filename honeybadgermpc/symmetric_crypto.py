from Crypto.Cipher import AES
from Crypto import Random
from hashlib import sha256
from pickle import dumps, loads


class SymmetricCrypto(object):
    """
    Uses AES with a 32-byte key.
    Semantic security (iv is randomized).
    Copied from honeybadgerbft.
    """

    BS = 16

    @staticmethod
    def pad(s):
        padding = (SymmetricCrypto.BS - len(s) % SymmetricCrypto.BS) * bytes(
            [SymmetricCrypto.BS - len(s) % SymmetricCrypto.BS]
        )
        return s + padding

    @staticmethod
    def unpad(s):
        return s[: -ord(s[len(s) - 1 :])]

    @staticmethod
    def encrypt(key, plaintext):
        """ """
        key = sha256(key).digest()  # hash the key
        assert len(key) == 32
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        ciphertext = iv + cipher.encrypt(SymmetricCrypto.pad(dumps(plaintext)))
        return ciphertext

    @staticmethod
    def decrypt(key, ciphertext):
        """ """
        key = sha256(key).digest()  # hash the key
        assert len(key) == 32
        iv = ciphertext[:16]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        plaintext = loads(SymmetricCrypto.unpad(cipher.decrypt(ciphertext[16:])))
        return plaintext
