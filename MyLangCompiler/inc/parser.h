#ifndef PARSER_H
#define PARSER_H

#include "lexer.h"
#include "AST.h"

ASTNode* parse_program(Token **cur);
void parser_set_filename(const char *name);
void print_ast(ASTNode *node, int indent);
// Writes the AST to a FILE* instead of stdout.
void fprint_ast(FILE *out, ASTNode *node, int indent);
void free_ast(ASTNode *node);

#endif
