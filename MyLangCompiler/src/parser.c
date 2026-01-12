#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "parser.h"
#include "lexer.h"
#include "AST.h"

typedef struct FunctionTable {
    ASTNode **funcs;
    int count;
} FunctionTable;

#define MAX_TYPE_NAME 128
typedef struct TypeTable {
    char **typenames;
    int count;
} TypeTable;

typedef struct StructDef {
    char *name;
    ASTNode **members;
    int member_count;
} StructDef;

typedef struct StructTable {
    StructDef **structs;
    int count;
} StructTable;

Token *token_head = NULL;
ASTNode *root;
StructTable g_struct_table = { NULL, 0 };

FunctionTable g_func_table = { NULL, 0 };
TypeTable g_type_table = { NULL, 0 };

void add_function(ASTNode *fn) {
    g_func_table.funcs = realloc(g_func_table.funcs, sizeof(ASTNode*) * (g_func_table.count + 1));
    g_func_table.funcs[g_func_table.count++] = fn;
}

static const char *g_parse_filename = NULL;
void parser_set_filename(const char *name) { g_parse_filename = name; }

ASTNode* find_function(const char *name) {
    for (int i = 0; i < g_func_table.count; i++) {
        if (strcmp(g_func_table.funcs[i]->fundef.name, name) == 0) {
            return g_func_table.funcs[i];
        }
    }
    return NULL;
}

void add_typename(const char *name) {
    g_type_table.typenames = realloc(g_type_table.typenames, sizeof(char*) * (g_type_table.count + 1));
    g_type_table.typenames[g_type_table.count++] = strdup(name);
}

int is_user_typename(const char *name) {
    for (int i = 0; i < g_type_table.count; i++) {
        if (strcmp(g_type_table.typenames[i], name) == 0) return 1;
    }
    return 0;
}

void add_structdef(char *name, ASTNode **members, int member_count) {
    StructDef *def = malloc(sizeof(StructDef));
    def->name = strdup(name);
    def->members = members;
    def->member_count = member_count;
    g_struct_table.structs = realloc(g_struct_table.structs, sizeof(StructDef*) * (g_struct_table.count + 1));
    g_struct_table.structs[g_struct_table.count++] = def;
}

StructDef *find_structdef(const char *name) {
    for (int i = 0; i < g_struct_table.count; i++) {
        if (strcmp(g_struct_table.structs[i]->name, name) == 0) return g_struct_table.structs[i];
    }
    return NULL;
}

ASTNode *new_var_decl(ASTNode *type, char *name, ASTNode *init);

ASTNode *new_string_literal(char *str) {
    ASTNode *node = calloc(1, sizeof(ASTNode));
    node->type = AST_STRING_LITERAL;
    node->string_literal.value = strdup(str);
    return node;
}

ASTNode *new_char_literal(char *str) {
    ASTNode *node = calloc(1, sizeof(ASTNode));
    node->type = AST_CHAR_LITERAL;
    node->char_literal.value = strdup(str);
    return node;
}

ASTNode *new_sizeof(ASTNode *expr) {
    ASTNode *node = calloc(1, sizeof(ASTNode));
    node->type = AST_SIZEOF;
    node->sizeof_expr.expr = expr;
    return node;
}


ASTNode *new_type_array(ASTNode *elem_type, int size) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_TYPE_ARRAY;
    node->type_array.element_type = elem_type;
    node->type_array.array_size = size;
    return node;
}

ASTNode *new_var_decl(ASTNode *type, char *name, ASTNode *init) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_VAR_DECL;
    node->var_decl.var_type = type;
    node->var_decl.name = strdup(name);
    node->var_decl.init = init;
    return node;
}

ASTNode* new_param(ASTNode *type, char *name) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_PARAM;
    node->param.type = type;
    node->param.name = strdup(name);
    return node;
}
ASTNode* new_fundef(ASTNode *ret_type, char *name, ASTNode **params, int param_count, ASTNode *body) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_FUNDEF;
    node->fundef.ret_type = ret_type;
    node->fundef.name = strdup(name);
    node->fundef.params = params;
    node->fundef.param_count = param_count;
    node->fundef.body = body;
    return node;
}
ASTNode *new_number(char *val) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_NUMBER;
    node->number.value = strdup(val);
    return node;
}
ASTNode *new_identifier(char *name) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_IDENTIFIER;
    node->identifier.name = strdup(name);
    return node;
}
ASTNode *new_binary(TokenKind op, ASTNode *left, ASTNode *right) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_BINARY;
    node->binary.op = op;
    node->binary.left = left;
    node->binary.right = right;
    return node;
}
ASTNode *new_unary(TokenKind op, ASTNode *operand) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_UNARY;
    node->unary.op = op;
    node->unary.operand = operand;
    return node;
}
ASTNode *new_assign(ASTNode *left, ASTNode *right) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_ASSIGN;
    node->assign.left = left;
    node->assign.right = right;
    return node;
}
ASTNode *new_ternary(ASTNode *cond, ASTNode *then_expr, ASTNode *else_expr) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_TERNARY;
    node->ternary.cond = cond;
    node->ternary.then_expr = then_expr;
    node->ternary.else_expr = else_expr;
    return node;
}
ASTNode *new_type_node(ASTNode *base_type, int pointer_level, int modifiers) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_TYPE;
    node->type_node.base_type = base_type;
    node->type_node.pointer_level = pointer_level;
    node->type_node.type_modifiers = modifiers;
    return node;
}

ASTNode *new_expr_stmt(ASTNode *expr) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_EXPR_STMT;
    node->expr_stmt.expr = expr;
    return node;
}

ASTNode *new_typedef(ASTNode *src_type, char *alias) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_TYPEDEF;
    node->typedef_stmt.src_type = src_type;
    node->typedef_stmt.alias = strdup(alias);
    return node;
}

ASTNode *new_typedef_struct(char *struct_name, ASTNode **members, int member_count, char *typedef_name) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_TYPEDEF_STRUCT;
    node->typedef_struct.struct_name = strdup(struct_name ? struct_name : "");
    node->typedef_struct.members = members;
    node->typedef_struct.member_count = member_count;
    node->typedef_struct.typedef_name = strdup(typedef_name);
    return node;
}

ASTNode *new_struct(char *name, ASTNode **members, int member_count) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_STRUCT;
    node->struct_stmt.name = strdup(name);
    node->struct_stmt.members = members;
    node->struct_stmt.member_count = member_count;
    return node;
}

ASTNode *new_import_stmt(char *path, char **symbols, int count) {
    ASTNode *node = calloc(1, sizeof(ASTNode));
    node->type = AST_IMPORT;
    node->import_stmt.path = strdup(path);
    node->import_stmt.symbols = symbols;
    node->import_stmt.symbol_count = count;
    return node;
}

ASTNode *new_member_access(ASTNode *lhs, char *member_name) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_MEMBER_ACCESS;
    node->member_access.lhs = lhs;
    node->member_access.member = strdup(member_name);
    return node;
}
ASTNode *new_arrow_access(ASTNode *lhs, char *member_name) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_ARROW_ACCESS;
    node->arrow_access.lhs = lhs;
    node->arrow_access.member = strdup(member_name);
    return node;
}

ASTNode *new_struct_member(char *type, char *name) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_STRUCT_MEMBER;
    node->struct_member.type = strdup(type);
    node->struct_member.name = strdup(name);
    return node;
}

ASTNode *new_init_list(ASTNode **elems, int count) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_INIT_LIST;
    node->init_list.elements = elems;
    node->init_list.count = count;
    return node;
}

ASTNode *new_while(ASTNode *cond, ASTNode *body) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_WHILE;
    node->while_stmt.cond = cond;
    node->while_stmt.body = body;
    return node;
}

