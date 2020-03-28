from pathlib import Path

PARENT_DIR = Path(__file__).resolve().parent
PUBLIC_DATA_DIR = "public-data"
CONTRACT_ADDRESS_FILENAME = "contract_address"
CONTRACT_ADDRESS_FILEPATH = PARENT_DIR.joinpath(
    PUBLIC_DATA_DIR, CONTRACT_ADDRESS_FILENAME
)
