// `clippy` is a code linting tool for improving code quality by catching
// common mistakes or strange code patterns. If the `cargo-clippy` feature
// is provided, all compiler warnings are prohibited.
#![cfg_attr(feature = "cargo-clippy", deny(warnings))]
#![cfg_attr(feature = "cargo-clippy", allow(inline_always))]
#![cfg_attr(feature = "cargo-clippy", allow(too_many_arguments))]
#![cfg_attr(feature = "cargo-clippy", allow(unreadable_literal))]
#![cfg_attr(feature = "cargo-clippy", allow(many_single_char_names))]
#![cfg_attr(feature = "cargo-clippy", allow(new_without_default_derive))]
#![cfg_attr(feature = "cargo-clippy", allow(write_literal))]
// Force public structures to implement Debug
#![deny(missing_debug_implementations)]

#![feature(specialization)]
#[macro_use]
extern crate pyo3;

use pyo3::prelude::*;


extern crate byteorder;
#[macro_use]
extern crate ff;
extern crate rand;

#[cfg(test)]
pub mod tests;

pub mod bls12_381;
use bls12_381::{G1, G2, Fr, Fq, Fq2, Fq6, Fq12, FqRepr, FrRepr};
mod wnaf;
pub use self::wnaf::Wnaf;

use ff::{Field,  PrimeField, PrimeFieldDecodingError, PrimeFieldRepr, ScalarEngine, SqrtField};
use std::error::Error;
use std::fmt;
use std::io::{self, Write};
use rand::{Rand, Rng, SeedableRng, XorShiftRng};

fn hex_to_bin (hexstr: &String) -> String
{
    let mut out = String::from("");
    let mut bin = "";
    //Ignore the 0x at the beginning
    for c in hexstr[2..].chars()
    {
        match c
        {
            '0' => bin = "0000",
            '1' => bin = "0001",
            '2' => bin = "0010",
            '3' => bin = "0011",
            '4' => bin = "0100",
            '5' => bin = "0101",
            '6' => bin = "0110",
            '7' => bin = "0111",
            '8' => bin = "1000",
            '9' => bin = "1001",
            'A'|'a' => bin = "1010",
            'B'|'b' => bin = "1011",
            'C'|'c' => bin = "1100",
            'D'|'d' => bin = "1101",
            'E'|'e' => bin = "1110",
            'F'|'f' => bin = "1111",
            _ => bin = ""
        }
        out.push_str(bin);
    }
    out
}

/// An "engine" is a collection of types (fields, elliptic curve groups, etc.)
/// with well-defined relationships. In particular, the G1/G2 curve groups are
/// of prime order `r`, and are equipped with a bilinear pairing function.
pub trait Engine: ScalarEngine {
    /// The projective representation of an element in G1.
    type G1: CurveProjective<
            Engine = Self,
            Base = Self::Fq,
            Scalar = Self::Fr,
            Affine = Self::G1Affine,
        >
        + From<Self::G1Affine>;

    /// The affine representation of an element in G1.
    type G1Affine: CurveAffine<
            Engine = Self,
            Base = Self::Fq,
            Scalar = Self::Fr,
            Projective = Self::G1,
            Pair = Self::G2Affine,
            PairingResult = Self::Fqk,
        >
        + From<Self::G1>;

    /// The projective representation of an element in G2.
    type G2: CurveProjective<
            Engine = Self,
            Base = Self::Fqe,
            Scalar = Self::Fr,
            Affine = Self::G2Affine,
        >
        + From<Self::G2Affine>;

    /// The affine representation of an element in G2.
    type G2Affine: CurveAffine<
            Engine = Self,
            Base = Self::Fqe,
            Scalar = Self::Fr,
            Projective = Self::G2,
            Pair = Self::G1Affine,
            PairingResult = Self::Fqk,
        >
        + From<Self::G2>;

    /// The base field that hosts G1.
    type Fq: PrimeField + SqrtField;

    /// The extension field that hosts G2.
    type Fqe: SqrtField;

    /// The extension field that hosts the target group of the pairing.
    type Fqk: Field;

