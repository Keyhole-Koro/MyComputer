#include "AST.h"

char *astType2str(ASTNodeType type) {
    switch (type) {
        case AST_NUMBER: return "AST_NUMBER";
        case AST_IDENTIFIER: return "AST_IDENTIFIER";
        case AST_BINARY: return "AST_BINARY";
        case AST_TYPE: return "AST_TYPE";
        case AST_TYPE_ARRAY: return "AST_TYPE_ARRAY";
        case AST_VAR_DECL: return "AST_VAR_DECL";
        case AST_ASSIGN: return "AST_ASSIGN";
        case AST_UNARY: return "AST_UNARY";
        case AST_EXPR_STMT: return "AST_EXPR_STMT";
        case AST_IF: return "AST_IF";
        case AST_RETURN: return "AST_RETURN";
        case AST_BLOCK: return "AST_BLOCK";
        case AST_FUNDEF: return "AST_FUNDEF";
        case AST_PARAM: return "AST_PARAM";
        case AST_CALL: return "AST_CALL";
        case AST_WHILE: return "AST_WHILE";
        case AST_FOR: return "AST_FOR";
        case AST_TYPEDEF: return "AST_TYPEDEF";
        case AST_STRUCT: return "AST_STRUCT";
        case AST_STRUCT_MEMBER: return "AST_STRUCT_MEMBER";
        case AST_TYPEDEF_STRUCT: return "AST_TYPEDEF_STRUCT";
        case AST_STRING_LITERAL: return "AST_STRING_LITERAL";
        case AST_CHAR_LITERAL: return "AST_CHAR_LITERAL";
        case AST_MEMBER_ACCESS: return "AST_MEMBER_ACCESS";
        case AST_ARROW_ACCESS: return "AST_ARROW_ACCESS";
        case AST_BREAK: return "AST_BREAK";
        case AST_CONTINUE: return "AST_CONTINUE";
        case AST_DO_WHILE: return "AST_DO_WHILE";
        case AST_INIT_LIST: return "AST_INIT_LIST";
        case AST_SIZEOF: return "AST_SIZEOF";
        case AST_TERNARY: return "AST_TERNARY";
        case AST_IMPORT: return "AST_IMPORT";
    }
    return "<unknown>";
}
