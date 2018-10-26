#!/bin/sh 
n=3
k=32
b=1
for c in `seq 1 $n`
do
	rm -r -f phase2-party$c
	rm -r -f party$c-powermixing-online-phase1-output
	rm -f party$c-powermixing-online-phase3-output
	rm -f powers.sum$i
	rm -f /solver_phase4/party$c-powermixing-online-phase3-output
done

cd cpp_phase2
make clean 
make
cd ..

cd solver_phase4
python3 solver_build.py
cd ..

python3.6 powermixing_online.py 1
for c in `seq 1 $n`
do
	mkdir phase2-party$c
	cp -r cpp_phase2 phase2-party$c/cpp_phase2
	cd phase2-party$c/cpp_phase2
	sh run-compute-power-sums-local.sh $k $c $b

	for batch in $( seq 1 $b )
	do
		cp powers.sum_batch${batch} ../../powers.sum${c}_batch${batch}
	done
	cd ../..
done

python3.6 powermixing_online.py 3

for c in `seq 1 $n`
do
	for batch in $( seq 1 $b )
	do
		cp party$c-powermixing-online-phase3-output-batch${batch} solver_phase4/party$c-powermixing-online-phase3-output-batch${batch}
	done
	cd solver_phase4
	python3 solver.py $c $b

	end_tm=`date +%s%N`;

	for batch in $( seq 1 $b )
	do
		
		mv party$c-finaloutput-batch${batch} ../party$c-finaloutput-batch${batch}
	done
	cd ..
done

for c in `seq 1 $n`
do
	rm -r -f phase2-party$c
	rm -r -f party$c-powermixing-online-phase1-output
	rm -f party$c-powermixing-online-phase3-output
	rm -f powers.sum$i
	rm -f /solver_phase4/party$c-powermixing-online-phase3-output
done