import random
import os
import shutil
import logging
from apps.netting.config.config import (
    NUMTX,
    NUM_CLIENTS,
    mu_tx,
    mu_bal,
    sigma_tx,
    sigma_bal,
    tx_file_prefix,
    tx_file_suffix,
    bal_file_prefix,
    bal_file_suffix,
    NETTING_BASE_DIR,
)


def open_tx_files():
    f = []
    for i in range(0, NUM_CLIENTS):
        file = tx_file_prefix + str(i) + tx_file_suffix
        f.append(open(NETTING_BASE_DIR + "data/" + file, "a+"))
    return f


def open_bal_files():
    f = []
    for i in range(0, NUM_CLIENTS):
        file = bal_file_prefix + str(i) + bal_file_suffix
        f.append(open(NETTING_BASE_DIR + "data/" + file, "a+"))
    return f


def close_files(files):
    for f in files:
        f.close()


def gen_data_files():

    f = open_tx_files()

    for i in range(0, NUMTX):
        # sample random sender: Samples from 1 through to N
        sender = random.randint(0, NUM_CLIENTS - 1)

        # sample reciever such that it is different from sender
        reciever = None
        while True:
            reciever = random.randint(0, NUM_CLIENTS - 1)
            if sender != reciever:
                break

        # sample amount from a normal distribution
        amount = random.gauss(mu_tx, sigma_tx)
        # Add the tx to sender file
        f[sender].write(
            str(sender)
            + ","
            + str(reciever)
            + ","
            + str.format("{0:.2f}", amount)
            + "\n"
        )
        # Add tx to reciever file
        f[reciever].write(
            str(sender)
            + ","
            + str(reciever)
            + ","
            + str.format("{0:.2f}", amount)
            + "\n"
        )

    close_files(f)

    f = open_bal_files()

    for i in range(0, NUM_CLIENTS):
        f[i].write(str.format("{0:.2f}", random.gauss(mu_bal, sigma_bal)) + "\n")

    close_files(f)


def clean_files():
    path = NETTING_BASE_DIR + "data/"
    try:
        shutil.rmtree(path)
    except Exception as e:
        logging.exception(e)
        pass
    os.makedirs(NETTING_BASE_DIR + "data")


def main():
    # clean data folder
    clean_files()
    # recreate all data
    gen_data_files()


if __name__ == "__main__":
    main()
