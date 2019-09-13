from honeybadgermpc.proofs import prove_inner_product, verify_inner_product, \
    prove_inner_product_one_known, verify_inner_product_one_known, \
    prove_batch_inner_product_one_known, verify_batch_inner_product_one_known, \
    MerkleTree
from honeybadgermpc.betterpairing import ZR, G1


def test_inner_product_proof():
    n = 10
    a = [ZR.random() for i in range(n)]
    b = [ZR.random() for i in range(n)]
    iprod = ZR(0)
    for i in range(n):
        iprod += a[i]*b[i]
    comm, iprod, proof = prove_inner_product(a, b)
    assert verify_inner_product(comm, iprod, proof)
    comm, iprod, proof2 = prove_inner_product(a, b, comm=comm)
    assert verify_inner_product(comm, iprod, proof2)
    comm, iprod, badproof = prove_inner_product(a, b, comm=G1.rand())
    assert not verify_inner_product(comm, iprod, badproof)


def test_inner_product_proof_one_known():
    n = 10
    a = [ZR.random() for i in range(n)]
    b = [ZR.random() for i in range(n)]
    iprod = ZR(0)
    for i in range(n):
        iprod += a[i]*b[i]
    comm, iprod, proof = prove_inner_product_one_known(a, b)
    assert verify_inner_product_one_known(comm, iprod, b, proof)
    comm, iprod, badproof = prove_inner_product_one_known(a, b, comm=G1.rand())
    assert not verify_inner_product_one_known(comm, iprod, b, badproof)


def test_batch_inner_product_proof_one_known():
    n = 10
    a = [ZR.random() for i in range(n)]
    bs = [[ZR.random() for j in range(n)] for i in range(3*n)]
    comm, iprods, proofs = prove_batch_inner_product_one_known(a, bs)
    assert verify_batch_inner_product_one_known(comm, iprods[2], bs[2], proofs[2])
    comm, iprods, badproofs = prove_batch_inner_product_one_known(a, bs, comm=G1.rand())
    assert not verify_batch_inner_product_one_known(comm, iprods[2], bs[2], badproofs[2])


def test_merkle_tree():
    import pickle
    leaves = [b"Cravings", b"is", b"best", b"restaurant"]
    t = MerkleTree(leaves)
    rh = t.get_root_hash()
    br = t.get_branch(0)
    assert MerkleTree.verify_membership(b"Cravings", br, rh)
    assert not MerkleTree.verify_membership(b"Chipotle", br, rh)
    t2 = MerkleTree()
    vec = [pickle.dumps(G1.rand()) for _ in range(12)]
    t2.append(vec[0])
    t2.append_many(vec[1:])
    rh2 = t2.get_root_hash()
    br2 = t2.get_branch(7)
    assert MerkleTree.verify_membership(vec[7], br2, rh2)
    # If this fails, buy a lottery ticket... or check that G1.rand() is actually random
    assert not MerkleTree.verify_membership(pickle.dumps(G1.rand()), br2, rh2)
    assert not MerkleTree.verify_membership(vec[6], br2, rh)
