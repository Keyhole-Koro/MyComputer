
int add3(int a, int b, int c) {
    return a + b + c;
}

int add4(int a, int b, int c, int d) {
    return a + b + c + d;
}

int main() {
    int x = 2;
    int y = 3;
    if (x > 0) {
        x = x + 1; // x becomes 3
    }
    int z = add3(x, y, 10); // 15
    return z;
}
