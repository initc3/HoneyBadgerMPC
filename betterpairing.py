from pypairing import * 
import random

def dupe_pyg1(pyg1):
    out = PyG1(0x5dbe6259, 0x8d313d76, 0x3237db17, 0xe5bc0654)
    out.copy(pyg1)
    return out
def dupe_pyfr(pyfr):
    out = PyFr("1")
    out.copy(pyfr)
    return out

class G1:
    def __init__(self, other=None):
        if other is None:
            self.pyg1 = PyG1(0, 0, 0, 1)
        #if type(other) is bytes:
        #    other = list(other)        
        if type(other) is list:
            assert len(other) == 2
            assert len(other[0]) == 6
            x=PyFqRepr(other[0][0], other[0][1], other[0][2], other[0][3], other[0][4], other[0][5])
            y=PyFqRepr(other[1][0], other[1][1], other[1][2], other[1][3], other[1][4], other[1][5])
            xq = PyFq(0,0,0,1)
            yq = PyFq(0,0,0,1)
            xq.from_repr(x)
            yq.from_repr(y)
            self.pyg1 = PyG1(0, 0, 0, 1)
            self.pyg1.loadfq(xq,yq)
        elif type(other) is PyG1:
            self.pyg1 = other
    def __str__(self):
        x = int(self.pyg1.projective()[4:102],0)
        y = int(self.pyg1.projective()[108:206],0)
        return "(" + str(x) + ", " + str(y) + ")"
    #def __bytes__(self):
    #    listlist = self.__getstate__()
    #    return bytes(listlist[0] + listlist[1])
    def __mul__(self, other):
        if type(other) is G1:
            out = dupe_pyg1(self.pyg1)
            out.add_assign(other.pyg1)
            return G1(out)
    def __imul__(self,other):
        if type(other) is G1:
            self.pyg1.add_assign(other.pyg1)
            return self
    def __pow__(self, other):
        if type(other) is int:
            out = G1(dupe_pyg1(self.pyg1))
            if other == 0:
                out.pyg1.zero()
                return out
            if other < 0:
                out.invert()
                other = -1 * other
            prodend = ZR(other)
            out.pyg1.mul_assign(prodend.val)
            return out
        elif type(other) is ZR:
            out = G1(dupe_pyg1(self.pyg1))
            out.pyg1.mul_assign(other.val)
            return out
        else:
            raise TypeError('Invalid exponentiation param. Expected ZR or int. Got '+ str(type(other)))
    #Thought this might be faster. It wasn't.
    #def __pow__(self, other):
    #    if type(other) not in [int, ZR]:
    #        raise TypeError('Invalid exponentiation param. Expected int or ZR. Got '+ str(type(other)))
    #    if type(other) is int:
    #        if other == 0:
    #            out = PyG1(0, 0, 0, 1)
    #            out.zero()
    #            return G1(out)
    #        r = 52435875175126190479447740508185965837690552500527637822603658699938581184513
    #        other = other % (r-1)
    #    else:
    #        other = int(other)
    #    out = dupe_pyg1(self.pyg1)
    #    if self.pp == []:
    #        self.initPP()
    #    i = 0
    #    #Hacky solution to my off by one error
    #    other -= 1
    #    while other > 0:
    #        if other % 2 == 1:
    #            out.add_assign(self.pp[i])
    #        i+= 1
    #        other = other >> 1
    #    return G1(out)
            
    def __ipow__(self, other):
        if type(other) is int:
            if other == 0:
                self.pyg1.zero()
                return self
            if other < 0:
                self.invert()
                other = other * -1
            self.pyg1.mul_assign(ZR(other).val)
            return self
        elif type(other) is ZR:
            self.pyg1.mul_assign(other)
            return self
        else:
            raise TypeError('Invalid exponentiation param. Expected ZR or int. Got '+ str(type(other)))
            
    def __eq__(self, other):
        if type(other) is not G1:
            return False
        return self.pyg1.equals(other.pyg1)
        
    def __getstate__(self):
        x = self.pyg1.projective()[6:102]
        y = self.pyg1.projective()[110:206]
        xlist = [x[80:96],x[64:80],x[48:64],x[32:48],x[16:32],x[0:16]]
        ylist = [y[80:96],y[64:80],y[48:64],y[32:48],y[16:32],y[0:16]]
        for i in range(6):
            xlist[i] = int(xlist[i],16)
            ylist[i] = int(ylist[i],16)
        return [xlist, ylist]
        
    def __setstate__(self, d):
        self.__init__(d)
        
    def invert(self):
        negone = PyFr(str(1))
        negone.negate()
        self.pyg1.mul_assign(negone)
        
    def duplicate(self):
        return G1(dupe_pyg1(self.pyg1))
     
    def projective(self):
        return self.pyg1.projective()
        
    def one():
        out = PyG1(0x5dbe6259, 0x8d313d76, 0x3237db17, 0xe5bc0654)
        out.zero()
        #'G1(x = Fq(0x17f1d3a73197d7942695638c4fa9ac0fc3688c4f9774b905a14e3a3f171bac586c55e83ff97a1aeffb3af00adb22c6bb) , y = Fq(0x08b3f481e3aaa0f1a09e30ed741d8ae4fcf5e095d5d00af600db18cb2c04b3edd03cc744a2888ae40caa232946c5e7e1) )'
        return G1(out)
    
    def rand(seed=None):
        if seed is None:
            seed = []
            for i in range(4):
                seed.append(random.SystemRandom().randint(0,4294967295))
            out = PyG1(seed[0],seed[1],seed[2],seed[3])
        else:
            assert seed is list
            assert len(seed) == 4
            out = PyG1(seed[0],seed[1],seed[2],seed[3])
        return G1(out)
        