ASTNode *new_do_while(ASTNode *cond, ASTNode *body) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_DO_WHILE;
    node->do_while_stmt.cond = cond;
    node->do_while_stmt.body = body;
    return node;
}

ASTNode *new_for(ASTNode *init, ASTNode *cond, ASTNode *inc, ASTNode *body) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_FOR;
    node->for_stmt.init = init;
    node->for_stmt.cond = cond;
    node->for_stmt.inc = inc;
    node->for_stmt.body = body;
    return node;
}

ASTNode *new_break() {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_BREAK;
    return node;
}

ASTNode *new_continue() {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_CONTINUE;
    return node;
}

ASTNode *new_if(ASTNode *cond, ASTNode *then_stmt, ASTNode *else_stmt) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_IF;
    node->if_stmt.cond = cond;
    node->if_stmt.then_stmt = then_stmt;
    node->if_stmt.else_stmt = else_stmt;
    return node;
}
ASTNode *new_return(ASTNode *expr) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_RETURN;
    node->ret.expr = expr;
    return node;
}
ASTNode *new_block(ASTNode **stmts, int count) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_BLOCK;
    node->block.stmts = stmts;
    node->block.count = count;
    return node;
}
ASTNode *new_call(char *name, ASTNode **args, int arg_count) {
    ASTNode *node = malloc(sizeof(ASTNode));
    node->type = AST_CALL;
    node->call.name = strdup(name);
    node->call.args = args;
    node->call.arg_count = arg_count;
    return node;
}

static void print_line_snippet(const char *file, int line, int col) {
    if (!file || line <= 0) return;
    FILE *fp = fopen(file, "r");
    if (!fp) return;
    char buf[512];
    int cur_line = 1;
    while (fgets(buf, sizeof(buf), fp)) {
        if (cur_line == line) {
            size_t len = strlen(buf);
            while (len > 0 && (buf[len-1] == '\n' || buf[len-1] == '\r')) buf[--len] = '\0';
            fprintf(stderr, "  %s\n", buf);
            if (col > 0) fprintf(stderr, "  %*s^\n", col, "");
            break;
        }
        cur_line++;
    }
    fclose(fp);
}

void parse_error(const char *msg, Token *head, Token *cur) {
    fprintf(stderr, "%s:%d:%d: error: %s\n",
            g_parse_filename ? g_parse_filename : "<input>",
            cur ? cur->line : 0,
            cur ? cur->col : 0,
            msg);
    if (cur) print_line_snippet(g_parse_filename, cur->line, cur->col);

    // Print a small window of surrounding tokens for context
    Token *prevs[2] = {NULL, NULL};
    Token *nexts[2] = {NULL, NULL};

    Token *p = head;
    while (p && p != cur) {
        prevs[1] = prevs[0];
        prevs[0] = p;
        p = p->next;
    }
    Token *q = cur;
    for (int i = 0; i < 2 && q; i++) {
        q = q->next;
        nexts[i] = q;
    }

    if (prevs[1])
        fprintf(stderr, "  prev-2: kind=%s, value=%s (l%d c%d)\n",
                tokenkind2str(prevs[1]->kind),
                prevs[1]->value ? prevs[1]->value : "(null)",
                prevs[1]->line, prevs[1]->col);
    if (prevs[0])
        fprintf(stderr, "  prev-1: kind=%s, value=%s (l%d c%d)\n",
                tokenkind2str(prevs[0]->kind),
                prevs[0]->value ? prevs[0]->value : "(null)",
                prevs[0]->line, prevs[0]->col);
    if (nexts[0])
        fprintf(stderr, "  next+1: kind=%s, value=%s (l%d c%d)\n",
                tokenkind2str(nexts[0]->kind),
                nexts[0]->value ? nexts[0]->value : "(null)",
                nexts[0]->line, nexts[0]->col);
    if (nexts[1])
        fprintf(stderr, "  next+2: kind=%s, value=%s (l%d c%d)\n",
                tokenkind2str(nexts[1]->kind),
                nexts[1]->value ? nexts[1]->value : "(null)",
                nexts[1]->line, nexts[1]->col);
    exit(1);
}
int expect(Token **cur, TokenKind kind) {
    if (*cur && (*cur)->kind == kind) {
        *cur = (*cur)->next;
        return 1;
    }
    return 0;
}
int is_type(TokenKind kind, Token *cur) {
    if (kind == CONST || kind == UNSIGNED || kind == SIGNED) return 1;

    if (kind == VOID ||
        kind == INT ||
        kind == CHAR ||
        kind == FLOAT ||
        kind == DOUBLE ||
        kind == BOOL
    ) return 1;
    if (kind == IDENTIFIER && is_user_typename(cur->value)) return 1;
    return 0;
}

ASTNode *parse_expr(Token **cur);
ASTNode *parse_variable_declaration(Token **cur, int need_semicolon);
ASTNode *parse_struct(Token **cur);
ASTNode *parse_type(Token **cur);

ASTNode *parse_primary(Token **cur) {

    if ((*cur)->kind == NUMBER) {
        ASTNode *node = new_number((*cur)->value);
        *cur = (*cur)->next;
        return node;
    }
    if ((*cur)->kind == STRING_LITERAL) {
        ASTNode *node = new_string_literal((*cur)->value);
        *cur = (*cur)->next;
        return node;
    }
    if ((*cur)->kind == CHAR_LITERAL) {
        ASTNode *node = new_char_literal((*cur)->value);
        *cur = (*cur)->next;
        return node;
    }

    if ((*cur)->kind == IDENTIFIER) {
        char *name = (*cur)->value;
        *cur = (*cur)->next;

        if ((*cur)->kind == L_PARENTHESES) {
            *cur = (*cur)->next;
            ASTNode **args = NULL;
            int arg_count = 0;
            if ((*cur)->kind != R_PARENTHESES) {
                while (1) {
                    ASTNode *arg = parse_expr(cur);
                    args = realloc(args, sizeof(ASTNode*) * (arg_count + 1));
                    args[arg_count++] = arg;
                    if ((*cur)->kind == COMMA) { *cur = (*cur)->next; continue; }
                    break;
                }
            }

            if (!expect(cur, R_PARENTHESES))
                parse_error("expected ')' after args", token_head, *cur);
            return new_call(name, args, arg_count);
        }

        ASTNode *node = new_identifier(name);
        while ((*cur)->kind == L_BRACKET) {
            *cur = (*cur)->next;
            ASTNode *index = parse_expr(cur);

            if (!expect(cur, R_BRACKET))
                parse_error("expected ']' after array index", token_head, *cur);

            ASTNode *add = new_binary(ADD, node, index);
            node = new_unary(ASTARISK, add);  // *(name + index)
        }

        return node;
    }

    if ((*cur)->kind == L_PARENTHESES) {
        *cur = (*cur)->next;
        ASTNode *node = parse_expr(cur);
        if (!expect(cur, R_PARENTHESES)) parse_error("expected ')'", token_head, *cur);
        return node;
    }
    parse_error("expected primary", token_head, *cur);

    return NULL;
}
ASTNode *parse_base_type(Token **cur) {
    if (!is_type((*cur)->kind, *cur))
        parse_error("expected type", token_head, *cur);
    ASTNode *base = new_identifier((*cur)->value);
    *cur = (*cur)->next;
    return base;
}
void parse_struct_members(Token **cur, ASTNode ***members, int *member_count) {
    *members = NULL;
    *member_count = 0;
    if (!expect(cur, L_BRACE)) parse_error("expected '{' in struct", token_head, *cur);
    while ((*cur)->kind != R_BRACE) {
        ASTNode *member = parse_variable_declaration(cur, 1);
        *members = realloc(*members, sizeof(ASTNode*) * (*member_count + 1));
        (*members)[(*member_count)++] = member;
    }
    if (!expect(cur, R_BRACE)) parse_error("expected '}' to close struct definition", token_head, *cur);
}
ASTNode *parse_struct(Token **cur) {
    if (!expect(cur, STRUCT))
        parse_error("expected 'struct'", token_head, *cur);

    char *name = NULL;
    if ((*cur)->kind == IDENTIFIER) {
        name = strdup((*cur)->value);
        *cur = (*cur)->next;
    }

    ASTNode **members = NULL;
    int member_count = 0;

    if ((*cur)->kind == L_BRACE) {
        parse_struct_members(cur, &members, &member_count);
        if ((*cur)->kind == IDENTIFIER) {
            char *typedef_name = strdup((*cur)->value);
            *cur = (*cur)->next;
            if (!expect(cur, SEMICOLON))
                parse_error("expected ';' after typedef struct", token_head, *cur);
            add_typename(typedef_name);
            return new_typedef_struct(name ? name : "", members, member_count, typedef_name);
        }
        if (!expect(cur, SEMICOLON))
            parse_error("expected ';' after struct definition", token_head, *cur);
        if (name) add_typename(name);
        return new_struct(name ? name : "", members, member_count);
    }
    if (!expect(cur, SEMICOLON))
        parse_error("expected ';' after struct declaration", token_head, *cur);
    if (name) add_typename(name);
    return new_struct(name ? name : "", NULL, 0);
}

