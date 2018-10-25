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
use bls12_381::{G1, G2, Fr, Fq, Fq12, FqRepr};
mod wnaf;
pub use self::wnaf::Wnaf;

use ff::{Field,  PrimeField, PrimeFieldDecodingError, PrimeFieldRepr, ScalarEngine, SqrtField};
use std::error::Error;
use std::fmt;
use rand::{Rand, Rng, SeedableRng, XorShiftRng};


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
   g1 : G1
}

#[pymethods]
impl PyG1 {
    
    #[new]
    fn __new__(obj: &PyRawObject, s1: u32, s2: u32, s3: u32, s4: u32) -> PyResult<()>{
        let mut rng = XorShiftRng::from_seed([s1,s2,s3,s4]);
        let g =  G1::rand(&mut rng);
        obj.init(|t| PyG1{
            g1: g,
        })
    }
    
    fn load_fq_proj(&mut self, fqx: &PyFq, fqy: &PyFq, fqz: &PyFq) -> PyResult<()> {
        self.g1.x = fqx.fq;
        self.g1.y = fqy.fq;
        self.g1.z = fqz.fq;
        Ok(())
    }
    
    fn load_fq_affine(&mut self, fqx: &PyFq, fqy: &PyFq) -> PyResult<()> {
        let mut a = self.g1.into_affine();
        a.x = fqx.fq;
        a.y = fqy.fq;
        self.g1 = a.into_projective();
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
        Ok(())
    }
   
    fn zero(&mut self) -> PyResult<()> {
        self.g1 = G1::zero();
        Ok(())
    }

    fn double(&mut self) -> PyResult<()> {
        self.g1.double();
        Ok(())
    }
    
    fn negate(&mut self) -> PyResult<()> {
        self.g1.negate();
        Ok(())
    }
    
    fn affine_negate(&mut self) -> PyResult<()> {
        let mut a = self.g1.into_affine();
        a.negate();
        self.g1 = a.into_projective();
        Ok(())
    }
    
    fn add_assign(&mut self, other: &Self) -> PyResult<()> {
        self.g1.add_assign(&other.g1);
        Ok(())
    }

    fn sub_assign(&mut self, other: &Self) -> PyResult<()> {
        self.g1.sub_assign(&other.g1);
        Ok(())
    }

    fn mul_assign(&mut self, other:&PyFr) -> PyResult<()> {
        self.g1.mul_assign(other.fr);
        Ok(())
    }

    /// a.equals(b)
    fn equals(&self, other: &Self) -> bool {
        self.g1 == other.g1
    }
    
    /// Copy other into self
    fn copy(&mut self, other: &Self) -> PyResult<()> {
        self.g1 = other.g1;
        Ok(())
    }
    pub fn projective(&self) -> PyResult<String> {
        Ok(format!("({}, {}, {})",self.g1.x, self.g1.y, self.g1.z))
    }
    pub fn __str__(&self) -> PyResult<String> {
        Ok(format!("({}, {})",self.g1.into_affine().x, self.g1.into_affine().y))                
    }

}

#[pyclass]
struct PyG2 {
    g2 : G2
}

#[pymethods]
impl PyG2 {
    #[new]
    fn __new__(obj: &PyRawObject, s1: u32, s2: u32, s3: u32, s4: u32) -> PyResult<()>{
        let mut rng = XorShiftRng::from_seed([s1,s2,s3,s4]);
        let g =  G2::rand(&mut rng);
        obj.init(|t| PyG2{
            g2: g,
        })
    }
    
    fn py_pairing_with(&self, g1: &PyG1, r: &mut PyFq12) -> PyResult<()> {
        let a = self.g2.into_affine();
        let b = g1.g1.into_affine();
        r.fq12 = a.pairing_with(&b);
        Ok(())
    }

    fn one(&mut self) -> PyResult<()> {
        self.g2 = G2::one();
        Ok(())
    }
   
    fn zero(&mut self) -> PyResult<()> {
        self.g2 = G2::zero();
        Ok(())
    }
    
    fn double(&mut self) -> PyResult<()> {
        self.g2.double();
        Ok(())
    }
    
