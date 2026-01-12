#ifndef UTILS_H
#define UTILS_H

#include <stdio.h>
#include <stdlib.h>

// Reads a source file verbatim (no include expansion).
// Caller owns the returned NUL-terminated buffer.
char *readSampleInput(const char *filePath);

// Saves content to filePath, creating the tests/outputs directory if needed.
void saveOutput(const char *filePath, const char *content);

#endif
