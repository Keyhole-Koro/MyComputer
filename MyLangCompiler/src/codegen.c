#include "codegen.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

// --- Basic struct support scaffolding ---
typedef struct {
    const char *name;   // member name
    int offset;         // byte offset from base (slot-based for now)
    int size_bytes;     // natural element size (1 for char, SLOT_SIZE for word-sized)
    int total_size_bytes; // full storage size for the member (arrays etc.)
    const char *base_type;  // underlying base type name
    int pointer_level;      // pointer count for the member type
    int is_array;           // whether member is declared as array
    int array_length;       // first dimension length if array (0 if unknown)
} MemberInfo;

typedef struct {
    const char *type_name;   // typedef name or struct name
    MemberInfo *members;     // flat members (no nesting)
    int member_count;
    int size_bytes;          // total size in bytes (slot-based approximation)
} StructInfo;

typedef struct {
    const char *name;       // variable name
    const char *base_type;  // type name (typedef/struct)
    int pointer_level;      // explicit pointer level (excludes array levels)
    int type_modifiers;     // bitmask of TypeModifier (const etc.)
    int is_array;           // whether the declaration was an array
    int array_length;       // first dimension length if array (legacy)
    int dims[8];            // array dimensions outer->inner (unknown => 0)
    int dims_count;
} LocalInfo;

typedef struct {
    const char *base_type;
    int pointer_level;
    int type_modifiers; // TypeModifier bitmask from AST
    int is_array;
    int dims[8];
    int dims_count;
} TypeInfo;

// ---- String literal pool ----
typedef struct {
    char *text;     // NUL-terminated literal contents (without quotes)
    char *label;    // label name like s_0
} StrItem;

typedef struct {
    const char *alias;
    TypeInfo info;
} TypedefInfo;

// ---- Codegen context (keeps state in one place) ----
typedef struct {
    StructInfo *structs;
    int struct_count;
    TypedefInfo *typedefs;
    int typedef_count;
    LocalInfo *locals_info;
    int locals_count;
    StrItem *strings;
    int string_count;
    StringBuilder data_sb; // holds emitted data bytes
    int data_sb_inited;
    int label_counter;
    const char *return_label;
} CompilerContext;

#define cg_structs       (cc->structs)
#define cg_struct_count  (cc->struct_count)
#define cg_typedefs      (cc->typedefs)
#define cg_typedef_count (cc->typedef_count)
#define cg_locals_info   (cc->locals_info)
#define cg_locals_count  (cc->locals_count)
#define cg_strings       (cc->strings)
#define cg_string_count  (cc->string_count)
#define cg_data_sb       (cc->data_sb)
#define cg_data_sb_inited (cc->data_sb_inited)

static const char *intern_string_literal(CompilerContext *cc, const char *s)
{
    // deduplicate
    for (int i = 0; i < cg_string_count; i++) {
        if (strcmp(cg_strings[i].text, s) == 0) return cg_strings[i].label;
    }
    // create new
    char buf[32];
    snprintf(buf, sizeof(buf), "s_%d", cg_string_count);
    StrItem it = { strdup(s), strdup(buf) };
    // ensure data sb
    if (!cg_data_sb_inited) { sb_init(&cg_data_sb); cg_data_sb_inited = 1; }
    // emit data for this string as bytes plus NUL
    sb_append(&cg_data_sb, "%s:\n", it.label);
    // Prefer a simple .byte list (emit bytes in hex)
    sb_append(&cg_data_sb, "  .byte ");
    const unsigned char *p = (const unsigned char*)s;
    int first = 1;
    while (*p) {
        sb_append(&cg_data_sb, "%s0x%02X", first ? "" : ", ", (unsigned)*p);
        first = 0;
        p++;
    }
    // terminating NUL
    sb_append(&cg_data_sb, "%s0x00\n", first ? "" : ", ");

    // store
    cg_strings = (StrItem*)realloc(cg_strings, sizeof(StrItem) * (cg_string_count + 1));
    cg_strings[cg_string_count++] = it;
    return it.label;
}

static const TypedefInfo *find_typedef(CompilerContext *cc, const char *alias) {
    for (int i = 0; i < cg_typedef_count; i++) {
        if (strcmp(cg_typedefs[i].alias, alias) == 0) return &cg_typedefs[i];
    }
    return NULL;
}

static void resolve_type(CompilerContext *cc, TypeInfo *ti) {
    if (!ti || !ti->base_type) return;
    for (int depth = 0; depth < 10; depth++) {
        const TypedefInfo *td = find_typedef(cc, ti->base_type);
        if (!td) break;
        ti->base_type = td->info.base_type;
        ti->pointer_level += td->info.pointer_level;
        ti->type_modifiers |= td->info.type_modifiers;
        if (td->info.is_array) {
            ti->is_array = 1;
            int offset = ti->dims_count;
            int new_count = ti->dims_count + td->info.dims_count;
            if (new_count > 8) new_count = 8;
            for (int k = 0; k < td->info.dims_count && (offset + k) < 8; k++) {
                ti->dims[offset + k] = td->info.dims[k];
            }
            ti->dims_count = new_count;
        }
    }
}

static int next_label(CompilerContext *cc) {
    return cc->label_counter++;
}

// Argument registers for first three args
static const char *arg_regs[] = {"r5", "r6", "r7"};

// (usually 4)
#define SLOT_SIZE 4

// Get offset for parameter n (first param: n=0 → bp+4)
static int param_offset(int n) { return -(4 + n * SLOT_SIZE); }
// Get offset for local n (first local: n=0 → bp-4)
static int local_offset(int n) { return -SLOT_SIZE * (n + 1); }

// Find param index by name, or -1
static int param_index(const char *name, char **params, int param_count)
{
    for (int i = 0; i < param_count; i++)
        if (strcmp(name, params[i]) == 0)
            return i;
    return -1;
}
static int local_index_last(const char *name, char **locals, int local_count)
{
    int idx = -1;
    for (int i = 0; i < local_count; i++) {
        if (locals[i] && strcmp(name, locals[i]) == 0) idx = i;
    }
    return idx;
}

static const LocalInfo *find_local_info(CompilerContext *cc, const char *name);

static const StructInfo *find_struct(CompilerContext *cc, const char *type_name);

static void gen_lvalue_addr(CompilerContext *cc, ASTNode *node, StringBuilder *sb, const char *target_reg,
                            char **params, int param_count,
                            char **locals, int local_count);
                            
static void gen_stmt(CompilerContext *cc, ASTNode *node, StringBuilder *sb,
    char **params, int param_count,
    char **locals, int local_count);

static void gen_stmt_internal(CompilerContext *cc, ASTNode *node, StringBuilder *sb,
    char **params, int param_count,
    char **locals, int local_count,
    const char *break_label,
    const char *continue_label);

// Internal function prototypes (used before their definitions)
static void emit_load_var(CompilerContext *cc, StringBuilder *sb, const char *name, const char *target_reg,
                          char **params, int param_count,
                          char **locals, int local_count);
static void emit_store_var(CompilerContext *cc, StringBuilder *sb, const char *name, const char *src_reg,
                           char **params, int param_count,
                           char **locals, int local_count);
static void emit_store_to_addr(StringBuilder *sb, const char *addr_reg, const char *value_reg, int is_byte);
static void emit_addr_of_var(CompilerContext *cc, StringBuilder *sb, const char *name, const char *target_reg,
                             char **params, int param_count, char **locals, int local_count);
static void emit_cond_jump(CompilerContext *cc, ASTNode *left, ASTNode *right, TokenKind op, StringBuilder *sb,
                           char **params, int param_count, char **locals, int local_count,
                           const char *trueLabel, const char *falseLabel);
static void gen_expr(CompilerContext *cc, ASTNode *node, StringBuilder *sb, const char *target_reg,
                     char **params, int param_count,
                     char **locals, int local_count);
static void _gen_expr(CompilerContext *cc, ASTNode *node, StringBuilder *sb, const char *target_reg,
                      char **params, int param_count,
                      char **locals, int local_count,
                      int load_value);
static void gen_expr_binop(CompilerContext *cc, ASTNode *node, StringBuilder *sb, const char *target_reg,
                           char **params, int param_count, char **locals, int local_count);
static void gen_call(CompilerContext *cc, ASTNode *node, StringBuilder *sb, const char *target_reg,
                     char **params, int param_count, char **locals, int local_count);
static void gen_if(CompilerContext *cc, ASTNode *node, StringBuilder *sb,
                   char **params, int param_count,
                   char **locals, int local_count,
                   const char *break_label,
                   const char *continue_label);
static void gen_for(CompilerContext *cc, ASTNode *node, StringBuilder *sb,
                    char **params, int param_count,
                    char **locals, int local_count,
                    const char *break_label,
                    const char *continue_label);
static void gen_while(CompilerContext *cc, ASTNode *node, StringBuilder *sb,
                      char **params, int param_count,
                      char **locals, int local_count,
                      const char *break_label,
                      const char *continue_label);
static void set_localinfo_from_type(CompilerContext *cc, LocalInfo *info, ASTNode *type_node);
static int base_type_is_char(const char *name);
static int typeinfo_is_byte(const TypeInfo *info);
static int infer_expr_type(CompilerContext *cc, ASTNode *expr, TypeInfo *out);
static int pointer_step_bytes(CompilerContext *cc, const TypeInfo *info);
static int typeinfo_elem_size_bytes(CompilerContext *cc, const TypeInfo *info);
static int typeinfo_total_size_bytes(CompilerContext *cc, const TypeInfo *info);
// Char/byte and struct helpers (forward decls)
static const MemberInfo *find_member_info(CompilerContext *cc, const char *type_name, const char *member);
static int is_char_scalar_var(CompilerContext *cc, const char *name);
static int lvalue_is_byte(CompilerContext *cc, ASTNode *node);
static int lvalue_is_const(CompilerContext *cc, ASTNode *node);
static void emit_load_from_addr(StringBuilder *sb, const char *target_reg, const char *addr_reg, int is_byte);
static void emit_store_to_addr(StringBuilder *sb, const char *addr_reg, const char *value_reg, int is_byte);
static void emit_scale_reg_const(CompilerContext *cc, StringBuilder *sb, const char *reg, long factor);

// Recursively collect all local variable names in the block and its nested statements
static int slots_for_type(CompilerContext *cc, ASTNode *type_node)
{
    if (!type_node) return 1;
    if (type_node->type == AST_TYPE_ARRAY) {
        int elem = slots_for_type(cc, type_node->type_array.element_type);
        int n = type_node->type_array.array_size;
        if (n <= 0) n = 1;
        return elem * n;
    }
    if (type_node->type == AST_TYPE) {
        if (type_node->type_node.pointer_level > 0) return 1;
        ASTNode *bt = type_node->type_node.base_type;
        if (bt && bt->type == AST_IDENTIFIER) {
            const StructInfo *si = find_struct(cc, bt->identifier.name);
            if (si) {
                if (si->size_bytes > 0)
                    return (si->size_bytes + SLOT_SIZE - 1) / SLOT_SIZE;
                return si->member_count > 0 ? si->member_count : 1;
            }
        }
        return 1;
    }
    return 1;
}

