import logging
import os


def setupLogger(nodeId, name, logFile, level=logging.INFO):
    handler = logging.FileHandler(logFile)
    formatter = logging.Formatter(
        f"[{nodeId}]:" +
        '%(asctime)s:[%(filename)s:%(lineno)s]:[%(levelname)s]:%(message)s')
    handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger


class BenchmarkLogger(object):
    logger = None

    @staticmethod
    def get(nodeId):
        logFilePath = f"benchmark/benchmark_{nodeId}.log"
        os.makedirs(os.path.dirname(logFilePath), exist_ok=True)
        if BenchmarkLogger.logger is None:
            BenchmarkLogger.logger = setupLogger(nodeId, "BenchmarkLogger", logFilePath)
        BenchmarkLogger.logger.info(f"{'#'*10} NODE ID: {nodeId} {'#'*10}")
        return BenchmarkLogger.logger