    fn add_assign(&mut self, other: &Self) -> PyResult<()> {
        self.g2.add_assign(&other.g2);
        Ok(())
    }

    fn sub_assign(&mut self, other: &Self) -> PyResult<()> {
        self.g2.sub_assign(&other.g2);
        Ok(())
    }
    
    fn mul_assign(&mut self, other:&PyFr) -> PyResult<()> {
        self.g2.mul_assign(other.fr);
        Ok(())
    }
    
    /// a.equals(b)
    fn equals(&self, other: &Self) -> bool {
        self.g2 == other.g2
    }
    
    /// Copy other into self
    fn copy(&mut self, other: &Self) -> PyResult<()> {
        self.g2 = other.g2;
        Ok(())
    }
   
    pub fn __str__(&self) -> PyResult<String> {
        Ok(format!("({}, {})",self.g2.into_affine().x, self.g2.into_affine().y))                
    }

}

#[pyclass]
struct PyFr {
   fr : Fr
}

#[pymethods]
impl PyFr {
    
    #[new]
    //fn __new__(obj: &PyRawObject, s1: u32, s2: u32, s3: u32, s4: u32) -> PyResult<()>{
    //    let mut rng = XorShiftRng::from_seed([s1,s2,s3,s4]);
    //    let f =  Fr::rand(&mut rng);
    //    obj.init(|t| PyFr{
    //        fr: f,
    //    })
    //}
    //fn __new__(obj: &PyRawObject, s1: u32, s2: u32, s3: u32, s4: u32) -> PyResult<()>{
    fn __new__(obj: &PyRawObject, s: &str) -> PyResult<()>{
        //let mut val = XorShiftRng::from_seed([s1,s2,s3,s4]);
        //let f =  Fr::from_str("8008").unwrap();
        let f =  Fr::from_str(s).unwrap();
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
    fn __new__(obj: &PyRawObject, s1: u32, s2: u32, s3: u32, s4: u32) -> PyResult<()>{
        let mut rng = XorShiftRng::from_seed([s1,s2,s3,s4]);
        let f =  Fq::rand(&mut rng);
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
    fq12 : Fq12
} 

#[pymethods]
impl PyFq12 {
    #[new]
    fn __new__(obj: &PyRawObject) -> PyResult<()>{
        Ok(())
    }

    pub fn __str__(&self) -> PyResult<String> {
        Ok(format!("Fq12({} + {} * w)",self.fq12.c0, self.fq12.c1 ))                
    }

    pub fn __repr__(&self) -> PyResult<String> {
        Ok(format!("Fq12({} + {} * w)",self.fq12.c0, self.fq12.c1 ))                
    }

    fn rand(&mut self, s1: u32, s2: u32, s3: u32, s4: u32) -> PyResult<()> {
        let mut rng = XorShiftRng::from_seed([s1,s2,s3,s4]);
        self.fq12.c0 = rng.gen();
        self.fq12.c1 = rng.gen();
        Ok(())
    }

    fn add_assign(&mut self, other: &Self) -> PyResult<()> {
        self.fq12.add_assign(&other.fq12);
        Ok(())
    }

    fn sub_assign(&mut self, other: &Self) -> PyResult<()> {
        self.fq12.sub_assign(&other.fq12);
        Ok(())
    }
    
    fn mul_assign(&mut self, other: &Self) -> PyResult<()> {
        self.fq12.mul_assign(&other.fq12);
        Ok(())
    }
    
    fn equals(&self, other: &Self) -> bool {
        self.fq12 == other.fq12
    }
    
    /// Copy other into self
    fn copy(&mut self, other: &Self) -> PyResult<()> {
        self.fq12 = other.fq12;
        Ok(())
    }

    
}


#[pymodinit]
fn pypairing(py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PyG1>()?;
    m.add_class::<PyG2>()?;
    m.add_class::<PyFq>()?;
    m.add_class::<PyFqRepr>()?;
    m.add_class::<PyFq12>()?;
    m.add_class::<PyFr>()?;
    m.add_function(wrap_function!(py_pairing)).unwrap();
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