static int collect_locals(CompilerContext *cc, ASTNode *node, char **locals)
{
    int count = 0;
    if (!node)
        return 0;
    switch (node->type)
    {
    case AST_BLOCK:
        for (int i = 0; i < node->block.count; i++)
        {
            count += collect_locals(cc, node->block.stmts[i], locals + count);
        }
        break;
    case AST_VAR_DECL: {
        int slots = slots_for_type(cc, node->var_decl.var_type);
        if (slots < 1) slots = 1;
        for (int s = 0; s < slots; s++) {
            locals[count++] = node->var_decl.name;
        }
        break; }
    case AST_FOR:
        // Collect locals from the init part (e.g. for (int i = ...))
        if (node->for_stmt.init)
            count += collect_locals(cc, node->for_stmt.init, locals + count);
        // Collect from body and inc, just in case there are decls there too
        if (node->for_stmt.body)
            count += collect_locals(cc, node->for_stmt.body, locals + count);
        if (node->for_stmt.inc)
            count += collect_locals(cc, node->for_stmt.inc, locals + count);
        break;
    case AST_IF:
        if (node->if_stmt.then_stmt)
            count += collect_locals(cc, node->if_stmt.then_stmt, locals + count);
        if (node->if_stmt.else_stmt)
            count += collect_locals(cc, node->if_stmt.else_stmt, locals + count);
        break;
    // Add other cases (AST_WHILE, AST_BLOCK, etc.) if needed
    default:
        break;
    }
    return count;
}

// Compute offset for a variable name
static int find_var_offset(const char *name, char **params, int param_count,
                    char **locals, int local_count, int *is_param)
{
    int idx = param_index(name, params, param_count);
    if (idx >= 0)
    {
        if (is_param)
            *is_param = 1;
        if (idx < 3)
            return param_offset(idx);
        return 8 + (idx - 3) * SLOT_SIZE;
    }
    idx = local_index_last(name, locals, local_count);
    if (idx >= 0)
    {
        if (is_param)
            *is_param = 0;
        return local_offset(idx);
    }
    if (is_param)
        *is_param = -1;
    return 0;
}

static void emit_unary_inc_dec(CompilerContext *cc, ASTNode *node, StringBuilder *sb, const char *target_reg,
                        char **params, int param_count,
                        char **locals, int local_count)
{
    if (!node || node->type != AST_UNARY) {
        fprintf(stderr, "Codegen error: emit_unary_inc_dec on non-unary node\n");
        exit(1);
    }
    if (lvalue_is_const(cc, node->unary.operand)) {
        fprintf(stderr, "Codegen error: modifying a const value is not allowed\n");
        exit(1);
    }

    // Compute address of operand lvalue into r3
    gen_lvalue_addr(cc, node->unary.operand, sb, "r3", params, param_count, locals, local_count);
    int is_byte = lvalue_is_byte(cc, node->unary.operand);
    // Load current value into r1
    emit_load_from_addr(sb, "r1", "r3", is_byte);

    int delta = 1;
    TypeInfo operand_type = (TypeInfo){0};
    if (infer_expr_type(cc, node->unary.operand, &operand_type) && operand_type.pointer_level > 0) {
        delta = pointer_step_bytes(cc, &operand_type);
    }

    switch (node->unary.op) {
    case POST_INC: {
        // result is original value
        if (strcmp(target_reg, "r1") != 0)
            sb_append(sb, "  mov %s, r1\n", target_reg);
        sb_append(sb, "  addis r1, %d\n", delta);
        emit_store_to_addr(sb, "r3", "r1", is_byte);
        break; }
    case POST_DEC: {
        if (strcmp(target_reg, "r1") != 0)
            sb_append(sb, "  mov %s, r1\n", target_reg);
        sb_append(sb, "  addis r1, -%d\n", delta);
        emit_store_to_addr(sb, "r3", "r1", is_byte);
        break; }
    case INC: {
        sb_append(sb, "  addis r1, %d\n", delta);
        emit_store_to_addr(sb, "r3", "r1", is_byte);
        if (strcmp(target_reg, "r1") != 0)
            sb_append(sb, "  mov %s, r1\n", target_reg);
        break; }
    case DEC: {
        sb_append(sb, "  addis r1, -%d\n", delta);
        emit_store_to_addr(sb, "r3", "r1", is_byte);
        if (strcmp(target_reg, "r1") != 0)
            sb_append(sb, "  mov %s, r1\n", target_reg);
        break; }
    default:
        fprintf(stderr, "Codegen error: unknown unary inc/dec op\n");
        exit(1);
    }
}

// Emit code to load variable (param/local/global) to target_reg
static void emit_load_var(CompilerContext *cc, StringBuilder *sb, const char *name, const char *target_reg,
                   char **params, int param_count,
                   char **locals, int local_count)
{
    const LocalInfo *li_info = find_local_info(cc, name);
    if (li_info && li_info->is_array) {
        // arrays decay to pointers
        emit_addr_of_var(cc, sb, name, target_reg, params, param_count, locals, local_count);
        return;
    }

    int idx = param_index(name, params, param_count);
    int offset;
    if (idx >= 0)
    {
        if (idx < 3)
        {
            // bp-4, bp-8, bp-12…
            offset = -(4 + idx * SLOT_SIZE);
            sb_append(sb, "  \n; load param '%s' (arg%d, reg) into %s\n", name, idx + 1, target_reg);
            sb_append(sb, "  mov   r3, bp\n");
            sb_append(sb, "  addis r3, %d\n", offset);
            emit_load_from_addr(sb, target_reg, "r3", is_char_scalar_var(cc, name));
        }
        else
        {
            // bp+N
            offset = 8 + (idx - 3) * SLOT_SIZE;
            sb_append(sb, "  \n; load param '%s' (arg%d, stack) into %s\n", name, idx + 1, target_reg);
            sb_append(sb, "  mov   r3, bp\n");
            sb_append(sb, "  addis r3, %d\n", offset);
            emit_load_from_addr(sb, target_reg, "r3", is_char_scalar_var(cc, name));
        }
    }
    else
    {
        int local_idx = local_index_last(name, locals, local_count);
        if (local_idx >= 0)
        {
            // bp-4, bp-8, ...
            offset = -SLOT_SIZE * (local_idx + 1);
            sb_append(sb, "  \n; load local '%s' into %s\n", name, target_reg);
            sb_append(sb, "  mov   r3, bp\n");
            sb_append(sb, "  addis r3, %d\n", offset);
            emit_load_from_addr(sb, target_reg, "r3", is_char_scalar_var(cc, name));
        }
        else
        {
            // fallback global
            sb_append(sb, "  movi  r2, %s\n", name);
            sb_append(sb, "  load  %s, r2\n", target_reg);
        }
    }
}

// Emit code to store target_reg to variable (param/local/global)
static void emit_store_var(CompilerContext *cc, StringBuilder *sb, const char *name, const char *src_reg,
                    char **params, int param_count,
                    char **locals, int local_count)
{
    int is_param = 0;
    int offset = find_var_offset(name, params, param_count, locals, local_count, &is_param);
    if (is_param == 1 || is_param == 0)
    {
        sb_append(sb, "  \n; store %s to var '%s'\n", src_reg, name);
        sb_append(sb, "  mov   r3, bp\n");
        sb_append(sb, "  addis r3, %d\n", offset);
        emit_store_to_addr(sb, "r3", src_reg, is_char_scalar_var(cc, name));
    }
    else
    {
        // fallback global
        sb_append(sb, "  movi  r3, %s\n", name);
        sb_append(sb, "  store r3, %s\n", src_reg);
    }
}

static void emit_addr_of_var(CompilerContext *cc, StringBuilder *sb, const char *name, const char *target_reg,
                      char **params, int param_count, char **locals, int local_count)
{
    int is_param = 0;
    int offset = find_var_offset(name, params, param_count, locals, local_count, &is_param);
    if (is_param == 0) {
        const LocalInfo *li = find_local_info(cc, name);
        int occur = 0;
        for (int i = 0; i < local_count; i++) {
            if (locals[i] && strcmp(locals[i], name) == 0) occur++;
        }
        if ((li && li->is_array) || occur > 1) {
            int last = local_index_last(name, locals, local_count);
            if (last >= 0) offset = local_offset(last);
        }
    }
    if (is_param == -1) {
        sb_append(sb, "  \n; address of global '%s'\n", name);
        sb_append(sb, "  movi %s, %s\n", target_reg, name);
        return;
    }
    sb_append(sb, "  \n; address of '%s'\n", name);
    sb_append(sb, "  mov   %s, bp\n", target_reg);
    sb_append(sb, "  addis %s, %d\n", target_reg, offset);
}

static int is_comparison_op(TokenKind op) {
    return op == EQ || op == NEQ || op == LT || op == GT || op == LTE || op == GTE;
}

// Emit conditional jump based on binary comparison operator
// If the condition is true, jump to `trueLabel`
// If the condition is false, jump to `falseLabel` (optional)
// Supported operators: ==, !=, <, >, <=, >= using basic jz, jnz, jl, jg
static void emit_cond_jump(CompilerContext *cc, ASTNode *left, ASTNode *right, TokenKind op, StringBuilder *sb,
                    char **params, int param_count, char **locals, int local_count,
                    const char *trueLabel, const char *falseLabel)
{
    // Generate left and right expressions into r2 and r3
    gen_expr(cc, left, sb, "r2", params, param_count, locals, local_count);
    gen_expr(cc, right, sb, "r3", params, param_count, locals, local_count);
    sb_append(sb, "  cmp r2, r3\n");

    // Emit jump instructions based on operator
    switch (op)
    {
    case EQ: // ==
        sb_append(sb, "  jz %s\n", trueLabel);
        if (falseLabel)
            sb_append(sb, "  jmp %s\n", falseLabel);
        break;
    case NEQ: // !=
        sb_append(sb, "  jnz %s\n", trueLabel);
        if (falseLabel)
            sb_append(sb, "  jmp %s\n", falseLabel);
        break;
    case LT: // <
        sb_append(sb, "  jl %s\n", trueLabel);
        if (falseLabel)
            sb_append(sb, "  jmp %s\n", falseLabel);
        break;
    case GT: // >
        sb_append(sb, "  jg %s\n", trueLabel);
        if (falseLabel)
            sb_append(sb, "  jmp %s\n", falseLabel);
        break;
    case LTE: // <= → !(a > b)
        if (falseLabel)
            sb_append(sb, "  jg %s\n", falseLabel); // if a > b → jump to false
        sb_append(sb, "  jmp %s\n", trueLabel);     // else → true
        break;
    case GTE: // >= → !(a < b)
        if (falseLabel)
            sb_append(sb, "  jl %s\n", falseLabel); // if a < b → jump to false
        sb_append(sb, "  jmp %s\n", trueLabel);     // else → true
        break;
    default:
        // Fallback: treat nonzero as true
        sb_append(sb, "  jnz %s\n", trueLabel);
        if (falseLabel)
            sb_append(sb, "  jmp %s\n", falseLabel);
        break;
    }
}

