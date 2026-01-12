#ifndef TOKEN_H
#define TOKEN_H

typedef int symbol;

typedef enum {
    ADD,      // +
    SUB,      // -
    //MUL,      // *
    DIV,      // /
    MOD,      // %
    ASSIGN,   // =
    EQ,       // ==
    NEQ,      // !=
    LT,       // <
    GT,       // >
    LTE,      // <=
    GTE,      // >=
    LAND,      // &&
    LOR,       // ||
    NOT,      // !
    AMPERSAND,
    //BITAND,   // &
    BITOR,    // |
    BITXOR,   // ^
    BITNOT,   // ~
    LSH,      // <<
    RSH,      // >>
    POST_INC, // ++ (postfix)
    POST_DEC, // -- (postfix)
    INC,      // ++
    DEC,      // --

    ASTARISK,  // *
    ADDRESS,  // &
    ARROW,   // ->

    BOOL,     // bool
    INT,      // int
    CHAR,     // char
    FLOAT,    // float
    DOUBLE,   // double
    VOID,     // void
    LONG,     // long
    SHORT,    // short
    UNSIGNED, // unsigned
    SIGNED,   // signed
    
    CONST,    // const
    STATIC,   // static
    EXTERN,   // extern
    AUTO,     // auto
    REGISTER, // register

    IF,       // if
    ELSE,     // else
    WHILE,    // while
    DO,       // do
    FOR,      // for
    SWITCH,   // switch
    CASE,     // case
    DEFAULT,  // default
    BREAK,    // break
    CONTINUE, // continue
    RETURN,   // return
    TYPEDEF,  // typedef
    STRUCT,   // struct
    UNION,    // union
    ENUM,     // enum
    SIZEOF,   // sizeof
    IMPORT,   // import
    FROM,     // from

    L_PARENTHESES, // (
    R_PARENTHESES, // )
    SEMICOLON,     // ;
    COMMA,         // ,
    L_BRACE,       // {
    R_BRACE,       // }
    L_BRACKET,     // [
    R_BRACKET,     // ]
    DOT,           // .
    QUESTION,      // ?
    COLON,         // :
    VERTICAL_BAR,  // |
    CARET,         // ^
    HASH,          // #

    NUMBER,        // number
    STRING_LITERAL, // "abc"
    CHAR_LITERAL,   // 'a'
    IDENTIFIER,     // defined by user
    INLINE,         // inline but not implemented
    EOT,            // end of token

} TokenKind;

typedef struct Token Token;

struct Token{
  TokenKind kind;
  char *value;
  int line;
  int col;
  Token *next;
};

typedef struct {
  char *str;
  symbol kind;
} StringTokenKindMap;

Token *lexer(char *input);

char *tokenkind2str(TokenKind kind);

// Reads the given file (expanding #include "..." the same way as readSampleInput)
// and tokenizes the result in one step.
Token *lexer_from_file(const char *file_path);

#endif
