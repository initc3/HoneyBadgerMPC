all:
	g++ -g -O2 -std=c++17 -pthread -march=native compute-power-sums.cpp -o compute-power-sums -lntl -lgmp -lm
clean:
	rm -f compute-power-sums powers.sum
test: clean all
	./compute-power-sums compute-power-sums.input