// gen_expr: output result to target_reg (should be r5/r6/r7)
static void gen_expr(CompilerContext *cc, ASTNode *node, StringBuilder *sb, const char *target_reg,
              char **params, int param_count,
              char **locals, int local_count);

// ---- Struct support helpers ----
static const StructInfo *find_struct(CompilerContext *cc, const char *type_name) {
    for (int i = 0; i < cg_struct_count; i++) {
        if (strcmp(cg_structs[i].type_name, type_name) == 0) return &cg_structs[i];
    }
    return NULL;
}

static const MemberInfo *find_member_info(CompilerContext *cc, const char *type_name, const char *member) {
    const StructInfo *si = find_struct(cc, type_name);
    if (!si) return NULL;
    for (int i = 0; i < si->member_count; i++)
        if (strcmp(si->members[i].name, member) == 0) return &si->members[i];
    return NULL;
}

static int base_type_is_char(const char *name) {
    return name && strcmp(name, "char") == 0;
}

static int ast_type_is_char_scalar(ASTNode *type_node) {
    if (!type_node || type_node->type != AST_TYPE) return 0;
    if (type_node->type_node.pointer_level != 0) return 0;
    ASTNode *bt = type_node->type_node.base_type;
    if (bt && bt->type == AST_IDENTIFIER)
        return base_type_is_char(bt->identifier.name);
    return 0;
}

static int is_char_scalar_var(CompilerContext *cc, const char *name) {
    const LocalInfo *li = find_local_info(cc, name);
    return (li && li->pointer_level == 0 && !li->is_array && base_type_is_char(li->base_type));
}

static int typeinfo_is_byte(const TypeInfo *info) {
    return info && info->pointer_level == 0 && info->dims_count == 0 && base_type_is_char(info->base_type);
}

static int infer_expr_type(CompilerContext *cc, ASTNode *expr, TypeInfo *out) {
    if (!expr || !out) return 0;
    out->base_type = "";
    out->pointer_level = 0;
    out->type_modifiers = 0;
    out->is_array = 0;
    out->dims_count = 0;
    for (int i = 0; i < 8; i++) out->dims[i] = 0;
    switch (expr->type) {
    case AST_IDENTIFIER: {
        const LocalInfo *li = find_local_info(cc, expr->identifier.name);
        if (!li) return 0;
        out->base_type = li->base_type;
        out->pointer_level = li->pointer_level;
        out->type_modifiers = li->type_modifiers;
        out->is_array = li->is_array;
        out->dims_count = li->dims_count;
        for (int i = 0; i < li->dims_count && i < 8; i++) out->dims[i] = li->dims[i];
        // Arrays decay to pointer-to-first-element when used as value
        if (li->is_array && li->dims_count > 0) {
            out->pointer_level += 1;
            // drop the first dimension (array -> pointer to element array)
            for (int i = 1; i < li->dims_count; i++) out->dims[i-1] = li->dims[i];
            out->dims_count = li->dims_count - 1;
            out->is_array = out->dims_count > 0;
        }
        return 1;
    }
    case AST_NUMBER:
        out->base_type = "int";
        out->pointer_level = 0;
        out->type_modifiers = 0;
        out->is_array = 0;
        out->dims_count = 0;
        return 1;
    case AST_MEMBER_ACCESS: {
        TypeInfo lhs = {0};
        if (!infer_expr_type(cc, expr->member_access.lhs, &lhs)) return 0;
        if (!lhs.base_type || lhs.base_type[0] == '\0') return 0;
        const MemberInfo *mi = find_member_info(cc, lhs.base_type, expr->member_access.member);
        if (!mi) return 0;
        out->base_type = mi->base_type ? mi->base_type : "";
        out->pointer_level = mi->pointer_level;
        out->type_modifiers = lhs.type_modifiers;
        out->is_array = mi->is_array;
        if (mi->is_array) out->pointer_level += 1;
        out->dims_count = 0;
        return 1;
    }
    case AST_ARROW_ACCESS: {
        TypeInfo lhs = {0};
        if (!infer_expr_type(cc, expr->arrow_access.lhs, &lhs)) return 0;
        if (lhs.pointer_level <= 0 || !lhs.base_type || lhs.base_type[0] == '\0') return 0;
        const MemberInfo *mi = find_member_info(cc, lhs.base_type, expr->arrow_access.member);
        if (!mi) return 0;
        out->base_type = mi->base_type ? mi->base_type : "";
        out->pointer_level = mi->pointer_level;
        out->type_modifiers = lhs.type_modifiers;
        out->is_array = mi->is_array;
        if (mi->is_array) out->pointer_level += 1;
        out->dims_count = 0;
        return 1;
    }
    case AST_SIZEOF:
        out->base_type = "int";
        out->pointer_level = 0;
        out->type_modifiers = 0;
        out->is_array = 0;
        out->dims_count = 0;
        return 1;
    case AST_BINARY: {
        TypeInfo lhs = {0};
        TypeInfo rhs = {0};
        if (!infer_expr_type(cc, expr->binary.left, &lhs) ||
            !infer_expr_type(cc, expr->binary.right, &rhs)) {
            return 0;
        }

        if (expr->binary.op == ADD || expr->binary.op == SUB) {
            if (lhs.pointer_level > 0 && rhs.pointer_level == 0) {
                *out = lhs;
                return 1;
            }
            if (expr->binary.op == ADD && rhs.pointer_level > 0 && lhs.pointer_level == 0) {
                *out = rhs;
                return 1;
            }
            if (expr->binary.op == SUB && lhs.pointer_level > 0 && rhs.pointer_level > 0) {
                out->base_type = "int";
                out->pointer_level = 0;
                out->is_array = 0;
                out->dims_count = 0;
                return 1;
            }
        }

        if (lhs.pointer_level == 0 && rhs.pointer_level == 0) {
            *out = lhs;
            return 1;
        }
        return 0;
    }
    case AST_UNARY:
        if (expr->unary.op == ASTARISK) {
            TypeInfo inner = {0};
            if (!infer_expr_type(cc, expr->unary.operand, &inner)) return 0;
            if (inner.pointer_level <= 0) return 0;
            out->base_type = inner.base_type;
            out->pointer_level = inner.pointer_level - 1;
            out->type_modifiers = inner.type_modifiers;
            out->dims_count = inner.dims_count;
            for (int i = 0; i < inner.dims_count; i++) out->dims[i] = inner.dims[i];
            out->is_array = (out->dims_count > 0);
            return 1;
        } else if (expr->unary.op == AMPERSAND) {
            TypeInfo inner = {0};
            if (!infer_expr_type(cc, expr->unary.operand, &inner)) return 0;
            out->base_type = inner.base_type;
            out->pointer_level = inner.pointer_level + 1;
            out->type_modifiers = inner.type_modifiers;
            out->dims_count = inner.dims_count;
            for (int i = 0; i < inner.dims_count; i++) out->dims[i] = inner.dims[i];
            out->is_array = inner.is_array;
            return 1;
        }
        return 0;
    case AST_TERNARY: {
        TypeInfo t = {0};
        if (infer_expr_type(cc, expr->ternary.then_expr, &t)) {
            *out = t;
            return 1;
        }
        if (infer_expr_type(cc, expr->ternary.else_expr, &t)) {
            *out = t;
            return 1;
        }
        return 0;
    }
    default:
        return 0;
    }
}

static int typeinfo_elem_size_bytes(CompilerContext *cc, const TypeInfo *info) {
    if (!info || !info->base_type) return SLOT_SIZE;
    if (base_type_is_char(info->base_type)) return 1;
    const StructInfo *si = find_struct(cc, info->base_type);
    if (si && si->size_bytes > 0) return si->size_bytes;
    return SLOT_SIZE;
}

static int typeinfo_total_size_bytes(CompilerContext *cc, const TypeInfo *info) {
    if (!info) return SLOT_SIZE;
    if (info->pointer_level > 0 && info->dims_count == 0) return SLOT_SIZE;
    long sz = typeinfo_elem_size_bytes(cc, info);
    for (int i = 0; i < info->dims_count; i++) {
        int len = info->dims[i] > 0 ? info->dims[i] : 1;
        sz *= len;
    }
    if (sz <= 0) sz = SLOT_SIZE;
    return (int)sz;
}

static int pointer_step_bytes(CompilerContext *cc, const TypeInfo *info) {
    if (!info) return 1;
    if (info->pointer_level <= 0) {
        if (info->dims_count > 0) {
            long sz = typeinfo_elem_size_bytes(cc, info);
            for (int i = 1; i < info->dims_count; i++) {
                int len = info->dims[i] > 0 ? info->dims[i] : 1;
                sz *= len;
            }
            if (sz <= 0) sz = SLOT_SIZE;
            return (int)sz;
        }
        return 1;
    }
    // pointer_level > 0
    if (info->dims_count > 0) {
        return typeinfo_total_size_bytes(cc, info);
    }
    if (info->pointer_level > 1) return SLOT_SIZE; // pointer to pointer etc.
    return typeinfo_elem_size_bytes(cc, info);
}

static int array_element_size_bytes(ASTNode *array_type) {
    if (!array_type || array_type->type != AST_TYPE_ARRAY) return SLOT_SIZE;
    ASTNode *elem = array_type->type_array.element_type;
    if (ast_type_is_char_scalar(elem)) return 1;
    return SLOT_SIZE;
}

static int array_total_elements(ASTNode *array_type) {
    if (!array_type || array_type->type != AST_TYPE_ARRAY) return 1;
    int n = array_type->type_array.array_size > 0 ? array_type->type_array.array_size : 1;
    return n * array_total_elements(array_type->type_array.element_type);
}

static int lvalue_is_byte(CompilerContext *cc, ASTNode *node) {
    TypeInfo info = (TypeInfo){0};
    if (!infer_expr_type(cc, node, &info)) return 0;
    return typeinfo_is_byte(&info);
}

static int lvalue_is_const(CompilerContext *cc, ASTNode *node) {
    TypeInfo info = (TypeInfo){0};
    if (!infer_expr_type(cc, node, &info)) return 0;
    return (info.type_modifiers & TYPEMOD_CONST) != 0;
}

static void emit_load_from_addr(StringBuilder *sb, const char *target_reg, const char *addr_reg, int is_byte) {
    if (is_byte)
        sb_append(sb, "  loadb %s, %s\n", target_reg, addr_reg);
    else
        sb_append(sb, "  load %s, %s\n", target_reg, addr_reg);
}

static void emit_store_to_addr(StringBuilder *sb, const char *addr_reg, const char *value_reg, int is_byte) {
    if (is_byte)
        sb_append(sb, "  storeb %s, %s\n", addr_reg, value_reg);
    else
        sb_append(sb, "  store %s, %s\n", addr_reg, value_reg);
}

