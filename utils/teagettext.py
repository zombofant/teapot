#!/usr/bin/python3
import functools
import itertools
import os
import operator
import textwrap

import xsltea.i18n

import lxml.etree as etree

xmlns = xsltea.i18n.I18NProcessor.xmlns

def files_from_directory(path):
    for dirname, dirs, files in os.walk(path):
        for filename in files:
            if filename.endswith(".xml"):
                yield os.path.join(dirname, filename)

def process_tree(tree, filename, **kwargs):
    nsmap = {"i18n": str(xmlns)}
    for node in tree.xpath("//i18n:_ | //i18n:n", namespaces=nsmap):
        logger.debug("found node: %s", node)
        yield xsltea.i18n.node_to_msgid(node, filename, **kwargs)
    ns_prefix = "{"+str(xmlns)+"}"
    for node in tree.xpath("//*[@i18n:*]", namespaces=nsmap):
        logger.debug("found node with attrs: %s")
        parent = node
        while parent is not None:
            if parent.tag.startswith(ns_prefix):
                logger.debug("skipping i18n node")
                break
            parent = parent.getparent()
        if parent is not None:
            continue

        for value in (value for key, value in node.attrib.items()
                     if key.startswith(ns_prefix)):
            msg = xsltea.i18n.Message()
            msg.filename = filename
            msg.singular = value
            msg.sourceline = node.sourceline
            yield msg


def split_msgstr_lines(lines):
    for line in lines:
        parts = iter(line.split("\n"))
        prev = next(parts)
        for part in parts:
            yield prev + "\\n"
            prev = part
        if prev:
            yield prev

def strip_msgstr_lines(s):
    return "\n".join(map(str.strip, s.split("\n")))

def format_msgstr(s):
    lines = [line+"\n" for line in s.split("\n")]
    if lines:
        lines[-1] = lines[-1][:-1]
    wrapped = []
    for line in lines:
        wrapped.extend(textwrap.wrap(
            strip_msgstr_lines(line.replace('\\', '\\\\').replace('"', '\\"')),
            width=70,
            expand_tabs=False,
            replace_whitespace=False,
            break_on_hyphens=False,
            break_long_words=False,
            drop_whitespace=False))
    return '"'+'"\n"'.join(split_msgstr_lines(wrapped))+'"'


if __name__ == "__main__":
    import argparse
    import logging
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "infiles",
        nargs="*",
        metavar="INPUTFILE",
        help="Files to scan")
    parser.add_argument(
        "-f", "--files-from",
        default=None,
        metavar="FILE",
        help="A file with more file names to source from")
    parser.add_argument(
        "-D", "--directory",
        default=None,
        metavar="DIRECTORY",
        help="Recursively scan the given directory for input XML files")

    parser.add_argument(
        "-o", "--output",
        dest="outfile",
        metavar="FILE",
        help="Name for destination file")

    parser.add_argument(
        "-v",
        dest="verbosity",
        action="count",
        default=0,
        help="Increase verbosity")

    args = parser.parse_args()

    logging.basicConfig(
        level={
            0: logging.ERROR,
            1: logging.WARNING,
            2: logging.INFO
        }.get(args.verbosity, logging.DEBUG),
        format='{0}:%(levelname)-8s %(message)s'.format(
            os.path.basename(sys.argv[0]))
    )

    logger = logging.getLogger()

    if "-" in args.infiles and args.files_from == "-":
        logger.error("Standard input specified multiple times")
        sys.exit(1)

    files = args.infiles

    if args.files_from:
        if args.files_from == "-":
            files_from = sys.stdin
        else:
            files_from = open(args.files_from, "r")
        with files_from as f:
            files.extend(f)

    filesiter = iter(files)
    if args.directory:
        filesiter = itertools.chain(filesiter,
                                    files_from_directory(args.directory))

    messages = []

    parser = etree.XMLParser(remove_blank_text=True)

    for filename in filesiter:
        if filename == "-":
            infile = sys.stdin
            filename = "stdin"
        else:
            infile = open(filename, "r")
        logger.debug("%s: reading", filename)
        with infile as f:
            tree = etree.fromstring(f.read(), parser=parser)
        logger.debug("%s: processing", filename)
        messages.extend(process_tree(tree, filename))

    if args.outfile == "-":
        outfile = sys.stdout
    else:
        outfile = open(args.outfile, "w")

    groupkey = lambda x: x.singular
    messages.sort(key=groupkey)
    with outfile:
        for key, msgs in itertools.groupby(messages, key=groupkey):
            msg = next(iter(msgs))
            if msg.filename or msg.sourceline:
                print(
                    "#: {filename}:{sourceline}".format(
                        filename=msg.filename,
                        sourceline=msg.sourceline),
                    file=outfile)
            if msg.context:
                print("msgctxt {}".format(format_msgstr(msg.context)),
                      file=outfile)
            print("msgid {}".format(format_msgstr(msg.singular)),
                  file=outfile)
            if msg.plural:
                print("msgid_plural {}".format(format_msgstr(msg.plural)),
                      file=outfile)
                print('msgstr[0] ""',
                      file=outfile)
                print('msgstr[1] ""',
                      file=outfile)
            else:
                print('msgstr ""',
                      file=outfile)
            print(file=outfile)
