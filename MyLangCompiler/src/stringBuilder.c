#include "stringBuilder.h"

void sb_init(StringBuilder *sb) {
    sb->cap = 1024;
    sb->len = 0;
    sb->buf = (char*)malloc(sb->cap);
    if (!sb->buf) {
        sb->cap = sb->len = 0;
        return;
    }
    sb->buf[0] = '\0';
}

void sb_append(StringBuilder *sb, const char *fmt, ...) {
    if (!sb || !sb->buf) return;

    va_list ap;
    va_start(ap, fmt);
    int need = vsnprintf(NULL, 0, fmt, ap);
    va_end(ap);

    if (need < 0) return;

    size_t required = sb->len + (size_t)need + 1;
    if (required > sb->cap) {
        size_t new_cap = sb->cap;
        while (new_cap < required) new_cap *= 2;
        char *new_buf = (char*)realloc(sb->buf, new_cap);
        if (!new_buf) return;
        sb->buf = new_buf;
        sb->cap = new_cap;
    }
    va_start(ap, fmt);
    vsnprintf(sb->buf + sb->len, sb->cap - sb->len, fmt, ap);
    va_end(ap);
    sb->len += (size_t)need;
}

char *sb_dump(StringBuilder *sb) {
    return sb ? sb->buf : NULL;
}

void sb_free(StringBuilder *sb) {
    if (!sb) return;
    free(sb->buf);
    sb->buf = NULL;
    sb->cap = sb->len = 0;
}
