import argparse
import asyncio
from pathlib import Path

PARENT_DIR = Path(__file__).resolve().parent


async def main(config_file):
    from apps.toolkit.client import Client

    client = Client.from_toml_config(config_file)
    await client.join()


if __name__ == "__main__":
    # arg parsing
    default_config_path = PARENT_DIR.joinpath("client.toml")
    parser = argparse.ArgumentParser(description="MPC client.")
    parser.add_argument(
        "-c",
        "--config-file",
        default=str(default_config_path),
        help=f"Configuration file to use. Defaults to '{default_config_path}'.",
    )
    args = parser.parse_args()

    # Launch a client
    asyncio.run(main(Path(args.config_file).expanduser()))
