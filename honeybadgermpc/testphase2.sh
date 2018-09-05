#!/bin/sh 
k=$1
n=$2
b=$3

mkdir phase2-party$n
cp -r cpp_phase2 phase2-party$n/cpp_phase2
cd phase2-party$n/cpp_phase2
sh run-compute-power-sums-local.sh $k $n $b
for batch in $( seq 1 $b )
do
	cp powers.sum_batch${batch} ../../powers.sum${n}_batch${batch}
done
cd ../..