static void emit_scale_reg_const(CompilerContext *cc, StringBuilder *sb, const char *reg, long factor) {
    if (factor == 1) return;
    if (factor <= 0) {
        sb_append(sb, "  ; unsupported scale factor %ld\n", factor);
        return;
    }
    sb_append(sb, "  ; scale %s by %ld\n", reg, factor);
    sb_append(sb, "  mov r4, %s\n", reg);
    sb_append(sb, "  movi %s, 0\n", reg);
    sb_append(sb, "  movi r5, %ld\n", factor);
    int lbl = next_label(cc);
    sb_append(sb, "b_idx_mul_%d:\n", lbl);
    sb_append(sb, "  cmp r5, 0\n");
    sb_append(sb, "  jz b_idx_mul_end_%d\n", lbl);
    sb_append(sb, "  add %s, r4\n", reg);
    sb_append(sb, "  addis r5, -1\n");
    sb_append(sb, "  jmp b_idx_mul_%d\n", lbl);
    sb_append(sb, "b_idx_mul_end_%d:\n", lbl);
}

static const LocalInfo *find_local_info(CompilerContext *cc, const char *name) {
    for (int i = 0; i < cg_locals_count; i++) {
        if (strcmp(cg_locals_info[i].name, name) == 0) return &cg_locals_info[i];
    }
    return NULL;
}

static void set_localinfo_from_type(CompilerContext *cc, LocalInfo *info, ASTNode *type_node) {
    if (!info) return;
    info->base_type = "";
    info->pointer_level = 0;
    info->type_modifiers = 0;
    info->is_array = 0;
    info->array_length = 0;
    info->dims_count = 0;
    for (int i = 0; i < 8; i++) info->dims[i] = 0;
    if (!type_node) return;

    // Collect array dimensions from inner-most to outer-most then reverse
    int tmp_dims[8] = {0};
    int tmp_count = 0;
    ASTNode *node = type_node;
    while (node && node->type == AST_TYPE_ARRAY && tmp_count < 8) {
        tmp_dims[tmp_count++] = node->type_array.array_size;
        node = node->type_array.element_type;
    }
    if (tmp_count > 0) info->is_array = 1;
    for (int i = 0; i < tmp_count; i++) {
        int dim = tmp_dims[tmp_count - 1 - i]; // reverse so dims[0] is outer-most
        info->dims[i] = dim;
        if (i == 0 && info->array_length == 0 && dim > 0) {
            info->array_length = dim;
        }
        info->dims_count++;
    }

    if (node->type == AST_TYPE) {
        ASTNode *bt = node->type_node.base_type;
        if (bt && bt->type == AST_IDENTIFIER) {
            info->base_type = bt->identifier.name;
        }
        info->pointer_level = node->type_node.pointer_level;
        info->type_modifiers = node->type_node.type_modifiers;
    } else {
        info->pointer_level = 0;
    }

    // Resolve typedefs
    TypeInfo ti;
    ti.base_type = info->base_type;
    ti.pointer_level = info->pointer_level;
    ti.type_modifiers = info->type_modifiers;
    ti.is_array = info->is_array;
    ti.dims_count = info->dims_count;
    for(int i=0; i<8; i++) ti.dims[i] = info->dims[i];

    resolve_type(cc, &ti);

    info->base_type = ti.base_type;
    info->pointer_level = ti.pointer_level;
    info->type_modifiers = ti.type_modifiers;
    info->is_array = ti.is_array;
    info->dims_count = ti.dims_count;
    for(int i=0; i<8; i++) info->dims[i] = ti.dims[i];
    if (info->is_array && info->dims_count > 0) info->array_length = info->dims[0];
}

static int collect_local_type_info(CompilerContext *cc, ASTNode *node, LocalInfo *arr) {
    int n = 0;
    if (!node) return 0;
    switch (node->type) {
    case AST_BLOCK:
        for (int i = 0; i < node->block.count; i++)
            n += collect_local_type_info(cc, node->block.stmts[i], arr ? (arr + n) : NULL);
        break;
    case AST_VAR_DECL:
        if (arr) {
            arr[n].name = node->var_decl.name;
            set_localinfo_from_type(cc, &arr[n], node->var_decl.var_type);
        }
        n++;
        break;
    case AST_FOR:
        if (node->for_stmt.init)
            n += collect_local_type_info(cc, node->for_stmt.init, arr ? (arr + n) : NULL);
        n += collect_local_type_info(cc, node->for_stmt.body, arr ? (arr + n) : NULL);
        if (node->for_stmt.inc)
            n += collect_local_type_info(cc, node->for_stmt.inc, arr ? (arr + n) : NULL);
        break;
    case AST_IF:
        n += collect_local_type_info(cc, node->if_stmt.then_stmt, arr ? (arr + n) : NULL);
        if (node->if_stmt.else_stmt)
            n += collect_local_type_info(cc, node->if_stmt.else_stmt, arr ? (arr + n) : NULL);
        break;
    default:
        break;
    }
    return n;
}

static void gen_lvalue_addr(CompilerContext *cc, ASTNode *node, StringBuilder *sb, const char *target_reg,
                            char **params, int param_count,
                            char **locals, int local_count) {
    if (!node) { sb_append(sb, "  ; gen_lvalue_addr: null\n"); return; }
    switch (node->type) {
    case AST_IDENTIFIER: {
        emit_addr_of_var(cc, sb, node->identifier.name, target_reg, params, param_count, locals, local_count);
        break; }
    case AST_UNARY: {
        if (node->unary.op == ASTARISK) {
            // address is the value of operand
            gen_expr(cc, node->unary.operand, sb, target_reg, params, param_count, locals, local_count);
        } else {
            sb_append(sb, "  ; unsupported lvalue op\n");
        }
        break; }
    case AST_MEMBER_ACCESS: {
        TypeInfo lhs_type = (TypeInfo){0};
        if (!infer_expr_type(cc, node->member_access.lhs, &lhs_type) ||
            !lhs_type.base_type || lhs_type.base_type[0] == '\0') {
            sb_append(sb, "  ; unknown member base type\n");
            break;
        }
        const MemberInfo *mi = find_member_info(cc, lhs_type.base_type, node->member_access.member);
        if (!mi) {
            sb_append(sb, "  ; unknown member %s of %s\n", node->member_access.member, lhs_type.base_type);
            break;
        }
        gen_lvalue_addr(cc, node->member_access.lhs, sb, target_reg, params, param_count, locals, local_count);
        sb_append(sb, "  addis %s, %d\n", target_reg, mi->offset);
        break; }
    case AST_ARROW_ACCESS: {
        TypeInfo lhs_type = (TypeInfo){0};
        if (!infer_expr_type(cc, node->arrow_access.lhs, &lhs_type) ||
            lhs_type.pointer_level <= 0 ||
            !lhs_type.base_type || lhs_type.base_type[0] == '\0') {
            sb_append(sb, "  ; unknown pointer base for arrow access\n");
            break;
        }
        const MemberInfo *mi = find_member_info(cc, lhs_type.base_type, node->arrow_access.member);
        if (!mi) {
            sb_append(sb, "  ; unknown member %s of %s\n", node->arrow_access.member, lhs_type.base_type);
            break;
        }
        gen_expr(cc, node->arrow_access.lhs, sb, target_reg, params, param_count, locals, local_count);
        sb_append(sb, "  addis %s, %d\n", target_reg, mi->offset);
        break; }
    default:
        sb_append(sb, "  ; unsupported lvalue kind: %s\n", astType2str(node->type));
    }
}

