from .field import GF
from .elliptic_curve import Subgroup

# Jubjub

Field = GF.get(Subgroup.BLS12_381)

class Jubjub(object):
   def __init__(self, a = Field(-1), d = -(Field(10240)/Field(10241))):
      self.a = a
      self.d = d 

      self.disc = a * d * (a - d) * (a - d) * (a - d) * (a - d)
      self.j = 16 * (a * a + 14 * a * d + d * d) * (a * a + 14 * a * d + d * d) * \
               (a * a + 14 * a * d + d * d) / self.disc
      if not self.isSmooth():
         raise Exception("The curve %s is not smooth!" % self)


   def isSmooth(self):
      return self.disc != 0


   def testPoint(self, x, y):
      return self.a * x * x + y*y == 1 + self.d * x * x * y * y


   def __str__(self):
      return '%sx^2 + y^2 = 1 + %sx^2y^2' % (self.a, self.d)


   def __repr__(self):
      return str(self)


   def __eq__(self, other):
      return (self.a, self.d) == (other.a, other.d)


class Point(object):
   def __init__(self, x, y):
      self.curve = Jubjub() # the curve containing this point
      self.x = x
      self.y = y

      if not self.curve.testPoint(x,y):
         raise Exception("The point %s is not on the given curve %s!" % (self, curve))


   def __str__(self):
      return "(%r, %r)" % (self.x, self.y)


   def __repr__(self):
      return str(self)


   def __neg__(self):
      return Point(self.curve, Field(-self.x), self.y)


   def __add__(self, Q):
      if self.curve != Q.curve:
         raise Exception("Can't add points on different curves!")
      if isinstance(Q, Ideal):
         return self

      x1, y1, x2, y2 = self.x, self.y, Q.x, Q.y

      x3 = ((x1 * y2) + (y1 * x2)) / (1 + self.curve.d * x1 * x2 * y1 * y2)
      y3 = ((y1 * y2) + (x1 * x2)) / (1 - self.curve.d * x1 * x2 * y1 * y2)

      return Point(x3, y3)


   def double(self):
      return self + self


   def __sub__(self, Q):
      return self + -Q


   def __mul__(self, n):
      if not isinstance(n, int):
         raise Exception("Can't scale a point by something which isn't an int!")

      if n < 0:
         return -self * -n

      if n == 0:
         return Ideal(self.curve)

      Q = self
      R = self if n & 1 == 1 else Ideal(self.curve)

      i = 2
      while i <= n:
         Q += Q

         if n & i == i:
             R += Q

         i = i << 1

      return R


   def __rmul__(self, n):
      return self * n


   def __list__(self):
      return [self.x, self.y]


   def __eq__(self, other):
      if type(other) is Ideal:
         return False

      return self.x, self.y == other.x, other.y


   def __ne__(self, other):
      return not self == other
      

   def __getitem__(self, index):
      return [self.x, self.y][index]


class Ideal(Point):
   def __init__(self, curve):
      self.curve = curve

   def __neg__(self):
      return self

   def __str__(self):
      return "Ideal"

   def __add__(self, Q):
      if self.curve != Q.curve:
         raise Exception("Can't add points on different curves!")
      return Q

   def __mul__(self, n):
      if not isinstance(n, int):
         raise Exception("Can't scale a point by something which isn't an int!")
      else:
         return self

   def __eq__(self, other):
      return type(other) is Ideal

