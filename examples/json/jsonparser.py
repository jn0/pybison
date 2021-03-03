import logging
import time
import os
import json

from bison import BisonParser

LOGGER = logging.getLogger(__name__)


class Parser(BisonParser):

    def __init__(self, **kwargs):
        self.bisonEngineLibName = self.__class__.__name__ + '_engine'

        tokens = [[x.strip() for x in y.split('=')]
                  for y in self.__doc__.split('\n')
                  if y.strip() != '']

        self.precedences = (
        )

        attribs = dir(self)
        handlers = [getattr(self, x) for x in attribs
                    if x.startswith('on_')]
        start = [x.__name__.replace('on_', '')
                 for x in handlers if getattr(x, '__start__', False)]
        assert len(start) == 1, 'needs exactly one start node, found {}!'.format(len(start))
        self.start = start[0]
        return_location = kwargs.pop('return_location', False)
        if return_location:
            fmt = "{} {{ returntoken_loc({}); }}"
        else:
            fmt = "{} {{ returntoken({}); }}"
        lex_rules = '\n'.join([fmt
                               .format(*x) if x[1][0] != '_' else
                               "{} {{ {} }}".format(x[0], x[1][1:])
                               for x in tokens])

        self.tokens = sorted(list(set([x[1] for x in tokens if not x[1].startswith('_')])))
        self.lexscript = r"""
%{
// Start node is: """ + self.start + r"""
#include <stdio.h>
#include <string.h>
#include "Python.h"
#include "tmp.tab.h"
int yycolumn = 1;
int yywrap() { return(1); }
extern void *py_parser;
extern void (*py_input)(PyObject *parser, char *buf, int *result, int max_size);
#define returntoken(tok) yylval = PyUnicode_FromString(strdup(yytext)); return (tok);
#define returntoken_loc(tok) yylval = PyTuple_Pack(3, PyUnicode_FromString(strdup(yytext)), PyTuple_Pack(2, PyLong_FromLong(yylloc.first_line), PyLong_FromLong(yylloc.first_column)), PyTuple_Pack(2, PyLong_FromLong(yylloc.last_line), PyLong_FromLong(yylloc.last_column))); return (tok);
#define YY_INPUT(buf,result,max_size) { (*py_input)(py_parser, buf, &result, max_size); }
#define YY_USER_ACTION yylloc.first_line = yylloc.last_line; \
    yylloc.first_column = yylloc.last_column; \
    for(int i = 0; yytext[i] != '\0'; i++) { \
        if(yytext[i] == '\n') { \
            yylloc.last_line++; \
            yylloc.last_column = 0; \
        } \
        else { \
            yylloc.last_column++; \
        } \
    }
%}

%%
""" + lex_rules + """

%%
    """
        super(Parser, self).__init__(**kwargs)


def start(method):
    method.__start__ = True
    return method


class JSONParser(Parser):
    r"""
        -?[0-9]+                            = INTEGER
        -?[0-9]+([.][0-9]+)?([eE]-?[0-9]+)? = FLOAT
        false|true|null                     = BOOL
        \"([^\"]|\\[.])*\"                  = STRING
        \{                                  = O_START
        \}                                  = O_END
        \[                                  = A_START
        \]                                  = A_END
        ,                                   = COMMA
        :                                   = COLON
        [ \t\n]                             = _
    """

    @start
    def on_value(self, target, option, names, values):
        """
        value
        : string
        | INTEGER
        | FLOAT
        | BOOL
        | array
        | object
        """
        if option == 1:
            return int(values[0])
        if option == 2:
            return float(values[0])
        if option == 3:
            return {'false': False,
                    'true': True,
                    'null': None}[values[0]]
        return values[0]

    def on_string(self, target, option, names, values):
        """
        string
        : STRING
        """
        return values[0][1:-1]

    def on_object(self, target, option, names, values):
        """
        object
        : O_START O_END
        | O_START members O_END
        """
        return {} if option == 0 else dict(values[1])

    def on_members(self, target, option, names, values):
        """
        members
        : pair
        | pair COMMA members
        """
        if option == 0:
            return [values[0]]
        return [values[0]]+ values[2]

    def on_pair(self, target, option, names, values):
        """
        pair
        : string COLON value
        """
        return (values[0], values[2])

    def on_array(self, target, option, names, values):
        """
        array
        : A_START A_END
        | A_START elements A_END
        """
        if option == 0:
            return ()
        return values[1]

    def on_elements(self, target, option, names, values):
        """
        elements
        : value
        | value COMMA elements
        """
        if option == 0:
            return [values[0]]
        return [values[0]] + values[2]


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(prog="PyBison Parser Template")
    parser.add_argument("-k", "--keepfiles", action="store_true",
                        help="Keep temporary files used in building parse engine lib")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose messages while parser is running")
    parser.add_argument("-d", "--debug", action="store_true",
                        help="Enable garrulous debug messages from parser engine")
    parser.add_argument("filename", type=str, nargs="*", default="example.json",
                        help="path of a file to parse, defaults to stdin")
    args = parser.parse_args()

    start = time.time()
    p = Parser(verbose=args.verbose, keepfiles=args.keepfiles, debug=args.debug)
    duration = time.time() - start
    LOGGER.info('instantiate parser {}s'.format(duration))

    if args.filename is None:
        print("(Reading from standard input - please type stuff)")
        start = time.time()
        tree = p.run(file=None, debug=args.debug)
        duration = time.time() - start
        LOGGER.info('bison-based JSONParser {}'.format(duration))
    else:
        for fp in args.filename:
            start = time.time()
            with open(args.filename) as fh:
                result_json = json.load(fh)
            duration = time.time() - start
            LOGGER.info('json {}'.format(duration))
            start = time.time()
            result_bison = p.run(file=fp, debug=args.debug)
            duration = time.time() - start
            LOGGER.info('bison-based JSONParser {}'.format(duration))
            LOGGER.info('result equal to json: {}'.format(result_json == result_bison))
            LOGGER.info('filesize: {} kB'.format(os.stat(args.filename).st_size / 1024))
