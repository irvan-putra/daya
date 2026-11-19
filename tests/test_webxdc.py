import io
import unittest
import zipfile

from dayalib.domains import webxdc


VALID = {
    "domain": "webxdc",
    "app": {
        "name": "Shared errands",
        "version": "0.1.0",
        "source_code_url": "https://github.com/irvan-putra/daya",
    },
    "title": "Shared errands",
    "sections": [
        {
            "type": "todo",
            "heading": "This week",
            "storage_key": "xdc-test-errands",
            "items": ["Buy rice"],
        }
    ],
}


def build(recipe):
    model, errors = webxdc.validate(recipe)
    assert not errors, errors
    payload = webxdc.generate(model)
    webxdc.self_check(payload, model)
    return payload


def entries(payload):
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        return {name: zf.read(name).decode("utf-8") for name in zf.namelist()}


class BuildTests(unittest.TestCase):
    def test_valid_recipe_builds_xdc(self):
        payload = build(VALID)
        self.assertTrue(payload.startswith(b"PK"))
        files = entries(payload)
        self.assertEqual(sorted(files), ["index.html", "manifest.toml"])
        self.assertIn("<title>Shared errands</title>", files["index.html"])
        self.assertIn('data-storage-key="xdc-test-errands"', files["index.html"])
        self.assertEqual(
            files["manifest.toml"],
            'version = "0.1.0"\n'
            'name = "Shared errands"\n'
            'source_code_url = "https://github.com/irvan-putra/daya"\n',
        )

    def test_deterministic_bytes(self):
        self.assertEqual(build(VALID), build(VALID))

    def test_source_code_url_optional(self):
        recipe = {
            "domain": "webxdc",
            "app": {"name": "Mini", "version": "1.0.0"},
            "title": "Mini",
            "sections": [{"type": "counter", "label": "x"}],
        }
        files = entries(build(recipe))
        self.assertEqual(
            files["manifest.toml"], 'version = "1.0.0"\nname = "Mini"\n'
        )

    def test_zip_metadata_fixed(self):
        payload = build(VALID)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for info in zf.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))


class ValidateTests(unittest.TestCase):
    def errors(self, recipe):
        _model, errors = webxdc.validate(recipe)
        return errors

    def test_app_required(self):
        errors = self.errors({"domain": "webxdc", "title": "t", "sections": []})
        self.assertIn("app: must be an object", errors)

    def test_name_rules(self):
        for bad in (None, "", "x" * 51, 'has "quote"', "back\\slash", "new\nline", 7):
            recipe = dict(VALID)
            recipe["app"] = {"version": "0.1.0"}
            if bad is not None:
                recipe["app"]["name"] = bad
            errors = self.errors(recipe)
            self.assertTrue(
                any(e.startswith("app.name:") for e in errors),
                "name={!r} should fail".format(bad),
            )

    def test_version_rules(self):
        for bad in (None, "1.0", "v1.0.0", "1.0.0-beta", "latest", 5):
            recipe = dict(VALID)
            recipe["app"] = {"name": "ok"}
            if bad is not None:
                recipe["app"]["version"] = bad
            errors = self.errors(recipe)
            self.assertTrue(
                any(e.startswith("app.version:") for e in errors),
                "version={!r} should fail".format(bad),
            )

    def test_source_code_url_rules(self):
        for bad in ("http://insecure.example", "ftp://x", "not a url", 'quo"te',
                    "https://ok.example/bad path", "https://" + "x" * 220):
            recipe = dict(VALID)
            recipe["app"] = dict(VALID["app"], source_code_url=bad)
            errors = self.errors(recipe)
            self.assertTrue(
                any(e.startswith("app.source_code_url:") for e in errors),
                "url={!r} should fail".format(bad),
            )

    def test_unknown_app_field(self):
        recipe = dict(VALID)
        recipe["app"] = dict(VALID["app"], icon="evil.png")
        self.assertIn("app: unknown field 'icon'", self.errors(recipe))

    def test_unknown_top_field(self):
        recipe = dict(VALID, script="alert(1)")
        self.assertIn("recipe: unknown field 'script'", self.errors(recipe))

    def test_page_validation_errors_propagate(self):
        recipe = dict(VALID, sections=[{"type": "todo"}])
        errors = self.errors(recipe)
        self.assertTrue(any(e.startswith("sections[0].storage_key:") for e in errors))

    def test_page_fields_still_required(self):
        recipe = {"domain": "webxdc", "app": {"name": "x", "version": "0.1.0"}}
        errors = self.errors(recipe)
        self.assertTrue(any(e.startswith("title:") for e in errors))
        self.assertTrue(any(e.startswith("sections:") for e in errors))


if __name__ == "__main__":
    unittest.main()