static void gen_expr_binop(CompilerContext *cc, ASTNode *node, StringBuilder *sb, const char *target_reg,
                    char **params, int param_count, char **locals, int local_count)
{
    if (node->binary.op == LAND) {
        int label = next_label(cc);
        char label_false[32], label_end[32];
        snprintf(label_false, sizeof(label_false), "b_land_false_%d", label);
        snprintf(label_end, sizeof(label_end), "b_land_end_%d", label);

        gen_expr(cc, node->binary.left, sb, "r1", params, param_count, locals, local_count);
        sb_append(sb, "  cmp r1, 0\n");
        sb_append(sb, "  jz %s\n", label_false);

        gen_expr(cc, node->binary.right, sb, "r1", params, param_count, locals, local_count);
        sb_append(sb, "  cmp r1, 0\n");
        sb_append(sb, "  jz %s\n", label_false);

        sb_append(sb, "  movi r1, 1\n");
        sb_append(sb, "  jmp %s\n", label_end);
        sb_append(sb, "%s:\n", label_false);
        sb_append(sb, "  movi r1, 0\n");
        sb_append(sb, "%s:\n", label_end);

        if (strcmp(target_reg, "r1") != 0)
            sb_append(sb, "  mov %s, r1\n", target_reg);
        return;
    }

    if (node->binary.op == LOR) {
        int label = next_label(cc);
        char label_true[32], label_end[32];
        snprintf(label_true, sizeof(label_true), "b_lor_true_%d", label);
        snprintf(label_end, sizeof(label_end), "b_lor_end_%d", label);

        gen_expr(cc, node->binary.left, sb, "r1", params, param_count, locals, local_count);
        sb_append(sb, "  cmp r1, 0\n");
        sb_append(sb, "  jnz %s\n", label_true);

        gen_expr(cc, node->binary.right, sb, "r1", params, param_count, locals, local_count);
        sb_append(sb, "  cmp r1, 0\n");
        sb_append(sb, "  jnz %s\n", label_true);

        sb_append(sb, "  movi r1, 0\n");
        sb_append(sb, "  jmp %s\n", label_end);
        sb_append(sb, "%s:\n", label_true);
        sb_append(sb, "  movi r1, 1\n");
        sb_append(sb, "%s:\n", label_end);

        if (strcmp(target_reg, "r1") != 0)
            sb_append(sb, "  mov %s, r1\n", target_reg);
        return;
    }

    // Pointer arithmetic with constant index: scale by element size
    TypeInfo lhs_t = {0}, rhs_t = {0};
    int lhs_ptr = infer_expr_type(cc, node->binary.left, &lhs_t) &&
                  (lhs_t.pointer_level > 0 || lhs_t.dims_count > 0);
    int rhs_ptr = infer_expr_type(cc, node->binary.right, &rhs_t) &&
                  (rhs_t.pointer_level > 0 || rhs_t.dims_count > 0);
    if ((node->binary.op == ADD || node->binary.op == SUB) && lhs_ptr != rhs_ptr) {
        ASTNode *ptr_expr = lhs_ptr ? node->binary.left : node->binary.right;
        ASTNode *idx_expr = lhs_ptr ? node->binary.right : node->binary.left;
        TypeInfo *ptr_t = lhs_ptr ? &lhs_t : &rhs_t;
        long step = pointer_step_bytes(cc, ptr_t);
        if (idx_expr->type == AST_NUMBER) {
            long idx_val = strtol(idx_expr->number.value, NULL, 10);
            long offset = idx_val * step;
            if (node->binary.op == SUB && lhs_ptr) offset = -offset;
            gen_expr(cc, ptr_expr, sb, target_reg, params, param_count, locals, local_count);
            if (offset != 0) {
                sb_append(sb, "  addis %s, %ld\n", target_reg, offset);
            }
            return;
        } else {
            // dynamic index
            gen_expr(cc, ptr_expr, sb, target_reg, params, param_count, locals, local_count);
            gen_expr(cc, idx_expr, sb, "r1", params, param_count, locals, local_count);
            emit_scale_reg_const(cc, sb, "r1", step);
            if (node->binary.op == SUB && lhs_ptr) {
                sb_append(sb, "  sub %s, r1\n", target_reg);
            } else {
                sb_append(sb, "  add %s, r1\n", target_reg);
            }
            return;
        }
    }

    // --- Generate code for the left-hand operand ---
    // If the operand is *ptr (dereference), we need to:
    //   1. Evaluate the inner expression to get the address
    //   2. Load the value from that address
    if (node->binary.left->type == AST_UNARY &&
        node->binary.left->unary.op == ASTARISK) {
        gen_expr(cc, node->binary.left->unary.operand, sb, "r2", params, param_count, locals, local_count);
        int isb = lvalue_is_byte(cc, node->binary.left);
        emit_load_from_addr(sb, "r2", "r2", isb);
    } else {
        gen_expr(cc, node->binary.left, sb, "r2", params, param_count, locals, local_count);
    }

    // Preserve left operand across right evaluation (calls clobber r2)
    sb_append(sb, "  push r2\n");

    // --- Generate code for the right-hand operand ---
    if (node->binary.right->type == AST_UNARY &&
        node->binary.right->unary.op == ASTARISK) {
        gen_expr(cc, node->binary.right->unary.operand, sb, "r1", params, param_count, locals, local_count);
        int isb = lvalue_is_byte(cc, node->binary.right);
        emit_load_from_addr(sb, "r1", "r1", isb);
    } else {
        gen_expr(cc, node->binary.right, sb, "r1", params, param_count, locals, local_count);
    }

    sb_append(sb, "  pop r2\n");


    switch (node->binary.op)
    {
    case ADD:
        sb_append(sb, "\n; addition\n  add  r1, r2\n");
        break;
    case SUB:
        sb_append(sb, "\n; subtraction\n  sub  r2, r1\n");
        sb_append(sb, "  mov r1, r2\n");
        break;
    case ASTARISK:
        sb_append(sb, "\n; multiply r2 * r1\n");
        sb_append(sb, "  movi r4, 0      ; r4 = result\n");
        sb_append(sb, "  mov r5, r1     ; r5 = count\n");
        int lbl_mul = next_label(cc);
        sb_append(sb, "b_mul_loop_%d:\n", lbl_mul);
        sb_append(sb, "  cmp r5, 0\n");
        sb_append(sb, "  jz b_mul_end_%d\n", lbl_mul);
        sb_append(sb, "  add r4, r2\n");
        sb_append(sb, "  addis r5, -1\n");
        sb_append(sb, "  jmp b_mul_loop_%d\n", lbl_mul);
        sb_append(sb, "b_mul_end_%d:\n", lbl_mul);
        sb_append(sb, "  mov r1, r4\n");
        break;
    case DIV:
        sb_append(sb, "\n; divide r2 / r1\n");
        sb_append(sb, "  movi r4, 0      ; r4 = result (quotient)\n");
        int lbl_div = next_label(cc);
        sb_append(sb, "b_div_loop_%d:\n", lbl_div);
        sb_append(sb, "  cmp r2, r1\n");
        sb_append(sb, "  jl b_div_end_%d\n", lbl_div);
        sb_append(sb, "  sub r2, r1\n");
        sb_append(sb, "  addis r4, 1\n");
        sb_append(sb, "  jmp b_div_loop_%d\n", lbl_div);
        sb_append(sb, "b_div_end_%d:\n", lbl_div);
        sb_append(sb, "  mov r1, r4\n");
        break;
    case MOD:
        sb_append(sb, "\n; modulo r2 %% r1\n");
        sb_append(sb, "  mov r6, r2     ; r6 = dividend backup (r2)\n");
        sb_append(sb, "  movi r4, 0      ; r4 = result (quotient)\n");
        int lbl_mod = next_label(cc);
        sb_append(sb, "b_mod_loop_%d:\n", lbl_mod);
        sb_append(sb, "  cmp r2, r1\n");
        sb_append(sb, "  jl b_mod_end_%d\n", lbl_mod);
        sb_append(sb, "  sub r2, r1\n");
        sb_append(sb, "  addis r4, 1\n");
        sb_append(sb, "  jmp b_mod_loop_%d\n", lbl_mod);
        sb_append(sb, "b_mod_end_%d:\n", lbl_mod);
        sb_append(sb, "  ; r2 now contains remainder\n");
        sb_append(sb, "  mov r1, r2\n");
        break;
        
    case AMPERSAND:
        sb_append(sb, "\n; bitwise AND\n  and r1, r2\n");
        break;
    case BITOR:
        sb_append(sb, "\n; bitwise OR\n  or r1, r2\n");
        break;
    case BITXOR:
        sb_append(sb, "\n; bitwise XOR\n  xor r1, r2\n");
        break;
    case LSH: {
        sb_append(sb, "\n; bitwise left shift\n");
        sb_append(sb, "  mov r4, r2\n"); // r4 = value (LHS)
        sb_append(sb, "  mov r5, r1\n"); // r5 = count (RHS)
        int lbl = next_label(cc);
        sb_append(sb, "b_lsh_loop_%d:\n", lbl);
        sb_append(sb, "  cmp r5, 0\n");
        sb_append(sb, "  jz b_lsh_end_%d\n", lbl);
        sb_append(sb, "  shl r4\n");
        sb_append(sb, "  addis r5, -1\n");
        sb_append(sb, "  jmp b_lsh_loop_%d\n", lbl);
        sb_append(sb, "b_lsh_end_%d:\n", lbl);
        sb_append(sb, "  mov r1, r4\n");
        break;
    }
    case RSH: {
        sb_append(sb, "\n; bitwise right shift\n");
        sb_append(sb, "  mov r4, r2\n"); // r4 = value (LHS)
        sb_append(sb, "  mov r5, r1\n"); // r5 = count (RHS)
        int lbl = next_label(cc);
        sb_append(sb, "b_rsh_loop_%d:\n", lbl);
        sb_append(sb, "  cmp r5, 0\n");
        sb_append(sb, "  jz b_rsh_end_%d\n", lbl);
        sb_append(sb, "  shr r4\n");
        sb_append(sb, "  addis r5, -1\n");
        sb_append(sb, "  jmp b_rsh_loop_%d\n", lbl);
        sb_append(sb, "b_rsh_end_%d:\n", lbl);
        sb_append(sb, "  mov r1, r4\n");
        break;
    }

    case EQ:
    case NEQ:
    case LT:
    case GT:
    case LTE:
    case GTE: {
        int label = next_label(cc);
        char label_true[32], label_end[32];
        snprintf(label_true, sizeof(label_true), "b_cmp_true_%d", label);
        snprintf(label_end, sizeof(label_end), "b_cmp_end_%d", label);
        sb_append(sb, "  cmp r2, r1\n");
        switch (node->binary.op) {
        case EQ:
            sb_append(sb, "  jz %s\n", label_true);
            break;
        case NEQ:
            sb_append(sb, "  jnz %s\n", label_true);
            break;
        case LT:
            sb_append(sb, "  jl %s\n", label_true);
            break;
        case GT:
            sb_append(sb, "  jg %s\n", label_true);
            break;
        case LTE:
            sb_append(sb, "  jl %s\n", label_true);
            sb_append(sb, "  jz %s\n", label_true);
            break;
        case GTE:
            sb_append(sb, "  jg %s\n", label_true);
            sb_append(sb, "  jz %s\n", label_true);
            break;
        default:
            break;
        }
        sb_append(sb, "  movi r1, 0\n");
        sb_append(sb, "  jmp %s\n", label_end);
        sb_append(sb, "%s:\n", label_true);
        sb_append(sb, "  movi r1, 1\n");
        sb_append(sb, "%s:\n", label_end);
        break;
    }

    default:
        fprintf(stderr, "Codegen error: unknown binary op\n");
        exit(1);
    }

    if (strcmp(target_reg, "r1") != 0)
        sb_append(sb, "  mov %s, r1\n", target_reg);
}

static void gen_call(CompilerContext *cc, ASTNode *node, StringBuilder *sb, const char *target_reg,
              char **params, int param_count, char **locals, int local_count)
{
    int argc = node->call.arg_count;
    int stack_args = argc > 3 ? (argc - 3) : 0;

    // Allocate space for stack-passed arguments (4th and beyond)
    if (stack_args > 0)
    {
        sb_append(sb, "  ; push stack arguments\n");
        sb_append(sb, "  addis sp, -%d\n", stack_args * SLOT_SIZE);
        for (int i = 3; i < argc; i++)
        {
            gen_expr(cc, node->call.args[i], sb, "r1", params, param_count, locals, local_count);
            sb_append(sb, "  mov r2, sp\n");
            sb_append(sb, "  addis r2, %d\n", (i - 3) * SLOT_SIZE);
            sb_append(sb, "  store r2, r1\n"); // Store the argument value at [sp + offset]
        }
    }

    // Pass the first 3 arguments via registers r5, r6, r7 (left to right)
    for (int i = 0; i < argc && i < 3; i++)
    {
        gen_expr(cc, node->call.args[i], sb, arg_regs[i], params, param_count, locals, local_count);
    }

    sb_append(sb, "  call f_%s\n", node->call.name);

    // After call, restore stack pointer
    if (stack_args > 0)
    {
        sb_append(sb, "  ; restore sp after call\n");
        sb_append(sb, "  addis sp, %d\n", stack_args * SLOT_SIZE);
    }

    // Move return value to target register if needed
    if (strcmp(target_reg, "r1") != 0)
        sb_append(sb, "  mov %s, r1\n", target_reg);
}

static void gen_if(CompilerContext *cc, ASTNode *node, StringBuilder *sb,
    char **params, int param_count,
    char **locals, int local_count,
    const char *break_label,
    const char *continue_label)
{
    int cur_label = next_label(cc);

    char then_label[32], else_label[32], end_label[32];
    snprintf(then_label, sizeof(then_label), "b_L_then_%d", cur_label);
    snprintf(end_label, sizeof(end_label), "b_L_end_%d", cur_label);

    if (node->if_stmt.else_stmt)
        snprintf(else_label, sizeof(else_label), "b_L_else_%d", cur_label);
    else
        strcpy(else_label, end_label);

    ASTNode *cond = node->if_stmt.cond;

    if (cond->type == AST_BINARY)
    {
        if (is_comparison_op(cond->binary.op)) {
            emit_cond_jump(cc, cond->binary.left, cond->binary.right, cond->binary.op, sb,
                           params, param_count, locals, local_count, then_label, else_label);
        } else {
            gen_expr(cc, cond, sb, "r1", params, param_count, locals, local_count);
            sb_append(sb, "  cmp r1, 0\n");
            sb_append(sb, "  jnz %s\n", then_label);
            sb_append(sb, "  jmp %s\n", else_label);
        }
    }
    else
    {
        // General case: treat cond as value
        gen_expr(cc, cond, sb, "r1", params, param_count, locals, local_count);
        sb_append(sb, "  cmp r1, 0\n");
        sb_append(sb, "  jnz %s\n", then_label);
        sb_append(sb, "  jmp %s\n", else_label);
    }

    sb_append(sb, "%s:\n", then_label);
    gen_stmt_internal(cc, node->if_stmt.then_stmt, sb, params, param_count, locals, local_count,
        break_label, continue_label);
    sb_append(sb, "  jmp %s\n", end_label);

    if (node->if_stmt.else_stmt)
    {
        sb_append(sb, "%s:\n", else_label);
        gen_stmt_internal(cc, node->if_stmt.else_stmt, sb, params, param_count, locals, local_count,
            break_label, continue_label);
    }
    sb_append(sb, "%s:\n", end_label);
}
static void gen_for(CompilerContext *cc, ASTNode *node, StringBuilder *sb,
    char **params, int param_count,
    char **locals, int local_count,
    const char *break_label,
    const char *continue_label)

