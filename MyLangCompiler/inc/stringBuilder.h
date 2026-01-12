#ifndef STRING_BUILDER_H
#define STRING_BUILDER_H

#include <stdio.h>
#include <stdlib.h>

#include <string.h>
#include <stdarg.h>

typedef struct {
    char *buf;
    size_t cap;
    size_t len;
} StringBuilder;

void sb_init(StringBuilder *sb);
void sb_append(StringBuilder *sb, const char *fmt, ...);
char *sb_dump(StringBuilder *sb);
void sb_free(StringBuilder *sb);

#endif