ASTNode *parse_typedef(Token **cur) {
    if (!expect(cur, TYPEDEF)) parse_error("expected 'typedef'", token_head, *cur);

    if ((*cur)->kind == STRUCT) {
        *cur = (*cur)->next;
        char *struct_name = NULL;
        if ((*cur)->kind == IDENTIFIER) {
            struct_name = strdup((*cur)->value);
            *cur = (*cur)->next;
        }
        ASTNode **members = NULL;
        int member_count = 0;
        parse_struct_members(cur, &members, &member_count);
        // typedef struct {...} Name;
        if ((*cur)->kind != IDENTIFIER)
            parse_error("expected typedef name after struct definition", token_head, *cur);
        char *typedef_name = strdup((*cur)->value);
        *cur = (*cur)->next;
        if (!expect(cur, SEMICOLON))
            parse_error("expected ';' after typedef", token_head, *cur);
        add_typename(typedef_name);
        return new_typedef_struct(struct_name ? struct_name : "", members, member_count, typedef_name);
    } else {
        // typedef int MyInt;
        ASTNode *type = parse_type(cur);
        if ((*cur)->kind != IDENTIFIER)
            parse_error("expected typedef name", token_head, *cur);
        char *typedef_name = strdup((*cur)->value);
        *cur = (*cur)->next;
        if (!expect(cur, SEMICOLON))
            parse_error("expected ';' after typedef", token_head, *cur);
        add_typename(typedef_name);
        return new_typedef(type, typedef_name);
    }
}


ASTNode *parse_type(Token **cur) {
    int modifiers = 0;

    while ((*cur)->kind == CONST || (*cur)->kind == UNSIGNED || (*cur)->kind == SIGNED) {
        if ((*cur)->kind == CONST)    modifiers |= TYPEMOD_CONST;
        if ((*cur)->kind == UNSIGNED) modifiers |= TYPEMOD_UNSIGNED;
        if ((*cur)->kind == SIGNED)   modifiers |= TYPEMOD_SIGNED;
        *cur = (*cur)->next;
    }

    if (!is_type((*cur)->kind, *cur))
        parse_error("expected base type", token_head, *cur);

    ASTNode *base_type = parse_base_type(cur);

    int pointer_level = 0;
    while ((*cur)->kind == ASTARISK) {
        pointer_level++;
        *cur = (*cur)->next;
    }
   return new_type_node(base_type, pointer_level, modifiers);

}

ASTNode *parse_postfix(Token **cur) {
    ASTNode *node = parse_primary(cur);
    while (1) {
        if ((*cur)->kind == INC) {
            *cur = (*cur)->next;
            node = new_unary(POST_INC, node);
        } else if ((*cur)->kind == DEC) {
            *cur = (*cur)->next;
            node = new_unary(POST_DEC, node);
        } 
        else if ((*cur)->kind == DOT) {
            *cur = (*cur)->next;
            if ((*cur)->kind != IDENTIFIER)
                parse_error("expected identifier after '.'", token_head, *cur);
            char *member_name = (*cur)->value;
            *cur = (*cur)->next;
            node = new_member_access(node, member_name);
        }
        else if ((*cur)->kind == ARROW) {
            *cur = (*cur)->next;
            if ((*cur)->kind != IDENTIFIER)
                parse_error("expected identifier after '->'", token_head, *cur);
            char *member_name = (*cur)->value;
            *cur = (*cur)->next;
            node = new_arrow_access(node, member_name);
        } else {
            break;
        }
    }
    return node;
}

ASTNode *parse_unary(Token **cur) {
    printf("parse_unary: cur kind = %s\n", tokenkind2str((*cur)->kind));
    if ((*cur)->kind == SUB) {
        *cur = (*cur)->next;
        return new_unary(SUB, parse_unary(cur));
    }
    if ((*cur)->kind == BITNOT) {
        *cur = (*cur)->next;
        return new_unary(BITNOT, parse_unary(cur));
    }
    if ((*cur)->kind == NOT) {
        *cur = (*cur)->next;
        return new_unary(NOT, parse_unary(cur));
    }
    if ((*cur)->kind == AMPERSAND) {
        *cur = (*cur)->next;
        return new_unary(AMPERSAND, parse_unary(cur));
    }
    if ((*cur)->kind == ASTARISK) {
        *cur = (*cur)->next;
        return new_unary(ASTARISK, parse_unary(cur));
    }
    if ((*cur)->kind == INC) {
        *cur = (*cur)->next;
        return new_unary(INC, parse_unary(cur));
    }
    if ((*cur)->kind == DEC) {
        *cur = (*cur)->next;
        return new_unary(DEC, parse_unary(cur));
    }
    if ((*cur)->kind == SIZEOF) {
        *cur = (*cur)->next;
        if (!expect(cur, L_PARENTHESES)) parse_error("expected '(' after sizeof", token_head, *cur);
        ASTNode *inner = parse_expr(cur);
        if (!expect(cur, R_PARENTHESES)) parse_error("expected ')' after sizeof expression", token_head, *cur);
        return new_sizeof(inner);
    }
    if ((*cur)->kind == STRING_LITERAL) {
        ASTNode *node = new_string_literal((*cur)->value);
        *cur = (*cur)->next;
        return node;
    }
    if ((*cur)->kind == CHAR_LITERAL) {
        ASTNode *node = new_char_literal((*cur)->value);
        *cur = (*cur)->next;
        return node;
    }

    return parse_postfix(cur);
}


ASTNode *parse_mul(Token **cur) {
    ASTNode *node = parse_unary(cur);
    while ((*cur)->kind == ASTARISK || (*cur)->kind == DIV || (*cur)->kind == MOD) {
        TokenKind op = (*cur)->kind;
        *cur = (*cur)->next;
        node = new_binary(op, node, parse_unary(cur));
    }
    return node;
}

ASTNode *parse_add(Token **cur) {
    ASTNode *node = parse_mul(cur);
    while ((*cur)->kind == ADD || (*cur)->kind == SUB) {
        TokenKind op = (*cur)->kind;
        *cur = (*cur)->next;
        node = new_binary(op, node, parse_mul(cur));
    }
    return node;
}

ASTNode *parse_shift(Token **cur) {
    ASTNode *node = parse_add(cur);
    while (1) {
        if ((*cur)->kind == LSH) {
            *cur = (*cur)->next;
            node = new_binary(LSH, node, parse_add(cur));
        } else if ((*cur)->kind == RSH) {
            *cur = (*cur)->next;
            node = new_binary(RSH, node, parse_add(cur));
        } else {
            break;
        }
    }
    return node;
}

