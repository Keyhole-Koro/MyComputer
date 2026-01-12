#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "lexer.h"
#include "parser.h"
#include "codegen.h"
#include "AST.h"
#include "utils.h"

static char *build_sidecar_path(const char *out_path, const char *suffix) {
    if (!out_path || !suffix) return NULL;
    const char *last_slash = strrchr(out_path, '/');
    const char *last_back = strrchr(out_path, '\\');
    const char *sep = last_slash > last_back ? last_slash : last_back;
    const char *fname = sep ? sep + 1 : out_path;
    const char *dot = strrchr(fname, '.');
    size_t base_len = dot ? (size_t)(dot - out_path) : strlen(out_path);
    size_t suff_len = strlen(suffix);
    char *res = (char*)malloc(base_len + suff_len + 1);
    if (!res) return NULL;
    memcpy(res, out_path, base_len);
    memcpy(res + base_len, suffix, suff_len);
    res[base_len + suff_len] = '\0';
    return res;
}

int main(int argc, char *argv[]) {
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <input.ml> <output.asm>\n", argv[0]);
        return 1;
    }
    char *input_path = argv[1];
    char *output_path = argv[2];

    Token *tokens = lexer_from_file(input_path);
    if (!tokens) {
        fprintf(stderr, "Failed to read input file (or included files).\n");
        return 1;
    }
    // Also print to console as before
    for (Token *t = tokens; t; t = t->next) {
        printf("Token: kind=%s, value=%s\n", tokenkind2str(t->kind), t->value ? t->value : "(null)");
    }

    parser_set_filename(input_path);
    Token *cur = tokens;
    ASTNode *root = parse_program(&cur);

    print_ast(root, 0);
    printf("AST parsing completed.\n");

    char *output = codegen(root);
    
    if (!output) {
        fprintf(stderr, "Code generation failed.\n");
        return 1;
    }
    saveOutput(output_path, output);
    
    printf("Code generation completed. Output saved to %s\n", output_path);
    
    free(output);

    // Save lexer tokens and AST to sidecar .txt files next to the output
    char *tokens_txt = build_sidecar_path(output_path, "_tokens.txt");
    char *ast_txt = build_sidecar_path(output_path, "_ast.txt");

    if (tokens_txt) {
        FILE *tf = fopen(tokens_txt, "wb");
        if (tf) {
            for (Token *t = tokens; t; t = t->next) {
                fprintf(tf, "Token: kind=%s, value=%s\n",
                        tokenkind2str(t->kind), t->value ? t->value : "(null)");
            }
            fclose(tf);
            printf("Tokens saved to %s\n", tokens_txt);
        } else {
            perror("Failed to save tokens.txt");
        }
    }

    if (ast_txt) {
        FILE *af = fopen(ast_txt, "wb");
        if (af) {
            fprint_ast(af, root, 0);
            fclose(af);
            printf("AST saved to %s\n", ast_txt);
        } else {
            perror("Failed to save ast.txt");
        }
    }

    free(tokens_txt);
    free(ast_txt);

    return 0;
}
