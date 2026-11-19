"""Command line interface for daya."""

import argparse
import hashlib
import json
import sys

from . import __version__
from .domains import DOMAINS
from .recipe import RecipeError, load_recipe


def _load_domain(recipe_path):
    data = load_recipe(recipe_path)
    name = data.get("domain")
    if not isinstance(name, str):
        raise RecipeError('{}: missing "domain" field'.format(recipe_path))
    domain = DOMAINS.get(name)
    if domain is None:
        raise RecipeError(
            "{}: unknown domain {!r}; available: {}".format(
                recipe_path, name, ", ".join(sorted(DOMAINS))
            )
        )
    return data, domain


def _report_recipe_error(recipe_path, exc):
    print("error: {}".format(exc), file=sys.stderr)
    return 2


def cmd_build(args):
    try:
        data, domain = _load_domain(args.recipe)
    except RecipeError as exc:
        return _report_recipe_error(args.recipe, exc)
    model, errors = domain.validate(data)
    if errors:
        for line in errors:
            print("error: {}: {}".format(args.recipe, line), file=sys.stderr)
        return 2
    output_text = domain.generate(model)
    try:
        domain.self_check(output_text, model)
    except ValueError as exc:
        print("internal error: {}".format(exc), file=sys.stderr)
        return 1
    payload = output_text.encode("utf-8")
    with open(args.output, "wb") as fh:
        fh.write(payload)
    digest = hashlib.sha256(payload).hexdigest()
    print("built {} ({} bytes, sha256 {})".format(args.output, len(payload), digest))
    return 0


def cmd_validate(args):
    try:
        data, domain = _load_domain(args.recipe)
    except RecipeError as exc:
        return _report_recipe_error(args.recipe, exc)
    _model, errors = domain.validate(data)
    if errors:
        for line in errors:
            print("error: {}: {}".format(args.recipe, line), file=sys.stderr)
        return 2
    print("{}: valid {} recipe".format(args.recipe, data["domain"]))
    return 0


def cmd_domains(args):
    for name in sorted(DOMAINS):
        print("{}: {}".format(name, DOMAINS[name].DESCRIPTION))
    return 0


def cmd_schema(args):
    domain = DOMAINS.get(args.domain)
    if domain is None:
        print(
            "error: unknown domain {!r}; available: {}".format(
                args.domain, ", ".join(sorted(DOMAINS))
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(domain.schema(), indent=2, sort_keys=True))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="daya",
        description=(
            "Deterministic code generator: small structured recipes in, "
            "validated tested code out."
        ),
    )
    parser.add_argument("--version", action="version", version="daya " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="validate a recipe and write the generated code")
    build.add_argument("recipe", help="path to a recipe JSON file")
    build.add_argument("-o", "--output", required=True, help="file to write")
    build.set_defaults(func=cmd_build)

    validate = sub.add_parser("validate", help="check a recipe without generating code")
    validate.add_argument("recipe", help="path to a recipe JSON file")
    validate.set_defaults(func=cmd_validate)

    domains = sub.add_parser("domains", help="list available domains")
    domains.set_defaults(func=cmd_domains)

    schema = sub.add_parser("schema", help="print a domain's recipe schema")
    schema.add_argument("domain", help="domain name, see: daya domains")
    schema.set_defaults(func=cmd_schema)

    args = parser.parse_args(argv)
    return args.func(args)
