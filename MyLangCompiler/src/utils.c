#include "utils.h"

#include <stdio.h>
#include <stdlib.h>

#ifdef _WIN32
#include <direct.h>
#else
#include <sys/stat.h>
#include <sys/types.h>
#endif

// Read a file verbatim into a newly allocated buffer (no include expansion).
char *readSampleInput(const char *filePath) {
    if (!filePath) return NULL;

    FILE *f = fopen(filePath, "rb");
    if (!f) {
        perror("Failed to open file");
        return NULL;
    }

    if (fseek(f, 0, SEEK_END) != 0) {
        perror("Failed to seek file");
        fclose(f);
        return NULL;
    }
    long sz = ftell(f);
    if (sz < 0) {
        perror("Failed to tell file size");
        fclose(f);
        return NULL;
    }
    rewind(f);

    char *buf = (char*)malloc((size_t)sz + 1);
    if (!buf) {
        fclose(f);
        return NULL;
    }

    size_t read = fread(buf, 1, (size_t)sz, f);
    buf[read] = '\0';
    fclose(f);

    return buf;
}

static void ensure_outputs_dir(void) {
#ifdef _WIN32
    _mkdir("tests\\outputs");
#else
    struct stat st;
    if (stat("tests/outputs", &st) == 0) {
        if (!S_ISDIR(st.st_mode)) {
            fprintf(stderr, "Path tests/outputs exists and is not a directory\n");
        }
        return;
    }
    if (mkdir("tests/outputs", 0777) != 0) {
        fprintf(stderr, "Failed to create directory tests/outputs\n");
    }
#endif
}

void saveOutput(const char *filePath, const char *content) {
    ensure_outputs_dir();

    FILE *f = fopen(filePath, "wb");
    if (!f) {
        perror("Failed to open output file");
        return;
    }
    if (content) {
        fputs(content, f);
    }
    fclose(f);
}