ASTNode *parse_relational(Token **cur) {
    ASTNode *node = parse_shift(cur);
    while (1) {
        if ((*cur)->kind == LT) {
            *cur = (*cur)->next;
            node = new_binary(LT, node, parse_add(cur));
        } else if ((*cur)->kind == GT) {
            *cur = (*cur)->next;
            node = new_binary(GT, node, parse_add(cur));
        } else if ((*cur)->kind == LTE) {
            *cur = (*cur)->next;
            node = new_binary(LTE, node, parse_add(cur));
        } else if ((*cur)->kind == GTE) {
            *cur = (*cur)->next;
            node = new_binary(GTE, node, parse_add(cur));
        } else break;
    }
    return node;
}
ASTNode *parse_equality(Token **cur) {
    ASTNode *node = parse_relational(cur);
    while (1) {
        if ((*cur)->kind == EQ) {
            *cur = (*cur)->next;
            node = new_binary(EQ, node, parse_relational(cur));
        } else if ((*cur)->kind == NEQ) {
            *cur = (*cur)->next;
            node = new_binary(NEQ, node, parse_relational(cur));
        } else break;
    }
    return node;
}

ASTNode *parse_bitwise_and(Token **cur) {
    ASTNode *node = parse_equality(cur);
    while ((*cur)->kind == AMPERSAND) {
        *cur = (*cur)->next;
        node = new_binary(AMPERSAND, node, parse_equality(cur));
    }
    return node;
}

ASTNode *parse_bitwise_xor(Token **cur) {
    ASTNode *node = parse_bitwise_and(cur);
    while ((*cur)->kind == BITXOR) {
        *cur = (*cur)->next;
        node = new_binary(BITXOR, node, parse_bitwise_and(cur));
    }
    return node;
}

ASTNode *parse_bitwise_or(Token **cur) {
    ASTNode *node = parse_bitwise_xor(cur);
    while ((*cur)->kind == BITOR) {
        *cur = (*cur)->next;
        node = new_binary(BITOR, node, parse_bitwise_xor(cur));
    }
    return node;
}

// &&
ASTNode *parse_logical_and(Token **cur) {
    ASTNode *node = parse_bitwise_or(cur);
    while ((*cur)->kind == LAND) {
        *cur = (*cur)->next;
        node = new_binary(LAND, node, parse_bitwise_or(cur));
    }
    return node;
}

// ||
ASTNode *parse_logical_or(Token **cur) {
    ASTNode *node = parse_logical_and(cur);
    while ((*cur)->kind == LOR) {
        *cur = (*cur)->next;
        node = new_binary(LOR, node, parse_logical_and(cur));
    }
    return node;
}

// ?: (right-associative)
ASTNode *parse_conditional(Token **cur) {
    ASTNode *cond = parse_logical_or(cur);
    if ((*cur)->kind == QUESTION) {
        *cur = (*cur)->next;
        ASTNode *then_expr = parse_expr(cur);
        if (!expect(cur, COLON))
            parse_error("expected ':' in ternary expression", token_head, *cur);
        ASTNode *else_expr = parse_conditional(cur);
        return new_ternary(cond, then_expr, else_expr);
    }
    return cond;
}

ASTNode *parse_assign_expr(Token **cur) {
    ASTNode *node = parse_conditional(cur);
    if ((*cur)->kind == ASSIGN) {
        *cur = (*cur)->next;
        node = new_assign(node, parse_assign_expr(cur));
    }
    return node;
}
ASTNode *parse_expr(Token **cur) {
    return parse_assign_expr(cur);
}

ASTNode* parse_param(Token **cur) {
    ASTNode *type = parse_type(cur);
    if ((*cur)->kind != IDENTIFIER) parse_error("expected param name", token_head, *cur);
    char *name = (*cur)->value;
    *cur = (*cur)->next;

    ASTNode *final_type = type;
    while ((*cur)->kind == L_BRACKET) {
        *cur = (*cur)->next;
        int size = -1;
        if ((*cur)->kind == NUMBER) {
            size = atoi((*cur)->value);
            *cur = (*cur)->next;
        }
        if (!expect(cur, R_BRACKET)) parse_error("expected ']' for parameter array", token_head, *cur);
        final_type = new_type_array(final_type, size);
    }

    return new_param(final_type, name);
}

ASTNode** parse_param_list(Token **cur, int *out_count) {
    ASTNode **params = NULL;
    int count = 0;
    if ((*cur)->kind == R_PARENTHESES) { *out_count = 0; return NULL; }
    while (1) {
        ASTNode *param = parse_param(cur);
        params = realloc(params, sizeof(ASTNode*) * (count+1));
        params[count++] = param;
        if ((*cur)->kind == COMMA) { *cur = (*cur)->next; continue; }
        break;
    }
    *out_count = count;
    return params;
}

ASTNode *parse_stmt(Token **cur);

ASTNode *parse_block(Token **cur) {
    if (!expect(cur, L_BRACE)) parse_error("expected '{'", token_head, *cur);
    ASTNode **stmts = NULL;
    int count = 0;
    while ((*cur)->kind != R_BRACE && (*cur)->kind != EOT) {
        stmts = realloc(stmts, sizeof(ASTNode*) * (count+1));
        stmts[count++] = parse_stmt(cur);
    }
    if (!expect(cur, R_BRACE)) parse_error("expected '}'", token_head, *cur);
    root = new_block(stmts, count);
    return root;
}

ASTNode *parse_while_stmt(Token **cur) {
    if (!expect(cur, WHILE)) parse_error("expected 'while'", token_head, *cur);
    if (!expect(cur, L_PARENTHESES)) parse_error("expected '(' after while", token_head, *cur);
    ASTNode *cond = parse_expr(cur);
    if (!expect(cur, R_PARENTHESES)) parse_error("expected ')'", token_head, *cur);
    ASTNode *body = parse_stmt(cur);
    return new_while(cond, body);
}

ASTNode *parse_do_while_stmt(Token **cur) {
    if (!expect(cur, DO)) parse_error("expected 'do'", token_head, *cur);
    ASTNode *body = parse_stmt(cur);
    if (!expect(cur, WHILE)) parse_error("expected 'while' after do-body", token_head, *cur);
    if (!expect(cur, L_PARENTHESES)) parse_error("expected '(' after while", token_head, *cur);
    ASTNode *cond = parse_expr(cur);
    if (!expect(cur, R_PARENTHESES)) parse_error("expected ')'", token_head, *cur);
    if (!expect(cur, SEMICOLON)) parse_error("expected ';' after do-while", token_head, *cur);
    return new_do_while(cond, body);
}

ASTNode *parse_for_stmt(Token **cur) {
    if (!expect(cur, FOR)) parse_error("expected 'for'", token_head, *cur);
    if (!expect(cur, L_PARENTHESES)) parse_error("expected '(' after for", token_head, *cur);

    // for (init; cond; inc)
    ASTNode *init = NULL, *cond = NULL, *inc = NULL;

    if ((*cur)->kind != SEMICOLON) {
        if (is_type((*cur)->kind, *cur)) {
            init = parse_variable_declaration(cur, 0);
        } else {
            init = parse_expr(cur);
        }
    }
    if (!expect(cur, SEMICOLON)) parse_error("expected ';' after for-init", token_head, *cur);

    if ((*cur)->kind != SEMICOLON) {
        cond = parse_expr(cur);
    }
    if (!expect(cur, SEMICOLON)) parse_error("expected second ';' in for", token_head, *cur);

    if ((*cur)->kind != R_PARENTHESES) {
        inc = parse_expr(cur);
    }
    if (!expect(cur, R_PARENTHESES)) parse_error("expected ')' after for", token_head, *cur);

    ASTNode *body = parse_stmt(cur);
    return new_for(init, cond, inc, body);
}