class ZR:
    def __init__(self, val = None):
        self.pp = []
        if val == None:
            self.val = PyFr(0x5dbe6259, 0x8d313d76, 0x3237db17, 0xe5bc0654)
        elif type(val) is int:
            if val < 0:
                val = val * -1
                self.val = PyFr(str(val))
                self.val.negate()
            else:
                self.val = PyFr(str(val))
        elif type(val) is str:
            if val[1] == 'x':
                self.val = PyFr(val)
            elif int(val) < 0:
                intval = int(val) * -1
                self.val = PyFr(str(intval))
                self.val.negate()
            else:
                self.val = PyFr(val)
        elif type(val) is PyFr:
            self.val = val
    def __str__(self):
        hexstr = self.val.__str__()[3:-1]
        return str(int(hexstr,0))
    def __int__(self):
        hexstr = self.val.__str__()[3:-1]
        return int(hexstr,0)
    def __add__(self, other):
        if type(other) is ZR:
            out = dupe_pyfr(self.val)
            out.add_assign(other.val)
            return ZR(out)
        elif type(other) is int:
            out = dupe_pyfr(self.val)
            if other < 0:
                other *= -1
                addend = PyFr(str(other))
                addend.negate()
            else:
                addend = PyFr(str(other))
            out.add_assign(addend)
            return ZR(out)
        else:
            raise TypeError('Invalid addition param. Expected ZR or int. Got '+ str(type(other)))
    def __iadd__(self, other):
        if type(other) is ZR:
            self.val.add_assign(other.val)
            return self
        elif type(other) is int:
            if other < 0:
                other *= 1
                addend = PyFr(str(other))
                addend.negate()
            else:
                addend = PyFr(str(other))
            self.val.add_assign(addend)
            self.pp = []
            return self
        else:
            raise TypeError('Invalid addition param. Expected ZR or int. Got '+ str(type(other)))
    def __sub__(self, other):
        if type(other) is ZR:
            out = dupe_pyfr(self.val)
            out.sub_assign(other.val)
            return ZR(out)
        elif type(other) is int:
            out = dupe_pyfr(self.val)
            if other < 0:
                other *= -1
                subend = PyFr(str(other))
                subend.negate()
            else:
                subend = PyFr(str(other))
            out.sub_assign(subend)
            return ZR(out)
        else:
            raise TypeError('Invalid addition param. Expected ZR or int. Got '+ str(type(other)))
    def __isub__(self, other):
        if type(other) is ZR:
            self.val.sub_assign(other.val)
            return self
        elif type(other) is int:
            if other < 0:
                other *= 1
                subend = PyFr(str(other))
                subend.negate()
            else:
                subend = PyFr(str(other))
            self.val.sub_assign(subend)
            self.pp = []
            return self
        else:
            raise TypeError('Invalid addition param. Expected ZR or int. Got '+ str(type(other)))
    def __mul__(self, other):
        if type(other) is ZR:
            out = dupe_pyfr(self.val)
            out.mul_assign(other.val)
            return ZR(out)
        elif type(other) is int:
            out = dupe_pyfr(self.val)
            if other < 0:
                other *= -1
                prodend = PyFr(str(other))
                prodend.negate()
            else:
                prodend = PyFr(str(other))
            out.mul_assign(prodend)
            return ZR(out)
        else:
            raise TypeError('Invalid multiplication param. Expected ZR or int. Got '+ str(type(other)))
    def __imul__(self, other):
        if type(other) is ZR:
            self.val.mul_assign(other.val)
            return self
        elif type(other) is int:
            if other < 0:
                other *= -1
                prodend = PyFr(str(other))
                prodend.negate()
            else:
                prodend = PyFr(str(other))
            self.val.mul_assign(prodend)
            self.pp = []
            return self
        else:
            raise TypeError('Invalid multiplication param. Expected ZR or int. Got '+ str(type(other)))
            
    def __pow__(self, other):
        if type(other) is int:
            if other == 0:
                return ZR(1)
            r = 52435875175126190479447740508185965837690552500527637822603658699938581184513
            other = other % (r-1)
            out = dupe_pyfr(self.val)
            if self.pp == []:
                self.initPP()
            i = 0
            #Hacky solution to my off by one error
            other -= 1
            while other > 0:
                if other % 2 == 1:
                    out.mul_assign(self.pp[i])
                i+= 1
                other = other >> 1
            return ZR(out)
        elif type(other) is ZR:
            out = dupe_pyfr(self.val)
            if self.pp == []:
                self.initPP()
            i = 0
            #Hacky solution to my off by one error
            other = int(other)
            other -= 1
            while other > 0:
                if other % 2 == 1:
                    out.mul_assign(self.pp[i])
                i+= 1
                other = other >> 1
            return ZR(out)
        else:
            raise TypeError('Invalid multiplication param. Expected int or ZR. Got '+ str(type(other)))
    def __eq__(self, other):
        if type(other) is not ZR:
            return False
        return self.pyg1.equals(other.val)
        
    def __getstate__(self):
        return int(self)
        
    def __setstate__(self, d):
        self.__init__(d)
    
    def initPP(self):
        self.pp.append(dupe_pyfr(self.val))
        for i in range(1,255):
            power = dupe_pyfr(self.pp[i-1])
            power.square()
            self.pp.append(power)
        
    def rand():
        #megabignum = 3248875134290623212325429203829831876024364170316860259933542844758450336418538569901990710701240661702808867062612075657861768196242274635305077449545396068598317421057721935408562373834079015873933065667961469731886739181625866970316226171512545167081793907058686908697431878454091011239990119126
        r = 52435875175126190479447740508185965837690552500527637822603658699938581184513
        r = random.SystemRandom().randint(0,r-1)
        return ZR(str(r))
        
            
        
        