{
    (void)break_label; (void)continue_label;
    int cur_label = next_label(cc);
    char for_cond[32], for_body[32], for_inc[32], for_end[32];
    snprintf(for_cond, sizeof(for_cond), "b_L_for_cond_%d", cur_label);
    snprintf(for_body, sizeof(for_body), "b_L_for_body_%d", cur_label);
    snprintf(for_inc, sizeof(for_inc), "b_L_for_inc_%d", cur_label);
    snprintf(for_end, sizeof(for_end), "b_L_for_end_%d", cur_label);

    if (node->for_stmt.init)
        gen_stmt(cc, node->for_stmt.init, sb, params, param_count, locals, local_count);

    sb_append(sb, "%s:\n", for_cond);

    if (node->for_stmt.cond && node->for_stmt.cond->type == AST_BINARY)
    {
        if (is_comparison_op(node->for_stmt.cond->binary.op)) {
            emit_cond_jump(cc, node->for_stmt.cond->binary.left, node->for_stmt.cond->binary.right,
                           node->for_stmt.cond->binary.op, sb,
                           params, param_count, locals, local_count,
                           for_body, for_end);
        } else {
            gen_expr(cc, node->for_stmt.cond, sb, "r1", params, param_count, locals, local_count);
            sb_append(sb, "  cmp r1, 0\n");
            sb_append(sb, "  jnz %s\n", for_body);
            sb_append(sb, "  jmp %s\n", for_end);
        }
    }
    else if (node->for_stmt.cond)
    {
        gen_expr(cc, node->for_stmt.cond, sb, "r1", params, param_count, locals, local_count);
        sb_append(sb, "  cmp r1, 0\n");
        sb_append(sb, "  jnz %s\n", for_body);
        sb_append(sb, "  jmp %s\n", for_end);
    }
    else
    {
        sb_append(sb, "  jmp %s\n", for_body);
    }

    sb_append(sb, "%s:\n", for_body);
    gen_stmt_internal(cc, node->for_stmt.body, sb, params, param_count, locals, local_count,
        for_end, for_inc);

    sb_append(sb, "%s:\n", for_inc);
    if (node->for_stmt.inc)
        gen_stmt(cc, node->for_stmt.inc, sb, params, param_count, locals, local_count);

    sb_append(sb, "  jmp %s\n", for_cond);
    sb_append(sb, "%s:\n", for_end);
}

static void gen_while(CompilerContext *cc, ASTNode *node, StringBuilder *sb,
    char **params, int param_count,
    char **locals, int local_count,
    const char *break_label,
    const char *continue_label)
{
    (void)break_label; (void)continue_label;
    int cur = next_label(cc);

    char cond_label[32], body_label[32], end_label[32];
    snprintf(cond_label, sizeof(cond_label), "b_L_while_cond_%d", cur);
    snprintf(body_label, sizeof(body_label), "b_L_while_body_%d", cur);
    snprintf(end_label, sizeof(end_label), "b_L_while_end_%d", cur);

    // condition check
    sb_append(sb, "%s:\n", cond_label);

    if (node->while_stmt.cond->type == AST_BINARY) {
        if (is_comparison_op(node->while_stmt.cond->binary.op)) {
            emit_cond_jump(cc,
                node->while_stmt.cond->binary.left,
                node->while_stmt.cond->binary.right,
                node->while_stmt.cond->binary.op,
                sb, params, param_count, locals, local_count,
                body_label, end_label
            );
        } else {
            gen_expr(cc, node->while_stmt.cond, sb, "r1", params, param_count, locals, local_count);
            sb_append(sb, "  cmp r1, 0\n");
            sb_append(sb, "  jnz %s\n", body_label);
            sb_append(sb, "  jmp %s\n", end_label);
        }
    } else {
        gen_expr(cc, node->while_stmt.cond, sb, "r1", params, param_count, locals, local_count);
        sb_append(sb, "  cmp r1, 0\n");
        sb_append(sb, "  jnz %s\n", body_label);
        sb_append(sb, "  jmp %s\n", end_label);
    }

    // loop body
    sb_append(sb, "%s:\n", body_label);
    gen_stmt_internal(
        cc, node->while_stmt.body, sb,
        params, param_count, locals, local_count,
        end_label, cond_label
    );

    // loop back
    sb_append(sb, "  jmp %s\n", cond_label);

    // exit label
    sb_append(sb, "%s:\n", end_label);
}

static void gen_do_while(CompilerContext *cc, ASTNode *node, StringBuilder *sb,
    char **params, int param_count,
    char **locals, int local_count,
    const char *break_label,
    const char *continue_label)
{
    (void)break_label; (void)continue_label;
    int cur = next_label(cc);

    char cond_label[32], body_label[32], end_label[32];
    snprintf(cond_label, sizeof(cond_label), "b_L_dowhile_cond_%d", cur);
    snprintf(body_label, sizeof(body_label), "b_L_dowhile_body_%d", cur);
    snprintf(end_label, sizeof(end_label), "b_L_dowhile_end_%d", cur);

    // loop body start
    sb_append(sb, "%s:\n", body_label);

    // generate body
    gen_stmt_internal(
        cc, node->do_while_stmt.body, sb,
        params, param_count, locals, local_count,
        end_label, cond_label
    );

    // condition check (continue label)
    sb_append(sb, "%s:\n", cond_label);

    if (node->do_while_stmt.cond->type == AST_BINARY) {
        if (is_comparison_op(node->do_while_stmt.cond->binary.op)) {
            emit_cond_jump(cc,
                node->do_while_stmt.cond->binary.left,
                node->do_while_stmt.cond->binary.right,
                node->do_while_stmt.cond->binary.op,
                sb, params, param_count, locals, local_count,
                body_label, end_label
            );
        } else {
            gen_expr(cc, node->do_while_stmt.cond, sb, "r1", params, param_count, locals, local_count);
            sb_append(sb, "  cmp r1, 0\n");
            sb_append(sb, "  jnz %s\n", body_label);
            sb_append(sb, "  jmp %s\n", end_label);
        }
    } else {
        gen_expr(cc, node->do_while_stmt.cond, sb, "r1", params, param_count, locals, local_count);
        sb_append(sb, "  cmp r1, 0\n");
        sb_append(sb, "  jnz %s\n", body_label);
        sb_append(sb, "  jmp %s\n", end_label);
    }
    
    // exit label
    sb_append(sb, "%s:\n", end_label);
}

static void gen_assign(CompilerContext *cc, ASTNode *node, StringBuilder *sb,
              char **params, int param_count,
              char **locals, int local_count,
              const char *target_reg) {
    if (!node || node->type != AST_ASSIGN) {
        fprintf(stderr, "Codegen error: gen_assign called on non-assignment node\n");
        exit(1);
    }
    if (lvalue_is_const(cc, node->assign.left)) {
        fprintf(stderr, "Codegen error: assignment to const lvalue is not allowed\n");
        exit(1);
    }
    gen_expr(cc, node->assign.right, sb, "r1", params, param_count, locals, local_count);
    gen_lvalue_addr(cc, node->assign.left, sb, "r3", params, param_count, locals, local_count);
    int is_byte = lvalue_is_byte(cc, node->assign.left);
    emit_store_to_addr(sb, "r3", "r1", is_byte);
    if (target_reg && strcmp(target_reg, "r1") != 0) {
        sb_append(sb, "  mov %s, r1\n", target_reg);
    }
}

static void gen_expr(CompilerContext *cc, ASTNode *node, StringBuilder *sb, const char *target_reg,
              char **params, int param_count,
              char **locals, int local_count) {
                _gen_expr(cc, node, sb, target_reg, params, param_count, locals, local_count, 0);
              }