ASTNode *parse_if_stmt(Token **cur) {
    if (!expect(cur, IF)) parse_error("expected 'if'", token_head, *cur);
    if (!expect(cur, L_PARENTHESES)) parse_error("expected '(' after if", token_head, *cur);
    ASTNode *cond = parse_expr(cur);
    if (!expect(cur, R_PARENTHESES)) parse_error("expected ')'", token_head, *cur);
    ASTNode *then_stmt = parse_stmt(cur);
    ASTNode *else_stmt = NULL;
    if ((*cur)->kind == ELSE) {
        expect(cur, ELSE);
        else_stmt = parse_stmt(cur);
    }
    return new_if(cond, then_stmt, else_stmt);
}
ASTNode *parse_return_stmt(Token **cur) {
    if (!expect(cur, RETURN)) parse_error("expected 'return'", token_head, *cur);
    ASTNode *expr = parse_expr(cur);
    if (!expect(cur, SEMICOLON)) parse_error("expected ';' after return", token_head, *cur);
    return new_return(expr);
}
ASTNode *parse_expr_stmt(Token **cur) {
    ASTNode *expr = parse_expr(cur);
    if (!expect(cur, SEMICOLON)) parse_error("expected ';' after expression", token_head, *cur);
    return new_expr_stmt(expr);
}

static ASTNode *parse_init_list(Token **cur) {
    if (!expect(cur, L_BRACE)) parse_error("expected '{' for initializer list", token_head, *cur);
    ASTNode **elems = NULL;
    int count = 0;
    if ((*cur)->kind != R_BRACE) {
        while (1) {
            ASTNode *e = parse_expr(cur);
            elems = realloc(elems, sizeof(ASTNode*) * (count + 1));
            elems[count++] = e;
            if ((*cur)->kind == COMMA) {
                *cur = (*cur)->next;
                continue;
            }
            break;
        }
    }
    if (!expect(cur, R_BRACE)) parse_error("expected '}' to close initializer list", token_head, *cur);
    return new_init_list(elems, count);
}
ASTNode *parse_variable_declaration(Token **cur, int need_semicolon) {
    ASTNode *type = parse_type(cur);
    if ((*cur)->kind != IDENTIFIER)
        parse_error("expected identifier for variable name", token_head, *cur);
    char *name = (*cur)->value;
    *cur = (*cur)->next;

    ASTNode *final_type = type;
    while ((*cur)->kind == L_BRACKET) {
        *cur = (*cur)->next;
        int size = -1;
        if ((*cur)->kind == NUMBER) {
            size = atoi((*cur)->value);
            *cur = (*cur)->next;
        }
        if (!expect(cur, R_BRACKET)) parse_error("expected ']' for array", token_head, *cur);
        final_type = new_type_array(final_type, size);
    }

    ASTNode *init = NULL;
    if (expect(cur, ASSIGN)) {
        if ((*cur)->kind == L_BRACE) {
            init = parse_init_list(cur);
        } else {
            init = parse_expr(cur);
        }
        if (final_type && final_type->type == AST_TYPE_ARRAY && final_type->type_array.array_size <= 0) {
            if (init && init->type == AST_STRING_LITERAL) {
                int inferred = (int)strlen(init->string_literal.value) + 1; // include NUL
                final_type->type_array.array_size = inferred;
            } else if (init && init->type == AST_INIT_LIST) {
                final_type->type_array.array_size = init->init_list.count;
            }
        }
    }
    if (need_semicolon) {
        if (!expect(cur, SEMICOLON))
            parse_error("expected ';' after variable declaration", token_head, *cur);
    }
    return new_var_decl(final_type, name, init);
}


ASTNode *parse_variable_assignment(Token **cur) {
    if ((*cur)->kind != IDENTIFIER) parse_error("expected identifier for assignment", token_head, *cur);
    char *name = (*cur)->value;
    *cur = (*cur)->next;
    if (!expect(cur, ASSIGN)) parse_error("expected '=' for assignment", token_head, *cur);
    ASTNode *expr = parse_expr(cur);
    if (!expect(cur, SEMICOLON)) parse_error("expected ';' after assignment", token_head, *cur);
    return new_assign(new_identifier(name), expr);
}

ASTNode *parse_stmt(Token **cur) {
    if ((*cur)->kind == IF) return parse_if_stmt(cur);
    if ((*cur)->kind == WHILE) return parse_while_stmt(cur);
    if ((*cur)->kind == DO) return parse_do_while_stmt(cur);
    if ((*cur)->kind == FOR) return parse_for_stmt(cur);
    if ((*cur)->kind == RETURN) return parse_return_stmt(cur);

    if ((*cur)->kind == BREAK) {
        *cur = (*cur)->next;
        if (!expect(cur, SEMICOLON)) parse_error("expected ';' after break", token_head, *cur);
        return new_break();
    }
    if ((*cur)->kind == CONTINUE) {
        *cur = (*cur)->next;
        if (!expect(cur, SEMICOLON)) parse_error("expected ';' after continue", token_head, *cur);
        return new_continue();
    }

    if ((*cur)->kind == L_BRACE) return parse_block(cur);
    if (is_type((*cur)->kind, *cur)) return parse_variable_declaration(cur, 1);

    printf("DEBUG: parse_stmt falling back to expr_stmt at token kind %s\n", tokenkind2str((*cur)->kind));
    return parse_expr_stmt(cur);
}

ASTNode* parse_fundef(Token **cur) {
    ASTNode *ret_type = parse_type(cur);
    if ((*cur)->kind != IDENTIFIER) parse_error("expected function name", token_head, *cur);
    char *name = (*cur)->value;
    *cur = (*cur)->next;
    if (!expect(cur, L_PARENTHESES)) parse_error("expected '(' after function name", token_head, *cur);

    int param_count = 0;
    ASTNode **params = NULL;
    if ((*cur)->kind != R_PARENTHESES)
        params = parse_param_list(cur, &param_count);

    if (!expect(cur, R_PARENTHESES)) parse_error("expected ')' after parameter list", token_head, *cur);

    // Function prototype (declaration without body)
    if ((*cur)->kind == SEMICOLON) {
        *cur = (*cur)->next; // consume ';'
        return NULL;
    }

    ASTNode *body = parse_block(cur);
    ASTNode *fndef = new_fundef(ret_type, name, params, param_count, body);
    add_function(fndef);
    return fndef;
}

ASTNode *parse_import(Token **cur) {
    if (!expect(cur, IMPORT)) parse_error("expected 'import'", token_head, *cur);
    if (!expect(cur, L_BRACE)) parse_error("expected '{'", token_head, *cur);
    
    char **symbols = NULL;
    int count = 0;
    
    if ((*cur)->kind != R_BRACE) {
        while(1) {
            if ((*cur)->kind != IDENTIFIER) parse_error("expected identifier in import list", token_head, *cur);
            symbols = realloc(symbols, sizeof(char*) * (count + 1));
            symbols[count++] = strdup((*cur)->value);
            *cur = (*cur)->next;
            if ((*cur)->kind == COMMA) {
                *cur = (*cur)->next;
                continue;
            }
            break;
        }
    }
    
    if (!expect(cur, R_BRACE)) parse_error("expected '}'", token_head, *cur);
    if (!expect(cur, FROM)) parse_error("expected 'from'", token_head, *cur);
    
    if ((*cur)->kind != STRING_LITERAL) parse_error("expected file path string", token_head, *cur);
    char *path = (*cur)->value;
    *cur = (*cur)->next;
    
    if (!expect(cur, SEMICOLON)) parse_error("expected ';'", token_head, *cur);

    return new_import_stmt(path, symbols, count);
}

