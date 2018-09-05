make clean;
make;
k=$1;
id=$2;
n=$(lscpu -p | grep -c "^[0-9]");
rm -f powers.sum;time  seq $k | xargs -n1 -P$n -I{} sh -c "./compute-power-sums ../party$id-powermixing-online-phase1-output/powermixing-online-phase1-output{}"

