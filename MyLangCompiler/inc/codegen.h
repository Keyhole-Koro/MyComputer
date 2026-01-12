#ifndef MASM_GEN_H
#define MASM_GEN_H

#include <stdio.h>

#include "AST.h"
#include "parser.h"
#include "stringBuilder.h"

char *codegen(ASTNode *root);

#endif