ASTNode* parse_toplevel(Token **cur) {
    if ((*cur)->kind == IMPORT) return parse_import(cur);
    if ((*cur)->kind == TYPEDEF) return parse_typedef(cur);
    if ((*cur)->kind == STRUCT) return parse_struct(cur);
    if (is_type((*cur)->kind, *cur)) {
        Token *save = *cur;
        ASTNode *fn = parse_fundef(cur);
        if (fn || *cur != save) return fn; // definition returns node; declaration returns NULL but consumes tokens
        *cur = save;
    }
    ASTNode *stmt = parse_stmt(cur);
    if (!stmt) parse_error("unexpected toplevel construct", token_head, *cur);
    return stmt;
}
ASTNode* parse_program(Token **cur) {
    ASTNode **nodes = NULL;
    int count = 0;
    while ((*cur)->kind != EOT) {
        ASTNode *node = parse_toplevel(cur);
        if (!node) continue; // prototype or skipped declaration
        nodes = realloc(nodes, sizeof(ASTNode*) * (count+1));
        nodes[count++] = node;
    }
    return new_block(nodes, count);
}

void print_ast(ASTNode *node, int indent) {
    if (!node) return;
    #define INDENT for (int i = 0; i < indent; i++) printf("  ")
    switch (node->type) {
    case AST_NUMBER:
        INDENT; printf("Number: %s\n", node->number.value);
        break;
    case AST_IDENTIFIER:
        INDENT; printf("Identifier: %s\n", node->identifier.name);
        break;
    case AST_BINARY:
        INDENT; printf("Binary: %s\n", tokenkind2str(node->binary.op));
        print_ast(node->binary.left, indent+1);
        print_ast(node->binary.right, indent+1);
        break;
    case AST_TYPE:
        INDENT; printf("Type:\n");
        print_ast(node->type_node.base_type, indent+1);
        INDENT; printf("pointers: %d\n", node->type_node.pointer_level);
        INDENT; printf("modifiers:");
        if (node->type_node.type_modifiers & TYPEMOD_CONST) printf(" const");
        if (node->type_node.type_modifiers & TYPEMOD_UNSIGNED) printf(" unsigned");
        if (node->type_node.type_modifiers & TYPEMOD_SIGNED) printf(" signed");
        if (!(node->type_node.type_modifiers & (TYPEMOD_CONST|TYPEMOD_UNSIGNED|TYPEMOD_SIGNED))) printf(" none");
        printf("\n");
        break;
    case AST_TYPE_ARRAY:
        INDENT; printf("TypeArray: size=%d\n", node->type_array.array_size);
        print_ast(node->type_array.element_type, indent+1);
        break;
    case AST_VAR_DECL:
        INDENT; printf("VarDecl:\n");
        INDENT; printf("  Type:\n");
        print_ast(node->var_decl.var_type, indent+2);
        INDENT; printf("  Name: %s\n", node->var_decl.name);
        if (node->var_decl.init) {
            INDENT; printf("  Init:\n");
            print_ast(node->var_decl.init, indent+2);
        }
        break;
    case AST_ASSIGN:
        INDENT; printf("Assign\n");
        print_ast(node->assign.left, indent+1);
        print_ast(node->assign.right, indent+1);
        break;
    case AST_UNARY:
        INDENT;
        switch (node->unary.op) {
            case AMPERSAND: printf("Unary: & (address)\n"); break;
            case SUB: printf("Unary: - (negate)\n"); break;
            case INC: printf("Unary: ++ (pre-increment)\n"); break;
            case DEC: printf("Unary: -- (pre-decrement)\n"); break;
            case POST_INC: printf("Unary: ++ (post-increment)\n"); break;
            case POST_DEC: printf("Unary: -- (post-decrement)\n"); break;
            case ASTARISK: printf("Unary: * (dereference)\n"); break;
            default: printf("Unary: %d\n", node->unary.op); break;
        }
        print_ast(node->unary.operand, indent+1);
        break;
    case AST_TERNARY:
        INDENT; printf("Ternary\n");
        print_ast(node->ternary.cond, indent+1);
        print_ast(node->ternary.then_expr, indent+1);
        print_ast(node->ternary.else_expr, indent+1);
        break;
    case AST_IMPORT:
        INDENT; printf("Import: %s\n", node->import_stmt.path);
        for(int i=0; i<node->import_stmt.symbol_count; i++) {
            INDENT; printf("  Symbol: %s\n", node->import_stmt.symbols[i]);
        }
        break;
    case AST_SIZEOF:
        INDENT; printf("Sizeof\n");
        print_ast(node->sizeof_expr.expr, indent+1);
        break;
    case AST_EXPR_STMT:
        INDENT; printf("ExprStmt\n");
        print_ast(node->expr_stmt.expr, indent+1);
        break;
    case AST_IF:
        INDENT; printf("If\n");
        print_ast(node->if_stmt.cond, indent+1);
        print_ast(node->if_stmt.then_stmt, indent+1);
        if (node->if_stmt.else_stmt) print_ast(node->if_stmt.else_stmt, indent+1);
        break;
    case AST_RETURN:
        INDENT; printf("Return\n");
        print_ast(node->ret.expr, indent+1);
        break;
    case AST_BLOCK:
        INDENT; printf("Block\n");
        for (int i = 0; i < node->block.count; i++)
            print_ast(node->block.stmts[i], indent+1);
        break;
    case AST_FUNDEF:
        INDENT; printf("Function:  %s\n", node->fundef.name);
        for (int i = 0; i < node->fundef.param_count; i++) {
            INDENT; printf("  Param:  %s\n",
                node->fundef.params[i]->param.name);
        }
        print_ast(node->fundef.body, indent+1);
        break;
    case AST_CALL:
        INDENT; printf("Call: %s\n", node->call.name);
        for (int i = 0; i < node->call.arg_count; i++)
            print_ast(node->call.args[i], indent+1);
        break;
    case AST_WHILE:
        INDENT; printf("While\n");
        print_ast(node->while_stmt.cond, indent+1);
        print_ast(node->while_stmt.body, indent+1);
        break;
    case AST_FOR:
        INDENT; printf("For\n");
        if (node->for_stmt.init) {
            INDENT; printf("  Init:\n");
            print_ast(node->for_stmt.init, indent+2);
        }
        if (node->for_stmt.cond) {
            INDENT; printf("  Cond:\n");
            print_ast(node->for_stmt.cond, indent+2);
        }
        if (node->for_stmt.inc) {
            INDENT; printf("  Inc:\n");
            print_ast(node->for_stmt.inc, indent+2);
        }
        print_ast(node->for_stmt.body, indent+1);
        break;
    case AST_PARAM:
        INDENT; printf("Param:  %s\n", node->param.name);
        break;
    case AST_STRUCT:
        INDENT; printf("Struct: %s\n", node->struct_stmt.name);
        for (int i = 0; i < node->struct_stmt.member_count; i++) {
            ASTNode *m = node->struct_stmt.members[i];
            const char *n = (m->type == AST_STRUCT_MEMBER) ? m->struct_member.name :
                             (m->type == AST_VAR_DECL) ? m->var_decl.name : "";
            INDENT; printf("  Member:  %s\n", n);
        }
        break;
    case AST_TYPEDEF:
        INDENT; printf("Typedef: %s\n", node->typedef_stmt.alias);
        INDENT; printf("  BaseType:\n");
        print_ast(node->typedef_stmt.src_type, indent+2);
        break;
    case AST_STRUCT_MEMBER:
        INDENT; printf("StructMember: %s %s\n",
            node->struct_member.type,
            node->struct_member.name);
        break;
    case AST_TYPEDEF_STRUCT:
        INDENT; printf("TypedefStruct:  -> %s\n",
            node->typedef_struct.typedef_name);
        for (int i = 0; i < node->typedef_struct.member_count; i++) {
            ASTNode *m = node->typedef_struct.members[i];
            const char *n = (m->type == AST_STRUCT_MEMBER) ? m->struct_member.name :
                             (m->type == AST_VAR_DECL) ? m->var_decl.name : "";
            INDENT; printf("  Member:  %s\n", n);
        }
        break;
    case AST_STRING_LITERAL:
        INDENT; printf("StringLiteral: \"%s\"\n", node->string_literal.value);
        break;
    case AST_CHAR_LITERAL:
        INDENT; printf("CharLiteral: '%c'\n", node->char_literal.value ? node->char_literal.value[0] : '\0');
        break;
    case AST_MEMBER_ACCESS:
        INDENT; printf("MemberAccess: %s\n", node->member_access.member);
        print_ast(node->member_access.lhs, indent+1);
        break;
    case AST_ARROW_ACCESS:
        INDENT; printf("ArrowAccess: %s\n", node->arrow_access.member);
        print_ast(node->arrow_access.lhs, indent+1);
        break;
    case AST_INIT_LIST:
        INDENT; printf("InitList:\n");
        for (int i = 0; i < node->init_list.count; i++) {
            print_ast(node->init_list.elements[i], indent+1);
        }
        break;
    case AST_BREAK:
        INDENT; printf("Break\n");
        break;
    case AST_CONTINUE:
        INDENT; printf("Continue\n");
        break;
    default:
        INDENT; printf("Unknown AST Node Type: %d\n", node->type);
    }
    #undef INDENT
}

