import uuid
from honeybadgermpc.symmetric_crypto import SymmetricCrypto


def test_encrypt_decrypt():
    key = uuid.uuid4().hex.encode("utf-8")
    plaintext = uuid.uuid4().hex
    ciphertext = SymmetricCrypto.encrypt(key, plaintext)
    plaintext_ = SymmetricCrypto.decrypt(key, ciphertext)
    assert plaintext_ == plaintext
