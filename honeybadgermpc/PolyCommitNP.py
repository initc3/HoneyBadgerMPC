from honeybadgermpc.betterpairing import *

class PolyCommitNP:
    def __init__ (self, t, pk):
        self.g = pk[0].duplicate()
        self.h = pk[1].duplicate()
        self.t = t

    def commit (self, poly, secretpoly):
        #initPP?
        cs = []
        for i in range(self.t+1):
            c = (self.g**poly[i])*(self.h**secretpoly[i])
            cs.append(c)
        return cs

    def verify_eval(self, c, i, polyeval, secretpolyeval, witness=None):
        lhs = G1.one()
        for j in range(len(c)):
            lhs = lhs * c[j]**(i**j)
        rhs = (self.g**polyeval)*(self.h**secretpolyeval)
        return  lhs == rhs