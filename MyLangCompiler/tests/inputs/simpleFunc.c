
int add3(int a, int b, int c) {
    return a + b + c;
}

int main() {
    int x = 2;
    int y = 3;
    int z = 0;
    if (x > 0) {
        z = add3(x, y, 10); // 15
    }
    return z;
}
