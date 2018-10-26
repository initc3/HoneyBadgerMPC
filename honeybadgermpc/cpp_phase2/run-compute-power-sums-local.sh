echo "begin phase 2"
k=$1;
id=$2;
batch=$3;
n=$(lscpu -p | grep -c "^[0-9]");

for b in $( seq 1 $batch )
do
	rm -f powers.sum;time  seq $k | xargs -n1 -P$n -I{} sh -c "./compute-power-sums ../../party$id-powermixing-online-phase1-output/powermixing-online-phase1-output{}-batch${b}"
	mv powers.sum powers.sum_batch${b}
done