// Write AST to a FILE* (mirrors print_ast but targets a stream)
void fprint_ast(FILE *out, ASTNode *node, int indent) {
    if (!node) return;
    #define INDENT for (int i = 0; i < indent; i++) fprintf(out, "  ")
    switch (node->type) {
    case AST_NUMBER:
        INDENT; fprintf(out, "Number: %s\n", node->number.value);
        break;
    case AST_IDENTIFIER:
        INDENT; fprintf(out, "Identifier: %s\n", node->identifier.name);
        break;
    case AST_BINARY:
        INDENT; fprintf(out, "Binary: %s\n", tokenkind2str(node->binary.op));
        fprint_ast(out, node->binary.left, indent+1);
        fprint_ast(out, node->binary.right, indent+1);
        break;
    case AST_TYPE:
        INDENT; fprintf(out, "Type:\n");
        fprint_ast(out, node->type_node.base_type, indent+1);
        INDENT; fprintf(out, "pointers: %d\n", node->type_node.pointer_level);
        INDENT; fprintf(out, "modifiers:");
        if (node->type_node.type_modifiers & TYPEMOD_CONST) fprintf(out, " const");
        if (node->type_node.type_modifiers & TYPEMOD_UNSIGNED) fprintf(out, " unsigned");
        if (node->type_node.type_modifiers & TYPEMOD_SIGNED) fprintf(out, " signed");
        if (!(node->type_node.type_modifiers & (TYPEMOD_CONST|TYPEMOD_UNSIGNED|TYPEMOD_SIGNED))) fprintf(out, " none");
        fprintf(out, "\n");
        break;
    case AST_TYPE_ARRAY:
        INDENT; fprintf(out, "TypeArray: size=%d\n", node->type_array.array_size);
        fprint_ast(out, node->type_array.element_type, indent+1);
        break;
    case AST_VAR_DECL:
        INDENT; fprintf(out, "VarDecl:\n");
        INDENT; fprintf(out, "  Type:\n");
        fprint_ast(out, node->var_decl.var_type, indent+2);
        INDENT; fprintf(out, "  Name: %s\n", node->var_decl.name);
        if (node->var_decl.init) {
            INDENT; fprintf(out, "  Init:\n");
            fprint_ast(out, node->var_decl.init, indent+2);
        }
        break;
    case AST_ASSIGN:
        INDENT; fprintf(out, "Assign\n");
        fprint_ast(out, node->assign.left, indent+1);
        fprint_ast(out, node->assign.right, indent+1);
        break;
    case AST_UNARY:
        INDENT;
        switch (node->unary.op) {
            case AMPERSAND: fprintf(out, "Unary: & (address)\n"); break;
            case SUB: fprintf(out, "Unary: - (negate)\n"); break;
            case INC: fprintf(out, "Unary: ++ (pre-increment)\n"); break;
            case DEC: fprintf(out, "Unary: -- (pre-decrement)\n"); break;
            case POST_INC: fprintf(out, "Unary: ++ (post-increment)\n"); break;
            case POST_DEC: fprintf(out, "Unary: -- (post-decrement)\n"); break;
            case ASTARISK: fprintf(out, "Unary: * (dereference)\n"); break;
            default: fprintf(out, "Unary: %d\n", node->unary.op); break;
        }
        fprint_ast(out, node->unary.operand, indent+1);
        break;
    case AST_TERNARY:
        INDENT; fprintf(out, "Ternary\n");
        fprint_ast(out, node->ternary.cond, indent+1);
        fprint_ast(out, node->ternary.then_expr, indent+1);
        fprint_ast(out, node->ternary.else_expr, indent+1);
        break;
    case AST_IMPORT:
        INDENT; fprintf(out, "Import: %s\n", node->import_stmt.path);
        for(int i=0; i<node->import_stmt.symbol_count; i++) {
            INDENT; fprintf(out, "  Symbol: %s\n", node->import_stmt.symbols[i]);
        }
        break;
    case AST_SIZEOF:
        INDENT; fprintf(out, "Sizeof\n");
        fprint_ast(out, node->sizeof_expr.expr, indent+1);
        break;
    case AST_EXPR_STMT:
        INDENT; fprintf(out, "ExprStmt\n");
        fprint_ast(out, node->expr_stmt.expr, indent+1);
        break;
    case AST_IF:
        INDENT; fprintf(out, "If\n");
        fprint_ast(out, node->if_stmt.cond, indent+1);
        fprint_ast(out, node->if_stmt.then_stmt, indent+1);
        if (node->if_stmt.else_stmt) fprint_ast(out, node->if_stmt.else_stmt, indent+1);
        break;
    case AST_RETURN:
        INDENT; fprintf(out, "Return\n");
        fprint_ast(out, node->ret.expr, indent+1);
        break;
    case AST_BLOCK:
        INDENT; fprintf(out, "Block\n");
        for (int i = 0; i < node->block.count; i++)
            fprint_ast(out, node->block.stmts[i], indent+1);
        break;
    case AST_FUNDEF:
        INDENT; fprintf(out, "Function:  %s\n", node->fundef.name);
        for (int i = 0; i < node->fundef.param_count; i++) {
            INDENT; fprintf(out, "  Param:  %s\n",
                node->fundef.params[i]->param.name);
        }
        fprint_ast(out, node->fundef.body, indent+1);
        break;
    case AST_CALL:
        INDENT; fprintf(out, "Call: %s\n", node->call.name);
        for (int i = 0; i < node->call.arg_count; i++)
            fprint_ast(out, node->call.args[i], indent+1);
        break;
    case AST_WHILE:
        INDENT; fprintf(out, "While\n");
        fprint_ast(out, node->while_stmt.cond, indent+1);
        fprint_ast(out, node->while_stmt.body, indent+1);
        break;
    case AST_FOR:
        INDENT; fprintf(out, "For\n");
        if (node->for_stmt.init) {
            INDENT; fprintf(out, "  Init:\n");
            fprint_ast(out, node->for_stmt.init, indent+2);
        }
        if (node->for_stmt.cond) {
            INDENT; fprintf(out, "  Cond:\n");
            fprint_ast(out, node->for_stmt.cond, indent+2);
        }
        if (node->for_stmt.inc) {
            INDENT; fprintf(out, "  Inc:\n");
            fprint_ast(out, node->for_stmt.inc, indent+2);
        }
        fprint_ast(out, node->for_stmt.body, indent+1);
        break;
    case AST_PARAM:
        INDENT; fprintf(out, "Param:  %s\n", node->param.name);
        break;
    case AST_STRUCT:
        INDENT; fprintf(out, "Struct: %s\n", node->struct_stmt.name);
        for (int i = 0; i < node->struct_stmt.member_count; i++) {
            ASTNode *m = node->struct_stmt.members[i];
            const char *n = (m->type == AST_STRUCT_MEMBER) ? m->struct_member.name :
                             (m->type == AST_VAR_DECL) ? m->var_decl.name : "";
            INDENT; fprintf(out, "  Member:  %s\n", n);
        }
        break;
    case AST_TYPEDEF:
        INDENT; fprintf(out, "Typedef: %s\n", node->typedef_stmt.alias);
        INDENT; fprintf(out, "  BaseType:\n");
        fprint_ast(out, node->typedef_stmt.src_type, indent+2);
        break;
    case AST_STRUCT_MEMBER:
        INDENT; fprintf(out, "StructMember: %s %s\n",
            node->struct_member.type,
            node->struct_member.name);
        break;
    case AST_TYPEDEF_STRUCT:
        INDENT; fprintf(out, "TypedefStruct:  -> %s\n",
            node->typedef_struct.typedef_name);
        for (int i = 0; i < node->typedef_struct.member_count; i++) {
            ASTNode *m = node->typedef_struct.members[i];
            const char *n = (m->type == AST_STRUCT_MEMBER) ? m->struct_member.name :
                             (m->type == AST_VAR_DECL) ? m->var_decl.name : "";
            INDENT; fprintf(out, "  Member:  %s\n", n);
        }
        break;
    case AST_STRING_LITERAL:
        INDENT; fprintf(out, "StringLiteral: \"%s\"\n", node->string_literal.value);
        break;
    case AST_CHAR_LITERAL:
        INDENT; fprintf(out, "CharLiteral: '%c'\n", node->char_literal.value ? node->char_literal.value[0] : '\0');
        break;
    case AST_MEMBER_ACCESS:
        INDENT; fprintf(out, "MemberAccess: %s\n", node->member_access.member);
        fprint_ast(out, node->member_access.lhs, indent+1);
        break;
    case AST_ARROW_ACCESS:
        INDENT; fprintf(out, "ArrowAccess: %s\n", node->arrow_access.member);
        fprint_ast(out, node->arrow_access.lhs, indent+1);
        break;
    case AST_INIT_LIST:
        INDENT; fprintf(out, "InitList:\n");
        for (int i = 0; i < node->init_list.count; i++) {
            fprint_ast(out, node->init_list.elements[i], indent+1);
        }
        break;
    case AST_BREAK:
        INDENT; fprintf(out, "Break\n");
        break;
    case AST_CONTINUE:
        INDENT; fprintf(out, "Continue\n");
        break;
    default:
        INDENT; fprintf(out, "Unknown AST Node Type: %d\n", node->type);
    }
    #undef INDENT
}