    /// Perform a miller loop with some number of (G1, G2) pairs.
    fn miller_loop<'a, I>(i: I) -> Self::Fqk
    where
        I: IntoIterator<
            Item = &'a (
                &'a <Self::G1Affine as CurveAffine>::Prepared,
                &'a <Self::G2Affine as CurveAffine>::Prepared,
            ),
        >;

    /// Perform final exponentiation of the result of a miller loop.
    fn final_exponentiation(&Self::Fqk) -> Option<Self::Fqk>;

    /// Performs a complete pairing operation `(p, q)`.
    fn pairing<G1, G2>(p: G1, q: G2) -> Self::Fqk
    where
        G1: Into<Self::G1Affine>,
        G2: Into<Self::G2Affine>,
    {
        Self::final_exponentiation(&Self::miller_loop(
            [(&(p.into().prepare()), &(q.into().prepare()))].into_iter(),
        )).unwrap()
    }



}

#[pyfunction]
fn py_pairing(g1: &PyG1, g2: &PyG2) -> PyResult<()> {
    let a = g1.g1.into_affine();
    let b = g2.g2.into_affine();

    Ok(())
}

#[pyclass]
struct PyG1 {
   g1 : G1,
   pp : Vec<G1>,
   pplevel : usize
}

#[pymethods]
impl PyG1 {

    #[new]
    fn __new__(obj: &PyRawObject) -> PyResult<()>{
        let g =  G1::one();
        obj.init(|t| PyG1{
            g1: g,
            pp: Vec::new(),
            pplevel : 0
        })
    }

