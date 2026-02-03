int align_up_4(int value) {
  return (value + 3) & (~3);
}

int kernel_main() {
  int heap_base = 4096;          // 0x1000
  int heap_limit = heap_base + 65536; // reserve 64 KiB
  int heap_next = heap_base;

  heap_next = heap_next + align_up_4(24);
  heap_next = heap_next + align_up_4(40);

  return heap_limit - heap_next;
}