static void _gen_expr(CompilerContext *cc, ASTNode *node, StringBuilder *sb, const char *target_reg,
              char **params, int param_count, char **locals, int local_count,
              int want_address)
{
    switch (node->type)
    {
    case AST_SIZEOF: {
        int sz = SLOT_SIZE;
        int determined = 0;
        if (node->sizeof_expr.expr && node->sizeof_expr.expr->type == AST_IDENTIFIER) {
            const LocalInfo *li = find_local_info(cc, node->sizeof_expr.expr->identifier.name);
            if (li) {
                TypeInfo ti = {0};
                ti.base_type = li->base_type;
                ti.pointer_level = li->pointer_level;
                ti.is_array = li->is_array;
                ti.dims_count = li->dims_count;
                for (int i = 0; i < li->dims_count && i < 8; i++) ti.dims[i] = li->dims[i];
                sz = typeinfo_total_size_bytes(cc, &ti);
                determined = 1;
            }
        }
            if (!determined) {
                TypeInfo ti = {0};
                if (infer_expr_type(cc, node->sizeof_expr.expr, &ti)) {
                    sz = typeinfo_total_size_bytes(cc, &ti);
                }
            }
        sb_append(sb, "  movi %s, %d\n", target_reg, sz);
        break; }
    case AST_STRING_LITERAL: {
        const char *label = intern_string_literal(cc, node->string_literal.value ? node->string_literal.value : "");
        sb_append(sb, "  movi  %s, %s\n", target_reg, label);
        break; }
    case AST_CHAR_LITERAL: {
        unsigned char v = 0;
        if (node->char_literal.value)
            v = (unsigned char)node->char_literal.value[0];
        sb_append(sb, "  \n; load char %u into %s\n", (unsigned)v, target_reg);
        sb_append(sb, "  movi  %s, %u\n", target_reg, (unsigned)v);
        break; }
    case AST_ASSIGN:
        gen_assign(cc, node, sb, params, param_count, locals, local_count, target_reg);
        break;
    case AST_TERNARY: {
        int lbl = next_label(cc);
        char label_else[32], label_end[32];
        snprintf(label_else, sizeof(label_else), "b_ternary_else_%d", lbl);
        snprintf(label_end, sizeof(label_end), "b_ternary_end_%d", lbl);
        gen_expr(cc, node->ternary.cond, sb, "r1", params, param_count, locals, local_count);
        sb_append(sb, "  cmp r1, 0\n");
        sb_append(sb, "  jz %s\n", label_else);
        gen_expr(cc, node->ternary.then_expr, sb, target_reg, params, param_count, locals, local_count);
        sb_append(sb, "  jmp %s\n", label_end);
        sb_append(sb, "%s:\n", label_else);
        gen_expr(cc, node->ternary.else_expr, sb, target_reg, params, param_count, locals, local_count);
        sb_append(sb, "%s:\n", label_end);
        break;
    }
    case AST_NUMBER:
        sb_append(sb, "  \n; load constant %s into %s\n", node->number.value, target_reg);
        sb_append(sb, "  movi  %s, %s\n", target_reg, node->number.value);
        break;
    case AST_UNARY:
        switch (node->unary.op)
        {
        case SUB: {
            // Unary minus: 0 - operand
            _gen_expr(cc, node->unary.operand, sb, target_reg, params, param_count, locals, local_count, 0);
            const char *zero_reg = (strcmp(target_reg, "r1") == 0) ? "r2" : "r1";
            sb_append(sb, "  mov %s, 0\n", zero_reg);
            sb_append(sb, "  sub %s, %s\n", zero_reg, target_reg);
            sb_append(sb, "  mov %s, %s\n", target_reg, zero_reg);
            break;
        }
        case BITNOT:
            _gen_expr(cc, node->unary.operand, sb, target_reg, params, param_count, locals, local_count, 0);
            sb_append(sb, "  movi r3, -1\n");
            sb_append(sb, "  xor %s, r3\n", target_reg);
            break;
        case NOT: {
            _gen_expr(cc, node->unary.operand, sb, target_reg, params, param_count, locals, local_count, 0);
            int lbl_true = next_label(cc);
            int lbl_end = next_label(cc);
            sb_append(sb, "  cmp %s, 0\n", target_reg);
            sb_append(sb, "  jz b_not_true_%d\n", lbl_true);
            sb_append(sb, "  movi %s, 0\n", target_reg);
            sb_append(sb, "  jmp b_not_end_%d\n", lbl_end);
            sb_append(sb, "b_not_true_%d:\n", lbl_true);
            sb_append(sb, "  movi %s, 1\n", target_reg);
            sb_append(sb, "b_not_end_%d:\n", lbl_end);
            break; }
        case ASTARISK: // *
            _gen_expr(cc, node->unary.operand, sb, "r3",
                      params, param_count, locals, local_count,
                      0);
            TypeInfo result_type = (TypeInfo){0};
            int have_type = infer_expr_type(cc, node, &result_type);
            int is_array_result = have_type && result_type.dims_count > 0;
            if (!want_address) {
                if (is_array_result) {
                    sb_append(sb, "  ; dereference array -> decay to pointer\n");
                    sb_append(sb, "  mov %s, r3\n", target_reg);
                } else {
                    sb_append(sb, "  ; dereference *expr\n");
                    int isb = have_type ? typeinfo_is_byte(&result_type) : 0;
                    emit_load_from_addr(sb, target_reg, "r3", isb);
                }
            } else {
                sb_append(sb, "  mov %s, r3\n", target_reg);
            }
            break;
        case AMPERSAND:
            gen_lvalue_addr(cc, node->unary.operand, sb, target_reg, params, param_count, locals, local_count);
            break;

        default:
            emit_unary_inc_dec(cc, node, sb, target_reg, params, param_count, locals, local_count);
        }
        break;

    case AST_IDENTIFIER:
        emit_load_var(cc, sb, node->identifier.name, target_reg, params, param_count, locals, local_count);
        break;
    case AST_BINARY:
        gen_expr_binop(cc, node, sb, target_reg, params, param_count, locals, local_count);
        break;
    case AST_CALL:
        gen_call(cc, node, sb, target_reg, params, param_count, locals, local_count);
        break;
    case AST_MEMBER_ACCESS: {
        // load *(addr(lhs) + offset(member))
        gen_lvalue_addr(cc, node, sb, "r3", params, param_count, locals, local_count);
        {
            int isb = lvalue_is_byte(cc, node);
            emit_load_from_addr(sb, target_reg, "r3", isb);
        }
        break; }
    case AST_ARROW_ACCESS: {
        gen_lvalue_addr(cc, node, sb, "r3", params, param_count, locals, local_count);
        {
            int isb = lvalue_is_byte(cc, node);
            emit_load_from_addr(sb, target_reg, "r3", isb);
        }
        break; }
    case AST_IMPORT:
        break;
    default:
        fprintf(stderr, "Codegen error: unknown expr node %s\n", astType2str(node->type));
        exit(1);
    }
}

static void gen_stmt(CompilerContext *cc, ASTNode *node, StringBuilder *sb,
              char **params, int param_count,
              char **locals, int local_count)
{
    gen_stmt_internal(cc, node, sb, params, param_count, locals, local_count,
                      NULL, NULL);
}

// Statement codegen
static void gen_stmt_internal(CompilerContext *cc, ASTNode *node, StringBuilder *sb,
                       char **params, int param_count,
                       char **locals, int local_count,
                       const char *break_label,
                       const char *continue_label)
{
    switch (node->type)
    {
    case AST_VAR_DECL:
        if (node->var_decl.init)
        {
            ASTNode *vtype = node->var_decl.var_type;
            if (vtype && vtype->type == AST_TYPE_ARRAY &&
                (node->var_decl.init->type == AST_INIT_LIST || node->var_decl.init->type == AST_STRING_LITERAL)) {
                // Array initializer
                sb_append(sb, "  ; init array '%s'\n", node->var_decl.name);
                // address of var into r3
                emit_addr_of_var(cc, sb, node->var_decl.name, "r3", params, param_count, locals, local_count);

                int elem_size = array_element_size_bytes(vtype);
                int is_byte_elem = (elem_size == 1);
                int total_elems = array_total_elements(vtype);

                if (node->var_decl.init->type == AST_STRING_LITERAL && vtype->type_array.element_type && vtype->type_array.element_type->type != AST_TYPE_ARRAY) {
                    const char *str = node->var_decl.init->string_literal.value ? node->var_decl.init->string_literal.value : "";
                    int len = (int)strlen(str);
                    int total = total_elems > 0 ? total_elems : (len + 1);
                    for (int i = 0; i < total; i++) {
                        unsigned char val = 0;
                        if (i < len) {
                            val = (unsigned char)str[i];
                        } else if (i == len) {
                            val = 0; // explicit NUL
                        }
                        int offset = elem_size * i;
                        sb_append(sb, "  movi r1, %u\n", (unsigned)val);
                        if (offset == 0) {
                            emit_store_to_addr(sb, "r3", "r1", 1);
                        } else {
                            sb_append(sb, "  mov r2, r3\n");
                            sb_append(sb, "  addis r2, %d\n", offset);
                            emit_store_to_addr(sb, "r2", "r1", 1);
                        }
                    }
                } else if (node->var_decl.init->type == AST_INIT_LIST) {
                    int count = node->var_decl.init->init_list.count;
                    int total = total_elems > 0 ? total_elems : count;
                    int limit = count < total ? count : total;
                    for (int i = 0; i < limit; i++) {
                        gen_expr(cc, node->var_decl.init->init_list.elements[i], sb, "r1", params, param_count, locals, local_count);
                        int offset = elem_size * i;
                        if (offset == 0) {
                            emit_store_to_addr(sb, "r3", "r1", is_byte_elem);
                        } else {
                            sb_append(sb, "  mov r2, r3\n");
                            sb_append(sb, "  addis r2, %d\n", offset);
                            emit_store_to_addr(sb, "r2", "r1", is_byte_elem);
                        }
                    }
                    // zero-fill remaining slots if array is larger
                    if (total > limit) {
                        sb_append(sb, "  movi r1, 0\n");
                        for (int i = limit; i < total; i++) {
                            int offset = elem_size * i;
                            if (offset == 0) {
                                emit_store_to_addr(sb, "r3", "r1", is_byte_elem);
                            } else {
                                sb_append(sb, "  mov r2, r3\n");
                                sb_append(sb, "  addis r2, %d\n", offset);
                                emit_store_to_addr(sb, "r2", "r1", is_byte_elem);
                            }
                        }
                    }
                }
            } else {
                gen_expr(cc, node->var_decl.init, sb, "r1", params, param_count, locals, local_count);
                emit_store_var(cc, sb, node->var_decl.name, "r1", params, param_count, locals, local_count);
            }
        }
        break;
    case AST_UNARY:
        emit_unary_inc_dec(cc, node, sb, "r1", params, param_count, locals, local_count);
        break;
    case AST_ASSIGN:
        gen_assign(cc, node, sb, params, param_count, locals, local_count, "r1");
        break;
    case AST_BREAK:
        if (break_label)
            sb_append(sb, "  jmp %s\n", break_label);
        else
            sb_append(sb, "  ; error: break used outside loop\n");
        break;
    case AST_CONTINUE:
        if (continue_label)
            sb_append(sb, "  jmp %s\n", continue_label);
        else
            sb_append(sb, "  ; error: continue used outside loop\n");
        break;
    case AST_EXPR_STMT:
        gen_expr(cc, node->expr_stmt.expr, sb, "r1", params, param_count, locals, local_count);
        break;
    case AST_IF:
        gen_if(cc, node, sb, params, param_count, locals, local_count, break_label, continue_label);
        break;
    case AST_FOR:
        gen_for(cc, node, sb, params, param_count, locals, local_count,
                break_label, continue_label);
        break;
    case AST_WHILE:
        gen_while(cc, node, sb, params, param_count, locals, local_count,
                  break_label, continue_label);
        break;
    case AST_DO_WHILE:
        gen_do_while(cc, node, sb, params, param_count, locals, local_count,
                  break_label, continue_label);
        break;
    case AST_RETURN:
        gen_expr(cc, node->ret.expr, sb, "r1", params, param_count, locals, local_count);
        // r1 = return value. No 'ret' for main.
        sb_append(sb, "  \n; return\n");
        if (cc->return_label)
            sb_append(sb, "  jmp %s\n", cc->return_label);
        break;
    case AST_BLOCK:
        for (int i = 0; i < node->block.count; i++)
        {
            gen_stmt_internal(cc, node->block.stmts[i], sb, params, param_count, locals, local_count,
                                 break_label, continue_label);
        }
        break;
    case AST_IMPORT:
        // Imports are resolved at parse time; no code to generate
        break;
    default:
        fprintf(stderr, "Codegen error: unknown stmt node %s\n", astType2str(node->type));
        exit(1);
    }
}