    fn rand(&mut self, s1: u32, s2: u32, s3: u32, s4: u32) -> PyResult<()>{
        let mut rng = XorShiftRng::from_seed([s1,s2,s3,s4]);
        let g = G1::rand(&mut rng);
        self.g1 = g;
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn load_fq_proj(&mut self, fqx: &PyFq, fqy: &PyFq, fqz: &PyFq) -> PyResult<()> {
        self.g1.x = fqx.fq;
        self.g1.y = fqy.fq;
        self.g1.z = fqz.fq;
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn load_fq_affine(&mut self, fqx: &PyFq, fqy: &PyFq) -> PyResult<()> {
        let mut a = self.g1.into_affine();
        a.x = fqx.fq;
        a.y = fqy.fq;
        self.g1 = a.into_projective();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn py_pairing_with(&self, g2: &PyG2, r: &mut PyFq12) -> PyResult<()> {
        let a = self.g1.into_affine();
        let b = g2.g2.into_affine();
        r.fq12 = a.pairing_with(&b);
        Ok(())
    }

    fn one(&mut self) -> PyResult<()> {
        self.g1 = G1::one();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn zero(&mut self) -> PyResult<()> {
        self.g1 = G1::zero();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn double(&mut self) -> PyResult<()> {
        self.g1.double();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn negate(&mut self) -> PyResult<()> {
        self.g1.negate();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn affine_negate(&mut self) -> PyResult<()> {
        let mut a = self.g1.into_affine();
        a.negate();
        self.g1 = a.into_projective();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn add_assign(&mut self, other: &Self) -> PyResult<()> {
        self.g1.add_assign(&other.g1);
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn sub_assign(&mut self, other: &Self) -> PyResult<()> {
        self.g1.sub_assign(&other.g1);
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    //Keeping previous code for multithreading in case it comes in handy
    //fn mul_assign(&mut self, py: Python, other:&PyFr) -> PyResult<()> {
    fn mul_assign(&mut self, other:&PyFr) -> PyResult<()>{
        //py.allow_threads(move || self.g1.mul_assign(other.fr));
        self.g1.mul_assign(other.fr);
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    /// a.equals(b)
    fn equals(&self, other: &Self) -> bool {
        self.g1 == other.g1
    }

    /// Copy other into self
    fn copy(&mut self, other: &Self) -> PyResult<()> {
        self.g1 = other.g1;
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    pub fn projective(&self) -> PyResult<String> {
        Ok(format!("({}, {}, {})",self.g1.x, self.g1.y, self.g1.z))
    }

    pub fn __str__(&self) -> PyResult<String> {
        Ok(format!("({}, {})",self.g1.into_affine().x, self.g1.into_affine().y))
    }

    //Creates preprocessing elements to allow fast scalar multiplication.
    //Level determines extent of precomputation
    fn preprocess(&mut self, level: usize) -> PyResult<()> {
        self.pplevel = level;
        //Everything requires a different kind of int (and only works with that kind)
        let mut base: u64 = 2;
        //calling pow on a u64 only accepts a u32 parameter for reasons undocumented
        base = base.pow(level as u32);
        let ppsize = (base as usize - 1) * (255 + level - 1)/(level);
        self.pp = Vec::with_capacity(ppsize);
        //FrRepr::from only takes a u64
        let factor = Fr::from_repr(FrRepr::from(base)).unwrap();
        self.pp.push(self.g1.clone());
        for i in 1..base-1
        {
            //Yes, I really need to expicitly cast the indexing variable...
            let mut next = self.pp[i as usize -1].clone();
            next.add_assign(&self.g1);
            self.pp.push(next);
        }
        //(x + y - 1) / y is a way to round up the integer division x/y
        for i in base-1..(base - 1) * (255 + level as u64 - 1)/(level as u64) {
            let mut next = self.pp[i as usize - (base-1) as usize].clone();
            //Wait, so add_assign takes a borrowed object but mul_assign doesn't?!?!?!?
            next.mul_assign(factor);
            self.pp.push(next);
        }
        //It's not really Ok. This is terrible.
        Ok(())
    }
    fn ppmul(&self, prodend: &PyFr, out: &mut PyG1) -> PyResult<()>
    {
        if self.pp.len() == 0
        {
            out.g1 = self.g1.clone();
            out.g1.mul_assign(prodend.fr);
        }
        else
        {
            let zero = Fr::from_repr(FrRepr::from(0)).unwrap();
            out.g1.mul_assign(zero);
            let hexstr = format!("{}", prodend.fr);
            let binstr = hex_to_bin(&hexstr);
            let mut buffer = 0usize;
            for (i, c) in binstr.chars().rev().enumerate()
            {
                if i%self.pplevel == 0 && buffer != 0
                {
                    //(2**level - 1)*(i/level - 1) + (buffer - 1)
                    out.g1.add_assign(&self.pp[(2usize.pow(self.pplevel as u32) - 1)*(i/self.pplevel - 1) + (buffer-1)]);
                    buffer = 0;
                }
                if c == '1'
                {
                    buffer = buffer + 2usize.pow((i%self.pplevel) as u32);
                }
            }
        }
        Ok(())
    }
}

#[pyclass]
struct PyG2 {
   g2 : G2,
   pp : Vec<G2>,
   pplevel : usize
}

#[pymethods]
impl PyG2 {

    #[new]
    fn __new__(obj: &PyRawObject) -> PyResult<()>{
        //let mut rng = XorShiftRng::from_seed([0,0,0,1]);
        //let g = G2::rand(&mut rng);
        let g =  G2::one();
        obj.init(|t| PyG2{
            g2: g,
            pp: Vec::new(),
            pplevel : 0
        })
    }

    fn rand(&mut self, s1: u32, s2: u32, s3: u32, s4: u32) -> PyResult<()>{
        let mut rng = XorShiftRng::from_seed([s1,s2,s3,s4]);
        let g = G2::rand(&mut rng);
        self.g2 = g;
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn load_fq_proj(&mut self, fq2x: &PyFq2, fq2y: &PyFq2, fq2z: &PyFq2) -> PyResult<()> {
        self.g2.x = fq2x.fq2;
        self.g2.y = fq2y.fq2;
        self.g2.z = fq2z.fq2;
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn load_fq_affine(&mut self, fq2x: &PyFq2, fq2y: &PyFq2) -> PyResult<()> {
        let mut a = self.g2.into_affine();
        a.x = fq2x.fq2;
        a.y = fq2y.fq2;
        self.g2 = a.into_projective();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn py_pairing_with(&self, g1: &PyG1, r: &mut PyFq12) -> PyResult<()> {
        let a = self.g2.into_affine();
        let b = g1.g1.into_affine();
        r.fq12 = a.pairing_with(&b);
        Ok(())
    }

    fn one(&mut self) -> PyResult<()> {
        self.g2 = G2::one();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn zero(&mut self) -> PyResult<()> {
        self.g2 = G2::zero();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn double(&mut self) -> PyResult<()> {
        self.g2.double();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn negate(&mut self) -> PyResult<()> {
        self.g2.negate();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn affine_negate(&mut self) -> PyResult<()> {
        let mut a = self.g2.into_affine();
        a.negate();
        self.g2 = a.into_projective();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn add_assign(&mut self, other: &Self) -> PyResult<()> {
        self.g2.add_assign(&other.g2);
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn sub_assign(&mut self, other: &Self) -> PyResult<()> {
        self.g2.sub_assign(&other.g2);
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn mul_assign(&mut self, other:&PyFr) -> PyResult<()> {
        self.g2.mul_assign(other.fr);
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    /// a.equals(b)
    fn equals(&self, other: &Self) -> bool {
        self.g2 == other.g2
    }

    /// Copy other into self
    fn copy(&mut self, other: &Self) -> PyResult<()> {
        self.g2 = other.g2;
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }
    pub fn projective(&self) -> PyResult<String> {
        Ok(format!("({}, {}, {})",self.g2.x, self.g2.y, self.g2.z))
    }
    pub fn __str__(&self) -> PyResult<String> {
        Ok(format!("({}, {})",self.g2.into_affine().x, self.g2.into_affine().y))
    }
    fn preprocess(&mut self, level: usize) -> PyResult<()> {
        self.pplevel = level;
        let mut base: u64 = 2;
        base = base.pow(level as u32);
        let ppsize = (base as usize - 1) * (255 + level - 1)/(level);
        self.pp = Vec::with_capacity(ppsize);
        let factor = Fr::from_repr(FrRepr::from(base)).unwrap();
        self.pp.push(self.g2.clone());
        for i in 1..base-1
        {
            let mut next = self.pp[i as usize -1].clone();
            next.add_assign(&self.g2);
            self.pp.push(next);
        }
        //(x + y - 1) / y is a way to round up the integer division x/y
        for i in base-1..(base - 1) * (255 + level as u64 - 1)/(level as u64) {
            let mut next = self.pp[i as usize - (base-1) as usize].clone();
            next.mul_assign(factor);
            self.pp.push(next);
        }
        Ok(())
    }
    fn ppmul(&self, prodend: &PyFr, out: &mut PyG2) -> PyResult<()>
    {
        if self.pp.len() == 0
        {
            out.g2 = self.g2.clone();
            out.g2.mul_assign(prodend.fr);
        }
        else
        {
            let zero = Fr::from_repr(FrRepr::from(0)).unwrap();
            out.g2.mul_assign(zero);
            let hexstr = format!("{}", prodend.fr);
            let binstr = hex_to_bin(&hexstr);
            let mut buffer = 0usize;
            for (i, c) in binstr.chars().rev().enumerate()
            {
                if i%self.pplevel == 0 && buffer != 0
                {
                    //(2**level - 1)*(i/level - 1) + (buffer - 1)
                    out.g2.add_assign(&self.pp[(2usize.pow(self.pplevel as u32) - 1)*(i/self.pplevel - 1) + (buffer-1)]);
                    buffer = 0;
                }
                if c == '1'
                {
                    buffer = buffer + 2usize.pow((i%self.pplevel) as u32);
                }
            }
        }
        Ok(())
    }

}

#[pyclass]
struct PyFr {
   fr : Fr
}

#[pymethods]
impl PyFr {

    #[new]
    fn __new__(obj: &PyRawObject, s1: u64, s2: u64, s3: u64, s4: u64) -> PyResult<()>{
        let f = Fr::from_repr(FrRepr([s1,s2,s3,s4])).unwrap();
        obj.init(|t| PyFr{
            fr: f,
        })
    }
    
    fn one(&mut self) -> PyResult<()> {
        self.fr = Fr::one();
        Ok(())
    }

    fn zero(&mut self) -> PyResult<()> {
        self.fr = Fr::zero();
        Ok(())
    }

    fn negate(&mut self) -> PyResult<()> {
        self.fr.negate();
        Ok(())
    }

    fn inverse(&mut self) -> PyResult<()> {
        self.fr = self.fr.inverse().unwrap();
        Ok(())
    }

    fn double(&mut self) -> PyResult<()> {
        self.fr.double();
        Ok(())
    }

    fn square(&mut self) -> PyResult<()> {
        self.fr.square();
        Ok(())
    }

    fn pow(&mut self, s1: u64, s2: u64, s3: u64, s4: u64, s5: u64, s6:u64) -> PyResult<()> {
        self.fr.pow([s1,s2,s3,s4,s5,s6]);
        Ok(())
    }

    fn add_assign(&mut self, other: &Self) -> PyResult<()> {
        self.fr.add_assign(&other.fr);
        Ok(())
    }

    fn sub_assign(&mut self, other: &Self) -> PyResult<()> {
        self.fr.sub_assign(&other.fr);
        Ok(())
    }

    fn mul_assign(&mut self, other: &Self) -> PyResult<()> {
        self.fr.mul_assign(&other.fr);
        Ok(())
    }
    
    fn pow_assign(&mut self, other: &PyFr) -> PyResult<()> {
        self.fr = self.fr.pow(&other.fr.into_repr());
        Ok(())
    }

    /// a.equals(b)
    fn equals(&self, other: &Self) -> bool {
        self.fr == other.fr
    }

    /// Copy other into self
    fn copy(&mut self, other: &Self) -> PyResult<()> {
        self.fr = other.fr;
        Ok(())
    }

    pub fn __str__(&self) -> PyResult<String> {
        Ok(format!("{}",self.fr))
    }

}

#[pyclass]
struct PyFq {
    fq : Fq
}
 #[pymethods]
impl PyFq {
    #[new]
    fn __new__(obj: &PyRawObject) -> PyResult<()>{
        let f =  Fq::zero();
        obj.init(|t| PyFq{
            fq: f,
        })
    }
    fn from_repr(&mut self, py_fq_repr: &PyFqRepr) -> PyResult<()> {
        let f = Fq::from_repr(py_fq_repr.fq_repr).unwrap();
        self.fq = f;
        Ok(())
    }
}

#[pyclass]
struct PyFq2 {
    fq2 : Fq2
}
 #[pymethods]
impl PyFq2 {
    #[new]
    fn __new__(obj: &PyRawObject) -> PyResult<()>{
        let f =  Fq2::zero();
        obj.init(|t| PyFq2{
            fq2: f,
        })
    }
    fn from_repr(&mut self, py_fq_repr: &PyFqRepr, py_fq_repr2: &PyFqRepr) -> PyResult<()> {
        let c0 = Fq::from_repr(py_fq_repr.fq_repr).unwrap();
        let c1 = Fq::from_repr(py_fq_repr2.fq_repr).unwrap();
        self.fq2.c0 = c0;
        self.fq2.c1 = c1;
        Ok(())
    }
}

#[pyclass]
struct PyFq6 {
    fq6 : Fq6
}
 #[pymethods]
impl PyFq6 {
    #[new]
    fn __new__(obj: &PyRawObject) -> PyResult<()>{
        let f =  Fq6::zero();
        obj.init(|t| PyFq6{
            fq6: f,
        })
    }
}

#[pyclass]
struct PyFqRepr {
    fq_repr : FqRepr
}
 #[pymethods]
impl PyFqRepr {
     #[new]
    fn __new__(obj: &PyRawObject, s1: u64, s2: u64, s3: u64, s4: u64, s5: u64, s6: u64) -> PyResult<()>{
        let f = FqRepr([s1,s2,s3,s4,s5,s6]);
        obj.init(|t| PyFqRepr{
            fq_repr: f,
        })
    }
}

#[pyclass]
struct PyFq12 {
    fq12 : Fq12,
    pp : Vec<Fq12>,
    pplevel : usize
}

#[pymethods]
impl PyFq12 {
    #[new]
    fn __new__(obj: &PyRawObject) -> PyResult<()>{
        let q =  Fq12::zero();
        obj.init(|t| PyFq12{
            fq12: q,
            pp: Vec::new(),
            pplevel : 0
        })
    }
    fn from_strs(&mut self, s1: &str, s2: &str, s3: &str, s4: &str, s5: &str, s6: &str, s7: &str, s8: &str, s9: &str, s10: &str, s11: &str, s12: &str) -> PyResult<()> {
        let c0 = Fq6 {
            c0: Fq2 {
                c0: Fq::from_str(s1).unwrap(),
                c1: Fq::from_str(s2).unwrap()
            },
            c1: Fq2 {
                c0: Fq::from_str(s3).unwrap(),
                c1: Fq::from_str(s4).unwrap()
            },
            c2: Fq2 {
                c0: Fq::from_str(s5).unwrap(),
                c1: Fq::from_str(s6).unwrap()
            }
        };
        let c1 = Fq6 {
            c0: Fq2 {
                c0: Fq::from_str(s7).unwrap(),
                c1: Fq::from_str(s8).unwrap()
            },
            c1: Fq2 {
                c0: Fq::from_str(s9).unwrap(),
                c1: Fq::from_str(s10).unwrap()
            },
            c2: Fq2 {
                c0: Fq::from_str(s11).unwrap(),
                c1: Fq::from_str(s12).unwrap()
            }
        };
        self.fq12.c0 = c0;
        self.fq12.c1 = c1;
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    pub fn __str__(&self) -> PyResult<String> {
        Ok(format!("({} + {} * w)",self.fq12.c0, self.fq12.c1 ))
    }

    pub fn __repr__(&self) -> PyResult<String> {
        Ok(format!("({} + {} * w)",self.fq12.c0, self.fq12.c1 ))
    }

    fn rand(&mut self, s1: u32, s2: u32, s3: u32, s4: u32) -> PyResult<()> {
        let mut rng = XorShiftRng::from_seed([s1,s2,s3,s4]);
        self.fq12 = Fq12::rand(&mut rng);
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn add_assign(&mut self, other: &Self) -> PyResult<()> {
        self.fq12.add_assign(&other.fq12);
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn sub_assign(&mut self, other: &Self) -> PyResult<()> {
        self.fq12.sub_assign(&other.fq12);
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn mul_assign(&mut self, other: &Self) -> PyResult<()> {
        self.fq12.mul_assign(&other.fq12);
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }
    
    fn pow_assign(&mut self, other: &PyFr) -> PyResult<()> {
        self.fq12 = self.fq12.pow(&other.fr.into_repr());
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }
    
    fn inverse(&mut self) -> PyResult<()> {
        self.fq12 = self.fq12.inverse().unwrap();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn conjugate(&mut self) -> PyResult<()> {
        self.fq12.conjugate();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }
    
    fn preprocess(&mut self, level: usize) -> PyResult<()> {
        self.pplevel = level;
        let mut base: u64 = 2;
        base = base.pow(level as u32);
        let ppsize = (base as usize - 1) * (255 + level - 1)/(level);
        self.pp = Vec::with_capacity(ppsize);
        let factor = Fr::from_repr(FrRepr::from(base)).unwrap();
        self.pp.push(self.fq12.clone());
        for i in 1..base-1
        {
            let mut next = self.pp[i as usize -1].clone();
            next.mul_assign(&self.fq12);
            self.pp.push(next);
        }
        for i in base-1..(base - 1) * (255 + level as u64 - 1)/(level as u64) {
            let mut next = self.pp[i as usize - (base-1) as usize].clone();
            //This needs to be pow lolol!!!
            next = next.pow(factor.into_repr());
            //next.mul_assign(factor);
            self.pp.push(next);
        }
        Ok(())
    }
    fn pppow(&self, prodend: &PyFr, out: &mut PyFq12) -> PyResult<()>
    {
        if self.pp.len() == 0
        {
            out.fq12 = self.fq12.clone();
            //pow assign
            out.fq12 = out.fq12.pow(&prodend.fr.into_repr());
            //out.fq.mul_assign(prodend.fr);
        }
        else
        {
            let zero = Fr::from_repr(FrRepr::from(0)).unwrap();
            //powassign
            out.fq12 = out.fq12.pow(FrRepr::from(0));
            //out.fq12.mul_assign(zero);
            let hexstr = format!("{}", prodend.fr);
            let binstr = hex_to_bin(&hexstr);
            let mut buffer = 0usize;
            for (i, c) in binstr.chars().rev().enumerate()
            {
                if i%self.pplevel == 0 && buffer != 0
                {
                    //(2**level - 1)*(i/level - 1) + (buffer - 1)
                    out.fq12.mul_assign(&self.pp[(2usize.pow(self.pplevel as u32) - 1)*(i/self.pplevel - 1) + (buffer-1)]);
                    buffer = 0;
                }
                if c == '1'
                {
                    buffer = buffer + 2usize.pow((i%self.pplevel) as u32);
                }
            }
        }
        Ok(())
    }

    fn one(&mut self) -> PyResult<()> {
        self.fq12 = Fq12::one();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn zero(&mut self) -> PyResult<()> {
        self.fq12 = Fq12::zero();
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }

    fn equals(&self, other: &Self) -> bool {
        self.fq12 == other.fq12
    }

    /// Copy other into self
    fn copy(&mut self, other: &Self) -> PyResult<()> {
        self.fq12 = other.fq12;
        if self.pplevel != 0 {
            self.pp = Vec::new();
            self.pplevel = 0;
        }
        Ok(())
    }
}

#[pyfunction]
fn vec_sum(a: &PyList) -> PyResult<String>{
    let mut sum =  Fr::from_str("0").unwrap();
    for item in a.iter(){
        let myfr: &PyFr = item.try_into().unwrap();
        sum.add_assign(&myfr.fr);
    }
    Ok(format!("{}",sum))
}

#[pymodinit]
fn pypairing(py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PyG1>()?;
    m.add_class::<PyG2>()?;
    m.add_class::<PyFq>()?;
    m.add_class::<PyFqRepr>()?;
    m.add_class::<PyFq2>()?;
    m.add_class::<PyFq6>()?;
    m.add_class::<PyFq12>()?;
    m.add_class::<PyFr>()?;
    m.add_function(wrap_function!(py_pairing)).unwrap();
    //m.add_function(wrap_function!(vec_sum))?;
    m.add_function(wrap_function!(vec_sum)).unwrap();
    Ok(())
}


/// Projective representation of an elliptic curve point guaranteed to be
/// in the correct prime order subgroup.
pub trait CurveProjective:
    PartialEq
    + Eq
    + Sized
    + Copy
    + Clone
    + Send
    + Sync
    + fmt::Debug
    + fmt::Display
    + rand::Rand
    + 'static
{
    type Engine: Engine<Fr = Self::Scalar>;
    type Scalar: PrimeField + SqrtField;
    type Base: SqrtField;
    type Affine: CurveAffine<Projective = Self, Scalar = Self::Scalar>;

    /// Returns the additive identity.
    fn zero() -> Self;

    /// Returns a fixed generator of unknown exponent.
    fn one() -> Self;

    /// Determines if this point is the point at infinity.
    fn is_zero(&self) -> bool;

    /// Normalizes a slice of projective elements so that
    /// conversion to affine is cheap.
    fn batch_normalization(v: &mut [Self]);

    /// Checks if the point is already "normalized" so that
    /// cheap affine conversion is possible.
    fn is_normalized(&self) -> bool;

    /// Doubles this element.
    fn double(&mut self);

    /// Adds another element to this element.
    fn add_assign(&mut self, other: &Self);

    /// Subtracts another element from this element.
    fn sub_assign(&mut self, other: &Self) {
        let mut tmp = *other;
        tmp.negate();
        self.add_assign(&tmp);
    }

    /// Adds an affine element to this element.
    fn add_assign_mixed(&mut self, other: &Self::Affine);

    /// Negates this element.
    fn negate(&mut self);

    /// Performs scalar multiplication of this element.
    fn mul_assign<S: Into<<Self::Scalar as PrimeField>::Repr>>(&mut self, other: S);

    /// Converts this element into its affine representation.
    fn into_affine(&self) -> Self::Affine;

    /// Recommends a wNAF window table size given a scalar. Always returns a number
    /// between 2 and 22, inclusive.
    fn recommended_wnaf_for_scalar(scalar: <Self::Scalar as PrimeField>::Repr) -> usize;

    /// Recommends a wNAF window size given the number of scalars you intend to multiply
    /// a base by. Always returns a number between 2 and 22, inclusive.
    fn recommended_wnaf_for_num_scalars(num_scalars: usize) -> usize;
}

/// Affine representation of an elliptic curve point guaranteed to be
/// in the correct prime order subgroup.
pub trait CurveAffine:
    Copy + Clone + Sized + Send + Sync + fmt::Debug + fmt::Display + PartialEq + Eq + 'static
{
    type Engine: Engine<Fr = Self::Scalar>;
    type Scalar: PrimeField + SqrtField;
    type Base: SqrtField;
    type Projective: CurveProjective<Affine = Self, Scalar = Self::Scalar>;
    type Prepared: Clone + Send + Sync + 'static;
    type Uncompressed: EncodedPoint<Affine = Self>;
    type Compressed: EncodedPoint<Affine = Self>;
    type Pair: CurveAffine<Pair = Self>;
    type PairingResult: Field;

    /// Returns the additive identity.
    fn zero() -> Self;

    /// Returns a fixed generator of unknown exponent.
    fn one() -> Self;

    /// Determines if this point represents the point at infinity; the
    /// additive identity.
    fn is_zero(&self) -> bool;

    /// Negates this element.
    fn negate(&mut self);

    /// Performs scalar multiplication of this element with mixed addition.
    fn mul<S: Into<<Self::Scalar as PrimeField>::Repr>>(&self, other: S) -> Self::Projective;

    /// Prepares this element for pairing purposes.
    fn prepare(&self) -> Self::Prepared;

    /// Perform a pairing
    fn pairing_with(&self, other: &Self::Pair) -> Self::PairingResult;

    /// Converts this element into its affine representation.
    fn into_projective(&self) -> Self::Projective;

    /// Converts this element into its compressed encoding, so long as it's not
    /// the point at infinity.
    fn into_compressed(&self) -> Self::Compressed {
        <Self::Compressed as EncodedPoint>::from_affine(*self)
    }

    /// Converts this element into its uncompressed encoding, so long as it's not
    /// the point at infinity.
    fn into_uncompressed(&self) -> Self::Uncompressed {
        <Self::Uncompressed as EncodedPoint>::from_affine(*self)
    }
}

/// An encoded elliptic curve point, which should essentially wrap a `[u8; N]`.
pub trait EncodedPoint:
    Sized + Send + Sync + AsRef<[u8]> + AsMut<[u8]> + Clone + Copy + 'static
{
    type Affine: CurveAffine;

    /// Creates an empty representation.
    fn empty() -> Self;

    /// Returns the number of bytes consumed by this representation.
    fn size() -> usize;

    /// Converts an `EncodedPoint` into a `CurveAffine` element,
    /// if the encoding represents a valid element.
    fn into_affine(&self) -> Result<Self::Affine, GroupDecodingError>;

    /// Converts an `EncodedPoint` into a `CurveAffine` element,
    /// without guaranteeing that the encoding represents a valid
    /// element. This is useful when the caller knows the encoding is
    /// valid already.
    ///
    /// If the encoding is invalid, this can break API invariants,
    /// so caution is strongly encouraged.
    fn into_affine_unchecked(&self) -> Result<Self::Affine, GroupDecodingError>;

    /// Creates an `EncodedPoint` from an affine point, as long as the
    /// point is not the point at infinity.
    fn from_affine(affine: Self::Affine) -> Self;
}

/// An error that may occur when trying to decode an `EncodedPoint`.
#[derive(Debug)]
pub enum GroupDecodingError {
    /// The coordinate(s) do not lie on the curve.
    NotOnCurve,
    /// The element is not part of the r-order subgroup.
    NotInSubgroup,
    /// One of the coordinates could not be decoded
    CoordinateDecodingError(&'static str, PrimeFieldDecodingError),
        //assert!(a.pairing_with(&b) == pairing(a, b));

    /// The compression mode of the encoded element was not as expected
    UnexpectedCompressionMode,
    /// The encoding contained bits that should not have been set
    UnexpectedInformation,
}

impl Error for GroupDecodingError {
    fn description(&self) -> &str {
        match *self {
            GroupDecodingError::NotOnCurve => "coordinate(s) do not lie on the curve",
            GroupDecodingError::NotInSubgroup => "the element is not part of an r-order subgroup",
            GroupDecodingError::CoordinateDecodingError(..) => "coordinate(s) could not be decoded",
            GroupDecodingError::UnexpectedCompressionMode => {
                "encoding has unexpected compression mode"
            }
            GroupDecodingError::UnexpectedInformation => "encoding has unexpected information",
        }
    }
}

impl fmt::Display for GroupDecodingError {
    fn fmt(&self, f: &mut fmt::Formatter) -> Result<(), fmt::Error> {
        match *self {
            GroupDecodingError::CoordinateDecodingError(description, ref err) => {
                write!(f, "{} decoding error: {}", description, err)
            }
            _ => write!(f, "{}", self.description()),
        }
    }
}
