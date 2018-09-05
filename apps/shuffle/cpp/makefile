all:
	g++ -g -O2 -std=c++17 -pthread -march=native compute-power-sums.cpp -o compute-power-sums -lntl -lgmp -lm
	mv compute-power-sums /usr/local/bin/
clean:
	rm -f compute-power-sums
