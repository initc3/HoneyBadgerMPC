from abc import abstractmethod


class ProgramRunner(object):
    @abstractmethod
    def add(self, program, **kwargs):
        raise NotImplementedError

    @abstractmethod
    async def join(self):
        raise NotImplementedError
