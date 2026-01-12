#include "unity.h"
#include "../inc/lexer.h"
#include "../inc/parser.h"
#include "../inc/codegen.h"
#include "../inc/utils.h"

#include <stdio.h>
#include <stdlib.h>

void setUp(void) {}
void tearDown(void) {}

void test_codegen_from_simpleFunc(void) {
    Token *tokens = lexer_from_file("tests/inputs/simpleFunc.c");
    TEST_ASSERT_NOT_NULL(tokens);

    Token *cur = tokens;
    ASTNode *root = parse_program(&cur);

    print_ast(root, 0);

    char *output = codegen(root);

    saveOutput("tests/outputs/simpleFunc_gen.masm", output);
    free(output);
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_codegen_from_simpleFunc);
    return UNITY_END();
}
