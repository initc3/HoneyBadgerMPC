if __name__ == "__main__":
    import asyncio

    import toml

    from apps.robohash.mpcprogrunner import MPCProgRunner
    from apps.robohash.preprocessor import PreProcessor

    from apps.sdk.httpserver import HTTPServer
    from apps.sdk.mpcserver import runner
    from apps.sdk.parsers import ServerArgumentParser

    from honeybadgermpc.progs.mixins.constants import MixinConstants
    from honeybadgermpc.progs.mixins.share_arithmetic import (
        BeaverMultiply,
        BeaverMultiplyArrays,
    )

    # arg parsing
    parser = ServerArgumentParser()
    args = parser.parse_args()

    # read config and merge with cmdline args -- cmdline args have priority
    config = toml.load(args.config_path)
    _args = parser.post_process_args(args, config)

    asyncio.run(
        runner(
            "sid",
            _args["myid"],
            host=_args["host"],
            mpc_port=_args["mpc_port"],
            peers=_args["peers"],
            w3=_args["w3"],
            contract_context=_args["contract_context"],
            db=_args["db"],
            http_context={"host": _args["host"], "port": _args["http_port"]},
            preprocessor_class=PreProcessor,
            httpserver_class=HTTPServer,
            mpcprogrunner_class=MPCProgRunner,
            mpc_config={
                MixinConstants.MultiplyShareArray: BeaverMultiplyArrays(),
                MixinConstants.MultiplyShare: BeaverMultiply(),
            },
        )
    )
