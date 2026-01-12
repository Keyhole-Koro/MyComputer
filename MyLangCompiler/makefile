CC = gcc
CFLAGS = -Wall -Wextra -Iinc
SRC = $(wildcard src/*.c)
TESTS = $(wildcard tests/*.c)
SRC_NO_MAIN = $(filter-out src/main.c, $(SRC))
OUT = test
MYCC = mlc

all: mlc

mlc: $(SRC)
	$(CC) $(CFLAGS) -o $(MYCC) $(SRC)

test: $(SRC_NO_MAIN) $(TESTS)
	$(CC) $(CFLAGS) -g $(SRC_NO_MAIN) $(TESTS) -o $(OUT)
	./$(OUT)

debug: $(SRC_NO_MAIN) $(TESTS)
	$(CC) $(CFLAGS) -g $(SRC_NO_MAIN) $(TESTS) -o $(OUT)
	gdb ./$(OUT)

debug-mycc: $(SRC)
	$(CC) $(CFLAGS) -g -o $(MYCC) $(SRC)
	gdb --args ./$(MYCC) $(IN) $(OUT)

clean:
	rm -f $(OUT) $(MYCC)