void free_ast(ASTNode *node) {
    if (!node) return;
    switch (node->type) {
        case AST_NUMBER:
            free(node->number.value);
            break;
        case AST_IDENTIFIER:
            free(node->identifier.name);
            break;
        case AST_BINARY:
            free_ast(node->binary.left);
            free_ast(node->binary.right);
            break;
        case AST_ASSIGN:
            free_ast(node->assign.left);
            free_ast(node->assign.right);
            break;
        case AST_VAR_DECL:
            free_ast(node->var_decl.var_type);
            free(node->var_decl.name);
            if (node->var_decl.init) free_ast(node->var_decl.init);
            break;
        case AST_TYPE:
            free_ast(node->type_node.base_type);
            break;
        case AST_TYPE_ARRAY:
            free_ast(node->type_array.element_type);
            break;
        case AST_STRING_LITERAL:
            free(node->string_literal.value);
            break;
        case AST_CHAR_LITERAL:
            free(node->char_literal.value);
            break;
        case AST_UNARY:
            free_ast(node->unary.operand);
            break;
        case AST_TERNARY:
            free_ast(node->ternary.cond);
            free_ast(node->ternary.then_expr);
            free_ast(node->ternary.else_expr);
            break;
        case AST_IMPORT:
            free(node->import_stmt.path);
            for(int i=0; i<node->import_stmt.symbol_count; i++) free(node->import_stmt.symbols[i]);
            free(node->import_stmt.symbols);
            break;
        case AST_EXPR_STMT:
            free_ast(node->expr_stmt.expr);
            break;
        case AST_IF:
            free_ast(node->if_stmt.cond);
            free_ast(node->if_stmt.then_stmt);
            if (node->if_stmt.else_stmt) free_ast(node->if_stmt.else_stmt);
            break;
        case AST_RETURN:
            free_ast(node->ret.expr);
            break;
        case AST_BLOCK:
            for (int i = 0; i < node->block.count; i++)
                free_ast(node->block.stmts[i]);
            free(node->block.stmts);
            break;
        case AST_FUNDEF:
            if (node->fundef.ret_type) free_ast(node->fundef.ret_type);
            free(node->fundef.name);
            for (int i = 0; i < node->fundef.param_count; i++)
                free_ast(node->fundef.params[i]);
            free(node->fundef.params);
            free_ast(node->fundef.body);
            break;
        case AST_CALL:
            free(node->call.name);
            for (int i = 0; i < node->call.arg_count; i++)
                free_ast(node->call.args[i]);
            free(node->call.args);
            break;
        case AST_PARAM:
            if (node->param.type) free_ast(node->param.type);
            free(node->param.name);
            break;
        case AST_STRUCT:
            free(node->struct_stmt.name);
            for (int i = 0; i < node->struct_stmt.member_count; i++)
                free_ast(node->struct_stmt.members[i]);
            free(node->struct_stmt.members);
            break;
        case AST_STRUCT_MEMBER:
            free(node->struct_member.type);
            free(node->struct_member.name);
            break;
        case AST_TYPEDEF:
            free(node->typedef_stmt.alias);
            free_ast(node->typedef_stmt.src_type);
            break;
        case AST_TYPEDEF_STRUCT:
            free(node->typedef_struct.struct_name);
            for (int i = 0; i < node->typedef_struct.member_count; i++)
                free_ast(node->typedef_struct.members[i]);
            free(node->typedef_struct.members);
            free(node->typedef_struct.typedef_name);
            break;
        case AST_MEMBER_ACCESS:
            free(node->member_access.member);
            free_ast(node->member_access.lhs);
            break;
        case AST_ARROW_ACCESS:
            free(node->arrow_access.member);
            free_ast(node->arrow_access.lhs);
            break;
        case AST_INIT_LIST:
            for (int i = 0; i < node->init_list.count; i++)
                free_ast(node->init_list.elements[i]);
            free(node->init_list.elements);
            break;
        case AST_SIZEOF:
            free_ast(node->sizeof_expr.expr);
            break;
        case AST_WHILE:
            free_ast(node->while_stmt.cond);
            free_ast(node->while_stmt.body);
            break;
        case AST_DO_WHILE:
            free_ast(node->do_while_stmt.cond);
            free_ast(node->do_while_stmt.body);
            break;
        case AST_FOR:
            if (node->for_stmt.init) free_ast(node->for_stmt.init);
            if (node->for_stmt.cond) free_ast(node->for_stmt.cond);
            if (node->for_stmt.inc) free_ast(node->for_stmt.inc);
            free_ast(node->for_stmt.body);
            break;
        case AST_BREAK:
        case AST_CONTINUE:
            break;
        default:
            fprintf(stderr, "Unknown AST Node Type: %d\n", node->type);
            exit(1);
    }
    free(node);
}
