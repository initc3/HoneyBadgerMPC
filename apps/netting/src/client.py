"""
Netting Client
"""
from apps.netting.config.config import (
    NUM_CLIENTS,
    NETTING_BASE_DIR,
    tx_file_prefix,
    tx_file_suffix,
    bal_file_prefix,
    bal_file_suffix,
)
import logging


class Transaction:

    """
    Initalize the transaction from CSV file line. Currently this is the only
    way we take inputs.
    """

    def __init__(self, csv_string):
        params = csv_string.split(",")
        assert len(params) == 3, "File transaction format incorrect"
        self.amount = int(float(params[2]) * 100)
        self.sender = int(params[0])
        self.reciever = int(params[1])


def read_balance(id):
    ret = ""
    with open(
        NETTING_BASE_DIR + "data/" + bal_file_prefix + str(id) + bal_file_suffix, "r"
    ) as f:
        for line in f.readlines():
            ret = int(float(line) * 100)
    return ret


def read_txs(id):
    in_tx = []
    out_tx = []
    with open(
        NETTING_BASE_DIR + "data/" + tx_file_prefix + str(id) + tx_file_suffix
    ) as f:
        for line in f.readlines():
            tx = Transaction(line)
            if tx.sender == id:
                out_tx.append(tx)
            elif tx.reciever == id:
                in_tx.append(tx)
            else:
                logging.execption(
                    "Incorrect reading of file \
                    either or reicever must be the same as file id"
                )
                raise
    return (in_tx, out_tx)


class Client:
    def __init__(self, id):
        self.id = id
        self.balance = read_balance(id)
        self.out_tx, self.in_tx = read_txs(id)


def init_clients():
    clients = []
    for i in range(0, NUM_CLIENTS):
        clients.append(Client(i))
    return clients


if __name__ == "__main__":
    clients = init_clients()
