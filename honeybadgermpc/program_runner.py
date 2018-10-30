from abc import abstractmethod


class ProgramRunner(object):

    @abstractmethod
    def add(self, program): raise NotImplementedError

    @abstractmethod
    async def join(self): raise NotImplementedError