void gen_func(CompilerContext *cc, ASTNode *node, StringBuilder *sb)
{

    if (node->type != AST_FUNDEF) return;

    char *fname = strcmp(node->fundef.name, "main") == 0 ? "__START__" : node->fundef.name;
    int param_count = node->fundef.param_count;
    char *params[16] = {0};
    for (int i = 0; i < param_count; i++)
    {
        params[i] = node->fundef.params[i]->param.name;
    }

    char *locals[32] = {0};
    int local_count = collect_locals(cc, node->fundef.body, locals);

    // Collect param + local type info for struct member access
    int locals_only_count = collect_local_type_info(cc, node->fundef.body, NULL);
    cg_locals_count = param_count + locals_only_count;
    if (cg_locals_count > 0) {
        cg_locals_info = (LocalInfo*)malloc(sizeof(LocalInfo) * cg_locals_count);
        int idx = 0;
        // Parameters first
        for (int i = 0; i < param_count; i++, idx++) {
            ASTNode *p = node->fundef.params[i];
            cg_locals_info[idx].name = p->param.name;
            set_localinfo_from_type(cc, &cg_locals_info[idx], p->param.type);
        }
        // Then locals from body
        if (locals_only_count > 0) {
            collect_local_type_info(cc, node->fundef.body, cg_locals_info + idx);
        }
    } else {
        cg_locals_info = NULL;
    }

    sb_append(sb, "\n");
    sb_append(sb, "%s%s:\n", strcmp(fname, "__START__") == 0 ? "" : "f_", fname);
    sb_append(sb, "; prologue\n");
    sb_append(sb, "  push lr\n");
    sb_append(sb, "  push bp\n");
    sb_append(sb, "  mov bp, sp\n  addis sp, -%d\n",
              (local_count + param_count) * SLOT_SIZE);

    // Store first 3 parameters from registers to stack frame
    for (int i = 0; i < param_count && i < 3; i++)
    {
        sb_append(sb, "  ; store parameter '%s' from register %s\n", params[i], arg_regs[i]);
        sb_append(sb, "  mov   r3, bp\n");
        sb_append(sb, "  addis r3, %d\n", param_offset(i));
        sb_append(sb, "  store r3, %s\n", arg_regs[i]);
    }

    char ret_label[32];
    snprintf(ret_label, sizeof(ret_label), "b_L_ret_%d", next_label(cc));
    cc->return_label = ret_label;

    // Function body
    gen_stmt(cc, node->fundef.body, sb, params, param_count, locals, local_count);

    sb_append(sb, "%s:\n", ret_label);
    sb_append(sb, "  addis sp, %d\n", (local_count + param_count) * SLOT_SIZE);
    sb_append(sb, "; epilogue\n  pop  bp\n  pop  lr\n");

    // Epilogue (not for main)
    if (strcmp(fname, "__START__") != 0)
    {
        sb_append(sb, "  mov  pc, lr\n");
    }
    if (strcmp(fname, "__START__") == 0)
        sb_append(sb, "  halt");

    cc->return_label = NULL;

    // cleanup per-function locals info
    if (cg_locals_info) { free(cg_locals_info); cg_locals_info = NULL; }
    cg_locals_count = 0;
}

char *codegen(ASTNode *root)
{
    CompilerContext ctx = {0};
    CompilerContext *cc = &ctx;
    StringBuilder sb;
    sb_init(&sb);

    // Build struct table from toplevel AST (typedef struct and struct)
    // Assume each member consumes SLOT_SIZE and lay out sequentially
    cg_struct_count = 0;
    cg_structs = NULL;
    cg_typedef_count = 0;
    cg_typedefs = NULL;
    if (root && root->type == AST_BLOCK) {
        // Pass 1: Collect Typedefs (non-struct)
        for (int i = 0; i < root->block.count; i++) {
            ASTNode *n = root->block.stmts[i];
            if (n->type == AST_TYPEDEF) {
                LocalInfo tmp = {0};
                set_localinfo_from_type(cc, &tmp, n->typedef_stmt.src_type);
                
                cg_typedefs = (TypedefInfo*)realloc(cg_typedefs, sizeof(TypedefInfo) * (cg_typedef_count + 1));
                cg_typedefs[cg_typedef_count].alias = n->typedef_stmt.alias;
                cg_typedefs[cg_typedef_count].info.base_type = tmp.base_type;
                cg_typedefs[cg_typedef_count].info.pointer_level = tmp.pointer_level;
                cg_typedefs[cg_typedef_count].info.type_modifiers = tmp.type_modifiers;
                cg_typedefs[cg_typedef_count].info.is_array = tmp.is_array;
                cg_typedefs[cg_typedef_count].info.dims_count = tmp.dims_count;
                for(int k=0; k<8; k++) cg_typedefs[cg_typedef_count].info.dims[k] = tmp.dims[k];
                cg_typedef_count++;
            }
        }

        // Pass 2: Structs
        for (int i = 0; i < root->block.count; i++) {
            ASTNode *n = root->block.stmts[i];
            if (n->type == AST_TYPEDEF_STRUCT) {
                int count = n->typedef_struct.member_count;
                MemberInfo *members = NULL;
                int struct_bytes = 0;
                if (count > 0) {
                    members = (MemberInfo*)malloc(sizeof(MemberInfo) * count);
                    int offset = 0;
                    for (int m = 0; m < count; m++) {
                        ASTNode *mem = n->typedef_struct.members[m];
                        const char *mname = "";
                        LocalInfo tmp = {0};
                        int member_slots = 1;
                        if (mem->type == AST_VAR_DECL) {
                            mname = mem->var_decl.name ? mem->var_decl.name : "";
                            set_localinfo_from_type(cc, &tmp, mem->var_decl.var_type);
                            if (mem->var_decl.var_type) {
                                member_slots = slots_for_type(cc, mem->var_decl.var_type);
                                if (member_slots < 1) member_slots = 1;
                            }
                        } else if (mem->type == AST_STRUCT_MEMBER) {
                            mname = mem->struct_member.name ? mem->struct_member.name : "";
                            tmp.base_type = mem->struct_member.type ? mem->struct_member.type : "";
                            tmp.pointer_level = 0;
                            tmp.is_array = 0;
                            tmp.array_length = 0;
                        } else {
                            tmp.base_type = "";
                            tmp.pointer_level = 0;
                            tmp.is_array = 0;
                            tmp.array_length = 0;
                        }
                        members[m].name = mname;
                        members[m].base_type = tmp.base_type ? tmp.base_type : "";
                        members[m].pointer_level = tmp.pointer_level;
                        members[m].is_array = tmp.is_array;
                        members[m].array_length = tmp.array_length;
                        members[m].size_bytes = (tmp.pointer_level == 0 && !tmp.is_array && base_type_is_char(tmp.base_type)) ? 1 : SLOT_SIZE;
                        members[m].offset = offset;
                        members[m].total_size_bytes = member_slots * SLOT_SIZE;
                        offset += members[m].total_size_bytes;
                    }
                    struct_bytes = offset;
                }
                cg_structs = (StructInfo*)realloc(cg_structs, sizeof(StructInfo) * (cg_struct_count + 1));
                cg_structs[cg_struct_count].type_name = n->typedef_struct.typedef_name;
                cg_structs[cg_struct_count].members = members;
                cg_structs[cg_struct_count].member_count = count;
                cg_structs[cg_struct_count].size_bytes = struct_bytes > 0 ? struct_bytes : SLOT_SIZE;
                cg_struct_count++;
            } else if (n->type == AST_STRUCT && n->struct_stmt.name) {
                int count = n->struct_stmt.member_count;
                MemberInfo *members = NULL;
                int struct_bytes = 0;
                if (count > 0) {
                    members = (MemberInfo*)malloc(sizeof(MemberInfo) * count);
                    int offset = 0;
                    for (int m = 0; m < count; m++) {
                        ASTNode *mem = n->struct_stmt.members[m];
                        const char *mname = "";
                        LocalInfo tmp = {0};
                        int member_slots = 1;
                        if (mem->type == AST_VAR_DECL) {
                            mname = mem->var_decl.name ? mem->var_decl.name : "";
                            set_localinfo_from_type(cc, &tmp, mem->var_decl.var_type);
                            if (mem->var_decl.var_type) {
                                member_slots = slots_for_type(cc, mem->var_decl.var_type);
                                if (member_slots < 1) member_slots = 1;
                            }
                        } else if (mem->type == AST_STRUCT_MEMBER) {
                            mname = mem->struct_member.name ? mem->struct_member.name : "";
                            tmp.base_type = mem->struct_member.type ? mem->struct_member.type : "";
                            tmp.pointer_level = 0;
                            tmp.is_array = 0;
                            tmp.array_length = 0;
                        } else {
                            tmp.base_type = "";
                            tmp.pointer_level = 0;
                            tmp.is_array = 0;
                            tmp.array_length = 0;
                        }
                        members[m].name = mname;
                        members[m].base_type = tmp.base_type ? tmp.base_type : "";
                        members[m].pointer_level = tmp.pointer_level;
                        members[m].is_array = tmp.is_array;
                        members[m].array_length = tmp.array_length;
                        members[m].size_bytes = (tmp.pointer_level == 0 && !tmp.is_array && base_type_is_char(tmp.base_type)) ? 1 : SLOT_SIZE;
                        members[m].offset = offset;
                        members[m].total_size_bytes = member_slots * SLOT_SIZE;
                        offset += members[m].total_size_bytes;
                    }
                    struct_bytes = offset;
                }
                cg_structs = (StructInfo*)realloc(cg_structs, sizeof(StructInfo) * (cg_struct_count + 1));
                cg_structs[cg_struct_count].type_name = n->struct_stmt.name;
                cg_structs[cg_struct_count].members = members;
                cg_structs[cg_struct_count].member_count = count;
                cg_structs[cg_struct_count].size_bytes = struct_bytes > 0 ? struct_bytes : SLOT_SIZE;
                cg_struct_count++;
            }
        }
    }

    // Output __START__ (main) first
    for (int i = 0; i < root->block.count; i++)
    {
        ASTNode *fn = root->block.stmts[i];
        if (fn->type == AST_FUNDEF && strcmp(fn->fundef.name, "main") == 0)
        {
            gen_func(cc, fn, &sb);
            break;
        }
    }
    // Output all other functions
    for (int i = 0; i < root->block.count; i++)
    {
        ASTNode *fn = root->block.stmts[i];
        if (fn->type == AST_FUNDEF && strcmp(fn->fundef.name, "main") != 0)
        {
            gen_func(cc, fn, &sb);
        }
    }
    // Append data (string literals) at the end
    if (cg_data_sb_inited) {
        sb_append(&sb, "\n; data\n");
        sb_append(&sb, "%s", cg_data_sb.buf);
    }

    // optional: free struct table memory (builder returns raw string; sb freed by caller)
    if (cg_structs) {
        for (int i = 0; i < cg_struct_count; i++) {
            free(cg_structs[i].members);
        }
        free(cg_structs);
        cg_structs = NULL;
        cg_struct_count = 0;
    }
    if (cg_typedefs) {
        free(cg_typedefs);
        cg_typedefs = NULL;
        cg_typedef_count = 0;
    }
    // free string pool
    if (cg_strings) {
        for (int i = 0; i < cg_string_count; i++) { free(cg_strings[i].text); free(cg_strings[i].label); }
        free(cg_strings); cg_strings = NULL; cg_string_count = 0;
    }
    if (cg_data_sb_inited) { sb_free(&cg_data_sb); cg_data_sb_inited = 0; }
    return sb_dump(&sb);
}
